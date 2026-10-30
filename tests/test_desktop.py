import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from sfx_vault.__main__ import Window
from sfx_vault.core import Catalog, inspect_audio
from test_core import sample
from sfx_vault.organization_ui import OrganizationDialog
from PySide6.QtTest import QTest
from unittest.mock import patch
from PySide6.QtWidgets import QMessageBox, QPushButton
from sfx_vault.imports import ImportMonitor, reconsider
from sfx_vault.import_ui import ImportSettings
import time

class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.slot_errors = []
        hook = patch('sys.excepthook', lambda kind, value, trace: self.slot_errors.append(str(value)))
        hook.start(); self.addCleanup(hook.stop)
        self.addCleanup(lambda: self.assertEqual(self.slot_errors, [], 'Unhandled Qt slot errors'))
    def test_close_during_background_monitoring(self):
        app = QApplication.instance() or QApplication([])
        class SlowMonitor:
            def poll(self, catalog, progress, cancelled, **kwargs):
                for _ in range(50):
                    if cancelled(): break
                    time.sleep(.01)
                return dict(new=0, waiting=0, errors=[])
        with tempfile.TemporaryDirectory() as directory:
            window = Window(Path(directory) / 'catalog.db'); window.monitor = SlowMonitor()
            window.start_import_task('poll'); window.close()
            deadline = time.monotonic() + 5
            while window.import_worker.isRunning() and time.monotonic() < deadline: QTest.qWait(10)
            app.processEvents(); self.assertFalse(window.import_worker.isRunning()); window.close()
    def test_pending_badge_filters_matching_preview_and_history(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); folder = root / 'downloads'; folder.mkdir()
            window = Window(root / 'catalog.db')
            window.catalog.configure('import_folders', [dict(path=str(folder), enabled=True, recursive=True)])
            for name in ['rain-storm-thunder.wav', 'door.wav', 'mystery.wav']: sample(folder / name)
            current = [100.]; monitor = ImportMonitor(lambda: current[0]); monitor.poll(window.catalog); current[0] += 6; monitor.poll(window.catalog)
            window.populate_nav(); self.assertEqual(window.nav.item(3).text(), 'Pending Review (3)')
            window.nav.setCurrentRow(3)
            self.assertEqual(window.table.rowCount(), 3)
            selected = window.table.selectionModel().selectedRows(); self.assertEqual(len(selected), 1)
            high = window.table.item(selected[0].row(), 0).data(256); self.assertGreaterEqual(high['confidence'], .75)
            window.table.setCurrentCell(selected[0].row(), 0); window.table.selectRow(selected[0].row())
            self.assertEqual(window.duplicate_choices.count(), 2)
            with patch.object(window, 'play_path') as play:
                window.preview_duplicate(); self.assertNotEqual(play.call_args.args[0], high['path'])
            window.confidence_filter.setCurrentText('Low (<50%)'); self.assertEqual(window.table.rowCount(), 1)
            window.import_category.setCurrentText('Doors'); self.assertEqual(window.table.rowCount(), 0)
            window.import_category.setCurrentIndex(0); window.confidence_filter.setCurrentIndex(0)
            window.select_all_visible()
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes): window.review('rejected')
            deadline = time.monotonic() + 10
            while window.import_worker.isRunning() and time.monotonic() < deadline: QTest.qWait(10)
            app.processEvents(); self.assertEqual(window.table.rowCount(), 0); self.assertEqual(window.nav.item(3).text(), 'Pending Review (0)')
            window.nav.setCurrentRow(5); self.assertEqual(window.table.rowCount(), 3)
            self.assertTrue(window.name.isReadOnly()); self.assertFalse(window.approve_import_button.isEnabled())
            window.table.selectRow(0)
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes): window.reconsider_rejected()
            deadline = time.monotonic() + 10
            while window.import_worker.isRunning() and time.monotonic() < deadline: QTest.qWait(10)
            app.processEvents(); self.assertEqual(len(window.catalog.rows(view='Pending Review')), 1)
            window.close(); app.processEvents()
    def test_import_settings_persist_and_monitor_refresh_preserves_edits(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); window = Window(root / 'catalog.db')
            dialog = ImportSettings(window); dialog.add_row(dict(path=str(root / 'downloads'), enabled=False, recursive=False))
            dialog.interval.setValue(17); dialog.enabled.setChecked(False)
            from PySide6.QtWidgets import QDialogButtonBox
            dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).click()
            self.assertEqual(window.catalog.setting('import_options', {})['interval'], 17)
            self.assertFalse(window.catalog.setting('import_folders', [])[0]['recursive'])
            path = root / 'door.wav'; sample(path); window.catalog.register(inspect_audio(path), 'pending')
            window.populate_nav(); window.nav.setCurrentRow(3); window.table.selectRow(0)
            window.name.setText('Unsaved correction'); window.dirty()
            other = Catalog(root / 'catalog.db')
            extra = root / 'rain.wav'; sample(extra); other.register(inspect_audio(extra), 'pending'); other.close()
            window.import_complete(dict(new=1))
            self.assertEqual(window.name.text(), 'Unsaved correction'); self.assertTrue(window.form_dirty)
            window.close(); app.processEvents()
    def test_rescan_button_runs_managed_scan_without_monitoring(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); audio = root / 'library' / 'rain.wav'; sample(audio)
            window = Window(root / 'catalog.db'); window.catalog.configure('roots', [str(audio.parent)])
            window.catalog.configure('import_options', dict(stable_seconds=.01))
            self.assertFalse(window.poll.isActive())
            next(b for b in window.findChildren(QPushButton) if b.text() == 'Rescan').click()
            self.assertIsNotNone(window.worker)
            deadline = time.monotonic() + 10
            while window.worker.isRunning() and time.monotonic() < deadline: QTest.qWait(10)
            app.processEvents(); self.assertEqual(len(window.catalog.rows(view='Pending Review')), 1)
            self.assertEqual(len(window.catalog.rows()), 0)
            window.close(); app.processEvents()
    def test_organization_review_filters_and_preview(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); audio = root / 'rain.wav'; sample(audio)
            window = Window(root / 'catalog.db'); window.catalog.register(inspect_audio(audio), 'managed')
            dialog = OrganizationDialog(window, True)
            deadline = time.monotonic() + 10
            while dialog.worker.isRunning() and time.monotonic() < deadline: QTest.qWait(10)
            app.processEvents()
            self.assertEqual(len(dialog.proposals), 1); self.assertFalse(dialog.approve.isEnabled())
            self.assertEqual(window.catalog.db.execute('SELECT count(*) FROM organization').fetchone()[0], 0)
            dialog.close()
            dialog = OrganizationDialog(window, False)
            deadline = time.monotonic() + 10
            while dialog.worker.isRunning() and time.monotonic() < deadline: QTest.qWait(10)
            app.processEvents(); self.assertEqual(len(dialog.proposals), 1)
            dialog.table.item(0, 2).setText('Quiet evening')
            dialog.confidence.setCurrentText('High (75%+)'); self.assertTrue(dialog.table.isRowHidden(0))
            dialog.select_visible(); self.assertFalse(dialog.table.selectionModel().selectedRows())
            dialog.confidence.setCurrentText('All confidence'); dialog.select_visible()
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes): dialog.decide(True)
            self.assertEqual(window.catalog.rows()[0]['display'], 'Quiet evening')
            self.assertEqual(window.catalog.rows()[0]['edited'], 1)
            dialog.close(); window.close(); app.processEvents()
    def test_edit_review_and_player(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); audio = root / 'rain.wav'; sample(audio)
            window = Window(root / 'catalog.db')
            window.catalog.register(inspect_audio(audio), 'pending')
            window.nav.setCurrentRow(3); window.refresh(); window.table.selectRow(0)
            self.assertEqual(window.selected['original'], 'rain.wav')
            window.name.setText('Evening rain'); window.save()
            window.table.selectRow(0)
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes): window.review('managed')
            deadline = time.monotonic() + 10
            while window.import_worker.isRunning() and time.monotonic() < deadline: QTest.qWait(10)
            app.processEvents()
            window.nav.setCurrentRow(0); window.refresh(); window.table.selectRow(0)
            self.assertEqual(window.selected['display'], 'Evening rain')
            with patch.object(window.player, 'play'):
                window.play()
                deadline = time.monotonic() + 5
                while window.file_workers and time.monotonic() < deadline: QTest.qWait(10)
                app.processEvents()
                self.assertTrue(window.player.source().toLocalFile().endswith('rain.wav'))
            window.favorite(); self.assertEqual(window.catalog.rows(view='Favorites')[0]['display'], 'Evening rain')
            window.close(); app.processEvents()

if __name__ == '__main__': unittest.main()
