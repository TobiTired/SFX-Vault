import tempfile
import unittest
import wave
from pathlib import Path
from sfx_vault.core import Catalog, inspect_audio, scan, suggested_name

def sample(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(8000); f.writeframes(b'\0\0' * 800)

class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.db = Catalog(self.root / 'catalog.db'); self.audio = self.root / 'library' / 'rain-window-75830.wav'; sample(self.audio)
    def tearDown(self): self.db.close(); self.temp.cleanup()
    def test_scan_preserves_edits_and_audio(self):
        content = self.audio.read_bytes(); scan(self.db, [self.audio.parent]); row = self.db.rows()[0]
        self.db.update(row['id'], display='My Rain', tags='relaxation', category='Custom')
        scan(self.db, [self.audio.parent]); row = self.db.rows('relaxation')[0]
        self.assertEqual(row['display'], 'My Rain'); self.assertEqual(len(self.db.rows()), 1)
        self.assertEqual(self.audio.read_bytes(), content); self.assertAlmostEqual(row['duration'], .1)
    def test_pending_reject_and_duplicate(self):
        scan(self.db, [self.audio.parent]); other = self.root / 'imports' / 'other.wav'; sample(other)
        stable = {}; scan(self.db, [other.parent], True, stable); self.assertFalse(self.db.rows(view='Pending Review'))
        for path, value in stable.items(): stable[path] = (value[0], value[1] - 10)
        scan(self.db, [other.parent], True, stable); pending = self.db.rows(view='Pending Review')[0]
        self.assertEqual(len(self.db.duplicates(pending)), 1)
        self.db.update(pending['id'], status='rejected'); scan(self.db, [other.parent], True, stable); scan(self.db, [other.parent])
        self.assertFalse(self.db.rows(view='Pending Review')); self.assertTrue(other.exists()); self.assertEqual(len(self.db.rows()), 1)
    def test_offline_retained_missing_detected(self):
        scan(self.db, [self.audio.parent]); self.audio.unlink(); scan(self.db, [self.audio.parent]); self.assertEqual(self.db.rows()[0]['missing'], 1)
        self.audio.parent.rmdir(); scan(self.db, [self.audio.parent]); self.assertEqual(len(self.db.rows()), 1)
    def test_suggestion(self):
        self.assertEqual(suggested_name('barefoot-walking-hardwood-75830.mp3'), 'Barefoot Walking – Hardwood')
    def test_changed_file_keeps_pending(self):
        self.db.register(inspect_audio(self.audio), 'pending'); self.audio.touch(); scan(self.db, [self.audio.parent]); self.assertEqual(len(self.db.rows(view='Pending Review')), 1)
    def test_nested_watched_folder_is_not_auto_approved(self):
        scan(self.db, [self.root], exclude=[self.audio.parent])
        self.assertEqual(len(self.db.rows()), 0)

if __name__ == '__main__': unittest.main()
