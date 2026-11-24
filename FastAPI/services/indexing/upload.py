# ==============================================================================
# PROPRIÉTÉ DE AI ASSISTANT - (c) 2024-2026 Mourad Daghfous
# Système d'Interaction Vocale Intelligent pour l'Éducation
# ------------------------------------------------------------------------------
# Ce fichier est confidentiel et protégé par les lois sur la propriété 
# intellectuelle. Toute diffusion non autorisée est passible de poursuites.
# ==============================================================================
# ==============================================================================
# PROPRIÉTÉ DE AI ASSISTANT - (c) 2024-2026 Mourad Daghfous
# Système d'Interaction Vocale Intelligent pour l'Éducation
# ------------------------------------------------------------------------------
# Ce fichier est confidentiel et protégé par les lois sur la propriété 
# intellectuelle. Toute diffusion non autorisée est passible de poursuites.
# ==============================================================================
from linecache import clearcache

import fitz  # PyMuPDF
import torch
import uuid
import os
import sys
from PIL import Image
from qdrant_client import QdrantClient, models
from fastembed import LateInteractionTextEmbedding, TextEmbedding
from colpali_engine.models import ColPaliProcessor, ColPali, ColIdefics3Processor, ColIdefics3
from transformers import BlipProcessor, BlipForConditionalGeneration, AutoProcessor, AutoModelForVision2Seq
from sentence_transformers import SentenceTransformer
import google.generativeai as genai
from services.utils.mlops_config import get_active_embedding_config

# --- CONFIGURATION GLOBALE ---
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "Vector_Embeddings")
TEXT_VECTOR_NAME = "colbert_text"
IMAGE_VECTOR_NAME = "colpali_image"

# Chemin vers le cache des modèles (optimisé pour Docker)
CACHE_DIR = os.getenv("AI_MODELS_CACHE_PATH", "/Volumes/MonSSD/pfe/ai_models_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

class Upload:
    def __init__(self, specific_config=None):
        """ Initialisation de l'agent.
        :param specific_config: (dict) Configuration MLOps récupérée au préalable.
         Si None, récupère la config active par défaut.  """
        # --- LOGIQUE DE PRIORITÉ MLOps ---
        if specific_config:
            self.mlops_config = specific_config
            print(
                f"🎯 Utilisation d'une configuration MLOps SPÉCIFIQUE (Version: {self.mlops_config.get('version_name', 'unknown')})")
        else:
            self.mlops_config = get_active_embedding_config()
            print(
                f"🚀 Initialisation via configuration ACTIVE (Version: {self.mlops_config.get('version_name', 'default')})...")

        # Définition de la collection cible
        self.collection_name = self.mlops_config.get("qdrant_collection", os.getenv("COLLECTION_NAME", "Vector_Embeddings"))

        # 1. Connexion Qdrant (Augmentation du timeout à 120s pour les gros documents)
        self.client = QdrantClient(QDRANT_URL, timeout=120)
        # 2. Chargement du modèle TEXTE (Factory)
        text_model_name = self.mlops_config.get("text_model", "colbert-ir/colbertv2.0")
        self.is_colbert = "colbert" in text_model_name.lower()
        self.is_gemini_text = "gemini" in text_model_name.lower()
        self.is_qwen_text = "qwen3" in text_model_name.lower()
        self.text_vector_name = "colbert_text" if self.is_colbert else "text"
        
        print(f"Loading Text Model ({text_model_name}) from {CACHE_DIR}...")
        if self.is_gemini_text:
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
            self.text_model = "GEMINI_API"
        elif self.is_qwen_text:
            self.text_model = SentenceTransformer(text_model_name.replace("-Int4", ""), cache_folder=CACHE_DIR)
        elif self.is_colbert:
            self.text_model = LateInteractionTextEmbedding(
                model_name=text_model_name,
                cache_dir=os.path.join(CACHE_DIR, "fastembed")
            )
        else:
            self.text_model = TextEmbedding(
                model_name=text_model_name,
                cache_dir=os.path.join(CACHE_DIR, "fastembed")
            )

        # 3. Chargement du modèle IMAGE
        if torch.cuda.is_available():
            self.device = "cuda"
        elif torch.backends.mps.is_available():
            self.device = "mps"
        else:
            self.device = "cpu"
            
        print(f"Loading Vision Model on {self.device}...")

        if self.device in ["cuda", "mps"]:
            model_name = self.mlops_config.get("vision_model_cuda", "vidore/colpali-v1.3")
            dtype = torch.float16 if self.device == "mps" else torch.bfloat16
            
            if "colqwen" in model_name.lower() or "hydra" in model_name.lower():
                self.vis_processor = AutoProcessor.from_pretrained(model_name, cache_dir=CACHE_DIR)
                self.vis_model = AutoModelForVision2Seq.from_pretrained(model_name, torch_dtype=dtype, cache_dir=CACHE_DIR).to(self.device)
            else:
                self.vis_processor = ColPaliProcessor.from_pretrained(model_name, cache_dir=CACHE_DIR)
                self.vis_model = ColPali.from_pretrained(model_name, torch_dtype=dtype, cache_dir=CACHE_DIR).to(self.device)
        else:
            model_name = self.mlops_config.get("vision_model_cpu", "vidore/colSmol-256M")
            self.vis_processor = ColIdefics3Processor.from_pretrained(model_name, cache_dir=CACHE_DIR)
            self.vis_model = ColIdefics3.from_pretrained(model_name, torch_dtype=torch.float32, cache_dir=CACHE_DIR).to(self.device)

        # 4. Configuration de la structure de la base
        self._setup_collection()

    def _setup_collection(self):
        """Détecte dynamiquement les dimensions et configure Qdrant."""
        if self.client.collection_exists(self.collection_name):
            return

        print(f"🛠️  Configuration dynamique de la collection : {self.collection_name}")

        # 1. DÉTECTION DIMENSION TEXTE (ColBERT ou Standard)
        try:
            if self.is_colbert:
                # ColBERT utilise passage_embed et renvoie un tenseur 3D [nb_tokens, dim]
                dummy_text_emb = list(self.text_model.passage_embed(["test"]))[0]
                text_dim = dummy_text_emb.shape[1]  # On prend la dimension de la dernière couche
            elif self.is_gemini_text:
                response = genai.embed_content(model="models/text-embedding-004", content="test")
                text_dim = len(response['embedding'])
            elif self.is_qwen_text:
                text_dim = len(self.text_model.encode(["test"])[0])
            else:
                dummy_text_emb = list(self.text_model.embed(["test"]))[0]
                text_dim = len(dummy_text_emb)
        except Exception as e:
            print(f"⚠️ Erreur détection texte, fallback à 128: {e}")
            text_dim = 128

        # 2. DÉTECTION DIMENSION VISION (ColPali / ColSmol)
        try:
            # On crée une petite image blanche de test pour obtenir la dimension de sortie réelle
            dummy_image = Image.new('RGB', (224, 224), color='white')
            vis_batch = self.vis_processor.process_images([dummy_image]).to(self.device)

            with torch.no_grad():
                dummy_vis_emb = self.vis_model(**vis_batch)
                # ColPali renvoie [1, nb_patches, dim]. On veut le 'dim'.
                vision_dim = dummy_vis_emb.shape[-1]
        except Exception as e:
            print(f"⚠️ Erreur détection vision, fallback à 128: {e}")
            vision_dim = 128

        print(f"✅ Dimensions détectées -> Texte: {text_dim} | Vision: {vision_dim}")

        # 3. CONFIGURATION DES VECTEURS
        vectors_config = {
            "colpali_image": models.VectorParams(
                size=vision_dim,
                distance=models.Distance.DOT,
                multivector_config=models.MultiVectorConfig(comparator=models.MultiVectorComparator.MAX_SIM)
            )
        }

        # On définit le nom du vecteur texte dynamiquement
        text_vector_key = "colbert_text" if self.is_colbert else "text"

        vectors_config[text_vector_key] = models.VectorParams(
            size=text_dim,
            distance=models.Distance.COSINE,
            # On active le multi-vecteur seulement si c'est du ColBERT
            multivector_config=models.MultiVectorConfig(
                comparator=models.MultiVectorComparator.MAX_SIM) if self.is_colbert else None
        )

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=vectors_config,
            # --- OPTIMISATION MÉMOIRE : QUANTIFICATION SCALAIRE (DÉSACTIVÉE) ---
            # Pour activer (divise la RAM par 4), décommentez les lignes ci-dessous :
            # quantization_config=models.ScalarQuantization(
            #     scalar=models.ScalarQuantizationConfig(
            #         type=models.ScalarType.INT8,
            #         quantile=0.99,
            #         always_ram=True
            #     )
            # )
        )

    def _clean_existing_file_data(self, mongo_id):
        """Supprime les anciens vecteurs du fichier via son ID unique pour éviter les collisions."""
        if not mongo_id:
            return
        print(f"🧹 Nettoyage des anciennes données pour l'ID : {mongo_id}")
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[models.FieldCondition(key="mongo_file_id", match=models.MatchValue(value=mongo_id))]
                )
            ),
        )

    def _find_nearest_caption(self, img_bbox, text_passages, threshold=100):
        """Associe l'image à la légende la plus proche géométriquement."""
        closest_text = "Légende non détectée"
        min_dist = float('inf')
        img_y_bottom = img_bbox[3]

        for passage in text_passages:
            text_y_top = passage['bbox'][1]
            dist = abs(text_y_top - img_y_bottom)
            if dist < min_dist and dist < threshold:
                min_dist = dist
                closest_text = passage['content']
        return closest_text

    def process_pdf(self, pdf_path, mongo_id=None, progress_callback=None):
        """Pipeline complet d'indexation."""
        self._clean_existing_file_data(mongo_id)

        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        print(f"🚀 Indexation chirurgicale : {total_pages} pages pour {os.path.basename(pdf_path)}")

        for page_num in range(total_pages):
            page = doc[page_num]
            print(f"📖 Page {page_num + 1}/{total_pages} : Analyse en cours...", flush=True)
            # --- C. HYBRID INDEXING (BLOCKS, LINES, WORDS) ---
            print("  - Extraction du texte...", end="", flush=True)
            blocks = page.get_text("dict")["blocks"]
            print(f" OK ({len(blocks)} blocs détectés).", flush=True)
            current_page_passages = []
            
            # Phase 1: Blocks (for RAG context)
            threshold = self.mlops_config.get("text_block_threshold", 15)
            for b in blocks:
                if b['type'] == 0:  # Texte
                    text_content = " ".join([s["text"] for l in b["lines"] for s in l["spans"]]).strip()
                    if len(text_content) > threshold:
                        current_page_passages.append({
                            "content": text_content,
                            "bbox": b['bbox'],
                            "type": "text_block"
                        })

            # Phase 2: Precision Lines & Words (for Tracking)
            precision_items = []
            for b in blocks:
                if b['type'] == 0:
                    for line in b["lines"]:
                        line_text = " ".join([s["text"] for s in line["spans"]]).strip()
                        if len(line_text) > 3:
                            precision_items.append({
                                "content": line_text, 
                                "bbox": line["bbox"], 
                                "type": "text_line"
                            })
            
                            # On reste au niveau de la ligne pour la performance et la stabilité.
                            # Le soulignement par ligne est fluide et 10x plus rapide que par mot.

            # --- D. TRAITEMENT DES IMAGES INDIVIDUELLES ---
            images_info = page.get_image_info()
            if images_info:
                print(f"  - {len(images_info)} images trouvées. Vérification...", flush=True)

            for img_idx, img_info in enumerate(images_info):
                bbox = img_info['bbox']

                # Smart Crop de l'image avec force RGB
                pix = page.get_pixmap(clip=bbox, dpi=200, colorspace=fitz.csRGB)
                
                # Filtrage : Ignorer les images trop petites ou trop fines (lignes, icônes, séparateurs)
                # qui font planter les processeurs de vision avec des erreurs de dimension (ex: 1px de haut)
                if pix.width < 40 or pix.height < 40:
                    continue
                    
                print(f"    🖼️ Analyse image {img_idx+1}/{len(images_info)} (ColPali)...", flush=True)
                img_pil = Image.frombytes("RGB", [pix.width, pix.height], pix.samples).convert("RGB")
                caption = self._find_nearest_caption(bbox, current_page_passages)

                # Vectorisation Vision
                if hasattr(self.vis_processor, "process_images"):
                    vis_batch = self.vis_processor.process_images([img_pil]).to(self.device)
                else:
                    vis_batch = self.vis_processor(images=img_pil, return_tensors="pt").to(self.device)

                with torch.no_grad():
                    if hasattr(self.vis_model, "get_image_embeddings"):
                        image_embeddings = self.vis_model.get_image_embeddings(**vis_batch)
                    else:
                        image_embeddings = self.vis_model(**vis_batch)

                if isinstance(image_embeddings, torch.Tensor):
                    image_vec = image_embeddings[0].cpu().float().numpy().tolist()
                else:
                    image_vec = image_embeddings.last_hidden_state[0].cpu().float().numpy().tolist()

                # Upsert dans Qdrant
                self.client.upsert(
                    self.collection_name,
                    points=[models.PointStruct(
                        id=uuid.uuid4().hex,
                        vector={IMAGE_VECTOR_NAME: image_vec},
                        payload={
                            "type": "individual_image",
                            "page_number": page_num + 1,
                            "source": pdf_path,
                            "mongo_file_id": mongo_id,
                            "caption": caption,
                            "is_alternative": False
                        }
                    )]
                )

            # --- INDEXATION TEXTUELLE ---
            all_text_items = current_page_passages + precision_items
            if all_text_items:
                print(f"  - Vectorisation de {len(all_text_items)} segments de texte...", end="", flush=True)
                texts = [p["content"] for p in all_text_items]
                # Encodage par batch pour éviter l'explosion mémoire
                if self.is_gemini_text:
                    embeddings_gen = [genai.embed_content(model="models/text-embedding-004", content=t)['embedding'] for t in texts]
                elif self.is_qwen_text:
                    embeddings_gen = self.text_model.encode(texts)
                elif self.is_colbert:
                    embeddings_gen = self.text_model.passage_embed(texts)
                else:
                    embeddings_gen = self.text_model.embed(texts)

                points_to_upsert = []
                for i, embedding in enumerate(embeddings_gen):
                    item = all_text_items[i]
                    points_to_upsert.append(models.PointStruct(
                        id=uuid.uuid4().hex,
                        vector={self.text_vector_name: embedding.tolist()},
                        payload={
                            "type": item["type"],
                            "content": item["content"],
                            "page_number": page_num + 1,
                            "source": pdf_path,
                            "mongo_file_id": mongo_id,
                            "bbox": item["bbox"]
                        }
                    ))
                
                # Upsert par petits batches de 100 pour la stabilité
                for j in range(0, len(points_to_upsert), 100):
                    self.client.upsert(self.collection_name, points=points_to_upsert[j : j + 100])
                print(" OK.", flush=True)
            
            print(f"✅ Page {page_num + 1}/{total_pages} terminée.", flush=True)

            # Envoi de la progression au worker Celery (via callback)
            if progress_callback:
                progress_callback(current=page_num + 1, total=total_pages)

        print(f"🎉 Succès : Le cours est disponible pour l'assistant.", flush=True)


# --- POINT D'ENTRÉE POUR JAVA / TERMINAL ---
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("❌ Erreur : Paramètres manquants.")
        print("Usage: python Upload.py <chemin_du_pdf> <mongo_file_id>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    mongo_id = sys.argv[2]

    if os.path.exists(pdf_path):
        indexer = Upload()
        indexer.process_pdf(pdf_path, mongo_id)
    else:
        print(f"❌ Erreur : Fichier introuvable à l'adresse {pdf_path}")
        sys.exit(1)

"""
# --- BLOC D'EXÉCUTION POUR TEST MANUEL SÉCURISÉ ---
if __name__ == "__main__":
    # Dossier uploads relatif au script
    base_dir = os.path.dirname(os.path.abspath(__file__))
    uploads_dir = os.path.join(base_dir, "uploads")

    print("\n--- TESTEUR DE SOUS-AGENT IMAGE ---")
    print(f"📁 Dossier de recherche : {uploads_dir}")

    if not os.path.exists(uploads_dir):
        print(f"⚠️ Le dossier 'uploads' n'existe pas. Création en cours...")
        os.makedirs(uploads_dir)

    file_name = "texte2.pdf"
    pdf_path = os.path.join(uploads_dir, file_name)

    # Simulation d'un ID MongoDB
    test_mongo_id = "test_manual_indexation_" + uuid.uuid4().hex[:6]

    if os.path.exists(pdf_path):
        print(f"✅ Fichier trouvé. Initialisation des modèles...")
        try:
            indexer = Upload()
            indexer.process_pdf(pdf_path, test_mongo_id)
        except Exception as e:
            print(f"❌ Erreur lors du traitement : {e}")
    else:
        print(f"❌ Erreur : Le fichier '{file_name}' est introuvable dans {uploads_dir}")"""
