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
    ],
    tips: [
      'Les CA avec une icône de clé (🔑) possèdent une clé privée et peuvent signer des certificats',
      'Utilisez des CA intermédiaires pour la signature quotidienne, gardez la CA racine hors ligne si possible',
      'L\'exportation PKCS#12 inclut la chaîne complète et est idéale pour la sauvegarde',
    ],
    warnings: [
      'Supprimer une CA ne révoquera PAS les certificats qu\'elle a émis — révoquez-les d\'abord',
      'Les clés privées sont stockées chiffrées ; perdre la base de données signifie perdre les clés',
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
4. Définissez la période de validité (typiquement 10-20 ans pour les CA racines)
5. Sélectionnez optionnellement un modèle de certificat
6. Cliquez sur **Créer**

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
`
  }
}
