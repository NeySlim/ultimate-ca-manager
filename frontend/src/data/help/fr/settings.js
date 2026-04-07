export default {
  helpContent: {
    title: 'Paramètres',
    subtitle: 'Configuration du système',
    overview: 'Configurez tous les aspects du système UCM. Les paramètres sont organisés par catégorie : général, apparence, e-mail, sécurité, SSO, sauvegarde, audit, base de données, HTTPS, mises à jour et webhooks.',
    sections: [
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
          { label: 'Base de données', text: 'Chemin de la base de données, taille et statut de migration' },
          { label: 'HTTPS', text: 'Certificat TLS pour l\'interface web UCM' },
          { label: 'Mises à jour', text: 'Vérifier les nouvelles versions, voir le journal des modifications, mise à jour automatique (DEB/RPM)' },
          { label: 'Webhooks', text: 'Webhooks HTTP pour les événements de certificat (émission, révocation, expiration)' },
        ]
      },
    ],
    tips: [
      'Utilisez le widget État du système en haut pour vérifier rapidement la santé des services',
      'Testez les paramètres SMTP avant de vous fier aux notifications par e-mail',
      'Personnalisez le modèle d\'e-mail avec votre marque à l\'aide de l\'éditeur HTML/Texte intégré',
      'Programmez des sauvegardes automatiques pour les environnements de production',
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

Informations sur la base de données UCM :
- Chemin sur le disque
- Taille du fichier
- Version de migration
- Version de SQLite

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

### Créer un webhook
1. Cliquez sur **Ajouter un webhook**
2. Entrez l'**URL** (doit être HTTPS)
3. Sélectionnez les **événements** auxquels s'abonner
4. Définissez optionnellement un **secret** pour la vérification de signature HMAC
5. Cliquez sur **Créer**

### Test
Cliquez sur **Tester** pour envoyer un événement exemple à l'URL du webhook et vérifier qu'il est accessible.
`
  }
}
