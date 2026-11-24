from qdrant_client import QdrantClient, models

# --- CONFIGURATION ---
QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "radiology_course_smart_hybrid_2"
TEXT_VECTOR_NAME = "colbert_text"
IMAGE_VECTOR_NAME = "colpali_image"

def init_qdrant():
    client = QdrantClient(QDRANT_URL)
    
    if client.collection_exists(COLLECTION_NAME):
        print(f"✅ La collection '{COLLECTION_NAME}' existe déjà.")
        return

    print(f"🔧 Création de la collection '{COLLECTION_NAME}'...")
    
    # Note: On utilise des dimensions standards pour l'initialisation.
    # ColBERT v2 est généralement en 128.
    # ColPali v1.3 / ColSmol est aussi en 128.
    
    client.create_collection(
        COLLECTION_NAME,
        vectors_config={
            TEXT_VECTOR_NAME: models.VectorParams(
                size=128,
                distance=models.Distance.COSINE,
                multivector_config=models.MultiVectorConfig(comparator=models.MultiVectorComparator.MAX_SIM),
            ),
            IMAGE_VECTOR_NAME: models.VectorParams(
                size=128, 
                distance=models.Distance.DOT,
                multivector_config=models.MultiVectorConfig(comparator=models.MultiVectorComparator.MAX_SIM),
                hnsw_config=models.HnswConfigDiff(m=0),
            ),
        },
    )
    print(f"✅ Collection '{COLLECTION_NAME}' créée avec succès.")

if __name__ == "__main__":
    try:
        init_qdrant()
    except Exception as e:
        print(f"❌ Erreur lors de l'initialisation de Qdrant : {e}")
