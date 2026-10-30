"""Shared visual system, independent of the catalog and source files."""
from pathlib import Path
from PySide6.QtGui import QFont, QIcon, QFontDatabase
ASSETS = Path(__file__).resolve().parent / 'assets'
STYLE = '''
QWidget { background:#101419; color:#dce5ed; font-family:"Segoe UI"; font-size:12px; }
QLabel { background:transparent; }
QLabel#Brand { font-size:18px; font-weight:700; letter-spacing:2px; color:#f2f7fb; }
QLabel#Eyebrow { color:#91a5b7; font-size:10px; font-weight:700; letter-spacing:2px; }
QLabel#PageTitle { font-size:21px; font-weight:600; }
QLabel#Muted,QStatusBar { color:#91a1af; }
QWidget#Header,QWidget#Player { background:#171e26; border:1px solid #293744; border-radius:8px; }
QWidget#Inspector,QWidget#Sidebar { background:#141a21; }
QLineEdit,QComboBox,QPlainTextEdit,QDoubleSpinBox { background:#1b242e; border:1px solid #33424f; border-radius:5px; padding:6px; selection-background-color:#225875; }
QLineEdit:focus,QComboBox:focus,QPlainTextEdit:focus,QDoubleSpinBox:focus { border:1px solid #54c6ed; }
QLineEdit#Search { font-size:14px; padding:10px 12px; }
QPushButton,QToolButton { background:#202b36; border:1px solid #344451; border-radius:5px; padding:6px 10px; }
QPushButton:hover,QToolButton:hover { background:#2b3a48; border-color:#577386; }
QPushButton:pressed,QToolButton:pressed { background:#214760; }
QPushButton:checked { color:#80dbf8; border-color:#3ca1c4; background:#19384a; }
QPushButton:focus,QToolButton:focus { border:1px solid #78d8f5; }
QPushButton#Primary { background:#329fc5; color:#06151d; font-weight:700; border-color:#54c6ed; }
QPushButton#Primary:hover { background:#67d0ef; }
QPushButton:disabled,QComboBox:disabled { color:#73818d; background:#19212a; border-color:#27323b; }
QTableWidget { background:#111820; alternate-background-color:#151e27; border:1px solid #293541; border-radius:6px; gridline-color:#24313c; selection-background-color:#20435b; selection-color:#e8f8ff; }
QTableWidget::item { padding:5px 9px; border-bottom:1px solid #1e2b36; }
QTableWidget::item:hover { background:#1b3040; }
QTableWidget::item:selected { background:#20435b; color:#e8f8ff; }
QTableWidget::item:focus { border:1px solid #60cbed; }
QHeaderView::section { background:#1a242e; color:#9bb0c1; padding:9px; border:0; border-right:1px solid #293541; font-weight:600; }
QTableCornerButton::section { background:#1a242e; border:0; }
QListWidget { background:transparent; border:0; outline:0; padding:4px; }
QListWidget::item { padding:9px 10px; margin:2px 0; border-radius:5px; }
QListWidget::item:hover { background:#1d2c38; }
QListWidget::item:selected { background:#193d52; color:#7bd8f4; border-left:2px solid #52c8ee; }
QListWidget::item:focus { border:1px solid #60cbed; }
QScrollArea { border:0; }
QSplitter::handle { background:#101419; }
QSplitter::handle:hover { background:#329fc5; }
QSlider::groove:horizontal { height:4px; background:#344451; border-radius:2px; }
QSlider::sub-page:horizontal { background:#48b7dc; border-radius:2px; }
QSlider::handle:horizontal { background:#8cddf5; width:12px; margin:-5px 0; border-radius:6px; }
QMenu { background:#1b242e; border:1px solid #405361; padding:5px; }
QMenu::item { padding:8px 22px; }
QMenu::item:selected { background:#20435b; }
QScrollBar:vertical { background:#141b22; width:10px; margin:0; }
QScrollBar::handle:vertical { background:#3b4b59; min-height:28px; border-radius:4px; }
QScrollBar:horizontal { background:#141b22; height:10px; margin:0; }
QScrollBar::handle:horizontal { background:#3b4b59; min-width:28px; border-radius:4px; }
QScrollBar::add-line,QScrollBar::sub-line { width:0; height:0; }
QCheckBox { spacing:7px; padding:3px; }
QCheckBox::indicator { width:14px; height:14px; border:1px solid #7993a5; border-radius:3px; background:#202b36; }
QCheckBox::indicator:checked { background:#54c6ed; border:2px solid #b4edff; }
QCheckBox:focus { border:1px solid #54c6ed; }
QToolTip { background:#253747; color:#f2f7fb; border:1px solid #608296; padding:5px; }
'''

def apply_theme(app):
    for face in ('segoeui.ttf','segoeuib.ttf','seguisym.ttf'):
        path=Path('C:/Windows/Fonts')/face
        if path.exists(): QFontDatabase.addApplicationFont(str(path))
    app.setStyle('Fusion'); app.setFont(QFont('Segoe UI', 10)); app.setStyleSheet(STYLE)
    app.setWindowIcon(QIcon(str(ASSETS / 'sfx-vault.ico')))
