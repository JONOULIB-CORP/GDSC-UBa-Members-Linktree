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

3.  **Lancement de Tomcat bridé à 4 cœurs (0,1,2,3) :**
    ```bash
    ulimit -n 65535
    cd ~/mesures
    taskset -c 0,1,2,3 ./apache-tomcat-11.0.1/bin/startup.sh
    ```

---

## ÉTAPE 3 : Benchmarking (M1)

**Où :** Nœud Client.
```bash
# Exemple de poussée (32 threads, 500 connexions)
./wrk2/wrk -t32 -c500 -d60s -R25000 --latency "http://IP_INTERMEDIAIRE:8080/serv/Serv?machine=NOM_BACKEND&image=image_1KB.jpg"
```

---

## ÉTAPE 4 : Monitoring Précis (M2)

```bash
mpstat -P 0,1,2,3 1
```

---

## DÉPANNAGE : Diagnostic des "Résultats Catastrophiques"

Si vos résultats montrent un RPS très bas (ex: 5000 au lieu de 25000) et un débit de transfert minuscule (ex: quelques KB/s), **le serveur renvoie probablement des erreurs.**

### 1. Vérifier la taille des réponses (Analyse Scientifique)
Calculez la taille moyenne par requête : `Total Read / Total Requests`.
*   **Si Moyenne < 100 octets** : Le serveur renvoie des erreurs HTTP (404, 500). Un fichier de 1KB devrait générer > 1000 octets par réponse.
*   **Action** : Testez manuellement l'URL avec `curl -v "URL_DU_TEST"`. Si vous voyez `404 Not Found` ou `500 Internal Server Error`, corrigez le chemin de l'image ou le nom du backend.

### 2. Vérifier les Logs d'erreurs (M2)
Si le CPU travaille (ex: 60%) mais que le RPS est bas, le serveur perd du temps à gérer des exceptions Java.
```bash
# Regardez les erreurs en temps réel sur l'intermédiaire
tail -f ~/mesures/apache-tomcat-11.0.1/logs/catalina.out
```

### 3. Surcharge et Timeouts
Si `wrk` affiche beaucoup de **Socket errors (timeout)** :
*   Le serveur est soit totalement saturé (vérifiez `mpstat`, si idle < 5%).
*   Soit une file d'attente est pleine (vérifiez `net.core.somaxconn` et les threads Tomcat).
*   Soit le réseau entre l'intermédiaire et le backend est coupé.

### 4. Le Client (M1) est-il saturé ?
Si `wrk` n'arrive pas à envoyer le débit demandé alors que le serveur est "Idle" :
*   Vérifiez le CPU sur le nœud client. S'il est à 100%, augmentez le nombre de threads (`-t`) et de connexions (`-c`).
