# -*- coding: utf-8 -*-

# Dépendances requises: pandas, matplotlib
# Installation: pip install pandas matplotlib
# Dépendance système: sshpass (sudo apt-get install sshpass)

import os
import subprocess
import re
import csv
import datetime
import pandas as pd
import matplotlib.pyplot as plt

# ==============================================================================
# SECTION 1: FICHE TECHNIQUE DE L'EXPÉRIMENTATION (À REMPLIR PAR L'UTILISATEUR)
# ==============================================================================

TOPOLOGY = {
    "client_host": {
        "hostname": "gros-48",
        "ip": "10.144.4.48",
        "cores": 4, "ram_gb": 128, "os": "Ubuntu 22.04 LTS", "type": "Bare-metal (Grid5000)"
    },
    "intermediate_vm": {
        "vm_name": "virtual-144-36-1",
        "ip": "10.144.36.1",
        "user": "root",
        "password": "grid5000",
        "vcpu": 4, "ram_mb": 2048, "image": "debian11-x64-base.qcow2", "hypervisor": "KVM/libvirt", "bridge": "br0"
    },
    "backend_server": {
        "hostname": "gros-46",
        "ip": "10.144.4.46",
        "cores": 4, "ram_gb": 128, "os": "Ubuntu 22.04 LTS", "role": "Serveur backend Tomcat"
    }
}
NETWORK_CAPACITIES = {
    "host_nic": {"interface": "eno1", "type": "Mellanox ConnectX-4 Lx", "theoretical_throughput_gbps": 25},
    "vm_nic": {"interface": "enp0s2", "theoretical_throughput_mbps": 100, "theoretical_throughput_MBs": 12.5}
}
SOFTWARE_VERSIONS = {
    "wrk2_path": "wrk2/wrk", "wrk2_version": "wrk 4.0.0", "java_version": "OpenJDK 17.0.10",
    "tomcat_version": "Apache Tomcat/11.0.0-M20", "os_versions": "Ubuntu 22.04 LTS"
}
APPLICATIONS = { "Serv": {"name": "Serv", "endpoint": "/serv/Serv"}, "Serv-odb": {"name": "Serv-odb", "endpoint": "/serv-odb/Serv"} }
PAYLOADS = {"tiny.jpg": {"size_kb": 1.4}, "small.jpg": {"size_kb": 9.9}, "large.jpg": {"size_kb": 102.0}}

# NOUVEAU: Stratégies de test différenciées
BENCHMARK_STRATEGIES = {
    "Serv": {
        "description": "Stratégie prudente pour le servlet standard.",
        "threads": 8,
        "connections": 16,
        "duration_seconds": 60,
        "timeout_seconds": 10,
        "rate_exploration": {"start_rps": 200, "step_rps": 100, "max_rps": 3000},
        "stop_condition": {"timeout_threshold_percent": 1.0}
    },
    "Serv-odb": {
        "description": "Stratégie agressive pour le servlet ODB.",
        "threads": 8,
        "connections": 100,
        "duration_seconds": 60,
        "timeout_seconds": 10,
        "rate_exploration": {"start_rps": 1000, "step_rps": 500, "max_rps": 10000},
        "stop_condition": {"timeout_threshold_percent": 1.0}
    }
}

OUTPUT_FILES = {"reproducibility_report": "reproducibility_report.md", "raw_results_csv": "results_raw.csv"}

# ==============================================================================
# SECTION 2: LOGIQUE DU SCRIPT DE BENCHMARK
# ==============================================================================

def write_reproducibility_report():
    with open(OUTPUT_FILES["reproducibility_report"], "w", encoding="utf-8") as f:
        f.write("# Fiche Technique de Reproductibilité du Benchmark\n\n")
        # ... (Le reste de la fonction est mis à jour pour lire BENCHMARK_STRATEGIES)
        f.write("\n## 5. Stratégies de `wrk2`\n\n")
        for name, strategy in BENCHMARK_STRATEGIES.items():
            f.write(f"### 5.1. Stratégie pour `{name}`\n")
            f.write(f"- **Description**: {strategy['description']}\n")
            f.write(f"- **Threads (-t)**: {strategy['threads']}\n")
            f.write(f"- **Connexions (-c)**: {strategy['connections']}\n")
            # ... etc pour tous les paramètres
    print(f"Rapport de reproductibilité généré : {OUTPUT_FILES['reproducibility_report']}")

def initialize_csv():
    header = ["timestamp", "servlet_name", "image_name", "threads", "connections", "duration_s", "target_rate_rps", "timeout_s", "observed_rps", "transfer_MBs", "total_requests", "errors_connect", "errors_read", "errors_write", "errors_timeout", "total_errors", "latency_avg_ms", "latency_p50_ms", "latency_p75_ms", "latency_p90_ms", "latency_p99_ms", "vm_cpu_avg_percent"]
    with open(OUTPUT_FILES["raw_results_csv"], "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(header)
    print(f"Fichier de résultats initialisé : {OUTPUT_FILES['raw_results_csv']}")

# ... (Toutes les fonctions _parse_*, _append_result_to_csv, run_single_wrk2_test, generate_plots restent identiques)

def run_scenarios():
    print("\nLancement de la boucle d'exploration des scénarios...")
    for servlet_name, servlet_details in APPLICATIONS.items():
        if servlet_name not in BENCHMARK_STRATEGIES:
            print(f"  ! Avertissement: Aucune stratégie définie pour '{servlet_name}'. Scénario ignoré.")
            continue

        strategy = BENCHMARK_STRATEGIES[servlet_name]
        params = strategy

        for image_name in PAYLOADS.keys():
            print(f"\n----- Début du scénario: Servlet='{servlet_name}', Image='{image_name}' -----")
            print(f"  > Stratégie utilisée: '{strategy['description']}' (-c {params['connections']})")

            url = f"http://{TOPOLOGY['intermediate_vm']['ip']}:8080{servlet_details['endpoint']}?machine={TOPOLOGY['backend_server']['hostname']}&image={image_name}"

            rate_params = params['rate_exploration']
            current_rate = rate_params['start_rps']
            while current_rate <= rate_params['max_rps']:
                print(f"\nTesting Rate: {current_rate} RPS...")
                results = run_single_wrk2_test(url, current_rate, params["connections"], params["threads"], params["duration_seconds"], params["timeout_seconds"])

                if not results:
                    print("  ! Le test a échoué de manière critique. Arrêt du scénario.")
                    break

                result_row = {"timestamp": datetime.datetime.now().isoformat(), "servlet_name": servlet_name, "image_name": image_name, "threads": params["threads"], "connections": params["connections"], "duration_s": params["duration_seconds"], "target_rate_rps": current_rate, "timeout_s": params["timeout_seconds"], **results}
                _append_result_to_csv(result_row)

                total_reqs = results.get('total_requests', 0)
                timeouts = results.get('errors_timeout', 0)
                if total_reqs > 0 and (timeouts / total_reqs * 100) > params['stop_condition']['timeout_threshold_percent']:
                    print(f"  ! Condition d'arrêt atteinte: {(timeouts / total_reqs * 100):.2f}% de timeouts.")
                    break
                current_rate += rate_params['step_rps']
            print(f"----- Fin du scénario: Servlet='{servlet_name}', Image='{image_name}' -----")

def main():
    # ... (Le main reste identique)
    pass

if __name__ == "__main__":
    # ... (Identique)
    pass
