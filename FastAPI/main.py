# ==============================================================================
# PROPRIÉTÉ DE AI ASSISTANT - (c) 2024-2026 Mourad Daghfous
# Système d'Interaction Vocale Intelligent pour l'Éducation
# ------------------------------------------------------------------------------
# Ce fichier est confidentiel et protégé par les lois sur la propriété 
# intellectuelle. Toute diffusion non autorisée est passible de poursuites.
# ==============================================================================
import os
os.environ["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn
import redis.asyncio as aioredis
from contextlib import asynccontextmanager

import api.dependencies_state as ds
from admin_routes import router as admin_router
from api.routes.indexing import router as indexing_router
from api.routes.multimedia import router as multimedia_router
from api.routes.orchestration import router as orchestration_router
from api.routes.realtime import router as realtime_router

celery_process = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global celery_process

    # Ordre de test : 1. Variable d'env / 2. Docker Network / 3. Localhost
    possible_urls = [
        os.getenv("REDIS_URL"),  # Priorité à l'environnement
        "redis://redis:6379/0",  # Nom du service dans Docker
        "redis://localhost:6379/0"  # Accès depuis ton Mac (MPS)
    ]

    ds.redis_client = None
    for url in filter(None, possible_urls):
        try:
            print(f"🔍 Tentative de connexion Redis : {url}")
            client = await aioredis.from_url(url, encoding="utf-8", decode_responses=True)
            await asyncio.wait_for(client.ping(), timeout=2.0)  # Timeout rapide
            ds.redis_client = client
            print(f"✅ Redis connecté avec succès sur {url}")
            break  # On a trouvé une connexion, on arrête de chercher
        except (Exception, asyncio.TimeoutError) as e:
            print(f"❌ Échec sur {url}")
            continue

    if not ds.redis_client:
        print("⚠️ Aucun serveur Redis trouvé. Fallback RAM actif.")
    
    # Purge automatique des fichiers audio temporaires obsolètes (> 24h)
    try:
        from services.agents.voice_utils import VoiceAgentUtils
        VoiceAgentUtils.cleanup_expired_audio(max_age_hours=24)
    except Exception as e:
        print(f"⚠️ Erreur lors du nettoyage audio au démarrage : {e}")

    yield
    
    if celery_process:
        print("🛑 Arrêt du Worker Celery...")
        celery_process.terminate()
        celery_process.wait()
        print("✅ Worker Celery arrêté.")
    
    if ds.redis_client:
        await ds.redis_client.close()
        print("🛑 Redis fermé.")

app = FastAPI(title="RadioIA RAG Service", lifespan=lifespan)

from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app)

from fastapi.responses import Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from services.utils.metrics import get_registry

@app.get("/metrics", include_in_schema=False)
def metrics():
    registry = get_registry()
    data = generate_latest(registry)
    return Response(data, media_type=CONTENT_TYPE_LATEST)

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static Files
app.mount("/static/uploads", StaticFiles(directory="uploads"), name="static")

# Inclusion des routeurs
app.include_router(admin_router)
app.include_router(indexing_router)
app.include_router(multimedia_router)

app.include_router(orchestration_router)
app.include_router(realtime_router)

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=5005,
        reload=False,
        ws="websockets",
        http="h11"
    )