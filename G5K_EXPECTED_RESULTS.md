# Expected Results of ODB Benchmarking

After running `python3 run_benchmark_auto.py --mode all`, you should find the following files in your `~/mesures` directory:

## 1. CSV Data Files (Raw Results)
- `results_motivation.csv`: Performance data for the standard Servlet (Serv).
- `results_odb.csv`: Performance data for the ODB Servlet (Serv-odb).
- `results_random_table.csv`: Performance data for random images across both servlets.
- `results_random_table_synth.csv`: A pivot table summary of the random test suite.
- **`results_comparison_max_rps.csv`**: A direct comparison of max throughput and speedup for each image size.

### CSV Columns:
- `timestamp`: Time of measurement.
- `servlet_name`: Serv or Serv-odb.
- `image_name`: Name of the payload tested.
- `size_kb`: Payload size.
- `target_rps`: The RPS requested from wrk.
- `real_rps`: The RPS actually achieved by the system.
- `gbps`: Measured network throughput from Client perspective.
- `lat_ms`: Average latency.
- `lat_p99_ms`: Tail latency (99th percentile).
- `cpu_lb`, `cpu_inter`, `cpu_back`: CPU usage on each node (M2, M3, M4).
- `bw_lb`, `bw_inter`, `bw_back`: Network throughput (rx+tx) measured on each node in Gbps.
- `reason`: The scientific diagnosis of saturation.

## 2. Scientific Graphs (PNG)

Toutes les courbes utilisent une échelle logarithmique pour les tailles d'images (1KB à 1MB).

### Motivation & Bottlenecks
- **`graph_motivation_combined.png`** : Graphe à 3 panneaux (RPSmax, Débit Gbps, et CPU à saturation). Il prouve visuellement le passage d'un goulot CPU (petits fichiers) à un goulot Bande passante (gros fichiers).

### Preuves de performance ODB
- **`graph_efficiency.png`** : **LA preuve scientifique.** Affiche le "Coût CPU sur M3 pour 1000 requêtes". Pour ODB, cette courbe est plate.
- **`graph_odb_invariance.png`** : Montre que ODB (toutes tailles) est équivalent au standard (1KB).
- **`graph_odb_speedup.png`** : Histogramme du gain brut.
- **`graph_latency_common.png`** : Comparaison de la latence au meilleur RPS commun trouvé dynamiquement.
- **`graph_multi_node_cpu.png`** : Compare la charge CPU sur le LB (M2), le Proxy (M3) et le Backend (M4) lors de la saturation ODB.
