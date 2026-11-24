# ==============================================================================
# PROPRIÉTÉ DE AI ASSISTANT - (c) 2024-2026 Mourad Daghfous
# Système d'Interaction Vocale Intelligent pour l'Éducation
# ------------------------------------------------------------------------------
# Ce fichier est confidentiel et protégé par les lois sur la propriété 
# intellectuelle. Toute diffusion non autorisée est passible de poursuites.
# ==============================================================================
import os

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient
import gc
import torch

# Charger les variables du fichier .env (injecté par Docker ou présent localement)
load_dotenv()

# ============================================================
# 🔴 IMPORTANT: Ces variables DOIVENT être définies en PREMIER,
#    avant tout import de torch/transformers/huggingface,
#    pour rediriger TOUS les caches vers le SSD externe.
# ============================================================
# Chemin du cache IA (priorité à l'env injecté par Docker)
_MODEL_CACHE = os.getenv("AI_MODELS_CACHE_PATH", "/Volumes/MonSSD/pfe/ai_models_cache")
os.environ["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"
os.environ["HF_HOME"] = _MODEL_CACHE                    # Cache principal HuggingFace
os.environ["HUGGINGFACE_HUB_CACHE"] = os.path.join(_MODEL_CACHE, "hub")  # Hub de modèles
os.environ["TRANSFORMERS_CACHE"] = _MODEL_CACHE         # Modèles Transformers
os.environ["HF_DATASETS_CACHE"] = os.path.join(_MODEL_CACHE, "datasets")  # Datasets HF
os.environ["TORCH_HOME"] = os.path.join(_MODEL_CACHE, "torch")  # Cache PyTorch
os.environ["XDG_CACHE_HOME"] = _MODEL_CACHE             # Cache XDG global (fallback)
import asyncio
from celery import Celery
from services.indexing.upload import Upload
from services.indexing.upload_advanced import UploadAdvanced

# Configuration Celery
# Détection dynamique de l'hôte Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("archiviste_tasks", broker=REDIS_URL, backend=REDIS_URL)

# Instances des indexeurs (chargées une seule fois par le worker)
indexer = None
indexer_advanced = None
rag_service = None

def get_indexer():
    global indexer
    if indexer is None:
        indexer = Upload()
    return indexer

def get_indexer_advanced():
    global indexer_advanced
    if indexer_advanced is None:
        indexer_advanced = UploadAdvanced()
    return indexer_advanced

def get_rag_service():
    global rag_service
    if rag_service is None:
        from services.agents.rag import RAGService
        rag_service = RAGService()
    return rag_service

def purge_memory():
    """Libère agressivement la mémoire vive et MPS après une tâche lourde."""
    global indexer, indexer_advanced, rag_service
    print("♻️ Purge de la mémoire en cours...")
    
    # 1. Suppression des instances lourdes
    indexer = None
    indexer_advanced = None
    rag_service = None
    
    # 2. Nettoyage Python
    gc.collect()
    
    # 3. Nettoyage MPS (Apple Silicon)
    if torch.backends.mps.is_available():
        torch.mps.empty_cache()
        print("✅ Cache MPS vidé.")
    
    print("✅ Mémoire libérée. Le prochain document demandera un rechargement complet.")


async def background_analyze_logic(pdf_path, mongo_id):
    """
    Analyse le contexte du cours via l'IA et met à jour les métadonnées
    dans le course-service (Java) et MongoDB.
    """
    try:
        import httpx
        from pymongo import MongoClient
        from bson import ObjectId

        print(f"🧠 [Celery] Début de l'analyse automatique pour le document : {mongo_id}")

        # 1. Récupération du service RAG
        rag = get_rag_service()

        # 2. CRITIQUE : Charger la config MLOps liée à ce document précis
        # Cela initialise 'rag.config' et évite l'erreur 'NoneType'
        try:
            rag._prepare_context_for_document(mongo_id)
            print(f"⚙️ [Celery] Configuration '{rag.config.get('version_name')}' chargée pour l'analyse.")
        except Exception as e:
            print(f"⚠️ [Celery] Impossible de charger la config spécifique, utilisation de la config par défaut : {e}")

        # 3. Analyse IA (Domaine et Rôle Système)
        # On utilise to_thread car l'analyse PDF/OpenAI est bloquante
        context, role = await asyncio.to_thread(rag.analyze_course_context, pdf_path)
        print(f"✅ [Celery] Contexte détecté : {context}")

        # 4. Connexion MongoDB pour récupérer le course_id
        MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")

        with MongoClient(MONGO_URI) as client:
            db = client["course_db"]
            doc_meta = db["documents"].find_one({"_id": ObjectId(mongo_id)})

            if not doc_meta:
                print(f"❌ [Celery] Erreur : Document {mongo_id} introuvable.")
                return

            course_id = doc_meta.get("course_id")
            if not course_id:
                print(f"❌ [Celery] Erreur : course_id manquant pour le document {mongo_id}.")
                return

        # 5. Préparation du Payload pour le service Java
        # On utilise rag.config qui est maintenant garanti d'exister
        payload = {
            "courseContext": context,
            "systemRole": role,
            "mlops_version": rag.config.get("version_name", "Inconnue"),
            "text_model": rag.config.get("text_model", "standard"),
            "vision_model": rag.config.get("vision_model", "vidore/colpali-v1.3"),
            "qdrant_collection": rag.config.get("qdrant_collection", "Vector_Embeddings")
        }

        # 6. Mise à jour via le Course-Service (Java/Spring Boot)
        COURSE_SERVICE_URL = os.getenv("COURSE_SERVICE_URL", "http://localhost:8082")
        DOC_METADATA_URL = f"{COURSE_SERVICE_URL}/api/courses/{course_id}/documents/{mongo_id}/metadata"

        async with httpx.AsyncClient(timeout=10.0) as httpx_client:
            resp = await httpx_client.patch(DOC_METADATA_URL, json=payload)

            if resp.status_code == 200:
                print(f"🚀 [Celery] Métadonnées synchronisées avec le service Java.")
            else:
                print(f"⚠️ [Celery] Échec synchro Java (Status {resp.status_code}): {resp.text}")

    except Exception as e:
        print(f"❌ [Celery] Erreur critique dans background_analyze_logic : {str(e)}")

import os
import time
from prometheus_client import start_http_server
from services.utils.metrics import (
    IA_INDEXING_DURATION, 
    IA_INDEXING_SIZE_BYTES, 
    IA_INDEXING_SUCCESS, 
    IA_INDEXING_FAILURE,
    IA_REQUESTS_RECEIVED_TOTAL
)

# Démarrage du serveur de métriques pour Prometheus sur un port dédié (ex: 8000)
try:
    from services.utils.metrics import get_registry
    from prometheus_client import start_http_server, make_wsgi_app
    
    # Création du dossier temporaire pour les métriques multiprocess
    os.makedirs(os.getenv('PROMETHEUS_MULTIPROC_DIR', '/tmp/metrics'), exist_ok=True)
    
    # On démarre le serveur avec le registre multiprocess
    registry = get_registry()
    start_http_server(8000, registry=registry)
    print("📈 Serveur de métriques IA (Worker Multiprocess) démarré sur le port 8000")
except Exception as e:
    print(f"⚠️ Impossible de démarrer le serveur de métriques : {e}")

# ... (Previous imports and config)

@celery_app.task(name="tasks.index_pdf", bind=True)
def index_pdf_task(self, pdf_path, mongo_id):
    start_time = time.time()
    method = "standard"
    IA_REQUESTS_RECEIVED_TOTAL.inc()
    print(f"🚀 [Celery] Tâche reçue : Indexation {method} pour {pdf_path}")
    try:
        # Mesure de la taille
        file_size = os.path.getsize(pdf_path)
        IA_INDEXING_SIZE_BYTES.labels(method=method).inc(file_size)
        
        idx = get_indexer()

        # Callback branchant les prints existants sur Redis via update_state
        def progress_callback(current, total):
            percent = int((current / total) * 100)
            print(f"📊 [Progress] Page {current}/{total} ({percent}%)", flush=True)
            self.update_state(
                state='PROGRESS',
                meta={'current': current, 'total': total, 'percent': percent}
            )

        idx.process_pdf(pdf_path, mongo_id=mongo_id, progress_callback=progress_callback)
        
        # Timing
        duration = time.time() - start_time
        IA_INDEXING_DURATION.labels(method=method).observe(duration)
        IA_INDEXING_SUCCESS.labels(method=method).inc()
        
        # Analyse de contexte après indexation
        asyncio.run(background_analyze_logic(pdf_path, mongo_id))
        
        # PURGE SÉCURISÉE DES MODÈLES LOURDS (PRESERVE HARDWARE)
        purge_memory()
        
        return f"Successfully indexed {pdf_path} (Size: {file_size} bytes, Duration: {round(duration, 2)}s)"
    except Exception as e:
        IA_INDEXING_FAILURE.labels(method=method).inc()
        print(f"❌ [Celery] Erreur tâche indexation : {e}")
        purge_memory() # Purge même en cas d'erreur
        raise e


def get_fresh_indexer_advanced():
    """
    Force la création d'une nouvelle instance.
    L'init de UploadAdvanced appellera get_active_embedding_config()
    qui cherchera le document avec is_active: true.
    """
    from services.indexing.upload_advanced import UploadAdvanced
    return UploadAdvanced()


@celery_app.task(name="tasks.index_pdf_advanced", bind=True)
def index_pdf_advanced_task(self, pdf_path, mongo_id):
    start_time = time.time()
    method = "advanced"
    IA_REQUESTS_RECEIVED_TOTAL.inc()

    print(f"🚀 [Celery] Nouvelle tâche reçue. Lecture de la config active dans MongoDB...")

    try:
        # 1. Mesure de la taille du fichier
        file_size = os.path.getsize(pdf_path)
        IA_INDEXING_SIZE_BYTES.labels(method=method).inc(file_size)

        # 2. Instanciation fraîche (récupère la config 'is_active: True' actuelle)
        idx = get_fresh_indexer_advanced()

        mlops_config_id = idx.mlops_config.get("_id")
        version_name = idx.mlops_config.get("version_name")
        print(f"⚙️ Utilisation de la version MLOps : {version_name} (ID: {mlops_config_id})")

        # Callback branchant les prints existants sur Redis via update_state
        def progress_callback(current, total):
            percent = int((current / total) * 100)
            print(f"📊 [Progress] Page {current}/{total} ({percent}%)", flush=True)
            self.update_state(
                state='PROGRESS',
                meta={'current': current, 'total': total, 'percent': percent}
            )

        # 3. Lancement de l'indexation (Vecteurs vers Qdrant)
        idx.process_pdf(pdf_path, mongo_id=mongo_id, progress_callback=progress_callback)

        # 4. Enregistrement de l'ID de version dans le document MongoDB
        # On ouvre une connexion rapide pour sceller la version
        mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")

        with MongoClient(mongo_uri) as client:
            db = client["course_db"]
            # On met à jour le document avec l'ID de la version MLOps
            db["documents"].update_one(
                {"_id": ObjectId(mongo_id)},
                {"$set": {
                    "mlops_version_id": mlops_config_id,
                    "indexing_method": "advanced",
                    "status": "READY"  # On s'assure que le status est à jour
                }}
            )

        print(f"✅ [MongoDB] Document {mongo_id} lié à la version MLOps {mlops_config_id}")

        # 5. Métriques et Analyse de contexte
        duration = time.time() - start_time
        IA_INDEXING_DURATION.labels(method=method).observe(duration)
        IA_INDEXING_SUCCESS.labels(method=method).inc()

        asyncio.run(background_analyze_logic(pdf_path, mongo_id))

        # PURGE SÉCURISÉE DES MODÈLES LOURDS (PRESERVE HARDWARE)
        purge_memory()

        return f"Successfully indexed with {version_name} in {round(duration, 2)}s"

    except Exception as e:
        IA_INDEXING_FAILURE.labels(method=method).inc()
        print(f"❌ [Celery] Erreur lors de l'indexation avancée : {e}")
        
        # Purge même en cas d'erreur
        purge_memory()

        # En cas d'erreur, on peut marquer le document comme en échec
        try:
            with MongoClient(mongo_uri) as client:
                client["course_db"]["documents"].update_one(
                    {"_id": ObjectId(mongo_id)},
                    {"$set": {"status": "FAILED", "error_log": str(e)}}
                )
        except:
            pass
        raise e
