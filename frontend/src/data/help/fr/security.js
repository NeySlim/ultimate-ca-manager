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
          { label: 'Activer / Désactiver', text: 'Chiffrer toutes les clés privées en AES-256. L’activation supprime les copies de clés en clair et la désactivation les recrée' },
          { label: 'Fichiers de clé sur disque', text: 'Indique combien de copies de clés en clair subsistent ; utilisez les hooks de déploiement lorsqu’un autre service a besoin d’un fichier de clé' },
          { label: 'UCM_REQUIRE_DB_ENCRYPTION_KEY', text: 'Variable d\'environnement opt-in : refuser de démarrer sans clé de chiffrement de base de données explicite' },
          { label: 'UCM_REQUIRE_KEY_ENCRYPTION', text: 'Variable d\'environnement opt-in : refuser de démarrer si le chiffrement des clés privées n\'est pas activé' },
        ]
      },
      {
        title: 'Politique de mot de passe',
        items: [
          { label: 'Longueur minimale', text: 'Nombre minimal de caractères requis' },
          { label: 'Complexité', text: 'Exiger majuscules, minuscules, chiffres, caractères spéciaux' },
          { label: 'Expiration', text: 'Forcer le changement de mot de passe après un nombre de jours défini' },
          { label: 'Historique', text: 'Empêcher la réutilisation des mots de passe précédents' },
        ]
      },
      {
        title: 'Session et accès',
        items: [
          { label: 'Délai d\'expiration de session', text: 'Déconnexion automatique après une période d\'inactivité' },
          { label: 'Limitation de débit', text: 'Limiter les tentatives de connexion pour prévenir les attaques par force brute' },
          { label: 'Restrictions IP', text: 'Autoriser ou refuser l\'accès depuis des plages IP spécifiques' },
          { label: 'Application de la 2FA', text: 'Exiger l\'authentification à deux facteurs pour tous les utilisateurs' },
        ]
      },
      {
        title: 'Authentification mTLS',
        items: [
          { label: 'CA de confiance', text: 'Sélectionner la CA qui émet et valide les certificats client de connexion mTLS' },
          { label: 'Exiger un certificat client', text: 'Rendre optionnellement mTLS obligatoire pour l\'interface web, la modification des paramètres mTLS nécessite un redémarrage du service' },
        ]
      },
    ],
    tips: [
      'Activez la limitation de débit pour vous protéger contre les outils d\'attaque automatisés',
      'Utilisez les restrictions IP pour limiter l\'accès admin aux réseaux de confiance',
    ],
    warnings: [
      'Une politique de mot de passe trop stricte peut frustrer les utilisateurs',
      'Assurez-vous toujours qu\'au moins un admin peut accéder au système avant d\'activer les restrictions IP',
      'Les paramètres sensibles (session, verrouillage, HSTS, URL publique, politique de mot de passe) exigent admin:settings, les champs sont verrouillés pour les opérateurs',
    ],
  },
  helpGuides: {
    title: 'Paramètres de sécurité',
    content: `
## Vue d'ensemble

Configuration de sécurité à l'échelle du système affectant tous les comptes utilisateurs et les modèles d'accès.

## Chiffrement des clés privées

Chiffrez toutes les clés privées de CA et de certificats stockées en base de données avec AES-256, protégées par un fichier de clé maîtresse conservé en dehors de la base.

- **Statut et compteurs** : La section indique si le chiffrement est activé et combien de clés sont actuellement **chiffrées** vs **non chiffrées**
- **Activer le chiffrement** : Génère le fichier de clé maîtresse et chiffre toutes les clés privées stockées. Sauvegardez le fichier de clé immédiatement : sans lui, les clés chiffrées sont définitivement perdues
- **Désactiver le chiffrement** : Déchiffre toutes les clés privées vers le stockage en clair (confirmation requise)

### Application au démarrage

Sans clé de chiffrement configurée, UCM journalise un avertissement au démarrage mais continue de fonctionner. Deux **variables d'environnement opt-in** transforment cela en échec bloquant :

- \`UCM_REQUIRE_DB_ENCRYPTION_KEY\` : refuser de démarrer sans clé de chiffrement de base de données explicite (sinon les secrets d'intégration se rabattent sur une clé dérivée de l'identifiant machine)
- \`UCM_REQUIRE_KEY_ENCRYPTION\` : refuser de démarrer si le chiffrement des clés privées n'est pas activé

Les deux acceptent \`1\`/\`true\`/\`yes\`/\`on\`. Une clé invalide est traitée comme fatale au lieu de retomber silencieusement en clair.

## Politique de mot de passe

### Exigences de complexité
- **Longueur minimale** : 8 à 32 caractères
- **Exiger majuscules** : Au moins une lettre majuscule
- **Exiger minuscules** : Au moins une lettre minuscule
- **Exiger chiffres** : Au moins un chiffre
- **Exiger caractères spéciaux** : Au moins un symbole

### Expiration du mot de passe
Forcer les utilisateurs à changer leur mot de passe après un nombre de jours défini. Définir à 0 pour désactiver.

### Historique des mots de passe
Empêcher la réutilisation des N derniers mots de passe. Les utilisateurs ne peuvent pas définir un mot de passe correspondant à l'un de leurs N précédents mots de passe.

## Gestion de session

### Délai d'expiration de session
Déconnecter automatiquement les utilisateurs après N minutes d'inactivité. S'applique uniquement aux sessions de l'interface web, pas aux clés API.

### Sessions simultanées
Limiter le nombre de sessions simultanées par utilisateur. Les connexions supplémentaires termineront la session la plus ancienne.

## Limitation de débit

### Tentatives de connexion
Limiter les tentatives de connexion échouées par adresse IP dans une fenêtre temporelle. Après dépassement de la limite, l'IP est temporairement bloquée.

### Durée de verrouillage
Durée pendant laquelle une IP est bloquée après dépassement de la limite de tentatives de connexion.

## Restrictions IP

### Liste autorisée
Autoriser uniquement les connexions depuis des IP ou plages CIDR spécifiées. Toutes les autres IP sont bloquées.

### Liste refusée
Bloquer des IP ou plages CIDR spécifiques. Toutes les autres IP sont autorisées.

> ⚠ Soyez extrêmement prudent avec les restrictions IP. Une mauvaise configuration peut verrouiller tous les utilisateurs, y compris les admins. Testez toujours d'abord avec une seule IP.

## Authentification à deux facteurs

### Application
Exiger que tous les utilisateurs activent la 2FA. Les utilisateurs qui n'ont pas configuré la 2FA seront invités à le faire lors de leur prochaine connexion. Une application TOTP ou une clé de sécurité enregistrée la satisfait, à l'enrôlement comme à la connexion. Tant qu'elle est imposée, TOTP ne peut être désactivé que si une clé de sécurité reste, et la dernière clé supprimée que si TOTP reste.

### Méthodes prises en charge
- **TOTP** : Mots de passe à usage unique basés sur le temps (applications d'authentification)
- **WebAuthn** : Clés de sécurité matérielles et biométrie

> 💡 Appliquez la 2FA pour les comptes admin au minimum. Envisagez de l'appliquer pour tous les utilisateurs dans les environnements sensibles en termes de sécurité.

## Authentification mTLS

Permettre aux utilisateurs de se connecter avec un certificat client au lieu d'un mot de passe :

- **CA de confiance** : Sélectionner la CA qui émet et valide les certificats client mTLS
- **Exiger un certificat client** : Rendre optionnellement mTLS obligatoire pour l'interface web
- La modification des paramètres mTLS nécessite un redémarrage du service

## Permissions requises

Les paramètres sensibles : session, verrouillage, HSTS, URL publique et politique de mot de passe, exigent la permission **admin:settings**. Pour les opérateurs (write:settings uniquement), ces champs apparaissent verrouillés ; le reste de la carte s'enregistre normalement.
`
  }
}
