import requests
import json
import time
from pymongo import MongoClient

FASTAPI_URL = "http://localhost:5005"
MONGO_URI = "mongodb://localhost:27017/"

def main():
    print("=== Test de commutation LLM (OpenAI <-> Ollama) ===")
    
    # 1. Trouver le document
    client = MongoClient(MONGO_URI)
    db = client["EduAIVision"]
    doc = db["pdf_documents"].find_one({"filename": {"$regex": "Les conteneurs", "$options": "i"}, "user_email": "test1@test.com"})
    
    if not doc:
        print("❌ Document 'Les conteneurs.pdf' pour test1@test.com non trouvé.")
        doc = db["pdf_documents"].find_one({"filename": {"$regex": "conteneur", "$options": "i"}})
        if not doc:
            print("❌ Aucun document avec 'conteneur' trouvé. Test annulé.")
            return
        else:
            print(f"⚠️ Document trouvé mais avec email différent: {doc.get('user_email')} - {doc.get('filename')}")
    
    mongo_file_id = str(doc["_id"])
    print(f"✅ Document trouvé. ID: {mongo_file_id}")
    
    # Payload pour orchestrator
    payload = {
        "command": "SYNC",
        "mongo_file_id": mongo_file_id,
        "current_page": 5,
        "speech_text": "c'est quoi un conteneur ?",
        "role": "PROFESSOR"
    }
    
    # 2. Configurer OpenAI
    print("\n--- 1. Configuration de OpenAI ---")
    openai_config = {
        "config_name": "Test_OpenAI",
        "llm_provider": "OPENAI",
        "llm_model": "gpt-4o-mini",
        "llm_temperature": 0.7,
        "llm_max_tokens": 200,
        "llm_top_p": 1.0,
        "llm_frequency_penalty": 0.0,
        "llm_presence_penalty": 0.0,
        "stt_provider": "OPENAI",
        "tts_provider": "OPENAI"
    }
    requests.post(f"{FASTAPI_URL}/api/admin/mlops/llm-configs", json=openai_config)
    requests.put(f"{FASTAPI_URL}/api/admin/mlops/llm-configs/Test_OpenAI/activate")
    print("✅ OpenAI activé.")
    
    print("⏳ Appel à l'orchestrateur (OpenAI)...")
    start = time.time()
    try:
        res = requests.post(f"{FASTAPI_URL}/api/ai/orchestrate", json=payload)
        duration = time.time() - start
        print(f"✅ Réponse OpenAI ({duration:.2f}s) :")
        print(res.json().get('data', {}).get('ai_speech', 'Pas de texte'))
    except Exception as e:
        print("❌ Erreur:", e)
        
    # 3. Configurer Ollama
    print("\n--- 2. Configuration de Ollama ---")
    ollama_config = {
        "config_name": "Test_Ollama",
        "llm_provider": "OLLAMA",
        "llm_model": "llama3.1:8b",
        "llm_temperature": 0.7,
        "llm_max_tokens": 200,
        "llm_top_p": 1.0,
        "llm_frequency_penalty": 0.0,
        "llm_presence_penalty": 0.0,
        "stt_provider": "OPENAI",
        "tts_provider": "OPENAI"
    }
    requests.post(f"{FASTAPI_URL}/api/admin/mlops/llm-configs", json=ollama_config)
    requests.put(f"{FASTAPI_URL}/api/admin/mlops/llm-configs/Test_Ollama/activate")
    print("✅ Ollama activé.")
    
    print("⏳ Appel à l'orchestrateur (Ollama)...")
    start = time.time()
    try:
        res = requests.post(f"{FASTAPI_URL}/api/ai/orchestrate", json=payload)
        duration = time.time() - start
        print(f"✅ Réponse Ollama ({duration:.2f}s) :")
        print(res.json().get('data', {}).get('ai_speech', 'Pas de texte'))
    except Exception as e:
        print("❌ Erreur:", e)

if __name__ == "__main__":
    main()
