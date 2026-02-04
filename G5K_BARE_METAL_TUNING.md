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
        # Masque 'f' = Cœurs 0, 1, 2, 3
        echo "f" | sudo-g5k tee /proc/irq/$IRQ/smp_affinity > /dev/null
    done
    ```

3.  **Lancement de Tomcat bridé à 4 cœurs (0,1,2,3) :**
    ```bash
    ulimit -n 65535
    cd ~/mesures
    # 'taskset -c 0-3' force le processus sur les 4 premiers cœurs
    taskset -c 0,1,2,3 ./apache-tomcat-11.0.1/bin/startup.sh
    ```

---

## ÉTAPE 3 : Benchmarking (M1)

**Où :** Nœud Client.
**Quand :** Une fois les serveurs démarrés.

```bash
# Exemple de poussée vers la saturation (32 threads, 500 connexions, 25k+ RPS)
./wrk2/wrk -t32 -c500 -d60s -R25000 --latency "http://IP_INTERMEDIAIRE:8080/serv/Serv?machine=NOM_BACKEND&image=image_1KB.jpg"
```
*   **IP_INTERMEDIAIRE** : L'IP de votre nœud M2.
*   **NOM_BACKEND** : Le nom d'hôte de votre nœud M3 (ex: dahu-11).

---

## ÉTAPE 4 : Monitoring Précis (M2)

Lancez cette commande sur l'intermédiaire **pendant** que le test tourne.
```bash
mpstat -P 0,1,2,3 1
```

---

## ANALYSE : Que faire si le CPU ne monte pas à 100% ?

Si votre `%idle` reste élevé (ex: > 15%) malgré un débit cible élevé :

1.  **Vérifier la saturation du Client (M1) :**
    Lancez `top` sur M1. Si le processus `wrk` sature ses propres cœurs, il ne pourra pas envoyer le débit demandé. Augmentez le nombre de threads (`-t64`) et de connexions (`-c1000`).
2.  **Limite de Threads Tomcat (M2) :**
    Vérifiez si Tomcat atteint sa limite de threads internes (souvent 200 par défaut). Si l'utilisation CPU plafonne alors que le débit demandé augmente, c'est un signe de saturation logicielle des threads Tomcat.
3.  **Vérifier la Bande Passante :**
    Lancez `sar -n DEV 1` sur M2. Vérifiez que vous ne saturez pas les 10Gbps (~1.2GB/s).
