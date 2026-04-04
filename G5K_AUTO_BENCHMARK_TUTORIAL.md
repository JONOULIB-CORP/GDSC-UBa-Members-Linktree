# Tutorial: ODB Automatic Benchmarking on Grid'5000

This tutorial explains how to execute the `run_benchmark_auto.py` script to evaluate the performance gain of On-Demand Bytes (ODB).

## 1. Prerequisites

### Software
Ensure the following are installed on the **Client (M1)**:
- Python 3.8+
- `pandas`, `numpy`, `matplotlib` (Install via `pip install pandas numpy matplotlib`)
- `sshpass` (optional, if you don't want to use SSH keys)

### Infrastructure (4 Nodes)
1. **M1 (Client)**: Where you run the script.
2. **M2 (Load Balancer)**: Nginx configured with Keep-Alive to M3.
3. **M3 (Intermediate)**: Tomcat + Servlet, restricted to 4 cores.
4. **M4 (Backend)**: Tomcat + Servlet (Storage mode).

**Note**: All nodes must have access to `~/mesures` (NFS shared folder).

## 2. Configuration

Before running, edit the `TOPOLOGY` dictionary in `run_benchmark_auto.py` to match your current Grid'5000 reservation IPs and hostnames.

```python
TOPOLOGY = {
    "client":       {"ip": "172.16.x.x"},
    "lb":           {"ip": "172.16.x.x"},
    "intermediate": {"ip": "172.16.x.x", "hostname": "dahu-x"},
    "backend":      {"ip": "172.16.x.x", "hostname": "dahu-y"}
}
```

## 3. Execution

Launch the full campaign from **M1**:
```bash
python3 run_benchmark_auto.py --mode all
```

### Modes available:
- `motivation`: Tests standard Servlet only (Baseline).
- `odb_test`: Tests ODB Servlet only.
- `random_table`: Tests a random subset of images with both servlets.
- `all`: Runs everything.
- `report`: Only regenerates the graphs from existing CSV files.

## 4. Features of the Script

- **Automatic Resume**: If the script is interrupted, it reads the CSV files and continues from where it left off.
- **Intelligent Stop**: For each payload, the script stops increasing the RPS as soon as saturation (CPU, Bandwidth, or Latency) is detected. It intelligently ensures that the `FIXED_RPS_COMPARISON` point is always measured for the graphs.
- **Precision Phase**: When a coarse-grained step (e.g., 5000 RPS) causes saturation, the script automatically triggers a finer-grained sweep (1000 or 200 RPS steps) between the last stable and the first saturated point. This ensures high-resolution detection of the exact `RPSmax`.
- **Log Cleanup**: Remote temporary logs on M3 are automatically cleaned up between tests.
- **Coherent Steps**: Steps are designed to ensure the `max` RPS value is always tested if saturation hasn't been reached yet.
- **Explicit Diagnosis**: Each result is labeled with a scientific reason if saturation occurs (e.g., `SAT_CPU`, `SAT_BW`) and includes a full diagnostic string with measured values (CPU, BW, Latency) stored in the CSV.

## 5. Troubleshooting

- **502 Bad Gateway**: Verify that Tomcat is running on M3 and M4, and that Nginx on M2 is correctly pointing to M3.
- **0.0% CPU**: Verify that your SSH keys are correctly set up between M1 and M3 so the script can run `mpstat` non-interactively.
- **No data in CSV**: Ensure the `wrk2` binary is correctly located in `~/mesures/wrk2/wrk`.
