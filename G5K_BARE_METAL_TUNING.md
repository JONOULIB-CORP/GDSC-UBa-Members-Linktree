# Grid'5000 Bare-Metal Tuning Guide (4-Node Setup)

This guide provides the necessary steps to achieve high CPU utilization and stable benchmarks on Grid'5000 physical nodes in a 4-tier architecture (**M1-M2-M3-M4**).

## Architecture Mapping
*   **M1**: Client (wrk)
*   **M2**: Load Balancer (Nginx) - *Keep default high performance*
*   **M3**: **Web Server (Tomcat Proxy) - TARGET FOR TUNING**
*   **M4**: Final Server (Tomcat Storage) - *Keep default high performance*

**Note**: Tomcat is located in `~/mesures/apache-tomcat-11.0.1`. All configuration changes (`conf/server.xml`) should be made in that directory.

---

## 1. M3 Core Restriction (Simulate 4-Core Node)
To observe CPU consumption in a controlled environment, we restrict M3 to exactly 4 cores. This is done by disabling all other CPUs at the kernel level.

### Disabling Extra Cores
```bash
# Disable CPUs 4 to 63 to keep only cores 0-3 active
for i in $(seq 4 63); do
  echo "0" | sudo-g5k tee /sys/devices/system/cpu/cpu"$i"/online
done
```

---

## 2. M3 Kernel Network Tuning
Standard Debian/Ubuntu settings are too low for high RPS (>2000).

```bash
# Increase the size of the listen queue
sudo-g5k sysctl -w net.core.somaxconn=1024

# Increase the number of packets allowed in the input queue
sudo-g5k sysctl -w net.core.netdev_max_backlog=2000

# Increase the max SYN backlog
sudo-g5k sysctl -w net.ipv4.tcp_max_syn_backlog=1024
```

---

## 3. M3 Application Tuning (Tomcat)
Ensure Tomcat is not throttling itself before the CPU hits 100%.

### Thread Pool (`conf/server.xml`)
Increase `maxThreads` to ensure we don't block on the application level during proxying.
```xml
<Connector port="8080" protocol="HTTP/1.1"
           connectionTimeout="20000"
           maxThreads="1000"
           minSpareThreads="100"
           redirectPort="8443" />
```

### Disable Logging
I/O wait for access logs can artificially lower CPU usage.
Comment out the `AccessLogValve` in `server.xml`.

---

## 4. Verification Protocol
1.  **Monitor M3** with `mpstat -P ALL 1`.
2.  **Verify M3 Load** with `top` (should see 4 cores near 100%).
3.  **Check M1 (Client)** output:
    *   If `Socket errors: connect` -> Increase `somaxconn`.
    *   If `Socket errors: timeout` -> Increase Tomcat `maxThreads` or M3 is truly saturated.
