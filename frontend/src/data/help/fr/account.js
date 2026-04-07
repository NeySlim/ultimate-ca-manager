export default {
  helpContent: {
    title: 'Mon compte',
    subtitle: 'Paramètres personnels et sécurité',
    overview: 'Gérez votre profil, vos paramètres de sécurité et vos clés API. Activez l\'authentification à deux facteurs et enregistrez des clés de sécurité pour une protection renforcée du compte.',
    sections: [
      {
        title: 'Profil',
        items: [
          { label: 'Nom complet', text: 'Votre nom d\'affichage affiché dans toute l\'application' },
          { label: 'E-mail', text: 'Utilisé pour les notifications et la récupération de compte' },
          { label: 'Infos du compte', text: 'Date de création, dernière connexion, nombre total de connexions' },
        ]
      },
      {
        title: 'Sécurité',
        items: [
          { label: 'Mot de passe', text: 'Changer votre mot de passe actuel' },
          { label: '2FA (TOTP)', text: 'Activer les mots de passe à usage unique basés sur le temps via une application d\'authentification' },
          { label: 'Clés de sécurité', text: 'Enregistrer des clés WebAuthn/FIDO2 (YubiKey, empreinte digitale, etc.)' },
          { label: 'mTLS', text: 'Gérer les certificats client pour l\'authentification TLS mutuel' },
        ]
      },
      {
        title: 'Clés API',
        items: [
          { label: 'Créer une clé', text: 'Générer une nouvelle clé API avec expiration optionnelle' },
          { label: 'Permissions', text: 'Les clés API héritent des permissions de votre rôle' },
          { label: 'Révoquer', text: 'Invalider immédiatement une clé API' },
        ]
      },
    ],
    tips: [
      'Activez au moins un second facteur (TOTP ou clé de sécurité) pour les comptes admin',
      'Les clés API peuvent être limitées avec une date d\'expiration pour les intégrations de courte durée',
      'Scannez le code QR avec n\'importe quelle application TOTP : Google Authenticator, Authy, 1Password, etc.',
    ],
  },
  helpGuides: {
    title: 'Mon compte',
    content: `
## Vue d'ensemble

Gérez votre profil personnel, vos paramètres de sécurité et vos clés API.

## Profil

- **Nom complet** — Votre nom d'affichage affiché dans UCM
- **E-mail** — Utilisé pour les notifications, la récupération de mot de passe et l'enregistrement ACME
- **Infos du compte** — Date de création, horodatage de la dernière connexion, nombre total de connexions

## Sécurité

### Changement de mot de passe
Changez votre mot de passe actuel. Doit respecter la politique de mot de passe du système (longueur minimale, exigences de complexité).

### Authentification à deux facteurs (TOTP)
Ajoutez un mot de passe à usage unique basé sur le temps à l'aide de n'importe quelle application d'authentification :

1. Cliquez sur **Activer la 2FA**
2. Scannez le code QR avec votre application d'authentification (Google Authenticator, Authy, 1Password, etc.)
3. Entrez le code à 6 chiffres pour confirmer
4. Sauvegardez les **codes de récupération** — ils ne sont affichés qu'une seule fois

> ⚠ Si vous perdez l'accès à votre application d'authentification et aux codes de récupération, un administrateur devra désactiver votre 2FA.

### Clés de sécurité (WebAuthn/FIDO2)
Enregistrez des clés de sécurité matérielles ou des authentificateurs biométriques :
- YubiKey
- Lecteur d'empreinte digitale
- Windows Hello
- Touch ID

1. Cliquez sur **Enregistrer une clé de sécurité**
2. Entrez un nom pour la clé
3. Suivez l'invite du navigateur pour vous authentifier
4. La clé apparaît dans la liste de vos identifiants enregistrés

### Certificats mTLS
Gérez les certificats client pour l'authentification TLS mutuel :
- Téléverser un certificat client
- Télécharger vos certificats enregistrés
- Supprimer les anciens certificats

## Clés API

### Créer une clé API
1. Cliquez sur **Créer une clé API**
2. Entrez un **nom** (descriptif, par ex. « Pipeline CI/CD »)
3. Définissez optionnellement une **date d'expiration**
4. Cliquez sur **Créer**
5. Copiez la clé immédiatement — elle n'est affichée qu'une seule fois

### Utiliser les clés API
Incluez la clé dans l'en-tête \`X-API-Key\` :

\`\`\`
X-API-Key: <votre-cle-api>
\`\`\`

### Permissions
Les clés API héritent des permissions du rôle de votre utilisateur. Elles ne peuvent pas avoir plus d'accès que votre compte.

### Révoquer des clés
Cliquez sur **Supprimer** pour invalider immédiatement une clé API. Les sessions actives utilisant la clé seront terminées.

> 💡 Utilisez des clés API de courte durée avec des dates d'expiration pour le CI/CD et l'automatisation.
`
  }
}
