"""Fail-closed publication audit. Private rules/reports are never publication inputs."""
import argparse,hashlib,json,os,re,struct,subprocess,sys,types,zipfile,io
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[1]
MANIFEST='publication-files.txt'

def git(*args,binary=False):
    result=subprocess.run(['git','-C',str(ROOT),*args],capture_output=True,check=True)
    return result.stdout if binary else result.stdout.decode('utf-8').strip()

def manifest(root=ROOT):
    entries=[line.strip() for line in (root/MANIFEST).read_text('utf-8').splitlines() if line.strip() and not line.startswith('#')]
    if len(set(entries))!=len(entries): raise ValueError('Duplicate publication paths')
    for name in entries:
        path=PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name or name!=path.as_posix(): raise ValueError('Unsafe publication path')
        forbidden_dirs={'.git','.privacy','sources','build','dist','release','test-data','sample-library','.venv','__pycache__'}
        if any(part.lower() in forbidden_dirs for part in path.parts) or path.name in ('AGENTS.md','PLAN.md','.privacy-local.json') or path.suffix.lower() in ('.env','.log','.sqlite3','.db','.lnk','.pem','.key','.pdb','.tmp'):
            raise ValueError('Private/development file cannot be allowlisted: '+name)
        full=root/name
        if not full.is_file() or full.is_symlink() or not full.resolve().is_relative_to(root.resolve()): raise ValueError('Missing or redirected publication file: '+name)
    return entries

def ignore_rules(entries):
    directories=set()
    for name in entries:
        parent=PurePosixPath(name).parent
        while str(parent)!='.': directories.add(parent.as_posix()); parent=parent.parent
    lines=['# Generated default-deny publication boundary. See publication-files.txt.','/*']
    for folder in sorted(directories,key=lambda p:(p.count('/'),p)):
        lines.extend(['!/'+folder+'/','/'+folder+'/*'])
    lines.extend('!/'+name for name in sorted(entries))
    return '\n'.join(lines)+'\n'

HOME=re.compile(r'(?i)(?:[A-Z]:[\\/]+Users[\\/]+|/(?:Users|home)/)[^\\/\s"\x27<>]+')
EMAIL=re.compile(r'(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b')
SECRET=re.compile(r'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')

def inspect_text(text,policy,private=None):
    findings=[]
    if HOME.search(text): findings.append('personal home-directory path')
    if SECRET.search(text): findings.append('credential/private-key pattern')
    emails={item.lower() for item in EMAIL.findall(text)}
    allowed={policy['identity']['email'].lower(),'noreply@github.com'}
    if emails-allowed: findings.append('unapproved email address')
    for value in (private or {}).get('blocked_terms',[]):
        if re.search(r'(?<![\w])'+re.escape(value)+r'(?![\w])',text,re.I): findings.append('private identity/cross-project rule')
    return sorted(set(findings))

def png_metadata(raw):
    if not raw.startswith(b'\x89PNG\r\n\x1a\n'): return []
    found=[]; offset=8
    while offset+12<=len(raw):
        length=struct.unpack_from('>I',raw,offset)[0]; kind=raw[offset+4:offset+8]
        if offset+12+length>len(raw): return ['malformed PNG']
        if kind in (b'tEXt',b'zTXt',b'iTXt',b'eXIf'): found.append('image metadata requires review')
        offset+=12+length
    return sorted(set(found))

def inspect_bytes(raw,name,policy,private=None):
    result=[]
    if Path(name).suffix.lower() in ('.png','.ico'):
        if name.lower().endswith('.png'): result+=png_metadata(raw)
        elif len(raw)>=6:
            count=struct.unpack_from('<H',raw,4)[0]
            for i in range(count):
                if 6+16*i+16>len(raw): result.append('malformed ICO'); break
                size,offset=struct.unpack_from('<II',raw,6+16*i+8); result+=png_metadata(raw[offset:offset+size])
    else:
        try: result+=inspect_text(raw.decode('utf-8-sig'),policy,private)
        except UnicodeDecodeError: result.append('unexpected binary file in source proposal')
    return sorted(set(result))

def audit_source(staged=False,identity=False):
    entries=manifest(ROOT); policy=json.loads((ROOT/'publication-policy.json').read_text('utf-8'))
    private_path=ROOT/'.privacy-local.json'; private=json.loads(private_path.read_text('utf-8')) if private_path.exists() else {}
    errors=[]; records=[]
    if (ROOT/'.gitignore').read_text('utf-8')!=ignore_rules(entries): errors.append('Default-deny .gitignore does not match the explicit allowlist')
    if staged:
        indexed=set(filter(None,git('ls-files','-z',binary=True).decode('utf-8').split('\0')))
        if indexed!=set(entries): errors.append('Exact staged tree differs from publication allowlist')
        # Also reject symlink/submodule modes, even when the worktree looks ordinary.
        for row in git('ls-files','--stage').splitlines():
            if not row.startswith(('100644 ','100755 ')): errors.append('Unexpected Git entry mode')
    for name in entries:
        raw=git('show',':'+name,binary=True) if staged else (ROOT/name).read_bytes()
        if staged and raw!=(ROOT/name).read_bytes(): errors.append(name+': worktree differs from the audited index')
        findings=inspect_bytes(raw,name,policy,private)
        errors.extend(name+': '+item for item in findings)
        records.append(dict(path=name,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)))
    identities={}
    if identity:
        if not private.get('blocked_terms') or not private.get('binary_blocked_terms'): errors.append('Private identity rules are missing; local publication audit is blocked')
        expected=policy['identity']['name']+' <'+policy['identity']['email']+'>'
        for key in ('GIT_AUTHOR_IDENT','GIT_COMMITTER_IDENT'):
            value=git('var',key); identities[key]=value
            if not value.startswith(expected+' '): errors.append(key+' does not use the approved identity')
        if git('config','--local','--get','user.useConfigOnly')!='true': errors.append('Repository-local explicit identity guard is disabled')
        if git('config','--local','--get','commit.gpgsign')!='false': errors.append('Signing identity has not been isolated')
        if git('config','--local','--get','core.hooksPath')!='.githooks': errors.append('Publication hooks are not installed')
        remotes=git('remote','-v')
        if remotes and any('https://github.com/'+policy['repository']+'.git' not in row for row in remotes.splitlines()): errors.append('Unexpected remote identity/destination')
    return dict(passed=not errors,errors=errors,files=records,identities=identities,scope='index' if staged else 'worktree',private_rules_loaded=bool(private))

def audit_artifacts(folder):
    """Read PE metadata, unpack Python archives in memory, scan every payload file."""
    import pefile
    from PyInstaller.archive.readers import CArchiveReader
    policy=json.loads((ROOT/'publication-policy.json').read_text('utf-8')); private_path=ROOT/'.privacy-local.json'
    private=json.loads(private_path.read_text('utf-8')) if private_path.exists() else {}
    review_path=ROOT/'publication-vendor-review.json'
    review=json.loads(review_path.read_text('utf-8')) if review_path.exists() else {'files':{},'code_strings':{}}
    findings=[]; warnings=[]; records=[]; code_count=0
    # Dependency libraries contain ordinary third-party email credits/locale names;
    # only concrete local identity/path/secret matches are blockers in vendor bytes.
    def binary_findings(raw):
        values=[]
        for encoding in ('utf-8','utf-16le'):
            text=raw.decode(encoding,errors='replace')
            if HOME.search(text): values.append('embedded developer home path')
            if SECRET.search(text): values.append('embedded credential/private key')
            for term in private.get('binary_blocked_terms',[]):
                if re.search(r'(?<![\w])'+re.escape(term)+r'(?![\w])',text,re.I): values.append('embedded private identity')
        return sorted(set(values))
    def code_scan(code,label):
        nonlocal code_count
        if not isinstance(code,types.CodeType): return
        code_count+=1
        for value in [code.co_filename]+[v for v in code.co_consts if isinstance(v,str)]:
            # Standard-library tests/docs include generic emails; app bytecode is stricter.
            issues=inspect_text(value,policy,private) if label.startswith('sfx_vault') else binary_findings(value.encode())
            digest=hashlib.sha256(value.encode()).hexdigest()
            approved=review.get('code_strings',{}).get(label+':'+digest,{})
            for issue in issues:
                if issue in approved.get('findings',[]) and issue=='embedded developer home path':
                    warnings.append(dict(file=label,classification='reviewed standard-library documentation example',sha256=digest,finding=issue))
                else: findings.append(label+': '+issue)
        for value in code.co_consts:
            if isinstance(value,types.CodeType): code_scan(value,label)
    for path in sorted(folder.rglob('*')):
        if not path.is_file(): continue
        name=path.relative_to(folder).as_posix(); raw=path.read_bytes()
        if path.suffix.lower() in ('.log','.db','.sqlite3','.lnk','.pem','.key','.pdb'): findings.append(name+': forbidden release payload')
        issues=binary_findings(raw)
        if path.suffix.lower() in ('.json','.md','.txt','.svg'):
            issues+=inspect_text(raw.decode('utf-8-sig',errors='replace'),policy,private)
        if path.suffix.lower()=='.png': issues+=png_metadata(raw)
        digest=hashlib.sha256(raw).hexdigest(); approved=review.get('files',{}).get(name,{})
        payload_digest=None
        if path.name=='base_library.zip':
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                entries={n:hashlib.sha256(archive.read(n)).hexdigest() for n in sorted(archive.namelist())}
            payload_digest=hashlib.sha256(json.dumps(entries,sort_keys=True).encode()).hexdigest()
        approved_bytes=approved.get('sha256')==digest or (payload_digest is not None and approved.get('payload_sha256')==payload_digest)
        real_key=re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\r\n]+[A-Za-z0-9+/=\r\n]{40,}-----END',raw)
        if real_key: findings.append(name+': private-key material, not just a parser marker')
        for issue in issues:
            if not real_key and approved_bytes and issue in approved.get('findings',[]) and issue in ('embedded developer home path','embedded credential/private key'):
                warnings.append(dict(file=name,classification=approved['classification'],sha256=digest,finding=issue))
            else: findings.append(name+': '+issue)
        record=dict(path=name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
        if payload_digest: record['payload_sha256']=payload_digest
        if path.suffix.lower()=='.exe':
            pe=pefile.PE(data=raw); meta={}
            for group in getattr(pe,'FileInfo',[]):
                for item in group:
                    for table in getattr(item,'StringTable',[]): meta.update({k.decode():v.decode(errors='replace').strip() for k,v in table.entries.items()})
            record['metadata']=meta; record['certificate_bytes']=pe.OPTIONAL_HEADER.DATA_DIRECTORY[4].Size
            for value in meta.values(): findings.extend(name+': '+v for v in inspect_text(value,policy,private))
            if path.name=='SFX Vault.exe':
                archive=CArchiveReader(str(path)); pyz=archive.open_embedded_archive('PYZ.pyz')
                for module in pyz.toc: code_scan(pyz.extract(module),module)
        if path.name=='base_library.zip':
            import marshal
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                for entry in archive.namelist():
                    if entry.endswith('.pyc'): code_scan(marshal.loads(archive.read(entry)[16:]),entry)
        records.append(record)
    sums=folder/'SHA256SUMS.txt'
    if sums.exists():
        for line in sums.read_text('utf-8').splitlines():
            digest,name=line.split(); target=folder/name
            if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest()!=digest: findings.append('Release checksum mismatch')
    return dict(passed=not findings,errors=sorted(set(findings)),reviewed_vendor_findings=warnings,files=records,code_objects=code_count,private_rules_loaded=bool(private),limitations=['Inno compressed payload is not independently extracted; matching unpacked build payload is scanned.','Vendor classifications bind to exact reviewed hashes, not filenames or blanket exclusions.','No claim of absolute anonymity or exhaustive credential detection.'])

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--staged',action='store_true'); parser.add_argument('--identity',action='store_true'); parser.add_argument('--artifacts',type=Path); parser.add_argument('--report',type=Path); parser.add_argument('--write-ignore',action='store_true'); args=parser.parse_args()
    if args.write_ignore: (ROOT/'.gitignore').write_text(ignore_rules(manifest()),encoding='utf-8'); return
    result=audit_artifacts(args.artifacts.resolve()) if args.artifacts else audit_source(args.staged,args.identity)
    if args.report:
        target=args.report.resolve()
        if not target.is_relative_to(ROOT/'.privacy'): raise SystemExit('Reports must stay in the excluded .privacy folder')
        target.parent.mkdir(exist_ok=True); target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='files'},indent=2)); print('Audited files:',len(result['files']))
    if not result['passed']: raise SystemExit(1)

if __name__=='__main__': main()
