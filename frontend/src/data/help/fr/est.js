export default {
  helpContent: {
    title: 'EST',
    subtitle: 'Inscription par transport sécurisé',
    overview: 'EST (RFC 7030) fournit une inscription sécurisée de certificats via HTTPS avec TLS mutuel (mTLS) ou authentification HTTP Basic. Idéal pour les environnements d\'entreprise modernes nécessitant une inscription basée sur des standards avec une forte sécurité de transport.',
    sections: [
      {
        title: 'Onglets',
        items: [
          { label: 'Paramètres', text: 'Activer EST, sélectionner la CA de signature, configurer les identifiants d\'authentification et la validité des certificats' },
          { label: 'Informations', text: 'URL des points de terminaison EST pour l\'intégration, statistiques d\'inscription et exemples d\'utilisation' },
        ]
      },
      {
        title: 'Authentification',
        items: [
          { label: 'mTLS (TLS mutuel)', text: 'Le client présente un certificat lors de la poignée de main TLS, méthode d\'authentification la plus forte' },
          { label: 'HTTP Basic Auth', text: 'Repli par nom d\'utilisateur/mot de passe lorsque mTLS n\'est pas disponible' },
          { label: 'Certificat présenté', text: 'Pour /simpleenroll et /serverkeygen en mTLS, un certificat signé par la CA EST doit être un certificat qu\'elle détient encore : les certificats révoqués, remplacés ou supprimés sont refusés (RFC 7030 §3.3.2) ; un certificat d\'une autre autorité à laquelle la couche TLS fait confiance reste accepté' },
        ]
      },
      {
        title: 'Points de terminaison',
        items: [
          { label: '/cacerts', text: 'Récupérer la chaîne de certificats CA (aucune authentification requise)' },
          { label: '/simpleenroll', text: 'Soumettre une CSR et recevoir un certificat signé' },
          { label: '/simplereenroll', text: 'Renouveler un certificat existant (nécessite mTLS)' },
          { label: '/csrattrs', text: 'Obtenir les attributs CSR recommandés par le serveur' },
          { label: '/serverkeygen', text: 'Le serveur génère une paire de clés et retourne le certificat + la clé. La clé prend la force de l\'AC émettrice, dans la famille de la clé de la requête si elle est RSA ou EC (sa taille ou sa courbe est ignorée), sinon celle de l\'AC, ramenée au type autorisé le plus proche par les politiques. La clé est livrée en PKCS#8 non chiffré sous TLS ; une CSR qui nomme la clé du certificat mTLS (AsymmetricDecryptKeyIdentifier) la reçoit chiffrée vers ce certificat, par transport de clé pour une clé RSA de 2048 bits ou plus (keyEncipherment) ou par accord de clé pour une clé EC (keyAgreement), avec les algorithmes que liste la SMIMECapabilities de la CSR, dans un paquet de clé signé par un certificat « EST key generator » que l\'AC émettrice délivre à cet effet (Ed25519 sous une AC Ed448, v2.252)' },
        ]
      },
    ],
    tips: [
      'EST est le remplacement moderne de SCEP : préférez EST pour les nouveaux déploiements',
      'Utilisez l\'authentification mTLS pour la meilleure sécurité : Basic Auth est un repli',
      'Le point de terminaison /simplereenroll nécessite que le client présente son certificat actuel via mTLS',
      'Copiez les URL des points de terminaison depuis l\'onglet Informations pour configurer vos clients EST',
    ],
    warnings: [
      'EST nécessite HTTPS : le client doit faire confiance au certificat du serveur UCM ou à la CA',
      'L\'authentification mTLS nécessite une configuration correcte de la terminaison TLS (le proxy inverse doit transmettre les certificats client)',
    ],
  },
  helpGuides: {
    title: 'Protocole EST',
    content: `
## Vue d'ensemble

L'inscription par transport sécurisé (EST) est définie dans le **RFC 7030** et fournit l'inscription de certificats, la ré-inscription et la récupération de certificats CA via HTTPS. EST est le remplacement moderne de SCEP, offrant une sécurité renforcée grâce à l'authentification TLS mutuel (mTLS).

## Configuration

### Onglet Paramètres

1. **Activer EST** : Basculer le protocole EST on ou off
2. **CA de signature** : Sélectionner quelle autorité de certification signe les certificats inscrits via EST
3. **Authentification** : Configurer les identifiants HTTP Basic Auth (nom d'utilisateur et mot de passe)
4. **Validité du certificat** : Période de validité par défaut pour les certificats émis via EST (en jours)

### Enregistrer la configuration

Cliquez sur **Enregistrer** pour appliquer les modifications. Les points de terminaison EST deviennent disponibles immédiatement lorsqu'ils sont activés.

## Authentification

EST prend en charge deux méthodes d'authentification :

### TLS mutuel (mTLS) : Recommandé

Le client présente un certificat lors de la poignée de main TLS. UCM valide le certificat et authentifie le client automatiquement.

- **Méthode la plus forte** : identité client cryptographique
- **Requis pour** \`/simplereenroll\` : le client doit présenter son certificat actuel
- **Certificat présenté** : pour \`/simpleenroll\` et \`/serverkeygen\`, un certificat signé par la CA EST doit être un certificat qu'elle détient encore : les certificats révoqués, remplacés ou supprimés sont refusés (RFC 7030 §3.3.2) ; un certificat d'une autre autorité de confiance reste accepté
- **Dépend de** la configuration correcte de la terminaison TLS (le proxy inverse doit transmettre \`SSL_CLIENT_CERT\` à UCM)

### HTTP Basic Auth. Repli

Authentification par nom d'utilisateur et mot de passe via HTTPS. Configurée dans les paramètres EST.

- **Plus simple à configurer** : aucun certificat client nécessaire
- **Moins sécurisé** : identifiants transmis par requête (protégés par HTTPS)
- **À utiliser quand** l'infrastructure mTLS n'est pas disponible

## Points de terminaison EST

Tous les points de terminaison sont sous \`/.well-known/est/\` :

### GET /cacerts
Récupérer la chaîne de certificats CA. **Aucune authentification requise.**

Utilisez ceci pour établir la confiance : les clients récupèrent le certificat CA avant l'inscription.

\`\`\`bash
curl -k https://votre-serveur:8443/.well-known/est/cacerts | \\
  base64 -d | openssl pkcs7 -inform DER -print_certs
\`\`\`

### POST /simpleenroll
Soumettre une CSR PKCS#10 et recevoir un certificat signé.

Nécessite une authentification (mTLS ou Basic Auth).

\`\`\`bash
# Avec curl et Basic Auth
curl -k --user est-user:est-password \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @csr.pem \\
  https://votre-serveur:8443/.well-known/est/simpleenroll
\`\`\`

### POST /simplereenroll
Renouveler un certificat existant. **Nécessite mTLS** : le client doit présenter le certificat à renouveler.

\`\`\`bash
curl -k --cert client.pem --key client.key \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @csr.pem \\
  https://votre-serveur:8443/.well-known/est/simplereenroll
\`\`\`

### GET /csrattrs
Obtenir les attributs CSR (OID) recommandés par le serveur.

### POST /serverkeygen
Le serveur génère une paire de clés et retourne le certificat accompagné de la clé privée. Utile lorsque le client ne peut pas générer de clés localement.

La clé générée prend la force de l'AC émettrice : la famille de la clé de la requête si elle est RSA ou EC (sa taille ou sa courbe est ignorée), sinon celle de l'AC, ramenée au type autorisé le plus proche par les politiques. 

La clé privée est livrée en PKCS#8 non chiffré (\`application/pkcs8\`), protégée par TLS. Pour l'obtenir chiffrée, authentifiez-vous en mTLS et placez l'identifiant de clé du certificat client dans la CSR (AsymmetricDecryptKeyIdentifier) : la clé arrive alors dans un paquet de clé RFC 5958 enveloppé pour ce certificat, par transport de clé pour un certificat RSA de 2048 bits ou plus déclarant keyEncipherment, ou par accord de clé (ECDH) pour un certificat EC déclarant keyAgreement, les algorithmes de transport ou d'accord de clé et de contenu étant tirés de la SMIMECapabilities de la CSR, dans l'ordre du client. Le paquet est signé par un certificat « EST key generator » que l'AC émettrice délivre à la première utilisation et renouvelle seule ; il se rattache à l'AC que sert \`/cacerts\` et a la famille de clé de l'AC, Ed25519 sous une AC Ed448 (v2.252).

## Onglet Informations

L'onglet Informations affiche :
- **URL des points de terminaison** : URL prêtes à copier-coller pour chaque opération EST
- **Statistiques d'inscription** : Nombre d'inscriptions, de ré-inscriptions et d'erreurs
- **Dernière activité** : Opérations EST les plus récentes depuis les journaux d'audit

## Exemples d'intégration

### Utiliser le client est (libest)
\`\`\`bash
estclient -s votre-serveur -p 8443 \\
  --srp-user est-user --srp-password est-password \\
  -o /tmp/certs --enroll
\`\`\`

### Utiliser OpenSSL
\`\`\`bash
# Récupérer les certificats CA
curl -k https://votre-serveur:8443/.well-known/est/cacerts | \\
  base64 -d > cacerts.p7

# Générer une CSR
openssl req -new -newkey rsa:2048 -nodes \\
  -keyout client.key -out client.csr \\
  -subj "/CN=mon-appareil/O=MonOrg"

# Inscrire (Basic Auth)
curl -k --user est-user:est-password \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @<(openssl req -in client.csr -outform DER | base64) \\
  https://votre-serveur:8443/.well-known/est/simpleenroll | \\
  base64 -d | openssl x509 -inform DER -out client.pem
\`\`\`

### Windows (certutil)
\`\`\`cmd
certutil -enrollmentServerURL add \\
  "https://votre-serveur:8443/.well-known/est" \\
  kerberos
\`\`\`

## EST vs SCEP

| Caractéristique | EST | SCEP |
|-----------------|-----|------|
| Transport | HTTPS (TLS) | HTTP ou HTTPS |
| Authentification | mTLS + Basic Auth | Mot de passe de défi |
| Standard | RFC 7030 (2013) | RFC 8894 (2020, mais hérité) |
| Génération de clé | Option côté serveur | Client uniquement |
| Renouvellement | Ré-inscription mTLS | Ré-inscription |
| Sécurité | Forte (basée sur TLS) | Plus faible (secret partagé) |
| Recommandation | ✅ Préféré pour les nouveaux | Appareils hérités uniquement |

> 💡 Utilisez EST pour les nouveaux déploiements. Utilisez SCEP uniquement pour les appareils réseau hérités qui ne prennent pas en charge EST.
`
  }
}
