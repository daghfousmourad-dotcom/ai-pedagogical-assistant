#!/bin/bash
# setup_venv.sh
# Initialise l'environnement virtuel pour le projet config_AI

cd /Volumes/MonSSD/pfe/test-microservices/config_AI

echo "📦 Création de l'environnement virtuel..."
python3 -m venv .venv

echo "🚀 Activation et installation des dépendances..."
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "✅ Configuration terminée."
echo "Pour lancer les tests : source .venv/bin/activate && python mlops_tester.py"
