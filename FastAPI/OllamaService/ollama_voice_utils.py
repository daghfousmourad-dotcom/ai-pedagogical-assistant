import os
import sys
import uuid
import json
import time
import subprocess
import requests
from dotenv import load_dotenv

# Charger les clés API / config depuis le .env
load_dotenv()

class OllamaVoiceUtils:
    def __init__(self):
        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.model = os.getenv("OLLAMA_LLM_MODEL", "qwen2.5-coder:7b")
        print(f"🦙 Initialisation de OllamaVoiceUtils (Modèle: {self.model})")

    def is_available(self):
        """Vérifie si Ollama est accessible."""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags")
            return response.status_code == 200
        except:
            return False

    def transcribe_audio(self, audio_file_path):
        """
        STT Local : Whisper (via faster-whisper ou autre bibliothèque locale).
        Note: Pour cette démo, on simule ou on recommande l'installation de faster-whisper.
        """
        print(f"🎤 STT Local (Simulé/Whisper) pour : {audio_file_path}")
        # En production PFE, on utiliserait : 
        # from faster_whisper import WhisperModel
        # model = WhisperModel("base", device="cpu", compute_type="int8")
        # segments, _ = model.transcribe(audio_file_path)
        # return "".join([s.text for s in segments])
        return "[Simulation STT Locale] Note: Whisper local doit être installé."

    def text_to_speech(self, text, output_filename=None, upload_dir="uploads"):
        """
        TTS Local : Génération M4A hors-ligne sécurisée (compatible Mac / Navigateurs).
        Utilise subprocess avec passage direct des arguments pour éviter les corruptions de shell.
        """
        if not text or not text.strip():
            return "Erreur : Aucun texte fourni."

        if output_filename is None:
            output_filename = f"tts_local_{uuid.uuid4().hex}.m4a"
        
        os.makedirs(upload_dir, exist_ok=True)
        output_path = os.path.join(upload_dir, output_filename)

        clean_text = text.strip()
        print(f"🔊 TTS Local pour ({len(clean_text)} caractères) : {clean_text[:40]}...")

        try:
            # Invocation directe sécurisée sans passer par /bin/sh
            res = subprocess.run(
                ["say", "-o", output_path, clean_text],
                capture_output=True,
                text=True,
                check=False
            )
            if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return output_path
            else:
                err_msg = res.stderr.strip() if res.stderr else "say a échoué"
                print(f"⚠️ Échec say commande: {err_msg}")
                return f"Erreur TTS Local: {err_msg}"
        except Exception as e:
            print(f"❌ Exception TTS Local: {e}")
            return f"Erreur TTS Local: {str(e)}"

    @staticmethod
    def cleanup_expired_audio(directories=None, max_age_hours=24):
        """
        Supprime les fichiers audio temporaires (tts_local_*.m4a et tts_*.mp3) vieux de plus de max_age_hours.
        """
        if directories is None:
            directories = [
                "uploads",
                "/Volumes/MonSSD/pfe/test-microservices/shared_uploads",
                "/Volumes/MonSSD/pfe/test-microservices/FastAPI/uploads"
            ]

        now = time.time()
        max_age_seconds = max_age_hours * 3600
        deleted_count = 0
        reclaimed_bytes = 0

        for d in directories:
            if not os.path.exists(d):
                continue
            for fname in os.listdir(d):
                if fname.startswith("tts_") and (fname.endswith(".mp3") or fname.endswith(".m4a")):
                    fpath = os.path.join(d, fname)
                    try:
                        fstat = os.stat(fpath)
                        if now - fstat.st_mtime > max_age_seconds:
                            fsize = fstat.st_size
                            os.remove(fpath)
                            deleted_count += 1
                            reclaimed_bytes += fsize
                    except Exception as e:
                        print(f"⚠️ Erreur suppression {fpath}: {e}")

        reclaimed_mb = round(reclaimed_bytes / (1024 * 1024), 2)
        print(f"🧹 [Audio GC Local] Nettoyage : {deleted_count} fichiers supprimés ({reclaimed_mb} Mo libérés)")
        return {
            "deleted_files": deleted_count,
            "reclaimed_mb": reclaimed_mb
        }

    def classify_intent(self, text_query):
        """
        Analyse d'intention via le modèle LLM spécifié sur Ollama.
        """
    def classify_intent(self, text_query):
        """
        Analyse d'intention via le modèle LLM spécifié sur Ollama.
        """
        try:
            system_prompt = """
Tu es un assistant IA pédagogique. Tu dois classer l'intention de l'utilisateur.
RÈGLES :
- Question sur un visuel/schéma à l'écran -> IMAGE_CLARIFICATION.
- Question sur le contenu/cours (explications) -> TECHNICAL_QUESTION.
- Ordre de navigation (page X, suivante...) -> NAVIGATION.
- Recherche de mot-clé spécifique -> TEXT_QUERY.

Réponds en JSON uniquement {"intent": "...", "confidence": 0.x}.
"""
            payload = {
                "model": self.model,
                "system": system_prompt,
                "prompt": f"Classe cette phrase : '{text_query}'",
                "stream": False,
                "format": "json"
            }
            response = requests.post(f"{self.ollama_url}/api/generate", json=payload, timeout=30)
            if response.status_code != 200:
                print(f"❌ Ollama Error {response.status_code}: {response.text}")
                return {"intent": "TEXT_QUERY", "confidence": 0.0, "reasoning": "Error from Ollama"}
            
            result = response.json()
            response_text = result.get('response', '').strip()
            
            # Tentative de nettoyage si le modèle a mis du texte avant/après le JSON
            if "{" in response_text and "}" in response_text:
                start = response_text.find("{")
                end = response_text.rfind("}") + 1
                response_text = response_text[start:end]
            
            try:
                if not response_text:
                    raise ValueError("Réponse vide")
                return json.loads(response_text)
            except Exception as parse_err:
                print(f"⚠️ Échec parsing JSON Ollama: {parse_err} | Raw: {response_text}")
                if "IMAGE_CLARIFICATION" in response_text:
                    return {"intent": "IMAGE_CLARIFICATION", "confidence": 0.5, "reasoning": "Extrait du texte"}
                return {"intent": "TEXT_QUERY", "confidence": 0.5, "reasoning": "Fallback par défaut"}

        except Exception as e:
            print(f"❌ Erreur Ollama Intent: {e}")
            return {"intent": "TEXT_QUERY", "confidence": 0.0, "reasoning": str(e)}

if __name__ == "__main__":
    agent = OllamaVoiceUtils()
    if len(sys.argv) > 2:
        mode = sys.argv[1].lower()
        content = sys.argv[2]
        if mode == "stt": print(agent.transcribe_audio(content))
        elif mode == "intent": print(agent.classify_intent(content))
        elif mode == "tts": print(agent.text_to_speech(content))
