import os
import sys
import time
import json
from pymongo import MongoClient
from bson import ObjectId
from grid_config import TEXT_MODELS, VISION_CUDA_MODELS
from mongo_manager import MongoManager
from test_runner import TestRunner
from health_monitor import HealthMonitor

# Add FastAPI to path for RAG-service
FASTAPI_PATH = "/Volumes/MonSSD/pfe/test-microservices/FastAPI"
sys.path.append(FASTAPI_PATH)
from services.agents.rag import RAGService

PDF_PATH = "/Volumes/MonSSD/pfe/test-microservices/shared_uploads/Sémiologie radiologie en pathologie digestive 2015.pdf"
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MAPPING_FILE = "mlops_model_mapping.json"

def main():
    print("\n" + "="*50)
    print("🚀 DÉMARRAGE DE LA PHASE 0 : INDEXATION GRANULAIRE")
    print("="*50)

    mongo = MongoManager()
    runner = TestRunner()
    monitor = HealthMonitor()
    rag = RAGService()
    db_client = MongoClient(MONGO_URI)
    db = db_client["course_db"]

    # Initialisation du mapping
    model_mapping = {}
    if os.path.exists(MAPPING_FILE):
        with open(MAPPING_FILE, "r") as f:
            model_mapping = json.load(f)

    configurations = []
    for text_m in TEXT_MODELS:
        for vis_m in VISION_CUDA_MODELS:
            config = {
                "version_name": f"MLOps_Phase0_{text_m.replace('/', '_')}_{vis_m.replace('/', '_')}",
                "text_model": text_m,
                "vision_model_cuda": vis_m,
                "qdrant_collection": f"MLOps_{text_m.replace('/', '_')}_{vis_m.replace('/', '_')}"
            }
            configurations.append(config)

    print(f"📦 {len(configurations)} combinaisons à traiter avec documents MongoDB uniques.")

    for i, config in enumerate(configurations):
        monitor.wait_if_paused()
        
        v_name = config["version_name"]
        print("\n" + "-"*50)
        print(f"🔄 Itération {i+1}/15 : {v_name}")
        print("-" * 50)

        try:
            # 1. Génération du contexte unique via OpenAI
            print(f"🧠 Extraction du contexte spécifique pour ce couple...")
            context, role = rag.analyze_course_context(PDF_PATH)
            
            # 2. Création d'un NOUVEAU document MongoDB pour ce couple
            new_doc = {
                "course_context": context,
                "system_role": role,
                "title": f"[MLOps] {config['text_model']} | {config['vision_model_cuda']}",
                "nom": os.path.basename(PDF_PATH),
                "file_path": PDF_PATH,
                "type": "application/pdf",
                "status": "READY",
                "mlops_tag": "phase0"
            }
            res = db["documents"].insert_one(new_doc)
            mongo_id = str(res.inserted_id)
            print(f"   ✅ Document MongoDB créé (ID: {mongo_id})")

            # 3. Mise à jour du mapping
            model_mapping[v_name] = mongo_id
            with open(MAPPING_FILE, "w") as f:
                json.dump(model_mapping, f, indent=4)

            # 4. Activation de la config MLOps
            # On ajoute le mongo_id à la config pour que trigger_indexing puisse le passer à l'indexer
            config["mongo_id"] = mongo_id
            mongo.create_version(config)
            mongo.activate_version(v_name)
            
            # 5. Lancement de l'indexation
            idx_res = runner.run_indexing()
            if idx_res.get("status") == "error":
                print(f"❌ Erreur Indexation : {idx_res['error']}")
                sys.exit(1)
            
            print(f"✅ Indexation terminée pour {v_name}")

        except Exception as e:
            print(f"❌ CRASH Itération : {e}")
            sys.exit(1)
        finally:
            mongo.restore_default()
            
        print("⏳ Pause de 5 secondes...")
        time.sleep(5)
        
    print("\n" + "="*50)
    print("🏁 TOUS LES INDEX ET DOCUMENTS SONT PRÊTS.")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
