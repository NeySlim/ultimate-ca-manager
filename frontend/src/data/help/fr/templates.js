export default {
  helpContent: {
    title: 'Modèles de certificat',
    subtitle: 'Profils de certificat réutilisables',
    overview: 'Définissez des profils de certificat réutilisables avec des champs de sujet préconfigurés, l\'utilisation de la clé, l\'utilisation étendue de la clé, les périodes de validité et d\'autres extensions. Appliquez les modèles lors de l\'émission ou de la signature de certificats.',
    sections: [
      {
        title: 'Types de modèles',
        definitions: [
          { term: 'Entité finale', description: 'Pour les certificats serveur, client, signature de code et e-mail' },
          { term: 'CA', description: 'Pour créer des autorités de certification intermédiaires' },
        ]
      },
      {
        title: 'Fonctionnalités',
        items: [
          { label: 'Valeurs par défaut du sujet', text: 'Préremplir Organisation, OU, Pays, État, Ville' },
          { label: 'Utilisation de la clé', text: 'Signature numérique, chiffrement de clé, etc.' },
          { label: 'Utilisation étendue de la clé', text: 'Authentification serveur, authentification client, signature de code, protection e-mail' },
          { label: 'Validité', text: 'Période de validité par défaut en jours' },
          { label: 'Dupliquer', text: 'Cloner un modèle existant et le modifier' },
          { label: 'Importer/Exporter', text: 'Partager des modèles sous forme de fichiers JSON entre instances UCM' },
        ]
      },
    ],
    tips: [
      'Créez des modèles séparés pour les serveurs TLS, les clients et la signature de code',
      'Utilisez l\'action Dupliquer pour créer rapidement des variantes d\'un modèle',
    ],
  },
  helpGuides: {
    title: 'Modèles de certificat',
    content: `
## Vue d'ensemble

Les modèles définissent des profils de certificat réutilisables. Au lieu de configurer manuellement l'utilisation de la clé, l'utilisation étendue de la clé, la validité et les champs du sujet à chaque fois, appliquez un modèle pour tout préremplir.

## Types de modèles

### Modèles d'entité finale
Pour les certificats serveur, les certificats client, la signature de code et la protection e-mail. Ces modèles définissent généralement :
- **Utilisation de la clé** — Signature numérique, chiffrement de clé
- **Utilisation étendue de la clé** — Authentification serveur, authentification client, signature de code, protection e-mail

### Modèles de CA
Pour créer des CA intermédiaires. Ceux-ci définissent :
- **Utilisation de la clé** — Signature de certificat, signature de CRL
- **Contraintes de base** — CA:TRUE, longueur de chemin optionnelle

## Créer un modèle

1. Cliquez sur **Créer un modèle**
2. Entrez un **nom** et une description optionnelle
3. Sélectionnez le **type** de modèle (entité finale ou CA)
4. Configurez les **valeurs par défaut du sujet** (O, OU, C, ST, L)
5. Sélectionnez les indicateurs d'**utilisation de la clé**
6. Sélectionnez les valeurs d'**utilisation étendue de la clé**
7. Définissez la **période de validité par défaut** en jours
8. Cliquez sur **Créer**

## Utiliser les modèles

Lors de l'émission d'un certificat ou de la signature d'une CSR, sélectionnez un modèle dans la liste déroulante. Le modèle prérempli :
- Les champs du sujet (vous pouvez les modifier)
- L'utilisation de la clé et l'utilisation étendue de la clé
- La période de validité

## Dupliquer des modèles

Cliquez sur **Dupliquer** pour créer une copie d'un modèle existant. Modifiez la copie sans affecter l'original.

## Importer et exporter

### Exporter
Exportez les modèles au format JSON pour les partager entre instances UCM.

### Importer
Importez depuis :
- **Fichier JSON** — Téléversez un fichier JSON de modèle
- **Coller du JSON** — Collez le JSON directement dans la zone de texte

## Exemples de modèles courants

### Serveur TLS
- Utilisation de la clé : Signature numérique, chiffrement de clé
- Utilisation étendue de la clé : Authentification serveur
- Validité : 365 jours

### Authentification client
- Utilisation de la clé : Signature numérique
- Utilisation étendue de la clé : Authentification client
- Validité : 365 jours

### Signature de code
- Utilisation de la clé : Signature numérique
- Utilisation étendue de la clé : Signature de code
- Validité : 365 jours
`
  }
}
