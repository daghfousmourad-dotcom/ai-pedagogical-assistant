#!/bin/bash
# Script de lancement avec MLOps Metrics activé

cd /Volumes/MonSSD/pfe/test-microservices/FastAPI

echo "🧹 Nettoyage des anciennes métriques..."
mkdir -p /tmp/metrics
rm -f /tmp/metrics/*

export PROMETHEUS_MULTIPROC_DIR=/tmp/metrics

echo "🚀 Lancement de FastAPI..."
source .venv/bin/activate
nohup uvicorn main:app --host 0.0.0.0 --port 5005 > fastapi_mlops.log 2>&1 &
FASTAPI_PID=$!

echo "🧠 Lancement du Worker Celery..."
nohup celery -A celery_worker.celery_app worker --loglevel=info > celery_mlops.log 2>&1 &
CELERY_PID=$!

echo "✅ Services lancés en arrière-plan !"
echo "FastAPI PID: $FASTAPI_PID"
echo "Celery PID: $CELERY_PID"
echo "Les métriques sont désormais synchronisées dans /tmp/metrics"
