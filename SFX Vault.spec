# Build with: .venv\Scripts\python.exe -m PyInstaller --noconfirm "SFX Vault.spec"
from pathlib import Path
import os,json
from PyInstaller.utils.win32.versioninfo import VSVersionInfo,FixedFileInfo,StringFileInfo,StringTable,StringStruct,VarFileInfo,VarStruct
root=Path(SPECPATH)
version=os.environ.get('SFX_BUILD_VERSION','0.7.0')
parts=tuple(int(n) for n in version.split('.'))+(0,)
metadata=root/'build'/('metadata-'+version+'-'+os.environ.get('SFX_TEST_BUILD','0')); metadata.mkdir(parents=True,exist_ok=True)
(metadata/'build-info.json').write_text(json.dumps(dict(version=version,repository=os.environ.get('SFX_BUILD_REPO','TobiTired/SFX-Vault'),test=os.environ.get('SFX_TEST_BUILD')=='1')))
version_file=metadata/'version.txt'
version_file.write_text(str(VSVersionInfo(ffi=FixedFileInfo(filevers=parts,prodvers=parts,mask=0x3f,flags=0,OS=0x40004,fileType=1,subtype=0,date=(0,0)),kids=[StringFileInfo([StringTable('040904B0',[StringStruct('FileDescription','SFX Vault'),StringStruct('FileVersion',version),StringStruct('ProductName','SFX Vault'),StringStruct('ProductVersion',version)])]),VarFileInfo([VarStruct('Translation',[1033,1200])])])))
a=Analysis([str(root/'tools/app_entry.py')],pathex=[str(root)],
    binaries=[],datas=[(str(root/name),'sfx_vault/'+str(Path(name).parent.relative_to('sfx_vault'))) for name in (root/'publication-files.txt').read_text('utf-8').splitlines() if name.startswith('sfx_vault/assets/')]+[(str(metadata/'build-info.json'),'sfx_vault')],
    hiddenimports=[],hookspath=[],hooksconfig={},runtime_hooks=[],excludes=[],noarchive=False)
# Qt uses Windows' system ICU API. An unrelated Poppler/Conda icuuc.dll on PATH
# has a different export set and must not shadow the Windows component.
a.binaries=[entry for entry in a.binaries if Path(entry[0]).name.lower()!='icuuc.dll']
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='SFX Vault',debug=False,
    bootloader_ignore_signals=False,strip=False,upx=False,console=False,
    icon=str(root/'sfx_vault/assets/sfx-vault.ico'),version=str(version_file))
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='SFX Vault')


