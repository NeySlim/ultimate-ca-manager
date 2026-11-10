export default {
  helpContent: {
    title: 'Overview',
    subtitle: 'What needs action, and the state of the PKI',
    overview: 'Six independent cards over the live data of your PKI. Each card loads on its own and shows its own loading, empty, error or missing-permission state. Every counter that has a list opens the certificate list filtered to exactly the certificates it counts.',
    sections: [
      {
        title: 'Cards',
        items: [
          { label: 'To handle', text: 'The six most urgent items, critical first, each linking to its record; a folded tier gives the total per kind, and the four renewal kinds open the certificate list' },
          { label: 'Automation health', text: 'Per protocol (ACME, SCEP, EST) the daily successes and failures, and the scheduler state' },
          { label: 'Hierarchy', text: 'The authorities as a tree under their parent, with CRL and OCSP state, an offline or cross-signed mark, and the certificates each issued over 7 days; each authority opens its page' },
          { label: 'Expiry horizon', text: 'The expiring and expired counters, each opening its list, and the five certificates that expire next' },
          { label: 'Compliance', text: 'Live certificates by key algorithm and weakness (RSA below 3072 bits, weak signature hash, server certificates over 398 days, incomplete chain, no private key); each counter opens the matching list' },
          { label: 'Latest operations', text: 'The five most recent operations; with the audit permission, a link opens the whole trail' },
        ]
      },
    ],
    tips: [
      'Pick the Operator, Manager or All cards preset in the header to choose which cards are shown',
      'The layout is saved with your account and follows you across browsers',
      'On the certificate list, filters coming from the overview appear as chips; remove one with its x',
    ],
  },
  helpGuides: {
    title: 'Tableau de bord',
    content: `
## Vue d'ensemble

Le tableau de bord est votre centre de surveillance principal. Il affiche des métriques en temps réel, des graphiques et des alertes sur l'ensemble de votre infrastructure PKI à travers des widgets personnalisables.

## Widgets

### Carte de statistiques
Affiche ces compteurs :
- **Certificats** : tous les certificats, expirés et révoqués inclus
- **CA** : Autorités de certification racines et intermédiaires
- **CSR** : Demandes de signature de certificat en attente de signature
- **ACME** : comptes ACME enregistrés
- **Certificats SSH** : affiché lorsqu'une CA SSH existe

### Activité des certificats
Un graphique en aires des certificats émis, révoqués et expirés par jour sur la période choisie. Survolez les points de données pour voir les comptages exacts.

### Distribution des statuts
Diagramme circulaire montrant la répartition des états des certificats :
- **Valide** : Dans la période de validité et non révoqué
- **Expirant** : Expire dans les 30 jours
- **Expiré** : Après la date « Not After »
- **Révoqué** : Explicitement révoqué

### Prochaine expiration
Liste les six certificats valides qui expirent le plus tôt, quelle que soit leur date. Cliquez sur n'importe quel certificat pour accéder à ses détails.

### État du système
Affiche la santé des services UCM :
- Serveur ACME (activé/désactivé)
- Serveur SCEP
- Protocole EST (activé/désactivé, CA assignée)
- Auto-régénération CRL avec nombre de CDP
- Répondeur OCSP
- TSA, SMTP et webhooks
- Statut du renouvellement automatique

Le panneau Santé du système affiche aussi la connexion WebSocket, la base de données, l'API et l'heure de la dernière actualisation.

### Activité récente
Un flux en direct des dernières opérations : émission de certificats, révocations, importations, connexions utilisateurs. Se met à jour en temps réel via WebSocket.

### Autorités de certification
Vue rapide des dernières CA, chacune marquée Racine ou Sub.

### Expiration du magasin de confiance
Certificats de confiance qui expirent le plus tôt.

### Comptes ACME
Liste les comptes clients ACME enregistrés et leur nombre de commandes.

## Personnalisation

### Réorganiser les widgets
Cliquez sur **Modifier la disposition** dans l'en-tête de la page, puis glissez n'importe quel widget par son en-tête pour le repositionner. La disposition utilise une grille responsive qui s'adapte à la taille de votre écran.

### Afficher/Masquer les widgets
Cliquez sur **Personnaliser** (icône de curseurs) dans l'en-tête de la page, puis sur l'œil à côté d'un widget pour basculer sa visibilité. Les widgets masqués sont mémorisés entre les sessions.

### Persistance de la disposition
Votre disposition est sauvegardée dans le navigateur, pas dans votre compte : tous les comptes qui se connectent depuis le même profil de navigateur la partagent, et un autre navigateur repart de la disposition par défaut.

## Mises à jour en temps réel
Le tableau de bord reçoit des mises à jour en direct via WebSocket. Aucune actualisation manuelle n'est nécessaire : les nouveaux certificats, changements de statut et entrées d'activité apparaissent automatiquement.

> 💡 Le point vert dans la barre latérale indique une connexion WebSocket active et disparaît quand elle tombe. Les données s'actualiseront à la reconnexion.
`
  }
}
