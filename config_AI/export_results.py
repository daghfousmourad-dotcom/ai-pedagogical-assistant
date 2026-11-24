import json
import csv
import os

def format_val(val):
    if val is None: return ""
    if isinstance(val, (int, float)):
        return round(float(val), 3)
    if isinstance(val, str) and val.startswith("np.float64"):
        try:
            num = float(val.split('(')[1].split(')')[0])
            return round(num, 3)
        except:
            return val
    return val

def export_to_csv():
    progress_path = "/Volumes/MonSSD/pfe/test-microservices/config_AI/results/progress.json"
    if not os.path.exists(progress_path):
        print("Progress file not found.")
        return

    with open(progress_path, 'r') as f:
        data = json.load(f)

    # Export Phase 1
    p1_results = data.get("phase1_results", [])
    if p1_results:
        all_keys = set()
        for row in p1_results:
            all_keys.update(row.keys())
        
        with open("/Volumes/MonSSD/pfe/Rapport/phase1_results.csv", 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=sorted(list(all_keys)))
            writer.writeheader()
            for row in p1_results:
                formatted_row = {k: format_val(row.get(k)) for k in all_keys}
                writer.writerow(formatted_row)
        print("Generated phase1_results.csv")

    # Export Phase 2
    p2_results = data.get("phase2_results", [])
    if p2_results:
        all_keys = set()
        for row in p2_results:
            all_keys.update(row.keys())
            
        with open("/Volumes/MonSSD/pfe/Rapport/phase2_results.csv", 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=sorted(list(all_keys)))
            writer.writeheader()
            for row in p2_results:
                formatted_row = {k: format_val(row.get(k)) for k in all_keys}
                writer.writerow(formatted_row)
        print("Generated phase2_results.csv")

if __name__ == "__main__":
    export_to_csv()
