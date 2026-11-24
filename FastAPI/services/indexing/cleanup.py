import os
from qdrant_client import QdrantClient, models
from services.utils.mlops_config import get_active_embedding_config

# --- CONFIGURATION GLOBALE (Synchronisée avec Upload.py) ---
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME_FALLBACK = os.getenv("COLLECTION_NAME", "Vector_Embeddings")

class Cleanup:
    def __init__(self):
        print(f"🧹 Initialisation du Service de Nettoyage Qdrant sur {QDRANT_URL}...")
        # Ajout d'un timeout pour éviter que le thread Java ne reste bloqué indéfiniment
        try:
            self.client = QdrantClient(url=QDRANT_URL, timeout=10)
            self.config = get_active_embedding_config()
            self.collection_name = self.config.get("qdrant_collection", COLLECTION_NAME_FALLBACK)
        except Exception as e:
            print(f"❌ Erreur critique de connexion Qdrant : {e}")
            raise e

    def _get_all_embedding_collections(self):
        """Récupère toutes les collections liées aux embeddings MLOps."""
        try:
            response = self.client.get_collections()
            collections = [c.name for c in response.collections if "Vector_Embeddings" in c.name or "MLOps" in c.name]
            if self.collection_name not in collections:
                collections.append(self.collection_name)
            return list(set(collections))
        except Exception as e:
            print(f"⚠️ Erreur get_collections: {e}")
            return [self.collection_name]

    def delete_by_mongo_id(self, mongo_id: str):
        """Supprime tous les vecteurs associés à un ID MongoDB spécifique à travers TOUTES les collections."""
        print(f"🗑️ [QDRANT] Tentative de suppression globale pour mongo_file_id: {mongo_id}")

        collections = self._get_all_embedding_collections()
        deleted_any = False

        for coll in collections:
            if not self.client.collection_exists(coll):
                continue
            try:
                self.client.delete(
                    collection_name=coll,
                    points_selector=models.FilterSelector(
                        filter=models.Filter(
                            must=[
                                models.FieldCondition(
                                    key="mongo_file_id",
                                    match=models.MatchValue(value=mongo_id)
                                )
                            ]
                        )
                    ),
                )
                print(f"✅ [QDRANT] Suppression effectuée dans la collection {coll} (si existant)")
                deleted_any = True
            except Exception as e:
                print(f"⚠️ [QDRANT] Skip collection {coll} pour {mongo_id}: {str(e)}")
                
        return deleted_any

    def delete_by_source_path(self, source_path: str):
        """Supprime tous les vecteurs associés à un chemin de fichier à travers TOUTES les collections."""
        print(f"🗑️ [QDRANT] Tentative de suppression globale pour source: {source_path}")
        
        collections = self._get_all_embedding_collections()
        deleted_any = False

        for coll in collections:
            if not self.client.collection_exists(coll):
                continue
            try:
                self.client.delete(
                    collection_name=coll,
                    points_selector=models.FilterSelector(
                        filter=models.Filter(
                            must=[
                                models.FieldCondition(
                                    key="source", 
                                    match=models.MatchValue(value=source_path)
                                )
                            ]
                        )
                    ),
                )
                print(f"✅ [QDRANT] Suppression effectuée dans la collection {coll} pour {source_path}")
                deleted_any = True
            except Exception as e:
                print(f"⚠️ [QDRANT] Skip collection {coll} pour {source_path}: {str(e)}")
                
        return deleted_any

    def get_all_mongo_ids(self):
        """Récupère tous les IDs MongoDB uniques présents dans TOUTES les collections Qdrant."""
        ids = set()
        collections = self._get_all_embedding_collections()
        print(f"🔍 [QDRANT] Recherche des IDs dans les collections: {collections}")
        
        for coll in collections:
            offset = None
            if not self.client.collection_exists(coll):
                continue
                
            while True:
                try:
                    scroll_result = self.client.scroll(
                        collection_name=coll,
                        limit=100,
                        with_payload=True,
                        with_vectors=False,
                        offset=offset
                    )
                    points, next_offset = scroll_result
                    for p in points:
                        if p.payload and "mongo_file_id" in p.payload:
                            ids.add(p.payload["mongo_file_id"])
                    
                    if not next_offset:
                        break
                    offset = next_offset
                except Exception as e:
                    print(f"⚠️ Erreur lors du scroll sur {coll}: {e}")
                    break
            
        print(f"✅ [QDRANT] Total des IDs uniques trouvés : {len(ids)}")
        return list(ids)
