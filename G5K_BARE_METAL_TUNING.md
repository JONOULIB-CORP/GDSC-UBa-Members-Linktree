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

### 1. Brider la fréquence au MINIMUM (La clé du 100%)
Si 1.2GHz laisse encore de l'idle, passez au minimum absolu (souvent 800MHz ou 1GHz).
```bash
# 1. Désactiver le Turbo Boost
echo 1 | sudo-g5k tee /sys/devices/system/cpu/intel_pstate/no_turbo

# 2. Forcer 800MHz (ou le min de 'cpupower frequency-info')
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

## ÉTAPE 3 : Benchmarking (M1) - Le réglage fin

Vos derniers résultats (~87% CPU) montrent que le système "étouffe" sous le nombre de connexions. Pour atteindre 100%, il faut réduire l'overhead.

**Où :** Nœud Client.
```bash
# RÉDUISEZ -c (connexions) pour augmenter l'efficacité.
# Testez avec -c 200 et un -R très élevé (40 000).
./wrk2/wrk -t32 -c200 -d60s -R40000 --latency "http://IP_INTERMEDIAIRE:8080/serv/Serv?machine=NOM_BACKEND&image=small.jpg"
```

---

## ANALYSE : Pourquoi le CPU stagne ?

Si vous voyez votre RPS observé **baisser** alors que vous augmentez `-R` (ex: 23.3k au lieu de 23.9k), vous avez dépassé le **point de rupture**. Le CPU perd son temps en "Context Switching" (le noyau change de thread sans arrêt).

1.  **Réduire la Concurrence** : Passer de `-c 500` à `-c 200` permet à chaque thread d'avoir plus de temps CPU utile.
2.  **Diminuer la Fréquence** : Si le CPU est trop rapide, il finit ses tâches trop vite et attend. À **800MHz**, chaque cycle compte et l'idle disparaîtra.
