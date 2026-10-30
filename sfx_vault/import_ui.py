"""Import automation settings and background tasks for the existing desktop shell."""
import time
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QTableWidget, QTableWidgetItem, QPushButton, QCheckBox, QSpinBox, QFileDialog,
    QDialogButtonBox, QMessageBox)
from .core import Catalog
from .imports import ImportMonitor, options, pending_summary, review_imports, reconsider

class ImportWorker(QThread):
    progress = Signal(str)
    completed = Signal(dict)
    def __init__(self, database, monitor=None, action='poll', snapshots=None, policy='skip'):
        super().__init__(); self.database = database; self.monitor = monitor
        self.action, self.snapshots, self.policy = action, snapshots or [], policy
    def run(self):
        catalog = None
        try:
            catalog = Catalog(self.database)
            last = [0.]
            def progress(message):
                now = time.monotonic()
                if now - last[0] >= .15: self.progress.emit(message); last[0] = now
            if self.action in ('poll', 'check'):
                folders = catalog.setting('import_folders', []) if self.action == 'check' else None
                result = self.monitor.poll(catalog, progress, self.isInterruptionRequested, folders_override=folders)
                if self.action == 'check' and result['waiting'] and not self.isInterruptionRequested():
                    self.progress.emit('Waiting for import transfers to stabilize…')
                    deadline = time.monotonic() + options(catalog)['stable_seconds']
                    while time.monotonic() < deadline and not self.isInterruptionRequested(): self.msleep(100)
                    if not self.isInterruptionRequested():
                        later = self.monitor.poll(catalog, progress, self.isInterruptionRequested, folders_override=folders)
                        later['new'] += result['new']; later['errors'] = list(dict.fromkeys(result['errors'] + later['errors'])); result = later
            elif self.action in ('approve', 'reject'):
                self.progress.emit('Saving import review decisions…')
                result = review_imports(catalog, self.snapshots, self.action == 'approve', self.policy)
            else:
                result = dict(reconsidered=reconsider(catalog, self.snapshots or None))
            result['summary'] = pending_summary(catalog, options(catalog)['duplicates'])
        except Exception as exc:
            result = dict(errors=[f'Import operation failed; review records retained: {exc}'])
        finally:
            if catalog: catalog.close()
        self.completed.emit(result)

class ImportSettings(QDialog):
    def __init__(self, parent):
        super().__init__(parent); self.setWindowTitle('Import Automation'); self.resize(850, 620)
        catalog = parent.catalog; settings = options(catalog)
        layout = QVBoxLayout(self)
        notice = QLabel('Files always require approval. Monitoring and hashing run in the background.\nConfigured folder scopes are reserved during library scans, even when monitoring is paused.'); notice.setWordWrap(True); layout.addWidget(notice)
        form = QFormLayout(); layout.addLayout(form)
        self.enabled = QCheckBox('Enable background monitoring'); self.enabled.setChecked(settings['enabled']); form.addRow(self.enabled)
        self.startup = QCheckBox('Check for missed files on startup'); self.startup.setChecked(settings['scan_startup']); form.addRow(self.startup)
        self.duplicates = QCheckBox('Check SHA-256 duplicates (cache unchanged files)'); self.duplicates.setChecked(settings['duplicates']); form.addRow(self.duplicates)
        self.interval = QSpinBox(); self.interval.setRange(1, 3600); self.interval.setValue(settings['interval']); self.interval.setSuffix(' seconds'); form.addRow('Scan interval', self.interval)
        self.stability = QSpinBox(); self.stability.setRange(3, 300); self.stability.setValue(settings['stable_seconds']); self.stability.setSuffix(' seconds'); form.addRow('Minimum unchanged period', self.stability)
        self.table = QTableWidget(0, 3); self.table.setHorizontalHeaderLabels(['Folder', 'Enabled', 'Subfolders']); self.table.setColumnWidth(0, 570); layout.addWidget(self.table)
        for entry in catalog.setting('import_folders', []): self.add_row(entry)
        row = QHBoxLayout(); layout.addLayout(row)
        add = QPushButton('Add folder…'); row.addWidget(add)
        remove = QPushButton('Remove selected configuration'); row.addWidget(remove)
        add.clicked.connect(self.choose_folder); remove.clicked.connect(self.remove_rows)
        reconsider_button = QPushButton('Reconsider previously rejected files…'); layout.addWidget(reconsider_button)
        reconsider_button.clicked.connect(lambda: parent.reconsider_rejected(True))
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel); layout.addWidget(buttons); buttons.rejected.connect(self.reject)
        def save():
            folders = []
            for index in range(self.table.rowCount()):
                path = self.table.item(index, 0).text().strip()
                if not path or not Path(path).is_absolute():
                    QMessageBox.warning(self, 'Folder path required', 'Use an absolute local or UNC folder path.'); return
                entry = dict(path=str(Path(path)), enabled=self.table.item(index, 1).checkState() == Qt.Checked, recursive=self.table.item(index, 2).checkState() == Qt.Checked)
                if any(f['path'].casefold() == entry['path'].casefold() for f in folders):
                    QMessageBox.warning(self, 'Repeated folder', 'Each monitored folder may appear only once.'); return
                folders.append(entry)
            try:
                # Both settings are committed together.
                import json
                with catalog.db:
                    for key, value in [('import_folders', folders), ('import_options', dict(enabled=self.enabled.isChecked(), scan_startup=self.startup.isChecked(), duplicates=self.duplicates.isChecked(), interval=self.interval.value(), stable_seconds=self.stability.value()))]:
                        catalog.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, json.dumps(value)))
            except Exception as exc: QMessageBox.warning(self, 'Could not save settings', str(exc)); return
            self.accept()
        buttons.accepted.connect(save)
    def add_row(self, entry):
        index = self.table.rowCount(); self.table.insertRow(index)
        path_item = QTableWidgetItem(entry['path']); path_item.setToolTip(entry['path']); self.table.setItem(index, 0, path_item)
        for column, field in [(1, 'enabled'), (2, 'recursive')]:
            item = QTableWidgetItem(); item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if entry.get(field, True) else Qt.Unchecked); self.table.setItem(index, column, item)
    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, 'Choose import folder')
        if path: self.add_row(dict(path=path, enabled=True, recursive=True))
    def remove_rows(self):
        for index in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True): self.table.removeRow(index)
