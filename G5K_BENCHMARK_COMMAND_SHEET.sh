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

# Install Java 17 (Required for Tomcat 11)
sudo-g5k apt update && sudo-g5k apt install -y openjdk-17-jre

# Start Tomcat (assuming serv.war is already in webapps/)
cd ~/mesures/apache-tomcat-11.0.1
./bin/startup.sh

# Verify local file access
curl -I "http://localhost:8080/serv/Serv?image=small.jpg"

# ------------------------------------------------------------------------------
# 2. SETUP NODE M3 (WEB SERVER - PROXY UNDER TEST)
# ------------------------------------------------------------------------------
# Role: Proxy requests to M4. THIS IS THE BOTTLENECK NODE.

# Install Java 17
sudo-g5k apt update && sudo-g5k apt install -y openjdk-17-jre

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

sudo-g5k apt update && sudo-g5k apt install -y nginx

# Create Proxy Config with Keep-Alive to M3
cat <<EOF | sudo-g5k tee /etc/nginx/sites-available/serv-proxy
upstream tomcat_backend {
    server <IP_M3>:8080;
    keepalive 100; # Keep 100 idle connections open to M3
}

server {
    listen 8080;
    location /serv/ {
        proxy_pass http://tomcat_backend/serv/;

        # Mandatory for Upstream Keep-Alive
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
sudo-g5k systemctl restart nginx

# ------------------------------------------------------------------------------
# 4. EXECUTION ON M1 (CLIENT - LOAD GENERATOR)
# ------------------------------------------------------------------------------

# Target: M2 (LB)
# Parameter 'machine': M4 (Final Server)

# Test 1: Small Image (1KB) - Goal: Saturation RPS (CPU Bound on M3)
# Note: uses -R (rate) from wrk2
~/mesures/wrk2/wrk -t12 -c200 -d30s -R2000 --latency \
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
