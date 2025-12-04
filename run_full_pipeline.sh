#!/bin/bash
set -e
set -o pipefail

# ==============================================================================
# SCRIPT MAÎTRE POUR L'EXÉCUTION COMPLÈTE DU PIPELINE DE BENCHMARK
# Usage: ./run_full_pipeline.sh
# ==============================================================================

echo "--- Étape 1: Lancement du script de déploiement de l'environnement ---"
# Rendre le script de déploiement exécutable s'il ne l'est pas
chmod +x setup_g5k.sh
./setup_g5k.sh

# Le script de déploiement a mis à jour user_config.py avec la topologie.
# Nous pouvons maintenant lire ce fichier pour obtenir l'IP du client.

echo -e "\n--- Étape 2: Lancement automatique des scénarios de benchmark ---"

# Fonction pour parser les variables depuis le fichier de conf Python
get_config_value() {
    # Cette fonction est un peu plus complexe pour extraire les valeurs des sous-dictionnaires
    grep -A 3 "$1" user_config.py | grep "$2" | cut -d'"' -f2
}

CLIENT_NODE=$(get_config_value "client_host" "hostname")
REMOTE_PROJECT_NAME=$(grep "^REMOTE_PROJECT_NAME" user_config.py | cut -d'"' -f2)

if [ -z "$CLIENT_NODE" ]; then
    echo "ERREUR: Impossible de récupérer le nom du nœud client depuis user_config.py."
    exit 1
fi

echo "Le nœud client est : $CLIENT_NODE"
echo "Lancement des 3 scénarios de benchmark sur le nœud client..."

SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
ssh $SSH_OPTS "root@$CLIENT_NODE" /bin/bash <<EOF
set -e
echo "--- Connecté à \$HOSTNAME. Lancement des benchmarks ---"

cd "/root/$REMOTE_PROJECT_NAME"

echo -e "\n--- Lancement du scénario 'motivation' ---"
python3 run_benchmark.py --mode motivation

echo -e "\n--- Lancement du scénario 'random_table' ---"
python3 run_benchmark.py --mode random_table

echo -e "\n--- Lancement du scénario 'latency' ---"
python3 run_benchmark.py --mode latency

echo "--- Tous les scénarios de benchmark sont terminés. ---"
EOF

echo -e "\n--- PIPELINE COMPLET TERMINÉ ---"
echo "Tous les résultats (fichiers .csv, graphiques, rapports) ont été générés dans le dossier '$REMOTE_PROJECT_NAME' sur le nœud client ($CLIENT_NODE)."
echo "Vous pouvez les récupérer en utilisant scp. Exemple :"
echo "scp -r root@$CLIENT_NODE:/root/$REMOTE_PROJECT_NAME/plots ."
echo "scp -r root@$CLIENT_NODE:/root/$REMOTE_PROJECT_NAME/results_*.csv ."
echo "N'oubliez pas de libérer vos ressources Grid'5000."
