"""
WhisperBridge — STT local via faster-whisper (CPU, modèle BASE)
Compatible Docker/Linux, pas besoin de Metal.
Optimisé pour la transcription continue de cours (français & anglais).
"""
import os
import asyncio
import tempfile
import io
import wave

# faster-whisper : bibliothèque Python pour whisper.cpp CTranslate2
# Modèle : base (multilingue), quantization INT8, ~150MB RAM
try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    print("⚠️ faster-whisper non installé. WhisperBridge désactivé.")


# Configuration via variables d'environnement
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")    # base / small / medium
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")  # int8 pour CPU
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")              # cpu (Metal non dispo en Docker)
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "fr")           # langue principale
FASTEMBED_CACHE_PATH = os.getenv("FASTEMBED_CACHE_PATH", "/tmp/whisper_models")


class WhisperBridge:
    """
    Pont entre le flux audio WebSocket et le modèle Whisper local.
    Utilise faster-whisper (CTranslate2) pour une transcription CPU optimisée.
    
    Configuration Mac → Docker (CPU uniquement) :
    - Modèle BASE multilingue (~145MB)
    - Quantization INT8 (~60MB RAM actif)
    - Latence estimée : 200-500ms pour 1-2 secondes d'audio
    """

    _instance = None  # Singleton pour ne charger le modèle qu'une fois

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.model = None
        self._load_model()

    def _load_model(self):
        if not WHISPER_AVAILABLE:
            print("❌ WhisperBridge: faster-whisper non disponible.")
            return

        model_dir = os.path.join(FASTEMBED_CACHE_PATH, "whisper")
        os.makedirs(model_dir, exist_ok=True)

        try:
            print(f"🎤 WhisperBridge: Chargement du modèle '{WHISPER_MODEL_SIZE}' ({WHISPER_COMPUTE_TYPE}) sur {WHISPER_DEVICE}...")
            self.model = WhisperModel(
                WHISPER_MODEL_SIZE,
                device=WHISPER_DEVICE,
                compute_type=WHISPER_COMPUTE_TYPE,
                download_root=model_dir
            )
            print("✅ WhisperBridge: Modèle prêt.")
        except Exception as e:
            print(f"❌ WhisperBridge: Erreur de chargement : {e}")
            self.model = None

    def is_available(self) -> bool:
        return self.model is not None

    def transcribe_bytes(self, audio_bytes: bytes, sample_rate: int = 16000) -> dict:
        """
        Transcrit un buffer PCM16 (bytes bruts) en texte.
        Retourne {"text": "...", "words": [...], "language": "fr"}
        
        Args:
            audio_bytes: Données audio PCM16 raw (mono, 16kHz)
            sample_rate: Taux d'échantillonnage (défaut 16000 Hz)
        Returns:
            dict avec text, words (timestamps), language
        """
        if not self.is_available():
            return {"text": "", "words": [], "language": "unknown", "error": "model_not_loaded"}

        try:
            # Encapsuler le PCM16 dans un WAV temporaire pour faster-whisper
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, 'wb') as wf:
                wf.setnchannels(1)       # Mono
                wf.setsampwidth(2)       # 16-bit PCM
                wf.setframerate(sample_rate)
                wf.writeframes(audio_bytes)

            wav_buffer.seek(0)

            # Transcription avec faster-whisper
            # word_timestamps=True pour le surlignage précis mot-à-mot
            segments, info = self.model.transcribe(
                wav_buffer,
                language=WHISPER_LANGUAGE,
                beam_size=1,          # Priorité vitesse sur CPU
                best_of=1,
                temperature=0.0,      # Greedy decoding (plus rapide)
                word_timestamps=True, # Essentiel pour le surlignage mot-à-mot
                vad_filter=True,      # VAD agressif pour réduire les calculs
                vad_parameters={"min_silence_duration_ms": 300}
            )

            full_text = ""
            all_words = []

            for segment in segments:
                full_text += segment.text + " "
                if segment.words:
                    for word in segment.words:
                        all_words.append({
                            "word": word.word.strip(),
                            "start": round(word.start, 3),
                            "end": round(word.end, 3),
                            "probability": round(word.probability, 3)
                        })

            return {
                "text": full_text.strip(),
                "words": all_words,
                "language": info.language,
                "duration": info.duration
            }

        except Exception as e:
            print(f"❌ WhisperBridge.transcribe_bytes error: {e}")
            return {"text": "", "words": [], "language": "unknown", "error": str(e)}

    async def async_transcribe_bytes(self, audio_bytes: bytes, sample_rate: int = 16000) -> dict:
        """
        Version asynchrone non-bloquante (délègue à un thread).
        À utiliser depuis les handlers FastAPI/WebSocket.
        """
        return await asyncio.to_thread(self.transcribe_bytes, audio_bytes, sample_rate)
