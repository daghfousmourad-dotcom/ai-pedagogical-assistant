import os
import json
import re
from collections import Counter
import sys
import asyncio
import csv

# Set up path to import services
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.agents.voice_utils import VoiceAgentUtils

# =====================================================================
# 1. DATASET DE TEST POUR LA CLASSIFICATION D'INTENTION
# Ce dataset permet de mesurer l'Accuracy du routeur cognitif.
# =====================================================================
dataset_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "synthetic_test_set.json")
if os.path.exists(dataset_path):
    with open(dataset_path, "r", encoding="utf-8") as f:
        INTENT_TEST_DATA = json.load(f)
else:
    INTENT_TEST_DATA = [{"text": "Passe", "expected": "NAVIGATION"}]

# =====================================================================
# 2. FONCTION DE CALCUL DU F1-SCORE TEXTUEL (Token-Level F1)
# =====================================================================
def compute_f1_token(prediction: str, truth: str) -> float:
    """
    Calcule le F1-Score au niveau des mots (Tokens).
    - Précision : Les mots de la prédiction sont-ils pertinents ?
    - Rappel : A-t-on oublié des mots importants de la vérité terrain ?
    """
    pred_tokens = set(re.findall(r'\w+', str(prediction).lower()))
    truth_tokens = set(re.findall(r'\w+', str(truth).lower()))
    
    if len(pred_tokens) == 0 or len(truth_tokens) == 0:
        return 0.0
        
    common_tokens = pred_tokens.intersection(truth_tokens)
    num_common = len(common_tokens)
    
    if num_common == 0:
        return 0.0
        
    precision = num_common / len(pred_tokens)
    recall = num_common / len(truth_tokens)
    
    f1 = (2 * precision * recall) / (precision + recall)
    return f1

async def main():
    print("🚀 [MLOps] Démarrage de l'évaluation des métriques statistiques...")
    
    # --- PARTIE 1: CLASSIFICATION D'INTENTION (Accuracy) ---
    print("\n📊 Évaluation de l'Analyse d'Intention...")
    voice_agent = VoiceAgentUtils()
    
    correct = 0
    total = len(INTENT_TEST_DATA)
    intent_results = []
    
    for item in INTENT_TEST_DATA:
        result = voice_agent.classify_intent(item["text"])
        pred = result.get("intent", "UNKNOWN")
        
        # Mapping pour tolérance RAG
        if pred == "TEXT_QUERY": pred = "TECHNICAL_QUESTION"
            
        is_correct = (pred == item["expected"])
        if is_correct:
            correct += 1
            
        intent_results.append({
            "text": item["text"],
            "expected_intent": item["expected"],
            "predicted_intent": pred,
            "is_correct": is_correct
        })
        
    accuracy = (correct / total) * 100
    print(f"🎯 Accuracy Routeur Cognitif : {accuracy:.2f}% ({correct}/{total})")
    
    # --- PARTIE 2: F1-SCORE SUR RAG (Chevauchement) ---
    print("\n📊 Évaluation du F1-Score Textuel (RAG)...")
    rag_csv = "/Volumes/MonSSD/pfe/Rapport/ragas_results.csv"
    f1_scores = []
    
    if os.path.exists(rag_csv):
        with open(rag_csv, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Ignorer la ligne de synthèse
                if row.get("question") == "MOYENNES / TOTALS":
                    continue
                    
                # Dans votre CSV, les colonnes sont 'response' et 'reference'
                truth = row.get("reference", row.get("ground_truth", ""))
                pred = row.get("response", row.get("answer", ""))
                
                if truth and pred:
                    f1 = compute_f1_token(pred, truth)
                    f1_scores.append(f1)
                
        avg_f1 = sum(f1_scores) / len(f1_scores) if f1_scores else 0
        print(f"📈 F1-Score Moyen (Génération RAG) : {avg_f1:.4f}")
    else:
        print("⚠️ Fichier ragas_results.csv introuvable. Exécutez evaluate_rag.py d'abord.")
        avg_f1 = 0
        
    # --- EXPORTATION DU RAPPORT POUR COLAB ---
    export_path = "/Volumes/MonSSD/pfe/Rapport/mlops_colab_metrics.json"
    
    export_data = {
        "intent_classification": {
            "metric": "Accuracy",
            "score": accuracy,
            "total_samples": total,
            "details": intent_results
        },
        "rag_performance": {
            "metric": "Token_F1_Score",
            "score": avg_f1 * 100, # Convertir en pourcentage
            "total_samples": len(f1_scores),
            "individual_f1_scores": f1_scores
        }
    }
    
    with open(export_path, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, indent=4, ensure_ascii=False)
        
    print(f"\n✅ Rapport de métriques généré de manière RESTful (Fichier JSON autonome) :")
    print(f"   -> {export_path}")
    print("💡 Importez ce fichier dans Google Colab pour générer vos matrices de confusion et graphiques.")

if __name__ == "__main__":
    asyncio.run(main())
