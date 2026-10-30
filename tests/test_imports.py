import os
import sqlite3
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch
from sfx_vault.core import Catalog, scan, inspect_audio
from sfx_vault.imports import ImportMonitor, review_imports, reconsider, pending_summary, enqueue
from test_core import sample

class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.folder = self.root / 'downloads'; self.folder.mkdir()
        self.database = self.root / 'catalog.db'; self.catalog = Catalog(self.database)
        self.catalog.configure('import_folders', [dict(path=str(self.folder), enabled=True, recursive=True)])
        self.clock = 100.; self.monitor = ImportMonitor(lambda: self.clock)
    def tearDown(self): self.catalog.close(); self.temp.cleanup()
    def poll(self, settle=False):
        result = self.monitor.poll(self.catalog)
        if settle:
            self.clock += 6
            result = self.monitor.poll(self.catalog)
        return result
    def pending(self): return [dict(r) for r in self.catalog.rows(view='Pending Review')]
    def changed_sample(self, path):
        with wave.open(str(path), 'wb') as audio:
            audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000); audio.writeframes(b'\x01\0' * 1600)
    def test_new_nested_detection_and_restart(self):
        path = self.folder / 'nested' / 'wooden-door-knocking.wav'; sample(path)
        self.assertEqual(self.poll(settle=True)['new'], 1)
        self.assertEqual(self.pending()[0]['category'], 'Doors'); self.assertEqual(self.catalog.rows(), [])
        self.catalog.close(); self.catalog = Catalog(self.database); self.monitor = ImportMonitor(lambda: self.clock)
        self.assertEqual(self.poll(settle=True)['new'], 0); self.assertEqual(len(self.pending()), 1)
        missed = self.folder / 'rain.wav'; sample(missed)
        self.monitor = ImportMonitor(lambda: self.clock)
        self.assertEqual(self.poll(settle=True)['new'], 1); self.assertEqual(len(self.pending()), 2)
    def test_disabled_and_nonrecursive_configuration(self):
        sample(self.folder / 'nested' / 'door.wav'); sample(self.folder / 'rain.wav')
        self.catalog.configure('import_folders', [dict(path=str(self.folder), enabled=False, recursive=True)])
        self.assertEqual(self.poll(settle=True)['new'], 0)
        scan(self.catalog, [self.folder]); self.assertEqual(self.catalog.rows(), [])
        self.catalog.configure('import_folders', [dict(path=str(self.folder), enabled=True, recursive=False)])
        self.assertEqual(self.poll(settle=True)['new'], 1); self.assertEqual(self.pending()[0]['original'], 'rain.wav')
    def test_download_stability_and_temporary_files(self):
        path = self.folder / 'door.wav'; sample(path)
        sample(self.folder / 'ignored.wav.part')
        self.assertEqual(self.poll()['new'], 0)
        self.clock += 4; self.changed_sample(path)
        self.assertEqual(self.poll()['new'], 0)
        self.clock += 4; self.assertEqual(self.poll()['new'], 0)
        companion = Path(str(path) + '.crdownload'); companion.write_bytes(b'partial')
        self.clock += 6; self.assertEqual(self.poll()['new'], 0)
        companion.unlink(); self.assertEqual(self.poll()['new'], 1)
        self.assertEqual(len(self.pending()), 1)
    def test_incomplete_and_unreadable_audio_retried(self):
        path = self.folder / 'door.wav'; path.write_bytes(b'RIFF')
        result = self.poll(settle=True); self.assertTrue(result['errors']); self.assertFalse(self.pending())
        sample(path); self.assertEqual(self.poll(settle=True)['new'], 1)
        path = self.folder / 'truncated.wav'; sample(path); path.write_bytes(path.read_bytes()[:-100])
        result = self.poll(settle=True); self.assertTrue(result['errors']); self.assertEqual(len(self.pending()), 1)
    def test_different_name_and_same_batch_duplicates(self):
        existing = self.root / 'library' / 'source.wav'; sample(existing)
        self.catalog.register(inspect_audio(existing), 'managed')
        for name in ('one.wav', 'two.wav'): sample(self.folder / name)
        self.poll(settle=True)
        self.assertEqual(pending_summary(self.catalog)['duplicates'], 2)
        self.assertEqual(len(self.catalog.duplicates(self.pending()[0])), 2)
        result = review_imports(self.catalog, self.pending(), True)
        self.assertEqual(result['skipped'], 2); self.assertEqual(len(self.catalog.rows()), 1)
        result = review_imports(self.catalog, self.pending(), True, 'keep')
        self.assertEqual(result['approved'], 2); self.assertEqual(len(self.catalog.rows()), 3)
        self.assertFalse(self.pending())
    def test_unchanged_files_are_not_rehashed(self):
        sample(self.folder / 'rain.wav'); self.poll(settle=True)
        with patch('sfx_vault.imports.inspect_audio', side_effect=AssertionError('unchanged file rehashed')):
            for _ in range(4): self.poll(settle=True)
        self.assertEqual(len(self.pending()), 1)
    def test_duplicate_toggle_backfills_without_requeuing_rejection(self):
        self.catalog.configure('import_options', dict(duplicates=False))
        sample(self.folder / 'rain.wav'); self.poll(settle=True)
        self.assertEqual(self.pending()[0]['sha'], '')
        review_imports(self.catalog, self.pending(), False)
        self.catalog.configure('import_options', dict(duplicates=True)); self.poll(settle=True)
        self.assertEqual(self.pending(), [])
        row = self.catalog.db.execute('SELECT * FROM sounds').fetchone()
        self.assertTrue(row['sha']); self.assertEqual(row['status'], 'rejected')
    def test_rejection_change_and_explicit_reconsideration(self):
        path = self.folder / 'rain.wav'; sample(path); original = path.read_bytes(); self.poll(settle=True)
        self.assertEqual(review_imports(self.catalog, self.pending(), False)['rejected'], 1)
        self.assertEqual(path.read_bytes(), original); self.poll(settle=True); self.assertFalse(self.pending())
        self.catalog.close(); self.catalog = Catalog(self.database); self.monitor = ImportMonitor(lambda: self.clock)
        self.poll(settle=True); self.assertFalse(self.pending())
        self.changed_sample(path); self.assertEqual(self.poll(settle=True)['new'], 1)
        self.assertEqual(self.catalog.db.execute('SELECT count(*) FROM import_history').fetchone()[0], 2)
        review_imports(self.catalog, self.pending(), False)
        self.assertEqual(reconsider(self.catalog), 1); self.assertEqual(len(self.pending()), 1)
        self.assertEqual(self.catalog.db.execute('SELECT count(*) FROM import_history').fetchone()[0], 3)
    def test_approved_legacy_metadata_remains_approved_on_change(self):
        path = self.folder / 'rain.wav'; sample(path)
        self.catalog.register(inspect_audio(path), 'managed'); row = self.catalog.rows()[0]
        self.catalog.update(row['id'], display='My original name', category='Custom', tags='manual')
        before = path.read_bytes(); self.poll(settle=True)
        self.assertEqual(path.read_bytes(), before); self.assertFalse(self.pending())
        self.changed_sample(path); self.poll(settle=True)
        row = self.catalog.rows()[0]; self.assertEqual(row['display'], 'My original name'); self.assertEqual(row['tags'], 'manual')
        self.assertEqual(row['category'], 'Custom'); self.assertFalse(self.pending())
    def test_overlapping_library_scan_does_not_bypass_review(self):
        path = self.folder / 'nested' / 'door.wav'; sample(path)
        scan(self.catalog, [self.root]); self.assertEqual(len(self.catalog.rows()), 0)
        self.poll(settle=True); scan(self.catalog, [self.root]); self.assertEqual(len(self.catalog.rows()), 0)
        self.assertEqual(len(self.pending()), 1); self.assertEqual(review_imports(self.catalog, self.pending(), True, 'keep')['approved'], 1)
        scan(self.catalog, [self.root]); self.assertEqual(len(self.catalog.rows()), 1)
    def test_confidence_summary_and_batch_decisions(self):
        for name in ['rain-storm-thunder.wav', 'door.wav', 'mystery.wav']: sample(self.folder / name)
        self.poll(settle=True); summary = pending_summary(self.catalog)
        self.assertEqual((summary['high'], summary['medium'], summary['low']), (1, 1, 1))
        rows = self.pending(); self.catalog.update(rows[0]['id'], display='Edited pending name', category='Custom', tags='quiet')
        self.assertEqual(review_imports(self.catalog, [rows[0]], True, 'keep')['stale'], 1)
        rows = self.pending(); self.assertEqual(review_imports(self.catalog, rows[:2], True, 'keep')['approved'], 2)
        self.assertEqual(review_imports(self.catalog, self.pending(), False)['rejected'], 1)
        history = self.catalog.db.execute('SELECT * FROM import_history').fetchall()
        self.assertTrue(all(r['decided'] and r['detected'] for r in history))
        self.assertEqual({r['status'] for r in history}, {'approved', 'rejected'})
    def test_missed_startup_disabled_baseline(self):
        self.catalog.configure('import_options', dict(scan_startup=False))
        sample(self.folder / 'old.wav'); self.assertEqual(self.poll(settle=True)['new'], 0)
        sample(self.folder / 'new.wav'); self.assertEqual(self.poll(settle=True)['new'], 1)
        self.assertEqual(self.pending()[0]['original'], 'new.wav')
    def test_manual_check_can_revisit_skipped_startup_files(self):
        self.catalog.configure('import_options', dict(scan_startup=False))
        sample(self.folder / 'old.wav'); self.poll(settle=True); self.assertFalse(self.pending())
        folders = self.catalog.setting('import_folders', [])
        self.monitor.poll(self.catalog, folders_override=folders); self.clock += 6
        self.assertEqual(self.monitor.poll(self.catalog, folders_override=folders)['new'], 1)
    def test_library_discovery_respects_reserved_paused_scope(self):
        sample(self.folder / 'rain.wav')
        scopes = self.catalog.setting('import_folders', [])
        self.catalog.configure('import_folders', [scopes[0] | dict(enabled=False)])
        library_scope = [dict(path=str(self.root), enabled=True, recursive=True)]
        result = self.monitor.poll(self.catalog, folders_override=library_scope, exclude_scopes=scopes)
        self.clock += 6
        result = self.monitor.poll(self.catalog, folders_override=library_scope, exclude_scopes=scopes)
        self.assertEqual(result['new'], 0); self.assertFalse(self.pending())
    def test_unavailable_folder_and_reconnect(self):
        self.catalog.configure('import_folders', [dict(path=str(self.root / 'offline'), enabled=True, recursive=True)])
        result = self.poll(settle=True); self.assertTrue(result['errors'])
        sample(self.root / 'offline' / 'rain.wav'); self.assertEqual(self.poll(settle=True)['new'], 1)
        self.assertEqual(len(self.pending()), 1)
    def test_changed_file_cannot_be_approved_from_stale_queue(self):
        path = self.folder / 'rain.wav'; sample(path); self.poll(settle=True); rows = self.pending()
        self.changed_sample(path)
        self.assertEqual(review_imports(self.catalog, rows, True, 'keep')['stale'], 1)
        self.assertEqual(len(self.pending()), 1); self.assertFalse(self.catalog.rows())
    def test_database_failure_does_not_lose_pending_decision(self):
        sample(self.folder / 'rain.wav'); self.poll(settle=True)
        self.catalog.db.execute("CREATE TRIGGER fail_history BEFORE UPDATE ON import_history BEGIN SELECT RAISE(ABORT, 'simulated failure'); END")
        with self.assertRaises(sqlite3.IntegrityError): review_imports(self.catalog, self.pending(), False)
        self.assertEqual(len(self.pending()), 1)
        self.assertEqual(self.catalog.db.execute('SELECT status FROM import_history').fetchone()[0], 'pending')
    def test_import_approval_rejection_preserves_source_bytes_and_times(self):
        paths = [self.folder / 'rain.wav', self.folder / 'door.wav']
        for path in paths: sample(path)
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns, p.name) for p in paths}
        self.poll(settle=True); rows = self.pending()
        review_imports(self.catalog, [rows[0]], True, 'keep')
        review_imports(self.catalog, [rows[1]], False)
        scan(self.catalog, [self.root]); self.poll(settle=True)
        for path in paths: self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns, path.name), before[path])
    def test_v02_migration_backup_and_metadata(self):
        path = self.folder / 'rain.wav'; sample(path); self.catalog.register(inspect_audio(path), 'managed')
        row = self.catalog.rows()[0]; self.catalog.update(row['id'], display='V02 manual', tags='keep', favorite=1)
        self.catalog.db.execute('DROP TABLE import_history')
        for name in ('detected', 'decision_at', 'generation'): self.catalog.db.execute(f'ALTER TABLE sounds DROP COLUMN {name}')
        self.catalog.db.execute('PRAGMA user_version=2'); self.catalog.db.commit(); self.catalog.close()
        self.catalog = Catalog(self.database); row = self.catalog.rows()[0]
        self.assertEqual(row['display'], 'V02 manual'); self.assertEqual(row['favorite'], 1); self.assertEqual(row['tags'], 'keep'); self.assertEqual(row['status'], 'managed')
        self.assertTrue(Path(str(self.database) + '.v02-backup.sqlite3').exists())
        backup = sqlite3.connect(str(self.database) + '.v02-backup.sqlite3')
        self.assertEqual(backup.execute('PRAGMA user_version').fetchone()[0], 2); backup.close()
        self.poll(settle=True); self.assertFalse(self.pending())

if __name__ == '__main__': unittest.main()
