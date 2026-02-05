#!/bin/bash
# ==============================================================================
# FEUILLE DE ROUTE : TOUTES LES COMMANDES DU BENCHMARK (DE A À Z)
# Projet : mesures | Machine : Bare Metal G5K (4 cœurs sur Inter)
# ==============================================================================

# --- PRÉPARATION (À FAIRE SUR LES 3 NOEUDS : M1, M2, M3) ---
sudo-g5k apt-get update
sudo-g5k apt-get install -y openjdk-17-jre sysstat linux-cpupower build-essential git
cd ~/mesures


# ==============================================================================
# ÉTAPE 1 : SUR LE BACKEND (M3)
# ==============================================================================
# 1. Ouvrir les vannes du noyau
sudo-g5k sysctl -w net.core.somaxconn=10000
sudo-g5k sysctl -w net.core.netdev_max_backlog=100000

# 2. Relancer Tomcat proprement
./apache-tomcat-11.0.1/bin/shutdown.sh 2>/dev/null || true
sleep 2
./apache-tomcat-11.0.1/bin/startup.sh


# ==============================================================================
# ÉTAPE 2 : SUR L'INTERMÉDIAIRE (M2)
# ==============================================================================

# --- A. BRIDAGE MATÉRIEL (POUR FORCER LE 100% CPU) ---
# 1. Désactiver le Turbo Boost
echo 1 | sudo-g5k tee /sys/devices/system/cpu/intel_pstate/no_turbo
# 2. Fixer la fréquence à 800MHz (ou 1.2GHz selon besoin)
sudo-g5k cpupower frequency-set -d 800MHz -u 800MHz -g performance
# 3. Vérifier (doit afficher ~800)
grep MHz /proc/cpuinfo

# --- B. TUNING KERNEL (DÉBLOQUER LA LATENCE) ---
sudo-g5k sysctl -w net.core.somaxconn=10000
sudo-g5k sysctl -w net.core.netdev_max_backlog=100000
sudo-g5k sysctl -w net.ipv4.tcp_max_syn_backlog=10000
sudo-g5k sysctl -w net.ipv4.tcp_tw_reuse=1

# --- C. AFFINITÉ IRQ (ALIGNER RÉSEAU ET CPU) ---
sudo-g5k systemctl stop irqbalance 2>/dev/null || true
INTERFACE=$(ip route get 8.8.8.8 | grep -oP 'dev \K\S+')
IRQS=$(grep -E "$INTERFACE|mlx5_comp" /proc/interrupts | awk '{print $1}' | sed 's/://')
for IRQ in $IRQS; do
    # Masque 'f' = Cœurs 0,1,2,3
    echo "f" | sudo-g5k tee /proc/irq/$IRQ/smp_affinity > /dev/null
done

# --- D. TUNING TOMCAT (MAX PERFORMANCE) ---
# 1. Nettoyage et configuration des Threads et Buffers
sed -i 's/maxThreads="[0-9]*"/maxThreads="1000"/' ~/mesures/apache-tomcat-11.0.1/conf/server.xml
sed -i 's/<Connector port="8080"/<Connector port="8080" socket.appReadBufSize="65536" socket.appWriteBufSize="65536" bufferSize="16384"/' ~/mesures/apache-tomcat-11.0.1/conf/server.xml

# 2. Désactiver les Logs d'accès (Suppression de la ligne contenant AccessLogValve)
sed -i '/AccessLogValve/d' ~/mesures/apache-tomcat-11.0.1/conf/server.xml

# 3. Optimiser la JVM (GC G1 + 4GB Heap)
echo 'export CATALINA_OPTS="-Xms4G -Xmx4G -XX:+UseG1GC"' > ~/mesures/apache-tomcat-11.0.1/bin/setenv.sh
chmod +x ~/mesures/apache-tomcat-11.0.1/bin/setenv.sh

# --- E. LANCEMENT BRIDÉ (4 COEURS) ---
ulimit -n 65535
cd ~/mesures
# Arrêter Tomcat s'il tourne déjà
./apache-tomcat-11.0.1/bin/shutdown.sh 2>/dev/null || true
sleep 2
# Lancer Tomcat sur les 4 premiers cœurs
taskset -c 0,1,2,3 ./apache-tomcat-11.0.1/bin/startup.sh


# ==============================================================================
# ÉTAPE 3 : SUR LE CLIENT (M1)
# ==============================================================================
# 1. Compiler wrk (si besoin)
cd ~/mesures/wrk2 && make && cd ..

# 2. Lancer le test (Adapter IP_M2 et NOM-M3)
# Note: Utilisez des tirets '-' dans les noms de machines (ex: dahu-11)

# Scénario A (1KB) :
./wrk2/wrk -t32 -c200 -d60s -R20000 --latency "http://IP_M2:8080/serv/Serv?machine=NOM-M3&image=image_1KB.jpg"

# Scénario B (1MB) :
./wrk2/wrk -t32 -c200 -d60s -R1000 --latency "http://IP_M2:8080/serv/Serv?machine=NOM-M3&image=image_1000KB.jpg"


# ==============================================================================
# ÉTAPE 4 : MONITORING (SUR M2)
# ==============================================================================
# Voir la conso par cœur et la moyenne à la fin
mpstat -P 0,1,2,3 1

# Voir le débit réseau réel
sar -n DEV 1
