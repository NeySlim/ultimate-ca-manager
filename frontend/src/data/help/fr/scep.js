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
          { label: 'Profils', text: 'Endpoints d\'enrôlement nommés, chacun avec sa propre URL, CA, template et challenge' },
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
      {
        title: 'Profils',
        items: [
          { label: 'Segment d\'URL', text: 'Chaque profil est servi sur /scep/<segment>/pkiclient.exe — pointez chaque flotte d\'appareils ou profil MDM vers sa propre URL' },
          { label: 'Template de certificat', text: 'Quand un template est lié, ses usages de clé (KU/EKU) et sa validité gouvernent chaque certificat émis via le profil' },
          { label: 'Challenge par profil', text: 'Chaque profil a son propre mot de passe de défi, stocké chiffré, avec la même fenêtre d\'expiration que le challenge global' },
          { label: 'Endpoint par défaut', text: 'L\'endpoint /scep/pkiclient.exe sans segment continue de servir la configuration globale' },
          { label: 'Validation Microsoft Intune', text: 'Un profil peut se valider face au challenge SCEP propre à Intune par appareil au lieu d\'un mot de passe statique — nécessite une inscription d\'application Entra (permissions SCEP challenge validation + Application.Read.All) et l\'approbation automatique activée' },
        ]
      },
    ],
    tips: [
      'Utilisez des mots de passe de défi uniques par CA pour un meilleur audit de sécurité',
      'L\'approbation automatique est pratique mais examinez les requêtes manuellement dans les environnements haute sécurité',
      'Format de l\'URL SCEP : https://votre-serveur:port/scep',
      'Les profils Intune nécessitent l\'approbation automatique — l\'inscription Intune est un aller-retour synchrone de validation puis émission, sans file d\'approbation côté Intune',
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

### Profils
Endpoints d'enrôlement nommés, chacun servi sur sa propre URL :

\`\`\`
https://votre-serveur:8443/scep/<profil>/pkiclient.exe
\`\`\`

Chaque profil est lié à :
- **Sa propre CA** — différentes flottes d'appareils peuvent s'enrôler auprès de CAs différentes
- **Un template de certificat optionnel** — quand un template est lié, ses usages de clé (KU/EKU) et sa validité gouvernent chaque certificat émis via le profil
- **Un mot de passe de défi par profil** — stocké chiffré, avec la même fenêtre d'expiration que le challenge global
- **Une politique d'approbation** — approbation automatique ou revue manuelle par profil

Pointez chaque flotte d'appareils, profil MDM ou tenant vers sa propre URL de profil. L'endpoint \`/scep/pkiclient.exe\` sans segment continue de servir la configuration globale sans changement.

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
https://votre-serveur:8443/scep                         (endpoint global)
https://votre-serveur:8443/scep/<profil>/pkiclient.exe  (endpoint par profil)
\`\`\`

Les appareils ont besoin de l'URL plus l'identifiant CA pour s'inscrire. Utilisez une URL de profil pour cibler la CA, le template et le mot de passe de défi de ce profil.

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

### JAMF
Configurez le profil SCEP avec :
- URL du serveur : \`https://votre-serveur:8443/scep\`
- Défi : le mot de passe depuis UCM

### Microsoft Intune
Intune ne prend pas en charge un mot de passe de défi statique — il émet son propre défi chiffré par appareil que seule l'API Intune peut valider. Sur un **profil** SCEP (pas le point de terminaison global), activez **Validation du challenge SCEP Microsoft Intune** et fournissez l'ID de locataire, l'ID client et le secret client d'une inscription d'application Entra :

1. Dans Microsoft Entra ID, inscrivez une application et accordez-lui les autorisations d'application **Intune API → SCEP challenge validation** (\`scep_challenge_provider\`) et **Microsoft Graph → Application.Read.All**, toutes deux avec consentement administrateur
2. Saisissez l'ID de locataire, l'ID client et le secret client sur le profil, puis cliquez sur **Tester la connexion** pour confirmer que UCM peut joindre Intune avant d'enregistrer
3. Dans Intune, pointez l'URL du serveur du profil SCEP de l'appareil vers le point de terminaison \`/scep/<segment>/pkiclient.exe\` de ce profil

Les profils avec Intune activé doivent avoir l'**approbation automatique** activée — l'inscription Intune est un aller-retour synchrone de validation puis émission, sans file d'attente côté Intune pour une revue manuelle.
`
  }
}
