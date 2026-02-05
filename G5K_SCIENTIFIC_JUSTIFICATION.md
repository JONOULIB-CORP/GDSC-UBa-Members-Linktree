# Justification Scientifique de la Limite de Performance sur Grid'5000

Ce document explique pourquoi le RPS plafonne (RPSmax) sans pour autant saturer le CPU (100%) ou la Bande Passante (10Gbps).

---

## 1. La Loi de Little : La Preuve Mathématique

La limite de votre système n'est pas une limite de **ressource brute** (CPU), mais une limite de **concurrence**.

**Loi de Little :**  $$L = \lambda \times W$$
*   **L** (Concurrency) : Nombre de requêtes en cours dans le système (équivalent au nombre de threads Tomcat actifs).
*   **$\lambda$** (Throughput) : Le débit de requêtes par seconde (RPS).
*   **W** (Latency) : Le temps de réponse moyen (Latence).

### Pourquoi le CPU reste en "Idle" ?
Si votre latence (**W**) augmente (ex: 15 secondes) alors que votre nombre de threads (**L**) est fixe (ex: 500 threads) :
$$\lambda = L / W = 500 / 15 = 33 \text{ requêtes/sec par lot}$$

À ce stade, vos threads passent **99% de leur temps à attendre** et seulement **1% à travailler**.
*   Pendant l'attente (Waiting/Stalled), le CPU ne fait rien : il est en **IDLE**.
*   Le RPSmax est atteint car tous les threads sont occupés à attendre. Le système ne peut plus accepter de nouvelles requêtes, même s'il reste du CPU disponible.

---

## 2. Les 3 Goulots d'Étranglement "Invisibles"

### A. La Dépendance au Backend (M3)
L'Intermédiaire (M2) est un proxy. Il ne peut pas finir de traiter la requête tant que le Backend (M3) n'a pas renvoyé les données.
*   Si le réseau M2-M3 est lent ou si le Backend prend du temps à répondre, le thread sur M2 est **bloqué**.
*   **Preuve scientifique** : Si vous saturez M3, M2 restera toujours en idle.

### B. Le "Context Switching" (Surcharge du Noyau)
À très haut RPS ou très haute concurrence (`-c 1000`), le noyau Linux passe son temps à décider quel thread doit tourner.
*   Ce temps est visible dans `%sys` (système) et non dans `%usr` (utilisateur).
*   Si `%sys` est élevé mais que le CPU n'atteint pas 100%, c'est que les threads se battent pour les mêmes ressources (locks), créant des micro-pauses de CPU.

### C. La Limite de la File d'Attente (TCP Backlog)
Si le débit de requêtes arrivant du Client est plus rapide que la capacité de Tomcat à les "sortir" de la file d'attente système, le noyau rejette les paquets.
*   Le CPU de M2 ne monte pas car le travail n'arrive même pas jusqu'à l'application Tomcat.

---

## 3. Comment "Prouver" cet état d'attente ?

Sur l'Intermédiaire (M2), pendant que le test tourne avec une latence élevée :

### 1. Voir l'état des threads Tomcat
```bash
# Identifier le PID de Tomcat
PID=$(jcmd | grep Bootstrap | awk '{print $1}')
# Voir ce que font les threads
jstack $PID | grep "java.lang.Thread.State" | sort | uniq -c
```
*   **Résultat attendu** : Vous verrez des centaines de threads en état `TIMED_WAITING` ou `BLOCKED`. Cela prouve que le goulot est logiciel (attente) et non matériel.

### 2. Voir les files d'attente réseau
```bash
netstat -st | grep -i "overflowed"
```
*   Si les compteurs augmentent, les requêtes sont jetées à la porte du serveur, expliquant pourquoi le CPU ne travaille pas.

---

## Conclusion pour votre Rapport
"Le RPSmax observé sur Grid'5000 n'est pas limité par la puissance de calcul brute (CPU) mais par la **capacité de parallélisme synchrone**. En raison de la latence induite par le backend et le réseau, le pool de threads Tomcat est saturé par des requêtes en attente d'E/S (I/O Wait). Conformément à la Loi de Little, le débit est bridé par le ratio Concurrence/Latence bien avant l'épuisement des cycles CPU."
