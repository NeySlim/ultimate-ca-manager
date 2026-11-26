export default {
  helpContent: {
    title: 'Mon compte',
    subtitle: 'Paramètres personnels et sécurité',
    overview: 'Gérez votre profil, vos paramètres de sécurité et vos clés API. Activez l’authentification à deux facteurs et enregistrez des clés de sécurité pour une protection renforcée du compte.',
    sections: [
      {
        title: 'Disposition de la page',
        content: 'Profil, sécurité et clés d’API sont sur une seule page, chacun dans son cadre ; le sommaire à gauche y mène (sur un téléphone, la liste Aller à la section).',
        items: [
          { label: 'Actions propres', text: 'Le nom et l’e-mail se modifient sur place : l’état d’enregistrement, dans l’en-tête de la page, au-dessus du formulaire (en bas de la page sur un téléphone), dit ce qui est modifié et non enregistré, Annuler les modifications remet les valeurs enregistrées et Enregistrer les envoie (Entrée dans un champ aussi) ; Créer une clé ouvre le formulaire de clé' },
          { label: 'Liens', text: 'Un lien vers /account?tab=security ou /account?tab=api-keys ouvre la page sur ce cadre' },
          { label: 'Modification gardée', text: 'Une modification du profil non enregistrée est marquée Modifié au sommaire, gardée dans cet onglet quand vous quittez la page et retrouvée à votre retour ; Annuler les modifications l’oublie' },
          { label: 'Préférences', text: 'Fermer l’inspecteur en naviguant : les objets ouverts dans l’inspecteur se ferment quand vous changez de page. Désactivé par défaut : ils restent ouverts, en onglets. Le choix est gardé dans ce navigateur' },
        ],
      },
      {
        title: 'Profil',
        items: [
          { label: 'Nom complet', text: 'Votre nom d’affichage affiché dans toute l’application' },
          { label: 'E-mail', text: 'Utilisé pour les notifications et la récupération de compte. Le modifier demande votre mot de passe, et un avis part vers l’ancienne adresse' },
          { label: 'Informations du compte', text: 'Date de création, dernière connexion, nombre total de connexions' },
        ]
      },
      {
        title: 'Sécurité',
        items: [
          { label: 'Mot de passe', text: 'Changer votre mot de passe actuel. Vos autres sessions sont fermées ; celle-ci reste ouverte' },
          { label: '2FA (TOTP)', text: 'Activer les mots de passe à usage unique basés sur le temps via une application d’authentification. La réactiver alors qu’elle est déjà active est refusé : désactivez-la d’abord. Chaque code ne fonctionne qu’une fois : après en avoir utilisé un, attendez le suivant pour confirmer une autre action' },
          { label: 'Clés de sécurité', text: 'Enregistrer des clés WebAuthn/FIDO2 (YubiKey, empreinte digitale, etc.). L’ajout d’une clé demande d’abord votre mot de passe, ou votre code d’authentification pour un compte sans mot de passe' },
          { label: 'mTLS', text: 'Gérer les certificats client pour l’authentification TLS mutuel. L’ajout d’un certificat demande d’abord votre mot de passe, ou votre code d’authentification pour un compte sans mot de passe' },
          { label: "Changement de mot de passe imposé (v2.245)", text: "Un compte à qui l’on a demandé un nouveau mot de passe, comme le premier administrateur dont UCM a généré le mot de passe au premier démarrage, ne peut rien faire d’autre tant qu’il ne l’a pas changé, API et WebSocket compris ; l’invite ne peut pas être ignorée et son seul autre bouton est Déconnexion. Ce changement supprime le fichier qui contenait le mot de passe généré. Un mot de passe fourni par INITIAL_ADMIN_PASSWORD ou INITIAL_ADMIN_PASSWORD_FILE n’a pas à être changé, sauf si INITIAL_ADMIN_PASSWORD_FORCE_CHANGE est défini (le chart Helm le définit pour le mot de passe qu’il génère)" },
        ]
      },
      {
        title: 'Clés API',
        items: [
          { label: 'Créer une clé', text: 'Générer une nouvelle clé API, expirant éventuellement après un nombre de jours' },
          { label: 'Permissions', text: 'Une clé porte le périmètre choisi à sa création, jamais plus que vos propres permissions. Une clé ne peut créer ou régénérer qu’une clé dont elle détient elle-même les permissions, expirant au plus tard comme elle. Régénérer, ce que seule l’API propose, conserve la durée de vie de la clé ; une clé révoquée ou expirée ne peut pas être régénérée' },
          { label: 'Révoquer', text: 'Invalider immédiatement une clé API' },
          { label: 'Gestion d’instance', text: 'Préréglage pour une console qui surveille plusieurs instances : lit l’état de l’instance et les réglages, lance une sauvegarde ou une mise à jour, rien d’autre. Proposé aux administrateurs seulement' },
          { label: 'Adresses sources autorisées', text: 'Adresses IP ou réseaux CIDR depuis lesquels la clé peut être utilisée ; depuis toute autre adresse la clé est refusée (403) et sa dernière utilisation n’est pas mise à jour. Une clé créée ou régénérée par une clé limitée reste dans ses réseaux. Vide : toute adresse' },
          { label: 'Utilisateurs désactivés', text: 'Les clés API appartenant à un utilisateur désactivé sont rejetées même si la clé elle-même est encore valide' },
          { label: 'Session interactive uniquement', text: 'Les clés API, même à accès complet, ne peuvent pas modifier votre profil, mot de passe, 2FA, clés de sécurité, certificats mTLS ou sessions, ni atteindre votre propre compte via les actions d’administration des utilisateurs : connectez-vous de façon interactive' },
        ]
      },
      {
        title: 'Préférences (synchronisées côté serveur)',
        content: 'Votre langue, famille de thème et mode (clair/sombre) sont persistés en base et vous suivent à travers les navigateurs et appareils :',
        items: [
          { label: 'Stocké', text: 'Dans users.preferences (JSON). Nouveaux endpoints GET/PUT /api/v2/account/preferences' },
          { label: 'Auto-appliqué', text: '/api/v2/auth/verify retourne vos préférences, appliquées au chargement de chaque page' },
          { label: 'Nouveau navigateur', text: 'Connexion depuis un nouvel appareil ou après nettoyage du site → vos langue et thème choisis sont restaurés, sans repli sur la langue du navigateur' },
        ]
      },

    ],
    tips: [
      'Activez au moins un second facteur (TOTP ou clé de sécurité) pour les comptes admin',
      'Les clés API peuvent expirer après un nombre de jours défini pour les intégrations de courte durée',
      'Les clés API peuvent aussi être créées sans expiration pour l’automatisation à long terme',
      'Scannez le code QR avec n’importe quelle application TOTP : Google Authenticator, Authy, 1Password, etc.',
      'Les sélections de filtres sur les principales pages liste (Certificats, AC, Modèles, Audit, Politiques, Magasin de confiance et autres) sont persistées au rechargement ; CSR, Approbations, Récupération de clés, Découverte et Journaux système démarrent sans filtre',
    ],
  },
  helpGuides: {
    title: 'Mon compte',
    content: `
## Vue d’ensemble

Gérez votre profil personnel, vos paramètres de sécurité et vos clés API.

## Profil

- **Nom complet** : Votre nom d’affichage affiché dans UCM
- **E-mail** : Utilisé pour les notifications et la récupération de mot de passe. Le modifier demande votre mot de passe, et un avis part vers l’ancienne adresse
- **Informations du compte** : Date de création, horodatage de la dernière connexion, nombre total de connexions

## Sécurité

### Changement de mot de passe
Changez votre mot de passe actuel. Doit respecter la politique de mot de passe du système (longueur minimale, exigences de complexité). Vos autres sessions sont fermées ; celle depuis laquelle vous l’avez changé reste ouverte. Une réinitialisation du mot de passe ou de la 2FA par un administrateur ferme toutes les sessions de l’utilisateur.

Lorsque UCM demande un nouveau mot de passe à la connexion (le compte \`admin\` du premier démarrage quand UCM a généré son mot de passe, par exemple), ce changement passe avant tout le reste : tant qu’il n’est pas fait, le serveur refuse toutes les autres requêtes de cette session, API comprise.

### Authentification à deux facteurs (TOTP)
Ajoutez un mot de passe à usage unique basé sur le temps à l’aide de n’importe quelle application d’authentification :

1. Cliquez sur **Activer la 2FA**
2. Scannez le code QR avec votre application d’authentification (Google Authenticator, Authy, 1Password, etc.)
3. Entrez le code à 6 chiffres pour confirmer
4. Sauvegardez les **codes de secours** : ils ne sont affichés qu’une seule fois

> ⚠ Si vous perdez l’accès à votre application d’authentification et aux codes de secours, un administrateur devra désactiver votre 2FA.

Pour migrer la 2FA vers une nouvelle application d’authentification, désactivez-la d’abord : la réactiver alors qu’elle est déjà active est refusé.
Chaque code n’est accepté qu’une fois (RFC 6238) : un code utilisé pour se connecter ne peut pas confirmer une autre action ni une seconde connexion, attendez donc le suivant.

### Clés de sécurité (WebAuthn/FIDO2)
Enregistrez des clés de sécurité matérielles ou des authentificateurs biométriques :
- YubiKey
- Lecteur d’empreinte digitale
- Windows Hello
- Touch ID

1. Cliquez sur **Ajouter une clé**
2. Entrez un nom pour la clé
3. Suivez l’invite du navigateur pour vous authentifier
4. La clé apparaît dans la liste de vos identifiants enregistrés

UCM demande d’abord votre mot de passe, ou le code de votre application d’authentification pour un compte sans mot de passe local : une clé ouvre une session à elle seule, une session laissée ouverte ne peut donc pas en ajouter. L’ajout d’un certificat mTLS demande de même.

Avec la 2FA activée ou imposée, une clé enregistrée peut aussi valider la seconde étape d’une connexion par mot de passe : choisissez **Utiliser la clé de sécurité**.

Sans application d’authentification, activez **Clé de sécurité comme second facteur** dans la section Authentification à deux facteurs : chaque connexion par mot de passe demande alors l’une de vos clés, et la dernière clé ne peut pas être supprimée tant que l’option est active.

### Certificats mTLS
Gérez les certificats client pour l’authentification TLS mutuel :
- Téléverser un certificat client
- Télécharger vos certificats enregistrés
- Supprimer les anciens certificats

## Clés API

### Créer une clé API
1. Cliquez sur **Créer une clé**
2. Entrez un **nom** (descriptif, par ex. « Pipeline CI/CD »)
3. Définissez optionnellement une expiration en **jours**
4. Cliquez sur **Créer**, puis confirmez avec votre mot de passe (ou votre code d’authentification pour un compte sans mot de passe) : une clé continue de fonctionner après un changement de mot de passe
5. Copiez la clé immédiatement : elle n’est affichée qu’une seule fois

### Utiliser les clés API
Incluez la clé dans l’en-tête \`X-API-Key\` :

\`\`\`
X-API-Key: <your-api-key>
\`\`\`

Ou envoyez-la comme jeton bearer : \`Authorization: Bearer <your-api-key>\`.

### Permissions
Chaque clé porte le périmètre choisi à sa création (**Accès complet**, **Lecture seule**, **Lecture et écriture**, **Certificats uniquement**) et jamais plus d’accès que votre compte. **Certificats uniquement** émet des certificats X.509 et SSH et lit les AC, les AC SSH et les CRL, mais ne peut ni créer ni modifier une AC. Une clé ne peut créer ou régénérer qu’une clé dont elle détient elle-même les permissions, et cette clé expire au plus tard avec celle qui la demande. Régénérer une clé, ce que seule l’API propose (\`POST /api/v2/account/apikeys/<id>/regenerate\`), conserve ses permissions et sa durée ; une clé révoquée ou expirée ne peut pas être régénérée.

Les clés API, même à accès complet, ne peuvent pas modifier votre profil, mot de passe, 2FA, clés de sécurité, certificats mTLS ou sessions, ni atteindre votre propre compte via les actions d’administration des utilisateurs : celles-ci exigent une session interactive.

### Gestion d’instance et adresses sources
Le préréglage **Gestion d’instance**, proposé aux administrateurs, donne à une clé ce dont a besoin une console qui surveille plusieurs instances : \`read:instance\` (\`GET /api/v2/system/instance\`), \`read:settings\`, \`write:backups\` et \`write:updates\`, sans \`admin:system\`. **Adresses sources autorisées** limite une clé à des adresses IP ou des réseaux CIDR : depuis toute autre adresse elle est refusée (403). Régénérer une clé conserve ses réseaux ; une clé créée ou régénérée par une clé limitée ne va jamais plus loin que celle-ci, et celle qui n’en avait pas les reçoit.

### Révoquer des clés
**Révoquer** sur une clé en usage la révoque immédiatement : les requêtes qui l’utilisent sont refusées dès lors. Une clé révoquée ou expirée propose **Supprimer**, qui la retire. Le tableau liste d’abord les clés en usage, puis les clés expirées et révoquées ; il se cherche par nom ou préfixe, se trie par chaque colonne et se pagine au-delà de dix clés.

> 💡 Utilisez des clés API de courte durée pour le CI/CD et l’automatisation.
`
  }
}
