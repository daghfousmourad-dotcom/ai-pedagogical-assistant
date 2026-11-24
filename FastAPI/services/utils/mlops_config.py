import os
from pymongo import MongoClient

from services.utils.naming import get_safe_collection_name


def get_active_embedding_config():
    """
    Récupère la configuration d'embedding active depuis MongoDB.
    Sert de point d'entrée MLOps pour piloter l'IA depuis l'interface.
    """
    # Détection dynamique du host pour éviter le blocage sur localhost
    _MONGO_HOST = "mongodb" if os.path.exists('/.dockerenv') else "localhost"
    default_uri = f"mongodb://{_MONGO_HOST}:27017"

    mongo_uri = os.getenv("MONGO_URI", default_uri)

    client = None
    try:
        # On utilise un timeout court pour ne pas bloquer le worker si MongoDB est down
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=2000)
        db = client["course_db"]
        collection = db["mlops_versions"]

        # On cherche la version active
        active = collection.find_one({"is_active": True})
        if active:
            return active

    except Exception as e:
        print(f"⚠️ Erreur MLOps MongoDB ({e}). Utilisation du fallback.")
    finally:
        if client:
            client.close()  # TRÈS IMPORTANT : On ferme la connexion après la lecture


    # Fallback par défaut si aucune connexion ou configuration
    text_m = "colbert-ir/colbertv2.0"
    vision_m = "vidore/colpali-v1.3"
    
    return {
        "version_name": "v1_colbert_colpali",
        "is_active": True,
        "text_model": text_m,
        "vision_model_cuda": vision_m,
        "vision_model_cpu": "vidore/colSmol-256M",
        "extraction_method": "pymupdf_blocks",
        "qdrant_collection": get_safe_collection_name(text_m, vision_m),
        "text_block_threshold": 10,
    }

def get_active_llm_config():
    """
    Récupère la configuration LLM active depuis MongoDB.
    """
    _MONGO_HOST = "mongodb" if os.path.exists('/.dockerenv') else "localhost"
    default_uri = f"mongodb://{_MONGO_HOST}:27017"

    mongo_uri = os.getenv("MONGO_URI", default_uri)

    client = None
    try:
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=2000)
        db = client["course_db"]
        collection = db["mlops_llm_configs"]

        active = collection.find_one({"is_active": True})
        if active:
            return active

    except Exception as e:
        print(f"⚠️ Erreur MLOps MongoDB LLM ({e}). Utilisation du fallback LLM.")
    finally:
        if client:
            client.close()

    # Fallback LLM par défaut (Modèle local léger et économe en RAM)
    local_model = os.getenv("OLLAMA_LLM_MODEL", "qwen2.5-coder:7b")
    local_provider = os.getenv("LLM_PROVIDER", "OLLAMA")
    return {
        "config_name": "local_lightweight",
        "llm_provider": local_provider,
        "llm_model": local_model,
        "llm_temperature": 0.7,
        "llm_max_tokens": 400,
        "llm_top_p": 1.0,
        "llm_frequency_penalty": 0.0,
        "llm_presence_penalty": 0.0,
        "stt_provider": "OPENAI",
        "tts_provider": "OPENAI",
        "is_active": True
    }
