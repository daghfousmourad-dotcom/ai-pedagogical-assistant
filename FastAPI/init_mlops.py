import os
from pymongo import MongoClient

def init_mlops_db():
    print("🔧 Initialisation de la configuration MLOps dans MongoDB...")
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    client = MongoClient(mongo_uri)
    db = client["course_db"]
    collection = db["mlops_versions"]

    # Vérification si une version existe déjà
    if collection.count_documents({}) == 0:
        default_version = {
            "version_name": "v1_colbert_colpali",
            "is_active": True,
            "text_model": "colbert-ir/colbertv2.0",
            "vision_model_cuda": "vidore/colpali-v1.3",
            "vision_model_cpu": "vidore/colSmol-256M",
            "extraction_method": "pymupdf_blocks",
            "qdrant_collection": os.getenv("COLLECTION_NAME", "Vector_Embeddings"),
            "text_block_threshold": 15
        }
        collection.insert_one(default_version)
        print(f"✅ Version par défaut insérée : {default_version['version_name']}")
    else:
        active = collection.find_one({"is_active": True})
        if active:
            print(f"✅ Configuration MLOps existante trouvée. Version active : {active.get('version_name')}")
        else:
            print("⚠️ Aucune version active n'a été trouvée dans la DB.")

if __name__ == "__main__":
    init_mlops_db()
