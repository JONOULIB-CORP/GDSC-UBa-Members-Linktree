# -*- coding: utf-8 -*-
import os, subprocess, re, csv, datetime, argparse, random, time, json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Topologie par défaut (sera écrasée si --config est utilisé)
TOPOLOGY = {
    "client":       {"ip": "172.16.20.8"},
    "lb":           {"ip": "172.16.20.21"},
    "intermediate": {"ip": "172.16.20.20", "hostname": "dahu-20"},
    "backend":      {"ip": "172.16.20.12", "hostname": "dahu-12"}
}

# Paramètres de mesure
WARMUP_SEC           = 10
MEASURE_SEC          = 30
WRK_THREADS          = 12
WRK_CONNECTIONS      = 400
TIMEOUT              = "15s"
FIXED_RPS_COMPARISON = 1000

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
# LOGIQUE (EXTRACTION & MESURE)
# ==============================================================================

def log(msg, level="INFO"):
    colors = {"INFO": "\033[94m", "SUCCESS": "\033[92m", "WARN": "\033[93m", "ERROR": "\033[91m", "BOLD": "\033[1m", "END": "\033[0m"}
    print(f"{colors.get(level, '')}[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}{colors['END']}")

def analyze_saturation(res, target_rps):
    observed = res["observed_rps"]
    cpu = res["node_cpu_avg_percent"]
    bw = res["measured_gbps"]
    lat = res["latency_avg_ms"]
    if observed < (target_rps * 0.90):
        if cpu >= THEO_CPU_LIMIT: return "SAT_CPU"
        if bw >= THEO_BW_GBPS: return "SAT_BW"
        if lat > 500: return "SAT_LATENCY"
        return "SAT_SOFT"
    return "None"

def parse_wrk_output(output):
    res = {"observed_rps": 0.0, "measured_gbps": 0.0, "latency_avg_ms": 0.0, "latency_p99_ms": 0.0}
    if m := re.search(r'Requests/sec:\s*([\d\.]+)', output): res["observed_rps"] = float(m.group(1))
    if m := re.search(r'Transfer/sec:\s*([\d\.]+)([kKmMgG]?)B', output):
        val, unit = float(m.group(1)), m.group(2).upper()
        mult = {'G': 1e9, 'M': 1e6, 'K': 1e3, '': 1}
        res["measured_gbps"] = (val * mult.get(unit, 1) * 8) / 1e9
    if m := re.search(r'Latency\s+([\d\.]+)(\w+)', output):
        val, unit = float(m.group(1)), m.group(2)
        res["latency_avg_ms"] = val * 1000 if 's' == unit else val
    if m := re.search(r'99\.000%\s+([\d\.]+)(\w+)', output):
        val, unit = float(m.group(1)), m.group(2)
        res["latency_p99_ms"] = val * 1000 if 's' == unit else val
    return res

def execute_test(app_id, img_name, rate, topo):
    inter_ip, lb_ip = topo["intermediate"]["ip"], topo["lb"]["ip"]
    url = f"http://{lb_ip}:8080{APPLICATIONS[app_id]['endpoint']}?machine={topo['backend']['hostname']}&image={img_name}"

    # Remote cleanup
    subprocess.run([f"ssh {inter_ip} 'rm -f /tmp/cpu_measure.log'"], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    wrk_cmd = f"~/mesures/wrk2/wrk -t{WRK_THREADS} -c{WRK_CONNECTIONS} -d{MEASURE_SEC}s -R{rate} -H 'Connection: keep-alive' --latency --timeout {TIMEOUT} \"{url}\""
    log(f"EXEC: {app_id} | {img_name} | {rate} RPS", "INFO")

    # Warmup
    subprocess.run([f"~/mesures/wrk2/wrk -t{WRK_THREADS} -c{WRK_CONNECTIONS} -d{WARMUP_SEC}s -R{rate} \"{url}\""], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Measure
    cpu_proc = subprocess.Popen([f"ssh {inter_ip} 'LC_ALL=C mpstat {MEASURE_SEC} 1 | grep Average > /tmp/cpu_measure.log'"], shell=True)
    wrk_run = subprocess.run([wrk_cmd], shell=True, capture_output=True, text=True)
    cpu_proc.wait()

    cpu_out = subprocess.run([f"ssh {inter_ip} 'cat /tmp/cpu_measure.log'"], shell=True, capture_output=True, text=True)
    try: cpu_val = 100.0 - float(cpu_out.stdout.split()[-1])
    except: cpu_val = 0.0

    data = parse_wrk_output(wrk_run.stdout)
    data["node_cpu_avg_percent"] = cpu_val
    return data

# ==============================================================================
# SUITE ET REPRISE
# ==============================================================================

def run_suite(payload_set, app_list, csv_filename, topo):
    history = {}
    if os.path.exists(csv_filename):
        with open(csv_filename, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = (row["servlet_name"], row["image_name"])
                if key not in history: history[key] = set()
                history[key].add(int(float(row["target_rps"])))
    else:
        with open(csv_filename, 'w') as f:
            csv.writer(f).writerow(["timestamp", "servlet_name", "image_name", "size_kb", "target_rps", "real_rps", "gbps", "lat_ms", "lat_p99_ms", "cpu", "reason"])

    for img_name, img_size in payload_set.items():
        for app_id in app_list:
            log(f"MODE: {app_id} | IMG: {img_name} ({img_size}KB)", "BOLD")
            strat = STRATEGY[app_id]["small" if img_size < 100 else "large"]
            rps_list = sorted(list(range(strat["start"], strat["max"] + 1, strat["step"])))
            if rps_list[-1] < strat["max"]: rps_list.append(strat["max"])

            for curr_rps in rps_list:
                if (app_id, img_name) in history and curr_rps in history[(app_id, img_name)]: continue
                res = execute_test(app_id, img_name, curr_rps, topo)
                reason = analyze_saturation(res, curr_rps)

                color = "\033[92m" if reason == "None" else "\033[91m"
                print(f"   {color}[RES] {res['observed_rps']:>6.0f}/{curr_rps:>6} | CPU: {res['node_cpu_avg_percent']:>4.1f}% | Sat: {reason}\033[0m")

                with open(csv_filename, 'a', newline='') as f:
                    csv.writer(f).writerow([datetime.datetime.now().isoformat(), app_id, img_name, img_size, curr_rps, res["observed_rps"], res["measured_gbps"], res["latency_avg_ms"], res["latency_p99_ms"], res["node_cpu_avg_percent"], reason])
                if reason != "None": break

# ==============================================================================
# RAPPORTS
# ==============================================================================

def generate_all_reports(mot_csv, odb_csv, rnd_csv):
    log("GENERATION DES RAPPORTS", "SUCCESS")
    files = [f for f in [mot_csv, odb_csv, rnd_csv] if os.path.exists(f)]
    if not files: return
    df = pd.concat([pd.read_csv(f) for f in files]).drop_duplicates(subset=['servlet_name', 'image_name', 'target_rps'])

    # Motivation Plot
    df_mot = df[df['servlet_name'] == 'Serv']
    if not df_mot.empty:
        sm = df_mot.groupby('size_kb').agg({'real_rps': 'max', 'gbps': 'max', 'cpu': 'max'}).sort_index()
        fig, axes = plt.subplots(3, 1, figsize=(10, 12), sharex=True)
        for i, (col, lbl, clr) in enumerate([('real_rps', 'RPSmax', 'b'), ('gbps', 'Gbps', 'g'), ('cpu', 'CPU%', 'r')]):
            axes[i].plot(sm.index, sm[col], 'o-', color=clr); axes[i].set_ylabel(lbl); axes[i].grid(True); axes[i].set_xscale('log')
        plt.tight_layout(); plt.savefig("graph_motivation_combined.png"); plt.close()

    # ODB Invariance
    df_odb = df[df['servlet_name'] == 'Serv-odb']
    if not df_odb.empty:
        sm_odb = df_odb.groupby('size_kb')['real_rps'].max().sort_index()
        baseline_1k = df[(df['servlet_name'] == 'Serv') & (df['size_kb'] <= 1.5)]['real_rps'].max()
        plt.figure(figsize=(10, 6)); plt.plot(sm_odb.index, sm_odb.values, 's-', color='purple', label='ODB (All sizes)')
        if baseline_1k: plt.axhline(y=baseline_1k, color='r', ls='--', label='Serv (1KB)'); plt.text(sm_odb.index[0], baseline_1k*1.02, 'Baseline 1KB')
        plt.xscale('log'); plt.legend(); plt.grid(True); plt.savefig("graph_odb_invariance.png"); plt.close()

    # Efficiency
    plt.figure(figsize=(10, 6))
    for app in df['servlet_name'].unique():
        sub = df[(df['servlet_name'] == app) & (df['real_rps'] > 100)].copy()
        sub['cost'] = sub['cpu'] / (sub['real_rps'] / 1000.0)
        sum_eff = sub.groupby('size_kb')['cost'].mean().sort_index()
        plt.plot(sum_eff.index, sum_eff.values, 'o-', label=app)
    plt.xscale('log'); plt.legend(); plt.grid(True); plt.savefig("graph_efficiency.png"); plt.close()

    # Dynamic Latency Comparison
    df['pair'] = df['servlet_name'] + "_" + df['image_name']
    stb = df[df['reason'] == 'None'].groupby('target_rps')['pair'].nunique()
    exp = len(df['servlet_name'].unique()) * len(df['image_name'].unique())
    common = stb[stb >= exp].index.tolist()
    if common:
        bc = max(common)
        sub = df[df['target_rps'] == bc]
        plt.figure(figsize=(10, 6))
        for app in sub['servlet_name'].unique():
            d = sub[sub['servlet_name'] == app].sort_values('size_kb')
            plt.plot(d['size_kb'], d['lat_ms'], 's-', label=f"{app} Avg")
        plt.xscale('log'); plt.legend(); plt.grid(True); plt.savefig("graph_latency_common.png"); plt.close()

# ==============================================================================
# MAIN
# ==============================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['motivation', 'odb_test', 'random_table', 'all', 'report'], required=True)
    parser.add_argument('--config', type=str, help="Fichier JSON de topologie")
    args = parser.parse_args()

    if args.config:
        with open(args.config, 'r') as f: TOPOLOGY = json.load(f)
        log(f"Topologie chargée depuis {args.config}", "SUCCESS")

    F_MOT, F_ODB, F_RND = "results_motivation.csv", "results_odb.csv", "results_random_table.csv"
    if args.mode in ['motivation', 'all']: run_suite(CORE_PAYLOADS, ["Serv"], F_MOT, TOPOLOGY)
    if args.mode in ['odb_test', 'all']: run_suite(CORE_PAYLOADS, ["Serv-odb"], F_ODB, TOPOLOGY)
    if args.mode in ['random_table', 'all']:
        rnd = dict(random.sample(list(FULL_PAYLOAD_POOL.items()), min(5, len(FULL_PAYLOAD_POOL))))
        run_suite(rnd, ["Serv", "Serv-odb"], F_RND, TOPOLOGY)

    if args.mode != 'none': generate_all_reports(F_MOT, F_ODB, F_RND)
