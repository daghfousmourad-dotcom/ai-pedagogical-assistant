# ==============================================================================
# PROPRIÉTÉ DE AI ASSISTANT - (c) 2024-2026 Mourad Daghfous
# Système d'Interaction Vocale Intelligent pour l'Éducation
# ------------------------------------------------------------------------------
# Ce fichier est confidentiel et protégé par les lois sur la propriété 
# intellectuelle. Toute diffusion non autorisée est passible de poursuites.
# ==============================================================================
import fitz  # PyMuPDF
import torch
import uuid
import os
import sys
import time
from PIL import Image
from qdrant_client import QdrantClient, models
from fastembed import LateInteractionTextEmbedding, TextEmbedding
from colpali_engine.models import ColPaliProcessor, ColPali, ColIdefics3Processor, ColIdefics3
from transformers import BlipProcessor, BlipForConditionalGeneration, AutoProcessor, AutoModelForVision2Seq, BitsAndBytesConfig
from sentence_transformers import SentenceTransformer
import google.generativeai as genai
from services.utils.mlops_config import get_active_embedding_config

# --- CONFIGURATION GLOBALE ---
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
# COLLECTION_NAME est utilisé comme fallback si la config MLOps est absente
COLLECTION_NAME_DEFAULT = os.getenv("COLLECTION_NAME", "Vector_Embeddings")

# Chemin vers le cache des modèles (optimisé pour Docker)
CACHE_DIR = os.getenv("AI_MODELS_CACHE_PATH", "/Volumes/MonSSD/pfe/ai_models_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

class UploadAdvanced:
    def __init__(self, specific_config=None):
        """
            Initialisation de l'agent.
            :param specific_config: (dict) Configuration MLOps récupérée au préalable.
                                    Si None, récupère la config active par défaut.
            """
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

        # 1. Connexion Qdrant
        print(f"Connecting to Qdrant at: {QDRANT_URL}")
        try:
            self.client = QdrantClient(QDRANT_URL, timeout=180) # Augmentation timeout
            self.image_vector_name = "colpali_image"
        except Exception as e:
            print(f"❌ Critical Error: Could not initialize QdrantClient at {QDRANT_URL}: {e}")
            raise

        # 2. Choix du Device (MPS pour Mac, CUDA pour GPU, CPU sinon)
        if torch.cuda.is_available():
            self.device = "cuda"
        elif torch.backends.mps.is_available():
            self.device = "mps"
        else:
            self.device = "cpu"
        
        print(f"Using device: {self.device}")

        # 3. Chargement du modèle Text (Dynamic Factory)
        text_model_name = self.mlops_config.get("text_model", "colbert-ir/colbertv2.0")
        self.is_colbert = "colbert" in text_model_name.lower()
        self.is_gemini_text = "gemini" in text_model_name.lower()
        self.is_qwen_text = "qwen3" in text_model_name.lower()
        
        print(f"Loading Text Model ({text_model_name}) from {CACHE_DIR}...")
        
        if self.is_gemini_text:
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
            self.text_model = "GEMINI_API"
        elif self.is_qwen_text:
            # Support Qwen3 via SentenceTransformers (Quantized if requested)
            load_args = {"cache_folder": CACHE_DIR}
            if "-int4" in text_model_name.lower():
                # Note: bitsandbytes requires CUDA for 4-bit. Fallback to default on MPS/CPU.
                if self.device == "cuda":
                    load_args["model_kwargs"] = {"load_in_4bit": True}
            self.text_model = SentenceTransformer(text_model_name.replace("-Int4", ""), **load_args)
        elif self.is_colbert:
            self.text_model = LateInteractionTextEmbedding(model_name=text_model_name, cache_dir=os.path.join(CACHE_DIR, "fastembed"))
        else:
            self.text_model = TextEmbedding(model_name=text_model_name, cache_dir=os.path.join(CACHE_DIR, "fastembed"))

        self.text_vector_name = "colbert_text" if self.is_colbert else "text"

        # 4. Chargement du modèle Vision (ColPali, ColQwen, Hydra)
        vision_model_name = self.mlops_config.get("vision_model_cuda" if self.device != "cpu" else "vision_model_cpu", "vidore/colpali-v1.3")
        dtype = torch.float16 if self.device == "mps" else (torch.bfloat16 if self.device == "cuda" else torch.float32)
        
        print(f"Loading Vision Model ({vision_model_name}) on {self.device}...")
        try:
            # Gestion de la quantification (Int4)
            bnb_config = None
            if "-int4" in vision_model_name.lower() and self.device == "cuda":
                bnb_config = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=dtype)
                vision_model_name = vision_model_name.replace("-Int4", "")

            if "colqwen" in vision_model_name.lower() or "hydra" in vision_model_name.lower():
                print(f"🚀 Loading New Gen Vision-Language Model: {vision_model_name}")
                self.vis_processor = AutoProcessor.from_pretrained(vision_model_name, cache_dir=CACHE_DIR)
                self.vis_model = AutoModelForVision2Seq.from_pretrained(
                    vision_model_name,
                    torch_dtype=dtype,
                    quantization_config=bnb_config,
                    cache_dir=CACHE_DIR
                ).to(self.device)
            elif "colpali" in vision_model_name.lower():
                self.vis_processor = ColPaliProcessor.from_pretrained(vision_model_name, cache_dir=CACHE_DIR)
                self.vis_model = ColPali.from_pretrained(
                    vision_model_name, 
                    torch_dtype=dtype,
                    cache_dir=CACHE_DIR
                ).to(self.device)
            else:
                # Fallback léger
                self.vis_processor = ColIdefics3Processor.from_pretrained("vidore/colSmol-256M", cache_dir=CACHE_DIR)
                self.vis_model = ColIdefics3.from_pretrained(
                    "vidore/colSmol-256M", 
                    torch_dtype=torch.float32,
                    cache_dir=CACHE_DIR
                ).to(self.device)
        except Exception as e:
            print(f"❌ Critical Error loading Vision Model {vision_model_name}: {e}")
            raise

        # 5. Agent LLM Local (BLIP pour résumé textuel des images)
        print(f"Loading Agent LLM (BLIP) from {CACHE_DIR}...")
        for attempt in range(3):
            try:
                self.blip_processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base", cache_dir=CACHE_DIR)
                blip_dtype = torch.float16 if self.device == "mps" else (torch.bfloat16 if self.device == "cuda" else torch.float32)
                self.blip_model = BlipForConditionalGeneration.from_pretrained(
                    "Salesforce/blip-image-captioning-base", 
                    torch_dtype=blip_dtype,
                    cache_dir=CACHE_DIR
                ).to(self.device)
                break
            except Exception as e:
                if attempt == 2: raise
                print(f"⚠️  Tentative BLIP {attempt+1} échouée: {e}. Retrying in 2s...")
                time.sleep(2)

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
                # Appel API Gemini pour la détection de dimension
                response = genai.embed_content(model="models/text-embedding-004", content="test")
                text_dim = len(response['embedding'])
            elif self.is_qwen_text:
                dummy_text_emb = self.text_model.encode(["test"])[0]
                text_dim = len(dummy_text_emb)
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
        if not mongo_id:
            return
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[models.FieldCondition(key="mongo_file_id", match=models.MatchValue(value=mongo_id))]
                )
            ),
        )

    def _find_nearest_caption(self, img_bbox, text_passages, threshold=150):
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
        self._clean_existing_file_data(mongo_id)

        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        print(f"📡 Indexation Avancée (Méthode 2) : {total_pages} pages pour {os.path.basename(pdf_path)}")

        for page_num in range(total_pages):
            page = doc[page_num]
            print(f"📖 Page {page_num+1}/{total_pages} : Analyse en cours...", flush=True)
            # --- C. HYBRID INDEXING (BLOCKS, LINES, WORDS) ---
            print("  - Extraction du texte...", end="", flush=True)
            blocks = page.get_text("dict")["blocks"]
            print(f" OK ({len(blocks)} blocs détectés).", flush=True)
            current_page_passages = []
            
            # Phase 1: Semantic Blocks (for RAG/Ollama) - Already existing logic refined
            current_chunk = ""
            current_bbox = None
            
            for b in blocks:
                if b['type'] == 0:  # Texte
                    text_content = " ".join([s["text"] for l in b["lines"] for s in l["spans"]]).strip()
                    if not text_content: continue
                    
                    if not current_chunk:
                        current_chunk = text_content
                        current_bbox = b['bbox']
                    else:
                        if abs(b['bbox'][1] - current_bbox[3]) < 20: 
                            current_chunk += " " + text_content
                            current_bbox = (current_bbox[0], current_bbox[1], max(current_bbox[2], b['bbox'][2]), max(current_bbox[3], b['bbox'][3]))
                        else:
                            threshold = self.mlops_config.get("text_block_threshold", 10)
                            if len(current_chunk.split()) >= threshold:
                                current_page_passages.append({"content": current_chunk, "bbox": current_bbox, "type": "text_block"})
                            current_chunk = text_content
                            current_bbox = b['bbox']
            
            if current_chunk and len(current_chunk.split()) >= self.mlops_config.get("text_block_threshold", 10):
                current_page_passages.append({"content": current_chunk, "bbox": current_bbox, "type": "text_block"})

            # Phase 2: Precision Lines & 
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

            # --- D. AGENTIC MULTIMODAL PROCESSING ---
            images_info = page.get_image_info()
            if images_info:
                print(f"  - {len(images_info)} images trouvées. Filtrage et analyse...", flush=True)
            
            for img_idx, img_info in enumerate(images_info):
                bbox = img_info['bbox']
                pix = page.get_pixmap(clip=bbox, dpi=200, colorspace=fitz.csRGB)
                
                if pix.width < 40 or pix.height < 40:
                    continue
                
                print(f"    🖼️ Analyse image {img_idx+1}/{len(images_info)} (ColPali + BLIP)...", flush=True)
                img_pil = Image.frombytes("RGB", [pix.width, pix.height], pix.samples).convert("RGB")
                caption = self._find_nearest_caption(bbox, current_page_passages)

                # 1. Vecteur Vision Pur (ColPali/Smol/Qwen/Hydra)
                t_start_vis = time.perf_counter()
                
                # Prétraitement spécifique selon le processeur
                if hasattr(self.vis_processor, "process_images"):
                    vis_batch = self.vis_processor.process_images([img_pil]).to(self.device)
                else:
                    # Cas AutoProcessor (Qwen/Hydra)
                    vis_batch = self.vis_processor(images=img_pil, return_tensors="pt").to(self.device)

                with torch.no_grad():
                    # Hydra et ColQwen génèrent des embeddings via le modèle de base ou une méthode spécifique
                    if hasattr(self.vis_model, "get_image_embeddings"):
                        image_embeddings = self.vis_model.get_image_embeddings(**vis_batch)
                    else:
                        image_embeddings = self.vis_model(**vis_batch)
                
                # On extrait le dernier état caché ou l'embedding projeté
                if isinstance(image_embeddings, torch.Tensor):
                    image_vec = image_embeddings[0].cpu().float().numpy().tolist()
                else:
                    image_vec = image_embeddings.last_hidden_state[0].cpu().float().numpy().tolist()

                t_end_vis = time.perf_counter()
                print(f"      ⏱️ [Vision] {t_end_vis - t_start_vis:.2f}s", flush=True)

                self.client.upsert(
                    self.collection_name,
                    points=[models.PointStruct(
                        id=uuid.uuid4().hex,
                        vector={self.image_vector_name: image_vec},
                        payload={
                            "type": "individual_image",
                            "page_number": page_num + 1,
                            "source": pdf_path,
                            "mongo_file_id": mongo_id,
                            "caption": caption,
                            "bbox": bbox,
                            "is_alternative": False
                        }
                    )]
                )

                # 2. IA Agentique (Génération textuelle de l'image)
                t_start_blip = time.perf_counter()
                inputs = self.blip_processor(img_pil, "An image showing", return_tensors="pt").to(self.device)
                with torch.no_grad():
                    out = self.blip_model.generate(**inputs, max_new_tokens=40)
                ai_generated_caption = self.blip_processor.decode(out[0], skip_special_tokens=True)
                t_end_blip = time.perf_counter()
                print(f"      ⏱️ [BLIP] {t_end_blip - t_start_blip:.2f}s", flush=True)

                ai_full_text = f"[Résumé IA de l'image] : {ai_generated_caption}. [Contexte géométrique] : {caption}."
                
                # Indexation de ce résumé textuel dans la base des textes !
                if self.is_colbert:
                    emb_generator = self.text_model.passage_embed([ai_full_text])
                else:
                    emb_generator = self.text_model.embed([ai_full_text])
                embedding = list(emb_generator)[0].tolist()

                self.client.upsert(
                    self.collection_name,
                    points=[models.PointStruct(
                        id=uuid.uuid4().hex,
                        vector={self.text_vector_name: embedding},
                        payload={
                            "type": "ai_image_summary",
                            "content": ai_full_text,
                            "page_number": page_num + 1,
                            "source": pdf_path,
                            "mongo_file_id": mongo_id,
                            "bbox": bbox
                        }
                    )]
                )

            # --- INDEXATION TEXTUELLE ---
            all_text_items = current_page_passages + precision_items
            if all_text_items:
                print(f"  - Vectorisation de {len(all_text_items)} segments de texte...", end="", flush=True)
                texts = [p["content"] for p in all_text_items]
                
                if self.is_gemini_text:
                    embeddings_list = [genai.embed_content(model="models/text-embedding-004", content=t)['embedding'] for t in texts]
                    embeddings_gen = embeddings_list
                elif self.is_qwen_text:
                    embeddings_gen = self.text_model.encode(texts)
                elif self.is_colbert:
                    embeddings_gen = self.text_model.passage_embed(texts)
                else:
                    embeddings_gen = self.text_model.embed(texts)

                points_to_upsert = []
                for i, embedding in enumerate(embeddings_gen):
                    item = all_text_items[i]
                    vector_name = "colbert_text" if self.is_colbert else "text"
                    points_to_upsert.append(models.PointStruct(
                        id=uuid.uuid4().hex,
                        vector={vector_name: embedding.tolist()},
                        payload={
                            "type": item["type"],
                            "content": item["content"],
                            "page_number": page_num + 1,
                            "source": pdf_path,
                            "mongo_file_id": mongo_id,
                            "bbox": item["bbox"],
                            "index": item.get("index", 999) # Utilise l'index calculé ou fallback
                        }
                    ))
                self.client.upsert(self.collection_name, points=points_to_upsert)
                print(" OK.", flush=True)
            
            print(f"✅ Page {page_num+1}/{total_pages} terminée.", flush=True)

            # Envoi de la progression au worker Celery (via callback)
            if progress_callback:
                progress_callback(current=page_num + 1, total=total_pages)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(1)
    pdf_path = sys.argv[1]
    mongo_id = sys.argv[2]
    if os.path.exists(pdf_path):
        indexer = UploadAdvanced()
        indexer.process_pdf(pdf_path, mongo_id)
