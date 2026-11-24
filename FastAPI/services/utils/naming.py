import re

def get_safe_collection_name(text_model: str, vision_model: str, version_name: str = None) -> str:
    """
    Génère un nom de collection Qdrant déterministe et sûr à partir du couple de modèles et de la version.
    Exemple: BAAI/bge-small-en-v1.5 + vidore/colpali-v1.3 + prod_v4
             -> MLOps_prod_v4_bge_small_en_v1_5_colpali_v1_3
    """
    # Extraction du nom de base (après le dernier /) pour plus de compacité
    text_base = text_model.split("/")[-1]
    vision_base = vision_model.split("/")[-1]
    
    # Nettoyage des noms (alphanumérique uniquement)
    text_clean = re.sub(r'[^a-zA-Z0-9]', '_', text_base)
    vision_clean = re.sub(r'[^a-zA-Z0-9]', '_', vision_base)
    version_clean = re.sub(r'[^a-zA-Z0-9]', '_', version_name) if version_name else ""
    
    # Nettoyage des underscores doubles potentiels
    text_clean = re.sub(r'_+', '_', text_clean).strip('_')
    vision_clean = re.sub(r'_+', '_', vision_clean).strip('_')
    version_clean = re.sub(r'_+', '_', version_clean).strip('_')
    
    prefix = f"{version_clean}_" if version_clean else ""
    return f"MLOps_{prefix}{text_clean}_{vision_clean}"
