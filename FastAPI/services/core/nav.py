import re
import asyncio
import numpy as np
import fitz
from fuzzywuzzy import fuzz
from typing import Dict, Any, Optional, Set
from nltk.stem.snowball import SnowballStemmer

class NavigationLogic:
    def __init__(self, navigator_service, redis_client=None):
        self.nav = navigator_service
        self.redis = redis_client
        self.stemmer = SnowballStemmer("french")
        self._local_state = {}

    def _clean_word(self, w: str) -> str:
        """Nettoyage unifié d'un mot."""
        return "".join(c for c in w.lower() if c.isalnum())

    async def calculate_coverage(self, mongo_id: str, current_page: int, speech_clean: str, session_id: str) -> float:
        """Calcule le pourcentage de mots lus sur la page actuelle via normalisation linguistique."""
        all_page_words = await asyncio.to_thread(self.nav.get_page_word_set, mongo_id, current_page)
        if not all_page_words:
            return 0.0

        # On pré-calcule les racines (stems) de la page pour une comparaison robuste
        # Harmonisation avec navigator.py/surlignage.py
        stop_words = {
            "le", "la", "les", "un", "une", "des", "du", "de", "et", "ou", "mais", "où", "on", "se", "ce", "en", "au", "aux", 
            "est", "sont", "pour", "dans", "avec", "par", "dans", "plus", "moins", "donc", "car", "qui", "que", "quoi", "dont", 
            "tout", "tous", "cette", "cet", "ces", "mon", "ton", "son", "notre", "votre", "leur", "ma", "ta", "sa", "mes", "tes", "ses"
        }
        
        # Référence paginée (racines uniques)
        ref_stems = {self.stemmer.stem(w.lower()) for w in all_page_words if w.lower() not in stop_words and len(w) > 2}
        total_stems = len(ref_stems)
        if total_stems == 0: return 1.0 # Page vide = couverture totale par défaut

        # Extraction et normalisation des mots prononcés
        speech_raw = re.findall(r'\w+', speech_clean)
        seen_stems = set()
        
        for w in speech_raw:
            clean = self._clean_word(w)
            if clean and clean not in stop_words and len(clean) > 2:
                stem = self.stemmer.stem(clean)
                if stem in ref_stems:
                    seen_stems.add(stem)
                else:
                    # Sécurité Fuzzy : Capture les déformations phonétiques (ex: Docker -> Docteur)
                    # On cherche une ressemblance de 85% entre la racine prononcée et les racines de la page
                    for ref in ref_stems:
                        if fuzz.ratio(stem, ref) >= 85:
                            seen_stems.add(ref)
                            break
        
        # --- SYNCHRONISATION ÉTAT (Redis ou RAM) ---
        redis_set_key = f"seen_stems:{session_id or 'default'}:{mongo_id}:{current_page}"
        if self.redis:
            if seen_stems:
                await self.redis.sadd(redis_set_key, *seen_stems)
                await self.redis.expire(redis_set_key, 3600)
            seen_count = await self.redis.scard(redis_set_key)
        else:
            ram_key = f"seen_stems:{session_id or 'default'}:{mongo_id}:{current_page}"
            if ram_key not in self._local_state: self._local_state[ram_key] = set()
            self._local_state[ram_key].update(seen_stems)
            seen_count = len(self._local_state[ram_key])
            
        coverage = min(1.0, seen_count / total_stems)
        if seen_stems:
            print(f"📊 [Coverage-Stemmed] p.{current_page}: {seen_count}/{total_stems} racines (Couverture: {coverage:.2f})")
        return coverage

    async def check_last_words_read(self, mongo_id: str, current_page: int, speech_clean: str) -> bool:
        """Vérifie si les 5 derniers mots (significatifs) de la page ont été lus dans le texte récent."""
        try:
            # Passe False pour should_prefetch car get_page_word_map de navigator prend ce paramètre
            word_map = await asyncio.to_thread(self.nav.get_page_word_map, mongo_id, current_page, False)
            if not word_map: return False
            
            # On récupère les 10 derniers mots significatifs (> 2 lettres) de la page
            stop_words = {"les", "des", "une", "dans", "pour", "avec", "par", "très"}
            target_words = []
            for wm in reversed(word_map):
                w = wm['text'].lower()
                clean = "".join(c for c in w if c.isalnum())
                if len(clean) > 2 and clean not in stop_words:
                    target_words.append(clean)
                if len(target_words) >= 10: break
            
            if not target_words: return True 
            
            # Inverser pour avoir l'ordre chronologique du texte (du début vers la fin)
            target_words.reverse()
            
            # On extrait les 20 derniers mots prononcés (sous forme de liste pour préserver l'ordre)
            speech_words = [self._clean_word(w) for w in re.findall(r'\w+', speech_clean)]
            speech_words = [w for w in speech_words if len(w) > 2 and w not in stop_words]
            
            recent_spoken = speech_words[-20:]
            
            # Application du Stemmer pour effacer les différences de conjugaison/pluriels
            stemmed_targets = [self.stemmer.stem(w) for w in target_words]
            stemmed_spoken = [self.stemmer.stem(w) for w in recent_spoken]
            
            # Algorithme LCS (Longest Common Subsequence) pour vérifier l'apparition DANS L'ORDRE
            m = len(stemmed_targets)
            n = len(stemmed_spoken)
            dp = [[0] * (n + 1) for _ in range(m + 1)]
            
            for i in range(1, m + 1):
                for j in range(1, n + 1):
                    # Comparaison parfaite sur les "racines" des mots (exécutions == exécutés -> execut)
                    if stemmed_targets[i-1] == stemmed_spoken[j-1]:
                        dp[i][j] = dp[i-1][j-1] + 1
                    else:
                        dp[i][j] = max(dp[i-1][j], dp[i][j-1])
                        
            ordered_matches = dp[m][n]
            
            # Backtracking pour s'assurer que le match est bien collé à la FIN de la phrase
            last_matched_recent_idx = -1
            i, j = m, n
            while i > 0 and j > 0:
                if stemmed_targets[i-1] == stemmed_spoken[j-1]:
                    if last_matched_recent_idx == -1:
                        last_matched_recent_idx = j - 1
                    i -= 1
                    j -= 1
                elif dp[i-1][j] > dp[i][j-1]:
                    i -= 1
                else:
                    j -= 1
                    
            is_near_end = True
            if last_matched_recent_idx != -1:
                gap_to_end = (n - 1) - last_matched_recent_idx
                # Réduction critique du gap : il ne peut y avoir plus de 2 mots parasites après les mots de fin
                if gap_to_end > 2:
                    is_near_end = False
            
            # Au moins 6 mots sur les 10 doivent matcher en séquence
            is_ok = (ordered_matches >= 6) and is_near_end 
            print(f"🏁 [Barrier] Fin de page p.{current_page}: {ordered_matches}/10 mots lus DANS L'ORDRE. Près de la fin: {is_near_end}. OK: {is_ok}")
            return is_ok
        except Exception as e:
            print(f"⚠️ Error checking last words: {e}")
            return False

    async def check_lexical_jump(self, mongo_id: str, current_page: int, speech_clean: str) -> Optional[int]:
        """Vérifie si les mots prononcés correspondent à la fin de la page."""
        trigger_text = await asyncio.to_thread(self.nav.get_page_end_trigger, mongo_id, current_page)
        if not trigger_text:
            return None
            
        # Protection contre les micro-fragments (ex: "le test") 
        # qui faussent token_set_ratio (intersection trop facile)
        speech_words = speech_clean.split()
        if len(speech_words) < 5:
            return None
            
        # On ne compare que la fin du discours récent (jusqu'à 30 mots)
        recent_speech = " ".join(speech_words[-30:])
            
        score = fuzz.token_set_ratio(recent_speech, trigger_text.lower())
        print(f"🔎 [Lexical] p.{current_page} Trigger: '{trigger_text[:30]}...' | Score: {score}")
        if score > 75: # Seuil légèrement assoupli car le fallback LCS est maintenant très strict
            return current_page + 1
        return None
