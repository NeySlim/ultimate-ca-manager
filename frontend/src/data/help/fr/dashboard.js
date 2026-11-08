export default {
  helpContent: {
    title: 'Tableau de bord',
    subtitle: 'Vue d\'ensemble et surveillance du système',
    overview: 'Vue d\'ensemble en temps réel de votre infrastructure PKI. Les widgets affichent l\'état des certificats, les alertes d\'expiration, la santé du système et l\'activité récente. La disposition est entièrement personnalisable par glisser-déposer.',
    sections: [
      {
        title: 'Widgets',
        items: [
          { label: 'Statistiques', text: 'Total des certificats (expirés et révoqués inclus), des CA, des CSR en attente et des comptes ACME, plus les certificats SSH lorsqu\'une CA SSH existe' },
          { label: 'Activité des certificats', text: 'Certificats émis, révoqués et expirés par jour sur la période choisie' },
          { label: 'Distribution des statuts', text: 'Diagramme circulaire : valide / expirant / expiré / révoqué' },
          { label: 'Prochaine expiration', text: 'Les six certificats valides qui expirent le plus tôt, quelle que soit leur date ; le signeur TSA dédié configuré est signalé par une pastille « TSA signer » (v2.218)' },
          { label: 'État du système', text: 'Santé des services : ACME, SCEP, EST, OCSP, CRL/CDP, TSA (v2.218), renouvellement automatique, SMTP et webhooks. Les badges affichent un état d\'avertissement ambre distinct (signeur TSA proche de l\'expiration, SMTP configuré mais désactivé) et leur message de statut au survol' },
          { label: 'Activité récente', text: 'Dernières opérations sur l\'ensemble du système avec read:audit ; sans cette permission, vos propres événements uniquement' },
          { label: 'Certificats récents', text: 'Certificats récemment émis ou importés' },
          { label: 'Autorités de certification', text: 'Dernières CA, chacune marquée Racine ou Sub' },
          { label: 'Comptes ACME', text: 'Comptes clients ACME enregistrés' },
          { label: 'Expiration du magasin de confiance', text: 'Certificats de confiance qui expirent le plus tôt' },
        ]
      },
    ],
    tips: [
      'Cliquez sur Modifier la disposition dans l\'en-tête, puis glissez les widgets pour les réorganiser',
      'Cliquez sur le bouton Personnaliser (icône de curseurs) dans l\'en-tête, puis sur l\'œil à côté d\'un widget pour l\'afficher ou le masquer',
      'Le tableau de bord se met à jour en temps réel via WebSocket : aucune actualisation manuelle nécessaire',
      'La disposition est sauvegardée dans ce navigateur, pour tous les comptes qui s\'y connectent',
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
