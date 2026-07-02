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
          { label: 'HTTPS', text: 'Certificat TLS pour l\'interface web UCM' },
          { label: 'Mises à jour', text: 'Vérifier les nouvelles versions, voir le journal des modifications, mise à jour automatique (DEB/RPM)' },
          { label: 'Webhooks', text: 'Webhooks HTTP pour les événements de certificat (émission, révocation, expiration). Authentification sortante optionnelle : Bearer, Basic, API key ou en-tête personnalisé' },
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

## Sauvegardes planifiées

Paramètres › Sauvegarde permet des sauvegardes automatiques.

- Cadence **quotidienne / hebdomadaire / mensuelle**
- **Rétention** : conserve les N plus récentes, purge les anciennes
- Sauvegardes **chiffrées** avec le mot de passe de sauvegarde

`
  }
}
