export default {
  helpContent: {
    title: 'Opérations',
    subtitle: 'Actions en masse et gestion des données',
    overview: 'Effectuez des opérations en masse sur plusieurs ressources simultanément. Révoquez, renouvelez, exportez ou supprimez des certificats par lots. Gérez les CA, CSR, modèles et utilisateurs en masse.',
    sections: [
      {
        title: 'Onglets',
        items: [
          { label: 'Importation/Exportation', text: 'Identique à la page Importation & Exportation — assistant d\'importation intelligente et export en masse' },
          { label: 'OPNsense', text: 'Intégration OPNsense pour l\'importation de certificats et CA depuis le pare-feu' },
          { label: 'Actions en masse', text: 'Sélectionner plusieurs éléments et effectuer des opérations par lots' },
        ]
      },
      {
        title: 'Actions en masse disponibles',
        items: [
          { label: 'Certificats', text: 'Révoquer, renouveler, exporter ou supprimer en masse' },
          { label: 'CA', text: 'Exporter ou supprimer les CA sélectionnées' },
          { label: 'CSR', text: 'Signer en masse avec une CA sélectionnée ou supprimer' },
          { label: 'Modèles', text: 'Exporter ou supprimer les modèles sélectionnés' },
          { label: 'Utilisateurs', text: 'Désactiver ou supprimer les comptes utilisateurs sélectionnés' },
        ]
      },
    ],
    tips: [
      'Utilisez la recherche et le filtre dans le panneau de gauche pour trouver rapidement des éléments spécifiques',
      'Créez toujours une sauvegarde avant d\'effectuer des suppressions ou révocations en masse',
    ],
    warnings: [
      'Les opérations en masse sont irréversibles — vérifiez bien votre sélection avant d\'exécuter',
    ],
  },
  helpGuides: {
    title: 'Opérations',
    content: `
## Vue d'ensemble

Opérations en masse et gestion des données. Effectuez des actions par lots sur plusieurs ressources simultanément.

## Onglet Importation/Exportation

Identique à la page Importation & Exportation — assistant d'importation intelligente et fonctionnalité d'export en masse.

## Onglet OPNsense

Identique à l'intégration OPNsense de la page Importation & Exportation — connectez-vous, parcourez et importez depuis OPNsense.

## Actions en masse

Effectuez des opérations par lots sur plusieurs ressources à la fois.

### Comment ça fonctionne
1. Sélectionnez le **type de ressource** (Certificats, CA, CSR, Modèles, Utilisateurs)
2. Parcourez les éléments disponibles dans le **panneau de gauche**
3. Déplacez les éléments vers le **panneau de droite** (sélectionné) à l'aide des flèches de transfert
4. Choisissez l'**action** à effectuer
5. Confirmez et exécutez

### Actions disponibles par ressource

#### Certificats
- **Révocation en masse** — Révoquer plusieurs certificats à la fois
- **Renouvellement en masse** — Renouveler plusieurs certificats
- **Exportation en masse** — Télécharger les certificats sélectionnés en bundle
- **Suppression en masse** — Supprimer définitivement les certificats sélectionnés

#### CA
- **Exportation en masse** — Télécharger les CA sélectionnées
- **Suppression en masse** — Supprimer les CA sélectionnées (ne doivent pas avoir d'enfants)

#### CSR
- **Signature en masse** — Signer plusieurs CSR avec une CA sélectionnée
- **Suppression en masse** — Supprimer les CSR sélectionnées

#### Modèles
- **Exportation en masse** — Exporter au format JSON
- **Suppression en masse** — Supprimer les modèles sélectionnés

#### Utilisateurs
- **Désactivation en masse** — Désactiver les comptes utilisateurs sélectionnés
- **Suppression en masse** — Supprimer définitivement les utilisateurs sélectionnés

> ⚠ Les opérations en masse sont irréversibles. Créez toujours une sauvegarde avant d'effectuer des suppressions ou révocations en masse.

> 💡 Utilisez la recherche et le filtre dans le panneau de gauche pour trouver rapidement des éléments spécifiques.
`
  }
}
