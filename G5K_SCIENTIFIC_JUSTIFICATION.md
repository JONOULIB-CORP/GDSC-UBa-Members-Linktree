# Justification Scientifique : Pourquoi le CPU plafonne malgré le RPSmax

Ce document explique scientifiquement pourquoi, sur Grid'5000, le système peut atteindre sa limite de débit (RPSmax) tout en gardant une utilisation CPU faible (ex: 50% d'idle) et une latence énorme (ex: 15s).

---

## 1. Le Goulot d'Étranglement du Noyau (Listen Queue)

Si vous avez augmenté le thread pool de Tomcat (ex: 1000 threads) mais que rien n'a changé, c'est que les requêtes sont bloquées **AVANT** d'arriver à Tomcat.

### Le mécanisme Linux :
Par défaut sur Grid'5000 (Debian/Ubuntu), `net.core.somaxconn` est réglé sur **128**.
*   Si vous lancez `wrk` avec **-c 1000**, le noyau ne peut mettre que 128 connexions dans la file d'attente.
*   **Résultat** : La latence explose car les requêtes font la queue dans le noyau Linux. Mais le CPU de Tomcat reste faible car il ne "voit" que 128 connexions à la fois, au lieu des 1000 threads disponibles.

---

## 2. La Barrière de la Grosse Image (1MB vs 1KB)

Vos derniers tests montrent que **500 RPS** avec une image de **1MB** sont plus difficiles à atteindre que **20 000 RPS** avec 1KB. Voici pourquoi :

### Comparaison des besoins en bande passante :
*   **Test 1KB @ 25 000 RPS** : Besoin de **25 MB/s**. C'est léger pour le réseau. Le bottleneck est le **CPU** (gestion de 25 000 requêtes).
*   **Test 1MB @ 500 RPS** : Besoin de **500 MB/s**. C'est massif. Le bottleneck devient la **Délivrance des données**.

### Pourquoi l'Intermédiaire (M2) reste en "Idle" à 50% ?
Dans votre test 1MB, vous obtenez **293 RPS** (286 MB/s) au lieu des 500 demandés.
1.  **L'attente du Backend (M3)** : Pour chaque image, M2 doit "tirer" 1MB depuis M3. Si M3 ou le réseau entre les deux plafonne à 286 MB/s, M2 ne recevra jamais assez de travail pour occuper ses 4 cœurs à 100%.
2.  **L'I/O Wait invisible** : Le CPU de M2 passe son temps à attendre que le prochain paquet de 1MB arrive. Pendant cette attente, le CPU ne fait rien : il est en **IDLE**.
3.  **SoftIRQ Hotspot** : Vos résultats montrent 35% de `%soft` sur certains cœurs. Cela prouve que le noyau travaille énormément pour gérer le flux réseau (2.3 Gbps), mais l'application (Tomcat) attend les données.

---

## 3. Preuve Mathématique : Loi de Little

Même avec un noyau débloqué, si la latence (**W**) reste élevée à cause du réseau ou du backend, le débit (**$\lambda$**) est limité par :
$$\lambda = L / W$$
*   Si **W** = 15s (latence observée) et **L** = 200 (vos connexions), alors **$\lambda$** = 13.3 requêtes/sec.
*   Si vous obtenez **293 RPS**, c'est que votre système gère en fait $\sim 4400$ requêtes en parallèle (en comptant les files d'attente système).
*   Le système est à sa limite de **Débit de Données**, pas de **Puissance CPU**.

---

## Conclusion Scientifique
"Le passage d'images de 1KB à 1MB déplace le goulot d'étranglement de la **Logique de Calcul** (CPU de M2) vers la **Logique de Transfert** (Bande passante Backend/Réseau). M2 reste partiellement idle car il est 'affamé' par M3 : il traite les données plus vite qu'il ne les reçoit."
