export default {
  helpContent: {
    title: 'Vue d\'ensemble',
    subtitle: 'Ce qui demande une action et l\'état de la PKI',
    overview: 'Un bandeau de quatre chiffres, puis des cartes indépendantes sur les données en direct de votre PKI. Chaque carte se charge seule et affiche son propre état de chargement, de vide, d\'erreur ou d\'autorisation manquante. Chaque chiffre qui a une liste ouvre la liste des certificats filtrée sur exactement les certificats qu\'il compte.',
    sections: [
      {
        title: 'Cartes',
        items: [
          { label: 'Chiffres', text: 'Les certificats (avec les autorités et, quand il y en a, les demandes en attente et les certificats SSH), les éléments à traiter, les certificats expirés, et les échecs ACME, SCEP et EST du jour UTC en cours' },
          { label: 'À traiter', text: 'Les six interventions les plus urgentes, critiques d\'abord, chacune sur deux lignes (le nom et son type, puis la cause) avec son délai et la date exacte ; un bouton là où UCM peut agir (Renouveler, Relancer, Publier maintenant), sinon un lien vers l\'enregistrement. Des pastilles filtrent par type avec leurs totaux, et ce qui reste seulement à surveiller est replié à part (avec le droit de lire le magasin de confiance, les certificats du magasin de confiance qui expirent dans 90 jours ou sont expirés sont aussi listés)' },
          { label: 'Santé de l\'automatisation', text: 'Par protocole (ACME, SCEP, EST), les succès et échecs du jour et de la période, la dernière opération et une courbe quand il y a quelque chose à tracer ; puis l\'état du planificateur, le signataire TSA quand la TSA est activée (un avertissement tant que le certificat de l\'AC signe) et, avec le droit de lire les paramètres, si l\'email, les webhooks et le renouvellement automatique sont configurés' },
          { label: 'Hiérarchie', text: 'Dix autorités au plus, les arbres qui ont le plus émis d\'abord, chacune sous sa parente avec l\'état CRL et OCSP, une marque hors ligne ou signée croisée, et les certificats qu\'elle a émis en 7 jours quand il y en a ; chaque autorité ouvre sa page et un lien les ouvre toutes' },
          { label: 'Horizon d\'expiration', text: 'Les compteurs d\'expirants et d\'expirés, chacun ouvrant sa liste, et les six prochains certificats à expirer, chacun avec les jours restants et une barre pour la part de validité déjà écoulée' },
          { label: 'Activité des certificats', text: 'Les certificats émis, révoqués et expirés par jour sur 7, 15 ou 30 jours, en courbes avec leurs totaux ; les flèches gauche et droite lisent le graphique jour par jour' },
          { label: 'Répartition des états', text: 'Les certificats valides, expirant bientôt, expirés et révoqués en anneau, avec leurs nombres et leurs parts ; chaque ligne ouvre sa liste' },
          { label: 'Conformité', text: 'Les certificats actifs par algorithme de clé et par faiblesse (RSA sous 3072 bits, hachage de signature faible, certificats serveur de plus de 398 jours, chaîne incomplète, sans clé privée) ; chaque chiffre qui a une liste l\'ouvre' },
          { label: 'Dernières opérations', text: 'Les six opérations les plus récentes avec leur délai ; avec la permission d\'audit, un lien ouvre toute la piste' },
        ]
      },
    ],
    tips: [
      'Choisissez le préréglage Opérateur ou Responsable dans l\'en-tête, ou ouvrez Cartes pour afficher, masquer et réordonner les cartes',
      'Faites glisser une carte par sa poignée pour la déplacer, ou placez le focus sur la poignée et utilisez les flèches ; la disposition est enregistrée avec votre compte et vous suit d\'un navigateur à l\'autre',
      'Dans la liste des certificats, les filtres venant de la vue d\'ensemble apparaissent sous forme de puces ; retirez-en une avec sa croix',
    ],
  },
  helpGuides: {
    title: 'Vue d\'ensemble',
    content: `
## Aperçu

La Vue d'ensemble est la page d'accueil : un bandeau de quatre chiffres, puis des cartes indépendantes sur les données en direct de votre PKI. Chaque carte se charge seule et affiche son propre état de chargement, de vide, d'erreur ou d'autorisation manquante.

## Chiffres
Quatre chiffres ouvrent la page : les certificats (avec le nombre d'autorités et, quand il y en a, les demandes en attente et les certificats SSH), les éléments à traiter (répartis entre ce qui est à faire et ce qui est à surveiller), les certificats expirés (avec ceux qui expirent bientôt), et les échecs ACME, SCEP et EST du jour UTC en cours. Certificats et Expirés ouvrent la liste des certificats ; les deux autres mènent à leur carte quand elle est affichée. Un chiffre que le serveur n'a pas donné se lit comme un tiret.

## Cartes

### À traiter
Les six interventions les plus urgentes, critiques d'abord, puis par échéance ; **Afficher les autres** liste le reste. Chaque ligne a deux niveaux : le nom, qui ouvre l'enregistrement, avec son type, puis la cause. À droite, le délai (« dans 12 jours », « en retard de 6 mois ») avec la date exacte dessous, et un bouton : **Renouveler** pour un renouvellement manuel, **Relancer** pour un renouvellement que le client ACME a manqué, **Publier maintenant** pour une CRL à publier ou manquante, chacun avec la permission d'écriture correspondante ; toute autre ligne, ou une ligne sans cette permission, porte un lien vers son enregistrement. Les pastilles au-dessus de la liste filtrent par type et portent le total de chacun. Ce qui ne demande rien aujourd'hui (certificats que leur client renouvelle, autorités et ancres de confiance encore loin de l'expiration) est compté sur une ligne à part, **Afficher** la déplie ; un élément critique n'y est jamais rangé. Avec le droit de lire le magasin de confiance, les certificats du magasin de confiance qui expirent dans 90 jours ou sont déjà expirés sont aussi listés (les expirés en critique).

### Santé de l'automatisation
Par protocole (ACME, SCEP, EST), les succès et échecs du jour UTC en cours et de la période, la dernière opération, le dernier état, et une courbe des chiffres quotidiens quand il y en a. Dessous, l'état du planificateur et, quand la TSA est activée, l'état de son signataire : un avertissement tant que le certificat de l'AC signe, ses jetons ne satisfaisant pas la RFC 3161. Avec le droit de lire les paramètres, trois tuiles de plus disent si l'email, les webhooks et le renouvellement automatique sont configurés : un réglage non configuré est une information, pas une alerte ; un email configuré mais désactivé ou incomplet, ou des webhooks sans aucun actif, sont des alertes. Une ligne sous la carte compte les lignes qui signalent un problème.

### Hiérarchie
Dix autorités au plus, quelle que soit la taille de l'installation : les arbres qui ont le plus émis en 7 jours viennent d'abord, puis les plus grands, chaque autorité sous sa parente avec l'état CRL et OCSP, une marque hors ligne ou signée croisée, et les certificats qu'elle a émis en 7 jours quand il y en a. Une autorité dont les filles ne sont pas toutes affichées dit combien il en reste en dessous. Chaque autorité ouvre sa page ; **Explorer** et **Tout voir** ouvrent la page Autorités de certification.

### Horizon d'expiration
Les compteurs d'expirants et d'expirés, chacun ouvrant sa liste, et les six prochains certificats à expirer. Chaque ligne donne les jours restants, colorés selon l'urgence (7 jours ou moins, 30 jours ou moins, au-delà), et une barre aussi longue que la part de validité déjà écoulée.

### Activité des certificats
Les certificats émis, révoqués et expirés par jour, sur 7, 15 ou 30 jours, en trois courbes avec leurs totaux sous le graphique. Pointer le graphique, ou y placer le focus et appuyer sur les flèches gauche et droite, lit un jour à la fois. Une période sans aucun événement affiche une phrase à la place d'un graphique vide.

### Répartition des états
Les certificats valides, expirant bientôt, expirés et révoqués en anneau autour de leur total. Chaque ligne donne le nombre et la part d'un état et ouvre la liste des certificats filtrée sur lui.

### Conformité
Les certificats actifs par algorithme de clé et par faiblesse : RSA sous 3072 bits, hachage de signature faible, certificats serveur de plus de 398 jours, chaîne incomplète, sans clé privée. Chaque chiffre qui a une liste l'ouvre.

### Dernières opérations
Les six opérations les plus récentes avec leur délai ; la date exacte s'affiche au survol. Une marque **En direct** s'affiche tant que le lien en direct est établi. Sans **read:audit**, vous ne voyez que vos propres événements ; avec cette permission, un lien ouvre toute la piste sur la page Journaux d'audit.

## Ouvrir une liste filtrée
Chaque chiffre qui a une liste ouvre la page Certificats filtrée sur exactement les certificats qu'il compte. Le filtre apparaît sous forme de puce au-dessus du tableau ; retirez-le avec sa croix.

## Choisir et ordonner les cartes
Choisissez le préréglage **Opérateur** ou **Responsable** dans l'en-tête de la page, ou ouvrez **Cartes** pour cocher les cartes à afficher, les monter et les descendre, ou appliquer un préréglage (**Toutes les cartes** affiche toutes les cartes dans l'ordre initial). Pour déplacer une carte sur la page même, faites-la glisser par la poignée à gauche de son titre jusqu'à la place d'une autre carte, ou placez le focus sur la poignée et appuyez sur une flèche ; le menu d'une carte la déplace ou la masque aussi. L'ordre et les cartes masquées sont enregistrés avec votre compte et vous suivent d'un navigateur à l'autre.

## Actions rapides
L'en-tête propose **Émettre** (ouvre le formulaire de certificat), **Nouvelle AC** et **Découverte réseau**, chacune affichée seulement avec la permission qu'elle demande.

## Actualisation
Les cartes se chargent à l'ouverture de la page puis se rechargent d'elles-mêmes, sans quitter la page, quand des certificats ou des AC changent, quand le lien en direct revient et quand vous revenez sur l'onglet ; le bouton d'actualisation de l'en-tête les recharge toutes d'un coup. Tant que le lien en direct est coupé, elles se rechargent une fois par minute. Une carte en erreur propose **Réessayer**. L'icône de connexion de la barre supérieure indique l'état du lien en direct, et la barre d'état en bas affiche la version et si le service répond.
`
  }
}
