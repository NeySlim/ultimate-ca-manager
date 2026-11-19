export default {
  helpContent: {
    title: 'Certificats utilisateur',
    subtitle: 'Gérer les certificats clients mTLS',
    overview: 'Gestion dédiée des certificats clients mTLS enrôlés depuis la page Compte. Consultez, exportez, révoquez et supprimez les certificats émis aux utilisateurs pour l\'authentification TLS mutuelle.',
    sections: [
      {
        title: 'Statut du certificat',
        definitions: [
          { term: 'Valide', description: 'Dans sa période de validité et non révoqué' },
          { term: 'Expire bientôt', description: 'Expirera dans les 30 jours' },
          { term: 'Expiré', description: 'Au-delà de la date « Not After »' },
          { term: 'Révoqué', description: 'Explicitement révoqué par un opérateur ou un administrateur' },
        ]
      },
      {
        title: 'Actions',
        items: [
          { label: 'Exporter', text: 'Télécharger au format PEM (avec clé et chaîne) ou PKCS#12 (protégé par mot de passe)' },
          { label: 'Révoquer', text: 'Révoquer avec un motif, le certificat apparaîtra dans la CRL' },
          { label: 'Supprimer', text: 'Retirer le certificat et son association utilisateur de UCM' },
        ]
      },
      {
        title: 'Permissions',
        items: [
          { label: 'Viewers', text: 'Ne voient que leurs propres certificats' },
          { label: 'Operators', text: 'Peuvent consulter, exporter, révoquer et supprimer tous les certificats utilisateur ; exporter la clé privée du certificat d\'un autre utilisateur exige read:private_keys, que ce rôle n\'a pas' },
          { label: 'Admins', text: 'Accès complet, clés privées incluses' },
          { label: 'Auditors', text: 'Peuvent consulter et exporter les certificats, sans leur clé privée' },
        ]
      },
    ],
    tips: [
      'Enrôlez de nouveaux certificats mTLS depuis Compte → onglet mTLS',
      'Les certificats sont stockés et gérés par UCM comme n\'importe quel autre certificat',
      'Utilisez la barre de statistiques pour filtrer rapidement par statut',
      'Cliquez sur une ligne pour afficher les détails complets du certificat dans une fenêtre flottante',
    ],
    warnings: [
      'Révoquer un certificat utilisateur empêche immédiatement la connexion mTLS avec ce certificat',
      'La suppression retire le certificat définitivement : il ne peut pas être récupéré',
    ],
  },
  helpGuides: {
    title: 'Certificats utilisateur',
    content: `
## Vue d'ensemble

La page Certificats utilisateur gère les certificats clients mTLS enrôlés via l'onglet **Compte → mTLS**. Contrairement aux certificats classiques, ceux-ci sont spécifiquement liés à des comptes utilisateur pour l'authentification TLS mutuelle.

Les certificats présents ici sont entièrement gérés par UCM : ils sont stockés en base de données avec leurs clés privées et peuvent être exportés, révoqués ou supprimés à tout moment.

## Enrôler un certificat

1. Allez dans **Compte → onglet mTLS**
2. Cliquez sur **Enrôler un certificat**
3. Le système génère une paire de clés et émet un certificat client signé par votre CA mTLS
4. Le certificat apparaît sur cette page et peut être utilisé pour la connexion mTLS

## Statut du certificat

- **Valide** : Dans sa période de validité et non révoqué
- **Expire bientôt** : Expirera dans les 30 jours
- **Expiré** : Au-delà de la date « Not After »
- **Révoqué** : Explicitement révoqué, publié dans la CRL

## Exporter un certificat

1. Sélectionnez un certificat → **Exporter**
2. Choisissez le format :
   - **PEM** : Certificat + clé privée + chaîne de CA au format texte
   - **PKCS#12** : Archive binaire, protégée par mot de passe (8 caractères minimum)
3. Cliquez sur **Télécharger**

Le fichier exporté peut être importé dans des navigateurs, des systèmes d'exploitation ou des clients API pour l'authentification mTLS.

> ⚠ Le mot de passe PKCS#12 doit comporter au moins 8 caractères.

## Révoquer un certificat

1. Sélectionnez un certificat → **Révoquer**
2. Choisissez un motif de révocation :
   - Key Compromise
   - Affiliation Changed
   - Superseded
   - Cessation of Operation
   - Unspecified
3. Confirmez la révocation

> ⚠ La révocation d'un certificat empêche immédiatement la connexion mTLS avec ce certificat. La révocation est définitive.

## Supprimer un certificat

La suppression retire à la fois le certificat et l'association utilisateur-certificat. Seuls les admins et les operators peuvent supprimer.

> ⚠ La suppression est définitive et ne peut pas être annulée.

## Permissions

| Rôle | Consultation | Export | Révocation | Suppression |
|------|--------------|--------|------------|-------------|
| Admin | Tous | Tous | Tous | Tous |
| Operator | Tous | Tous (la clé privée d'un autre utilisateur exige read:private_keys) | Tous | Tous |
| Auditor | Tous | Certificat seul, sans clé privée | ✗ | ✗ |
| Viewer | Les siens | Les siens | ✗ | ✗ |

### Permissions requises

- **read:user_certificates** : Consulter la liste et les détails des certificats
- **write:user_certificates** : Révoquer des certificats
- **delete:user_certificates** : Supprimer des certificats

> 💡 Enrôlez les nouveaux certificats mTLS depuis la page Compte. Cette page sert à gérer les certificats existants.
`
  }
}
