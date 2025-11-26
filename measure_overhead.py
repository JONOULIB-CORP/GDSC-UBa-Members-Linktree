# -*- coding: utf-8 -*-

"""
Ce script mesure et compare l'overhead de l'agent ODB en termes de:
1. Temps de démarrage du serveur Tomcat.
2. Utilisation de la mémoire (RSS) du processus Tomcat.

Il effectue ces mesures pour un Tomcat standard (baseline) et pour un Tomcat
avec l'agent ODB et une application (Serv-odb) déployée.
"""

import subprocess
import time
import re
import numpy as np
import os

# ==============================================================================
# CONFIGURATION (À adapter si nécessaire)
# ==============================================================================

# Informations de connexion à la VM intermédiaire où Tomcat est exécuté
VM_CONFIG = {
    "user": "root",
    "ip": "10.144.0.1",
    "password": "grid5000"
}

# Paramètres de la mesure
MEASUREMENT_CONFIG = {
    "num_runs": 5,  # Nombre de fois où chaque mesure est répétée pour obtenir une moyenne
    "delay_between_runs_s": 10  # Temps d'attente entre chaque redémarrage de Tomcat
}

# Commandes et chemins sur la VM
REMOTE_COMMANDS = {
    "tomcat_startup_script": "/root/apache-tomcat-11.0.0-M20/bin/startup.sh",
    "tomcat_shutdown_script": "/root/apache-tomcat-11.0.0-M20/bin/shutdown.sh",
    "tomcat_log_file": "/root/apache-tomcat-11.0.0-M20/logs/catalina.out",
    "tomcat_webapps_dir": "/root/apache-tomcat-11.0.0-M20/webapps",
    "serv_odb_war_path": "/root/serv1.war" # Chemin vers le .war à déployer pour le test ODB
}

# ==============================================================================
# LOGIQUE DU SCRIPT
# ==============================================================================

def _run_remote_command(command, check=True, timeout=30):
    """Exécute une commande sur la VM via SSH."""
    ssh_cmd = ["sshpass", "-p", VM_CONFIG['password'], "ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-T", f"{VM_CONFIG['user']}@{VM_CONFIG['ip']}", command]
    try:
        proc = subprocess.run(ssh_cmd, check=check, capture_output=True, text=True, timeout=timeout)
        return proc.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Erreur lors de l'exécution de la commande distante: {e.stderr}")
        return None
    except subprocess.TimeoutExpired:
        print(f"Timeout lors de l'exécution de la commande distante.")
        return None

def _stop_tomcat():
    """Arrête Tomcat de manière forcée."""
    print("  > Arrêt de Tomcat...")
    _run_remote_command(f"{REMOTE_COMMANDS['tomcat_shutdown_script']} -force", check=False)
    time.sleep(5)

def _get_tomcat_memory_usage():
    """Récupère l'utilisation mémoire (RSS en KB) du processus Tomcat."""
    cmd = "ps -C java -o rss= | head -n 1"
    output = _run_remote_command(cmd)
    return int(output) if output and output.isdigit() else 0

def _measure_single_run():
    """Mesure le temps de démarrage et la mémoire pour un seul démarrage de Tomcat."""
    _stop_tomcat()
    _run_remote_command(f"rm -f {REMOTE_COMMANDS['tomcat_log_file']}")
    _run_remote_command(REMOTE_COMMANDS['tomcat_startup_script'])

    start_time = time.time()
    startup_time_ms = 0
    while time.time() - start_time < 120: # Timeout de 2 minutes
        log_content = _run_remote_command(f"cat {REMOTE_COMMANDS['tomcat_log_file']}")
        if log_content:
            match = re.search(r"Server startup in \[([\d,]+)\] ms", log_content)
            if match:
                startup_time_ms = int(match.group(1).replace(',', ''))
                break
        time.sleep(2)

    if startup_time_ms == 0:
        print("  ! Le temps de démarrage n'a pas pu être déterminé.")
        return None, None

    time.sleep(10) # Stabilisation
    memory_kb = _get_tomcat_memory_usage()

    print(f"    - Démarrage: {startup_time_ms} ms, Mémoire: {memory_kb} KB")
    return startup_time_ms, memory_kb

def run_measurement_scenario(scenario_name):
    """Exécute une série de mesures et retourne les moyennes."""
    print(f"\n--- Début du scénario: '{scenario_name}' ---")
    times, memories = [], []
    for i in range(MEASUREMENT_CONFIG["num_runs"]):
        print(f"  Run {i+1}/{MEASUREMENT_CONFIG['num_runs']}...")
        startup_time, memory = _measure_single_run()
        if startup_time and memory:
            times.append(startup_time)
            memories.append(memory)
        time.sleep(MEASUREMENT_CONFIG["delay_between_runs_s"])

    return {
        "startup_avg_ms": np.mean(times) if times else 0,
        "memory_avg_kb": np.mean(memories) if memories else 0
    }

def main():
    print("Début de la mesure de l'overhead de l'agent ODB.")

    war_filename = os.path.basename(REMOTE_COMMANDS['serv_odb_war_path'])
    app_dirname = war_filename.replace('.war', '')
    webapp_path = REMOTE_COMMANDS['tomcat_webapps_dir']

    # Étape 1: Mesurer la baseline (s'assurer que l'environnement est propre)
    _run_remote_command(f"rm -rf {webapp_path}/{app_dirname} {webapp_path}/{war_filename}")
    baseline_results = run_measurement_scenario("Baseline (Tomcat seul)")

    # Étape 2: Mesurer avec ODB
    _run_remote_command(f"cp {REMOTE_COMMANDS['serv_odb_war_path']} {webapp_path}/")
    odb_results = run_measurement_scenario("Avec Agent ODB")

    # Nettoyage final
    _run_remote_command(f"rm -rf {webapp_path}/{app_dirname} {webapp_path}/{war_filename}")

    # Affichage des résultats
    print("\n" + "="*60)
    print("            Tableau Comparatif de l'Overhead")
    print("="*60)
    b_start = baseline_results['startup_avg_ms']
    o_start = odb_results['startup_avg_ms']
    overhead_start = ((o_start - b_start) / b_start * 100) if b_start else 0

    b_mem = baseline_results['memory_avg_kb']
    o_mem = odb_results['memory_avg_kb']
    overhead_mem = ((o_mem - b_mem) / b_mem * 100) if b_mem else 0

    print(f"| {'Métrique':<25} | {'Baseline':<15} | {'Avec ODB':<15} | {'Overhead':<10} |")
    print(f"|{'-'*27}|{'-'*17}|{'-'*17}|{'-'*12}|")
    print(f"| {'Temps démarrage (ms)':<25} | {b_start:<15.2f} | {o_start:<15.2f} | {overhead_start:>8.2f}% |")
    print(f"| {'Utilisation mémoire (KB)':<25} | {b_mem:<15.2f} | {o_mem:<15.2f} | {overhead_mem:>8.2f}% |")
    print("="*80)

if __name__ == "__main__":
    main()
