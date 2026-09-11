export default {
  helpContent: {
    title: 'Certificats',
    subtitle: 'Émettre, gérer et surveiller les certificats',
    overview: 'Gestion centralisée de tous les certificats X.509. Émettez de nouveaux certificats depuis vos CA, importez des certificats existants, suivez les dates d\'expiration et gérez les renouvellements et révocations.',
    sections: [
      {
        title: "Linting de conformité",
        content: "Le bouton « Linter » sur le détail d'un certificat le passe dans des linters de standards et affiche les anomalies. Purement informatif — ne bloque jamais l'émission.",
        items: [
          { label: "Profils", text: "RFC 5280 (toujours pertinent) et CA/Browser Forum Baseline Requirements (certificats TLS serveur)" },
          { label: "Sévérités", text: "Les résultats sont gradés : fatal, error, warning, notice, info" },
          { label: "Moteur", text: "Propulsé par pkilint (et zlint si son binaire est présent) — dépendance serveur optionnelle" },
          { label: "PKI interne", text: "Les règles CA/Browser Forum visent les certificats publics ; attendez-vous à des anomalies non applicables sur une PKI interne" },
        ]
      },
      {
        title: 'Statut des certificats',
        definitions: [
          { term: 'Valide', description: 'Dans la période de validité et non révoqué' },
          { term: 'Expirant', description: 'Expirera dans les 30 jours' },
          { term: 'Expiré', description: 'Après la date « Not After »' },
          { term: 'Révoqué', description: 'Explicitement révoqué (publié dans la CRL)' },
          { term: 'Orphelin', description: 'La CA émettrice n\'existe plus dans le système' },
          { term: 'Archivé', description: 'Remplacé par un renouvellement ou un ré-enrôlement qui a conservé l\'ancien enregistrement pour l\'historique (SCEP, EST, WSTEP, ACME, répondeur OCSP) ; listé avec le filtre de statut « Archivé »' },
        ]
      },
      {
        title: 'Actions',
        items: [
          { label: 'Émettre', text: 'Créer un nouveau certificat signé par une de vos CA' },
          { label: 'Importer', text: 'Importer un certificat existant (PEM, DER ou PKCS#12)' },
          { label: 'Renouveler', text: 'En place depuis la v2.214 : mêmes id/refid, nouveaux numéro de série et période de validité — le numéro de série remplacé reste dans la CRL jusqu\'à l\'ancienne expiration. Un certificat révoqué ne peut pas être renouvelé' },
          { label: 'Renommer', text: 'Définir un nom d\'affichage indépendant du CN (par défaut le CN, ou le premier nom DNS des SAN pour les certificats sans CN)' },
          { label: 'Révoquer', text: 'Marquer comme révoqué avec un motif — apparaîtra dans la CRL' },
          { label: 'Lever la suspension', text: 'Annuler la suspension d\'un certificat révoqué avec le motif « Suspension de certificat » — restaure le statut valide' },
          { label: 'Révoquer et remplacer', text: 'Révoquer et émettre immédiatement un remplacement' },
          { label: 'Exporter', text: 'Télécharger au format PEM, DER, PKCS#12 ou JKS' },
          { label: 'Mode compatibilité PKCS#12 (v2.222)', text: 'Les dialogues d\'export proposent un profil 3DES/SHA-1 pour les importeurs qui refusent l\'archive AES-256 par défaut comme un mot de passe incorrect : Android 15 et antérieur, macOS 14 et antérieur, Windows Server 2016 et antérieur, Java ancien. Désactivé par défaut, il protège moins bien le fichier' },
          { label: 'Comparer', text: 'Comparaison côte à côte de deux certificats' },
        ]
      },
      {
        title: 'EKU supplémentaires personnalisés (RFC 5280 §4.2.1.12)',
        content: 'Le formulaire d\'émission et la modale de signature de CSR exposent un sélecteur multi-valeurs « EKU supplémentaires » qui ajoute des OID Extended Key Usage en plus des EKU par défaut du type de certificat :',
        items: [
          { label: 'Catalogue', text: '18 EKU connus (Microsoft RDP 1.3.6.1.4.1.311.54.1.2, smartcard logon, document signing, IPsec, Kerberos PKINIT, etc.)' },
          { label: 'OID libre', text: 'Tout OID pointé bien formé respectant ^[0-2](?:\\.(?:0|[1-9]\\d*)){1,15}$' },
          { label: 'Limite', text: 'Jusqu\'à 16 OID au total par certificat' },
          { label: 'Fusion (jamais remplacement)', text: 'Les EKU par défaut du type (par ex. serverAuth) restent verrouillés — les extras s\'ajoutent par-dessus' },
          { label: 'Refusé', text: 'anyExtendedKeyUsage (2.5.29.37.0) est explicitement interdit' },
        ]
      },
      {
        title: 'Fichiers certificats sur disque (v2.140)',
        items: [
          { label: 'Auto-matérialisés', text: 'Les fichiers .crt / .key sont écrits sous data/certs/ pour chaque chemin de création (UI, signature CSR, ACME, SCEP, import)' },
          { label: 'CA aussi', text: 'Les fichiers .crt / .key des CA sont écrits sous data/cas/ via le même mécanisme' },
          { label: 'Filet de sécurité', text: 'Un scan de régénération au démarrage reconstruit tout fichier manquant depuis la base' },
          { label: 'Non bloquant', text: 'Les erreurs d\'écriture sont loguées mais n\'interrompent jamais la transaction DB' },
        ]
      },
      {
        title: 'Déploiement (v2.215)',
        content: "Poussez ce certificat vers des hôtes distants en SSH/SFTP — réservé aux admins, les cibles se gèrent dans Paramètres › Déploiement.",
        items: [
          { label: 'Attacher une cible', text: "Depuis le panneau de détails du certificat : choisissez une cible de déploiement et définissez des chemins de destination absolus pour le certificat, la clé privée et/ou la chaîne complète (au moins un)" },
          { label: 'Même hôte', text: "Pour déployer sur l’hôte UCM lui-même, utilisez une cible SFTP sur 127.0.0.1 avec un compte SSH dédié ; le service isolé ne peut pas écrire hors de son répertoire de données" },
          { label: 'Automatique', text: "À l'émission et au renouvellement, les fichiers liés sont poussés à nouveau et la commande de rechargement de la cible s'exécute — les livraisons sont mises en file avec réessais" },
          { label: 'Fichiers', text: "Écrits de façon atomique aux chemins exacts configurés (le répertoire parent doit exister) : clé 0600, certificat/chaîne 0644" },
          { label: 'Déployer maintenant', text: "Envoi manuel depuis le panneau de détails, avec le statut de livraison et la dernière erreur affichés par cible" },
        ]
      },

    ],
    tips: [
      'Ajoutez une étoile ⭐ aux certificats importants pour les ajouter à vos favoris',
      'Utilisez les filtres pour trouver rapidement les certificats par statut, CA ou texte de recherche — votre sélection est conservée au rechargement',
      'Le renouvellement conserve le même enregistrement (id, refid, date de création) — les certificats dont la clé est détenue par UCM reçoivent une nouvelle clé, ceux enrôlés par protocole (SCEP/EST/ACME) conservent leur clé côté client',
      'Besoin d\'un EKU non-standard (Microsoft RDP, smartcard logon, document signing) ? Ajoutez-le via « EKU supplémentaires » plutôt que d\'éditer les modèles',
    ],
    warnings: [
      'La révocation est généralement permanente — sauf pour « Suspension de certificat » qui peut être levée',
      'Un certificat valide non révoqué ne peut pas être supprimé (409) — révoquez-le d\'abord pour que la révocation atteigne la CRL/OCSP ; les révocations survivent à la suppression',
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
- **Archivé** — Remplacé par un renouvellement ou un ré-enrôlement qui a conservé l'ancien enregistrement pour l'historique (SCEP, EST, WSTEP, ACME, répondeur OCSP)

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

Depuis la v2.214, le renouvellement met à jour le certificat **en place** :
- Même enregistrement : **id, refid et date de création ne changent jamais** — les intégrations conservent leurs références
- Mêmes sujet et SAN ; nouveaux numéro de série et période de validité
- Les certificats dont UCM détient la clé reçoivent **une nouvelle clé** ; les certificats enrôlés par protocole (SCEP/EST/ACME) sont re-signés avec leur clé publique existante
- Le **numéro de série remplacé reste publié dans la CRL** (motif \`superseded\`) et répond \`revoked\` via OCSP jusqu'à l'expiration originale de l'ancien certificat
- \`renewed_at\` / \`renewed_times\` tracent l'historique des renouvellements
- Un certificat révoqué ne peut pas être renouvelé (409) — émettez-en un nouveau à la place

**Suppression** : un certificat valide non révoqué ne peut pas être supprimé (409) — révoquez-le d'abord pour que les parties utilisatrices voient le changement. Les révocations sont persistées indépendamment de l'enregistrement du certificat et survivent à la suppression.

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

- **Filtre par statut** — Valide, Expirant, Expiré, Révoqué, Orphelin, Archivé
- **Filtre par CA** — Afficher les certificats d'une CA spécifique
- **Filtre par source** — Filtrer selon la manière dont le certificat est entré dans UCM (émis, importé, ACME, SCEP, etc.)
- **Filtre par modèle** — Trouver les certificats **modifiés depuis le modèle** : émis depuis un modèle mais avec le type de clé, la validité ou l'algorithme de hachage explicitement remplacés au moment de la demande. Les champs divergents sont listés sur le détail du certificat ; l'enregistrement est figé à l'émission
- **Recherche textuelle** — Recherche par CN, numéro de série ou SAN
- **Tri** — Par nom, date d'expiration, date de création, statut
## Linting de conformité

Le bouton **Linter** (détail d'un certificat) vérifie la conformité aux standards X.509. Informatif uniquement.

- **RFC 5280** — profil X.509 IETF, toujours pertinent
- **CA/Browser Forum** — Baseline Requirements pour certificats TLS publics (bruit attendu sur PKI interne)
- Sévérités : fatal / error / warning / notice / info
- Moteur : pkilint (+ zlint si présent) — dépendance serveur optionnelle, dégradation gracieuse si absente

`
  }
}
