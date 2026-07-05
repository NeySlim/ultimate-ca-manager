export default {
  helpContent: {
    title: 'Autorités de certification',
    subtitle: 'Gérer votre hiérarchie PKI',
    overview: 'Créez et gérez les autorités de certification racines et intermédiaires. Construisez une chaîne de confiance complète pour votre organisation. Les CA avec des clés privées peuvent signer des certificats directement.',
    sections: [
      {
        title: 'Vues',
        items: [
          { label: 'Vue arborescente', text: 'Affichage hiérarchique montrant les relations parent-enfant des CA' },
          { label: 'Vue liste', text: 'Vue tableau plate avec tri et filtrage' },
          { label: 'Vue organisation', text: 'Regroupement par organisation pour les configurations multi-locataires' },
        ]
      },
      {
        title: 'Actions',
        items: [
          { label: 'Créer une CA racine', text: 'Autorité de niveau supérieur auto-signée' },
          { label: 'Créer une intermédiaire', text: 'CA signée par une CA parente dans la chaîne' },
          { label: 'Importer une CA', text: 'Importer un certificat de CA existant (avec ou sans clé privée)' },
          { label: 'Exporter', text: 'PEM, DER ou PKCS#12 (P12/PFX) avec protection par mot de passe' },
          { label: 'Renouveler la CA', text: 'Réémettre le certificat de la CA avec une nouvelle période de validité' },
          { label: 'Réparation de chaîne', text: 'Corriger automatiquement les relations parent-enfant rompues' },
        ]
      },
      {
        title: 'CA adossées HSM',
        items: [
          { label: 'Stockage de la clé', text: 'Choisissez Local (chiffré en BD) ou HSM lors de la création de la CA' },
          { label: 'Générer une nouvelle clé', text: 'Créer une nouvelle clé de signature sur le fournisseur HSM sélectionné' },
          { label: 'Utiliser une clé existante', text: 'Lier la CA à une clé de signature inutilisée déjà présente sur le HSM' },
          { label: 'Pas d\'export de clé privée', text: 'Les clés adossées HSM ne quittent jamais le HSM — les exports PKCS#12, JKS et clé seule sont désactivés' },
          { label: 'Prérequis', text: 'Configurer et connecter un fournisseur HSM dans la gestion HSM au préalable' },
        ]
      },
      {
        title: 'Mode hors ligne',
        items: [
          { label: 'Objectif', text: "Protéger la clé privée d'une CA (typiquement une racine) contre l'usage runtime tout en gardant le certificat, la chaîne, la CRL et l'OCSP disponibles" },
          { label: 'Protégée par mot de passe', text: 'La clé est chiffrée avec un mot de passe utilisateur (PKCS#8) et reste en base. Restauration en saisissant le mot de passe.' },
          { label: 'Exportée en fichier', text: 'La clé est exportée en PEM chiffré téléchargeable une fois et retirée de la base. Restauration en re-téléversant le fichier avec son mot de passe.' },
          { label: 'Politique de mot de passe', text: "Le mot de passe suit la politique de complexité UCM (longueur et classes de caractères). S'il est perdu, la clé est irrécupérable." },
          { label: 'Effet sur la signature', text: "La signature de CSR, l'émission de certificats et le renouvellement de la CA sont bloqués hors ligne. CRL et OCSP continuent depuis les signatures en cache." },
          { label: 'Sous-CA', text: 'Les CA racines et intermédiaires peuvent être mises hors ligne indépendamment' },
        ]
      },
    ],
    tips: [
      'Les CA avec une icône de clé (🔑) possèdent une clé privée et peuvent signer des certificats',
      'Utilisez des CA intermédiaires pour la signature quotidienne, gardez la CA racine hors ligne si possible',
      'L\'exportation PKCS#12 inclut la chaîne complète et est idéale pour la sauvegarde',
      'Mettez la CA racine hors ligne dès que vos intermédiaires sont opérationnelles',
      'Utilisez « Exportée en fichier » pour le meilleur isolement air-gap ; « Protégée par mot de passe » pour une restauration rapide en place',
    ],
    warnings: [
      'Supprimer une CA ne révoquera PAS les certificats qu\'elle a émis — révoquez-les d\'abord',
      'Les clés privées sont stockées chiffrées ; perdre la base de données signifie perdre les clés',
      'Les mots de passe du mode hors ligne ne sont PAS récupérables — stockez-les dans votre coffre-fort avant de confirmer',
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

### Vue arborescente
Affiche la hiérarchie complète des CA sous forme d'arbre repliable. Les relations parent-enfant sont visualisées avec une indentation et des lignes de connexion.

### Vue liste
Tableau plat avec colonnes triables : Nom, Type, Statut, Certificats émis, Date d'expiration.

### Vue organisation
Regroupe les CA par leur champ Organisation (O). Utile pour les configurations multi-locataires où différents départements gèrent des arborescences de CA séparées.

## Créer une CA

### Créer une CA racine
1. Cliquez sur **Créer** → **CA racine**
2. Remplissez les champs du sujet (CN, O, OU, C, ST, L)
3. Sélectionnez l'algorithme de clé (RSA 2048/4096, ECDSA P-256/P-384)
4. Choisissez l'algorithme de signature (Auto, SHA-256/384/512 — Auto aligne P-384 sur SHA-384)
5. Définissez la période de validité (typiquement 10-20 ans pour les CA racines)
6. Optionnel : ouvrez **Profil certificat (RFC 5280)** pour ajuster Key Usage / EKU
7. Cliquez sur **Créer**

### Créer une CA intermédiaire
1. Cliquez sur **Créer** → **CA intermédiaire**
2. Sélectionnez la **CA parente** (doit posséder une clé privée)
3. Remplissez les champs du sujet
4. Définissez la période de validité (typiquement 5-10 ans)
5. Cliquez sur **Créer**

> ⚠ La validité de la CA intermédiaire ne peut pas dépasser celle de sa CA parente.

## Importer une CA

Importez des certificats de CA existants via :
- **Fichier PEM** — Certificat au format PEM
- **Fichier DER** — Format binaire DER
- **PKCS#12** — Certificat + clé privée en bundle (nécessite un mot de passe)

Lors de l'importation sans clé privée, la CA peut vérifier les certificats mais ne peut pas en signer de nouveaux.

## Exporter une CA

Formats d'exportation :
- **PEM** — Certificat encodé en Base64
- **DER** — Format binaire
- **PKCS#12 (P12/PFX)** — Certificat + clé privée + chaîne, protégé par mot de passe

> 💡 L'exportation PKCS#12 inclut la chaîne de certificats complète et est idéale pour la sauvegarde.

## Clés privées

Les CA avec une **icône de clé** (🔑) ont une clé privée stockée dans UCM et peuvent signer des certificats. Les CA sans clé sont en mode confiance uniquement — elles valident les chaînes mais ne peuvent pas émettre.

### Stockage des clés
Les clés privées sont chiffrées au repos dans la base de données UCM. Pour une sécurité renforcée, envisagez d'utiliser un fournisseur HSM (voir la page HSM).

## Réparation de chaîne

Si les relations parent-enfant sont rompues (par exemple, après une importation), utilisez la **Réparation de chaîne** pour reconstruire automatiquement la hiérarchie basée sur la correspondance Émetteur/Sujet.

## Renouveler une CA

Le renouvellement réémet le certificat de la CA avec :
- Même sujet et clé
- Nouvelle période de validité
- Nouveau numéro de série

Les certificats existants signés par la CA restent valides.

## Supprimer une CA

> ⚠ Supprimer une CA la retire de UCM mais ne révoque PAS les certificats qu'elle a émis. Révoquez les certificats au préalable si nécessaire.

La suppression est bloquée si la CA a des CA enfants. Supprimez ou réaffectez les enfants d'abord.

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
   - **Générer une nouvelle clé** — fournissez une étiquette (lettres/chiffres/_/-) et choisissez l'algorithme (RSA-2048/3072/4096 ou EC-P256/P384/P521)
   - **Utiliser une clé existante** — choisissez une clé de signature inutilisée déjà présente sur le HSM
6. Validez. UCM crée le certificat de CA et le lie à la clé HSM.

### Limitations
- Les clés privées adossées HSM **ne peuvent pas être exportées**. Les options d'export PKCS#12, JKS et clé seule sont masquées pour les CA HSM. Seul le certificat (PEM/DER/P7B) peut être exporté.
- Il n'y a **pas de migration en place** entre Local et HSM. Pour « déplacer » une CA locale existante sur un HSM, créez une nouvelle CA sur le HSM et réémettez les certificats.
- Les clés existantes proposées dans *Utiliser une clé existante* sont filtrées sur les clés asymétriques de signature non encore liées à une autre CA.

## Mode hors ligne

Sortez la clé de signature d'une CA de l'usage runtime sans supprimer la CA. Le certificat, la chaîne, la CRL et l'OCSP continuent de fonctionner — seules les opérations de signature (signer un CSR, émettre un certificat, renouveler la CA) sont bloquées.

C'est la façon standard de protéger une CA racine entre des cérémonies rares, tout en gardant son ancre de confiance et son infrastructure de révocation en ligne.

### Deux modes

**Protégée par mot de passe** — la clé privée reste en base de données UCM, chiffrée (PKCS#8) avec un mot de passe que vous choisissez. Pour remettre la CA en ligne, cliquez sur **Restaurer** et ressaisissez le mot de passe. Rapide et pratique ; la sécurité dépend de la robustesse du mot de passe et de la non-compromission d'UCM.

**Exportée en fichier** — la clé privée est exportée en fichier PEM chiffré par mot de passe téléchargé une fois. La clé est ensuite **retirée de la base**. Pour remettre la CA en ligne, cliquez sur **Restaurer**, téléversez le fichier et saisissez le mot de passe. C'est l'option la plus forte (vrai air-gap) mais vous êtes pleinement responsable du fichier : si vous le perdez, la clé est irrécupérable.

### Règles de mot de passe
Le mot de passe suit la politique de complexité standard UCM : longueur minimale, mélange de classes de caractères, pas de séquences triviales. Mêmes règles que les mots de passe utilisateurs.

### Étape par étape — Mettre hors ligne
1. Ouvrez le panneau de détails de la CA
2. Cliquez sur **Mettre hors ligne**
3. Lisez l'explication, cliquez sur **Continuer**
4. Choisissez un mode (*Protégée par mot de passe* ou *Exportée en fichier*)
5. Saisissez le mot de passe deux fois
6. Confirmez. Pour *Exportée en fichier*, la clé chiffrée est téléchargée immédiatement — stockez-la en sécurité.

### Étape par étape — Restaurer
1. Ouvrez le panneau de détails de la CA hors ligne
2. Cliquez sur **Restaurer**
3. Saisissez le mot de passe
4. Pour *Exportée en fichier* : sélectionnez aussi le fichier de clé téléchargé précédemment
5. Confirmez. Les opérations de signature reprennent immédiatement.

### Effet sur les opérations
| Opération | En ligne | Hors ligne |
|---|---|---|
| Émettre un certificat | Autorisé | **Bloqué** |
| Signer un CSR | Autorisé | **Bloqué** |
| Renouveler la CA | Autorisé | **Bloqué** |
| Renouveler un certificat émis | Autorisé | **Bloqué** |
| Servir CRL / OCSP | Autorisé | Autorisé (signature en cache) |
| Exporter le certificat / la chaîne | Autorisé | Autorisé |
| Supprimer la CA | Autorisé | Autorisé |

> ⚠ Les mots de passe du mode hors ligne ne sont **pas récupérables**. Stockez-les dans votre coffre-fort avant de confirmer. Mot de passe perdu = CA inutilisable = réémission complète de la hiérarchie subordonnée.
`
  }
}