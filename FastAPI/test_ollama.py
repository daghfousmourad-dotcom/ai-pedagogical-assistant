import requests

payload = {
    "model": "qwen3.5:9b",
    "prompt": "Citer les 3 portions de l'oesophage. Format JSON {'llmResponse': '...'} uniquement.",
    "stream": False,
    "options": {
        "num_predict": 100,
        "num_ctx": 4096
    }
}
resp = requests.post("http://localhost:11434/api/generate", json=payload, timeout=60)
print(resp.json().get("response", "EMPTY"))
