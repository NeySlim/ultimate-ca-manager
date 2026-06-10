export default {
  helpContent: {
    title: 'ACME',
    subtitle: 'Gestion automatisée des certificats',
    overview: 'UCM prend en charge deux modes ACME : client ACME pour les certificats publics depuis tout CA conforme RFC 8555 (Let\'s Encrypt, ZeroSSL, Buypass, HARICA, etc.), et serveur ACME local pour l\'automatisation PKI interne avec mappage multi-CA de domaines.',
    sections: [
      {
        title: 'Client ACME',
        items: [
          { label: 'Client', text: 'Demander des certificats depuis tout CA ACME — Let\'s Encrypt, ZeroSSL, Buypass, HARICA ou personnalisé' },
          { label: 'Serveur personnalisé', text: 'Définir une URL de répertoire ACME personnalisée pour utiliser tout CA conforme RFC 8555' },
          { label: 'EAB', text: 'Prise en charge de la liaison de compte externe pour les CA nécessitant une pré-inscription (ZeroSSL, HARICA, etc.)' },
          { label: 'Types de clés', text: 'RSA-2048, RSA-4096, ECDSA P-256, ECDSA P-384 pour les clés de certificat' },
          { label: 'Clés de compte', text: 'Algorithmes ES256 (P-256), ES384 (P-384) ou RS256 pour les clés de compte ACME' },
          { label: 'Fournisseurs DNS', text: 'Configurer les fournisseurs de défi DNS-01 (Cloudflare, Route53, etc.)' },
          { label: 'Domaines', text: 'Associer des domaines aux fournisseurs DNS pour la validation automatique' },
        ]
      },
      {
        title: 'Serveur ACME local',
        items: [
          { label: 'Configuration', text: 'Activer/désactiver le serveur ACME intégré, sélectionner la CA par défaut' },
          { label: 'Domaines locaux', text: 'Associer des domaines internes à des CA spécifiques pour l\'émission multi-CA' },
          { label: 'Comptes', text: 'Voir et gérer les comptes clients ACME enregistrés' },
          { label: 'Historique', text: 'Suivre toutes les commandes d\'émission de certificats ACME' },
        ]
      },
      {
        title: 'Proxy ACME',
        items: [
          { label: 'CA en amont', text: 'Sélectionnez un préréglage (Let\'s Encrypt Production/Staging) ou entrez une URL personnalisée pour tout CA RFC 8555' },
          { label: 'État du compte', text: 'Indique si UCM est enregistré auprès du CA en amont. Les comptes sont auto-enregistrés à la première requête proxy' },
          { label: 'Test de connexion', text: 'Vérifiez la connectivité avec le CA en amont et vérifiez si des identifiants EAB sont requis' },
          { label: 'Réinitialiser le compte', text: 'Effacez les identifiants du compte en amont pour forcer une réinscription (à utiliser après un changement de CA)' },
          { label: 'Identifiants EAB', text: 'Identifiants External Account Binding pour les CAs qui les exigent (ex: ZeroSSL, Google Trust)' },
          { label: 'Défis DNS', text: 'UCM gère les défis DNS-01 pour le compte des clients en utilisant les fournisseurs DNS configurés' },
        ]
      },
      {
        title: 'Résolution multi-CA',
        content: 'Lorsqu\'un client ACME demande un certificat, UCM résout la CA de signature dans cet ordre :',
        items: [
          '1. Mappage de domaine local — correspondance exacte du domaine, puis domaine parent',
          '2. Mappage de domaine DNS — vérifie la CA émettrice configurée pour le fournisseur DNS',
          '3. Valeur par défaut globale — la CA définie dans la configuration du serveur ACME',
          '4. Première CA disponible avec une clé privée',
        ]
      },
      {
        title: 'Identifiants EAB (côté serveur)',
        content: 'Lorsque UCM joue le rôle de serveur ACME, le External Account Binding (RFC 8555 §7.3.4) permet d\'exiger des identifiants pré-émis avant qu\'un client puisse créer un compte :',
        items: [
          { label: 'Émettre', text: 'Générer une nouvelle paire kid + clé HMAC depuis ACME → EAB Credentials' },
          { label: 'Distribuer', text: 'Transmettre le kid + HMAC au client (cert-manager, certbot, acme.sh)' },
          { label: 'Lier', text: 'Le client signe un JWS avec la clé MAC sur newAccount pour lier son compte ACME' },
          { label: 'Rotation / Révocation', text: 'Révoquer un kid à tout moment — les comptes existants continuent, les nouvelles liaisons sont refusées' },
          { label: 'Audit', text: 'Émission, rotation et révocation sont auditées sous l\'opérateur qui les a effectuées' },
        ]
      },
      {
        title: 'Résolveurs DNS personnalisés (DNS-01)',
        items: [
          { label: 'Override par compte', text: 'Surcharge des résolveurs système lors de la validation des TXT _acme-challenge' },
          { label: 'Split-horizon', text: 'Utile lorsque votre serveur autoritaire est interne mais la vue publique est cachée ailleurs' },
          { label: 'Enregistrements obsolètes', text: 'Évite la mise en cache des résolveurs publics pendant les renouvellements rapides' },
        ]
      },
      {
        title: 'ACME sur IP internes / privées',
        content: 'La validation HTTP-01 et TLS-ALPN-01 fonctionne nativement pour les cibles RFC1918, loopback, .lan / .local / .corp — le mode de déploiement principal de UCM.',
        items: [
          { label: 'Bascule', text: 'Settings → SystemConfig → acme.allow_private_ips (par défaut : true)' },
          { label: 'Toujours bloqué', text: 'Les IP de métadonnées cloud (169.254.169.254, fd00:ec2::254, etc.) sont bloquées inconditionnellement' },
        ]
      },

      {
        title: 'Certificats d\'adresse IP (RFC 8738)',
        content: 'Le serveur ACME local peut émettre des certificats pour des adresses IPv4 et IPv6, pas seulement des noms DNS. Utilisez le type d\'identifiant « ip » dans la commande.',
        items: [
          { label: 'Identifiant', text: 'Commande avec { "type": "ip", "value": "192.0.2.10" } (IPv4) ou un littéral IPv6 comme 2001:db8::1' },
          { label: 'Défis', text: 'Seuls HTTP-01 et TLS-ALPN-01 sont proposés — DNS-01 est interdit pour les identifiants IP selon RFC 8738' },
          { label: 'SNI TLS-ALPN-01', text: 'La validation utilise la forme reverse-DNS (in-addr.arpa / ip6.arpa) comme nom d\'hôte SNI' },
          { label: 'SAN émis', text: 'Le certificat porte un SAN iPAddress ; les commandes mixtes DNS + IP sont prises en charge' },
          { label: 'IP internes', text: 'Les adresses RFC1918 et loopback se valident nativement — le mode de déploiement principal de UCM' },
        ]
      },
    ],
    tips: [
      'URL du répertoire ACME : https://votre-serveur:port/acme/directory',
      'Utilisez une URL de répertoire personnalisée pour se connecter à ZeroSSL, Buypass, HARICA ou tout CA RFC 8555',
      'Les identifiants EAB (Key ID + clé HMAC) sont fournis par votre CA lors de l\'inscription',
      'Les clés ECDSA P-256 offrent une sécurité équivalente à RSA-2048 avec une taille bien plus petite',
      'Utilisez les domaines locaux pour attribuer différentes CA à différents domaines internes',
      'Toute CA avec une clé privée peut être sélectionnée comme CA émettrice',
      'Les domaines génériques (*.exemple.com) nécessitent la validation DNS-01',
      'Quand UCM est le serveur ACME, émettez vos propres identifiants EAB dans ACME → EAB Credentials',
      'Pour Kubernetes/cert-manager : voir les manifests de référence sous examples/kubernetes/cert-manager/',
    ],
    warnings: [
      'La validation de domaine est requise — votre serveur doit être accessible ou le DNS configuré',
      'Changer le type de clé du compte nécessite de ré-enregistrer votre compte ACME',
    ],
  },
  helpGuides: {
    title: 'ACME',
    content: `
## Vue d'ensemble

UCM prend en charge ACME (Automated Certificate Management Environment) en deux modes :

- **Client ACME** — Obtenir des certificats depuis tout CA conforme RFC 8555 (Let's Encrypt, ZeroSSL, Buypass, HARICA ou personnalisé)
- **Serveur ACME local** — Serveur ACME intégré pour l'automatisation PKI interne avec support multi-CA

## Client ACME

### Paramètres du client
Gérez la configuration de votre client ACME :
- **Environnement** — Staging (test) ou Production (certificats réels)
- **E-mail de contact** — Requis pour l'enregistrement du compte
- **Renouvellement automatique** — Renouveler automatiquement les certificats avant l'expiration
- **Type de clé de certificat** — RSA-2048, RSA-4096, ECDSA P-256 ou ECDSA P-384
- **Algorithme de clé de compte** — ES256, ES384 ou RS256 pour la signature du compte ACME

### Serveur ACME personnalisé
Utilisez tout CA conforme RFC 8555, pas seulement Let's Encrypt :

| Fournisseur CA | URL du répertoire |
|---|---|
| **Let's Encrypt** | *(par défaut, laisser vide)* |
| **ZeroSSL** | \`https://acme.zerossl.com/v2/DV90\` |
| **Buypass** | \`https://api.buypass.com/acme/directory\` |
| **HARICA** | \`https://acme-v02.harica.gr/acme/<token>/directory\` |
| **Google Trust** | \`https://dv.acme-v02.api.pki.goog/directory\` |

Définissez l'URL du répertoire de votre CA dans **Paramètres** → **Serveur ACME personnalisé**.

### Liaison de compte externe (EAB)
Certains CA nécessitent des identifiants EAB pour lier votre compte ACME à un compte existant chez le CA :

1. Inscrivez-vous sur le portail de votre CA pour obtenir le **Key ID EAB** et la **clé HMAC**
2. Entrez les deux valeurs dans **Paramètres** → **Serveur ACME personnalisé**
3. La clé HMAC est encodée en base64url (fournie par le CA)

> 💡 EAB est requis par ZeroSSL, HARICA, Google Trust Services et la plupart des CA d'entreprise.

### ECDSA vs RSA

| Type de clé | Taille | Sécurité | Performance |
|---|---|---|---|
| **RSA-2048** | 2048 bits | Standard | Référence |
| **RSA-4096** | 4096 bits | Supérieure | Plus lent |
| **ECDSA P-256** | 256 bits | ≈ RSA-3072 | Beaucoup plus rapide |
| **ECDSA P-384** | 384 bits | ≈ RSA-7680 | Plus rapide |

Les clés ECDSA sont recommandées pour les déploiements modernes — plus petites, plus rapides et tout aussi sécurisées.

### Fournisseurs DNS
Configurez les fournisseurs de défi DNS-01 pour la validation de domaine. Les fournisseurs pris en charge incluent :
- Cloudflare
- AWS Route 53
- Google Cloud DNS
- DigitalOcean
- OVH
- Et plus encore

Chaque fournisseur nécessite des identifiants API spécifiques au service DNS.

### Domaines
Associez vos domaines aux fournisseurs DNS. Lors de la demande d'un certificat pour un domaine, UCM utilise le fournisseur associé pour créer les enregistrements de défi DNS-01.

1. Cliquez sur **Ajouter un domaine**
2. Entrez le nom de domaine (par ex. \`exemple.com\` ou \`*.exemple.com\`)
3. Sélectionnez le fournisseur DNS
4. Cliquez sur **Enregistrer**

> 💡 Les certificats génériques (\`*.exemple.com\`) nécessitent la validation DNS-01.


## Mode Proxy ACME

Le proxy ACME permet aux clients internes de demander des certificats à un CA public (Let's Encrypt, ZeroSSL, etc.) via UCM, sans accès direct à Internet. UCM agit comme intermédiaire, gérant les défis DNS-01 et transférant les requêtes au CA en amont.

### Quand utiliser le mode proxy
- Serveurs internes sans accès direct à Internet
- Gestion centralisée des défis DNS-01 via les fournisseurs DNS configurés dans UCM
- Audit et suivi de toutes les émissions de certificats publics

### Configuration
1. Allez dans **ACME** → onglet **Let's Encrypt**
2. Faites défiler jusqu'à la section **Proxy ACME**
3. Activez le bouton **Proxy ACME**
4. Sélectionnez un **CA en amont** : Let's Encrypt Production, Let's Encrypt Staging ou Personnalisé
5. Pour les CAs personnalisés, entrez l'URL du répertoire ACME manuellement
6. Si le CA en amont nécessite un EAB, développez **Identifiants EAB** et entrez le Key ID et la clé HMAC
7. Cliquez sur **Test de connexion** pour vérifier la connectivité avec le CA en amont
8. UCM enregistre automatiquement un compte à la première requête proxy

### Gestion des comptes
- Le **badge de statut du compte** indique si UCM est enregistré auprès du CA en amont
- Changer de CA en amont efface automatiquement les identifiants obsolètes et force une réinscription
- Utilisez le bouton **Réinitialiser le compte** pour effacer manuellement les identifiants si nécessaire
- **Test de connexion** vérifie si le répertoire en amont est accessible et si un EAB est requis

### Utilisation du proxy
Dirigez vos clients ACME internes vers le répertoire proxy :
\`\`\`
https://votre-serveur-ucm:8443/acme/proxy/directory
\`\`\`

> 💡 Les identifiants EAB proxy sont distincts de l'EAB client — ils authentifient UCM auprès du CA en amont, pas vos clients auprès de UCM.

> ⚠ Le mode proxy nécessite au moins un fournisseur DNS configuré dans UCM pour la résolution des défis.

## Serveur ACME local

### Configuration
- **Activer/Désactiver** — Basculer le serveur ACME intégré
- **CA par défaut** — Sélectionner quelle CA signe les certificats par défaut
- **Conditions d'utilisation** — URL optionnelle des conditions pour les clients

### URL du répertoire ACME
\`\`\`
https://votre-serveur:8443/acme/directory
\`\`\`

Les clients comme certbot, acme.sh ou Caddy utilisent cette URL pour découvrir les points de terminaison ACME.

### Domaines locaux (multi-CA)
Associez des domaines internes à des CA spécifiques. Cela permet à différents domaines d'être signés par différentes CA.

1. Cliquez sur **Ajouter un domaine**
2. Entrez le domaine (par ex. \`interne.corp\` ou \`*.dev.local\`)
3. Sélectionnez la **CA émettrice**
4. Activez/désactivez l'**approbation automatique**
5. Cliquez sur **Enregistrer**

### Ordre de résolution des CA
Lorsqu'un client ACME demande un certificat, UCM détermine la CA de signature dans cet ordre :
1. **Mappage de domaine local** — Correspondance exacte, puis correspondance de domaine parent
2. **Mappage de domaine DNS** — La CA configurée pour le fournisseur DNS
3. **Valeur par défaut globale** — La CA définie dans la configuration du serveur ACME
4. **Première disponible** — Toute CA avec une clé privée

### Comptes
Voir les comptes clients ACME enregistrés :
- ID du compte et e-mail de contact
- Date d'inscription
- Nombre de commandes

### Historique
Parcourir toutes les commandes d'émission de certificats :
- Statut de la commande (en attente, valide, invalide, prêt)
- Noms de domaine demandés
- CA de signature utilisée
- Horodatage d'émission

## Utiliser certbot

\`\`\`
# Enregistrer un compte (Let's Encrypt — par défaut)
certbot register --agree-tos --email admin@exemple.com

# Enregistrer avec un CA ACME personnalisé + EAB
certbot register \\
  --server 'https://acme.zerossl.com/v2/DV90' \\
  --eab-kid 'votre-key-id' \\
  --eab-hmac-key 'votre-cle-hmac' \\
  --agree-tos --email admin@exemple.com

# Demander un certificat avec clé ECDSA
certbot certonly --server https://votre-serveur:8443/acme/directory \\
  --standalone -d monserveur.interne.corp \\
  --key-type ecdsa --elliptic-curve secp256r1

# Renouveler
certbot renew --server https://votre-serveur:8443/acme/directory
\`\`\`

## Utiliser acme.sh

\`\`\`
# Par défaut (Let's Encrypt)
acme.sh --issue -d exemple.com --standalone

# CA ACME personnalisé avec EAB et ECDSA
acme.sh --issue \\
  --server 'https://acme-v02.harica.gr/acme/TOKEN/directory' \\
  --eab-kid 'votre-key-id' \\
  --eab-hmac-key 'votre-cle-hmac' \\
  --keylength ec-256 \\
  -d exemple.com --standalone
\`\`\`

> ⚠ Pour ACME interne, les clients doivent faire confiance à la CA UCM. Installez le certificat de la CA racine dans le magasin de confiance du client.
## Certificats d'adresse IP (RFC 8738)

Le serveur ACME local peut émettre des certificats pour des **adresses IP** (IPv4 et IPv6), pas seulement des noms DNS. Utile pour les services internes, les équipements et les hôtes adressés directement par IP.

### Commander un certificat IP
Utilisez le type d'identifiant \`ip\` dans la commande ACME :
\`\`\`json
{
  "identifiers": [
    { "type": "ip", "value": "192.0.2.10" },
    { "type": "ip", "value": "2001:db8::1" }
  ]
}
\`\`\`
Les commandes mixtes DNS + IP sont également prises en charge.

### Validation
- **HTTP-01** et **TLS-ALPN-01** sont les seuls défis proposés pour les identifiants IP. **DNS-01 est interdit** pour les IP par la RFC 8738.
- **HTTP-01** se connecte directement à l'IP (les littéraux IPv6 sont entre crochets, ex. \`http://[2001:db8::1]/...\`).
- **TLS-ALPN-01** utilise la forme reverse-DNS de l'IP (\`in-addr.arpa\` / \`ip6.arpa\`) comme nom d'hôte SNI.

### Certificat émis
Le certificat signé contient une entrée SubjectAltName **iPAddress** pour chaque IP validée.

> 💡 Les adresses internes (RFC1918, loopback) se valident nativement — le mode de déploiement principal de UCM. Les IP de métadonnées cloud restent bloquées.

`
  }
}
