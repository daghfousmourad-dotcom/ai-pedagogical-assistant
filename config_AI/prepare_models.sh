#!/bin/bash
# prepare_models.sh
# Télécharge et prépare tous les modèles Ollama requis sur /Volumes/MonSSD

# Vérification que le stockage Ollama pointe bien vers MonSSD
if [[ "$OLLAMA_MODELS" != "/Volumes/MonSSD/ollama" ]]; then
    echo "⚠️  ATTENTION: OLLAMA_MODELS n'est pas configuré sur MonSSD."
    echo "   Définissez: export OLLAMA_MODELS=/Volumes/MonSSD/ollama"
    echo "   Ajoutez cette ligne dans votre ~/.zshrc pour la rendre permanente."
    exit 1
fi

echo "✅ Stockage Ollama: $OLLAMA_MODELS"
echo ""
echo "📦 Modèles actuellement disponibles:"
ollama list
echo ""

# --- Modèles requis pour les tests ---
REQUIRED_MODELS=(
    "qwen3.5:9b"
)

echo "🚀 Vérification et téléchargement des modèles requis..."
for model in "${REQUIRED_MODELS[@]}"; do
    if ollama list | grep -q "$model"; then
        echo "  ✅ $model : déjà disponible"
    else
        echo "  ⬇️  Téléchargement de $model sur MonSSD..."
        ollama pull "$model"
        if [ $? -eq 0 ]; then
            echo "  ✅ $model : téléchargé avec succès"
        else
            echo "  ❌ $model : échec du téléchargement"
        fi
    fi
done

echo ""
echo "📦 Modèles disponibles après préparation:"
ollama list
echo ""
echo "✅ Préparation terminée. Vous pouvez relancer mlops_tester.py"
