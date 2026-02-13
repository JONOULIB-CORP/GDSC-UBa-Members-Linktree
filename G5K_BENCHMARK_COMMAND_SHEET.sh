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

# Install Java 21 and Monitoring tools
sudo-g5k apt update && sudo-g5k apt install -y openjdk-21-jre sysstat

# Start Tomcat (assuming serv.war is already in webapps/)
cd ~/mesures/apache-tomcat-11.0.1
./bin/startup.sh

# Verify local file access
curl -I "http://localhost:8080/serv/Serv?image=small.jpg"

# ------------------------------------------------------------------------------
# 2. SETUP NODE M3 (WEB SERVER - PROXY UNDER TEST)
# ------------------------------------------------------------------------------
# Role: Proxy requests to M4. THIS IS THE BOTTLENECK NODE.

# Install Java 21 and Monitoring tools
sudo-g5k apt update && sudo-g5k apt install -y openjdk-21-jre sysstat

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

    # Standard Servlet
    location /serv/ {
        proxy_pass http://tomcat_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host \$host;
        proxy_buffers 16 16k;
        proxy_buffer_size 32k;
    }

    # ODB Servlet
    location /serv1/ {
        proxy_pass http://tomcat_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host \$host;
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

# ------------------------------------------------------------------------------
# 6. TROUBLESHOOTING: FIXING "NoSuchMethodError" or "404"
# ------------------------------------------------------------------------------

# A. Fix 404: Ensure web.xml is in the correct location
# For serv (Standard):
mkdir -p ~/mesures/apache-tomcat-11.0.1/webapps/serv/WEB-INF
if [ -f ~/mesures/apache-tomcat-11.0.1/webapps/serv/web.xml ]; then
  mv ~/mesures/apache-tomcat-11.0.1/webapps/serv/web.xml ~/mesures/apache-tomcat-11.0.1/webapps/serv/WEB-INF/
fi

# For serv1 (ODB):
mkdir -p ~/mesures/apache-tomcat-11.0.1/webapps/serv1/WEB-INF
if [ -f ~/mesures/apache-tomcat-11.0.1/webapps/serv1/web.xml ]; then
  mv ~/mesures/apache-tomcat-11.0.1/webapps/serv1/web.xml ~/mesures/apache-tomcat-11.0.1/webapps/serv1/WEB-INF/
fi

# B. Fix NoSuchMethodError & Version Mismatch: Clean and Recompile Servlets
# IMPORTANT 1: Current ODB Parser (Parser6.java) has a bug with InvokeDynamic linkage.
# It fails to update lambda signatures in BootstrapMethods, causing NoSuchMethodError.
# FIX: Use this "Lambda-Free" version of Serv.java until the parser is fixed.
# IMPORTANT 2: Use --release 21 to match the environment.

mkdir -p ~/mesures/apache-tomcat-11.0.1/webapps/serv1/WEB-INF/classes/app
cat <<EOF > ~/mesures/apache-tomcat-11.0.1/webapps/serv1/WEB-INF/classes/app/Serv.java
package app;

import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.Optional;

import jakarta.servlet.ServletException;
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

@WebServlet("/Serv")
public class Serv extends HttpServlet {
    private final HttpClient client = HttpClient.newHttpClient();

    @Override
    protected void doGet(HttpServletRequest request, HttpServletResponse response) throws ServletException, IOException {
        String machine = request.getParameter("machine");
        String image = request.getParameter("image");

        if (machine == null) {
            InputStream file = request.getServletContext().getResourceAsStream("/" + image);
            if (file == null) { response.sendError(404); return; }
            byte[] bytes = file.readAllBytes();
            response.setContentType(getServletContext().getMimeType(image));
            response.setContentLength(bytes.length);
            response.getOutputStream().write(bytes);
            return;
        }

        // Dynamisation du chemin du contexte (utilise le contexte actuel de l'appli)
        String contextPath = request.getContextPath();
        String url = "http://" + machine + ":8080" + contextPath + "/Serv?image=" + image;
        HttpRequest req = HttpRequest.newBuilder().uri(URI.create(url)).GET().build();

        try {
            HttpResponse<byte[]> resp = client.send(req, HttpResponse.BodyHandlers.ofByteArray());

            // --- LAMBDA-FREE HEADER PROCESSING (Avoids ODB NoSuchMethodError) ---
            Optional<String> ct = resp.headers().firstValue("Content-Type");
            if (ct.isPresent()) response.setContentType(ct.get());

            Optional<String> cl = resp.headers().firstValue("Content-Length");
            if (cl.isPresent()) response.setHeader("Content-Length", cl.get());

            for (String cc : resp.headers().allValues("Cache-Control")) {
                response.addHeader("Cache-Control", cc);
            }

            response.getOutputStream().write(resp.body());

        } catch (Exception e) {
            e.printStackTrace();
            response.sendError(500);
        }
    }
}
EOF

# Recompile
cd ~/mesures/apache-tomcat-11.0.1/webapps/serv1/WEB-INF/classes
javac --release 21 -cp "../../../lib/*" app/Serv.java

# Restart Tomcat to apply changes
cd ~/mesures/apache-tomcat-11.0.1
./bin/shutdown.sh && ./bin/startup.sh
