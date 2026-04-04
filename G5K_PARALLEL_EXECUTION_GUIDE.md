# Guide : Exécution Parallèle des Benchmarks sur Grid'5000

Pour gagner du temps, vous pouvez lancer les modes `motivation`, `odb_test` et `random_table` simultanément sur des réservations différentes. Tous les résultats seront centralisés dans le même répertoire `~/mesures`.

## 1. Principe
Chaque mode de test écrit dans son propre fichier CSV (`results_motivation.csv`, `results_odb.csv`, etc.). Comme ces fichiers sont distincts, il n'y a pas de conflit d'écriture.

**Règle absolue** : Vous devez utiliser un groupe de 4 machines **différent** pour chaque instance lancée.

## 2. Préparation des configurations
Créez 3 fichiers JSON dans `~/mesures` pour définir vos 3 topologies.

### `topo_motivation.json`
```json
{
    "client": {"ip": "172.16.x.1"},
    "lb": {"ip": "172.16.x.2"},
    "intermediate": {"ip": "172.16.x.3", "hostname": "dahu-3"},
    "backend": {"ip": "172.16.x.4", "hostname": "dahu-4"}
}
```

### `topo_odb.json`
```json
{
    "client": {"ip": "172.16.y.1"},
    "lb": {"ip": "172.16.y.2"},
    "intermediate": {"ip": "172.16.y.3", "hostname": "dahu-y3"},
    "backend": {"ip": "172.16.y.4", "hostname": "dahu-y4"}
}
```

... et ainsi de suite pour `topo_random.json`.

## 3. Lancement Simultané
Ouvrez 3 terminaux sur votre machine de front-end ou utilisez `screen`/`tmux`.

**Terminal 1 (Motivation) :**
```bash
python3 run_benchmark_auto.py --mode motivation --config topo_motivation.json
```

**Terminal 2 (ODB) :**
```bash
python3 run_benchmark_auto.py --mode odb_test --config topo_odb.json
```

**Terminal 3 (Random Table) :**
```bash
python3 run_benchmark_auto.py --mode random_table --config topo_random.json
```

## 4. Résultats par Mode

| Mode | Fichiers générés / mis à jour | Graphes générés |
| :--- | :--- | :--- |
| **motivation** | `results_motivation.csv` | `graph_motivation_combined.png` |
| **odb_test** | `results_odb.csv` | (Attend les données motivation pour les comparaisons) |
| **random_table** | `results_random_table.csv` | (Attend les autres pour la synthèse) |

## 5. Génération finale des rapports
Une fois que les 3 terminaux ont terminé, vous pouvez forcer la génération de tous les graphes de comparaison (Bypass proof, Efficiency, Latency Common) en lançant :

```bash
python3 run_benchmark_auto.py --mode report
```

Cette commande lira tous les CSV accumulés et produira les 5 graphiques finaux et le CSV de comparaison synthétique.
