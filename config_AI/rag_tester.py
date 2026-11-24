import os
import time
import json
import asyncio
from dotenv import load_dotenv
from openai import OpenAI
from qdrant_client import QdrantClient, models
from fastembed import LateInteractionTextEmbedding, TextEmbedding

# --- ISOLATED TESTER FOR MLOPS ---
# This file is a COPY of services/agents/rag.py modified for Phase 2 Hyperparameter Injection

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "Vector_Embeddings")

class RAGTester:
    def __init__(self, config):
        """
        Initialisation avec une configuration spécifique passée par l'évaluateur.
        """
        self.config = config
        self.provider = "OPENAI" # Forcé pour Phase 2
        self.model_name = config.get("llm_model", "gpt-4o-mini")
        self.collection_name = config.get("qdrant_collection", COLLECTION_NAME)
        
        self.client = QdrantClient(QDRANT_URL, check_compatibility=False)
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        CACHE_DIR = os.getenv("AI_MODELS_CACHE_PATH", "/Volumes/MonSSD/pfe/ai_models_cache")
        embedding_model = config.get("text_model", "colbert-ir/colbertv2.0")
        
        is_colbert = "colbert" in embedding_model.lower()
        if is_colbert:
            self.text_processor = LateInteractionTextEmbedding(
                model_name=embedding_model,
                cache_dir=os.path.join(CACHE_DIR, "fastembed")
            )
            self.is_colbert = True
            self.text_vector_name = "colbert_text"
        else:
            self.text_processor = TextEmbedding(
                model_name=embedding_model,
                cache_dir=os.path.join(CACHE_DIR, "fastembed")
            )
            self.is_colbert = False
            self.text_vector_name = "text"

    async def search_and_generate(self, query, mongo_id=None, forced_params=None):
        """
        Génération avec injection directe d'hyperparamètres (forced_params).
        """
        if not self.text_processor: return None

        # 1. Encodage & Recherche (Identique prod)
        if self.is_colbert:
            query_embeddings = next(self.text_processor.query_embed([query]))
        else:
            query_embeddings = next(self.text_processor.embed([query]))

        search_filter = None
        if mongo_id:
            search_filter = models.Filter(
                must=[models.FieldCondition(key="mongo_file_id", match=models.MatchValue(value=mongo_id))]
            )

        search_result = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embeddings.tolist(),
            using=self.text_vector_name,
            query_filter=search_filter,
            limit=5,
            with_payload=True,
        ).points

        if not search_result: return None

        context_text = "\n".join([f"[Page {p.payload.get('page_number')}]: {p.payload.get('content')}" for p in search_result])
        
        # 2. Injection des hyperparamètres
        params = forced_params or {}
        temperature = params.get("temperature", 0.7)
        top_p = params.get("top_p", 1.0)
        max_tokens = params.get("max_tokens", 300)
        freq_penalty = params.get("frequency_penalty", 0.0)
        pres_penalty = params.get("presence_penalty", 0.0)

        print(f"   [MLOPS DEBUG] Params: Temp={temperature}, TopP={top_p}, FP={freq_penalty}, PP={pres_penalty}")

        prompt = f"""Tu es un assistant pédagogique expert. Utilise UNIQUEMENT le contexte suivant :
        {context_text}
        
        QUESTION : {query}
        
        Format JSON : {{"llmResponse": "...", "simpleExample": "..."}}
        """

        start_time = time.time()
        completion = self.openai_client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            frequency_penalty=freq_penalty,
            presence_penalty=pres_penalty
        )
        
        full_content = completion.choices[0].message.content
        try:
            ai_data = json.loads(full_content)
        except json.JSONDecodeError:
            print(f"[MLOPS WARNING] Failed to parse JSON at high temperature. Attempting regex recovery...")
            import re
            # Extract content from potentially malformed JSON-like string
            resp_match = re.search(r'"llmResponse":\s*"(.*?)"', full_content, re.DOTALL)
            ex_match = re.search(r'"simpleExample":\s*"(.*?)"', full_content, re.DOTALL)
            
            ai_data = {
                "llmResponse": resp_match.group(1) if resp_match else full_content,
                "simpleExample": ex_match.group(1) if ex_match else ""
            }
        
        return {
            "llmResponse": ai_data.get("llmResponse", "Error parsing response"),
            "simpleExample": ai_data.get("simpleExample", ""),
            "pageToDisplay": search_result[0].payload.get('page_number')
        }
