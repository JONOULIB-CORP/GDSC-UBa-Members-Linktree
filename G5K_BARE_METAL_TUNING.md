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
2.  **Tuning Kernel** :
    ```bash
    sudo-g5k sysctl -w net.core.somaxconn=10000
    ```

---

## ÉTAPE 2 : Limitation et BRIDAGE de l'Intermédiaire (M2)

### 1. Brider la fréquence au MINIMUM
```bash
echo 1 | sudo-g5k tee /sys/devices/system/cpu/intel_pstate/no_turbo
sudo-g5k cpupower frequency-set -d 800MHz -u 800MHz -g performance
```

### 2. DÉBLOQUER LE NOYAU
```bash
sudo-g5k sysctl -w net.core.somaxconn=10000
sudo-g5k sysctl -w net.core.netdev_max_backlog=100000
```

### 3. Tuning Tomcat pour le Maximum de Performance
*   **Threads** : Réglez `maxThreads="1000"` dans `conf/server.xml`.
*   **Désactiver les Logs (ROBUSTE)** :
    ```bash
    # Cette commande supprime correctement la Valve AccessLog même sur plusieurs lignes
    sed -i '/AccessLogValve/,/\/>/d' ~/mesures/apache-tomcat-11.0.1/conf/server.xml
    ```
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

```bash
# Vérifiez que Tomcat tourne avant de lancer wrk !
./wrk2/wrk -t32 -c200 -d60s -R15000 --latency "http://IP_INTERMEDIAIRE:8080/serv/Serv?machine=NOM-BACKEND&image=small.jpg"
```

---

## DÉPANNAGE : Erreur "Connection refused"

Si `wrk` affiche **Connection refused**, c'est que Tomcat n'a pas démarré (probablement une erreur de syntaxe XML dans `server.xml`).

1.  **Vérifier le processus** : `ps aux | grep catalina`
2.  **Vérifier le port** : `ss -tlnp | grep 8080`
3.  **Lire la cause réelle de l'erreur** :
    ```bash
    tail -n 50 ~/mesures/apache-tomcat-11.0.1/logs/catalina.out
    ```
    *Si vous voyez une erreur de parsing XML, restaurez votre fichier `server.xml` original ou corrigez la balise supprimée.*
