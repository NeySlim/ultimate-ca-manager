export default {
  helpContent: {
    title: 'Paramètres de sécurité',
    subtitle: 'Renforcement du système',
    overview: 'Configurez les politiques de sécurité à l\'échelle du système. Gérez les politiques de mot de passe, les délais de session, la limitation de débit, les restrictions IP et l\'application de l\'authentification à deux facteurs.',
    sections: [
      {
        title: 'Politique de mot de passe',
        items: [
          { label: 'Longueur minimale', text: 'Longueur minimale requise pour le mot de passe (8-32 caractères)' },
          { label: 'Exigences de complexité', text: 'Exiger majuscules, minuscules, chiffres et caractères spéciaux' },
          { label: 'Expiration du mot de passe', text: 'Forcer les changements de mot de passe après un nombre de jours défini' },
          { label: 'Historique des mots de passe', text: 'Empêcher la réutilisation des N derniers mots de passe' },
        ]
      },
      {
        title: 'Gestion de session',
        items: [
          { label: 'Délai d\'expiration', text: 'Déconnexion automatique après N minutes d\'inactivité' },
          { label: 'Sessions simultanées', text: 'Nombre maximum de sessions actives par utilisateur' },
        ]
      },
      {
        title: 'Limitation de débit',
        items: [
          { label: 'Tentatives de connexion', text: 'Nombre maximum de tentatives de connexion échouées par adresse IP' },
          { label: 'Durée de verrouillage', text: 'Durée pendant laquelle une IP est bloquée après dépassement de la limite' },
        ]
      },
      {
        title: 'Restrictions IP',
        items: [
          { label: 'Liste autorisée', text: 'Autoriser uniquement les connexions depuis des IP ou plages CIDR spécifiées' },
          { label: 'Liste refusée', text: 'Bloquer des IP ou plages CIDR spécifiques' },
        ]
      },
    ],
    tips: [
      'Appliquez la 2FA pour les comptes admin au minimum',
      'Testez les restrictions IP soigneusement avant de les appliquer — des règles incorrectes peuvent verrouiller tout le monde',
    ],
    warnings: [
      'Les restrictions IP doivent être soigneusement testées — une mauvaise configuration peut verrouiller tous les utilisateurs y compris les admins',
    ],
  },
  helpGuides: {
    title: 'Paramètres de sécurité',
    content: `
## Vue d'ensemble

Configuration de sécurité à l'échelle du système affectant tous les comptes utilisateurs et les modèles d'accès.

## Politique de mot de passe

### Exigences de complexité
- **Longueur minimale** — 8 à 32 caractères
- **Exiger majuscules** — Au moins une lettre majuscule
- **Exiger minuscules** — Au moins une lettre minuscule
- **Exiger chiffres** — Au moins un chiffre
- **Exiger caractères spéciaux** — Au moins un symbole

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
Exiger que tous les utilisateurs activent la 2FA. Les utilisateurs qui n'ont pas configuré la 2FA seront invités à le faire lors de leur prochaine connexion.

### Méthodes prises en charge
- **TOTP** — Mots de passe à usage unique basés sur le temps (applications d'authentification)
- **WebAuthn** — Clés de sécurité matérielles et biométrie

> 💡 Appliquez la 2FA pour les comptes admin au minimum. Envisagez de l'appliquer pour tous les utilisateurs dans les environnements sensibles en termes de sécurité.
`
  }
}
