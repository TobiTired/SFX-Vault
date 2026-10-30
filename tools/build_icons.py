"""Render editable vector masters and package PNG frames into a Windows ICO."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import struct
from pathlib import Path
from PySide6.QtCore import QByteArray,QBuffer,QIODevice,QRectF,Qt
from PySide6.QtGui import QImage,QPainter,QColor,QFont,QFontDatabase
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'sfx_vault/assets'
SIZES=(16,20,24,32,40,48,64,128,256)
MARKS={
 '01-vault-wave': ('Vault / Wave', '<rect x="51" y="51" width="154" height="154" rx="24" fill="none" stroke="#728a9b" stroke-width="12"/><path d="M81 113v30m24-48v66m23-84v102m23-84v66m24-48v30" stroke="#66d7f4" stroke-width="12" stroke-linecap="round"/>'),
 '02-signal-s': ('Signal / S', '<path d="M177 76H99L73 102l28 26h54l28 26-26 26H79" fill="none" stroke="#66d7f4" stroke-width="21" stroke-linecap="square" stroke-linejoin="bevel"/><path d="M128 51v24m0 106v24" stroke="#728a9b" stroke-width="10"/>'),
 '03-wave-tile': ('Wave / Tile', '<path d="M61 112v32m33-62v92m34-115v138m34-115v92m33-62v32" stroke="#66d7f4" stroke-width="16" stroke-linecap="round"/>'),
 '04-audio-archive': ('Audio / Archive', '<path d="M58 78h140M68 58h120M58 99v94h140V99" fill="none" stroke="#728a9b" stroke-width="12" stroke-linejoin="round"/><path d="M91 136v22m25-44v66m25-66v66m25-44v22" stroke="#66d7f4" stroke-width="11" stroke-linecap="round"/>'),
}

def svg(mark):
    return '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256"><rect x="8" y="8" width="240" height="240" rx="47" fill="#131c25" stroke="#344857" stroke-width="5"/>'+mark+'</svg>'

def render(source,size):
    image=QImage(size,size,QImage.Format_ARGB32); image.fill(Qt.transparent)
    painter=QPainter(image); QSvgRenderer(QByteArray(source.encode())).render(painter); painter.end(); return image

def png_bytes(image):
    data=QByteArray(); buffer=QBuffer(data); buffer.open(QIODevice.WriteOnly); image.save(buffer,'PNG'); return bytes(data)

def build():
    app=QApplication.instance() or QApplication([]); DEST.mkdir(exist_ok=True); concepts=DEST/'concepts'; concepts.mkdir(exist_ok=True)
    for face in ('segoeui.ttf','segoeuib.ttf'): QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+face)
    sheet=QImage(1280,540,QImage.Format_ARGB32); sheet.fill(QColor('#101419')); p=QPainter(sheet); p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QColor('#e8f2fa')); p.setFont(QFont('Segoe UI',22,QFont.Bold)); p.drawText(40,51,'SFX VAULT / ICON EXPLORATIONS')
    p.setFont(QFont('Segoe UI',11)); p.setPen(QColor('#91a5b7')); p.drawText(40,80,'Charcoal + cyan · geometric audio marks · shown at large and taskbar sizes')
    for index,(key,(title,mark)) in enumerate(MARKS.items()):
        source=svg(mark); (concepts/(key+'.svg')).write_text(source,encoding='utf-8'); render(source,512).save(str(concepts/(key+'.png')))
        x=40+index*310; p.drawImage(x+35,120,render(source,200)); p.setPen(QColor('#e8f2fa')); p.setFont(QFont('Segoe UI',14,QFont.Bold)); p.drawText(x,365,title)
        p.setFont(QFont('Segoe UI',10)); p.setPen(QColor('#91a5b7')); p.drawText(x,392,'Recommended' if index==0 else 'Alternative '+str(index+1))
        offset=0
        for size in (16,24,32,48): p.drawImage(x+offset,425,render(source,size)); offset+=size+18
    p.end(); sheet.save(str(DEST/'icon-concepts.png'))
    final=svg(MARKS['01-vault-wave'][1]); (DEST/'sfx-vault.svg').write_text(final,encoding='utf-8'); render(final,512).save(str(DEST/'sfx-vault.png'))
    frames=[png_bytes(render(final,size)) for size in SIZES]; offset=6+16*len(frames); entries=[]
    for size,data in zip(SIZES,frames):
        entries.append(struct.pack('<BBBBHHII',size%256,size%256,0,0,1,32,len(data),offset)); offset+=len(data)
    (DEST/'sfx-vault.ico').write_bytes(struct.pack('<HHH',0,1,len(frames))+b''.join(entries)+b''.join(frames))
    navigation=DEST/'navigation'; navigation.mkdir(exist_ok=True)
    paths={
        'library':'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z',
        'favorite':'M12 20 4 12C-1 5 8 1 12 7c4-6 13-2 8 5z',
        'recent':'M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16M12 7v5l4 2',
        'pending':'M12 3 2 21h20zM12 9v5M12 17v1',
        'category':'M4 9v6M8 6v12M12 3v18M16 6v12M20 9v6',
        'collection':'M3 8l9-5 9 5-9 5zM3 12l9 5 9-5M3 16l9 5 9-5',
        'unknown':'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M9 8c0-4 8-3 6 1l-3 3v2M12 17v1',
    }
    for key,path in paths.items():
        (navigation/(key+'.svg')).write_text('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path d="'+path+'" fill="none" stroke="#8bb8cb" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/></svg>')
    print('Rendered four concepts and nine ICO sizes:',SIZES)

if __name__=='__main__': build()
