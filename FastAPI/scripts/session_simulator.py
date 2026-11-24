import os
import sys
import asyncio
import time
from datetime import datetime

# Ajout du chemin racine pour les imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.audio.whisper_bridge import WhisperBridge
from services.core.orchestrator import OrchestratorService
from services.core.navigator import SmartCourseNavigator
from services.agents.voice_utils import VoiceAgentUtils
from services.agents.rag import RAGService
from services.agents.image_clarifier import ImageClarifierAgent

# --- CONFIGURATION DU TEST ---
TEST_MONGO_ID = "69c810dd139359198fc1aaf1" # Document par défaut
AUDIO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test_audio")
SESSION_ID = "sim_session_debug"

async def run_simulation():
    print(f"🚀 [INIT] Démarrage de la simulation AI Assistant...")
    
    # 1. Initialisation des services (Simule api/dependencies.py)
    import redis.asyncio as aioredis
    redis_client = await aioredis.from_url("redis://localhost:6379/0", encoding="utf-8", decode_responses=True)
    
    nav = SmartCourseNavigator()
    voice = VoiceAgentUtils()
    rag = RAGService()
    clarifier = ImageClarifierAgent()
    
    # On utilise maintenant le vrai client Redis pour tester les verrous réels
    orch = OrchestratorService(nav, voice, rag, clarifier, redis_client=redis_client)
    
    bridge = WhisperBridge.get_instance()
    if not bridge.is_available():
        print("❌ ERREUR: Whisper n'est pas chargé.")
        return

    # 2. Liste des fichiers audios (dans l'ordre logique supposé)
    audio_files = [
        "Assistant mourad.m4a",
        "Lecture page 5.m4a",
        "Passage page 5.m4a",
        "Lecture page 6.m4a"
    ]
    
    current_page = 5 # On commence sur la page 5 comme suggéré par les fichiers
    
    # --- TEST SPÉCIFIQUE (FAUX POSITIF NLP) ---
    print("\n=== TEST SPÉCIFIQUE : TOLÉRANCE NLP STEMMER PAGE 5 ===")
    texte_partiel = "pas de pollution entre plusieurs exécution des test le test peut être exécuté très souvent"
    print(f"📡 [API] SYNC Payload (Page 5) : {texte_partiel}")
    
    res_partiel = await orch.process_sync(
        mongo_id=TEST_MONGO_ID,
        current_page=5,
        speech_text=texte_partiel,
        role="PROFESSOR",
        session_id=SESSION_ID
    )
    
    if res_partiel.get("type") == "IGNORE":
        print("✅ SUCCÈS : Le saut a été correctement validé (tolérance pluriel/conjugaison prouvée !)")
    else:
        print("❌ ÉCHEC : Le saut a été bloqué au lieu d'être validé.")
    
    await asyncio.sleep(2)
    print("\n=== FIN TEST SPÉCIFIQUE ===\n")
    
    print(f"--- Fichiers détectés dans {AUDIO_DIR} ---")
    for f in audio_files:
        path = os.path.join(AUDIO_DIR, f)
        if not os.path.exists(path):
            print(f"⚠️  Fichier manquant : {f}")
            continue
        
        print(f"\n🎧 [AUDIO] Fichier: {f}")
        
        # A. Transcription réelle via Whisper
        print(f"🎤 [STT] Transcription en cours...")
        segments, info = bridge.model.transcribe(path, language="fr")
        full_text = " ".join(s.text for s in segments).strip()
        print(f"📝 [Result] '{full_text}'")
        
        if not full_text:
            print("   (Audio vide ou non reconnu par Whisper)")
            continue

        # B. Injection dans l'Orchestrateur (process_sync)
        # On envoie le segment COMPLET car c'est ainsi que WhisperBridge fonctionne en prod
        print(f"\n📡 [API] SYNC Payload (Page {current_page}): {full_text}")
        
        res = await orch.process_sync(
            mongo_id=TEST_MONGO_ID,
            current_page=current_page,
            speech_text=full_text,
            role="PROFESSOR",
            session_id=SESSION_ID
        )
        
        # Analyse de la réponse
        if res.get("type") == "NAVIGATE_RESULT":
            action = res["data"].get("action")
            target = res["data"].get("target_page")
            print(f"🚀 [NAVIGATION] Action {action} détectée vers p.{target} !")
            current_page = target # On met à jour l'état local du simulateur
        elif res.get("type") == "IGNORE":
            # L'orchestrateur peut ignorer pour cause de barrière ou délai
            pass
        
        # Simulation du délai entre segments
        await asyncio.sleep(1.0) 

    print("\n🏁 [FIN] Simulation terminée.")

if __name__ == "__main__":
    asyncio.run(run_simulation())
