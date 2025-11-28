#!/bin/bash
set -e # Stop on any error

# ==============================================================================
# CONFIGURATION
# ==============================================================================
VM_NAME="my-vm"
VM_DISK_SIZE="20G"
VM_RAM_KB="2048000"
VM_VCPUS="4"
BASE_IMAGE_PATH="/grid5000/virt-images/ubuntu2204-x64-min-2025072816.qcow2"
MAC_ADDRESS='00:16:3E:84:00:01'
WORK_DIR="/tmp"
# ==============================================================================

BASE_IMAGE_FILENAME=$(basename "$BASE_IMAGE_PATH")

echo "--- 1. Cleaning up previous VM environment ---"
sudo-g5k virsh destroy "$VM_NAME" 2>/dev/null || true
sudo-g5k virsh undefine "$VM_NAME" 2>/dev/null || true
echo "Cleaning old files from $WORK_DIR..."
rm -f "$WORK_DIR/$VM_NAME.qcow2" "$WORK_DIR/$VM_NAME.xml" "$WORK_DIR/cloud-init-data.iso"
rm -rf "$WORK_DIR/cloud-init-data"

echo "--- 2. Preparing VM disk image ---"
echo "Copying base image to $WORK_DIR..."
cp "$BASE_IMAGE_PATH" "$WORK_DIR/"

echo "Creating new VM disk with size $VM_DISK_SIZE..."
qemu-img create -f qcow2 -o backing_file="$WORK_DIR/$BASE_IMAGE_FILENAME" "$WORK_DIR/$VM_NAME.qcow2" "$VM_DISK_SIZE"

echo "--- 3. Preparing the robust Cloud-Init configuration ---"
cd "$WORK_DIR"
if [ ! -f ~/.ssh/id_rsa.pub ]; then
    echo "ERROR: Public SSH key not found at ~/.ssh/id_rsa.pub. Please create one."
    exit 1
fi

#
# === FINAL ROBUST SOLUTION ===
# We create a self-deleting systemd service that runs a script late in the boot process.
# This avoids any cloud-init timing issues.
#
mkdir -p cloud-init-data
cat <<'EOF' > cloud-init-data/user-data
#cloud-config
users:
- name: root
  ssh_authorized_keys:
  - __SSH_KEY_PLACEHOLDER__
  sudo: ['ALL=(ALL) NOPASSWD:ALL']

# 1. Write the resize script to a file on the VM.
write_files:
- path: /opt/resize_disk.sh
  permissions: '0755'
  content: |
    #!/bin/bash
    # Log everything for easy debugging if needed
    exec > /var/log/resize_disk_output.log 2>&1

    echo "--- Starting disk resize script at $(date) ---"

    # Update apt and install necessary tools
    echo "Updating apt and installing tools..."
    apt-get update
    apt-get install -y lvm2 cloud-guest-utils

    echo "Extending partition /dev/vda, number 3..."
    growpart /dev/vda 3

    echo "Resizing LVM Physical Volume /dev/vda3..."
    pvresize /dev/vda3

    echo "Extending LVM Logical Volume..."
    lvextend -l +100%FREE /dev/mapper/ubuntu--vg-ubuntu--lv

    echo "Resizing filesystem..."
    resize2fs /dev/mapper/ubuntu--vg-ubuntu--lv

    echo "Disk resize complete. Disabling this service."

    # 2. Disable and remove the service and script to ensure it only runs once.
    systemctl disable resize-disk.service
    rm /etc/systemd/system/resize-disk.service
    rm /opt/resize_disk.sh
    echo "--- Service disabled and scripts removed. ---"

# 3. Create a systemd service to run our script on boot.
runcmd:
- |
  cat <<'EOT' > /etc/systemd/system/resize-disk.service
  [Unit]
  Description=Resize disk to fill partition on first boot
  After=network.target

  [Service]
  Type=oneshot
  ExecStart=/opt/resize_disk.sh
  RemainAfterExit=true
  StandardOutput=journal

  [Install]
  WantedBy=multi-user.target
EOT
- systemctl daemon-reload
- systemctl enable resize-disk.service

EOF

# Inject the user's actual SSH key into the placeholder
SSH_KEY=$(cat ~/.ssh/id_rsa.pub)
sed -i "s|__SSH_KEY_PLACEHOLDER__|${SSH_KEY}|" cloud-init-data/user-data

touch cloud-init-data/meta-data

echo "Creating ISO image for cloud-init..."
genisoimage -output cloud-init-data.iso -volid cidata -joliet -rock cloud-init-data/

echo "--- 4. Creating VM definition XML ---"
cat <<EOF > "$WORK_DIR/$VM_NAME.xml"
<domain type='kvm'>
  <name>$VM_NAME</name>
  <memory>$VM_RAM_KB</memory>
  <vcpu>$VM_VCPUS</vcpu>
  <cpu mode='host-model'/>
  <os><type arch="x86_64">hvm</type></os>
  <clock offset="localtime"/>
  <on_poweroff>destroy</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>destroy</on_crash>
  <devices>
    <emulator>/usr/bin/kvm</emulator>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source file='$WORK_DIR/$VM_NAME.qcow2'/>
      <target dev='vda' bus='virtio'/>
    </disk>
    <disk type='file' device='cdrom'>
      <source file='$WORK_DIR/cloud-init-data.iso'/>
      <target dev='hda' bus='ide'/>
      <readonly/>
    </disk>
    <interface type='bridge'>
      <source bridge='br0'/>
      <mac address='$MAC_ADDRESS'/>
    </interface>
    <serial type='pty'><target port='0'/></serial>
    <console type='pty'><target type='serial' port='0'/></console>
  </devices>
</domain>
EOF

echo "--- 5. Defining and starting the VM ---"
sudo-g5k virsh define "$WORK_DIR/$VM_NAME.xml"
sudo-g5k virsh start "$VM_NAME"

echo "--- DONE! ---"
echo "VM '$VM_NAME' created with a $VM_DISK_SIZE disk. It will resize automatically on this first boot."
echo "Please wait 1-2 minutes for the boot and resize process to complete."
echo "You can check the resize log on the VM at /var/log/resize_disk_output.log"
