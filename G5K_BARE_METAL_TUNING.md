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

### 1. Brider la fréquence au MINIMUM (La clé du 100% CPU)
```bash
# 1. Désactiver le Turbo Boost
echo 1 | sudo-g5k tee /sys/devices/system/cpu/intel_pstate/no_turbo

# 2. Forcer 800MHz (ou le minimum de 'cpupower frequency-info')
sudo-g5k cpupower frequency-set -d 800MHz -u 800MHz -g performance

# 3. Vérifier que MHz est proche de 800
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

### 3. Tuning Tomcat pour le Maximum de Performance
*   **Threads** : Éditez `conf/server.xml` et réglez `maxThreads="1000"` dans le Connector 8080.
*   **Logs** : **Supprimez ou commentez la balise `<Valve ... AccessLogValve ... />`**. Si vous la laissez, le disque va ralentir tout le système à 20k RPS.
*   **Mémoire (JVM)** :
    ```bash
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
# UTILISEZ DES TIRETS '-' pour les noms de machines (dahu-11, gros-4)
./wrk2/wrk -t32 -c200 -d60s -R15000 --latency "http://IP_INTERMEDIAIRE:8080/serv/Serv?machine=NOM-BACKEND&image=small.jpg"
```

---

## ÉTAPE 4 : Monitoring (M2)
```bash
mpstat -P 0,1,2,3 1
```

---

## ANALYSE : Pourquoi je ne vois pas 100% de CPU ?

Si vous avez beaucoup d'Idle malgré une forte charge, lisez le document de justification :
[**Justification Scientifique (Loi de Little)**](./G5K_SCIENTIFIC_JUSTIFICATION.md)

En résumé : si la latence monte (ex: 15s) mais que le CPU reste à 20% d'idle, vos threads sont en train d'**attendre** le backend ou le réseau. Ils n'utilisent pas le CPU pendant l'attente.
