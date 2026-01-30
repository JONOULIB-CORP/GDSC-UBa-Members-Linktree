# Guide d'Optimisation de Performance sur Grid'5000 (Bare Metal)

Ce guide fournit les étapes et commandes nécessaires pour saturer le CPU (atteindre le "vrai" 100%) et optimiser la bande passante lors de tests de charge haute performance (RPS élevé) sur des nœuds Grid'5000.

## 1. Pourquoi le CPU plafonne à 90% ? (Analyse Scientifique)

Si vous observez un plateau à 90% malgré une charge croissante, cela est généralement dû à l'un des facteurs suivants :

*   **Bottleneck SoftIRQ (Saturation d'un seul cœur)** : Les interruptions réseau sont souvent traitées par un seul cœur. Si ce cœur est à 100% en mode `%soft` (SoftIRQ), le système ne peut plus traiter de paquets supplémentaires, même si les autres cœurs sont libres. L'utilisation *moyenne* semble bloquée sous les 100%.
*   **Gouverneur de Fréquence** : Par défaut, le CPU peut être en mode `powersave`. Il ne monte pas à sa fréquence Turbo maximale, ou il y a une latence dans l'ajustement.
*   **Limites du Kernel** : Les files d'attente réseau (`backlog`) ou les buffers TCP sont saturés, forçant le CPU à passer son temps à rejeter des paquets (overhead invisible).
*   **SMT (Hyper-threading)** : 90% sur des cœurs logiques peut signifier que les unités d'exécution physiques partagées sont déjà saturées.

---

## 2. Commandes d'Optimisation

Exécutez ces commandes sur le nœud **Intermédiaire** (Proxy/Serveur sous test).

### A. Forcer le mode Performance du CPU
Élimine les baisses de fréquence et force le Turbo Boost.
```bash
# Installer l'outil si nécessaire
sudo-g5k apt-get update && sudo-g5k apt-get install -y linux-cpupower

# Définir le gouverneur sur 'performance' pour TOUS les cœurs
sudo-g5k cpupower frequency-set -g performance
```

### B. Optimisation de la Pile Réseau (sysctl)
Augmente les limites de réception et les buffers pour éviter les pertes de paquets silencieuses.
```bash
# Augmenter la file d'attente d'entrée (très important pour le haut RPS)
sudo-g5k sysctl -w net.core.netdev_max_backlog=100000

# Augmenter les buffers TCP (16MB max)
sudo-g5k sysctl -w net.core.rmem_max=16777216
sudo-g5k sysctl -w net.core.wmem_max=16777216
sudo-g5k sysctl -w net.ipv4.tcp_rmem="4096 87380 16777216"
sudo-g5k sysctl -w net.ipv4.tcp_wmem="4096 65536 16777216"

# Optimiser la réutilisation des sockets (évite l'épuisement des ports)
sudo-g5k sysctl -w net.ipv4.tcp_tw_reuse=1
sudo-g5k sysctl -w net.ipv4.ip_local_port_range="1024 65535"
```

### C. Gestion de l'Affinité des Interruptions (IRQ Affinity)
C'est l'étape la plus critique pour "dépasser" le plateau des 90%. Il faut forcer la carte réseau à distribuer ses interruptions sur plusieurs cœurs.

1.  Trouver l'interface réseau (ex: `eno1` ou `eth0`) : `ip link`
2.  Identifier les IRQ associées :
    ```bash
    grep eno1 /proc/interrupts | awk '{print $1}' | sed 's/://'
    ```
3.  Distribuer les IRQs (Exemple : si vous avez 4 IRQs et voulez utiliser les cœurs 0-3) :
    ```bash
    # Note : Le masque 'f' (1111 en binaire) permet d'utiliser les 4 premiers cœurs.
    # Remplacez $IRQ par les numéros trouvés à l'étape précédente.
    echo "f" | sudo-g5k tee /proc/irq/$IRQ/smp_affinity
    ```
    *Note : Sur G5K, le script `irqbalance` est souvent actif. Il est préférable de l'arrêter pour un contrôle manuel scientifique.*
    ```bash
    sudo-g5k systemctl stop irqbalance
    ```

### D. Augmenter les Limites de Fichiers (ulimit)
Essentiel pour gérer des milliers de connexions simultanées avec `wrk`.
```bash
ulimit -n 65535
```

---

## 3. Protocole de Vérification Scientifique

Pendant que votre test `wrk` tourne, ouvrez une autre console sur le nœud intermédiaire :

### Vérifier la saturation par cœur
```bash
mpstat -P ALL 1
```
*   **Si un cœur affiche `%soft` proche de 100%** : Vous avez un bottleneck d'interruptions réseau. Appliquez l'optimisation IRQ Affinity (Section 2.C).
*   **Si `%idle` est proche de 0% sur tous les cœurs** : Félicitations, vous avez atteint la saturation CPU réelle.

### Vérifier la bande passante réelle
```bash
sar -n DEV 1
```
*   Regardez `rxkB/s` et `txkB/s`. Comparez avec la capacité théorique de l'interface (10 Gbps = ~1250 MB/s).

### Vérifier les erreurs réseau (Paquets ignorés)
```bash
netstat -s | grep -i "dropped"
# OU
ethtool -S eno1 | grep "drop"
```
*   Si les compteurs augmentent, votre bottleneck est au niveau du kernel/driver (Section 2.B nécessaire).
