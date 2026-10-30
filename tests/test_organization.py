import json
import sqlite3
import time
import unittest
from pathlib import Path
from sfx_vault.core import Catalog, classify, RULES, scan, suggested_name
from sfx_vault.organization import preview, stage, staged, decide, bulk, rename_category
import test_core

class OrganizationTests(unittest.TestCase):
    setUp = test_core.CatalogTests.setUp
    tearDown = test_core.CatalogTests.tearDown
    def proposals(self):
        scan(self.db, [self.audio.parent]); return preview(self.root / 'catalog.db')
    def test_representative_names(self):
        examples = {
            'barefoot-walking-hardwood-floor-75830.mp3': 'Barefoot Walking – Hardwood Floor',
            '001_wooden_door_knocking_02.wav': 'Wooden Door Knocking',
            'pixabay-heavy-rain-123456.mp3': 'Heavy Rain',
            'engine_24bit_48khz.wav': 'Engine 24Bit 48Khz',
            'car-1960.wav': 'Car 1960',
        }
        for source, expected in examples.items(): self.assertEqual(suggested_name(source), expected)
    def test_classification_and_confidence(self):
        self.assertEqual(classify('nested/rain/heavy_rain_window.mp3', '', RULES)[0], 'Ambience / Rain')
        self.assertEqual(classify('nested/doors/wooden_knocking.wav', '', RULES)[0], 'Doors')
        self.assertEqual(classify('nested/mystery.wav', '', RULES), ('Uncategorized', '', 0))
        ambiguous = classify('rain-gun.wav', '', RULES)
        self.assertEqual(ambiguous[0], 'Uncategorized'); self.assertLess(ambiguous[2], .5)
        self.assertEqual(classify('nested/unknown.wav', '{"description":"car engine"}', RULES)[0], 'Vehicles')
    def test_preview_does_not_write(self):
        scan(self.db, [self.audio.parent]); changes = self.db.db.total_changes
        before = self.db.db.execute('SELECT * FROM sounds').fetchall()
        result = preview(self.root / 'catalog.db')
        self.assertEqual(len(result), 1); self.assertEqual(self.db.db.total_changes, changes)
        self.assertEqual([tuple(r) for r in before], [tuple(r) for r in self.db.db.execute('SELECT * FROM sounds')])
        self.assertEqual(self.db.db.execute('SELECT count(*) FROM organization').fetchone()[0], 0)
    def test_approval_rejection_and_no_repeated_processing(self):
        proposals = self.proposals(); stage(self.db, proposals)
        self.assertEqual(decide(self.db, proposals, False), (1, 0))
        stage(self.db, preview(self.root / 'catalog.db')); self.assertEqual(staged(self.db), [])
        self.assertEqual(decide(self.db, proposals, True), (0, 1))
        bulk(self.db, [proposals[0]['id']], 'Reset automatic metadata')
        stage(self.db, preview(self.root / 'catalog.db')); pending = staged(self.db)
        pending[0]['proposed']['display'] = 'My reviewed rain'; pending[0]['custom'] = True
        content = self.audio.read_bytes()
        self.assertEqual(decide(self.db, pending, True), (1, 0))
        scan(self.db, [self.audio.parent]); self.db.close(); self.db = Catalog(self.root / 'catalog.db')
        row = self.db.rows()[0]; self.assertEqual(row['display'], 'My reviewed rain'); self.assertEqual(row['edited'], 1)
        self.assertEqual(self.audio.read_bytes(), content)
    def test_manual_and_stale_protected(self):
        proposals = self.proposals(); stage(self.db, proposals)
        self.db.update(proposals[0]['id'], display='Manual title')
        self.assertEqual(decide(self.db, proposals, True), (0, 1)); self.assertEqual(self.db.rows()[0]['display'], 'Manual title')
        stage(self.db, preview(self.root / 'catalog.db')); self.assertTrue(staged(self.db)[0]['protected'])
        self.assertEqual(decide(self.db, staged(self.db), True), (0, 1))
    def test_bulk_reset_protects_manual_and_tags_merge(self):
        p = self.proposals()[0]; ident = p['id']
        bulk(self.db, [ident], 'Add tags', 'ASMR, rain')
        bulk(self.db, [ident], 'Add tags', 'asmr, window')
        bulk(self.db, [ident], 'Remove tags', 'rain')
        self.assertEqual(self.db.rows()[0]['tags'].count('asmr'), 1); self.assertNotIn('rain', self.db.rows()[0]['tags'])
        bulk(self.db, [ident], 'Category', 'Custom'); bulk(self.db, [ident], 'Subcategory', 'Quiet')
        bulk(self.db, [ident], 'Favorite'); self.assertEqual(self.db.rows(view='Favorites')[0]['category'], 'Custom / Quiet')
        self.assertEqual(bulk(self.db, [ident], 'Reset automatic metadata'), (0, 1))
        bulk(self.db, [ident], 'Unfavorite'); self.assertEqual(self.db.rows(view='Favorites'), [])
    def test_rename_category_descendants_and_rules(self):
        p = self.proposals()[0]; rename_category(self.db, 'Ambience', 'Atmosphere')
        self.assertEqual(self.db.rows()[0]['category'], 'Atmosphere / Rain')
        self.assertTrue(self.db.rows()[0]['edited']); self.assertEqual(self.db.setting('rules', [])[0]['category'], 'Atmosphere / Rain')
    def test_changed_rules_or_source_cannot_apply_stale_proposal(self):
        proposals = self.proposals(); stage(self.db, proposals)
        self.db.configure('rules', [])
        self.assertEqual(decide(self.db, proposals, True), (0, 1))
        self.db.configure('rules', RULES); self.audio.touch(); scan(self.db, [self.audio.parent])
        self.assertEqual(decide(self.db, proposals, True), (0, 1))
    def test_migration_and_backup_idempotent(self):
        self.proposals(); row = self.db.rows()[0]; self.db.update(row['id'], display='V01 edit')
        self.db.db.execute('DROP TABLE organization'); self.db.db.execute('ALTER TABLE sounds DROP COLUMN revision'); self.db.db.execute('PRAGMA user_version=0'); self.db.db.commit(); self.db.close()
        self.db = Catalog(self.root / 'catalog.db')
        self.assertEqual(self.db.rows()[0]['display'], 'V01 edit'); self.assertTrue(self.db.rows()[0]['edited'])
        backup = sqlite3.connect(str(self.root / 'catalog.db.v01-backup.sqlite3'))
        self.assertEqual(backup.execute('SELECT display FROM sounds').fetchone()[0], 'V01 edit'); backup.close()
        self.db.close(); self.db = Catalog(self.root / 'catalog.db'); self.assertEqual(len(self.db.rows()), 1)
    def test_failed_batch_rolls_back_every_change(self):
        proposals = self.proposals()
        other = self.audio.parent / 'door.wav'; test_core.sample(other)
        scan(self.db, [self.audio.parent]); proposals = preview(self.root / 'catalog.db'); stage(self.db, proposals)
        originals = [dict(r) for r in self.db.rows()]
        proposals[0]['proposed']['display'] = 'Should roll back'
        del proposals[1]['proposed']['display']
        with self.assertRaises(KeyError): decide(self.db, proposals, True)
        self.assertEqual([dict(r) for r in self.db.rows()], originals)
        self.assertEqual(len(staged(self.db)), 2)
    def test_1338_catalog_preview_and_search(self):
        for i in range(1338):
            self.db.register(dict(path=str(self.root / 'nested' / f'rain-window-{100000+i}.wav'), original=f'rain-window-{100000+i}.wav', format='WAV', size=100, mtime=0, duration=1., metadata='', sha=str(i)), 'managed')
        start = time.monotonic(); proposals = preview(self.root / 'catalog.db'); elapsed = time.monotonic() - start
        self.assertEqual(len(proposals), 1338)
        stage(self.db, proposals); self.assertEqual(decide(self.db, proposals[:1000], True), (1000, 0))
        self.assertEqual(decide(self.db, proposals[1000:1100], False), (100, 0))
        stage(self.db, preview(self.root / 'catalog.db')); self.assertEqual(len(staged(self.db)), 238)
        self.assertEqual(len(self.db.rows('window')), 1338)
        self.assertLess(elapsed, 10)
        print(f'\n1338-row read-only preview: {elapsed:.3f}s')

if __name__ == '__main__': unittest.main()
