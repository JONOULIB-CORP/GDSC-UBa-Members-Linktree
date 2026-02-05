# Justification Scientifique : Pourquoi le CPU plafonne malgré le RPSmax

Ce document explique scientifiquement pourquoi, sur Grid'5000, le système peut atteindre sa limite de débit (RPSmax) tout en gardant une utilisation CPU faible (ex: 20% d'idle) et une latence énorme (ex: 15s).

---

## 1. Le Goulot d'Étranglement du Noyau (Listen Queue)

Si vous avez augmenté le thread pool de Tomcat (ex: 1000 threads) mais que rien n'a changé, c'est que les requêtes sont bloquées **AVANT** d'arriver à Tomcat.

### Le mécanisme Linux :
1.  **SYN Backlog** : La requête arrive sur la carte réseau.
2.  **Listen Queue (somaxconn)** : Une fois la connexion TCP établie, elle attend dans une file gérée par le noyau Linux d'être récupérée par l'application (Tomcat).
3.  **Application (Tomcat)** : L'Acceptor de Tomcat tire une connexion de la queue et la donne à un thread de travail.

### La Preuve du Problème sur G5K :
Par défaut sur Grid'5000 (Debian/Ubuntu), `net.core.somaxconn` est réglé sur **128**.
*   Si vous lancez `wrk` avec **-c 1000**, le noyau ne peut mettre que 128 connexions dans la file d'attente.
*   Les 872 autres connexions sont soit rejetées, soit attendent dans un état instable.
*   **Résultat** : La latence explose car les requêtes font la queue dans le noyau Linux. Mais le CPU de Tomcat reste faible car il ne "voit" que 128 connexions à la fois, au lieu des 1000 threads disponibles.

---

## 2. Loi de Little et "Stalled States"

Même avec un noyau débloqué, si la latence (**W**) reste élevée à cause du réseau ou du backend, le débit (**$\lambda$**) est limité par :
$$\lambda = L / W$$
Où **L** est votre nombre de threads.
*   Si **W** = 15s et **L** = 1000, alors **$\lambda$** = 66 requêtes/sec.
*   Les threads passent 14.9s à attendre et 0.1s à travailler. Le CPU ne peut pas monter à 100% car il n'a rien à faire pendant 99% du temps (I/O Wait).

---

## 3. Pourquoi ça marche "ailleurs" ?

Les environnements optimisés pour la performance (Cloud, serveurs d'entreprise) ont souvent des paramètres noyau beaucoup plus élevés par défaut :
*   `net.core.somaxconn` peut être à 1024 ou 4096.
*   `net.core.netdev_max_backlog` peut être à 5000+.

Sur Grid'5000, vous êtes sur du **Bare Metal "brut"**. C'est à vous d'ouvrir les vannes du noyau pour permettre au flux d'atteindre votre application.

---

## Conclusion Scientifique
"L'impossibilité d'atteindre 100% de CPU malgré un pool de threads Tomcat élevé est la signature d'un **goulot d'étranglement en amont de l'application**. La file d'attente système (`somaxconn`) agit comme un goulot de bouteille, limitant artificiellement le nombre de requêtes visibles par Tomcat. Les requêtes s'accumulent dans le noyau, créant une latence massive, tandis que les threads Tomcat restent sous-alimentés, laissant le CPU en état de repos relatif."
