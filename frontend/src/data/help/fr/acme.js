export default {
  helpContent: {
    title: 'ACME',
    subtitle: 'Gestion automatisée des certificats',
    overview: 'UCM prend en charge deux modes ACME : client ACME pour les certificats publics depuis tout CA conforme RFC 8555 (Let\'s Encrypt, ZeroSSL, Buypass, HARICA, etc.), et serveur ACME local pour l\'automatisation PKI interne avec mappage multi-CA de domaines.',
    sections: [
      {
        title: "Renewal Information (ARI, RFC 9773)",
        content: "Le serveur ACME local publie une ressource renewalInfo : les clients y apprennent le moment idéal pour renouveler chaque certificat.",
        items: [
          { label: "Fenêtre suggérée", text: "Renvoie une fenêtre début/fin centrée avant l'expiration, pour étaler les renouvellements" },
          { label: "Révocation", text: "Un certificat révoqué renvoie une fenêtre dans le passé → les clients conformes renouvellent immédiatement" },
          { label: "Sans authentification", text: "renewalInfo est un simple GET — ni compte ni JWS requis (RFC 9773)" },
        ]
      },
      {
        title: 'Client ACME',
        items: [
          { label: 'Client', text: 'Demander des certificats depuis tout CA ACME — Let\'s Encrypt, ZeroSSL, Buypass, HARICA ou personnalisé' },
          { label: 'Onglet des orders (v2.219)', text: 'Les orders du client ont leur propre onglet « Let\'s Encrypt orders » dans la barre latérale, avec compteur visibles/total et filtre de statut, à l\'image de la vue Local orders' },
          { label: 'Comptes CA externes', text: 'Un ou plusieurs comptes par CA — plusieurs comptes peuvent partager la même URL de répertoire (ex. deux comptes Let\'s Encrypt pour une séparation administrative) ; une URL de répertoire vide vaut Let\'s Encrypt Production' },
          { label: 'Serveur personnalisé', text: 'Définir une URL de répertoire ACME personnalisée pour utiliser tout CA conforme RFC 8555' },
          { label: 'EAB', text: 'Prise en charge de la liaison de compte externe pour les CA nécessitant une pré-inscription (ZeroSSL, HARICA, etc.)' },
          { label: 'Types de clés', text: 'RSA-2048, RSA-4096, ECDSA P-256, ECDSA P-384 pour les clés de certificat' },
          { label: 'Clés de compte', text: 'Algorithmes ES256 (P-256), ES384 (P-384) ou RS256 pour les clés de compte ACME' },
          { label: 'Fournisseurs DNS', text: 'Configurer les fournisseurs de défi DNS-01 (Cloudflare, Route53, Tencent DNSPod, etc.)' },
          { label: 'Custom Command', text: 'Type de fournisseur DNS exécutant des commandes locales configurées par l\'admin pour créer/supprimer les TXT — détails de l\'enregistrement passés via les variables d\'environnement DOMAIN, RECORD_NAME, RECORD_VALUE, TTL, ACTION. Chemin binaire absolu requis, sans shell, timeout configurable' },
          { label: 'Domaines', text: 'Associer des domaines aux fournisseurs DNS pour la validation automatique' },
        ]
      },
      {
        title: 'Serveur ACME local',
        items: [
          { label: 'Configuration', text: 'Activer/désactiver le serveur ACME intégré, sélectionner la CA par défaut' },
          { label: 'Domaines locaux', text: 'Associer des domaines internes à des CA spécifiques pour l\'émission multi-CA' },
          { label: 'Comptes', text: 'Voir et gérer les comptes clients ACME enregistrés' },
          { label: 'E-mail du compte (v2.218)', text: 'L\'e-mail de contact d\'un compte local peut être modifié depuis son panneau de détails. Selon la RFC 8555, le contact appartient au client ACME : sa prochaine mise à jour de compte peut donc écraser la valeur' },
          { label: 'Historique', text: 'Suivre toutes les commandes d\'émission de certificats ACME' },
                  { label: 'Orders locaux (v2.217)', text: 'L\'onglet Local orders liste les orders du serveur intégré avec filtre de statut, suppression unitaire et purge ; les orders expirés non émis sont purgés automatiquement toutes les 6 h, et un digest de signature par défaut s\'applique aux orders sans profil. Depuis la v2.218, la purge supprime aussi les défis frères résiduels encore pending des autorisations déjà validées' },
                  { label: 'Profils et templates (v2.221)', text: 'Les profils de certificat (draft-ietf-acme-profiles) sont publiés dans le directory et choisis par le client à chaque order. Chaque profil fixe validité et digest et peut lier un template de certificat, dont les KU/EKU gouvernent alors le certificat émis' },
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
          { label: 'Purge des certificats remplacés', text: 'Bascule opt-in : quand un ordre proxy se finalise, les certificats précédemment importés par des ordres proxy pour exactement le même ensemble de domaines sont supprimés. Les certificats révoqués sont toujours conservés ; les certificats hors proxy ne sont jamais touchés. Désactivé par défaut' },
                  { label: 'Pre-checks clients (v2.217)', text: 'Le proxy publie aussi les valeurs TXT dns-01 calculées avec la clé de compte de chaque client : les pre-checks de propagation de lego/Traefik/Caddy passent sans être désactivés ; un new-order retenté renvoie l\'order encore pending du compte' },
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
          { label: 'Restrictions de domaines', text: 'Limiter un identifiant aux domaines qu\'il peut demander : * (tous), *.example.com (tous les sous-domaines), ou une liste explicite — une liste vide bloque entièrement l\'émission. Appliqué sur new-order/new-authz, serveur et proxy ; pertinent seulement quand l\'EAB est exigé' },
        ]
      },
      {
        title: 'Résolveurs DNS personnalisés (DNS-01)',
        items: [
          { label: 'Override par compte', text: 'Surcharge des résolveurs système lors de la validation des TXT _acme-challenge' },
          { label: 'Split-horizon', text: 'Utile lorsque votre serveur autoritaire est interne mais la vue publique est cachée ailleurs' },
          { label: 'Enregistrements obsolètes', text: 'Évite la mise en cache des résolveurs publics pendant les renouvellements rapides' },
          { label: 'Entrées host:port', text: 'Les résolveurs n\'écoutant pas sur le port 53 sont acceptés (par ex. un BIND en loopback seul ou dnsmasq sur un port alternatif) — séparés par des virgules, les IP simples fonctionnent toujours' },
        ]
      },
      {
        title: 'ACME sur IP internes / privées',
        content: 'La validation HTTP-01 et TLS-ALPN-01 fonctionne nativement pour les cibles RFC1918, loopback, .lan / .local / .corp — le mode de déploiement principal de UCM.',
        items: [
          { label: 'Bascule', text: 'Settings → SystemConfig → acme.allow_private_ips (par défaut : true)' },
          { label: 'Bascule', text: 'Onglet Let\'s Encrypt → Autoriser un CA ACME sur loopback — pour un CA colocalisé sur 127.0.0.1 (par défaut : désactivé)' },
          { label: 'Toujours bloqué', text: 'Les IP de métadonnées cloud (169.254.169.254, fd00:ec2::254, etc.) sont bloquées inconditionnellement' },
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
      {
        title: 'Validation DNS persistante (dns-persist-01)',
        content: 'Le serveur ACME local peut valider des domaines via un enregistrement TXT persistant lié au compte ACME (draft-ietf-acme-dns-persist) — renouvellement sans écriture DNS. Opt-in, désactivé par défaut.',
        items: [
          { label: 'Enregistrement', text: 'Créez _validation-persist.<domaine> TXT "<domaine-émetteur>; accounturi=<URL du compte>" — l\'objet challenge annonce les deux valeurs attendues' },
          { label: 'Activation', text: 'ACME → Configuration → Validation DNS persistante (dns-persist-01)' },
          { label: 'Wildcard / sous-domaines', text: 'Ajoutez policy=wildcard pour autoriser aussi les certificats wildcard et les sous-domaines du nom validé' },
          { label: 'persistUntil', text: 'persistUntil=<timestamp unix> optionnel : bloque les nouvelles validations après cette date' },
          { label: 'Sécurité', text: 'L\'enregistrement donne au compte la capacité d\'émission tant qu\'il existe — supprimez le TXT pour la révoquer' },
        ]
      }
    ],
    tips: [
      'URL du répertoire ACME : https://votre-serveur:port/acme/directory',
      'Utilisez une URL de répertoire personnalisée pour se connecter à ZeroSSL, Buypass, HARICA ou tout CA RFC 8555',
      'Les identifiants EAB (Key ID + clé HMAC) sont fournis par votre CA lors de l\'inscription',
      'Quand UCM est le serveur ACME, émettez vos propres identifiants EAB dans ACME → EAB Credentials',
      'Pour Kubernetes/cert-manager : voir les manifests de référence sous examples/kubernetes/cert-manager/',
      'Les clés ECDSA P-256 offrent une sécurité équivalente à RSA-2048 avec une taille bien plus petite',
      'Utilisez les domaines locaux pour attribuer différentes CA à différents domaines internes',
      'Toute CA avec une clé privée peut être sélectionnée comme CA émettrice',
      'Les domaines génériques (*.exemple.com) nécessitent la validation DNS-01',
      'Changer de CA en amont efface automatiquement les identifiants de compte obsolètes',
      'Utilisez l\'URL du proxy avec certbot : certbot certonly --server https://votre-serveur:port/acme/proxy/directory',
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

### Comptes CA externes
Gérez tous les comptes externes avec lesquels UCM s'enregistre :

- **Plusieurs comptes par CA autorisés** — plusieurs comptes peuvent partager la même URL de répertoire (ex. deux comptes Let's Encrypt avec des e-mails de contact différents pour la séparation administrative, utile avec dns-persist-01). La ligne du compte, pas l'URL, sert d'identité.
- **URL de répertoire vide** — vaut par défaut Let's Encrypt Production.
- **Compte par défaut** — utilisé quand une demande ne sélectionne aucun compte ; les recherches par URL renvoient le compte par défaut.
- **Import** — importez la clé privée d'un compte existant à la création : les enveloppes PKCS#8, SEC1/X9.62 (\`BEGIN EC PRIVATE KEY\`) et PKCS#1 (\`BEGIN RSA PRIVATE KEY\`) sont acceptées ; l'algorithme est déduit automatiquement.
- **Point de terminaison proxy dédié** — chaque compte peut exposer \`/acme/proxy/<slug>/directory\` avec son propre slug.

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

### Source de la clé
Lors d'une demande de certificat, choisissez d'où vient la clé privée :

- **Générer une nouvelle clé** *(défaut)* — UCM crée une paire de clés à chaque ordre
- **Réutiliser la clé au renouvellement** — conserve la même clé privée d'un renouvellement à l'autre (nécessaire pour DANE/TLSA et le key pinning) ; la première émission génère la clé, les renouvellements la rechargent
- **Fournir un CSR externe** — collez un CSR PEM généré ailleurs ; UCM le soumet au finalize et la clé privée n'entre jamais dans UCM. Les domaines du CSR doivent correspondre exactement aux identifiants de l'ordre

### Preflight (test à blanc)
**Lancer le preflight** sur le formulaire de demande valide toute la requête contre le répertoire **staging** de Let's Encrypt, sans consommer les limites de production :

- Vérifie la syntaxe des domaines, l'email de contact, le compte ACME / EAB et la connectivité CA
- Le mode **Complet** crée un ordre staging et prévisualise les enregistrements TXT \`_acme-challenge\` exacts à publier
- **Validation seule** vérifie configuration et connectivité sans créer d'ordre
- Peut vérifier la propagation DNS des TXT une fois les enregistrements ajoutés

> 💡 Les CA personnalisées n'ont pas d'endpoint staging — le preflight ne valide alors que la configuration et la connectivité.

### Fournisseurs DNS
Configurez les fournisseurs de défi DNS-01 pour la validation de domaine. Les fournisseurs pris en charge incluent :
- Cloudflare
- AWS Route 53
- Azure DNS
- Google Cloud DNS
- DigitalOcean
- OVH
- Tencent Cloud DNSPod
- Et plus encore

Chaque fournisseur nécessite des identifiants API spécifiques au service DNS.

#### Fournisseur Custom Command
Pour les services DNS sans pilote natif, le fournisseur **Custom Command** exécute des commandes locales configurées par l'admin pour créer/supprimer les enregistrements TXT. Les détails de l'enregistrement sont passés en variables d'environnement :

- \`DOMAIN\` — domaine de base en cours de validation
- \`RECORD_NAME\` — nom complet de l'enregistrement TXT (\`_acme-challenge.example.com\`)
- \`RECORD_VALUE\` — contenu du TXT (digest du défi)
- \`TTL\` — TTL de l'enregistrement en secondes
- \`ACTION\` — \`create\` ou \`delete\`

La commande exige un **chemin binaire absolu**, s'exécute sans shell (ni pipes ni expansion) et est tuée après un timeout configurable (5–300 s, 60 par défaut). Utilisez un petit script wrapper pour relier n'importe quel outillage DNS externe.

### Résolveurs DNS personnalisés
Surchargez optionnellement les résolveurs utilisés pour vérifier les enregistrements TXT \`_acme-challenge\` (utile pour le DNS split-horizon ou pour éviter la mise en cache des résolveurs publics). Les entrées sont séparées par des virgules et acceptent des IP simples ou \`host:port\` — par ex. un BIND en loopback seul ou une instance dnsmasq sur un port alternatif.

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
4. Sélectionnez un **Compte CA en amont** dans **Comptes CA externes** (Let's Encrypt, Actalis, ZeroSSL, URL personnalisée, EAB)
5. Cliquez sur **Tester la connexion** pour vérifier la connectivité avec le CA en amont
6. Enregistrez le compte amont si nécessaire (email + **Enregistrer le compte**)
7. UCM enregistre automatiquement un compte à la première requête proxy si ce n'est pas déjà fait

### Chemins proxy dédiés (multi-CA)
Chaque compte CA externe peut exposer son propre endpoint proxy ACME :

1. Ouvrez **Comptes CA externes** (même onglet Let's Encrypt)
2. Modifiez ou créez un compte CA
3. Activez **Exposer via le proxy ACME**
4. Définissez un **Chemin proxy (slug)** unique — ex. \`actalis-production\`, \`letsencrypt-staging\`
5. Enregistrez — l'URL apparaît dans la section proxy et sur la fiche du compte

Les clients utilisent :
\`\`\`
https://votre-serveur-ucm:8443/acme/proxy/<slug>/directory
\`\`\`

Le chemin par défaut legacy reste disponible pour le compte sélectionné dans les réglages proxy :
\`\`\`
https://votre-serveur-ucm:8443/acme/proxy/directory
\`\`\`

Slugs réservés (interdits) : \`directory\`, \`new-order\`, \`challenge\`, \`acct\`, etc.

### Gestion des comptes
- Le **badge de statut du compte** indique si UCM est enregistré auprès du CA en amont
- Changer de CA en amont efface automatiquement les identifiants obsolètes et force une réinscription
- Utilisez le bouton **Réinitialiser le compte** pour effacer manuellement les identifiants si nécessaire
- **Test de connexion** vérifie si le répertoire en amont est accessible et si un EAB est requis

### Purge des certificats remplacés
Chaque renouvellement via le proxy importe un nouveau certificat dans l'inventaire, si bien que les certificats remplacés s'accumulent avec le temps. La bascule **Purger les certificats remplacés** (réglages proxy) nettoie automatiquement : quand un ordre proxy se finalise, les certificats précédemment importés par des ordres proxy pour **exactement le même ensemble de domaines** sont supprimés.

- **Les certificats révoqués sont toujours conservés** — la trace de révocation reste intacte
- Les certificats non émis via le proxy ne sont jamais touchés
- Désactivé par défaut

### Utilisation du proxy
Dirigez vos clients ACME internes vers le répertoire proxy du CA cible.

**URL par slug** (recommandé lorsque plusieurs CAs sont exposés) :
\`\`\`
https://votre-serveur-ucm:8443/acme/proxy/<slug>/directory
\`\`\`

**URL par défaut** (compte sélectionné dans les réglages proxy) :
\`\`\`
https://votre-serveur-ucm:8443/acme/proxy/directory
\`\`\`

Exemple avec certbot (remplacez \`<slug>\` par votre slug CA) :
\`\`\`
certbot certonly \\
  --server https://votre-serveur-ucm:8443/acme/proxy/<slug>/directory \\
  --preferred-challenges dns-01 \\
  --authenticator manual \\
  --manual-auth-hook /bin/true \\
  --manual-cleanup-hook /bin/true \\
  --non-interactive --agree-tos -m you@example.com \\
  -d subdomain.example.com
\`\`\`

> 💡 Les identifiants EAB proxy sont distincts de l'EAB client — ils authentifient UCM auprès du CA en amont, pas vos clients auprès de UCM.

> ⚠ Prérequis : le domaine (ou un domaine parent couvrant les sous-domaines) doit être configuré dans ACME Domains avec un fournisseur DNS. Le proxy ne gère que dns-01.

> ⚠ Évitez les demandes simultanées pour le même FQDN (Certbot + interface UCM) : le second enregistrement TXT peut écraser le premier.

> ℹ️ En environnement lab / certificat auto-signé, ajoutez \`--no-verify-ssl\` à Certbot.

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

### Identifiants EAB (côté serveur)
Quand UCM est le serveur ACME (ou le proxy), vous pouvez exiger le **External Account Binding** : les clients doivent présenter un kid + une clé HMAC pré-émis pour enregistrer un compte. Émettez et révoquez les identifiants depuis **ACME → EAB Credentials**.

Chaque identifiant peut être restreint aux **domaines pour lesquels il peut demander des certificats** :
- \`*\` — tout domaine (valeur par défaut pour les identifiants nouveaux et préexistants)
- \`*.example.com\` — le domaine et tous ses sous-domaines
- Une liste explicite de domaines
- Une **liste vide bloque entièrement l'émission** pour cet identifiant

Les restrictions sont appliquées sur new-order et new-authz, à la fois sur le serveur ACME intégré et sur le proxy. Elles n'ont de sens que quand l'**EAB est exigé** — sinon les clients peuvent simplement s'enregistrer sans identifiant.

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

## Validation DNS persistante (dns-persist-01)

Le serveur ACME local prend en charge **dns-persist-01** (draft-ietf-acme-dns-persist) : validation via un enregistrement TXT **persistant** lié au compte ACME — les renouvellements ne nécessitent aucune écriture DNS.

### Mise en place
1. Activez-le dans **ACME → Configuration → Validation DNS persistante** (désactivé par défaut).
2. Créez l'enregistrement une seule fois :
\`\`\`
_validation-persist.app.example.com. IN TXT "ca.example.com; accounturi=https://ca.example.com/acme/acct/<id>"
\`\`\`
L'objet challenge annonce les valeurs attendues \`accounturi\` et \`issuer-domain-names\`.

### Options
- \`policy=wildcard\` — autorise aussi les certificats wildcard et les sous-domaines du nom validé (un enregistrement sur un domaine parent couvre ses enfants)
- \`persistUntil=<timestamp-unix>\` — bloque les nouvelles validations après cette date

> ⚠️ L'enregistrement donne la capacité d'émission à la clé du compte ACME tant qu'il existe — supprimez le TXT pour la révoquer.

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

## Renewal Information (ARI, RFC 9773)

Le serveur ACME local annonce \`renewalInfo\` dans son directory et sert une **fenêtre de renouvellement suggérée** par certificat.

- Fenêtre centrée avant l'expiration → renouvellements étalés dans le temps
- Certificat révoqué → fenêtre dans le passé (renouveler tout de suite)
- GET non authentifié sur \`/acme/renewalInfo/<certID>\`

`
  }
}
