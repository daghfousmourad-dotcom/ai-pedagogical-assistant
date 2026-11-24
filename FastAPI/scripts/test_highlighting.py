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

# Configuration du test
TEST_MONGO_ID = "69c810dd139359198fc1aaf1" # ID du document PDF de test
SESSION_ID = "test_highlight_session"

async def test_highlight_comparison():
    print("🔍 Initialisation des services...")
    nav = SmartCourseNavigator()
    voice = VoiceAgentUtils()
    rag = RAGService()
    clarifier = ImageClarifierAgent()
    
    orch = OrchestratorService(nav, voice, rag, clarifier)
    
    # Phrases de test (Bribes lues par le professeur sur la page 5)
    test_segments = [
        "utilisation pour de l'intégration continue",
        "environnement de test créé à partir d'une image docker",
        "les tests peuvent être exécutés sur n'importe quelle plateforme",
        "un nouveau conteneur créé pour chaque étape de test",
        "pas de pollution entre les étapes d'un test"
    ]

    async def run_suite(mode_name, use_dtw):
        print(f"\n🚀 === TEST MODE : {mode_name} (use_dtw={use_dtw}) ===")
        orch.highlight_logic.use_dtw = use_dtw
        last_index = 0
        
        for segment in test_segments:
            print(f"\n🎤 Transcription : '{segment}'")
            # Appel direct à la logique de surlignage pour isoler le test
            highlight = await orch.highlight_logic.get_highlight(
                mongo_id=TEST_MONGO_ID,
                current_page=5,
                speech_text=segment,
                last_word_index=last_index
            )
            
            if highlight and (highlight.get("index") is not None or highlight.get("bbox")):
                last_index = highlight.get("index", last_index)
                source = highlight.get("source", "unknown")
                text = highlight.get("text") or highlight.get("content")
                print(f"✅ Surlignage : '{text}' | Index: {last_index} | Source: {source}")
                print(f"📍 BBox : {highlight['bbox']}")
            else:
                print("❌ Aucun surlignage détecté.")

    # Exécution des trois modes pour comparaison
    await run_suite("ALIGNEMENT ÉLASTIQUE (DTW)", 1)
    
    # Reset de la session
    if orch.redis: await orch.redis.delete(f"sync:{SESSION_ID}:{TEST_MONGO_ID}")
    else: orch._local_state = {}

    await run_suite("RECHERCHE SÉMANTIQUE (FUZZY)", 2)

    # Reset de la session
    if orch.redis: await orch.redis.delete(f"sync:{SESSION_ID}:{TEST_MONGO_ID}")
    else: orch._local_state = {}

    await run_suite("POINTEUR SÉQUENTIEL (PFE)", 3)

if __name__ == "__main__":
    asyncio.run(test_highlight_comparison())
