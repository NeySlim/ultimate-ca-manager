export default {
  helpContent: {
    title: 'TSA',
    subtitle: 'Autorité d\'horodatage',
    overview: 'TSA (RFC 3161) fournit des horodatages de confiance qui prouvent qu\'un document ou un hash existait à un moment précis. Utilisé pour la signature de code, la conformité juridique et les pistes d\'audit.',
    sections: [
      {
        title: 'Onglets',
        items: [
          { label: 'Paramètres', text: 'Activer TSA, sélectionner la CA de signature et configurer l\'OID de politique TSA' },
          { label: 'Informations', text: 'URL du point de terminaison TSA, exemples d\'utilisation avec OpenSSL et statistiques de requêtes' },
        ]
      },
      {
        title: 'Configuration',
        items: [
          { label: 'CA de signature', text: 'La CA dont la clé privée signe les jetons d\'horodatage — doit être une CA valide et non expirée' },
          { label: 'OID de politique', text: 'Identifiant d\'objet pour la politique TSA (par ex. 1.2.3.4.1) — inclus dans chaque réponse d\'horodatage' },
          { label: 'Activer/Désactiver', text: 'Basculer le point de terminaison TSA sans perdre la configuration' },
        ]
      },
      {
        title: 'Utilisation',
        items: [
          { label: 'Créer une requête', text: 'openssl ts -query -data file.txt -sha256 -no_nonce -out request.tsq' },
          { label: 'Envoyer au TSA', text: 'curl -H "Content-Type: application/timestamp-query" --data-binary @request.tsq https://votre-serveur/tsa -o response.tsr' },
          { label: 'Vérifier', text: 'openssl ts -verify -data file.txt -in response.tsr -CAfile ca-chain.pem' },
        ]
      },
    ],
    tips: [
      'Les horodatages TSA sont utilisés dans la signature de code pour garantir que les signatures restent valides après l\'expiration du certificat',
      'Le point de terminaison TSA accepte les requêtes HTTP POST avec Content-Type: application/timestamp-query',
      'Utilisez SHA-256 ou des algorithmes de hachage plus forts lors de la création de requêtes d\'horodatage',
      'Aucune authentification n\'est requise — le point de terminaison TSA est accessible publiquement comme CRL/OCSP',
    ],
    warnings: [
      'Une CA de signature valide doit être configurée avant d\'activer TSA',
      'Le point de terminaison TSA est un point de terminaison de protocole public — ne mettez pas de données sensibles dans les requêtes d\'horodatage',
    ],
  },
  helpGuides: {
    title: 'Protocole TSA',
    content: `
## Vue d'ensemble

L'autorité d'horodatage (TSA) implémente le **RFC 3161** pour fournir des horodatages de confiance qui prouvent cryptographiquement qu'un document, un hash ou une signature numérique existait à un moment précis. TSA est largement utilisé pour la signature de code, la conformité juridique, l'archivage à long terme et les pistes d'audit.

## Comment ça fonctionne

1. **Le client crée une requête d'horodatage** — hache un fichier avec SHA-256/SHA-512 et crée un \`TimeStampReq\` (encodé ASN.1 DER)
2. **Le client envoie la requête au TSA** — HTTP POST vers le point de terminaison \`/tsa\` avec \`Content-Type: application/timestamp-query\`
3. **UCM signe l'horodatage** — la CA configurée signe le hash + l'heure actuelle dans un \`TimeStampResp\`
4. **Le client reçoit et stocke la réponse** — le fichier \`.tsr\` peut ensuite prouver que le document existait à ce moment

## Configuration

### Onglet Paramètres

1. **Activer TSA** — Basculer le serveur TSA on ou off
2. **CA de signature** — Sélectionner quelle autorité de certification signe les jetons d'horodatage
3. **OID de politique** — Identifiant d'objet pour la politique TSA (par ex. \`1.2.3.4.1\`), inclus dans chaque réponse d'horodatage

### Choisir une CA de signature

La clé privée de la CA de signature est utilisée pour signer chaque jeton d'horodatage. Bonnes pratiques :

- Utilisez une **sous-CA dédiée** pour l'horodatage plutôt que votre CA racine
- Le certificat de la CA devrait inclure l'utilisation étendue de la clé **id-kp-timeStamping** (OID 1.3.6.1.5.5.7.3.8)
- Assurez-vous que le certificat de la CA a une **validité suffisante** — les horodatages doivent rester vérifiables pendant des années

### OID de politique

L'OID de politique identifie la politique TSA sous laquelle les horodatages sont émis. Il est intégré dans chaque \`TimeStampResp\`.

- Par défaut : \`1.2.3.4.1\` (espace réservé)
- En production, enregistrez un OID sous l'arc de votre organisation ou utilisez-en un de votre CP/CPS

## Onglet Informations

L'onglet Informations affiche :

- **URL du point de terminaison TSA** — URL prête à copier-coller pour la configuration client
- **Exemples d'utilisation** — Commandes OpenSSL pour créer des requêtes, les envoyer et vérifier les réponses
- **Statistiques** — Total des requêtes d'horodatage traitées (réussies et échouées)

## Exemples d'utilisation

### Créer une requête d'horodatage

\`\`\`bash
# Hacher un fichier et créer une requête d'horodatage
openssl ts -query -data file.txt -sha256 -no_nonce -out request.tsq
\`\`\`

### Envoyer la requête au TSA

\`\`\`bash
# Envoyer la requête et recevoir une réponse d'horodatage
curl -s -H "Content-Type: application/timestamp-query" \\
  --data-binary @request.tsq \\
  https://votre-serveur:8443/tsa -o response.tsr
\`\`\`

### Vérifier un horodatage

\`\`\`bash
# Vérifier la réponse d'horodatage par rapport au fichier original
openssl ts -verify -data file.txt -in response.tsr \\
  -CAfile ca-chain.pem
\`\`\`

### Signature de code avec horodatages

Lors de la signature de code, ajoutez l'URL TSA pour garantir que les signatures restent valides après l'expiration du certificat :

\`\`\`bash
# Signer avec horodatage (osslsigncode)
osslsigncode sign -certs cert.pem -key key.pem \\
  -ts https://votre-serveur:8443/tsa \\
  -in app.exe -out app-signed.exe

# Signer avec horodatage (signtool.exe sous Windows)
signtool sign /fd SHA256 /tr https://votre-serveur:8443/tsa \\
  /td SHA256 /f cert.pfx app.exe
\`\`\`

### Horodatages de documents PDF

\`\`\`bash
# Créer un horodatage détaché pour un PDF
openssl ts -query -data document.pdf -sha256 -cert \\
  -out document.tsq

curl -s -H "Content-Type: application/timestamp-query" \\
  --data-binary @document.tsq \\
  https://votre-serveur:8443/tsa -o document.tsr
\`\`\`

## Détails du protocole

| Propriété | Valeur |
|-----------|--------|
| RFC | 3161 (Internet X.509 PKI TSP) |
| Point de terminaison | \`/tsa\` (POST) |
| Content-Type | \`application/timestamp-query\` |
| Type de réponse | \`application/timestamp-reply\` |
| Algorithmes de hachage | SHA-256, SHA-384, SHA-512, SHA-1 (hérité) |
| Authentification | Aucune (point de terminaison public) |
| Transport | HTTP ou HTTPS |

## Considérations de sécurité

- Le point de terminaison TSA est **public** — aucune authentification n'est requise (comme CRL/OCSP)
- Chaque réponse d'horodatage est **signée** par la clé de la CA — les clients vérifient la signature pour garantir l'authenticité
- Utilisez **SHA-256 ou plus fort** pour les algorithmes de hachage lors de la création de requêtes (SHA-1 est accepté mais déconseillé)
- Le TSA ne **voit pas** le document original — seul le hash est transmis
- Envisagez la **limitation de débit** si le point de terminaison TSA est exposé à Internet

> 💡 Les horodatages sont essentiels pour la signature de code : ils garantissent que votre logiciel signé reste de confiance même après l'expiration du certificat de signature.
`
  }
}
