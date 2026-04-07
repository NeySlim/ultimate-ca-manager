export default {
  helpContent: {
    title: 'Outils de certificat',
    subtitle: 'Décoder, convertir et vérifier les certificats',
    overview: 'Une suite d\'outils pour travailler avec les certificats, CSR et clés. Décodez les certificats pour inspecter leur contenu, convertissez entre formats, vérifiez les points de terminaison SSL distants et vérifiez les correspondances de clés.',
    sections: [
      {
        title: 'Outils disponibles',
        items: [
          { label: 'Vérificateur SSL', text: 'Se connecter à un hôte distant et inspecter sa chaîne de certificats SSL/TLS' },
          { label: 'Décodeur de CSR', text: 'Collez une CSR au format PEM pour voir son sujet, ses SAN et ses infos de clé' },
          { label: 'Décodeur de certificat', text: 'Collez un certificat au format PEM pour inspecter tous les champs' },
          { label: 'Vérificateur de correspondance de clé', text: 'Vérifier qu\'un certificat, une CSR et une clé privée correspondent' },
          { label: 'Convertisseur', text: 'Convertir entre les formats PEM, DER, PKCS#12 et PKCS#7' },
        ]
      },
      {
        title: 'Détails du convertisseur',
        items: [
          'Conversion PEM ↔ DER',
          'PEM → PKCS#12 avec mot de passe et chaîne complète',
          'PKCS#12 → extraction PEM',
          'PEM → PKCS#7 (P7B) regroupement de chaîne',
        ]
      },
    ],
    tips: [
      'Le vérificateur SSL prend en charge les ports personnalisés — utilisez-le pour vérifier tout service TLS',
      'Le vérificateur de correspondance de clé compare les hachages de modules pour vérifier les paires correspondantes',
      'Le convertisseur préserve la chaîne de certificats complète lors de la création de PKCS#12',
    ],
  },
  helpGuides: {
    title: 'Outils de certificat',
    content: `
## Vue d'ensemble

Une boîte à outils pour inspecter, convertir et vérifier les certificats sans quitter UCM.

## Vérificateur SSL

Inspecter le certificat SSL/TLS d'un serveur distant :

1. Entrez le **nom d'hôte** (par ex. \`google.com\`)
2. Changez optionnellement le **port** (par défaut : 443)
3. Cliquez sur **Vérifier**

Les résultats incluent :
- Sujet et émetteur du certificat
- Dates de validité
- SAN (noms alternatifs du sujet)
- Type et taille de la clé
- Chaîne de certificats complète
- Version du protocole TLS

## Décodeur de CSR

Analyser et afficher le contenu d'une CSR :

1. Collez une CSR au format PEM
2. Cliquez sur **Décoder**

Affiche : Sujet, SAN, algorithme de clé, taille de clé, algorithme de signature.

## Décodeur de certificat

Analyser et afficher les détails d'un certificat :

1. Collez un certificat au format PEM
2. Cliquez sur **Décoder**

Affiche : Sujet, émetteur, SAN, validité, numéro de série, utilisation de la clé, extensions, empreintes.

## Vérificateur de correspondance de clé

Vérifier qu'un certificat, une CSR et une clé privée correspondent :

1. Collez le PEM du **certificat**
2. Collez le PEM de la **clé privée** (optionnellement chiffrée — fournissez le mot de passe)
3. Collez optionnellement le PEM de la **CSR**
4. Cliquez sur **Vérifier**

UCM compare les hachages de module (RSA) ou de clé publique (EC). Une correspondance confirme qu'ils forment une paire valide.

## Convertisseur

Convertir entre les formats de certificat et de clé :

### PEM → DER
Convertit un PEM encodé en Base64 en format binaire DER.

### PEM → PKCS#12
Crée un fichier P12/PFX protégé par mot de passe à partir de :
- PEM du certificat
- PEM de la clé privée
- Certificats de chaîne optionnels
- Mot de passe pour le fichier P12

### PKCS#12 → PEM
Extrait le certificat, la clé et la chaîne d'un fichier P12 :
- Téléversez le fichier P12
- Entrez le mot de passe
- Téléchargez les composants PEM extraits

### PEM → PKCS#7
Regroupe plusieurs certificats dans un seul fichier P7B (sans clés).

> 💡 Le convertisseur préserve la chaîne de certificats complète lors de la création de fichiers PKCS#12.
`
  }
}
