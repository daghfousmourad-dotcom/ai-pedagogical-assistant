import asyncio
import os
import sys
import numpy as np
import time

# Add core path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock Navigator that loads real PDF
class MockSmartCourseNavigator:
    def __init__(self, pdf_path):
        self.pdf_path = pdf_path
        
    def get_page_word_map(self, mongo_id, page_num):
        import fitz  # PyMuPDF
        if not os.path.exists(self.pdf_path):
            print(f"❌ PDF not found at {self.pdf_path}")
            return []
            
        try:
            doc = fitz.open(self.pdf_path)
            if page_num > len(doc):
                doc.close()
                return []
                
            page = doc[page_num - 1]
            page_height = page.rect.height
            words = page.get_text("words")
            doc.close()
            
            # Spatial sorting (reading order)
            words_sorted = sorted(words, key=lambda w: (round(w[1] / 5) * 5, w[0]))
            
            result = []
            for i, w in enumerate(words_sorted):
                y0_inv = page_height - w[3]
                y1_inv = page_height - w[1]
                result.append({
                    "text": w[4],
                    "bbox": [w[0], y0_inv, w[2], y1_inv],
                    "index": i
                })
            return result
        except Exception as e:
            print(f"❌ Error extracting words: {e}")
            return []

# Load the implementations
from services.core.surlignage import HighlightLogic as HighlightLogicV1
from services.core.surlignage_v2 import HighlightLogicV2
from services.core.surlignage_v3 import HighlightLogic as HighlightLogicV3

# Define test paths
PDF_PATH = "/Volumes/MonSSD/pfe/test-microservices/shared_uploads/Les conteneurs.pdf"

async def run_audit():
    print("=" * 70)
    print("🔬 COMPARAISON DES VERSIONS DE SURLIGNAGE (AUDIT DE PRÉCISION)")
    print("=" * 70)
    
    mock_nav = MockSmartCourseNavigator(PDF_PATH)
    
    # Instantiate all three logics
    hl_v1 = HighlightLogicV1(mock_nav)
    hl_v2 = HighlightLogicV2(mock_nav)
    hl_v3 = HighlightLogicV3(mock_nav)
    
    # Audit cases (based on audit_surlignage_unique.py)
    audit_tests = [
        # PAGE 5
        {"page": 5, "word": "intégration", "expected_idx": 3, "speech": "Utilisation pour de l'intégration"},
        {"page": 5, "word": "Environnement", "expected_idx": 7, "speech": "continue, c.I. Environnement"},
        {"page": 5, "word": "conteneur (Whisper: cantonneur)", "expected_idx": 31, "speech": "Un nouveau cantonneur"},
        {"page": 5, "word": "exécutions", "expected_idx": 51, "speech": "plusieurs executions"},
        
        # PAGE 6
        {"page": 6, "word": "distribution", "expected_idx": 3, "speech": "Utilisation pour la distribution"},
        {"page": 6, "word": "Dockerfiles (Whisper: Docker5)", "expected_idx": 12, "speech": "à partir de Docker5"},
        {"page": 6, "word": "pérenne", "expected_idx": 21, "speech": "stockage pérenne"},
        {"page": 6, "word": "dépendances", "expected_idx": 36, "speech": "toutes les dépendances"}
    ]
    
    logics = [
        {"name": "Version 1 (Originale)", "instance": hl_v1, "version": 1},
        {"name": "Version 2 (FA / NLP Fallback)", "instance": hl_v2, "version": 2},
        {"name": "Version 3 (Production V6 Finale)", "instance": hl_v3, "version": 3}
    ]
    
    results_summary = {}
    
    for logic in logics:
        name = logic["name"]
        hl = logic["instance"]
        v_num = logic["version"]
        
        print(f"\n🏃 Exécution des tests pour : {name}...")
        
        last_word_index = 0
        current_page = None
        
        passed = 0
        near = 0
        failed = 0
        total_time = 0
        
        test_details = []
        
        for t in audit_tests:
            if t["page"] != current_page:
                current_page = t["page"]
                last_word_index = 0
                if hasattr(hl, 'reset_cursor'):
                    hl.reset_cursor()
            
            speech = t["speech"]
            word_label = t["word"]
            expected = t["expected_idx"]
            
            start_time = time.perf_counter()
            res = await hl.get_highlight("dummy_mongo_id", current_page, speech, last_word_index)
            end_time = time.perf_counter()
            duration = (end_time - start_time) * 1000  # ms
            total_time += duration
            
            actual_idx = None
            detected_text = ""
            bboxes = []
            
            if res:
                if isinstance(res, dict):
                    actual_idx = res.get("index")
                    detected_text = res.get("text", "")
                    bboxes = [res.get("bbox")] if "bbox" in res else []
                else:  # Object like HighlightResult
                    actual_idx = getattr(res, "index", None)
                    detected_text = getattr(res, "text", "")
                    if hasattr(res, "bboxes"):
                        bboxes = getattr(res, "bboxes", [])
                    elif hasattr(res, "bbox"):
                        bboxes = [getattr(res, "bbox")]
            
            status = "FAIL"
            if actual_idx == expected:
                status = "PASS"
                passed += 1
            elif actual_idx is not None and abs(actual_idx - expected) <= 1:
                status = "NEAR"
                near += 1
            else:
                failed += 1
                
            print(f"  [{status}] Mot: '{word_label}' | Attendu: {expected} | Obtenu: {actual_idx} | Texte: '{detected_text}' | Temps: {duration:.2f}ms")
            
            if actual_idx is not None:
                last_word_index = actual_idx
                
            test_details.append({
                "page": current_page,
                "word": word_label,
                "expected": expected,
                "actual": actual_idx,
                "status": status,
                "text": detected_text,
                "bboxes": bboxes,
                "time_ms": duration
            })
            
        results_summary[name] = {
            "passed": passed,
            "near": near,
            "failed": failed,
            "avg_time_ms": total_time / len(audit_tests),
            "details": test_details
        }
        
    # --- DISPLAY COMPARISON TABLE ---
    print("\n" + "=" * 80)
    print(f"{'VERSION':<30} | {'PASS':<6} | {'NEAR':<6} | {'FAIL':<6} | {'TEMPS MOY':<12}")
    print("=" * 80)
    for name, stats in results_summary.items():
        print(f"{name:<30} | {stats['passed']:<6} | {stats['near']:<6} | {stats['failed']:<6} | {stats['avg_time_ms']:<8.2f} ms")
    print("=" * 80)
    
    # --- MULTI-LINE HIGHLIGHTING ANALYSIS ---
    print("\n🔬 ANALYSE DES LIMITATIONS MULTI-LIGNES")
    print("=" * 80)
    print("Test d'une phrase qui dépasse une seule ligne physique dans le PDF:")
    # On choisit un segment plus long sur la page 5 pour forcer le saut de ligne
    long_speech = "utilisation pour de l'intégration continue c.I. Environnement de test créé à partir d'une image docker"
    
    for name, hl in [(l["name"], l["instance"]) for l in logics]:
        if hasattr(hl, 'reset_cursor'): hl.reset_cursor()
        res = await hl.get_highlight("dummy_mongo_id", 5, long_speech, 0)
        
        if res:
            if isinstance(res, dict):
                bboxes = [res.get("bbox")] if "bbox" in res else []
                text = res.get("text", "")
            else:
                text = getattr(res, "text", "")
                if hasattr(res, "bboxes"):
                    bboxes = getattr(res, "bboxes", [])
                else:
                    bboxes = [getattr(res, "bbox")]
            print(f"- {name:<30} -> Texte surligné: '{text[:50]}...'" )
            print(f"  Nombre de BBoxes renvoyées: {len(bboxes)}")
            print(f"  BBoxes: {bboxes}")
        else:
            print(f"- {name:<30} -> Aucun surlignage détecté.")

if __name__ == "__main__":
    asyncio.run(run_audit())
