"""Explicit, checksummed GitHub installer updates. No catalog/audio mutations."""
from dataclasses import dataclass
import hashlib,json,os,re,shutil,subprocess,sys,tempfile,time
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlparse

class UpdateError(Exception): pass

def version_tuple(value):
    if not isinstance(value,str) or not re.fullmatch(r'v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)',value):
        raise UpdateError('Expected a stable version such as 0.7.1.')
    return tuple(map(int,value.lstrip('v').split('.')))

def repository(value):
    value=value.strip()
    if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9_.-]+',value) or value.split('/')[1] in ('.','..'):
        raise UpdateError('Enter a GitHub repository as owner/repository.')
    return value

def releases_url(repo): return 'https://github.com/'+repository(repo)+'/releases'

def checked_url(url):
    p=urlparse(url)
    if p.scheme!='https' or p.hostname not in ('api.github.com','github.com','objects.githubusercontent.com','release-assets.githubusercontent.com') or p.username or p.password or p.port not in (None,443):
        raise UpdateError('Release uses an unsupported download address.')
    return url

@dataclass(frozen=True)
class Release:
    version:str
    notes:str
    url:str
    size:int
    sha256:str
    page:str
    test:bool=False

class GitHubClient:
    def __init__(self,repo): self.repo=repository(repo)
    def open(self,url):
        checked_url(url)
        response=urlopen(Request(url,headers={'Accept':'application/vnd.github+json','User-Agent':'SFX-Vault-Updater','X-GitHub-Api-Version':'2026-03-10'}),timeout=20)
        try: checked_url(response.geturl())
        except Exception: response.close(); raise
        return response
    def read(self,url,limit):
        with self.open(url) as response: data=response.read(limit+1)
        if len(data)>limit: raise UpdateError('Release response is too large.')
        return data
    def latest(self,current):
        try: document=json.loads(self.read(f'https://api.github.com/repos/{self.repo}/releases/latest',2*1024*1024))
        except Exception as exc: raise UpdateError('Cannot check GitHub. Check the repository, connection and API rate limit, then retry.') from exc
        return self.parse(document,current)
    def parse(self,document,current):
        try:
            if not isinstance(document,dict) or document.get('draft') is not False or document.get('prerelease') is not False: raise UpdateError('The release is not a published stable release.')
            tag=document['tag_name']; version_tuple(tag); version=tag.lstrip('v')
            if version_tuple(version)<=version_tuple(current): return None
            notes=document.get('body')
            if notes is None: notes=''
            if not isinstance(notes,str): raise UpdateError('Invalid release notes.')
            assets=document['assets']; name=f'SFX-Vault-Setup-{version}.exe'
            matches=[a for a in assets if a.get('name')==name and a.get('state')=='uploaded']
            if len(matches)!=1: raise UpdateError('Release must contain exactly one matching Windows setup installer.')
            asset=matches[0]; url=checked_url(asset['browser_download_url'])
            expected=f'https://github.com/{self.repo}/releases/download/{tag}/'
            if not url.startswith(expected) or url.rsplit('/',1)[-1]!=name: raise UpdateError('Installer belongs to an unexpected repository or release.')
            size=asset['size']
            if type(size)!=int or not 64<=size<=1024**3: raise UpdateError('Invalid installer size.')
            digest=asset.get('digest','') or ''
            if re.fullmatch(r'sha256:[0-9a-fA-F]{64}',digest): checksum=digest[7:].lower()
            else:
                sidecars=[a for a in assets if a.get('name')=='SHA256SUMS.txt' and a.get('state')=='uploaded']
                if len(sidecars)!=1: raise UpdateError('No SHA-256 digest or checksum file was published. Installation is blocked.')
                sideurl=checked_url(sidecars[0]['browser_download_url'])
                if sideurl!=expected+'SHA256SUMS.txt': raise UpdateError('Unexpected checksum address.')
                lines=self.read(sideurl,65536).decode('utf-8').splitlines()
                checks=[line.split()[0].lower() for line in lines if len(line.split())==2 and line.split()[1].lstrip('*')==name]
                if len(checks)!=1 or not re.fullmatch('[0-9a-f]{64}',checks[0]): raise UpdateError('Malformed installer checksum.')
                checksum=checks[0]
            return Release(version,notes[:65536],url,size,checksum,releases_url(self.repo))
        except (KeyError,TypeError,ValueError,AttributeError) as exc: raise UpdateError('Malformed GitHub release; no files were installed.') from exc
    def stream(self,release): return self.open(release.url)

class LocalTestClient:
    """Only enabled by explicit --test-update. Never used by production checking."""
    def __init__(self,manifest): self.manifest=Path(manifest).resolve()
    def latest(self,current):
        data=json.loads(self.manifest.read_text('utf-8')); path=(self.manifest.parent/data['installer']).resolve()
        if not path.is_relative_to(self.manifest.parent) or not path.is_file(): raise UpdateError('Invalid local test installer.')
        version_tuple(data['version'])
        if version_tuple(data['version'])<=version_tuple(current): return None
        if not re.fullmatch('[0-9a-f]{64}',data['sha256']): raise UpdateError('Invalid local test checksum.')
        return Release(data['version'],data['notes'],str(path),path.stat().st_size,data['sha256'],'',True)
    def stream(self,release): return Path(release.url).open('rb')

def download(client,release,progress=lambda *_:None,cancelled=lambda:False,cache=None):
    folder=Path(tempfile.mkdtemp(prefix='sfx-vault-update-',dir=cache)); partial=folder/'installer.part'; target=folder/f'SFX-Vault-Setup-{release.version}.exe'
    try:
        count=0; digest=hashlib.sha256()
        with client.stream(release) as source,partial.open('xb') as output:
            while True:
                if cancelled(): raise UpdateError('Download cancelled. The installed app is unchanged.')
                chunk=source.read(256*1024)
                if not chunk: break
                count+=len(chunk)
                if count>release.size: raise UpdateError('Download exceeds the published size.')
                output.write(chunk); digest.update(chunk); progress(count,release.size)
            output.flush(); os.fsync(output.fileno())
        if count!=release.size or digest.hexdigest()!=release.sha256: raise UpdateError('Installer checksum or size does not match. Installation is blocked.')
        with partial.open('rb') as stream:
            if stream.read(2)!=b'MZ': raise UpdateError('Downloaded file is not a Windows executable.')
        partial.replace(target); return target
    except Exception:
        # The directory was uniquely created by this function, never a source folder.
        shutil.rmtree(folder); raise

def verify_installer(path,checksum):
    path=Path(path)
    if path.suffix.lower()!='.exe' or not re.fullmatch('[0-9a-f]{64}',checksum): raise UpdateError('Invalid installer request.')
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        if stream.read(2)!=b'MZ': raise UpdateError('Invalid Windows installer.')
        stream.seek(0)
        for block in iter(lambda:stream.read(1024*1024),b''): digest.update(block)
    if digest.hexdigest()!=checksum: raise UpdateError('Installer changed since download.')

def wait_for_process(pid,timeout=120):
    import ctypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32]; kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint32]; kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=kernel.OpenProcess(0x100000,False,pid)
    if not handle:
        if ctypes.get_last_error()==87: return
        raise UpdateError('Cannot verify that SFX Vault has exited.')
    try:
        if kernel.WaitForSingleObject(handle,timeout*1000)!=0: raise UpdateError('SFX Vault has not exited. Update cancelled.')
    finally: kernel.CloseHandle(handle)

def installer_helper(path,checksum,parent):
    try:
        wait_for_process(parent); verify_installer(path,checksum)
        subprocess.Popen([str(Path(path).resolve())],close_fds=True)
    except Exception as exc:
        Path(str(path)+'.error.txt').write_text(str(exc),encoding='utf-8')
        if sys.platform=='win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,str(exc)+'\nYour installed application and catalog were retained.','SFX Vault update',0x10)

def start_installer_helper(path,checksum):
    command=([sys.executable] if getattr(sys,'frozen',False) else [sys.executable,'-m','sfx_vault'])
    return subprocess.Popen(command+['--install-update',str(path),'--installer-sha256',checksum,'--parent-pid',str(os.getpid())],close_fds=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
