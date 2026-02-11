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
- `gbps`: Measured network throughput on the intermediate node.
- `lat_ms`: Average latency.
- `lat_p99_ms`: Tail latency (99th percentile).
- `cpu`: CPU utilization percentage on M3 (Average across the 4 active cores).
- `reason`: The scientific diagnosis of saturation (None, SAT_CPU, SAT_BW, SAT_LATENCY, or SAT_SOFT).

## 2. Scientific Graphs (PNG)

Toutes les courbes utilisent une échelle logarithmique pour les tailles d'images (1KB à 1MB).

### Motivation & Bottlenecks
- **`graph_motivation_combined.png`** : Graphe à 3 panneaux (RPSmax, Débit Gbps, et CPU à saturation). Il prouve visuellement le passage d'un goulot CPU (petits fichiers) à un goulot Bande passante (gros fichiers).

### Preuves de performance ODB
- **`graph_efficiency.png`** : **LA preuve scientifique.** Affiche le "Coût CPU pour 1000 requêtes". Pour ODB, cette courbe doit rester **plate et basse**, prouvant l'indépendance vis-à-vis de la taille. Pour `Serv`, le coût explose.
- **`graph_odb_invariance.png`** : Montre que les performances d'ODB sur tous les fichiers (même 1MB) "collent" à la performance du servlet standard sur un tout petit fichier (1KB).
- **`graph_odb_speedup.png`** : Histogramme du gain brut (ex: ODB est 8x plus rapide sur 1MB).
- **`graph_latency_common.png`** : Comparaison de la latence au meilleur RPS commun trouvé dynamiquement par le script.
