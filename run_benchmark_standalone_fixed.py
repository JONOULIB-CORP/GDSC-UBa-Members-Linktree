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
# SECTION 1: CONFIGURATION DE L'EXPÉRIMENTATION (CHARGÉE DYNAMIQUEMENT)
# ==============================================================================

# ==============================================================================
# SECTION 1: FICHE TECHNIQUE DE L'EXPÉRIMENTATION (CONFIGURATION STATIQUE)
# ==============================================================================

TOPOLOGY = {
    "client_host": {
        "hostname": "gros-114", "ip": "172.16.66.114"
    },
    "intermediate_vm": {
        "vm_name": "my-vm", "ip": "10.144.40.1", "user": "root", "password": "grid5000"
    },
    "backend_server": {
        "hostname": "gros-111", "ip": "172.16.66.111"
    }
}

PAYLOADS = {
    "image_1KB.jpg": 1.0,
    "image_10KB.jpg": 10.0,
    "image_100KB.jpg": 100.0,
    "image_1000KB.jpg": 1024.0
}

FULL_PAYLOAD_POOL = {
    "img_20k": 20.1, "img_50k": 50.3, "img_80k": 80.7, "img_120k": 120.2,
    "img_150k": 150.9, "img_180k": 180.4, "img_220k": 220.6, "img_250k": 250.1,
    "img_280k": 280.8, "img_320k": 320.3, "img_350k": 350.5, "img_380k": 380.9,
    "img_420k": 420.2, "img_450k": 450.7, "img_480k": 480.1, "img_520k": 520.6,
    "img_550k": 550.4, "img_580k": 580.8, "img_620k": 620.3, "img_650k": 650.9,
}

# Fiche technique statique de l'expérimentation
NETWORK_CAPACITIES = {
    "host_nic": {"interface": "eno1", "type": "Mellanox ConnectX-4 Lx", "theoretical_throughput_gbps": 25},
    "vm_nic": {"interface": "enp0s2", "theoretical_throughput_mbps": 100, "theoretical_throughput_MBs": 12.5}
}
SOFTWARE_VERSIONS = {
    "wrk2_path": "wrk2/wrk", "wrk2_version": "wrk 4.0.0", "java_version": "OpenJDK 17.0.10",
    "tomcat_version": "Apache Tomcat/11.0.1", "os_versions": "Ubuntu 22.04 LTS"
}
APPLICATIONS = { "Serv": {"name": "Serv", "endpoint": "/serv/Serv"}, "Serv-odb": {"name": "Serv-odb", "endpoint": "/serv1/Serv"} }
# Stratégies de benchmark ajustées avec un timeout plus court pour un arrêt plus rapide en cas de surcharge
BENCHMARK_STRATEGIES = {
    "Serv": { "threads": 8, "connections": 15, "duration_seconds": 60, "timeout_seconds": 5, "rate_exploration": {"start_rps": 200, "step_rps": 100, "max_rps": 3000}, "stop_condition": {"timeout_threshold_percent": 1.0} },
    "Serv-odb": { "threads": 8, "connections": 100, "duration_seconds": 60, "timeout_seconds": 5, "rate_exploration": {"start_rps": 1000, "step_rps": 500, "max_rps": 10000}, "stop_condition": {"timeout_threshold_percent": 1.0} }
}
OUTPUT_FILES = {"reproducibility_report": "reproducibility_report.md", "raw_results_csv": "results_raw.csv"}

def write_reproducibility_report(payloads_to_report):
    with open(OUTPUT_FILES["reproducibility_report"], "w", encoding="utf-8") as f:
        f.write(f"Date du test: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("## 1. Topologie de l'expérimentation\n\n")
        f.write("### 1.1. Client (C)\n")
        for key, value in TOPOLOGY["client_host"].items(): f.write(f"- **{key.replace('_', ' ').capitalize()}**: {value}\n")
        f.write("\n### 1.2. Intermédiaire (I)\n")
        for key, value in TOPOLOGY["intermediate_vm"].items(): f.write(f"- **{key.replace('_', ' ').capitalize()}**: {value}\n")
        f.write("\n### 1.3. Serveur final (S)\n")
        for key, value in TOPOLOGY["backend_server"].items(): f.write(f"- **{key.replace('_', ' ').capitalize()}**: {value}\n")
        f.write("\n## 2. Configuration réseau & capacités\n\n")
        # ... (le reste de la fonction reste inchangé)

def initialize_csv():
    header = ["timestamp", "servlet_name", "image_name", "image_size_kb", "threads", "connections", "duration_s", "target_rate_rps", "timeout_s", "observed_rps", "transfer_MBs", "total_requests", "errors_connect", "errors_read", "errors_write", "errors_timeout", "total_errors", "latency_avg_ms", "latency_p50_ms", "latency_p75_ms", "latency_p90_ms", "latency_p99_ms", "vm_cpu_avg_percent"]
    try:
        with open(OUTPUT_FILES["raw_results_csv"], "w", newline="", encoding="utf-8") as f: csv.writer(f).writerow(header)
        print(f"Fichier de résultats initialisé : {OUTPUT_FILES['raw_results_csv']}")
    except IOError as e: print(f"Erreur CSV : {e}"); exit(1)

def _parse_time(t):
    if 'us' in t: return float(t.replace('us',''))/1000.0
    if 'ms' in t: return float(t.replace('ms',''))
    if 's' in t: return float(t.replace('s',''))*1000.0
    return 0.0

def _parse_bytes(b):
    b = b.lower()
    if 'kb' in b: return float(b.replace('kb',''))/1024.0
    if 'mb' in b: return float(b.replace('mb',''))
    if 'gb' in b: return float(b.replace('gb',''))*1024.0
    if 'b' in b: return float(b.replace('b',''))/(1024.0*1024.0)
    return 0.0

def _parse_wrk2_output(output):
    res = { 'observed_rps': 0, 'transfer_MBs': 0, 'total_requests': 0, 'errors_connect': 0, 'errors_read': 0, 'errors_write': 0, 'errors_timeout': 0, 'total_errors': 0, 'latency_p50_ms': 0, 'latency_p75_ms': 0, 'latency_p90_ms': 0, 'latency_p99_ms': 0, 'latency_avg_ms': 0 }
    try: res['observed_rps'] = float(re.search(r'Requests/sec:\s*([\d\.]+)', output).group(1))
    except (AttributeError, ValueError): pass
    try: res['transfer_MBs'] = _parse_bytes(re.search(r'Transfer/sec:\s*([\d\.]+[kKmMgG]B)', output).group(1))
    except (AttributeError, ValueError): pass
    try: res['total_requests'] = int(re.search(r'([\d]+) requests in', output).group(1))
    except (AttributeError, ValueError): pass
    try:
        if m := re.search(r'Socket errors: connect (\d+), read (\d+), write (\d+), timeout (\d+)', output):
            res.update(errors_connect=int(m.group(1)), errors_read=int(m.group(2)), errors_write=int(m.group(3)), errors_timeout=int(m.group(4)), total_errors=sum(map(int, m.groups())))
    except (AttributeError, ValueError): pass
    try:
        if m := re.search(r'Latency\s+([\d\.\w]+)\s+(?!Distribution)', output):
             res['latency_avg_ms'] = _parse_time(m.group(1))
    except (AttributeError, ValueError): pass
    try:
        if m := re.search(r'Latency Distribution\s+50%\s+([\d\.\w]+)\s+75%\s+([\d\.\w]+)\s+90%\s+([\d\.\w]+)\s+99%\s+([\d\.\w]+)', output):
            res.update(latency_p50_ms=_parse_time(m.group(1)), latency_p75_ms=_parse_time(m.group(2)), latency_p90_ms=_parse_time(m.group(3)), latency_p99_ms=_parse_time(m.group(4)))
    except (AttributeError, ValueError): pass
    return res

def _parse_mpstat_output(output):
    idle = [float(p[-1]) for l in output.strip().split('\n') if len(p := l.split()) >= 12 and p[2].lower()=='all' and 'Average:' not in l]
    return 100.0 - np.mean(idle) if idle else 0.0

def run_single_wrk2_test(url, rate, connections, threads, duration_seconds, timeout_seconds, hdr_histogram_output=None):
    vm = TOPOLOGY['intermediate_vm']; remote_log, local_log = "/tmp/cpu.log", "cpu.log"; mon_proc=None
    ssh_opts = ["-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]
    try:
        if hdr_histogram_output is None:
            ssh_cmd = ["sshpass","-p",vm['password'],"ssh"]+ssh_opts+[f"{vm['user']}@{vm['ip']}",f"mpstat -P ALL 1 {duration_seconds} > {remote_log}"]
            mon_proc = subprocess.Popen(ssh_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        wrk2_cmd = [SOFTWARE_VERSIONS['wrk2_path'],f"-t{threads}",f"-c{connections}",f"-d{duration_seconds}s",f"-R{rate}",f"--timeout={timeout_seconds}s","--latency",url]
        if hdr_histogram_output: wrk2_cmd.extend(["--hdr-histogram", hdr_histogram_output])
        print(f"  > Lancement wrk2: {' '.join(wrk2_cmd)}")
        proc = subprocess.run(wrk2_cmd, capture_output=True, text=True, check=False, timeout=duration_seconds+20)
        results = _parse_wrk2_output(proc.stdout + proc.stderr)

        if mon_proc:
            mon_proc.wait(duration_seconds + 10)
            scp_cmd = ["sshpass","-p",vm['password'],"scp"]+ssh_opts+[f"{vm['user']}@{vm['ip']}:{remote_log}",local_log]
            subprocess.run(scp_cmd, check=True, stdout=subprocess.DEVNULL, stderr=None, timeout=15)
            with open(local_log,"r") as f: results['vm_cpu_avg_percent'] = _parse_mpstat_output(f.read())
            print(f"  > CPU moyen VM: {results['vm_cpu_avg_percent']:.2f}%")
        else: results['vm_cpu_avg_percent'] = 0.0
        return results
    except Exception as e:
        print(f"  ! Erreur critique: {e}");
        if mon_proc: mon_proc.kill()
        return None
    finally:
        subprocess.run(["sshpass","-p",vm['password'],"ssh"]+ssh_opts+[f"{vm['user']}@{vm['ip']}",f"rm -f {remote_log}"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(local_log): os.remove(local_log)

def _append_result_to_csv(result_data):
    header = ["timestamp","servlet_name","image_name","image_size_kb","threads","connections","duration_s","target_rate_rps","timeout_s","observed_rps","transfer_MBs","total_requests","errors_connect","errors_read","errors_write","errors_timeout","total_errors","latency_avg_ms","latency_p50_ms","latency_p75_ms","latency_p90_ms","latency_p99_ms","vm_cpu_avg_percent"]
    new = not os.path.exists(OUTPUT_FILES["raw_results_csv"])
    with open(OUTPUT_FILES["raw_results_csv"], "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        if new: w.writeheader()
        w.writerow({k:v for k,v in result_data.items() if k in header})

def run_scenarios(payloads, apps=None):
    if apps is None: apps = APPLICATIONS
    print(f"\nLancement de l'exploration pour {len(payloads)} image(s) sur {len(apps)} servlet(s)...")
    for i_name, i_size in payloads.items():
        print(f"\n===== Test pour l'image : '{i_name}' ({i_size} KB) =====")
        for s_name, s_details in apps.items():
            print(f"\n--- Scénario: Servlet='{s_name}' ---")
            strat = BENCHMARK_STRATEGIES[s_name]
            url = f"http://{TOPOLOGY['intermediate_vm']['ip']}:8080{s_details['endpoint']}?machine={TOPOLOGY['backend_server']['hostname']}&image={i_name}"
            for rate in range(strat['rate_exploration']['start_rps'], strat['rate_exploration']['max_rps'] + 1, strat['rate_exploration']['step_rps']):
                print(f"\nTesting Rate: {rate} RPS...")
                res = run_single_wrk2_test(url, rate, **{k:v for k,v in strat.items() if k in ['connections','threads','duration_seconds','timeout_seconds']})
                if not res: break
                if res and res.get('observed_rps', 0) > 0:
                    theoretical_bw = res['observed_rps'] * i_size / 1024.0
                    measured_bw = res.get('transfer_MBs', 0)
                    print(f"  > [DEBUG] Bande Passante: Mesurée={measured_bw:.2f} MB/s vs Théorique={theoretical_bw:.2f} MB/s")
                flat_result = {"timestamp": datetime.datetime.now().isoformat(),"servlet_name": s_name,"image_name": i_name,"image_size_kb": i_size,"target_rate_rps": rate,**strat,**res}
                _append_result_to_csv(flat_result)
                if res.get('total_requests', 0) > 0 and (res.get('errors_timeout', 0) / res['total_requests'] * 100) > strat['stop_condition']['timeout_threshold_percent']:
                    print("  ! Condition d'arrêt atteinte (seuil de timeouts dépassé). Passage au scénario suivant.")
                    break

def execute_benchmark_scenario(mode, payloads, apps=None):
    """Fonction helper pour exécuter une campagne de test et sauvegarder les résultats."""
    mode_to_csv = {
        'motivation': 'results_motivation.csv',
        'odb_test': 'results_odb.csv',
        'random_table': 'results_random_table.csv'
    }
    OUTPUT_FILES['raw_results_csv'] = mode_to_csv[mode]
    print(f"\n--- Lancement de la campagne de test pour le mode '{mode}' ---")
    write_reproducibility_report(payloads)
    initialize_csv()
    run_scenarios(payloads, apps)
    print(f"--- Campagne de test '{mode}' terminée ---")

def main():
    parser = argparse.ArgumentParser(description="Script de benchmark ODB.")
    parser.add_argument('--mode', type=str, default='motivation', choices=['motivation', 'odb_test', 'random_table', 'latency'])
    args = parser.parse_args()
    print(f"Mode d'exécution: {args.mode}")

    mode_to_csv = {
        'motivation': 'results_motivation.csv',
        'odb_test': 'results_odb.csv',
        'random_table': 'results_random_table.csv'
    }

    if args.mode == 'motivation':
        execute_benchmark_scenario('motivation', PAYLOADS, {"Serv": APPLICATIONS["Serv"]})
    elif args.mode == 'odb_test':
        execute_benchmark_scenario('odb_test', PAYLOADS, {"Serv-odb": APPLICATIONS["Serv-odb"]})
    elif args.mode == 'random_table':
        if not FULL_PAYLOAD_POOL:
            print("[ERREUR] Le dictionnaire 'FULL_PAYLOAD_POOL' est vide.")
            return

        target_count = 10
        results_file = 'results_random_table.csv'
        completed_images = set()

        if os.path.exists(results_file):
            try:
                df = pd.read_csv(results_file)
                if not df.empty:
                    image_counts = df.groupby('image_name')['servlet_name'].nunique()
                    completed_images = set(image_counts[image_counts == 2].index)
                    print(f"Fichier de résultats existant trouvé. {len(completed_images)}/{target_count} images déjà completées.")
            except (pd.errors.EmptyDataError, FileNotFoundError):
                print(f"Un fichier de résultats existant ('{results_file}') est vide ou corrompu. Il sera écrasé.")

        num_to_run = target_count - len(completed_images)

        if num_to_run > 0:
            available_images = [name for name in FULL_PAYLOAD_POOL.keys() if name not in completed_images]
            if len(available_images) < num_to_run:
                print(f"[AVERTISSEMENT] Pas assez d'images uniques disponibles pour atteindre {target_count}. Sélection de {len(available_images)} images.")
                num_to_run = len(available_images)

            if num_to_run > 0:
                selected_names = random.sample(available_images, num_to_run)
                payloads_to_run = {n: FULL_PAYLOAD_POOL[n] for n in selected_names}
                print(f"Sélection de {num_to_run} nouvelle(s) image(s) à tester: {list(payloads_to_run.keys())}")

                # Logique adaptée de execute_benchmark_scenario pour gérer l'ajout
                OUTPUT_FILES['raw_results_csv'] = results_file
                if not os.path.exists(results_file):
                    print("Aucun fichier de résultats existant. Création d'un nouveau fichier.")
                    initialize_csv()

                write_reproducibility_report(payloads_to_run)
                run_scenarios(payloads_to_run)
            else:
                print("Aucune nouvelle image à tester.")
        else:
            print(f"Le benchmark 'random_table' est déjà complet avec {len(completed_images)} images. Passage à l'analyse.")

    analysis_df = None
    if args.mode in ['motivation', 'odb_test', 'random_table']:
        analysis_file = mode_to_csv[args.mode]
        if os.path.exists(analysis_file):
            analysis_df = pd.read_csv(analysis_file)
    elif args.mode == 'latency':
        motivation_file = 'results_motivation.csv'
        odb_file = 'results_odb.csv'
        if not os.path.exists(motivation_file):
            print(f"[INFO] Fichier '{motivation_file}' introuvable. Lancement automatique du test 'motivation'.")
            execute_benchmark_scenario('motivation', PAYLOADS, {"Serv": APPLICATIONS["Serv"]})
        if not os.path.exists(odb_file):
            print(f"[INFO] Fichier '{odb_file}' introuvable. Lancement automatique du test 'odb_test'.")
            execute_benchmark_scenario('odb_test', PAYLOADS, {"Serv-odb": APPLICATIONS["Serv-odb"]})

        print(f"Fusion des fichiers '{motivation_file}' et '{odb_file}' pour l'analyse...")
        df_motivation = pd.read_csv(motivation_file)
        df_odb = pd.read_csv(odb_file)
        analysis_df = pd.concat([df_motivation, df_odb], ignore_index=True)

    if analysis_df is not None:
        try:
            if analysis_df.empty:
                print("Le jeu de données pour l'analyse est vide.")
                return
            if args.mode == 'motivation':
                generate_motivation_plots(analysis_df)
            elif args.mode == 'odb_test':
                pass # Ne génère aucun graphique, comme demandé
            elif args.mode == 'random_table':
                output_synth_path = mode_to_csv[args.mode].replace('.csv', '_synth.csv')
                generate_comparison_table(analysis_df, output_csv_path=output_synth_path)
            elif args.mode == 'latency':
                generate_latency_comparison_plot(analysis_df)
        except Exception as e:
            print(f"Une erreur est survenue lors de l'analyse : {e}")
    else:
        print("Aucun jeu de données n'a été chargé pour l'analyse.")

    print("\nCampagne de benchmark terminée.")

def get_peak_performance(df):
    return df.loc[df.groupby(['servlet_name', 'image_name'])['observed_rps'].idxmax()]

def generate_motivation_plots(df):
    print("\nGénération des graphiques de motivation...")
    plots_dir="plots"; os.makedirs(plots_dir, exist_ok=True)
    serv_df = df[df['servlet_name'] == 'Serv']
    if serv_df.empty:
        print(" ! Aucune donnée pour le servlet 'Serv' trouvée. Impossible de générer les graphiques.")
        return
    peak = get_peak_performance(serv_df).sort_values('image_size_kb')
    x = peak['image_size_kb']
    fig, axes = plt.subplots(3,1,figsize=(12,18),sharex=True)
    fig.suptitle("Motivation: Performance du Servlet Standard", fontsize=16)
    axes[0].plot(x, peak['observed_rps'], 'o-b'); axes[0].set_title('RPS Max vs Taille'); axes[0].set_ylabel('req/s'); axes[0].grid(True, which="both", ls="--")
    axes[1].plot(x, peak['transfer_MBs'], 'o-g'); axes[1].set_title('Bande Passante à RPS Max'); axes[1].set_ylabel('MB/s'); axes[1].grid(True, which="both", ls="--")
    axes[2].plot(x, peak['vm_cpu_avg_percent'], 'o-r'); axes[2].set_title('CPU à RPS Max'); axes[2].set_ylabel('%'); axes[2].set_xlabel('Taille (KB)'); axes[2].set_ylim(0,110); axes[2].grid(True, which="both", ls="--")
    plt.xscale('log')
    ticks = sorted(list(PAYLOADS.values()))
    labels = [name for name, size in sorted(PAYLOADS.items(), key=lambda item: item[1])]
    plt.xticks(ticks, labels, rotation=45)
    plt.tight_layout(rect=[0,0,1,0.96])
    output_path = f"{plots_dir}/motivation_corrected.png"
    plt.savefig(output_path)
    plt.close()
    print(f" > Graphiques de motivation corrigés sauvegardés dans : {output_path}")

def generate_comparison_table(df, output_csv_path=None):
    """
    Génère un tableau comparatif des performances de pointe (RPSmax),
    l'affiche dans la console et le sauvegarde dans un fichier CSV si spécifié.
    """
    print("\nGénération du tableau comparatif des RPSmax...")
    peak = get_peak_performance(df)

    # S'assurer que le pool complet d'images est disponible pour le mapping taille/nom
    all_payloads = {**PAYLOADS, **FULL_PAYLOAD_POOL}
    # S'assurer que la colonne de taille est bien présente en cas de valeurs manquantes
    if 'image_size_kb' not in peak.columns or peak['image_size_kb'].isnull().any():
        peak['image_name'] = peak['image_name'].map(all_payloads)

    # Gérer le cas où une image du CSV n'est pas dans le pool (peu probable mais prudent)
    peak.dropna(subset=['image_size_kb'], inplace=True)

    # --- AMÉLIORATION : Créer des en-têtes de colonnes clairs ---
    # Format: "nom_image (tailleKB)" pour une lisibilité maximale
    peak['column_header'] = peak.apply(lambda row: f"{row['image_name']} ({row['image_size_kb']}KB)", axis=1)

    # Créer le tableau croisé dynamique avec les nouveaux en-têtes
    pivot = peak.pivot_table(index='servlet_name', columns='column_header', values='observed_rps')

    # Trier les colonnes en se basant sur la taille originale de l'image
    # Cela garantit que le tableau est ordonné de la plus petite à la plus grande image
    header_to_size_map = peak.set_index('column_header')['image_size_kb'].to_dict()
    sorted_columns = sorted(pivot.columns, key=lambda c: header_to_size_map.get(c, 0))
    pivot = pivot[sorted_columns]

    # Afficher le tableau formaté dans la console
    print("\n" + "="*120)
    print("Tableau Comparatif des RPS Maximum (req/s)".center(120))
    print("="*120)
    print(pivot.to_string(float_format="%.2f"))
    print("="*120)

    # --- NOUVEAU : Sauvegarder le tableau dans un fichier CSV ---
    if output_csv_path:
        try:
            # S'assurer que le répertoire de sortie existe
            output_dir = os.path.dirname(output_csv_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            pivot.to_csv(output_csv_path, float_format="%.2f")
            print(f" > Tableau de synthèse sauvegardé dans : {output_csv_path}")
        except IOError as e:
            print(f" ! Erreur lors de la sauvegarde du fichier de synthèse : {e}")

def generate_latency_comparison_plot(df):
    """
    Génère un graphique comparant la latence moyenne à un RPS de référence fixe.
    Si des données sont manquantes pour Serv-odb à ce RPS, un test ciblé est lancé
    pour les générer "à la volée".
    """
    print("\nGénération du graphique de comparaison de latence à RPS fixe...")
    plots_dir = "plots"; os.makedirs(plots_dir, exist_ok=True)

    reference_rps = BENCHMARK_STRATEGIES['Serv']['rate_exploration']['start_rps']
    print(f"  > Utilisation du RPS de référence : {reference_rps} req/s (basé sur le start_rps de 'Serv')")

    df_analysis = df.copy()
    plot_data = {'image_size_kb': [], 'Serv_latency_ms': [], 'Serv-odb_latency_ms': []}

    for image_name, image_size in PAYLOADS.items():
        print(f"\n--- Traitement de l'image : {image_name} ---")

        serv_data_point = df_analysis[(df_analysis['servlet_name'] == 'Serv') & (df_analysis['image_name'] == image_name) & (df_analysis['target_rate_rps'] == reference_rps)]
        odb_data_point = df_analysis[(df_analysis['servlet_name'] == 'Serv-odb') & (df_analysis['image_name'] == image_name) & (df_analysis['target_rate_rps'] == reference_rps)]

        if serv_data_point.empty:
            print(f" ! AVERTISSEMENT: Donnée de référence manquante pour 'Serv' avec '{image_name}' à {reference_rps} RPS. Image ignorée.")
            continue
        serv_latency = serv_data_point['latency_avg_ms'].iloc[0]

        if odb_data_point.empty:
            print(f"  > [INFO] Donnée manquante pour 'Serv-odb' à {reference_rps} RPS. Lancement d'un test ciblé...")
            s_details = APPLICATIONS['Serv-odb']; strat = BENCHMARK_STRATEGIES['Serv-odb']
            url = f"http://{TOPOLOGY['intermediate_vm']['ip']}:8080{s_details['endpoint']}?machine={TOPOLOGY['backend_server']['hostname']}&image={image_name}"
            res = run_single_wrk2_test(url, reference_rps, connections=strat['connections'], threads=strat['threads'], duration_seconds=30, timeout_seconds=strat['timeout_seconds'])

            if res and res.get('total_requests', 0) > 0:
                print(f"  > Test réussi. Latence mesurée : {res.get('latency_avg_ms', 0):.2f} ms")
                odb_latency = res.get('latency_avg_ms', 0)
                flat_result = {"timestamp": datetime.datetime.now().isoformat(), "servlet_name": 'Serv-odb', "image_name": image_name, "image_size_kb": image_size, "target_rate_rps": reference_rps, **strat, **res}

                original_csv_target = OUTPUT_FILES.get("raw_results_csv")
                OUTPUT_FILES["raw_results_csv"] = 'results_odb.csv'
                _append_result_to_csv(flat_result)
                if original_csv_target: OUTPUT_FILES["raw_results_csv"] = original_csv_target

                df_analysis = pd.concat([df_analysis, pd.DataFrame([flat_result])], ignore_index=True)
            else:
                print(f"  ! ECHEC du test ciblé pour 'Serv-odb' avec '{image_name}'. Image ignorée.")
                continue
        else:
            odb_latency = odb_data_point['latency_avg_ms'].iloc[0]
            print(f"  > Données existantes trouvées pour 'Serv-odb'. Latence : {odb_latency:.2f} ms")

        plot_data['image_size_kb'].append(image_size)
        plot_data['Serv_latency_ms'].append(serv_latency)
        plot_data['Serv-odb_latency_ms'].append(odb_latency)

    if not plot_data['image_size_kb']:
        print(" ! Aucune donnée comparable n'a pu être trouvée ou générée. Le graphique ne sera pas créé.")
        return

    plot_df = pd.DataFrame(plot_data).sort_values('image_size_kb')

    plt.figure(figsize=(12, 7))
    plt.plot(plot_df['image_size_kb'], plot_df['Serv_latency_ms'], 'o-', label='Serv')
    plt.plot(plot_df['image_size_kb'], plot_df['Serv-odb_latency_ms'], 'o-', label='Serv-odb')

    plt.title(f'Latence Moyenne vs Taille de l\'Image (à {reference_rps} RPS)')
    plt.xlabel('Taille de l\'Image (KB)')
    plt.ylabel('Latence Moyenne (ms)')
    plt.xscale('log'); plt.yscale('log')
    plt.grid(True, which="both", ls="--")

    ticks = sorted(list(PAYLOADS.values()))
    labels = [name for name, size in sorted(PAYLOADS.items(), key=lambda item: item[1])]
    plt.xticks(ticks, labels, rotation=45, ha="right")

    plt.legend(); plt.tight_layout()

    output_path = f"{plots_dir}/latency_comparison_at_fixed_rps.png"
    plt.savefig(output_path)
    plt.close()
    print(f" > Graphique de comparaison de latence sauvegardé dans : {output_path}")

if __name__ == "__main__":
    main()
