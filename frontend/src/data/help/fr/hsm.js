export default {
  helpContent: {
    title: 'Modules de sécurité matériels',
    subtitle: 'Stockage de clés externe',
    overview: 'Intégrez des modules de sécurité matériels pour le stockage sécurisé des clés privées. Prend en charge PKCS#11, AWS CloudHSM, Azure Key Vault, Google Cloud KMS et OpenBao/Vault Transit.',
    sections: [
      {
        title: 'Fournisseurs pris en charge',
        definitions: [
          { term: 'PKCS#11', description: 'Interface HSM standard de l\'industrie (Thales, Entrust, SoftHSM)' },
          { term: 'AWS CloudHSM', description: 'HSM basé sur le cloud Amazon Web Services' },
          { term: 'Azure Key Vault', description: 'Stockage de clés géré Microsoft Azure' },
          { term: 'Google KMS', description: 'Service de gestion des clés Google Cloud' },
          { term: 'OpenBao / Vault Transit', description: 'Moteur de secrets Transit OpenBao ou HashiCorp Vault pour la gestion de clés en chiffrement-as-a-service' },
        ]
      },
      {
        title: 'Actions',
        items: [
          { label: 'Ajouter un fournisseur', text: 'Configurer la connexion à un HSM (chemin de bibliothèque, identifiants, slot)' },
          { label: 'Tester la connexion', text: 'Vérifier que le HSM est joignable et que les identifiants sont valides ; pour un module PKCS#11, enregistre aussi ce qu\'il déclare (bibliothèque, fabricant, versions de la bibliothèque et du firmware), affiché sur la page du fournisseur' },
          { label: 'Générer une clé', text: 'Créer une nouvelle paire de clés directement sur le HSM' },
          { label: 'Statut', text: 'Surveiller la santé de la connexion du fournisseur' },
          { label: 'Certification', text: 'Déclarer la certification du HSM : Common Criteria EAL 4+, EUCC élevé, FIPS 140-3 niveau 3, FIPS 140-2 niveau 3 ou autre. Laissée vide, elle n\'est pas déclarée. Le profil de conformité eu-acm n\'accepte que Common Criteria EAL 4+, EUCC élevé et FIPS 140-3 niveau 3 (jusqu\'au 31 décembre 2030) pour une CA adossée à un HSM' },
        ]
      },
      {
        title: 'CA adossées à HSM (v2.130+)',
        content: 'Une fois un fournisseur HSM configuré, vous pouvez épingler la clé privée d\'une CA à ce HSM dès sa création :',
        items: [
          { label: 'Bascule Stockage de clé', text: 'Sur le formulaire de création de CA, choisir Local (chiffré en DB) ou HSM. Sélectionner le fournisseur + label de clé' },
          { label: 'Chemin de signature', text: 'Chaque émission, signature de CRL et signature OCSP de cette CA passe par le HSM, la clé ne sort jamais' },
          { label: 'Restrictions d\'export', text: 'L\'export PKCS#12, JKS et clé seule est désactivé pour les CA HSM (seul le certificat public / la chaîne peut être exporté)' },
          { label: 'CRL & OCSP', text: 'Les deux fonctionnent de manière transparente avec les CA HSM (signés via HSM)' },
          { label: 'Migration', text: 'Les CA locales existantes ne peuvent pas être déplacées vers un HSM après création, choisir à la création' },
        ]
      },

    ],
    tips: [
      'Utilisez SoftHSM pour les tests avant de déployer avec un HSM physique',
      'Les clés générées sur un HSM ne quittent jamais le matériel : elles ne peuvent pas être exportées',
      'Testez la connexion avant d\'utiliser un fournisseur HSM pour la signature de CA',
      'Pour les CA racines à longue durée de vie en production, préférez le stockage de clé adossé à HSM',
    ],
    warnings: [
      'La certification déclarée est l\'affirmation de l\'opérateur sur le HSM : UCM ne vérifie pas le matériel. Les profils alignés sur eIDAS la lisent pour contrôler la protection de la clé de la CA',
      'Une mauvaise configuration du fournisseur HSM peut empêcher la signature de certificats',
      'Perdre l\'accès au HSM signifie perdre l\'accès aux clés qui y sont stockées',
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

> 💡 **Docker** : SoftHSM est pré-installé dans l'image Docker. Au premier démarrage, un jeton par défaut est auto-initialisé et enregistré comme fournisseur \`SoftHSM-Default\` : prêt à l'emploi immédiatement. En mode FIPS, SoftHSM n'est pas un module validé : le fournisseur par défaut n'est pas créé et un fournisseur SoftHSM est refusé, sauf si \`UCM_FIPS_ALLOW_SOFTHSM=1\` en autorise un pour des tests.

Configuration :
- **Chemin de la bibliothèque** : Chemin vers la bibliothèque partagée PKCS#11 (.so/.dll)
- **Slot** : Numéro de slot HSM
- **PIN** : PIN utilisateur pour l'authentification

### AWS CloudHSM
HSM basé sur le cloud Amazon Web Services :
- **ID du cluster** : Identifiant du cluster CloudHSM
- **Étiquette de token** : étiquette du token PKCS#11 CloudHSM
- **Utilisateur crypto / Mot de passe crypto** : l'utilisateur crypto (CU) avec lequel UCM se connecte ; aucune clé d'accès AWS n'est nécessaire

### Azure Key Vault
Stockage de clés géré Microsoft Azure :
- **URL du coffre** : Point de terminaison Azure Key Vault
- **ID du locataire** : Locataire Azure AD
- **ID client/Secret** : Identifiants du principal de service

### Google Cloud KMS
Service de gestion des clés Google Cloud :
- **Projet** : ID du projet GCP
- **Emplacement** : Emplacement de l'anneau de clés KMS
- **Anneau de clés** : Nom de l'anneau de clés
- **Identifiants** : Clé JSON du compte de service

### OpenBao / Vault Transit
Moteur de secrets Transit OpenBao ou HashiCorp Vault. Les clés sont gérées à distance via l'API Transit : aucune bibliothèque PKCS#11 requise.

Configuration :
- **URL** : Adresse du serveur (ex. \`https://openbao.example.com:8200\`)
- **Token** : Jeton d'authentification
- **Chemin de montage** : Point de montage du moteur Transit (par défaut : \`transit\`)
- **Espace de noms** : Espace de noms optionnel pour les configurations multi-locataires
- **Ignorer la vérification TLS** : Ignorer la vérification du certificat TLS (pour les certificats auto-signés)

Types de clés pris en charge :
- RSA 2048, 3072, 4096
- ECDSA P-256, P-384, P-521
- AES-256-GCM (symétrique)

> 💡 OpenBao est un fork communautaire de HashiCorp Vault. UCM fonctionne avec les deux.

> 💡 Pour le développement, lancez OpenBao en mode dev : \`docker run -d -p 8200:8200 -e BAO_DEV_ROOT_TOKEN_ID=test-token quay.io/openbao/openbao:latest server -dev\`

## Gérer les fournisseurs

### Ajouter un fournisseur
1. Cliquez sur **Ajouter un fournisseur**
2. Sélectionnez le **type de fournisseur**
3. Entrez les détails de connexion
4. Cliquez sur **Tester la connexion** pour vérifier
5. Cliquez sur **Enregistrer**

### Tester la connexion
Testez toujours la connexion après avoir créé ou modifié un fournisseur. UCM vérifie qu'il peut communiquer avec le HSM et s'authentifier. Pour un module PKCS#11, le test enregistre aussi ce que le module déclare (bibliothèque, fabricant, versions de la bibliothèque et du firmware), affiché sur la page du fournisseur.

### Statut du fournisseur
Chaque fournisseur affiche un indicateur de statut de connexion :
- **Connecté** : Le HSM est accessible et authentifié
- **Déconnecté** : Impossible de joindre le HSM
- **Erreur** : Problème d'authentification ou de configuration

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
