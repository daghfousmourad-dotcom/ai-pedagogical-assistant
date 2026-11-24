import os
import sys
import time
from pymongo import MongoClient
from qdrant_client import QdrantClient
from bson import ObjectId

# Setup environment to import FastAPI modules correctly
FASTAPI_PATH = "/Volumes/MonSSD/pfe/test-microservices/FastAPI"
sys.path.append(FASTAPI_PATH)

from dotenv import load_dotenv
load_dotenv("/Volumes/MonSSD/pfe/test-microservices/.env")

from services.agents.rag import RAGService

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
MONGO_URI = "mongodb://localhost:27017" # Assuming we run this from Mac
MONGO_ID = "69b7f59cfd94fa75413eeef3"
PDF_PATH = "/Volumes/MonSSD/pfe/test-microservices/shared_uploads/Sémiologie radiologie en pathologie digestive 2015.pdf"

def clean_qdrant():
    print(f"🧹 Connexion à Qdrant ({QDRANT_URL}) pour nettoyage...")
    try:
        client = QdrantClient(QDRANT_URL, timeout=30)
        collections = client.get_collections().collections
        count = 0
        for collection in collections:
            if collection.name.startswith("MLOps_"):
                print(f"   🗑️ Suppression de la collection : {collection.name}")
                client.delete_collection(collection.name)
                count += 1
        print(f"✅ Nettoyage Qdrant terminé. {count} collections supprimées.")
    except Exception as e:
        print(f"❌ Erreur lors du nettoyage Qdrant : {e}")
        sys.exit(1)

def init_mongodb():
    print(f"🧠 Analyse du contexte du document avec OpenAI...")
    try:
        rag = RAGService()
        context, role = rag.analyze_course_context(PDF_PATH)
        print(f"   🎯 Contexte détecté : {context}")
        print(f"   🎭 Rôle système attribué : {role}")

        print(f"💾 Sauvegarde dans MongoDB (ID: {MONGO_ID})...")
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping') # Validate connection
        db = client["course_db"]
        
        # Upsert the MLOps document
        result = db["documents"].update_one(
            {"_id": ObjectId(MONGO_ID)},
            {
                "$set": {
                    "course_context": context,
                    "system_role": role,
                    "title": "Document de Test MLOps",
                    "file_path": PDF_PATH,
                    "type": "application/pdf"
                }
            },
            upsert=True
        )
        if result.upserted_id:
            print("   ✅ Document créé dans MongoDB.")
        else:
            print("   ✅ Document mis à jour dans MongoDB.")
            
    except Exception as e:
        print(f"❌ Erreur lors de l'initialisation MongoDB/OpenAI : {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("\n" + "="*50)
    print("🚀 DÉMARRAGE DE LA PHASE 0 : INITIALISATION DE L'ENVIRONNEMENT")
    print("="*50)
    clean_qdrant()
    init_mongodb()
    print("="*50)
    print("🏁 INITIALISATION TERMINÉE AVEC SUCCÈS.")
    print("="*50 + "\n")
