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

---

## ÉTAPE 2 : Optimisation de l'Intermédiaire (M2)

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

3.  **ULTIME OPTIMISATION : Tomcat pour le 100% CPU**
    *Si vous bloquez à 80% avec 15s de latence, c'est que Tomcat est étranglé par ses logs et sa gestion mémoire.*

    *   **Désactiver COMPLÈTEMENT les Logs** (Gain massif) :
        ```bash
        # Supprime la ligne de la Valve AccessLog du fichier server.xml
        sed -i '/AccessLogValve/d' ~/mesures/apache-tomcat-11.0.1/conf/server.xml
        ```
    *   **Optimiser la JVM (GC G1 + 4GB)** :
        ```bash
        echo 'export CATALINA_OPTS="-Xms4G -Xmx4G -XX:+UseG1GC -XX:MaxGCPauseMillis=200"' > ~/mesures/apache-tomcat-11.0.1/bin/setenv.sh
        chmod +x ~/mesures/apache-tomcat-11.0.1/bin/setenv.sh
        ```
    *   **Vérifier les Threads** (Doit être à 1000) :
        ```bash
        sed -i 's/maxThreads="[0-9]*"/maxThreads="1000"/' ~/mesures/apache-tomcat-11.0.1/conf/server.xml
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
# RÉDUISEZ -c pour diminuer la latence et augmenter le CPU effectif.
# Si vous avez 1000 threads sur le serveur, testez avec 500 connexions.
./wrk2/wrk -t32 -c500 -d60s -R35000 --latency "http://IP_INTERMEDIAIRE:8080/serv/Serv?machine=NOM_BACKEND&image=image_1KB.jpg"
```

---

## ÉTAPE 4 : Monitoring Précis (M2)

```bash
mpstat -P 0,1,2,3 1
```

---

## ANALYSE : Pourquoi le CPU reste à ~75-80% ?

Si votre latence est > 10s, votre système est en **congestion**.

1.  **I/O Bottleneck** : Votre dernier test montrait que `AccessLogValve` était encore activé. Écrire des logs à 20 000 req/s sature le disque et bloque les threads Tomcat (ils attendent la fin de l'écriture).
2.  **Context Switching** : Avec `-c1000` (1000 connexions simultanées), le noyau Linux passe trop de temps à jongler entre les connexions au lieu de laisser Tomcat travailler. Essayez `-c500`.
3.  **GC Overhead** : Si la JVM n'a pas assez de mémoire ou un mauvais Garbage Collector, elle passe son temps à nettoyer la mémoire. Utilisez le GC G1 (Étape 2.3).
