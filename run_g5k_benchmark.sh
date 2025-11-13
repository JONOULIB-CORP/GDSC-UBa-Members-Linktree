#!/bin/bash

# ==============================================================================
# SCRIPT D'AUTOMATISATION DES MESURES DE PERFORMANCE ODB SUR GRID'5000 (v2)
#
# Auteur: Jules, Ingénieur Logiciel
# Version: 2.0 (100% Automatisé avec Cloud Image)
#
# Description:
# Ce script automatise entièrement le processus d'évaluation. Il utilise une
# image Cloud Ubuntu et cloud-init pour provisionner la VM sans aucune
# intervention manuelle.
#
# ==============================================================================

set -e # Quitte immédiatement si une commande échoue
# set -x # Décommenter pour un mode de débogage verbeux

# --- --------------------------------------------------------------------- ---
# ---                           CONFIGURATION                               ---
# --- --------------------------------------------------------------------- ---

# Informations Grid'5000
G5K_USER="mteumou"
G5K_SITE="grenoble"
G5K_FRONTEND="access.grid5000.fr"
G5K_WALLTIME="1:30:00" # Réduit car l'installation est plus rapide

# Configuration du projet
PROJECT_REPO="https://github.com/vignol/mesures.git"
PROJECT_DIR_NAME="mesures"
REMOTE_BASE_DIR="/home/${G5K_USER}"

# Image Cloud Ubuntu (LTS - Jammy Jellyfish)
CLOUD_IMAGE_URL="https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img"
CLOUD_IMAGE_NAME="jammy-server-cloudimg-amd64.img"

# Configuration cloud-init
CLOUD_INIT_USER_DATA_FILE="user-data"

# Spécifications de la VM
VM_NAME="odb-vm"
VM_CORES=4
VM_RAM_MB=2048
VM_DISK_GB=15
VM_OS_VARIANT="ubuntu22.04"
VM_USER="odb" # Défini dans le fichier user-data
VM_PASS="odb" # Défini dans le fichier user-data

# Paramètres du Benchmark
WRK_THREADS=10
WRK_CONNECTIONS=300
WRK_DURATION="60s"
WRK_RATE=1000
WRK_TIMEOUT="10s"
IMAGES=("large.jpg" "small.jpg" "tiny.jpg" "zero.jpg")
WAR_FILES=("serv" "serv1")

# --- --------------------------------------------------------------------- ---
# ---                           FONCTIONS UTILITAIRES                       ---
# --- --------------------------------------------------------------------- ---

log_info() { echo -e "\n\e[1;34m[INFO] $1\e[0m"; }
log_error() { echo -e "\n\e[1;31m[ERREUR] $1\e[0m"; }

# Exécute une commande sur le frontend G5K
ssh_frontend() { ssh -t -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "${G5K_USER}@${G5K_FRONTEND}" "$@"; }
# Exécute une commande sur un noeud G5K
ssh_node() { ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "root@$1" "$@"; }
# Exécute une commande sur la VM
ssh_vm() { sshpass -p "${VM_PASS}" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "${VM_USER}@$1" "$@"; }

# --- --------------------------------------------------------------------- ---
# ---                           SCRIPT PRINCIPAL                            ---
# --- --------------------------------------------------------------------- ---

# --- ÉTAPE 1: Préparation Locale ---
log_info "Étape 1/10: Préparation locale"

# Clonage du dépôt
if [ ! -d "$PROJECT_DIR_NAME" ]; then
    log_info "Clonage du dépôt '${PROJECT_REPO}'"
    git clone "$PROJECT_REPO"
fi

# Téléchargement de l'image Cloud
if [ ! -f "$CLOUD_IMAGE_NAME" ]; then
    log_info "Téléchargement de l'image Cloud Ubuntu..."
    wget -O "$CLOUD_IMAGE_NAME" "$CLOUD_IMAGE_URL"
fi

# Vérification du fichier user-data
if [ ! -f "$CLOUD_INIT_USER_DATA_FILE" ]; then
    log_error "Le fichier de configuration cloud-init '${CLOUD_INIT_USER_DATA_FILE}' est introuvable."
    exit 1
fi

# --- ÉTAPE 2: Téléversement vers Grid'5000 ---
log_info "Étape 2/10: Téléversement des fichiers vers ${G5K_SITE}"
ssh_frontend "ssh ${G5K_SITE} 'mkdir -p ${REMOTE_BASE_DIR}'"
scp -r "./${PROJECT_DIR_NAME}" "$CLOUD_IMAGE_NAME" "$CLOUD_INIT_USER_DATA_FILE" "${G5K_USER}@${G5K_FRONTEND}:${G5K_SITE}/"

# --- ÉTAPE 3: Réservation et Déploiement sur les Nœuds ---
log_info "Étape 3/10: Réservation des 3 nœuds sur Grid'5000"
OAR_JOB_ID=$(ssh_frontend "ssh ${G5K_SITE} 'oarsub -I -l nodes=3,walltime=${G5K_WALLTIME}' | grep OAR_JOB_ID | cut -d'=' -f2")

if [ -z "$OAR_JOB_ID" ]; then
    log_error "La réservation a échoué." && exit 1
fi

ssh_frontend "ssh ${G5K_SITE} 'oarwait ${OAR_JOB_ID}'" > /dev/null 2>&1

NODES_STR=$(ssh_frontend "ssh ${G5K_SITE} 'uniq \$OAR_NODEFILE'")
read -r -a NODES <<< "$NODES_STR"
M1=${NODES[0]}
M2=${NODES[1]}
M3=${NODES[2]}

log_info "Nœuds réservés (Job ID: ${OAR_JOB_ID}): M1=${M1}, M2=${M2}, M3=${M3}"
log_info "Déploiement de Debian 11 sur les nœuds..."
ssh_frontend "ssh ${G5K_SITE} 'kadeploy3 -f \$OAR_NODEFILE -e debian11-x64-std -k'"

# --- ÉTAPE 4: Configuration des Nœuds ---
log_info "Étape 4/10: Configuration des nœuds M1, M2 et M3"

(
    log_info "[M1] Installation des dépendances et compilation de wrk2"
    ssh_node "${M1}" "apt-get update && apt-get install -y build-essential default-jdk git && cd ${PROJECT_DIR_NAME}/wrk2 && make"
) &
(
    log_info "[M3] Installation de Java et démarrage de Tomcat"
    ssh_node "${M3}" "apt-get update && apt-get install -y default-jdk"
    ssh_node "${M3}" "source /etc/profile; ./${PROJECT_DIR_NAME}/apache-tomcat-11.0.1/bin/startup.sh"
) &
(
    log_info "[M2] Installation de KVM et configuration du réseau"
    ssh_node "${M2}" "apt-get update && apt-get install -y qemu-kvm libvirt-daemon-system virtinst bridge-utils cloud-image-utils"
    IFACE=$(ssh_node "${M2}" "ip -o -4 route show to default | awk '{print \$5}'")
    ssh_node "${M2}" "
        systemctl stop networking.service
        cat > /etc/network/interfaces << EOF
source /etc/network/interfaces.d/*
auto lo
iface lo inet loopback
auto ${IFACE}
iface ${IFACE} inet manual
auto br0
iface br0 inet dhcp
    bridge_ports ${IFACE}
EOF
        systemctl start networking.service
    "
) &
wait
log_info "Configuration des nœuds terminée."

# --- ÉTAPE 5: Création et Démarrage de la VM ---
log_info "Étape 5/10: Création de la VM sur M2 via cloud-init"
ssh_node "${M2}" "
    # Créer un disque pour la VM basé sur l'image cloud
    qemu-img create -f qcow2 -b ${CLOUD_IMAGE_NAME} /var/lib/libvirt/images/${VM_NAME}.qcow2 ${VM_DISK_GB}G

    # Créer une ISO cloud-init avec les meta-data et user-data
    genisoimage -output /var/lib/libvirt/images/cloud-init.iso -V cidata -r -J \
        -meta-data <(echo \"instance-id: ${VM_NAME}; local-hostname: ${VM_NAME}\") \
        ${CLOUD_INIT_USER_DATA_FILE}

    # Lancer la VM
    virt-install \\
        --name ${VM_NAME} \\
        --ram ${VM_RAM_MB} \\
        --vcpus ${VM_CORES} \\
        --os-variant ${VM_OS_VARIANT} \\
        --disk path=/var/lib/libvirt/images/${VM_NAME}.qcow2,device=disk \\
        --disk path=/var/lib/libvirt/images/cloud-init.iso,device=cdrom \\
        --import \\
        --network bridge=br0 \\
        --noautoconsole
"

log_info "Attente du démarrage et de la configuration de la VM par cloud-init... (peut prendre 2-3 minutes)"
# Boucle pour récupérer l'IP de la VM depuis le bail DHCP de libvirt
VM_IP=""
while [ -z "$VM_IP" ]; do
    sleep 10
    VM_IP=$(ssh_node "${M2}" "virsh domifaddr ${VM_NAME}" | awk '/ipv4/ {print $4}' | cut -d'/' -f1)
done
log_info "VM démarrée et configurée ! IP: ${VM_IP}"
# Attente supplémentaire pour que les services (ssh, tomcat) soient prêts
sleep 45

# --- ÉTAPE 6: Boucle de Tests ---
log_info "Étape 6/10: Démarrage de la boucle de tests"
RESULTS_DIR="results_$(date +%F_%H-%M-%S)"
mkdir -p "$RESULTS_DIR"

for war in "${WAR_FILES[@]}"; do
    for image in "${IMAGES[@]}"; do
        CURRENT_TEST_NAME="${war}_${image/\.jpg/}"
        log_info "--- Test en cours: ${CURRENT_TEST_NAME} ---"

        # 1. Déploiement du WAR sur M2(VM) et M3
        log_info "  - Déploiement de ${war}.war"
        ssh_node "${M3}" "rm -f ./${PROJECT_DIR_NAME}/apache-tomcat-11.0.1/webapps/serv* && cp ./${PROJECT_DIR_NAME}/${war}.war ./${PROJECT_DIR_NAME}/apache-tomcat-11.0.1/webapps/serv.war"
        ssh_vm "${VM_IP}" "rm -f ./${PROJECT_DIR_NAME}/apache-tomcat-11.0.1/webapps/serv* && cp ./${PROJECT_DIR_NAME}/${war}.war ./${PROJECT_DIR_NAME}/apache-tomcat-11.0.1/webapps/serv.war"

        # 2. Redémarrage de Tomcat
        log_info "  - Redémarrage des serveurs Tomcat"
        ssh_node "${M3}" "source /etc/profile; ./${PROJECT_DIR_NAME}/apache-tomcat-11.0.1/bin/shutdown.sh; ./${PROJECT_DIR_NAME}/apache-tomcat-11.0.1/bin/startup.sh" &
        ssh_vm "${VM_IP}" "source /etc/profile; ./${PROJECT_DIR_NAME}/apache-tomcat-11.0.1/bin/shutdown.sh; ./${PROJECT_DIR_NAME}/apache-tomcat-11.0.1/bin/startup.sh" &
        wait
        log_info "  - Attente de 15s pour le démarrage de Tomcat..."
        sleep 15

        # 3. Lancement de cpu_logger sur M2 (Hôte) pour surveiller la VM
        CPU_LOG_FILE="cpu_log_${CURRENT_TEST_NAME}.csv"
        log_info "  - Lancement de cpu_logger sur M2"
        ssh_node "${M2}" "cd ${PROJECT_DIR_NAME} && ./cpu_logger.sh ${CPU_LOG_FILE} 1" &
        CPU_LOGGER_PID=$!

        # 4. Lancement de wrk2 depuis M1
        WRK_LOG_FILE="wrk_log_${CURRENT_TEST_NAME}.txt"
        WRK_URL="http://${VM_IP}:8080/serv/Serv?machine=${M3}&image=${image}"
        log_info "  - Lancement de wrk2 depuis M1 sur ${WRK_URL}"
        ssh_node "${M1}" "cd ${PROJECT_DIR_NAME}/wrk2 && ./wrk -t${WRK_THREADS} -c${WRK_CONNECTIONS} -d${WRK_DURATION} -R${WRK_RATE} --timeout ${WRK_TIMEOUT} --latency '${WRK_URL}'" > "./${RESULTS_DIR}/${WRK_LOG_FILE}"

        # 5. Arrêt de cpu_logger
        log_info "  - Arrêt de cpu_logger"
        ssh_node "${M2}" "killall cpu_logger.sh"

        # 6. Collecte des logs CPU
        log_info "  - Collecte des logs CPU"
        scp "root@${M2}:~/${PROJECT_DIR_NAME}/${CPU_LOG_FILE}" "./${RESULTS_DIR}/"
    done
done

# --- ÉTAPE 7: Génération du Rapport ---
log_info "Étape 7/10: Génération du rapport de synthèse"
REPORT_FILE="./${RESULTS_DIR}/rapport_synthese.md"

# Initialisation du fichier rapport
{
    echo "# Rapport de Synthèse des Performances ODB"
    echo ""
    echo "## 1. Résultats Bruts"
    echo ""
    echo "| Image      | Scénario | RPS Moyen | CPU Moyen (%) | CPU Écart-type (%) |"
    echo "|:-----------|:---------|:----------|:--------------|:-------------------|"
} > "${REPORT_FILE}"

# Script AWK pour traiter tous les logs, calculer les statistiques et générer le rapport.
# Cette approche est plus performante et robuste qu'une boucle en Bash.
gawk '
# Fonction pour calculer la moyenne et l écart-type d un fichier CSV
function calculate_stats(file,    data, n, sum, sum_sq, values, val, mean, stdev) {
    n = 0; sum = 0; sum_sq = 0;
    # On saute l en-tête avec getline
    getline data < file;
    while ((getline data < file) > 0) {
        split(data, values, ";");
        val = values[2];
        n++;
        sum += val;
        sum_sq += val*val;
    }
    close(file);
    if (n > 0) {
        mean = sum / n;
        stdev = sqrt(sum_sq/n - mean*mean);
        return sprintf("%.2f;%.2f", mean, stdev);
    }
    return "N/A;N/A";
}
BEGIN {
    # Définition des tableaux pour stocker les résultats
    split("large small tiny zero", images, " ");
}
# Traitement des fichiers de log wrk
FNR==1 {
    # Extraire le scénario et l image du nom de fichier
    split(FILENAME, parts, "_");
    war = parts[2];
    image_base = parts[3];
    sub(/\.txt$/, "", image_base);
    current_key = war"_"image_base;
}
/Requests\/sec:/ {
    # Extraire le RPS
    rps[current_key] = $2;
}
# Logique de fin: une fois tous les fichiers traités
END {
    # Itérer sur les images dans un ordre défini pour un rapport cohérent
    for (i in images) {
        image = images[i];

        # Clés pour les scénarios standard et ODB
        key_std = "serv_"image;
        key_odb = "serv1_"image;

        # Calculer les stats CPU pour les deux scénarios
        stats_std_str = calculate_stats("'"${RESULTS_DIR}"'/cpu_log_" key_std ".csv");
        split(stats_std_str, stats_std, ";");
        cpu_mean_std = stats_std[1];
        cpu_stdev_std = stats_std[2];

        stats_odb_str = calculate_stats("'"${RESULTS_DIR}"'/cpu_log_" key_odb ".csv");
        split(stats_odb_str, stats_odb, ";");
        cpu_mean_odb = stats_odb[1];
        cpu_stdev_odb = stats_odb[2];

        # Stocker pour la synthèse
        cpu_std_map[image] = cpu_mean_std;
        cpu_odb_map[image] = cpu_mean_odb;

        # Imprimer les lignes du tableau de résultats bruts
        printf("| %-10s | %-8s | %-9s | %-13s | %-18s |\n", image ".jpg", "serv", rps[key_std], cpu_mean_std, cpu_stdev_std);
        printf("| %-10s | %-8s | %-9s | %-13s | %-18s |\n", image ".jpg", "serv1", rps[key_odb], cpu_mean_odb, cpu_stdev_odb);
    }

    # Imprimer le tableau de synthèse
    print "\n## 2. Synthèse et Gains\n";
    print "| Image      | CPU Standard (%) | CPU ODB (%) | Gain CPU (%) |";
    print "|:-----------|:-----------------|:------------|:-------------|";
    for (i in images) {
        image = images[i];
        if (image != "zero") {
            cpu_std = cpu_std_map[image];
            cpu_odb = cpu_odb_map[image];
            if (cpu_std > 0) {
                gain = (cpu_std - cpu_odb) / cpu_std * 100;
                printf("| %-10s | %-16.2f | %-11.2f | **%+.2f%%**   |\n", image ".jpg", cpu_std, cpu_odb, gain);
            } else {
                printf("| %-10s | %-16.2f | %-11.2f | N/A          |\n", image ".jpg", cpu_std, cpu_odb);
            }
        }
    }

    print "\n### Analyse du Benchmark (zero.jpg)\n";
    print "Le test avec `zero.jpg` sert de baseline. Il mesure la surcharge de base de chaque servlet. Idéalement, la consommation CPU devrait être minimale et similaire entre `serv` (`" cpu_std_map["zero"] "`%) et `serv1` (`" cpu_odb_map["zero"] "`%), car aucune donnée d image n est traitée.";
}
' ./"${RESULTS_DIR}"/wrk_log_*.txt >> "${REPORT_FILE}"

# --- ÉTAPE 8 & 9: Nettoyage ---
log_info "Étape 8/10: Nettoyage des ressources (VM, Tomcats)"
ssh_node "${M2}" "virsh destroy ${VM_NAME} && virsh undefine ${VM_NAME} --remove-all-storage"
ssh_node "${M3}" "source /etc/profile; ./${PROJECT_DIR_NAME}/apache-tomcat-11.0.1/bin/shutdown.sh"

log_info "Étape 9/10: Libération des nœuds Grid'5000"
ssh_frontend "ssh ${G5K_SITE} 'oardel ${OAR_JOB_ID}'"

# --- ÉTAPE 10: Terminé ---
log_info "Étape 10/10: Terminé!"
echo "Les résultats sont disponibles dans le dossier: ./${RESULTS_DIR}"

exit 0
