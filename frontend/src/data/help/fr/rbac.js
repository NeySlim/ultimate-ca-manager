export default {
  helpContent: {
    title: 'Contrôle d\'accès basé sur les rôles',
    subtitle: 'Gestion granulaire des permissions',
    overview: 'Définissez des rôles personnalisés avec des permissions granulaires. Les rôles système (Admin, Opérateur, Auditeur, Lecteur) sont intégrés. Les rôles personnalisés vous permettent de contrôler exactement quelles opérations chaque utilisateur peut effectuer.',
    sections: [
      {
        title: 'Rôles système',
        definitions: [
          { term: 'Admin', description: 'Accès complet à toutes les fonctionnalités et paramètres' },
          { term: 'Opérateur', description: 'Peut gérer les certificats et CA mais pas les paramètres système' },
          { term: 'Auditeur', description: 'Accès en lecture seule à toutes les données opérationnelles pour la conformité et l\'audit' },
          { term: 'Lecteur', description: 'Accès de base en lecture seule aux certificats, CA et modèles' },
        ]
      },
      {
        title: 'Rôles personnalisés',
        items: [
          { label: 'Créer un rôle', text: 'Définir un nouveau rôle avec un nom et une description' },
          { label: 'Matrice de permissions', text: 'Cocher/décocher les permissions par catégorie (CA, Certificats, Utilisateurs, etc.)' },
          { label: 'Couverture', text: 'Pourcentage visuel du total des permissions accordées au rôle' },
          { label: 'Nombre d\'utilisateurs', text: 'Voir combien d\'utilisateurs sont assignés à chaque rôle' },
        ]
      },
    ],
    tips: [
      'Suivez le principe du moindre privilège — n\'accordez que les permissions nécessaires',
      'Les rôles système ne peuvent pas être modifiés ou supprimés',
      'Basculez des catégories entières on/off pour une configuration rapide des rôles',
    ],
  },
  helpGuides: {
    title: 'Contrôle d\'accès basé sur les rôles',
    content: `
## Vue d'ensemble

RBAC fournit une gestion granulaire des permissions. Définissez des rôles personnalisés avec des permissions spécifiques et attribuez-les aux utilisateurs ou groupes.

## Rôles système

Quatre rôles intégrés qui ne peuvent pas être modifiés ou supprimés :

- **Admin** — Accès complet à tout
- **Opérateur** — Gérer les certificats, CA, CSR, modèles. Pas d'accès aux paramètres système, utilisateurs ou RBAC
- **Auditeur** — Accès en lecture seule à toutes les données opérationnelles (certificats, CA, ACME, SCEP, HSM, journaux d'audit, politiques, groupes) mais pas aux paramètres ou à la gestion des utilisateurs
- **Lecteur** — Accès de base en lecture seule aux certificats, CA, CSR, modèles et magasin de confiance

## Rôles personnalisés

### Créer un rôle personnalisé
1. Cliquez sur **Créer un rôle**
2. Entrez un **nom** et une description optionnelle
3. Configurez les permissions à l'aide de la **matrice de permissions**
4. Cliquez sur **Créer**

### Matrice de permissions
Les permissions sont organisées par catégorie :
- **CA** — Créer, lire, mettre à jour, supprimer, importer, exporter
- **Certificats** — Émettre, lire, révoquer, renouveler, exporter, supprimer
- **CSR** — Créer, lire, signer, supprimer
- **Modèles** — Créer, lire, mettre à jour, supprimer
- **Utilisateurs** — Créer, lire, mettre à jour, supprimer
- **Groupes** — Créer, lire, mettre à jour, supprimer
- **Paramètres** — Lire, mettre à jour
- **Audit** — Lire, exporter, nettoyer
- **ACME** — Configurer, gérer les comptes
- **SCEP** — Configurer, approuver les requêtes
- **Magasin de confiance** — Gérer les certificats de confiance
- **HSM** — Gérer les fournisseurs et les clés
- **Sauvegarde** — Créer, restaurer

### Bascules de catégorie
Cliquez sur un en-tête de catégorie pour activer/désactiver toutes les permissions de cette catégorie d'un coup.

### Indicateur de couverture
Un badge de pourcentage montre quelle part de l'ensemble total des permissions le rôle couvre. 100% = équivalent Admin.

## Attribuer des rôles

Les rôles sont attribués :
- **Directement** — Sur la page Utilisateurs, modifiez un utilisateur et sélectionnez un rôle
- **Via les groupes** — Attribuez un rôle à un groupe ; tous les membres en héritent

## Permissions effectives

Les permissions effectives d'un utilisateur sont calculées comme l'union de :
1. Les permissions du rôle directement attribué
2. Tous les rôles des groupes auxquels il appartient

La règle la plus permissive l'emporte (modèle additif, pas de règles de refus).

> ⚠ Les rôles système ne peuvent pas être modifiés ou supprimés. Créez des rôles personnalisés pour des besoins spécifiques.
`
  }
}
