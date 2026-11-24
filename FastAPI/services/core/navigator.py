# ==============================================================================
# PROPRIÉTÉ DE AI ASSISTANT - (c) 2024-2026 Mourad Daghfous
# Système d'Interaction Vocale Intelligent pour l'Éducation
# ------------------------------------------------------------------------------
# Ce fichier est confidentiel et protégé par les lois sur la propriété 
# intellectuelle. Toute diffusion non autorisée est passible de poursuites.
# ==============================================================================
import asyncio
import sys
import json
import os
from typing import Optional
from pymongo import MongoClient
from bson import ObjectId
from qdrant_client import QdrantClient, models
from fuzzywuzzy import process
from fastembed import LateInteractionTextEmbedding, TextEmbedding
from services.utils.mlops_config import get_active_embedding_config
from functools import lru_cache
import logging
import numpy as np
import fitz # PyMuPDF
import threading # Pour le prefetching en arrière-plan

logging.basicConfig(level=logging.ERROR)
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# --- Fallback natif pour exécution locale ---
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
# ⚠️ COLLECTION_NAME_FALLBACK sert de valeur par défaut si config absente
COLLECTION_NAME_FALLBACK = os.getenv("COLLECTION_NAME", "Vector_Embeddings")

class SmartCourseNavigator:
    def __init__(self):
        self.mongo_client = MongoClient(MONGO_URI)
        self.db = self.mongo_client['identity_db']
        self.qdrant_client = QdrantClient(QDRANT_URL)
        # Chemin vers le cache central (optimisé pour Docker)
        CACHE_DIR = os.getenv("FASTEMBED_CACHE_PATH", "/Volumes/MonSSD/pfe/ai_models_cache/fastembed")
        
        self.config = get_active_embedding_config()
        self.COLLECTION_NAME = self.config.get("qdrant_collection", COLLECTION_NAME_FALLBACK)
        text_model_name = self.config.get("text_model", "colbert-ir/colbertv2.0")
        self.is_colbert = "colbert" in text_model_name.lower()
        self.TEXT_VECTOR_NAME = "colbert_text" if self.is_colbert else "text"
        
        print(f"📦 Navigator : Chargement du modèle {text_model_name} depuis {CACHE_DIR}...")
        if self.is_colbert:
            self.text_model = LateInteractionTextEmbedding(
                model_name=text_model_name,
                cache_dir=CACHE_DIR,
                verbose=False
            )
        else:
            self.text_model = TextEmbedding(
                model_name=text_model_name,
                cache_dir=CACHE_DIR
            )

        # Modèle MiniLM ONNX Quantized pour le word-sync (Ultra-rapide)
        self.fast_model = TextEmbedding(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            cache_dir=CACHE_DIR
        )
        
        # Cache pour les chemins de fichiers (mongo_id -> local_path)
        self._pdf_path_cache = {}
        # Cache pour les configurations effectives (mongo_id -> dict)
        self._config_cache = {}
        # Tracking du prefetching pour éviter les doublons
        self._last_prefetched_key = None # (mongo_id, next_page)

    def _get_effective_config(self, mongo_id: str):
        """
        Résout la configuration Qdrant (Collection/Vecteur) à utiliser pour ce document.
        Assure la cohérence Multi-Version (Version Locking).
        """
        if not mongo_id:
            return self.COLLECTION_NAME, self.TEXT_VECTOR_NAME
            
        if mongo_id in self._config_cache:
            return self._config_cache[mongo_id]
            
        # Par défaut, on utilise la config globale
        eff_collection = self.COLLECTION_NAME
        eff_vector = self.TEXT_VECTOR_NAME
        
        try:
            # On utilise identity_db (ou course_db selon l'injection, ici ds.db pointe sur identity_db)
            # Dans le doute, on tente de se reconnecter proprement à course_db pour les docs
            # Utilise le client déjà initialisé dans __init__ pour être plus propre
            db = self.mongo_client["course_db"]
            doc_meta = db["documents"].find_one({"_id": ObjectId(mongo_id)})
            
            if doc_meta:
                if doc_meta.get("qdrant_collection"):
                    eff_collection = doc_meta.get("qdrant_collection")
                    print(f"📎 [Navigator MLOps] Collection verrouillée : {eff_collection}")
                
                if doc_meta.get("text_model"):
                    is_doc_colbert = "colbert" in doc_meta.get("text_model").lower()
                    eff_vector = "colbert_text" if is_doc_colbert else "text"
        except Exception as e:
            print(f"⚠️ [Navigator MLOps] Erreur Version Lock : {e}")
            
        self._config_cache[mongo_id] = (eff_collection, eff_vector)
        return eff_collection, eff_vector

    def get_pdf_path(self, mongo_id):
        """Récupère le chemin local du PDF via Qdrant."""
        if mongo_id in self._pdf_path_cache:
            return self._pdf_path_cache[mongo_id]
            
        try:
            # Multi-Version Fix: On résout la collection effective
            eff_collection, _ = self._get_effective_config(mongo_id)
            
            # On cherche n'importe quel point associé à ce document
            results, _ = self.qdrant_client.scroll(
                collection_name=eff_collection,
                scroll_filter=models.Filter(
                    must=[models.FieldCondition(key="mongo_file_id", match=models.MatchValue(value=mongo_id))]
                ),
                limit=1,
                with_payload=True
            )
            if results:
                path = results[0].payload.get("source")
                if path and os.path.exists(path):
                    self._pdf_path_cache[mongo_id] = path
                    return path
        except Exception as e:
            print(f"❌ Navigator: Erreur get_pdf_path({mongo_id}): {e}")
        return None

    @lru_cache(maxsize=10) # Cache les 10 dernières pages consultées toutes sessions confondues
    def get_page_word_map(self, mongo_id, page_num, should_prefetch=True):
        """Extrait la géométrie de chaque mot de la page (JIT)."""
        pdf_path = self.get_pdf_path(mongo_id)
        if not pdf_path:
            return []
            
        try:
            doc = fitz.open(pdf_path)
            if page_num > len(doc):
                doc.close()
                return []
                
            page = doc[page_num - 1]
            page_height = page.rect.height
            # Extraction des mots (x0, y0, x1, y1, text, block_no, line_no, word_no)
            words = page.get_text("words")
            doc.close()
            
            # --- TRI SPATIAL (ORDRE DE LECTURE) ---
            # On trie par Y (Haut vers Bas) avec une tolérance de 5 points pour regrouper par ligne,
            # puis par X (Gauche vers Droite) à l'intérieur de chaque ligne.
            words_sorted = sorted(words, key=lambda w: (round(w[1] / 5) * 5, w[0]))
            
            result = []
            for i, w in enumerate(words_sorted):
                # INVERSION Y : PyMuPDF (0 en haut) -> PDF Standard (0 en bas)
                # Le frontend via viewport.convertToViewportRectangle attend le 0 en bas.
                y0_inv = page_height - w[3] # Le bas du mot en haut devient le haut du mot en bas
                y1_inv = page_height - w[1] # Le haut du mot en haut devient le bas du mot en bas
                
                result.append({
                    "text": w[4],
                    "bbox": [w[0], y0_inv, w[2], y1_inv],
                    "index": i
                })
            
            # Lancer le prefetching de la page suivante en tâche de fond (thread)
            if should_prefetch:
                threading.Thread(target=self.prefetch_next_page, args=(mongo_id, page_num)).start()
            
            return result
        except Exception as e:
            print(f"❌ Navigator: Erreur extraction mots p.{page_num}: {e}")
            return []

    def prefetch_next_page(self, mongo_id, current_page):
        """Prépare les données de la page suivante pour une transition instantanée."""
        next_page = current_page + 1
        
        # Éviter de pré-charger ce qui l'est déjà
        prefetch_key = (mongo_id, next_page)
        if self._last_prefetched_key == prefetch_key:
            return
            
        print(f"🚀 Prefetching page {next_page}...")
        self._last_prefetched_key = prefetch_key
        # On définit should_prefetch=False pour éviter la récursion infinie
        self.get_page_word_map(mongo_id, next_page, should_prefetch=False)
        # On pourrait aussi pré-calculer les embeddings MiniLM ici si besoin

    def resolve_course_id(self, prof_id, spoken_title):
        try:
            # LOG DEBUG 1
            sys.stderr.write(f"\n--- DEBUG PYTHON START ---\n")
            sys.stderr.write(f"PARAM RECU - prof_id: {prof_id}\n")
            sys.stderr.write(f"PARAM RECU - spoken_title: '{spoken_title}'\n")

            query_id = ObjectId(prof_id) if ObjectId.is_valid(prof_id) else prof_id
            user = self.db['users'].find_one({"_id": query_id})

            if not user:
                sys.stderr.write(f"ERREUR: Aucun utilisateur trouvé pour l'ID {prof_id}\n")
                return {"status": "error", "message": "Professeur non trouvé."}

            if 'cours' not in user or not user['cours']:
                sys.stderr.write(f"ERREUR: Le professeur existe mais n'a AUCUN cours dans son tableau 'cours'\n")
                return {"status": "error", "message": "Aucun cours trouvé."}

            # LOG DEBUG 2
            original_titles = [c['titre'] for c in user['cours']]
            sys.stderr.write(f"TITRES EN BDD: {original_titles}\n")

            lookup = {t.lower().strip(): t for t in original_titles}
            spoken_clean = spoken_title.lower().strip()
            sys.stderr.write(f"COMPARAISON: '{spoken_clean}' PARMI {list(lookup.keys())}\n")

            # 3. Comparaison floue
            best_match_lower, score = process.extractOne(spoken_clean, lookup.keys())
            sys.stderr.write(f"RESULTAT MATCH: '{best_match_lower}' avec score: {score}\n")

            if score >= 60:
                final_title = lookup[best_match_lower]
                selected_course = next(c for c in user['cours'] if c['titre'] == final_title)

                # LOG DEBUG 3
                sys.stderr.write(f"SUCCÈS: Cours trouvé '{final_title}'\n")

                # Vérification de la structure des documents
                if 'documents' in selected_course and len(selected_course['documents']) > 0:
                    doc_id = selected_course['documents'][0]['id']
                    return {
                        "status": "success",
                        "mongo_file_id": doc_id,
                        "course_title": final_title
                    }
                else:
                    sys.stderr.write(f"ERREUR: Le cours '{final_title}' n'a pas de documents rattachés.\n")
                    return {"status": "error", "message": "Cours sans document."}

            sys.stderr.write(f"ECHEC: Score trop bas ({score})\n")
            return {"status": "error", "message": f"Titre non reconnu ({score}%)"}

        except Exception as e:
            sys.stderr.write(f"EXCEPTION PYTHON: {str(e)}\n")
            return {"status": "error", "message": str(e)}
        finally:
            sys.stderr.write(f"--- DEBUG PYTHON END ---\n\n")

    def parse_direct_navigation(self, speech_text: str, current_page: int, total_pages: int = 9999) -> Optional[dict]:
        """
        Détecte les commandes de navigation DIRECTES (numéro de page explicite, suivant, précédent…)
        avant de faire appel à la recherche vectorielle.
        Retourne un dict {action, target_page} si détecté, sinon None.
        """
        import re

        text = speech_text.lower().strip()

        # --- Dictionnaire chiffres en lettres (français) ---
        WORD_TO_NUM = {
            "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
            "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
            "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15,
            "seize": 16, "dix-sept": 17, "dix sept": 17, "dix-huit": 18, "dix huit": 18,
            "dix-neuf": 19, "dix neuf": 19, "vingt": 20, "trente": 30, "quarante": 40,
            "cinquante": 50, "soixante": 60, "soixante-dix": 70, "soixante dix": 70,
            "quatre-vingt": 80, "quatre vingt": 80, "quatre-vingt-dix": 90, "quatre vingt dix": 90,
            "cent": 100,
        }

        def word_or_digit_to_int(s: str) -> Optional[int]:
            """Convertit un token en entier (chiffre ou mot français)."""
            s = s.strip()
            if s.isdigit():
                return int(s)
            return WORD_TO_NUM.get(s)

        # --- Patterns de navigation ---

        # 1. Page suivante
        if re.search(r"\b(page\s+suivante|suivant|prochain(?:e)?|avance[rz]?)\b", text):
            target = min(current_page + 1, total_pages)
            return {"action": "JUMP", "target_page": target, "source": "keyword:next"}

        # 2. Page précédente
        if re.search(r"\b(page\s+pr[eé]c[eé]dente|pr[eé]c[eé]dent|retour|revenir|recu[lr][ue][rs]?|recule)\b", text):
            target = max(current_page - 1, 1)
            return {"action": "JUMP", "target_page": target, "source": "keyword:prev"}

        # 3. Numéro de page explicite — chiffre arabe ou mot
        # Exemples : "page 5", "passe à la page 12", "va page cinq", "slide 3"
        pattern_page = re.compile(
            r"\b(?:page|slide|diapo(?:sitive)?|num[eé]ro)\s+(\d+|"
            + "|".join(re.escape(w) for w in sorted(WORD_TO_NUM, key=len, reverse=True))
            + r")\b"
        )
        m = pattern_page.search(text)
        if m:
            page_num = word_or_digit_to_int(m.group(1))
            if page_num and 1 <= page_num <= total_pages:
                action = "JUMP" if abs(page_num - current_page) > 1 else "SCROLL"
                return {"action": action, "target_page": page_num, "source": "keyword:direct"}

        # 4. "va au début" / "première page"
        if re.search(r"\b(d[eé]but|premi[eè]re?\s+page|page\s+1|page\s+un(?:e)?)\b", text):
            return {"action": "JUMP", "target_page": 1, "source": "keyword:start"}

        # 5. "va à la fin" / "dernière page"
        if re.search(r"\b(fin|derni[eè]re?\s+page)\b", text):
            return {"action": "JUMP", "target_page": total_pages, "source": "keyword:end"}

        return None  # Aucune commande directe détectée → laisser la recherche sémantique

    def get_navigation_decision(self, mongo_id, current_page, speech_text):
        # ─────────────────────────────────────────────────────
        # ÉTAPE 1 : Commandes directes (numéro de page, suivant…)
        # Priorité absolue sur la recherche sémantique
        # ─────────────────────────────────────────────────────
        direct = self.parse_direct_navigation(speech_text, current_page)
        if direct:
            print(f"🎯 Navigation directe détectée : {direct}")
            return direct

        # ─────────────────────────────────────────────────────
        # ÉTAPE 2 : Recherche sémantique ColBERT dans Qdrant
        # ─────────────────────────────────────────────────────
        query_embeddings = list(self.text_model.query_embed([speech_text]))[0]

        eff_collection, eff_vector = self._get_effective_config(mongo_id)

        search_results = self.qdrant_client.query_points(
            collection_name=eff_collection,
            query=query_embeddings.tolist(),
            using=eff_vector,
            query_filter=models.Filter(
                must=[models.FieldCondition(key="mongo_file_id", match=models.MatchValue(value=mongo_id))]
            ),
            limit=5
        ).points

        if not search_results:
            return {"action": "STAY", "page": current_page}

        top_hit = search_results[0]
        detected_page = top_hit.payload['page_number']
        score = top_hit.score

        print(f"🔍 Recherche sémantique : meilleur résultat page {detected_page} (score={score:.2f})")

        # Seuil ColBERT MaxSim (ajusté empiriquement, plus strict pour éviter transitions prématurées)
        if score > 16.0:
            action = "JUMP" if abs(detected_page - current_page) > (2 if score < 18.0 else 1) else "SCROLL"
            
            # Si le score est bon mais pas incroyable, on préfère RESTER sur la page actuelle
            # si l'IA a trouvé quelque chose sur la page actuelle avec un score correct (> 12)
            if detected_page != current_page and score < 17.0:
                page_match = next((p for p in search_results if p.payload['page_number'] == current_page), None)
                if page_match and page_match.score > 12.0:
                    print(f"📍 Maintien sur page {current_page} (score local {page_match.score:.2f} > 12)")
                    return {
                        "action": "STAY", 
                        "page": current_page, 
                        "bbox": page_match.payload.get('bbox'),
                        "source": "tracking:sticky"
                    }

            return {
                "action": action, 
                "target_page": detected_page, 
                "score": score, 
                "bbox": top_hit.payload.get('bbox')
            }

        return {"action": "STAY", "page": current_page}


    def get_page_text(self, mongo_id, page_number):
        """
        Récupère tout le texte d'une page spécifique à partir des blocs textuels indexés.
        """
        try:
            eff_collection, eff_vector = self._get_effective_config(mongo_id)
            results = self.qdrant_client.query_points(
                collection_name=eff_collection,
                query=[0.0]*128,
                using=eff_vector,
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(key="mongo_file_id", match=models.MatchValue(value=mongo_id)),
                        models.FieldCondition(key="page_number", match=models.MatchValue(value=page_number)),
                        models.FieldCondition(key="type", match=models.MatchValue(value="text_block"))
                    ]
                ),
                limit=50
            ).points
            
            if not results:
                return ""
            
            text_blocks = [r.payload.get('content', '') for r in results]
            return "\n".join(text_blocks)
            
        except Exception as e:
            print(f"⚠️ Erreur get_page_text : {e}")
            return ""


    # Dans la classe SmartCourseNavigator de services/smart_course_navigator.py

    def get_page_end_trigger(self, mongo_id: str, page_num: int) -> str:
        """Récupère dynamiquement les 20 derniers mots de la page via le PDF local (JIT)."""
        try:
            # On utilise get_page_word_map qui est déjà JIT et robuste
            word_map = self.get_page_word_map(mongo_id, page_num, should_prefetch=False)
            if not word_map: return ""

            # On prend les 25 derniers mots pour avoir une marge, et on en garde 20
            last_words = [wm['text'] for wm in word_map[-25:]]
            return " ".join(last_words)
        except Exception as e:
            print(f"❌ Erreur Navigator (EndTrigger JIT): {e}")
            return ""

    def get_page_word_set(self, mongo_id: str, page_num: int) -> set:
        """Extrait l'ensemble des mots uniques significatifs d'une page (sans stop-words)."""
        try:
            words = self.get_page_word_map(mongo_id, page_num, should_prefetch=False)
            if not words: return set()
            
            stop_words = {
                "le", "la", "les", "un", "une", "des", "du", "de", "et", "ou", "mais", "où", "on", "se", "ce", "en", "au", "aux", 
                "est", "sont", "pour", "dans", "avec", "par", "dans", "plus", "moins", "donc", "car", "qui", "que", "quoi", "dont", 
                "tout", "tous", "cette", "cet", "ces", "mon", "ton", "son", "notre", "votre", "leur", "ma", "ta", "sa", "mes", "tes", "ses"
            }
            
            clean_words = set()
            for w in words:
                clean = "".join(c for c in w['text'].lower() if c.isalnum())
                if clean and clean not in stop_words and len(clean) > 2:
                    clean_words.add(clean)
            return clean_words
        except Exception as e:
            print(f"❌ Erreur Navigator (WordSet JIT): {e}")
            return set()

    def get_page_max_index(self, mongo_id: str, page_num: int) -> int:
        """Récupère l'index maximum (nombre de mots) sur cette page via le PDF local."""
        try:
            # On utilise le même mécanisme que get_page_word_map pour être cohérent avec le DTW
            words = self.get_page_word_map(mongo_id, page_num, should_prefetch=False)
            if not words: return 0
            # L'index est la position dans la liste
            return len(words)
        except Exception as e:
            print(f"❌ Erreur Navigator (MaxIndex JIT): {e}")
            return 0


    def get_page_semantic_fingerprint(self, mongo_id: str, page_num: int):
        """Calcule le vecteur moyen de la page cible pour l'orchestrateur."""
        try:
            eff_collection, eff_vector = self._get_effective_config(mongo_id)
            results, _ = self.qdrant_client.scroll(
                collection_name=eff_collection,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(key="mongo_file_id", match=models.MatchValue(value=mongo_id)),
                        models.FieldCondition(key="page_number", match=models.MatchValue(value=page_num))
                    ]
                ),
                with_vectors=True,
                limit=50
            )
            # On extrait les vecteurs et on calcule la moyenne
            vectors = []
            for p in results:
                if p.vector:
                    if isinstance(p.vector, dict):
                        # Gérer les vecteurs nommés
                        if 'colbert' in p.vector:
                            vec = np.array(p.vector['colbert'])
                            if vec.ndim == 2: vec = np.mean(vec, axis=0)
                            vectors.append(vec)
                        elif eff_vector in p.vector:
                            vec = np.array(p.vector[eff_vector])
                            if vec.ndim == 2: vec = np.mean(vec, axis=0)
                            vectors.append(vec)
                        elif 'text-dense' in p.vector:
                            vectors.append(p.vector['text-dense'])
                    else:
                        vectors.append(p.vector)
            
            if not vectors: return None
            return np.mean(vectors, axis=0)
        except Exception as e:
            print(f"❌ Erreur Navigator (Sémantique): {e}")
            return None
if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(1)

    mode = sys.argv[1]
    try:
        payload = json.loads(sys.argv[2])
        navigator = SmartCourseNavigator()

        if mode == "INIT":
            result = navigator.resolve_course_id(payload.get("prof_id"), payload.get("spoken_title"))
        elif mode == "NAVIGATE":
            result = navigator.get_navigation_decision(payload.get("mongo_file_id"), payload.get("current_page"),
                                                       payload.get("speech_text"))

        sys.stdout.write(json.dumps(result) + "\n")
        sys.stdout.flush()
    except Exception as e:
        print(json.dumps({"error": str(e), "action": "STAY"}))