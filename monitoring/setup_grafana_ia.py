import urllib.request
import json
import base64

GRAFANA_URL = "http://localhost:3000"
AUTH_BODY = "admin:admin"
AUTH_HEADER = f"Basic {base64.b64encode(AUTH_BODY.encode()).decode()}"

def grafana_request(path, method="GET", data=None):
    url = f"{GRAFANA_URL}{path}"
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", AUTH_HEADER)
    req.add_header("Content-Type", "application/json")
    body = json.dumps(data).encode("utf-8") if data else None
    try:
        with urllib.request.urlopen(req, data=body) as res:
            return json.loads(res.read().decode("utf-8")), res.status
    except Exception as e:
        print(f"❌ Erreur sur {path}: {e}")
        return None, 500

def create_mlops_dashboard():
    print("📊 Raffinement du Dashboard : Ajout du Pipeline de Flux AI...")
    
    # Mapping des services pour le trafic
    api_services = [
        ("/api/ai/orchestrate", "🧠 Cerveau RAG (Orchestration)"),
        ("/api/ai/upload-pdf-advanced", "🚀 Indexation Avancée (ColPali)"),
        ("/api/ai/upload-pdf", "📄 Indexation Standard"),
        ("/api/ai/tts", "🔊 Synthèse Vocale (TTS)"),
        ("/api/ai/classify-intent", "🗣️ Analyse Intention Vocale"),
        ("/api/ai/clarify-image", "👁️ Analyse Image (Vision)"),
        ("/api/admin/mlops/versions", "⚙️ Gestion des Modèles"),
        ("/api/admin/mlops/mongo/collections", "💾 Gestion Collections Mongo"),
        ("/api/admin/mlops/system/restart", "🔄 Redémarrage Services")
    ]

    traffic_targets = [
        {"expr": f"sum(rate(http_request_duration_seconds_count{{handler='{path}'}}[5m]))", "legendFormat": label}
        for path, label in api_services
    ]

    panels = [
        # --- LIGNE 1 : Statut de Santé (Chiffres/Statut) ---
        {"title": "🌐 État du Serveur Web", "type": "stat", "gridPos": {"h": 4, "w": 6, "x": 0, "y": 0}, 
         "description": "Indique si le service principal (FastAPI) répond. Si cette valeur est à 0, l'assistant ne pourra pas communiquer avec l'interface.",
         "targets": [{"expr": "up{job='fastapi-web'}"}], 
         "options": {"textMode": "value_and_name"},
         "fieldConfig": {"defaults": {"mappings": [{"options": {"0": {"color": "red", "text": "HORS LIGNE"}, "1": {"color": "green", "text": "OPÉRATIONNEL"}}, "type": "value"}]}}},
        
        {"title": "🤖 Workers IA Disponibles", "type": "stat", "gridPos": {"h": 4, "w": 6, "x": 6, "y": 0},
         "description": "Nombre de processus IA (Celery Workers) actuellement prêts à traiter des tâches d'indexation ou de synthèse.",
         "targets": [{"expr": "sum(celery_workers_online) or celery_active_worker_count"}]},

        {"title": "✅ Succès Indexation", "type": "stat", "gridPos": {"h": 4, "w": 6, "x": 12, "y": 0},
         "description": "Nombre total de documents PDF ayant été indexés avec succès. Cette valeur est cumulative et persiste même après un redémarrage.",
         "targets": [{"expr": "sum(increase(ia_indexing_success_total[30d])) or sum(celery_task_succeeded_total)"}], 
         "fieldConfig": {"defaults": {"color": {"mode": "fixed", "fixedColor": "green"}}}},

        {"title": "❌ Échecs Détectés", "type": "stat", "gridPos": {"h": 4, "w": 6, "x": 18, "y": 0},
         "description": "Nombre total d'erreurs rencontrées. Cette valeur cumule tous les échecs détectés sur les 30 derniers jours.",
         "targets": [{"expr": "sum(increase(ia_indexing_failure_total[30d])) or sum(celery_task_failed_total)"}], 
         "fieldConfig": {"defaults": {"color": {"mode": "fixed", "fixedColor": "red"}}}},

        # --- LIGNE 2 : Performance Technique (Chiffres direct) ---
        {"title": "⚡ Vitesse Globale d'Analyse (ko/s)", "type": "stat", "gridPos": {"h": 5, "w": 8, "x": 0, "y": 4},
         "description": "Vitesse moyenne de traitement des PDF depuis le démarrage. Calcule le ratio Taille/Temps pour évaluer l'efficacité du matériel.",
         "targets": [
             {"expr": "sum(ia_indexing_size_bytes_total) / sum(ia_indexing_duration_seconds_sum) / 1024", "legendFormat": "Global"}
         ], "options": {"graphMode": "none"}},
        
        {"title": "⏱️ Latence Premier Token (TTFT)", "type": "stat", "gridPos": {"h": 5, "w": 8, "x": 8, "y": 4},
         "description": "Délai moyen (en secondes) avant que l'IA ne commence à répondre. Moyenne calculée sur l'ensemble des sessions des 30 derniers jours pour assurer la continuité après redémarrage.",
         "targets": [{"expr": "sum(increase(ia_llm_ttft_seconds_sum[30d])) / sum(increase(ia_llm_ttft_seconds_count[30d]))"}],
         "fieldConfig": {"defaults": {"unit": "s", "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "orange", "value": 1.5}, {"color": "red", "value": 3}]}}}},

        {"title": "🚀 Rapidité de Génération (TPS)", "type": "stat", "gridPos": {"h": 5, "w": 8, "x": 16, "y": 4},
         "description": "Vitesse moyenne de débit du texte (Tokens par seconde) calculée sur les 30 derniers jours. Persiste après redémarrage.",
         "targets": [{"expr": "sum(increase(ia_llm_tps_tokens_per_second_sum[30d])) / sum(increase(ia_llm_tps_tokens_per_second_count[30d]))"}],
         "fieldConfig": {"defaults": {"unit": "dtdfr"}}},

        # --- LIGNE 3 : VOLUME ET TRAFIC (Graphique pour la visibilité historique) ---
        {"title": "📈 Historique d'Activité par Service", "type": "timeseries", "gridPos": {"h": 10, "w": 24, "x": 0, "y": 9},
         "description": "Visualisation temporelle de l'utilisation des différents services (Orchestration, Vision, TTS). Permet d'identifier les pics de charge.",
         "targets": [
             {"expr": f"sum by (handler) (rate(http_requests_total{{handler='{path}'}}[5m]))", "legendFormat": label}
             for path, label in api_services
         ],
         "options": {
             "legend": {"displayMode": "table", "placement": "right", "calcs": ["last", "sum"]}
         }}
    ]

    dashboard = {
        "dashboard": {
            "uid": "mlops-dashboard",
            "title": "Monitoring IA : Statut & Performances",
            "tags": ["mlops", "ia", "simplified"],
            "timezone": "browser",
            "schemaVersion": 16,
            "version": 8,
            "panels": panels
        },
        "overwrite": True
    }

    res, status = grafana_request("/api/dashboards/db", method="POST", data=dashboard)
    if status == 200:
        print("✅ Dashboard mis à jour : Pipeline de Flux AI ajouté.")
    else:
        print(f"❌ Erreur dashboard ({status})")

if __name__ == "__main__":
    create_mlops_dashboard()
