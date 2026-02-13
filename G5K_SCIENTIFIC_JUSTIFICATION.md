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

## 4. L'Effet du 4ème Nœud : La "Taxe TCP"

L'ajout de M2 (Nginx) introduit un saut réseau supplémentaire. Si la connexion entre M2 et M3 n'est pas persistante (Keep-Alive), chaque requête de 1KB subit une "taxe" énorme.

### Pourquoi le RPS s'effondre (ex: 24k -> 13k) ?
Sans Keep-Alive entre M2 et M3 :
1.  **Triple Handshake** : Pour chaque image de 1KB, le système doit d'abord échanger 3 paquets (SYN, SYN-ACK, ACK) pour ouvrir la connexion.
2.  **Fermeture** : Puis échanger des paquets pour fermer la connexion.
3.  **Coût CPU** : Le CPU de M3 (Web Server) passe plus de temps à gérer l'ouverture/fermeture des sockets qu'à traiter les images.

### Analyse de vos résultats :
*   **Ancien (3-tier)** : 88% CPU pour 24 000 RPS.
*   **Nouveau (4-tier)** : 82% CPU pour 13 000 RPS.
*   **Verdict** : Le coût CPU par requête a augmenté de **~70%**. M3 travaille beaucoup plus dur pour faire moins de choses. C'est le goulot d'étranglement de la gestion des connexions.

---

## 5. Le Paradoxe de l'Efficacité

Si après avoir activé le **Keep-Alive**, vous observez que le RPS augmente mais que le CPU moyen diminue (ex: de 5%), c'est une excellente nouvelle technique, mais un défi pour votre test de saturation.

### Pourquoi le CPU baisse alors que le débit augmente ?
1. **Élimination du travail inutile** : Sans Keep-Alive, le CPU de M3 gaspillait 10 à 15% de ses cycles uniquement pour ouvrir et fermer des sockets TCP.
2. **Gain d'efficience** : Maintenant, 100% du travail CPU est dédié au traitement des images. Chaque requête "coûte" moins de cycles CPU qu'avant.
3. **Besoin de plus de charge** : Pour atteindre 100% CPU avec ce système plus efficace, vous devez augmenter la pression. Si vous étiez à 88% CPU pour 24 000 RPS avec l'ancien système "inefficace", il vous faudra peut-être 35 000 ou 40 000 RPS pour saturer les 4 cœurs maintenant.

---

## Conclusion Scientifique
"L'ajout d'un 4ème nœud introduit une taxe TCP massive qui sature le système prématurément. L'optimisation par Keep-Alive supprime cette taxe, rendant le système plus efficace (plus de RPS pour moins de CPU). Pour observer une **surcharge** (saturation à 100%), il faut alors pousser le débit (RPS) et la concurrence jusqu'à ce que la puissance de calcul pure devienne à nouveau le goulot d'étranglement. L'utilisation d'une **phase de précision** adaptative est essentielle pour détecter avec exactitude la transition entre un état stable et la saturation physique."

### Note sur l'Agent ODB et les Lambdas Java
Lors de nos expérimentations, nous avons identifié que l'agent d'instrumentation ODB actuel présente une incompatibilité avec les **expressions lambdas** Java qui capturent les objets `HttpServletResponse` ou `HttpServletRequest`. L'agent modifie la signature des méthodes synthétiques générées par le compilateur sans mettre à jour les sites d'appel `InvokeDynamic`, ce qui provoque des erreurs `NoSuchMethodError`. Pour garantir la stabilité, le code des servlets doit utiliser des structures de contrôle impératives classiques (boucles `for`, blocs `if`) plutôt que des API fonctionnelles (Streams, Optional.ifPresent) lors de la manipulation des entêtes et flux de sortie.
