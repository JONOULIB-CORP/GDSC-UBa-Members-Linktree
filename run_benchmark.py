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
import argparse

# ==============================================================================
# SECTION 1: FICHE TECHNIQUE DE L'EXPÉRIMENTATION (À REMPLIR PAR L'UTILISATEUR)
# ==============================================================================

TOPOLOGY = {
    "client_host": {
        "hostname": "gros-86",
        "ip": "172.16.66.86",
        "cores": 36, "ram_gb": 90, "os": "Debian GNU/Linux 11 (bullseye)", "type": "Bare-metal (Grid5000)"
    },
    "intermediate_vm": {
        "vm_name": "virtual-144-0-1",
        "ip": "10.144.0.1",
        "user": "root",
        "password": "grid5000",
        "vcpu": 4, "ram_mb": 2048, "image": "debian11-x64-base.qcow2", "hypervisor": "KVM/libvirt", "bridge": "br0"
    },
    "backend_server": {
        "hostname": "gros-80",
        "ip": "172.16.66.80",
        "cores": 36, "ram_gb": 90, "os": "Debian GNU/Linux 11 (bullseye)", "role": "Serveur backend Tomcat"
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
APPLICATIONS = { "Serv": {"name": "Serv", "endpoint": "/serv/Serv"}, "Serv-odb": {"name": "Serv-odb", "endpoint": "/serv1/Serv"} }
PAYLOADS = {
    "1k.jpg": {"size_kb": 1.0},
    "10k.jpg": {"size_kb": 10.0},
    "50k.jpg": {"size_kb": 50.0},
    "100k.jpg": {"size_kb": 100.0},
    "250k.jpg": {"size_kb": 250.0},
    "500k.jpg": {"size_kb": 500.0},
    "1M.jpg": {"size_kb": 1024.0}
}


# NOUVEAU: Stratégies de test différenciées
BENCHMARK_STRATEGIES = {
    "Serv": {
        "description": "Stratégie prudente pour le servlet standard.",
        "threads": 8,
        "connections": 15,
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
        f.write(f"Date du test: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        # Section 1: Topologie
        f.write("## 1. Topologie de l'expérimentation\n\n")

        f.write("### 1.1. Client (C)\n")
        for key, value in TOPOLOGY["client_host"].items():
            f.write(f"- **{key.replace('_', ' ').capitalize()}**: {value}\n")
        f.write("\n")

        f.write("### 1.2. Intermédiaire (I)\n")
        for key, value in TOPOLOGY["intermediate_vm"].items():
            f.write(f"- **{key.replace('_', ' ').capitalize()}**: {value}\n")
        f.write("\n")

        f.write("### 1.3. Serveur final (S)\n")
        for key, value in TOPOLOGY["backend_server"].items():
            f.write(f"- **{key.replace('_', ' ').capitalize()}**: {value}\n")
        f.write("\n")

        # Section 2: Réseau
        f.write("## 2. Configuration réseau & capacités\n\n")
        f.write("### 2.1. Carte réseau du nœud physique\n")
        for key, value in NETWORK_CAPACITIES["host_nic"].items():
            f.write(f"- **{key.replace('_', ' ').capitalize()}**: {value}\n")
        f.write("\n")

        f.write("### 2.2. Interface réseau de la VM\n")
        for key, value in NETWORK_CAPACITIES["vm_nic"].items():
            f.write(f"- **{key.replace('_', ' ').capitalize()}**: {value}\n")

        f.write("\n")

        # Section 3: Logiciels
        f.write("## 3. Logiciels & versions\n\n")
        for key, value in SOFTWARE_VERSIONS.items():
            f.write(f"- **{key.replace('_', ' ').capitalize()}**: {value}\n")
        f.write("\n")

        # Section 4: Applications
        f.write("## 4. Applications testées\n\n")
        for name, details in APPLICATIONS.items():
            f.write(f"### 4.1. {name}\n")
            f.write(f"- **Endpoint**: `{details['endpoint']}`\n\n")

        f.write("### 4.2. Payloads\n")
        for name, details in PAYLOADS.items():
            f.write(f"- **{name}**: {details['size_kb']} KB\n")
        f.write("\n")
        f.write("\n## 5. Stratégies de `wrk2`\n\n")
        for name, strategy in BENCHMARK_STRATEGIES.items():
            f.write(f"### 5.1. Stratégie pour `{name}`\n")
            f.write(f"- **Description**: {strategy['description']}\n")
            f.write(f"- **Threads (-t)**: {strategy['threads']}\n")
            f.write(f"- **Connexions (-c)**: {strategy['connections']}\n")
            f.write(f"- **Durée (-d)**: {strategy['duration_seconds']}s\n")
            f.write(f"- **Timeout**: {strategy['timeout_seconds']}s\n")
            f.write(f"- **Stratégie d'exploration du Rate (R)**:\n")
            f.write(f"  - Début: {strategy['rate_exploration']['start_rps']} RPS\n")
            f.write(f"  - Incrément: {strategy['rate_exploration']['step_rps']} RPS\n")
            f.write(f"  - Plafond: {strategy['rate_exploration']['max_rps']} RPS\n")
            f.write(f"- **Condition d'arrêt**: Taux de timeouts > {strategy['stop_condition']['timeout_threshold_percent']}%\n")
    print(f"Rapport de reproductibilité généré : {OUTPUT_FILES['reproducibility_report']}")

def initialize_csv():
    header = ["timestamp", "servlet_name", "image_name", "threads", "connections", "duration_s", "target_rate_rps", "timeout_s", "observed_rps", "transfer_MBs", "total_requests", "errors_connect", "errors_read", "errors_write", "errors_timeout", "total_errors", "latency_avg_ms", "latency_p50_ms", "latency_p75_ms", "latency_p90_ms", "latency_p99_ms", "vm_cpu_avg_percent"]
    try:
        with open(OUTPUT_FILES["raw_results_csv"], "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
        print(f"Fichier de résultats initialisé : {OUTPUT_FILES['raw_results_csv']}")
    except IOError as e:
        print(f"Erreur lors de l'initialisation du fichier CSV : {e}")
        exit(1)

def _parse_time(time_str):
    """Convertit une chaîne de temps (ex: 2.34ms, 1.12s) en millisecondes."""
    if 'us' in time_str:
        return float(time_str.replace('us', '')) / 1000.0
    if 'ms' in time_str:
        return float(time_str.replace('ms', ''))
    if 's' in time_str:
        return float(time_str.replace('s', '')) * 1000.0
    return 0.0

def _parse_bytes(bytes_str):
    """Convertit une chaîne de taille (ex: 1.23KB, 2.34MB) en MB."""
    bytes_str = bytes_str.lower()
    if 'kb' in bytes_str:
        return float(bytes_str.replace('kb', '')) / 1024.0
    if 'mb' in bytes_str:
        return float(bytes_str.replace('mb', ''))
    if 'gb' in bytes_str:
        return float(bytes_str.replace('gb', '')) * 1024.0
    if 'b' in bytes_str:
         return float(bytes_str.replace('b', '')) / (1024.0 * 1024.0)
    return 0.0

def _parse_wrk2_output(output):
    """
    Analyse la sortie texte de wrk2 pour en extraire les métriques clés.
    Retourne un dictionnaire de résultats.
    """
    results = {}

    # RPS et Transfert
    rps_match = re.search(r'Requests/sec:\s*([\d\.]+)', output)
    results['observed_rps'] = float(rps_match.group(1)) if rps_match else 0

    transfer_match = re.search(r'Transfer/sec:\s*([\d\.]+[kKmMgG]B)', output)
    results['transfer_MBs'] = _parse_bytes(transfer_match.group(1)) if transfer_match else 0

    # Total des requêtes
    total_req_match = re.search(r'([\d]+) requests in', output)
    results['total_requests'] = int(total_req_match.group(1)) if total_req_match else 0

    # Erreurs
    errors_match = re.search(r'Socket errors: connect (\d+), read (\d+), write (\d+), timeout (\d+)', output)
    if errors_match:
        results['errors_connect'] = int(errors_match.group(1))
        results['errors_read'] = int(errors_match.group(2))
        results['errors_write'] = int(errors_match.group(3))
        results['errors_timeout'] = int(errors_match.group(4))
        results['total_errors'] = sum(results[k] for k in ['errors_connect', 'errors_read', 'errors_write', 'errors_timeout'])
    else:
        results['errors_connect'] = results['errors_read'] = results['errors_write'] = results['errors_timeout'] = results['total_errors'] = 0

    # Latence
    latency_dist = re.search(r'Latency Distribution\s+50%\s+([\d\.\w]+)\s+75%\s+([\d\.\w]+)\s+90%\s+([\d\.\w]+)\s+99%\s+([\d\.\w]+)', output)
    if latency_dist:
        results['latency_p50_ms'] = _parse_time(latency_dist.group(1))
        results['latency_p75_ms'] = _parse_time(latency_dist.group(2))
        results['latency_p90_ms'] = _parse_time(latency_dist.group(3))
        results['latency_p99_ms'] = _parse_time(latency_dist.group(4))
    else:
        results['latency_p50_ms'] = results['latency_p75_ms'] = results['latency_p90_ms'] = results['latency_p99_ms'] = 0

    avg_latency_match = re.search(r'Latency\s+([\d\.\w]+)\s+', output)
    results['latency_avg_ms'] = _parse_time(avg_latency_match.group(1)) if avg_latency_match else 0

    return results

def _parse_mpstat_output(output):
    """
    Analyse la sortie de mpstat pour calculer le % d'utilisation CPU moyen.
    L'utilisation est calculée comme 100 - %idle moyen sur tous les cœurs.
    """
    lines = output.strip().split('\n')
    idle_percentages = []

    for line in lines:
        # On cherche les lignes contenant des données pour 'all' cœurs.
        if 'Average:' in line or 'Linux' in line or 'CPU' in line or not line:
            continue

        parts = line.split()
        if len(parts) >= 12 and parts[2].lower() == 'all':
            try:
                idle_percent = float(parts[-1])
                idle_percentages.append(idle_percent)
            except (ValueError, IndexError):
                continue # Ligne malformée

    if not idle_percentages:
        print("  ! Avertissement: Impossible de parser la sortie de mpstat.")
        return 0.0

    avg_idle = sum(idle_percentages) / len(idle_percentages)
    return 100.0 - avg_idle

def run_single_wrk2_test(url, rate, connections, threads, duration, timeout, lua_script=None, hdr_histogram_output=None):
    """
    Orchestre un test unique: lance le monitoring CPU (si nécessaire), exécute wrk2,
    et retourne les résultats combinés.
    """
    vm_user = TOPOLOGY['intermediate_vm']['user']
    vm_ip = TOPOLOGY['intermediate_vm']['ip']
    vm_password = TOPOLOGY['intermediate_vm']['password']
    remote_log = "/tmp/cpu_benchmark.log"
    local_log = "cpu_benchmark.log"
    monitor_process = None

    ssh_options = ["-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]

    try:
        # --- Démarrage du monitoring CPU (sauf si on ne fait que capturer l'histogramme) ---
        if hdr_histogram_output is None:
            mpstat_cmd = f"mpstat -P ALL 1 {duration} > {remote_log}"
            print("  > Démarrage du monitoring CPU sur la VM...")
            ssh_command = ["sshpass", "-p", vm_password, "ssh"] + ssh_options + [f"{vm_user}@{vm_ip}", mpstat_cmd]
            monitor_process = subprocess.Popen(ssh_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # --- Exécution du test wrk2 ---
        wrk2_path = SOFTWARE_VERSIONS['wrk2_path']
        command = [
            wrk2_path, f"-t{threads}", f"-c{connections}", f"-d{duration}s",
            f"-R{rate}", f"--timeout={timeout}s", "--latency", url
        ]
        if lua_script:
            command.extend(["-s", lua_script])
        if hdr_histogram_output:
            command.extend(["--hdr-histogram", hdr_histogram_output])

        print(f"  > Lancement wrk2: {' '.join(command)}")

        wrk2_output = ""
        try:
            # Utiliser un timeout généreux pour la commande wrk2
            process = subprocess.run(command, capture_output=True, text=True, check=True, timeout=duration + 20)
            wrk2_output = process.stdout
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            print(f"  ! Avertissement: wrk2 a terminé avec une erreur ou un timeout.")
            wrk2_output = e.stdout + e.stderr if hasattr(e, 'stdout') and e.stdout else ""

        results = _parse_wrk2_output(wrk2_output)

        # --- Arrêt et récupération des métriques CPU ---
        if monitor_process:
            print("  > Attente de la fin du monitoring CPU...")
            monitor_process.wait(timeout=15)

            print("  > Récupération des logs CPU...")
            scp_cmd = ["sshpass", "-p", vm_password, "scp"] + ssh_options + [f"{vm_user}@{vm_ip}:{remote_log}", local_log]
            subprocess.run(scp_cmd, check=True, capture_output=True, timeout=15)

            with open(local_log, "r", encoding="utf-8") as f:
                cpu_log_content = f.read()
            results['vm_cpu_avg_percent'] = _parse_mpstat_output(cpu_log_content)
            print(f"  > CPU moyen VM: {results['vm_cpu_avg_percent']:.2f}%")
        else:
            results['vm_cpu_avg_percent'] = 0.0 # Pas de mesure CPU si pas de monitoring

        return results

    except Exception as e:
        print(f"  ! Erreur critique durant l'exécution du test: {e}")
        if monitor_process:
            monitor_process.kill() # Tenter de tuer le process SSH
        return None
    finally:
        # --- Nettoyage ---
        try:
            print("  > Nettoyage des fichiers de log...")
            cleanup_cmd = ["sshpass", "-p", vm_password, "ssh"] + ssh_options + [f"{vm_user}@{vm_ip}", f"rm -f {remote_log}"]
            subprocess.run(cleanup_cmd, check=False)
            if os.path.exists(local_log):
                os.remove(local_log)
        except Exception as e:
            print(f"  ! Avertissement: Le nettoyage des logs a échoué: {e}")


def _append_result_to_csv(result_data):
    """Ajoute une ligne de résultat au fichier CSV."""
    try:
        with open(OUTPUT_FILES["raw_results_csv"], "a", newline="", encoding="utf-8") as f:
            # L'ordre des clés doit correspondre à l'en-tête défini dans initialize_csv
            writer = csv.DictWriter(f, fieldnames=result_data.keys())
            writer.writerow(result_data)
    except IOError as e:
        print(f"Erreur lors de l'écriture dans le fichier CSV : {e}")

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
    parser = argparse.ArgumentParser(description="Script de benchmark avancé pour ODB.")
    parser.add_argument(
        '--mode', type=str, default='all',
        choices=['all', 'motivation', 'table', 'latency'],
        help="Mode d'exécution: 'all' (tout exécuter), 'motivation' (baseline et graphiques de motivation), 'table' (générer tableau comparatif), 'latency' (analyse de latence)."
    )
    args = parser.parse_args()

    print("Début de la campagne de benchmark...")

    if args.mode == 'all':
        write_reproducibility_report()
        initialize_csv()
        run_scenarios()

    try:
        results_df = pd.read_csv(OUTPUT_FILES["raw_results_csv"])
        if results_df.empty:
            print("Le fichier de résultats est vide. Aucune analyse possible.")
            return
    except FileNotFoundError:
        print(f"Fichier de résultats '{OUTPUT_FILES['raw_results_csv']}' non trouvé. Veuillez d'abord exécuter une campagne de tests (--mode all).")
        return

    if args.mode in ['all', 'motivation']:
        generate_motivation_plots(results_df)

    if args.mode in ['all', 'table']:
        generate_comparison_table(results_df)

    if args.mode in ['all', 'latency']:
        analyze_latency_distribution(results_df)

    print("\nCampagne de benchmark terminée.")


def generate_motivation_plots(df):
    """Génère les graphiques de motivation (RPSmax, CPU, Bandwidth vs. taille) pour le servlet 'Serv'."""
    print("\nGénération des graphiques de motivation pour 'Serv'...")
    plots_dir = "plots"
    os.makedirs(plots_dir, exist_ok=True)

    serv_df = df[df['servlet_name'] == 'Serv'].copy()
    if serv_df.empty:
        print("Aucune donnée trouvée pour le servlet 'Serv'. Impossible de générer les graphiques.")
        return

    image_size_map = {name: details['size_kb'] for name, details in PAYLOADS.items()}
    serv_df['image_size_kb'] = serv_df['image_name'].map(image_size_map)

    peak_perf_df = serv_df.loc[serv_df.groupby('image_name')['observed_rps'].idxmax()].sort_values('image_size_kb')
    x_axis = peak_perf_df['image_size_kb']

    fig, axes = plt.subplots(3, 1, figsize=(12, 18), sharex=True)
    fig.suptitle("Scénario de Motivation: Performance du Servlet Standard ('Serv')", fontsize=16)

    axes[0].plot(x_axis, peak_perf_df['observed_rps'], marker='o', color='b')
    axes[0].set_title('RPS Maximum vs. Taille de la Charge Utile')
    axes[0].set_ylabel('RPS Maximum (req/s)')
    axes[0].grid(True)

    axes[1].plot(x_axis, peak_perf_df['transfer_MBs'], marker='o', color='g')
    axes[1].set_title('Bande Passante à RPS Maximum')
    axes[1].set_ylabel('Bande Passante (MB/s)')
    axes[1].grid(True)

    axes[2].plot(x_axis, peak_perf_df['vm_cpu_avg_percent'], marker='o', color='r')
    axes[2].set_title('Utilisation CPU à RPS Maximum')
    axes[2].set_ylabel('Utilisation CPU (%)')
    axes[2].set_xlabel('Taille de la Charge Utile (KB)')
    axes[2].set_ylim(0, 110)
    axes[2].grid(True)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    filename = f"{plots_dir}/motivation_scenario_serv_performance.png"
    plt.savefig(filename)
    plt.close()
    print(f"  > Graphiques de motivation sauvegardés : {filename}")


def generate_comparison_table(df):
    """Génère un tableau comparatif des RPSmax pour chaque servlet et image."""
    print("\nGénération du tableau comparatif des RPSmax...")

    image_size_map = {name: details['size_kb'] for name, details in PAYLOADS.items()}
    df['image_size_kb'] = df['image_name'].map(image_size_map)

    peak_perf_df = df.loc[df.groupby(['servlet_name', 'image_name'])['observed_rps'].idxmax()]

    comparison_pivot = peak_perf_df.pivot_table(index='servlet_name', columns='image_name', values='observed_rps')

    sorted_columns = sorted(comparison_pivot.columns, key=lambda x: image_size_map[x])
    comparison_pivot = comparison_pivot[sorted_columns]

    print("\n" + "="*80)
    print("                      Tableau Comparatif des RPS Maximum (req/s)")
    print("="*80)
    print(comparison_pivot.to_string(float_format="%.2f"))
    print("="*80)


def analyze_latency_distribution(df):
    """Analyse la distribution de latence en capturant des histogrammes HDR aux points de performance max."""
    print("\nLancement de l'analyse détaillée de la latence...")
    latency_dir = "latency_analysis"
    os.makedirs(latency_dir, exist_ok=True)

    target_images = ["1k.jpg", "10k.jpg", "100k.jpg"]
    df_subset = df[df['image_name'].isin(target_images)]

    if df_subset.empty:
        print("  ! Aucune donnée pour les images cibles de l'analyse de latence. Annulation.")
        return

    peak_perf_df = df_subset.loc[df_subset.groupby(['servlet_name', 'image_name'])['observed_rps'].idxmax()]

    for _, row in peak_perf_df.iterrows():
        servlet_name = row['servlet_name']
        image_name = row['image_name']
        peak_rate = int(row['target_rate_rps'])
        strategy = BENCHMARK_STRATEGIES[servlet_name]

        print(f"\n  > Capture de l'histogramme pour '{servlet_name}' avec '{image_name}' à {peak_rate} RPS...")
        url = f"http://{TOPOLOGY['intermediate_vm']['ip']}:8080{APPLICATIONS[servlet_name]['endpoint']}?machine={TOPOLOGY['backend_server']['hostname']}&image={image_name}"
        hdr_file = f"{latency_dir}/{servlet_name}_{image_name.replace('.jpg', '')}.hdr"

        run_single_wrk2_test(url, peak_rate, strategy['connections'], strategy['threads'], strategy['duration_seconds'], strategy['timeout_seconds'], hdr_histogram_output=hdr_file)

    print("\nGénération du graphique de distribution de la latence...")
    plt.figure(figsize=(12, 8))
    styles = {'Serv': 'blue', 'Serv-odb': 'red'}
    line_styles = {'1k.jpg': '-', '10k.jpg': '--', '100k.jpg': ':'}

    for _, row in peak_perf_df.iterrows():
        servlet_name = row['servlet_name']
        image_name = row['image_name']
        hdr_file = f"{latency_dir}/{servlet_name}_{image_name.replace('.jpg', '')}.hdr"

        if os.path.exists(hdr_file):
            try:
                hist_df = pd.read_csv(hdr_file, skiprows=3, delim_whitespace=True, usecols=['Value', 'Percentile'], header=0)
                hist_df['Value_ms'] = hist_df['Value'] / 1000.0
                plt.plot(hist_df['Percentile'], hist_df['Value_ms'],
                         label=f'{servlet_name} - {image_name}',
                         color=styles.get(servlet_name),
                         linestyle=line_styles.get(image_name))
            except Exception as e:
                print(f"  ! Erreur lors du parsing de {hdr_file}: {e}")

    plt.title('Distribution de la Latence (Histogramme HDR) aux RPS Maximum')
    plt.xlabel('Percentile')
    plt.ylabel('Latence (ms)')
    plt.grid(True, which="both", ls="--")
    plt.xscale('log')
    plt.legend()

    filename = f"{latency_dir}/latency_distribution_comparison.png"
    plt.savefig(filename)
    plt.close()
    print(f"  > Graphique de distribution sauvegardé : {filename}")

if __name__ == "__main__":
    main()
