export default {
  helpContent: {
    title: 'Certificats utilisateur',
    subtitle: 'Gérer les certificats clients mTLS',
    overview: 'Gestion dédiée des certificats clients mTLS enrôlés depuis la page Compte. Consultez, exportez, révoquez et supprimez les certificats émis aux utilisateurs pour l’authentification TLS mutuelle.',
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
          { label: 'Exporter', text: 'Dans le détail du certificat : PEM, DER, PKCS#7, PKCS#12 ou JKS, la clé privée seulement si elle est cochée et permise' },
          { label: 'Révoquer', text: 'Dans le menu ⋯ du détail : révoquer avec un motif, le certificat apparaîtra dans la CRL' },
          { label: 'Supprimer', text: 'Dans le menu ⋯ du détail : retirer le certificat et son association utilisateur de UCM' },
          { label: 'Exporter la liste', text: 'Tous les certificats que gardent la recherche et le filtre d’état, en CSV ou JSON (10 000 au plus)' },
        ]
      },
      {
        title: 'Permissions',
        items: [
          { label: 'Viewers', text: 'Ne voient que leurs propres certificats' },
          { label: 'Operators', text: 'Peuvent consulter, exporter, révoquer et supprimer tous les certificats utilisateur ; exporter la clé privée du certificat d’un autre utilisateur exige read:private_keys, que ce rôle n’a pas' },
          { label: 'Admins', text: 'Accès complet, clés privées incluses' },
          { label: 'Auditors', text: 'Peuvent consulter et exporter les certificats, sans leur clé privée' },
        ]
      },
    ],
    tips: [
      'Enrôlez de nouveaux certificats mTLS depuis Mon compte → Sécurité',
      'Les certificats sont stockés et gérés par UCM comme n’importe quel autre certificat',
      'Les puces d’état au-dessus de la liste comptent et filtrent les certificats Valides, À renouveler, Expirés et Révoqués',
      'Cliquez sur un nom pour ouvrir son détail sous la liste ; Inspecter le certificat ouvre le certificat lui-même dans la page Certificats',
    ],
    warnings: [
      'Révoquer un certificat utilisateur empêche immédiatement la connexion mTLS avec ce certificat',
      'La suppression retire le certificat définitivement : il ne peut pas être récupéré',
    ],
  },
  helpGuides: {
    title: 'Certificats utilisateur',
    content: `
## Vue d’ensemble

La page Certificats utilisateur gère les certificats clients mTLS enrôlés depuis **Mon compte → Sécurité**, section **Certificats clients (mTLS)**. Contrairement aux certificats classiques, ceux-ci sont spécifiquement liés à des comptes utilisateur pour l’authentification TLS mutuelle.

Les certificats présents ici sont entièrement gérés par UCM : ils sont stockés en base de données avec leurs clés privées et peuvent être exportés, révoqués ou supprimés à tout moment.

## Enrôler un certificat

1. Allez dans **Mon compte → Sécurité**, section **Certificats clients (mTLS)**
2. Cliquez sur **Ajouter un certificat**, gardez **Générer** et cliquez sur **Générer le certificat**
3. Le système génère une paire de clés et émet un certificat client signé par votre AC mTLS
4. Le certificat apparaît sur cette page et peut être utilisé pour la connexion mTLS

## Statut du certificat

- **Valide** : Dans sa période de validité et non révoqué
- **Expire bientôt** : Expirera dans les 30 jours
- **Expiré** : Au-delà de la date « Not After »
- **Révoqué** : Explicitement révoqué, publié dans la CRL

## Exporter un certificat

1. Cliquez sur le nom du certificat : son détail s’ouvre sous la liste
2. Cliquez sur **Exporter** et choisissez le format :
   - **PEM** : Certificat, avec la chaîne d’AC et la clé privée si elle est cochée, au format texte
   - **PKCS#12** : Archive binaire, protégée par mot de passe (8 caractères minimum)
3. Cliquez sur **Télécharger**

**Exporter la liste**, dans l’en-tête de la page, enregistre tous les certificats que gardent la recherche et le filtre d’état, en CSV ou JSON.

Le fichier exporté peut être importé dans des navigateurs, des systèmes d’exploitation ou des clients API pour l’authentification mTLS.

> ⚠ Le mot de passe PKCS#12 doit comporter au moins 8 caractères.

## Révoquer un certificat

1. Ouvrez le certificat, puis son menu **⋯** → **Révoquer**
2. Choisissez un motif de révocation :
   - Key Compromise
   - Affiliation Changed
   - Superseded
   - Cessation of Operation
   - Unspecified
3. Confirmez la révocation

> ⚠ La révocation d’un certificat empêche immédiatement la connexion mTLS avec ce certificat. La révocation est définitive.

## Supprimer un certificat

La suppression, dans le menu **⋯** du détail du certificat, retire à la fois le certificat et l’association utilisateur-certificat. Seuls les admins et les operators peuvent supprimer.

> ⚠ La suppression est définitive et ne peut pas être annulée.

## Permissions

| Rôle | Consultation | Export | Révocation | Suppression |
|------|--------------|--------|------------|-------------|
| Admin | Tous | Tous | Tous | Tous |
| Operator | Tous | Tous (la clé privée d’un autre utilisateur exige read:private_keys) | Tous | Tous |
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
