export default {
  helpContent: {
    title: 'Tableau de bord',
    subtitle: 'Vue d\'ensemble et surveillance du système',
    overview: 'Vue d\'ensemble en temps réel de votre infrastructure PKI. Les widgets affichent l\'état des certificats, les alertes d\'expiration, la santé du système et l\'activité récente. La disposition est entièrement personnalisable par glisser-déposer.',
    sections: [
      {
        title: 'Widgets',
        items: [
          { label: 'Statistiques', text: 'Total des CA, certificats actifs, CSR en attente et nombre d\'expirations imminentes' },
          { label: 'Tendance des certificats', text: 'Graphique de l\'historique d\'émission dans le temps' },
          { label: 'Distribution des statuts', text: 'Diagramme circulaire : valide / expirant / expiré / révoqué' },
          { label: 'Prochaine expiration', text: 'Certificats expirant dans les 30 jours' },
          { label: 'État du système', text: 'Santé des services : ACME, SCEP, EST, OCSP, CRL/CDP, statut du renouvellement automatique' },
          { label: 'Activité récente', text: 'Dernières opérations sur l\'ensemble du système' },
          { label: 'Certificats récents', text: 'Certificats récemment émis ou importés' },
          { label: 'Autorités de certification', text: 'Liste des CA avec informations sur la chaîne' },
          { label: 'Comptes ACME', text: 'Comptes clients ACME enregistrés' },
        ]
      },
    ],
    tips: [
      'Glissez les widgets pour réorganiser la disposition de votre tableau de bord',
      'Cliquez sur l\'icône œil dans l\'en-tête pour afficher/masquer des widgets spécifiques',
      'Le tableau de bord se met à jour en temps réel via WebSocket — aucune actualisation manuelle nécessaire',
      'La disposition est sauvegardée par utilisateur et persiste entre les sessions',
    ],
  },
  helpGuides: {
    title: 'Tableau de bord',
    content: `
## Vue d'ensemble

Le tableau de bord est votre centre de surveillance principal. Il affiche des métriques en temps réel, des graphiques et des alertes sur l'ensemble de votre infrastructure PKI à travers des widgets personnalisables.

## Widgets

### Carte de statistiques
Affiche quatre compteurs clés :
- **Total des CA** — Autorités de certification racines et intermédiaires
- **Certificats actifs** — Certificats valides et non révoqués
- **CSR en attente** — Demandes de signature de certificat en attente d'approbation
- **Expiration imminente** — Certificats expirant dans les 30 jours

### Tendance des certificats
Un graphique linéaire montrant l'émission de certificats dans le temps. Survolez les points de données pour voir les comptages exacts.

### Distribution des statuts
Diagramme circulaire montrant la répartition des états des certificats :
- **Valide** — Dans la période de validité et non révoqué
- **Expirant** — Expire dans les 30 jours
- **Expiré** — Après la date « Not After »
- **Révoqué** — Explicitement révoqué

### Prochaine expiration
Liste les certificats expirant le plus tôt. Cliquez sur n'importe quel certificat pour accéder à ses détails. Configurez le seuil dans **Paramètres → Général**.

### État du système
Affiche la santé des services UCM :
- Serveur ACME (activé/désactivé)
- Serveur SCEP
- Protocole EST (activé/désactivé, CA assignée)
- Auto-régénération CRL avec nombre de CDP
- Répondeur OCSP
- Statut du renouvellement automatique
- Temps de fonctionnement du service

### Activité récente
Un flux en direct des dernières opérations : émission de certificats, révocations, importations, connexions utilisateurs. Se met à jour en temps réel via WebSocket.

### Autorités de certification
Vue rapide de toutes les CA avec leur type (racine/intermédiaire) et nombre de certificats.

### Comptes ACME
Liste les comptes clients ACME enregistrés et leur nombre de commandes.

## Personnalisation

### Réorganiser les widgets
Glissez n'importe quel widget par son en-tête pour le repositionner. La disposition utilise une grille responsive qui s'adapte à la taille de votre écran.

### Afficher/Masquer les widgets
Cliquez sur l'**icône œil** dans l'en-tête de la page pour basculer la visibilité de chaque widget. Les widgets masqués sont mémorisés entre les sessions.

### Persistance de la disposition
Votre configuration de disposition est sauvegardée par utilisateur dans le navigateur. Elle persiste entre les sessions et les appareils partageant le même profil de navigateur.

## Mises à jour en temps réel
Le tableau de bord reçoit des mises à jour en direct via WebSocket. Aucune actualisation manuelle n'est nécessaire — les nouveaux certificats, changements de statut et entrées d'activité apparaissent automatiquement.

> 💡 Si le WebSocket est déconnecté, un indicateur jaune apparaît dans la barre latérale. Les données s'actualiseront à la reconnexion.
`
  }
}
