"""
report_generator.py
-------------------
Consolide les résultats de chaque test dans un fichier CSV centralisé.
Gère aussi la sauvegarde de progress.json pour la reprise après interruption.
"""
import os
import json
import pandas as pd

class ReportGenerator:
    def __init__(self, results_dir="/Volumes/MonSSD/pfe/test-microservices/config_AI/results"):
        self.results_dir = results_dir
        self.progress_file = os.path.join(results_dir, "progress.json")
        self.phase1_csv = os.path.join(results_dir, "phase1_results.csv")
        self.phase2_csv = os.path.join(results_dir, "phase2_results.csv")
        self.csv_file = self.phase1_csv # Compatibility
        self.errors_file = os.path.join(results_dir, "error_report.json")
        
        if not os.path.exists(results_dir):
            os.makedirs(results_dir)

    def load_progress(self):
        """Charge l'état d'avancement pour reprendre le test."""
        if os.path.exists(self.progress_file):
            with open(self.progress_file, "r") as f:
                return json.load(f)
        return {"current_phase": 1, "completed_configs": [], "phase1_results": []}

    def save_progress(self, progress_data):
        """Sauvegarde l'état d'avancement."""
        with open(self.progress_file, "w") as f:
            json.dump(progress_data, f, indent=4)

    def add_result(self, config, rag_metrics, img_metrics, status="success", error="", phase=1):
        """Ajoute un résultat à la liste globale et met à jour le CSV correspondant à la phase."""
        result = {
            "config_id": config["version_name"],
            "text_model": config["text_model"],
            "llm_provider": config["llm_provider"],
            "llm_model": config["llm_model"],
            "vision_cuda": config["vision_model_cuda"],
            "vision_cpu": config["vision_model_cpu"],
            "temperature": config["llm_temperature"],
            "top_p": config["llm_top_p"],
            "freq_penalty": config["llm_frequency_penalty"],
            "pres_penalty": config["llm_presence_penalty"],
            "status": status,
            "error": error
        }

        def calculate_avg(val):
            if isinstance(val, (int, float)):
                return val
            if isinstance(val, str):
                try:
                    import ast
                    import re
                    # Nettoyer les chaines np.float64(...) -> ...
                    cleaned_val = re.sub(r"np\.float\d+\((.*?)\)", r"\1", val)
                    data = ast.literal_eval(cleaned_val)
                    if isinstance(data, list) and len(data) > 0:
                        avg = sum(data) / len(data)
                        return round(avg, 3)
                except:
                    pass
            return 0

        # Intégrer les métriques RAG (si présentes)
        if rag_metrics:
            f_val = rag_metrics.get("faithfulness", 0)
            r_val = rag_metrics.get("answer_relevancy", 0)
            result.update({
                "rag_faithfulness": f_val,
                "rag_relevancy": r_val,
                "rag_faithfulness_avg": calculate_avg(f_val),
                "rag_relevancy_avg": calculate_avg(r_val),
                "rag_ttft": rag_metrics.get("TTFT Moyen", 0),
                "rag_tps": rag_metrics.get("TPS Global", 0)
            })
            # Intégrer les réponses IA si disponibles dans json_data
            if "json_data" in rag_metrics:
                jd = rag_metrics["json_data"]
                if "individual_results" in jd:
                    for i, r in enumerate(jd["individual_results"]):
                        result[f"rag_q{i+1}_answer"] = r.get("answer", "")

        # Intégrer les métriques Image (si présentes)
        if img_metrics:
            f_val = img_metrics.get("faithfulness", 0)
            r_val = img_metrics.get("answer_relevancy", 0)
            
            result.update({
                "img_faithfulness": f_val,
                "img_relevancy": r_val,
                "img_faithfulness_avg": calculate_avg(f_val),
                "img_relevancy_avg": calculate_avg(r_val),
                "img_ttft": round(img_metrics.get("TTFT Moyen", 0), 3),
                "img_tps": round(img_metrics.get("TPS Global", 0), 3)
            })
            # Intégrer les réponses IA si disponibles dans json_data
            if "json_data" in img_metrics:
                jd = img_metrics["json_data"]
                if "individual_results" in jd:
                    for i, r in enumerate(jd["individual_results"]):
                        result[f"img_q{i+1}_answer"] = r.get("answer", "")

        # Arrondir les scores RAG TTFT/TPS s'ils existent
        if "rag_ttft" in result:
             result["rag_ttft"] = round(result["rag_ttft"], 3)
             result["rag_tps"] = round(result["rag_tps"], 3)

        # ROBUST CSV UPDATE: Read, Concat, Overwrite (safely handles dynamic columns)
        target_csv = self.phase2_csv if phase == 2 else self.phase1_csv
        
        if os.path.exists(target_csv):
            try:
                # Use low_memory=False to avoid DtypeWarning
                existing_df = pd.read_csv(target_csv, low_memory=False)
                # Concatenate with the result (result is already a dict, convert to DF)
                new_df = pd.DataFrame([result])
                # concat handles different columns by adding NaNs/Empty
                df = pd.concat([existing_df, new_df], ignore_index=True)
                # Save the whole thing back
                df.to_csv(target_csv, index=False, encoding='utf-8-sig')
            except Exception as e:
                print(f"   ⚠️ Warning: CSV update failed ({e}). Falling back to fresh file.")
                pd.DataFrame([result]).to_csv(target_csv, index=False, encoding='utf-8-sig')
        else:
            pd.DataFrame([result]).to_csv(target_csv, index=False, encoding='utf-8-sig')

        return result

        return result

    def log_error(self, config, error_msg):
        """Log un crash spécifique pour analyse ultérieure."""
        error_entry = {
            "version_name": config["version_name"],
            "config": config,
            "error": error_msg
        }
        
        errors = []
        if os.path.exists(self.errors_file):
            with open(self.errors_file, "r") as f:
                errors = json.load(f)
        
        errors.append(error_entry)
        
        with open(self.errors_file, "w") as f:
            json.dump(errors, f, indent=4)
