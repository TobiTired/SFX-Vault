"""Generate a disposable V0.4 catalog for manual REAPER checks; never reads a real library."""
import math
import struct
import subprocess
import wave
from pathlib import Path
from sfx_vault.core import Catalog, inspect_audio

root=Path(__file__).resolve().parents[1]/'test-data'/'v04-reaper'
audio_folder=root/'samples'; audio_folder.mkdir(parents=True,exist_ok=True)
for name,frequency in [('door-tap.wav',330),('rain-loop.wav',220),('cloth-movement.wav',440)]:
    path=audio_folder/name
    if not path.exists():
        with wave.open(str(path),'wb') as audio:
            audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(22050)
            audio.writeframes(b''.join(struct.pack('<h',int(800*math.sin(2*math.pi*frequency*i/22050))) for i in range(44100)))
encoder=Path('C:/Program Files/Shutter Encoder/app/Library/ffmpeg.exe')
mp3=audio_folder/'cloth-movement.mp3'
if encoder.exists() and not mp3.exists():
    subprocess.run([str(encoder),'-nostdin','-hide_banner','-loglevel','error','-i',str(audio_folder/'cloth-movement.wav'),'-codec:a','libmp3lame','-q:a','5',str(mp3)],check=True)
catalog=Catalog(root/'catalog.sqlite3')
try:
    for path in sorted(audio_folder.iterdir()):
        if path.suffix in ('.wav','.mp3'): catalog.register(inspect_audio(path),'managed')
    catalog.configure('production_workflow',dict(auto_preview=False,volume=20,track_usage=True))
finally: catalog.close()
print(root)
