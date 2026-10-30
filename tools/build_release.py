"""Reproducible Windows package + per-user Setup + release checksums."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sfx_vault.version import VERSION
from sfx_vault.updates import version_tuple,repository

def build(version,repo='',test=False):
    version_tuple(version)
    if repo: repository(repo)
    subprocess.run([sys.executable,str(ROOT/'tools/privacy_check.py')],cwd=ROOT,check=True)
    output=ROOT/'release'/('test' if test else 'stable')/version; output.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy(); env['SFX_BUILD_VERSION']=version; env['SFX_BUILD_REPO']=repo; env['SFX_TEST_BUILD']='1' if test else '0'
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--distpath',str(output/'app'),'--workpath',str(ROOT/'build'/('test-'+version if test else 'stable-'+version)),str(ROOT/'SFX Vault.spec')],cwd=ROOT,env=env,check=True)
    compiler=Path(os.environ.get('ISCC',r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'))
    if not compiler.is_file(): raise SystemExit('Install Inno Setup 6 or set ISCC to its compiler path.')
    command=[str(compiler),f'/DAppVersion={version}',f'/DAppSource={output/"app/SFX Vault"}',f'/DReleaseOutput={output}']
    if test: command.append('/DTestBuild=yes')
    subprocess.run(command+[str(ROOT/'installer/SFX-Vault.iss')],cwd=ROOT,check=True)
    setup=output/f'SFX-Vault-Setup-{version}.exe'; digest=hashlib.sha256(setup.read_bytes()).hexdigest()
    (output/'SHA256SUMS.txt').write_text(f'{digest}  {setup.name}\n',encoding='utf-8')
    notes=ROOT/'release-notes'/f'{version}.md'
    (output/'RELEASE-NOTES.md').write_text(notes.read_text('utf-8') if notes.exists() else f'SFX Vault {version}\n',encoding='utf-8')
    (output/'release-metadata.json').write_text(json.dumps(dict(tag_name='v'+version,name='SFX Vault '+version,draft=True,prerelease=False,body=(output/'RELEASE-NOTES.md').read_text('utf-8')),indent=2),encoding='utf-8')
    if test:
        (output/'test-update.json').write_text(json.dumps(dict(version=version,installer=setup.name,sha256=digest,notes='Test update '+version+'\nVerifies installer upgrades, version display, explicit approval and catalog retention. No new sound-management features.'),indent=2),encoding='utf-8')
    subprocess.run([sys.executable,str(ROOT/'tools/privacy_check.py'),'--artifacts',str(output)],cwd=ROOT,check=True)
    print('Release ready:',output)
    return output

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--version',default=VERSION); parser.add_argument('--repository',default='TobiTired/SFX-Vault'); parser.add_argument('--test',action='store_true'); args=parser.parse_args()
    build(args.version,args.repository,args.test)
