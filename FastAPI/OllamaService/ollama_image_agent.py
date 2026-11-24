import base64
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

class OllamaImageClarifierAgent:
    def __init__(self):
        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.model = os.getenv("OLLAMA_VISION_MODEL", "qwen3.5:9b") # Qwen 3.5 gère la vision et le texte
        print(f"🦙 Initialisation de OllamaImageClarifier (Modèle: {self.model})")

    def _encode_image(self, image_path_or_bytes):
        if isinstance(image_path_or_bytes, bytes):
            return base64.b64encode(image_path_or_bytes).decode('utf-8')
        with open(image_path_or_bytes, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def analyze_original_image(self, image_input, system_role="Tu es un assistant pédagogique expert."):
        """ Analyse technique via le modèle Vision de Ollama. """
        try:
            base64_image = self._encode_image(image_input)
            payload = {
                "model": self.model,
                "prompt": f"{system_role} Analyse cette image technique ou ce schéma pédagogique. Identifie les concepts clés de manière concise pour un étudiant.",
                "stream": False,
                "images": [base64_image]
            }
            response = requests.post(f"{self.ollama_url}/api/generate", json=payload, timeout=30)
            if response.status_code != 200:
                print(f"❌ Ollama Vision Error {response.status_code}: {response.text}")
                return f"Erreur Ollama: {response.status_code}"
            
            result = response.json()
            if 'response' not in result:
                print(f"❌ Ollama Vision: No 'response' in result: {result}")
                return "L'analyse visuelle a échoué (réponse incomplète)."
                
            return result['response']
        except Exception as e:
            return f"Erreur Vision Locale: {str(e)}"

    def refine_search_query(self, student_remark, visual_analysis):
        """ Raffinement de la recherche via Ollama (Modèle LLM standard recommandé). """
        # On utilise le modèle LLM standard ici pour la réflexion
        llm_model = os.getenv("OLLAMA_LLM_MODEL", "qwen3.5:9b")
        prompt = f"Analyse: {visual_analysis} | Question: {student_remark}. Génère 5 mots-clés de recherche précis pour trouver un schéma ou une photo éducative équivalente (Anglais, séparés par virgules)."
        
        try:
            payload = {"model": llm_model, "prompt": prompt, "stream": False}
            response = requests.post(f"{self.ollama_url}/api/generate", json=payload, timeout=30)
            return response.json()['response'].strip()
        except:
            return "radiology clinical case"

    def process_clarification(self, student_remark, image_input, mongo_file_id=None):
        # Pour le PFE, on peut garder Tavily pour la recherche (besoin du web) 
        # ou simuler si on veut être 100% offline. 
        # Ici on réutilise la logique de recherche si Tavily est dispo.
        from services.agents.image_clarifier import ImageClarifierAgent
        legacy_agent = ImageClarifierAgent() 
        
        # Récupération rôle et sources personnalisées
        custom_sources = []
        system_role = "Tu es un assistant pédagogique expert."
        if mongo_file_id:
            try:
                from pymongo import MongoClient
                from bson import ObjectId
                client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
                db = client["course_db"]
                doc = db["documents"].find_one({"_id": ObjectId(mongo_file_id)})
                if doc:
                    if doc.get("system_role"):
                        system_role = doc.get("system_role")
                    if doc.get("custom_sources"):
                        custom_sources = doc.get("custom_sources")
            except:
                pass

        visual_analysis = self.analyze_original_image(image_input, system_role=system_role)
        refined_query = self.refine_search_query(student_remark, visual_analysis)
        images = legacy_agent.search_alternative_images(refined_query, custom_sources)

        return {
            "status": "success",
            "context_understood": visual_analysis,
            "search_query": refined_query,
            "found_images": images[:3]
        }
