"""
health_monitor.py
-----------------
Surveille les ressources système (CPU, RAM, disque) en temps réel.
Met en pause automatiquement si les seuils sont dépassés.
Seul le disque /Volumes/MonSSD est utilisé.
"""
import time
import psutil
import os
import signal
import threading
import socket

# --- SEUILS DE SÉCURITÉ ---
CPU_PAUSE_THRESHOLD = 85.0      # % CPU au-delà duquel on pause
RAM_PAUSE_THRESHOLD = 92.0      # % RAM au-delà duquel on pause (ajusté pour Jina/ColPali)
DISK_MIN_FREE_GB = 5.0          # Go minimum libres sur /Volumes/MonSSD
DISK_OS_MIN_FREE_GB = 4.0       # Go minimum libres sur le disque système (Macintosh HD)
COOL_DOWN_SECONDS = 30          # Secondes à attendre avant de reprendre
CHECK_INTERVAL = 5              # Secondes entre chaque vérification
MONITORED_DISK = "/Volumes/MonSSD"
MONITORED_DISK_OS = "/"          # Disque système pour le Swap


class HealthMonitor:
    """Moniteur de santé système avec pause automatique."""

    def __init__(self):
        self._paused_by_system = False
        self._stop = False

        # Gestion de Ctrl+C pour pause propre
        signal.signal(signal.SIGINT, self._handle_interrupt)

    def _handle_interrupt(self, signum, frame):
        """Ctrl+C définit maintenant une demande de pause à la fin du test en cours."""
        if not self._paused_by_system:
            print("\n\n⏸️  Demande de PAUSE reçue. Le test en cours va se terminer avant la pause...")
            self._paused_by_system = True
        else:
            print("\n\n🛑 Deuxième Ctrl+C : Arrêt complet demandé.")
            self._stop = True

    def should_stop(self):
        return self._stop

    def check_and_wait_for_pause(self):
        """Vérifie si une pause a été demandée via Ctrl+C et attend la validation."""
        if self._paused_by_system:
            print("\n" + "="*50)
            print("⏸️  TEST EN PAUSE (Terminé proprement)")
            print("Appuyez sur ENTRÉE pour reprendre le test suivant.")
            print("="*50)
            input()
            print("▶️  Reprise...")
            self._paused_by_system = False

    def wait_if_paused(self):
        """Appelé avant chaque test pour bloquer si le système est surchargé ou hors ligne."""
        while True:
            # 1. Vérification Internet (Important pour OpenAI/Tavily)
            if not self.is_internet_available():
                print("\n🌐 Connexion Internet perdue. En attente du rétablissement...")
                time.sleep(10)
                continue

            # 2. Vérification des ressources
            ok, reason = self._check_resources()
            if ok:
                break
            else:
                print(f"\n⚠️  Système surchargé ({reason}). Pause de {COOL_DOWN_SECONDS}s...")
                for remaining in range(COOL_DOWN_SECONDS, 0, -5):
                    stats = self.get_stats()
                    print(f"   ⏳ Attente {remaining}s... | CPU: {stats['cpu']:.0f}% | RAM: {stats['ram']:.0f}% | Disque libre: {stats['disk_free_gb']:.1f} Go")
                    time.sleep(min(5, remaining))

    def _check_resources(self):
        stats = self.get_stats()

        if stats["cpu"] > CPU_PAUSE_THRESHOLD:
            return False, f"CPU à {stats['cpu']:.1f}%"

        if stats["ram"] > RAM_PAUSE_THRESHOLD:
            return False, f"RAM à {stats['ram']:.1f}%"

        if stats["disk_free_gb"] < DISK_MIN_FREE_GB:
            return False, f"Disque MonSSD presque plein ({stats['disk_free_gb']:.1f} Go libres)"

        if stats["disk_os_free_gb"] < DISK_OS_MIN_FREE_GB:
            return False, f"Disque SYSTÈME presque plein ({stats['disk_os_free_gb']:.1f} Go libres - Risque de Swap permanent)"

        return True, "OK"

    def get_stats(self):
        """Retourne les statistiques courantes du système."""
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory().percent

        try:
            disk = psutil.disk_usage(MONITORED_DISK)
            disk_free_gb = disk.free / (1024 ** 3)
            disk_pct = disk.percent
        except FileNotFoundError:
            disk_free_gb = 999.0
            disk_pct = 0.0

        try:
            disk_os = psutil.disk_usage(MONITORED_DISK_OS)
            disk_os_free_gb = disk_os.free / (1024 ** 3)
        except Exception:
            disk_os_free_gb = 999.0

        return {
            "cpu": cpu,
            "ram": ram,
            "disk_free_gb": disk_free_gb,
            "disk_pct": disk_pct,
            "disk_os_free_gb": disk_os_free_gb
        }

    def is_internet_available(self, host="8.8.8.8", port=53, timeout=3):
        """Vérifie si la connexion internet est active via un ping TCP sur Google DNS."""
        try:
            socket.setdefaulttimeout(timeout)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
            return True
        except socket.error:
            return False

    def print_stats(self, prefix="📊"):
        stats = self.get_stats()
        print(
            f"{prefix} CPU: {stats['cpu']:.0f}% | "
            f"RAM: {stats['ram']:.0f}% | "
            f"SSD: {stats['disk_free_gb']:.1f}G | "
            f"OS: {stats['disk_os_free_gb']:.1f}G"
        )
