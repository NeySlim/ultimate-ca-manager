export default {
  helpContent: {
    title: 'Demandes de signature de certificat',
    subtitle: 'Gérer le flux de travail des CSR',
    overview: 'Téléversez, examinez et signez les demandes de signature de certificat. Les CSR permettent aux systèmes externes de demander des certificats à vos CA sans exposer les clés privées.',
    sections: [
      {
        title: 'Flux de travail',
        items: [
          { label: 'Générer une CSR', text: 'Créer une nouvelle CSR avec paire de clés directement dans UCM' },
          { label: 'Téléverser une CSR', text: 'Accepter des fichiers CSR encodés en PEM ou coller du texte PEM' },
          { label: 'Examiner', text: 'Inspecter le sujet, les SAN, le type de clé et la signature avant de signer' },
          { label: 'Signer', text: 'Sélectionner une CA, le type de certificat, définir la période de validité et émettre le certificat' },
          { label: 'Télécharger', text: 'Télécharger la CSR originale au format PEM' },
        ]
      },
      {
        title: 'Onglets',
        items: [
          { label: 'En attente', text: 'CSR en attente d\'examen et de signature' },
          { label: 'Historique', text: 'CSR précédemment signées ou rejetées' },
        ]
      },
    ],
    tips: [
      'Les CSR préservent la clé privée du demandeur — elle ne quitte jamais son système',
      'Vous pouvez ajouter une clé privée à une CSR après la signature si nécessaire pour l\'exportation PKCS#12',
      'Utilisez le mode Microsoft CA pour signer les CSR via AD CS lorsque vous êtes connecté à une PKI Windows',
    ],
  },
  helpGuides: {
    title: 'Demandes de signature de certificat',
    content: `
## Vue d'ensemble

Les demandes de signature de certificat (CSR) permettent aux systèmes externes de demander des certificats sans exposer leurs clés privées. La CSR contient la clé publique et les informations du sujet ; la clé privée reste chez le demandeur.

## Onglets

### En attente
CSR en attente d'examen et de signature. Les nouvelles CSR apparaissent ici après le téléversement.

### Historique
CSR précédemment signées ou rejetées, avec des liens vers les certificats résultants.

## Générer une CSR

UCM peut générer une CSR et une paire de clés directement :

1. Cliquez sur **Générer une CSR**
2. Remplissez les champs du sujet (CN obligatoire)
3. Ajoutez des noms alternatifs du sujet si nécessaire
4. Sélectionnez le type et la taille de la clé (RSA 2048/4096, ECDSA P-256/P-384)
5. Cliquez sur **Générer**

La CSR et la clé privée sont créées et stockées dans UCM. La CSR apparaît dans l'onglet En attente prête à être signée.

> 💡 C'est pratique lorsque vous souhaitez qu'UCM gère l'ensemble du cycle de vie — CSR, signature et stockage des clés.

## Téléverser une CSR

1. Cliquez sur **Téléverser une CSR**
2. Collez du texte PEM ou téléversez un fichier PEM/DER
3. UCM valide la signature de la CSR et affiche les détails
4. La CSR apparaît dans l'onglet En attente

## Examiner une CSR

Cliquez sur une CSR pour voir :
- **Sujet** — CN, O, OU, C, etc.
- **SAN** — Noms DNS, adresses IP, e-mails
- **Info clé** — Algorithme, taille, empreinte de la clé publique
- **Signature** — Algorithme et validité

## Signer une CSR

### Signature par CA locale

1. Sélectionnez une CSR en attente
2. Cliquez sur **Signer**
3. Choisissez la **CA de signature** (doit posséder une clé privée)
4. Sélectionnez le **type de certificat** (serveur, client, signature de code, e-mail)
5. Définissez la **période de validité** en jours
5. Appliquez optionnellement un modèle pour l'utilisation de la clé et les extensions
6. Cliquez sur **Signer**

Le certificat résultant apparaît sur la page des certificats.

### Signature par Microsoft CA

Si des connexions Microsoft CA sont configurées, un onglet **Microsoft CA** apparaît dans le modal de signature :

1. Sélectionnez une CSR en attente et cliquez sur **Signer**
2. Passez à l'onglet **Microsoft CA**
3. Sélectionnez la **connexion MS CA**
4. Sélectionnez le **modèle de certificat** (chargé automatiquement depuis la CA)
5. Cliquez sur **Signer**

Si le modèle nécessite l'approbation d'un gestionnaire, UCM suit la demande en attente. Vérifiez son statut depuis le panneau de détail de la CSR.

### Inscription pour le compte d'autrui (EOBO)

Lors de la signature via Microsoft CA, vous pouvez inscrire pour le compte d'un autre utilisateur :

1. Sélectionnez la connexion MS CA et le modèle
2. Cochez **Inscription pour le compte d'autrui (EOBO)**
3. Les champs **DN du bénéficiaire** et **UPN du bénéficiaire** se remplissent automatiquement à partir du sujet et du SAN e-mail de la CSR
4. Ajustez les valeurs si nécessaire et cliquez sur **Signer**

> ⚠️ EOBO nécessite un certificat d'agent d'inscription configuré sur le serveur AD CS, et le modèle doit autoriser l'inscription pour le compte d'autres utilisateurs.

## Ajouter une clé privée

Après la signature, vous pouvez attacher une clé privée au certificat pour l'exportation PKCS#12. Cliquez sur **Ajouter une clé** sur le certificat signé.

> 💡 C'est utile lorsque le demandeur envoie à la fois la CSR et la clé de manière sécurisée.

## Supprimer des CSR

La suppression retire la CSR de UCM. Si la CSR a déjà été signée, le certificat résultant n'est pas affecté.
`
  }
}
