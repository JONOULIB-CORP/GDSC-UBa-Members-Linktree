#!/bin/bash
# ==============================================================================
# FEUILLE DE ROUTE : TOUTES LES COMMANDES DU BENCHMARK (RÉVISÉE POUR DAHAU)
# Projet : mesures | Machine : Bare Metal G5K (4 cœurs sur Inter)
# ==============================================================================

# --- PRÉPARATION (SUR LES 3 NOEUDS : M1, M2, M3) ---
sudo-g5k apt-get update
sudo-g5k apt-get install -y openjdk-17-jre sysstat linux-cpupower build-essential git
cd ~/mesures


# ==============================================================================
# ÉTAPE 1 : SUR LE BACKEND (M3)
# ==============================================================================
# 1. Tuning Kernel
sudo-g5k sysctl -w net.core.somaxconn=10000
sudo-g5k sysctl -w net.core.netdev_max_backlog=100000

# 2. Démarrer Tomcat
./apache-tomcat-11.0.1/bin/startup.sh


# ==============================================================================
# ÉTAPE 2 : SUR L'INTERMÉDIAIRE (M2)
# ==============================================================================

# --- A. BRIDAGE MATÉRIEL ---
echo 1 | sudo-g5k tee /sys/devices/system/cpu/intel_pstate/no_turbo
sudo-g5k cpupower frequency-set -d 800MHz -u 800MHz -g performance

# --- B. TUNING KERNEL ---
sudo-g5k sysctl -w net.core.somaxconn=10000
sudo-g5k sysctl -w net.core.netdev_max_backlog=100000
sudo-g5k sysctl -w net.ipv4.tcp_max_syn_backlog=10000
sudo-g5k sysctl -w net.ipv4.tcp_tw_reuse=1

# --- C. AFFINITÉ IRQ ---
sudo-g5k systemctl stop irqbalance 2>/dev/null || true
INTERFACE=$(ip route get 8.8.8.8 | grep -oP 'dev \K\S+')
IRQS=$(grep -E "$INTERFACE|mlx5_comp" /proc/interrupts | awk '{print $1}' | sed 's/://')
for IRQ in $IRQS; do
    echo "f" | sudo-g5k tee /proc/irq/$IRQ/smp_affinity > /dev/null
done

# --- D. TUNING TOMCAT (ROBUSTE) ---
# 1. Configurer Threads à 1000
sed -i 's/maxThreads="[0-9]*"/maxThreads="1000"/' ~/mesures/apache-tomcat-11.0.1/conf/server.xml
# 2. Supprimer la Valve AccessLog (Même si elle est sur plusieurs lignes)
sed -i '/AccessLogValve/,/\/>/d' ~/mesures/apache-tomcat-11.0.1/conf/server.xml
# 3. Optimiser la JVM
echo 'export CATALINA_OPTS="-Xms4G -Xmx4G -XX:+UseG1GC"' > ~/mesures/apache-tomcat-11.0.1/bin/setenv.sh
chmod +x ~/mesures/apache-tomcat-11.0.1/bin/setenv.sh

# --- E. LANCEMENT ET VÉRIFICATION ---
ulimit -n 65535
./apache-tomcat-11.0.1/bin/shutdown.sh 2>/dev/null || true
sleep 2
# Lancement sur les cœurs 0-3
taskset -c 0,1,2,3 ./apache-tomcat-11.0.1/bin/startup.sh

# --- F. VÉRIFICATION DE SANTÉ (Si Connection Refused) ---
# 1. Vérifier si le processus tourne
ps aux | grep catalina
# 2. Vérifier si le port 8080 est ouvert
ss -tlnp | grep 8080
# 3. Voir les erreurs si Tomcat n'a pas démarré
tail -n 50 ~/mesures/apache-tomcat-11.0.1/logs/catalina.out


# ==============================================================================
# ÉTAPE 3 : SUR LE CLIENT (M1)
# ==============================================================================
# Lancer le test (Adapter IP_M2 et NOM_M3)
./wrk2/wrk -t32 -c200 -d60s -R15000 --latency "http://IP_INTERMEDIAIRE:8080/serv/Serv?machine=NOM-BACKEND&image=image_1KB.jpg"
