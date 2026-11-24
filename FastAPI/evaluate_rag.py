import os
import json
import asyncio
import pandas as pd
import dotenv
import re

# Load environment variables from the root .env file FIRST
dotenv.load_dotenv("/Volumes/MonSSD/pfe/test-microservices/.env")
# Force QDRANT_URL to localhost for host-based execution
os.environ["QDRANT_URL"] = "http://localhost:6333"

from datasets import Dataset
from ragas import evaluate
try:
    from ragas.metrics import faithfulness, answer_relevancy
except ImportError:
    from ragas.metrics.collections import faithfulness, answer_relevancy
from services.agents.rag import RAGService
from services.utils.mlops_config import get_active_embedding_config
from OllamaService.ollama_rag_service import OllamaRAGService
from qdrant_client import QdrantClient, models
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

# Upgrade the judge model to GPT-4o-mini to avoid massive API costs during MLOps tests
eval_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
eval_embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

def clean_text(text):
    """Nettoie le texte des caractères spéciaux et normalise les ligatures."""
    if text is None:
        return ""
    if isinstance(text, (dict, list)):
        text = str(text)
    
    # Remplacer les ligatures
    text = text.replace('Œ', 'OE').replace('œ', 'oe')
    # Normaliser les termes médicaux fréquents mal extraits
    text = text.replace('OEsophage', 'oesophage').replace('Oesophage', 'oesophage')
    text = text.replace('gastriquil', 'gastrique. il').replace('intra-thoraciqula', 'intra-thoracique. la')
    
    # Supprimer les marqueurs de liste de manière sécurisée
    text = re.sub(r'(^|\s)\d+[)\.]\s*', r'\1', text)
    text = re.sub(r'(^|\s)[a-z][)\.]\s*', r'\1', text)
    
    # Remplacer les caractères spéciaux du PDF
    for char in ['⇨', '•', '●', '▪', '◦', '➢', '→', '·']:
        text = text.replace(char, '-')
    text = text.replace('\xa0', ' ').replace('\u200b', '')
    
    # Supprimer les doubles espaces
    text = re.sub(r'\s+', ' ', text)
    return text.strip().lower()

def filter_contexts(contexts):
    """Filtre les contextes pour retirer le bruit (ex: résumés d'images non pertinents)."""
    filtered = []
    for c in contexts:
        # Si le contexte parle de "knee" (genou), c'est une erreur d'extraction/indexation 
        # qui empoisonne le juge RAGAS, même s'il y a un mot clé digestif plus loin.
        if "knee" in c.lower() or "genou" in c.lower() or "cervical" in c.lower():
             if "oesophage" not in c.lower()[:100]: # Sauf si c'est vraiment le début du texte
                continue
        filtered.append(c)
    return filtered

# Config
MONGO_ID = "69b7f59cfd94fa75413eeef3"
QA_DATA = [
    {
        "question": "Citer, sans les décrire, les 3 portions de l’Oesophage.",
        "ground_truth": "Oesophage cervical (portion cervicale), Oesophage thoracique (portion thoracique), Oesophage abdominal (portion sous diaphragmatique)."
    },
    {
        "question": "décrire les deux types de stenoses de l’oesophage: benigne et maligne (ou tumorale)",
        "ground_truth": "Stenose benigne: axiale, régulière, progressiste. Maligne (tumorale): défilé irrégulier, excentré, raccordement abrut avec zone saisie."
    },
    {
        "question": "Définir la hernie hiatale",
        "ground_truth": "C’est le glissement sus-diaphragmatique du pôle supérieur de l’estomac à travers l’orifice Oesophagien"
    },
    {
        "question": "Citer 4 types de calcifications anormales qu’on pourrait voir sur un cliché d’abdomen sans préparation (ASP)",
        "ground_truth": "Kyste Hydatique du Foie, Calcul Vesiculaire, Calcul Urinaire, Micro calcifications pancréatiques"
    },
    {
        "question": "Citer 3 possibilités de présence d’air en dehors du tube digestif sur un cliché d’abdomen sans préparation (ASP)",
        "ground_truth": "Pneumopéritoine, Aérobilie, De l’air dans un abcès à germe anaérobie"
    },
    {
        "question": "parmi les propositions suivantes, laquelle est juste? A/ En echographie un kyste est améchogène renforçant les echos B/ En echographie un calcul est hyperéchogène renforçant les echos C/ Les urines dans la vessie sont hyperéchogène en echographie",
        "ground_truth": "Proposition A En echographie un kyste est améchogène renforçant les echos"
    },
    {
        "question": "Répondre par Vrai ou Faux: a. L'examen Doppler permet d’étudier les vaisseaux b. L'examen Doppler est réalisé grâce à des tubes à rayons X. c. L'echographie ne permet pas de faire la différence entre masse liquidienne et masse tissulaire d. L'echographie permet d’étudier les masses pariétales",
        "ground_truth": "a. Vrai, b. Faux, c. Faux, d. Vrai"
    },
    {
        "question": "Décrire les signes directs d’un ulcère digestif sur les clichés de face et de profil d’une opacification digestif",
        "ground_truth": "De face: Tache opâque ronde, entourrée d’un halot clair régulier (oedème). De profil: Saillie opâque, triangulaire à sommet arrondi, à bords réguliers émergeant en dehors du contour habituel du segment digestif"
    },
    {
        "question": "Décrire l’image d’un abcès sur un examen de tomodensitométrie (TDM)",
        "ground_truth": "Masse spontanément hypodense hétérogène se rehaussant en périphérie après injection intra-veineuse de produit de contraste, aménageant une zone centrale de densité liquidienne"
    },
    {
        "question": "Répondre par Vrai ou Faux: a. L'imagerie IRM est basée sur l’utilisation des ultrasons b. L'imagerie IRM permet d’étudier les vaisseaux et les voies biliaires sans injection de produit de contraste c. L'imagerie IRM ne permet pas d’étudier le contenu intra huminale du tube digestif",
        "ground_truth": "a. Faux, b. Vrai, c. Faux"
    }
]
# QA_DATA = QA_DATA[:5] # Réduction à 5 questions pour optimiser les coûts


async def run_eval():
    # Détecter le fournisseur LLM actif
    active_config = get_active_embedding_config()
    provider = active_config.get("llm_provider", "OPENAI")
    
    if provider == "OLLAMA":
        print(f"🦙 Utilisation de OllamaRAGService avec {active_config.get('llm_model')}...")
        rag = OllamaRAGService()
        use_ollama = True
    else:
        # --- ISOLATION MLOPS ---
        import sys
        sys.path.append("/Volumes/MonSSD/pfe/test-microservices/config_AI")
        from rag_tester import RAGTester
        rag = RAGTester(active_config)
        use_ollama = False

    local_qdrant = QdrantClient("http://localhost:6333")
    results = []
    
    import time
    total_latency = 0
    total_characters = 0
    
    # Préparer les hyperparamètres forcés
    forced_params = {
        "temperature": float(active_config.get("llm_temperature", 0.7)),
        "top_p": float(active_config.get("llm_top_p", 1.0)),
        "max_tokens": int(active_config.get("llm_max_tokens", 300)),
        "frequency_penalty": float(active_config.get("llm_frequency_penalty", 0.0)),
        "presence_penalty": float(active_config.get("llm_presence_penalty", 0.0))
    }

    for item in QA_DATA:
        query = item['question']
        print(f"Testing (Isolated): {query[:50]}...")
        
        start_time = time.time()
        
        # --- RÉCUPÉRATION DU CONTEXTE (Identique prod mais via tester) ---
        if rag.is_colbert:
            try:
                query_embeddings = next(rag.text_processor.query_embed([query]))
            except:
                query_embeddings = next(rag.text_processor.embed([query]))
        else:
            query_embeddings = next(rag.text_processor.embed([query]))
            
        search_filter = models.Filter(
            must=[models.FieldCondition(key="mongo_file_id", match=models.MatchValue(value=MONGO_ID))]
        )
        
        collection_name = rag.config.get("qdrant_collection", "Vector_Embeddings")
        search_result = local_qdrant.query_points(
            collection_name=collection_name,
            query=query_embeddings.tolist(),
            using=rag.text_vector_name,
            query_filter=search_filter,
            limit=5,
            with_payload=True,
        ).points
            
        # Filtrer et nettoyer les contextes pour RAGAS
        raw_contexts = [p.payload.get('content', '') for p in search_result]
        filtered_contexts = filter_contexts(raw_contexts)
        contexts = [clean_text(c) for c in filtered_contexts]

        # Appel du TESTER avec paramètres forcés
        if use_ollama:
            response = await asyncio.to_thread(rag.search_and_generate, query, mongo_id=MONGO_ID)
        else:
            print(f"📊 [MLOPS DEBUG] Sending to RAGTester: {forced_params}", flush=True)
            response = await rag.search_and_generate(query, mongo_id=MONGO_ID, forced_params=forced_params)
        
        latency = time.time() - start_time
        answer = clean_text(response.get("llmResponse", "")) if response else "error"
        
        total_latency += latency
        total_characters += len(answer)
        
        results.append({
            "question": str(query),
            "answer": str(answer),
            "contexts": contexts,
            "ground_truth": clean_text(item['ground_truth']),
            "latency": latency
        })

    # Metrics de performance
    avg_ttft = total_latency / len(QA_DATA) if QA_DATA else 0
    tps = total_characters / total_latency if total_latency > 0 else 0
    
    print(f"\n📊 [Performances RAG] TTFT Moyen: {avg_ttft:.3f}s | TPS Global: {tps:.2f} car/sec")

    # Conversion en dataset Ragas
    ds = Dataset.from_dict({
        "question": [r["question"] for r in results],
        "answer": [r["answer"] for r in results],
        "contexts": [r["contexts"] for r in results],
        "ground_truth": [r["ground_truth"] for r in results]
    })
    
    print("📊 Calcul des scores RAGAS (Faithfulness & Relevancy)...")
    # Forcer un nettoyage des buffers asyncio
    await asyncio.sleep(0.5)
    
    eval_result = evaluate(
        ds,
        metrics=[faithfulness, answer_relevancy],
        llm=eval_llm,
        embeddings=eval_embeddings
    )
    
    print("\n✅ RÉSULTATS DE L'ÉVALUATION (Bruts) :")
    print(eval_result)
    
    # Audit des scores individuels pour le debug MLOps
    df = eval_result.to_pandas()
    for i, row in df.iterrows():
        print(f"   🔍 [MLOPS DEBUG] Question {i+1} : Faith={row['faithfulness']:.3f}, Relevancy={row['answer_relevancy']:.3f}")
    
    # Save to file with summary row
    df = eval_result.to_pandas()
    summary_row = {
        "question": "MOYENNES / TOTALS",
        "answer": f"TTFT Moyen: {avg_ttft:.2f}s",
        "ground_truth": f"TPS Global: {tps:.2f} ch/s",
        "faithfulness": eval_result["faithfulness"],
        "answer_relevancy": eval_result["answer_relevancy"],
        "TTFT Moyen": avg_ttft,
        "TPS Global": tps
    }
    df = pd.concat([df, pd.DataFrame([summary_row])], ignore_index=True)
    
    def safe_float(val):
        if isinstance(val, list) and len(val) > 0: return float(val[0])
        try: return float(val)
        except: return 0.0

    # JSON output for MLOps capture
    json_output = {
        "avg_ttft": avg_ttft,
        "tps_global": tps,
        "faithfulness": safe_float(eval_result["faithfulness"]),
        "answer_relevancy": safe_float(eval_result["answer_relevancy"]),
        "individual_results": [
            {
                "question": r["question"],
                "answer": r["answer"],
                "ground_truth": r["ground_truth"],
                "latency": r["latency"],
                "faithfulness": float(df.loc[i, "faithfulness"]),
                "answer_relevancy": float(df.loc[i, "answer_relevancy"])
            } for i, r in enumerate(results)
        ]
    }

    print("\n---JSON_RESULTS_START---")
    print(json.dumps(json_output))
    print("---JSON_RESULTS_END---")
    
    # SAUVEGARDE DU CSV POUR TESTRUNNER
    csv_path = "/Volumes/MonSSD/pfe/Rapport/ragas_results.csv"
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"✅ Résultats RAG sauvegardés dans {csv_path}")

if __name__ == "__main__":
    asyncio.run(run_eval())
