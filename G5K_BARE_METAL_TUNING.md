# Guide de Benchmark Manuel : Protocole de Saturation sur 4 Cœurs (G5K)

Ce document détaille le protocole pour limiter l'exécution à **4 cœurs** sur l'intermédiaire et atteindre les 100% CPU réels.

---

## 0. Préparation (Sur TOUS les nœuds : C, I, S)

```bash
sudo-g5k apt-get update && sudo-g5k apt-get install -y openjdk-17-jre sysstat linux-cpupower
```

---

## ÉTAPE 1 : Configuration du Serveur Backend (M3)

**Où :** Nœud Backend.
1.  **Démarrer Tomcat.**
2.  **Optimisation Kernel (pour gérer le flux massif)** :
    ```bash
    sudo-g5k sysctl -w net.core.somaxconn=10000
    ```

---

## ÉTAPE 2 : Limitation et BRIDAGE de l'Intermédiaire (M2)

### 1. Brider la fréquence au MINIMUM (Pour forcer les 100% CPU)
```bash
echo 1 | sudo-g5k tee /sys/devices/system/cpu/intel_pstate/no_turbo
sudo-g5k cpupower frequency-set -d 800MHz -u 800MHz -g performance
```

### 2. DÉBLOQUER LE NOYAU (Ouvrir les vannes du Kernel)
*Si la latence est de 15s alors que le CPU est à 20% d'idle, c'est que les requêtes sont bloquées **dans le noyau Linux** avant d'arriver à Tomcat.*

```bash
# Augmenter la queue d'acceptation (Crucial : par défaut à 128 sur G5K)
sudo-g5k sysctl -w net.core.somaxconn=10000

# Augmenter la file d'attente de la carte réseau
sudo-g5k sysctl -w net.core.netdev_max_backlog=100000

# Augmenter le backlog des SYN
sudo-g5k sysctl -w net.ipv4.tcp_max_syn_backlog=10000

# Autoriser la réutilisation rapide des sockets (évite l'attente TIME_WAIT)
sudo-g5k sysctl -w net.ipv4.tcp_tw_reuse=1
```

### 3. Tuning Tomcat
*   **Threads** : `maxThreads="1000"` dans `conf/server.xml`.
*   **Logs** : Désactiver le `AccessLogValve`.
*   **Mémoire** : `CATALINA_OPTS="-Xms4G -Xmx4G -XX:+UseG1GC"` dans `bin/setenv.sh`.

### 4. Lancement bridé à 4 cœurs
```bash
ulimit -n 65535
cd ~/mesures
taskset -c 0,1,2,3 ./apache-tomcat-11.0.1/bin/startup.sh
```

---

## ÉTAPE 3 : Benchmarking (M1)

**Où :** Nœud Client.
```bash
# Testez avec -c 200 ou -c 500 pour éviter de saturer inutilement la file d'attente
./wrk2/wrk -t32 -c200 -d60s -R20000 --latency "http://IP_INTERMEDIAIRE:8080/serv/Serv?machine=NOM-BACKEND&image=small.jpg"
```

---

## ANALYSE : Pourquoi je ne vois pas 100% de CPU ?

Si la latence est énorme (15s) et le CPU idle (20%) :
1.  **Le goulot est AVANT Tomcat** : Les requêtes attendent dans la file `somaxconn` du noyau. Tomcat ne peut pas les traiter car il ne les "voit" pas encore.
2.  **L'explication scientifique complète** : [**Justification Scientifique**](./G5K_SCIENTIFIC_JUSTIFICATION.md)
