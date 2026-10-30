import logging
import os
import sys
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QUrl, QMimeData, QItemSelectionModel, QEventLoop
from PySide6.QtGui import QDesktopServices, QFont, QColor, QShortcut, QKeySequence, QIcon
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QAbstractItemView, QSplitter, QFormLayout, QLabel, QComboBox, QSlider, QFileDialog, QMessageBox, QPlainTextEdit, QDialog, QDialogButtonBox, QCheckBox, QHeaderView, QListWidgetItem, QScrollArea, QDoubleSpinBox, QGridLayout)
from .core import Catalog, CATEGORIES, RULES, scan
from .organization import CONFIDENCES
from .organization_ui import OrganizationDialog, BulkDialog, categories_dialog
from .imports import ImportMonitor, options, pending_summary
from .import_ui import ImportWorker, ImportSettings
from .workflow import preferences, record_usage, collections, memberships, usage, change_members
from .workflow_ui import PathCheckWorker, execute_drag, SeekSlider, CollectionDialog, ProductionSettings
import json
from .workspace_ui import build_workspace, save_layout
from .theme import apply_theme, ASSETS

class SortItem(QTableWidgetItem):
    def __lt__(self, other):
        first, second = self.data(Qt.UserRole+1), other.data(Qt.UserRole+1)
        if first is not None and second is not None: return first < second
        first, second = self.data(Qt.DisplayRole), other.data(Qt.DisplayRole)
        if isinstance(first,(int,float)) and isinstance(second,(int,float)): return first < second
        return self.text().casefold() < other.text().casefold()

class Scanner(QThread):
    finished_scan = Signal(dict)
    progress = Signal(str)
    def __init__(self, database, roots, watched, stable, startup=False):
        super().__init__()
        self.database, self.roots, self.watched, self.stable = database, roots, watched, stable
        self.startup = startup
    def run(self):
        catalog = None
        try:
            catalog = Catalog(self.database)
            # Explicit library scans discover new files through the same review pipeline.
            monitor = ImportMonitor()
            scopes = [dict(path=str(root), enabled=True, recursive=True) for root in self.roots]
            if self.startup and not options(catalog)['scan_startup']: scopes = []
            reserved = catalog.setting('import_folders', [])
            result = monitor.poll(catalog, self.progress.emit, self.isInterruptionRequested, folders_override=scopes, exclude_scopes=reserved)
            if result['waiting'] and not self.isInterruptionRequested():
                self.progress.emit('Waiting for file transfers to stabilize…')
                import time
                deadline = time.monotonic() + options(catalog)['stable_seconds']
                while time.monotonic() < deadline and not self.isInterruptionRequested(): self.msleep(100)
                if not self.isInterruptionRequested():
                    later = monitor.poll(catalog, self.progress.emit, self.isInterruptionRequested, folders_override=scopes, exclude_scopes=reserved)
                    later['new'] += result['new']; later['errors'] = list(dict.fromkeys(result['errors'] + later['errors'])); result = later
            if not self.isInterruptionRequested(): result['errors'] += scan(catalog, self.roots, only_existing=True)
            result['summary'] = pending_summary(catalog, options(catalog)['duplicates'])
        except Exception as exc:
            logging.exception('Scan failed')
            result = dict(errors=[str(exc)])
        finally:
            if catalog: catalog.close()
        self.finished_scan.emit(result)

class SoundTable(QTableWidget):
    action_requested = Signal(str)
    drag_requested = Signal(list)
    def startDrag(self, actions):
        rows = []
        for index in self.selectionModel().selectedRows():
            item = self.item(index.row(), 0)
            if item and item.data(Qt.UserRole)['status'] == 'managed': rows.append(item.data(Qt.UserRole))
        self.drag_requested.emit(rows)
    def keyPressEvent(self, event):
        mods = event.modifiers(); control = Qt.ControlModifier
        action = None
        if mods == Qt.NoModifier:
            action = {Qt.Key_Space:'play', Qt.Key_Escape:'stop', Qt.Key_Return:'details', Qt.Key_Enter:'details'}.get(event.key())
        elif mods == control:
            action = {Qt.Key_C:'copy', Qt.Key_D:'favorite', Qt.Key_R:'restart'}.get(event.key())
        elif mods == (control | Qt.ShiftModifier) and event.key() == Qt.Key_C: action = 'collection'
        if action:
            if not event.isAutoRepeat(): self.action_requested.emit(action)
            event.accept()
        else: super().keyPressEvent(event)

def clock(ms):
    seconds = int(ms / 1000)
    return f'{seconds // 60}:{seconds % 60:02}'

def action_label(value):
    return {'drag_started':'File drag started','copy_path':'Path copied'}.get(value, '—')

class Window(QMainWindow):
    def __init__(self, database):
        super().__init__()
        self.database = database; self.catalog = Catalog(database)
        self.worker = None; self.import_worker = None; self.monitor = ImportMonitor(); self.stable = {}; self.selected = None
        self.form_dirty = False; self.last_view = None; self.closing = False; self.last_import_errors = []
        self.update_workers = []; self.file_workers = []; self.play_request = 0; self.last_selected_id = None
        self.drag_check_pending = False; self.drag_active = False
        build_workspace(self, SoundTable, categories_dialog)
        self.output = QAudioOutput(); self.output.setVolume(self.volume.value()/100)
        self.player = QMediaPlayer(); self.player.setAudioOutput(self.output)
        self.player.positionChanged.connect(self.position); self.player.durationChanged.connect(lambda d: self.seek.setRange(0, d))
        self.player.playbackStateChanged.connect(lambda state: self.play_button.setText("Pause" if state == QMediaPlayer.PlayingState else "Play"))
        self.player.errorOccurred.connect(self.playback_error)
        self.seek.sliderReleased.connect(lambda: self.player.setPosition(self.seek.value()))
        self.volume.valueChanged.connect(self.volume_changed)
        self.table.itemSelectionChanged.connect(self.select); self.table.cellDoubleClicked.connect(lambda *_: self.play())
        self.table.currentCellChanged.connect(lambda *_: self.select())
        self.debounce = QTimer(); self.debounce.setSingleShot(True); self.debounce.setInterval(150); self.debounce.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda: self.debounce.start()); self.types.currentIndexChanged.connect(self.refresh)
        self.confidence_filter.currentIndexChanged.connect(self.refresh)
        self.import_category.currentIndexChanged.connect(self.refresh)
        for control in self.advanced_controls:
            if isinstance(control, QLineEdit): control.textChanged.connect(lambda: self.debounce.start())
            elif isinstance(control, QDoubleSpinBox): control.valueChanged.connect(lambda: self.debounce.start())
            else: control.currentIndexChanged.connect(self.refresh)
        self.nav.currentTextChanged.connect(self.refresh)
        for field in [self.name, self.subcategory, self.tags, self.category.lineEdit()]: field.textEdited.connect(self.dirty)
        self.favorite_check.clicked.connect(self.dirty)
        self.autoplay_timer = QTimer(); self.autoplay_timer.setSingleShot(True); self.autoplay_timer.setInterval(120)
        self.autoplay_timer.timeout.connect(lambda: self.play_path(self.selected['path'], restart=True) if self.selected else None)
        self.search_shortcut = QShortcut(QKeySequence('Ctrl+F'), self); self.search_shortcut.activated.connect(lambda: (self.search.setFocus(), self.search.selectAll()))
        self.populate_nav(); self.nav.setCurrentRow(0); self.refresh()
        self.data_version = self.catalog.db.execute('PRAGMA data_version').fetchone()[0]
        self.poll = QTimer(); self.poll.timeout.connect(self.check_imports)
        self.configure_monitoring()
        self.rescan(startup=True)
    def button(self, layout, text, callback):
        button = QPushButton(text); button.clicked.connect(lambda checked=False: callback())
        if isinstance(layout, QFormLayout): layout.addRow(button)
        else: layout.addWidget(button)
        return button
    def populate_nav(self):
        current = self.current_view()
        cats = self.category_names()
        self.nav.blockSignals(True); self.nav.clear()
        pending = self.catalog.db.execute("SELECT count(*) FROM sounds WHERE status='pending'").fetchone()[0]
        names = ['All Sounds','Favorites','Recently Added','Pending Review','Uncategorized','Import History','Recently Used','Frequently Used']
        def add_nav(name,key=None):
            self.nav.addItem(f'Pending Review ({pending})' if name=='Pending Review' else name)
            item=self.nav.item(self.nav.count()-1); item.setData(Qt.UserRole,key or name)
            kind={'All Sounds':'library','Favorites':'favorite','Pending Review':'pending','Uncategorized':'unknown','Import History':'recent','Recently Added':'recent','Recently Used':'recent','Frequently Used':'recent'}.get(name,'collection' if key and key.startswith('collection:') else 'category')
            item.setIcon(QIcon(str(ASSETS/'navigation'/(kind+'.svg'))))
        def section(text):
            item=QListWidgetItem(text); item.setFlags(Qt.NoItemFlags); item.setForeground(QColor('#8198aa')); self.nav.addItem(item)
        for name in names: add_nav(name)
        section('CATEGORIES')
        for name in cats:
            if name!='Uncategorized': add_nav(('   '+name.partition(' / ')[2]) if ' / ' in name else name,name)
        section('COLLECTIONS')
        for collection in collections(self.catalog): add_nav(collection['name'],f"collection:{collection['id']}")
        # Counts use catalog data only; no filesystem access on the UI thread.
        managed=[dict(row) for row in self.catalog.db.execute("SELECT id,category,favorite FROM sounds WHERE status='managed'")]
        counts={'All Sounds':len(managed),'Favorites':sum(r['favorite'] for r in managed),'Recently Added':len(managed),'Pending Review':pending,'Uncategorized':sum(r['category']=='Uncategorized' for r in managed)}
        counts['Import History']=self.catalog.db.execute('SELECT count(*) FROM import_history').fetchone()[0]
        used=self.catalog.db.execute("SELECT count(*) FROM sound_usage u JOIN sounds s ON s.id=u.sound_id WHERE s.status='managed'").fetchone()[0]
        counts.update({'Recently Used':used,'Frequently Used':used})
        for i in range(self.nav.count()):
            item=self.nav.item(i); key=item.data(Qt.UserRole)
            if key is None: continue
            if key.startswith('collection:'):
                count=self.catalog.db.execute("SELECT count(*) FROM collection_members m JOIN sounds s ON s.id=m.sound_id WHERE collection_id=? AND s.status='managed'",(int(key.split(':')[1]),)).fetchone()[0]
            else: count=counts.get(key,sum(r['category']==key or r['category'].startswith(key+' / ') for r in managed))
            # Pending count is already part of the accessible label.
            if key!='Pending Review': item.setData(Qt.UserRole+2,count)
            item.setToolTip(f'{item.text()} · {count:,} sounds')
        match = next((self.nav.item(i) for i in range(self.nav.count()) if self.nav.item(i).data(Qt.UserRole) == current), self.nav.item(0))
        self.nav.setCurrentItem(match); self.nav.blockSignals(False)
        category = self.category.currentText()
        self.category.clear(); self.category.addItems(cats)
        if category: self.category.setCurrentText(category)
        selected_category = self.import_category.currentText()
        self.import_category.blockSignals(True); self.import_category.clear(); self.import_category.addItem('All import categories'); self.import_category.addItems(cats); self.import_category.setCurrentText(selected_category); self.import_category.blockSignals(False)
        current_category = self.filter_category.currentText(); current_collection = self.filter_collection.currentData()
        self.filter_category.blockSignals(True); self.filter_category.clear(); self.filter_category.addItem('Any category'); self.filter_category.addItems(cats); self.filter_category.setCurrentText(current_category); self.filter_category.blockSignals(False)
        self.filter_collection.blockSignals(True); self.filter_collection.clear(); self.filter_collection.addItem('Any collection', None)
        for collection in collections(self.catalog): self.filter_collection.addItem(collection['name'], collection['id'])
        self.filter_collection.setCurrentIndex(max(0,self.filter_collection.findData(current_collection))); self.filter_collection.blockSignals(False)
    def current_view(self):
        return (self.nav.currentItem().data(Qt.UserRole) or self.nav.currentItem().text()) if self.nav.currentItem() else 'All Sounds'
    def selected_rows(self):
        return [self.table.item(i.row(), 0).data(Qt.UserRole) for i in self.table.selectionModel().selectedRows()]
    def list_action(self, action):
        handlers = {'play':self.play, 'stop':self.stop_playback, 'copy':self.copy_path,
                    'favorite':self.favorite_selected, 'collection':self.add_to_collection,
                    'restart':lambda: self.play_path(self.selected['path'], restart=True) if self.selected else None,
                    'details':lambda: (self.name.setFocus(), self.name.selectAll()) if self.selected else None}
        handlers[action]()
    def production_settings(self):
        ProductionSettings(self).exec()
        if not preferences(self.catalog)['auto_preview']: self.autoplay_timer.stop(); self.play_request += 1
    def volume_changed(self, value):
        self.output.setVolume(value/100)
        self.catalog.configure('production_workflow', preferences(self.catalog) | dict(volume=value))
    def add_to_collection(self):
        ids = [r['id'] for r in self.selected_rows() if r['status'] == 'managed']
        if not ids and self.selected and self.selected['status'] == 'managed': ids = [self.selected['id']]
        if ids: CollectionDialog(self, ids).exec()
        else: self.statusBar().showMessage('Select approved library sounds to add to a collection.')
    def remove_from_collection(self):
        view = self.current_view()
        if not view.startswith('collection:'): self.statusBar().showMessage('Open a collection first.'); return
        change_members(self.catalog, int(view.split(':')[1]), [r['id'] for r in self.selected_rows()], add=False)
        self.refresh()
    def favorite_selected(self):
        for row in self.selected_rows(): self.catalog.update(row['id'], favorite=1-row['favorite'])
        self.populate_nav(); self.refresh(preserve=True)
    def checked_paths(self, rows, callback):
        worker = PathCheckWorker(rows); self.file_workers.append(worker)
        def checked(available, unavailable):
            if self.closing: return
            with self.catalog.db:
                for row in available: self.catalog.db.execute('UPDATE sounds SET missing=0 WHERE path=?', (row['path'],))
                for row in unavailable: self.catalog.db.execute('UPDATE sounds SET missing=1 WHERE path=?', (row['path'],))
            callback(available, unavailable)
        worker.checked.connect(checked)
        worker.finished.connect(lambda: self.file_worker_finished(worker)); worker.start()
    def file_worker_finished(self, worker):
        if worker in self.file_workers: self.file_workers.remove(worker)
        if self.closing: QTimer.singleShot(0, self.close)
    def prepare_drag(self, rows):
        if self.drag_check_pending or self.drag_active: return
        rows = list({row['id']:row for row in rows}.values())
        rows = [row for row in rows if self.catalog.db.execute("SELECT 1 FROM sounds WHERE id=? AND path=? AND status='managed'", (row['id'],row['path'])).fetchone()]
        if not rows: self.statusBar().showMessage('Drag approved library sounds; pending files need approval first.'); return
        self.autoplay_timer.stop()
        self.drag_check_pending = True
        self.statusBar().showMessage(f'Preparing {len(rows)} original file(s) for native drag… Keep the mouse button held.')
        # Stay inside QAbstractItemView.startDrag: a queued callback loses the native gesture.
        # A bounded, event-processing loop keeps file I/O in a worker and the UI responsive.
        result = []; loop = QEventLoop(self); timeout = QTimer(self); timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)
        def checked(available, unavailable):
            result.append((available, unavailable)); loop.quit()
        self.checked_paths(rows, checked)
        if not result: timeout.start(750); loop.exec()
        timeout.stop(); timeout.deleteLater()
        self.drag_check_pending = False
        if not result:
            self.statusBar().showMessage('File check is taking too long; drag cancelled. Try again when the source drive is available.'); return
        available, unavailable = result[0]
        if self.closing: return
        if not available:
            self.statusBar().showMessage('Drag unavailable: files are missing, unreadable, or offline.'); return
        if not QApplication.mouseButtons() & Qt.LeftButton:
            self.statusBar().showMessage('Drag cancelled before the file check finished. Try again and keep the mouse held.'); return
        self.drag_active = True
        try:
            record_usage(self.catalog, [r['id'] for r in available], 'drag_started')
            self.statusBar().showMessage(f'Drag started: {len(available)} original file(s)' + (f'; {len(unavailable)} unavailable skipped' if unavailable else '') + '. REAPER insertion is not verified by SFX Vault.')
            execute_drag(self.table, available)
        finally: self.drag_active = False
        if self.current_view() in ('Recently Used', 'Frequently Used'): self.refresh(preserve=True)
    def dirty(self, *_): self.form_dirty = True
    def advanced_filters(self):
        return dict(category=self.filter_category.currentText() if self.filter_category.currentIndex()>0 else '',
            subcategory=self.filter_subcategory.text().strip(), tags=self.filter_tags.text(),
            min_duration=self.filter_min.value() or None, max_duration=self.filter_max.value() or None,
            favorite=None if not self.filter_favorite.currentIndex() else self.filter_favorite.currentIndex()==1,
            collection=self.filter_collection.currentData(), used=self.filter_used.currentIndex()==1,
            availability=['', 'available', 'missing'][self.filter_available.currentIndex()], sort=self.filter_sort.currentText())
    def reset_filters(self):
        controls = [self.search, self.types, self.confidence_filter, self.import_category] + self.advanced_controls
        for control in controls:
            control.blockSignals(True)
            if isinstance(control,QLineEdit): control.clear()
            elif isinstance(control,QDoubleSpinBox): control.setValue(0)
            elif isinstance(control,QComboBox): control.setCurrentIndex(0)
            control.blockSignals(False)
        self.debounce.stop()
        if self.current_view() not in ('Pending Review','Import History'):
            self.nav.blockSignals(True); self.nav.setCurrentRow(0); self.nav.blockSignals(False)
        self.refresh()
    def select_all_visible(self):
        self.table.selectAll()
    def select_high(self):
        if self.current_view() != 'Pending Review': return
        self.table.clearSelection()
        for i in range(self.table.rowCount()):
            row = self.table.item(i, 0).data(Qt.UserRole)
            if row['confidence'] >= .75:
                for column in range(self.table.columnCount()): self.table.item(i, column).setSelected(True)
    def configure_monitoring(self):
        self.poll.stop()
        settings = options(self.catalog)
        active = settings['enabled'] and any(f.get('enabled', True) for f in self.catalog.setting('import_folders', []))
        if active:
            self.poll.start(max(1, int(settings['interval'])) * 1000)
            QTimer.singleShot(0, self.check_imports)
    def import_settings(self):
        if ImportSettings(self).exec() == QDialog.Accepted:
            self.monitor_reset = True
            self.configure_monitoring(); self.refresh(preserve=True)
    def check_imports(self, manual=False):
        if self.closing: return
        self.start_import_task('check' if manual else 'poll')
    def start_import_task(self, action, snapshots=None, policy='skip'):
        if self.closing: return
        if self.import_worker and self.import_worker.isRunning():
            if action != 'poll':
                if not hasattr(self, 'import_tasks'): self.import_tasks = []
                self.import_tasks.append((action, snapshots, policy))
                self.statusBar().showMessage('Review decision queued behind the current background check…')
            return
        if getattr(self, 'monitor_reset', False):
            self.monitor = ImportMonitor(); self.monitor_reset = False
        self.import_worker = ImportWorker(self.database, self.monitor, action, snapshots, policy)
        self.import_worker.progress.connect(lambda text: self.statusBar().showMessage(text))
        self.import_worker.completed.connect(self.import_complete)
        self.import_worker.finished.connect(self.import_idle)
        self.import_worker.start()
    def import_idle(self):
        if self.closing: self.close(); return
        if getattr(self, 'import_tasks', []):
            action, snapshots, policy = self.import_tasks.pop(0)
            self.start_import_task(action, snapshots, policy)
    def import_complete(self, result):
        version = self.catalog.db.execute('PRAGMA data_version').fetchone()[0]
        changed = version != self.data_version
        if changed:
            self.data_version = version; self.populate_nav()
            if not self.form_dirty: self.refresh(preserve=True)
        errors = result.get('errors', [])
        if errors and errors != self.last_import_errors: logging.warning('\n'.join(errors))
        self.last_import_errors = errors
        messages = []
        if result.get('new'): messages.append(f"{result['new']} new sounds awaiting review")
        if result.get('approved'): messages.append(f"{result['approved']} sounds approved")
        if result.get('rejected'): messages.append(f"{result['rejected']} sounds rejected; files retained")
        if result.get('reconsidered'): messages.append(f"{result['reconsidered']} rejected sounds returned for review")
        if result.get('skipped'): messages.append(f"{result['skipped']} exact duplicates left pending")
        if result.get('stale'): messages.append(f"{result['stale']} changed or unavailable sounds skipped; review again")
        if result.get('waiting'): messages.append(f"{result['waiting']} files waiting for a stable transfer")
        summary = result.get('summary', {})
        if result.get('new') and summary.get('duplicates'): messages.append(f"{summary['duplicates']} potential duplicates")
        if errors: messages.append(errors[0])
        if self.form_dirty and (result.get('new') or changed): messages.append('Save current properties to refresh the list')
        if messages: self.statusBar().showMessage(' · '.join(messages))
        elif result.get('checked'): self.statusBar().showMessage('Import check completed')
        if result.get('folders'): self.import_summary.setToolTip('\n'.join(f'{path}: {status}' for path, status in result['folders']))
    def reconsider_rejected(self, all_rejected=False):
        ids = None
        if self.current_view() == 'Import History' and not all_rejected:
            rows = [self.table.item(i.row(), 0).data(Qt.UserRole) for i in self.table.selectionModel().selectedRows()]
            ids = list({r['id'] for r in rows if r.get('history_status') == 'rejected' and r['status'] == 'rejected'})
        if ids == []: self.statusBar().showMessage('Select rejected history rows to reconsider.'); return
        count = len(ids) if ids is not None else self.catalog.db.execute("SELECT count(*) FROM sounds WHERE status='rejected'").fetchone()[0]
        if count and QMessageBox.question(self, 'Reconsider rejected imports', f'Return {count} rejected sounds to Pending Review?\nApproval will still be required.') == QMessageBox.Yes:
            self.start_import_task('reconsider', ids)
    def preview_duplicate(self):
        path = self.duplicate_choices.currentData()
        if path: self.play_path(path)
    def reveal_duplicate(self):
        path = self.duplicate_choices.currentData()
        if path: self.reveal_path(path)
    def category_names(self):
        names = set(CATEGORIES) | set(self.catalog.setting('categories', [])) | {r[0] for r in self.catalog.db.execute('SELECT DISTINCT category FROM sounds')} | {r['category'] for r in self.catalog.setting('rules', RULES)}
        names -= set(self.catalog.setting('hidden_categories', []))
        names |= {name.split(' / ')[0] for name in names}
        return sorted(names)
    def organize(self, dry):
        dialog = OrganizationDialog(self, dry); dialog.exec()
    def bulk_edit(self):
        if self.current_view() in ('Pending Review', 'Import History'):
            QMessageBox.information(self, 'Library bulk editing', 'Use the properties editor for pending sounds and approve selected imports when ready.'); return
        ids = [self.table.item(i.row(), 0).data(Qt.UserRole)['id'] for i in self.table.selectionModel().selectedRows()]
        if not ids: QMessageBox.information(self, 'Select sounds', 'Select one or more sounds first.'); return
        BulkDialog(self, ids).exec()
    def refresh(self, *_, preserve=False):
        if self.closing: return
        view = self.current_view(); entering = view != self.last_view; self.last_view = view
        pending = view == 'Pending Review'; history = view == 'Import History'
        self.remove_collection_button.setVisible(view.startswith('collection:'))
        self.import_panel.setVisible(pending or history)
        self.approve_import_button.setEnabled(pending); self.reject_import_button.setEnabled(pending)
        for button in self.pending_only_buttons: button.setVisible(pending)
        self.confidence_filter.setEnabled(not history); self.types.setEnabled(not history)
        category = '' if view in ['All Sounds', 'Favorites', 'Recently Added', 'Pending Review', 'Uncategorized', 'Import History', 'Recently Used', 'Frequently Used'] or view.startswith('collection:') else view
        if pending or history: category = self.import_category.currentText() if self.import_category.currentIndex() > 0 else ''
        filters = self.advanced_filters()
        if view.startswith('collection:'): filters['collections'] = [int(view.split(':')[1])]
        self.filter_note.setVisible(filters['favorite'] is False or any(v not in ('', None, False, 'Default order') for v in filters.values()))
        self.filter_note.setText('Combined filters active · Reset filters clears search and filters. Availability reflects the last scan or file check.')
        self.filter_panel.setEnabled(not history)
        rows = self.catalog.rows(self.search.text(), view, category, self.types.currentText() if self.types.currentIndex() else '', self.confidence_filter.currentText(), filters=filters)
        selected_ids = {self.table.item(i.row(), 0).data(Qt.UserRole)['id'] for i in self.table.selectionModel().selectedRows()} if preserve else set()
        current_id = self.selected['id'] if preserve and self.selected else None
        if history:
            rows = []
            query = '''SELECT h.id AS history_id,h.detected AS history_detected,h.decided AS history_decided,
                h.status AS history_status,h.category AS history_category,s.* FROM import_history h
                JOIN sounds s ON s.id=h.sound_id ORDER BY h.detected DESC,h.id DESC'''
            for row in self.catalog.db.execute(query):
                text = ' '.join(str(row[k] or '') for k in ('original', 'path', 'display', 'tags', 'history_category', 'history_status')).lower()
                if any(word.lower() not in text for word in self.search.text().split()): continue
                if category and row['history_category'] != category and not row['history_category'].startswith(category + ' / '): continue
                rows.append(row)
        self.table.blockSignals(True); self.table.setSortingEnabled(False); self.table.setRowCount(0)
        headers = (['Sound', 'Category / subcategory', 'Tags', 'Confidence', 'Duplicate status', 'Duration', 'Type', 'Date detected', 'Original filename', 'Source folder'] if pending else
                   ['Original filename', 'Source location', 'Date detected', 'Date decided', 'Final category', 'Import status'] if history else ['Sound', 'Category', 'Duration', 'Type', 'Added', 'Status', 'Last used', 'Uses', 'Last production action'])
        self.table.setColumnCount(len(headers)); self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Interactive if pending or history else QHeaderView.Stretch)
        for column in range(len(headers)): self.table.setColumnHidden(column,not pending and not history and column>=6 and view not in ('Recently Used','Frequently Used'))
        import datetime
        duplicates_enabled = options(self.catalog)['duplicates']
        def date(value): return datetime.datetime.fromtimestamp(value).strftime('%Y-%m-%d %H:%M:%S') if value else '—'
        for r in rows:
            i = self.table.rowCount(); self.table.insertRow(i)
            duplicates = self.catalog.duplicates(r) if pending and duplicates_enabled else []
            if pending:
                values = [r['display'], r['category'], r['tags'], f"{r['confidence']:.0%}" + (' · Review closely' if r['confidence'] < .5 else ''), f'Exact duplicate ({len(duplicates)})' if duplicates else 'Checking hash' if duplicates_enabled and not r['sha'] else 'Not checked' if not duplicates_enabled else 'No match', r['duration'], r['format'], date(r['detected'] or r['added']), r['original'], str(Path(r['path']).parent)]
            elif history: values = [r['original'], r['path'], date(r['history_detected']), date(r['history_decided']), r['history_category'], r['history_status']]
            else: values = [r['display'], r['category'], r['duration'], r['format'], date(r['decision_at'] or r['added']), 'Missing' if r['missing'] else ('★' if r['favorite'] else ''), date(r['last_used']), r['use_count'], action_label(r['last_action'])]
            for j, value in enumerate(values):
                item = SortItem(); item.setData(Qt.DisplayRole, round(value, 2) if isinstance(value, float) else value)
                if not pending and not history and j in (4,6): item.setData(Qt.UserRole+1, (r['decision_at'] or r['added']) if j==4 else (r['last_used'] or 0))
                if pending and j==7: item.setData(Qt.UserRole+1, r['detected'] or r['added'])
                if pending and j==3: item.setData(Qt.UserRole+1,r['confidence'])
                if history and j in (2,3): item.setData(Qt.UserRole+1,r['history_detected'] if j==2 else (r['history_decided'] or 0))
                if j == 0: item.setData(Qt.UserRole, dict(r))
                item.setToolTip(str(value))
                if pending and j == 4 and duplicates: item.setToolTip('\n'.join(d['path'] for d in duplicates))
                if pending and r['confidence'] < .5: item.setBackground(QColor('#3b3029'))
                self.table.setItem(i, j, item)
            if r['id'] in selected_ids or entering and pending and r['confidence'] >= .75:
                for j in range(len(values)): self.table.item(i, j).setSelected(True)
            if current_id == r['id']: self.table.setCurrentCell(i, 0, QItemSelectionModel.SelectionFlag.NoUpdate)
        self.table.setSortingEnabled(True)
        self.table.blockSignals(False)
        for control in (self.match_label,self.review_label,self.approve_import_button,self.reject_import_button,self.duplicate_choices,self.preview_match,self.reveal_match): control.setVisible(pending)
        self.table.setColumnWidth(0, 280)
        if pending:
            self.table.setColumnWidth(0, 220)
            for col, width in [(1, 175), (2, 160), (3, 130), (4, 150), (5, 85), (6, 65), (7, 170), (8, 230), (9, 210)]: self.table.setColumnWidth(col, width)
        elif history:
            for col, width in enumerate([180, 185, 140, 140, 140, 100]): self.table.setColumnWidth(col, width)
        else:
            for col,width in ((1,190),(2,80),(3,65),(4,150),(5,75)): self.table.setColumnWidth(col,width)
        for field in [self.name, self.subcategory, self.tags]: field.setReadOnly(history)
        self.category.setEnabled(not history); self.favorite_check.setEnabled(not history); self.save_button.setEnabled(not history)
        if not (preserve and self.form_dirty): self.select()
        if view == 'Recently Added': self.table.sortItems(4, Qt.DescendingOrder)
        if not pending and not history:
            if view == 'Recently Used' or filters['sort']=='Recent use first': self.table.sortItems(6,Qt.DescendingOrder)
            if view == 'Frequently Used' or filters['sort']=='Frequent first': self.table.sortItems(7,Qt.DescendingOrder)
        summary = pending_summary(self.catalog, duplicates_enabled)
        self.import_summary.setText(f"{summary['total']} pending · {summary['high']} high · {summary['medium']} medium · {summary['low']} low · {summary['duplicates']} potential duplicates" + (' · Automatic preselection requires explicit approval' if pending else ' · History includes pending and past decisions'))
        self.page_title.setText((self.nav.currentItem().text() if view.startswith('collection:') else view))
        self.browser_note.setText(f'{len(rows):,} sounds  ·  Space to preview  ·  Drag original files to your DAW')
        self.statusBar().showMessage(f'{len(rows)} sounds · Audio files stay in their original locations')
    def select(self):
        item = self.table.item(self.table.currentRow(), 0)
        self.selected = item.data(Qt.UserRole) if item else None
        if not self.selected:
            self.last_selected_id = None; self.autoplay_timer.stop(); return
        changed = self.selected['id'] != self.last_selected_id; self.last_selected_id = self.selected['id']
        self.form_dirty = False
        r = self.selected; self.original.setText(r['original']); self.name.setText(r['display']); self.category.setCurrentText(r['category'].split(' / ')[0]); self.subcategory.setText(r['category'].partition(' / ')[2]); self.tags.setText(r['tags']); self.favorite_check.setChecked(bool(r['favorite']))
        duplicates = self.catalog.duplicates(r) if options(self.catalog)['duplicates'] else []
        self.duplicate_choices.clear()
        for duplicate in duplicates: self.duplicate_choices.addItem(f"{duplicate['status']} · {duplicate['path']}", duplicate['path'])
        from datetime import datetime
        used = usage(self.catalog, r['id']); member_names = ', '.join(c['name'] for c in memberships(self.catalog,r['id'])) or 'None'
        last_used = datetime.fromtimestamp(used['last_used']).strftime('%Y-%m-%d %H:%M:%S') + f" · {used['use_count']} action(s) · {action_label(used['last_action'])}" if used else 'Never'
        self.detail.setText(f"{r['path']}\n\n{r['format']} · {r['duration']:.2f} seconds · {r['size']:,} bytes\nAvailability: {'Missing / offline' if r['missing'] else 'Available'} at last check\nCollections: {member_names}\nLast used: {last_used}\nSuggestion confidence: {r['confidence']:.0%}\n" + ('\nExact duplicates:\n' + '\n'.join(d['path'] for d in duplicates) if duplicates else '') + ('\n\nMetadata: ' + r['metadata'] if r['metadata'] else ''))
        if changed and preferences(self.catalog)['auto_preview'] and self.current_view() != 'Import History':
            self.play_request += 1; self.player.stop(); self.autoplay_timer.start()
    def save(self):
        if self.selected:
            category = self.category.currentText().strip() or 'Uncategorized'
            if self.subcategory.text().strip(): category = category.split(' / ')[0] + ' / ' + self.subcategory.text().strip()
            self.catalog.update(self.selected['id'], display=self.name.text().strip() or self.selected['suggestion'], category=category, tags=self.tags.text().strip(), favorite=int(self.favorite_check.isChecked()), edited=1)
            self.form_dirty = False
            self.populate_nav(); self.refresh()
    def restore(self):
        if self.selected: self.name.setText(self.selected['suggestion'])
    def favorite(self):
        if self.selected: self.catalog.update(self.selected['id'], favorite=1-self.selected['favorite']); self.populate_nav(); self.refresh()
    def review(self, status):
        if self.current_view() != 'Pending Review': self.statusBar().showMessage('Open Pending Review to approve or reject imports.'); return
        snapshots = [self.table.item(i.row(), 0).data(Qt.UserRole) for i in self.table.selectionModel().selectedRows()]
        snapshots = [s for s in snapshots if s['status'] == 'pending']
        if not snapshots: self.statusBar().showMessage('Select pending files to review.'); return
        if self.form_dirty:
            QMessageBox.information(self, 'Save metadata first', 'Save your properties edits before approving or rejecting selected files.'); return
        approve = status == 'managed'; policy = 'skip'
        if approve and any(self.catalog.duplicates(s) for s in snapshots) and options(self.catalog)['duplicates']:
            box = QMessageBox(self); box.setWindowTitle('Exact duplicates selected'); box.setText('Some selected files match existing or pending sounds. Choose how to handle them. No files will be deleted.')
            skip = box.addButton('Approve nonduplicates; leave matches pending', QMessageBox.AcceptRole)
            keep = box.addButton('Keep duplicates as separate entries', QMessageBox.ActionRole)
            box.addButton(QMessageBox.Cancel); box.exec()
            if box.clickedButton() == keep: policy = 'keep'
            elif box.clickedButton() != skip: return
        elif QMessageBox.question(self, 'Confirm import review', f'{"Approve" if approve else "Reject"} {len(snapshots)} selected files?\nSource files stay in place.') != QMessageBox.Yes: return
        self.start_import_task('approve' if approve else 'reject', snapshots, policy)
    def copy_path(self):
        rows = self.selected_rows() or ([self.selected] if self.selected else [])
        if rows:
            QApplication.clipboard().setText('\r\n'.join(dict.fromkeys(r['path'] for r in rows)))
            record_usage(self.catalog, [r['id'] for r in rows], 'copy_path')
            self.statusBar().showMessage(f"{len(rows)} original file path(s) copied. REAPER insertion is not verified.")
            self.refresh(preserve=True)
    def reveal(self):
        if self.selected: self.reveal_path(self.selected['path'])
    def reveal_path(self, path):
        if sys.platform == 'win32':
            import subprocess
            subprocess.Popen(['explorer.exe', '/select,', path])
        else: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))
    def play(self):
        if not self.selected: return
        self.autoplay_timer.stop()
        self.play_path(self.selected['path'])
    def stop_playback(self):
        self.play_request += 1; self.autoplay_timer.stop(); self.player.stop(); self.player.setSource(QUrl())
        self.now_playing.setText('No preview'); self.seek.setValue(0); self.time.setText('0:00 / 0:00')
    def playback_error(self, *_):
        message = self.player.errorString()
        self.player.stop(); self.now_playing.setText('Preview unavailable')
        self.statusBar().showMessage('Playback unavailable: ' + message)
    def play_path(self, path, restart=False):
        url = QUrl.fromLocalFile(path)
        if self.player.source() == url:
            self.play_request += 1
            if restart: self.player.setPosition(0); self.player.play()
            elif self.player.playbackState() == QMediaPlayer.PlayingState: self.player.pause()
            else: self.player.play()
            return
        self.player.stop(); self.play_request += 1; request = self.play_request
        self.statusBar().showMessage('Checking preview file…')
        def ready(available, unavailable):
            if request != self.play_request: return
            if not available:
                self.stop_playback(); self.now_playing.setText('File missing / offline'); self.statusBar().showMessage('Preview unavailable: source is missing, unreadable, or offline.'); return
            self.player.setSource(url); self.player.setPosition(0); self.player.play()
            title = self.selected['display'] if self.selected and self.selected['path']==path else Path(path).name
            self.now_playing.setText(title); self.now_playing.setToolTip(path)
        self.checked_paths([dict(path=path)], ready)
    def step(self, delta):
        row = self.table.currentRow() + delta
        if 0 <= row < self.table.rowCount(): self.table.selectRow(row); self.autoplay_timer.stop(); self.play_path(self.selected['path'], restart=True)
    def position(self, value):
        if not self.seek.isSliderDown(): self.seek.setValue(value)
        self.time.setText(clock(value) + ' / ' + clock(self.player.duration()))
    def add_folder(self, key):
        folder = QFileDialog.getExistingDirectory(self, 'Choose folder')
        if folder:
            roots = self.catalog.setting(key, [])
            if folder not in roots: roots.append(folder); self.catalog.configure(key, roots)
            self.rescan()
    def add_library(self): self.add_folder('roots')
    def add_watch(self): self.add_folder('watched')
    def rescan(self, full=True, startup=False):
        if self.worker and self.worker.isRunning(): return
        roots = self.catalog.setting('roots', []) if full else []
        watched = []
        if not roots and not watched: return
        self.statusBar().showMessage('Scanning audio folders…')
        self.worker = Scanner(self.database, roots, watched, self.stable, startup); self.worker.finished_scan.connect(self.scanned); self.worker.progress.connect(lambda text: self.statusBar().showMessage(text)); self.worker.start()
    def scanned(self, result):
        self.import_complete(result)
        if not result.get('new') and not result.get('errors'): self.statusBar().showMessage('Library scan complete · Existing metadata retained')
    def settings(self):
        dialog = QDialog(self); dialog.setWindowTitle('Library settings'); dialog.resize(680, 600); layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel('One folder per line. Removing a folder retains its catalog records.'))
        roots = QPlainTextEdit('\n'.join(self.catalog.setting('roots', []))); layout.addWidget(QLabel('Managed folders')); layout.addWidget(roots)
        layout.addWidget(QLabel('Configure monitored folders and duplicate checks using Import Automation in the toolbar.'))
        rules = QPlainTextEdit(json.dumps(self.catalog.setting('rules', RULES), indent=2)); layout.addWidget(QLabel('Category rules · JSON: category, keywords, tags')); layout.addWidget(rules)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel); layout.addWidget(buttons); buttons.rejected.connect(dialog.reject)
        def accept():
            try:
                data = json.loads(rules.toPlainText())
                if not isinstance(data, list): raise ValueError('Rules must be a list')
                for r in data:
                    if not isinstance(r, dict) or not isinstance(r.get('category'), str) or not r['category'].strip() or not isinstance(r.get('keywords'), list) or not all(isinstance(k, str) for k in r['keywords']) or not isinstance(r.get('tags', []), list) or not all(isinstance(t, str) for t in r.get('tags', [])): raise ValueError('Each rule needs a category, keyword list and optional tag list')
                self.catalog.configure('rules', data)
                self.catalog.configure('roots', list(dict.fromkeys(p.strip() for p in roots.toPlainText().splitlines() if p.strip())))
                dialog.accept(); self.populate_nav(); self.rescan()
            except (ValueError, TypeError) as exc: QMessageBox.warning(dialog, 'Invalid settings', str(exc))
        buttons.accepted.connect(accept); dialog.exec()
    def closeEvent(self, event):
        if getattr(self,'catalog_closed',False): event.accept(); return
        self.closing = True
        self.poll.stop(); self.debounce.stop()
        self.autoplay_timer.stop(); self.play_request += 1
        active = [worker for worker in [self.worker, self.import_worker] + self.file_workers + self.update_workers if worker and worker.isRunning()]
        if active:
            self.statusBar().showMessage('Finishing background work before closing…')
            for worker in active: worker.requestInterruption(); worker.finished.connect(self.close, Qt.UniqueConnection)
            event.ignore(); return
        save_layout(self)
        self.player.stop(); self.player.setSource(QUrl()); self.catalog.close(); self.catalog_closed=True; event.accept()

def main():
    import argparse
    parser = argparse.ArgumentParser(); parser.add_argument('--data-dir', type=Path); parser.add_argument('--test-update',type=Path); parser.add_argument('--verify-install',type=Path); parser.add_argument('--install-update',type=Path); parser.add_argument('--installer-sha256'); parser.add_argument('--parent-pid',type=int); args = parser.parse_args()
    if args.install_update:
        from .updates import installer_helper
        if not args.parent_pid or not args.installer_sha256: parser.error('Installer helper requires parent process and checksum.')
        installer_helper(args.install_update,args.installer_sha256,args.parent_pid); return
    from .version import TEST_EDITION
    if TEST_EDITION and args.data_dir is None:
        args.data_dir=Path(os.environ.get('LOCALAPPDATA',str(Path.home()))) / 'SFX Vault Update Test'
    if sys.platform=='win32':
        import ctypes
        ctypes.windll.kernel32.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_wchar_p]
        ctypes.windll.kernel32.CreateMutexW.restype=ctypes.c_void_p
        app_mutex=ctypes.windll.kernel32.CreateMutexW(None,False,'SFXVault.UpdateTest' if TEST_EDITION else 'SFXVault.Desktop')
    data = args.data_dir or Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'SFX Vault'
    data.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=data / 'sfx-vault.log', level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('SFXVault.UpdateTest' if TEST_EDITION else 'SFXVault.Desktop')
    app = QApplication(sys.argv); apply_theme(app)
    window = Window(data / 'catalog.sqlite3'); window.test_update=args.test_update; window.show()
    from .update_ui import automatic_check
    QTimer.singleShot(1500,lambda:automatic_check(window))
    if args.verify_install:
        from .install_verify import verify
        QTimer.singleShot(200,lambda:verify(window,args.verify_install))
    sys.exit(app.exec())

if __name__ == '__main__': main()
