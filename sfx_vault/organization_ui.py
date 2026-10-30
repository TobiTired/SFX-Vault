import json
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QTableWidget, QTableWidgetItem, QAbstractItemView, QMessageBox,
    QFormLayout, QLineEdit, QDialogButtonBox, QInputDialog)
from .core import Catalog, CATEGORIES
from .organization import preview, stage, staged, decide, confidence_matches, CONFIDENCES, bulk, rename_category

class OrganizationWorker(QThread):
    result = Signal(list, str)
    def __init__(self, database, dry):
        super().__init__(); self.database, self.dry = database, dry
    def run(self):
        try:
            proposals = preview(self.database)
            if not self.dry:
                catalog = Catalog(self.database)
                try: stage(catalog, proposals); proposals = staged(catalog)
                finally: catalog.close()
            self.result.emit(proposals, '')
        except Exception as exc: self.result.emit([], str(exc))

class OrganizationDialog(QDialog):
    def __init__(self, parent, dry=False):
        super().__init__(parent); self.catalog = parent.catalog; self.dry = dry; self.proposals = []
        self.setWindowTitle('Organization preview · Read only' if dry else 'Review organization suggestions')
        self.resize(1280, 740); layout = QVBoxLayout(self)
        self.notice = QLabel('Generating suggestions from indexed metadata…'); self.notice.setWordWrap(True); layout.addWidget(self.notice)
        filters = QHBoxLayout(); layout.addLayout(filters)
        self.categories = QComboBox(); self.categories.addItem('All categories'); filters.addWidget(self.categories)
        self.confidence = QComboBox(); self.confidence.addItems(CONFIDENCES); filters.addWidget(self.confidence)
        select = QPushButton('Select all visible'); filters.addWidget(select)
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(['Original filename', 'Current name', 'Suggested name', 'Confidence', 'Protection', 'Suggested category', 'Suggested tags', 'Current category', 'Current tags', 'File location'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        layout.addWidget(self.table, 1)
        buttons = QHBoxLayout(); layout.addLayout(buttons)
        self.approve = QPushButton('Approve selected'); self.reject_button = QPushButton('Reject selected'); close = QPushButton('Close')
        for b in [self.approve, self.reject_button, close]: buttons.addWidget(b)
        self.approve.setEnabled(False); self.reject_button.setEnabled(False)
        self.approve.clicked.connect(lambda: self.decide(True)); self.reject_button.clicked.connect(lambda: self.decide(False)); close.clicked.connect(self.close)
        self.categories.currentTextChanged.connect(self.filter); self.confidence.currentTextChanged.connect(self.filter)
        select.clicked.connect(self.select_visible); self.table.itemChanged.connect(self.edit)
        self.worker = OrganizationWorker(parent.database, dry); self.worker.result.connect(self.loaded); self.worker.start()
    def loaded(self, proposals, error):
        if error: self.notice.setText('Could not generate suggestions: ' + error); return
        self.proposals = proposals
        self.notice.setText(f'{len(proposals)} suggestions · ' + ('Read-only preview: nothing is saved or applied.' if self.dry else 'Edit suggested columns, then select and approve. Protected or stale sounds are skipped. Unreviewed sounds stay unchanged.'))
        chosen = self.categories.currentText()
        self.categories.blockSignals(True); self.categories.clear(); self.categories.addItem('All categories')
        category_names = {p['proposed']['category'] for p in proposals}
        category_names |= {c.split(' / ')[0] for c in category_names}
        self.categories.addItems(sorted(category_names))
        self.categories.setCurrentText(chosen if chosen == 'All categories' or chosen in category_names else 'All categories')
        self.categories.blockSignals(False)
        self.table.blockSignals(True); self.table.setRowCount(len(proposals))
        for index, p in enumerate(proposals):
            current, proposed = p['current'], p['proposed']
            values = [p['original'], current['display'], proposed['display'], f"{proposed['confidence']:.0%}", 'Manual — protected' if p['protected'] else 'Automatic', proposed['category'], proposed['tags'], current['category'], current['tags'], p['path']]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column not in (2, 5, 6) or self.dry or p['protected']: item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(index, column, item)
        self.table.blockSignals(False); self.table.resizeColumnsToContents()
        for col in (0, 1, 2, 5, 6, 7, 8, 9): self.table.setColumnWidth(col, min(200, max(150, self.table.columnWidth(col))))
        self.table.setColumnWidth(3, 85); self.table.setColumnWidth(4, 135)
        self.approve.setEnabled(not self.dry); self.reject_button.setEnabled(not self.dry); self.filter()
    def edit(self, item):
        if item.column() not in (2, 5, 6): return
        p = self.proposals[item.row()]; key = {2:'display', 5:'category', 6:'tags'}[item.column()]
        p['proposed'][key] = item.text().strip() or ('Uncategorized' if key == 'category' else p['current']['display'] if key == 'display' else '')
        p['custom'] = True
        if not self.dry:
            with self.catalog.db:
                self.catalog.db.execute("UPDATE organization SET payload=? WHERE sound_id=? AND state='pending' AND fingerprint=?", (json.dumps(p), p['id'], p['fingerprint']))
    def filter(self, *_):
        for i, p in enumerate(self.proposals):
            cat = self.categories.currentText()
            visible = (cat == 'All categories' or p['proposed']['category'] == cat or p['proposed']['category'].startswith(cat + ' / ')) and confidence_matches(p['proposed']['confidence'], self.confidence.currentText())
            self.table.setRowHidden(i, not visible)
            if not visible:
                for c in range(self.table.columnCount()): self.table.item(i, c).setSelected(False)
    def select_visible(self):
        self.table.clearSelection()
        for i in range(self.table.rowCount()):
            if not self.table.isRowHidden(i):
                for c in range(self.table.columnCount()): self.table.item(i, c).setSelected(True)
    def decide(self, approve):
        selected = [self.proposals[i.row()] for i in self.table.selectionModel().selectedRows() if not self.table.isRowHidden(i.row())]
        if not selected: return
        action = 'Apply metadata for' if approve else 'Reject suggestions for'
        if QMessageBox.question(self, 'Confirm organization', f'{action} {len(selected)} selected sounds?\nAudio files are unchanged. Manual edits are protected.') != QMessageBox.Yes: return
        try: count, skipped = decide(self.catalog, selected, approve)
        except Exception as exc: QMessageBox.warning(self, 'Could not save review', str(exc)); return
        self.loaded(staged(self.catalog), '')
        self.notice.setText(f'{count} {"approved" if approve else "rejected"}; {skipped} protected, stale or already reviewed. {len(self.proposals)} pending.')
        self.parent().populate_nav(); self.parent().refresh()
    def closeEvent(self, event):
        if self.worker.isRunning(): self.notice.setText('Finishing suggestion generation…'); event.ignore(); return
        event.accept()
    def reject(self):
        if self.worker.isRunning(): return
        super().reject()

class BulkDialog(QDialog):
    def __init__(self, parent, ids):
        super().__init__(parent); self.setWindowTitle(f'Bulk edit · {len(ids)} sounds'); layout = QFormLayout(self)
        layout.addRow(QLabel('Only the chosen operation changes. Category replaces its subcategory.\nReset clears generated metadata; manually edited sounds are skipped.'))
        operation = QComboBox(); operation.addItems(['Category', 'Subcategory', 'Add tags', 'Remove tags', 'Favorite', 'Unfavorite', 'Reset automatic metadata']); layout.addRow('Operation', operation)
        value = QLineEdit(); layout.addRow('Value / comma-separated tags', value)
        buttons = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Cancel); layout.addRow(buttons); buttons.rejected.connect(self.reject)
        def apply():
            op = operation.currentText()
            if op in ('Category', 'Add tags', 'Remove tags') and not value.text().strip():
                QMessageBox.warning(self, 'Value required', 'Enter a category or tags.'); return
            if QMessageBox.question(self, 'Confirm bulk change', f'{op}: {value.text() or "(no value)"}\nApply to {len(ids)} sounds?\nExisting values for the chosen field may change.') != QMessageBox.Yes: return
            try: count, skipped = bulk(parent.catalog, ids, op, value.text())
            except Exception as exc: QMessageBox.warning(self, 'Bulk edit failed', str(exc)); return
            parent.populate_nav(); parent.refresh(); QMessageBox.information(self, 'Bulk edit complete', f'{count} changed; {skipped} skipped.'); self.accept()
        buttons.button(QDialogButtonBox.Apply).clicked.connect(apply)

def categories_dialog(parent):
    dialog = QDialog(parent); dialog.setWindowTitle('Manage categories'); layout = QFormLayout(dialog)
    choice = QComboBox(); choice.setEditable(True); choice.addItems(parent.category_names()); layout.addRow('Category', choice)
    layout.addRow(QLabel('Use “Primary / Subcategory” for a nested category.\nRenaming also updates descendants and rules, and protects affected metadata.'))
    def create():
        name = choice.currentText().strip()
        if not name: return
        parent.catalog.configure('categories', sorted(set(parent.catalog.setting('categories', []) + [name])))
        parent.catalog.configure('hidden_categories', [c for c in parent.catalog.setting('hidden_categories', []) if c != name])
        parent.populate_nav(); choice.clear(); choice.addItems(parent.category_names())
    def rename():
        old = choice.currentText(); new, ok = QInputDialog.getText(dialog, 'Rename category', 'New category name:', text=old)
        if not ok or new.strip() == old: return
        if QMessageBox.question(dialog, 'Confirm category rename', f'Rename “{old}” and its subcategories to “{new}”?\nThis updates catalog metadata only.') != QMessageBox.Yes: return
        try: rename_category(parent.catalog, old, new)
        except ValueError as exc: QMessageBox.warning(dialog, 'Invalid category', str(exc)); return
        parent.populate_nav(); parent.refresh(); choice.clear(); choice.addItems(parent.category_names())
    add = QPushButton('Create category'); add.clicked.connect(create); layout.addRow(add)
    button = QPushButton('Rename category…'); button.clicked.connect(rename); layout.addRow(button)
    close = QPushButton('Close'); close.clicked.connect(dialog.accept); layout.addRow(close); dialog.exec()
