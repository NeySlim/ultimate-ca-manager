export default {
  helpContent: {
    title: 'Paramètres de sécurité',
    subtitle: 'Politiques d\'authentification et d\'accès',
    overview: 'Configurez les politiques de mot de passe, la gestion de session, la limitation de débit et la sécurité réseau. Ces paramètres s\'appliquent à l\'échelle du système et affectent tous les comptes utilisateurs.',
    sections: [
      {
        title: 'Chiffrement des clés privées',
        items: [
          { label: 'Statut et compteurs', text: 'Indique si le chiffrement est activé et combien de clés privées stockées sont chiffrées vs non chiffrées' },
          { label: 'Activer / Désactiver', text: 'Chiffrer toutes les clés privées de CA et de certificats en AES-128 (Fernet, avec HMAC-SHA256) sous un fichier de clé maîtresse. L’activation supprime aussi les copies de clés en clair et la désactivation les recrée' },
          { label: 'Premier démarrage', text: 'Sans clé maîtresse, UCM crée /etc/ucm/master.key (0600) au démarrage et chiffre les clés déjà stockées. Un conteneur ne le fait que si /etc/ucm est un volume nommé ou un répertoire de l\'hôte. Ignoré avec KEY_ENCRYPTION_KEY défini, avec des clés chiffrées ou une chaîne d\'audit à clé déjà en base, après une désactivation du chiffrement ici, ou avec UCM_AUTO_MASTER_KEY=false. À chaque démarrage, une clé chargée chiffre aussi les valeurs encore stockées en clair, et une clé qui ne les déchiffre pas place UCM en mode sans échec. Sauvegardez le fichier de clé' },
          { label: 'Fichiers de clé sur disque', text: 'Indique combien de copies de clés en clair subsistent ; utilisez les hooks de déploiement lorsqu’un autre service a besoin d’un fichier de clé' },
          { label: 'UCM_REQUIRE_DB_ENCRYPTION_KEY', text: 'Variable d\'environnement opt-in : refuser de démarrer sans clé de chiffrement de base de données explicite' },
          { label: 'UCM_REQUIRE_KEY_ENCRYPTION', text: 'Variable d\'environnement opt-in : refuser de démarrer si le chiffrement des clés privées n\'est pas activé' },
          { label: 'Chiffrer les clés restantes', text: 'Affiché tant que le chiffrement est activé et que certaines clés ou certains secrets restent stockés non chiffrés : les chiffre, en laissant tels quels ceux qui le sont déjà' },
          { label: 'Rotation de la clé de données', text: 'Les clés sont chiffrées sous une clé de données stockée en base et enveloppée par la clé maîtresse (master.key ou KEY_ENCRYPTION_KEY), qui reste le seul fichier à sauvegarder. Rotation de la clé de données rechiffre chaque clé et secret stocké sous une nouvelle clé de données sans changer la clé maîtresse ; une rotation interrompue garde les deux clés de données et se termine en la relançant. L\'empreinte affichée désigne la clé maîtresse sans la révéler' },
        ]
      },
      {
        title: 'Politique de mot de passe',
        items: [
          { label: 'Longueur minimale', text: 'Nombre minimal de caractères requis, de 6 à 32' },
          { label: 'Complexité', text: 'Exiger des majuscules, des chiffres et des caractères spéciaux, chacun activé séparément' },
        ]
      },
      {
        title: 'Session et accès',
        items: [
          { label: 'Délai d\'expiration de session', text: 'Déconnexion automatique après une période d\'inactivité (Paramètres › Général)' },
          { label: 'Durée de session', text: 'Durée maximale d\'une session en heures, quelle que soit l\'activité' },
          { label: 'Verrouillage de compte', text: 'Max tentatives de connexion et Durée de verrouillage (Paramètres › Général) verrouillent un compte après des échecs répétés. Les limites de requêtes par IP sont fixées par les variables d\'environnement RATE_LIMIT_*, pas sur cette page' },
          { label: 'Liste d\'accès administrateur', text: 'Limiter l\'interface web et l\'API de gestion aux adresses IP et réseaux listés' },
          { label: 'Application de la 2FA', text: 'Exiger l\'authentification à deux facteurs pour tous les utilisateurs' },
        ]
      },
      {
        title: 'Liste d\'accès administrateur',
        items: [
          { label: 'Réseaux', text: 'Une adresse IPv4 ou IPv6 ou un réseau CIDR par ligne, 100 au maximum. Vide signifie aucune restriction. IPv4 et IPv6 sont listés séparément : 0.0.0.0/0 n\'admet pas un client IPv6, ni ::/0 un client IPv4' },
          { label: 'Ce qui est bloqué', text: 'Depuis les autres adresses : l\'interface web, la connexion, l\'API /api/v2 (clés API comprises) et le canal WebSocket répondent 403' },
          { label: 'Toujours accessibles', text: 'ACME, SCEP, EST, OCSP, CRL/AIA, TSA, XCEP/WSTEP, le script d\'installation SSH et les points de contrôle de santé' },
          { label: 'Votre adresse', text: 'La section affiche l\'adresse que le serveur voit pour vous ; une liste qui ne l\'inclut pas est refusée' },
          { label: 'UCM_ADMIN_ALLOWED_NETWORKS', text: 'Variable d\'environnement (séparée par des virgules) qui l\'emporte sur le paramètre et le rend en lecture seule' },
          { label: 'UCM_ADMIN_ALLOWLIST_DISABLE', text: 'Définie à 1 avec un redémarrage, désactive le contrôle après un verrouillage' },
        ]
      },
      {
        title: 'Authentification mTLS',
        items: [
          { label: 'CA de confiance', text: 'La CA dont les certificats client sont acceptés à la connexion, et l\'émettrice par défaut lorsqu\'un utilisateur en génère un. Toute CA dont le certificat n\'est pas révoqué peut être choisie, y compris sans clé ou hors ligne : une telle CA n\'émet rien, ses utilisateurs importent donc des certificats émis ailleurs (v2.248). C\'est la seule ancre de confiance du port HTTPS : un certificat client de sa parente ou d\'une CA sœur est refusé à la poignée de main TLS, faites donc confiance à une racine pour accepter toute sa hiérarchie (v2.252)' },
          { label: 'Exiger un certificat client', text: 'Rendre optionnellement mTLS obligatoire pour l\'interface web, la modification des paramètres mTLS nécessite un redémarrage du service' },
          { label: "Même numéro de série, autre AC (v2.251)", text: "Un enrôlement est identifié par son émetteur et son numéro de série : un certificat client peut être enrôlé, importé ou assigné même si le certificat enrôlé d'une autre AC porte le même numéro de série" },
          { label: "En-têtes de reverse proxy (v2.252)", text: "Derrière un proxy qui transmet le certificat client sous forme d'en-têtes, envoyez le DN de l'émetteur (X-SSL-Client-I-DN) avec le numéro de série, lu en hexadécimal, ou le certificat lui-même (X-SSL-Client-Cert). Un numéro de série sans son émetteur n'ouvre aucun enrôlement qui en a enregistré un, et un certificat présenté ne peut pas être enrôlé sans lui" },
          { label: 'Émetteur révoqué', text: 'Un certificat client émis sous une CA révoquée, à n\'importe quel niveau de sa chaîne, n\'ouvre aucune session et ne peut être ni enrôlé ni importé (v2.252)' },
          { label: "Clés générées (v2.251)", text: "Un certificat mTLS utilisateur généré par UCM reçoit une clé à la force de l'AC émettrice, RSA ou courbe NIST acceptée par les navigateurs, ramenée au type autorisé le plus proche par les politiques, au lieu de toujours du RSA-2048" },
        ]
      },
    ],
    tips: [
      'Activez la limitation de débit pour vous protéger contre les outils d\'attaque automatisés',
      'Utilisez la liste d\'accès administrateur pour limiter l\'interface web à votre VLAN de gestion, bastion ou VPN',
    ],
    warnings: [
      'Une politique de mot de passe trop stricte peut frustrer les utilisateurs',
      'Derrière un reverse proxy, définissez UCM_BEHIND_PROXY et UCM_TRUSTED_PROXIES avant d\'utiliser la liste d\'accès administrateur, sinon toutes les requêtes semblent provenir du proxy',
      'Les paramètres sensibles (session, verrouillage, HSTS, URL publique, politique de mot de passe) exigent admin:settings, les champs sont verrouillés pour les opérateurs',
    ],
  },
  helpGuides: {
    title: 'Paramètres de sécurité',
    content: `
## Vue d'ensemble

Configuration de sécurité à l'échelle du système affectant tous les comptes utilisateurs et les modèles d'accès.

## Chiffrement des clés privées

Chiffrez toutes les clés privées de CA et de certificats stockées en base de données avec AES-128 (Fernet, avec HMAC-SHA256), protégées par un fichier de clé maîtresse conservé en dehors de la base.

- **Statut et compteurs** : La section indique si le chiffrement est activé et combien de clés sont actuellement **chiffrées** vs **non chiffrées**
- **Premier démarrage** : Une installation sans clé maîtresse crée \`/etc/ucm/master.key\` (mode 0600) au démarrage et chiffre les clés et secrets déjà stockés. Dans un conteneur, cela n'arrive que si \`/etc/ucm\` est un volume nommé ou un répertoire de l'hôte, jamais un volume anonyme. Cela n'arrive pas quand \`KEY_ENCRYPTION_KEY\` est défini, quand la base contient déjà des clés chiffrées (mode sans échec) ou une chaîne d'audit scellée sous une clé précédente, après une désactivation du chiffrement ici, ni avec \`UCM_AUTO_MASTER_KEY=false\`. Cela supprime aussi les copies de clés en clair sous \`data/private\`. À chaque démarrage, une clé chargée chiffre aussi les valeurs encore stockées en clair, et une clé qui ne les déchiffre pas place UCM en mode sans échec jusqu'à la restauration de la précédente. Sauvegardez le fichier de clé : les sauvegardes UCM n'en ont pas besoin, mais une copie de la base ne peut pas être déchiffrée sans lui
- **Activer le chiffrement** : Génère le fichier de clé maîtresse et chiffre toutes les clés privées stockées, quand aucune clé n'a été créée au premier démarrage ; refusé dans un conteneur dont \`/etc/ucm\` ne survivrait pas. Sauvegardez le fichier de clé immédiatement : sans lui, les clés chiffrées sont définitivement perdues
- **Désactiver le chiffrement** : Déchiffre toutes les clés privées vers le stockage en clair (confirmation requise). UCM ne crée alors plus de clé aux démarrages suivants, jusqu'à la réactivation du chiffrement
- **Chiffrer les clés restantes** : Affiché tant que le chiffrement est activé et que certaines clés ou certains secrets restent stockés non chiffrés ; les chiffre, en laissant tels quels ceux qui le sont déjà

### Application au démarrage

Sans clé de chiffrement configurée, UCM journalise un avertissement au démarrage mais continue de fonctionner. Deux **variables d'environnement opt-in** transforment cela en échec bloquant :

- \`UCM_REQUIRE_DB_ENCRYPTION_KEY\` : refuser de démarrer sans clé de chiffrement de base de données explicite (sinon les secrets d'intégration se rabattent sur une clé dérivée de l'identifiant machine)
- \`UCM_REQUIRE_KEY_ENCRYPTION\` : refuser de démarrer si le chiffrement des clés privées n'est pas activé

Les deux acceptent \`1\`/\`true\`/\`yes\`/\`on\`. Une clé invalide est traitée comme fatale au lieu de retomber silencieusement en clair.

## Politique de mot de passe

### Exigences de complexité
- **Longueur minimale** : 6 à 32 caractères (8 par défaut)
- **Exiger majuscules** : Au moins une lettre majuscule
- **Exiger chiffres** : Au moins un chiffre
- **Exiger caractères spéciaux** : Au moins un symbole

UCM n'a ni expiration de mot de passe ni historique des mots de passe.

## Gestion de session

### Délai d'expiration de session
Sous **Paramètres › Général** : déconnecter automatiquement les utilisateurs après N minutes d'inactivité. S'applique uniquement aux sessions de l'interface web, pas aux clés API.

### Durée de session
Durée maximale d'une session en heures, quelle que soit l'activité. Le nombre de sessions simultanées par utilisateur n'est pas limité.

## Protection de connexion

### Max tentatives de connexion
Sous **Paramètres › Général** : le nombre de connexions échouées après lequel le **compte** est verrouillé.

### Durée de verrouillage
Durée pendant laquelle le compte reste verrouillé, en minutes.
Un compte verrouillé répond à une connexion par mot de passe ou LDAP par le même « Invalid credentials » qu'un nom inconnu jusqu'à la fin du verrouillage, la réponse ne révèle donc pas que le compte existe ; le verrouillage est consigné dans le journal d'audit.

### Limites de requêtes
Les requêtes sont aussi limitées par adresse IP du client, par les variables d'environnement \`RATE_LIMIT_*\` (seaux authentification, lourd, standard et protocole ; clients de réseau privé exemptés avec \`RATE_LIMIT_TRUST_LAN\`). Les routes de connexion ont leur propre limite, 5 tentatives par minute, signalée par \`Retry-After\` dans la réponse 429.

## Liste d'accès administrateur

Limitez l'interface web et l'API de gestion à une liste d'adresses IP et de réseaux CIDR, IPv4 ou IPv6, un par ligne (100 au maximum). Une liste vide ne restreint rien. IPv4 et IPv6 sont listés séparément : \`0.0.0.0/0\` n'admet pas un client IPv6, et \`::/0\` n'admet pas un client IPv4.

- **Bloqué depuis les autres adresses** : l'interface web et ses ressources, la connexion, chaque appel \`/api/v2\` (clés API comprises) et le canal WebSocket répondent **403**
- **Toujours accessibles** : ACME et le proxy ACME, SCEP, EST, OCSP, CRL et AIA, TSA, XCEP/WSTEP, le script d'installation SSH, et les points de contrôle de santé et de métriques, afin que les équipements et les sondes continuent de fonctionner
- **Votre adresse** : la section affiche l'adresse que le serveur voit pour vous. Une liste qui ne l'inclut pas est refusée, un enregistrement ne peut donc pas vous verrouiller
- **Audit** : chaque modification de la liste est écrite dans le journal d'audit

### Variables d'environnement
- \`UCM_ADMIN_ALLOWED_NETWORKS\` : liste séparée par des virgules qui l'emporte sur le paramètre et rend le champ en lecture seule
- \`UCM_ADMIN_ALLOWLIST_DISABLE=1\` : désactive le contrôle après un redémarrage ; à utiliser pour sortir d'un verrouillage, puis à retirer

### Reverse proxy, Docker et Kubernetes
Derrière un reverse proxy, définissez \`UCM_BEHIND_PROXY=1\` et listez le proxy dans \`UCM_TRUSTED_PROXIES\`, sinon toutes les requêtes semblent provenir du proxy. Avec Docker en mode bridge et sans proxy, l'adresse vue peut être celle située après le NAT de Docker : vérifiez l'adresse affichée avant d'enregistrer.

> ⚠ Ce filtre agit au niveau applicatif. Conservez aussi un pare-feu devant le port HTTPS.

## Authentification à deux facteurs

### Application
Exiger que tous les utilisateurs activent la 2FA. Les utilisateurs qui n'ont pas configuré la 2FA seront invités à le faire lors de leur prochaine connexion. Une application TOTP ou une clé de sécurité enregistrée la satisfait, à l'enrôlement comme à la connexion. Tant qu'elle est imposée, TOTP ne peut être désactivé que si une clé de sécurité reste, et la dernière clé supprimée que si TOTP reste. Un utilisateur dont la clé est devenue le second facteur la garde quand l'imposition est levée.

### Méthodes prises en charge
- **TOTP** : Mots de passe à usage unique basés sur le temps (applications d'authentification)
- **WebAuthn** : Clés de sécurité matérielles et biométrie

> 💡 Appliquez la 2FA pour les comptes admin au minimum. Envisagez de l'appliquer pour tous les utilisateurs dans les environnements sensibles en termes de sécurité.

## Authentification mTLS

Permettre aux utilisateurs de se connecter avec un certificat client au lieu d'un mot de passe :

- **CA de confiance** : La CA dont les certificats client sont acceptés à la connexion, et l'émettrice par défaut lorsqu'un utilisateur en génère un. Toute CA dont le certificat n'est pas révoqué peut être choisie, y compris sans clé ou hors ligne : une telle CA n'émet rien, ses utilisateurs importent donc des certificats émis ailleurs (v2.248). C'est la seule ancre de confiance du port HTTPS : un certificat client de sa parente ou d'une CA sœur est refusé à la poignée de main TLS, faites donc confiance à une racine pour accepter toute sa hiérarchie (v2.252)
- **Exiger un certificat client** : Rendre optionnellement mTLS obligatoire pour l'interface web
- La modification des paramètres mTLS nécessite un redémarrage du service
- **Émetteur révoqué** : Un certificat client émis sous une CA révoquée, à n'importe quel niveau de sa chaîne, n'ouvre aucune session et ne peut être ni enrôlé ni importé (v2.252)

## Permissions requises

Les paramètres sensibles : session, verrouillage, HSTS, URL publique et politique de mot de passe, exigent la permission **admin:settings**. Pour les opérateurs (write:settings uniquement), ces champs apparaissent verrouillés ; le reste de la carte s'enregistre normalement.
`
  }
}
