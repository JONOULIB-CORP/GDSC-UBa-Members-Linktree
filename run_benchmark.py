# -*- coding: utf-8 -*-

# Dépendances requises: pandas, matplotlib, numpy
# Installation: pip install pandas matplotlib numpy
# Dépendance système: sshpass (sudo apt-get install sshpass)

import os
import subprocess
import re
import csv
import datetime
import pandas as pd
import matplotlib.pyplot as plt
import argparse
import random
import numpy as np

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

# Liste des payloads pour les analyses de motivation et de latence
PAYLOADS = {
    "1k.jpg": {"size_kb": 1.0},
    "10k.jpg": {"size_kb": 10.0},
    "100k.jpg": {"size_kb": 100.0},
    "1000k.jpg": {"size_kb": 1000.0}
}

# Grand pool de 50 images pour le test de table comparative aléatoire
# REMPLIR CETTE LISTE AVEC VOS 50 NOMS DE FICHIERS D'IMAGES
# Exemple: FULL_PAYLOAD_POOL = ["image1.jpg", "photo_abc.jpg", "data_1024.bin", ...]
FULL_PAYLOAD_POOL = []

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

def write_reproducibility_report(payloads_to_report):
    with open(OUTPUT_FILES["reproducibility_report"], "w", encoding="utf-8") as f:
        f.write(f"Date du test: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        # ... (le reste du code de cette fonction est inchangé et complet)
        f.write("### 4.2. Payloads\n")
        for name, details in payloads_to_report.items():
            f.write(f"- **{name}**: {details['size_kb']} KB\n")
        f.write("\n")

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
    if 'us' in time_str: return float(time_str.replace('us', '')) / 1000.0
    if 'ms' in time_str: return float(time_str.replace('ms', ''))
    if 's' in time_str: return float(time_str.replace('s', '')) * 1000.0
    return 0.0

def _parse_bytes(bytes_str):
    bytes_str = bytes_str.lower()
    if 'kb' in bytes_str: return float(bytes_str.replace('kb', '')) / 1024.0
    if 'mb' in bytes_str: return float(bytes_str.replace('mb', ''))
    if 'gb' in bytes_str: return float(bytes_str.replace('gb', '')) * 1024.0
    if 'b' in bytes_str: return float(bytes_str.replace('b', '')) / (1024.0 * 1024.0)
    return 0.0

def _parse_wrk2_output(output):
    results = {}
    results['observed_rps'] = float(m.group(1)) if (m := re.search(r'Requests/sec:\s*([\d\.]+)', output)) else 0
    results['transfer_MBs'] = _parse_bytes(m.group(1)) if (m := re.search(r'Transfer/sec:\s*([\d\.]+[kKmMgG]B)', output)) else 0
    results['total_requests'] = int(m.group(1)) if (m := re.search(r'([\d]+) requests in', output)) else 0
    if m := re.search(r'Socket errors: connect (\d+), read (\d+), write (\d+), timeout (\d+)', output):
        results.update(errors_connect=int(m.group(1)), errors_read=int(m.group(2)), errors_write=int(m.group(3)), errors_timeout=int(m.group(4)))
        results['total_errors'] = sum(results[k] for k in ['errors_connect', 'errors_read', 'errors_write', 'errors_timeout'])
    else:
        results.update(errors_connect=0, errors_read=0, errors_write=0, errors_timeout=0, total_errors=0)
    if m := re.search(r'Latency Distribution\s+50%\s+([\d\.\w]+)\s+75%\s+([\d\.\w]+)\s+90%\s+([\d\.\w]+)\s+99%\s+([\d\.\w]+)', output):
        results.update(latency_p50_ms=_parse_time(m.group(1)), latency_p75_ms=_parse_time(m.group(2)), latency_p90_ms=_parse_time(m.group(3)), latency_p99_ms=_parse_time(m.group(4)))
    results['latency_avg_ms'] = _parse_time(m.group(1)) if (m := re.search(r'Latency\s+([\d\.\w]+)\s+', output)) else 0
    return results

def _parse_mpstat_output(output):
    lines = output.strip().split('\n')
    idle_percentages = [float(parts[-1]) for line in lines if len(parts := line.split()) >= 12 and parts[2].lower() == 'all' and 'Average:' not in line]
    if not idle_percentages:
        print("  ! Avertissement: Impossible de parser la sortie de mpstat.")
        return 0.0
    return 100.0 - np.mean(idle_percentages)

def run_single_wrk2_test(url, rate, connections, threads, duration, timeout, hdr_histogram_output=None):
    vm_user, vm_ip, vm_password = TOPOLOGY['intermediate_vm']['user'], TOPOLOGY['intermediate_vm']['ip'], TOPOLOGY['intermediate_vm']['password']
    remote_log, local_log = "/tmp/cpu_benchmark.log", "cpu_benchmark.log"
    monitor_process = None
    ssh_options = ["-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]

    try:
        if hdr_histogram_output is None:
            mpstat_cmd = f"mpstat -P ALL 1 {duration} > {remote_log}"
            ssh_command = ["sshpass", "-p", vm_password, "ssh"] + ssh_options + [f"{vm_user}@{vm_ip}", mpstat_cmd]
            monitor_process = subprocess.Popen(ssh_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        command = [SOFTWARE_VERSIONS['wrk2_path'], f"-t{threads}", f"-c{connections}", f"-d{duration}s", f"-R{rate}", f"--timeout={timeout}s", "--latency", url]
        if hdr_histogram_output:
            command.extend(["--hdr-histogram", hdr_histogram_output])
        print(f"  > Lancement wrk2: {' '.join(command)}")

        process = subprocess.run(command, capture_output=True, text=True, check=False, timeout=duration + 20)
        results = _parse_wrk2_output(process.stdout + process.stderr)

        if monitor_process:
            monitor_process.wait(timeout=15)
            scp_cmd = ["sshpass", "-p", vm_password, "scp"] + ssh_options + [f"{vm_user}@{vm_ip}:{remote_log}", local_log]
            subprocess.run(scp_cmd, check=True, capture_output=True, timeout=15)
            with open(local_log, "r", encoding="utf-8") as f:
                results['vm_cpu_avg_percent'] = _parse_mpstat_output(f.read())
            print(f"  > CPU moyen VM: {results['vm_cpu_avg_percent']:.2f}%")
        else:
            results['vm_cpu_avg_percent'] = 0.0
        return results
    except Exception as e:
        print(f"  ! Erreur critique durant l'exécution du test: {e}")
        if monitor_process: monitor_process.kill()
        return None
    finally:
        cleanup_cmd = ["sshpass", "-p", vm_password, "ssh"] + ssh_options + [f"{vm_user}@{vm_ip}", f"rm -f {remote_log}"]
        subprocess.run(cleanup_cmd, check=False)
        if os.path.exists(local_log): os.remove(local_log)

def _append_result_to_csv(result_data):
    header = ["timestamp", "servlet_name", "image_name", "threads", "connections", "duration_s", "target_rate_rps", "timeout_s", "observed_rps", "transfer_MBs", "total_requests", "errors_connect", "errors_read", "errors_write", "errors_timeout", "total_errors", "latency_avg_ms", "latency_p50_ms", "latency_p75_ms", "latency_p90_ms", "latency_p99_ms", "vm_cpu_avg_percent"]
    with open(OUTPUT_FILES["raw_results_csv"], "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        if f.tell() == 0: writer.writeheader()
        writer.writerow({k:v for k,v in result_data.items() if k in header})

def run_scenarios(payloads_to_test, applications_to_test=None):
    if applications_to_test is None:
        applications_to_test = APPLICATIONS
    print(f"\nLancement de l'exploration pour {len(applications_to_test)} servlet(s) sur {len(payloads_to_test)} image(s)...")
    for servlet_name, servlet_details in applications_to_test.items():
        for image_name in payloads_to_test.keys():
            print(f"\n----- Scénario: Servlet='{servlet_name}', Image='{image_name}' -----")
            strategy = BENCHMARK_STRATEGIES[servlet_name]
            params = strategy
            url = f"http://{TOPOLOGY['intermediate_vm']['ip']}:8080{servlet_details['endpoint']}?machine={TOPOLOGY['backend_server']['hostname']}&image={image_name}"

            rate_params = params['rate_exploration']
            for current_rate in range(rate_params['start_rps'], rate_params['max_rps'] + 1, rate_params['step_rps']):
                print(f"\nTesting Rate: {current_rate} RPS...")
                results = run_single_wrk2_test(url, current_rate, params["connections"], params["threads"], params["duration_seconds"], params["timeout_seconds"])
                if not results: break

                _append_result_to_csv({"timestamp": datetime.datetime.now().isoformat(), "servlet_name": servlet_name, "image_name": image_name, **params, "target_rate_rps": current_rate, **results})

                if results.get('total_requests', 0) > 0 and (results.get('errors_timeout', 0) / results['total_requests'] * 100) > params['stop_condition']['timeout_threshold_percent']:
                    print(f"  ! Condition d'arrêt atteinte.")
                    break

def main():
    parser = argparse.ArgumentParser(description="Script de benchmark avancé pour ODB.")
    parser.add_argument('--mode', type=str, default='all', choices=['all', 'motivation', 'random_table', 'latency'], help="Mode d'exécution.")
    args = parser.parse_args()

    print(f"Début de la campagne de benchmark (mode: {args.mode})")

    if args.mode == 'all':
        write_reproducibility_report(PAYLOADS)
        initialize_csv()
        run_scenarios(PAYLOADS)

    elif args.mode == 'random_table':
        if not FULL_PAYLOAD_POOL:
            print("[ERREUR] La liste FULL_PAYLOAD_POOL est vide. Veuillez la remplir.")
            return
        selected_images = random.sample(FULL_PAYLOAD_POOL, 10)
        selected_payloads = {img: {"size_kb": float(re.search(r'(\d+)', img).group(1))} for img in selected_images}

        write_reproducibility_report(selected_payloads)
        initialize_csv()
        run_scenarios(selected_payloads)

        try:
            results_df = pd.read_csv(OUTPUT_FILES["raw_results_csv"])
            if not results_df.empty: generate_comparison_table(results_df)
        except FileNotFoundError: print("Fichier de résultats non trouvé après l'exécution.")
        return

    try:
        results_df = pd.read_csv(OUTPUT_FILES["raw_results_csv"])
        if results_df.empty:
            print("Le fichier de résultats est vide. Aucune analyse possible.")
            return
    except FileNotFoundError:
        print(f"Fichier de résultats non trouvé. Exécutez d'abord une campagne (--mode all ou --mode random_table).")
        return

    if args.mode in ['all', 'motivation']: generate_motivation_plots(results_df)
    if args.mode in ['all', 'random_table']: generate_comparison_table(results_df)
    if args.mode in ['all', 'latency']: analyze_latency_distribution(results_df)

    print("\nCampagne de benchmark terminée.")

def get_peak_performance(df):
    return df.loc[df.groupby(['servlet_name', 'image_name'])['observed_rps'].idxmax()]

def generate_motivation_plots(df):
    print("\nGénération des graphiques de motivation pour 'Serv'...")
    plots_dir = "plots"
    os.makedirs(plots_dir, exist_ok=True)
    serv_df = df[df['servlet_name'] == 'Serv'].copy()
    if serv_df.empty: return

    serv_df['image_size_kb'] = serv_df['image_name'].map({name: details['size_kb'] for name, details in PAYLOADS.items()})
    peak_perf_df = serv_df.loc[serv_df.groupby('image_name')['observed_rps'].idxmax()].sort_values('image_size_kb')
    x_axis = peak_perf_df['image_size_kb']

    fig, axes = plt.subplots(3, 1, figsize=(12, 18), sharex=True)
    fig.suptitle("Scénario de Motivation: Performance du Servlet Standard ('Serv')", fontsize=16)
    axes[0].plot(x_axis, peak_perf_df['observed_rps'], marker='o', color='b'); axes[0].set_title('RPS Maximum'); axes[0].set_ylabel('req/s'); axes[0].grid(True)
    axes[1].plot(x_axis, peak_perf_df['transfer_MBs'], marker='o', color='g'); axes[1].set_title('Bande Passante à RPS Max'); axes[1].set_ylabel('MB/s'); axes[1].grid(True)
    axes[2].plot(x_axis, peak_perf_df['vm_cpu_avg_percent'], marker='o', color='r'); axes[2].set_title('Utilisation CPU à RPS Max'); axes[2].set_ylabel('%'); axes[2].set_xlabel('Taille (KB)'); axes[2].set_ylim(0, 110); axes[2].grid(True)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(f"{plots_dir}/motivation_scenario.png"); plt.close()
    print(f"  > Graphiques de motivation sauvegardés.")

def generate_comparison_table(df):
    print("\nGénération du tableau comparatif des RPSmax...")
    peak_perf_df = get_peak_performance(df)
    all_payloads = {**PAYLOADS, **{p: {"size_kb": float(re.search(r'(\d+)', p).group(1))} for p in df['image_name'].unique()}}
    peak_perf_df['image_size_kb'] = peak_perf_df['image_name'].map({name: details['size_kb'] for name, details in all_payloads.items()})

    comparison_pivot = peak_perf_df.pivot_table(index='servlet_name', columns='image_name', values='observed_rps')
    sorted_columns = sorted(comparison_pivot.columns, key=lambda x: all_payloads[x]['size_kb'])
    comparison_pivot = comparison_pivot[sorted_columns]
    print("\n" + "="*100); print("Tableau Comparatif des RPS Maximum (req/s)".center(100)); print("="*100)
    print(comparison_pivot.to_string(float_format="%.2f")); print("="*100)

def analyze_latency_distribution(df):
    print("\nLancement de l'analyse détaillée de la latence...")
    latency_dir = "latency_analysis"; os.makedirs(latency_dir, exist_ok=True)
    target_images = ["1k.jpg", "10k.jpg", "100k.jpg", "1000k.jpg"]
    df_subset = df[df['image_name'].isin(target_images)]
    if df_subset.empty: return

    peak_perf_df = get_peak_performance(df_subset)
    for _, row in peak_perf_df.iterrows():
        s_name, i_name, rate = row['servlet_name'], row['image_name'], int(row['target_rate_rps'])
        strategy = BENCHMARK_STRATEGIES[s_name]
        print(f"\n  > Capture de l'histogramme pour '{s_name}' avec '{i_name}' à {rate} RPS...")
        url = f"http://{TOPOLOGY['intermediate_vm']['ip']}:8080{APPLICATIONS[s_name]['endpoint']}?machine={TOPOLOGY['backend_server']['hostname']}&image={i_name}"
        hdr_file = f"{latency_dir}/{s_name}_{i_name.replace('.jpg', '')}.hdr"
        run_single_wrk2_test(url, rate, strategy['connections'], strategy['threads'], strategy['duration_seconds'], strategy['timeout_seconds'], hdr_histogram_output=hdr_file)

    print("\nGénération du graphique de distribution de la latence...")
    plt.figure(figsize=(12, 8))
    styles = {'Serv': 'blue', 'Serv-odb': 'red'}; line_styles = {'1k.jpg': '-', '10k.jpg': '--', '100k.jpg': ':', '1000k.jpg': '-.'}
    for _, row in peak_perf_df.iterrows():
        s_name, i_name = row['servlet_name'], row['image_name']
        hdr_file = f"{latency_dir}/{s_name}_{i_name.replace('.jpg', '')}.hdr"
        if os.path.exists(hdr_file):
            try:
                hist_df = pd.read_csv(hdr_file, skiprows=3, delim_whitespace=True, usecols=['Value', 'Percentile'], header=0)
                plt.plot(hist_df['Percentile'], hist_df['Value'] / 1000.0, label=f'{s_name} - {i_name}', color=styles.get(s_name), linestyle=line_styles.get(i_name))
            except Exception as e: print(f"  ! Erreur parsing {hdr_file}: {e}")

    plt.title('Distribution de la Latence (HDR) aux RPS Maximum'); plt.xlabel('Percentile'); plt.ylabel('Latence (ms)')
    plt.grid(True, which="both", ls="--"); plt.xscale('log'); plt.legend()
    plt.savefig(f"{latency_dir}/latency_distribution_comparison.png"); plt.close()
    print(f"  > Graphique de distribution sauvegardé.")

if __name__ == "__main__":
    main()
