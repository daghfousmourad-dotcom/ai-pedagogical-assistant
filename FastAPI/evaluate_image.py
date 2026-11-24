import os
import json
import time
import csv
import re
import fitz  # PyMuPDF
import pandas as pd
from datasets import Dataset
from ragas import evaluate
try:
    from ragas.metrics import Faithfulness, AnswerRelevancy
except ImportError:
    from ragas.metrics.collections import Faithfulness, AnswerRelevancy
from langchain_openai import ChatOpenAI
from langchain_openai import OpenAIEmbeddings
from qdrant_client import QdrantClient, models

# Importer l'agent clarificateur d'image
from services.agents.image_clarifier import ImageClarifierAgent
from services.utils.mlops_config import get_active_embedding_config

# ---------------------------------------------------------------------------
# Normalisation des abréviations médicales (pour l'évaluation RAGAS SEULEMENT)
# Évite que des abréviations comme "UIV" vs "urographie intraveineuse" pénalisent
# le score de fidélité alors que le concept est identique.
# ---------------------------------------------------------------------------
MEDICAL_ABBR = {
    r"\bUIV\b": "urographie intraveineuse",
    r"\bAUSP\b": "abdomen sans préparation",
    r"\bTDM\b": "tomodensitométrie scanner",
    r"\bASP\b": "abdomen sans préparation",
    r"\bIRM\b": "imagerie par résonance magnétique",
    r"\bECHO\b": "échographie",
    r"\bIVP\b": "urographie intraveineuse",
    r"\bKBP\b": "kyste bassin pyélique",
}

def normalize_text(text: str) -> str:
    """Remplace les abréviations médicales par leur forme développée (insensible à la casse)."""
    if not isinstance(text, str):
        return text
    result = text.lower()
    for pattern, replacement in MEDICAL_ABBR.items():
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result

# Configuration
MONGO_ID = "69b97420c0ffee11e99b16bc" # ID in course_db.documents
PDF_PATH = "/Volumes/MonSSD/pfe/test-microservices/shared_uploads/sémiologie de l'appariel urinaire 2015 2.pdf"
CACHE_FILE = "/tmp/image_eval_cache.json" # Added cache file

# Données extraites de Question-Reponse images.pdf
QA_DATA = [
    {
        "page_num": 5,
        "question": "Question 1:\nil s'agit d'un cliché d'un arbre urinaire sans préparation = AUSP\nA/ quelle est la tranche d'âge du patient: Adulte ou enfant et pourquoi\nB/ Décrire les anomalies et donner le diagnostic",
        "ground_truth": "A/ Il s’agit d’un enfant avant la fin de la croissance : les cartilages de croissance sur les têtes fémorales sont visibles\nB/ Présence de calcifications multiples en projection des 2 reins et de la vessie\nDiagnostic = lithiase rénale bilatérale et vésicale"
    },
    {
        "page_num": 43,
        "question": "Question 2:\nA/ Reconnaitre l’examen radiologique proposé\nB/ Décrire les anomalies et donner le diagnostique",
        "ground_truth": "A/ Examen: Urographie Intra-veineuse (UIV)\nB/ les grands axes des deux reins convergent vers le rachis au niveau des poles inférieurs\nDiagnostic: reins en fer à cheval"
    },
    {
        "page_num": 47,
        "question": "Question 3:\nA/ reconnaitre l’examen radiologique proposé\nB/ Décrire les anomalies et donner le diagnostic",
        "ground_truth": "A/ examen = Urographie Intra-Veineuse (UIV)\nB/ Rein droit situé à gauche en position lombaire, alors que son uretère s’abouche normalement à droite dans la vessie.\nDiagnostic = Ectopie rénale croisée"
    },
    {
        "page_num": 49,
        "question": "Question 4:\nA/ reconnaitre l’examen radiologique proposé\nB/ Décrire les anomalies et donner le diagnostic",
        "ground_truth": "A/ examen = Urographie Intra-Veineuse (UIV)\nB/ Cavités pyelo-uréterales droites et gauches doubles. Fusion des uretères et abouchement uréteral unique des deux côtés.\nDiagnostic : bifidité pyélo-urétérale bilatérale."
    },
    {
        "page_num": 68,
        "question": "Question 5:\nA/ reconnaitre l’examen radiologique proposé\nB/ Décrire les anomalies et donner le diagnostic",
        "ground_truth": "A/ Examen = Tomodensitométrique (TDM) ou scanner avec injection intra veineuse de produit de contraste\nB/ Présence d’une masse rénale gauche bien limitée, hypodense homogène, ne prend pas le contraste (donc non vascularisée)\nDiagnostic = kyste rénale simple"
    },
    {
        "page_num": 76, # Updated page_num directly in QA_DATA
        "question": "Question 6:\nA/ 2 examens proposés = une échographie et 2 images de scanners avec injection intraveineuse de contraste en coupe axiale et en coupe coronale\nB/ Décrire les lésions et donner le diagnostic",
        "ground_truth": "A/ 2 examens proposés = une échographie et 2 images de scanners avec injection intraveineuse de contraste en coupe axiale et en coupe coronale\nB/ échographie : très nombreuses lésions kystiques. Scanner = les 2 reins sont totalement envahis pas des formations qui ne prennent pas le contraste. On trouve ces lésions aussi sur le foie\nDiagnostics = polykystose hêpato-rénale"
    },
    {
        "page_num": 84,
        "question": "Question 7:\nA/ reconnaitre l’examen radiologique proposé\nB/ Décrire les lésions et donner le diagnostic",
        "ground_truth": "A/ Examen = Urographie intra-veineuse (UIV)\nB/ image compression extrinsèque sur le plancher de la vessie, à limites nettes et régulières. Cavités rénales droites pelviennes\nDiagnostic = Empreinte prostatique sur la vessie, rein droit ectopique pelvien"
    },
    {
        "page_num": 91,
        "question": "Question 8:\nA/ reconnaitre l’examen radiologique proposé\nB/ Décrire les anomalies et donner le diagnostic",
        "ground_truth": "A/ examen: plusieurs clichés d’urographie intra veineuse (UIV) à différents temps\nB/ Importante dilatation pyelo calicielle et de l’uretère du côté droit avec aspect convexe vers le bas du bord inférieur du pyelon\nDiagnostic = syndrome de la jonction pyelo-calicielle avec hydronéphrose"
    },
    {
        "page_num": 101,
        "question": "Question 9:\nIl s’agit d’un cliché d’arbre urinaire sans préparation (AUSP), décrire les anomalies et donner le diagnostic",
        "ground_truth": "Présence d’opacités calcifiées décrivant la totalité du rein droit et les 2/3 de l’uretère lombaire\nDiagnostic = tuberculose renale avec aspect de rein mastic"
    },
    {
        "page_num": 106,
        "question": "Question 10:\nA/ reconnaitre l’examen radiologique proposé\nB/ Décrire les anomalies et donner le diagnostic",
        "ground_truth": "A/ Examen : urographie intraveineuse (UIV).\nB/ Rein droit non sécrétant. Dilatation globale urétéropyélocalicielle gauche avec sténose serrée de l’uretère terminal. Vessie de très faible capacité (microvessie).\nDiagnostic : tuberculose urinaire."
    }
]
QA_DATA = QA_DATA[:5] # Réduction à 5 questions pour optimiser les coûts


def run_eval():
    print(f"🚀 Démarrage de l'évaluation Image Clarifier sur {len(QA_DATA)} questions...", flush=True)
    
    # --- ISOLATION MLOPS ---
    import sys
    sys.path.append("/Volumes/MonSSD/pfe/test-microservices/config_AI")
    from image_tester import ImageTester
    agent = ImageTester()
    
    # Initialisation Qdrant pour récupérer les métadonnées indexées
    mlops_config = get_active_embedding_config()
    
    # Hyperparamètres forcés
    forced_temp = float(mlops_config.get("llm_temperature", 0.7))
    forced_tokens = int(mlops_config.get("llm_max_tokens", 300))

    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    collection_name = mlops_config.get("qdrant_collection", os.getenv("COLLECTION_NAME", "Vector_Embeddings"))
    q_client = QdrantClient(qdrant_url)
    
    if not os.path.exists(PDF_PATH):
        print(f"❌ Erreur: Fichier PDF introuvable : {PDF_PATH}", flush=True)
        return
        
    doc = fitz.open(PDF_PATH)
    results = []
    
    total_latency = 0
    total_characters = 0

    # Charger le cache si existant
    cached_data = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                cached_data = json.load(f)
            print(f"📦 Cache chargé depuis {CACHE_FILE}", flush=True)
        except json.JSONDecodeError:
            print(f"⚠️ Erreur de lecture du cache {CACHE_FILE}, le fichier sera ignoré.", flush=True)
            cached_data = {}

    for idx, data in enumerate(QA_DATA):
        q_text = data["question"]
        page_num = data["page_num"]
        ground_truth = data["ground_truth"]
        
        # ID de cache unique basé sur le texte de la question et les paramètres FORCE
        cache_id = f"{q_text[:50]}_t{forced_temp}" # invalidate cache if temp changes
        
        # 1. FORCE NO CACHE for MLOps Diagnostic
        # if cache_id in cached_data: ...
        
        print(f"\n🧪 [MLOPS DIAGNOSTIC] Testing Q{idx+1} on Page {page_num} | Temp={forced_temp}", flush=True)
        
        # Obtenir l'image de la page depuis le PDF
        # Obtenir l'image de la page depuis le PDF
        page_index = page_num - 1
        page = doc.load_page(page_index)
        # Rendre la page sous forme de Pixmap (image)
        pix = page.get_pixmap(dpi=150) # Qualité suffisante pour l'IA Vision
        
        # Save temporary image for ImageTester
        temp_image = f"/tmp/eval_img_p{page_num}.jpg"
        pix.save(temp_image)
        
        # Chronométrer l'appel
        start_time = time.time()
            
        # --- NOUVEAU : Récupération des métadonnées depuis Qdrant ---
        try:
            search_res = q_client.scroll(
                collection_name=collection_name,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(key="mongo_file_id", match=models.MatchValue(value=MONGO_ID)),
                        models.FieldCondition(key="page_number", match=models.MatchValue(value=page_num)),
                        models.FieldCondition(key="type", match=models.MatchValue(value="individual_image"))
                    ]
                ),
                limit=1
            )
            points = search_res[0]
            metadata = points[0].payload.get("caption", "") if points else ""
            if metadata:
                print(f"    📖 Métadonnées trouvées : {metadata[:100]}...", flush=True)
        except Exception as e:
            print(f"    ⚠️ Erreur Qdrant : {e}", flush=True)
            metadata = ""

        # Appel au service Image TESTER avec les hyperparamètres
        prompt_with_meta = f"Analyse cette image de cours médical. Question: {q_text}\nContexte: {metadata}"
        answer = agent.analyze_image(temp_image, prompt_with_meta, temperature=forced_temp, max_tokens=forced_tokens)
        
        latency = time.time() - start_time
        search_query = metadata # Simplified for tester
        
        # Sauvegarder dans le cache
        cached_data[cache_id] = {"answer": answer, "latency": latency, "search_query": search_query}
        with open(CACHE_FILE, "w") as f:
            json.dump(cached_data, f)

        print(f"⏱️  Latency: {latency:.2f}s", flush=True)
        print(f"🤖 Answer: {answer[:100]}...", flush=True)
        
        total_latency += latency
        total_characters += len(answer)
        
        # Préparation des données pour RAGAS et le rapport
        results.append({
            "contexte complet de recherche par l'IA": search_query,
            "réponse complète de l'IA": answer,
            "réponse de référence": ground_truth,
            "latency": latency,
            # Champs pour RAGAS
            "question": q_text,
            "answer": answer,
            "contexts": [ground_truth],
            "ground_truth": ground_truth
        })

    # Calcul des métriques de performance globales
    avg_ttft = total_latency / len(QA_DATA) if QA_DATA else 0
    tps = total_characters / total_latency if total_latency > 0 else 0
    
    print(f"\n📊 [Performances Vision] TTFT Moyen: {avg_ttft:.3f}s | TPS Global: {tps:.2f} caractères/sec", flush=True)
    
    print("\n📊 Calcul des scores RAGAS (Faithfulness & Relevancy)...", flush=True)
    print("   ℹ️  Normalisation des abréviations médicales (UIV, AUSP, TDM, ...) pour l'évaluation.", flush=True)
    
    # Copie normalisée pour RAGAS uniquement (les abréviations médicales sont développées)
    ragas_records = [
        {
            "question": normalize_text(r["question"]),
            "answer": normalize_text(r["answer"]),
            "contexts": [normalize_text(ctx) for ctx in r["contexts"]],
            "ground_truth": normalize_text(r["ground_truth"])
        }
        for r in results
    ]
    dataset = Dataset.from_pandas(pd.DataFrame(ragas_records))
    judge_llm = ChatOpenAI(model="gpt-4o-mini")
    embeddings = OpenAIEmbeddings()

    # Ragas evaluation
    score = evaluate(
        dataset,
        metrics=[Faithfulness(), AnswerRelevancy()],
        llm=judge_llm,
        embeddings=embeddings
    )
    
    print("\n✅ RÉSULTATS DE L'ÉVALUATION :", flush=True)
    print(score, flush=True)
    
    # Création du DataFrame final avec les colonnes demandées
    # Note: Ragas in recent versions returns global scores but also per-instance in the result object if handled correctly.
    # To be precise, let's extract the per-instance scores from the scores attribute of the result object.
    scores_df = score.to_pandas()
    
    final_df = pd.DataFrame({
        "contexte complet de recherche par l'IA": [res["contexte complet de recherche par l'IA"] for res in results],
        "réponse complète de l'IA": [res["réponse complète de l'IA"] for res in results],
        "réponse de référence": [res["réponse de référence"] for res in results],
        "faithfulness": scores_df["faithfulness"].tolist(),
        "answer_relevancy": scores_df["answer_relevancy"].tolist()
    })

    # Ajout de la dernière ligne summary avec colonnes de métriques réelles
    summary_row = {
        "contexte complet de recherche par l'IA": "MOYENNES / TOTALS",
        "réponse complète de l'IA": "Summary",
        "réponse de référence": "Summary",
        "faithfulness": score["faithfulness"],
        "answer_relevancy": score["answer_relevancy"],
        "TTFT Moyen": avg_ttft,
        "TPS Global": tps
    }
    

    final_df = pd.concat([final_df, pd.DataFrame([summary_row])], ignore_index=True)
    
    csv_path = "/Volumes/MonSSD/pfe/Rapport/image_clarifier_results.csv"

    def safe_float(val):
        if isinstance(val, list) and len(val) > 0: return float(val[0])
        try: return float(val)
        except: return 0.0

    # JSON output for MLOps capture
    json_output = {
        "avg_ttft": avg_ttft,
        "tps_global": tps,
        "faithfulness": safe_float(score["faithfulness"]),
        "answer_relevancy": safe_float(score["answer_relevancy"]),
        "individual_results": [
            {
                "question": r["question"],
                "answer": r["answer"],
                "ground_truth": r["ground_truth"],
                "latency": r["latency"],
                "faithfulness": float(final_df.loc[i, "faithfulness"]) if i < len(results) else 0,
                "answer_relevancy": float(final_df.loc[i, "answer_relevancy"]) if i < len(results) else 0
            } for i, r in enumerate(results)
        ]
    }

    print("\n---JSON_RESULTS_START---")
    print(json.dumps(json_output))
    print("---JSON_RESULTS_END---")
    
    # SAUVEGARDE DU CSV POUR TESTRUNNER
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    final_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"✅ Résultats IMAGE sauvegardés dans {csv_path}")

if __name__ == "__main__":
    run_eval()
