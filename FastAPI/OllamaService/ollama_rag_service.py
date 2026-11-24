import os
import json
import requests
from dotenv import load_dotenv
from qdrant_client import QdrantClient, models
from fastembed import LateInteractionTextEmbedding
import fitz

load_dotenv()

from services.utils.mlops_config import get_active_embedding_config

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "Vector_Embeddings")

class OllamaRAGService:
    def __init__(self):
        default_model = os.getenv("OLLAMA_LLM_MODEL", "qwen2.5-coder:7b")
        print(f"🦙 Initialisation du OllamaRAGService (Modèle: {default_model})...")
        self.qdrant = QdrantClient(QDRANT_URL)
        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.model = default_model
        
        # Récupération de la config MLOps active
        self.ml_config = get_active_embedding_config()
        self.collection_name = self.ml_config.get("qdrant_collection", os.getenv("COLLECTION_NAME", "Vector_Embeddings"))
        embedding_model = self.ml_config.get("text_model", "colbert-ir/colbertv2.0")
        
        # Le modèle d'embedding reste local (FastEmbed est déjà local et CPU-friendly)
        PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        CACHE_DIR = os.getenv("AI_MODELS_CACHE_PATH", "/Volumes/MonSSD/pfe/ai_models_cache")
        
        try:
            print(f"📦 OllamaRAGService : Chargement du modèle {embedding_model} (Collection: {self.collection_name})...")
            self.is_colbert = "colbert" in embedding_model.lower()
            from fastembed import TextEmbedding # Ensure TextEmbedding is available
            
            if self.is_colbert:
                self.text_processor = LateInteractionTextEmbedding(
                    model_name=embedding_model,
                    cache_dir=os.path.join(CACHE_DIR, "fastembed")
                )
                self.text_vector_name = "colbert_text"
            else:
                self.text_processor = TextEmbedding(
                    model_name=embedding_model,
                    cache_dir=os.path.join(CACHE_DIR, "fastembed")
                )
                self.text_vector_name = "text"
                
            print(f"✅ OllamaRAGService : Modèle {'ColBERT' if self.is_colbert else 'Dense'} chargé.")
        except Exception as e:
            print(f"❌ OllamaRAGService ERROR: {e}")
            self.text_processor = None

    def search_and_generate(self, query, mongo_id=None):
        # 1. Recherche dans Qdrant
        if self.is_colbert:
            query_embeddings = next(self.text_processor.query_embed([query]))
        else:
            query_embeddings = next(self.text_processor.embed([query]))
            
        search_filter = None
        if mongo_id:
            search_filter = models.Filter(
                must=[models.FieldCondition(key="mongo_file_id", match=models.MatchValue(value=mongo_id))]
            )
        
        search_result = self.qdrant.query_points(
            collection_name=self.collection_name,
            query=query_embeddings.tolist(),
            using=self.text_vector_name,
            query_filter=search_filter,
            limit=5,
            with_payload=True,
        ).points

        if not search_result:
            return {"llmResponse": "Aucune information locale trouvée.", "simpleExample": "Réessayez.", "pageToDisplay": None}

        # 2. Contexte
        context_text = "\n".join([f"[Page {p.payload.get('page_number')}]: {p.payload.get('content')}" for p in search_result])
        best_page = search_result[0].payload.get('page_number')

        # 4. Récupération du rôle dynamique (Niveau DOCUMENT désormais)
        system_role = "Tu es un assistant expert qui aide les étudiants à comprendre leur cours."
        try:
            from pymongo import MongoClient
            from bson import ObjectId
            client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
            db = client["course_db"]
            doc_meta = db["documents"].find_one({"_id": ObjectId(mongo_id)})
            if doc_meta and doc_meta.get("system_role"):
                system_role = doc_meta["system_role"]
        except Exception as e:
            print(f"⚠️ Erreur rôle dynamique local : {e}")

        # 5. Génération IA
        # Raccourcir le contexte pour éviter la surcharge
        short_context = context_text[:2000]

        prompt = f"""Tu es un assistant expert qui aide les étudiants à comprendre leur cours.
En utilisant uniquement les extraits de cours fournis ci-dessous, réponds à la question de l'utilisateur.

QUESTION : "{query}"

CONTEXTE EXTRAIT DU COURS :
{short_context}

Réponds en JSON avec exactement ces deux clés (sans aucun autre texte) :
{{"llmResponse": "Réponse technique et précise en français.", "simpleExample": "Explication simplifiée pour un étudiant."}}
"""
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": 400,
                    "num_ctx": 4096
                }
            }
            response = requests.post(f"{self.ollama_url}/api/generate", json=payload, timeout=300)
            
            if response.status_code != 200:
                print(f"❌ Erreur HTTP {response.status_code}: {response.text[:200]}")
                return None
                
            resp_json = response.json()
            if "response" not in resp_json:
                print(f"❌ Ollama response manquante: {resp_json}")
                return None
                
            ai_data_str = resp_json["response"]
            if not ai_data_str.strip():
                print("❌ Réponse vide reçue de Ollama.")
                return None

            # Nettoyage Markdown (si le LLM renvoie ```json ... ```)
            clean_str = ai_data_str.strip()
            if clean_str.startswith("```json"):
                clean_str = clean_str[7:]
            if clean_str.startswith("```"):
                clean_str = clean_str[3:]
            if clean_str.endswith("```"):
                clean_str = clean_str[:-3]
            clean_str = clean_str.strip()

            import re
            # Sécurité supplémentaire : chercher un bloc JSON valide
            match = re.search(r'\{.*\}', clean_str, re.DOTALL)
            if match:
                clean_str = match.group(0)

            try:
                ai_data = json.loads(clean_str)
            except Exception as e:
                print(f"⚠️ Avertissement: Réponse non-JSON d'Ollama. Contenu: {clean_str[:150]}...")
                ai_data = {
                    "llmResponse": clean_str,
                    "simpleExample": "Explication simplifiée non générée."
                }

            return {
                "llmResponse": ai_data.get("llmResponse", ""),
                "simpleExample": ai_data.get("simpleExample", ""),
                "pageToDisplay": best_page
            }
        except Exception as e:
            print(f"❌ Erreur Ollama RAG : {e}")
            return None

    def analyze_course_context(self, pdf_path):
        """
        Analyse locale via le modèle spécifié.
        """
        try:
            doc = fitz.open(pdf_path)
            text_sample = ""
            for i in range(min(3, len(doc))):
                text_sample += doc[i].get_text()
            doc.close()

            if not text_sample:
                return "Inconnu", "Assistant pédagogique général."

            prompt = f"""Analyse le contenu suivant :
---
{text_sample[:4000]}
---
Détermine le domaine du cours et un rôle système pour une IA.
Réponds UNIQUEMENT en JSON, avec exactement les clés suivantes :
{{"courseContext": "Domaine", "systemRole": "Tu es un expert en..."}}
"""
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": 100,
                    "num_ctx": 4096
                }
            }
            response = requests.post(f"{self.ollama_url}/api/generate", json=payload, timeout=120)
            if response.status_code != 200:
                print(f"❌ Erreur HTTP {response.status_code}: {response.text[:200]}")
                return "Inconnu", "Assistant pédagogique général."

            resp_json = response.json()
            if "response" not in resp_json:
                return "Inconnu", "Assistant pédagogique général."

            ai_data_str = resp_json["response"].strip()
            
            # Nettoyage Markdown
            if ai_data_str.startswith("```json"):
                ai_data_str = ai_data_str[7:]
            if ai_data_str.startswith("```"):
                ai_data_str = ai_data_str[3:]
            if ai_data_str.endswith("```"):
                ai_data_str = ai_data_str[:-3]
            ai_data_str = ai_data_str.strip()

            import re
            match = re.search(r'\{.*\}', ai_data_str, re.DOTALL)
            if match:
                ai_data_str = match.group(0)

            try:
                data = json.loads(ai_data_str)
            except Exception as e:
                print(f"⚠️ Avertissement: Analyse de contexte non-JSON. Contenu: {ai_data_str[:150]}...")
                data = {
                    "courseContext": "Général",
                    "systemRole": "Assistant pédagogique."
                }

            return data.get("courseContext", "Général"), data.get("systemRole", "Assistant.")

        except Exception as e:
            print(f"❌ Erreur analyse contexte locale : {e}")
            return "Général", "Assistant."
