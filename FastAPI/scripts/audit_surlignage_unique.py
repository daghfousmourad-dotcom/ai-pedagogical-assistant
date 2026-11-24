import asyncio
import os
import sys

# Ajout du chemin racine pour les imports
sys.path.append(os.getcwd())

from services.core.navigator import SmartCourseNavigator
from services.core.surlignage import HighlightLogic

async def run_accuracy_audit():
    print("📋 [AUDIT PRÉCISION] Début de la vérification des mots uniques...\n")
    
    nav = SmartCourseNavigator()
    hl = HighlightLogic(nav)
    mongo_id = '69c810dd139359198fc1aaf1'
    
    # --- CONFIGURATION DES TESTS ---
    tests = [
        # PAGE 5
        {"page": 5, "word": "intégration", "expected_idx": 3, "speech": "Utilisation pour de l'intégration"},
        {"page": 5, "word": "Environnement", "expected_idx": 7, "speech": "continue, c.I. Environnement"},
        {"page": 5, "word": "conteneur (Whisper: cantonneur)", "expected_idx": 31, "speech": "Un nouveau cantonneur", "target_word": "cantonneur"},
        {"page": 5, "word": "exécutions", "expected_idx": 51, "speech": "plusieurs executions"},
        
        # PAGE 6
        {"page": 6, "word": "distribution", "expected_idx": 3, "speech": "Utilisation pour la distribution"},
        {"page": 6, "word": "Dockerfiles (Whisper: Docker5)", "expected_idx": 12, "speech": "à partir de Docker5", "target_word": "Docker5"},
        {"page": 6, "word": "pérenne", "expected_idx": 21, "speech": "stockage pérenne"},
        {"page": 6, "word": "dépendances", "expected_idx": 36, "speech": "toutes les dépendances"}
    ]
    
    last_word_index = 0
    current_page = None
    
    results = []
    
    for t in tests:
        if t["page"] != current_page:
            current_page = t["page"]
            last_word_index = 0 # Reset pour nouvelle page
            print(f"\n--- 📄 TEST PAGE {current_page} ---")

        speech = t["speech"]
        word_label = t["word"]
        expected = t["expected_idx"]
        
        # On simule l'appel de surlignage
        res = await hl.get_highlight(mongo_id, current_page, speech, last_word_index)
        
        actual_idx = res.get("index") if res else None
        
        status = "✅ PASS" if actual_idx == expected else "❌ FAIL"
        if actual_idx != expected:
            # On vérifie si c'est un match partiel ou proche (acceptable pour Whisper)
            if actual_idx is not None and abs(actual_idx - expected) <= 1:
                status = "⚠️ NEAR (±1)"
        
        print(f"{status} | Mot: {word_label:25} | Attendu: {expected:2} | Obtenu: {actual_idx if actual_idx is not None else 'None':2}")
        if res:
            print(f"      > Texte détecté: '{res['text']}'")
            last_word_index = res["index"]
        
        results.append({
            "page": current_page,
            "word": word_label,
            "expected": expected,
            "actual": actual_idx,
            "status": status
        })

    # --- RÉSUMÉ FINAL ---
    print("\n" + "="*50)
    print("📊 RÉSUMÉ DE L'AUDIT")
    print("="*50)
    passed = sum(1 for r in results if "PASS" in r["status"])
    near = sum(1 for r in results if "NEAR" in r["status"])
    failed = len(results) - passed - near
    
    print(f"✅ Total Pass  : {passed}")
    print(f"⚠️ Total Near  : {near}")
    print(f"❌ Total Fail  : {failed}")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(run_accuracy_audit())
