# ==============================================================================
# PROPRIÉTÉ DE AI ASSISTANT - (c) 2024-2026 Mourad Daghfous
# Système d'Interaction Vocale Intelligent pour l'Éducation
# ------------------------------------------------------------------------------
# Ce fichier est confidentiel et protégé par les lois sur la propriété 
# intellectuelle. Toute diffusion non autorisée est passible de poursuites.
# ==============================================================================
import os
import time
import json
import asyncio
import requests
from dotenv import load_dotenv
from openai import OpenAI
from qdrant_client import QdrantClient, models
from fastembed import LateInteractionTextEmbedding, TextEmbedding
from sentence_transformers import SentenceTransformer
import google.generativeai as genai
import fitz
from pymongo import MongoClient
from bson import ObjectId

from services.utils.mlops_config import get_active_embedding_config, get_active_llm_config

# --- CONFIGURATION (Alignée sur le reste du projet) ---
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "Vector_Embeddings")
CACHE_DIR = os.getenv("AI_MODELS_CACHE_PATH", "/Volumes/MonSSD/pfe/ai_models_cache")


class RAGService:
    def __init__(self):
        print("🧠 Initialisation du RAGService (Assistant Textuel)...")
        self.client = QdrantClient(QDRANT_URL, check_compatibility=False)
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self._openai_client = None
        self.current_model_id = None
        self.text_processor = None
        self.config = None
        self.is_colbert = False
        self.text_vector_name = "text"

    @property
    def openai_client(self):
        if self._openai_client is None:
            if not self.openai_api_key:
                print("⚠️ OPENAI_API_KEY manquante. Les fonctionnalités OpenAI seront indisponibles.")
                return None
            self._openai_client = OpenAI(api_key=self.openai_api_key)
        return self._openai_client

    def _prepare_context_for_document(self, mongo_id):
        """ Charge la config MLOps scellée au document et initialise les modèles. """
        mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")

        with MongoClient(mongo_uri) as mc:
            db = mc["course_db"]
            doc = db["documents"].find_one({"_id": ObjectId(mongo_id)})
            if not doc:
                raise ValueError(f"Document {mongo_id} introuvable.")

            version_id = doc.get("mlops_version_id")
            if version_id:
                config = db["mlops_versions"].find_one({"_id": version_id})
            else:
                config = get_active_embedding_config()

        if not config:
            raise ValueError("Aucune configuration MLOps disponible.")

        model_name = config.get("text_model", "colbert-ir/colbertv2.0")

        # Chargement/Basculement dynamique du modèle
        if self.current_model_id != str(config.get("_id")):
            print(f"🔄 Basculement vers le modèle : {model_name}")
            self.is_colbert = "colbert" in model_name.lower()
            self.is_gemini_text = "gemini" in model_name.lower()
            self.is_qwen_text = "qwen3" in model_name.lower()

            if self.is_gemini_text:
                genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
                self.text_processor = "GEMINI_API"
                self.text_vector_name = "text"
            elif self.is_qwen_text:
                load_args = {"cache_folder": CACHE_DIR}
                self.text_processor = SentenceTransformer(model_name.replace("-Int4", ""), **load_args)
                self.text_vector_name = "text"
            elif self.is_colbert:
                self.text_processor = LateInteractionTextEmbedding(model_name=model_name,
                                                                   cache_dir=os.path.join(CACHE_DIR, "fastembed"))
                self.text_vector_name = "colbert_text"
            else:
                self.text_processor = TextEmbedding(model_name=model_name,
                                                    cache_dir=os.path.join(CACHE_DIR, "fastembed"))
                self.text_vector_name = "text"

            self.current_model_id = str(config.get("_id"))
            self.config = config

        return self.config

    def analyze_course_context(self, pdf_path, mongo_id=None):
        """ 
        Détecte le domaine et initialise self.config si un mongo_id est fourni. 
        Supporte OpenAI, Gemini et Ollama.
        """
        if mongo_id:
            try:
                self._prepare_context_for_document(mongo_id)
            except Exception as e:
                print(f"⚠️ [RAG] Impossible de charger la config pour l'analyse : {e}")

        llm_config = get_active_llm_config()
        provider = llm_config.get("llm_provider", "OPENAI")
        model_name = llm_config.get("llm_model", "gpt-4o-mini")

        try:
            doc = fitz.open(pdf_path)
            text_sample = "".join([page.get_text() for page in doc[:3]])
            doc.close()

            if not text_sample: return "Général", "Assistant pédagogique."

            prompt = f"""
            Analyse ce cours et retourne UNIQUEMENT un JSON avec 'courseContext' et 'systemRole'. 
            Le 'courseContext' est le domaine d'enseignement (ex: Informatique, Médecine, Droit, Histoire, Économie, etc.). 
            Le 'systemRole' est une instruction courte pour l'IA adaptée au rôle pédagogique d'un assistant dans ce domaine.
            Contenu : {text_sample[:3000]}
            """

            if provider == "GEMINI":
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(
                    prompt, 
                    generation_config=genai.types.GenerationConfig(response_mime_type="application/json")
                )
                data = json.loads(response.text)
            elif provider == "OLLAMA":
                ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
                payload = {"model": model_name, "prompt": prompt, "stream": False, "format": "json"}
                # Timeout de 120s pour laisser le temps à Ollama de charger le modèle de 4.7 Go en RAM lors de la première requête
                resp = requests.post(f"{ollama_url}/api/generate", json=payload, timeout=120)
                data = json.loads(resp.json()['response'])
            else:
                if not self.openai_client:
                    raise ValueError("Client OpenAI non disponible pour l'analyse.")
                completion = self.openai_client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}
                )
                data = json.loads(completion.choices[0].message.content)

            return data.get("courseContext", "Général"), data.get("systemRole", "Assistant.")
        except Exception as e:
            print(f"❌ Erreur analyse (Provider: {provider}) : {e}")
            return "Général", "Assistant pédagogique."

    async def search_and_generate(self, query, mongo_id=None, history=None):
        """
        Génère une réponse structurée (Humaine + Pédagogique) à partir du cours et du contexte.
        """
        if not mongo_id:
            return {"error": "L'ID du document est requis pour la recherche."}

        print(f"🔍 RAG Search pour : '{query}' (doc: {mongo_id})")

        # 1. Préparation du contexte du document et des LLMs
        current_config = self._prepare_context_for_document(mongo_id)
        llm_config = get_active_llm_config()

        if not self.text_processor:
            return {"error": "Modèle non chargé"}

        # Récupération dynamique des paramètres LLM
        provider = llm_config.get("llm_provider", "OPENAI")
        model_name = llm_config.get("llm_model", "gpt-4o-mini")
        target_collection = current_config.get("qdrant_collection", COLLECTION_NAME)

        # 2. Encodage de la requête
        if self.is_gemini_text:
            response = genai.embed_content(model="models/text-embedding-004", content=query)
            query_embeddings = response['embedding']
        elif self.is_qwen_text:
            query_embeddings = self.text_processor.encode([query])[0]
        elif self.is_colbert:
            query_embeddings = next(self.text_processor.query_embed([query]))
        else:
            query_embeddings = next(self.text_processor.embed([query]))

        query_vec = query_embeddings if isinstance(query_embeddings, list) else query_embeddings.tolist()

        # 3. Recherche Qdrant
        try:
            search_filter = models.Filter(
                must=[models.FieldCondition(key="mongo_file_id", match=models.MatchValue(value=mongo_id))]
            )

            search_result = self.client.query_points(
                collection_name=target_collection,
                query=query_vec,
                using=self.text_vector_name,
                query_filter=search_filter,
                limit=5,
                with_payload=True,
            ).points
        except Exception as e:
            print(f"❌ Erreur Qdrant RAG: {e}")
            return None

        if not search_result:
            return {
                "llmResponse": "Je n'ai pas trouvé assez d'éléments dans ce cours pour t'expliquer cela précisément. Pourrais-tu reformuler ?",
                "simpleExample": "Essaie de demander sur un autre concept du cours.",
                "pageToDisplay": None
            }

        # 4. Préparation du contexte
        context_list = []
        for p in search_result:
            payload = p.payload
            context_list.append({
                "content": payload.get('content'),
                "page_number": payload.get('page_number'),
                "type": payload.get('type')
            })

        context_text = "\n".join(
            [f"[Page {p['page_number']}]: {p['content']}" for p in context_list]
        )
        best_page = context_list[0]['page_number']

        # 5. Récupération du rôle dynamique depuis MongoDB
        system_role = "Tu es Siri, un assistant pédagogique expert et très humain. Ton but est d'aider les étudiants à comprendre les concepts académiques complexes."
        try:
            client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
            db = client["course_db"]
            doc_meta = db["documents"].find_one({"_id": ObjectId(mongo_id)})
            if doc_meta and doc_meta.get("system_role"):
                system_role = f"Je m'appelle {doc_meta.get('ai_name', 'Siri')}. {doc_meta['system_role']}"
        except Exception as e:
            print(f"⚠️ Erreur rôle dynamique : {e}")

        # 6. Formatage de l'historique pour le prompt
        history_text = ""
        if history:
            history_text = "\nCONVERSATION RÉCENTE :\n" + "\n".join([f"- {h['role']}: {h['content']}" for h in history])

        # 7. Génération IA
        start_time = time.time()
        from services.utils.metrics import IA_LLM_TTFT, IA_LLM_TPS

        try:
            # Récupération des paramètres de température depuis la config
            temperature = llm_config.get("llm_temperature", 0.7)
            max_tokens = llm_config.get("llm_max_tokens", 500)
            top_p = llm_config.get("llm_top_p", 1.0)
            freq_penalty = llm_config.get("llm_frequency_penalty", 0.0)
            pres_penalty = llm_config.get("llm_presence_penalty", 0.0)

            prompt = f"""
            {system_role}

            SOURCE DE VÉRITÉ (CONTEXTE DU COURS) :
            ---
            {context_text}
            ---

            CONSIGNES GÉNÉRALES :
            1. RÉPONSE STRICTE : Réponds uniquement en utilisant les informations du contexte ci-dessus. 
            2. REJET DU HORS-SUJET : Si la question de l'utilisateur ne concerne pas le cours (ex: cuisine, météo, questions personnelles) ou si l'information n'est pas dans le contexte, réponds EXACTEMENT : "Je ne peux pas répondre à une question qui sort du contexte du cours actuel."
            3. ANALOGIES : N'utilise des comparaisons ou des exemples de la vie courante (autoroutes, cuisine, etc.) QUE pour expliquer un concept technique présent dans le cours. Ne fabrique jamais de lien forcé entre deux domaines si le cours n'en traite pas.
            4. TON : Sois pédagogue, humain et encourageant. Réponds en français.
            5. CAS RÉEL HISTORIQUE : Cite **quand c'est possible** un exemple célèbre, une entreprise, une personnalité ou une invention qui illustre ce concept dans le monde réel.

            {history_text}

            QUESTION UTILISATEUR : "{query}"

            Format JSON attendu :
            {{
                "llmResponse": "Ta réponse pédagogique ici",
                "simpleExample": "Ton analogie ou exemple concret ici"
            }}
            """

            full_content = ""
            ttft = None

            if provider == "GEMINI":
                model = genai.GenerativeModel(model_name)
                # Note: Le format JSON dans Gemini se configure via response_mime_type
                response = await asyncio.to_thread(
                    model.generate_content, 
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=temperature,
                        max_output_tokens=max_tokens,
                        top_p=top_p,
                        response_mime_type="application/json"
                    )
                )
                full_content = response.text
                ttft = (time.time() - start_time) * 0.5
            elif provider == "OLLAMA":
                ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
                payload = {
                    "model": model_name,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                        "top_p": top_p
                    }
                }
                response = await asyncio.to_thread(requests.post, f"{ollama_url}/api/generate", json=payload,
                                                   timeout=120)
                ai_data_str = response.json()['response']
                full_content = ai_data_str
                # Estimation pour Ollama
                total_duration = time.time() - start_time
                ttft = total_duration * 0.4
            else:
                # STREAMING pour TTFT réel avec Hyperparamètres injection
                stream = self.openai_client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system",
                         "content": "Tu es Siri, un assistant pédagogique expert qui respecte strictement le contexte."},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    stream=True,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=top_p,
                    frequency_penalty=freq_penalty,
                    presence_penalty=pres_penalty
                )

                for chunk in stream:
                    if ttft is None and chunk.choices[0].delta.content:
                        ttft = time.time() - start_time
                        IA_LLM_TTFT.observe(ttft)

                    if chunk.choices[0].delta.content:
                        full_content += chunk.choices[0].delta.content

            total_duration = time.time() - start_time
            # Calcul TPS (Tokens Per Second) - Estimation 1 token ~= 4 caractères
            token_count = len(full_content) / 4
            tps = token_count / total_duration if total_duration > 0 else 0
            IA_LLM_TPS.observe(tps)

            print(f"📊 [IA Metrics] TTFT: {round(ttft, 3) if ttft else 'N/A'}s | TPS: {round(tps, 2)}")

            ai_data = json.loads(full_content)
            return {
                "llmResponse": ai_data.get("llmResponse"),
                "simpleExample": ai_data.get("simpleExample"),
                "pageToDisplay": best_page
            }

        except Exception as e:
            print(f"❌ Erreur RAG LLM : {e}")
            return None
