export default {
  helpContent: {
    title: 'Magasin de confiance',
    subtitle: 'Gérer les certificats de confiance',
    overview: 'Importez et gérez les certificats CA racines et intermédiaires de confiance. Le magasin de confiance est utilisé pour la validation de chaîne et peut être synchronisé avec le magasin de confiance du système d\'exploitation.',
    sections: [
      {
        title: 'Types de certificats',
        definitions: [
          { term: 'CA racine', description: 'Ancre de confiance auto-signée de niveau supérieur' },
          { term: 'Intermédiaire', description: 'Certificat CA signé par une racine ou un autre intermédiaire' },
          { term: 'Authentification client', description: 'Certificat utilisé pour l\'authentification client (mTLS)' },
          { term: 'Signature de code', description: 'Certificat utilisé pour la vérification de signature de code' },
          { term: 'Personnalisé', description: 'Certificat de confiance catégorisé manuellement' },
        ]
      },
      {
        title: 'Actions',
        items: [
          { label: 'Importer un fichier', text: 'Téléverser des fichiers de certificat PEM, DER ou PKCS#7' },
          { label: 'Importer depuis une URL', text: 'Récupérer un certificat depuis une URL distante' },
          { label: 'Ajouter un PEM', text: 'Coller directement du texte de certificat encodé en PEM' },
          { label: 'Synchroniser depuis le système', text: 'Importer les CA de confiance du système d\'exploitation dans UCM' },
          { label: 'Exporter', text: 'Télécharger les certificats de confiance individuellement' },
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

Le magasin de confiance gère les certificats CA de confiance utilisés pour la validation de chaîne. Importez des CA racines et intermédiaires depuis des sources externes ou synchronisez avec le magasin de confiance du système d'exploitation.

## Catégories de certificats

- **CA racine** — Ancres de confiance auto-signées
- **Intermédiaire** — CA signées par une racine ou d'autres intermédiaires
- **Authentification client** — Certificats pour l'authentification client mTLS
- **Signature de code** — Certificats pour la vérification de signature de code
- **Personnalisé** — Certificats catégorisés manuellement

## Importer des certificats

### Depuis un fichier
Téléversez des fichiers de certificat dans ces formats :
- **PEM** — Encodé en Base64 (simple ou groupé)
- **DER** — Format binaire
- **PKCS#7 (P7B)** — Chaîne de certificats

### Depuis une URL
Récupérez un certificat depuis un point de terminaison HTTPS distant. UCM télécharge et importe la chaîne de certificats du serveur.

### Coller du PEM
Collez du texte de certificat encodé en PEM directement dans la zone de texte.

### Synchroniser depuis le système
Importez toutes les CA de confiance du magasin de confiance du système d'exploitation. Cela remplit UCM avec les mêmes CA racines approuvées par le système d'exploitation (par ex. le bundle CA de Mozilla sous Linux).

> 💡 La synchronisation depuis le système est un import ponctuel. Les modifications du magasin de confiance du système d'exploitation ne sont pas automatiquement reflétées.

## Gérer les entrées

- **Filtrer par usage** — Restreindre la liste par catégorie de certificat
- **Rechercher** — Trouver des certificats par nom de sujet
- **Exporter** — Télécharger des certificats individuels au format PEM
- **Supprimer** — Retirer un certificat du magasin de confiance

## Cas d'utilisation

### Validation de chaîne
Lors de la vérification d'une chaîne de certificats, UCM consulte le magasin de confiance pour les CA racines reconnues.

### mTLS
Les certificats client présentés lors de l'authentification TLS mutuel sont validés contre le magasin de confiance.

### ACME
Lorsque UCM agit comme client ACME (Let's Encrypt), le magasin de confiance est utilisé pour vérifier le certificat du CA ACME.
`
  }
}
