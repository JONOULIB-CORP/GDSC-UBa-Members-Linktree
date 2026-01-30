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
1.  **Démarrer Tomcat normalement :**
    ```bash
    cd ~/votre_projet
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
    On force le traitement réseau sur les mêmes cœurs que l'application.
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
    cd ~/votre_projet
    taskset -c 0,1,2,3 ./apache-tomcat-11.0.1/bin/startup.sh
    ```

---

## ÉTAPE 3 : Benchmarking (M1)

**Où :** Nœud Client.
```bash
# Note : Commencez par -R 2000 puis augmentez (4000, 6000...)
./wrk2/wrk -t8 -c100 -d60s -R4000 --latency "http://IP_INTERMEDIAIRE:8080/Serv?machine=IP_BACKEND&image=small.jpg"
```

---

## ÉTAPE 4 : Monitoring Précis (M2)

Lancez cette commande sur l'intermédiaire **pendant** que le test tourne.
```bash
mpstat -P 0,1,2,3 1
```

---

## DÉPANNAGE : Que faire si le CPU reste à ~97% d'idle ?

Si vos résultats `mpstat` ressemblent à ceci (Idle > 90%) :
```
Average:  CPU    %usr   %sys   %soft   %idle
Average:   0    1.52   0.81   0.52   97.15
```
**Ce n'est PAS normal.** Le serveur ne reçoit pas de charge. Voici comment corriger :

1.  **Vérifier la connectivité (depuis le Client) :**
    ```bash
    # Si le curl échoue ou renvoie une erreur 404/500, wrk n'enverra rien d'utile
    curl -I "http://IP_INTERMEDIAIRE:8080/Serv?machine=IP_BACKEND&image=small.jpg"
    ```
2.  **Vérifier les Logs Tomcat (sur l'Intermédiaire) :**
    ```bash
    # Regardez si les requêtes arrivent en temps réel
    tail -f ~/votre_projet/apache-tomcat-11.0.1/logs/localhost_access_log.*.txt
    ```
3.  **Vérifier la sortie de wrk (sur le Client) :**
    *   Si `wrk` affiche **"Socket errors: connect 100..."**, c'est que l'intermédiaire n'accepte pas les connexions.
    *   Si `wrk` affiche **"Requests/sec: 0.00"**, l'URL est probablement fausse.
4.  **Augmenter le débit (-R) :**
    Si tout fonctionne mais que le CPU reste bas, augmentez massivement le `-R` (ex: `-R 10000`).
5.  **Vérifier l'IP de la machine backend :**
    L'URL doit contenir l'IP réelle du backend (`machine=IP_BACKEND`). Si le backend est injoignable par l'intermédiaire, le proxy va attendre en vain (idle).
