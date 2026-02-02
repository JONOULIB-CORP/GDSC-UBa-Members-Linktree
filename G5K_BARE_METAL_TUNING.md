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
    rm -rf apache-tomcat-11.0.1/webapps/*
    cp serv.war apache-tomcat-11.0.1/webapps/
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
    cd ~/votre_projet
    rm -rf apache-tomcat-11.0.1/webapps/*
    cp serv.war apache-tomcat-11.0.1/webapps/
    taskset -c 0,1,2,3 ./apache-tomcat-11.0.1/bin/startup.sh
    ```

---

## ÉTAPE 3 : Benchmarking (M1) - La poussée finale vers 100%

Vos derniers résultats montrent que vous êtes à **~84% de charge** (16% idle). Pour atteindre les 100%, vous devez augmenter la pression.

**Où :** Nœud Client.
```bash
# Augmentez le débit à 35 000 RPS et la concurrence à 1000 connexions / 64 threads
./wrk2/wrk -t64 -c1000 -d60s -R35000 --latency "http://IP_INTERMEDIAIRE:8080/serv/Serv?machine=NOM_BACKEND&image=small.jpg"
```

### Pourquoi le CPU pourrait bloquer avant 100% ?

Si malgré l'augmentation de `-R`, le CPU reste bloqué à ~85-90% :

1.  **Bottleneck du Client (M1) :** Vérifiez avec `top` sur le client. Si `wrk` sature ses propres cœurs, il ne pourra pas envoyer les 35k RPS demandés.
2.  **Limite de Threads Tomcat (M2) :** Par défaut, Tomcat 11 limite le nombre de threads de traitement à **200**. Si vous avez 1000 connexions ouvertes, beaucoup attendent peut-être un thread libre.
    *   *Observation scientifique* : Si l'idle reste stable malgré l'augmentation de `-R`, c'est que Tomcat a atteint son débit maximum de requêtes par seconde autorisé par son pool de threads.
    *   *Solution* : Si vous voulez vraiment pousser le CPU à 100%, il faudra peut-être augmenter cette limite dans `conf/server.xml` (ex: `maxThreads="500"` dans le `<Connector ... />`).

---

## ÉTAPE 4 : Monitoring Précis (M2)

Lancez cette commande sur l'intermédiaire **pendant** que le test tourne.
```bash
mpstat -P 0,1,2,3 1
```
*Vérifiez les moyennes à la fin (ligne Average). L'objectif est de voir `%idle` proche de 0.00.*
