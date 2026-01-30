# Guide de Benchmark Manuel : Protocole de Saturation CPU sur Grid'5000

Ce document détaille le protocole exact, nœud par nœud et étape par étape, pour réussir à saturer le CPU (100%) lors de vos tests sur Grid'5000.

---

## 0. Préparation (Sur TOUS les nœuds : C, I, S)

Avant de commencer, assurez-vous que les outils de base sont installés sur les trois nœuds.
```bash
sudo-g5k apt-get update && sudo-g5k apt-get install -y openjdk-17-jre sysstat
```

---

## ÉTAPE 1 : Configuration du Serveur Backend (M3)

Le backend doit être prêt à servir les images avant que le reste ne démarre.

**Quand :** À faire en premier.
**Où :** Sur le nœud Backend.

1.  **Préparer Tomcat :**
    ```bash
    # Déployer l'application standard
    cd ~/votre_projet
    rm -rf apache-tomcat-11.0.1/webapps/*
    cp serv.war apache-tomcat-11.0.1/webapps/ROOT.war
    ```
2.  **Démarrer Tomcat :**
    ```bash
    ./apache-tomcat-11.0.1/bin/startup.sh
    ```

---

## ÉTAPE 2 : Optimisation et Lancement de l'Intermédiaire (M2)

C'est ici que les optimisations sont cruciales pour dépasser le plateau des 90%.

**Quand :** Après le démarrage du Backend.
**Où :** Sur le nœud Intermédiaire (Proxy).

1.  **Optimisation du CPU (Gouverneur) :**
    ```bash
    sudo-g5k apt-get install -y linux-cpupower
    sudo-g5k cpupower frequency-set -g performance
    ```
2.  **Tuning de la Pile Réseau (Kernel) :**
    ```bash
    sudo-g5k sysctl -w net.core.netdev_max_backlog=100000
    sudo-g5k sysctl -w net.core.somaxconn=10000
    sudo-g5k sysctl -w net.ipv4.ip_local_port_range="1024 65535"
    ```
3.  **Gestion des Interruptions (Affinité IRQ) :**
    *C'est la commande magique pour débloquer le CPU.*
    ```bash
    # 1. Arrêter l'équilibreur automatique
    sudo-g5k systemctl stop irqbalance

    # 2. Identifier l'IRQ de votre carte réseau (ex: eno1)
    # Cherchez le numéro à gauche de 'eno1' dans /proc/interrupts
    grep eno1 /proc/interrupts | awk '{print $1}' | sed 's/://'

    # 3. Forcer l'IRQ sur plusieurs cœurs (ex: masque 'f' pour les cœurs 0-3)
    # Remplacez $IRQ par le numéro trouvé ci-dessus
    echo "f" | sudo-g5k tee /proc/irq/$IRQ/smp_affinity
    ```
4.  **Augmenter les limites système :**
    ```bash
    ulimit -n 65535
    ```
5.  **Démarrer l'application à tester :**
    ```bash
    # Déployer la version (Serv ou Serv-odb)
    cd ~/votre_projet
    rm -rf apache-tomcat-11.0.1/webapps/*
    cp serv_a_tester.war apache-tomcat-11.0.1/webapps/ROOT.war
    ./apache-tomcat-11.0.1/bin/startup.sh
    ```

---

## ÉTAPE 3 : Benchmarking depuis le Client (M1)

**Quand :** Une fois que le Backend et l'Intermédiaire sont prêts.
**Où :** Sur le nœud Client.

1.  **Compiler wrk2 (si ce n'est pas fait) :**
    ```bash
    cd ~/votre_projet/wrk2 && make
    ```
2.  **Lancer le test de charge :**
    ```bash
    # Remplacez IP_INTERMEDIAIRE et IP_BACKEND par les vraies IPs
    ./wrk -t8 -c100 -d60s -R2000 --latency "http://IP_INTERMEDIAIRE:8080/Serv?machine=IP_BACKEND&image=small.jpg"
    ```

---

## ÉTAPE 4 : Monitoring (Pendant le test)

Pendant que `wrk` tourne à l'Étape 3, exécutez ces commandes pour valider scientifiquement la saturation.

**Où :** Sur le nœud **Intermédiaire (M2)**.

1.  **Vérifier la saturation par cœur :**
    ```bash
    mpstat -P ALL 1
    ```
    *Regardez si `%soft` est distribué sur plusieurs cœurs ou si un seul cœur plafonne.*

2.  **Surveiller le trafic réseau :**
    ```bash
    sar -n DEV 1
    ```

3.  **Vérifier la fréquence réelle du CPU :**
    ```bash
    watch -n 1 "grep MHz /proc/cpuinfo"
    ```
    *Vérifiez que tous les cœurs sont à leur fréquence maximale (Turbo).*
