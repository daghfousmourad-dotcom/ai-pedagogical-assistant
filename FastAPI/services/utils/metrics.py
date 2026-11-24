import os
from prometheus_client import Histogram, Counter, Gauge, CollectorRegistry, multiprocess, REGISTRY

# --- GESTION DU REGISTRE (Multiprocess pour Celery) ---
multiproc_dir = os.getenv('PROMETHEUS_MULTIPROC_DIR')
if multiproc_dir:
    os.makedirs(multiproc_dir, exist_ok=True)

def get_registry():
    if multiproc_dir:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return registry
    # Fallback sur le registre par défaut si on n'est pas en multiprocess (ex: mode Host)
    return REGISTRY

# On définit les métriques sur le registre par défaut (Web) ou spécifique (Worker)
# Pour simplifier, on garde les globales mais on peut les lier à un registre si besoin.
# Ici, prometheus_client utilise REGISTRY par défaut.

# --- MÉTRIQUES D'INDEXATION ---
IA_INDEXING_DURATION = Histogram(
    'ia_indexing_duration_seconds',
    'Durée totale de l\'opération d\'indexation',
    ['method']
)

IA_INDEXING_SIZE_BYTES = Counter(
    'ia_indexing_size_bytes_total',
    'Taille totale des fichiers PDF indexés en octets',
    ['method']
)

IA_PROCESSING_DURATION = Histogram(
    'ia_processing_duration_seconds',
    'Temps pur de traitement IA (inférence ColBERT/ColPali)',
    ['method']
)

# --- MÉTRIQUES LLM/RAG ---
IA_LLM_TTFT = Histogram(
    'ia_llm_ttft_seconds',
    'Temps écoulé avant le premier token généré par le LLM'
)

IA_LLM_TPS = Histogram(
    'ia_llm_tps_tokens_per_second',
    'Nombre de tokens générés par seconde'
)

# --- COMPTEURS ---
IA_INDEXING_SUCCESS = Counter(
    'ia_indexing_success_total',
    'Nombre total d\'indexations terminées avec succès',
    ['method']
)

IA_REQUESTS_RECEIVED_TOTAL = Counter(
    'ia_requests_received_total',
    'Nombre total de requêtes reçues par les workers IA'
)

IA_INDEXING_FAILURE = Counter(
    'ia_indexing_failure_total',
    'Nombre total d\'échecs d\'indexation',
    ['method']
)
