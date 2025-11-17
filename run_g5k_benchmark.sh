#!/bin/bash
#
# =================================================================================
# Script (semi-automatisé) pour les benchmarks ODB sur Grid'5000
# ... (USAGE inchangé)
# =================================================================================

# --- Configuration Principale ---
# ... (Configuration G5K et VM inchangée)

# Noms des fichiers WAR pour l'application étudiante
STUDENT_APP_STANDARD_WAR="students-server-standard.war"
STUDENT_APP_ODB_WAR="students-server-odb.war"

# ... (Configuration du projet et des tests de charge inchangée)

# Listes pour la boucle de tests
SERVLET_MODES=("serv" "serv1")
IMAGE_SIZES=("zero.jpg" "tiny.jpg" "small.jpg" "large.jpg")
STUDENT_QUERIES=("firstname=Alain&lastname=Tchana" "firstname=Boris&lastname=Teabe")
STUDENT_MODES=("standard" "odb")

# --- Fonctions ---

# ... (log, die, ssh_g5k, scp_g5k, generate_ssh_config inchangées)

prepare_and_upload() {
    log "--- Préparation et téléversement ---"
    # ... (Vérifications pour id_rsa.pub et image cloud inchangées)

    # Ajout de la vérification pour les WARs étudiants
    if [ ! -f "$STUDENT_APP_STANDARD_WAR" ]; then die "Fichier '${STUDENT_APP_STANDARD_WAR}' non trouvé."; fi
    if [ ! -f "$STUDENT_APP_ODB_WAR" ]; then die "Fichier '${STUDENT_APP_ODB_WAR}' non trouvé."; fi

    log "Nettoyage et téléversement du projet vers ${G5K_SITE}..."
    ssh_g5k g5k-site "rm -rf ${PROJECT_DIR} && mkdir ${PROJECT_DIR}" || die "Échec du nettoyage distant."
    scp_g5k -r "./${PROJECT_DIR}" "g5k-site:~/" || die "Échec du téléversement du projet."
    scp_g5k "${LOCAL_IMAGE_NAME}" "g5k-site:~/${PROJECT_DIR}/" || die "Échec du téléversement de l'image."
    scp_g5k "${STUDENT_APP_STANDARD_WAR}" "g5k-site:~/${PROJECT_DIR}/" || die "Échec du téléversement du WAR standard étudiant."
    scp_g5k "${STUDENT_APP_ODB_WAR}" "g5k-site:~/${PROJECT_DIR}/" || die "Échec du téléversement du WAR ODB étudiant."
}

# ... (deploy_vm_on_m2, prepare_node, stop_tomcat, start_tomcat inchangées)

run_test_loop() {
    log "--- Exécution de la boucle de tests (Images) ---"
    # ... (boucle de tests pour les images, inchangée)

    log "--- Exécution de la boucle de tests (Application Étudiante) ---"
    for mode in "${STUDENT_MODES[@]}"; do
        local app_war_name=""
        if [ "$mode" == "standard" ]; then
            app_war_name=$STUDENT_APP_STANDARD_WAR
        else
            app_war_name=$STUDENT_APP_ODB_WAR
        fi

        for query in "${STUDENT_QUERIES[@]}"; do
            local test_name="students_${mode}_${query//&/_}"
            log "--- Début du test: ${test_name} ---"

            stop_tomcat m3; stop_tomcat vm

            # Déployer la version STANDARD sur le backend
            ssh_g5k m3 "rm -rf ${REMOTE_PROJECT_PATH}/apache-tomcat-11.0.1/webapps/*; cp ${REMOTE_PROJECT_PATH}/${STUDENT_APP_STANDARD_WAR} ${REMOTE_PROJECT_PATH}/apache-tomcat-11.0.1/webapps/ROOT.war"
            start_tomcat m3

            # Déployer la version à tester (standard ou ODB) sur l'intermédiaire
            ssh_g5k vm "rm -rf ${REMOTE_PROJECT_PATH}/apache-tomcat-11.0.1/webapps/*; cp ${REMOTE_PROJECT_PATH}/${app_war_name} ${REMOTE_PROJECT_PATH}/apache-tomcat-11.0.1/webapps/ROOT.war"
            start_tomcat vm

            local cpu_log="results_cpu_${test_name}.csv"
            local pid=$(ssh_g5k vm "cd ${REMOTE_PROJECT_PATH}; nohup ./cpu_logger.sh ${cpu_log} 1 > /dev/null 2>&1 & echo \$!")

            local wrk_log="results_wrk_${test_name}.log"
            # L'application est déployée en tant que ROOT.war, donc pas de préfixe dans l'URL
            local url="http://${M2}:8080/getstudent?${query}&machine=${M3}"
            log "Lancement de wrk2 vers ${url}..."
            ssh_g5k m1 "cd ${REMOTE_PROJECT_PATH}/wrk2; ./wrk -t${WRK_THREADS} -c${WRK_CONNECTIONS} -d${WRK_DURATION} -R${WRK_RPS} --timeout ${WRK_TIMEOUT} --latency '${url}' > ${REMOTE_PROJECT_PATH}/${wrk_log}"

            ssh_g5k vm "kill ${pid}" &> /dev/null
        done
    done
}

# ... (collect_results, cleanup, main inchangés)
