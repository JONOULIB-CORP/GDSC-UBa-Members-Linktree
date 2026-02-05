# Guide de Benchmark Manuel : Protocole de Saturation sur 4 Cœurs (G5K)

Ce document détaille le protocole pour limiter l'exécution à **4 cœurs** sur l'intermédiaire et le **brider** pour atteindre les 100% CPU réels.

---

## 0. Préparation (Sur TOUS les nœuds : C, I, S)

```bash
sudo-g5k apt-get update && sudo-g5k apt-get install -y openjdk-17-jre sysstat linux-cpupower
```

---

## ÉTAPE 1 : Configuration du Serveur Backend (M3)

**Où :** Nœud Backend.
1.  **Démarrer Tomcat.**
2.  **URGENT : Vérifiez le CPU du Backend (M3) avec `mpstat` !**
    *   *Observation* : Pour une image de 1000KB (1MB), le backend doit envoyer énormément de données. S'il sature (100% CPU), l'intermédiaire (M2) sera bloqué et restera en idle (30%+) car il attend que les paquets arrivent.

---

## ÉTAPE 2 : Limitation et BRIDAGE de l'Intermédiaire (M2)

### 1. Brider la fréquence au MINIMUM
```bash
echo 1 | sudo-g5k tee /sys/devices/system/cpu/intel_pstate/no_turbo
sudo-g5k cpupower frequency-set -d 800MHz -u 800MHz -g performance
```

### 2. Tuning Tomcat pour les Grosses Images (1MB)
Quand la taille de l'image augmente, le coût CPU change : ce n'est plus la gestion de la requête qui coûte cher, mais la **gestion des buffers** (mémoire et réseau).

*   **Désactiver les logs** (Essentiel) : `sed -i '/AccessLogValve/d' ~/mesures/apache-tomcat-11.0.1/conf/server.xml`
*   **Augmenter les Buffers Réseau** :
    Pour 1MB, les buffers par défaut sont trop petits. Tomcat passe son temps à faire des petits read/write.
    ```bash
    # Modifier le Connecteur dans server.xml pour ajouter des buffers plus gros
    sed -i 's/<Connector port="8080"/<Connector port="8080" socket.appReadBufSize="65536" socket.appWriteBufSize="65536" bufferSize="16384"/' ~/mesures/apache-tomcat-11.0.1/conf/server.xml
    ```

---

## ÉTAPE 3 : Benchmarking (M1)

**Où :** Nœud Client.
```bash
# Avec 1MB, le RPS sera forcément bas (~500 à 1000). Ne mettez pas un -R trop haut (tentez -R 1000).
./wrk2/wrk -t32 -c200 -d60s -R1000 --latency "http://IP_INTERMEDIAIRE:8080/serv/Serv?machine=NOM_BACKEND&image=image_1000KB.jpg"
```

---

## ANALYSE : Pourquoi le RPS plafonne avec 1MB sans saturer le CPU/Réseau ?

Si vous avez 30% d'idle et seulement 486MB/s de débit (~4Gbps) :

1.  **Le Goulot est au Backend (M3)** : C'est l'explication la plus probable. Pour envoyer 500 images de 1MB par seconde, le Backend doit travailler dur. Si le Backend n'est pas optimisé (CPU 100%, ou buffers trop petits), l'Intermédiaire **attend** les données. Le CPU de l'intermédiaire reste donc en idle.
    *   **Test** : Lancez `mpstat` sur M3. Si M3 est à 100% ou saturé sur un cœur, il bride tout le test.
2.  **Séquentialité du Proxy** : L'intermédiaire doit lire 1MB avant de le renvoyer. Ce temps de lecture (latency=359ms) multiplié par le nombre de connexions limite mathématiquement le RPS, même si le CPU est libre.
    *   **Solution** : Augmentez massivement le nombre de threads Tomcat sur M2 (`maxThreads="2000"`) pour compenser la latence de lecture par plus de parallélisme.
3.  **Window TCP** : Le lien entre M2 et M3 est peut-être limité par la fenêtre TCP.
    *   **Action** : `sudo-g5k sysctl -w net.ipv4.tcp_window_scaling=1` (déjà activé par défaut sur G5K, mais à vérifier).
