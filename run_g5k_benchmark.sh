#!/bin/bash
#
# =================================================================================
# Script (semi-automatisé) pour les benchmarks ODB sur Grid'5000
# ... (description et configuration inchangées)
# =================================================================================

# ... (toutes les sections et fonctions avant 'deploy_vm_on_m2' sont inchangées)

deploy_vm_on_m2() {
    log "--- Déploiement de la VM sur M2 ---"
    local user_data_file="${LOCAL_TMP_DIR}/user-data"
    local ssh_public_key=$(cat "${HOME}/.ssh/id_rsa.pub")

    # ... (user-data inchangé)

    log "Configuration de M2 pour KVM..."
    # ... (commandes de configuration KVM inchangées)

    scp_g5k "$user_data_file" "m2:/tmp/user-data" || die "Échec du téléversement du user-data."

    log "Lancement de la VM..."
    ssh_g5k m2 "
        sudo-g5k virt-install --name ${VM_NAME} --memory ${VM_MEMORY_MB} --vcpus ${VM_CORES} \
        --disk path=${REMOTE_PROJECT_PATH}/${LOCAL_IMAGE_NAME},size=${VM_DISK_SIZE%.*} \
        --os-variant ubuntu24.04 --network bridge=br0 --graphics none --import --noautoconsole \
        --cloud-init user-data=/tmp/user-data;
    " || die "Échec de la création de la VM."

    log "Attente de la VM..."
    for i in {1..30}; do
        if ssh_g5k -o ConnectTimeout=5 vm "echo ok" &> /dev/null; then log "VM prête."; sleep 10; return 0; fi
        sleep 5
    done
    die "La VM n'a pas pu être contactée."
}

# ... (le reste du script est inchangé)
