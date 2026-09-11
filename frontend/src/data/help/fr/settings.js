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
          { label: "Admin", text: "admin.ucm.example.com — GUI et API (mTLS selon politique)" },
          { label: "ACME", text: "acme.ucm.example.com — /acme/* et /acme/proxy/* (sans mTLS client)" },
          { label: "TLS wildcard", text: "Nom concret (ex. acme.ucm.example.com). Un SAN *.ucm.example.com sur le certificat couvre le TLS admin et ACME — ne pas saisir *.ucm.example.com comme vhost" },
          { label: "Avant enregistrement", text: "DNS et TLS opérationnels pour le vhost ACME — les clients basculent les URL du directory immédiatement" },
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
        content: "Paramètres › Système liste les tâches d'arrière-plan avec leur statut et leur dernière exécution.",
        items: [
          { label: "Tâches", text: "Vérifications d'expiration, rafraîchissement CRL, livraison webhooks, sauvegardes planifiées, renouvellement auto, etc." },
          { label: "Exécuter", text: "Déclencher n'importe quelle tâche à la demande" },
          { label: "Visibilité", text: "Dernière exécution, dernière durée et nombre d'échecs par tâche" },
        ]
      },
      {
        title: "Sauvegardes planifiées",
        content: "Sauvegardes chiffrées et automatiques de la base de données, à cadence configurable et avec rétention.",
        items: [
          { label: "Cadence", text: "Quotidienne / hebdomadaire / mensuelle" },
          { label: "Rétention", text: "Conserver les N sauvegardes les plus récentes ; les plus anciennes sont purgées" },
          { label: "Chiffrement", text: "Les sauvegardes sont chiffrées avec le mot de passe de sauvegarde configuré" },
        ]
      },
      {
        title: "Mises à jour automatiques (v2.215)",
        content: "Paramètres › Mises à jour : vérification quotidienne en arrière-plan des nouvelles versions, et installation sans surveillance optionnelle.",
        items: [
          { label: "Canal", text: "« Versions stables » ne suit que les releases finales ; « Versions candidates » n'accepte en plus que les versions rcN — jamais les alpha/bêta" },
          { label: "Notification", text: "Une version nouvellement disponible déclenche l'événement webhook/e-mail system.update_available, une fois par version" },
          { label: "Installation auto", text: "Désactivée par défaut. Une fois activée, UCM télécharge, vérifie et installe la mise à jour à l'heure choisie, puis redémarre — installations DEB/RPM uniquement" },
          { label: "Somme de contrôle", text: "Une installation sans surveillance exige le SHA256 publié de la release pour vérification ; une installation manuelle vérifie aussi dès qu'une somme de contrôle est publiée" },
          { label: "Docker", text: "Les conteneurs ne peuvent pas se mettre à jour eux-mêmes — la vérification et la notification fonctionnent toujours ; récupérez la nouvelle image pour mettre à jour" },
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
          { label: 'Général', text: 'Nom de l\'instance, nom d\'hôte et valeurs par défaut à l\'échelle du système' },
          { label: 'Apparence', text: 'Sélection du thème (clair/sombre/système), couleur d\'accentuation, mode bureau' },
          { label: 'E-mail (SMTP)', text: 'Serveur SMTP, identifiants, éditeur de modèle d\'e-mail et notifications d\'alerte d\'expiration' },
          { label: 'Sécurité', text: 'Politiques de mot de passe, délai d\'expiration de session, limitation de débit, restrictions IP' },
          { label: 'SSO', text: 'Intégration d\'authentification unique SAML 2.0, OAuth2/OIDC et LDAP' },
          { label: 'Sauvegarde', text: 'Sauvegardes de base de données manuelles et programmées' },
          { label: 'Audit', text: 'Rétention des journaux, transfert syslog, vérification d\'intégrité' },
          { label: 'Base de données', text: 'Backend actif (SQLite ou PostgreSQL), taille, nombre de tables, tester/basculer/migrer entre les backends' },
          { label: 'HTTPS', text: 'Certificat TLS pour l\'interface web UCM. Le certificat appliqué est mémorisé et réappliqué lors de son renouvellement (v2.217) ; le certificat lié est affiché avec un bouton pour le délier et ne plus suivre les renouvellements (v2.218)' },
          { label: 'Mises à jour', text: 'Vérifier les nouvelles versions, voir le journal des modifications, vérification quotidienne planifiée avec installation sans surveillance en opt-in (DEB/RPM)' },
          { label: 'Webhooks', text: 'Webhooks HTTP pour les événements de certificat (émission, révocation, expiration). Authentification sortante optionnelle : Bearer, Basic, API key ou en-tête personnalisé' },
          { label: 'Déploiement', text: "Cibles de déploiement : hôtes distants vers lesquels les certificats sont poussés en SSH/SFTP à l'émission et au renouvellement, avec une commande de rechargement fixe (réservé aux admins, v2.215)" },
          { label: 'Active Directory', text: "Connexion AD/LDAP propre à UCM pour les recherches liées aux certificats (résolution de principal Kerberos, sujets dérivés d'AD)" },
          { label: 'Auto-inscription Windows', text: 'Inscription Windows native MS-XCEP/MS-WSTEP : découverte de stratégie, émission de certificats et liaison Kerberos/SPNEGO' },
        ]
      },
      {
        title: 'Hooks de déploiement (v2.215)',
        content: "Paramètres › Déploiement (réservé aux admins) : hôtes distants vers lesquels UCM pousse les certificats en SFTP, puis exécute une commande de rechargement fixe en SSH.",
        items: [
          { label: 'Cible', text: "Hôte, port, utilisateur SSH. UCM génère une clé ed25519 (installez la clé publique affichée sur la cible) ou accepte une clé privée importée — stockée chiffrée" },
          { label: "Clé d'hôte", text: "Épinglée à la première connexion réussie (trust-on-first-use) ; tout changement ultérieur fait échouer la connexion. Changer l'hôte ré-épingle la clé" },
          { label: 'Commande de rechargement', text: "Une commande fixe, définie par l'admin, exécutée après un envoi réussi (par ex. systemctl reload nginx) — exit 0 = succès, pas de templating" },
          { label: 'Liaisons', text: "Les certificats sont attachés aux cibles depuis le panneau de détails du certificat, avec des chemins de destination par fichier" },
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
          { label: 'Champs', text: 'Serveur, port, LDAPS avec vérification AC facultative, DN de base, DN de liaison/mot de passe' },
          { label: 'Tester la connexion', text: "Vérifier la connectivité et les identifiants avant d'enregistrer" },
          { label: "URL d'inscription GPO", text: "URL de stratégie d'inscription de certificats Kerberos et Nom d'utilisateur/Mot de passe à enregistrer dans la stratégie de groupe" },
        ]
      },
      {
        title: 'Auto-inscription Windows (XCEP/WSTEP)',
        content: "Inscription de certificats Windows native via la découverte de stratégie MS-XCEP et l'émission MS-WSTEP -- prend en charge l'inscription manuelle MMC/certreq et l'auto-inscription GPO sans surveillance.",
        items: [
          { label: 'XCEP', text: "Permet aux clients Windows de découvrir les modèles de certificat disponibles avant l'inscription" },
          { label: 'WSTEP', text: 'Gère la demande et le renouvellement du certificat une fois la stratégie découverte' },
          { label: 'Kerberos/SPNEGO', text: "Lie les points de terminaison authentifiés par Kerberos utilisés pour l'auto-inscription GPO silencieuse (nécessite un SPN et un keytab du contrôleur de domaine)" },
          { label: 'Liste de contrôle de configuration', text: "L'onglet affiche une liste de contrôle en direct de ce qui est configuré par rapport à ce qui manque encore, pour l'inscription manuelle et sans surveillance" },
          { label: "Sujets dérivés d'AD", text: "Les modèles peuvent choisir de dériver leur sujet/SAN depuis Active Directory (via le connecteur AD) pour l'inscription sans surveillance" },
        ]
      },
      {
        title: 'Renouvellement automatique',
        items: [
          { label: 'Sources', text: 'Le planificateur renouvelle les certificats dont le serveur détient la clé privée : par défaut ceux émis depuis le formulaire ou une requête signée (« manual »), ainsi que les enrôlements SCEP, ACME et EST à clé générée par le serveur. Les appareils qui détiennent leur propre clé se renouvellent via leur protocole' },
          { label: 'En attente d\'approbation', text: 'Un certificat dont le renouvellement est en file d\'approbation est laissé à cette décision, tant qu\'elle peut intervenir avant l\'expiration du certificat' },
          { label: 'Renouvelé entre-temps', text: 'Un certificat qu\'un opérateur a renouvelé pendant le lot n\'est pas renouvelé une seconde fois ; un certificat supprimé pendant le lot est ignoré' },
        ]
      },

    ],
    tips: [
      'Utilisez le widget État du système en haut pour vérifier rapidement la santé des services',
      'Testez les paramètres SMTP avant de vous fier aux notifications par e-mail',
      'Personnalisez le modèle d\'e-mail avec votre marque à l\'aide de l\'éditeur HTML/Texte intégré',
      'Programmez des sauvegardes automatiques pour les environnements de production',
      'Le basculement SQLite ↔ PostgreSQL est bidirectionnel — l\'UI exécute des contrôles de sûreté (driver chargé, cible joignable, cible vide) avant migration',
    ],
    warnings: [
      'Le changement du certificat HTTPS nécessite un redémarrage du service',
      'La modification des paramètres de sécurité peut verrouiller les utilisateurs — vérifiez l\'accès avant d\'enregistrer',
    ],
  },
  helpGuides: {
    title: 'Paramètres',
    content: `
## Vue d'ensemble

Configuration à l'échelle du système organisée en onglets. Les modifications prennent effet immédiatement sauf indication contraire.

## Général

- **Nom de l'instance** — Affiché dans le titre du navigateur et les e-mails
- **Nom d'hôte** — Le nom de domaine pleinement qualifié du serveur
- **Validité par défaut** — Période de validité par défaut des certificats en jours
- **Seuil d'alerte d'expiration** — Jours avant l'expiration pour déclencher des avertissements
- **Vhost ACME public** — Nom d'hôte concret dans les URL du directory ACME (ex. \`acme.ucm.example.com\`, pas \`*.ucm.example.com\`). Un **SAN de certificat TLS** wildcard \`*.ucm.example.com\` couvre à la fois \`admin.ucm.example.com\` et \`acme.ucm.example.com\`. Configurez le DNS et le TLS du vhost ACME **avant** d'enregistrer : les clients qui relisent le directory basculent immédiatement d'URL.

## Apparence

- **Thème** — Clair, Sombre ou Système (suit la préférence du système d'exploitation)
- **Couleur d'accentuation** — Couleur principale utilisée pour les boutons, liens et mises en évidence
- **Forcer le mode bureau** — Désactiver la disposition mobile responsive
- **Comportement de la barre latérale** — Repliée ou étendue par défaut

## E-mail (SMTP)

Configurez SMTP pour les notifications par e-mail (alertes d'expiration, invitations d'utilisateurs) :
- **Hôte SMTP** et **Port**
- **Nom d'utilisateur** et **Mot de passe**
- **Chiffrement** — Aucun, STARTTLS ou SSL/TLS
- **Adresse d'expédition** — Adresse e-mail de l'expéditeur
- **Type de contenu** — HTML, texte brut ou les deux
- **Destinataires des alertes** — Ajoutez plusieurs destinataires en utilisant le champ de tags

Cliquez sur **Tester** pour envoyer un e-mail de test et vérifier la configuration.

### Éditeur de modèle d'e-mail

Cliquez sur **Modifier le modèle** pour ouvrir l'éditeur de modèle en panneau divisé dans une fenêtre flottante :
- **Onglet HTML** — Modifiez le modèle d'e-mail HTML avec aperçu en direct à droite
- **Onglet Texte brut** — Modifiez la version texte brut pour les clients e-mail qui ne prennent pas en charge HTML
- Variables disponibles : \`{{title}}\`, \`{{content}}\`, \`{{datetime}}\`, \`{{instance_url}}\`, \`{{logo}}\`, \`{{title_color}}\`
- Cliquez sur **Rétablir les valeurs par défaut** pour restaurer le modèle UCM intégré
- La fenêtre est redimensionnable et déplaçable pour un édition confortable

### Alertes d'expiration

Lorsque SMTP est configuré, activez les alertes automatiques d'expiration de certificats :
- Basculez les alertes on/off
- Sélectionnez les seuils d'avertissement (90j, 60j, 30j, 14j, 7j, 3j, 1j)
- Lancez **Vérifier maintenant** pour déclencher une analyse immédiate

## Sécurité

### Politique de mot de passe
- Longueur minimale (8-32 caractères)
- Exiger majuscules, minuscules, chiffres, caractères spéciaux
- Expiration du mot de passe (jours)
- Historique des mots de passe (empêcher la réutilisation)

### Gestion de session
- Délai d'expiration de session (minutes d'inactivité)
- Sessions simultanées maximales par utilisateur

### Limitation de débit
- Limite de tentatives de connexion par IP
- Durée de verrouillage après dépassement de la limite

### Restrictions IP
Autoriser ou refuser l'accès depuis des adresses IP ou plages CIDR spécifiques.

### Application de la 2FA
Exiger que tous les utilisateurs activent l'authentification à deux facteurs.

### Chiffrement des clés privées
Chiffrez toutes les clés privées stockées en base de données avec AES-256, protégées par un fichier de clé maîtresse. La section affiche l'état du chiffrement et les compteurs de clés **chiffrées / non chiffrées**. Deux variables d'environnement opt-in rendent l'absence de clé fatale au démarrage : \`UCM_REQUIRE_DB_ENCRYPTION_KEY\` (chiffrement des secrets d'intégration) et \`UCM_REQUIRE_KEY_ENCRYPTION\` (chiffrement des clés privées).

> 💡 Les paramètres sensibles (session, verrouillage, HSTS, URL publique, politique de mot de passe) exigent la permission **admin:settings** — les champs sont verrouillés pour les opérateurs.

> ⚠ Testez les restrictions IP soigneusement avant de les appliquer. Des règles incorrectes peuvent verrouiller tous les utilisateurs.

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
Cliquez sur **Créer une sauvegarde** pour générer un instantané de la base de données. Les sauvegardes incluent tous les certificats, CA, clés, paramètres et journaux d'audit.

### Sauvegarde programmée
Configurez des sauvegardes automatiques :
- Fréquence (quotidienne, hebdomadaire, mensuelle)
- Nombre de rétention (nombre de sauvegardes à conserver)

### Restauration
Téléversez un fichier de sauvegarde pour restaurer UCM à un état précédent.

> ⚠ La restauration d'une sauvegarde remplace TOUTES les données actuelles.

## Audit

- **Rétention des journaux** — Nettoyage automatique des anciens journaux après N jours
- **Transfert syslog** — Envoyer les événements à un serveur syslog distant (UDP/TCP/TLS)
- **Vérification d'intégrité** — Activer le chaînage de hachages pour la détection d'altération

## Base de données

UCM prend en charge deux backends de base de données :

- **SQLite** (par défaut) — basé sur fichier, sans configuration, idéal pour un nœud unique
- **PostgreSQL 13+** — recommandé pour la haute disponibilité, le multi-instance ou si vous opérez déjà un cluster PG géré

Le backend actif est sélectionné par la variable d'environnement \`DATABASE_URL\`. Si elle n'est pas définie, UCM utilise SQLite dans \`UCM_DATA_DIR/ucm.db\`.

### Panneau d'état
- Backend actif (sqlite / postgresql) et pilote
- Taille de la base et nombre de tables
- Version de migration

### Tester la connexion
Validez une \`DATABASE_URL\` (ex. \`postgresql://user:pass@host:5432/ucm\`) avant de basculer. Le test ouvre une vraie connexion et signale toute erreur. Les serveurs PostgreSQL antérieurs à la version 13 sont rejetés — UCM nécessite PostgreSQL 13 ou plus récent.

### Basculer le backend
Persiste \`DATABASE_URL\` dans \`/etc/ucm/ucm.env\` (DEB/RPM) et redémarre UCM. **Aucune donnée n'est copiée** — utilisez **Migrer** d'abord si vous voulez conserver vos données existantes.

### Migrer les données
Copie toutes les lignes du backend actuel vers le backend cible. Fonctionne dans les deux sens (SQLite ↔ PostgreSQL) :

1. La base source est sauvegardée dans \`/opt/ucm/data/backups/db_migration/\`
2. Le schéma est créé sur la cible via SQLAlchemy
3. Les contraintes FK sont désactivées pendant le chargement
4. Les colonnes source/cible sont intersectées (les colonnes héritées sont ignorées avec un avertissement)
5. Les séquences PostgreSQL sont réinitialisées après le chargement
6. Le service redémarre automatiquement (DEB/RPM) — sur Docker, définissez \`DATABASE_URL\` dans votre fichier compose et redémarrez le conteneur manuellement

**Contrôles de sécurité (échec rapide, source intacte) :**
- La cible doit être vide. Si \`users\`, \`cas\` ou \`certificates\` contiennent déjà des lignes, la migration est refusée avec un HTTP 409 et un indice de nettoyage :
  - PostgreSQL : \`psql ... -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'\`
  - SQLite : supprimez le fichier cible \`.db\`
- Si la migration échoue en cours de route, la source est intacte et le message d'erreur indique la sauvegarde source. Réinitialisez la cible avant de réessayer.

> ⚠ Effectuez toujours une sauvegarde complète d'UCM (Paramètres → Sauvegarde) avant de migrer entre backends.

## HTTPS

Gérez le certificat TLS utilisé par l'interface web UCM :
- Voir les détails du certificat actuel
- Importer un nouveau certificat (PEM ou PKCS#12)
- Générer un certificat auto-signé

> ⚠ Le changement du certificat HTTPS nécessite un redémarrage du service.

## Mises à jour

- Vérifier les nouvelles versions UCM depuis les releases GitHub
- Voir le journal des modifications pour les mises à jour disponibles
- Version actuelle et informations de build
- **Mise à jour automatique** : sur les installations prises en charge (DEB/RPM), cliquez sur **Mettre à jour maintenant** pour télécharger et installer automatiquement la dernière version
- **Inclure les pré-versions** : basculez pour également vérifier les versions candidates (rc)

## Webhooks

Configurez des webhooks HTTP pour notifier les systèmes externes lors d'événements :

### Événements pris en charge
- Certificat émis, révoqué, expiré, renouvelé
- CA créée, supprimée
- Connexion utilisateur, déconnexion
- Sauvegarde créée

### Authentification

Authentification sortante optionnelle (s'ajoute à la signature HMAC optionnelle) :

- **Aucune** — Pas d'en-tête d'authentification (webhooks publics)
- **Bearer** — Authorization: Bearer {token}
- **Basic** — Authorization: Basic base64(utilisateur:motdepasse)
- **Clé API** — En-tête personnalisé (p.ex. X-Api-Key: {token})
- **Personnalisée** — Authorization: {schéma} {token} (p.ex. auth-key VALEUR)

Les tokens sont stockés chiffrés et jamais renvoyés dans l'UI.

### Créer un webhook
1. Cliquez sur **Ajouter un webhook**
2. Entrez l'**URL** (doit être HTTPS)
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

Paramètres › Système expose les tâches d'arrière-plan.

- Liste des tâches avec **statut**, **dernière exécution**, **durée** et **échecs**
- **Exécuter maintenant** sur n'importe quelle tâche
- Couvre expiration, CRL, livraison webhooks, sauvegardes, renouvellement auto…

## Renouvellement automatique

Les paramètres de renouvellement automatique pilotent le planificateur de renouvellement.

- **Sources** — le planificateur renouvelle les certificats dont le serveur détient la clé privée : par défaut ceux émis depuis le formulaire ou une requête signée (« manual »), ainsi que les enrôlements SCEP, ACME et EST à clé générée par le serveur. Les appareils qui détiennent leur propre clé se renouvellent via leur protocole
- **En attente d'approbation** — un certificat dont le renouvellement est en file d'approbation est laissé à cette décision, tant qu'elle peut intervenir avant l'expiration du certificat
- **Renouvelé entre-temps** — un certificat qu'un opérateur a renouvelé pendant le lot n'est pas renouvelé une seconde fois ; un certificat supprimé pendant le lot est ignoré

## Sauvegardes planifiées

Paramètres › Sauvegarde permet des sauvegardes automatiques.

- Cadence **quotidienne / hebdomadaire / mensuelle**
- **Rétention** : conserve les N plus récentes, purge les anciennes
- Sauvegardes **chiffrées** avec le mot de passe de sauvegarde


## Connecteur Active Directory

Connexion LDAP propre à UCM à Active Directory, indépendante de tout fournisseur LDAP configuré sous SSO. Celui-ci sert à se connecter à UCM ; celui-ci est utilisé pour les recherches AD liées aux certificats et fonctionne indépendamment du fait que le SSO soit configuré ou non.

- **Objectif** — Résout un principal de machine ou d'utilisateur Kerberos vers son objet AD, afin qu'UCM puisse dériver un sujet/SAN de certificat comme le ferait une vraie AC Windows
- **Serveur** — Nom d'hôte/IP et port d'un contrôleur de domaine
- **LDAPS** — Activer pour utiliser LDAP sur SSL/TLS ; **Vérifier le certificat SSL** valide le certificat du DC (éventuellement par rapport à un bundle d'AC personnalisé lorsqu'il n'est pas approuvé publiquement)
- **DN de base** et **DN de liaison / Mot de passe** — Identifiants du compte de service utilisés pour les recherches
- **Tester la connexion** — Vérifier la connectivité et les identifiants avant d'enregistrer

### URL de stratégie d'inscription GPO

Une fois configuré, enregistrez l'une des URL affichées comme serveur de stratégie d'inscription de certificats dans la stratégie de groupe (Stratégies de clé publique → Client des services de certificats – Stratégie d'inscription de certificats), avec Client des services de certificats – Inscription automatique :
- **Kerberos** — Aucune invite d'identifiants ; nécessite un client joint au domaine et le type d'authentification de la GPO défini sur Kerberos
- **Nom d'utilisateur/Mot de passe** — Demande des identifiants ; pour l'inscription interactive « Demander un nouveau certificat » uniquement

## Auto-inscription Windows (XCEP/WSTEP)

Inscription de certificats Windows native via **MS-XCEP** (découverte de stratégie) et **MS-WSTEP** (émission et renouvellement de certificats) -- les mêmes protocoles qu'un vrai ADCS utilise pour l'inscription interactive « Demander un nouveau certificat » dans MMC, \`certreq\`, et l'auto-inscription GPO sans surveillance.

### Liste de contrôle de configuration

L'onglet suit ce qui est configuré par rapport à ce qui manque encore, pour les parcours d'inscription manuelle et sans surveillance -- une autorité de certification, la découverte de stratégie (XCEP), l'émission de certificats (WSTEP) et, pour l'auto-inscription GPO sans surveillance, un connecteur Active Directory, Kerberos/SPNEGO et au moins un modèle avec l'auto-inscription autorisée.

### Découverte de stratégie (XCEP)

- **Autorité de certification** — L'AC dont les modèles sont annoncés et qui émet des certificats via cette configuration
- **Validité (jours)** — Validité par défaut appliquée aux certificats émis via WSTEP

### Kerberos / SPNEGO

Lie les points de terminaison XCEP/WSTEP authentifiés par Kerberos utilisés pour l'auto-inscription GPO silencieuse, afin que les machines et les utilisateurs soient authentifiés par leur ticket Kerberos plutôt que par une invite d'identifiants :
- **Nom de principal de service (SPN)** — p. ex. \`HTTP/ucm.exemple.fr@EXEMPLE.FR\`
- **Keytab** — Généré avec \`ktpass\` ou \`ktutil\` sur le contrôleur de domaine pour le SPN ci-dessus

> ⚠ Kerberos nécessite le **backend \`gssapi\`** côté serveur (la bibliothèque Python \`gssapi\` plus les bibliothèques Kerberos système) — le paquet SPNEGO de base seul ne suffit pas. Sans lui, l'authentification Kerberos ne fonctionnera pas même si elle est activée ici, et la liaison Kerberos n'est pas annoncée ; un avertissement s'affiche sur l'onglet.

### URL de stratégie d'inscription

- **Nom d'utilisateur/Mot de passe** — Demande des identifiants ; pour l'inscription interactive « Demander un nouveau certificat », ne nécessite pas Active Directory
- **Kerberos** — Aucune invite d'identifiants ; nécessite un client joint au domaine et une configuration GPO

### Liaison de renouvellement par certificat

En plus de Nom d'utilisateur/Mot de passe et Kerberos, WSTEP prend en charge le **renouvellement par certificat client**, à l'image des vrais endpoints CES d'ADCS : la requête de renouvellement (RST) doit être signée en XML-DSig avec la clé privée d'un certificat **émis par UCM lui-même**. Le certificat présenté est comparé **octet par octet** au certificat stocké pour la CA configurée — le numéro de série ou le sujet seuls ne suffisent jamais. Cela permet aux clients Windows de renouveler sans surveillance avec leur certificat actuel, sans identifiants ni ticket Kerberos.

### Extension de sécurité SID (KB5014754)

Lors d'une **émission authentifiée par Kerberos**, UCM intègre le SID AD du demandeur dans l'extension de sécurité SID de Microsoft (\`szOID_NTDS_CA_SECURITY_EXT\`) du certificat émis. Les contrôleurs de domaine l'utilisent pour le **mappage fort de certificats** (KB5014754) — requis depuis l'application par AD du mappage fort pour l'authentification par certificat (connexion par carte à puce, PKINIT).

### Sujets dérivés d'AD

Un modèle de certificat peut choisir **Construire le sujet depuis Active Directory** (Modèles → Inscription) : pour l'auto-inscription GPO sans surveillance, le sujet et le SAN sont dérivés de l'objet AD du demandeur via le connecteur AD au lieu d'exiger que le client en fournisse un -- correspond à la configuration d'un modèle ADCS réel pour l'auto-inscription. Indépendamment, **Autoriser l'auto-inscription** annonce le modèle comme \`autoEnroll=true\` dans la stratégie d'inscription de certificats, afin que les clients authentifiés par GPO/Kerberos le demandent automatiquement à la connexion.
`
  }
}
