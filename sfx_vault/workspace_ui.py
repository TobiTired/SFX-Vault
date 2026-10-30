"""V0.6 workspace construction. Existing Window methods own all behavior."""
from PySide6.QtCore import Qt, QSize, QRect
from PySide6.QtGui import QIcon,QColor,QFont
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QComboBox,
    QPushButton,QMenu,QGridLayout,QDoubleSpinBox,QSplitter,QListWidget,QAbstractItemView,
    QFormLayout,QScrollArea,QCheckBox,QSlider,QStyledItemDelegate,QStyle,QStyleOptionViewItem)
from .theme import ASSETS
from .version import VERSION,TEST_EDITION
from .update_ui import show_updates
from .organization import CONFIDENCES
from .workflow import preferences
from .workflow_ui import SeekSlider, CollectionDialog

class NavigationDelegate(QStyledItemDelegate):
    """Paint counts separately so accessible item names and view keys stay stable."""
    def paint(self,painter,option,index):
        count=index.data(Qt.UserRole+2)
        if count is None: return super().paint(painter,option,index)
        painter.save(); option.rect=option.rect.adjusted(0,0,-40,0)
        super().paint(painter,option,index)
        painter.setPen(QColor('#8fc5da')); painter.drawText(QRect(option.rect.right(),option.rect.top(),39,option.rect.height()),Qt.AlignCenter,str(count)); painter.restore()

class SoundDelegate(QStyledItemDelegate):
    def paint(self,painter,option,index):
        row=index.data(Qt.UserRole)
        if not row or option.rect.height()<45: return super().paint(painter,option,index)
        opt=QStyleOptionViewItem(option); self.initStyleOption(opt,index); opt.text=''
        opt.widget.style().drawControl(QStyle.CE_ItemViewItem,opt,painter,opt.widget)
        painter.save(); painter.setPen(QColor('#e0edf5')); painter.drawText(option.rect.adjusted(10,4,-8,-24),Qt.AlignVCenter,index.data())
        font=QFont(option.font); font.setPointSize(max(8,font.pointSize()-1)); painter.setFont(font); painter.setPen(QColor('#91a8b9'))
        secondary=row.get('tags') or row.get('original','')
        painter.drawText(option.rect.adjusted(10,25,-8,-3),Qt.AlignVCenter,painter.fontMetrics().elidedText(secondary,Qt.ElideRight,option.rect.width()-20)); painter.restore()

def label(text, name='Muted'):
    item=QLabel(text); item.setObjectName(name); return item

def menu_button(window, layout, title, actions):
    button=QPushButton(title); menu=QMenu(button)
    for text, callback in actions:
        if text is None: menu.addSeparator()
        else: menu.addAction(text, callback)
    button.setMenu(menu); layout.addWidget(button); return button

def build_workspace(w, table_type, categories_dialog):
    w.setWindowTitle('SFX Vault · V'+VERSION+(' · Update Test' if TEST_EDITION else '')); w.setMinimumSize(1000,640); w.resize(1500,900)
    w.setWindowIcon(QIcon(str(ASSETS/'sfx-vault.ico')))
    central=QWidget(); w.setCentralWidget(central); layout=QVBoxLayout(central)
    layout.setContentsMargins(14,12,14,6); layout.setSpacing(10)
    header=QWidget(); header.setObjectName('Header'); bar=QHBoxLayout(header); layout.addWidget(header)
    brand=label('SFX VAULT','Brand'); brand.setPixmap(QIcon(str(ASSETS/'sfx-vault.ico')).pixmap(32,32)); bar.addWidget(brand)
    bar.addWidget(label('SFX VAULT','Brand')); bar.addSpacing(16)
    w.search=QLineEdit(); w.search.setObjectName('Search'); w.search.setPlaceholderText('Search sounds, filenames, tags…   Ctrl+F'); w.search.setClearButtonEnabled(True); bar.addWidget(w.search,1)
    w.button(bar,'Add library',w.add_library); w.button(bar,'Rescan',w.rescan)
    menu_button(w,bar,'Settings', [('Library settings',w.settings),('Import automation',w.import_settings),('Production workflow & shortcuts',w.production_settings),('Updates & About',lambda:show_updates(w))])
    top=QHBoxLayout(); layout.addLayout(top)
    w.sidebar_toggle=w.button(top,'Library',lambda: toggle_panel(w,'sidebar')); w.sidebar_toggle.setCheckable(True); w.sidebar_toggle.setChecked(True)
    w.page_title=label('All Sounds','PageTitle'); top.addWidget(w.page_title); top.addStretch()
    w.density=QComboBox(); w.density.addItems(['Compact rows','Comfortable rows']); w.density.setAccessibleName('Row density'); top.addWidget(w.density)
    w.inspector_toggle=w.button(top,'Inspector',lambda: toggle_panel(w,'inspector')); w.inspector_toggle.setCheckable(True); w.inspector_toggle.setChecked(True)
    w.split=QSplitter(); w.split.setHandleWidth(7); w.split.setChildrenCollapsible(False); layout.addWidget(w.split,1)
    w.sidebar=QWidget(); w.sidebar.setObjectName('Sidebar'); side=QVBoxLayout(w.sidebar); side.setContentsMargins(8,12,8,8)
    side.addWidget(label('WORKSPACE','Eyebrow')); w.nav=QListWidget(); w.nav.setIconSize(QSize(16,16)); w.nav.setMinimumWidth(185); w.nav.setItemDelegate(NavigationDelegate(w.nav)); side.addWidget(w.nav,1)
    w.button(side,'+ Collection',lambda:CollectionDialog(w).exec()); side.addWidget(label('LOCAL LIBRARY  ·  V'+VERSION,'Eyebrow')); w.split.addWidget(w.sidebar)
    browser=QWidget(); body=QVBoxLayout(browser); body.setContentsMargins(0,0,0,0); body.setSpacing(8); w.split.addWidget(browser)
    tools=QHBoxLayout(); body.addLayout(tools)
    w.types=QComboBox(); w.types.addItems(['All formats','WAV','MP3','FLAC','OGG','OPUS','M4A','AIF','AIFF','WMA','AAC']); tools.addWidget(w.types)
    w.confidence_filter=QComboBox(); w.confidence_filter.addItems(CONFIDENCES); tools.addWidget(w.confidence_filter)
    w.button(tools,'Filters',lambda:w.filter_panel.setVisible(not w.filter_panel.isVisible()))
    w.button(tools,'Reset',w.reset_filters); tools.addStretch()
    menu_button(w,tools,'Organize', [('Preview organization (read only)',lambda:w.organize(True)),('Review organization',lambda:w.organize(False)),('Bulk edit selected',w.bulk_edit),('Manage categories',lambda:categories_dialog(w)),('Manage collections',lambda:CollectionDialog(w).exec())])
    w.filter_panel=QWidget(); grid=QGridLayout(w.filter_panel); grid.setContentsMargins(0,0,0,0); body.addWidget(w.filter_panel); w.filter_panel.hide()
    w.filter_category=QComboBox(); w.filter_category.addItem('Any category')
    w.filter_subcategory=QLineEdit(); w.filter_tags=QLineEdit(); w.filter_tags.setPlaceholderText('Comma-separated')
    w.filter_min=QDoubleSpinBox(); w.filter_max=QDoubleSpinBox()
    for control in (w.filter_min,w.filter_max): control.setRange(0,864000); control.setSuffix(' sec'); control.setSpecialValueText('No limit')
    w.filter_favorite=QComboBox(); w.filter_favorite.addItems(['Any favorite status','Favorites only','Not favorites'])
    w.filter_collection=QComboBox(); w.filter_collection.addItem('Any collection',None)
    w.filter_used=QComboBox(); w.filter_used.addItems(['Any usage','Used sounds only'])
    w.filter_available=QComboBox(); w.filter_available.addItems(['Any availability','Available at last check','Missing / offline at last check'])
    w.filter_sort=QComboBox(); w.filter_sort.addItems(['Default order','Recent use first','Frequent first'])
    w.advanced_controls=[w.filter_category,w.filter_subcategory,w.filter_tags,w.filter_min,w.filter_max,w.filter_favorite,w.filter_collection,w.filter_used,w.filter_available,w.filter_sort]
    for index,(text,control) in enumerate(zip(['Category','Subcategory','Tags','Minimum duration','Maximum duration','Favorite','Collection','Usage','Availability','Order'],w.advanced_controls)):
        row,col=divmod(index,3); cell=QVBoxLayout(); cell.addWidget(label(text)); cell.addWidget(control); grid.addLayout(cell,row,col)
        control.setMinimumWidth(0)
    w.filter_note=label(''); body.addWidget(w.filter_note); w.filter_note.hide()
    w.import_panel=QWidget(); imports=QVBoxLayout(w.import_panel); imports.setContentsMargins(0,0,0,0); body.addWidget(w.import_panel)
    w.import_summary=label(''); w.import_summary.setWordWrap(True); imports.addWidget(w.import_summary)
    row=QHBoxLayout(); imports.addLayout(row); w.import_category=QComboBox(); w.import_category.addItem('All import categories'); row.addWidget(w.import_category)
    w.button(row,'Select all',w.select_all_visible); high=w.button(row,'High confidence',w.select_high)
    row2=QHBoxLayout(); imports.addLayout(row2)
    approve=w.button(row2,'Approve selected…',lambda:w.review('managed')); approve.setObjectName('Primary')
    reject=w.button(row2,'Reject selected…',lambda:w.review('rejected')); check=w.button(row2,'Check now',lambda:w.check_imports(True)); w.button(row2,'Reconsider…',w.reconsider_rejected)
    w.pending_only_buttons=[high,approve,reject,check]
    w.table=table_type(0,6); w.table.setSelectionBehavior(QAbstractItemView.SelectRows); w.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
    w.table.setEditTriggers(QAbstractItemView.NoEditTriggers); w.table.setDragEnabled(True); w.table.setSortingEnabled(True); w.table.setAlternatingRowColors(True); w.table.setShowGrid(False)
    w.table.verticalHeader().hide(); w.table.horizontalHeader().setStretchLastSection(True); w.table.horizontalHeader().setMinimumSectionSize(65)
    w.table.setItemDelegateForColumn(0,SoundDelegate(w.table)); w.table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft|Qt.AlignVCenter)
    w.table.drag_requested.connect(w.prepare_drag); w.table.action_requested.connect(w.list_action); body.addWidget(w.table,1)
    w.browser_note=label('Select to inspect  ·  Space to preview  ·  Drag original files to your DAW'); body.addWidget(w.browser_note)
    w.inspector=QScrollArea(); w.inspector.setWidgetResizable(True); w.inspector.setMinimumWidth(260); w.inspector.setObjectName('Inspector'); w.split.addWidget(w.inspector)
    panel=QWidget(); panel.setObjectName('Inspector'); form=QFormLayout(panel); form.setContentsMargins(14,14,14,14); form.setVerticalSpacing(10); form.setRowWrapPolicy(QFormLayout.WrapAllRows); w.inspector.setWidget(panel)
    form.addRow(label('SOUND PROPERTIES','Eyebrow'))
    w.original=QLabel('Select a sound'); w.original.setWordWrap(True); w.original.setTextInteractionFlags(Qt.TextSelectableByMouse); form.addRow('Original filename · read only',w.original)
    w.name=QLineEdit(); form.addRow('Display name',w.name)
    w.category=QComboBox(); w.category.setEditable(True); w.category.setMinimumContentsLength(10); w.category.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon); form.addRow('Primary category',w.category)
    w.subcategory=QLineEdit(); form.addRow('Subcategory',w.subcategory)
    w.tags=QLineEdit(); w.tags.setPlaceholderText('Tags, separated by commas'); form.addRow('Tags',w.tags)
    w.favorite_check=QCheckBox('Favorite'); form.addRow(w.favorite_check)
    w.save_button=w.button(form,'Save properties',w.save); w.save_button.setObjectName('Primary')
    quick=QHBoxLayout(); form.addRow(quick); w.button(quick,'Copy path',w.copy_path); w.button(quick,'Show file',w.reveal)
    menu_button(w,quick,'More', [('Restore suggested name',w.restore),('Toggle favorite',w.favorite),('Preview sound',w.play)])
    w.button(form,'Add to collection…',w.add_to_collection); w.remove_collection_button=w.button(form,'Remove from this collection',w.remove_from_collection)
    w.detail=QLabel(); w.detail.setWordWrap(True); w.detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
    w.review_label=label('IMPORT REVIEW','Eyebrow'); form.addRow(w.review_label)
    w.approve_import_button=w.button(form,'Approve selected…',lambda:w.review('managed')); w.reject_import_button=w.button(form,'Reject / skip selected…',lambda:w.review('rejected'))
    w.duplicate_choices=QComboBox(); w.duplicate_choices.setMinimumContentsLength(10); w.duplicate_choices.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon); form.addRow('Matching files',w.duplicate_choices)
    w.preview_match=w.button(form,'Preview matching file',w.preview_duplicate); w.reveal_match=w.button(form,'Open matching location',w.reveal_duplicate)
    w.match_label=form.labelForField(w.duplicate_choices); form.addRow(w.detail)
    for control in (w.approve_import_button,w.reject_import_button): control.setToolTip('Review selected rows in Pending Review. Source files remain in place.')
    player=QWidget(); player.setObjectName('Player'); playerbar=QHBoxLayout(player); playerbar.setContentsMargins(14,12,14,12); layout.addWidget(player)
    w.button(playerbar,'Previous',lambda:w.step(-1)); w.play_button=w.button(playerbar,'Play',w.play); w.play_button.setObjectName('Primary'); w.button(playerbar,'Next',lambda:w.step(1))
    names=QVBoxLayout(); names.addWidget(label('NOW PREVIEWING','Eyebrow')); w.now_playing=QLabel('No preview'); w.now_playing.setMaximumWidth(205); names.addWidget(w.now_playing); playerbar.addLayout(names)
    w.seek=SeekSlider(Qt.Horizontal); w.seek.setAccessibleName('Preview position'); playerbar.addWidget(w.seek,1)
    w.time=QLabel('0:00 / 0:00'); playerbar.addWidget(w.time)
    playerbar.addWidget(label('Volume')); w.volume=QSlider(Qt.Horizontal); w.volume.setRange(0,100); w.volume.setValue(preferences(w.catalog)['volume']); w.volume.setMaximumWidth(100); w.volume.setAccessibleName('Preview volume'); playerbar.addWidget(w.volume)
    w.split.setStretchFactor(0,0); w.split.setStretchFactor(1,1); w.split.setStretchFactor(2,0); w.split.setSizes([205,900,300])
    saved=w.catalog.setting('ui_layout',{}); w.panel_sizes=saved.get('panels',[205,900,300])
    w.split.setSizes(w.panel_sizes)
    for key in ('sidebar','inspector'):
        visible=bool(saved.get(key,True)); getattr(w,key).setVisible(visible); getattr(w,key+'_toggle').setChecked(visible)
    w.density.setCurrentIndex(1 if saved.get('comfortable',False) else 0); set_density(w)
    w.density.currentIndexChanged.connect(lambda:set_density(w))
    w.split.splitterMoved.connect(lambda *_: remember_sizes(w))
    for field,name in ((w.search,'Search library'),(w.name,'Display name'),(w.category,'Primary category'),(w.subcategory,'Subcategory'),(w.tags,'Tags')): field.setAccessibleName(name)

def set_density(w):
    w.table.verticalHeader().setDefaultSectionSize(48 if w.density.currentIndex() else 33)

def remember_sizes(w):
    sizes=w.split.sizes()
    for index in (0,1,2):
        if sizes[index]>0: w.panel_sizes[index]=sizes[index]

def toggle_panel(w,key):
    remember_sizes(w)
    panel=getattr(w,key); visible=panel.isHidden(); panel.setVisible(visible)
    getattr(w,key+'_toggle').setChecked(visible)
    if visible: w.split.setSizes(w.panel_sizes)

def save_layout(w):
    remember_sizes(w)
    w.catalog.configure('ui_layout',dict(panels=w.panel_sizes,sidebar=not w.sidebar.isHidden(),inspector=not w.inspector.isHidden(),comfortable=bool(w.density.currentIndex())))
