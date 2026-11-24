"""
mlops_tester.py
----------------
ORCHESTRATEUR PRINCIPAL DES TESTS MLOPS.
Ce script lance les tests en 2 phases, surveille la santé du MAC et gère les configurations MongoDB.
"""
import time
import sys
import os

# Ajout du dossier courant au path pour les imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from grid_config import generate_phase1_configs, generate_phase2_configs
from health_monitor import HealthMonitor
from mongo_manager import MongoManager
from test_runner import TestRunner
from report_generator import ReportGenerator

# Import utilitaire de nommage partagé depuis le dossier FastAPI
import sys
import os
fastapi_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "FastAPI")
if fastapi_path not in sys.path:
    sys.path.append(fastapi_path)
from services.utils.naming import get_safe_collection_name

def main():
    print("🚀 Démarrage de la Suite de Tests MLOps Automatisée")
    print("--------------------------------------------------")

    monitor = HealthMonitor()
    mongo = MongoManager()
    runner = TestRunner()
    reporter = ReportGenerator()

    # 1. Nettoyage de sécurité : Supprimer les anciennes configs de tests résiduelles
    print("🧹 Nettoyage des anciennes configurations de test...")
    mongo.cleanup_test_versions()

    # 2. Charger la progression
    progress = reporter.load_progress()
    monitor.print_stats("🔍 Etat initial :")

    # 2. PHASE 1 : Recherche des meilleurs modèles
    if progress["current_phase"] == 1:
        configs = generate_phase1_configs()
        
        last_text_model = None
        last_vision_model = None
        
        for config in configs:
            if monitor.should_stop(): break
            
            name = config["version_name"]
            if name in progress["completed_configs"]:
                continue

            print(f"\n⚙️  Test de la config : {name}")
            print(f"   Modèles: {config['text_model'].split('/')[-1]} | {config['llm_model']} | {config['vision_model_cuda'].split('/')[-1]}")
            
            # Injection du nom de collection dynamique
            config["qdrant_collection"] = get_safe_collection_name(config["text_model"], config["vision_model_cuda"])
            
            # Attendre si le Mac surchauffe
            monitor.wait_if_paused()

            # Cycle de vie de la configuration
            success = False
            error_reason = ""
            rag_res = None
            img_res = None

            try:
                # Création & Activation
                ok_c, msg_c = mongo.create_version(config)
                if not ok_c: raise Exception(f"Erreur création: {msg_c}")
                
                ok_a, msg_a = mongo.activate_version(name)
                if not ok_a: raise Exception(f"Erreur activation: {msg_a}")

                # 2.2 Re-indexation automatique délégée à trigger_indexing.py
                idx_res = runner.run_indexing()
                if idx_res["status"] == "error":
                    raise Exception(f"Erreur Indexation: {idx_res['error']}")

                # 2.3 Exécution des tests
                rag_res = runner.run_eval_rag()
                if rag_res["status"] == "error": 
                    print(f"   ⚠️  Erreur RAG : {rag_res['error'][:100]}...")
                
                # Vérifier à nouveau l'internet avant de lancer le test Image (long)
                monitor.wait_if_paused()

                img_res = runner.run_eval_image()
                if img_res["status"] == "error":
                    print(f"   ⚠️  Erreur Image : {img_res['error'][:100]}...")

                success = True
            except Exception as e:
                error_reason = str(e)
                if "already exists" in error_reason.lower():
                    print(f"   🔄 Version {name} existante détectée. Tentative de suppression et ré-essai...")
                    mongo.delete_version(name)
                    # On ne ré-essaye qu'une fois
                    try:
                        mongo.create_version(config)
                        mongo.activate_version(name)
                        
                        idx_res = runner.run_indexing()
                        if idx_res["status"] == "error":
                            raise Exception(f"Erreur Indexation au second essai: {idx_res['error']}")
                            
                        rag_res = runner.run_eval_rag()
                        img_res = runner.run_eval_image()
                        success = True
                        error_reason = "" # Clear error since retry worked
                    except Exception as e2:
                        error_reason = str(e2)
                        print(f"   ❌ Échec du second essai: {error_reason}")
                else:
                    print(f"   ❌ CRASH : {error_reason}")
                
                if not success:
                    reporter.log_error(config, error_reason)
            except KeyboardInterrupt:
                print("\n\n👋 Interruption clavier. Nettoyage et arrêt...")
                mongo.restore_default()
                mongo.delete_version(name)
                sys.exit(0)
            finally:
                # Nettoyage MongoDB (Impératif pour la mémoire)
                # On doit d'abord restaurer le défaut car on ne peut pas supprimer une version active
                mongo.restore_default()
                # On boucle un peu pour s'assurer que la suppression passe
                for _ in range(3):
                    ok_d, _ = mongo.delete_version(name)
                    if ok_d: break
                    time.sleep(1)

            # Enregistrement du résultat
            res_entry = reporter.add_result(
                config, 
                rag_res.get("metrics") if rag_res and rag_res["status"] == "success" else None,
                img_res.get("metrics") if img_res and img_res["status"] == "success" else None,
                status="success" if success else "failed",
                error=error_reason,
                phase=1
            )
            
            # Mise à jour de la progression
            if success:
                progress["completed_configs"].append(name)
                progress["phase1_results"].append(res_entry)
                reporter.save_progress(progress)
            else:
                print(f"🛑 Arrêt suite à l'échec de la configuration: {name}")
                print("L'erreur a été loggée. Corrigez le problème et relancez le script pour reprendre.")
                sys.exit(1)

            # --- VÉRIFICATION DE LA PAUSE ---
            # Si l'utilisateur a fait Ctrl+C pendant le test, on attend ici.
            monitor.check_and_wait_for_pause()

        # Fin Phase 1 -> Passage Phase 2
        print("\n✅ Phase 1 terminée.")
        progress["current_phase"] = 2
        reporter.save_progress(progress)

    # 3. PHASE 2 : Optimisation des hyperparamètres sur le gagnant
    if progress["current_phase"] == 2:
        print("\n📍 PHASE 2 : Optimisation des hyperparamètres")
        
        if not progress["phase1_results"]:
            print("❌ Erreur : Aucun résultat valide en Phase 1 pour choisir un modèle gagnant.")
            return

        # Calculer le gagnant (en utilisant les moyennes numériques)
        def get_score(r):
            rag = r.get("rag_relevancy_avg", r.get("rag_relevancy", 0))
            img = r.get("img_relevancy_avg", r.get("img_relevancy", 0))
            
            # Sécurité si c'est encore une chaine (vieux reliquat)
            if isinstance(rag, str): rag = 0
            if isinstance(img, str): img = 0
            
            return float(rag or 0) + float(img or 0)
        
        winner = max(progress["phase1_results"], key=get_score)
        print(f"🏆 Modèle gagnant : {winner['text_model']} + {winner['llm_model']}")
        
        configs = generate_phase2_configs(
            winner["text_model"], winner["llm_provider"], winner["llm_model"],
            winner["vision_cuda"], winner["vision_cpu"]
        )

        for config in configs:
            if monitor.should_stop(): break
            
            name = config["version_name"]
            if name in progress["completed_configs"]:
                continue

            print(f"\n⚙️  Test de la config hyperparams : {name}")
            monitor.wait_if_paused()

            # Injection du nom de collection dynamique (Phase 2)
            config["qdrant_collection"] = get_safe_collection_name(config["text_model"], config["vision_model_cuda"])

            success = False
            error_reason = ""
            rag_res = None
            img_res = None

            try:
                mongo.create_version(config)
                mongo.activate_version(name)
                
                # Re-indexation automatique (Phase 2)
                idx_res = runner.run_indexing()
                if idx_res["status"] == "error":
                    raise Exception(f"Erreur Indexation: {idx_res['error']}")

                rag_res = runner.run_eval_rag()
                
                # Vérification intermédiaire
                monitor.wait_if_paused()

                img_res = runner.run_eval_image()
                success = True
            except Exception as e:
                error_reason = str(e)
                print(f"   ❌ CRASH : {error_reason}")
                reporter.log_error(config, error_reason)
            except KeyboardInterrupt:
                print("\n\n👋 Interruption clavier. Nettoyage et arrêt...")
                mongo.restore_default()
                mongo.delete_version(name)
                sys.exit(0)
            finally:
                mongo.restore_default()
                for _ in range(3):
                    ok_d, _ = mongo.delete_version(name)
                    if ok_d: break
                    time.sleep(1)

            res = reporter.add_result(
                config, 
                rag_res.get("metrics") if rag_res and rag_res["status"] == "success" else None,
                img_res.get("metrics") if img_res and img_res["status"] == "success" else None,
                status="success" if success else "failed",
                error=error_reason,
                phase=2
            )
            
            # Ensure we actually got some metrics before marking as completed
            has_metrics = (rag_res and rag_res.get("metrics")) or (img_res and img_res.get("metrics"))

            if success and has_metrics:
                progress["completed_configs"].append(name)
                if "phase2_results" not in progress:
                    progress["phase2_results"] = []
                progress["phase2_results"].append(res)
                reporter.save_progress(progress)
            elif success and not has_metrics:
                print(f"   ⚠️  Config {name} success in execution but NO METRICS captured (CSV empty). Will retry.")
            else:
                print(f"   🛑 FAILED Phase 2 Config: {name} | Reason: {error_reason}")
                sys.exit(1)

            # --- VÉRIFICATION DE LA PAUSE ---
            monitor.check_and_wait_for_pause()

    # 4. Restauration finale au défaut
    print("\n🏁 Tous les tests sont terminés.")
    mongo.restore_default()
    print("🛡️  Configuration stable restaurée.")

if __name__ == "__main__":
    main()
