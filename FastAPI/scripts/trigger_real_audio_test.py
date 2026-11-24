
import asyncio
import os
import requests
from faster_whisper import WhisperModel

async def run_injected_audio_test():
    print("🎤 [Injection Audio] Chargement de Whisper...")
    model = WhisperModel('base', device='cpu', compute_type='int8')
    
    audio_path = "/Volumes/MonSSD/pfe/test-microservices/FastAPI/test_audio/Passage page 5.m4a"
    if not os.path.exists(audio_path):
        # Fallback si le chemin est différent
        audio_path = "/Volumes/MonSSD/pfe/test-microservices/FastAPI/uploads/tts_01d296766c374e739c9bcdb79a24cd0d.mp3"

    print(f"📖 [Injection Audio] Transcription de : {audio_path}")
    segments, _ = model.transcribe(audio_path)
    text = " ".join([s.text for s in segments])
    print(f"✅ [Transcription] Reconnu : '{text}'")

    # Envoi à l'Orchestrateur via l'API locale
    # On utilise l'ID du document cible pour simuler l'interaction dans la session
    payload = {
        "mongo_file_id": "69d00591b677d40ea1b902d6",
        "current_page": 1,
        "text": text,
        "role": "PROFESSOR",
        "command": "NAVIGATE"
    }

    print("🚀 [Orchestrateur] Envoi de la commande...")
    try:
        response = requests.post("http://localhost:5005/api/ai/orchestrate", json=payload)
        print(f"📡 [Réponse IA] : {response.status_code}")
        print(response.json())
    except Exception as e:
        print(f"❌ [Erreur] : {e}")

if __name__ == "__main__":
    asyncio.run(run_injected_audio_test())
