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

## 3. Preuve Mathématique : Loi de Little et Congestion Collapse

Même avec un noyau débloqué, si la latence (**W**) reste élevée à cause du réseau ou du backend, le débit (**$\lambda$**) est limité par :
$$\lambda = L / W$$
*   Si **W** = 15s (latence observée) et **L** = 200 (vos connexions), alors **$\lambda$** = 13.3 requêtes/sec.
*   Le système est à sa limite de **Débit de Données**, pas de **Puissance CPU**.

### Le Phénomène de Congestion Collapse
Si vous poussez le débit cible (target RPS) bien au-delà de la capacité maximale, la latence explose (ex: >10s). Dans cet état, le CPU de M3 passe son temps à gérer des timeouts et des retransmissions TCP plutôt qu'à traiter des requêtes utiles. Le RPS réel chute alors que le CPU reste très occupé. C'est le signe qu'il faut réduire le `target RPS` pour trouver le point de bascule exact.

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

## 6. Le Point d'Inflexion de la Payload (Pourquoi 1KB est un piège)

Lors des tests avec des petites payloads (1KB, 10KB), la différence entre `serv` (Standard) et `serv1` (ODB) peut paraître négligeable. C'est un comportement attendu expliqué par la répartition des coûts CPU :

### Coût Fixe vs Coût Variable
1.  **Coût Fixe (Network Stack) :** Le travail pour gérer l'interruption réseau, le paquet TCP et le parsing HTTP. Ce coût est présent pour chaque requête, quelle que soit la taille de l'image. Il se manifeste par un fort `%soft` et `%sys` dans `mpstat`.
2.  **Coût Variable (Data Copy) :** Le temps CPU passé à déplacer les données en mémoire (`memcpy`). Ce coût est strictement proportionnel à la taille de la payload.

### Analyse du bénéfice ODB
*   **À 1KB :** Le coût fixe représente ~99% du travail. Éliminer le coût variable (1%) ne change pas le RPS de façon visible.
*   **À 1MB :** Le coût variable (copie de 1Mo) devient massif et dépasse le coût fixe.
    *   **Standard (`serv`) :** S'effondre car le CPU passe son temps à copier des mégaoctets.
    *   **ODB (`serv1`) :** Reste performant car il continue de ne traiter que des descripteurs de ~1KB.

**Conclusion :** La preuve de l'efficacité d'ODB n'est pas l'augmentation du RPS max à 1KB, mais l'**invariance du RPS** quand la taille de l'image augmente vers 1MB.

## Conclusion Scientifique
"L'ajout d'un 4ème nœud introduit une taxe TCP massive qui sature le système prématurément. L'optimisation par Keep-Alive supprime cette taxe, rendant le système plus efficace (plus de RPS pour moins de CPU). Pour observer une **surcharge** (saturation à 100%), il faut alors pousser le débit (RPS) et la concurrence jusqu'à ce que la puissance de calcul pure devienne à nouveau le goulot d'étranglement. L'utilisation d'une **phase de précision** adaptative est essentielle pour détecter avec exactitude la transition entre un état stable et la saturation physique. Enfin, la supériorité d'ODB se démontre par sa capacité à maintenir un RPS élevé sur de grandes payloads (1MB), là où une architecture standard subit une dégradation linéaire de ses performances."

### Note sur l'Agent ODB et les Lambdas Java
L'agent d'instrumentation ODB (`Parser6.java`) présente une limitation technique majeure : il ne traite pas les instructions `INVOKEDYNAMIC`.
- **Symptôme** : `NoSuchMethodError` lors de l'appel de lambdas capturant des objets Servlet.
- **Cause Technique** : L'agent transforme les signatures des méthodes générées pour les lambdas (ex: `lambda$doGet$0`), mais ne met pas à jour les arguments de la **Bootstrap Method** dans le pool de constantes. L'appel dynamique tente alors d'exécuter une méthode avec l'ancienne signature (ex: `jakarta.servlet...`) qui n'existe plus dans la classe transformée.
- **Solution** : Le code des servlets doit être écrit en style **impératif classique** (boucles `for`, blocs `if`) pour éviter la génération de `INVOKEDYNAMIC` par le compilateur, ou le parseur doit être mis à jour pour transformer les `bsmArgs`.

### Le piège de l'API HttpClient (Matérialisation)
Pour bénéficier d'ODB dans un rôle de Proxy, il est impératif d'utiliser des API de streaming.
- **À éviter** : `BodyHandlers.ofByteArray()` télécharge l'intégralité des données en RAM sur le Proxy avant même que l'agent ODB ne puisse intervenir. Le bénéfice est alors nul (la copie a déjà eu lieu).
- **À privilégier** : `BodyHandlers.ofInputStream()` permet à l'agent d'intercepter le flux et de manipuler des descripteurs virtuels au lieu des octets réels.
