export default {
  helpContent: {
    title: 'SCEP',
    subtitle: 'Protocole d\'inscription de certificat simplifié',
    overview: 'SCEP permet aux appareils réseau (routeurs, commutateurs, pare-feu) et aux solutions MDM de demander et d\'obtenir automatiquement des certificats. Les appareils s\'authentifient à l\'aide d\'un mot de passe de défi.',
    sections: [
      {
        title: 'Onglets',
        items: [
          { label: 'Requêtes', text: 'Requêtes d\'inscription SCEP en attente, approuvées et rejetées' },
          { label: 'Configuration', text: 'Paramètres du serveur SCEP : sélection de CA, identifiant CA, approbation automatique' },
          { label: 'Mots de passe de défi', text: 'Gérer les mots de passe de défi par CA pour l\'inscription des appareils' },
          { label: 'Informations', text: 'URL des points de terminaison SCEP et instructions d\'intégration' },
        ]
      },
      {
        title: 'Configuration',
        items: [
          { label: 'CA de signature', text: 'Sélectionner quelle CA signe les certificats inscrits via SCEP' },
          { label: 'Approbation automatique', text: 'Approuver automatiquement les requêtes avec des mots de passe de défi valides' },
          { label: 'Mot de passe de défi', text: 'Secret partagé que les appareils utilisent pour authentifier l\'inscription' },
        ]
      },
    ],
    tips: [
      'Utilisez des mots de passe de défi uniques par CA pour un meilleur audit de sécurité',
      'L\'approbation automatique est pratique mais examinez les requêtes manuellement dans les environnements haute sécurité',
      'Format de l\'URL SCEP : https://votre-serveur:port/scep',
    ],
    warnings: [
      'Les mots de passe de défi sont transmis dans la requête SCEP — utilisez HTTPS pour la sécurité du transport',
    ],
  },
  helpGuides: {
    title: 'Serveur SCEP',
    content: `
## Vue d'ensemble

Le protocole d'inscription de certificat simplifié (SCEP) permet aux appareils réseau — routeurs, commutateurs, pare-feu, terminaux gérés par MDM — de demander et d'obtenir automatiquement des certificats.

## Onglets

### Requêtes
Voir toutes les requêtes d'inscription SCEP :
- **En attente** — En attente d'approbation manuelle (si l'approbation automatique est désactivée)
- **Approuvées** — Émises avec succès
- **Rejetées** — Refusées par un administrateur

### Configuration
Configurer le serveur SCEP :
- **Activer/Désactiver** — Basculer le service SCEP
- **CA de signature** — Sélectionner quelle CA signe les certificats inscrits via SCEP
- **Identifiant CA** — L'identifiant que les appareils utilisent pour localiser la bonne CA
- **Approbation automatique** — Approuver automatiquement les requêtes avec des mots de passe de défi valides

### Mots de passe de défi
Gérer les mots de passe de défi par CA. Les appareils doivent inclure un mot de passe de défi valide dans leur requête d'inscription pour s'authentifier.

- **Voir le mot de passe** — Afficher le défi actuel pour une CA
- **Régénérer** — Créer un nouveau mot de passe de défi (invalide l'ancien)

### Informations
Affiche l'URL du point de terminaison SCEP et les instructions d'intégration.

## Flux d'inscription SCEP

1. L'appareil envoie une requête **GetCACert** pour obtenir le certificat de la CA
2. L'appareil génère une paire de clés et crée une CSR
3. L'appareil enveloppe la CSR avec le **mot de passe de défi** et envoie un **PKCSReq**
4. UCM valide le mot de passe de défi
5. Si l'approbation automatique est activée, UCM signe et retourne le certificat
6. Si l'approbation automatique est désactivée, un administrateur examine et approuve/rejette

## URL SCEP

\`\`\`
https://votre-serveur:8443/scep
\`\`\`

Les appareils ont besoin de cette URL plus l'identifiant CA pour s'inscrire.

## Approuver/Rejeter des requêtes

Pour les requêtes en attente (approbation automatique désactivée) :
1. Examinez les détails de la requête (sujet, type de clé, défi)
2. Cliquez sur **Approuver** pour signer et émettre le certificat
3. Ou cliquez sur **Rejeter** avec un motif

> ⚠ Les mots de passe de défi sont transmis dans la requête SCEP. Utilisez toujours HTTPS pour le point de terminaison SCEP.

## Intégration d'appareils

### Cisco IOS
\`\`\`
crypto pki trustpoint UCM
  enrollment url https://votre-serveur:8443/scep
  password <mot-de-passe-de-défi>
\`\`\`

### Microsoft Intune / JAMF
Configurez le profil SCEP avec :
- URL du serveur : \`https://votre-serveur:8443/scep\`
- Défi : le mot de passe depuis UCM
`
  }
}
