"""Install/upgrade/reinstall/uninstall only the isolated Update Test edition."""
import hashlib,json,os,sqlite3,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from sfx_vault.core import Catalog,inspect_audio
from sfx_vault.workflow import create_collection,change_members

def run():
    work=ROOT/'test-data/v07'; install=work/'installed'; profile=work/'profile'; profile.mkdir(parents=True,exist_ok=True)
    database=profile/'catalog.sqlite3'; catalog=Catalog(database)
    samples=ROOT/'test-data/v04-reaper/samples'; before={str(p):[p.stat().st_size,p.stat().st_mtime_ns,hashlib.sha256(p.read_bytes()).hexdigest()] for p in samples.iterdir() if p.suffix in ('.wav','.mp3')}
    for name in before: catalog.register(inspect_audio(name),'managed')
    rows=catalog.rows(); catalog.update(rows[0]['id'],display='Installer test manual name',tags='keep,manual',favorite=1)
    pending=work/'pending-review.wav'
    if not pending.exists():
        import shutil
        shutil.copyfile(next(samples.glob('*.wav')),pending)
    catalog.register(inspect_audio(pending),'pending')
    with catalog.db:
        catalog.db.execute("""INSERT OR IGNORE INTO import_history(sound_id,generation,path,original,detected,category,status,sha)
            SELECT id,generation,path,original,added,category,status,sha FROM sounds WHERE status='pending'""")
    if not catalog.db.execute('SELECT 1 FROM collections').fetchone():
        collection=create_collection(catalog,'Update retention'); change_members(catalog,collection,[rows[0]['id']])
    catalog.configure('import_folders',[dict(path=str(work/'offline-watch'),enabled=False,recursive=True)])
    catalog.configure('updates',dict(repository='TobiTired/SFX-Vault',automatic=False,declined='0.7.9'))
    catalog.close()
    def snapshot():
        db=sqlite3.connect(database)
        try:
            return {table:db.execute(f'SELECT * FROM {table}'+(" WHERE key!='ui_layout'" if table=='settings' else '')).fetchall() for table in ('sounds','collections','collection_members','settings','import_history')}
        finally: db.close()
    saved=snapshot(); env=os.environ.copy(); env.pop('PYTHONPATH',None); env.pop('PYTHONHOME',None); env['PATH']=os.environ.get('SystemRoot','C:\\Windows')+'\\System32'
    phases=[]
    for index,version in enumerate(('0.7.0','0.7.1','0.7.1')):
        setup=ROOT/f'release/test/{version}/SFX-Vault-Setup-{version}.exe'
        command=[str(setup),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-',f'/DIR={install}','/TASKS=desktopicon',f'/LOG={work}/setup-{index}.log']
        result=subprocess.run(command,env=env,timeout=180); assert result.returncode==0,result.returncode
        exe=install/'SFX Vault.exe'; assert exe.exists()
        report=work/f'installed-{index}.json'
        process=subprocess.Popen([str(exe),'--data-dir',str(profile),'--verify-install',str(report)],cwd=install,env=env)
        process.wait(timeout=60); assert report.exists(),'Installed diagnostic did not run'
        evidence=json.loads(report.read_text()); assert evidence['version']==version and evidence['frozen'] and evidence['rows']==4 and evidence['search_rows']==2,evidence
        assert len(evidence['playback'])==2 and all(item['progress'] for item in evidence['playback']),evidence
        assert snapshot()==saved,'Catalog or preferences changed during installation'
        phases.append(dict(phase=('clean install','upgrade','reinstall')[index],**evidence))
    uninstaller=install/'unins000.exe'; result=subprocess.run([str(uninstaller),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',f'/LOG={work}/uninstall.log'],timeout=120)
    assert result.returncode==0
    import time
    deadline=time.monotonic()+30
    while (install/'SFX Vault.exe').exists() and time.monotonic()<deadline: time.sleep(.2)
    assert not (install/'SFX Vault.exe').exists(); assert snapshot()==saved
    for name,expected in before.items():
        p=Path(name); assert [p.stat().st_size,p.stat().st_mtime_ns,hashlib.sha256(p.read_bytes()).hexdigest()]==expected
    (work/'installer-results.json').write_text(json.dumps(dict(phases=phases,uninstalled=True,catalog_retained=True,audio_unchanged=len(before)),indent=2))
    print('PASS: clean install, Python-free launch, WAV/MP3 playback, upgrade, reinstall, uninstall, catalog and source retention.')

if __name__=='__main__': run()
