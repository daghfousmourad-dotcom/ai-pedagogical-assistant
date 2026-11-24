"""
mongo_manager.py
----------------
Gère la création, l'activation et la suppression des configurations via l'API FastAPI Admin.
Ceci assure que le système (FastAPI/Celery) prend bien en compte la nouvelle config.
"""
import requests
import time

class MongoManager:
    def __init__(self, api_url="http://localhost:5005/api/admin/mlops"):
        self.api_url = api_url
        self.versions_url = f"{api_url}/versions"

    def create_version(self, config):
        """Crée une nouvelle configuration dans MongoDB."""
        try:
            response = requests.post(self.versions_url, json=config, timeout=10)
            if response.status_code == 200:
                return True, "Success"
            else:
                return False, response.text
        except Exception as e:
            return False, str(e)

    def activate_version(self, version_name):
        """Active la configuration pour qu'elle soit utilisée par tout le système."""
        try:
            url = f"{self.versions_url}/{version_name}/activate"
            response = requests.put(url, timeout=10)
            if response.status_code == 200:
                # On attend 2 secondes pour laisser le temps aux services de "sentir" le changement
                # (Certains caches comme mlops_config.py peuvent avoir besoin d'un court délai)
                time.sleep(2)
                return True, "Activated"
            else:
                return False, response.text
        except Exception as e:
            return False, str(e)

    def delete_version(self, version_name):
        """Supprime la configuration de MongoDB pour économiser l'espace."""
        try:
            url = f"{self.versions_url}/{version_name}"
            response = requests.delete(url, timeout=10)
            if response.status_code == 200:
                return True, "Deleted"
            else:
                return False, response.text
        except Exception as e:
            return False, str(e)

    def restore_default(self):
        """Restaure la configuration par défaut (sécurité)."""
        try:
            url = f"{self.api_url}/default/activate"
            response = requests.post(url, timeout=10)
            return response.status_code == 200
        except:
            return False

    def cleanup_test_versions(self):
        """Supprime toutes les versions commençant par 'test_p'."""
        try:
            # Récupérer toutes les versions
            response = requests.get(self.versions_url, timeout=10)
            if response.status_code == 200:
                versions = response.json().get("versions", [])
                for v in versions:
                    name = v.get("version_name", "")
                    if name.startswith("test_p"):
                        print(f"   🗑️  Nettoyage : {name}")
                        self.delete_version(name)
            return True
        except Exception as e:
            print(f"⚠️ Erreur lors du nettoyage : {e}")
            return False
