# ==============================================================================
# PROPRIÉTÉ DE AI ASSISTANT - (c) 2024-2026 Mourad Daghfous
# Système d'Interaction Vocale Intelligent pour l'Éducation
# ------------------------------------------------------------------------------
# Ce fichier est confidentiel et protégé par les lois sur la propriété 
# intellectuelle. Toute diffusion non autorisée est passible de poursuites.
# ==============================================================================
import numpy as np
import re
import asyncio
from qdrant_client import models
from fuzzywuzzy import fuzz, process
from nltk.stem.snowball import SnowballStemmer

class HighlightLogic:
    def __init__(self, navigator_service):
        """
        :param navigator_service: Instance de SmartCourseNavigator pour accéder aux embeddings et Qdrant.
        """
        self.nav = navigator_service
        self.stemmer = SnowballStemmer("french")
        
        # Cache pour éviter de recalculer les racines de la page à chaque bribe
        # Structure: {(mongo_id, page): {"stems": [], "bboxes": [], "raw": []}}
        self._page_cache = {}
        # Mots de liaison à ignorer pour le déclenchement du surlignage (Recherche)
        self.stop_words = {
            'le', 'la', 'les', 'des', 'de', 'du', 'un', 'une', 'au', 'aux', 
            'ce', 'ces', 'dans', 'en', 'par', 'pour', 'sur', 'avec', 'et', 
            'ou', 'ne', 'pas', 'qui', 'que', 'quoi', 'dont', 'où',
            'mes', 'tes', 'ses', 'nos', 'vos', 'leurs', 'mais', 'donc', 'car', 'ni', 'si',
            'tout', 'tous', 'toute', 'toutes', 'chaque', 'aucun', 'aucune', 'autre', 'autres', 'comme'
        }

    def _clean_word(self, w: str) -> str:
        """Nettoyage unifié d'un mot : gère les apostrophes l', d', etc."""
        w = w.lower().strip()
        # Supprimer les préfixes élidés (l', d', s', n', j', qu')
        w = re.sub(r"^[ldsnj]('|’)", "", w)
        w = re.sub(r"^qu('|’)", "", w)
        # On garde les caractères alphanumériques (incluant les accents car SnowballStemmer les gère)
        return "".join(c for c in w if c.isalnum())

    def _stem_word(self, w: str) -> str:
        """Radicalisation d'un mot."""
        return self.stemmer.stem(self._clean_word(w))

    async def _get_page_stems(self, mongo_id, current_page):
        """Récupère et met en cache les racines de tous les mots de la page."""
        cache_key = (mongo_id, current_page)
        if cache_key in self._page_cache:
            return self._page_cache[cache_key]
            
        window = await asyncio.to_thread(self.nav.get_page_word_map, mongo_id, current_page)
        if not window:
            return None
            
        data = {
            "stems": [self._stem_word(w["text"]) for w in window],
            "bboxes": [w["bbox"] for w in window],
            "raw": [w["text"] for w in window]
        }
        self._page_cache[cache_key] = data
        return data

    async def get_highlight(self, mongo_id: str, current_page: int, speech_text: str, last_word_index: int):
        """
        Point d'entrée unique pour le surlignage JIT.
        L'ancrage est désormais géré en interne pour l'indépendance du service.
        """
        if last_word_index is None: last_word_index = 0

        # 1. Calcul de l'ancre (phare) en interne via bigrammes
        anchor_index = await self._find_anchor(mongo_id, current_page, speech_text, last_word_index)

        # 2. Alignement via Pointer Mode (Stratégie robuste)
        return await self._align_pointer_mode(mongo_id, current_page, speech_text, last_word_index, anchor_index)

    async def _find_anchor(self, mongo_id, current_page, speech_clean, last_word_index):
        """
        Identifie une position stable (ancre) dans le texte via des bigrammes.
        Fenêtre restreinte pour un suivi serré.
        """
        page_data = await self._get_page_stems(mongo_id, current_page)
        if not page_data: return last_word_index
        
        stems = page_data["stems"]
        
        # Nettoyage du discours
        speech_raw = [self._clean_word(w) for w in re.findall(r'\w+', speech_clean)]
        speech_stems = [self.stemmer.stem(w) for w in speech_raw if len(w) > 2]
        if len(speech_stems) < 2: return last_word_index

        # Bigrammes récents du discours (les 3 derniers couples)
        target_bigrams = []
        for i in range(len(speech_stems) - 1):
            target_bigrams.append((speech_stems[i], speech_stems[i+1]))
        target_bigrams = target_bigrams[-3:]

        # FENÊTRE DE RECHERCHE : 25 mots pour l'ancre
        search_start = last_word_index
        search_end = min(len(stems), search_start + 25)
        
        for i in range(search_start, search_end - 1):
            pdf_bigram = (stems[i], stems[i+1])
            if pdf_bigram in target_bigrams:
                print(f"⚓ [Highlight-Anchor] Ancre trouvée : Index {i+1}")
                return i + 1
                
        return last_word_index

    async def _align_pointer_mode(self, mongo_id, current_page, speech_text, last_word_index, anchor_index=None):
        """
        Avancement strict d'un pointeur sur une liste finie (le PDF).
        Très robuste contre les sauts erronés.
        """
        page_data = await self._get_page_stems(mongo_id, current_page)
        if not page_data:
            return None
            
        stems = page_data["stems"]
        bboxes = page_data["bboxes"]
        raw_words = page_data["raw"]
        
        # On extrait les 3 derniers mots du discours
        speech_words = speech_text.split()
        if not speech_words: return None
        
        # On crée une liste de candidats filtrés (Plus récents d'abord)
        search_candidates = []
        for i in range(1, min(4, len(speech_words)+1)):
            word = speech_words[-i]
            clean = self._clean_word(word)
            # Filtre Stopwords OU mot trop court (< 3 chars, sauf s'il n'y a que ça)
            if clean in self.stop_words or (len(clean) < 3 and len(speech_words) > 1):
                continue
            search_candidates.append(self._stem_word(word))

        if not search_candidates:
            print("⏳ [Highlight] Attente d'un mot porteur (Uniquement Stopwords détectés)")
            return None
            
        # FENÊTRE DE RECHERCHE : 
        # Priorité à l'ANCRE interne calculée
        if anchor_index is not None and anchor_index > last_word_index:
            search_start = max(0, anchor_index - 3)
            search_end = min(len(stems), anchor_index + 15)
            print(f"🔦 [Highlight-Anchor] Focus sur ligne Index {anchor_index} (Window: {search_start}-{search_end})")
        else:
            search_start = last_word_index
            search_end = min(len(stems), search_start + 60) # Fenêtre large pour retrouver son chemin
            print(f"🔦 [Highlight-Free] Recherche libre autour de Index {search_start} (Window: 60)")
        
        print(f"📍 [Highlight] Recherche entre Index {search_start} et {search_end} (Cibles filtrées: {search_candidates})")
        
        best_match_idx = -1
        
        # --- RECHERCHE PRIORITAIRE SUR LE MOT LE PLUS RÉCENT (Front de lecture) ---
        # On traite le candidat 0 (le dernier mot prononcé) avec une priorité totale (Strict puis Flou)
        cand_idx = 0
        cand_stem = search_candidates[0]
        orig_word = speech_words[-1]
        clean_cand = self._clean_word(orig_word)
        
        # 1.1 Strict pour le mot le plus récent
        for i in range(search_start, search_end):
            if stems[i] == cand_stem:
                best_match_idx = i
                print(f"✅ [Highlight] Match STRICT (Last Word) trouvé : '{raw_words[i]}' (Index {i})")
                break
        
        # 1.2 Flou pour le mot le plus récent (si pas de match strict)
        if best_match_idx == -1 and len(clean_cand) > 5:
            for i in range(search_start, search_end):
                clean_pdf = self._clean_word(raw_words[i])
                if len(clean_pdf) > 5:
                    ratio = fuzz.ratio(clean_pdf, clean_cand)
                    if ratio >= 65:
                        best_match_idx = i
                        print(f"✨ [Highlight-FUZZY] Match flou ({ratio}%) : '{raw_words[i]}' pour '{clean_cand}' (Index {i})")
                        break

        # --- RECHERCHE DE REPLI (Mots précédents) ---
        # Si le tout dernier mot n'a rien donné du tout, on regarde les mots juste avant
        if best_match_idx == -1 and len(search_candidates) > 1:
            for cand_idx in range(1, len(search_candidates)):
                cand_stem = search_candidates[cand_idx]
                for i in range(search_start, search_end):
                    if stems[i] == cand_stem:
                        best_match_idx = i
                        print(f"✅ [Highlight] Match STRICT (Fallback) trouvé : '{raw_words[i]}' (Index {i})")
                        break
                if best_match_idx != -1: break
        
        if best_match_idx != -1:
            # --- GESTION DU SURLIGNAGE DE GROUPE ---
            start_bbox = bboxes[last_word_index]
            end_bbox = bboxes[best_match_idx]
            
            # Vérification si même ligne (ordonnée Y proche)
            if abs(start_bbox[1] - end_bbox[1]) < 7:
                # BBox combinée [xmin, ymin, xmax, ymax]
                final_bbox = [
                    min(start_bbox[0], end_bbox[0]),
                    min(start_bbox[1], end_bbox[1]),
                    max(start_bbox[2], end_bbox[2]),
                    max(start_bbox[3], end_bbox[3])
                ]
            else:
                final_bbox = end_bbox
    
            return {
                "page": current_page,
                "bbox": final_bbox,
                "text": " ".join(raw_words[last_word_index : best_match_idx + 1]),
                "index": best_match_idx,
                "source": "pointer_seq_nlp"
            }
            
        return None
