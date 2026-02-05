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
```bash
echo 1 | sudo-g5k tee /sys/devices/system/cpu/intel_pstate/no_turbo
sudo-g5k cpupower frequency-set -d 800MHz -u 800MHz -g performance
```

### 2. Tuning Tomcat
*   **Logs et Threads** : Désactiver les logs et passer à 1000 threads.
*   **Buffers pour grosses images** :
    ```bash
    sed -i 's/<Connector port="8080"/<Connector port="8080" socket.appReadBufSize="65536" socket.appWriteBufSize="65536" bufferSize="16384" maxThreads="1000"/' ~/mesures/apache-tomcat-11.0.1/conf/server.xml
    sed -i '/AccessLogValve/d' ~/mesures/apache-tomcat-11.0.1/conf/server.xml
    ```

### 3. Lancement bridé à 4 cœurs
```bash
ulimit -n 65535
cd ~/mesures
taskset -c 0,1,2,3 ./apache-tomcat-11.0.1/bin/startup.sh
```

---

## ÉTAPE 3 : Benchmarking (M1)

```bash
# ATTENTION : Utilisez des '-' (tirets) et non des '_' (underscores) pour les noms de machines !
./wrk2/wrk -t32 -c200 -d60s -R1000 --latency "http://IP_INTERMEDIAIRE:8080/serv/Serv?machine=dahu-11&image=image_1000KB.jpg"
```

---

## DÉPANNAGE : Erreur HTTP 500 (Internal Server Error)

Si `curl -I` renvoie une **HTTP 500**, le servlet a crashé. Voici les causes classiques sur G5K :

1.  **ERREUR DE TYPO (La plus fréquente)** :
    *   Les noms de machines sur G5K utilisent des **tirets**, pas des underscores.
    *   **FAUX** : `machine=dahu_11`
    *   **VRAI** : `machine=dahu-11`
2.  **Image manquante** :
    *   Vérifiez que le fichier `image_1000KB.jpg` existe bien sur le **Backend (M3)**.
3.  **Vérifier la stacktrace (M2)** :
    Pour voir l'erreur exacte, regardez la fin du log Tomcat sur l'intermédiaire :
    ```bash
    tail -n 50 ~/mesures/apache-tomcat-11.0.1/logs/catalina.out
    ```
    *Si vous voyez `java.net.UnknownHostException`, c'est que le nom dans `machine=` est faux.*
    *Si vous voyez `java.net.ConnectException`, c'est que Tomcat n'est pas lancé sur le Backend.*
