import requests
import json

ollama_url = "http://localhost:11434"
model = "qwen3.5:9b"

payload = {
    "model": model,
    "messages": [
        {
            "role": "system",
            "content": "Tu es un assistant expert qui aide les étudiants à comprendre leur cours."
        },
        {
            "role": "user",
            "content": "En utilisant uniquement les extraits de cours fournis ci-dessous, réponds à la question de l'utilisateur.\n\nQUESTION : \"Citer, sans les décrire, les 3 portions de l’Oesophage.\"\n\nCONTEXTE EXTRAIT DU COURS :\nL'oesophage a 3 portions: cervicale, thoracique, abdominale.\n\nRéponds en JSON avec exactement ces deux clés (sans aucun autre texte) :\n{\"llmResponse\": \"Réponse technique et précise en français.\", \"simpleExample\": \"Explication simplifiée pour un étudiant.\"}"
        }
    ],
    "stream": False,
    "options": {
        "num_predict": 400,
        "temperature": 0.7
    }
}

print(f"Testing {model} with /api/chat...")
response = requests.post(f"{ollama_url}/api/chat", json=payload, timeout=120)

print(f"Status Code: {response.status_code}")
try:
    data = response.json()
    print("Response JSON Keys:", data.keys())
    reply = data.get("message", {}).get("content", "")
    print("Content Length:", len(reply))
    print("Raw text returned:")
    print("--- START ---")
    print(reply)
    print("--- END ---")
except Exception as e:
    print("Raw output not JSON:", response.text)
