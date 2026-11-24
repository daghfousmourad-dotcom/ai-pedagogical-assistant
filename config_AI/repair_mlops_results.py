import json
import os
import pandas as pd

def repair_csv():
    progress_file = "/Volumes/MonSSD/pfe/test-microservices/config_AI/results/progress.json"
    target_csv = "/Volumes/MonSSD/pfe/test-microservices/config_AI/results/phase2_results.csv"
    
    if not os.path.exists(progress_file):
        print(f"❌ Error: {progress_file} not found")
        return

    with open(progress_file, "r") as f:
        data = json.load(f)

    phase2_results = data.get("phase2_results", [])
    if not phase2_results:
        print("❌ Error: No phase2_results found in progress.json")
        return

    print(f"📊 Found {len(phase2_results)} results in progress.json")

    # Create DataFrame from all results
    df = pd.DataFrame(phase2_results)

    # Re-order columns to put diagnostic info first, then answers
    # Standard columns from ReportGenerator (approx 21)
    base_cols = [
        "config_id", "text_model", "llm_provider", "llm_model", "vision_cuda", "vision_cpu",
        "temperature", "top_p", "freq_penalty", "pres_penalty", "status", "error",
        "rag_faithfulness", "rag_relevancy", "rag_faithfulness_avg", "rag_relevancy_avg",
        "rag_ttft", "rag_tps", "img_faithfulness", "img_relevancy", "img_faithfulness_avg", "img_relevancy_avg"
    ]
    
    # Answers columns (Dynamic)
    answer_cols = sorted([col for col in df.columns if "_answer" in col])
    
    # Final column list (ordered)
    final_cols = [col for col in base_cols if col in df.columns] + answer_cols
    df = df[final_cols]

    # Save to CSV (Overwrite to clean corruption)
    df.to_csv(target_csv, index=False, encoding='utf-8-sig')
    print(f"✅ Successfully repaired {target_csv}")
    print(f"✅ Final record count: {len(df)}")

if __name__ == "__main__":
    repair_csv()
