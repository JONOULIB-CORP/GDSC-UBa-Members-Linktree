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

3.  **DÉBLOQUER LE CPU : Tuning de Tomcat (100% Hardware)**
    *Si vous avez 20% d'idle et 10s de latence, c'est que Tomcat sature logiciellement. Appliquez ceci :*

    *   **Augmenter les Threads** (Passez à 1000 pour gérer la charge massive) :
        ```bash
        sed -i 's/maxThreads="[0-9]*"/maxThreads="1000"/' ~/mesures/apache-tomcat-11.0.1/conf/server.xml
        ```
    *   **Désactiver les Logs d'accès** (Gros gain CPU) :
        ```bash
        # Commentez la Valve AccessLog dans server.xml
        sed -i 's/<Valve className="org.apache.catalina.valves.AccessLogValve"/<!-- <Valve className="org.apache.catalina.valves.AccessLogValve"/' ~/mesures/apache-tomcat-11.0.1/conf/server.xml
        sed -i 's/pattern="%h %l %u %t \&quot;%r\&quot; %s %b" \/>/pattern="%h %l %u %t \&quot;%r\&quot; %s %b" \/> -->/' ~/mesures/apache-tomcat-11.0.1/conf/server.xml
        ```
    *   **Allouer plus de mémoire à la JVM** :
        ```bash
        echo 'export CATALINA_OPTS="-Xms2G -Xmx2G"' > ~/mesures/apache-tomcat-11.0.1/bin/setenv.sh
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
# Recommandation : Gardez -c (connexions) inférieur ou égal à maxThreads
./wrk2/wrk -t32 -c500 -d60s -R35000 --latency "http://IP_INTERMEDIAIRE:8080/serv/Serv?machine=NOM_BACKEND&image=image_1KB.jpg"
```

---

## ÉTAPE 4 : Monitoring Précis (M2)

```bash
mpstat -P 0,1,2,3 1
```

---

## ANALYSE : Pourquoi le CPU stagne à ~80% ?

Si vous voyez une latence élevée (ex: 10s) mais 20% d'idle :

1.  **Congestion Thread Pool** : Tomcat ne peut plus prendre de nouvelles requêtes. Il attend qu'un thread se libère. Le CPU ne travaille pas pendant cette attente.
    *   *Solution* : Augmenter `maxThreads` à 1000.
2.  **Overhead de Logging** : Écrire chaque ligne de log consomme du CPU inutilement à 20k RPS.
    *   *Solution* : Désactiver les logs (Étape 2.3).
3.  **Collapse Point** : Votre RPS observé (19k) est plus bas que votre test précédent (23k) ? Vous avez dépassé le point de rupture. Trop de connexions concurrentes (`-c1000`) tuent la performance par "Context Switching".
    *   *Solution* : Réduisez `-c` à 500 et gardez `-R` à 30000.
