export default {
  helpContent: {
    title: 'Intégration Microsoft AD CS',
    subtitle: 'Signer des certificats avec une autorité de certification Microsoft',
    overview: 'Connectez UCM à Microsoft Active Directory Certificate Services (AD CS) pour signer les CSR avec votre infrastructure PKI Windows et gérer le cycle de vie complet des certificats. Prend en charge l\'authentification par certificat (mTLS), Kerberos et Basic, plus un canal admin WinRM optionnel pour la révocation, les CRL, l\'inventaire et la gestion des requêtes en attente.',
    sections: [
      {
        title: 'Méthodes d\'authentification',
        items: [
          { label: 'Certificat client (mTLS)', text: 'Le plus sécurisé. Générez un certificat client sur votre MS CA, exportez en PFX, téléversez le certificat et la clé en PEM.' },
          { label: 'Basic Auth', text: 'Nom d\'utilisateur/mot de passe sur HTTPS. Fonctionne sans jonction au domaine. Activez basic auth dans IIS certsrv.' },
          { label: 'Kerberos', text: 'Nécessite le paquet requests-kerberos et une machine jointe au domaine ou un keytab configuré.' },
        ]
      },
      {
        title: 'Signer des CSR',
        items: [
          { label: 'Sélection du modèle', text: 'Choisir parmi les modèles de certificats disponibles sur la MS CA' },
          { label: 'Auto-approuvé', text: 'Les modèles avec autoenroll retournent le certificat immédiatement' },
          { label: 'Approbation du gestionnaire', text: 'Certains modèles exigent l\'approbation du gestionnaire, UCM suit la requête en attente' },
          { label: 'Requêtes en attente', text: 'Une requête que la CA retient pour son gestionnaire reste En attente dans UCM, et la page ne propose pas de vérification du statut : une fois émise sur la CA, importez le certificat, ou laissez la synchronisation de l\'inventaire via le canal d\'administration WinRM importer les certificats que UCM ne connaît pas encore' },
        ]
      },
      {
        title: 'Inscription pour le compte d\'autrui (EOBO)',
        items: [
          { label: 'Vue d\'ensemble', text: 'Soumettre une CSR pour le compte d\'un autre utilisateur avec des certificats d\'agent d\'inscription' },
          { label: 'DN du bénéficiaire', text: 'Nom distinctif (DN) de l\'utilisateur cible (auto-rempli depuis le sujet de la CSR)' },
          { label: 'UPN du bénéficiaire', text: 'Nom principal d\'utilisateur (UPN) de l\'utilisateur cible (auto-rempli depuis le SAN e-mail de la CSR)' },
          { label: 'Prérequis', text: 'Le modèle de la CA doit autoriser l\'inscription pour le compte d\'autrui. Le compte de service UCM a besoin d\'un certificat d\'agent d\'inscription.' },
        ]
      },
      {
        title: 'Cycle de vie : renouvellement & révocation',
        items: [
          { label: 'Renouveler', text: 'Le renouvellement d\'un certificat émis par AD CS resoumet sa CSR d\'origine à la même connexion et au même modèle, c\'est la CA émettrice qui signe, pas UCM.' },
          { label: 'Révoquer', text: 'La révocation d\'un certificat émis par AD CS est locale à UCM, sauf si le canal admin WinRM est configuré, elle est alors propagée à la CA Windows.' },
          { label: 'Renouvellement en attente', text: 'Si la CA retient le renouvellement pour approbation du gestionnaire, UCM le suit comme n\'importe quelle requête en attente.' },
        ]
      },
      {
        title: 'Canal admin WinRM (optionnel)',
        items: [
          { label: 'Rôle', text: 'Exécute les opérations de gestion sur la CA Windows (révoquer, dé-révoquer, publier la CRL, inventaire, approuver/refuser) via PowerShell remoting + certutil, ce que l\'inscription Web AD CS ne sait pas faire.' },
          { label: 'Transport', text: 'NTLM ou Kerberos sur HTTP/HTTPS. Kerberos + HTTPS recommandé ; Kerberos réutilise le keytab de la connexion.' },
          { label: 'Identifiants', text: 'Réutilise par défaut ceux de la connexion. Les connexions en mTLS doivent définir un compte WinRM dédié (officier « Émettre et gérer les certificats » à moindre privilège).' },
          { label: 'Prérequis', text: 'WinRM activé sur la CA et le paquet optionnel pywinrm installé. Les opérations de gestion exigent admin:system ; propager une révocation ou une levée de suspension à la CA suit le write:certificates du certificat.' },
        ]
      },
      {
        title: 'Synchronisation CRL des révocations',
        items: [
          { label: 'Sens unique', text: 'Récupère périodiquement la CRL de la CA et marque comme révoqués dans UCM les certificats révoqués sur la CA. Ne dé-révoque jamais.' },
          { label: 'Source CRL', text: 'Une URL de CRL explicite, ou auto-détectée depuis le point de distribution CRL des certificats émis.' },
          { label: 'Vérifiée', text: 'La signature de la CRL est vérifiée avec le certificat de la CA avant toute application.' },
        ]
      },
      {
        title: 'Inventaire CA & panneau de contrôle',
        items: [
          { label: 'Sync d\'inventaire', text: 'Importe les certificats émis directement sur la CA et encore inconnus d\'UCM (incrémental par id de requête) ; la réconciliation est disponible via l\'API.' },
          { label: 'Requêtes en attente', text: 'Lister, approuver (resoumission + import auto) ou refuser les requêtes en attente d\'approbation du gestionnaire de la CA.' },
          { label: 'Santé de la CA', text: 'État du service CA, expiration du certificat CA, prochaine mise à jour de la CRL et nombre de requêtes en attente, d\'un coup d\'œil.' },
        ]
      },
    ],
    tips: [
      'Testez d\'abord la connexion pour vérifier l\'authentification et découvrir les modèles disponibles.',
      'Activez EOBO en cochant la case dans le modal de signature : les champs se remplissent automatiquement depuis la CSR.',
      'L\'authentification par certificat client est recommandée pour la production : elle ne nécessite pas de jonction au domaine.',
      'Activez le canal admin WinRM pour propager les révocations à la CA et gérer les requêtes en attente depuis UCM.',
    ],
    warnings: [
      'Kerberos nécessite une machine jointe au domaine ou un keytab configuré : non disponible dans Docker.',
      'EOBO nécessite un certificat d\'agent d\'inscription configuré sur le serveur AD CS.',
      'Sans le canal admin WinRM, révoquer un certificat AD CS ne le marque révoqué que dans UCM : la CA Windows n\'est pas notifiée.',
    ],
  },
  helpGuides: {
    title: 'Intégration Microsoft AD CS',
    content: `
## Vue d'ensemble

UCM s'intègre avec Microsoft Active Directory Certificate Services (AD CS) pour signer les CSR en utilisant votre infrastructure PKI Windows existante. Cela fait le pont entre votre CA interne et la gestion du cycle de vie des certificats d'UCM.

## Configurer une connexion

1. Allez dans **Paramètres → Microsoft CA**
2. Cliquez sur **Ajouter une connexion**
3. Entrez le **nom de la connexion** et le **nom d'hôte du serveur CA**
4. Entrez optionnellement le **nom commun de la CA** (le nom d'hôte du serveur est utilisé si vide)
5. Sélectionnez la **méthode d'authentification**
6. Entrez les identifiants pour la méthode choisie
7. Cliquez sur **Tester la connexion** pour vérifier
8. Définissez un **modèle par défaut** et cliquez sur **Enregistrer**

## Méthodes d'authentification

| Méthode | Prérequis | Idéal pour |
|---------|-----------|------------|
| **Certificat client (mTLS)** | Cert/clé client PEM de la CA | Production : pas besoin de jonction au domaine |
| **Basic Auth** | Nom d'utilisateur + mot de passe, HTTPS | Configurations simples : activer basic auth dans IIS certsrv |
| **Kerberos** | Machine jointe au domaine + keytab | Environnements AD d'entreprise |

### Configuration du certificat client (recommandée)

1. Sur votre CA Windows, créez un certificat pour le compte de service UCM
2. Exportez en PFX, puis convertissez en PEM :
   \`\`\`bash
   openssl pkcs12 -in client.pfx -out client-cert.pem -clcerts -nokeys
   openssl pkcs12 -in client.pfx -out client-key.pem -nocerts -nodes
   \`\`\`
3. Collez le contenu PEM du certificat et de la clé dans le formulaire de connexion UCM

## Signer des CSR via Microsoft CA

1. Naviguez vers **CSR → En attente**
2. Sélectionnez une CSR et cliquez sur **Signer**
3. Passez à l'onglet **Microsoft CA**
4. Sélectionnez la connexion et le modèle de certificat
5. Cliquez sur **Signer**

### Modèles auto-approuvés
Le certificat est retourné immédiatement et importé dans UCM.

### Modèles avec approbation du gestionnaire
UCM enregistre la requête comme **En attente** et suit l'ID de requête MS CA. La page ne propose pas de vérification du statut : une fois le certificat émis sur la CA Windows, importez-le, ou laissez la **synchronisation de l'inventaire** via le canal d'administration WinRM importer les certificats que UCM ne connaît pas encore.

## Inscription pour le compte d'autrui (EOBO)

EOBO permet à un agent d'inscription de demander des certificats pour le compte d'autres utilisateurs. C'est courant dans les environnements d'entreprise où un administrateur PKI gère les certificats pour les utilisateurs finaux.

### Prérequis

- Le compte de service UCM a besoin d'un **certificat d'agent d'inscription** émis par la CA
- Le modèle de certificat doit avoir la permission **« Inscrire pour le compte d'autres utilisateurs »** activée
- L'onglet sécurité du modèle doit accorder à l'agent d'inscription le droit d'inscrire

### Utiliser EOBO dans UCM

1. Dans le modal de signature, sélectionnez la connexion Microsoft CA et le modèle
2. Cochez la case **Inscription pour le compte d'autrui (EOBO)**
3. Les champs se remplissent automatiquement depuis la CSR :
   - **DN du bénéficiaire** : depuis le sujet de la CSR (par ex. CN=Jean Dupont,OU=Utilisateurs,DC=corp,DC=local)
   - **UPN du bénéficiaire** : depuis le SAN e-mail de la CSR (par ex. jean.dupont@corp.local)
4. Ajustez les valeurs si nécessaire
5. Cliquez sur **Signer**

UCM transmet ces valeurs comme attributs de requête ADCS :
- EnrolleeObjectName:<DN> : identifie l'utilisateur cible dans AD
- EnrolleePrincipalName:<UPN> : le nom de connexion de l'utilisateur

### EOBO vs inscription directe

| Caractéristique | Inscription directe | EOBO |
|-----------------|---------------------|------|
| Qui signe | L'utilisateur lui-même | L'agent d'inscription pour le compte |
| Clé privée | Machine de l'utilisateur | Peut être sur UCM (modèle CSR) |
| Permission du modèle | Inscription standard | Nécessite les droits d'agent d'inscription |
| Cas d'utilisation | Libre-service | Gestion centralisée PKI |

## Cycle de vie des certificats

### Renouveler un certificat AD CS
Le renouvellement ne re-signe **pas** localement (la clé émettrice réside sur la CA Windows). UCM resoumet la CSR d'origine du certificat : mêmes clé, sujet et SAN, à la connexion et au modèle qui l'ont émis, puis met à jour le certificat en place. Si la CA retient le renouvellement pour approbation du gestionnaire, il est suivi comme une requête en attente.

### Révoquer un certificat AD CS
L'inscription Web AD CS n'a pas de point de terminaison de révocation. Révoquer un certificat émis par AD CS :
- **Sans le canal admin WinRM** : le marque révoqué dans UCM uniquement ; la CA Windows n'est pas notifiée. Révoquez-le aussi sur la CA.
- **Avec le canal admin WinRM** : UCM propage la révocation à la CA Windows (certutil -revoke + publication de la CRL). La levée d'un certificateHold propage aussi la dé-révocation.

## Canal admin WinRM (optionnel)

Le canal admin permet à UCM d'exécuter sur la CA Windows des opérations de gestion impossibles via l'inscription Web : révoquer/dé-révoquer, publier la CRL, inventaire, et approuver/refuser les requêtes en attente. Il utilise PowerShell remoting + certutil.

### Prérequis
- **WinRM activé** sur la CA (Enable-PSRemoting ; listener HTTPS sur 5986 recommandé)
- Le paquet optionnel **pywinrm** installé dans UCM (pip install pywinrm)
- Un compte autorisé à **gérer les certificats** sur la CA (« Issue and Manage Certificates »)

### Configuration
1. Modifiez la connexion et activez le **canal admin WinRM**
2. Définissez l'hôte (par défaut le serveur de la connexion), le port et le transport
3. **Transport** : Kerberos (recommandé, réutilise le keytab de la connexion) ou NTLM, sur HTTP ou HTTPS
4. **Identifiants** : laissez vide pour réutiliser ceux de la connexion (Basic/Kerberos). Les connexions mTLS n'ont pas d'identifiant WinRM réutilisable, définissez un compte dédié
5. Cliquez sur **Tester le canal admin**

| Mode d'auth d'inscription | Réutilise les identifiants pour WinRM ? |
|---------------------------|-----------------------------------------|
| Kerberos (keytab) | Oui : même principal/keytab |
| Basic (utilisateur/mot de passe) | Oui : mot de passe vers NTLM/Kerberos |
| Certificat (mTLS) | Non : définissez un compte WinRM dédié |

## Synchronisation CRL des révocations

Activez **Synchroniser les révocations depuis la CRL de la CA** sur la connexion pour qu'UCM récupère périodiquement la CRL de la CA et marque comme révoqués dans UCM les certificats révoqués sur la CA. C'est strictement à sens unique (CA vers UCM) et un certificat révoqué dans UCM n'est jamais dé-révoqué. L'URL de la CRL vient de la connexion ou est auto-détectée depuis le point de distribution CRL des certificats émis, et sa signature est vérifiée avec le certificat de la CA avant toute application. S'exécute toutes les heures, plus une action **Synchroniser la CRL maintenant**.

## Synchronisation d'inventaire CA

Activez **Importer les certificats émis directement sur la CA** pour ramener dans le magasin d'UCM les certificats émis hors UCM (outils natifs, autoenrollment, ou antérieurs à UCM), afin qu'UCM suive tout le cycle de vie. La base de la CA est lue avec certutil -view, les certificats inconnus d'UCM sont importés (dédupliqués par numéro de série), en mode incrémental par id de requête (avec option de re-scan complet). Une vue de **réconciliation** liste les certificats présents sur la CA mais absents d'UCM, et inversement. S'exécute toutes les 6 heures, plus une action **Importer depuis la CA maintenant**. Nécessite le canal admin WinRM.

## Panneau de contrôle CA

Le panneau de contrôle (ouvert depuis la connexion, nécessite le canal admin) gère les requêtes en attente d'approbation du gestionnaire de la CA et affiche la santé de la CA :
- **Requêtes en attente** : lister, **Approuver** (certutil -resubmit ; le certificat émis est importé automatiquement) ou **Refuser** (certutil -deny)
- **Santé** : état du service CA, expiration du certificat CA, prochaine mise à jour de la CRL et nombre de requêtes en attente

## Dépannage

| Problème | Solution |
|----------|----------|
| Le test de connexion échoue | Vérifiez le nom d'hôte, le port 443 et que certsrv est accessible |
| Aucun modèle trouvé | Vérifiez que le compte UCM a les permissions d'inscription sur la CA |
| EOBO refusé | Vérifiez le certificat d'agent d'inscription et les permissions du modèle |
| Requête bloquée en attente | Approuvez-la depuis le panneau de contrôle CA, ou sur la console CA Windows puis actualisez le statut dans UCM |
| Le test du canal admin échoue | Vérifiez que WinRM est activé sur la CA, le port/transport, et que pywinrm est installé |
| Révocation absente sur la CA | Activez le canal admin WinRM : sans lui, la révocation est locale à UCM |
| Attente non détectée (CA non anglophone) | Corrigé en v2.192. UCM reconnaît désormais les pages d'attente AD CS localisées |

> 💡 Utilisez le bouton **Tester la connexion** pour vérifier l'authentification et découvrir les modèles disponibles avant de signer. Activez le **canal admin WinRM** pour gérer révocation, CRL, inventaire et requêtes en attente directement depuis UCM.
`
  }
}
