export default {
  helpContent: {
    title: 'Politiques de certificat',
    subtitle: 'Gouvernance et conformité',
    overview: 'Définissez les règles et contraintes appliquées lors de l\'émission, du renouvellement ou de la révocation de certificats. Les politiques peuvent restreindre les types de clés, les périodes de validité, les SAN et imposer des flux d\'approbation.',
    sections: [
      {
        title: 'Types de politiques',
        definitions: [
          { term: 'Émission', description: 'Règles appliquées lors de la création de nouveaux certificats' },
          { term: 'Renouvellement', description: 'Règles appliquées lors du renouvellement de certificats' },
          { term: 'Révocation', description: 'Règles appliquées lors de la révocation de certificats' },
        ]
      },
      {
        title: 'Configuration des règles',
        items: [
          { label: 'Validité maximale', text: 'Durée de vie maximale du certificat en jours' },
          { label: 'Types de clés autorisés', text: 'Restreindre les algorithmes de clé : RSA-2048, RSA-4096, EC-P256, EC-P384' },
          { label: 'Restrictions SAN', text: 'Nombre maximum de noms DNS et restrictions de motifs de domaine' },
          { label: 'Approbation requise', text: 'Activer les flux d\'approbation avec un nombre minimum d\'approbateurs' },
          { label: 'Notifications', text: 'Alerter les administrateurs lors de violations de politique' },
        ]
      },
      {
        title: 'Priorité',
        content: 'Les politiques sont évaluées par ordre de priorité. Les nombres plus bas ont une priorité plus élevée :',
        items: [
          '1-10 : Politiques de sécurité critiques (signature de code, certificats génériques)',
          '10-20 : Conformité standard (TLS public, PKI interne)',
          '20+ : Valeurs par défaut permissives',
        ]
      },
    ],
    tips: [
      'Utilisez des flux d\'approbation pour les certificats de haute valeur comme la signature de code et les certificats génériques',
      'Scopez les politiques à des CA spécifiques ou appliquez-les à l\'ensemble du système',
      'UCM inclut 5 politiques par défaut intégrées reflétant les meilleures pratiques PKI du monde réel',
    ],
  },
  helpGuides: {
    title: 'Politiques de certificat',
    content: `
## Vue d'ensemble

Les politiques de certificat définissent les règles et contraintes appliquées lors de l'émission, du renouvellement ou de la révocation de certificats. Les politiques sont évaluées par **ordre de priorité** (nombre plus bas = priorité plus élevée) et peuvent être scopées à des CA spécifiques.

## Types de politiques

### Politiques d'émission
Règles appliquées lors de la création de nouveaux certificats. C'est le type le plus courant. Contrôle les types de clés, les périodes de validité, les restrictions SAN et si l'approbation est requise.

### Politiques de renouvellement
Règles appliquées lors du renouvellement de certificats. Peuvent imposer une validité plus courte au renouvellement ou exiger une réapprobation.

### Politiques de révocation
Règles appliquées lors de la révocation de certificats. Peuvent exiger une approbation avant la révocation de certificats critiques.

## Configuration des règles

### Validité maximale
Durée de vie maximale du certificat en jours. Valeurs courantes :
- **90 jours** — Automatisation de courte durée (style ACME)
- **397 jours** — Baseline CA/Browser Forum pour TLS public
- **730 jours** — PKI interne/privée
- **365 jours** — Signature de code

### Types de clés autorisés
Restreindre les algorithmes et tailles de clés pouvant être utilisés :
- **RSA-2048** — Minimum pour la confiance publique
- **RSA-4096** — Sécurité plus élevée, certificats plus volumineux
- **EC-P256** — Moderne, rapide, recommandé
- **EC-P384** — Courbe elliptique à sécurité plus élevée
- **EC-P521** — Sécurité maximale (rarement nécessaire)

### Restrictions SAN
- **Noms DNS max** — Limiter le nombre de noms alternatifs du sujet
- **Motif DNS** — Restreindre à des motifs de domaine spécifiques (par ex. \`*.entreprise.com\`)

## Flux d'approbation

Lorsque **Approbation requise** est activé, l'émission de certificat est suspendue jusqu'à ce que le nombre requis d'approbateurs du groupe assigné aient approuvé la demande.

### Configuration
- **Groupe d'approbation** — Sélectionner un groupe d'utilisateurs responsable des approbations
- **Approbateurs min** — Nombre d'approbations requises (par ex. 2 sur 3 membres du groupe)
- **Notifications** — Alerter les administrateurs lors de violations de politique

> 💡 Utilisez les flux d'approbation pour les certificats de haute valeur comme la signature de code et les certificats génériques.

## Système de priorité

Les politiques sont évaluées par ordre de priorité. Les nombres plus bas ont une priorité plus élevée :
- **1-10** — Politiques de sécurité critiques (signature de code, génériques)
- **10-20** — Conformité standard (TLS public, PKI interne)
- **20+** — Valeurs par défaut permissives

Lorsque plusieurs politiques correspondent à une demande de certificat, la politique de priorité la plus élevée (nombre le plus bas) l'emporte.

## Portée

### Toutes les CA
La politique s'applique à chaque CA du système. À utiliser pour les règles à l'échelle de l'organisation.

### CA spécifique
La politique s'applique uniquement aux certificats émis par la CA sélectionnée. À utiliser pour un contrôle granulaire.

## Politiques par défaut

UCM est livré avec 5 politiques intégrées reflétant les meilleures pratiques PKI du monde réel :
- **Signature de code** (priorité 5) — Clés fortes, approbation requise
- **Certificats génériques** (priorité 8) — Approbation requise, max 10 SAN
- **TLS serveur web** (priorité 10) — Conforme CA/B Forum, max 397 jours
- **Automatisation courte durée** (priorité 15) — 90 jours style ACME
- **PKI interne** (priorité 20) — 730 jours, règles assouplies

> 💡 Personnalisez ou désactivez les politiques par défaut pour correspondre aux exigences de votre organisation.
`
  }
}
