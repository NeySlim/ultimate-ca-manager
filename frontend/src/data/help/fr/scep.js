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
          { label: 'Configuration', text: 'Paramètres du serveur SCEP : sélection de CA, approbation automatique' },
          { label: 'Profils', text: 'Endpoints d\'enrôlement nommés, chacun avec sa propre URL, CA, template et challenge' },
          { label: 'Inscriptions d\'application Intune', text: 'Inscriptions d\'application Entra (ID de locataire, ID client, secret client) partagées par les profils qui valident les challenges Intune ; un secret vide à l\'édition conserve l\'actuel, Tester la connexion demande un jeton et découvre le service sans consommer de challenge, et une app encore utilisée par un profil ne peut pas être supprimée' },
          { label: 'Défis', text: 'Afficher et régénérer les mots de passe de défi pour l\'inscription des appareils' },
          { label: 'Informations', text: 'URL des points de terminaison SCEP et instructions d\'intégration' },
        ]
      },
      {
        title: 'Configuration',
        items: [
          { label: 'CA de signature', text: 'Sélectionner quelle CA signe les certificats inscrits via SCEP. Les appareils chiffrent leur requête pour cette CA, elle doit donc détenir une clé RSA logicielle : les CA EC, adossées à un HSM, sans clé, hors ligne ou révoquées ne sont pas listées (v2.248)' },
          { label: 'Approbation automatique', text: 'Approuver automatiquement les requêtes avec des mots de passe de défi valides, ou les renouvellements signés par un certificat émis par le même endpoint' },
          { label: 'Servir en HTTP simple', text: 'Désactivé par défaut. Répond aussi au SCEP sur le port du protocole HTTP (8080 par défaut), à http://votre-serveur:8080/scep/pkiclient.exe et aux URL de profil, pour les clients comme sscep qui ne peuvent pas utiliser HTTPS. RFC 8894 §7.10 : les messages SCEP sont déjà protégés, l\'enveloppe CMS garde le mot de passe de défi privé' },
          { label: 'Mot de passe de défi', text: 'Secret partagé que les appareils utilisent pour authentifier l\'inscription. Un renouvellement (RenewalReq) signé par un certificat émis par le même endpoint (profil ou global) est authentifié par ce certificat : son défi n\'est pas vérifié et changer le secret n\'empêche pas les appareils enrôlés de renouveler (RFC 8894 §2.4). Tout autre certificat a toujours besoin du défi de l\'endpoint' },
          { label: 'Clés des appareils (v2.248)', text: 'Un appareil signe sa requête avec une clé RSA, ECDSA, Ed25519 ou ML-DSA ; une signature ML-DSA suit la RFC 9882 (condensat SHA-512). Ed448 est refusé, ML-DSA aussi en mode FIPS' },
        ]
      },
      {
        title: 'Profils',
        items: [
          { label: 'Segment d\'URL', text: 'Chaque profil est servi sur /scep/<segment>/pkiclient.exe, pointez chaque flotte d\'appareils ou profil MDM vers sa propre URL' },
          { label: 'Template de certificat', text: 'Quand un template est lié, ses usages de clé (KU/EKU) et sa validité gouvernent chaque certificat émis via le profil' },
          { label: "Digest de signature (v2.251)", text: "Les certificats émis via un profil sont signés avec le condensat de son template, relevé à celui qui correspond à la clé de l'AC, comme préférence que les politiques peuvent écarter. Sans template, le condensat de la clé de l'AC s'applique" },
          { label: 'Challenge par profil', text: 'Chaque profil a son propre mot de passe de défi, stocké chiffré, avec la même fenêtre d\'expiration que le challenge global' },
          { label: 'Endpoint par défaut', text: 'L\'endpoint /scep/pkiclient.exe sans segment continue de servir la configuration globale' },
          { label: 'Validation Microsoft Intune', text: 'Un profil peut se valider face au challenge SCEP propre à Intune par appareil au lieu d\'un mot de passe statique : choisissez une inscription d\'application dans l\'onglet Inscriptions d\'application Intune (permissions SCEP challenge validation + Application.Read.All), l\'approbation automatique reste obligatoire ; à la mise à niveau, chaque profil existant reçoit une app nommée d\'après lui, dédupliquée par locataire et client' },
          { label: 'Approbation manuelle', text: 'Une requête arrivée via un profil est approuvée avec le template de ce profil (validité, usages de clé), exactement comme l\'approbation automatique l\'émettrait' },
          { label: 'Usages interdits aux enrôlés', text: 'Un template lié à un profil ne peut pas porter la signature OCSP, l\'horodatage, « any purpose » ou Smartcard Logon, et un renouvellement SCEP ne les reporte jamais ; Smartcard Logon est autorisé quand le profil se valide face à Intune, qui se porte garant de l\'identité' },
        ]
      },
    ],
    tips: [
      'Utilisez des mots de passe de défi uniques par CA pour un meilleur audit de sécurité',
      'L\'approbation automatique est pratique mais examinez les requêtes manuellement dans les environnements haute sécurité',
      'URL SCEP : https://votre-serveur:8443/scep/pkiclient.exe pour la CA configurée, https://votre-serveur:8443/scep/<profil>/pkiclient.exe pour un profil',
      'Les profils Intune nécessitent l\'approbation automatique : l\'inscription Intune est un aller-retour synchrone de validation puis émission, sans file d\'approbation côté Intune',
    ],
    warnings: [
      'Le mot de passe de défi se trouve dans la CSR, qui voyage dans l\'enveloppe CMS chiffrée pour la CA (RFC 8894 §2.4) : le HTTP simple ne l\'expose donc pas ; un client qui l\'envoie comme attribut signé hors de l\'enveloppe l\'expose, en HTTP et à tout ce qui journalise la requête',
    ],
  },
  helpGuides: {
    title: 'Serveur SCEP',
    content: `
## Vue d'ensemble

Le protocole d'inscription de certificat simplifié (SCEP) permet aux appareils réseau : routeurs, commutateurs, pare-feu, terminaux gérés par MDM, de demander et d'obtenir automatiquement des certificats.

## Onglets

### Requêtes
Voir toutes les requêtes d'inscription SCEP :
- **En attente** : En attente d'approbation manuelle (si l'approbation automatique est désactivée)
- **Approuvées** : Émises avec succès
- **Rejetées** : Refusées par un administrateur

### Configuration
Configurer le serveur SCEP :
- **Activer/Désactiver** : Basculer le service SCEP
- **CA de signature** : Sélectionner quelle CA signe les certificats inscrits via SCEP. Les appareils chiffrent leur requête pour cette CA, elle doit donc détenir une clé RSA logicielle : les CA EC, adossées à un HSM, sans clé, hors ligne ou révoquées ne sont pas listées (v2.248)
- **Approbation automatique** : Approuver automatiquement les requêtes avec des mots de passe de défi valides

### Profils
Endpoints d'enrôlement nommés, chacun servi sur sa propre URL :

\`\`\`
https://votre-serveur:8443/scep/<profil>/pkiclient.exe
\`\`\`

Chaque profil est lié à :
- **Sa propre CA** : différentes flottes d'appareils peuvent s'enrôler auprès de CAs différentes
- **Un template de certificat optionnel** : quand un template est lié, ses usages de clé (KU/EKU) et sa validité gouvernent chaque certificat émis via le profil
- **Usages interdits aux enrôlés** : un template lié à un profil ne peut pas porter la signature OCSP, l'horodatage, « any purpose » ou Smartcard Logon, et un renouvellement SCEP ne les reporte jamais ; Smartcard Logon est autorisé quand le profil se valide face à Intune, qui se porte garant de l'identité
- **Un mot de passe de défi par profil** : stocké chiffré, avec la même fenêtre d'expiration que le challenge global
- **Une politique d'approbation** : approbation automatique ou revue manuelle par profil

Pointez chaque flotte d'appareils, profil MDM ou tenant vers sa propre URL de profil. L'endpoint \`/scep/pkiclient.exe\` sans segment continue de servir la configuration globale sans changement.

### Mots de passe de défi
L'onglet **Défis** affiche les mots de passe de défi. Les appareils doivent inclure un mot de passe de défi valide dans leur requête d'inscription pour s'authentifier.

- **Voir le mot de passe** : Afficher le défi actuel pour une CA
- **Régénérer** : Créer un nouveau mot de passe de défi (invalide l'ancien)

### Informations
Affiche l'URL du point de terminaison SCEP et les instructions d'intégration.

## Flux d'inscription SCEP

1. L'appareil envoie une requête **GetCACert** pour obtenir le certificat de la CA
2. L'appareil génère une paire de clés et crée une CSR
3. L'appareil enveloppe la CSR avec le **mot de passe de défi** et envoie un **PKCSReq**
4. UCM valide le mot de passe de défi
5. Si l'approbation automatique est activée, UCM signe et retourne le certificat
6. Si l'approbation automatique est désactivée, un administrateur examine et approuve/rejette

### Clés des appareils
L'appareil signe son PKCSReq avec sa propre clé : RSA, ECDSA, Ed25519 ou ML-DSA. Une signature ML-DSA est vérifiée selon la RFC 9882 (condensat SHA-512, identifiant d'algorithme propre à la clé, sans paramètres). Les signatures Ed448 sont refusées, et ML-DSA aussi en mode FIPS. La requête reste chiffrée pour la CA de signature RSA.

## URL SCEP

\`\`\`
https://votre-serveur:8443/scep/pkiclient.exe            (CA configurée)
https://votre-serveur:8443/scep/<profil>/pkiclient.exe   (endpoint par profil)
https://votre-serveur:8443/cgi-bin/pkiclient.exe         (CA configurée, chemin hérité)
http://votre-serveur:8080/scep/pkiclient.exe             (avec Servir en HTTP simple)
\`\`\`

Les appareils ont besoin de l'URL pour s'inscrire ; \`/scep\` seul est l'interface web, pas un endpoint SCEP. Utilisez une URL de profil pour cibler la CA, le template et le mot de passe de défi de ce profil.

### Bascule de CA (GetNextCACert)
GetNextCACert sert le successeur de la CA de l'endpoint, signé par la CA actuelle : une autre CA avec le même parent et le même DN de sujet, non révoquée, non hors ligne, détenant une clé RSA logicielle, et expirant plus tard. Une CA qui ne partage que le nom d'affichage n'est jamais servie ; sans successeur, la réponse est 404.

## Approuver/Rejeter des requêtes

Pour les requêtes en attente (approbation automatique désactivée) :
1. Examinez les détails de la requête (sujet, ID de transaction, statut, CSR)
2. Cliquez sur **Approuver** pour signer et émettre le certificat
3. Ou cliquez sur **Rejeter** avec un motif

Une requête arrivée via un profil est émise avec le template de ce profil (validité, usages de clé), exactement comme le ferait l'approbation automatique.

> Le mot de passe de défi se trouve dans la CSR, qui voyage dans l'enveloppe CMS chiffrée pour la CA (RFC 8894 §2.4) : le HTTP simple ne l'expose donc pas. Un client qui l'envoie comme attribut signé hors de l'enveloppe l'expose : gardez ces clients sur HTTPS.

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
Intune ne prend pas en charge un mot de passe de défi statique : il émet son propre défi chiffré par appareil que seule l'API Intune peut valider. Sur un **profil** SCEP (pas le point de terminaison global), activez **Validation du challenge SCEP Microsoft Intune** et fournissez l'ID de locataire, l'ID client et le secret client d'une inscription d'application Entra :

1. Dans Microsoft Entra ID, inscrivez une application et accordez-lui les autorisations d'application **Intune API → SCEP challenge validation** (\`scep_challenge_provider\`) et **Microsoft Graph → Application.Read.All**, toutes deux avec consentement administrateur
2. Dans **Inscriptions d'application Intune**, ajoutez l'inscription d'application une seule fois (nom, ID de locataire, ID client, secret client) et cliquez sur **Tester la connexion** pour confirmer que UCM peut joindre Intune ; choisissez-la ensuite dans le sélecteur **Inscription d'application** du profil. Les profils d'un même locataire la partagent, le secret se renouvelle donc à un seul endroit
3. Dans Intune, pointez l'URL du serveur du profil SCEP de l'appareil vers le point de terminaison \`/scep/<segment>/pkiclient.exe\` de ce profil

Les profils avec Intune activé doivent avoir l'**approbation automatique** activée : l'inscription Intune est un aller-retour synchrone de validation puis émission, sans file d'attente côté Intune pour une revue manuelle.
`
  }
}
