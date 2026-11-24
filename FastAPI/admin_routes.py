import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pymongo import MongoClient

# Nouveau routeur exclusif pour l'administration MLOps
router = APIRouter(prefix="/api/admin/mlops", tags=["MLOps Admin"])

# Connexion MongoDB
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)
db = client["course_db"]
collection = db["mlops_versions"]

class EmbeddingVersionItem(BaseModel):
    version_name: str
    text_model: str = "colbert-ir/colbertv2.0"
    vision_model_cuda: str = "vidore/colpali-v1.3"
    vision_model_cpu: str = "vidore/colSmol-256M"
    extraction_method: str = "pymupdf_blocks"
    qdrant_collection: str = "Vector_Embeddings"
    text_block_threshold: int = 15

class LLMConfigItem(BaseModel):
    config_name: str
    llm_provider: str = "OPENAI" # "OPENAI" | "OLLAMA"
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 500
    llm_top_p: float = 1.0
    llm_frequency_penalty: float = 0.0
    llm_presence_penalty: float = 0.0
    stt_provider: str = "OPENAI"
    tts_provider: str = "OPENAI"

@router.get("/versions")
def get_versions():
    """Récupère l'historique complet des versions configurées."""
    try:
        versions = list(collection.find({}, {"_id": 0}))
        return {"status": "success", "versions": versions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/active")
def get_active_version():
    """Récupère uniquement la version actuellement active."""
    try:
        active_v = collection.find_one({"is_active": True}, {"_id": 0})
        if not active_v:
            return {"status": "error", "message": "Aucune version active trouvée."}
        return {"status": "success", "version": active_v}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from services.utils.naming import get_safe_collection_name

@router.post("/versions")
def create_version(version: EmbeddingVersionItem):
    """Crée une nouvelle configuration d'embedding réutilisable."""
    # 1. Vérification de l'unicité du NOM
    if collection.find_one({"version_name": version.version_name}):
        raise HTTPException(status_code=400, detail="Version name already exists")
    
    # 2. GARDE-FOU: Vérification de l'unicité des PARAMÈTRES
    # On cherche si une config identique existe déjà avec un autre nom
    duplicate = collection.find_one({
        "text_model": version.text_model,
        "vision_model_cuda": version.vision_model_cuda
    })
    
    if duplicate:
        raise HTTPException(
            status_code=400, 
            detail=f"Une configuration identique existe déjà sous le nom '{duplicate['version_name']}'. "
                   f"Inutile de créer une version redondante."
        )

    version_dict = version.dict()
    
    # CALCUL AUTOMATIQUE DE LA COLLECTION (Cohérence Totale)
    # On écrase la valeur fournie par l'utilisateur par une valeur déterministe incluant le nom de version
    auto_collection = get_safe_collection_name(version.text_model, version.vision_model_cuda, version.version_name)
    version_dict["qdrant_collection"] = auto_collection
    
    version_dict["is_active"] = False # Désactivé par défaut à la création
    collection.insert_one(version_dict)
    
    if "_id" in version_dict:
        del version_dict["_id"]
        
    return {"status": "success", "version": version_dict, "auto_assigned_collection": auto_collection}

@router.put("/versions/{version_name}/activate")
def activate_version(version_name: str):
    """Bascule "à chaud" la version active qui sera utilisée par Celery et FastAPI."""
    if not collection.find_one({"version_name": version_name}):
        raise HTTPException(status_code=404, detail="Version not found")
        
    # Désactiver toutes les versions existantes
    collection.update_many({}, {"$set": {"is_active": False}})
    
    # Activer uniquement la nouvelle version
    collection.update_one({"version_name": version_name}, {"$set": {"is_active": True}})
    
    # --- HOT-SWAP ---
    # On force la réinitialisation des singletons FastAPI pour qu'ils rechargent la config
    try:
        from api.dependencies import reset_all_ai_services
        reset_all_ai_services()
    except Exception as e:
        print(f"⚠️ Erreur lors du Hot-Swap : {e}")
    
    return {"status": "success", "message": f"Version {version_name} is now active for all indexing and RAG tasks (Hot-Swap complete)."}

@router.put("/versions/{version_name}/default")
def set_default_version(version_name: str):
    """Marque une configuration comme étant celle par 'Défaut'."""
    if not collection.find_one({"version_name": version_name}):
        raise HTTPException(status_code=404, detail="Version not found")
    
    # On enlève le flag default de tous
    collection.update_many({}, {"$set": {"is_default": False}})
    # On l'ajoute à la cible
    collection.update_one({"version_name": version_name}, {"$set": {"is_default": True}})
    
    return {"status": "success", "message": f"Configuration {version_name} définie comme configuration par défaut."}

@router.post("/default/activate")
def activate_default_version():
    """Restaure et active la version marquée par défaut."""
    default_v = collection.find_one({"is_default": True})
    if not default_v:
        # Fallback si rien n'est marqué : chercher par nom ou prendre la première
        default_v = collection.find_one({"version_name": "default"}) or collection.find_one()
        
    if not default_v:
        raise HTTPException(status_code=404, detail="Aucune configuration par défaut trouvée.")
    
    version_name = default_v["version_name"]
    collection.update_many({}, {"$set": {"is_active": False}})
    collection.update_one({"version_name": version_name}, {"$set": {"is_active": True}})
    
    return {"status": "success", "message": f"Configuration par défaut ({version_name}) restaurée.", "version_name": version_name}

@router.post("/system/restart")
def restart_ai_services():
    """Redémarre uniquement les services IA (API + Worker)."""
    import subprocess
    try:
        # Redémarre uniquement les services IA
        subprocess.Popen(["sh", "-c", "sleep 2 && docker restart fastapi-web fastapi-celery-worker"])
        return {"status": "success", "message": "AI Services restart signal sent."}
    except Exception as e:
        return {"status": "error", "message": f"Détail: {str(e)}"}

@router.post("/system/restart-full")
def restart_system_full():
    """Redémarre l'intégralité du système Docker (Bases de données + Services)."""
    import subprocess
    try:
        # Redémarrage complet
        subprocess.Popen(["sh", "-c", "sleep 2 && docker restart radiology-mongodb radiology-qdrant radiology-redis fastapi-web fastapi-celery-worker"])
        return {"status": "success", "message": "Full System restart signal sent. Everything will reboot."}
    except Exception as e:
        return {"status": "error", "message": f"Détail: {str(e)}"}

@router.delete("/versions/{version_name}")
def delete_version(version_name: str):
    """Supprime une configuration si elle n'est pas active."""
    version = collection.find_one({"version_name": version_name})
    if not version:
        raise HTTPException(status_code=404, detail="Version non trouvée.")
    
    if version.get("is_active"):
        raise HTTPException(status_code=400, detail="Impossible de supprimer une configuration active.")
    
    collection.delete_one({"version_name": version_name})
    return {"status": "success", "message": f"Configuration {version_name} supprimée avec succès."}

# --- GESTION DES CONFIGS LLM ---

llm_collection = db["mlops_llm_configs"]

@router.get("/llm-configs")
def get_llm_configs():
    try:
        configs = list(llm_collection.find({}, {"_id": 0}))
        return {"status": "success", "configs": configs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/llm-configs/active")
def get_active_llm_config():
    try:
        active_c = llm_collection.find_one({"is_active": True}, {"_id": 0})
        if not active_c:
            return {"status": "error", "message": "Aucune config LLM active."}
        return {"status": "success", "config": active_c}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/llm-configs")
def create_llm_config(config: LLMConfigItem):
    if llm_collection.find_one({"config_name": config.config_name}):
        raise HTTPException(status_code=400, detail="Config name already exists")
    
    duplicate = llm_collection.find_one({
        "llm_provider": config.llm_provider,
        "llm_model": config.llm_model,
        "llm_temperature": config.llm_temperature
    })
    
    if duplicate:
        raise HTTPException(status_code=400, detail=f"Configuration similaire existe déjà: {duplicate['config_name']}")

    config_dict = config.dict()
    config_dict["is_active"] = False
    llm_collection.insert_one(config_dict)
    
    if "_id" in config_dict:
        del config_dict["_id"]
        
    return {"status": "success", "config": config_dict}

@router.put("/llm-configs/{config_name}/activate")
def activate_llm_config(config_name: str):
    if not llm_collection.find_one({"config_name": config_name}):
        raise HTTPException(status_code=404, detail="Config not found")
        
    llm_collection.update_many({}, {"$set": {"is_active": False}})
    llm_collection.update_one({"config_name": config_name}, {"$set": {"is_active": True}})
    
    try:
        from api.dependencies import reset_all_ai_services
        reset_all_ai_services()
    except Exception as e:
        print(f"⚠️ Erreur Hot-Swap LLM : {e}")
    
    return {"status": "success", "message": f"Config LLM {config_name} activée."}

@router.put("/llm-configs/{config_name}/default")
def set_default_llm_config(config_name: str):
    if not llm_collection.find_one({"config_name": config_name}):
        raise HTTPException(status_code=404, detail="Config not found")
    
    llm_collection.update_many({}, {"$set": {"is_default": False}})
    llm_collection.update_one({"config_name": config_name}, {"$set": {"is_default": True}})
    return {"status": "success"}

@router.post("/llm-configs/default/activate")
def activate_default_llm_config():
    default_c = llm_collection.find_one({"is_default": True})
    if not default_c:
        default_c = llm_collection.find_one({"config_name": "default"}) or llm_collection.find_one()
        
    if not default_c:
        raise HTTPException(status_code=404, detail="Aucune config LLM trouvée.")
    
    config_name = default_c["config_name"]
    llm_collection.update_many({}, {"$set": {"is_active": False}})
    llm_collection.update_one({"config_name": config_name}, {"$set": {"is_active": True}})
    return {"status": "success", "config_name": config_name}

@router.delete("/llm-configs/{config_name}")
def delete_llm_config(config_name: str):
    config = llm_collection.find_one({"config_name": config_name})
    if not config:
        raise HTTPException(status_code=404, detail="Config non trouvée.")
    if config.get("is_active"):
        raise HTTPException(status_code=400, detail="Impossible de supprimer une config active.")
    llm_collection.delete_one({"config_name": config_name})
    return {"status": "success"}

# --- EXPLORATEUR MONGODB ---

@router.get("/mongo/collections")
def list_collections():
    """Liste toutes les collections de la base de données course_db."""
    try:
        collections = db.list_collection_names()
        return {"status": "success", "collections": collections}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/mongo/collections/{collection_name}")
def get_collection_data(collection_name: str, limit: int = 50):
    """Récupère les documents d'une collection spécifique."""
    try:
        if collection_name not in db.list_collection_names():
             raise HTTPException(status_code=404, detail="Collection not found")
        
        # On limite à 50 documents par défaut pour les perfs
        cursor = db[collection_name].find().limit(limit)
        docs = []
        for doc in cursor:
            # Conversion de l'ObjectId en string pour le JSON
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])
            docs.append(doc)
            
        return {"status": "success", "data": docs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
