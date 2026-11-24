import asyncio
import os
import sys
import re

# Ajout du chemin racine pour les imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.core.navigator import SmartCourseNavigator
from services.core.orchestrator import OrchestratorService
from services.agents.voice_utils import VoiceAgentUtils
from services.agents.rag import RAGService
from services.agents.image_clarifier import ImageClarifierAgent

# Configuration du test (ID de document réel extrait de vos logs)
TEST_MONGO_ID = "69c810dd139359198fc1aaf1" 
SESSION_ID = "robot_test_session"

async def robot_test_coherence():
    print("🤖 [Robot Test] Démarrage du test de cohérence Navigation/Surlignage...")
    
    # Initialisation simplifiée (on mock les agents secondaires pour aller vite)
    nav = SmartCourseNavigator()
    voice = VoiceAgentUtils()
    rag = RAGService()
    clarifier = ImageClarifierAgent()
    
    orch = OrchestratorService(nav, voice, rag, clarifier)
    
    # 1. Simulation d'un début de lecture sur la page 5
    # Phrase : "Utilisation pour de l'intégration"
    speech = "utilisation pour de l'intégration"
    print(f"\n🎤 Étape 1 : Lecture de '{speech}'")
    
    # On joue le rôle de l'orchestrateur pour voir l'interaction
    last_word_index = 0
    current_page = 5
    
    # A. Navigation (Calcul de l'ancre)
    anchor = await orch.nav_logic.get_current_anchor(
        TEST_MONGO_ID, current_page, speech, last_word_index
    )
    print(f"⚓ Position Ancre détectée : {anchor}")
    
    # B. Surlignage (Utilisation de l'ancre)
    highlight = await orch.highlight_logic.get_highlight(
        TEST_MONGO_ID, current_page, speech, last_word_index, anchor_index=anchor
    )
    
    if highlight:
        print(f"✅ Surlignage réussi sur l'index {highlight.get('index')}")
        print(f"📍 Texte surligné : '{highlight.get('text')}'")
        print(f"🔦 Source : {highlight.get('source')}")
        last_word_index = highlight.get('index')
    else:
        print("❌ Échec du surlignage.")

    # 2. Simulation de la suite (Vérifier si l'ancre avance)
    speech_2 = "environnement de test créé à partir d'une image docker"
    print(f"\n🎤 Étape 2 : Lecture de '{speech_2}'")
    
    anchor_2 = await orch.nav_logic.get_current_anchor(
        TEST_MONGO_ID, current_page, speech_2, last_word_index
    )
    print(f"⚓ Position Ancre détectée : {anchor_2}")
    
    highlight_2 = await orch.highlight_logic.get_highlight(
        TEST_MONGO_ID, current_page, speech_2, last_word_index, anchor_index=anchor_2
    )

    if highlight_2 and anchor_2 > anchor:
        print(f"✅ Progression confirmée : Index {highlight_2.get('index')} (Ancre a avancé)")
        print(f"📍 Texte : '{highlight_2.get('text')}'")
    else:
        print("❌ Problème de progression ou de détection.")

    print("\n🏁 [Robot Test] Fin des tests. Vérifiez les logs ci-dessus pour la cohérence.")

if __name__ == "__main__":
    asyncio.run(robot_test_coherence())
