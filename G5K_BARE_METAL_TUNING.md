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
2.  **URGENT : Tuning Kernel pour les grosses images** :
    ```bash
    sudo-g5k sysctl -w net.core.somaxconn=10000
    sudo-g5k sysctl -w net.core.netdev_max_backlog=100000
    ```

---

## ÉTAPE 2 : Limitation et BRIDAGE de l'Intermédiaire (M2)

### 1. Brider la fréquence au MINIMUM
```bash
echo 1 | sudo-g5k tee /sys/devices/system/cpu/intel_pstate/no_turbo
sudo-g5k cpupower frequency-set -d 800MHz -u 800MHz -g performance
```

### 2. DÉBLOQUER LE NOYAU (Ouvrir les vannes)
```bash
sudo-g5k sysctl -w net.core.somaxconn=10000
sudo-g5k sysctl -w net.core.netdev_max_backlog=100000
```

### 3. Tuning Tomcat
*   **Threads** : `maxThreads="1000"`.
*   **Logs** : Désactiver `AccessLogValve`.
*   **Buffers (Pour 1MB)** :
    ```bash
    # Ajouter socket.appReadBufSize="65536" socket.appWriteBufSize="65536" dans server.xml
    ```

### 4. Lancement bridé à 4 cœurs
```bash
ulimit -n 65535
cd ~/mesures
taskset -c 0,1,2,3 ./apache-tomcat-11.0.1/bin/startup.sh
```

---

## ÉTAPE 3 : Benchmarking (M1) - Protocole Scientifique

Pour valider votre setup, vous devez comparer deux scénarios :

### Scénario A : Saturation CPU (Image 1KB)
Le but est de voir 100% CPU sur M2.
```bash
./wrk2/wrk -t32 -c500 -d60s -R25000 --latency "http://IP_INTERMEDIAIRE:8080/serv/Serv?machine=NOM-BACKEND&image=image_1KB.jpg"
```
*   **Attendu** : CPU M2 proche de 100%, Idle < 5%. RPS observé ~ 23-25k.

### Scénario B : Saturation Transfert (Image 1MB)
Ici, le CPU de M2 restera probablement Idle car le réseau/backend limite le flux.
```bash
./wrk2/wrk -t32 -c200 -d60s -R1000 --latency "http://IP_INTERMEDIAIRE:8080/serv/Serv?machine=NOM-BACKEND&image=image_1000KB.jpg"
```
*   **Attendu** : CPU M2 à ~50%. Débit de transfert plafonné (ex: 280MB/s).
*   **Preuve** : Si vous augmentez -R mais que le débit ne dépasse pas 280MB/s, c'est que **le Backend (M3) est au maximum de sa capacité d'envoi**.

---

## ANALYSE : Interprétation
Si l'image est grosse (1MB), M2 passe sa vie à attendre les données de M3. Un CPU qui attend est un CPU en **IDLE**. C'est normal et scientifiquement correct.
Plus d'infos : [**Justification Scientifique**](./G5K_SCIENTIFIC_JUSTIFICATION.md)
