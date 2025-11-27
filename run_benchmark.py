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

# Dictionnaire des payloads de base (nom_fichier -> taille_en_ko)
PAYLOADS = {
    "1k.jpg": 1.0,
    "10k.jpg": 10.0,
    "100k.jpg": 100.0,
    "1M.jpg": 1024.0
}

# Dictionnaire du grand pool de 50 images (nom_fichier -> taille_en_ko)
# À REMPLIR AVEC VOS NOMS DE FICHIERS ET LEURS TAILLES EXACTES
FULL_PAYLOAD_POOL = {
    # Exemple:
    # "photo_v1_24.5k.jpg": 24.5,
    # "archive.zip": 102.7,
}

BENCHMARK_STRATEGIES = {
    "Serv": { "threads": 8, "connections": 15, "duration_seconds": 60, "timeout_seconds": 10, "rate_exploration": {"start_rps": 200, "step_rps": 100, "max_rps": 3000}, "stop_condition": {"timeout_threshold_percent": 1.0} },
    "Serv-odb": { "threads": 8, "connections": 100, "duration_seconds": 60, "timeout_seconds": 10, "rate_exploration": {"start_rps": 1000, "step_rps": 500, "max_rps": 10000}, "stop_condition": {"timeout_threshold_percent": 1.0} }
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
        f.write("### 2.1. Carte réseau du nœud physique\n")
        for key, value in NETWORK_CAPACITIES["host_nic"].items(): f.write(f"- **{key.replace('_', ' ').capitalize()}**: {value}\n")
        f.write("\n### 2.2. Interface réseau de la VM\n")
        for key, value in NETWORK_CAPACITIES["vm_nic"].items(): f.write(f"- **{key.replace('_', ' ').capitalize()}**: {value}\n")
        f.write("\n## 3. Logiciels & versions\n\n")
        for key, value in SOFTWARE_VERSIONS.items(): f.write(f"- **{key.replace('_', ' ').capitalize()}**: {value}\n")
        f.write("\n## 4. Applications testées\n\n")
        for name, details in APPLICATIONS.items(): f.write(f"### 4.1. {name}\n- **Endpoint**: `{details['endpoint']}`\n\n")
        f.write("### 4.2. Payloads Testés\n")
        for name, size in payloads_to_report.items(): f.write(f"- **{name}**: {size} KB\n")
        f.write("\n\n## 5. Stratégies de `wrk2`\n\n")
        for name, strategy in BENCHMARK_STRATEGIES.items():
            if name in APPLICATIONS:
                f.write(f"### 5.1. Stratégie pour `{name}`\n")
                for key, value in strategy.items():
                    if isinstance(value, dict):
                        f.write(f"- **{key.replace('_', ' ').capitalize()}**:\n")
                        for sub_key, sub_value in value.items(): f.write(f"  - {sub_key.replace('_', ' ').capitalize()}: {sub_value}\n")
                    else: f.write(f"- **{key.replace('_', ' ').capitalize()}**: {value}\n")
    print(f"Rapport de reproductibilité généré : {OUTPUT_FILES['reproducibility_report']}")

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
    res = {}
    res['observed_rps'] = float(m.group(1)) if (m := re.search(r'Requests/sec:\s*([\d\.]+)', output)) else 0
    res['transfer_MBs'] = _parse_bytes(m.group(1)) if (m := re.search(r'Transfer/sec:\s*([\d\.]+[kKmMgG]B)', output)) else 0
    res['total_requests'] = int(m.group(1)) if (m := re.search(r'([\d]+) requests in', output)) else 0
    if m := re.search(r'Socket errors: connect (\d+), read (\d+), write (\d+), timeout (\d+)', output):
        res.update(errors_connect=int(m.group(1)), errors_read=int(m.group(2)), errors_write=int(m.group(3)), errors_timeout=int(m.group(4)), total_errors=sum(map(int, m.groups())))
    else: res.update(errors_connect=0, errors_read=0, errors_write=0, errors_timeout=0, total_errors=0)
    if m := re.search(r'Latency Distribution\s+50%\s+([\d\.\w]+)\s+75%\s+([\d\.\w]+)\s+90%\s+([\d\.\w]+)\s+99%\s+([\d\.\w]+)', output):
        res.update(latency_p50_ms=_parse_time(m.group(1)), latency_p75_ms=_parse_time(m.group(2)), latency_p90_ms=_parse_time(m.group(3)), latency_p99_ms=_parse_time(m.group(4)))
    res['latency_avg_ms'] = _parse_time(m.group(1)) if (m := re.search(r'Latency\s+([\d\.\w]+)\s+', output)) else 0
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
            mon_proc.wait(15)
            scp_cmd = ["sshpass","-p",vm['password'],"scp"]+ssh_opts+[f"{vm['user']}@{vm['ip']}:{remote_log}",local_log]
            subprocess.run(scp_cmd, check=True, capture_output=True, timeout=15)
            with open(local_log,"r") as f: results['vm_cpu_avg_percent'] = _parse_mpstat_output(f.read())
            print(f"  > CPU moyen VM: {results['vm_cpu_avg_percent']:.2f}%")
        else: results['vm_cpu_avg_percent'] = 0.0
        return results
    except Exception as e:
        print(f"  ! Erreur critique: {e}");
        if mon_proc: mon_proc.kill()
        return None
    finally:
        subprocess.run(["sshpass","-p",vm['password'],"ssh"]+ssh_opts+[f"{vm['user']}@{vm['ip']}",f"rm -f {remote_log}"], check=False)
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
    print(f"\nLancement de l'exploration pour {len(apps)} servlet(s) sur {len(payloads)} image(s)...")
    for s_name, s_details in apps.items():
        for i_name, i_size in payloads.items():
            print(f"\n----- Scénario: Servlet='{s_name}', Image='{i_name}' -----")
            strat = BENCHMARK_STRATEGIES[s_name]
            url = f"http://{TOPOLOGY['intermediate_vm']['ip']}:8080{s_details['endpoint']}?machine={TOPOLOGY['backend_server']['hostname']}&image={i_name}"
            for rate in range(strat['rate_exploration']['start_rps'], strat['rate_exploration']['max_rps']+1, strat['rate_exploration']['step_rps']):
                print(f"\nTesting Rate: {rate} RPS...")
                res = run_single_wrk2_test(url, rate, **{k:v for k,v in strat.items() if k in ['connections','threads','duration_seconds','timeout_seconds']})
                if not res: break
                _append_result_to_csv({"timestamp":datetime.datetime.now().isoformat(),"servlet_name":s_name,"image_name":i_name,"image_size_kb":i_size,"target_rate_rps":rate,**strat,**res})
                if res.get('total_requests',0)>0 and (res.get('errors_timeout',0)/res['total_requests']*100)>strat['stop_condition']['timeout_threshold_percent']:
                    print("  ! Condition d'arrêt atteinte."); break

def main():
    parser = argparse.ArgumentParser(description="Script de benchmark ODB.")
    parser.add_argument('--mode', type=str, default='all', choices=['all', 'motivation', 'random_table', 'latency'])
    args = parser.parse_args()
    print(f"Mode d'exécution: {args.mode}")

    # Chaque mode de test génère son propre fichier de résultats pour éviter les écrasements.
    # Le mode 'latency' est spécial : il ne génère pas de données, il en lit.
    mode_to_csv = {
        'all': 'results_all.csv',
        'motivation': 'results_motivation.csv',
        'random_table': 'results_random_table.csv'
    }

    # --- Lancement des campagnes de test (si applicable) ---
    if args.mode in mode_to_csv:
        OUTPUT_FILES['raw_results_csv'] = mode_to_csv[args.mode]
        print(f"Les résultats bruts seront écrits dans : {OUTPUT_FILES['raw_results_csv']}")

        if args.mode == 'all':
            write_reproducibility_report(PAYLOADS)
            initialize_csv()
            run_scenarios(PAYLOADS)
        elif args.mode == 'motivation':
            write_reproducibility_report(PAYLOADS)
            initialize_csv()
            run_scenarios(PAYLOADS, {"Serv": APPLICATIONS["Serv"]})
        elif args.mode == 'random_table':
            if not FULL_PAYLOAD_POOL:
                print("[ERREUR] Le dictionnaire 'FULL_PAYLOAD_POOL' est vide. Veuillez le remplir.")
                return
            names = random.sample(list(FULL_PAYLOAD_POOL.keys()), 10)
            payloads = {n: FULL_PAYLOAD_POOL[n] for n in names}
            write_reproducibility_report(payloads)
            initialize_csv()
            run_scenarios(payloads)

    # --- Lancement des analyses ---
    analysis_file = None
    if args.mode in ['all', 'motivation', 'random_table']:
        analysis_file = mode_to_csv[args.mode]
    elif args.mode == 'latency':
        # L'analyse de latence dépend des données de la campagne 'all'.
        analysis_file = 'results_all.csv'
        if not os.path.exists(analysis_file):
            print(f"[ERREUR] Fichier '{analysis_file}' introuvable. Veuillez d'abord exécuter le mode 'all' pour générer les données de base.")
            return

    if analysis_file and os.path.exists(analysis_file):
        try:
            df = pd.read_csv(analysis_file)
            if df.empty:
                print(f"Le fichier de résultats '{analysis_file}' est vide.")
                return

            # Exécuter les fonctions d'analyse appropriées pour le mode.
            if args.mode in ['all', 'motivation']:
                generate_motivation_plots(df)
            if args.mode in ['all', 'random_table']:
                generate_comparison_table(df)
            if args.mode in ['all', 'latency']:
                analyze_latency_distribution(df)

        except Exception as e:
            print(f"Une erreur est survenue lors de l'analyse du fichier '{analysis_file}': {e}")
    elif args.mode not in ['all', 'motivation', 'random_table']:
         print("Aucun fichier de résultats à analyser.")


    print("\nCampagne de benchmark terminée.")

def get_peak_performance(df):
    return df.loc[df.groupby(['servlet_name', 'image_name'])['observed_rps'].idxmax()]

def generate_motivation_plots(df):
    print("\nGénération des graphiques de motivation...")
    plots_dir="plots"; os.makedirs(plots_dir, exist_ok=True)
    serv_df = df[df['servlet_name'] == 'Serv']
    if serv_df.empty: return
    peak = get_peak_performance(serv_df).sort_values('image_size_kb')
    x = peak['image_size_kb']
    fig, axes = plt.subplots(3,1,figsize=(12,18),sharex=True)
    fig.suptitle("Motivation: Performance du Servlet Standard", fontsize=16)
    axes[0].plot(x,peak['observed_rps'],'o-b'); axes[0].set_title('RPS Max vs Taille'); axes[0].set_ylabel('req/s'); axes[0].grid(True)
    axes[1].plot(x,peak['transfer_MBs'],'o-g'); axes[1].set_title('Bande Passante à RPS Max'); axes[1].set_ylabel('MB/s'); axes[1].grid(True)
    axes[2].plot(x,peak['vm_cpu_avg_percent'],'o-r'); axes[2].set_title('CPU à RPS Max'); axes[2].set_ylabel('%'); axes[2].set_xlabel('Taille (KB)'); axes[2].set_ylim(0,110); axes[2].grid(True)
    plt.tight_layout(rect=[0,0,1,0.96]); plt.savefig(f"{plots_dir}/motivation.png"); plt.close()
    print("  > Graphiques de motivation sauvegardés.")

def generate_comparison_table(df):
    print("\nGénération du tableau comparatif des RPSmax...")
    peak = get_peak_performance(df)
    all_p = {**PAYLOADS, **FULL_PAYLOAD_POOL}
    peak['image_size_kb'] = peak['image_name'].map({n:s for n,s in all_p.items()})
    pivot = peak.pivot_table(index='servlet_name', columns='image_name', values='observed_rps')
    pivot = pivot[sorted(pivot.columns, key=lambda c: all_p.get(c, 0))]
    print("\n"+"="*120); print("Tableau Comparatif des RPS Maximum (req/s)".center(120)); print("="*120)
    print(pivot.to_string(float_format="%.2f")); print("="*120)

def analyze_latency_distribution(df):
    print("\nAnalyse détaillée de la latence...")
    lat_dir="latency_analysis"; os.makedirs(lat_dir, exist_ok=True)
    targets = ["1k.jpg", "10k.jpg", "100k.jpg", "1M.jpg"]
    df_sub = df[df['image_name'].isin(targets)]
    if df_sub.empty: return
    peak = get_peak_performance(df_sub)
    for _, row in peak.iterrows():
        s, i, r = row['servlet_name'], row['image_name'], int(row['target_rate_rps'])
        strat = BENCHMARK_STRATEGIES[s]
        print(f"\n  > Capture histogramme pour '{s}' avec '{i}' à {r} RPS...")
        url = f"http://{TOPOLOGY['intermediate_vm']['ip']}:8080{APPLICATIONS[s]['endpoint']}?machine={TOPOLOGY['backend_server']['hostname']}&image={i}"
        hdr = f"{lat_dir}/{s}_{i.replace('.jpg','')}.hdr"
        run_single_wrk2_test(url, r, **{k:v for k,v in strat.items() if k in ['connections','threads','duration_seconds','timeout_seconds']}, hdr_histogram_output=hdr)

    print("\nGénération du graphique de distribution de la latence...")
    plt.figure(figsize=(12,8))
    s={'Serv':'blue','Serv-odb':'red'}; l={'1k.jpg':'-','10k.jpg':'--','100k.jpg':':','1M.jpg':'-.'}
    for _, row in peak.iterrows():
        s_name, i_name = row['servlet_name'], row['image_name']
        hdr = f"{lat_dir}/{s_name}_{i_name.replace('.jpg','')}.hdr"
        if os.path.exists(hdr):
            try:
                hist = pd.read_csv(hdr, skiprows=3, delim_whitespace=True, usecols=['Value','Percentile'], header=0)
                plt.plot(hist['Percentile'], hist['Value']/1000.0, label=f'{s_name} - {i_name}', color=s.get(s_name), linestyle=l.get(i_name))
            except Exception as e: print(f"  ! Erreur parsing {hdr}: {e}")
    plt.title('Distribution de la Latence (HDR) aux RPS Maximum'); plt.xlabel('Percentile'); plt.ylabel('Latence (ms)')
    plt.grid(True,which="both",ls="--"); plt.xscale('log'); plt.legend()
    plt.savefig(f"{lat_dir}/latency_dist.png"); plt.close()
    print("  > Graphique de distribution sauvegardé.")

if __name__ == "__main__":
    main()
