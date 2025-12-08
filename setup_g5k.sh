#!/bin/bash
set -e
set -o pipefail

# ==============================================================================
# SCRIPT DE DÉPLOIEMENT UNIQUE POUR GRID'5000
# Usage: ./setup_g5k.sh
# ==============================================================================

# --- 1. Chargement de la Configuration ---
CONFIG_FILE="user_config.py"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERREUR : Le fichier de configuration '$CONFIG_FILE' est introuvable."
    exit 1
fi

get_config_value() {
    grep "^$1" "$CONFIG_FILE" | cut -d'"' -f2
}

# --- Grid'5000 & Projet ---
G5K_USER=$(get_config_value "G5K_USER")
G5K_SITE=$(get_config_value "G5K_SITE")
WALLTIME=$(get_config_value "WALLTIME")
G5K_ENVIRONMENT=$(get_config_value "G5K_ENVIRONMENT")
REMOTE_PROJECT_NAME=$(get_config_value "REMOTE_PROJECT_NAME")

# --- VM ---
VM_NAME=$(get_config_value "VM_NAME")
VM_DISK_SIZE=$(get_config_value "VM_DISK_SIZE")
VM_RAM_MB=$(get_config_value "VM_RAM_MB")
VM_VCPUS=$(get_config_value "VM_VCPUS")
VM_BASE_IMAGE_PATH=$(get_config_value "VM_BASE_IMAGE_PATH")

echo "Configuration chargée depuis $CONFIG_FILE."
mkdir -p logs

# --- 2. Réservation des Nœuds ---
echo -e "\n--- Réservation de 3 nœuds sur le site $G5K_SITE pour $WALLTIME ---"
OARSUB_CMD="oarsub -I -l \"slash_22=1,virtual='YES'\"+nodes=2,walltime=$WALLTIME -t deploy"
JOB_INFO=$(ssh "$G5K_USER@access.grid5000.fr" "ssh $G5K_SITE \"$OARSUB_CMD\"")
JOB_ID=$(echo "$JOB_INFO" | grep 'OAR_JOB_ID' | cut -d'=' -f2)

if [ -z "$JOB_ID" ]; then
    echo "ERREUR : La réservation de nœuds a échoué."
    exit 1
fi
echo "Job OAR $JOB_ID soumis. Récupération des noms de nœuds..."
sleep 5
NODES=$(oarstat -f -j "$JOB_ID" | grep "assigned_network_address" | cut -d'=' -f2)

mapfile -t NODE_LIST < <(echo "$NODES" | tr ' ' '\n')
VM_HOST=${NODE_LIST[0]}
CLIENT_NODE=${NODE_LIST[1]}
BACKEND_NODE=${NODE_LIST[2]}

echo "Nœuds réservés : VM_HOST=$VM_HOST, CLIENT=$CLIENT_NODE, BACKEND=$BACKEND_NODE"

# --- 3. Déploiement de l'Environnement ---
echo -e "\n--- Déploiement de '$G5K_ENVIRONMENT' sur les nœuds ---"
kadeploy3 -f <(echo "$NODES") -e "$G5K_ENVIRONMENT" -k ~/.ssh/id_rsa.pub
echo "Déploiement terminé."

# --- 4. Configuration et Déploiement ---
SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"

run_on() {
    local node=$1
    shift
    echo "[$node] Exécution: $@"
    ssh $SSH_OPTS "root@$node" "$@"
}

# --- 4.1 Copie du projet ---
echo -e "\n--- Copie du projet '$REMOTE_PROJECT_NAME' sur tous les nœuds ---"
for node in $VM_HOST $CLIENT_NODE $BACKEND_NODE; do
    rsync -az -e "ssh $SSH_OPTS" --exclude='.git/' --exclude='__pycache__/' --exclude='*.log' ./ "root@$node:/root/$REMOTE_PROJECT_NAME"
done

# --- 4.2 Configuration du Client ---
run_on $CLIENT_NODE "apt-get update && apt-get install -y sshpass build-essential"
run_on $CLIENT_NODE "cd /root/$REMOTE_PROJECT_NAME/wrk2 && make"

# --- 4.3 Réservation de l'adresse MAC sur le VM_HOST ---
echo -e "\n--- Réservation de l'adresse MAC pour la VM sur $VM_HOST ---"
VM_MAC_ADDRESS=$(run_on $VM_HOST "g5k-subnets -im" | awk '{print $2}')
if [ -z "$VM_MAC_ADDRESS" ]; then
    echo "ERREUR : Impossible de réserver une adresse MAC sur le nœud hôte."
    exit 1
fi
echo "Adresse MAC réservée : $VM_MAC_ADDRESS"

# --- 4.4 Création de la VM ---
echo -e "\n--- Lancement du script de création de la VM sur l'hôte $VM_HOST ---"
run_on $VM_HOST /bin/bash <<EOF
set -e
echo "--- Début du script de création de VM sur \$HOSTNAME ---"
apt-get update && apt-get install -y qemu-kvm libvirt-daemon-system libvirt-clients virtinst genisoimage
adduser \$(whoami) libvirt
virsh net-autostart default && virsh net-start default
echo "Nettoyage des anciennes VMs..."
virsh destroy "$VM_NAME" 2>/dev/null || true
virsh undefine "$VM_NAME" 2>/dev/null || true
rm -f "/tmp/$VM_NAME.qcow2" "/tmp/cloud-init-data.iso" && rm -rf /tmp/cloud-init-data
echo "Clonage de l'image de base $VM_BASE_IMAGE_PATH..."
BASE_IMAGE_FILENAME=\$(basename "$VM_BASE_IMAGE_PATH")
cp "$VM_BASE_IMAGE_PATH" "/tmp/"
echo "Création du nouveau disque de ${VM_DISK_SIZE}..."
qemu-img create -f qcow2 -o backing_file="/tmp/\$BASE_IMAGE_FILENAME" "/tmp/$VM_NAME.qcow2" "$VM_DISK_SIZE"
echo "Préparation de la configuration Cloud-Init..."
mkdir -p /tmp/cloud-init-data
SSH_KEY=\$(cat /root/.ssh/id_rsa.pub)
cat <<'EOT_USERDATA' > /tmp/cloud-init-data/user-data
#cloud-config
users:
- name: root
  ssh_authorized_keys:
  - __SSH_KEY_PLACEHOLDER__
  sudo: ['ALL=(ALL) NOPASSWD:ALL']
ssh_pwauth: true
chpasswd: { expire: False }
password: grid5000
write_files:
- path: /opt/resize_disk.sh
  permissions: '0755'
  content: |
    #!/bin/bash
    exec > /var/log/resize_disk_output.log 2>&1
    echo "--- Début du redimensionnement du disque LVM ---"
    growpart /dev/vda 3 &> /dev/null || growpart /dev/vda 1 &> /dev/null
    pvresize /dev/vda3 &> /dev/null || pvresize /dev/vda1 &> /dev/null
    lvextend -l +100%FREE /dev/mapper/ubuntu--vg-ubuntu--lv
    resize2fs /dev/mapper/ubuntu--vg-ubuntu--lv
    echo "--- Redimensionnement terminé. Auto-destruction du service. ---"
    systemctl disable resize-disk.service
    rm /etc/systemd/system/resize-disk.service
    rm /opt/resize_disk.sh
runcmd:
- sed -i 's/^#?PermitRootLogin .*/PermitRootLogin yes/' /etc/ssh/sshd_config
- systemctl restart ssh
- apt-get update && apt-get install -y sysstat openjdk-17-jre cloud-guest-utils lvm2
- |
  cat <<'EOT_INNER' > /etc/systemd/system/resize-disk.service
  [Unit]
  Description=Resize LVM to fill disk on first boot
  After=network.target
  [Service]
  Type=oneshot
  ExecStart=/opt/resize_disk.sh
  [Install]
  WantedBy=multi-user.target
EOT_INNER
- systemctl daemon-reload
- systemctl enable resize-disk.service
EOT_USERDATA
sed -i "s|__SSH_KEY_PLACEHOLDER__|\$SSH_KEY|" /tmp/cloud-init-data/user-data
touch /tmp/cloud-init-data/meta-data
genisoimage -output /tmp/cloud-init-data.iso -volid cidata -joliet -rock /tmp/cloud-init-data/
echo "Lancement de la VM avec virt-install..."
virt-install --name "$VM_NAME" --ram "$VM_RAM_MB" --vcpus "$VM_VCPUS" \\
  --disk path="/tmp/$VM_NAME.qcow2",device=disk,bus=virtio \\
  --disk path="/tmp/cloud-init-data.iso",device=cdrom \\
  --os-variant ubuntu22.04 --network bridge=br0,mac="$VM_MAC_ADDRESS" \\
  --graphics none --noautoconsole --import
echo "--- Fin du script de création de VM ---"
EOF

# --- 4.4 Finalisation de la Configuration et Lancement des Services ---
echo -e "\n--- Finalisation de la configuration ---"

echo "Attente de la disponibilité de la VM..."
VM_IP=""
for i in {1..20}; do
    VM_IP=$(run_on $VM_HOST "arp -n | grep -i '$VM_MAC_ADDRESS' | awk '{print \$1}'" || true)
    if [ -n "$VM_IP" ]; then break; fi
    echo "Tentative $i/20: IP de la VM non encore trouvée, nouvelle tentative dans 10s..."
    sleep 10
done
if [ -z "$VM_IP" ]; then echo "ERREUR: Impossible de trouver l'IP de la VM." >&2; exit 1; fi
echo "IP de la VM détectée : $VM_IP"

echo "Attente de la disponibilité SSH sur la VM..."
for i in {1..20}; do
    if sshpass -p 'grid5000' ssh $SSH_OPTS -o ConnectTimeout=5 "root@$VM_IP" echo "SSH OK" &>/dev/null; then break; fi
    echo "Tentative $i/20 : Le service SSH de la VM n'est pas encore prêt, nouvelle tentative dans 10s..."
    sleep 10
done
ssh-keygen -f "/root/.ssh/known_hosts" -R "$VM_IP" 2>/dev/null || true

echo "Copie du projet '$REMOTE_PROJECT_NAME' dans la VM..."
sshpass -p 'grid5000' rsync -az -e "ssh $SSH_OPTS" "root@$VM_HOST:/root/$REMOTE_PROJECT_NAME/" "root@$VM_IP:/root/$REMOTE_PROJECT_NAME/"

echo "Démarrage de Tomcat sur la VM (M2)..."
sshpass -p 'grid5000' ssh $SSH_OPTS "root@$VM_IP" "cd /root/$REMOTE_PROJECT_NAME && ./apache-tomcat-11.0.1/bin/startup.sh"

echo "Démarrage de Tomcat sur le serveur backend (M3)..."
run_on $BACKEND_NODE "apt-get update && apt-get install -y openjdk-17-jre"
run_on $BACKEND_NODE "cd /root/$REMOTE_PROJECT_NAME && ./apache-tomcat-11.0.1/bin/startup.sh"

# --- 5. Mise à jour du fichier de configuration ---
CLIENT_IP=$(run_on $CLIENT_NODE "hostname -i")
BACKEND_IP=$(run_on $BACKEND_NODE "hostname -i")

echo "Mise à jour de $CONFIG_FILE avec la topologie..."
sed -i '/^TOPOLOGY = {/,/}/d' "$CONFIG_FILE"
cat <<EOF >> "$CONFIG_FILE"

# ==============================================================================
# SECTION CI-DESSOUS GÉNÉRÉE AUTOMATIQUEMENT PAR setup_g5k.sh
# NE PAS MODIFIER MANUELLEMENT
# ==============================================================================
TOPOLOGY = {
    "client_host": {"hostname": "$CLIENT_NODE", "ip": "$CLIENT_IP"},
    "intermediate_vm": {"vm_name": "$VM_NAME", "ip": "$VM_IP", "user": "root", "password": "grid5000"},
    "backend_server": {"hostname": "$BACKEND_NODE", "ip": "$BACKEND_IP"}
}
EOF
echo "Le fichier '$CONFIG_FILE' a été mis à jour."

echo -e "\n--- DÉPLOIEMENT TERMINÉ ---"
echo "Job ID: $JOB_ID. Pour libérer les ressources : oardel $JOB_ID"
