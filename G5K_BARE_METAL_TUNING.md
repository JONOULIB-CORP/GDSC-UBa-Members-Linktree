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
    # Chercher les IRQs mlx5 (Dahu) ou par nom d'interface
    IRQS=$(grep -E "$INTERFACE|mlx5_comp" /proc/interrupts | awk '{print $1}' | sed 's/://')

    for IRQ in $IRQS; do
        # Masque 'f' = 1111 en binaire = Cœurs 0, 1, 2, 3
        echo "f" | sudo-g5k tee /proc/irq/$IRQ/smp_affinity > /dev/null
    done
    ```

3.  **Lancement de Tomcat bridé à 4 cœurs (0,1,2,3) :**
    ```bash
    ulimit -n 65535
    cd ~/votre_projet
    # 'taskset -c 0-3' force le processus à n'utiliser que les 4 premiers cœurs
    taskset -c 0,1,2,3 ./apache-tomcat-11.0.1/bin/startup.sh
    ```

---

## ÉTAPE 3 : Benchmarking (M1)

**Où :** Nœud Client.
```bash
# Augmentez -R (ex: 4000) pour saturer les 4 cœurs de l'intermédiaire
./wrk2/wrk -t8 -c100 -d60s -R4000 --latency "http://IP_INTERMEDIAIRE:8080/Serv?machine=IP_BACKEND&image=small.jpg"
```

---

## ÉTAPE 4 : Monitoring Précis (M2)

Pendant le test, lancez cette commande sur l'intermédiaire pour voir la consommation des 4 cœurs en temps réel.

1.  **Consommation en temps réel (par cœur) :**
    ```bash
    # Monitorer uniquement les cœurs 0, 1, 2, 3 toutes les secondes
    mpstat -P 0,1,2,3 1
    ```

2.  **Obtenir les moyennes à la fin :**
    *   **Méthode A (Automatique) :** Laissez `mpstat` tourner pendant toute la durée du test. Quand vous l'arrêtez avec `Ctrl+C`, il affiche une ligne **"Average:"** pour chaque cœur.
    *   **Méthode B (Capture) :** Pour capturer exactement la moyenne sur 60 secondes :
        ```bash
        mpstat -P 0,1,2,3 60 1
        ```
        Cette commande attendra 60 secondes et affichera directement la moyenne de consommation pour chaque cœur (0, 1, 2, 3) ainsi que la moyenne globale du système.

**Analyse scientifique :**
*   Si les 4 cœurs sont proches de 0% `%idle`, vous avez atteint la saturation réelle.
*   Comparez `%usr` (temps CPU application) et `%soft` (temps CPU réseau/interruptions).
