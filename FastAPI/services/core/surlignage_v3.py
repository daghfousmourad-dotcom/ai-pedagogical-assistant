# ==============================================================================
# PROPRIÉTÉ DE AI ASSISTANT - (c) 2024-2026 Mourad Daghfous
# Système d'Interaction Vocale Intelligent pour l'Éducation
# ------------------------------------------------------------------------------
# highlight_logic.py — Version de Production (V6 Finale - Optimisée et Déterministe)
# ==============================================================================

import asyncio
import re
import torch
import numpy as np
from typing import Optional, List, Tuple
from collections import deque, OrderedDict

# ──────────────────────────────────────────────────────────────────────────────
# DÉPENDANCES REQUISES
# ──────────────────────────────────────────────────────────────────────────────

try:
    from ctc_forced_aligner import (
        load_alignment_model,
        generate_emissions,
        preprocess_text,
        get_alignments,
        get_spans,
        postprocess_results,
    )
    CTC_AVAILABLE = True
except ImportError:
    CTC_AVAILABLE = False
    print("⚠️  ctc-forced-aligner non installé. Mode NLP de repli activé.")

try:
    from unidecode import unidecode
    UNIDECODE_AVAILABLE = True
except ImportError:
    UNIDECODE_AVAILABLE = False


# ──────────────────────────────────────────────────────────────────────────────
# Structures de données
# ──────────────────────────────────────────────────────────────────────────────

class AlignedWord:
    def __init__(self, text: str, bbox: list, page: int, pdf_index: int, score: float = 1.0):
        self.text = text
        self.bbox = bbox
        self.page = page
        self.pdf_index = pdf_index
        self.score = score


# ──────────────────────────────────────────────────────────────────────────────
# Utilitaires : Normalisation et Cache
# ──────────────────────────────────────────────────────────────────────────────

class LRUPageCache:
    def __init__(self, max_capacity: int = 15):
        self.cache: OrderedDict = OrderedDict()
        self.max_capacity = max_capacity

    def get(self, key: Tuple[str, int]) -> Optional[dict]:
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)
        return self.cache[key]

    def set(self, key: Tuple[str, int], value: dict):
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.max_capacity:
            self.cache.popitem(last=False)


class TextNormalizer:
    @staticmethod
    def clean(text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r"[''`]", "'", text)
        text = re.sub(r"^[ldsnj]'", "", text)
        text = re.sub(r"^qu'", "", text)
        text = re.sub(r"[^\w\u00C0-\u017E]", "", text)
        return text

    @staticmethod
    def romanize(text: str) -> str:
        if UNIDECODE_AVAILABLE:
            return unidecode(text.lower())
        return text.lower()

    @staticmethod
    def normalize_pdf_words(word_map: list) -> list:
        for w in word_map:
            w["norm"] = TextNormalizer.clean(w["text"])
            w["roman"] = TextNormalizer.romanize(w["norm"])
        return word_map


# ──────────────────────────────────────────────────────────────────────────────
# Moteurs et Logique
# ──────────────────────────────────────────────────────────────────────────────

class AudioBufferFixed:
    SAMPLE_RATE = 16_000
    WINDOW_S = 3.0
    OVERLAP_S = 0.5
    STRIDE_S = 0.5

    def __init__(self):
        self.window_samples = int(self.WINDOW_S * self.SAMPLE_RATE)
        self.stride_samples = int(self.STRIDE_S * self.SAMPLE_RATE)
        self.overlap_samples = int(self.OVERLAP_S * self.SAMPLE_RATE)
        self._storage = np.empty(0, dtype=np.float32)
        self._unread_samples = 0

    def add(self, audio_chunk: np.ndarray):
        self._storage = np.concatenate((self._storage, audio_chunk.astype(np.float32)))
        self._unread_samples += len(audio_chunk)

    def should_trigger(self) -> bool:
        return self._unread_samples >= self.stride_samples

    def get_window(self) -> Optional[np.ndarray]:
        if len(self._storage) < self.window_samples:
            return None
        window = self._storage[:self.window_samples]
        advance = self.window_samples - self.overlap_samples
        self._storage = self._storage[advance:]
        self._unread_samples = max(0, self._unread_samples - advance)
        return window

    def reset(self):
        self._storage = np.empty(0, dtype=np.float32)
        self._unread_samples = 0


class CursorTracker:
    LOOKBACK = 5
    MAX_JUMP = 40
    MIN_CONFIDENCE = 0.45

    def __init__(self):
        self.position = 0
        self.page = 0
        self._history = deque(maxlen=20)

    def validate_and_advance(self, aligned_words: list[AlignedWord]) -> Optional[AlignedWord]:
        if not aligned_words:
            return None

        candidates = [w for w in aligned_words if w.score >= self.MIN_CONFIDENCE]
        if not candidates:
            candidates = sorted(aligned_words, key=lambda w: w.score, reverse=True)[:1]

        best = max(candidates, key=lambda w: w.pdf_index)

        if best.pdf_index < self.position - self.LOOKBACK or best.pdf_index > self.position + self.MAX_JUMP:
            return None

        if best.pdf_index >= self.position:
            self.position = best.pdf_index
            self.page = best.page
            self._history.append(best.pdf_index)

        return best

    def reset(self):
        self.position = 0
        self.page = 0
        self._history.clear()


class AlignmentEngine:
    LANGUAGE = "fra"

    def __init__(self, device: str = None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._model = None
        self._tokenizer = None
        self._model_name = "facebook/mms-300m"
        self._loaded = False
        self._is_loading = False
        self._load_failed = False
        self._should_flush = False

    def load(self):
        if self._loaded or not CTC_AVAILABLE or self._load_failed:
            return

        self._is_loading = True
        try:
            print(f"🔄 [AlignmentEngine] Chargement de {self._model_name}...")
            self._model, self._tokenizer = load_alignment_model(self._model_name, device=self.device)
            self._loaded = True
            self._should_flush = True  # Déclenche le vidage du buffer audio
            print(f"✅ [AlignmentEngine] Modèle chargé sur {self.device}.")
        except Exception as e:
            print(f"❌ [AlignmentEngine] Échec du chargement : {e}. NLP fallback permanent.")
            self._load_failed = True
        finally:
            self._is_loading = False

    def align_chunk(self, audio_chunk: np.ndarray, pdf_words: list, start_offset: int = 0) -> list[AlignedWord]:
        if not CTC_AVAILABLE or not self._loaded:
            return []

        window_texts = [w["roman"] for w in pdf_words]
        transcript = " ".join(window_texts)
        waveform = torch.from_numpy(audio_chunk).unsqueeze(0).to(self.device)

        try:
            emissions, stride = generate_emissions(self._model, waveform, batch_size=1)
            tokens_starred, text_starred = preprocess_text(
                transcript, romanize=False, language=self.LANGUAGE, tokenizer=self._tokenizer, split_size="word"
            )
            segments, scores, blank_token = get_alignments(emissions, tokens_starred, self._tokenizer)
            spans = get_spans(tokens_starred, segments, blank_token)
            results = postprocess_results(text_starred, spans, stride, scores)
        except Exception as e:
            print(f"⚠️ [AlignmentEngine] Erreur : {e}")
            return []

        aligned = []
        for i, res in enumerate(results):
            pdf_idx = start_offset + i
            if pdf_idx >= len(pdf_words) + start_offset:
                break
            pdf_word = pdf_words[i] if i < len(pdf_words) else None
            if pdf_word is None:
                continue
            aligned.append(AlignedWord(
                text=pdf_word["text"],
                bbox=pdf_word["bbox"],
                page=pdf_word.get("page", 0),
                pdf_index=pdf_idx,
                score=float(res.get("score", 1.0)),
            ))
        return aligned


class NLPFallback:
    from nltk.stem.snowball import SnowballStemmer as _Stemmer
    from fuzzywuzzy import fuzz as _fuzz

    STOP_WORDS = {'le', 'la', 'les', 'des', 'de', 'du', 'un', 'une', 'au', 'aux', 'ce', 'ces', 'dans', 'en', 'par',
                  'pour', 'sur', 'avec', 'et', 'ou', 'ne', 'pas', 'qui', 'que', 'quoi', 'dont', 'où'}
    
    # Correction : Fenêtre de recherche portée à 60 mots par défaut pour une robustesse optimale (identique v1)
    BASE_WINDOW = 60
    
    def __init__(self):
        self._stemmer = self._Stemmer("french")
        self._stagnation_counter = 0
        self._STAGNATION_LIMIT = 8

    def _clean(self, w: str) -> str:
        return TextNormalizer.clean(w)

    def _stem(self, w: str) -> str:
        return self._stemmer.stem(self._clean(w))

    def _get_candidates(self, speech_words: list) -> list:
        candidates = []
        for i in range(1, min(6, len(speech_words) + 1)):
            w = speech_words[-i]
            c = self._clean(w)
            if c in self.STOP_WORDS or (len(c) < 3 and len(speech_words) > 1):
                continue
            candidates.append((self._stem(w), c, w))
        return candidates

    def _find_trigram_anchor(self, speech_stems: list, pdf_stems: list, search_start: int, search_end: int) -> int:
        if len(speech_stems) < 3:
            return search_start
            
        # CORRECTION : Conservation déterministe de l'ordre temporel des trigrammes (les plus récents en premier)
        target_trigrams_list = []
        for i in range(len(speech_stems) - 2):
            target_trigrams_list.append((speech_stems[i], speech_stems[i + 1], speech_stems[i + 2]))
            
        seen = set()
        unique_trigrams = []
        for tg in reversed(target_trigrams_list):
            if tg not in seen:
                seen.add(tg)
                unique_trigrams.append(tg)
                if len(unique_trigrams) == 4:
                    break
        target_trigrams = set(unique_trigrams)

        for i in range(search_start, min(search_end, len(pdf_stems) - 2)):
            tg = (pdf_stems[i], pdf_stems[i + 1], pdf_stems[i + 2])
            if tg in target_trigrams:
                return i + 2
        return search_start

    def find_highlight(self, speech_text: str, pdf_stems: list, pdf_bboxes: list, pdf_raw: list, last_index: int) -> Optional[dict]:
        speech_words = speech_text.split()
        if not speech_words:
            return None

        candidates = self._get_candidates(speech_words)
        if not candidates:
            return None

        speech_stems_list = [self._stem(w) for w in re.findall(r'\w+', speech_text) if len(self._clean(w)) > 2]
        
        # Fenêtre adaptative
        window_size = self.BASE_WINDOW * 3 if self._stagnation_counter >= self._STAGNATION_LIMIT else self.BASE_WINDOW
        if self._stagnation_counter >= self._STAGNATION_LIMIT:
            self._stagnation_counter = 0

        search_start = last_index
        search_end = min(len(pdf_stems), search_start + window_size)

        anchor = self._find_trigram_anchor(speech_stems_list, pdf_stems, search_start, search_end)
        if anchor > search_start:
            search_start = max(0, anchor - 5)
            search_end = min(len(pdf_stems), anchor + 20)

        best_idx = -1
        cand_stem, cand_clean, _ = candidates[0]

        # Passe 1 : match strict sur le mot le plus récents
        for i in range(search_start, search_end):
            if pdf_stems[i] == cand_stem:
                best_idx = i
                break

        # Passe 2 : match flou sur le mot le plus récent (CORRECTION : seuil recalibré à 65% pour robustesse ASR)
        if best_idx == -1 and len(cand_clean) > 5:
            best_ratio = 0
            for i in range(search_start, search_end):
                pdf_clean = self._clean(pdf_raw[i])
                if len(pdf_clean) > 5:
                    r = self._fuzz.ratio(pdf_clean, cand_clean)
                    if r >= 65 and r > best_ratio:
                        best_ratio = r
                        best_idx = i

        # Passe 3 : repli sur les mots précédents
        if best_idx == -1:
            for cand_stem, _, _ in candidates[1:]:
                for i in range(search_start, search_end):
                    if pdf_stems[i] == cand_stem:
                        best_idx = i
                        break
                if best_idx != -1:
                    break

        if best_idx == -1:
            self._stagnation_counter += 1
            return None

        self._stagnation_counter = 0

        # Bbox de repli (pour compatibilité)
        start_bbox = pdf_bboxes[last_index] if last_index < len(pdf_bboxes) else pdf_bboxes[best_idx]
        end_bbox = pdf_bboxes[best_idx]

        if abs(start_bbox[1] - end_bbox[1]) < 7:
            final_bbox = [
                min(start_bbox[0], end_bbox[0]),
                min(start_bbox[1], end_bbox[1]),
                max(start_bbox[2], end_bbox[2]),
                max(start_bbox[3], end_bbox[3]),
            ]
        else:
            final_bbox = end_bbox

        return {
            "bbox": final_bbox,
            "index": best_idx,
            "text": " ".join(pdf_raw[last_index: best_idx + 1]),
            "source": "nlp_fallback"
        }


# ──────────────────────────────────────────────────────────────────────────────
# HighlightLogic — Classe Principale
# ──────────────────────────────────────────────────────────────────────────────

class HighlightLogic:
    def __init__(self, navigator_service, line_y_threshold: float = 7.0):
        self.nav = navigator_service
        self._line_y_threshold = line_y_threshold
        self._aligner = AlignmentEngine()
        self._cursor = CursorTracker()
        self._audio_buf = AudioBufferFixed()
        self._nlp_fallback = NLPFallback()
        self._page_cache = LRUPageCache(max_capacity=15)

    def feed_audio(self, audio_chunk: np.ndarray):
        self._audio_buf.add(audio_chunk)

    def reset_cursor(self):
        self._cursor.reset()
        self._audio_buf.reset()

    def invalidate_page_cache(self, mongo_id: str, page: int):
        self._page_cache.cache.pop((mongo_id, page), None)

    async def get_highlight(
            self,
            mongo_id: str,
            current_page: int,
            speech_text: str,
            last_word_index: Optional[int],
            audio_chunk: Optional[np.ndarray] = None,
    ) -> Optional[dict]:  # CORRECTION : Retourne un dict pour rétrocompatibilité totale avec orchestrator.py

        if last_word_index is None:
            last_word_index = 0
        self._cursor.position = last_word_index

        key = (mongo_id, current_page)
        page_data = self._page_cache.get(key)
        if not page_data:
            page_data = await self._load_and_cache_page(mongo_id, current_page)
            if not page_data:
                return None

        # --- Gestion intelligente du CTC et Lazy Loading ---
        if CTC_AVAILABLE and not getattr(self._aligner, '_load_failed', False):
            if not self._aligner._loaded:
                # Lance le chargement sans bloquer le flux
                if not getattr(self._aligner, '_is_loading', False):
                    self._aligner._is_loading = True
                    asyncio.create_task(asyncio.to_thread(self._aligner.load))
            else:
                # Le modèle est prêt. Vidage du buffer si c'est le premier cycle après chargement.
                if getattr(self._aligner, '_should_flush', False):
                    self._audio_buf.reset()
                    self._aligner._should_flush = False
                    print("🧹 [HighlightLogic] Buffer audio vidé après le chargement du modèle.")

                if audio_chunk is not None:
                    self._audio_buf.add(audio_chunk)

                if self._audio_buf.should_trigger():
                    active_audio = self._audio_buf.get_window()
                    if active_audio is not None:
                        return await self._run_forced_alignment(
                            active_audio, page_data, current_page, last_word_index
                        )

                # Bloque le NLP si de l'audio est en train d'être traité par le CTC
                if self._audio_buf._unread_samples > 0:
                    return None

        # --- Pipeline NLP de Repli (attente du modèle ou absence CTC) ---
        return await self._run_nlp_fallback(
            speech_text, page_data, current_page, last_word_index
        )

    async def _load_and_cache_page(self, mongo_id: str, page: int) -> Optional[dict]:
        word_map = await asyncio.to_thread(self.nav.get_page_word_map, mongo_id, page)
        if not word_map:
            return None

        word_map = TextNormalizer.normalize_pdf_words(word_map)

        data = {
            "words": word_map,
            "stems": [self._nlp_fallback._stem(w["norm"]) for w in word_map],
            "bboxes": [w["bbox"] for w in word_map],
            "raw": [w["text"] for w in word_map],
        }

        key = (mongo_id, page)
        self._page_cache.set(key, data)
        return data

    def _segment_into_lines(self, bboxes: List[List[float]], y_threshold: Optional[float] = None) -> List[List[List[float]]]:
        threshold = y_threshold or self._line_y_threshold
        if not bboxes:
            return []

        lines = []
        current_line = [bboxes[0]]

        for bbox in bboxes[1:]:
            # Utilisation de l'ancre absolue de ligne [0] pour éviter la dérive
            if abs(bbox[1] - current_line[0][1]) < threshold:
                current_line.append(bbox)
            else:
                lines.append(current_line)
                current_line = [bbox]
        lines.append(current_line)
        return lines

    def _generate_smart_bboxes(self, bboxes: List[List[float]]) -> List[List[float]]:
        segmented_lines = self._segment_into_lines(bboxes)
        final_bboxes = []

        for line in segmented_lines:
            merged_line = [
                min(b[0] for b in line),
                min(b[1] for b in line),
                max(b[2] for b in line),
                max(b[3] for b in line),
            ]
            final_bboxes.append(merged_line)

        return final_bboxes

    async def _run_forced_alignment(
            self, audio_chunk: np.ndarray, page_data: dict, page: int, last_index: int
    ) -> Optional[dict]:

        window_size = 60
        start = max(0, last_index - 5)
        end = min(len(page_data["words"]), start + window_size)
        pdf_window = page_data["words"][start:end]

        if not pdf_window:
            return None

        aligned: list[AlignedWord] = await asyncio.to_thread(
            self._aligner.align_chunk, audio_chunk, pdf_window, start
        )

        if not aligned:
            return None

        best = self._cursor.validate_and_advance(aligned)
        if not best:
            return None

        group_start = max(last_index, best.pdf_index - 2)
        group_bboxes = [
            page_data["bboxes"][i]
            for i in range(group_start, best.pdf_index + 1)
            if i < len(page_data["bboxes"])
        ]

        final_bboxes = self._generate_smart_bboxes(group_bboxes)

        return {
            "page": page,
            "bboxes": final_bboxes,
            "bbox": final_bboxes[-1] if final_bboxes else [0, 0, 0, 0], # Compatibilité avec single-bbox clients
            "text": " ".join(page_data["raw"][group_start: best.pdf_index + 1]),
            "index": best.pdf_index,
            "source": "forced_align",
            "confidence": best.score,
        }

    async def _run_nlp_fallback(
            self, speech_text: str, page_data: dict, page: int, last_index: int
    ) -> Optional[dict]:

        result = self._nlp_fallback.find_highlight(
            speech_text, page_data["stems"], page_data["bboxes"], page_data["raw"], last_index
        )
        if not result:
            return None

        group_bboxes = [
            page_data["bboxes"][i]
            for i in range(last_index, result["index"] + 1)
            if i < len(page_data["bboxes"])
        ]
        final_bboxes = self._generate_smart_bboxes(group_bboxes)

        return {
            "page": page,
            "bboxes": final_bboxes,
            "bbox": final_bboxes[-1] if final_bboxes else [0, 0, 0, 0], # Compatibilité avec single-bbox clients
            "text": result["text"],
            "index": result["index"],
            "source": result["source"],
            "confidence": 0.6,
        }