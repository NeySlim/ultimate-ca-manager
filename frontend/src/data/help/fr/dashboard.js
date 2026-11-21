export default {
  helpContent: {
    title: 'Vue d’ensemble',
    subtitle: 'Ce qui demande une action et l’état de la PKI',
    overview: 'Un bandeau de quatre chiffres, puis les cartes de la vue d’ensemble sur les données en direct de votre PKI, dans l’ordre et la sélection que vous choisissez. Chaque carte se charge seule et affiche son propre état de chargement, de vide, d’erreur ou d’autorisation manquante. Chaque chiffre qui a une liste ouvre la liste des certificats filtrée sur exactement les certificats qu’il compte.',
    sections: [
      {
        title: 'Cartes',
        items: [
          { label: 'Chiffres', text: 'Les certificats (l’inventaire complet), les éléments à traiter (les interventions, et ceux à surveiller), les certificats expirés, et les échecs ACME, SCEP et EST du jour UTC en cours ; le deuxième affiche la carte À traiter, le dernier mène à la carte Santé de l’automatisation' },
          { label: 'Premiers pas', text: 'Sur une instance vide, un administrateur voit trois étapes au-dessus des chiffres (une AC racine, une AC émettrice, un protocole), chacune menant à son écran ; Plus tard les replie en une ligne qui garde la progression, Reprendre les rouvre' },
          { label: 'À traiter', text: 'Les interventions par urgence, critiques d’abord, six affichées et Afficher les autres pour le reste ; chaque ligne donne le nom et son type, la cause, un délai court avec la date exacte dessous, et un bouton : Renouveler, Relancer ou Publier maintenant là où UCM peut agir, sinon Examiner, Voir l’AC ou Ouvrir. Des pastilles filtrent par type avec leurs totaux, et ce qui reste seulement à surveiller est replié à part' },
          { label: 'Santé de l’automatisation', text: 'Par protocole (ACME, SCEP, EST), la dernière opération, les succès et échecs du jour et de la période, et une courbe par jour ; les échecs ACME ouvrent À traiter sur ACME. Puis le signataire TSA, le planificateur et, avec le droit de lire les paramètres, l’email, les webhooks et le renouvellement automatique, chacun avec son état' },
          { label: 'Hiérarchie', text: 'Dix autorités au plus, une colonne par racine : chaque racine avec sa marque hors ligne, sa CRL et la signature croisée, chaque autorité en dessous avec sa CRL, son OCSP et ses émissions sur 7 jours ; chaque autorité ouvre sa page, Explorer les ouvre toutes' },
          { label: 'Horizon des expirations', text: 'Les six prochains certificats à expirer, chacun avec son délai coloré selon l’urgence et une barre pour la part de validité déjà écoulée, puis les certificats valides, à renouveler, expirés et révoqués, chacun ouvrant sa liste' },
          { label: 'Conformité', text: 'Les certificats actifs par algorithme de clé, puis cinq contrôles (RSA sous 3072 bits, hachage de signature faible, certificats serveur de plus de 398 jours, chaîne incomplète, sans clé privée), chacun disant ce qu’il compte et ouvrant sa liste quand il en a une' },
          { label: 'Dernières opérations', text: 'Les cinq opérations les plus récentes, chacune avec l’icône de son type, son auteur et son heure ; avec la permission d’audit, l’opération ouvre le journal d’audit filtré sur elle et Tout voir ouvre toute la piste' },
          { label: 'Activité des certificats', text: 'Les certificats émis, révoqués et expirés par jour sur 7, 15 ou 30 jours, en courbes avec leurs totaux ; les flèches gauche et droite lisent le graphique jour par jour' },
        ]
      },
    ],
    tips: [
      'Choisissez la présélection Opérateur ou Responsable dans l’en-tête, ou ouvrez Cartes pour afficher, masquer et réordonner les cartes ; la disposition est enregistrée avec votre compte et vous suit d’un navigateur à l’autre',
      'Le menu d’une carte la masque ou ouvre la fenêtre Cartes ; une carte À traiter masquée revient quand un chiffre ou une autre carte la demande',
      'Dans la liste des certificats, les filtres venant de la vue d’ensemble apparaissent sous forme de puces ; retirez-en une avec sa croix',
    ],
  },
  helpGuides: {
    title: 'Vue d’ensemble',
    content: `
## Aperçu

La Vue d’ensemble est la page d’accueil : un bandeau de quatre chiffres, puis les cartes de la vue d’ensemble sur les données en direct de votre PKI. Chaque carte se charge seule et affiche son propre état de chargement, de vide, d’erreur ou d’autorisation manquante.

## Premiers pas
Sur une instance sans aucun certificat, un administrateur voit trois étapes au-dessus des chiffres : créer une AC racine, puis une AC émettrice, puis configurer un protocole (ACME, SCEP ou EST). Chaque étape mène à l’écran qui la réalise ; une étape attend la précédente. **Plus tard** replie les étapes en une ligne qui garde la progression, **Reprendre** les rouvre. Une fois les trois faites, **Émettre un premier certificat** ouvre le formulaire de certificat et **Masquer** ferme les étapes pour de bon.

## Chiffres
Quatre chiffres ouvrent la page : les certificats (l’inventaire complet), les éléments à traiter (les interventions, et ceux à surveiller), les certificats expirés, et les échecs ACME, SCEP et EST du jour UTC en cours. Certificats et Expirés ouvrent la liste des certificats ; À traiter affiche la carte À traiter, en la réaffichant si vous l’aviez masquée ; les échecs mènent à la carte Santé de l’automatisation quand elle est affichée. Un chiffre que le serveur n’a pas donné se lit comme un tiret.

## Cartes

### À traiter
Les interventions par urgence, critiques d’abord, puis par échéance ; six sont affichées et **Afficher les autres** liste le reste. Chaque ligne a deux niveaux : le nom avec son type, puis la cause. À droite, un délai court (« dans 12 j », « échu depuis 3 j ») avec la date exacte dessous, et un bouton : **Renouveler** pour un renouvellement manuel, **Relancer** pour un renouvellement que le client ACME a manqué, **Publier maintenant** pour une CRL à publier ou manquante, chacun avec la permission d’écriture correspondante ; le nom ouvre alors l’enregistrement. Toute autre ligne porte **Examiner** (une demande qui attend une approbation), **Voir l’AC** ou **Ouvrir**. Une relance ou une publication qui échoue laisse un message avec **Réessayer**, pour la relancer. Les pastilles au-dessus de la liste filtrent par type et portent le total de chacun, et un lien dans l’en-tête de la carte ouvre les renouvellements manuels à faire. Ce qui ne demande rien aujourd’hui (certificats que leur client renouvelle, autorités et ancres de confiance encore loin de l’expiration) est compté sur une ligne à part, **Afficher** la déplie ; un élément critique n’y est jamais rangé. Avec le droit de lire le magasin de confiance, les certificats du magasin de confiance qui expirent dans 90 jours ou sont déjà expirés sont aussi listés (les expirés en critique).

### Santé de l’automatisation
Par protocole (ACME, SCEP, EST) : la dernière opération, les succès et échecs du jour UTC en cours et de la période, et une courbe des chiffres quotidiens. Les échecs ACME ouvrent la carte À traiter sur ses lignes ACME. Un dernier état en échec ou inconnu est dit à côté du nom. Dessous, le signataire TSA quand la TSA est activée (un avertissement tant que le certificat de l’AC signe, ses jetons ne satisfaisant pas la RFC 3161), le planificateur avec son nombre de tâches et son dernier passage et, avec le droit de lire les paramètres, si l’email, les webhooks et le renouvellement automatique sont configurés : un réglage non configuré est une information, pas une alerte ; un email configuré mais désactivé ou incomplet, ou des webhooks sans aucun actif, sont des alertes. Une ligne sous la carte compte les lignes qui signalent un problème.

### Hiérarchie
Dix autorités au plus, quelle que soit la taille de l’installation, une colonne par racine : les arbres qui ont le plus émis en 7 jours viennent d’abord, puis les plus grands. Une racine donne sa marque hors ligne, sa CRL et la signature croisée ; chaque autorité en dessous donne sa CRL, son répondeur OCSP et ses émissions sur 7 jours. Une autorité dont les filles ne sont pas toutes affichées dit combien il en reste en dessous, et la ligne sous le titre dit combien sont affichées. Chaque autorité ouvre sa page ; **Explorer** ouvre la page Autorités de certification.

### Horizon des expirations
Les six prochains certificats à expirer, chacun avec son délai, en rouge une fois dépassé et en ambre à moins de 7 jours, et une barre aussi longue que la part de validité déjà écoulée ; le signataire TSA et le répondeur OCSP sont marqués. Dessous, les certificats valides, à renouveler, expirés et révoqués, chacun ouvrant sa liste ; **Tout voir** ouvre les certificats à renouveler.

### Conformité
Les certificats actifs par algorithme de clé, avec une barre pour la part de chacun, puis cinq contrôles : RSA sous 3072 bits, hachage de signature faible, certificats serveur de plus de 398 jours, chaîne incomplète, sans clé privée. Chaque contrôle dit ce qu’il compte et ouvre sa liste quand il en a une ; les quatre faiblesses sont un avertissement au-dessus de zéro et un état correct à zéro, les certificats sans clé privée un simple compte.

### Dernières opérations
Les cinq opérations les plus récentes, chacune avec l’icône de son type, l’opération, l’objet, son auteur et l’heure ; la date exacte s’affiche au survol. Sans **read:audit**, vous ne voyez que vos propres opérations ; avec cette permission, l’objet ouvre la page Journaux d’audit filtrée sur cette opération et **Tout voir** ouvre toute la piste.

### Activité des certificats
Les certificats émis, révoqués et expirés par jour, sur 7, 15 ou 30 jours, en trois courbes avec leurs totaux sous le graphique. Pointer le graphique, ou y placer le focus et appuyer sur les flèches gauche et droite, lit un jour à la fois. Une période sans aucun événement affiche une phrase à la place d’un graphique vide.

## Ouvrir une liste filtrée
Chaque chiffre qui a une liste ouvre la page Certificats filtrée sur exactement les certificats qu’il compte. Le filtre apparaît sous forme de puce au-dessus du tableau ; retirez-le avec sa croix.

## Choisir et ordonner les cartes
Choisissez la présélection **Opérateur** (À traiter, Santé de l’automatisation, Hiérarchie, Horizon des expirations) ou **Responsable** (Conformité, Horizon des expirations, Hiérarchie, Dernières opérations) dans l’en-tête de la page, ou ouvrez **Cartes** pour cocher les cartes à afficher, les monter et les descendre, ou appliquer une présélection (**Toutes les cartes** affiche toutes les cartes dans l’ordre initial). Le menu d’une carte la masque, le bouton Cartes la réaffichant, ou ouvre la même fenêtre. L’ordre et les cartes masquées sont enregistrés avec votre compte et vous suivent d’un navigateur à l’autre ; quand toutes les cartes sont masquées, la page le dit et propose le bouton Cartes.

## Actions rapides
L’en-tête propose **Émettre**, qui ouvre le formulaire de certificat, à qui peut émettre des certificats.

## Actualisation
Les cartes se chargent à l’ouverture de la page puis se rechargent d’elles-mêmes, sans quitter la page, quand des certificats ou des AC changent, quand le lien en direct revient et quand vous revenez sur l’onglet ; le bouton d’actualisation de l’en-tête les recharge toutes d’un coup. Tant que le lien en direct est coupé, elles se rechargent une fois par minute. Une carte qui n’a pas pu lire dit pourquoi (l’état et la requête) et propose **Réessayer**, et **Voir le journal** à qui peut le lire. L’icône de connexion de la barre supérieure indique l’état du lien en direct, et la barre d’état en bas affiche la version et si le service répond.
`
  }
}
