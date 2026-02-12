#!/bin/bash

# ==============================================================================
# G5K BENCHMARK COMMAND SHEET (4-NODE SETUP: M1-M2-M3-M4)
# ==============================================================================
# Architecture:
# M1 (Client) -> M2 (Load Balancer) -> M3 (Web Server/Proxy) -> M4 (Final Server)
#
# NOTE: All nodes access the same shared folder ~/mesures via NFS.
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. SETUP NODE M4 (FINAL SERVER - STORAGE)
# ------------------------------------------------------------------------------
# Role: Serve local files to M3

# Install Java 17 and Monitoring tools
sudo-g5k apt update && sudo-g5k apt install -y openjdk-17-jre sysstat

# Start Tomcat (assuming serv.war is already in webapps/)
cd ~/mesures/apache-tomcat-11.0.1
./bin/startup.sh

# Verify local file access
curl -I "http://localhost:8080/serv/Serv?image=small.jpg"

# ------------------------------------------------------------------------------
# 2. SETUP NODE M3 (WEB SERVER - PROXY UNDER TEST)
# ------------------------------------------------------------------------------
# Role: Proxy requests to M4. THIS IS THE BOTTLENECK NODE.

# Install Java 17 and Monitoring tools
sudo-g5k apt update && sudo-g5k apt install -y openjdk-17-jre sysstat

# Start Tomcat
cd ~/mesures/apache-tomcat-11.0.1
./bin/startup.sh

# --- TUNING M3 (The "Intermediate" role) ---

# A. Restrict to 4 cores (Disable CPUs 4 to 63)
for i in $(seq 4 63); do
  echo "0" | sudo-g5k tee /sys/devices/system/cpu/cpu"$i"/online
done

# B. Kernel Network Tuning
sudo-g5k sysctl -w net.core.somaxconn=1024
sudo-g5k sysctl -w net.core.netdev_max_backlog=2000
sudo-g5k sysctl -w net.ipv4.tcp_max_syn_backlog=1024

# ------------------------------------------------------------------------------
# 3. SETUP NODE M2 (LOAD BALANCER - NGINX)
# ------------------------------------------------------------------------------
# Role: Transparently forward M1 requests to M3

# Ensure port 8080 is free (stop Tomcat if it was started on M2 by mistake)
cd ~/mesures/apache-tomcat-11.0.1 && ./bin/shutdown.sh 2>/dev/null || true
sudo-g5k fuser -k 8080/tcp 2>/dev/null || true

# Install Nginx and Monitoring tools
sudo-g5k apt update && sudo-g5k apt install -y nginx sysstat

# Create Proxy Config with Keep-Alive to M3
# IMPORTANT: Replace <IP_M3> with the real IP of node M3
cat <<EOF | sudo-g5k tee /etc/nginx/sites-available/serv-proxy
upstream tomcat_backend {
    server <IP_M3>:8080;
    keepalive 100;
}

server {
    listen 8080;
    location /serv/ {
        proxy_pass http://tomcat_backend;

        proxy_http_version 1.1;
        proxy_set_header Connection "";

        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;

        proxy_buffers 16 16k;
        proxy_buffer_size 32k;
    }
}
EOF

sudo-g5k ln -sf /etc/nginx/sites-available/serv-proxy /etc/nginx/sites-enabled/
sudo-g5k rm -f /etc/nginx/sites-enabled/default

# Check syntax before restarting
sudo-g5k nginx -t && sudo-g5k systemctl restart nginx

# --- SAFETY CHECK (From M2) ---
# Verify that M2 can reach M3 before starting the benchmark
# Expected: HTTP/1.1 200 OK (or similar)
curl -I "http://localhost:8080/serv/Serv?image=small.jpg"

# ------------------------------------------------------------------------------
# 4. SETUP NODE M1 (CLIENT - GENERATOR & ANALYZER)
# ------------------------------------------------------------------------------

# Install Python dependencies for the automation script
pip install pandas matplotlib numpy

# Ensure SSH key is authorized on M2, M3, M4 for non-interactive monitoring
# cat ~/.ssh/id_rsa.pub | ssh <USER>@<NODE> 'cat >> ~/.ssh/authorized_keys'

# ------------------------------------------------------------------------------
# 5. EXECUTION ON M1
# ------------------------------------------------------------------------------

# Target: M2 (LB)
# Parameter 'machine': M4 (Final Server)

# Test 1: Small Image (1KB) - Goal: Observed Performance
~/mesures/wrk2/wrk -t12 -c400 -d30s -R25000 --latency \
"http://<IP_M2>:8080/serv/Serv?machine=<IP_M4>&image=small.jpg"

# Test 1 bis: SATURATION MODE (Goal: 100% CPU on M3)
# Increase rate and connections to push M3 to its limit
~/mesures/wrk2/wrk -t32 -c1000 -d60s -R40000 --timeout 15s --latency \
"http://<IP_M2>:8080/serv/Serv?machine=<IP_M4>&image=small.jpg"

# Test 2: Large Image (1MB) - Goal: Saturation Bandwidth (I/O Bound)
~/mesures/wrk2/wrk -t12 -c200 -d30s -R500 --latency \
"http://<IP_M2>:8080/serv/Serv?machine=<IP_M4>&image=large.jpg"

# ------------------------------------------------------------------------------
# 5. MONITORING (DURING RUN)
# ------------------------------------------------------------------------------
# On M3: check CPU usage per core
mpstat -P ALL 1

# On M3: check network queues
ss -lnt
