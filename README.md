# Guide d'Exécution du Pipeline de Benchmark Automatisé sur Grid'5000

Ce projet fournit un pipeline entièrement automatisé pour déployer un environnement complexe sur Grid'5000, exécuter une série de benchmarks de performance, et sauvegarder les résultats.

## Architecture

Le système est conçu pour être à la fois simple et puissant, reposant sur 4 fichiers principaux :

1.  `user_config.py`: Fichier de configuration **unique** où vous définissez tous vos paramètres (login Grid'5000, paramètres de la VM, payloads, etc.).
2.  `setup_g5k.sh`: Script de déploiement qui prépare l'intégralité de l'environnement (réservation de nœuds, création de VM, installations, etc.).
3.  `run_benchmark.py`: Script d'évaluation qui exécute les tests de performance.
4.  `run_full_pipeline.sh`: **Script maître et unique point d'entrée** qui orchestre les deux scripts précédents pour une automatisation complète.

## Workflow en 3 Étapes Simples

### Étape 1 : Configurer `user_config.py`

C'est la **seule chose à faire** avant de lancer une expérience. Ouvrez ce fichier et personnalisez les variables selon vos besoins.

### Étape 2 : Lancer le Pipeline Complet

Exécutez le script maître. Il s'occupera de tout, sans aucune autre intervention manuelle.

```bash
# Rendez le script exécutable (une seule fois)
chmod +x run_full_pipeline.sh

# Lancez le pipeline complet
./run_full_pipeline.sh
```

Le script va :
1.  Lancer `setup_g5k.sh` pour déployer l'environnement.
2.  Attendre que le déploiement soit terminé.
3.  Se connecter au nœud client.
4.  Lancer automatiquement les trois scénarios de benchmark (`motivation`, `random_table`, `latency`).

### Étape 3 : Récupérer vos Résultats

Une fois le pipeline terminé, tous les résultats (fichiers `.csv`, graphiques, rapports) sont stockés dans le répertoire `mesures` sur le **nœud client**.

Le script vous affichera à la fin la commande `scp` à utiliser pour copier ces résultats sur votre machine locale. N'oubliez pas de libérer vos ressources Grid'5000 avec la commande `oardel` qui vous sera également fournie.
