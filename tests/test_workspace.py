import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import struct,tempfile,time,unittest
from unittest.mock import patch
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage,QIcon
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from sfx_vault.__main__ import Window
from sfx_vault.theme import ASSETS,apply_theme
from sfx_vault.core import inspect_audio
from test_core import sample

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.app=QApplication.instance() or QApplication([]); apply_theme(self.app)
        self.errors=[]; hook=patch('sys.excepthook',lambda kind,value,trace:self.errors.append(str(value))); hook.start(); self.addCleanup(hook.stop); self.addCleanup(lambda:self.assertEqual(self.errors,[]))
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.w=Window(self.root/'catalog.db'); path=self.root/'rain.wav'; sample(path)
        self.w.catalog.register(inspect_audio(path),'managed'); self.w.populate_nav(); self.w.refresh()
    def tearDown(self):
        self.w.close(); self.app.processEvents(); self.temp.cleanup()
    def test_layout_persists_collapsed_inspector_density_and_width(self):
        w=self.w; w.show(); self.app.processEvents(); w.split.setSizes([240,800,320]); self.app.processEvents()
        w.density.setCurrentIndex(1); w.inspector_toggle.click(); self.app.processEvents(); w.close()
        self.w=Window(self.root/'catalog.db'); self.w.show(); self.app.processEvents()
        self.assertTrue(self.w.inspector.isHidden()); self.assertFalse(self.w.sidebar.isHidden())
        self.assertEqual(self.w.table.verticalHeader().defaultSectionSize(),48)
        self.w.inspector_toggle.click(); self.app.processEvents(); self.assertGreater(self.w.split.sizes()[2],200)
    def test_small_window_panels_and_pending_tools(self):
        w=self.w; w.show(); w.resize(1000,640); self.app.processEvents()
        self.assertEqual(w.width(),1000); self.assertEqual(w.height(),640)
        self.assertGreater(w.table.viewport().width(),250)
        w.sidebar_toggle.click(); w.inspector_toggle.click(); self.app.processEvents()
        self.assertGreater(w.table.viewport().width(),850)
        w.nav.setCurrentRow(3); self.app.processEvents(); self.assertTrue(w.import_panel.isVisible())
        w.nav.setCurrentRow(0); self.assertFalse(w.import_panel.isVisible())
        self.assertFalse(w.approve_import_button.isVisible())
    def test_counts_favorites_and_preserved_view_keys(self):
        w=self.w; self.assertEqual(w.nav.item(0).data(Qt.UserRole+2),1)
        w.table.selectRow(0); w.favorite_selected()
        self.assertEqual(w.nav.item(1).data(Qt.UserRole+2),1)
        w.nav.setCurrentRow(1); self.assertEqual(w.current_view(),'Favorites'); self.assertEqual(w.table.rowCount(),1)
    def test_ui_settings_do_not_mutate_source_or_schema(self):
        path=self.root/'rain.wav'; before=(path.read_bytes(),path.stat().st_mtime_ns)
        self.w.density.setCurrentIndex(1); self.w.sidebar_toggle.click(); self.w.close()
        self.assertEqual(before,(path.read_bytes(),path.stat().st_mtime_ns))
        self.assertTrue(self.w.windowIcon().availableSizes())
    def test_populated_browser_refresh_and_combined_search_1338(self):
        w=self.w; template=inspect_audio(self.root/'rain.wav')
        for i in range(1337):
            w.catalog.register(template|dict(path=str(self.root/f'nested/rain-{i}.wav'),original=f'rain-{i}.wav'),'managed')
        with w.catalog.db: w.catalog.db.execute("UPDATE sounds SET tags='rain,quiet',category='Ambience / Rain'")
        start=time.monotonic(); w.populate_nav(); w.refresh(); self.app.processEvents(); elapsed=time.monotonic()-start
        self.assertEqual(w.table.rowCount(),1338); self.assertLess(elapsed,5)
        w.search.setText('rain'); w.filter_tags.setText('quiet'); w.refresh()
        self.assertEqual(w.table.rowCount(),1338)
        w.search.setText('unmatched-file'); w.refresh(); self.assertEqual(w.table.rowCount(),0)
        print(f'\n1338-row workspace render: {elapsed:.3f}s')
    def test_ico_has_decodable_transparent_frames_at_all_windows_sizes(self):
        data=(ASSETS/'sfx-vault.ico').read_bytes(); reserved,kind,count=struct.unpack_from('<HHH',data)
        self.assertEqual((reserved,kind,count),(0,1,9)); sizes=[]
        for i in range(count):
            width,height,_,_,planes,bits,length,offset=struct.unpack_from('<BBBBHHII',data,6+16*i)
            size=width or 256; sizes.append(size); image=QImage.fromData(data[offset:offset+length],'PNG')
            self.assertEqual((image.width(),image.height()),(size,size)); self.assertEqual(bits,32)
            self.assertEqual(image.pixelColor(0,0).alpha(),0)
        self.assertEqual(sizes,[16,20,24,32,40,48,64,128,256])
        icon=QIcon(str(ASSETS/'sfx-vault.ico')); self.assertFalse(icon.isNull())
        for size in sizes: self.assertFalse(icon.pixmap(size,size).isNull())

if __name__=='__main__': unittest.main()
