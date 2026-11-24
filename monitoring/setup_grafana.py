import urllib.request
import json
import time

GRAFANA_URL = "http://localhost:3000"
AUTH_BODY = "admin:admin"
import base64
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

def setup_prometheus_datasource():
    print("🔍 Vérification de la source de données Prometheus...")
    datasources, status = grafana_request("/api/datasources")
    if datasources and any(ds['name'] == 'Prometheus' for ds in datasources):
        print("✅ Source Prometheus déjà configurée.")
        return
    
    payload = {
        "name": "Prometheus",
        "type": "prometheus",
        "url": "http://prometheus:9090",
        "access": "proxy",
        "isDefault": True
    }
    grafana_request("/api/datasources", method="POST", data=payload)
    print("✅ Source Prometheus ajoutée avec succès.")

def create_mlops_dashboard():
    print("📊 Création du Dashboard MLOps Simplifié...")
    
    panels = [
        {"title": "Statut API FastAPI", "type": "stat", "gridPos": {"h": 4, "w": 6, "x": 0, "y": 0}, 
         "targets": [{"expr": "up{job='fastapi-web'}"}]},
        {"title": "Workers Celery", "type": "stat", "gridPos": {"h": 4, "w": 6, "x": 6, "y": 0},
         "targets": [{"expr": "celery_active_worker_count"}]},
        {"title": "Indexations Réussies", "type": "stat", "gridPos": {"h": 4, "w": 6, "x": 12, "y": 0},
         "targets": [{"expr": "sum(celery_task_succeeded_total)"}]},
        {"title": "Échecs Indexation", "type": "stat", "gridPos": {"h": 4, "w": 6, "x": 18, "y": 0},
         "targets": [{"expr": "sum(celery_task_failed_total)"}]},
        {"title": "Trafic API (Req/sec)", "type": "timeseries", "gridPos": {"h": 8, "w": 12, "x": 0, "y": 4},
         "targets": [{"expr": "rate(http_request_duration_seconds_count[5m])"}]},
        {"title": "Latence API (ms)", "type": "timeseries", "gridPos": {"h": 8, "w": 12, "x": 12, "y": 4},
         "targets": [{"expr": "rate(http_request_duration_seconds_sum[5m]) / rate(http_request_duration_seconds_count[5m]) * 1000"}]},
        {"title": "Files d'attente (Queue)", "type": "gauge", "gridPos": {"h": 8, "w": 8, "x": 0, "y": 12},
         "targets": [{"expr": "celery_queue_length"}]},
        {"title": "Tâches en cours", "type": "stat", "gridPos": {"h": 8, "w": 8, "x": 8, "y": 12},
         "targets": [{"expr": "sum(celery_worker_tasks_active)"}]},
        {"title": "Retries (IA)", "type": "stat", "gridPos": {"h": 4, "w": 8, "x": 16, "y": 12},
         "targets": [{"expr": "sum(celery_task_retried_total)"}]},
        {"title": "Tâches Annulées", "type": "stat", "gridPos": {"h": 4, "w": 8, "x": 16, "y": 16},
         "targets": [{"expr": "sum(celery_task_revoked_total)"}]}
    ]

    dashboard = {
        "dashboard": {
            "uid": "mlops-dashboard",
            "title": "MLOps Dashboard",
            "tags": ["mlops"],
            "timezone": "browser",
            "schemaVersion": 16,
            "version": 1,
            "panels": panels
        },
        "overwrite": True
    }

    res, status = grafana_request("/api/dashboards/db", method="POST", data=dashboard)
    if status == 200:
        print("✅ Dashboard 'mlops-dashboard' créé/mis à jour.")
    else:
        print(f"❌ Erreur dashboard ({status})")

if __name__ == "__main__":
    setup_prometheus_datasource()
    create_mlops_dashboard()
