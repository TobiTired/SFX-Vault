"""Generate quiet sample tones in a new folder, without touching a real library."""
import math
import struct
import wave
from pathlib import Path

root = Path(__file__).resolve().parents[1] / 'sample-library'
for folder, name, frequency in [('rain', 'rain-window-75830.wav', 220), ('doors', 'wooden-door-knocking.wav', 440), ('custom', 'mystery-123456.wav', 660)]:
    path = root / folder / name
    if path.exists(): continue
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(22050)
        audio.writeframes(b''.join(struct.pack('<h', int(1500 * math.sin(2 * math.pi * frequency * i / 22050))) for i in range(22050)))
print(root)
