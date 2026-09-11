export default {
  helpContent: {
    title: 'Récupération de clés',
    subtitle: 'Récupérer les clés privées archivées sous double contrôle',
    overview: 'La récupération de clés permet de retrouver la clé privée archivée d\'un certificat déjà émis via un flux de travail soumis à approbation et entièrement audité. Elle existe pour les clés qui n\'ont pas été exportées au moment de l\'émission (le préréglage ne le permettait pas, ou l\'export a été omis) et qui sont nécessaires plus tard — avec une piste d\'approbation attachée à la récupération.',
    sections: [
      {
        title: 'Flux de travail',
        items: [
          { label: 'Demande', text: 'Un utilisateur demande la récupération de la clé archivée d\'un certificat spécifique, avec un motif' },
          { label: 'Approbation (quatre yeux)', text: 'Un second opérateur autorisé examine et approuve — le demandeur ne peut pas approuver sa propre demande' },
          { label: 'Téléchargement', text: 'Une fois approuvée, la clé est délivrée sous forme d\'archive PKCS#12 protégée par mot de passe' },
        ]
      },
      {
        title: 'Prérequis',
        items: [
          { label: 'Clé archivée', text: 'La clé privée du certificat doit être stockée dans la base de données — la récupération ne peut pas reconstruire une clé qui n\'a jamais été archivée' },
          { label: 'Double contrôle', text: 'La demande et l\'approbation sont des actions distinctes effectuées par des personnes différentes ; chaque étape est consignée dans la piste d\'audit' },
        ]
      },
    ],
    tips: [
      'La récupération de clés concerne les clés qui n\'ont pas été exportées lors de l\'émission du certificat ; elle ne remplace pas la restriction de l\'export de clés au moment de l\'émission.',
      'Chaque demande, approbation et téléchargement est enregistré dans la piste d\'audit à des fins de conformité.',
    ],
    warnings: [
      'Un certificat dont la clé privée n\'a jamais été archivée ne peut pas être récupéré — il n\'y a rien à délivrer.',
    ],
  },
  helpGuides: {
    title: 'Récupération de clés',
    content: `
## Vue d'ensemble

La récupération de clés permet de retrouver la **clé privée archivée** d'un certificat déjà émis via un flux de travail soumis à approbation et entièrement audité. Elle est destinée aux clés qui n'ont **pas été exportées au moment de l'émission** — le préréglage n'autorisait pas l'export, ou celui-ci a simplement été omis — et qui sont nécessaires plus tard, avec une piste d'approbation attachée à la récupération.

La récupération ne fonctionne que si la clé privée a été archivée (stockée dans la base de données) lors de l'émission. Elle ne peut pas reconstruire une clé qui n'a jamais été conservée.

## Flux de travail

### 1. Demande
Un utilisateur ouvre une demande de récupération pour un certificat spécifique et fournit un motif. La demande est enregistrée et passe à l'état en attente.

### 2. Approbation (quatre yeux)
Un second opérateur autorisé examine la demande et l'approuve. Le demandeur **ne peut pas approuver sa propre demande** — la demande et l'approbation sont des actions distinctes effectuées par des personnes différentes (double contrôle).

### 3. Téléchargement
Une fois approuvée, la clé archivée est délivrée sous forme d'archive **PKCS#12 protégée par mot de passe**. Le téléchargement est consigné dans la piste d'audit.

## Prérequis

- **Clé archivée** — la clé privée du certificat doit être présente dans la base de données. Les certificats dont la clé n'a jamais été archivée ne peuvent pas être récupérés.
- **Double contrôle** — la demande et l'approbation sont des étapes distinctes effectuées par des utilisateurs différents.

## Permissions

- **read:key_recovery** — Demander une récupération et consulter les demandes
- **admin** — Approuver ou refuser une demande de récupération en attente
- **read:private_keys** — Portée réservée aux administrateurs, requise pour l'export *direct* de clé privée depuis la page Certificats (en contournant ce flux)

## Ce que c'est (et ce que ce n'est pas)

La récupération de clés ajoute une **piste d'approbation** à la récupération d'une clé archivée après l'émission. Elle ne remplace pas la restriction de l'export des clés privées dans les préréglages — si un rôle peut déjà exporter des clés directement, il s'agit d'un chemin d'accès distinct à contrôler en tant que tel.

> 💡 Chaque demande, approbation et téléchargement est consigné dans la piste d'audit à des fins de conformité.
`
  }
}
