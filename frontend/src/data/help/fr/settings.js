export default {
  helpContent: {
    title: 'Paramètres',
    subtitle: 'Configuration du système',
    overview: 'Configurez tous les aspects du système UCM. Les paramètres sont organisés par catégorie : général, apparence, e-mail, sécurité, SSO, sauvegarde, audit, base de données, HTTPS, mises à jour et webhooks.',
    sections: [
      {
        title: "Métriques Prometheus",
        content: "Endpoint /metrics optionnel exposant des compteurs (certificats, CA, planificateur, webhooks, ACME) au format Prometheus.",
        items: [
          { label: "Activation", text: "Définissez un jeton de métriques dans Paramètres › Général ; sans jeton, l'endpoint renvoie 404 (désactivé)" },
          { label: "Authentification", text: "Scrapez avec Authorization: Bearer <jeton>" },
          { label: "Compteurs", text: "ucm_certificates, ucm_certificate_authorities, ucm_scheduler_task_*, ucm_webhook_deliveries, ucm_acme_*" },
        ]
      },
      {
        title: "Vhost ACME public",
        content: "Paramètres › Général : nom d'hôte et port publics pour les URL du directory ACME derrière un reverse proxy.",
        items: [
          { label: "Admin", text: "admin.ucm.example.com, GUI et API (mTLS selon politique)" },
          { label: "ACME", text: "acme.ucm.example.com, /acme/* et /acme/proxy/* (sans mTLS client)" },
          { label: "TLS wildcard", text: "Nom concret (ex. acme.ucm.example.com). Un SAN *.ucm.example.com sur le certificat couvre le TLS admin et ACME, ne pas saisir *.ucm.example.com comme vhost" },
          { label: "Avant enregistrement", text: "DNS et TLS opérationnels pour le vhost ACME, les clients basculent les URL du directory immédiatement" },
          { label: "ID certificat TLS", text: "Métadonnée du certificat déployé sur le vhost ACME (ex. wildcard)" },
        ]
      },
      {
        title: "Historique de livraison des webhooks",
        content: "Chaque endpoint webhook conserve un journal de livraison avec statut, tentatives et nouvelle tentative manuelle.",
        items: [
          { label: "Statuts", text: "pending / delivered / failed, avec le dernier code HTTP et l'erreur" },
          { label: "Réessayer", text: "Remettre manuellement en file un événement échoué ou déjà livré" },
          { label: "Asynchrone", text: "Les livraisons partent d'une file durable avec backoff exponentiel (jusqu'à 5 tentatives)" },
        ]
      },
      {
        title: "Vue du planificateur",
        content: "Paramètres › Planificateur liste les tâches d'arrière-plan avec leur statut et leur dernière exécution.",
        items: [
          { label: "Tâches", text: "Vérifications d'expiration, rafraîchissement CRL, livraison webhooks, sauvegardes planifiées, renouvellement auto, etc." },
          { label: "Exécuter", text: "Déclencher n'importe quelle tâche à la demande" },
          { label: "Visibilité", text: "Dernière exécution, dernière durée et nombre d'échecs par tâche" },
          { label: "Processus du planificateur (v2.251)", text: "Les tâches s'exécutent dans un processus de planification dédié, lancé avec le service et relancé en quelques secondes après un plantage ou un rechargement : une tâche longue ne retarde ni les requêtes ni les workers. Il occupe environ 150 Mo de mémoire" },
          { label: "Statut périmé (v2.251)", text: "Quand le processus du planificateur n'a pas donné signe de vie depuis un moment, l'onglet avertit que le statut affiché peut être obsolète" },
          { label: "Tâches longues (v2.251)", text: "Exécuter attend jusqu'à 30 secondes le résultat. Une tâche encore en cours est alors signalée comme démarrée et toujours en cours, et son résultat apparaît à un rafraîchissement ultérieur" },
        ]
      },
      {
        title: "Sauvegardes planifiées",
        content: "Sauvegardes chiffrées et automatiques de la base de données, à cadence configurable et avec rétention.",
        items: [
          { label: "Cadence", text: "Quotidienne / hebdomadaire / mensuelle" },
          { label: "Rétention", text: "Les sauvegardes plus anciennes que le nombre de jours défini (30 par défaut) sont purgées" },
          { label: "Chiffrement", text: "Les sauvegardes sont chiffrées avec le mot de passe de sauvegarde configuré" },
          { label: "Dérivation de clé", text: "Automatique (Argon2id si disponible, PBKDF2 en mode FIPS), PBKDF2-HMAC-SHA256 ou Argon2id. Les archives écrites avec Argon2id ne peuvent pas être restaurées sur une instance en mode FIPS" },
        ]
      },
      {
        title: 'Restauration (v2.251)',
        items: [
          { label: "Remplacer ou fusionner", text: "Restaurer depuis une sauvegarde remplace les données d'ici par celles de l'archive et supprime ce que l'archive ne contient pas ; l'entrée d'audit liste ce qui a été supprimé. L'API accepte aussi mode=merge, qui ajoute l'archive aux données d'ici" },
          { label: "Verrou partagé", text: "Sauvegardes et restaurations partagent un même verrou : une restauration est refusée (409) pendant une sauvegarde, et une sauvegarde manuelle attend la fin d'une restauration en cours" },
          { label: "Limite de téléversement", text: "Une archive créée depuis la 3.0 est restaurée par morceaux et n'a pas de limite de taille, sauf si BACKUP_MAX_ARCHIVE_MB en fixe une. Une archive plus ancienne est acceptée jusqu'à BACKUP_MAX_UPLOAD_MB (512 Mo par défaut). Les deux se règlent dans l'environnement du serveur et un refus nomme son paramètre. Un reverse proxy placé devant UCM conserve sa propre limite de corps de requête" },
          { label: "Contenu d'une archive", text: "Les archives incluent les orders du client ACME, les demandes d'approbation et les demandes de récupération de clé. Restaurer une archive écrite avant cette version laisse ces lignes ici telles quelles" },
          { label: "Mêmes noms", text: "Un fournisseur DNS, un compte CA ACME ou un webhook dont le nom est déjà porté par une autre ligne ici est restauré sous « nom (2) », et le résultat de restauration renvoyé par l'API le liste" },
          { label: "Paramètres qui désignent une ligne", text: "Les AC émettrices SCEP et ACME, les répondeurs OCSP et paramètres similaires suivent les lignes archivées. Depuis une archive plus ancienne restaurée sur une autre installation, ils sont vidés et doivent être choisis de nouveau" },
        ]
      },
      {
        title: "Mises à jour automatiques (v2.215)",
        content: "Paramètres › Mises à jour : vérification quotidienne en arrière-plan des nouvelles versions, et installation sans surveillance optionnelle.",
        items: [
          { label: "Canal", text: "« Versions stables » ne suit que les releases finales ; « Versions candidates » n'accepte en plus que les versions rcN, jamais les alpha/bêta" },
          { label: "Notification", text: "Une version nouvellement disponible déclenche l'événement webhook/e-mail system.update_available, une fois par version" },
          { label: "Installation auto", text: "Désactivée par défaut. Une fois activée, UCM télécharge, vérifie et installe la mise à jour à l'heure choisie, puis redémarre, installations DEB/RPM uniquement" },
          { label: "Somme de contrôle", text: "Une installation sans surveillance exige le SHA256 publié de la release pour vérification ; une installation manuelle vérifie aussi dès qu'une somme de contrôle est publiée" },
          { label: "Docker", text: "Les conteneurs ne peuvent pas se mettre à jour eux-mêmes, la vérification et la notification fonctionnent toujours ; récupérez la nouvelle image pour mettre à jour" },
          { label: 'HA mode', text: 'In HA mode on DEB/RPM, Install Update and the auto-install update the nodes one at a time; the next node starts once the previous one is back on the new version. The screen shows the nodes done, the node in progress and the node where it stopped with the reason; Resume continues from it. Docker and Kubernetes leave it to the orchestrator' },
          { label: 'Popup post-mise à jour', text: 'Optionnel (v2.217) : affiche une fois les notes de version après l\'installation d\'une mise à jour, par utilisateur. Désactivé par défaut' },
        ]
      },
      {
        title: "HSTS (Strict Transport Security)",
        content: "Politique HSTS configurable par l'opérateur afin que les instances utilisant des certificats auto-signés lors de la configuration initiale puissent s'exclure entièrement.",
        items: [
          { label: "Défaut", text: "HSTS activé, includeSubDomains, max-age 1 an (rétrocompatible)" },
          { label: "Désactivation", text: "Désactiver pour les instances avec certificats auto-signés lors de la configuration initiale (évite le verrouillage navigateur)" },
          { label: "Variable d'env.", text: "UCM_HSTS_ENABLED, UCM_HSTS_INCLUDE_SUBDOMAINS, UCM_HSTS_MAX_AGE dans /etc/ucm/ucm.env priment sur la base" },
          { label: "Sous-domaines", text: "Retirer includeSubDomains lorsque les sous-domaines hébergent des services distincts avec leurs propres certificats" },
        ]
      },
      {
        title: 'Catégories',
        items: [
          { label: 'Général', text: 'Nom d\'hôte syslog (envoyé comme HOSTNAME dans les messages syslog transmis), URL de base et valeurs par défaut à l\'échelle du système' },
          { label: 'Apparence', text: 'Sélection du thème (clair/sombre/système), couleur d\'accentuation, mode bureau' },
          { label: 'E-mail (SMTP)', text: 'Serveur SMTP, identifiants, éditeur de modèle d\'e-mail et notifications d\'alerte d\'expiration' },
          { label: 'Sécurité', text: 'Politique de mot de passe, durée de session, liste d\'accès administrateur, mTLS, chiffrement des clés privées ; le délai d\'inactivité et le verrouillage de compte sont sous Général' },
          { label: 'SSO', text: 'Intégration d\'authentification unique SAML 2.0, OAuth2/OIDC et LDAP' },
          { label: 'Sauvegarde', text: 'Sauvegardes de base de données manuelles et programmées' },
          { label: 'Audit', text: 'Rétention des journaux, transfert syslog, vérification d\'intégrité' },
          { label: 'Base de données', text: 'Backend actif (SQLite ou PostgreSQL), taille, nombre de tables, tester/basculer/migrer entre les backends' },
          { label: "Schéma PostgreSQL (v2.251)", text: "Une URL PostgreSQL dont le search_path désigne un schéma autre que public est prise en charge : le contrôle d'intégrité compte les tables de ce schéma, et une migration vers lui réaligne ses séquences" },
          { label: 'HTTPS', text: 'Certificat TLS pour l\'interface web UCM. Le certificat appliqué est mémorisé et réappliqué lors de son renouvellement (v2.217) ; le certificat lié est affiché avec un bouton pour le délier et ne plus suivre les renouvellements (v2.218). Un renouvellement par protocole dont UCM ne détient pas la clé laisse HTTPS sur le certificat précédent et le signale, jusqu\'à l\'import de la clé du certificat renouvelé' },
          { label: 'Mises à jour', text: 'Vérifier les nouvelles versions, voir le journal des modifications, vérification quotidienne planifiée avec installation sans surveillance en opt-in (DEB/RPM)' },
          { label: 'Webhooks', text: 'Webhooks HTTP pour les événements de certificat (émission, révocation, expiration). Authentification sortante optionnelle : Bearer, Basic, API key ou en-tête personnalisé' },
          { label: "Noms de webhooks uniques (v2.251)", text: "Un nom de webhook déjà utilisé est refusé (409), à la création comme au renommage. La mise à jour a renommé les doublons existants « nom (2) », « nom (3) », du plus ancien au plus récent" },
          { label: 'Déploiement', text: "Cibles de déploiement : connexions SSH/SFTP réutilisables, ou requête d'API HTTP (v2.252) ; chaque déploiement de certificat ou de CRL définit ses propres chemins et sa commande de rechargement facultative (réservé aux admins, v2.215)" },
          { label: 'Active Directory', text: "Connexion AD/LDAP propre à UCM pour les recherches liées aux certificats (résolution de principal Kerberos, sujets dérivés d'AD)" },
          { label: 'Auto-inscription Windows', text: 'Inscription Windows native MS-XCEP/MS-WSTEP : découverte de stratégie, émission de certificats et liaison Kerberos/SPNEGO' },
          { label: 'À propos', text: 'Informations système, Liens & Ressources et le lien Soutenir UCM mènent à Ko-fi (les administrateurs voient aussi une carte Ko-fi masquable une fois par version d\'UCM). Avec admin:system, Vérifier la préparation à FIPS liste ce que le mode FIPS refuserait sur cette instance, avec un remède pour chacun, et ne modifie rien' },
          { label: 'Profils de conformité', text: "Dans À propos, avec admin:system : Vérifier le profil liste ce qu'ANSSI, BSI ou EU ACM (règles alignées sur un texte de référence) refuserait ou déconseillerait sur cette instance, sans rien modifier. Avec admin:settings, Profil par défaut des nouvelles CA définit le profil reçu par une CA quand aucun n'est choisi ; les CA existantes ne changent pas" },
        ]
      },
      {
        title: 'Hooks de déploiement (v2.215)',
        content: "Paramètres › Déploiement (réservé aux admins) : connexions SSH/SFTP réutilisables, ou requêtes d'API HTTP, pour les déploiements de certificats et de CRL. Les chemins et la commande de rechargement facultative se règlent sur chaque déploiement SSH.",
        items: [
          { label: 'Cible', text: "Hôte, port, utilisateur SSH. UCM génère une clé ed25519 (installez la clé publique affichée sur la cible) ou accepte une clé privée importée, stockée chiffrée" },
          { label: 'Cible API HTTP (v2.252)', text: "URL, méthode (POST, PUT, PATCH), en-têtes de requête stockés chiffrés et jamais réaffichés, et un modèle de corps avec {{cert_pem}}, {{fullchain_pem}}, {{cn}}, {{serial}}... ainsi que les filtres |json, |jsonstr, |b64 et |urlencode. Un corps JSON est vérifié à l'enregistrement. La clé privée ({{key_pem}}) ne part qu'avec l'accord explicite de la cible et une URL https ; le certificat TLS est toujours vérifié, contre une ancre de confiance collée si l'appliance est auto-signée. Les redirections sont refusées, les adresses de métadonnées cloud et de loopback bloquées. Certificats uniquement : les CRL restent sur les cibles SSH" },
          { label: "Clé d'hôte", text: "Épinglée à la première connexion réussie (trust-on-first-use) ; tout changement ultérieur fait échouer la connexion. Changer l'hôte ré-épingle la clé" },
          { label: 'Commande de rechargement', text: "Une commande facultative, configurée sur chaque liaison de certificat ou de CRL et exécutée après un envoi réussi (par ex. systemctl reload nginx) : exit 0 = succès, pas de templating" },
          { label: 'Liaisons', text: "Les certificats sont attachés depuis le panneau de détails du certificat, les CRL depuis CRL & OCSP. Chaque liaison possède ses chemins, ses options de fichier et sa commande de rechargement" },
          { label: 'Livraison', text: "Les envois s'exécutent de façon asynchrone via une file durable avec réessais et backoff ; statut par livraison, « Déployer maintenant » et réessai manuels, piste d'audit complète" },
          { label: 'Moindre privilège', text: "Utilisez un compte SSH dédié sur chaque cible : accès en écriture aux chemins des certificats et permission de recharger le service, rien de plus" },
        ]
      },
      {
        title: 'SMTP OAuth2 (XOAUTH2)',
        content: 'Authentification OAuth2 moderne pour le mail sortant, remplaçant les flux app-password historiques que Microsoft et Google déprécient :',
        items: [
          { label: 'Gmail', text: 'Configurer un client OAuth2 Google Cloud avec le scope https://mail.google.com/' },
          { label: 'Microsoft 365 / Outlook.com', text: 'Enregistrer une application Azure AD avec la permission déléguée SMTP.Send' },
          { label: 'Refresh tokens', text: 'UCM stocke le refresh token et renouvelle les access tokens automatiquement avant chaque envoi' },
          { label: 'Repli', text: 'L\'authentification par mot de passe reste supportée si OAuth2 n\'est pas configuré' },
        ]
      },
      {
        title: 'Connecteur Active Directory',
        content: 'Connexion LDAP propre à UCM à Active Directory, indépendante de tout fournisseur LDAP configuré sous SSO -- celui-ci sert à se connecter à UCM, celui-ci aux recherches AD liées aux certificats.',
        items: [
          { label: 'Objectif', text: "Résout un principal de machine ou d'utilisateur Kerberos vers son objet AD, afin qu'UCM puisse dériver un sujet/SAN de certificat, comme le ferait une vraie AC Windows" },
          { label: 'Connecteurs', text: "Un par annuaire (forêt ou domaine), listé avec son realm, le SID de domaine lu et son état de santé. Un connecteur que des profils d'inscription Windows utilisent ne peut pas être supprimé, et le refus les liste" },
          { label: 'Champs', text: 'Nom, contrôleurs de domaine (un par ligne, chacun par son propre nom d\'hôte, essayés dans l\'ordre avec basculement), port, LDAPS avec vérification AC facultative, DN de base, DN de liaison et mot de passe (tous deux requis tant que le connecteur est activé)' },
          { label: 'Connecteur désactivé', text: "Un connecteur désactivé ne fait aucune recherche, mais son DN de base nomme encore le realm du profil par défaut en dernier recours, quand ni un connecteur activé, ni le SPN, ni le keytab ne le nomment" },
          { label: 'Tester la connexion', text: "Vérifier la connectivité et les identifiants avant d'enregistrer ; le test lit aussi le SID du domaine" },
          { label: 'Contrôle d\'état', text: 'Chaque contrôleur de domaine est sondé par une vraie liaison à l\'intervalle de contrôle d\'état ; un contrôleur injoignable est ignoré lors de l\'inscription jusqu\'à son rétablissement. Le verdict s\'affiche sur la ligne des paramètres et pour chaque DC' },
        ]
      },
      {
        title: 'Auto-inscription Windows (XCEP/WSTEP)',
        content: "Inscription de certificats Windows native via la découverte de stratégie MS-XCEP et l'émission MS-WSTEP -- prend en charge l'inscription manuelle MMC/certreq et l'auto-inscription GPO sans surveillance.",
        items: [
          { label: 'Profils', text: "Un profil par realm Active Directory, choisi d'après le realm du principal Kerberos du client : ses propres CA d'émission et de politique, sous-ensemble de modèles, connecteur AD et keytab ; les comptes UsernamePassword appartiennent au profil par défaut. La liste est paginée et filtrée par le serveur (nom ou realm, CA, état : complet, keytab manquant, connecteur en échec, désactivé)" },
          { label: 'Realm', text: "En majuscules, exactement comme le KDC l'écrit (CORP.EXAMPLE) : un KDC compare les realms caractère par caractère. Le profil par défaut sans realm refuse Kerberos tant qu'aucun n'est renseigné. Un profil désactivé refuse les postes de son realm ; ses clés restent dans le keytab servi, pour que le refus soit audité par realm" },
          { label: 'XCEP', text: "Permet aux clients Windows de découvrir les modèles de certificat disponibles avant l'inscription" },
          { label: 'WSTEP', text: 'Gère la demande et le renouvellement du certificat une fois la stratégie découverte' },
          { label: 'Kerberos/SPNEGO', text: "Lie les points de terminaison authentifiés par Kerberos utilisés pour l'auto-inscription GPO silencieuse (un SPN commun à tous les profils, et un keytab par profil issu du contrôleur de domaine de son realm ; le formulaire liste par realm les entrées du fichier choisi et signale un realm qui n'est pas celui du profil)" },
          { label: 'Liste de contrôle de configuration', text: "Le formulaire de chaque profil liste ce qui lui manque encore : realm, CA d'émission, keytab, un connecteur joignable, un modèle qui autorise l'inscription automatique, le profil activé" },
          { label: "URL de stratégie", text: "Les mêmes pour tous les profils : le routage se fait par realm, pas par URL" },
          { label: "Sujets dérivés d'AD", text: "Les modèles peuvent choisir de dériver leur sujet/SAN depuis Active Directory (via le connecteur AD) pour l'inscription sans surveillance" },
          { label: 'Templates ML-DSA (v2.248)', text: 'Annoncés par l\'OID de leur algorithme de clé avec le Microsoft Software Key Storage Provider, pas encore testés avec un vrai client Windows, et masqués en mode FIPS. Le renouvellement par certificat ne peut pas utiliser un certificat ML-DSA (XML-DSig n\'a pas de signature ML-DSA) : inscrivez-en un nouveau' },
          { label: "Templates ECDSA (v2.251)", text: "Annoncés en schéma de stratégie 3 avec leur courbe (ECDSA_P256, ECDSA_P384, ECDSA_P521) comme clé de signature et condensat de requête, le plus fort entre le condensat du template et celui de la courbe. Les templates RSA hors mode FIPS restent en schéma 2" },
          { label: 'Template nommé dans la requête (v2.252)', text: 'Chaque stratégie annonce son extension de template (szOID_CERTIFICATE_TEMPLATE), que Windows copie dans sa requête : le certificat est émis sous le template choisi sur le client, même si un autre a les mêmes EKU. Une requête qui ne nomme aucun template est appariée par ses EKU. Un template dont tous les EKU ne sont jamais émis à un inscrit, comme la signature OCSP, n\'est pas annoncé, et une requête pour lui est refusée' },
          { label: "Template et clé (v2.251)", text: "La clé de la requête doit convenir au template sous lequel elle est émise : même courbe ou même jeu ML-DSA, ou clé RSA au moins aussi longue. Une requête P-384 n'est donc plus émise sous un template P-256 qui partage son EKU. L'enveloppe de requête que Windows signe avec une clé ECDSA est acceptée" },
          { label: "Renouvellement depuis Windows (v2.248)", text: "Ne sert que les certificats émis par l'inscription Windows ; un certificat signé à la main est remplacé par une nouvelle inscription. Sous TLS, le certificat à renouveler est le certificat client : mTLS doit être activé, avec l'AC WSTEP, ou l'un de ses ancêtres, en confiance. Un renouvellement conserve le template et les EKU du certificat renouvelé, et son SubjectAltName quand la CSR n'en porte aucun (v2.252)" },
          { label: 'Type de certificat', text: 'Sans Server Auth, un template avec Email Protection ou EFS émet un certificat S/MIME, un avec Client Auth ou Smartcard Logon un certificat client : une requête utilisateur CN=jdoe sans SAN ne reçoit aucun nom DNS depuis son CN. Une requête sans Key Usage reçoit celui que configure le template, sinon celui du type de template : Digital Signature, Key Encipherment et Non Repudiation pour S/MIME ou EFS, Digital Signature et Key Encipherment pour Smartcard Logon, Digital Signature seul pour Client Auth. Tout autre template, ou aucun, émet un certificat serveur' },
          { label: "Kerberos dans Docker (v2.251)", text: "Les images Docker embarquent le backend Kerberos de pyspnego : la liaison Kerberos fonctionne en conteneur comme dans les installations DEB et RPM" },
        ]
      },
      {
        title: 'Renouvellement automatique',
        items: [
          { label: 'Sources', text: 'Le planificateur renouvelle les certificats dont le serveur détient la clé privée : par défaut ceux émis depuis le formulaire ou une requête signée (« manual »), ainsi que les enrôlements SCEP, ACME et EST à clé générée par le serveur. Les appareils qui détiennent leur propre clé se renouvellent via leur protocole' },
          { label: 'En attente d\'approbation', text: 'Un certificat dont le renouvellement est en file d\'approbation est laissé à cette décision, tant qu\'elle peut intervenir avant l\'expiration du certificat' },
          { label: 'Renouvelé entre-temps', text: 'Un certificat qu\'un opérateur a renouvelé pendant le lot n\'est pas renouvelé une seconde fois ; un certificat supprimé pendant le lot est ignoré' },
          { label: 'Certificats courts', text: 'Le renouvellement ne commence jamais avant le dernier tiers de la durée d\'un certificat : un certificat de 27 jours est renouvelé à 9 jours de l\'échéance, et non dès son émission' },
          { label: 'Exécuter maintenant', text: 'Exécute immédiatement une passe de renouvellement et signale les certificats arrivant à expiration qu\'elle a laissés de côté, comptés par motif : pas encore dans le dernier tiers de leur durée de vie, clé privée non détenue par le serveur, source non sélectionnée' },
          { label: "Digest de signature (v2.251)", text: "Un renouvellement conserve le condensat du certificat d'origine tant qu'il est au moins celui qui correspond à la clé de l'AC et que les politiques l'autorisent ; sinon il suit la règle d'émission : sous une AC P-384 ou P-521, un original en SHA-256 est renouvelé en SHA-384 ou SHA-512" },
        ]
      },

    ],
    tips: [
      'Utilisez la barre d\'état en bas pour vérifier que le service répond',
      'Testez les paramètres SMTP avant de vous fier aux notifications par e-mail',
      'Personnalisez le modèle d\'e-mail avec votre marque à l\'aide de l\'éditeur HTML/Texte intégré',
      'Programmez des sauvegardes automatiques pour les environnements de production',
      'Le basculement SQLite ↔ PostgreSQL est bidirectionnel : l\'UI exécute des contrôles de sûreté (driver chargé, cible joignable, cible vide) avant migration',
    ],
    warnings: [
      'Le changement du certificat HTTPS nécessite un redémarrage du service',
      'La modification des paramètres de sécurité peut verrouiller les utilisateurs : vérifiez l\'accès avant d\'enregistrer',
    ],
  },
  helpGuides: {
    title: 'Paramètres',
    content: `
## Vue d'ensemble

Configuration à l'échelle du système organisée en onglets. Les modifications prennent effet immédiatement sauf indication contraire.

## Général

- **Nom d'hôte syslog** : Envoyé comme HOSTNAME dans les messages syslog transmis ; le nom d'hôte de la machine si vide
- **URL de base** : URL HTTPS canonique de l'interface d'administration et de l'API ; les autres noms d'hôte et IP y sont redirigés
- **URL de base protocole** : URL de base écrite dans les adresses CDP et OCSP ; utilisez http:// pour éviter les boucles de vérification TLS, ou laissez vide pour utiliser l'URL de base
- **Port HTTP protocole** : Port HTTP simple qui sert CDP et OCSP ; 0 le désactive, un changement nécessite un redémarrage
- **Vhost ACME public** : Nom d'hôte concret dans les URL du directory ACME (ex. \`acme.ucm.example.com\`, pas \`*.ucm.example.com\`). Un **SAN de certificat TLS** wildcard \`*.ucm.example.com\` couvre à la fois \`admin.ucm.example.com\` et \`acme.ucm.example.com\`. Configurez le DNS et le TLS du vhost ACME **avant** d'enregistrer : les clients qui relisent le directory basculent immédiatement d'URL.

## Apparence

- **Thème** : Clair, Sombre ou Système (suit la préférence du système d'exploitation)
- **Couleur d'accentuation** : Couleur principale utilisée pour les boutons, liens et mises en évidence
- **Forcer le mode bureau** : Désactiver la disposition mobile responsive

## E-mail (SMTP)

Configurez SMTP pour les notifications par e-mail (alertes d'expiration, invitations d'utilisateurs) :
- **Hôte SMTP** et **Port**
- **Nom d'utilisateur** et **Mot de passe**
- **Chiffrement** : Aucun, STARTTLS ou SSL/TLS
- **Adresse d'expédition** : Adresse e-mail de l'expéditeur
- **Type de contenu** : HTML, texte brut ou les deux
- **Destinataires des alertes** : Ajoutez plusieurs destinataires en utilisant le champ de tags

Cliquez sur **Tester** pour envoyer un e-mail de test et vérifier la configuration.

### Éditeur de modèle d'e-mail

Cliquez sur **Modifier le modèle** pour ouvrir l'éditeur de modèle en panneau divisé dans une fenêtre flottante :
- **Onglet HTML** : Modifiez le modèle d'e-mail HTML avec aperçu en direct à droite
- **Onglet Texte brut** : Modifiez la version texte brut pour les clients e-mail qui ne prennent pas en charge HTML
- Variables disponibles : \`{{title}}\`, \`{{content}}\`, \`{{datetime}}\`, \`{{instance_url}}\`, \`{{logo}}\`, \`{{title_color}}\`
- Cliquez sur **Rétablir les valeurs par défaut** pour restaurer le modèle UCM intégré
- La fenêtre est redimensionnable et déplaçable pour un édition confortable

### Alertes d'expiration

Lorsque SMTP est configuré, activez les alertes automatiques d'expiration de certificats :
- Basculez les alertes on/off
- Sélectionnez les seuils d'avertissement (90j, 60j, 30j, 14j, 7j, 3j, 1j)
- Lancez **Vérifier maintenant** pour déclencher une analyse immédiate
- **Ignorer les certificats émis par ACME** : exclut les certificats émis par le serveur ACME d'UCM, que leurs clients renouvellent ; désactivé par défaut

## Sécurité

### Politique de mot de passe
- Longueur minimale (6-32 caractères)
- Exiger majuscules, chiffres, caractères spéciaux

### Gestion de session
- Durée de session (heures, quelle que soit l'activité) ; le délai d'inactivité est sous Général

### Verrouillage de compte
- Max tentatives de connexion et durée de verrouillage, sous Général : ils verrouillent le compte, pas l'adresse IP

### Liste d'accès administrateur
Limiter l'interface web et l'API de gestion aux adresses IP et réseaux CIDR listés ; les protocoles PKI restent accessibles de partout. Voir le guide des paramètres de sécurité.

### Application de la 2FA
Exiger que tous les utilisateurs activent l'authentification à deux facteurs.

### Chiffrement des clés privées
Chiffrez toutes les clés privées stockées en base de données avec AES-128 (Fernet, avec HMAC-SHA256), protégées par un fichier de clé maître. La section affiche l'état du chiffrement et les compteurs de clés **chiffrées / non chiffrées**. Deux variables d'environnement opt-in rendent l'absence de clé fatale au démarrage : \`UCM_REQUIRE_DB_ENCRYPTION_KEY\` (chiffrement des secrets d'intégration) et \`UCM_REQUIRE_KEY_ENCRYPTION\` (chiffrement des clés privées).
Une nouvelle installation crée la clé maître à son premier démarrage (dans un conteneur, seulement si \`/etc/ucm\` est un volume à part) ; la section Sécurité des Paramètres affiche l'état du chiffrement, et la Vue d'ensemble affiche une bannière tant qu'aucune clé n'est chargée.

> 💡 Les paramètres sensibles (session, verrouillage, HSTS, URL publique, politique de mot de passe) exigent la permission **admin:settings** : les champs sont verrouillés pour les opérateurs.

> ⚠ Une liste qui n'inclut pas votre propre adresse est refusée. Si vous perdez tout de même l'accès, définissez \`UCM_ADMIN_ALLOWLIST_DISABLE=1\` et redémarrez UCM.

## SSO (Authentification unique)

### SAML 2.0
- Fournissez à votre IDP l'**URL de métadonnées SP** : \`/api/v2/sso/saml/metadata\`
- Ou configurez manuellement : téléversez/liez le XML de métadonnées IDP, configurez l'Entity ID et l'URL ACS
- Mappez les attributs IDP aux champs utilisateur UCM (nom d'utilisateur, e-mail, rôle)

### OAuth2 / OIDC
- URL d'autorisation et URL de jeton
- Client ID et Client Secret
- URL d'info utilisateur (pour la récupération d'attributs)
- Scopes (openid, profile, email)
- Création automatique d'utilisateurs à la première connexion SSO

### LDAP
- Nom d'hôte du serveur, port (389/636), bascule SSL
- DN de liaison et mot de passe (compte de service)
- DN de base et filtre utilisateur
- Mappage d'attributs (nom d'utilisateur, e-mail, nom complet)

> 💡 Gardez toujours un compte admin local comme repli en cas de panne SSO.

## Sauvegarde

### Sauvegarde manuelle
Cliquez sur **Créer une sauvegarde** pour générer un instantané de la base de données. Les sauvegardes incluent les certificats, CA, clés et paramètres ; le journal d'audit et les autres tables d'historique n'y figurent pas.

### Sauvegarde programmée
Configurez des sauvegardes automatiques :
- Fréquence (quotidienne, hebdomadaire, mensuelle)
- Rétention en jours : les sauvegardes plus anciennes sont purgées (30 par défaut)
- **Dérivation de clé** : Automatique (Argon2id si disponible, PBKDF2 en mode FIPS), PBKDF2-HMAC-SHA256 ou Argon2id. Les archives écrites avec Argon2id ne peuvent pas être restaurées sur une instance en mode FIPS

### Restauration
Téléversez un fichier de sauvegarde pour restaurer UCM à un état précédent.

- Sauvegardes et restaurations partagent un même verrou : une restauration est refusée (409) pendant une sauvegarde, et une sauvegarde manuelle attend la fin d'une restauration en cours
- Une archive créée depuis la 3.0 est restaurée par morceaux, sans limite de taille sauf si \`BACKUP_MAX_ARCHIVE_MB\` en fixe une ; une archive plus ancienne est acceptée jusqu'à \`BACKUP_MAX_UPLOAD_MB\` (512 Mo par défaut). Les deux se règlent dans l'environnement du serveur ; un reverse proxy placé devant UCM conserve sa propre limite de corps de requête
- Les archives contiennent les orders du client ACME, les demandes d'approbation et les demandes de récupération de clé (v2.251)
- Un fournisseur DNS, un compte CA ACME ou un webhook dont le nom est déjà porté par une autre ligne ici est restauré sous \`nom (2)\`
- L'API accepte aussi \`mode=merge\`, qui ajoute l'archive aux données d'ici au lieu de les remplacer

> ⚠ La restauration d'une sauvegarde remplace TOUTES les données actuelles.

## Audit

- **Rétention des journaux** : Nettoyage automatique des anciens journaux après N jours
- **Transfert syslog** : Envoyer les événements à un serveur syslog distant (UDP/TCP/TLS)
- **Vérification d'intégrité** : Vérifier la chaîne de hachages qui relie chaque entrée d'audit ; la chaîne est toujours active, il n'y a rien à activer

## Base de données

UCM prend en charge deux backends de base de données :

- **SQLite** (par défaut) : basé sur fichier, sans configuration, idéal pour un nœud unique
- **PostgreSQL 13+** : recommandé pour la haute disponibilité, le multi-instance ou si vous opérez déjà un cluster PG géré

Le backend actif est sélectionné par la variable d'environnement \`DATABASE_URL\`. Si elle n'est pas définie, UCM utilise SQLite dans \`DATA_DIR/ucm.db\`.

### Panneau d'état
- Backend actif (sqlite / postgresql) et la version de son moteur
- Taille de la base et nombre de tables

### Tester la connexion
Validez une \`DATABASE_URL\` (ex. \`postgresql://user:pass@host:5432/ucm\`) avant de basculer. Le test ouvre une vraie connexion et signale toute erreur. Les serveurs PostgreSQL antérieurs à la version 13 sont rejetés, UCM nécessite PostgreSQL 13 ou plus récent.

### Basculer le backend
Persiste \`DATABASE_URL\` dans \`/etc/ucm/ucm.env\` (DEB/RPM) et redémarre UCM. Seules les tables des comptes, rôles, SSO et MFA sont copiées vers le nouveau backend, pour que vous puissiez toujours vous connecter ; utilisez **Migrer** d'abord si vous voulez conserver vos autres données.

### Migrer les données
Copie toutes les lignes du backend actuel vers le backend cible. Fonctionne dans les deux sens (SQLite ↔ PostgreSQL) :

1. La base source est sauvegardée dans \`/opt/ucm/data/backups/db_migration/\`
2. Le schéma est créé sur la cible via SQLAlchemy
3. Les contraintes FK sont désactivées pendant le chargement
4. Les colonnes sont appariées par nom ; seules les colonnes héritées connues sont ignorées, et toute autre colonne absente de la cible fait refuser la migration
5. Les séquences PostgreSQL sont réinitialisées après le chargement
6. Le service redémarre automatiquement (DEB/RPM) : sur Docker, définissez \`DATABASE_URL\` dans votre fichier compose et redémarrez le conteneur manuellement

**Contrôles de sécurité (échec rapide, source intacte) :**
- La cible doit être vide. Si l'une de ses tables contient déjà des lignes, la migration est refusée avec un HTTP 409 et un indice de nettoyage :
  - PostgreSQL : \`psql ... -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'\`
  - PostgreSQL dans un schéma autre que \`public\` (un \`search_path\` dans l'URL) : l'indice nomme ce schéma, dont la migration réaligne les séquences (v2.251)
  - SQLite : supprimez le fichier cible \`.db\`
- Si la migration échoue en cours de route, la source est intacte et le message d'erreur indique la sauvegarde source. Réinitialisez la cible avant de réessayer.

> ⚠ Effectuez toujours une sauvegarde complète d'UCM (Paramètres → Sauvegarde) avant de migrer entre backends.

## HTTPS

Gérez le certificat TLS utilisé par l'interface web UCM :
- Voir les détails du certificat actuel
- Importer un nouveau certificat (PEM ou PKCS#12)
- Générer un certificat auto-signé
- Quand le certificat lié est renouvelé par un protocole sans que sa clé parvienne à UCM, la page le signale : HTTPS continue de servir le certificat précédent jusqu'à l'import de la clé du certificat renouvelé, ce qui l'applique

> ⚠ Le changement du certificat HTTPS nécessite un redémarrage du service.

## Mises à jour

- Vérifier les nouvelles versions UCM depuis les releases GitHub
- Voir le journal des modifications pour les mises à jour disponibles
- Version actuelle et informations de build
- **Mise à jour automatique** : sur les installations prises en charge (DEB/RPM), cliquez sur **Installer la mise à jour** pour télécharger et installer automatiquement la dernière version
- **HA mode**: on DEB/RPM, **Install Update** and the auto-install update the nodes one at a time, and the screen follows the rolling update (nodes done, node in progress, package of each node, node where it stopped and why, **Resume**)
- **Canal de mise à jour** : stable, pré-version (versions candidates) ou dev

## Webhooks

Configurez des webhooks HTTP pour notifier les systèmes externes lors d'événements :

### Événements pris en charge
- Certificat émis, révoqué, renouvelé, bientôt expiré, expiré, importé, supprimé
- CA créée, modifiée, supprimée
- CSR soumise, approuvée, rejetée
- Modèle créé, modifié
- ACME preflight, échec de renouvellement, échec de révocation
- Mise à jour disponible, lancée, installée, en échec

Les imports de certificats et les modifications de modèles faits depuis l'interface web n'émettent pas leur événement.

### Authentification

Authentification sortante optionnelle (s'ajoute à la signature HMAC optionnelle) :

- **Aucune** : Pas d'en-tête d'authentification (webhooks publics)
- **Bearer** : Authorization: Bearer {token}
- **Basic** : Authorization: Basic base64(utilisateur:motdepasse)
- **Clé API** : En-tête personnalisé (p.ex. X-Api-Key: {token})
- **Personnalisée** : Authorization: {schéma} {token} (p.ex. auth-key VALEUR)

Les tokens sont stockés chiffrés et jamais renvoyés dans l'UI.

### Créer un webhook
1. Cliquez sur **Ajouter un webhook**
2. Entrez l'**URL** (HTTPS recommandé ; http:// est accepté)
3. Sélectionnez les **événements** auxquels s'abonner
4. Choisissez le **type d'authentification** et fournissez les identifiants (optionnel)
5. Définissez optionnellement un **secret** pour la vérification de signature HMAC
6. Cliquez sur **Créer**

### Test
Cliquez sur **Tester** pour envoyer un événement exemple à l'URL du webhook et vérifier qu'il est accessible.
## Métriques Prometheus

Endpoint **\`/metrics\`** opt-in et protégé par jeton.

- Activez-le en définissant un jeton de métriques (Paramètres › Général) ; sans jeton → 404
- Scrapez avec l'en-tête \`Authorization: Bearer <jeton>\`
- Expose \`ucm_certificates\`, \`ucm_certificate_authorities\`, \`ucm_scheduler_task_*\`, \`ucm_webhook_deliveries\`, \`ucm_acme_*\`

## Historique de livraison des webhooks

Ouvrez l'historique (icône horloge) sur un webhook pour voir ses livraisons.

- Statuts **pending / delivered / failed** avec dernier code HTTP et erreur
- **Réessayer** une livraison manuellement
- File durable avec backoff exponentiel (jusqu'à 5 tentatives)

## Vue du planificateur

Paramètres › Planificateur expose les tâches d'arrière-plan.

- Liste des tâches avec **statut**, **dernière exécution**, **durée** et **échecs**
- **Exécuter maintenant** sur n'importe quelle tâche : attend jusqu'à 30 secondes, et une tâche encore en cours est alors signalée comme démarrée, son résultat apparaissant à un rafraîchissement ultérieur
- Couvre expiration, CRL, livraison webhooks, sauvegardes, renouvellement auto…
- **Processus du planificateur** (v2.251) : les tâches s'exécutent dans un processus dédié, lancé avec le service et relancé en quelques secondes après un plantage ou un rechargement : une tâche longue ne retarde ni les requêtes ni les workers. Un avertissement s'affiche quand il n'a pas donné signe de vie depuis un moment

## Renouvellement automatique

Les paramètres de renouvellement automatique pilotent le planificateur de renouvellement.

- **Sources** : le planificateur renouvelle les certificats dont le serveur détient la clé privée : par défaut ceux émis depuis le formulaire ou une requête signée (« manual »), ainsi que les enrôlements SCEP, ACME et EST à clé générée par le serveur. Les appareils qui détiennent leur propre clé se renouvellent via leur protocole
- **En attente d'approbation** : un certificat dont le renouvellement est en file d'approbation est laissé à cette décision, tant qu'elle peut intervenir avant l'expiration du certificat
- **Renouvelé entre-temps** : un certificat qu'un opérateur a renouvelé pendant le lot n'est pas renouvelé une seconde fois ; un certificat supprimé pendant le lot est ignoré
- **Certificats courts** : le renouvellement ne commence jamais avant le dernier tiers de la durée d'un certificat : un certificat de 27 jours est renouvelé à 9 jours de l'échéance, et non dès son émission
- **Exécuter maintenant** : exécute immédiatement une passe de renouvellement et signale les certificats arrivant à expiration qu'elle a laissés de côté, comptés par motif : pas encore dans le dernier tiers de leur durée de vie, clé privée non détenue par le serveur, source non sélectionnée

## Sauvegardes planifiées

Paramètres › Sauvegarde permet des sauvegardes automatiques.

- Cadence **quotidienne / hebdomadaire / mensuelle**
- **Rétention** : les sauvegardes plus anciennes que le nombre de jours défini sont purgées
- Sauvegardes **chiffrées** avec le mot de passe de sauvegarde


## Connecteur Active Directory

Connexion LDAP propre à UCM à Active Directory, indépendante de tout fournisseur LDAP configuré sous SSO. Celui-ci sert à se connecter à UCM ; celui-ci est utilisé pour les recherches AD liées aux certificats et fonctionne indépendamment du fait que le SSO soit configuré ou non.

- **Connecteurs** : Un par annuaire (forêt ou domaine), listé sous Paramètres › Active Directory avec son nom, son realm, le SID de domaine lu et son état de santé. Un profil d'inscription Windows nomme le connecteur qui sert son realm ; un connecteur que des profils utilisent ne peut pas être supprimé, et le refus les liste
- **Objectif** : Résout un principal de machine ou d'utilisateur Kerberos vers son objet AD, afin qu'UCM puisse dériver un sujet/SAN de certificat comme le ferait une vraie AC Windows
- **Contrôleurs de domaine** : Un par ligne, chacun par son propre nom d'hôte, essayés dans l'ordre : les recherches basculent sur le suivant quand un DC est hors service. Un nom de domaine seul échoue à la vérification du certificat, car le certificat d'un contrôleur de domaine ne nomme que son propre hôte
- **LDAPS** : Activer pour utiliser LDAP sur SSL/TLS ; **Vérifier le certificat SSL** valide le certificat du DC (éventuellement par rapport à un bundle d'AC personnalisé lorsqu'il n'est pas approuvé publiquement)
- **DN de base** et **DN de liaison / Mot de passe** : Identifiants du compte de service utilisés pour les recherches ; le DN de liaison et le mot de passe sont tous deux requis tant que le connecteur est activé
- **Tester la connexion** : Vérifier la connectivité et les identifiants avant d'enregistrer
- **Intervalle de contrôle d'état** : Chaque contrôleur de domaine est sondé par une vraie liaison à cet intervalle ; un contrôleur injoignable est ignoré lors de l'inscription jusqu'à son rétablissement. Le verdict s'affiche sur la ligne du connecteur et pour chaque DC
- **Connecteur désactivé** : Un connecteur désactivé ne fait aucune recherche, mais son DN de base nomme encore le realm du profil par défaut en dernier recours, quand ni un connecteur activé, ni le SPN, ni le keytab ne le nomment

Les URL de stratégie d'inscription à enregistrer dans la stratégie de groupe sont les mêmes pour tous les profils ; elles s'affichent sous Paramètres › Auto-inscription Windows.

## Auto-inscription Windows (XCEP/WSTEP)

Inscription de certificats Windows native via **MS-XCEP** (découverte de stratégie) et **MS-WSTEP** (émission et renouvellement de certificats) -- les mêmes protocoles qu'un vrai ADCS utilise pour l'inscription interactive « Demander un nouveau certificat » dans MMC, \`certreq\`, et l'auto-inscription GPO sans surveillance.

### Profils

Un **profil par realm Active Directory**. UCM oriente un client vers son profil d'après le realm de son principal Kerberos : chaque profil a ses propres CA d'émission et de politique, modèles, connecteur AD et keytab ; les comptes UsernamePassword appartiennent au profil par défaut. La liste est paginée et filtrée par le serveur (nom ou realm, CA, état), si bien que cent profils s'ouvrent aussi vite qu'un seul :
- **Realm** : En majuscules, exactement comme le KDC l'écrit (\`CORP.EXAMPLE\`) : un KDC compare les realms caractère par caractère, un nom en minuscules ne correspond jamais à un ticket. Le formulaire le refuse et dit pourquoi
- **Connecteur** : Le connecteur AD qui sert le realm. Quand son domaine diffère du realm du profil, le formulaire avertit sans bloquer ; le serveur contrôle le couple quand l'un des deux est choisi
- **CA d'émission** et **CA de politique** : La CA qui émet, et celle dont XCEP annonce la politique et les OID de modèles (la CA d'émission si vide)
- **Modèles** : Le sous-ensemble proposé ; aucun coché propose les modèles de la CA. Un groupe AD exigé et des champs du sujet épinglés peuvent remplacer ceux du modèle pour tout le profil
- **État** : Complet, Keytab manquant, Connecteur en échec ou Désactivé. Un profil désactivé refuse les postes de son realm ; ses clés restent dans le keytab servi, pour que le refus soit prononcé et audité par realm

Le **profil par défaut** est celui dont une installation 2.x a hérité. Sans realm, Kerberos est refusé tant qu'un realm n'est pas renseigné (en majuscules, ou lu dans son keytab) ; l'écran le dit.

### Liste de contrôle de configuration, par profil

Le formulaire du profil liste ce qui lui manque encore : realm, CA d'émission, keytab, un connecteur joignable quand il y en a un, un modèle qui autorise l'inscription automatique, et le profil activé.

### Découverte de stratégie (XCEP)

- **Autorité de certification** : L'AC dont les modèles sont annoncés et qui émet des certificats via le profil
- **Validité (jours)** : Validité des certificats émis via WSTEP quand la demande ne correspond à aucun modèle ; sinon, la validité du modèle correspondant s'applique

Un modèle avec un type de clé **ML-DSA** est annoncé par l'OID de son algorithme de clé, avec le Microsoft Software Key Storage Provider et une spécification de clé réservée à la signature. Il est masqué en mode FIPS, et l'inscription depuis un vrai client Windows n'a pas encore été testée.

Un template **ECDSA** est annoncé en schéma de stratégie 3 avec sa courbe (\`ECDSA_P256\`, \`ECDSA_P384\`, \`ECDSA_P521\`) comme clé de signature et condensat de requête, le plus fort entre le condensat du template et celui de la courbe ; les templates RSA hors mode FIPS restent en schéma 2, qui ne nomme aucun condensat de requête : Windows signe alors sa requête CMC en SHA-1, ce qu'UCM accepte comme l'exigent ces clients ; une PKCS#10 simple signée en SHA-1 reste refusée. La clé de la requête doit convenir au template sous lequel elle est émise : même courbe ou même jeu ML-DSA, ou clé RSA au moins aussi longue (v2.251).

Une requête qui nomme son template, par OID (\`szOID_CERTIFICATE_TEMPLATE\`) ou par nom (\`szOID_ENROLL_CERTTYPE\`), est émise sous ce template ; un template que la CA n'offre pas ou inactif, deux noms pour deux templates, ou des EKU que le template n'émet pas sont refusés. Chaque stratégie annonce l'extension \`szOID_CERTIFICATE_TEMPLATE\` de son template, que Windows CertEnroll copie dans sa requête, ce qui distingue deux templates aux EKU identiques (v2.252). Une requête qui n'en nomme aucun est appariée à un template par ses EKU. Un template dont tous les EKU ne sont jamais émis à un inscrit, comme la signature OCSP, n'est pas annoncé, et une requête pour lui est refusée. Le certificat porte les EKU de son template, pas ceux que la requête demande.

WSTEP ne sert que le type de requête Issue, renouvellements compris, et refuse un message dont le \`wsu:Timestamp\` a expiré depuis plus de 5 minutes. Une PKCS#10 simple ou une requête CMC est reconnue à son contenu quel que soit son ValueType, et chaque réponse porte la CMC Full PKI Response à côté du certificat.

### Kerberos / SPNEGO

Lie les points de terminaison XCEP/WSTEP authentifiés par Kerberos utilisés pour l'auto-inscription GPO silencieuse, afin que les machines et les utilisateurs soient authentifiés par leur ticket Kerberos plutôt que par une invite d'identifiants :
- **Nom de principal de service (SPN)** : p. ex. \`HTTP/ucm.exemple.fr@EXEMPLE.FR\`, commun à tous les profils avec les interrupteurs XCEP, WSTEP et Kerberos
- **Keytab** : Un par profil, généré avec \`ktpass\` ou \`ktutil\` sur le contrôleur de domaine de son realm. Chaque entrée doit être \`HTTP/<hôte>@<realm du profil>\` ; le formulaire liste par realm les entrées du fichier choisi et signale un realm qui n'est pas celui du profil. Les keytabs de tous les profils sont servis comme un seul fichier

> ⚠ Kerberos nécessite le **backend \`gssapi\`** côté serveur (la bibliothèque Python \`gssapi\` plus les bibliothèques Kerberos système) : le paquet SPNEGO de base seul ne suffit pas. Sans lui, l'authentification Kerberos ne fonctionnera pas même si elle est activée ici, et la liaison Kerberos n'est pas annoncée ; un avertissement s'affiche sur l'onglet.

Les images Docker embarquent ce backend depuis la v2.251.

### URL de stratégie d'inscription

Les mêmes pour tous les profils : le routage se fait par realm, pas par URL.
- **Nom d'utilisateur/Mot de passe** : Demande des identifiants ; pour l'inscription interactive « Demander un nouveau certificat », ne nécessite pas Active Directory
- **Kerberos** : Aucune invite d'identifiants ; nécessite un client joint au domaine et une configuration GPO

### Liaison de renouvellement par certificat

En plus de Nom d'utilisateur/Mot de passe et Kerberos, WSTEP prend en charge le **renouvellement par certificat client**, à l'image des vrais endpoints CES d'ADCS : la requête de renouvellement (RST) doit être signée en XML-DSig avec la clé privée d'un certificat **émis par UCM lui-même**. Le certificat présenté est comparé **octet par octet** au certificat stocké pour la CA configurée, le numéro de série ou le sujet seuls ne suffisent jamais. Cela permet aux clients Windows de renouveler sans surveillance avec leur certificat actuel, sans identifiants ni ticket Kerberos.

XML-DSig n'a pas de méthode de signature ML-DSA : un certificat **ML-DSA** ne peut donc pas se renouveler ainsi, UCM nomme la clé dans son refus et le client inscrit un nouveau certificat.

Le renouvellement par certificat ne sert que les certificats émis par l'inscription Windows (WSTEP) ; un certificat signé à la main est remplacé par une nouvelle inscription, pas renouvelé. Sous TLS, le certificat à renouveler est le certificat client : activez mTLS avec l'AC WSTEP, ou l'un de ses ancêtres, en confiance. Un renouvellement conserve le template et les EKU du certificat renouvelé (v2.248). Un certificat que l'écouteur ne reconnaît pas est refusé pendant la poignée de main TLS, avant que UCM voie une requête : UCM n'audite rien (lire la sortie du client et le journal du service). Un profil hors de l'AC mTLS ne renouvelle que par Kerberos, et si Kerberos refuse (demandeur retiré du groupe AD, profil désactivé), il ne renouvelle pas.

### Extension de sécurité SID (KB5014754)

Lors d'une **émission authentifiée par Kerberos**, UCM intègre le SID AD du demandeur dans l'extension de sécurité SID de Microsoft (\`szOID_NTDS_CA_SECURITY_EXT\`) du certificat émis. Les contrôleurs de domaine l'utilisent pour le **mappage fort de certificats** (KB5014754) : requis depuis l'application par AD du mappage fort pour l'authentification par certificat (connexion par carte à puce, PKINIT). Un renouvellement WSTEP, EST ou SCEP reprend l'extension SID du certificat qu'il renouvelle, jamais celle de la CSR ; si le connecteur AD est activé, ce SID doit encore désigner un compte de l'annuaire.

### Sujets dérivés d'AD

Un modèle de certificat peut choisir **Construire le sujet depuis Active Directory** (Modèles → Inscription) : pour l'auto-inscription GPO sans surveillance, le sujet et le SAN sont dérivés de l'objet AD du demandeur via le connecteur AD au lieu d'exiger que le client en fournisse un -- correspond à la configuration d'un modèle ADCS réel pour l'auto-inscription. Indépendamment, **Autoriser l'auto-inscription** annonce le modèle comme \`autoEnroll=true\` dans la stratégie d'inscription de certificats, afin que les clients authentifiés par GPO/Kerberos le demandent automatiquement à la connexion.

## À propos

- **Informations système**, **Liens & Ressources** et le lien **Soutenir UCM** mènent à Ko-fi. Les administrateurs voient aussi une carte Ko-fi masquable une fois par version d'UCM
- **Vérifier la préparation à FIPS** (admin:system) : liste ce que le mode FIPS refuserait sur cette instance (hachages de mots de passe scrypt, autorités Ed25519, sauvegardes Argon2id, PostgreSQL sans TLS...), avec un remède pour chacun. Rien n'est modifié
`
  }
}
