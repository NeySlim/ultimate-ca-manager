export default {
  helpContent: {
    title: 'Vue d\'ensemble',
    subtitle: 'Ce qui demande une action et l\'état de la PKI',
    overview: 'Six cartes indépendantes sur les données en direct de votre PKI. Chaque carte se charge seule et affiche son propre état de chargement, de vide, d\'erreur ou d\'autorisation manquante. Chaque compteur qui a une liste ouvre la liste des certificats filtrée sur exactement les certificats qu\'il compte.',
    sections: [
      {
        title: 'Cartes',
        items: [
          { label: 'À traiter', text: 'Les six éléments les plus urgents, critiques d\'abord, chacun renvoyant à son enregistrement ; un niveau replié donne le total par type, et les quatre types de renouvellement ouvrent la liste des certificats' },
          { label: 'Santé de l\'automatisation', text: 'Par protocole (ACME, SCEP, EST), les succès et échecs du jour, et l\'état du planificateur' },
          { label: 'Hiérarchie', text: 'Les autorités sous forme d\'arbre sous leur parente, avec l\'état CRL et OCSP, une marque hors ligne ou signée croisée, et les certificats que chacune a émis en 7 jours ; chaque autorité ouvre sa page' },
          { label: 'Horizon d\'expiration', text: 'Les compteurs d\'expirants et d\'expirés, chacun ouvrant sa liste, et les cinq prochains certificats à expirer' },
          { label: 'Conformité', text: 'Les certificats actifs par algorithme de clé et par faiblesse (RSA sous 3072 bits, hachage de signature faible, certificats serveur de plus de 398 jours, chaîne incomplète, sans clé privée) ; chaque compteur ouvre la liste correspondante' },
          { label: 'Dernières opérations', text: 'Les cinq opérations les plus récentes ; avec la permission d\'audit, un lien ouvre toute la piste' },
        ]
      },
    ],
    tips: [
      'Choisissez le préréglage Opérateur, Responsable ou Toutes les cartes dans l\'en-tête pour définir les cartes affichées',
      'La disposition est enregistrée avec votre compte et vous suit d\'un navigateur à l\'autre',
      'Dans la liste des certificats, les filtres venant de la vue d\'ensemble apparaissent sous forme de puces ; retirez-en une avec sa croix',
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
