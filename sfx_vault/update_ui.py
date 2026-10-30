"""Update controls added to the approved Settings menu without changing its layout."""
from pathlib import Path
import sqlite3,time
from PySide6.QtCore import QThread,Signal,Qt,QTimer,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QCheckBox,QPushButton,QPlainTextEdit,QProgressBar,QMessageBox
from .version import VERSION,DEFAULT_REPOSITORY
from .updates import GitHubClient,LocalTestClient,repository,releases_url,download,verify_installer,start_installer_helper

class UpdateWorker(QThread):
    result=Signal(object); failed=Signal(str); progress=Signal(int,int)
    def __init__(self,client,release=None): super().__init__(); self.client=client; self.release=release
    def run(self):
        try:
            value=download(self.client,self.release,self.progress.emit,self.isInterruptionRequested) if self.release else self.client.latest(VERSION)
            self.result.emit(value)
        except Exception as exc: self.failed.emit(str(exc))

class UpdatesDialog(QDialog):
    def __init__(self,window):
        super().__init__(window); self.window=window; self.worker=None; self.release=None; self.downloaded=None; self.client=None
        self.setWindowTitle('SFX Vault · Updates & About'); self.resize(640,580)
        layout=QVBoxLayout(self); layout.addWidget(QLabel('SFX Vault '+VERSION))
        self.test_manifest=getattr(window,'test_update',None)
        if self.test_manifest: layout.addWidget(QLabel('LOCAL TEST UPDATE · no GitHub release will be installed'))
        settings=window.catalog.setting('updates',{})
        layout.addWidget(QLabel('GitHub repository (owner/repository)'))
        self.repo=QLineEdit(settings.get('repository',DEFAULT_REPOSITORY)); layout.addWidget(self.repo)
        self.auto=QCheckBox('Check for updates at launch (never download or install automatically)'); self.auto.setChecked(settings.get('automatic',False)); layout.addWidget(self.auto)
        row=QHBoxLayout(); layout.addLayout(row)
        self.save_button=QPushButton('Save preferences'); self.save_button.clicked.connect(self.save); row.addWidget(self.save_button)
        self.check_button=QPushButton('Check for Updates'); self.check_button.clicked.connect(self.check); row.addWidget(self.check_button)
        self.link=QPushButton('Open GitHub Releases'); self.link.clicked.connect(self.open_releases); row.addWidget(self.link)
        self.status=QLabel('Updates need your approval. Your catalog and audio remain in place.'); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.notes=QPlainTextEdit(); self.notes.setReadOnly(True); self.notes.setPlaceholderText('Release notes appear here.'); layout.addWidget(self.notes,1)
        self.progress=QProgressBar(); self.progress.setRange(0,100); self.progress.setValue(0); layout.addWidget(self.progress)
        buttons=QHBoxLayout(); layout.addLayout(buttons)
        self.get_button=QPushButton('Download update'); self.get_button.setEnabled(False); self.get_button.clicked.connect(self.get_update); buttons.addWidget(self.get_button)
        self.skip_button=QPushButton('Skip this version'); self.skip_button.setEnabled(False); self.skip_button.clicked.connect(self.skip); buttons.addWidget(self.skip_button)
        self.install_button=QPushButton('Install & restart…'); self.install_button.setEnabled(False); self.install_button.clicked.connect(self.install); buttons.addWidget(self.install_button)
        close=QPushButton('Close'); close.clicked.connect(self.reject); buttons.addWidget(close)
        self.repo.setEnabled(not self.test_manifest); self.auto.setEnabled(not self.test_manifest); self.link.setEnabled(not self.test_manifest)
        self.repo.textEdited.connect(self.invalidate)
    def invalidate(self,*_):
        self.release=None; self.downloaded=None; self.notes.clear(); self.busy(False)
        self.status.setText('Repository changed. Check again before downloading an update.')
    def save(self):
        try:
            repo=repository(self.repo.text())
            existing=self.window.catalog.setting('updates',{})
            if existing.get('repository',DEFAULT_REPOSITORY)!=repo: existing.pop('declined',None); self.invalidate()
            self.window.catalog.configure('updates',existing|dict(repository=repo,automatic=self.auto.isChecked()))
            self.status.setText('Update preferences saved.'); return True
        except Exception as exc: self.status.setText(str(exc)); return False
    def open_releases(self):
        try: QDesktopServices.openUrl(QUrl(releases_url(self.repo.text())))
        except Exception as exc: self.status.setText(str(exc))
    def busy(self,value):
        for control in (self.repo,self.auto,self.save_button,self.check_button): control.setEnabled(not value and (not self.test_manifest or control in (self.check_button,)))
        self.get_button.setEnabled(not value and self.release is not None and self.downloaded is None)
        self.skip_button.setEnabled(not value and self.release is not None)
        self.install_button.setEnabled(not value and self.downloaded is not None)
    def start(self,worker):
        self.worker=worker; self.window.update_workers.append(worker); self.busy(True)
        worker.failed.connect(lambda error:self.status.setText('Update failed: '+error))
        worker.progress.connect(lambda count,total:self.progress.setValue(int(100*count/total)))
        worker.finished.connect(lambda:self.finished(worker)); worker.start()
    def finished(self,worker):
        if worker in self.window.update_workers: self.window.update_workers.remove(worker)
        self.busy(False)
        if self.window.closing: QTimer.singleShot(0,self.window.close)
    def check(self):
        if not self.test_manifest and not self.save(): return
        self.release=None; self.downloaded=None; self.notes.clear(); self.progress.setValue(0); self.status.setText('Checking for a stable release…')
        self.client=LocalTestClient(self.test_manifest) if self.test_manifest else GitHubClient(self.repo.text())
        worker=UpdateWorker(self.client); worker.result.connect(self.available); self.start(worker)
    def available(self,release):
        self.release=release
        if release: self.status.setText('Version '+release.version+' is available. Review the notes before downloading.'); self.notes.setPlainText(release.notes)
        else: self.status.setText('You have the latest stable release.')
    def get_update(self):
        if not self.release: return
        self.status.setText('Downloading and verifying SHA-256…'); worker=UpdateWorker(self.client,self.release); worker.result.connect(self.ready); self.start(worker)
    def ready(self,path): self.downloaded=Path(path); self.status.setText('Version '+self.release.version+' downloaded and checksum verified. Install when ready.')
    def skip(self):
        if self.release and not self.test_manifest:
            existing=self.window.catalog.setting('updates',{}); self.window.catalog.configure('updates',existing|dict(declined=self.release.version))
        self.status.setText('This version will not prompt again automatically. Manual checks remain available.'); self.release=None; self.downloaded=None; self.busy(False)
    def install(self):
        if not self.release or not self.downloaded: return
        w=self.window
        detail='SFX Vault will close after background work finishes, then open the installer. Your catalog and source audio will be retained.'
        if w.form_dirty: detail+='\nUnsaved properties will be discarded. Choose No to save them first.'
        if w.player.playbackState()!=QMediaPlayer.StoppedState: detail+='\nThe current preview will stop.'
        if QMessageBox.question(self,'Install '+self.release.version+'?',detail,QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes: return
        try:
            verify_installer(self.downloaded,self.release.sha256)
            # Durable SQLite backup includes committed WAL data; sources are never copied.
            folder=Path(w.database).parent/'update-backups'; folder.mkdir(exist_ok=True)
            backup=sqlite3.connect(folder/f'catalog-before-{VERSION}-to-{self.release.version}-{time.time_ns()}.sqlite3')
            try: w.catalog.db.backup(backup)
            finally: backup.close()
            # The helper waits for this exact process to exit before running Setup.
            start_installer_helper(self.downloaded,self.release.sha256)
            self.accept(); w.close()
        except Exception as exc: self.status.setText('Installation blocked: '+str(exc))
    def reject(self):
        if self.worker and self.worker.isRunning(): self.worker.requestInterruption(); self.status.setText('Cancelling; waiting for the current network request to finish…'); return
        super().reject()

def show_updates(window):
    if getattr(window,'updates_dialog',None) and window.updates_dialog.isVisible(): window.updates_dialog.raise_(); return
    dialog=UpdatesDialog(window); window.updates_dialog=dialog; dialog.show()

def automatic_check(window):
    settings=window.catalog.setting('updates',{}); repo=settings.get('repository',DEFAULT_REPOSITORY)
    if not settings.get('automatic',False) or not repo or getattr(window,'test_update',None): return
    try: client=GitHubClient(repo)
    except Exception: return
    worker=UpdateWorker(client); window.update_workers.append(worker)
    def result(release):
        if release and settings.get('declined')!=release.version and not window.closing:
            show_updates(window); dialog=window.updates_dialog; dialog.client=client; dialog.available(release); dialog.busy(False)
    worker.result.connect(result); worker.failed.connect(lambda message:window.statusBar().showMessage('Update check unavailable; use Settings → Updates & About to retry.'))
    def done():
        if worker in window.update_workers: window.update_workers.remove(worker)
        if window.closing: QTimer.singleShot(0,window.close)
    worker.finished.connect(done); worker.start()
