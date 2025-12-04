# -*- coding: utf-8 -*-

# ==============================================================================
# FICHIER DE CONFIGURATION UNIQUE POUR L'ENSEMBLE DE L'EXPÉRIENCE
# ==============================================================================
#
# Instructions :
# 1. Ce fichier est le SEUL endroit où vous devez modifier des paramètres.
# 2. Remplissez les variables ci-dessous avec vos informations personnelles
#    et les paramètres spécifiques à votre test.
# 3. Les scripts `setup_g5k_environment.sh` et `run_benchmark2.py` liront
#    automatiquement ce fichier.

# --- Configuration Grid'5000 pour le déploiement ---
# Votre nom d'utilisateur Grid'5000
G5K_USER = "mteumou"

# Le site sur lequel vous voulez lancer l'expérience (ex: "toulouse", "grenoble")
G5K_SITE = "toulouse"

# Durée de la réservation des noeuds (format HH:MM:SS)
WALLTIME = "4:00:00"

# Environnement à déployer sur les noeuds via kadeploy3
G5K_ENVIRONMENT = "debian11-x64-std"


# --- Configuration du Projet ---
# Nom du dossier de votre projet qui sera copié sur les noeuds distants
REMOTE_PROJECT_NAME = "mesures"


# --- Configuration de la Machine Virtuelle (VM) ---
VM_NAME = "my-vm"
VM_DISK_SIZE = "20G"
VM_RAM_MB = "2048"
VM_VCPUS = "4"
VM_BASE_IMAGE_PATH = "/grid5000/virt-images/ubuntu2204-x64-min-2025072816.qcow2"
VM_MAC_ADDRESS = '00:16:3E:90:1C:01'


# --- Configuration de l'Expérience de Benchmark ---

# Dictionnaire des payloads de base (nom_fichier -> taille_en_ko)
# IMPORTANT : Les noms de fichiers ici doivent correspondre EXACTEMENT
# aux noms des fichiers stockés sur le serveur Tomcat.
PAYLOADS = {
    "image_1KB": 1.0,
    "image_10KB": 10.0,
    "image_100KB": 100.0,
    "image_1000KB": 1024.0
}

# Dictionnaire du grand pool d'images (nom_fichier -> taille_en_ko)
# Utilisé pour le scénario de test sur un échantillon aléatoire.
# À REMPLIR AVEC VOS NOMS DE FICHIERS ET LEURS TAILLES EXACTES.
FULL_PAYLOAD_POOL = {
    # Exemple :
    # "photo_v1_24.5k.jpg": 24.5,
    # "archive_102.7k.zip": 102.7,
    # "document.pdf": 512.0,
}
