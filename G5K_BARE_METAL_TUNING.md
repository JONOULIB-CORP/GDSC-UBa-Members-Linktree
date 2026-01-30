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
# Pour 4 cœurs, le débit doit être ÉLEVÉ (ex: commencez à 5000 et montez par paliers de 2000)
./wrk2/wrk -t8 -c100 -d60s -R10000 --latency "http://IP_INTERMEDIAIRE:8080/Serv?machine=IP_BACKEND&image=small.jpg"
```

---

## ÉTAPE 4 : Monitoring Précis (M2)

Lancez cette commande sur l'intermédiaire **pendant** que le test tourne.
```bash
mpstat -P 0,1,2,3 1
```

---

## ANALYSE : Comment atteindre le 100% CPU ?

Si vos résultats montrent un `%idle` supérieur à 5% (ex: 55% d'idle), cela signifie que le système n'est pas encore saturé.

### 1. Augmenter le débit (-R)
C'est la cause n°1. Si vous avez 50% d'idle à `-R 4000`, passez directement à `-R 10000`. Continuez d'augmenter jusqu'à ce que l'idle tombe sous les 2-3%.

### 2. Vérifier le Client (M1)
Si vous augmentez `-R` mais que le CPU de l'Intermédiaire ne monte plus, vérifiez le Client :
```bash
# Sur le nœud Client (M1) pendant le test
top
```
Si le processus `wrk` sur le client utilise 100% d'un cœur (ou plafonne), il ne peut plus envoyer assez de requêtes.
**Solution :** Augmentez le nombre de threads (`-t16`) et de connexions (`-c200`) sur le client.

### 3. Vérifier la Bande Passante (M2)
Sur l'Intermédiaire, vérifiez si vous saturez le lien réseau (10 Gbps) :
```bash
sar -n DEV 1
```
Si `rxkB/s` + `txkB/s` atteint ~1 200 000 kB/s (1.2 GB/s), vous avez atteint la limite physique du réseau. Le CPU ne montera pas plus haut car la carte réseau ne peut plus débiter.

### 4. Vérifier les erreurs Tomcat
Si le CPU ne monte pas et que le réseau n'est pas saturé, vérifiez que Tomcat n'est pas limité par son nombre de threads internes (bien que 100 connexions wrk devraient suffire). Regardez les logs d'erreurs.
