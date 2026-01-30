# Guide de Benchmark Manuel : Protocole de Saturation CPU (Version Robuste Dahu/G5K)

Ce document détaille le protocole exact pour saturer le CPU (100%) sur Grid'5000, avec des commandes auto-adaptatives pour les nœuds de type **Dahu** (Mellanox).

---

## 0. Préparation (Sur TOUS les nœuds : C, I, S)

Installez les outils nécessaires.
```bash
sudo-g5k apt-get update && sudo-g5k apt-get install -y openjdk-17-jre sysstat linux-cpupower
```

---

## ÉTAPE 1 : Configuration du Serveur Backend (M3)

**Quand :** À faire en premier.
**Où :** Sur le nœud Backend.

1.  **Démarrer Tomcat :**
    ```bash
    cd ~/votre_projet
    rm -rf apache-tomcat-11.0.1/webapps/*
    cp serv.war apache-tomcat-11.0.1/webapps/ROOT.war
    ./apache-tomcat-11.0.1/bin/startup.sh
    ```

---

## ÉTAPE 2 : Optimisation de l'Intermédiaire (M2)

**Quand :** Après le démarrage du Backend.
**Où :** Sur le nœud Intermédiaire (Proxy).

1.  **Forcer le mode Performance du CPU :**
    ```bash
    sudo-g5k cpupower frequency-set -g performance
    ```

2.  **Tuning de la Pile Réseau :**
    ```bash
    sudo-g5k sysctl -w net.core.netdev_max_backlog=100000
    sudo-g5k sysctl -w net.core.somaxconn=10000
    sudo-g5k sysctl -w net.ipv4.ip_local_port_range="1024 65535"
    ```

3.  **Gestion Robuste des Interruptions (IRQ Affinity) :**
    *Sur Dahu, l'interface n'est pas 'eno1'. Voici comment la trouver et configurer les IRQs.*

    ```bash
    # 1. Désactiver irqbalance s'il existe (ignorez l'erreur s'il n'est pas là)
    sudo-g5k systemctl stop irqbalance 2>/dev/null || true

    # 2. Détecter automatiquement l'interface réseau active
    INTERFACE=$(ip route get 8.8.8.8 | grep -oP 'dev \K\S+')
    echo "Interface détectée : $INTERFACE"

    # 3. Lister et configurer TOUTES les IRQs liées à cette interface
    # Cette boucle va répartir les IRQs sur les cœurs 0, 1, 2, 3...
    IRQS=$(grep "$INTERFACE" /proc/interrupts | awk '{print $1}' | sed 's/://')

    # Si la recherche par nom d'interface échoue (Mellanox), on cherche par driver mlx5
    if [ -z "$IRQS" ]; then
        IRQS=$(grep "mlx5_comp" /proc/interrupts | awk '{print $1}' | sed 's/://')
    fi

    echo "IRQs à configurer : $IRQS"

    # Appliquer le masque 'f' (pour utiliser les 4 premiers cœurs) à chaque IRQ
    for IRQ in $IRQS; do
        echo "Configuration IRQ $IRQ..."
        echo "f" | sudo-g5k tee /proc/irq/$IRQ/smp_affinity > /dev/null
    done
    ```

4.  **Lancer Tomcat avec des limites augmentées :**
    ```bash
    ulimit -n 65535
    cd ~/votre_projet
    rm -rf apache-tomcat-11.0.1/webapps/*
    cp serv_a_tester.war apache-tomcat-11.0.1/webapps/ROOT.war
    ./apache-tomcat-11.0.1/bin/startup.sh
    ```

---

## ÉTAPE 3 : Benchmarking depuis le Client (M1)

**Où :** Sur le nœud Client.

1.  **Lancer le test :**
    ```bash
    # Augmentez -R jusqu'à ce que le CPU de l'intermédiaire sature
    ./wrk2/wrk -t8 -c100 -d60s -R4000 --latency "http://IP_INTERMEDIAIRE:8080/Serv?machine=IP_BACKEND&image=small.jpg"
    ```

---

## ÉTAPE 4 : Monitoring (Sur l'Intermédiaire M2)

Pendant le test, vérifiez que la charge est bien répartie.
```bash
mpstat -P ALL 1
```
*Si vous voyez plusieurs cœurs avec du `%soft` ou du `%usr`, l'optimisation IRQ a fonctionné.*
