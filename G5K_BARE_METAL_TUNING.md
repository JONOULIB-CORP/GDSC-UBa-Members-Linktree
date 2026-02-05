# Guide de Benchmark Manuel : Protocole de Saturation sur 4 Cœurs (G5K)

Ce document détaille le protocole pour limiter l'exécution à **4 cœurs** sur l'intermédiaire et le **brider** pour atteindre les 100% CPU réels.

---

## 0. Préparation (Sur TOUS les nœuds : C, I, S)

```bash
sudo-g5k apt-get update && sudo-g5k apt-get install -y openjdk-17-jre sysstat linux-cpupower
```

---

## ÉTAPE 1 : Configuration du Serveur Backend (M3)

**Où :** Nœud Backend.
1.  **Démarrer Tomcat :**
    ```bash
    cd ~/mesures
    ./apache-tomcat-11.0.1/bin/startup.sh
    ```

---

## ÉTAPE 2 : Limitation et BRIDAGE de l'Intermédiaire (M2)

### 1. Brider la fréquence au MINIMUM
Si vous voulez voir 100% de CPU, il faut rendre le processeur plus lent.
```bash
# 1. Désactiver le Turbo Boost
echo 1 | sudo-g5k tee /sys/devices/system/cpu/intel_pstate/no_turbo

# 2. Forcer 800MHz (ou 1.2GHz)
sudo-g5k cpupower frequency-set -d 800MHz -u 800MHz -g performance

# 3. Vérifier
watch -n 1 "grep MHz /proc/cpuinfo"
```

### 2. Gestion des Interruptions (Cœurs 0-3)
```bash
sudo-g5k systemctl stop irqbalance 2>/dev/null || true
INTERFACE=$(ip route get 8.8.8.8 | grep -oP 'dev \K\S+')
IRQS=$(grep -E "$INTERFACE|mlx5_comp" /proc/interrupts | awk '{print $1}' | sed 's/://')
for IRQ in $IRQS; do
    echo "f" | sudo-g5k tee /proc/irq/$IRQ/smp_affinity > /dev/null
done
```

### 3. Tuning Tomcat
```bash
# Désactiver les logs
sed -i '/AccessLogValve/d' ~/mesures/apache-tomcat-11.0.1/conf/server.xml
# Threads à 1000
sed -i 's/maxThreads="[0-9]*"/maxThreads="1000"/' ~/mesures/apache-tomcat-11.0.1/conf/server.xml
# JVM Optimisée
echo 'export CATALINA_OPTS="-Xms4G -Xmx4G -XX:+UseG1GC"' > ~/mesures/apache-tomcat-11.0.1/bin/setenv.sh
chmod +x ~/mesures/apache-tomcat-11.0.1/bin/setenv.sh
```

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
# Testez avec -c 200 et un -R progressif (20k, 25k, 30k)
./wrk2/wrk -t32 -c200 -d60s -R30000 --latency "http://IP_INTERMEDIAIRE:8080/serv/Serv?machine=NOM_BACKEND&image=small.jpg"
```

---

## ANALYSE : Interprétation des Résultats

| Métrique | État : Saturation Saine | État : Effondrement (Collapse) |
| :--- | :--- | :--- |
| **CPU Idle** | Entre 1% et 5% | **Proche de 0%** |
| **Latence** | Faible (< 100ms) | **Énorme (> 10s)** |
| **RPS Observé** | Proche du RPS cible (-R) | **Très inférieur au cible** |
| **Signification** | Le système est à son maximum utile. | Le système est noyé (overhead massif). |

### Vos derniers résultats (94% CPU, 31s Latence)
*   **Victoire** : Vous avez cassé le plateau des 90% ! Les cœurs sont à ~94%.
*   **Problème** : Avec 31s de latence et un RPS observé qui chute (7k alors que vous aviez 23k précédemment), vous êtes en **effondrement**.
*   **Action** : Réduisez `-R` (ex: tentez `-R 28000`) pour trouver le point où le CPU est à **95%** mais la latence reste sous **1 seconde**. C'est le point de performance maximal réel de votre machine.
