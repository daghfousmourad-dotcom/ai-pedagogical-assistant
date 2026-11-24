# ==============================================================================
# PROPRIÉTÉ DE AI ASSISTANT - (c) 2024-2026 Mourad Daghfous
# Système d'Interaction Vocale Intelligent pour l'Éducation
# ------------------------------------------------------------------------------
# highlight_logic_v2.py — Architecture Forced Alignment (CTC/MMS)
#
# STRATÉGIE FONDAMENTALE :
#   Au lieu de faire ASR → texte → NLP → match PDF (2 sources d'erreur),
#   on fait directement : audio → forced alignment contre texte PDF (0 ASR erreur).
#   Le texte du PDF EST la vérité terrain. On n'en transcrit pas, on l'aligne.
# ==============================================================================

import asyncio
import re
import torch
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
from collections import deque

# ──────────────────────────────────────────────────────────────────────────────
# DÉPENDANCES REQUISES (pip install):
#   ctc-forced-aligner       — alignement forcé CTC multi-langue (dont français)
#   faster-whisper           — VAD + segmentation streaming (optionnel mais recommandé)
#   unidecode                — normalisation pour MMS_FA
#   torch torchaudio         — backend
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

@dataclass
class AlignedWord:
    """Résultat d'un alignement : mot PDF + bbox + confidence."""
    text:       str
    bbox:       list           # [x0, y0, x1, y1]
    page:       int
    pdf_index:  int            # position dans la liste des mots PDF
    score:      float = 1.0    # confiance de l'alignement (0-1)

@dataclass
class HighlightResult:
    page:       int
    bbox:       list
    text:       str
    index:      int            # dernier index atteint dans les mots PDF
    source:     str            # "forced_align" | "nlp_fallback" | "anchor_nlp"
    confidence: float = 1.0


# ──────────────────────────────────────────────────────────────────────────────
# Module 1 — Normalisation du texte (partagé entre CTC et NLP)
# ──────────────────────────────────────────────────────────────────────────────

class TextNormalizer:
    """Normalisation uniforme texte PDF ↔ texte transcrit pour la comparaison."""

    # Correspondances phonétiques françaises courantes (ASR → orthographe)
    _PHONETIC_MAP = {
        "c'est":    "c'est",
        "ses":      "ces",
        "sait":     "sait",
        "é":        "é",
        "ét":       "ét",
    }

    @staticmethod
    def clean(text: str) -> str:
        """Nettoyage de base : minuscules, suppression ponctuation, préfixes élidés."""
        text = text.lower().strip()
        text = re.sub(r"[''`]", "'", text)           # normaliser apostrophes
        text = re.sub(r"^[ldsnj]'", "", text)        # supprimer élisions
        text = re.sub(r"^qu'", "", text)
        text = re.sub(r"[^\w\u00C0-\u017E]", "", text)  # garder accents
        return text

    @staticmethod
    def romanize(text: str) -> str:
        """Translittération pour MMS_FA (qui fonctionne en ASCII)."""
        if UNIDECODE_AVAILABLE:
            return unidecode(text.lower())
        return text.lower()

    @staticmethod
    def normalize_pdf_words(word_map: list) -> list:
        """
        Prépare les mots PDF pour l'alignement forcé.
        Entrée : [{"text": str, "bbox": [...]}]
        Sortie : même liste avec champ "norm" et "roman" ajoutés.
        """
        for w in word_map:
            w["norm"]  = TextNormalizer.clean(w["text"])
            w["roman"] = TextNormalizer.romanize(w["text"])
        return word_map


# ──────────────────────────────────────────────────────────────────────────────
# Module 2 — AlignmentEngine (Forced Alignment CTC)
# ──────────────────────────────────────────────────────────────────────────────

class AlignmentEngine:
    """
    Moteur d'alignement forcé CTC.

    Principe :
      - Le texte PDF est la VÉRITÉ TERRAIN.
      - On aligne l'audio directement contre ce texte, par fenêtre glissante.
      - Résultat : timestamps au niveau du mot avec confidence score.

    Modèle utilisé : facebook/mms-300m (via ctc-forced-aligner)
      - Supporte le français nativement
      - Précision : ~50ms au niveau du mot
      - 5× moins de mémoire que torchaudio MMS_FA
    """

    SAMPLE_RATE = 16_000
    LANGUAGE    = "fra"          # code ISO 639-3 pour le français

    def __init__(self, device: str = None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._model      = None
        self._tokenizer  = None
        self._model_name = "facebook/mms-300m"
        self._loaded     = False

    def load(self):
        """Chargement paresseux du modèle (une seule fois)."""
        if self._loaded or not CTC_AVAILABLE:
            return
        print(f"🔄 [AlignmentEngine] Chargement du modèle {self._model_name}...")
        self._model, self._tokenizer = load_alignment_model(
            self._model_name,
            device=self.device,
        )
        self._loaded = True
        print(f"✅ [AlignmentEngine] Modèle chargé sur {self.device}.")

    def align_chunk(
        self,
        audio_chunk:  np.ndarray,      # shape (N,), float32, 16kHz
        pdf_words:    list,            # fenêtre de mots PDF normalisés
        start_offset: int = 0,         # index de départ dans pdf_words
    ) -> list[AlignedWord]:
        """
        Aligne un chunk audio contre une fenêtre de mots PDF.

        Retourne une liste de AlignedWord triés dans l'ordre de lecture,
        avec leur index PDF et leur bbox.
        """
        if not self._loaded:
            self.load()
        if not CTC_AVAILABLE or not self._loaded:
            return []

        # Construire la chaîne texte pour l'aligneur
        window_texts = [w["roman"] for w in pdf_words]
        transcript   = " ".join(window_texts)

        # Convertir audio en tensor
        waveform = torch.from_numpy(audio_chunk).unsqueeze(0).to(self.device)

        try:
            emissions, stride = generate_emissions(
                self._model, waveform, batch_size=1
            )
            tokens_starred, text_starred = preprocess_text(
                transcript,
                romanize=False,      # déjà romanisé
                language=self.LANGUAGE,
                tokenizer=self._tokenizer,
                split_size="word",
            )
            segments, scores, blank_token = get_alignments(
                emissions, tokens_starred, self._tokenizer
            )
            spans = get_spans(tokens_starred, segments, blank_token)
            results = postprocess_results(text_starred, spans, stride, scores)

        except Exception as e:
            print(f"⚠️ [AlignmentEngine] Erreur alignement : {e}")
            return []

        # Mapper résultats → mots PDF (par position séquentielle)
        aligned = []
        for i, res in enumerate(results):
            pdf_idx = start_offset + i
            if pdf_idx >= len(pdf_words) + start_offset:
                break
            pdf_word = pdf_words[i] if i < len(pdf_words) else None
            if pdf_word is None:
                continue
            aligned.append(AlignedWord(
                text      = pdf_word["text"],
                bbox      = pdf_word["bbox"],
                page      = pdf_word.get("page", 0),
                pdf_index = pdf_idx,
                score     = float(res.get("score", 1.0)),
            ))

        return aligned


# ──────────────────────────────────────────────────────────────────────────────
# Module 3 — AudioBuffer (fenêtre glissante temps réel)
# ──────────────────────────────────────────────────────────────────────────────

class AudioBuffer:
    """
    Tampon audio glissant pour le traitement streaming.

    Stratégie :
      - Fenêtre active de WINDOW_S secondes
      - Overlap de OVERLAP_S secondes (pour ne pas rater les mots aux jonctions)
      - Déclenchement de l'alignement à chaque STRIDE_S secondes de nouvel audio
    """

    SAMPLE_RATE = 16_000
    WINDOW_S    = 3.0    # taille de la fenêtre d'alignement
    OVERLAP_S   = 0.5    # chevauchement avec la fenêtre précédente
    STRIDE_S    = 0.5    # fréquence de déclenchement (toutes les 500ms)

    def __init__(self):
        self._buffer      = deque()
        self._total_added = 0
        self._last_trigger = 0

    def add(self, audio_chunk: np.ndarray):
        """Ajoute de l'audio (peut être de n'importe quelle taille)."""
        self._buffer.extend(audio_chunk.tolist())
        self._total_added += len(audio_chunk)

    def should_trigger(self) -> bool:
        """Indique si assez de nouvel audio est disponible pour un alignement."""
        new_samples = self._total_added - self._last_trigger
        return new_samples >= int(self.STRIDE_S * self.SAMPLE_RATE)

    def get_window(self) -> Optional[np.ndarray]:
        """
        Retourne la fenêtre courante d'audio pour l'alignement,
        ou None si pas assez d'audio.
        """
        window_samples = int(self.WINDOW_S  * self.SAMPLE_RATE)
        overlap_samples = int(self.OVERLAP_S * self.SAMPLE_RATE)

        buf_list = list(self._buffer)
        if len(buf_list) < overlap_samples:
            return None

        # On prend jusqu'à WINDOW_S secondes depuis le début du buffer
        window = buf_list[:window_samples]
        self._last_trigger = self._total_added

        # On consomme le buffer en gardant l'overlap
        consumed = max(0, len(buf_list) - overlap_samples)
        for _ in range(consumed):
            if self._buffer:
                self._buffer.popleft()

        return np.array(window, dtype=np.float32)

    def reset(self):
        self._buffer.clear()
        self._total_added = 0
        self._last_trigger = 0


# ──────────────────────────────────────────────────────────────────────────────
# Module 4 — CursorTracker (position et cohérence)
# ──────────────────────────────────────────────────────────────────────────────

class CursorTracker:
    """
    Gère la position courante dans le PDF et filtre les sauts aberrants.

    Règles de cohérence :
      1. Le curseur ne peut PAS reculer de plus de LOOKBACK mots
         (gère les répétitions normales d'un lecteur)
      2. Le curseur ne peut PAS avancer de plus de MAX_JUMP mots en une seule étape
         (filtre les fausses correspondances lointaines)
      3. Confidence minimale requise pour valider un avancement
    """

    LOOKBACK       = 5     # retour arrière max autorisé (répétitions)
    MAX_JUMP       = 40    # saut avant max (lecture rapide ou silence)
    MIN_CONFIDENCE = 0.45  # score d'alignement CTC minimum pour accepter

    def __init__(self):
        self.position   = 0    # index courant dans les mots PDF
        self.page       = 0
        self._history   = deque(maxlen=20)

    def validate_and_advance(self, aligned_words: list[AlignedWord]) -> Optional[AlignedWord]:
        """
        Filtre les mots alignés et retourne le meilleur mot valide pour le surlignage.
        Met à jour la position si validé.
        """
        if not aligned_words:
            return None

        # Filtrer par confidence
        candidates = [w for w in aligned_words if w.score >= self.MIN_CONFIDENCE]
        if not candidates:
            # Prendre quand même le meilleur score disponible si rien ne passe le seuil
            candidates = sorted(aligned_words, key=lambda w: w.score, reverse=True)[:1]

        # Choisir le dernier mot validé de la séquence (front de lecture)
        best = max(candidates, key=lambda w: w.pdf_index)

        # Règle 1 : pas de recul excessif
        if best.pdf_index < self.position - self.LOOKBACK:
            print(f"🚫 [Cursor] Recul excessif ignoré : {best.pdf_index} < {self.position - self.LOOKBACK}")
            return None

        # Règle 2 : pas de saut excessif vers l'avant
        if best.pdf_index > self.position + self.MAX_JUMP:
            print(f"🚫 [Cursor] Saut excessif ignoré : {best.pdf_index} > {self.position + self.MAX_JUMP}")
            return None

        # Validation : mise à jour du curseur
        if best.pdf_index >= self.position:
            self.position = best.pdf_index
            self.page     = best.page
            self._history.append(best.pdf_index)
            print(f"✅ [Cursor] Avancé → index {self.position}, score={best.score:.2f}")

        return best

    def reset(self):
        self.position = 0
        self.page     = 0
        self._history.clear()


# ──────────────────────────────────────────────────────────────────────────────
# Module 5 — NLPFallback (repli NLP amélioré si CTC non disponible)
# ──────────────────────────────────────────────────────────────────────────────

class NLPFallback:
    """
    Version améliorée de l'ancien algorithme de matching NLP.
    Utilisé uniquement si ctc-forced-aligner n'est pas installé.

    Améliorations vs v1 :
      - Trigrammes au lieu de bigrammes (ancrage plus stable)
      - Fenêtre dynamique adaptée à la vitesse de lecture
      - Score composite (strict > radicale > floue) avec seuils calibrés
      - Détection de stagnation avec reset automatique
    """

    from nltk.stem.snowball import SnowballStemmer as _Stemmer
    from fuzzywuzzy import fuzz as _fuzz

    STOP_WORDS = {
        'le','la','les','des','de','du','un','une','au','aux','ce','ces',
        'dans','en','par','pour','sur','avec','et','ou','ne','pas','qui',
        'que','quoi','dont','où','mes','tes','ses','nos','vos','leurs',
        'mais','donc','car','ni','si','tout','tous','toute','toutes',
        'chaque','aucun','aucune','autre','autres','comme','plus','très',
        'bien','aussi','même','alors','ainsi','encore','déjà','puis',
    }

    # Vitesse de lecture : mots/seconde → fenêtre de recherche adaptative
    READING_SPEED_WPS  = 3.0   # ~180 mots/min (lecture normale)
    AUDIO_CHUNK_S      = 2.0   # secondes par chunk ASR
    BASE_WINDOW        = int(READING_SPEED_WPS * AUDIO_CHUNK_S * 1.5)  # marge × 1.5

    def __init__(self):
        self._stemmer = self._Stemmer("french")
        self._stagnation_counter = 0
        self._STAGNATION_LIMIT   = 8   # chunks sans avancement → reset fenêtre

    def _clean(self, w: str) -> str:
        w = w.lower().strip()
        w = re.sub(r"[''`]", "'", w)
        w = re.sub(r"^[ldsnj]'", "", w)
        w = re.sub(r"^qu'", "", w)
        return "".join(c for c in w if c.isalnum())

    def _stem(self, w: str) -> str:
        return self._stemmer.stem(self._clean(w))

    def _get_candidates(self, speech_words: list) -> list:
        """Extrait les mots porteurs des 5 derniers mots du discours."""
        candidates = []
        for i in range(1, min(6, len(speech_words)+1)):
            w = speech_words[-i]
            c = self._clean(w)
            if c in self.STOP_WORDS or (len(c) < 3 and len(speech_words) > 1):
                continue
            candidates.append((self._stem(w), c, w))
        return candidates

    def _find_trigram_anchor(self, speech_stems: list, pdf_stems: list,
                             search_start: int, search_end: int) -> int:
        """Ancrage via trigrammes (plus robuste que bigrammes)."""
        if len(speech_stems) < 3:
            return search_start

        target_trigrams = set()
        for i in range(len(speech_stems) - 2):
            target_trigrams.add((speech_stems[i], speech_stems[i+1], speech_stems[i+2]))
        target_trigrams = set(list(target_trigrams)[-4:])  # 4 derniers trigrammes

        for i in range(search_start, min(search_end, len(pdf_stems) - 2)):
            tg = (pdf_stems[i], pdf_stems[i+1], pdf_stems[i+2])
            if tg in target_trigrams:
                print(f"⚓ [NLP-Anchor] Trigramme trouvé à index {i+2}")
                return i + 2

        # Repli sur bigrammes
        target_bigrams = set()
        for i in range(len(speech_stems) - 1):
            target_bigrams.add((speech_stems[i], speech_stems[i+1]))
        target_bigrams = set(list(target_bigrams)[-3:])

        for i in range(search_start, min(search_end, len(pdf_stems) - 1)):
            if (pdf_stems[i], pdf_stems[i+1]) in target_bigrams:
                print(f"⚓ [NLP-Anchor] Bigramme trouvé à index {i+1}")
                return i + 1

        return search_start

    def find_highlight(
        self,
        speech_text: str,
        pdf_stems:   list,
        pdf_bboxes:  list,
        pdf_raw:     list,
        last_index:  int,
    ) -> Optional[dict]:
        """Point d'entrée NLP fallback. Retourne un dict compatible HighlightResult."""

        speech_words = speech_text.split()
        if not speech_words:
            return None

        candidates = self._get_candidates(speech_words)
        if not candidates:
            return None

        speech_stems_list = [
            self._stemmer.stem(self._clean(w))
            for w in re.findall(r'\w+', speech_text)
            if len(self._clean(w)) > 2
        ]

        # Fenêtre adaptative : s'élargit si stagnation
        if self._stagnation_counter >= self._STAGNATION_LIMIT:
            window_size = self.BASE_WINDOW * 3
            self._stagnation_counter = 0
            print(f"🔁 [NLP] Fenêtre élargie (stagnation détectée) : {window_size}")
        else:
            window_size = self.BASE_WINDOW

        search_start = last_index
        search_end   = min(len(pdf_stems), search_start + window_size)

        # Ancrage trigramme
        anchor = self._find_trigram_anchor(
            speech_stems_list, pdf_stems, search_start, search_end
        )
        if anchor > search_start:
            search_start = max(0, anchor - 5)
            search_end   = min(len(pdf_stems), anchor + 20)

        best_idx = -1

        # Passe 1 : match strict sur le mot le plus récent
        cand_stem, cand_clean, _ = candidates[0]
        for i in range(search_start, search_end):
            if pdf_stems[i] == cand_stem:
                best_idx = i
                print(f"✅ [NLP] Strict (mot récent) : '{pdf_raw[i]}' idx={i}")
                break

        # Passe 2 : fuzzy sur le mot le plus récent
        if best_idx == -1 and len(cand_clean) > 5:
            best_ratio = 0
            for i in range(search_start, search_end):
                pdf_clean = self._clean(pdf_raw[i])
                if len(pdf_clean) > 5:
                    r = self._fuzz.ratio(pdf_clean, cand_clean)
                    if r >= 70 and r > best_ratio:   # seuil relevé 65→70
                        best_ratio = r
                        best_idx   = i
            if best_idx != -1:
                print(f"✨ [NLP] Fuzzy ({best_ratio}%) : '{pdf_raw[best_idx]}' idx={best_idx}")

        # Passe 3 : repli sur mots précédents
        if best_idx == -1:
            for cand_stem, _, _ in candidates[1:]:
                for i in range(search_start, search_end):
                    if pdf_stems[i] == cand_stem:
                        best_idx = i
                        print(f"✅ [NLP] Strict (repli) : '{pdf_raw[i]}' idx={i}")
                        break
                if best_idx != -1:
                    break

        if best_idx == -1:
            self._stagnation_counter += 1
            return None

        self._stagnation_counter = 0

        # Bbox combinée (même ligne)
        start_bbox = pdf_bboxes[last_index] if last_index < len(pdf_bboxes) else pdf_bboxes[best_idx]
        end_bbox   = pdf_bboxes[best_idx]

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
            "bbox":   final_bbox,
            "text":   " ".join(pdf_raw[last_index : best_idx + 1]),
            "index":  best_idx,
            "source": "nlp_fallback",
        }


# ──────────────────────────────────────────────────────────────────────────────
# HighlightLogicV2 — Classe principale (drop-in replacement de HighlightLogic)
# ──────────────────────────────────────────────────────────────────────────────

class HighlightLogicV2:
    """
    Gestionnaire de surlignage v2 — Architecture Forced Alignment.

    Interface publique identique à HighlightLogic v1 pour faciliter la migration.

    Pipeline :
      ┌─────────────────────────────────────────────────────────┐
      │  Audio chunk (16kHz float32)                            │
      │         ↓                                               │
      │  AudioBuffer (fenêtre glissante 3s, stride 0.5s)        │
      │         ↓                                               │
      │  AlignmentEngine (CTC forced align, MMS facebook)       │
      │         ↓    (si indisponible → NLPFallback)            │
      │  CursorTracker (cohérence + anti-saut)                  │
      │         ↓                                               │
      │  HighlightResult (page, bbox, text, index, confidence)  │
      └─────────────────────────────────────────────────────────┘
    """

    def __init__(self, navigator_service):
        self.nav            = navigator_service
        self._aligner       = AlignmentEngine()
        self._cursor        = CursorTracker()
        self._audio_buf     = AudioBuffer()
        self._nlp_fallback  = NLPFallback()
        self._normalizer    = TextNormalizer()

        # Cache page → word_map normalisé
        self._page_cache: dict = {}

        # Pré-chargement asynchrone du modèle CTC (non bloquant)
        asyncio.ensure_future(asyncio.to_thread(self._aligner.load))

    # ──────────────────────────────────────────────────────────
    # API publique
    # ──────────────────────────────────────────────────────────

    async def get_highlight(
        self,
        mongo_id:        str,
        current_page:    int,
        speech_text:     str,           # transcription ASR (pour NLP fallback)
        last_word_index: Optional[int],
        audio_chunk:     Optional[np.ndarray] = None,  # NOUVEAU : audio brut 16kHz
    ) -> Optional[HighlightResult]:
        """
        Point d'entrée unique.

        - Si audio_chunk fourni → pipeline Forced Alignment (mode optimal)
        - Sinon → pipeline NLP fallback (compatible v1)
        """
        if last_word_index is None:
            last_word_index = 0
        self._cursor.position = last_word_index

        page_data = await self._get_page_data(mongo_id, current_page)
        if not page_data:
            return None

        # ── Branche A : Forced Alignment (audio disponible) ──
        if audio_chunk is not None and CTC_AVAILABLE and self._aligner._loaded:
            return await self._run_forced_alignment(
                audio_chunk, page_data, current_page, last_word_index
            )

        # ── Branche B : NLP fallback (pas d'audio ou modèle non chargé) ──
        return await self._run_nlp_fallback(
            speech_text, page_data, current_page, last_word_index
        )

    def feed_audio(self, audio_chunk: np.ndarray):
        """
        Alimente le buffer audio (appeler depuis votre callback ASR/microphone).
        audio_chunk : np.ndarray float32, 16kHz, mono
        """
        self._audio_buf.add(audio_chunk)

    def reset_cursor(self):
        """Remet le curseur à zéro (changement de page, relecture)."""
        self._cursor.reset()
        self._audio_buf.reset()
        print("🔄 [HighlightV2] Curseur et buffer audio réinitialisés.")

    def invalidate_page_cache(self, mongo_id: str, page: int):
        self._page_cache.pop((mongo_id, page), None)

    # ──────────────────────────────────────────────────────────
    # Internals
    # ──────────────────────────────────────────────────────────

    async def _get_page_data(self, mongo_id: str, page: int) -> Optional[dict]:
        """Charge et normalise les mots de la page (avec cache)."""
        key = (mongo_id, page)
        if key in self._page_cache:
            return self._page_cache[key]

        word_map = await asyncio.to_thread(self.nav.get_page_word_map, mongo_id, page)
        if not word_map:
            return None

        # Enrichissement
        word_map = self._normalizer.normalize_pdf_words(word_map)

        from nltk.stem.snowball import SnowballStemmer
        stemmer = SnowballStemmer("french")

        data = {
            "words":  word_map,
            "stems":  [stemmer.stem(w["norm"]) for w in word_map],
            "bboxes": [w["bbox"] for w in word_map],
            "raw":    [w["text"] for w in word_map],
        }
        self._page_cache[key] = data
        return data

    async def _run_forced_alignment(
        self,
        audio_chunk:    np.ndarray,
        page_data:      dict,
        page:           int,
        last_index:     int,
    ) -> Optional[HighlightResult]:
        """Pipeline principal : forced alignment CTC."""

        # Fenêtre de texte PDF autour de la position courante
        window_size  = 60
        start        = max(0, last_index - 5)
        end          = min(len(page_data["words"]), start + window_size)
        pdf_window   = page_data["words"][start:end]

        if not pdf_window:
            return None

        # Alignement dans un thread pour ne pas bloquer l'event loop
        aligned: list[AlignedWord] = await asyncio.to_thread(
            self._aligner.align_chunk,
            audio_chunk,
            pdf_window,
            start,         # offset pour les index absolus
        )

        if not aligned:
            print("⚠️ [FA] Aucun alignement retourné.")
            return None

        # Validation par le curseur
        best = self._cursor.validate_and_advance(aligned)
        if not best:
            return None

        # Construction de la bbox de surlignage (groupe de mots)
        group_start = max(last_index, best.pdf_index - 2)
        group_bboxes = [
            page_data["bboxes"][i]
            for i in range(group_start, best.pdf_index + 1)
            if i < len(page_data["bboxes"])
        ]
        final_bbox = self._merge_bboxes(group_bboxes)

        return HighlightResult(
            page       = page,
            bbox       = final_bbox,
            text       = " ".join(page_data["raw"][group_start : best.pdf_index + 1]),
            index      = best.pdf_index,
            source     = "forced_align",
            confidence = best.score,
        )

    async def _run_nlp_fallback(
        self,
        speech_text: str,
        page_data:   dict,
        page:        int,
        last_index:  int,
    ) -> Optional[HighlightResult]:
        """Pipeline de repli NLP (compatible interface v1)."""
        result = self._nlp_fallback.find_highlight(
            speech_text,
            page_data["stems"],
            page_data["bboxes"],
            page_data["raw"],
            last_index,
        )
        if not result:
            return None
        return HighlightResult(
            page       = page,
            bbox       = result["bbox"],
            text       = result["text"],
            index      = result["index"],
            source     = result["source"],
            confidence = 0.6,
        )

    @staticmethod
    def _merge_bboxes(bboxes: list) -> list:
        """Fusionne plusieurs bboxes en une seule englobante (même ligne)."""
        if not bboxes:
            return [0, 0, 0, 0]
        if len(bboxes) == 1:
            return bboxes[0]

        # Vérifier si tous sur la même ligne (Y proche)
        y_vals = [b[1] for b in bboxes]
        if max(y_vals) - min(y_vals) < 7:
            return [
                min(b[0] for b in bboxes),
                min(b[1] for b in bboxes),
                max(b[2] for b in bboxes),
                max(b[3] for b in bboxes),
            ]
        # Lignes différentes → on retourne la dernière bbox
        return bboxes[-1]


# ──────────────────────────────────────────────────────────────────────────────
# Compatibilité v1 (alias drop-in)
# ──────────────────────────────────────────────────────────────────────────────

# Pour une migration sans friction :
#   from highlight_logic_v2 import HighlightLogic
HighlightLogic = HighlightLogicV2