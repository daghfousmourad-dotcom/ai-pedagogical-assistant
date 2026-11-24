import asyncio
import os
import sys

# Ajout du chemin racine pour les imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.core.navigator import SmartCourseNavigator
from services.core.orchestrator import OrchestratorService
from services.agents.voice_utils import VoiceAgentUtils
from services.agents.rag import RAGService
from services.agents.image_clarifier import ImageClarifierAgent

# Données des transcriptions réelles (Extraites des fichiers .m4a par Whisper)
AUDIO_TRANSCRIPTS = {
    "test_audio/Lecture page 5.m4a": "Utilisation pour de l'intégration continue, c.I. Environnement de test créé à partir d'une image d'occaire. Les tests peuvent être exécutés sur n'importe quelle plateforme, plateforme de c.I. Un nouveau cantonneur créé pour chaque étape de test. Pas de pollution entre les étapes d'un test, pas de pollution entre plusieurs executions de test. Les tests peuvent être exécutés très souvent.",
    "test_audio/Passage page 5.m4a": "Mouert passe à la page Sainte.",
    "test_audio/Lecture page 6.m4a": "Utilisation pour la distribution d'artéfacts. Construire notre application à partir de Docker5, stocker les images dans un registre, stockage pérenne, accessible pour tout le monde, exécuter en production, les images contiennent toutes les dépendances pour vos applications, versionnage possibilité de taguer les images.",
    "test_audio/Assistant mourad.m4a": "Bonjour, pour cette session, le nom de l'assistant est Murat."
}

TEST_MONGO_ID = "69c810dd139359198fc1aaf1" 
SESSION_ID = "real_audio_test"

async def test_audio_robustness():
    print("📢 [REAL AUDIO TEST] Lancement de la validation par vocaux réels...\n")
    
    nav = SmartCourseNavigator()
    voice = VoiceAgentUtils()
    rag = RAGService()
    clarifier = ImageClarifierAgent()
    orch = OrchestratorService(nav, voice, rag, clarifier)
    
    # Étape 1 : Commande de Navigation ("Mouert passe à la page Sainte")
    print(f"--- Fichier : Passage page 5.m4a ---")
    transcript_cmd = AUDIO_TRANSCRIPTS["test_audio/Passage page 5.m4a"]
    print(f"🎤 Transcrit : '{transcript_cmd}'")
    
    result_cmd = await orch.process_sync(TEST_MONGO_ID, 1, transcript_cmd, SESSION_ID, "PROFESSOR")
    
    if result_cmd and result_cmd.get("type") == "NAVIGATE_RESULT":
        data = result_cmd["data"]
        print(f"✅ Commande détectée : {data['action']} vers page {data['target_page']}")
    else:
        print("❌ ÉCHEC : La commande de navigation n'a pas été détectée.")

    # Étape 2 : Lecture p.5 (Vérifier le surlignage malgré les erreurs "d'occaire", "cantonneur")
    print(f"\n--- Fichier : Lecture page 5.m4a ---")
    transcript_p5 = AUDIO_TRANSCRIPTS["test_audio/Lecture page 5.m4a"]
    print(f"🎤 Transcrit : '{transcript_p5[:60]}...'")
    
    # On simule l'envoi progressif ou global
    result_p5 = await orch.process_sync(TEST_MONGO_ID, 5, transcript_p5, SESSION_ID, "PROFESSOR")
    
    if result_p5 and result_p5.get("type") == "SYNC_HIGHLIGHT":
        data = result_p5["data"]
        print(f"✅ Surlignage trouvé : '{data.get('text')}'")
        print(f"⚓ Anchor Index : {data.get('index')}")
    else:
        print("❌ ÉCHEC : Aucun surlignage malgré la lecture.")

    # Étape 3 : Lecture p.6 ("Docker5", "artéfacts")
    print(f"\n--- Fichier : Lecture page 6.m4a ---")
    transcript_p6 = AUDIO_TRANSCRIPTS["test_audio/Lecture page 6.m4a"]
    print(f"🎤 Transcrit : '{transcript_p6[:60]}...'")
    
    result_p6 = await orch.process_sync(TEST_MONGO_ID, 6, transcript_p6, SESSION_ID, "PROFESSOR")
    
    if result_p6 and result_p6.get("type") == "SYNC_HIGHLIGHT":
        data = result_p6["data"]
        print(f"✅ Surlignage p.6 trouvé : '{data.get('text')}'")
    else:
        print("❌ ÉCHEC : Problème sur la page 6.")

    print("\n🏁 [Test Audio] Terminé.")

if __name__ == "__main__":
    asyncio.run(test_audio_robustness())
