import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import hashlib,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QMessageBox
from sfx_vault.__main__ import Window
from sfx_vault.update_ui import UpdatesDialog,automatic_check
from sfx_vault.updates import Release

class UpdateUITests(unittest.TestCase):
    def setUp(self):
        self.app=QApplication.instance() or QApplication([]); self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.w=Window(self.root/'catalog.db'); self.dialog=UpdatesDialog(self.w)
        self.errors=[]; self.hook=patch('sys.excepthook',lambda kind,value,trace:self.errors.append(str(value))); self.hook.start()
    def tearDown(self):
        self.w.close(); self.app.processEvents(); self.hook.stop(); self.assertEqual(self.errors,[]); self.temp.cleanup()
    def test_opt_in_and_declined_version_persist(self):
        d=self.dialog; self.assertFalse(d.auto.isChecked()); d.repo.setText('TobiTired/SFX-Vault'); d.auto.setChecked(True); self.assertTrue(d.save())
        d.available(Release('0.7.1','Notes','url',100,'a'*64,'')); d.skip()
        settings=self.w.catalog.setting('updates',{}); self.assertTrue(settings['automatic']); self.assertEqual(settings['declined'],'0.7.1')
        d.repo.setText('TobiTired/Other'); d.save(); self.assertNotIn('declined',self.w.catalog.setting('updates',{}))
    def test_auto_disabled_does_not_start_network(self):
        with patch('sfx_vault.update_ui.UpdateWorker') as worker: automatic_check(self.w); worker.assert_not_called()
    def test_plain_text_notes_and_explicit_install_approval(self):
        d=self.dialog; d.available(Release('0.7.1','<script>notes</script>','url',100,'a'*64,'')); self.assertEqual(d.notes.toPlainText(),'<script>notes</script>')
        d.downloaded=self.root/'installer.exe'; self.w.form_dirty=True
        with patch.object(QMessageBox,'question',return_value=QMessageBox.No) as prompt,patch('sfx_vault.update_ui.start_installer_helper') as helper:
            d.install(); helper.assert_not_called(); self.assertIn('Unsaved',prompt.call_args.args[2]); self.assertFalse(self.w.closing)
    def test_corrupt_installer_never_closes_app(self):
        d=self.dialog; d.available(Release('0.7.1','notes','url',100,'a'*64,'')); d.downloaded=self.root/'bad.exe'; d.downloaded.write_bytes(b'corrupt')
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Yes),patch('sfx_vault.update_ui.start_installer_helper') as helper:
            d.install(); helper.assert_not_called(); self.assertFalse(self.w.closing); self.assertIn('blocked',d.status.text())
    def test_backup_committed_before_helper_and_clean_close(self):
        d=self.dialog; data=b'MZtest'; path=self.root/'good.exe'; path.write_bytes(data); d.downloaded=path
        d.available(Release('0.7.1','notes','url',len(data),hashlib.sha256(data).hexdigest(),''))
        self.w.catalog.configure('test-metadata',{'display':'Manual name','favorite':True})
        def verify_backup(*_):
            import sqlite3,json
            backups=list((self.root/'update-backups').glob('*.sqlite3')); self.assertEqual(len(backups),1)
            db=sqlite3.connect(backups[0])
            try: self.assertEqual(json.loads(db.execute("SELECT value FROM settings WHERE key='test-metadata'").fetchone()[0])['display'],'Manual name')
            finally: db.close()
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Yes),patch('sfx_vault.update_ui.start_installer_helper',side_effect=verify_backup) as helper:
            d.install(); helper.assert_called_once(); self.assertTrue(self.w.catalog_closed)
