export default {
  helpContent: {
    title: 'Politiques de certificat',
    subtitle: 'Règles d\'émission et application de la conformité',
    overview: 'Définissez et gérez les politiques de certificat qui contrôlent les règles d\'émission, les exigences de clés, les limites de validité et les flux d\'approbation. Les politiques sont évaluées par ordre de priorité lors des demandes de certificats.',
    sections: [
      {
        title: 'Opérations',
        items: [
          { label: 'Émission', text: 'Le formulaire d\'émission, la signature de CSR et la signature en masse, ainsi que les renouvellements effectués par un opérateur' },
          { label: 'Renouvellement', text: 'Renouvellements par un opérateur, un seul ou en masse, et par le planificateur, qui met son renouvellement en file au lieu de l\'effectuer' },
          { label: 'Révocation', text: 'Révocations de certificats et de CA intermédiaires par un opérateur ; un client ACME ne peut pas attendre une décision, sa révocation est donc refusée' },
          { label: 'Plusieurs à la fois', text: 'Une politique peut couvrir plusieurs opérations ; une politique sans aucune (ancien type renouvellement ou révocation, jamais appliqué) ne couvre rien tant que vous n\'en choisissez pas' },
        ]
      },
      {
        title: 'Règles',
        items: [
          { label: 'Validité maximale', text: 'Durée de vie maximale du certificat en jours' },
          { label: 'Types de clés autorisés', text: 'Restreindre les algorithmes et tailles de clés pouvant être utilisés' },
          { label: 'Restrictions SAN', text: 'Limiter le nombre de SAN et imposer des motifs de noms DNS' },
        ]
      },
      {
        title: 'Flux d\'approbation',
        items: [
          { label: 'Groupes d\'approbation', text: 'Assigner un groupe d\'utilisateurs responsable de l\'approbation des demandes' },
          { label: 'Approbateurs min', text: 'Nombre d\'approbations requises avant l\'émission' },
          { label: 'Notifications', text: 'Alerter les administrateurs lors de violations de politique' },
        ]
      },
    ],
    tips: [
      'Nombre de priorité plus bas = précédence plus élevée. Utilisez 1–10 pour les politiques critiques.',
      'Scopez les politiques à des CA spécifiques pour un contrôle granulaire.',
      'Activez les notifications pour détecter tôt les violations de politique.',
    ],
  },
  helpGuides: {
    title: 'Politiques de certificat',
    content: `
## Vue d'ensemble

Les politiques de certificat définissent les règles et contraintes appliquées lors de l'émission, du renouvellement ou de la révocation de certificats. Les politiques sont évaluées par **ordre de priorité** (nombre plus bas = priorité plus élevée) et peuvent être scopées à des CA spécifiques.

## Opérations

Une politique couvre une ou plusieurs opérations : son exigence d'approbation et ses règles s'appliquent à celles-ci.

### Émission
Le formulaire d'émission, la signature de CSR et la signature en masse, ainsi que les renouvellements effectués par un opérateur. C'est le choix le plus courant. Contrôle les types de clés, les périodes de validité, les restrictions SAN et si l'approbation est requise.

### Renouvellement
Renouvellements par un opérateur, un seul ou en masse, et par le planificateur. Sous une politique de renouvellement qui exige une approbation, le planificateur met le renouvellement en file au lieu de l'effectuer, et l'approbation re-signe la clé détenue par le serveur.

### Révocation
Révocations de certificats (un seul, en masse, depuis les certificats utilisateur) et de CA intermédiaires. Limitée par la CA émettrice, le modèle et le motif DNS ; les autres règles ne s'appliquent pas. Un client ACME ne peut pas attendre une décision : sa révocation est refusée et laissée aux opérateurs. Supprimer l'inscription mTLS d'un autre utilisateur est refusé tant que son certificat n'est pas révoqué ; supprimer la sienne n'est jamais retenu.

Une politique créée avant l'existence des opérations conserve son comportement : une politique d'émission le reste, et un type renouvellement ou révocation, jamais appliqué, ne couvre rien tant que vous n'en choisissez pas les opérations.

## Configuration des règles

### Validité maximale
Durée de vie maximale du certificat en jours. Valeurs courantes :
- **90 jours** : Automatisation de courte durée (style ACME)
- **397 jours** : Baseline CA/Browser Forum pour TLS public
- **730 jours** : PKI interne/privée
- **365 jours** : Signature de code

### Types de clés autorisés
Restreindre les algorithmes et tailles de clés pouvant être utilisés :
- **RSA-2048** : Minimum pour la confiance publique
- **RSA-4096** : Sécurité plus élevée, certificats plus volumineux
- **EC-P256** : Moderne, rapide, recommandé
- **EC-P384** : Courbe elliptique à sécurité plus élevée
- **EC-P521** : Sécurité maximale (rarement nécessaire)

### Restrictions SAN
- **Noms DNS max** : Limiter le nombre de noms alternatifs du sujet
- **Motif DNS** : Restreindre à des motifs de domaine spécifiques (par ex. \`*.entreprise.com\`)

## Flux d'approbation

Lorsque **Approbation requise** est activé, l'émission de certificat est suspendue jusqu'à ce que le nombre requis d'approbateurs du groupe assigné aient approuvé la demande.

### Configuration
- **Groupe d'approbation** : Sélectionner un groupe d'utilisateurs responsable des approbations
- **Approbateurs min** : Nombre d'approbations requises (par ex. 2 sur 3 membres du groupe)
- **Notifications** : Alerter les administrateurs lors de violations de politique

> 💡 Utilisez les flux d'approbation pour les certificats de haute valeur comme la signature de code et les certificats génériques.

## Système de priorité

Les politiques sont évaluées par ordre de priorité. Les nombres plus bas ont une priorité plus élevée :
- **1-10** : Politiques de sécurité critiques (signature de code, génériques)
- **10-20** : Conformité standard (TLS public, PKI interne)
- **20+** : Valeurs par défaut permissives

Lorsque plusieurs politiques correspondent à une demande de certificat, la politique de priorité la plus élevée (nombre le plus bas) l'emporte.

## Portée

### Toutes les CA
La politique s'applique à chaque CA du système. À utiliser pour les règles à l'échelle de l'organisation.

### CA spécifique
La politique s'applique uniquement aux certificats émis par la CA sélectionnée. À utiliser pour un contrôle granulaire.

## Politiques par défaut

UCM est livré avec 5 politiques intégrées reflétant les meilleures pratiques PKI du monde réel :
- **Signature de code** (priorité 5) : Clés fortes, approbation requise
- **Certificats génériques** (priorité 8) : Approbation requise, max 10 SAN
- **TLS serveur web** (priorité 10) : Conforme CA/B Forum, max 397 jours
- **Automatisation courte durée** (priorité 15) : 90 jours style ACME
- **PKI interne** (priorité 20) : 730 jours, règles assouplies

> 💡 Personnalisez ou désactivez les politiques par défaut pour correspondre aux exigences de votre organisation.
`
  }
}
