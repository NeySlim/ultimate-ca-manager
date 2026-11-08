export default {
  helpContent: {
    title: 'Magasin de confiance',
    subtitle: 'Gérer les certificats de confiance',
    overview: 'Conservez les certificats CA racines et intermédiaires de confiance. La vue de chaîne d\'un certificat et ses exports complètent la chaîne avec un certificat du magasin de confiance dont le sujet correspond au nom de l\'émetteur. Le magasin peut être rempli depuis le magasin de confiance du système d\'exploitation ou depuis les CA que UCM gère.',
    sections: [
      {
        title: 'Types de certificats',
        definitions: [
          { term: 'CA racine', description: 'Ancre de confiance auto-signée de niveau supérieur' },
          { term: 'Intermédiaire', description: 'Certificat CA signé par une racine ou un autre intermédiaire' },
          { term: 'Système', description: 'Importé depuis le magasin de confiance du système d\'exploitation' },
          { term: 'Signature de code', description: 'Certificat utilisé pour la vérification de signature de code' },
          { term: 'E-mail', description: 'Certificat utilisé pour S/MIME' },
          { term: 'Personnalisé', description: 'Certificat de confiance catégorisé manuellement' },
        ]
      },
      {
        title: 'Actions',
        items: [
          { label: 'Ajouter', text: 'Ajouter les certificats des CA que UCM gère. Un certificat externe s\'ajoute via l\'API (POST /api/v2/truststore avec le PEM, ou /api/v2/truststore/import avec un fichier PEM ou DER)' },
          { label: 'Synchroniser depuis le système', text: 'Importer les CA de confiance du système d\'exploitation dans UCM, jusqu\'au nombre choisi (500 par défaut, 1000 au maximum)' },
          { label: 'Exporter', text: 'Télécharger les certificats de confiance individuellement' },
          { label: 'Supprimer la sélection', text: 'Sélectionnez plusieurs certificats et supprimez-les ensemble, par exemple les CA système filtrées comme expirées ; seules les lignes affichées par les filtres actuels sont supprimées' },
        ]
      },
    ],
    tips: [
      'Utilisez « Synchroniser depuis le système » pour remplir rapidement le magasin de confiance avec les CA du système d\'exploitation',
      'Filtrez par usage pour vous concentrer sur des catégories de certificats spécifiques',
    ],
  },
  helpGuides: {
    title: 'Magasin de confiance',
    content: `
## Vue d'ensemble

Le magasin de confiance conserve les certificats CA de confiance. Remplissez-le depuis les CA que UCM gère ou depuis le magasin de confiance du système d'exploitation.

## Catégories de certificats

- **CA racine** : Ancres de confiance auto-signées
- **Intermédiaire** : CA signées par une racine ou d'autres intermédiaires
- **Système** : Importés depuis le magasin de confiance du système d'exploitation
- **Signature de code** : Certificats pour la vérification de signature de code
- **E-mail** : Certificats pour S/MIME
- **Personnalisé** : Certificats catégorisés manuellement

## Ajouter des certificats

### Depuis les CA gérées
**Ajouter** liste les CA que UCM gère : sélectionnez celles à approuver.

### Certificats externes
La page n'a pas de formulaire de téléversement pour un certificat extérieur à UCM. Ajoutez-le via l'API : \`POST /api/v2/truststore\` avec son PEM, ou \`POST /api/v2/truststore/import\` avec un fichier PEM ou DER.

### Synchroniser depuis le système
Importez les CA de confiance du magasin de confiance du système d'exploitation (par ex. le bundle CA de Mozilla sous Linux), jusqu'au nombre choisi : 500 par défaut, 1000 au maximum.

> 💡 La synchronisation depuis le système est un import ponctuel. Les modifications du magasin de confiance du système d'exploitation ne sont pas automatiquement reflétées.

## Gérer les entrées

- **Filtrer par usage** : Restreindre la liste par catégorie de certificat
- **Rechercher** : Trouver des certificats par nom de sujet
- **Exporter** : Télécharger des certificats individuels au format PEM
- **Supprimer** : Retirer un certificat du magasin de confiance
- **Supprimer la sélection** : Sélectionnez plusieurs certificats et supprimez-les ensemble, par exemple les CA système filtrées comme expirées ; seules les lignes affichées par les filtres actuels sont supprimées

## Cas d'utilisation

### Chaînes
La vue de chaîne d'un certificat, et ses exports avec la chaîne, prennent un certificat du magasin de confiance dont le sujet correspond au nom de l'émetteur pour compléter la chaîne. Aucune signature n'est vérifiée contre le magasin de confiance.

Le magasin de confiance ne joue aucun rôle dans l'authentification client mTLS (qui utilise la CA de confiance choisie sous Paramètres › Sécurité) ni dans la connexion du client ACME à sa CA.
`
  }
}
