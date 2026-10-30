import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from sfx_vault.core import Catalog, inspect_audio
from sfx_vault.workflow import (create_collection, rename_collection, delete_collection,
    change_members, collections, memberships, record_usage, usage)
from test_core import sample

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.database = self.root/'catalog.db'; self.catalog = Catalog(self.database)
        self.path = self.root/'footsteps.wav'; sample(self.path)
        self.catalog.register(inspect_audio(self.path), 'managed'); self.ident = self.catalog.rows()[0]['id']
    def tearDown(self): self.catalog.close(); self.temp.cleanup()
    def test_collections_many_to_many_persist_and_delete_without_audio_changes(self):
        before = (self.path.read_bytes(), self.path.stat().st_mtime_ns)
        first = create_collection(self.catalog,'Rainy Night'); second = create_collection(self.catalog,'Villain Roleplay')
        change_members(self.catalog,first,[self.ident,self.ident]); change_members(self.catalog,second,[self.ident])
        self.assertEqual(len(memberships(self.catalog,self.ident)),2)
        rename_collection(self.catalog,first,'Stormy Night'); self.catalog.close(); self.catalog=Catalog(self.database)
        self.assertEqual({c['name'] for c in memberships(self.catalog,self.ident)}, {'Stormy Night','Villain Roleplay'})
        change_members(self.catalog,first,[self.ident],add=False); self.assertEqual(len(memberships(self.catalog,self.ident)),1)
        delete_collection(self.catalog,second); self.assertEqual(memberships(self.catalog,self.ident),[])
        self.assertEqual(len(self.catalog.rows()),1); self.assertEqual((self.path.read_bytes(),self.path.stat().st_mtime_ns),before)
    def test_multi_selection_and_pending_not_admitted_to_collections(self):
        path=self.root/'door.wav'; sample(path); self.catalog.register(inspect_audio(path),'managed')
        pending=self.root/'pending.wav'; sample(pending); self.catalog.register(inspect_audio(pending),'pending')
        ident=create_collection(self.catalog,'Scene')
        all_ids=[r[0] for r in self.catalog.db.execute('SELECT id FROM sounds')]
        change_members(self.catalog,ident,all_ids)
        self.assertEqual(len(self.catalog.rows(filters=dict(collection=ident))),2)
        with self.assertRaises(sqlite3.IntegrityError): create_collection(self.catalog,'scene')
        with self.assertRaises(ValueError): create_collection(self.catalog,'   ')
    def test_explicit_usage_actions_and_opt_out(self):
        record_usage(self.catalog,[self.ident,self.ident],'drag_started')
        record_usage(self.catalog,[self.ident],'copy_path')
        self.assertEqual(usage(self.catalog,self.ident)['use_count'],2)
        self.assertEqual(usage(self.catalog,self.ident)['last_action'],'copy_path')
        with self.assertRaises(ValueError): record_usage(self.catalog,[self.ident],'preview')
        self.catalog.configure('production_workflow',dict(track_usage=False)); record_usage(self.catalog,[self.ident],'copy_path')
        self.assertEqual(usage(self.catalog,self.ident)['use_count'],2)
        self.catalog.close(); self.catalog=Catalog(self.database); self.assertEqual(len(self.catalog.rows(view='Recently Used')),1)
    def test_recent_and_frequent_sorting(self):
        path=self.root/'rain.wav'; sample(path); self.catalog.register(inspect_audio(path),'managed')
        other=next(r['id'] for r in self.catalog.rows() if r['id']!=self.ident)
        with patch('sfx_vault.workflow.time.time',return_value=100):
            record_usage(self.catalog,[self.ident],'copy_path'); record_usage(self.catalog,[self.ident],'copy_path')
        with patch('sfx_vault.workflow.time.time',return_value=200): record_usage(self.catalog,[other],'drag_started')
        self.assertEqual(self.catalog.rows(view='Recently Used')[0]['id'],other)
        self.assertEqual(self.catalog.rows(view='Frequently Used')[0]['id'],self.ident)
    def test_combined_category_subcategory_tags_type_duration_favorite_collection_and_usage(self):
        self.catalog.update(self.ident,category='Movement / Footsteps / Hardwood',tags='clothing, Quiet , floor',favorite=1)
        scene=create_collection(self.catalog,'Scene'); other=create_collection(self.catalog,'Other')
        change_members(self.catalog,scene,[self.ident]); record_usage(self.catalog,[self.ident],'copy_path')
        filters=dict(category='Movement',subcategory='Footsteps',tags='QUIET,clothing',favorite=True,
            min_duration=.05,max_duration=10,collection=scene,used=True,availability='available')
        self.assertEqual(len(self.catalog.rows(filetype='WAV',filters=filters)),1)
        self.assertEqual(self.catalog.rows(filetype='MP3',filters=filters),[])
        self.assertEqual(self.catalog.rows(filters=filters|dict(max_duration=.01)),[])
        self.assertEqual(self.catalog.rows(filters=filters|dict(collections=[other])),[])
        change_members(self.catalog,other,[self.ident]); self.assertEqual(len(self.catalog.rows(filters=filters|dict(collections=[other]))),1)
        self.assertEqual(self.catalog.rows(filters=dict(tags='cloth')),[])  # exact tag matching
        self.catalog.db.execute('UPDATE sounds SET missing=1'); self.catalog.db.commit()
        self.assertEqual(self.catalog.rows(filters=filters),[])
        self.assertEqual(len(self.catalog.rows(filters=filters|dict(availability='missing'))),1)
    def test_v03_migration_preserves_library_and_import_tables(self):
        self.catalog.update(self.ident,display='Manual title',tags='keep',favorite=1)
        self.catalog.configure('import_options',dict(enabled=False))
        for table in ['collections','collection_members','sound_usage']: self.catalog.db.execute(f'DROP TABLE {table}')
        self.catalog.db.execute('PRAGMA user_version=3'); self.catalog.db.commit(); self.catalog.close()
        self.catalog=Catalog(self.database); row=self.catalog.rows()[0]
        self.assertEqual((row['display'],row['tags'],row['favorite'],row['status']),('Manual title','keep',1,'managed'))
        self.assertFalse(self.catalog.setting('import_options',{})['enabled'])
        backup=sqlite3.connect(str(self.database)+'.v03-backup.sqlite3')
        self.assertEqual(backup.execute('PRAGMA user_version').fetchone()[0],3); backup.close()
        self.assertEqual(self.catalog.db.execute('PRAGMA user_version').fetchone()[0],4)
        self.assertIsNotNone(self.catalog.db.execute("SELECT name FROM sqlite_master WHERE name='import_history'").fetchone())
    def test_1338_combined_filter_performance(self):
        template=inspect_audio(self.path)
        for i in range(1337):
            self.catalog.register(template|dict(path=str(self.root/f'rain-{i}.wav'),original=f'rain-{i}.wav'), 'managed')
        self.catalog.db.execute("UPDATE sounds SET tags='rain,quiet',category='Ambience / Rain',favorite=1"); self.catalog.db.commit()
        start=time.monotonic()
        rows=self.catalog.rows('rain',filetype='WAV',filters=dict(tags='rain,quiet',category='Ambience',subcategory='Rain',max_duration=10,favorite=True,availability='available'))
        elapsed=time.monotonic()-start
        self.assertEqual(len(rows),1338); self.assertLess(elapsed,5)
        print(f'\n1338-row combined filter: {elapsed:.3f}s')

if __name__=='__main__': unittest.main()
