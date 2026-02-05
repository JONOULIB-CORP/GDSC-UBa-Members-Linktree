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

### 3. Tuning Tomcat (VERSION ROBUSTE)
Certaines commandes précédentes ont pu corrompre votre `server.xml` en ajoutant des attributs en double. Utilisez cette commande pour **réinitialiser et optimiser** proprement le connecteur :

```bash
# 1. Réécriture propre du Connecteur (Évite les erreurs de syntaxe XML)
sed -i '/<Connector port="8080"/,/\/>/c\    <Connector port="8080" protocol="HTTP/1.1" connectionTimeout="20000" redirectPort="8443" maxThreads="1000" socket.appReadBufSize="65536" socket.appWriteBufSize="65536" bufferSize="16384" />' ~/mesures/apache-tomcat-11.0.1/conf/server.xml

# 2. Désactivation propre des logs
sed -i '/AccessLogValve/,/\/>/d' ~/mesures/apache-tomcat-11.0.1/conf/server.xml

# 3. Mémoire (JVM)
echo 'export CATALINA_OPTS="-Xms4G -Xmx4G -XX:+UseG1GC"' > ~/mesures/apache-tomcat-11.0.1/bin/setenv.sh
chmod +x ~/mesures/apache-tomcat-11.0.1/bin/setenv.sh

# 4. VÉRIFICATION (Si Tomcat ne démarre pas, l'erreur sera affichée ici)
~/mesures/apache-tomcat-11.0.1/bin/catalina.sh configtest
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
./wrk2/wrk -t32 -c200 -d60s -R15000 --latency "http://IP_INTERMEDIAIRE:8080/serv/Serv?machine=NOM-BACKEND&image=small.jpg"
```

---

## DÉPANNAGE : Erreur "Connection refused" ou "SAXParseException"

Si Tomcat refuse de démarrer, c'est que votre fichier `server.xml` contient des erreurs (souvent des attributs en double comme `socket.appReadBufSize`).

1.  **Vérifier la cause** : `~/mesures/apache-tomcat-11.0.1/bin/catalina.sh configtest`
2.  **Si erreur XML** : Utilisez la commande `sed` de l'Étape 2.3.1 pour écraser le bloc corrompu par une version propre.
3.  **Vérifier les logs** : `tail -n 50 ~/mesures/apache-tomcat-11.0.1/logs/catalina.out`
