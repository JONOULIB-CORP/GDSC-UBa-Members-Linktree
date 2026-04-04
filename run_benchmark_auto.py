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
FIXED_RPS_COMPARISON = 500

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

# Pool complet d'images
FULL_PAYLOAD_POOL = {
    "image_1KB.jpg": 1.0, "image_10KB.jpg": 10.0, "image_100KB.jpg": 100.0, "image_1000KB.jpg": 1024.0,
    "img1.jpg":1.3, "img2.jpg":89.5, "img3.jpg":117.8, "img4.jpg":117.8, "img5.jpg":257.9,
    "img6.jpg":224, "img7.jpg":278.4, "img8.jpg":189.5, "img9.jpg":546.2, "img10.jpg":466.8,
    "img11.jpg":419.4, "img12.jpg":921.7, "img13.jpg":16.9, "img14.jpg":24.7, "img15.jpg":38,
    "img16.jpg":203.1, "img17.jpg":532.7, "img18.jpg":95, "img19.jpg":18.5, "img20.jpg":32.1,
    "img21.jpg":96.2, "img22.jpg":30, "img23.jpg":7.7, "img24.jpg":753.5, "img25.jpg":477.6,
    "img26.jpg":5.8, "img27.jpg":30.2, "img28.jpg":35.2, "img29.jpg":28.6, "img30.jpg":912.9,
    "img31.jpg":28.4, "img32.jpg":588, "img33.jpg":613.1, "img34.jpg":26.0, "img35.jpg":2.8,
    "img36.jpg":9.2, "img37.jpg":31.7, "img38.jpg":2.5, "img39.jpg":470.3, "img40.jpg":8,
    "img41.jpg":13.3, "img42.jpg":11.2, "img43.jpg":4.8, "img44.jpg":271.9, "img45.jpg":41.8,
    "img46.jpg":50.8, "img47.jpg":570.9, "img48.jpg":999.7, "img49.jpg":38.9, "img50.jpg":970.7,
}
# On garde quelques points clés pour les modes motivation/odb_test de base
CORE_PAYLOADS = {k: FULL_PAYLOAD_POOL[k] for k in ["image_1KB.jpg", "image_10KB.jpg", "image_100KB.jpg", "image_1000KB.jpg"] if k in FULL_PAYLOAD_POOL}

# ==============================================================================
# 2. LOGIQUE DE MONITORING ET ANALYSE
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
    details = f"Real:{observed:.0f} RPS, CPU:{cpu:.1f}%, BW:{bw:.2f} Gbps, Lat:{lat:.1f}ms"

    # 1. Saturation par débit (RPS drop)
    if observed < (target_rps * 0.90):
        # Pourquoi ça drop ?
        if cpu >= THEO_CPU_LIMIT:
            return "SAT_CPU", f"CPU Limit Hit ({cpu:.1f}% >= {THEO_CPU_LIMIT}%). Info: {details}"
        if bw >= THEO_BW_GBPS:
            return "SAT_BW", f"Bandwidth Limit Hit ({bw:.2f} >= {THEO_BW_GBPS} Gbps). Info: {details}"
        return "SAT_SOFT", f"Throughput Drop (>10% loss). Info: {details}"

    # 2. Saturation par Latence (System Stall)
    if lat > 500:
        return "SAT_LATENCY", f"Latency Threshold Hit ({lat:.1f}ms > 500ms). Info: {details}"

    return "None", f"Stable. Info: {details}"

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
# 3. GESTION DES SUITES DE TESTS (Precision Phase)
# ==============================================================================

def save_result(csv_filename, row):
    with open(csv_filename, 'a', newline='') as f:
        csv.writer(f).writerow(row)

def run_suite(payload_set, app_list, csv_filename, topo):
    history = {}
    if os.path.exists(csv_filename):
        with open(csv_filename, 'r') as f:
            reader = csv.DictReader(f); [history.setdefault((r["servlet_name"], r["image_name"]), set()).add(int(float(r["target_rps"]))) for r in reader]
    else:
        with open(csv_filename, 'w') as f: csv.writer(f).writerow(["timestamp", "servlet_name", "image_name", "size_kb", "target_rps", "real_rps", "gbps", "lat_ms", "lat_p99_ms", "cpu_lb", "cpu_inter", "cpu_back", "bw_lb", "bw_inter", "bw_back", "reason", "justification"])

    for img_name, img_size in payload_set.items():
        for app_id in app_list:
            log(f"SUITE: {app_id} | {img_name}", "BOLD")
            strat = STRATEGY[app_id]["small" if img_size < 100 else "large"]

            last_stable_rps = 0

            # 1. Sweep Principal (Gros paliers)
            rps_list = sorted(list(set([FIXED_RPS_COMPARISON] + list(range(strat["start"], strat["max"] + 1, strat["step"])))))
            for curr_rps in rps_list:
                if (app_id, img_name) in history and curr_rps in history[(app_id, img_name)]:
                    last_stable_rps = curr_rps
                    continue

                res = execute_test(app_id, img_name, curr_rps, topo)
                code, just = analyze_saturation(res, curr_rps)
                print(f"   [RES] {res['real_rps']:>6.0f}/{curr_rps:>6} | CPU Inter: {res['cpu_inter']:>4.1f}% | Sat: {code}")

                row = [datetime.datetime.now().isoformat(), app_id, img_name, img_size, curr_rps, res["real_rps"], res["gbps"], res["lat_ms"], res["lat_p99_ms"], res["cpu_lb"], res["cpu_inter"], res["cpu_back"], res["bw_lb"], res["bw_inter"], res["bw_back"], code, just]
                save_result(csv_filename, row)

                if code == "None":
                    last_stable_rps = curr_rps
                else:
                    # SATURATION DETECTÉE -> PHASE DE PRÉCISION (Finer Sweep)
                    threshold_for_precision = 1000 if img_size < 100 else 400
                    if last_stable_rps > 0 and (curr_rps - last_stable_rps) > threshold_for_precision:
                        log(f"   PRECISION PHASE: Refining limit between {last_stable_rps} and {curr_rps}", "WARN")
                        fine_step = 1000 if img_size < 100 else 200
                        fine_rps = last_stable_rps + fine_step
                        while fine_rps < curr_rps:
                            if (app_id, img_name) in history and fine_rps in history[(app_id, img_name)]:
                                fine_rps += fine_step
                                continue

                            res_f = execute_test(app_id, img_name, fine_rps, topo)
                            code_f, just_f = analyze_saturation(res_f, fine_rps)
                            print(f"      [PRECISION] {res_f['real_rps']:>6.0f}/{fine_rps:>6} | CPU: {res_f['cpu_inter']:>4.1f}% | Sat: {code_f}")

                            row_f = [datetime.datetime.now().isoformat(), app_id, img_name, img_size, fine_rps, res_f["real_rps"], res_f["gbps"], res_f["lat_ms"], res_f["lat_p99_ms"], res_f["cpu_lb"], res_f["cpu_inter"], res_f["cpu_back"], res_f["bw_lb"], res_f["bw_inter"], res_f["bw_back"], code_f, just_f]
                            save_result(csv_filename, row_f)

                            if code_f != "None": break
                            fine_rps += fine_step

                    if curr_rps >= FIXED_RPS_COMPARISON: break

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
        idx = df_mot.groupby('size_kb')['real_rps'].idxmax()
        sm = df_mot.loc[idx].sort_values('size_kb')
        fig, axes = plt.subplots(3, 1, figsize=(10, 15), sharex=True)
        for i, (col, lbl, clr) in enumerate([('real_rps', 'Max RPS', 'b'), ('gbps', 'Max Gbps', 'g'), ('cpu_inter', 'CPU% proxy', 'r')]):
            axes[i].plot(sm['size_kb'], sm[col], 'o-', color=clr); axes[i].set_ylabel(lbl); axes[i].grid(True, which="both"); axes[i].set_xscale('log')
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
        plt.plot(sum_eff.index, sum_eff.values, 'o-', label=app)
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

        # CPU & BW per image at fixed RPS
        fig, ax1 = plt.subplots(figsize=(10, 6))
        ax2 = ax1.twinx()
        for app in sub['servlet_name'].unique():
            d = sub[sub['servlet_name'] == app].sort_values('size_kb')
            ax1.plot(d['size_kb'], d['cpu_inter'], 'o-', label=f"{app} CPU")
            ax2.plot(d['size_kb'], d['gbps'], 'x--', label=f"{app} Bandwidth", alpha=0.6)
        ax1.set_xscale('log'); ax1.set_xlabel("Payload Size (KB)"); ax1.set_ylabel("CPU Proxy (%)"); ax2.set_ylabel("Throughput (Gbps)")
        plt.title(f"CPU & Bandwidth Trace per image at {bc} RPS"); ax1.legend(loc='upper left'); ax2.legend(loc='upper right'); plt.grid(True); plt.savefig("graph_fixed_rps_metrics.png"); plt.close()

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
        rnd = dict(random.sample(list(FULL_PAYLOAD_POOL.items()), min(10, len(FULL_PAYLOAD_POOL))))
        run_suite(rnd, ["Serv", "Serv-odb"], F_RND, TOPOLOGY)
    if args.mode != 'none': generate_all_reports(F_MOT, F_ODB, F_RND)
    log("TERMINÉ.", "SUCCESS")
