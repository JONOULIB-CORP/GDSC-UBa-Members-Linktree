# Guide de Benchmark Manuel : Protocole de Saturation sur 4 Cœurs (G5K)

Ce document détaille le protocole pour limiter l'exécution à **4 cœurs** sur l'intermédiaire et obtenir un monitoring précis (par cœur + moyennes).

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
2.  **Surveiller le CPU du Backend :**
    *Pendant le test, vérifiez si le backend est lui-même à 100%. S'il est saturé, l'intermédiaire ne pourra jamais atteindre 100% car il passera son temps à attendre le backend.*

---

## ÉTAPE 2 : Limitation à 4 Cœurs et Tuning de l'Intermédiaire (M2)

**Où :** Nœud Intermédiaire.

1.  **Optimisation CPU :**
    ```bash
    sudo-g5k cpupower frequency-set -g performance
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

3.  **DÉBLOQUER LE CPU : Augmenter les Threads Tomcat :**
    *Par défaut, Tomcat limite à 200 threads. Si vous saturez ces 200 threads, le CPU s'arrêtera de monter même si vous augmentez -R.*
    ```bash
    # Augmenter à 500 threads dans server.xml
    sed -i 's/<Connector port="8080"/<Connector port="8080" maxThreads="500"/' ~/mesures/apache-tomcat-11.0.1/conf/server.xml
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
# Pour saturer 4 cœurs réels, essayez ces paramètres :
./wrk2/wrk -t32 -c500 -d60s -R30000 --latency "http://IP_INTERMEDIAIRE:8080/serv/Serv?machine=NOM_BACKEND&image=image_1KB.jpg"
```

---

## ÉTAPE 4 : Monitoring Précis (M2)

```bash
mpstat -P 0,1,2,3 1
```

---

## ANALYSE : Pourquoi le CPU bloque à ~75-80% ?

Si vous voyez une latence énorme (ex: 15s) mais que le CPU reste à 20% d'idle, vous avez un **bottleneck logiciel**.

1.  **Saturation des Threads (M2)** : Les threads Tomcat sont tous occupés. Les nouvelles requêtes attendent dans la file d'attente TCP et ne consomment pas de CPU.
    *   **Action** : Augmentez `maxThreads` (voir Étape 2.3).
2.  **Saturation du Backend (M3)** : Si le backend est à 100% CPU, l'intermédiaire attend les données. L'attente réseau n'utilise pas le CPU.
    *   **Action** : Vérifiez `mpstat` sur M3. Si M3 est à 100%, l'intermédiaire ne montera pas plus haut.
3.  **Trop de Connexions Concurrentes** : Avec `-c1000`, la gestion de la file d'attente devient très lourde.
    *   **Action** : Testez avec `-c500` mais en gardant un `-R` élevé (ex: 35000).
