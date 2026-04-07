export default {
  helpContent: {
    title: 'Utilisateurs et groupes',
    subtitle: 'Gestion des identités et des accès',
    overview: 'Gérez les comptes utilisateurs et les appartenances aux groupes. Attribuez des rôles pour contrôler l\'accès aux fonctionnalités UCM. Les groupes permettent la gestion des permissions en masse pour les équipes.',
    sections: [
      {
        title: 'Utilisateurs',
        items: [
          { label: 'Créer un utilisateur', text: 'Ajouter un nouvel utilisateur avec nom d\'utilisateur, e-mail et mot de passe initial' },
          { label: 'Rôles', text: 'Attribuer des rôles système ou personnalisés pour contrôler les permissions' },
          { label: 'Statut', text: 'Activer ou désactiver les comptes utilisateurs' },
          { label: 'Réinitialisation du mot de passe', text: 'Réinitialiser le mot de passe d\'un utilisateur (action administrateur)' },
          { label: 'Clés API', text: 'Gérer les clés API par utilisateur pour l\'accès programmatique' },
        ]
      },
      {
        title: 'Groupes',
        items: [
          { label: 'Créer un groupe', text: 'Définir un groupe et assigner des membres' },
          { label: 'Héritage de rôle', text: 'Les groupes peuvent hériter des rôles — tous les membres obtiennent les permissions du groupe' },
          { label: 'Gestion des membres', text: 'Ajouter ou retirer des utilisateurs des groupes' },
        ]
      },
    ],
    tips: [
      'Utilisez les groupes pour gérer les permissions des équipes plutôt que des utilisateurs individuels',
      'Les utilisateurs désactivés ne peuvent pas se connecter mais leurs données sont préservées',
    ],
    warnings: [
      'La suppression d\'un utilisateur est permanente — envisagez la désactivation à la place',
    ],
  },
  helpGuides: {
    title: 'Utilisateurs et groupes',
    content: `
## Vue d'ensemble

Gérez les comptes utilisateurs, les groupes et les attributions de rôles. Les utilisateurs s'authentifient sur UCM via mot de passe, SSO, WebAuthn ou mTLS. Les groupes permettent la gestion des permissions en masse.

## Onglet Utilisateurs

### Créer un utilisateur
1. Cliquez sur **Créer un utilisateur**
2. Entrez le **nom d'utilisateur** (unique, ne peut pas être modifié ultérieurement)
3. Entrez l'**e-mail** (utilisé pour les notifications et la récupération)
4. Définissez un **mot de passe initial**
5. Sélectionnez un **rôle** (Admin, Opérateur, Auditeur, Lecteur ou personnalisé)
6. Cliquez sur **Créer**

### Statut de l'utilisateur
- **Actif** — Peut se connecter et effectuer des actions
- **Désactivé** — Ne peut pas se connecter, les données sont préservées

Basculez le statut d'un utilisateur sans supprimer son compte.

### Réinitialisation du mot de passe
Les administrateurs peuvent réinitialiser le mot de passe de tout utilisateur. L'utilisateur sera invité à le changer lors de sa prochaine connexion.

### Clés API
Chaque utilisateur peut avoir plusieurs clés API pour l'accès programmatique. Les clés API héritent des permissions du rôle de l'utilisateur. Voir la page Compte pour gérer vos propres clés.

## Onglet Groupes

### Créer un groupe
1. Cliquez sur **Créer un groupe**
2. Entrez un **nom** et une description optionnelle
3. Attribuez un **rôle** (les membres du groupe héritent de ce rôle)
4. Cliquez sur **Créer**

### Gérer les membres
- Cliquez sur un groupe pour voir ses membres
- Utilisez le **panneau de transfert** pour ajouter/retirer des utilisateurs
- Les utilisateurs peuvent appartenir à plusieurs groupes

### Héritage de rôle
Les permissions effectives d'un utilisateur sont l'**union** de :
- Leur rôle directement attribué
- Tous les rôles des groupes auxquels ils appartiennent

## Rôles

### Rôles système
- **Admin** — Accès complet à toutes les fonctionnalités
- **Opérateur** — Peut gérer les certificats, CA, CSR mais pas les paramètres système
- **Auditeur** — Accès en lecture seule à toutes les données opérationnelles pour la conformité et l'audit
- **Lecteur** — Accès en lecture seule aux certificats, CA et modèles

### Rôles personnalisés
Créez des rôles avec des permissions granulaires sur la page **RBAC**.

> 💡 Utilisez les groupes pour gérer les permissions d'équipe plutôt que d'attribuer des rôles à des utilisateurs individuels.
`
  }
}
