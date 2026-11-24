"""
grid_config.py
--------------
Définit toutes les configurations à tester dans le Grid Search.
Phase 1 : Varier les modèles (hyperparamètres fixés par défaut)
Phase 2 : Varier les hyperparamètres (meilleur modèle de Phase 1)
"""
from itertools import product

# --- CONSTANTES DISPONIBLES ---
TEXT_MODELS = [
    "colbert-ir/colbertv2.0",
    "snowflake/snowflake-arctic-embed-m",
    "BAAI/bge-small-en-v1.5",
    "jinaai/jina-embeddings-v2-base-en",
    "sentence-transformers/all-MiniLM-L6-v2",
]

# LLM réduit à 1 modèle (OpenAI exclusif)
LLM_CONFIGS = [
    {"provider": "OPENAI", "model": "gpt-4o-mini"}
]

VISION_CUDA_MODELS = [
    "vidore/colpali-v1.3",
    "vidore/colpali-v1.2",
    "vidore/colpali-v1.1",
]

VISION_CPU_MODELS = [
    "vidore/colSmol-256M",
    "vidore/colSmol-125M",
    "vidore/colIdefics3-8B-Small",
]

# Hyperparamètres LLM par défaut (Phase 1)
DEFAULT_HYPERPARAMS = {
    "llm_temperature": 0.7,
    "llm_top_p": 1.0,
    "llm_frequency_penalty": 0.0,
    "llm_presence_penalty": 0.0,
}

# Grid des hyperparamètres pour Phase 2 (Optimisation finale)
HYPERPARAM_GRID = {
    "llm_temperature": [0.1, 0.4, 0.7, 1.0, 1.3],
    "llm_top_p": [0.7, 1.0],
    "llm_frequency_penalty": [0.0, 0.5],
    "llm_presence_penalty": [0.0],
}

# Paramètres fixes (ne pas modifier)
FIXED_PARAMS = {
    "llm_max_tokens": 300,
    "text_block_threshold": 15,
    "extraction_method": "pymupdf_blocks",
    "stt_provider": "OPENAI",
    "tts_provider": "OPENAI",
}


def generate_phase1_configs():
    """
    Phase 1 : Varier les modèles avec hyperparamètres par défaut.
    Total : 5 × 2 × 3 × 3 = 90 configurations.
    """
    configs = []
    for idx, (text_m, llm, vcuda, vcpu) in enumerate(
        product(TEXT_MODELS, LLM_CONFIGS, VISION_CUDA_MODELS, VISION_CPU_MODELS)
    ):
        config = {
            "version_name": f"test_p1_{idx:04d}",
            "text_model": text_m,
            "llm_provider": llm["provider"],
            "llm_model": llm["model"],
            "vision_model_cuda": vcuda,
            "vision_model_cpu": vcpu,
            **DEFAULT_HYPERPARAMS,
            **FIXED_PARAMS,
        }
        configs.append(config)
    return configs


def generate_phase2_configs(best_text_model, best_llm_provider, best_llm_model,
                             best_vision_cuda, best_vision_cpu):
    """
    Phase 2 : Varier les hyperparamètres avec le meilleur modèle de Phase 1.
    Total : 3 × 3 × 3 × 3 = 81 configurations.
    """
    configs = []
    keys = list(HYPERPARAM_GRID.keys())
    for idx, values in enumerate(product(*HYPERPARAM_GRID.values())):
        params = dict(zip(keys, values))
        config = {
            "version_name": f"test_p2_{idx:04d}",
            "text_model": best_text_model,
            "llm_provider": best_llm_provider,
            "llm_model": best_llm_model,
            "vision_model_cuda": best_vision_cuda,
            "vision_model_cpu": best_vision_cpu,
            **params,
            **FIXED_PARAMS,
        }
        configs.append(config)
    return configs
