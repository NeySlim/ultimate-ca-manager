export default {
  helpContent: {
    title: 'Intégration Microsoft AD CS',
    subtitle: 'Signer des CSR via Windows PKI',
    overview: 'Intégrez UCM avec Microsoft Active Directory Certificate Services (AD CS) pour signer les CSR en utilisant votre infrastructure PKI Windows existante. Connectez-vous via mTLS, Basic Auth ou Kerberos.',
    sections: [
      {
        title: 'Configuration',
        items: [
          { label: 'Ajouter une connexion', text: 'Configurer les détails du serveur MS CA : nom d\'hôte, méthode d\'authentification et identifiants' },
          { label: 'Méthodes d\'authentification', text: 'Certificat client (mTLS), Basic Auth ou Kerberos' },
          { label: 'Tester la connexion', text: 'Vérifier la connectivité et l\'authentification avec le serveur CA' },
          { label: 'Modèle par défaut', text: 'Sélectionner le modèle de certificat par défaut de la CA Windows' },
        ]
      },
      {
        title: 'Signer des CSR',
        items: [
          { label: 'Modèles auto-approuvés', text: 'Le certificat est retourné immédiatement et importé dans UCM' },
          { label: 'Modèles avec approbation', text: 'UCM suit l\'ID de requête MS CA jusqu\'à l\'approbation du gestionnaire' },
          { label: 'EOBO', text: 'Inscrire pour le compte d\'un autre utilisateur avec les identifiants d\'agent d\'inscription' },
        ]
      },
    ],
    tips: [
      'L\'authentification par certificat client (mTLS) est recommandée pour la production',
      'EOBO nécessite un certificat d\'agent d\'inscription et des permissions de modèle appropriées',
      'Les modèles de certificat sont chargés automatiquement depuis la CA connectée',
    ],
    warnings: [
      'Le serveur CA doit avoir certsrv accessible pour la connexion UCM',
      'EOBO nécessite un certificat d\'agent d\'inscription configuré sur le serveur AD CS',
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
4. Entrez optionnellement le **nom commun de la CA** (auto-détecté si vide)
5. Sélectionnez la **méthode d'authentification**
6. Entrez les identifiants pour la méthode choisie
7. Cliquez sur **Tester la connexion** pour vérifier
8. Définissez un **modèle par défaut** et cliquez sur **Enregistrer**

## Méthodes d'authentification

| Méthode | Prérequis | Idéal pour |
|---------|-----------|------------|
| **Certificat client (mTLS)** | Cert/clé client PEM de la CA | Production — pas besoin de jonction au domaine |
| **Basic Auth** | Nom d'utilisateur + mot de passe, HTTPS | Configurations simples — activer basic auth dans IIS certsrv |
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
UCM enregistre la requête comme **En attente** et suit l'ID de requête MS CA. Une fois approuvée sur la CA Windows, vérifiez le statut depuis le panneau de détail de la CSR pour importer le certificat.

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
   - **DN du bénéficiaire** — depuis le sujet de la CSR (par ex. CN=Jean Dupont,OU=Utilisateurs,DC=corp,DC=local)
   - **UPN du bénéficiaire** — depuis le SAN e-mail de la CSR (par ex. jean.dupont@corp.local)
4. Ajustez les valeurs si nécessaire
5. Cliquez sur **Signer**

UCM transmet ces valeurs comme attributs de requête ADCS :
- EnrolleeObjectName:<DN> — identifie l'utilisateur cible dans AD
- EnrolleePrincipalName:<UPN> — le nom de connexion de l'utilisateur

### EOBO vs inscription directe

| Caractéristique | Inscription directe | EOBO |
|-----------------|---------------------|------|
| Qui signe | L'utilisateur lui-même | L'agent d'inscription pour le compte |
| Clé privée | Machine de l'utilisateur | Peut être sur UCM (modèle CSR) |
| Permission du modèle | Inscription standard | Nécessite les droits d'agent d'inscription |
| Cas d'utilisation | Libre-service | Gestion centralisée PKI |

## Dépannage

| Problème | Solution |
|----------|----------|
| Le test de connexion échoue | Vérifiez le nom d'hôte, le port 443 et que certsrv est accessible |
| Aucun modèle trouvé | Vérifiez que le compte UCM a les permissions d'inscription sur la CA |
| EOBO refusé | Vérifiez le certificat d'agent d'inscription et les permissions du modèle |
| Requête bloquée en attente | Approuvez sur la console CA Windows, puis actualisez le statut dans UCM |

> 💡 Utilisez le bouton **Tester la connexion** pour vérifier l'authentification et découvrir les modèles disponibles avant de signer.
`
  }
}
