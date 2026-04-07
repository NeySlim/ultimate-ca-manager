export default {
  helpContent: {
    title: 'Modules de sécurité matériels',
    subtitle: 'Protection des clés cryptographiques',
    overview: 'Intégrez des HSM pour le stockage inviolable des clés privées. Les clés stockées sur un HSM ne quittent jamais le matériel, offrant le plus haut niveau de protection. Prend en charge PKCS#11, AWS CloudHSM, Azure Key Vault et Google Cloud KMS.',
    sections: [
      {
        title: 'Fournisseurs pris en charge',
        items: [
          { label: 'PKCS#11', text: 'Interface HSM standard — Thales Luna, Entrust nShield, SoftHSM et tout appareil PKCS#11' },
          { label: 'AWS CloudHSM', text: 'HSM basé sur le cloud avec identifiants AWS' },
          { label: 'Azure Key Vault', text: 'Stockage de clés géré Microsoft Azure' },
          { label: 'Google Cloud KMS', text: 'Service de gestion des clés Google Cloud' },
        ]
      },
      {
        title: 'Gestion des clés',
        items: [
          { label: 'Générer une clé', text: 'Créer des clés RSA ou ECDSA directement sur le HSM' },
          { label: 'Utiliser les clés HSM', text: 'Sélectionner les clés HSM lors de la création de CA au lieu de clés logicielles' },
          { label: 'Tester la connexion', text: 'Vérifier la communication et l\'authentification avec le HSM' },
        ]
      },
    ],
    tips: [
      'SoftHSM est pré-installé dans l\'image Docker — un jeton par défaut est auto-initialisé au premier démarrage',
      'Utilisez SoftHSM pour le développement et les tests avant le déploiement avec des HSM physiques',
      'Les clés générées sur un HSM ne peuvent pas être exportées — planifiez soigneusement votre stratégie de sauvegarde',
    ],
    warnings: [
      'Les clés HSM ne peuvent pas être exportées — la perte d\'accès au HSM signifie la perte des clés',
      'Testez toujours la connexion après avoir créé ou modifié un fournisseur',
    ],
  },
  helpGuides: {
    title: 'Modules de sécurité matériels',
    content: `
## Vue d'ensemble

Les modules de sécurité matériels (HSM) fournissent un stockage inviolable pour les clés cryptographiques. Les clés privées stockées sur un HSM ne quittent jamais le matériel, offrant le plus haut niveau de protection des clés.

## Fournisseurs pris en charge

### PKCS#11
L'interface HSM standard de l'industrie. Appareils pris en charge :
- **Thales Luna** / **SafeNet**
- **Entrust nShield**
- **SoftHSM** (logiciel, pour les tests)
- Tout appareil compatible PKCS#11

> 💡 **Docker** : SoftHSM est pré-installé dans l'image Docker. Au premier démarrage, un jeton par défaut est auto-initialisé et enregistré comme fournisseur \`SoftHSM-Default\` — prêt à l'emploi immédiatement.

Configuration :
- **Chemin de la bibliothèque** — Chemin vers la bibliothèque partagée PKCS#11 (.so/.dll)
- **Slot** — Numéro de slot HSM
- **PIN** — PIN utilisateur pour l'authentification

### AWS CloudHSM
HSM basé sur le cloud Amazon Web Services :
- **ID du cluster** — Identifiant du cluster CloudHSM
- **Région** — Région AWS
- **Identifiants** — Clé d'accès et secret AWS

### Azure Key Vault
Stockage de clés géré Microsoft Azure :
- **URL du coffre** — Point de terminaison Azure Key Vault
- **ID du locataire** — Locataire Azure AD
- **ID client/Secret** — Identifiants du principal de service

### Google Cloud KMS
Service de gestion des clés Google Cloud :
- **Projet** — ID du projet GCP
- **Emplacement** — Emplacement de l'anneau de clés KMS
- **Anneau de clés** — Nom de l'anneau de clés
- **Identifiants** — Clé JSON du compte de service

## Gérer les fournisseurs

### Ajouter un fournisseur
1. Cliquez sur **Ajouter un fournisseur**
2. Sélectionnez le **type de fournisseur**
3. Entrez les détails de connexion
4. Cliquez sur **Tester la connexion** pour vérifier
5. Cliquez sur **Enregistrer**

### Tester la connexion
Testez toujours la connexion après avoir créé ou modifié un fournisseur. UCM vérifie qu'il peut communiquer avec le HSM et s'authentifier.

### Statut du fournisseur
Chaque fournisseur affiche un indicateur de statut de connexion :
- **Connecté** — Le HSM est accessible et authentifié
- **Déconnecté** — Impossible de joindre le HSM
- **Erreur** — Problème d'authentification ou de configuration

## Gestion des clés

### Générer des clés
1. Sélectionnez un fournisseur connecté
2. Cliquez sur **Générer une clé**
3. Choisissez l'algorithme (RSA 2048/4096, ECDSA P-256/P-384)
4. Entrez un label/alias pour la clé
5. Cliquez sur **Générer**

La clé est créée directement sur le HSM. UCM ne stocke qu'une référence.

### Utiliser les clés HSM
Lors de la création d'une CA, sélectionnez un fournisseur HSM et une clé au lieu de générer une clé logicielle. Les opérations de signature de la CA sont effectuées sur le HSM.

> ⚠ Les clés générées sur un HSM ne peuvent pas être exportées. Si vous perdez l'accès au HSM, vous perdez les clés.

> 💡 Utilisez SoftHSM pour le développement et les tests avant le déploiement avec des HSM physiques.
`
  }
}
