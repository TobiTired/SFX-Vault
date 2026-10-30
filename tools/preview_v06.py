"""Disposable, populated UI verification. Never opens the user's catalog."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import sys,time,wave,hashlib,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from sfx_vault.__main__ import Window
from sfx_vault.theme import apply_theme
from sfx_vault.core import Catalog,inspect_audio
from sfx_vault.workflow import create_collection,change_members

ROOT=Path(__file__).resolve().parents[1]/'test-data/v06-preview'

def seed():
    ROOT.mkdir(parents=True,exist_ok=True)
    catalog=Catalog(ROOT/'catalog.sqlite3')
    sounds=[('Ambience / Rain','Rain on a Glass Roof','rain, weather, glass'),('Movement / Footsteps','Barefoot Walking – Hardwood Floor','footsteps, hardwood, indoor'),('Doors','Heavy Door Closing','door, wood, impact'),('Vehicles','City Traffic – Distant Engines','traffic, engine, city'),('Human Sounds','Quiet Breathing','breath, human, quiet'),('Electronics','Computer Interface Beep','electronic, beep, interface'),('Objects','Glass Bottle Set Down','glass, object, impact'),('Fantasy','Magic Spell – Rising Shimmer','magic, spell, shimmer'),('Uncategorized','Unidentified Texture','texture')]
    if not catalog.rows():
        for i in range(1338+8):
            category,title,tags=sounds[i%len(sounds)]; path=ROOT/'audio'/category.split(' / ')[0]/f'{title.replace(" – ","-").replace(" ","-").lower()}-{i+10000}.wav'; path.parent.mkdir(parents=True,exist_ok=True)
            if not path.exists():
                with wave.open(str(path),'wb') as audio:
                    audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000); audio.writeframes(bytes([i%128,0])*800)
            catalog.register(inspect_audio(path),'managed' if i<1338 else 'pending')
            with catalog.db: catalog.db.execute('UPDATE sounds SET display=?,category=?,tags=?,confidence=? WHERE path=?',(title,category,tags,(.85,.65,.35)[i%3],str(path.resolve())))
        with catalog.db:
            catalog.db.execute("UPDATE sounds SET favorite=1 WHERE id%13=0 AND status='managed'")
        collection=create_collection(catalog,'Cinematic Foley'); change_members(catalog,collection,[r['id'] for r in catalog.rows()[:24]])
    with catalog.db:
        for i,row in enumerate(catalog.db.execute('SELECT id FROM sounds ORDER BY id').fetchall()):
            category,title,tags=sounds[i%len(sounds)]
            catalog.db.execute('UPDATE sounds SET display=?,category=?,tags=?,confidence=? WHERE id=?',(title,category,tags,(.85,.65,.35)[i%3],row['id']))
    catalog.close()

def manifest():
    return {str(p.relative_to(ROOT)):[p.stat().st_size,p.stat().st_mtime_ns,hashlib.sha256(p.read_bytes()).hexdigest()] for p in (ROOT/'audio').rglob('*.wav')}

def capture():
    seed(); before=manifest(); app=QApplication.instance() or QApplication([]); apply_theme(app)
    w=Window(ROOT/'catalog.sqlite3'); w.sidebar.show(); w.inspector.show(); w.sidebar_toggle.setChecked(True); w.inspector_toggle.setChecked(True); w.density.setCurrentIndex(0); w.show(); app.processEvents()
    w.resize(1600,950); w.split.setSizes([220,1030,310]); w.table.sortItems(4,Qt.AscendingOrder); w.table.selectRow(1); QTest.qWait(150); w.grab().save(str(ROOT/'library-desktop.png'))
    w.nav.setCurrentRow(3); app.processEvents(); w.table.selectRow(0); QTest.qWait(150); w.grab().save(str(ROOT/'pending-review.png'))
    w.nav.setCurrentRow(0); w.resize(1100,720); w.inspector_toggle.click(); QTest.qWait(150); w.grab().save(str(ROOT/'library-small.png'))
    w.density.setCurrentIndex(1); QTest.qWait(150); w.grab().save(str(ROOT/'expanded-rows.png'))
    w.close(); app.processEvents(); after=manifest(); assert before==after,'Fixture audio changed'
    (ROOT/'source-integrity.json').write_text(json.dumps(dict(files=len(before),unchanged=before==after),indent=2))
    print('Rendered desktop, Pending Review and small workspace; audio files unchanged:',len(before))

if __name__=='__main__': capture()
