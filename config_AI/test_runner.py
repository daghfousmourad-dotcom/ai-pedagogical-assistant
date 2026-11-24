"""
test_runner.py
--------------
Exécute les scripts d'évaluation existants (RAG et Image) en subprocess.
Capture les métriques finales depuis les fichiers générés ou la sortie console.
"""
import subprocess
import os
import json
import time

class TestRunner:
    def __init__(self, root_path="/Volumes/MonSSD/pfe/test-microservices/FastAPI"):
        self.root_path = root_path
        self.venv_python = os.path.join(root_path, ".venv/bin/python3")
        self.rag_script = os.path.join(root_path, "evaluate_rag.py")
        self.image_script = os.path.join(root_path, "evaluate_image.py")
        self.indexing_script = "/Volumes/MonSSD/pfe/test-microservices/config_AI/trigger_indexing.py"
        self.results_csv = "/Volumes/MonSSD/pfe/Rapport/ragas_results.csv"
        self.results_image_csv = "/Volumes/MonSSD/pfe/Rapport/image_clarifier_results.csv"

    def run_eval_rag(self):
        """Lance evaluate_rag.py et extrait les moyennes."""
        return self._run_script(self.rag_script, "rag")

    def run_indexing(self):
        """Lance trigger_indexing.py pour re-indexer le fichier avec le nouveau modèle."""
        print(f"   ▶️  Re-indexation du fichier test (Modèle: Active Config)...")
        try:
            # On utilise le venv de FastAPI pour avoir accès aux modèles d'embedding et Qdrant
            result = subprocess.run(
                [self.venv_python, self.indexing_script],
                cwd=os.path.dirname(self.indexing_script),
                start_new_session=True,
                timeout=7200 # 2 hours max for indexing
            )
            if result.returncode != 0:
                 return {"status": "error", "error": f"L'indexation a échoué (code {result.returncode})"}
            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def run_eval_image(self):
        """Lance evaluate_image.py et extrait les moyennes.
        On supprime d'abord le cache pour forcer un vrai test.
        """
        cache_file = "/tmp/image_eval_cache.json"
        if os.path.exists(cache_file):
            os.remove(cache_file)
        return self._run_script(self.image_script, "image")

    def _run_script(self, script_path, test_type):
        """Exécute un script et tente de lire les dernières lignes de son CSV de sortie."""
        print(f"   ▶️  Exécution de {os.path.basename(script_path)}...")
        
        try:
            # On lance le test en capturant la sortie pour parser le JSON
            result = subprocess.run(
                [self.venv_python, script_path],
                cwd=self.root_path,
                capture_output=True,
                text=True,
                start_new_session=True,
                timeout=3600
            )

            # Afficher quand même la sortie dans la console pour le suivi live
            print(result.stdout)
            if result.stderr:
                print(result.stderr)
            
            if result.returncode != 0:
                error_msg = f"Le script s'est terminé avec le code {result.returncode}. Vérifiez les sorties ci-dessus."
                return {"status": "error", "error": error_msg}

            # Parsing du bloc JSON dans la sortie console
            json_metrics = {}
            if "---JSON_RESULTS_START---" in result.stdout:
                try:
                    parts = result.stdout.split("---JSON_RESULTS_START---")[1].split("---JSON_RESULTS_END---")
                    json_metrics = json.loads(parts[0].strip())
                except Exception as e:
                    print(f"   ⚠️  Erreur parsing JSON results: {e}")

            # Lecture du CSV de sortie pour extraire les moyennes (dernière ligne)
            target_csv = self.results_csv if test_type == "rag" else self.results_image_csv
            
            if os.path.exists(target_csv):
                import pandas as pd
                try:
                    df = pd.read_csv(target_csv)
                    if df.empty:
                         return {"status": "error", "error": "Fichier CSV vide"}
                    # On cherche la ligne de résumé
                    summary = df.iloc[-1].to_dict()
                    # Fusionner avec les données JSON (qui contiennent les réponses brutes)
                    if json_metrics:
                        summary["json_data"] = json_metrics
                    return {"status": "success", "metrics": summary}
                except Exception as e:
                    return {"status": "error", "error": f"Erreur lecture CSV: {e}"}
            else:
                return {"status": "error", "error": f"Fichier CSV non trouvé: {target_csv}"}

        except subprocess.TimeoutExpired:
            return {"status": "error", "error": f"Timeout (Délai dépassé après {test_type})"}
        except Exception as e:
            return {"status": "error", "error": str(e)}
