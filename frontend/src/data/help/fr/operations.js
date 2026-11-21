export default {
  helpContent: {
    title: 'Opérations',
    subtitle: 'Importation, exportation et actions en masse',
    overview: 'Centre d’opérations centralisé. Importez des certificats depuis des fichiers ou OPNsense, exportez des bundles aux formats PEM/P7B et effectuez des actions en masse sur tous les types de ressources avec recherche et filtres intégrés.',
    sections: [
      {
        title: 'Disposition de la page',
        content: 'Le sommaire à gauche liste Importer, Exporter et Actions en masse ; l’opération choisie s’affiche dans son cadre. Chacune garde ses boutons, la page n’a pas de barre d’enregistrement.',
        items: [
          { label: 'Liens', text: 'Un lien vers /operations?tab=export ou /operations?tab=bulk ouvre cette opération' },
        ],
      },
      {
        title: 'Opérations',
        items: [
          { label: 'Importation', text: 'Importer des fichiers… ouvre l’importation intelligente (détection automatique du format) dans sa fenêtre ; l’import OPNsense récupère les certificats d’un pare-feu, sa connexion testée d’abord' },
          { label: 'Exportation', text: 'Télécharger des bundles de certificats par type de ressource au format PEM ou P7B en lignes avec leur bouton Télécharger' },
          { label: 'Actions en masse', text: 'Sélectionner un type de ressource et effectuer des opérations par lots sur plusieurs éléments' },
        ]
      },
      {
        title: 'Actions en masse',
        items: [
          { label: 'Certificats', text: 'Révoquer, renouveler, supprimer ou exporter, filtrer par statut et AC émettrice' },
          { label: 'AC', text: 'Supprimer ou exporter des autorités de certification' },
          { label: 'CSR', text: 'Signer avec une AC ou supprimer les requêtes en attente' },
          { label: 'Modèles', text: 'Supprimer des modèles de certificats' },
          { label: 'Utilisateurs', text: 'Supprimer des comptes utilisateurs' },
        ]
      },
    ],
    tips: [
      'Utilisez les puces de ressources pour basculer rapidement entre les types de ressources',
      'La recherche et les filtres intégrés (Statut, AC) permettent d’affiner les éléments sans quitter la barre d’outils',
      'Sélection montre les éléments cochés seuls, de toutes les pages, pour les vérifier ou les décocher avant l’action',
      'La révocation, le renouvellement, la signature et la suppression demandent une confirmation avant de s’exécuter ; un export démarre aussitôt',
    ],
    warnings: [
      'La suppression en masse est irréversible : créez toujours une sauvegarde d’abord',
      'La révocation en masse publiera des CRL mises à jour pour toutes les AC concernées',
    ],
  },
  helpGuides: {
    title: 'Opérations',
    content: `
## Vue d’ensemble

Opérations en masse et gestion des données. Effectuez des actions par lots sur plusieurs ressources simultanément.

## Onglet Importation

**Importer des fichiers…** ouvre l’assistant d’importation intelligente dans sa fenêtre. En dessous, l’intégration OPNsense : connexion, test de la connexion, choix des éléments trouvés et import.

## Onglet Exportation

Exportation en masse des certificats et des AC.

## Actions en masse

Effectuez des opérations par lots sur plusieurs ressources à la fois.

### Comment ça fonctionne
1. Sélectionnez le **type de ressource** (Certificats, AC, CSR, Modèles, Utilisateurs)
2. Cochez les éléments dans le tableau ; **Sélection** montre les éléments cochés seuls, de toutes les pages
3. Choisissez l'**action** à effectuer
4. Confirmez et exécutez

### Actions disponibles par ressource

#### Certificats
- **Révocation en masse** : Révoquer plusieurs certificats à la fois
- **Renouvellement en masse** : Renouveler plusieurs certificats
- **Exportation en masse** : Télécharger les certificats sélectionnés en bundle
- **Suppression en masse** : Supprimer définitivement les certificats sélectionnés

#### AC
- **Exportation en masse** : Télécharger les AC sélectionnées
- **Suppression en masse** : Supprimer les AC sélectionnées (ne doivent pas avoir d’enfants)

#### CSR
- **Signature en masse** : Signer plusieurs CSR avec une AC sélectionnée
- **Suppression en masse** : Supprimer les CSR sélectionnées

#### Modèles
- **Suppression en masse** : Supprimer les modèles sélectionnés

#### Utilisateurs
- **Suppression en masse** : Supprimer définitivement les utilisateurs sélectionnés

> ⚠ Les opérations en masse sont irréversibles. Créez toujours une sauvegarde avant d’effectuer des suppressions ou révocations en masse.

> 💡 Utilisez la recherche et les filtres au-dessus du tableau pour trouver rapidement des éléments spécifiques.
`
  }
}
