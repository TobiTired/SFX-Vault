import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import time
import unittest
import inspect
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt, QUrl, QPoint
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QCheckBox, QSlider
from PySide6.QtTest import QTest
from sfx_vault.__main__ import Window
from sfx_vault.core import inspect_audio
from sfx_vault.workflow import create_collection, change_members, usage, record_usage
from sfx_vault.workflow_ui import file_mime, PathCheckWorker, ProductionSettings, execute_drag
from test_core import sample

class FakePlayer:
    def __init__(self): self.url=QUrl(); self.playing=False; self.position=0
    def source(self): return self.url
    def setSource(self,url): self.url=url
    def stop(self): self.playing=False
    def play(self): self.playing=True
    def pause(self): self.playing=False
    def playbackState(self): return QMediaPlayer.PlayingState if self.playing else QMediaPlayer.PausedState
    def setPosition(self,value): self.position=value
    def duration(self): return 10000

class WorkflowDesktopTests(unittest.TestCase):
    def setUp(self):
        self.app=QApplication.instance() or QApplication([])
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.window=Window(self.root/'catalog.db')
        self.errors=[]; hook=patch('sys.excepthook',lambda kind,value,trace:self.errors.append(str(value)))
        hook.start(); self.addCleanup(hook.stop); self.addCleanup(lambda:self.assertEqual(self.errors,[]))
        self.paths=[]
        for name in ['footsteps.wav','rain.wav']:
            path=self.root/name; sample(path); self.paths.append(path)
            self.window.catalog.register(inspect_audio(path),'managed')
        self.window.populate_nav(); self.window.refresh(); self.window.table.selectRow(0)
    def tearDown(self):
        self.window.close()
        deadline=time.monotonic()+5
        while self.window.file_workers and time.monotonic()<deadline: QTest.qWait(10)
        self.app.processEvents(); self.temp.cleanup()
    def test_native_payload_is_urls_not_plain_text_and_copy_only(self):
        rows=[dict(r) for r in self.window.catalog.rows()]
        mime=file_mime(rows)
        self.assertTrue(mime.hasUrls()); self.assertNotIn('text/plain',mime.formats())
        self.assertEqual([Path(u.toLocalFile()) for u in mime.urls()],[Path(r['path']) for r in rows])
        self.assertIn('text/uri-list',mime.formats())
        with patch('sfx_vault.workflow_ui.QDrag') as drag:
            execute_drag(self.window.table,rows)
            drag.return_value.exec.assert_called_once_with(Qt.CopyAction,Qt.CopyAction)
    def test_drag_usage_records_start_even_if_cancelled_not_preview_or_selection(self):
        rows=[dict(r) for r in self.window.catalog.rows()]
        self.assertIsNone(usage(self.window.catalog,rows[0]['id']))
        with patch.object(self.window,'checked_paths',side_effect=lambda records,callback:callback(records,[])), patch.object(QApplication,'mouseButtons',return_value=Qt.LeftButton), patch('sfx_vault.__main__.execute_drag',return_value=Qt.IgnoreAction) as drag:
            self.window.prepare_drag(rows); self.assertEqual(drag.call_count,1)
        self.assertEqual(usage(self.window.catalog,rows[0]['id'])['last_action'],'drag_started')
        with patch.object(self.window,'checked_paths',side_effect=lambda records,callback:callback([],records)), patch('sfx_vault.__main__.execute_drag') as drag:
            self.window.prepare_drag(rows); drag.assert_not_called()
        self.assertEqual(usage(self.window.catalog,rows[0]['id'])['use_count'],1)
    def test_missing_path_worker_and_no_unapproved_drag(self):
        rows=[dict(r) for r in self.window.catalog.rows()]; missing=rows[0]|dict(path=str(self.root/'missing.wav'))
        result=[]; worker=PathCheckWorker([rows[1],missing]); worker.checked.connect(lambda a,b:result.append((a,b))); worker.start()
        deadline=time.monotonic()+5
        while worker.isRunning() and time.monotonic()<deadline: QTest.qWait(10)
        self.app.processEvents(); self.assertEqual(len(result[0][0]),1); self.assertEqual(len(result[0][1]),1)
        self.window.catalog.update(rows[0]['id'],status='pending')
        with patch.object(self.window,'checked_paths') as check: self.window.prepare_drag([rows[0]]); check.assert_not_called()
    def test_drag_stays_inside_original_start_drag_stack_during_background_preflight(self):
        calls=[]
        def drag(table,rows): calls.append([frame.function for frame in inspect.stack()])
        with patch.object(QApplication,'mouseButtons',return_value=Qt.LeftButton), patch('sfx_vault.__main__.execute_drag',side_effect=drag):
            self.window.table.startDrag(Qt.CopyAction)
        self.assertEqual(len(calls),1)
        self.assertIn('startDrag',calls[0])
    def test_shortcuts_text_fields_and_arrows(self):
        w=self.window
        with patch.object(w,'play') as play:
            QTest.keyClick(w.search,Qt.Key_Space); play.assert_not_called()
            QTest.keyClick(w.tags,Qt.Key_Space); play.assert_not_called()
            QTest.keyClick(w.table,Qt.Key_Space); play.assert_called_once()
        before=w.table.currentRow(); QTest.keyClick(w.table,Qt.Key_Down)
        self.assertEqual(w.table.currentRow(),min(before+1,w.table.rowCount()-1))
        current=w.selected['id']; QTest.keyClick(w.table,Qt.Key_D,Qt.ControlModifier)
        self.assertEqual(next(r['favorite'] for r in w.catalog.rows() if r['id']==current),1)
        w.table.selectRow(0); selected=w.selected['id']; QTest.keyClick(w.table,Qt.Key_C,Qt.ControlModifier)
        self.assertTrue(QApplication.clipboard().text().endswith('.wav')); self.assertEqual(usage(w.catalog,selected)['last_action'],'copy_path')
        QTest.keyClick(w.name,Qt.Key_A,Qt.ControlModifier); QTest.keyClick(w.name,Qt.Key_C,Qt.ControlModifier)
        self.assertEqual(usage(w.catalog,selected)['use_count'],1)
    def test_focus_search_and_details_shortcuts(self):
        w=self.window; w.show(); w.activateWindow(); self.app.processEvents()
        w.name.setFocus(); QTest.keyClick(w.name,Qt.Key_F,Qt.ControlModifier); self.app.processEvents()
        self.assertTrue(w.search.hasFocus())
        w.table.setFocus(); QTest.keyClick(w.table,Qt.Key_Return); self.assertTrue(w.name.hasFocus())
        with patch.object(w,'stop_playback') as stop: QTest.keyClick(w.table,Qt.Key_Escape); stop.assert_called_once()
    def test_recent_use_order_places_never_used_last(self):
        w=self.window; ident=w.catalog.rows()[0]['id']; record_usage(w.catalog,[ident],'copy_path')
        w.filter_sort.setCurrentText('Recent use first')
        self.assertEqual(w.table.item(0,0).data(Qt.UserRole)['id'],ident)
        self.assertEqual(w.table.item(1,6).text(),'—')
    def test_latest_preview_wins_restart_pause_and_missing(self):
        w=self.window; w.player=FakePlayer(); callbacks=[]
        with patch.object(w,'checked_paths',side_effect=lambda rows,callback:callbacks.append((rows,callback))):
            w.play_path(str(self.paths[0])); w.play_path(str(self.paths[1]))
            callbacks[1][1](callbacks[1][0],[]); callbacks[0][1](callbacks[0][0],[])
            self.assertEqual(Path(w.player.source().toLocalFile()),self.paths[1]); self.assertTrue(w.player.playing)
            w.play_path(str(self.paths[1])); self.assertFalse(w.player.playing)
            w.player.position=7000; w.play_path(str(self.paths[1]),restart=True); self.assertEqual(w.player.position,0)
            w.play_path(str(self.root/'offline.wav')); callbacks[-1][1]([],callbacks[-1][0]); self.assertTrue(w.player.source().isEmpty())
        self.assertEqual(w.catalog.rows(view='Recently Used'),[])
    def test_auto_preview_debounced_and_disabled(self):
        w=self.window; w.catalog.configure('production_workflow',dict(auto_preview=True))
        with patch.object(w,'play_path') as play:
            w.table.selectRow(1); w.table.selectRow(0); QTest.qWait(170)
            self.assertEqual(play.call_count,1)
            w.catalog.configure('production_workflow',dict(auto_preview=False)); w.table.selectRow(1); QTest.qWait(170)
            self.assertEqual(play.call_count,1)
        self.assertEqual(w.catalog.rows(view='Recently Used'),[])
    def test_volume_settings_collection_filters_reset_and_restart(self):
        w=self.window; scene=create_collection(w.catalog,'Scene'); ident=w.catalog.rows()[0]['id']
        change_members(w.catalog,scene,[ident]); w.populate_nav()
        index=next(i for i in range(w.nav.count()) if w.nav.item(i).data(Qt.UserRole)==f'collection:{scene}')
        w.nav.setCurrentRow(index); self.assertEqual(w.table.rowCount(),1)
        w.filter_min.setValue(10); w.refresh(); self.assertEqual(w.table.rowCount(),0)
        w.reset_filters(); self.assertEqual(w.current_view(),'All Sounds'); self.assertEqual(w.table.rowCount(),2)
        dialog=ProductionSettings(w)
        dialog.findChild(QSlider).setValue(23)
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).click()
        self.assertEqual(w.volume.value(),23)
        w.close(); self.window=Window(self.root/'catalog.db')
        self.assertEqual(self.window.volume.value(),23)
        self.assertEqual(self.window.catalog.rows(filters=dict(collection=scene))[0]['id'],ident)
    def test_click_to_seek(self):
        w=self.window; w.player=FakePlayer(); w.seek.resize(200,20); w.seek.setRange(0,10000)
        QTest.mouseClick(w.seek,Qt.LeftButton,pos=QPoint(100,10))
        self.assertAlmostEqual(w.player.position,5000,delta=100)

if __name__=='__main__': unittest.main()
