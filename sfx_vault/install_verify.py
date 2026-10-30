"""Explicit diagnostic mode for disposable installed-build acceptance tests."""
import json,sys,time
from pathlib import Path
from PySide6.QtCore import QTimer,Qt
from .version import VERSION

def verify(window,report):
    result=dict(version=VERSION,frozen=bool(getattr(sys,'frozen',False)),rows=window.table.rowCount(),playback=[])
    window.search.setText('cloth'); window.refresh(); result['search_rows']=window.table.rowCount(); window.reset_filters()
    sounds=[dict(row) for row in window.catalog.rows() if row['format'] in ('MP3','WAV')]
    chosen=[]
    for kind in ('WAV','MP3'):
        if any(row['format']==kind for row in sounds): chosen.append(next(row for row in sounds if row['format']==kind))
    timer=QTimer(window); start=[0.0]; active=[None]
    def finish():
        timer.stop(); window.stop_playback(); Path(report).write_text(json.dumps(result,indent=2),encoding='utf-8'); window.close()
    def tick():
        if active[0] is None:
            if not chosen: finish(); return
            row=chosen.pop(0); active[0]=row; start[0]=time.monotonic(); window.play_path(row['path'],restart=True); return
        if window.player.position()>0 and window.player.duration()>0:
            result['playback'].append(dict(format=active[0]['format'],progress=True)); active[0]=None; window.stop_playback()
        elif time.monotonic()-start[0]>10:
            result['playback'].append(dict(format=active[0]['format'],progress=False,error=window.player.errorString())); active[0]=None
    timer.timeout.connect(tick); timer.start(100)
