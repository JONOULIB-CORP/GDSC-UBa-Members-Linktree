# Guide de Benchmark Manuel : Protocole de Saturation sur 4 Cœurs (G5K)

Ce document détaille le protocole pour limiter l'exécution à **4 cœurs** sur l'intermédiaire et le **brider** (throttle) pour atteindre artificiellement les 100% CPU.

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

Si vos résultats montrent encore de l'idle (ex: 20%) malgré un gros débit, c'est que les CPU de Grid'5000 sont **trop performants** pour votre test. Il faut les brider.

1.  **BRIDER LA FRÉQUENCE CPU (La clé du 100%) :**
    Au lieu de chercher la performance maximale, on va forcer le CPU à sa fréquence minimale pour qu'il sature plus vite.
    ```bash
    # 1. Vérifier les fréquences disponibles
    sudo-g5k cpupower frequency-info

    # 2. Désactiver le Turbo Boost (Essentiel sur G5K)
    echo 1 | sudo-g5k tee /sys/devices/system/cpu/intel_pstate/no_turbo

    # 3. Forcer une fréquence basse (ex: 1.2 GHz ou le minimum affiché par frequency-info)
    # On utilise le gouverneur 'userspace' pour fixer la fréquence
    sudo-g5k cpupower frequency-set -g userspace
    sudo-g5k cpupower frequency-set -f 1.2GHz
    ```

2.  **Gestion des Interruptions (Cœurs 0-3) :**
    ```bash
    sudo-g5k systemctl stop irqbalance 2>/dev/null || true
    INTERFACE=$(ip route get 8.8.8.8 | grep -oP 'dev \K\S+')
    IRQS=$(grep -E "$INTERFACE|mlx5_comp" /proc/interrupts | awk '{print $1}' | sed 's/://')
    for IRQ in $IRQS; do
        echo "f" | sudo-g5k tee /proc/irq/$IRQ/smp_affinity > /dev/null
    done
    ```

3.  **Tuning Tomcat (Threads et Mémoire) :**
    ```bash
    # Supprimer les logs pour éviter les bottlenecks disque
    sed -i '/AccessLogValve/d' ~/mesures/apache-tomcat-11.0.1/conf/server.xml
    # S'assurer d'avoir assez de threads
    sed -i 's/maxThreads="[0-9]*"/maxThreads="1000"/' ~/mesures/apache-tomcat-11.0.1/conf/server.xml
    # Optimiser la JVM
    echo 'export CATALINA_OPTS="-Xms4G -Xmx4G -XX:+UseG1GC"' > ~/mesures/apache-tomcat-11.0.1/bin/setenv.sh
    chmod +x ~/mesures/apache-tomcat-11.0.1/bin/setenv.sh
    ```

4.  **Lancement bridé à 4 cœurs (0,1,2,3) :**
    ```bash
    ulimit -n 65535
    cd ~/mesures
    taskset -c 0,1,2,3 ./apache-tomcat-11.0.1/bin/startup.sh
    ```

---

## ÉTAPE 3 : Benchmarking (M1)

**Où :** Nœud Client.
```bash
# Avec un CPU bridé à 1.2GHz, 20k-30k RPS devraient suffire à atteindre 100% CPU
./wrk2/wrk -t32 -c500 -d60s -R30000 --latency "http://IP_INTERMEDIAIRE:8080/serv/Serv?machine=NOM_BACKEND&image=image_1KB.jpg"
```

---

## ÉTAPE 4 : Monitoring Précis (M2)

```bash
mpstat -P 0,1,2,3 1
```

---

## ANALYSE : Pourquoi brider le CPU ?

Si vous avez 20% d'idle avec un CPU à 2.1GHz (Turbo à 3.7GHz), cela signifie que le CPU finit son travail trop vite.

En abaissant la fréquence à **1.2GHz** :
1.  Chaque requête prend plus de temps CPU.
2.  Le CPU n'a plus le temps de "se reposer" (idle) entre deux requêtes.
3.  Vous atteindrez les **0.00% idle** (saturation réelle) beaucoup plus facilement, simulant ainsi une machine moins puissante.
