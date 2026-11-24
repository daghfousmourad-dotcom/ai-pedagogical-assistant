import os
import redis.asyncio as aioredis
import api.dependencies_state as ds # Pour garder la state

from services.indexing.upload import Upload
from services.indexing.upload_advanced import UploadAdvanced
from services.indexing.cleanup import Cleanup
from services.core.navigator import SmartCourseNavigator
from services.agents.rag import RAGService
from services.core.orchestrator import OrchestratorService
from services.agents.image_clarifier import ImageClarifierAgent
from services.agents.voice_utils import VoiceAgentUtils
from services.utils.mlops_config import get_active_llm_config

def get_indexer():
    if ds.indexer is None:
        ds.indexer = Upload()
    return ds.indexer

def get_indexer_advanced():
    if ds.indexer_advanced is None:
        ds.indexer_advanced = UploadAdvanced()
    return ds.indexer_advanced

def get_cleanup():
    if ds.cleanup_service is None:
        ds.cleanup_service = Cleanup()
    return ds.cleanup_service

def get_navigator():
    if ds.navigator is None:
        ds.navigator = SmartCourseNavigator()
    return ds.navigator

def get_rag_service():
    if ds.rag_service is None:
        llm_cfg = get_active_llm_config()
        provider = llm_cfg.get("llm_provider", os.getenv("LLM_PROVIDER", "OLLAMA"))
        if provider == "OLLAMA":
            from OllamaService.ollama_rag_service import OllamaRAGService
            ds.rag_service = OllamaRAGService()
        else:
            ds.rag_service = RAGService()
    return ds.rag_service

def get_voice_agent():
    if ds.voice_agent is None:
        llm_cfg = get_active_llm_config()
        provider = llm_cfg.get("llm_provider", os.getenv("LLM_PROVIDER", "OLLAMA"))
        if provider == "OLLAMA":
            from OllamaService.ollama_voice_utils import OllamaVoiceUtils
            ds.voice_agent = OllamaVoiceUtils()
        else:
            ds.voice_agent = VoiceAgentUtils()
    return ds.voice_agent

def get_clarifier():
    if ds.clarifier_agent is None:
        # ImageClarifierAgent prend désormais en charge les modèles locaux Ollama nativement
        ds.clarifier_agent = ImageClarifierAgent()
    return ds.clarifier_agent

def get_orchestrator():
    if ds.orchestrator is None:
        ds.orchestrator = OrchestratorService(
            get_navigator(), 
            get_voice_agent(), 
            get_rag_service(), 
            get_clarifier(),
            redis_client=ds.redis_client
        )
    return ds.orchestrator

def reset_all_ai_services():
    """Purge tous les singletons en mémoire pour forcer le rechargement de la config MLOps."""
    print("♻️  HOT-SWAP : Réinitialisation des services IA en cours...")
    ds.indexer = None
    ds.indexer_advanced = None
    ds.cleanup_service = None
    ds.navigator = None
    ds.rag_service = None
    ds.voice_agent = None
    ds.clarifier_agent = None
    ds.orchestrator = None
    print("✅ HOT-SWAP : Tous les services (y compris Navigator & Cleanup) ont été purgés. Ils seront rechargés au prochain appel.")
