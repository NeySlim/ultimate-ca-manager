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
          { label: 'Matrice de permissions', text: 'Cocher/décocher les permissions par catégorie (CA, Certificats, Clés privées, etc.)' },
          { label: 'Couverture', text: 'Pourcentage visuel du total des permissions accordées au rôle' },
          { label: 'Nombre d\'utilisateurs', text: 'Voir combien d\'utilisateurs sont assignés à chaque rôle' },
        ]
      },
    ],
    tips: [
      'Suivez le principe du moindre privilège : n\'accordez que les permissions nécessaires',
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

- **Admin** : Accès complet à tout
- **Opérateur** : Gérer les certificats, CA, CSR, modèles. Pas d'accès aux paramètres système, utilisateurs ou RBAC
- **Auditeur** : Accès en lecture seule à toutes les données opérationnelles (certificats, CA, ACME, SCEP, HSM, journaux d'audit, politiques, groupes) mais pas aux paramètres ou à la gestion des utilisateurs
- **Lecteur** : Accès de base en lecture seule aux certificats, CA, CSR, modèles et magasin de confiance

## Rôles personnalisés

### Créer un rôle personnalisé
1. Cliquez sur **Créer un rôle**
2. Entrez un **nom** et une description optionnelle
3. Configurez les permissions à l'aide de la **matrice de permissions**
4. Cliquez sur **Créer**

### Matrice de permissions
Les permissions sont organisées par catégorie :
- **CA** : Créer, lire, mettre à jour, supprimer, importer, exporter (certificat seul : voir Clés privées)
- **Certificats** : Émettre, lire, révoquer, renouveler, supprimer, exporter (certificat seul : voir Clés privées)
- **Clés privées** : Export direct de la clé privée d'un certificat ou d'une CA (\`read:private_keys\`). Aucun rôle intégré hormis Admin ne la détient ; un rôle personnalisé peut l'accorder. Les rôles sans cette permission passent par la récupération de clés
- **CSR** : Créer, lire, signer, supprimer
- **Modèles** : Créer, lire, mettre à jour, supprimer
- **Utilisateurs** : Lire (la gestion des comptes est réservée aux administrateurs)
- **Groupes** : Créer, lire, mettre à jour, supprimer
- **Paramètres** : Lire, mettre à jour
- **Audit** : Lire, exporter (le nettoyage est réservé aux administrateurs)
- **ACME** : Configurer, gérer les comptes
- **SCEP** : Configurer, approuver les requêtes
- **Magasin de confiance** : Gérer les certificats de confiance
- **HSM** : Gérer les fournisseurs et les clés
- **SSH** : Gérer les CA et certificats SSH
- **Politiques** : Consulter les politiques de certificat
- **Approbations** : Consulter et décider des demandes d'approbation
- **Récupération de clés** : Demander des récupérations et consulter les demandes (l'approbation est réservée aux administrateurs)

Un rôle personnalisé peut accorder toute permission vérifiée par UCM, sauf celles réservées aux administrateurs : l'accès complet et les jokers, toute action d'administration (approbation des récupérations de clés, administration du système et des utilisateurs), la gestion des comptes, le SSO, les déploiements, les événements système et la suppression du journal d'audit. Une permission enregistrée que le rôle ne peut pas accorder est affichée comme ignorée et conservée telle quelle.

### Bascules de catégorie
Cliquez sur un en-tête de catégorie pour activer/désactiver toutes les permissions de cette catégorie d'un coup.

### Indicateur de couverture
Un badge de pourcentage montre quelle part de l'ensemble total des permissions le rôle couvre.

## Attribuer des rôles

Les rôles sont attribués :
- **Directement** : Sur la page Utilisateurs, modifiez un utilisateur et sélectionnez un rôle intégré et, si besoin, un rôle personnalisé qui s'y ajoute. Les changements s'appliquent dès la requête suivante de l'utilisateur
- **Via les groupes** : Un groupe accorde un ensemble de permissions ; chaque membre les reçoit en plus de son propre rôle

## Permissions effectives

Les permissions effectives d'un utilisateur sont calculées comme l'union de :
1. Les permissions de son rôle intégré
2. Les permissions de son rôle personnalisé, y compris celles des rôles dont il hérite
3. Les permissions accordées par les groupes auxquels il appartient

La règle la plus permissive l'emporte (modèle additif, pas de règles de refus).

> ⚠ Les rôles système ne peuvent pas être modifiés ou supprimés. Créez des rôles personnalisés pour des besoins spécifiques.
`
  }
}
