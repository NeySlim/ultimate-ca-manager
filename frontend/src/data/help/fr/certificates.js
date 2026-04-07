export default {
  helpContent: {
    title: 'Certificats',
    subtitle: 'Émettre, gérer et surveiller les certificats',
    overview: 'Gestion centralisée de tous les certificats X.509. Émettez de nouveaux certificats depuis vos CA, importez des certificats existants, suivez les dates d\'expiration et gérez les renouvellements et révocations.',
    sections: [
      {
        title: 'Statut des certificats',
        definitions: [
          { term: 'Valide', description: 'Dans la période de validité et non révoqué' },
          { term: 'Expirant', description: 'Expirera dans les 30 jours' },
          { term: 'Expiré', description: 'Après la date « Not After »' },
          { term: 'Révoqué', description: 'Explicitement révoqué (publié dans la CRL)' },
          { term: 'Orphelin', description: 'La CA émettrice n\'existe plus dans le système' },
        ]
      },
      {
        title: 'Actions',
        items: [
          { label: 'Émettre', text: 'Créer un nouveau certificat signé par une de vos CA' },
          { label: 'Importer', text: 'Importer un certificat existant (PEM, DER ou PKCS#12)' },
          { label: 'Renouveler', text: 'Réémettre avec le même sujet et une nouvelle période de validité' },
          { label: 'Révoquer', text: 'Marquer comme révoqué avec un motif — apparaîtra dans la CRL' },
          { label: 'Lever la suspension', text: 'Annuler la suspension d\'un certificat révoqué avec le motif « Suspension de certificat » — restaure le statut valide' },
          { label: 'Révoquer et remplacer', text: 'Révoquer et émettre immédiatement un remplacement' },
          { label: 'Exporter', text: 'Télécharger en format PEM, DER ou PKCS#12' },
          { label: 'Comparer', text: 'Comparaison côte à côte de deux certificats' },
        ]
      },
    ],
    tips: [
      'Ajoutez une étoile ⭐ aux certificats importants pour les ajouter à vos favoris',
      'Utilisez les filtres pour trouver rapidement les certificats par statut, CA ou texte de recherche',
      'Le renouvellement conserve le même sujet mais génère une nouvelle paire de clés',
    ],
    warnings: [
      'La révocation est généralement permanente — sauf pour « Suspension de certificat » qui peut être levée',
      'Supprimer un certificat le retire de UCM mais ne le révoque pas',
    ],
  },
  helpGuides: {
    title: 'Certificats',
    content: `
## Vue d'ensemble

Gestion centralisée de tous les certificats X.509. Émettez de nouveaux certificats, importez des certificats existants, suivez les dates d'expiration, gérez les renouvellements et révocations.

## Statut des certificats

- **Valide** — Dans la période de validité et non révoqué
- **Expirant** — Expirera dans les 30 jours (configurable)
- **Expiré** — Après la date « Not After »
- **Révoqué** — Explicitement révoqué, publié dans la CRL
- **Orphelin** — La CA émettrice n'existe plus dans UCM

## Émettre un certificat

1. Cliquez sur **Émettre un certificat**
2. Sélectionnez la **CA de signature** (doit posséder une clé privée)
3. Remplissez le sujet (CN obligatoire, autres champs optionnels)
4. Ajoutez des noms alternatifs du sujet (SAN) : noms DNS, IP, e-mails
5. Choisissez le type et la taille de la clé
6. Définissez la période de validité
7. Appliquez optionnellement un **modèle** pour préremplir les paramètres
8. Cliquez sur **Émettre**

### Utiliser les modèles
Les modèles préremplissent l'utilisation de la clé, l'utilisation étendue de la clé, les valeurs par défaut du sujet et la validité. Sélectionnez un modèle avant de remplir le formulaire pour gagner du temps.

## Importer des certificats

Formats pris en charge :
- **PEM** — Certificats simples ou groupés
- **DER** — Format binaire
- **PKCS#12 (P12/PFX)** — Certificat + clé + chaîne (mot de passe requis)
- **PKCS#7 (P7B)** — Chaîne de certificats sans clés

## Renouveler un certificat

Le renouvellement crée un nouveau certificat avec :
- Même sujet et SAN
- Nouvelle paire de clés (générée automatiquement)
- Nouvelle période de validité
- Nouveau numéro de série

Le certificat original reste valide jusqu'à son expiration ou sa révocation.

## Révoquer un certificat

1. Sélectionnez le certificat → **Révoquer**
2. Choisissez un motif de révocation (Compromission de clé, Compromission de CA, Changement d'affiliation, Remplacement, Cessation d'activité, Suspension de certificat, etc.)
3. Confirmez la révocation

Les certificats révoqués sont publiés dans la CRL lors de la prochaine régénération.

> ⚠ La révocation est généralement permanente — sauf pour la **Suspension de certificat** qui peut être levée.

### Lever la suspension

Si un certificat a été révoqué avec le motif **Suspension de certificat**, il peut être restauré au statut valide :

1. Ouvrez les détails du certificat révoqué
2. Le bouton **Lever la suspension** apparaît dans la barre d'actions (uniquement pour les révocations de type Suspension de certificat)
3. Cliquez sur **Lever la suspension** pour restaurer le certificat
4. Le certificat retrouve le statut valide, la CRL est régénérée et le cache OCSP est mis à jour

> 💡 La suspension de certificat est utile pour les suspensions temporaires (par exemple, appareil perdu, enquête en cours).

### Révoquer et remplacer
Combine la révocation avec une réémission immédiate. Le nouveau certificat hérite du même sujet et des mêmes SAN.

## Exporter des certificats

Formats d'exportation :
- **PEM** — Certificat seul
- **PEM + Chaîne** — Certificat avec chaîne d'émetteur complète
- **DER** — Format binaire
- **PKCS#12** — Certificat + clé + chaîne, protégé par mot de passe

## Favoris

Ajoutez une étoile ⭐ aux certificats importants pour les marquer. Les favoris apparaissent en premier dans les vues filtrées et sont accessibles depuis le filtre des favoris.

## Comparer des certificats

Sélectionnez deux certificats et cliquez sur **Comparer** pour voir une comparaison côte à côte de leur sujet, SAN, utilisation de la clé, validité et extensions.

## Filtrage et recherche

- **Filtre par statut** — Valide, Expirant, Expiré, Révoqué, Orphelin
- **Filtre par CA** — Afficher les certificats d'une CA spécifique
- **Recherche textuelle** — Recherche par CN, numéro de série ou SAN
- **Tri** — Par nom, date d'expiration, date de création, statut
`
  }
}
