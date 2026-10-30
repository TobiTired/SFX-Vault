from pathlib import Path
from PySide6.QtCore import QThread, Signal, Qt, QMimeData, QUrl, QEvent
from PySide6.QtGui import QDrag, QPixmap, QPainter, QColor
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QFormLayout,
    QCheckBox, QSlider, QLabel, QDialogButtonBox, QComboBox, QPushButton,
    QInputDialog, QMessageBox, QLineEdit)
from .workflow import (preferences, collections, create_collection, rename_collection,
    delete_collection, change_members)

SHORTCUTS = '''Ctrl+F — focus search (main window only)
When the sound list has focus:
Space — play / pause selected sound
Up / Down — move through results
Ctrl+R — restart selected sound from the beginning
Esc — stop playback
Ctrl+C — copy selected original file paths
Ctrl+D — toggle favorites for selected sounds
Ctrl+Shift+C — add selected sounds to a collection
Enter — focus the selected sound's display name
In text fields, normal editing shortcuts apply. Esc dismisses an open dialog.
Native drag and copy-path usage record the export action, not verified REAPER insertion.'''

def file_mime(rows):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(row['path']) for row in rows])
    return mime

def execute_drag(table, rows):
    drag = QDrag(table); drag.setMimeData(file_mime(rows))
    pixmap = QPixmap(250, 38); pixmap.fill(QColor('#303648'))
    painter = QPainter(pixmap); painter.setPen(QColor('#e4e6ee'))
    painter.drawText(pixmap.rect(), Qt.AlignCenter, f'{len(rows)} original audio file(s) · Copy'); painter.end()
    drag.setPixmap(pixmap)
    return drag.exec(Qt.CopyAction, Qt.CopyAction)

class PathCheckWorker(QThread):
    checked = Signal(list, list)
    def __init__(self, rows): super().__init__(); self.rows = rows
    def run(self):
        available, unavailable = [], []
        for row in self.rows:
            if self.isInterruptionRequested(): break
            try:
                if not Path(row['path']).is_file(): raise OSError('File is missing or offline')
                with open(row['path'], 'rb') as stream: stream.read(1)
                available.append(row)
            except OSError: unavailable.append(row)
        self.checked.emit(available, unavailable)

class SeekSlider(QSlider):
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.width() > 0:
            value = self.minimum() + round((self.maximum()-self.minimum()) * max(0, min(1, event.position().x()/self.width())))
            self.setValue(value); self.sliderMoved.emit(value); self.sliderReleased.emit(); event.accept()
        else: super().mousePressEvent(event)

class CollectionDialog(QDialog):
    def __init__(self, parent, ids=None):
        super().__init__(parent); self.setWindowTitle('Collections'); self.resize(460, 300)
        self.catalog = parent.catalog; self.ids = ids
        layout = QVBoxLayout(self); self.choice = QComboBox(); layout.addWidget(self.choice)
        self.notice = QLabel(f'{len(ids)} selected sounds' if ids is not None else 'Collections are virtual. Deleting one keeps every sound.'); self.notice.setWordWrap(True); layout.addWidget(self.notice)
        def button(text, callback):
            b = QPushButton(text); b.clicked.connect(callback); layout.addWidget(b)
        button('Create collection…', self.create); button('Rename collection…', self.rename); button('Delete collection…', self.delete)
        if ids is not None: button('Add selected sounds', self.add)
        button('Close', self.accept); self.reload()
    def reload(self):
        self.choice.clear()
        for collection in collections(self.catalog): self.choice.addItem(collection['name'], collection['id'])
        self.parent().populate_nav()
    def attempt(self, operation):
        try: operation(); self.reload()
        except Exception as exc: QMessageBox.warning(self, 'Could not update collection', str(exc))
    def create(self):
        name, ok = QInputDialog.getText(self, 'Create collection', 'Name:')
        if ok:
            self.attempt(lambda: create_collection(self.catalog, name)); self.choice.setCurrentText(name.strip())
    def rename(self):
        ident = self.choice.currentData()
        if ident is None: return
        name, ok = QInputDialog.getText(self, 'Rename collection', 'Name:', text=self.choice.currentText())
        if ok: self.attempt(lambda: rename_collection(self.catalog, ident, name))
    def delete(self):
        ident = self.choice.currentData()
        if ident is not None and QMessageBox.question(self, 'Delete virtual collection', f'Delete “{self.choice.currentText()}”?\nAll sounds and source files are kept.') == QMessageBox.Yes:
            self.attempt(lambda: delete_collection(self.catalog, ident)); self.parent().refresh()
    def add(self):
        ident = self.choice.currentData()
        if ident is None: return
        self.attempt(lambda: change_members(self.catalog, ident, self.ids)); self.notice.setText('Selected managed sounds added.'); self.parent().refresh(preserve=True)

class ProductionSettings(QDialog):
    def __init__(self, parent):
        super().__init__(parent); self.setWindowTitle('Production Workflow'); self.resize(580, 430)
        layout = QFormLayout(self); settings = preferences(parent.catalog)
        auto = QCheckBox('Preview when the current sound changes'); auto.setChecked(settings['auto_preview']); layout.addRow(auto)
        volume = QSlider(Qt.Horizontal); volume.setRange(0,100); volume.setValue(settings['volume']); layout.addRow('Preview volume', volume)
        track = QCheckBox('Track explicit drag starts and copy-path actions'); track.setChecked(settings['track_usage']); layout.addRow(track)
        label = QLabel(SHORTCUTS); label.setWordWrap(True); label.setTextInteractionFlags(Qt.TextSelectableByMouse); layout.addRow(label)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel); layout.addRow(buttons); buttons.rejected.connect(self.reject)
        def save():
            parent.catalog.configure('production_workflow', dict(auto_preview=auto.isChecked(), volume=volume.value(), track_usage=track.isChecked()))
            parent.volume.setValue(volume.value()); self.accept()
        buttons.accepted.connect(save)
