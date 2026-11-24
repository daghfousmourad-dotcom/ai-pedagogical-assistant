import os
import sys
import uuid
from dotenv import load_dotenv
from openai import OpenAI

# Charger les clés API depuis le .env
load_dotenv()


class VoiceAgentUtils:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("⚠️  OPENAI_API_KEY non trouvée — TTS/STT backend désactivé (fallback navigateur actif)")
            self.client = None
        else:
            self.client = OpenAI(api_key=api_key)

    def is_available(self):
        """Retourne True si le client OpenAI est initialisé (clé API présente)."""
        return self.client is not None

    def transcribe_audio(self, audio_file_path):
        """
        Convertit la voix en texte (STT) en utilisant Whisper.
        Idéal pour capter les termes médicaux complexes.
        """
        if not self.is_available():
            return "Erreur : OpenAI non disponible (clé API manquante)."
        if not os.path.exists(audio_file_path):
            return "Erreur : Fichier audio introuvable."

        try:
            with open(audio_file_path, "rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="text"
                )
            return transcript
        except Exception as e:
            return f"Erreur lors de la transcription : {str(e)}"

    def text_to_speech(self, text, output_filename=None, upload_dir="uploads"):
        """
        Convertit un texte en fichier audio (TTS) via OpenAI tts-1.
        Retourne le chemin local du fichier MP3 généré, ou une chaîne d'erreur.
        """
        if not self.is_available():
            return "Erreur : OpenAI non disponible (clé API manquante)."
        try:
            if output_filename is None:
                output_filename = f"tts_{uuid.uuid4().hex}.mp3"

            os.makedirs(upload_dir, exist_ok=True)
            output_path = os.path.join(upload_dir, output_filename)

            response = self.client.audio.speech.create(
                model="tts-1",   # tts-1 : rapide, idéal temps réel
                voice="alloy",   # voix neutre et claire
                input=text
            )

            response.stream_to_file(output_path)
            return output_path
        except Exception as e:
            return f"Erreur lors de la synthèse vocale : {str(e)}"

    @staticmethod
    def cleanup_expired_audio(directories=None, max_age_hours=24):
        """
        Supprime les fichiers audio temporaires (tts_*.mp3) vieux de plus de max_age_hours.
        Protège l'espace disque contre la saturation.
        """
        import time
        if directories is None:
            directories = [
                "uploads",
                "/Volumes/MonSSD/pfe/test-microservices/shared_uploads",
                "/Volumes/MonSSD/pfe/test-microservices/FastAPI/uploads"
            ]

        deleted_count = 0
        reclaimed_bytes = 0
        now = time.time()
        max_age_seconds = max_age_hours * 3600

        seen_files = set()
        for d in directories:
            if not os.path.exists(d):
                continue
            try:
                for fname in os.listdir(d):
                    if fname.startswith("tts_") and fname.endswith(".mp3"):
                        fpath = os.path.realpath(os.path.join(d, fname))
                        if fpath in seen_files:
                            continue
                        seen_files.add(fpath)
                        if os.path.isfile(fpath):
                            file_age = now - os.path.getmtime(fpath)
                            if file_age > max_age_seconds:
                                size = os.path.getsize(fpath)
                                os.remove(fpath)
                                deleted_count += 1
                                reclaimed_bytes += size
            except Exception as e:
                print(f"⚠️ Erreur lors du nettoyage de {d}: {e}")

        reclaimed_mb = reclaimed_bytes / (1024 * 1024)
        print(f"🧹 [Garbage Collector TTS] {deleted_count} fichiers audio purgés ({reclaimed_mb:.2f} Mo libérés)")
        return {"deleted_files": deleted_count, "reclaimed_mb": round(reclaimed_mb, 2)}

    def classify_intent(self, text_query):
        """
        Analyse le texte pour déterminer l'intention du professeur.
        Intents: NAVIGATION, TECHNICAL_QUESTION, IMAGE_CLARIFICATION
        """
        if not self.is_available():
            return {"intent": "TECHNICAL_QUESTION", "confidence": 0.5, "is_navigation": False}

        prompt = f"""
        Requête : "{text_query}"

        Détermine l'intention :
        1. NAVIGATION : Commande de mouvement dans le document (ex: "va à la page 10", "montre la suite", "avance", "page suivante").
        2. TECHNICAL_QUESTION : Question sur un concept, demande d'explication ou de définition sur le cours enseigné, ou SUIVI d'une discussion précédente (ex: "c'est quoi la récursivité ?", "explique ce principe", "définis cette notion", "plus simple encore", "donne un exemple", "continue").
        3. IMAGE_CLARIFICATION : Demande d'analyser, d'expliquer ou d'agir sur un visuel/schéma présent dans la diapositive (ex: "explique ce schéma", "zoom sur ce graphique", "décris cette illustration").

        Réponds en JSON :
        {{
            "intent": "NAVIGATION" | "TECHNICAL_QUESTION" | "IMAGE_CLARIFICATION",
            "is_navigation": boolean (true si l'utilisateur veut explicitement bouger),
            "confidence": 0.0-1.0,
            "reasoning": "pourquoi ce choix"
        }}
        """
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            import json
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            return {"intent": "TECHNICAL_QUESTION", "confidence": 0.0, "is_navigation": False, "error": str(e)}

# --- MAIN (Appelé depuis Java) ---
if __name__ == "__main__":
    agent = VoiceAgentUtils()

    if len(sys.argv) < 3:
        print("Usage: python voice_agent_utils.py [stt|tts|route] [content]")
        sys.exit(1)

    mode = sys.argv[1].lower()
    content = sys.argv[2]

    if mode == "stt":
        # On fait la transcription PUIS la classification automatiquement
        raw_text = agent.transcribe_audio(content)
        intent_json_str = agent.classify_intent(raw_text)
        try:
            import json
            # Force la sortie en une seule ligne JSON compacte
            parsed = json.loads(intent_json_str)
            print(json.dumps(parsed))
        except:
             # Fallback si le JSON est malformé (peu probable avec GPT)
            print(intent_json_str)
    elif mode == "route":
        print(agent.classify_intent(content))
    elif mode == "tts":
        print(agent.text_to_speech(content))
