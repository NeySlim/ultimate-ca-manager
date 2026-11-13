export default {
  helpContent: {
    title: 'Autorités de certification',
    subtitle: 'Gérer votre hiérarchie PKI',
    overview: 'Créez et gérez les autorités de certification racines et intermédiaires. Construisez une chaîne de confiance complète pour votre organisation. Les CA avec des clés privées peuvent signer des certificats directement.',
    sections: [
      {
        title: 'Vues',
        items: [
          { label: 'Vue organigramme', text: 'Hiérarchie dessinée sous forme de schéma, chaque CA sous sa parente' },
          { label: 'Vue colonnes', text: 'Hiérarchie parcourue niveau par niveau, une colonne par niveau' },
          { label: 'Vue liste', text: 'Vue tableau plate avec tri et filtrage' },
        ]
      },
      {
        title: 'Actions',
        items: [
          { label: 'Créer CA', text: 'Un seul bouton ; la boîte de dialogue propose une racine auto-signée, une intermédiaire signée par une CA parente, ou une CA signée par une CA externe (CSR)' },
          { label: 'Importer une CA', text: 'Importer un certificat de CA existant (avec ou sans clé privée)' },
          { label: 'Exporter', text: 'PEM, DER ou PKCS#12 (P12/PFX) avec protection par mot de passe' },
          { label: 'Révoquer', text: 'Révoquer une CA intermédiaire auprès de sa CA parente : publiée dans la CRL et l\'OCSP du parent, et la CA ne peut plus signer (définitif)' },
          { label: 'Réparation de chaîne', text: 'Corriger automatiquement les relations parent-enfant rompues' },
          { label: 'Importer la clé privée', text: 'Rattacher la clé privée d\'une CA qui ne détient que son certificat, pour qu\'elle puisse signer' },
          { label: 'Clé et validité', text: 'RSA-3072 par défaut, locale ou HSM. Validité de 1, 2, 3, 5, 10, 15 ou 20 ans, ou Personnalisée (jours) jusqu\'à 50 ans. Une CA RSA-2048 qui dépasserait 2030 est signalée : l\'ANSSI accepte RSA-2048 jusqu\'à fin 2030, l\'ETSI TS 119 312 jusqu\'à fin 2026' },
          { label: 'Post-quantique (ML-DSA)', text: "ML-DSA-44, ML-DSA-65 ou ML-DSA-87 (FIPS 204, niveaux NIST 2, 3 et 5), générées en logiciel ou sur un fournisseur HSM qui prend en charge ML-DSA, et masquées en mode FIPS. Une clé ML-DSA signe sans digest séparé : la CA, ses CRL et ses réponses OCSP n'ont donc aucun digest à choisir. Une CA ML-DSA peut signer des certificats RSA ou EC, et une CA RSA ou EC peut signer une intermédiaire ML-DSA" },
          { label: 'EdDSA (Ed25519, Ed448)', text: "Clés Ed25519 ou Ed448 pour une CA racine, intermédiaire ou externe, en logiciel uniquement (aucun fournisseur HSM ne signe en EdDSA) et masquées en mode FIPS. Comme ML-DSA, une clé EdDSA signe sans digest, et la hiérarchie peut mélanger RSA, EC ou ML-DSA. Les navigateurs, Windows (CryptoAPI/CNG) et les clients SCEP n'acceptent pas ce qu'une CA EdDSA signe, quelle que soit la clé du certificat final : réservez-la aux consommateurs OpenSSL, Go ou Java 15+. SCEP et XCEP refusent une telle CA" },
          { label: "Import EdDSA (v2.251)", text: "Une clé de CA Ed25519 ou Ed448 peut être importée avec son certificat, ou ensuite avec Importer la clé privée" },
          { label: "Condensat par défaut (v2.251)", text: "Sous une AC P-384 ou P-521, ce qui est signé sans condensat choisi (EST, SCEP, WSTEP, Sign CSR, formulaire d'émission, orders ACME sans condensat, CRL) utilise SHA-384 ou SHA-512 ; les politiques bornent les certificats, pas les CRL. Les CRL déjà émises ne changent pas : la suivante applique la règle" },
          { label: "Pas de clé privée (v2.247)", text: "Une CA détenue sans sa clé privée est marquée Pas de clé privée, avec une action Importer la clé privée. Les sélecteurs de CA indiquent combien de CA ils écartent faute de pouvoir signer" },
          { label: 'Contraintes de noms', text: 'Contraintes avancées (RFC 5280) : les sous-arbres permis et exclus (DNS, plage IP, e-mail) limitent les noms que la CA peut certifier. Pour une CA signée en externe, ils sont fixés par la CA signataire' },
          { label: 'Schéma de signature RSA', text: "PKCS#1 v1.5 par défaut, ou RSA-PSS (sel aussi long que le hachage) pour une CA RSA avec une clé locale, PKCS#11 ou OpenBao. Il s'applique aux certificats, CRL, réponses OCSP et réponses SCEP signés par la CA ; les horodatages restent en PKCS#1 v1.5, le schéma que vérifie openssl ts -verify. « Signer avec RSA-PSS » dans les détails de la CA fait basculer une CA existante dans un sens ou dans l'autre : les certificats déjà émis conservent leur signature" },
          { label: 'Profil de conformité', text: "ANSSI, BSI ou EU ACM : des règles alignées sur un texte de référence encadrent ce que la CA émet (types de clé, hachages, schéma RSA, horizons de dates et, pour EU ACM, une clé de CA conservée sur HSM). À choisir à la création (une CA intermédiaire se voit proposer le profil de sa parente, sinon le profil par défaut défini dans Réglages, À propos). Sur une CA existante, le champ des détails permet de rattacher, changer ou retirer le profil : la vérification du profil s'exécute d'abord sur cette CA, ses constats sont listés, puis vous confirmez que les règles ne valent que pour les émissions futures, rien de ce qui est déjà émis n'est re-signé. Nécessite write:cas, et admin:system pour rattacher ou changer" },
          { label: "Listes d'émission", text: "Masquer à l'émission, dans les détails de la CA, retire une CA (une racine, en général) des listes de CA d'Émettre un certificat, de Signer un CSR, de la signature en masse de CSR, des certificats mTLS utilisateur (Mon compte, Utilisateurs et groupes) et du certificat de signature TSA. Un lien sous ces listes, Afficher les CA masquées, la rétablit au besoin, et une CA déjà choisie reste listée. Les réglages de protocoles (ACME, EST, SCEP, XCEP/WSTEP), la parente d'une nouvelle CA et la signature croisée la listent toujours. Nécessite write:cas" },
          { label: 'Parente invérifiable', text: "Une CA dont UCM ne peut pas vérifier la clé de la parente (SLH-DSA, GOST) est importée sans parente. Ses détails nomment la parente probable (même sujet que son émetteur, même identifiant de clé quand les deux en portent un) et l'algorithme ; Rattacher à cette parente demande une confirmation explicite, revérifie tout et garde qui l'a donnée et quand. La réparation de chaîne garde le lien, un réimport aussi tant que cette CA reste la parente probable, et Retirer le lien le défait. Une signature qui ne vérifie pas n'est jamais rattachée. Nécessite write:cas" },
        ]
      },
      {
        title: 'CA signées en externe (mode CSR, v2.214)',
        content: 'Le type de création « Signée par une CA externe (CSR) » couvre le schéma de racine hors ligne : la paire de clés vit dans UCM, le certificat est signé ailleurs. La clé privée ne quitte jamais UCM.',
        items: [
          { label: 'Créer', text: 'UCM génère la paire de clés (locale ou HSM) et un CSR de type CA, le CSR est téléchargé automatiquement' },
          { label: 'En attente de certificat', text: "La CA en attente ne peut ni signer, ni être exportée, ni être parente, ni passer hors ligne tant que son certificat n'est pas installé" },
          { label: 'Téléverser le certificat', text: 'Collez ou téléversez le certificat signé en externe (PEM/DER). Sa clé publique doit correspondre à la clé privée stockée ; les contraintes de CA sont vérifiées' },
          { label: 'Chaîne', text: "Liée automatiquement lorsque l'émetteur est connu de UCM, importez la racine externe (certificat seul) pour une chaîne complète" },
          { label: 'Renouveler via CSR', text: 'Réémet un CSR depuis la même clé (SKI stable) ; faites-le signer en externe et téléversez le nouveau certificat' },
          { label: 'Après renouvellement', text: "Le certificat remplacé reste valide jusqu'à son notAfter, UCM affiche son numéro de série après le téléversement ; révoquez-le auprès de la racine externe s'il ne doit plus être approuvé" },
        ]
      },
      {
        title: 'Certificats croisés',
        content: 'Un certificat croisé porte le sujet et la clé d\'une CA sous un autre émetteur : les clients qui ne font confiance qu\'à cette autre racine peuvent ainsi construire un chemin. Il se place à côté du certificat propre de la CA et ne le remplace jamais.',
        items: [
          { label: 'Où', text: 'Détails de la CA › Certificats croisés ; une CA qui en porte un affiche un badge Signée en croisé' },
          { label: 'Rattacher', text: 'Collez ou choisissez un certificat (PEM ou DER) émis par une autre CA pour la clé de cette CA ; les contraintes de noms ou de politique qu\'il porte sont signalées' },
          { label: 'Signer en croisé', text: 'Signe la clé de cette CA avec une autre CA détenue dans UCM, avec une validité et une longueur de chemin' },
          { label: 'Servir', text: 'Au plus un par CA est servi dans la chaîne par défaut (TLS, PKCS#12, ACME, WSTEP, TSA, déploiements, AIA .cer et .pem). Un certificat révoqué, expiré ou pas encore valide n\'est jamais servi' },
          { label: 'Chaîne à présenter', text: 'Les exports et les liaisons de déploiement peuvent imposer la chaîne par défaut, la racine auto-signée ou un certificat croisé. ACME propose les autres chaînes comme alternatives (certbot --preferred-chain)' },
          { label: 'Import', text: 'Un certificat sur la clé d\'une CA détenue est rattaché à une racine auto-signée ; sur une intermédiaire, le 409 propose Rattacher comme certificat croisé ou Remplacer. L\'import intelligent le rattache à côté d\'une racine détenue ou le signale comme écarté' },
          { label: 'Chaîne encore liée', text: 'Détails de la CA › Chaîne encore liée à cette CA liste les certificats, les sous-CA actives, les liaisons de déploiement et les envois de CRL qui passent encore par la CA, directement ou via un certificat croisé, pour savoir quand une ancienne racine peut être retirée ; un client qui a mis une chaîne en cache n\'est pas compté' },
          { label: 'Réparation', text: 'La barre sous les statistiques liste les enregistrements qu\'un ancien import a abîmés : Convertir en certificat croisé (nécessite delete:cas) et Restaurer comme principal. Rien ne s\'exécute seul' },
        ]
      },
      {
        title: 'CA adossées HSM',
        items: [
          { label: 'Stockage de la clé', text: 'Choisissez Local (en base de données, chiffrée sous la clé maître) ou HSM lors de la création de la CA' },
          { label: 'Générer une nouvelle clé', text: 'Créer une nouvelle clé de signature sur le fournisseur HSM sélectionné' },
          { label: 'Utiliser une clé existante', text: 'Lier la CA à une clé de signature inutilisée déjà présente sur le HSM' },
          { label: 'Pas d\'export de clé privée', text: 'Les clés adossées HSM ne quittent jamais le HSM, les exports PKCS#12, JKS et clé seule sont désactivés' },
          { label: 'Prérequis', text: 'Configurer et connecter un fournisseur HSM dans la gestion HSM au préalable' },
        ]
      },
      {
        title: 'Mode hors ligne',
        items: [
          { label: 'Objectif', text: "Protéger la clé privée d'une CA (typiquement une racine) contre l'usage runtime tout en gardant son certificat, sa chaîne et sa dernière CRL disponibles" },
          { label: 'Protégée par mot de passe', text: 'La clé est chiffrée avec un mot de passe utilisateur (PKCS#8) et reste en base. Restauration en saisissant le mot de passe.' },
          { label: 'Exportée en fichier', text: 'La clé est exportée en PEM chiffré téléchargeable une fois et retirée de la base. Restauration en re-téléversant le fichier avec son mot de passe.' },
          { label: 'Politique de mot de passe', text: "Le mot de passe suit la politique de complexité UCM (longueur et classes de caractères). S'il est perdu, la clé est irrécupérable." },
          { label: 'Effet sur la signature', text: "La signature de CSR, l'émission de certificats et le renouvellement sont bloqués hors ligne. La dernière CRL reste servie jusqu'à ce que vous en téléversiez une nouvelle, signée auprès de la clé ; l'OCSP répond via un répondeur délégué, sinon uniquement depuis les réponses déjà en cache, jusqu'à leur nextUpdate." },
          { label: 'Sous-CA', text: 'Les CA racines et intermédiaires peuvent être mises hors ligne indépendamment' },
        ]
      },
      {
        title: 'CRL externes pour les CA sans clé (v2.215)',
        content: "Une CA dont UCM ne peut pas utiliser la clé (CA hors ligne, import du certificat seul) ne peut pas signer sa propre CRL, téléversez à la place une CRL générée auprès de la clé hors ligne.",
        items: [
          { label: 'Où', text: "Panneau de détails de la CA › Liste de révocation (CRL) : affiche le numéro de la CRL servie, le nombre d'entrées, thisUpdate/nextUpdate, et un avertissement dès que nextUpdate est dépassé" },
          { label: 'Téléversement', text: "CRL complètes (non delta) uniquement, au format PEM ou DER. La signature doit se vérifier avec le certificat de la CA et l'émetteur doit correspondre à son sujet" },
          { label: 'Monotonie', text: 'Un téléversement plus ancien que la CRL actuellement servie (numéro de CRL ou thisUpdate) est refusé, émettez-la avec un numéro de CRL supérieur' },
          { label: 'Publication', text: "La CRL téléversée est servie au chemin CDP existant de la CA, et l'OCSP répond « révoqué » pour les numéros de série qu'elle liste" },
          { label: 'Flux de travail', text: "Révoquez auprès de la racine hors ligne, générez la CRL de la racine dans l'environnement isolé (air-gap), puis téléversez-la ici, la clé de la racine ne passe jamais en ligne" },
        ]
      },
    ],
    tips: [
      'Les CA avec une icône de clé (🔑) possèdent une clé privée et peuvent signer des certificats',
      'Mettez la CA racine hors ligne dès que vos intermédiaires sont opérationnelles',
      'Utilisez « Exportée en fichier » pour le meilleur isolement air-gap ; « Protégée par mot de passe » pour une restauration rapide en place',
      'L\'exportation PKCS#12 inclut la chaîne complète et est idéale pour la sauvegarde',
    ],
    warnings: [
      "Une CA ML-DSA ne peut pas encore être exportée en PKCS#12 ni en JKS : exportez le certificat et la clé privée en PEM. Les clients sans prise en charge de ML-DSA (OpenSSL avant 3.5, la plupart des navigateurs aujourd'hui) ne peuvent pas vérifier ce qu'elle signe",
      'Une CA ne peut pas être supprimée tant qu\'elle a des CA intermédiaires ou des certificats émis : révoquez-les et supprimez-les d\'abord',
      'Les clés privées sont stockées chiffrées ; perdre la base de données signifie perdre les clés',
      'Les mots de passe du mode hors ligne ne sont PAS récupérables : stockez-les dans votre coffre-fort avant de confirmer',
      'Un certificat croisé ne remplace jamais le certificat propre d\'une CA : une intermédiaire qui serait re-certifiée sous un autre émetteur est refusée (409) sauf si vous la rattachez comme certificat croisé ou remplacez le certificat actuel ; un roulement de racine sous le même nom d\'émetteur le remplace',
      'Une racine auto-signée écrasée ou supprimée n\'est pas récupérée par Convertir en certificat croisé : restaurez-la depuis une sauvegarde, ou fournissez son certificat à Restaurer comme principal',
    ],
  },
  helpGuides: {
    title: 'Autorités de certification',
    content: `
## Vue d'ensemble

Les autorités de certification (CA) constituent la base de votre PKI. UCM prend en charge les hiérarchies de CA multi-niveaux avec des CA racines, des CA intermédiaires et des sous-CA.

## Types de CA

### CA racine
Un certificat auto-signé qui sert d'ancre de confiance. Les CA racines devraient idéalement être conservées hors ligne dans les environnements de production. Dans UCM, une CA racine n'a pas de parent.

### CA intermédiaire
Signée par une CA racine ou une autre CA intermédiaire. Utilisée pour la signature quotidienne des certificats. Les CA intermédiaires limitent le rayon d'impact en cas de compromission.

### Sous-CA
Toute CA signée par une CA intermédiaire, créant des niveaux de hiérarchie plus profonds.

## Vues

Les trois boutons à côté du champ de recherche permettent de basculer entre :

### Vue organigramme
Dessine la hiérarchie des CA sous forme de schéma, chaque CA sous sa parente.

### Vue colonnes
Parcourt la hiérarchie niveau par niveau, une colonne par niveau : sélectionnez une CA pour voir celles qui sont en dessous.

### Vue liste
Tableau plat avec colonnes triables.

## Créer une CA

### Créer une CA racine
1. Cliquez sur **Créer CA** et choisissez le type racine dans la boîte de dialogue
2. Remplissez les champs du sujet (CN, O, OU, C, ST, L)
3. Sélectionnez l'algorithme de clé (RSA 2048/3072/4096, ECDSA P-256/P-384/P-521, ML-DSA 44/65/87, EdDSA Ed25519/Ed448) : RSA-3072 par défaut
4. Choisissez l'algorithme de signature (Auto, SHA-256/384/512. Auto aligne P-384 sur SHA-384)
5. Définissez la période de validité : 1, 2, 3, 5, 10, 15 ou 20 ans, ou **Personnalisée (jours)** jusqu'à 50 ans (typiquement 10-20 ans pour les CA racines)
6. Optionnel : ouvrez **Profil certificat (RFC 5280)** pour ajuster Key Usage / EKU
7. Cliquez sur **Créer**

### Créer une CA intermédiaire
1. Cliquez sur **Créer CA** et choisissez le type intermédiaire dans la boîte de dialogue
2. Sélectionnez la **CA parente** (doit posséder une clé privée)
3. Remplissez les champs du sujet
4. Définissez la période de validité (typiquement 5-10 ans)
5. Cliquez sur **Créer**

> ⚠ La validité de la CA intermédiaire ne peut pas dépasser celle de sa CA parente.

Le formulaire signale une CA RSA-2048 qui dépasserait 2030 : l'ANSSI accepte RSA-2048 jusqu'à fin 2030, l'ETSI TS 119 312 jusqu'à fin 2026. Choisissez RSA-3072 ou plus. Sous **Contraintes avancées (RFC 5280)**, les sous-arbres permis et exclus (DNS, plage IP, e-mail) limitent les noms que la CA peut certifier.

### CA post-quantiques (ML-DSA)
**ML-DSA-44**, **ML-DSA-65** et **ML-DSA-87** (FIPS 204) sont listées avec leur niveau de sécurité NIST (2, 3 et 5). La clé est générée en logiciel, ou sur un fournisseur HSM qui gère ML-DSA (voir CA adossées HSM), et l'algorithme est masqué en mode FIPS.

- Une clé ML-DSA signe sans digest séparé : le champ digest disparaît, et un digest envoyé par l'API est ignoré avec un avertissement. Les CRL et les réponses OCSP de la CA suivent la même règle.
- Les hiérarchies peuvent se mélanger : une racine ML-DSA peut signer une intermédiaire RSA ou EC, et une CA RSA ou EC peut signer une intermédiaire ML-DSA, qui utilise alors le digest de sa parente.
- Une CA ML-DSA s'exporte en PEM ou DER, pas en PKCS#12 ni en JKS. Les clients sans prise en charge de ML-DSA (OpenSSL avant 3.5, la plupart des navigateurs aujourd'hui) ne peuvent pas vérifier ce qu'elle signe.

### CA EdDSA (Ed25519, Ed448)
Des clés **Ed25519** et **Ed448** peuvent être générées pour une CA racine, intermédiaire ou externe, ou importées avec ou après le certificat de la CA. La clé est une clé logicielle (aucun fournisseur HSM ne signe en EdDSA), et l'algorithme est masqué en mode FIPS.

- Une clé EdDSA signe sans digest, comme ML-DSA : le champ digest disparaît, et les CRL et les réponses OCSP suivent la même règle.
- Les hiérarchies peuvent se mélanger : une CA EdDSA peut signer des intermédiaires et des certificats RSA, EC ou ML-DSA, et inversement.
- Les navigateurs, Windows (CryptoAPI/CNG) et les clients SCEP n'acceptent pas les certificats signés par une CA EdDSA, quelle que soit la clé du certificat final. SCEP et XCEP/WSTEP refusent une telle CA. Utilisez-la là où les consommateurs sont OpenSSL, Go ou Java 15+.

### Créer une CA signée en externe (mode CSR, v2.214)
Pour le schéma de racine hors ligne : la clé de la CA émettrice vit dans UCM, son certificat est signé ailleurs :
1. Cliquez sur **Créer CA** et choisissez le type **Signée par une CA externe (CSR)**
2. Renseignez le sujet et les paramètres de clé (locale ou HSM) : la validité est décidée par le signataire externe
3. Validez : UCM génère la paire de clés et un CSR de type CA (téléchargé automatiquement)
4. Faites signer le CSR par votre CA racine externe/hors ligne
5. De retour sur la CA (badge **En attente de certificat**), cliquez sur **Téléverser le certificat** et fournissez le certificat signé (PEM ou DER)

UCM n'active la CA que si la clé publique du certificat correspond à la clé privée stockée et que les contraintes de CA sont respectées. La chaîne se lie automatiquement lorsque l'émetteur est connu de UCM : importez la racine externe (certificat seul) pour une chaîne complète. Tant qu'elle n'est pas activée, la CA en attente ne peut ni signer, ni être exportée, ni être CA parente, ni passer hors ligne.

Pour renouveler, utilisez **Renouveler via CSR** : un nouveau CSR est émis **depuis la même clé** (le SKI reste stable), signé en externe, puis téléversé via le même flux.

## Importer une CA

Importez des certificats de CA existants via :
- **Fichier PEM** : Certificat au format PEM
- **Fichier DER** : Format binaire DER
- **PKCS#12** : Certificat + clé privée en bundle (nécessite un mot de passe)

Lors de l'importation sans clé privée, la CA peut vérifier les certificats mais ne peut pas en signer de nouveaux.

Un certificat qui porte le sujet et la clé d'une CA déjà présente dans UCM, sous un autre émetteur, est un certificat croisé et ne remplace jamais le certificat propre de la CA. Sur une racine auto-signée, il est rattaché comme certificat croisé. Sur une intermédiaire, et lors du téléversement après **Renouveler via CSR**, l'import est refusé (409) et propose **Rattacher comme certificat croisé** ou **Remplacer** ; un roulement de racine (même nom d'émetteur, nouvelle clé) remplace le certificat comme un renouvellement. L'import intelligent rattache celui trouvé à côté d'une racine détenue et le liste dans le résultat ; celui qu'il ne peut pas rattacher est écarté et signalé.

## Exporter une CA

Formats d'exportation :
- **PEM** : Certificat encodé en Base64
- **DER** : Format binaire
- **PKCS#12 (P12/PFX)** : Certificat + clé privée + chaîne, protégé par mot de passe

Lorsqu'un certificat croisé offre un autre chemin, la fenêtre d'exportation affiche **Chaîne à présenter** : la chaîne par défaut servie par UCM, la racine auto-signée ou un certificat croisé.

> 💡 L'exportation PKCS#12 inclut la chaîne de certificats complète et est idéale pour la sauvegarde.

## Certificats croisés

Un certificat croisé porte le sujet et la clé d'une CA sous la signature d'une autre CA. Les clients qui ne font confiance qu'à l'autre racine construisent par lui un chemin vers votre CA, ce qui permet de renouveler ou migrer une racine sans les casser. Il se place à côté du certificat propre de la CA, qui n'est jamais remplacé. Une CA qui en porte un affiche un badge **Signée en croisé**.

Dans les détails de la CA, **Certificats croisés** les liste :
- **Rattacher** : collez ou choisissez un certificat émis par une autre CA pour la clé de cette CA (PEM ou DER). Les contraintes de noms ou de politique qu'il porte sont signalées.
- **Signer en croisé** : signe la clé de cette CA avec une autre CA détenue dans UCM ; choisissez la validité et la longueur de chemin.
- **Servir / Ne plus servir** : au plus un par CA est servi, dans la chaîne par défaut de TLS, PKCS#12, ACME, WSTEP, TSA et des déploiements, et par les URL AIA \`.cer\` et \`.pem\`. Un certificat révoqué, expiré ou pas encore valide est conservé et exportable mais jamais servi.
- **Exporter** et **Détacher**.

Les exports et les liaisons de déploiement peuvent imposer une autre chaîne (**Chaîne à présenter** / **Variante de chaîne**). Le serveur ACME propose les autres chaînes comme alternatives, choisies par un client avec \`--preferred-chain\`. Les changements parviennent aux clients après la prochaine émission ou le prochain déploiement, et après les 24 heures de cache des URL AIA.

### Réparer des enregistrements abîmés

Une barre sous les statistiques des CA liste les enregistrements qu'un ancien import a laissés : un doublon qui détient le certificat croisé d'une racine également détenue (**Convertir en certificat croisé** déplace ses enfants et certificats vers la racine et supprime le doublon), ou une clé partagée par des certificats distincts sans enregistrement auto-signé (**Restaurer comme principal** reprend le certificat auto-signé). Rien n'est modifié sans un clic. Une racine auto-signée écrasée ou supprimée ne revient que depuis une sauvegarde ou par **Restaurer comme principal**.

## Clés privées

Les CA avec une **icône de clé** (🔑) ont une clé privée stockée dans UCM et peuvent signer des certificats. Les CA sans clé sont en mode confiance uniquement : elles valident les chaînes mais ne peuvent pas émettre.

### Stockage des clés
Les clés privées sont chiffrées au repos dans la base de données UCM. Pour une sécurité renforcée, envisagez d'utiliser un fournisseur HSM (voir la page HSM).

## Réparation de chaîne

Si les relations parent-enfant sont rompues (par exemple, après une importation), utilisez la **Réparation de chaîne** pour reconstruire automatiquement la hiérarchie basée sur la correspondance Émetteur/Sujet.

## Renouveler une CA

UCM ne réémet pas le certificat d'une CA qu'il a signée : pour remplacer une CA proche de son expiration, créez une nouvelle CA et émettez sous elle. Une CA signée par une CA externe se renouvelle avec **Renouveler via CSR**, qui réémet un CSR depuis la même clé pour que la CA externe le signe (voir CA signées en externe).

## Révoquer une CA intermédiaire

Une CA intermédiaire dont la clé est compromise ou qui est mise hors service est révoquée auprès de sa CA parente, comme un certificat :

1. Sélectionnez la CA intermédiaire et cliquez sur **Révoquer la CA**
2. Choisissez la raison RFC 5280 (compromission de clé, compromission de CA, cessation d'activité, ...)
3. Confirmez : la révocation est définitive

Ce qui se passe ensuite :
- Le numéro de série de la CA est publié dans la **CRL de la CA parente** (régénérée immédiatement) et le **répondeur OCSP** du parent répond \`revoked\` avec la raison
- La CA révoquée **ne peut plus rien signer** : certificats, CSR, renouvellements, sous-CA, et les CA situées en dessous non plus
- Les certificats qu'elle a émis ne sont plus approuvés par les clients qui valident la chaîne ; sa propre CRL et son OCSP continuent d'être servis jusqu'à la suppression de la CA
- Supprimer la CA révoquée conserve son entrée dans la CRL du parent jusqu'à l'expiration initiale du certificat

> ⚠ Une CA racine ne peut pas être révoquée depuis UCM (auto-signée : les parties utilisatrices la retirent de leurs magasins de confiance), et une intermédiaire signée par une racine externe est révoquée auprès de cette racine. Sa CRL peut ensuite être servie depuis UCM (voir Mode hors ligne).

## Supprimer une CA

La suppression est refusée (409) tant que la CA a des CA intermédiaires, a émis des certificats, ou est liée à un profil SCEP ou à un autre service. Révoquez et supprimez ses certificats, et supprimez ses enfants d'abord.

## CA adossées HSM

UCM peut stocker la clé de signature d'une CA sur un module matériel de sécurité (HSM) externe au lieu de la base de données chiffrée locale. C'est l'option recommandée pour les CA racines et intermédiaires en production.

### Quand l'utiliser
- Exigences de conformité (FIPS 140-2/3, eIDAS, Critères communs)
- Défense en profondeur : les clés ne peuvent pas être exfiltrées même si l'hôte UCM est compromis
- Gestion centralisée des clés sur plusieurs outils PKI

### Prérequis
1. Ouvrez **Gestion HSM** et configurez un fournisseur (PKCS#11 / OpenBao / etc.)
2. Vérifiez que le fournisseur est **Actif** et **Connecté**

### Étape par étape
1. Ouvrez **Créer une CA**
2. Renseignez le sujet et la validité comme d'habitude
3. Dans **Stockage de la clé**, basculez de *Local* à **HSM**
4. Choisissez le fournisseur HSM
5. Choisissez un mode de clé :
   - **Générer une nouvelle clé** : fournissez une étiquette (lettres/chiffres/_/-) et choisissez l'algorithme (RSA-2048/3072/4096 ou EC-P256/P384/P521, RSA-3072 par défaut ; Brainpool sur PKCS#11, ML-DSA sur les fournisseurs listés dans la gestion HSM)
   - **Utiliser une clé existante** : choisissez une clé de signature inutilisée déjà présente sur le HSM
6. Validez. UCM crée le certificat de CA et le lie à la clé HSM.

### Limitations
- Les clés privées adossées HSM **ne peuvent pas être exportées**. Les options d'export PKCS#12, JKS et clé seule sont masquées pour les CA HSM. Seul le certificat (PEM/DER/P7B) peut être exporté.
- Il n'y a **pas de migration en place** entre Local et HSM. Pour « déplacer » une CA locale existante sur un HSM, créez une nouvelle CA sur le HSM et réémettez les certificats.
- Les clés existantes proposées dans *Utiliser une clé existante* sont filtrées sur les clés asymétriques de signature non encore liées à une autre CA.

## Mode hors ligne

Sortez la clé de signature d'une CA de l'usage runtime sans supprimer la CA. Le certificat, la chaîne et la dernière CRL restent servis ; les opérations de signature (signer un CSR, émettre un certificat, renouveler, nouvelles CRL) sont bloquées. L'OCSP répond via un répondeur délégué, sinon uniquement depuis les réponses déjà en cache, jusqu'à leur nextUpdate.

C'est la façon standard de protéger une CA racine entre des cérémonies rares, tout en gardant son ancre de confiance et son infrastructure de révocation en ligne.

### Deux modes

**Protégée par mot de passe** : la clé privée reste en base de données UCM, chiffrée (PKCS#8) avec un mot de passe que vous choisissez. Pour remettre la CA en ligne, cliquez sur **Restaurer** et ressaisissez le mot de passe. Rapide et pratique ; la sécurité dépend de la robustesse du mot de passe et de la non-compromission d'UCM.

**Exportée en fichier** : la clé privée est exportée en fichier PEM chiffré par mot de passe téléchargé une fois. La clé est ensuite **retirée de la base**. Pour remettre la CA en ligne, cliquez sur **Restaurer**, téléversez le fichier et saisissez le mot de passe. C'est l'option la plus forte (vrai air-gap) mais vous êtes pleinement responsable du fichier : si vous le perdez, la clé est irrécupérable.

### Règles de mot de passe
Le mot de passe suit la politique de complexité standard UCM : longueur minimale, mélange de classes de caractères, pas de séquences triviales. Mêmes règles que les mots de passe utilisateurs.

### Étape par étape. Mettre hors ligne
1. Ouvrez la CA dans l'inspecteur
2. Cliquez sur **Mettre hors ligne**
3. Lisez l'explication, cliquez sur **Continuer**
4. Choisissez un mode (*Protégée par mot de passe* ou *Exportée en fichier*)
5. Saisissez le mot de passe deux fois
6. Confirmez. Pour *Exportée en fichier*, la clé chiffrée est téléchargée immédiatement : stockez-la en sécurité.

### Étape par étape. Restaurer
1. Ouvrez la CA hors ligne dans l'inspecteur
2. Cliquez sur **Restaurer**
3. Saisissez le mot de passe
4. Pour *Exportée en fichier* : sélectionnez aussi le fichier de clé téléchargé précédemment
5. Confirmez. Les opérations de signature reprennent immédiatement.

### Effet sur les opérations
| Opération | En ligne | Hors ligne |
|---|---|---|
| Émettre un certificat | Autorisé | **Bloqué** |
| Signer un CSR | Autorisé | **Bloqué** |
| Renouveler un certificat émis | Autorisé | **Bloqué** |
| Servir la dernière CRL | Autorisé | Autorisé (téléversez-en une nouvelle signée auprès de la clé) |
| OCSP | Autorisé | Répondeur délégué, ou réponses en cache jusqu'à nextUpdate |
| Exporter le certificat / la chaîne | Autorisé | Autorisé |
| Supprimer la CA | Autorisé | Autorisé |

> ⚠ Les mots de passe du mode hors ligne ne sont **pas récupérables**. Stockez-les dans votre coffre-fort avant de confirmer. Mot de passe perdu = CA inutilisable = réémission complète de la hiérarchie subordonnée.
`
  }
}