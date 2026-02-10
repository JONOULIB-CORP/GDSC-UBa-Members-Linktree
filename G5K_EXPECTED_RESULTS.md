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

### Motivation & Bottlenecks
- `graph_motivation_cpu.png`: Shows how CPU consumption increases with RPS for different image sizes in the baseline.
- `graph_motivation_gbps.png`: Shows the network throughput reaching the 10Gbps ceiling for large images in the baseline.

### ODB Performance Proofs
- **`graph_efficiency.png`**: (Crucial Proof). Shows the CPU cost per 1000 requests. For ODB, this curve remains **flat and low**, proving that the CPU cost is independent of payload size. For standard Serv, the cost **increases** with image size.
- **`graph_odb_speedup.png`**: A bar chart showing the speedup factor of ODB over the baseline. Speedup should be massive for 1MB images.
- **`graph_latency_fixed.png`**: Compares the average and P99 latency at a fixed RPS. ODB maintains much lower and more stable latency than the baseline as payload size increases.
