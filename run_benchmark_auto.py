# -*- coding: utf-8 -*-
import os, subprocess, re, csv, datetime, argparse, random, time, json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ==============================================================================
# 1. CONFIGURATION ET TOPOLOGIE
# ==============================================================================
TOPOLOGY = {
    "client":       {"ip": "172.16.20.8"},
    "lb":           {"ip": "172.16.20.21"}, # M2
    "intermediate": {"ip": "172.16.20.20", "hostname": "dahu-20"}, # M3
    "backend":      {"ip": "172.16.20.12", "hostname": "dahu-12"}  # M4
}

# Paramètres de mesure
WARMUP_SEC           = 10
MEASURE_SEC          = 30
WRK_THREADS          = 12
WRK_CONNECTIONS      = 400
TIMEOUT              = "15s"
FIXED_RPS_COMPARISON = 500 # Harmonisé à 500 pour que tout le monde ait un point commun

# Seuils de diagnostic scientifique
THEO_BW_GBPS         = 9.4
THEO_CPU_LIMIT       = 95.0

STRATEGY = {
    "Serv": {
        "small": {"start": 500, "step": 5000, "max": 40500},
        "large": {"start": 500, "step": 500,  "max": 8000}
    },
    "Serv-odb": {
        "small": {"start": 500, "step": 10000, "max": 60500},
        "large": {"start": 500, "step": 10000, "max": 60500}
    }
}

APPLICATIONS = {
    "Serv":     {"endpoint": "/serv/Serv"},
    "Serv-odb": {"endpoint": "/serv1/Serv"}
}

FULL_PAYLOAD_POOL = {
    "image_1KB.jpg": 1.0, "image_10KB.jpg": 10.0, "image_100KB.jpg": 100.0, "image_1000KB.jpg": 1024.0,
    "img1.jpg":1.3, "img2.jpg":89.5, "img3.jpg":117.8, "img4.jpg":117.8, "img5.jpg":257.9,
    "img10.jpg":466.8, "img24.jpg":753.5, "img48.jpg":999.7, "img50.jpg":970.7
}
CORE_PAYLOADS = {k: FULL_PAYLOAD_POOL[k] for k in ["image_1KB.jpg", "image_10KB.jpg", "image_100KB.jpg", "image_1000KB.jpg"]}

# ==============================================================================
# 2. LOGIQUE DE MONITORING
# ==============================================================================

def log(msg, level="INFO"):
    colors = {"INFO": "\033[94m", "SUCCESS": "\033[92m", "WARN": "\033[93m", "ERROR": "\033[91m", "BOLD": "\033[1m", "END": "\033[0m"}
    print(f"{colors.get(level, '')}[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}{colors['END']}")

def start_remote_monitor(ip, duration):
    cmd = f"ssh {ip} 'LC_ALL=C mpstat {duration} 1 | grep Average > /tmp/cpu_{ip}.log & LC_ALL=C sar -n DEV 1 {duration} | grep Average > /tmp/bw_{ip}.log &'"
    return subprocess.Popen(cmd, shell=True)

def parse_remote_cpu(ip):
    try:
        out = subprocess.run([f"ssh {ip} 'cat /tmp/cpu_{ip}.log'"], shell=True, capture_output=True, text=True)
        return 100.0 - float(out.stdout.split()[-1])
    except: return 0.0

def parse_remote_bw(ip):
    try:
        out = subprocess.run([f"ssh {ip} 'cat /tmp/bw_{ip}.log'"], shell=True, capture_output=True, text=True)
        max_bw = 0.0
        for line in out.stdout.splitlines():
            if "Average" in line and "IFACE" not in line and "lo" not in line:
                parts = line.split()
                rx_kbps, tx_kbps = float(parts[4]), float(parts[5])
                node_gbps = (rx_kbps + tx_kbps) * 8 / 1e6
                max_bw = max(max_bw, node_gbps)
        return max_bw
    except: return 0.0

def clean_remote_logs(ips):
    for ip in ips:
        subprocess.run([f"ssh {ip} 'rm -f /tmp/cpu_{ip}.log /tmp/bw_{ip}.log'"], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def analyze_saturation(res, target_rps):
    observed, cpu, bw, lat = res["real_rps"], res["cpu_inter"], res["gbps"], res["lat_ms"]
    if observed < (target_rps * 0.90):
        if cpu >= THEO_CPU_LIMIT: return "SAT_CPU"
        if bw >= THEO_BW_GBPS: return "SAT_BW"
        if lat > 500: return "SAT_LATENCY"
        return "SAT_SOFT"
    return "None"

def parse_wrk_output(output):
    res = {"real_rps": 0.0, "gbps": 0.0, "lat_ms": 0.0, "lat_p99_ms": 0.0}
    if m := re.search(r'Requests/sec:\s*([\d\.]+)', output): res["real_rps"] = float(m.group(1))
    if m := re.search(r'Transfer/sec:\s*([\d\.]+)([kKmMgG]?)B', output):
        val, unit = float(m.group(1)), m.group(2).upper()
        mult = {'G': 1e9, 'M': 1e6, 'K': 1e3, '': 1}
        res["gbps"] = (val * mult.get(unit, 1) * 8) / 1e9
    if m := re.search(r'Latency\s+([\d\.]+)(\w+)', output):
        val, unit = float(m.group(1)), m.group(2)
        res["lat_ms"] = val * 1000 if 's' == unit else val
    if m := re.search(r'99\.000%\s+([\d\.]+)(\w+)', output):
        val, unit = float(m.group(1)), m.group(2)
        res["lat_p99_ms"] = val * 1000 if 's' == unit else val
    return res

def execute_test(app_id, img_name, rate, topo):
    ips = [topo["lb"]["ip"], topo["intermediate"]["ip"], topo["backend"]["ip"]]
    clean_remote_logs(ips)
    url = f"http://{topo['lb']['ip']}:8080{APPLICATIONS[app_id]['endpoint']}?machine={topo['backend']['hostname']}&image={img_name}"
    wrk_cmd = f"~/mesures/wrk2/wrk -t{WRK_THREADS} -c{WRK_CONNECTIONS} -d{MEASURE_SEC}s -R{rate} -H 'Connection: keep-alive' --latency --timeout {TIMEOUT} \"{url}\""
    log(f"EXEC: {app_id} | {img_name} | {rate} RPS", "INFO")
    subprocess.run([f"~/mesures/wrk2/wrk -t{WRK_THREADS} -c{WRK_CONNECTIONS} -d{WARMUP_SEC}s -R{rate} \"{url}\""], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    procs = [start_remote_monitor(ip, MEASURE_SEC) for ip in ips]
    wrk_run = subprocess.run([wrk_cmd], shell=True, capture_output=True, text=True)
    for p in procs: p.wait()
    time.sleep(1)
    data = parse_wrk_output(wrk_run.stdout)
    data.update({
        "cpu_lb": parse_remote_cpu(topo["lb"]["ip"]), "cpu_inter": parse_remote_cpu(topo["intermediate"]["ip"]), "cpu_back": parse_remote_cpu(topo["backend"]["ip"]),
        "bw_lb": parse_remote_bw(topo["lb"]["ip"]), "bw_inter": parse_remote_bw(topo["intermediate"]["ip"]), "bw_back": parse_remote_bw(topo["backend"]["ip"])
    })
    return data

# ==============================================================================
# 3. GESTION DES SUITES DE TESTS
# ==============================================================================

def run_suite(payload_set, app_list, csv_filename, topo):
    history = {}
    if os.path.exists(csv_filename):
        with open(csv_filename, 'r') as f:
            reader = csv.DictReader(f); [history.setdefault((r["servlet_name"], r["image_name"]), set()).add(int(float(r["target_rps"]))) for r in reader]
    else:
        with open(csv_filename, 'w') as f: csv.writer(f).writerow(["timestamp", "servlet_name", "image_name", "size_kb", "target_rps", "real_rps", "gbps", "lat_ms", "lat_p99_ms", "cpu_lb", "cpu_inter", "cpu_back", "bw_lb", "bw_inter", "bw_back", "reason"])

    for img_name, img_size in payload_set.items():
        for app_id in app_list:
            log(f"SUITE: {app_id} | {img_name}", "BOLD")
            strat = STRATEGY[app_id]["small" if img_size < 100 else "large"]
            rps_list = sorted(list(set([FIXED_RPS_COMPARISON] + list(range(strat["start"], strat["max"] + 1, strat["step"])))))
            for curr_rps in rps_list:
                if (app_id, img_name) in history and curr_rps in history[(app_id, img_name)]: continue
                res = execute_test(app_id, img_name, curr_rps, topo)
                reason = analyze_saturation(res, curr_rps)
                print(f"   [RES] {res['real_rps']:>6.0f}/{curr_rps:>6} | CPU Inter: {res['cpu_inter']:>4.1f}% | Sat: {reason}")
                with open(csv_filename, 'a', newline='') as f:
                    csv.writer(f).writerow([datetime.datetime.now().isoformat(), app_id, img_name, img_size, curr_rps, res["real_rps"], res["gbps"], res["lat_ms"], res["lat_p99_ms"], res["cpu_lb"], res["cpu_inter"], res["cpu_back"], res["bw_lb"], res["bw_inter"], res["bw_back"], reason])
                if reason != "None" and curr_rps >= FIXED_RPS_COMPARISON: break

# ==============================================================================
# 4. GÉNÉRATION DES RAPPORTS
# ==============================================================================

def generate_all_reports(mot_csv, odb_csv, rnd_csv):
    log("GÉNÉRATION DES RAPPORTS FINAUX", "SUCCESS")
    all_files = [f for f in [mot_csv, odb_csv, rnd_csv] if os.path.exists(f)]
    if not all_files: return
    df = pd.concat([pd.read_csv(f) for f in all_files]).drop_duplicates(subset=['servlet_name', 'image_name', 'target_rps'])

    # 1. Motivation Combined
    df_mot = df[df['servlet_name'] == 'Serv']
    if not df_mot.empty:
        sm = df_mot.groupby('size_kb').agg({'real_rps': 'max', 'gbps': 'max', 'cpu_inter': 'max'}).sort_index()
        fig, axes = plt.subplots(3, 1, figsize=(10, 15), sharex=True)
        for i, (col, lbl, clr) in enumerate([('real_rps', 'Max RPS', 'b'), ('gbps', 'Max Gbps', 'g'), ('cpu_inter', 'CPU% proxy', 'r')]):
            axes[i].plot(sm.index, sm[col], 'o-', color=clr); axes[i].set_ylabel(lbl); axes[i].grid(True, which="both"); axes[i].set_xscale('log')
        axes[0].set_title("Standard Servlet Bottlenecks vs Payload Size")
        plt.tight_layout(); plt.savefig("graph_motivation_combined.png"); plt.close()

    # 2. ODB Invariance Proof
    df_odb = df[df['servlet_name'] == 'Serv-odb']
    if not df_odb.empty:
        sm_odb = df_odb.groupby('size_kb')['real_rps'].max().sort_index()
        baseline_1k = df[(df['servlet_name'] == 'Serv') & (df['size_kb'] <= 1.5)]['real_rps'].max()
        plt.figure(figsize=(10, 6)); plt.plot(sm_odb.index, sm_odb.values, 's-', color='purple', label='ODB (All sizes)')
        if baseline_1k:
            plt.axhline(y=baseline_1k, color='red', ls='--', label='Serv (1KB) Baseline')
            plt.text(sm_odb.index[0], baseline_1k * 1.02, 'Standard 1KB Level', color='red', fontweight='bold')
        plt.xscale('log'); plt.title("ODB Performance Invariance Proof"); plt.ylabel("Max RPS reached"); plt.xlabel("Payload Size (KB)"); plt.legend(); plt.grid(True, which="both"); plt.savefig("graph_odb_invariance.png"); plt.close()

    # 3. Efficiency
    plt.figure(figsize=(10, 6))
    for app in df['servlet_name'].unique():
        sub = df[(df['servlet_name'] == app) & (df['real_rps'] > 100)].copy()
        sub['cost'] = sub['cpu_inter'] / (sub['real_rps'] / 1000.0)
        sum_eff = sub.groupby('size_kb')['cost'].mean().sort_index()
        plt.plot(sum_eff.index, sum_eff.values, 'o-', label=f"{app} Efficiency")
    plt.xscale('log'); plt.title("CPU Efficiency (Cost per 1k requests)"); plt.ylabel("CPU % per 1000 RPS"); plt.legend(); plt.grid(True, which="both"); plt.savefig("graph_efficiency.png"); plt.close()

    # 4. ODB Speedup & Multi-Node CPU
    max_rps = df.groupby(['servlet_name', 'size_kb'])['real_rps'].max().unstack(level=0)
    if 'Serv' in max_rps.columns and 'Serv-odb' in max_rps.columns:
        speedup = max_rps['Serv-odb'] / max_rps['Serv']
        plt.figure(figsize=(10, 6)); speedup.sort_index().plot(kind='bar', color='green', alpha=0.7)
        plt.title("ODB Speedup Factor (Max RPS Ratio)"); plt.ylabel("Speedup (x)"); plt.axhline(y=1.0, color='r', ls='--'); plt.savefig("graph_odb_speedup.png"); plt.close()
        max_rps[['Serv', 'Serv-odb']].assign(speedup=speedup).to_csv("results_comparison_max_rps.csv")

    # 5. Dynamic Latency
    df['pair'] = df['servlet_name'] + "_" + df['image_name']
    stb = df[df['reason'] == 'None'].groupby('target_rps')['pair'].nunique()
    common = stb[stb >= (len(df['servlet_name'].unique()) * len(df['image_name'].unique()))].index.tolist()
    if common:
        bc = max(common)
        sub = df[df['target_rps'] == bc]
        plt.figure(figsize=(10, 6))
        for app in sub['servlet_name'].unique():
            d = sub[sub['servlet_name'] == app].sort_values('size_kb')
            plt.plot(d['size_kb'], d['lat_ms'], 's-', label=f"{app} Avg Latency at {bc} RPS")
        plt.xscale('log'); plt.legend(); plt.grid(True, which="both"); plt.savefig("graph_latency_common.png"); plt.close()

# ==============================================================================
# MAIN
# ==============================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument('--mode', choices=['motivation', 'odb_test', 'random_table', 'all', 'report'], required=True); parser.add_argument('--config', type=str)
    args = parser.parse_args()
    if args.config:
        with open(args.config, 'r') as f: TOPOLOGY = json.load(f)
    F_MOT, F_ODB, F_RND = "results_motivation.csv", "results_odb.csv", "results_random_table.csv"
    if args.mode in ['motivation', 'all']: run_suite(CORE_PAYLOADS, ["Serv"], F_MOT, TOPOLOGY)
    if args.mode in ['odb_test', 'all']: run_suite(CORE_PAYLOADS, ["Serv-odb"], F_ODB, TOPOLOGY)
    if args.mode in ['random_table', 'all']:
        rnd = dict(random.sample(list(FULL_PAYLOAD_POOL.items()), min(5, len(FULL_PAYLOAD_POOL))))
        run_suite(rnd, ["Serv", "Serv-odb"], F_RND, TOPOLOGY)
    if args.mode != 'none': generate_all_reports(F_MOT, F_ODB, F_RND)
    log("TERMINÉ.", "SUCCESS")
