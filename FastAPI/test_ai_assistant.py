import asyncio
import os
import sys

# Ajout du chemin racine pour pouvoir importer les modules de FastAPI
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.core.navigator import SmartCourseNavigator

# ==========================================
# 🎛️ PARAMÈTRES RÉGLABLES PAR LE PROFESSEUR
# ==========================================
# Ces valeurs sont celles que tu cherches à optimiser.
# Change-les, relance le script, et observe le résultat.

# Note : pip install fuzzywuzzy python-Levenshtein (si pas déjà fait dans le projet original)
try:
    from fuzzywuzzy import fuzz
except ImportError:
    print("Veuillez installer fuzzywuzzy: pip install fuzzywuzzy python-Levenshtein")
    sys.exit(1)

FUZZY_THRESHOLD = 80          # Score de similarité textuelle requis (sur 100)
SEMANTIC_THRESHOLD = 0.45     # Score de similarité vectoriel (Cosine) - Ajusté pour ColBERT pooling
WINDOW_WORDS_COUNT = 25       # Nombre de mots attendus "en fin de page"
INDEX_PROGRESS_MIN = 0.80     # % de la page franchi (80%) avant d'autoriser un saut

class JitScribeTester:
    def __init__(self, mongo_id: str, start_page: int = 2):
        print("\n🔧 Initialisation du simulateur AI Assistant...")
        self.nav = SmartCourseNavigator()
        self.mongo_id = mongo_id
        self.current_page = start_page
        self.last_word_index = 0
        
        self._load_page_data()

    def _load_page_data(self):
        print(f"\n📄 Chargement des métadonnées - Page {self.current_page}...")
        try:
            # Récupère le nombre total de mots sur cette page
            self.max_index = self.nav.get_page_max_index(self.mongo_id, self.current_page)
            # Récupère la phrase de fin (sur la base de 25 mots)
            self.end_trigger_text = self.nav.get_page_end_trigger(self.mongo_id, self.current_page)
            
            print(f"📊 Statistiques de la page {self.current_page}:")
            print(f"   - Index Max (Total Mots) : {self.max_index}")
            print(f"   - Phrase de fin attendue : '{self.end_trigger_text[-100:]}...'")
        except Exception as e:
            print(f"❌ Erreur lors du chargement de la page {self.current_page} : {e}")
            self.max_index = 0
            self.end_trigger_text = ""

    def simulate_stream(self, spoken_text: str):
        """Simule la réception d'un flux audio converti en texte par Whisper."""
        print(f"\n🗣️ Voix reçue : '{spoken_text}'")
        
        try:
            # 1. Recherche du mot via le Tracker (Simule process_sync de l'orchestrateur)
            # Dans la vraie vie, Whisper envoie mot par mot ou des portions de phrase.
            highlight = self.nav.get_sync_highlight(
                self.mongo_id, 
                self.current_page, 
                spoken_text, 
                # On triche un peu pour le test : on laisse l'algorithme chercher à partir du début 
                # si c'est la première fois, ou on peut le contraindre à self.last_word_index.
                0  
            )
            
            if not highlight:
                print("   ⚠️  Aucun match trouvé sur la page courante.")
                return

            print(f"   🔍 Analyse du Navigator :")
            if "source" in highlight:
                print(f"      - Méthode : {highlight['source'].upper()}")
            if "score" in highlight:
                print(f"      - Confiance : {highlight['score']}%")
            
            hit_index = highlight.get("match_index", highlight.get("index", 0)) or 0
            hit_word = highlight.get("content", "") or highlight.get("text", "")
            
            # Comparaison STT vs PDF
            if hit_word:
                print(f"      - PDF Source : '{hit_word}'")
                print(f"      - STT (Voix): '{spoken_text}'")

            # Mise à jour de la progression
            old_index = self.last_word_index
            if hit_index > self.last_word_index:
                self.last_word_index = hit_index

            progress_pct = hit_index / self.max_index if self.max_index > 0 else 0
            
            print(f"   📍 Suivi :")
            print(f"      ├─ Position : Index {hit_index} / {self.max_index}")
            print(f"      ├─ Progression : {progress_pct:.1%}")
            print(f"      └─ État : {'📈 AVANCE' if hit_index > old_index else '🔄 STAGNATION'}")

            # =========================================================
            # 🚦 SIMULATION DU DÉCLENCHEUR DE CHANGEMENT DE PAGE
            # =========================================================
            
            # CONDITION 1 : L'utilisateur est-il dans la zone critique (ex: > 80% de la page) ?
            if progress_pct > INDEX_PROGRESS_MIN:
                print("\n   ⏳ Zone critique atteinte. Test du changement de page...")
                
                recent_speech = spoken_text.lower()
                trigger_lower = self.end_trigger_text.lower()
                
                # CONDITION 2 : Correspondance lexicale grossière (Ex: 80/100)
                fuzzy_score = fuzz.partial_ratio(recent_speech.strip(), trigger_lower.strip())
                color_fuzz = "✅" if fuzzy_score >= FUZZY_THRESHOLD else "❌"
                print(f"   {color_fuzz} Score Fuzzy (Texte vocal vs Texte fin de page) : {fuzzy_score} / {FUZZY_THRESHOLD}")
                
                if fuzzy_score >= FUZZY_THRESHOLD:
                    # CONDITION 3 : Sécurité Sémantique (Vecteurs)
                    print("   🧠 Vérification sémantique avec la page suivante...")
                    
                    try:
                        # Empreinte ColBERT (ou BGE) de la page suivante
                        next_page_fp = self.nav.get_page_semantic_fingerprint(self.mongo_id, self.current_page + 1)
                        
                        if next_page_fp is not None:
                            import numpy as np
                            # Vecteur local de ce que le prof vient de dire
                            speech_emb = list(self.nav.text_model.embed([spoken_text]))[0]
                            if hasattr(speech_emb, 'ndim') and speech_emb.ndim == 2:
                                speech_emb = np.mean(speech_emb, axis=0)
                            
                            # Calcul mathématique pur du Cosinus (Cosine Similarity)
                            cosine_sim = np.dot(speech_emb, next_page_fp) / (np.linalg.norm(speech_emb) * np.linalg.norm(next_page_fp))
                            
                            color_sem = "✅" if cosine_sim > SEMANTIC_THRESHOLD else "❌"
                            print(f"   {color_sem} Score Sémantique (Sens vocal vs Sens Page N+1) : {cosine_sim:.3f} / {SEMANTIC_THRESHOLD}")
                            
                            if cosine_sim > SEMANTIC_THRESHOLD:
                                print("\n   🚀 BOUM ! CHANGEMENT DE PAGE DÉCLENCHÉ !")
                                print(f"   ➡️  Ton React va recevoir un événement NAVIGATE_RESULT pour la page {self.current_page + 1}\n")
                                
                                # Le test avance à la page suivante
                                self.current_page += 1
                                self.last_word_index = 0
                                self._load_page_data()
                            else:
                                print("   ❌ Refusé : Mots exacts, mais le sens vectoriel de la phrase ne correspond pas à la page suivante.")
                    except Exception as e:
                        print(f"   ⚠️ Erreur calcul Vecteur/Sémantique dans le test : {e}")
                else:
                    print(f"   ❌ Refusé : FuzzyScore insuffisant. (Vous avez dit '{recent_speech}', on attendait du '{trigger_lower}')")
            
        except Exception as e:
            print(f"   ❌ Erreur d'exécution de get_sync_highlight : {e}")


if __name__ == "__main__":
    print("=========================================================")
    print("🧪 SIMULATEUR AI ASSISTANT : TWEAKER LE CHANGEMENT DE PAGE ")
    print("=========================================================")
    print("Objectif : Ajuster FUZZY_THRESHOLD, SEMANTIC_THRESHOLD et")
    print("INDEX_PROGRESS_MIN sans toucher à orchestrator.py ni lancer React.")
    print("---------------------------------------------------------")
    
    # Remplace cette string par un VRAI Mongo ID de ta BD
    TEST_MONGO_ID = "69c810dd139359198fc1aaf1" # <-- Mis à jour après ré-upload !
    
    # Petit menu CLI pour éviter de hardcoder si nécessaire
    user_id = input(f"Entrez un mongo_file_id (Entrée pour utiliser {TEST_MONGO_ID}) : ").strip()
    if user_id:
        TEST_MONGO_ID = user_id
        
    try:
        tester = JitScribeTester(TEST_MONGO_ID, start_page=5)
        
        print("\n🎤 Tapez exactement ce que le prof dirait au micro pour la page 1.")
        print("   Exemples : " )
        print("   - Phrase aléatoire du milieu : 'L'opacité est visible ici...'")
        print("   - Fin de page exacte : 'Et c'est tout pour l'introduction au ventricule.'")
        print("   (Tapez 'exit' pour quitter)\n")
        
        while True:
            phrase = input("> Vous dites : ")
            if phrase.lower() in ['exit', 'quit', 'q']:
                break
            if not phrase.strip():
                continue
                
            tester.simulate_stream(phrase)
            
    except KeyboardInterrupt:
        print("\nFin de la simulation.")

