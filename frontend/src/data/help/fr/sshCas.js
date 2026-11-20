export default {
  helpContent: {
    title: 'Autorités de certification SSH',
    subtitle: 'Gérer les AC SSH pour l’authentification des utilisateurs et des hôtes',
    overview: 'Créez et gérez des autorités de certification SSH conformes aux standards OpenSSH. Les AC SSH éliminent la nécessité de distribuer les clés publiques individuellement, les serveurs et les utilisateurs font confiance à l’AC, et l’AC signe des certificats qui accordent l’accès.',
    sections: [
      {
        title: 'Types d’AC',
        items: [
          { label: 'AC utilisateur', text: 'Signe des certificats utilisateur pour la connexion SSH. Les serveurs font confiance à cette AC et acceptent tout certificat signé par elle.' },
          { label: 'AC hôte', text: 'Signe des certificats d’hôte pour prouver l’identité du serveur. Les clients font confiance à cette AC pour vérifier qu’ils se connectent au bon serveur.' },
        ]
      },
      {
        title: 'Algorithmes de clé',
        items: [
          { label: 'Ed25519', text: 'Moderne, rapide, petites clés (256 bits). Recommandé pour les nouveaux déploiements.' },
          { label: 'ECDSA P-256 / P-384 / P-521', text: 'Clés à courbe elliptique, largement prises en charge. Bon équilibre entre sécurité et compatibilité.' },
          { label: 'RSA 4096', text: 'Algorithme traditionnel, toujours en 4096 bits. Compatibilité la plus large avec les anciens systèmes.' },
        ]
      },
      {
        title: 'AC SSH adossées HSM',
        items: [
          { label: 'Stockage de la clé', text: 'À la création, choisissez Local ou HSM, puis le fournisseur et une clé de signature inutilisée. L’AC reprend son type de clé de la clé elle-même et la clé privée ne quitte jamais le HSM' },
          { label: 'Algorithmes', text: 'Clés RSA et ECDSA P-256, P-384 ou P-521. Les clés Ed25519 ne sont pas proposées : la signature sur HSM d’UCM ne couvre pas EdDSA, une AC SSH Ed25519 est donc une clé logicielle. Les clés Brainpool et ML-DSA ne le sont pas non plus : UCM signe avec elles sur HSM pour les AC X.509, mais les certificats OpenSSH n’ont pas de type de clé pour elles' },
          { label: 'Une clé, une autorité', text: 'Une clé sert une seule autorité, X.509 ou SSH. Une clé déjà tenue n’est pas proposée, et une demande qui la nomme est refusée (409) avec le nom de l’AC qui la tient. Ni la clé ni son fournisseur ne peuvent être supprimés tant que l’AC existe' },
          { label: 'Droits', text: 'write:ssh_cas et read:hsm. Sans read:hsm, le choix HSM est désactivé, et un refus (403) nomme le droit manquant' },
          { label: 'FIPS et HA', text: 'En mode FIPS, une clé que le mode FIPS refuse n’est pas proposée. En mode HA, une clé sur SoftHSM ou sur un lecteur de carte à puce local est refusée (409), car elle n’existe que sur un nœud' },
          { label: 'Jeton injoignable', text: 'Si le fournisseur est injoignable à la création de l’AC (503), rien n’est créé : vérifiez le fournisseur dans la gestion HSM puis réessayez' },
        ]
      },
      {
        title: 'Configuration du serveur',
        items: [
          { label: 'Script de configuration Linux/macOS', text: 'Téléchargez un script shell POSIX (.sh) qui configure automatiquement sshd pour faire confiance à cette AC. Installation rapide : curl -sSL <url> | sudo bash' },
          { label: 'Script de configuration Windows', text: 'Téléchargez un script PowerShell (.ps1) qui configure Windows OpenSSH Server (écrit la clé publique de l’AC dans %ProgramData%\\ssh, verrouille les ACL, ajoute TrustedUserCAKeys / HostCertificate dans sshd_config, valide avec sshd -T, redémarre sshd). Installation rapide : iwr <url> | iex' },
          { label: 'Bloc de diagnostic', text: 'En cas d’échec d’Add-WindowsCapability (WSUS / machine jointe au domaine), le script affiche un bloc étiqueté expliquant l’état de la politique et trois pistes de remédiation, il ne modifie jamais la politique WSUS / WU lui-même' },
          { label: 'Dry-run', text: 'Les deux scripts prennent en charge un drapeau -DryRun / --dry-run pour prévisualiser les modifications sans les appliquer' },
          { label: 'Configuration manuelle', text: 'Copiez la clé publique de l’AC et ajoutez TrustedUserCAKeys (AC utilisateur) ou HostCertificate (AC hôte) dans sshd_config' },
        ]
      },
      {
        title: 'Révocation de clés',
        items: [
          { label: 'KRL (Key Revocation List)', text: 'Format binaire compact pour révoquer des certificats individuels. Configuré via RevokedKeys dans sshd_config.' },
          { label: 'Télécharger la KRL', text: 'Téléchargez le fichier KRL actuel depuis le panneau de détail de l’AC.' },
        ]
      },
      {
        title: 'Formats de TTL',
        items: [
          { label: 'Durées suffixées', text: 'Les champs TTL par défaut et TTL max acceptent 24h, 7d, 365d, suffixes s, m, h, d, w, y' },
          { label: 'Nombres seuls', text: 'Un nombre seul est interprété en secondes (par ex. 3600 = 1 heure)' },
          { label: 'Validation', text: 'Les valeurs mal formées sont rejetées avec une erreur indiquant les formats acceptés' },
        ]
      },
      {
        title: 'Principals autorisés',
        items: [
          { label: 'Principals autorisés', text: 'Motifs séparés par des virgules (par ex. deploy, team-*). Chaque principal d’une demande doit correspondre à l’un d’eux.' },
          { label: 'Autoriser tout principal', text: 'Une AC dont la liste est vide signe pour n’importe quel nom, root compris, uniquement si cette option est cochée. Sinon elle ne signe rien.' },
          { label: 'Mise à niveau', text: 'Les AC créées avant 2.245 sans liste continuent de signer pour tout principal : la mise à niveau coche l’option pour elles.' },
        ]
      },
      {
        title: 'Key ID',
        items: [
          { label: 'Défini par l’AC', text: 'sshd journalise le key ID comme identité du titulaire. Par défaut, l’AC nomme chaque certificat principals@nom de l’AC, et une demande qui définit un autre key ID est refusée.' },
          { label: 'Laisser les demandeurs définir l’identifiant de clé', text: 'Cochez cette option pour laisser les demandeurs choisir le leur, par ex. un numéro de ticket ou d’employé.' },
          { label: 'Mise à niveau', text: 'À partir de 2.249, les AC existantes démarrent aussi avec l’option décochée.' },
        ]
      },
    ],
    tips: [
      'Utilisez des AC distinctes pour les certificats utilisateur et hôte : ne les mélangez jamais.',
      'Ed25519 est recommandé pour les nouveaux déploiements grâce à sa rapidité et sa sécurité.',
      'Téléchargez le script de configuration pour une mise en place facile du serveur : il gère automatiquement la sauvegarde et la validation.',
    ],
    warnings: [
      'Une AC ne peut pas être supprimée tant que des certificats qu’elle a signés subsistent : supprimez-les d’abord, et mettez à jour la confiance des serveurs.',
      'Si la clé privée de l’AC est compromise, tous les certificats signés par celle-ci doivent être considérés comme non fiables.',
    ],
  },
  helpGuides: {
    title: 'Autorités de certification SSH',
    content: `
## Vue d’ensemble

Les autorités de certification SSH (AC) constituent le fondement de l’authentification par certificats SSH. Au lieu de distribuer des clés publiques individuelles à chaque serveur, vous créez une AC et configurez les serveurs pour lui faire confiance. Tout certificat signé par l’AC est alors automatiquement accepté.

UCM prend en charge le format de certificat OpenSSH (RFC 4253 + extensions OpenSSH), nativement reconnu par OpenSSH 5.4+ : aucun logiciel supplémentaire n’est nécessaire sur les serveurs ou les clients.

## Types d’AC

### AC utilisateur
Une AC utilisateur signe des certificats qui authentifient les **utilisateurs auprès des serveurs**. Lorsqu’un serveur fait confiance à une AC utilisateur, tout utilisateur présentant un certificat valide signé par cette AC est autorisé à se connecter (sous réserve de correspondance des principals).

**Configuration du serveur :**
\`\`\`
# /etc/ssh/sshd_config
TrustedUserCAKeys /etc/ssh/user_ca.pub
\`\`\`

### AC hôte
Une AC hôte signe des certificats qui authentifient les **serveurs auprès des clients**. Lorsqu’un client fait confiance à une AC hôte, il peut vérifier que le serveur auquel il se connecte est légitime : éliminant les avertissements TOFU (Trust On First Use).

**Configuration du client :**
\`\`\`
# ~/.ssh/known_hosts
@cert-authority *.example.com ssh-ed25519 AAAA...
\`\`\`

## Créer une AC

1. Cliquez sur **Créer une AC SSH**
2. Saisissez un nom descriptif (ex. : « AC utilisateur de production »)
3. Sélectionnez le type d’AC : **Utilisateur** ou **Hôte**
4. Choisissez l’algorithme de clé :
   - **Ed25519** : Recommandé. Rapide, petites clés, sécurité moderne.
   - **ECDSA P-256/P-384/P-521** : Bonne compatibilité et sécurité.
   - **RSA 4096** : Compatibilité la plus large, clés plus volumineuses.
5. Définissez optionnellement la validité maximale et les extensions par défaut
6. Listez les principals autorisés, ou cochez **Autoriser tout principal**
7. Cliquez sur **Créer**

### Sur une clé HSM

Une AC SSH peut garder sa clé privée sur un fournisseur HSM.

1. Dans **Créer une AC SSH**, réglez **Stockage de la clé** sur **HSM**
2. Choisissez le **Fournisseur HSM**, puis la **Clé HSM existante** : seules les clés de signature RSA et ECDSA P-256/P-384/P-521 inutilisées sont listées
3. Cliquez sur **Créer**. L’AC reprend son type de clé de la clé elle-même, et la clé privée ne quitte jamais le jeton

Bon à savoir :
- Une AC SSH sur HSM prend une clé RSA ou ECDSA P-256, P-384 ou P-521. Les clés Ed25519 ne sont pas proposées : la signature sur HSM d’UCM ne couvre pas EdDSA, une AC SSH Ed25519 est donc une clé logicielle. Les clés Brainpool et ML-DSA ne le sont pas non plus : UCM signe avec elles sur HSM pour les AC X.509, mais les certificats OpenSSH n’ont pas de type de clé pour elles.
- Une clé HSM sert une seule autorité, X.509 ou SSH. Une clé qu’une AC tient déjà est refusée avec le nom de cette AC, et ni la clé ni son fournisseur ne peuvent être supprimés tant que l’AC existe.
- Il faut \`write:ssh_cas\` et \`read:hsm\`. Sans \`read:hsm\`, le choix **HSM** est désactivé.
- En mode FIPS, une clé que le mode FIPS refuse n’est pas proposée. En mode HA, une clé sur SoftHSM ou sur un lecteur de carte à puce local est refusée, car elle n’existe que sur un nœud.
- Si le fournisseur est injoignable à la création de l’AC, rien n’est créé.
### Principals autorisés

Le champ **Principals autorisés** restreint les noms pour lesquels une AC signe, sous forme de motifs séparés par des virgules (\`deploy\`, \`team-*\`, \`web??.example.com\`). Chaque principal d’une demande doit correspondre à l’un d’eux.

Une AC dont la liste est vide ne signe rien, sauf si **Autoriser tout principal** est coché : elle signe alors pour n’importe quel nom, \`root\` compris. Les AC créées avant 2.245 sans liste se comportaient ainsi implicitement ; la mise à niveau coche l’option pour elles, elles continuent donc de fonctionner.

### Key ID

sshd journalise le key ID d’un certificat comme identité du titulaire. L’AC le définit à \`principals@nom de l’AC\` et refuse une demande qui en définit un autre, sauf si **Laisser les demandeurs définir l’identifiant de clé** est coché. L’option est décochée pour toutes les AC, y compris les existantes depuis 2.249.

### Formats de TTL

Les champs **TTL par défaut** et **TTL max** acceptent des durées lisibles :

- Valeurs suffixées : \`24h\`, \`7d\`, \`365d\` (suffixes acceptés : \`s\`, \`m\`, \`h\`, \`d\`, \`w\`, \`y\`)
- Nombres seuls : interprétés en **secondes** (par ex. \`3600\` = 1 heure)

Les valeurs mal formées sont rejetées avec une erreur indiquant les formats acceptés.

> 💡 Utilisez des AC distinctes pour les certificats utilisateur et hôte. N’utilisez jamais une même AC pour les deux.

## Configuration du serveur

### Script de configuration automatique

UCM génère un script shell POSIX qui configure automatiquement votre serveur :

1. Ouvrez le panneau de détail de l’AC
2. Cliquez sur **Télécharger le script de configuration**
3. Transférez le script sur votre serveur
4. Exécutez-le :

\`\`\`bash
chmod +x setup-ssh-ca.sh
sudo ./setup-ssh-ca.sh
\`\`\`

Le script :
- Détecte votre système d’exploitation et votre système d’init
- Sauvegarde sshd_config avant toute modification
- Installe la clé publique de l’AC
- Ajoute TrustedUserCAKeys (AC utilisateur) ou HostCertificate (AC hôte)
- Valide la configuration avec \`sshd -t\`
- Redémarre sshd uniquement si la validation réussit
- Supporte \`--dry-run\` pour prévisualiser les modifications

### Configuration manuelle

#### AC utilisateur
\`\`\`bash
# Copiez la clé publique de l’AC sur le serveur
echo "ssh-ed25519 AAAA... user-ca" | sudo tee /etc/ssh/user_ca.pub

# Ajoutez à sshd_config
echo "TrustedUserCAKeys /etc/ssh/user_ca.pub" | sudo tee -a /etc/ssh/sshd_config

# Redémarrez sshd
sudo systemctl restart sshd
\`\`\`

#### AC hôte
\`\`\`bash
# Signez la clé d’hôte du serveur
# Puis ajoutez à sshd_config :
echo "HostCertificate /etc/ssh/ssh_host_ed25519_key-cert.pub" | sudo tee -a /etc/ssh/sshd_config
sudo systemctl restart sshd
\`\`\`

## Listes de révocation de clés (KRL)

Les AC SSH prennent en charge les listes de révocation de clés pour invalider les certificats compromis :

1. Révoquez les certificats depuis la page Certificats SSH
2. Téléchargez la KRL mise à jour depuis le panneau de détail de l’AC
3. Déployez le fichier KRL sur les serveurs :

\`\`\`bash
# Ajoutez à sshd_config
RevokedKeys /etc/ssh/revoked_keys
\`\`\`

> ⚠ Les serveurs doivent être configurés pour vérifier la KRL. La révocation ne prend effet qu’après le déploiement de la KRL.

## Bonnes pratiques

| Pratique | Recommandation |
|----------|---------------|
| AC distinctes | Utilisez des AC séparées pour les certificats utilisateur et hôte |
| Algorithme de clé | Ed25519 pour les nouveaux déploiements, RSA 4096 pour la compatibilité avec les anciens systèmes |
| Durée de vie de l’AC | Gardez les AC à longue durée de vie ; utilisez des certificats éphémères |
| Sauvegarde | Conservez les sauvegardes UCM : la clé privée de l’AC ne peut pas être exportée seule |
| Correspondance des principals | Associez les principals à des noms d’utilisateur spécifiques, pas à des jokers |
`
  }
}
