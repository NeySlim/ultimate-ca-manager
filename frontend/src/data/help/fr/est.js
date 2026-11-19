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
          { label: "Points d'accès EST", text: 'URL des points de terminaison EST pour l\'intégration et statistiques d\'inscription' },
        ]
      },
      {
        title: 'Authentification',
        items: [
          { label: 'mTLS (TLS mutuel)', text: 'Le client présente un certificat lors de la poignée de main TLS, méthode d\'authentification la plus forte' },
          { label: 'HTTP Basic Auth', text: 'Repli par nom d\'utilisateur/mot de passe lorsque mTLS n\'est pas disponible. Avec allow_empty_username défini via PATCH /api/v2/est/config, un client peut aussi envoyer un nom d\'utilisateur vide avec le mot de passe (RFC 7030 §3.2.3, v2.252)' },
          { label: 'Certificat présenté', text: 'Pour /simpleenroll et /serverkeygen en mTLS, un certificat signé par la CA EST doit être un certificat qu\'elle détient encore : les certificats révoqués, remplacés ou supprimés sont refusés (RFC 7030 §3.3.2) ; un certificat qu\'une autre CA de ce serveur a émis est refusé dès que lui ou une CA au-dessus est révoqué, ou une fois expiré (v2.252) ; celui d\'une autorité que ce serveur ne détient pas est laissé à la couche TLS' },
          { label: 'Liaison tls-unique', text: 'Une CSR avec un challengePassword doit porter la valeur tls-unique de sa connexion TLS 1.2 vers UCM (RFC 7030 §3.5) ; elle est refusée avec 400 quand la valeur diffère ou ne peut pas être vérifiée (TLS 1.3, proxy devant). /csrattrs n\'en demande pas. ignore_challenge_password, défini via PATCH /api/v2/est/config, désactive la vérification pour un client qui y met un mot de passe (v2.252)' },
          { label: 'Clés compromises', text: 'Une CSR dont la clé a été révoquée comme compromise (keyCompromise) est refusée avec 400 (v2.252)' },
        ]
      },
      {
        title: 'Points de terminaison',
        items: [
          { label: '/cacerts', text: 'Récupérer la chaîne de certificats CA (aucune authentification requise)' },
          { label: '/simpleenroll', text: 'Soumettre une CSR et recevoir un certificat signé' },
          { label: '/simplereenroll', text: 'Renouveler un certificat existant (nécessite mTLS ; sans certificat client : 403). Une CSR sans SubjectAltName renouvelle les noms propres du certificat, ou aucun s\'il n\'en avait pas, au lieu d\'un nom construit à partir du CN (RFC 7030 §4.2.2, v2.252)' },
          { label: '/csrattrs', text: 'Obtenir les attributs CSR recommandés par le serveur : keyUsage, subjectAltName et extKeyUsage sous forme d\'OID nus (RFC 9908 §5.2, v2.252). csrattrs_legacy_encoding, défini via PATCH /api/v2/est/config, sert l\'ancienne forme (les OID dans une extensionRequest) pour un client qui en a besoin' },
          { label: 'Erreurs', text: 'Les refus d\'inscription, limitation de débit comprise, arrivent sous forme d\'un message en texte brut (text/plain, RFC 8951 §5) qui en donne la raison, par exemple un corps qui n\'est pas du base64 ou pas une CSR PKCS#10, ou les contraintes de noms de la CA (v2.252)' },
          { label: '/serverkeygen', text: 'Le serveur génère une paire de clés et retourne le certificat + la clé. La clé prend la force de l\'AC émettrice, dans la famille de la clé de la requête si elle est RSA ou EC (sa taille ou sa courbe est ignorée), sinon celle de l\'AC, ramenée au type autorisé le plus proche par les politiques. La clé est livrée en PKCS#8 non chiffré sous TLS ; une CSR qui nomme la clé du certificat mTLS (AsymmetricDecryptKeyIdentifier) la reçoit chiffrée vers ce certificat, par transport de clé pour une clé RSA de 2048 bits ou plus (keyEncipherment) ou par accord de clé pour une clé EC (keyAgreement), avec les algorithmes que liste la SMIMECapabilities de la CSR, dans un paquet de clé signé par un certificat « EST key generator » que l\'AC émettrice délivre à cet effet (Ed25519 sous une AC Ed448, v2.252)' },
        ]
      },
    ],
    tips: [
      'EST est le remplacement moderne de SCEP : préférez EST pour les nouveaux déploiements',
      'Utilisez l\'authentification mTLS pour la meilleure sécurité : Basic Auth est un repli',
      'Le point de terminaison /simplereenroll nécessite que le client présente son certificat actuel via mTLS',
      'Copiez les URL des points de terminaison depuis l\'onglet Points d\'accès EST pour configurer vos clients EST',
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
- **Port 8443** : quand UCM termine le TLS, la poignée de main accepte les certificats de la CA de confiance mTLS (Paramètres → Sécurité) et des CA situées en dessous uniquement ; pour ré-inscrire des certificats d'une CA EST hors de cette branche, faites confiance à une CA au-dessus des deux (v2.252)
- **Certificat présenté** : pour \`/simpleenroll\` et \`/serverkeygen\`, un certificat signé par la CA EST doit être un certificat qu'elle détient encore : les certificats révoqués, remplacés ou supprimés sont refusés (RFC 7030 §3.3.2). Un certificat qu'une autre CA de ce serveur a émis est refusé dès que lui ou une CA au-dessus est révoqué, ou une fois expiré (v2.252) ; celui d'une autorité que ce serveur ne détient pas est laissé à la couche TLS
- **Liaison tls-unique** : une CSR avec un \`challengePassword\` doit porter la valeur \`tls-unique\` de sa connexion TLS 1.2 vers UCM (RFC 7030 §3.5), et est refusée avec 400 quand la valeur diffère ou ne peut pas être vérifiée (TLS 1.3, proxy devant) ; \`/csrattrs\` n'en demande pas. \`ignore_challenge_password\`, défini via \`PATCH /api/v2/est/config\`, désactive la vérification pour un client qui y met un mot de passe (v2.252)
- **Dépend de** la configuration correcte de la terminaison TLS (le proxy inverse doit transmettre \`SSL_CLIENT_CERT\` à UCM)

### HTTP Basic Auth. Repli

Authentification par nom d'utilisateur et mot de passe via HTTPS. Configurée dans les paramètres EST.

- **Plus simple à configurer** : aucun certificat client nécessaire
- **Moins sécurisé** : identifiants transmis par requête (protégés par HTTPS)
- **À utiliser quand** l'infrastructure mTLS n'est pas disponible
- **Mot de passe seul** : avec \`allow_empty_username\` défini via \`PATCH /api/v2/est/config\`, un client peut envoyer un nom d'utilisateur vide avec le mot de passe (RFC 7030 §3.2.3, v2.252)

Une CSR dont la clé a été révoquée comme compromise est refusée avec 400, et chaque refus d'inscription, limitation de débit comprise, arrive sous forme d'un message en texte brut qui en donne la raison (RFC 8951 §5, v2.252).

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
Renouveler un certificat existant. **Nécessite mTLS** : le client doit présenter le certificat à renouveler, sinon 403. Une CSR sans SubjectAltName renouvelle les noms propres du certificat, ou aucun s'il n'en avait pas, et non un nom construit à partir du CN (RFC 7030 §4.2.2, v2.252).

\`\`\`bash
curl -k --cert client.pem --key client.key \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @csr.pem \\
  https://votre-serveur:8443/.well-known/est/simplereenroll
\`\`\`

### GET /csrattrs
Obtenir les attributs CSR recommandés par le serveur : keyUsage, subjectAltName et extKeyUsage sous forme d'OID nus, la forme que donne la RFC 9908 §5.2 pour un OID demandé sans valeur (v2.252). Un client qui a besoin de l'ancienne forme (les OID dans un attribut extensionRequest) l'obtient avec \`csrattrs_legacy_encoding\`, défini via \`PATCH /api/v2/est/config\`.

### POST /serverkeygen
Le serveur génère une paire de clés et retourne le certificat accompagné de la clé privée. Utile lorsque le client ne peut pas générer de clés localement.

La clé générée prend la force de l'AC émettrice : la famille de la clé de la requête si elle est RSA ou EC (sa taille ou sa courbe est ignorée), sinon celle de l'AC, ramenée au type autorisé le plus proche par les politiques. 

La clé privée est livrée en PKCS#8 non chiffré (\`application/pkcs8\`), protégée par TLS. Pour l'obtenir chiffrée, authentifiez-vous en mTLS et placez l'identifiant de clé du certificat client dans la CSR (AsymmetricDecryptKeyIdentifier) : la clé arrive alors dans un paquet de clé RFC 5958 enveloppé pour ce certificat, par transport de clé pour un certificat RSA de 2048 bits ou plus déclarant keyEncipherment, ou par accord de clé (ECDH) pour un certificat EC déclarant keyAgreement, les algorithmes de transport ou d'accord de clé et de contenu étant tirés de la SMIMECapabilities de la CSR, dans l'ordre du client. Le paquet est signé par un certificat « EST key generator » que l'AC émettrice délivre à la première utilisation et renouvelle seule ; il se rattache à l'AC que sert \`/cacerts\` et a la famille de clé de l'AC, Ed25519 sous une AC Ed448 (v2.252).

## Onglet Points d'accès EST

L'onglet Points d'accès EST affiche :
- **URL des points de terminaison** : URL prêtes à copier-coller pour chaque opération EST
- **Statistiques d'inscription** : inscriptions totales, réussies et en échec

## Exemples d'intégration

### Utiliser le client est (libest)
Utilisez \`estclient\` avec des identifiants HTTP Basic (\`-u\` et \`-h\`) ou un certificat client. Ses options TLS-SRP ne s'appliquent pas : UCM n'offre pas TLS-SRP.

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
  base64 -d | openssl pkcs7 -inform DER -print_certs -out client.pem
\`\`\`

La réponse est un PKCS#7 en base64 (certs-only), pas un certificat nu : lisez-la avec \`openssl pkcs7\`, pas \`openssl x509\`.

### Windows
Windows n'a pas de client EST intégré : \`certutil -enrollmentServerURL\` enregistre un service web d'inscription de certificats (WSTEP), pas un serveur EST. Pour les machines Windows, utilisez l'inscription automatique Windows (XCEP/WSTEP).

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
