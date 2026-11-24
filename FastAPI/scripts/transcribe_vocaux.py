from faster_whisper import WhisperModel
import os

model = WhisperModel('base', device='cpu', compute_type='int8')
files = [
    'test_audio/Lecture page 5.m4a',
    'test_audio/Passage page 5.m4a',
    'test_audio/Lecture page 6.m4a',
    'test_audio/Assistant mourad.m4a'
]

for f in files:
    full_path = os.path.abspath(f)
    if os.path.exists(full_path):
        print(f"--- Transcribing {f} ---")
        segments, _ = model.transcribe(full_path)
        text = ' '.join([s.text for s in segments])
        print(text)
    else:
        print(f"--- Fichier non trouvé : {full_path} ---")
