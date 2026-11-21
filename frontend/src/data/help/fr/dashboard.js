export default {
  helpContent: {
    title: 'Vue d\'ensemble',
    subtitle: 'Ce qui demande une action et l\'état de la PKI',
    overview: 'Six cartes indépendantes sur les données en direct de votre PKI. Chaque carte se charge seule et affiche son propre état de chargement, de vide, d\'erreur ou d\'autorisation manquante. Chaque compteur qui a une liste ouvre la liste des certificats filtrée sur exactement les certificats qu\'il compte.',
    sections: [
      {
        title: 'Cartes',
        items: [
          { label: 'À traiter', text: 'Les six éléments les plus urgents, critiques d\'abord, chacun renvoyant à son enregistrement (avec le droit de lire le magasin de confiance, les certificats du magasin de confiance qui expirent dans 90 jours ou sont expirés) ; un niveau replié donne le total par type, et les quatre types de renouvellement ouvrent la liste des certificats' },
          { label: 'Santé de l\'automatisation', text: 'Par protocole (ACME, SCEP, EST), les succès et échecs du jour, et l\'état du planificateur ; le signataire TSA quand la TSA est activée (un avertissement tant que le certificat de l\'AC signe) ; avec le droit de lire les paramètres, si l\'email, les webhooks et le renouvellement automatique sont configurés' },
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
    title: 'Vue d\'ensemble',
    content: `
## Aperçu

La Vue d'ensemble est la page d'accueil : six cartes indépendantes sur les données en direct de votre PKI. Chaque carte se charge seule et affiche son propre état de chargement, de vide, d'erreur ou d'autorisation manquante.

## Cartes

### À traiter
Les six éléments les plus urgents, critiques d'abord, chacun renvoyant à son enregistrement. Avec le droit de lire le magasin de confiance, les certificats du magasin de confiance qui expirent dans 90 jours ou sont déjà expirés sont aussi listés (les expirés en critique). Un niveau replié donne le total par type ; les quatre types de renouvellement ouvrent la liste des certificats.

### Santé de l'automatisation
Par protocole (ACME, SCEP, EST), les succès et échecs du jour et la dernière opération, ainsi que l'état du planificateur et, quand la TSA est activée, l'état de son signataire : un avertissement tant que le certificat de l'AC signe, ses jetons ne satisfaisant pas la RFC 3161. Avec le droit de lire les paramètres, trois lignes de plus disent si l'email, les webhooks et le renouvellement automatique sont configurés : un réglage non configuré est une information, pas une alerte ; un email configuré mais désactivé ou incomplet, ou des webhooks sans aucun actif, sont des alertes.

### Hiérarchie
Les autorités sous forme d'arbre sous leur parente, avec l'état CRL et OCSP, une marque hors ligne ou signée croisée, et les certificats que chacune a émis en 7 jours. Chaque autorité ouvre sa page.

### Horizon d'expiration
Les compteurs d'expirants et d'expirés, chacun ouvrant sa liste, et les cinq prochains certificats à expirer.

### Conformité
Les certificats actifs par algorithme de clé et par faiblesse : RSA sous 3072 bits, hachage de signature faible, certificats serveur de plus de 398 jours, chaîne incomplète, sans clé privée. Chaque compteur ouvre la liste correspondante.

### Dernières opérations
Les cinq opérations les plus récentes. Sans **read:audit**, vous ne voyez que vos propres événements ; avec cette permission, un lien ouvre toute la piste sur la page Journaux d'audit.

## Ouvrir une liste filtrée
Chaque compteur qui a une liste ouvre la page Certificats filtrée sur exactement les certificats qu'il compte. Le filtre apparaît sous forme de puce au-dessus du tableau ; retirez-le avec sa croix.

## Choisir les cartes
Choisissez le préréglage **Opérateur**, **Responsable** ou **Toutes les cartes** dans l'en-tête de la page pour définir les cartes affichées. La disposition est enregistrée avec votre compte et vous suit d'un navigateur à l'autre.

## Actualisation
Les cartes se chargent à l'ouverture de la page puis se rechargent d'elles-mêmes, sans quitter la page, quand des certificats ou des AC changent, quand le lien en direct revient et quand vous revenez sur l'onglet ; **Actualiser** les recharge toutes d'un coup. Tant que le lien en direct est coupé, elles se rechargent une fois par minute. Une carte en erreur propose **Réessayer**. L'icône de connexion de la barre supérieure indique l'état du lien en direct, et la barre d'état en bas affiche la version et si le service répond.
`
  }
}
