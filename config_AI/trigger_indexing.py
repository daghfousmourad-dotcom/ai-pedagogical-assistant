import os
import sys
import json
import time
import torch
from qdrant_client import QdrantClient, models

# Add FastAPI root to path
FASTAPI_PATH = "/Volumes/MonSSD/pfe/test-microservices/FastAPI"
sys.path.append(FASTAPI_PATH)

from services.indexing.upload_advanced import UploadAdvanced
from services.utils.mlops_config import get_active_embedding_config

# Config
PDF_PATH = "/Volumes/MonSSD/pfe/test-microservices/shared_uploads/Sémiologie radiologie en pathologie digestive 2015.pdf"
MONGO_ID = "69b7f59cfd94fa75413eeef3"
CACHE_FILE = "/tmp/last_mlops_indexing.json"
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")

def get_model_dim(model_name, is_colbert=False):
    """Calcule dynamiquement la dimension du modèle avec retries."""
    from fastembed import LateInteractionTextEmbedding, TextEmbedding
    CACHE_DIR = os.getenv("AI_MODELS_CACHE_PATH", "/Volumes/MonSSD/pfe/ai_models_cache")
    
    if is_colbert:
        # ColBERT v2 est généralement 128
        return 128 
    
    for attempt in range(3):
        try:
            model = TextEmbedding(model_name=model_name, cache_dir=os.path.join(CACHE_DIR, "fastembed"))
            # Juste pour être sûr d'avoir la dimension réelle
            vec = next(model.embed(["test"]))
            return len(vec)
        except Exception as e:
            if attempt == 2: raise
            print(f"⚠️  Tentative {attempt+1} échouée pour {model_name}: {e}. Retrying in 2s...")
            time.sleep(2)
    return 384 # Fallback par défaut (BGE dimension)

def setup_qdrant_collection(client, collection_name, text_model_name, vision_model_name):
    """Recherche la collection et ne la recrée que si les dimensions sont incompatibles."""
    print(f"🔍 Vérification de la collection Qdrant : {collection_name}")
    
    is_colbert = "colbert" in text_model_name.lower()
    text_dim = get_model_dim(text_model_name, is_colbert)
    vision_dim = 128 
    
    target_vector = "colbert_text" if is_colbert else "text"
    
    # Check compatibility
    if client.collection_exists(collection_name):
        coll_info = client.get_collection(collection_name)
        vectors = coll_info.config.params.vectors
        
        if isinstance(vectors, dict) and target_vector in vectors:
            existing_dim = vectors[target_vector].size
            if existing_dim == text_dim:
                print(f"   ✅ Collection compatible détectée (Vector: {target_vector}, Dim: {existing_dim}).")
                return True # Compatible
            else:
                print(f"   ⚠️ Dimension incompatible ({existing_dim} vs {text_dim}).")
        else:
            print(f"   ⚠️ Vecteur cible {target_vector} non trouvé dans la collection existante.")
            
        print(f"   🗑️  Suppression pour mise à jour de la structure...")
        client.delete_collection(collection_name)
        
    vectors_config = {
        "colpali_image": models.VectorParams(
            size=vision_dim,
            distance=models.Distance.DOT,
            multivector_config=models.MultiVectorConfig(comparator=models.MultiVectorComparator.MAX_SIM)
        )
    }
    
    if is_colbert:
        vectors_config["colbert_text"] = models.VectorParams(
            size=text_dim,
            distance=models.Distance.COSINE,
            multivector_config=models.MultiVectorConfig(comparator=models.MultiVectorComparator.MAX_SIM)
        )
    else:
        vectors_config["text"] = models.VectorParams(
            size=text_dim,
            distance=models.Distance.COSINE
        )

    client.create_collection(
        collection_name=collection_name,
        vectors_config=vectors_config
    )
    print(f"✅ Collection {collection_name} créée avec succès.")
    return False # New collection created

def main():
    config = get_active_embedding_config()
    current_text_model = config.get("text_model", "colbert-ir/colbertv2.0")
    current_vision_model = config.get("vision_model_cuda", "vidore/colpali-v1.3")
    collection_name = config.get("qdrant_collection", "MLOps_Test_Collection")
    
    is_colbert = "colbert" in current_text_model.lower()
    print(f"📡 Mode détecté : {'ColBERT' if is_colbert else 'Dense'}")
    
    # Check cache FAST (if it exists)
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            last_run = json.load(f)
            if last_run.get("text_model") == current_text_model and \
               last_run.get("vision_model") == current_vision_model and \
               last_run.get("collection_name") == collection_name and \
               last_run.get("status") == "success":
                print(f"⏩ Indexation déjà à jour (Cache). Skip.")
                return

    client = QdrantClient(QDRANT_URL)
    
    try:
        # 1. Setup Collection
        collection_ready = setup_qdrant_collection(client, collection_name, current_text_model, current_vision_model)
        
        # --- ROBUST SKIP LOGIC: Direct Qdrant Check ---
        if collection_ready:
            try:
                coll_info = client.get_collection(collection_name)
                points_count = coll_info.points_count
                if points_count > 100:  # Threshold for a populated collection
                    print(f"   ⏩ Configuration déjà indexée dans Qdrant ({points_count} points). Skip.")
                    # Update cache for next time
                    with open(CACHE_FILE, "w") as f:
                        json.dump({
                            "text_model": current_text_model,
                            "vision_model": current_vision_model,
                            "collection_name": collection_name,
                            "status": "success",
                            "timestamp": time.time(),
                            "points": points_count
                        }, f)
                    return
            except Exception as e:
                print(f"   ⚠️ Erreur check Qdrant: {e}. On continue.")

        # 2. Run Indexing
        print(f"📡 Démarrage de l'indexation pour {current_text_model} + {current_vision_model}...")
        from services.indexing.upload_advanced import UploadAdvanced
        
        # Récupérer l'ID mongo s'il est défini dans la config
        target_mongo_id = config.get("mongo_id", "69b7f59cfd94fa75413eeef3")
        
        indexer = UploadAdvanced()
        start_time = time.time()
        indexer.process_pdf(PDF_PATH, mongo_id=target_mongo_id)
        duration = time.time() - start_time
        
        # Save cache
        with open(CACHE_FILE, "w") as f:
            json.dump({
                "text_model": current_text_model,
                "vision_model": current_vision_model,
                "collection_name": collection_name,
                "status": "success",
                "timestamp": time.time(),
                "duration": duration
            }, f)
            
        print(f"✅ Test Indexing terminé en {duration:.1f}s.")
        
    except Exception as e:
        error_reason = str(e)
        print(f"❌ Erreur Indexation: {error_reason}")
        if os.path.exists(CACHE_FILE): os.remove(CACHE_FILE)
        sys.exit(1)

if __name__ == "__main__":
    main()
