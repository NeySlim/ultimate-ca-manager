export default {
  helpContent: {
    title: 'Demandes d\'approbation',
    subtitle: 'Flux de travail d\'émission de certificats',
    overview: 'Examinez et approuvez ou rejetez les demandes de certificats qui nécessitent une approbation manuelle. Les flux d\'approbation sont configurés dans les politiques et s\'appliquent automatiquement lors de l\'émission de certificats.',
    sections: [
      {
        title: 'Cycle de vie des demandes',
        definitions: [
          { term: 'En attente', description: 'En attente d\'examen — le certificat ne peut pas être émis tant que les approbateurs n\'ont pas approuvé' },
          { term: 'Approuvée', description: 'Toutes les approbations requises ont été reçues — le certificat est émis automatiquement' },
          { term: 'Rejetée', description: 'Tout rejet unique arrête immédiatement la demande' },
          { term: 'Expirée', description: 'La demande n\'a pas été examinée avant l\'échéance' },
        ]
      },
      {
        title: 'Actions',
        items: [
          { label: 'Approuver', text: 'Examiner les détails du certificat et approuver la demande — un commentaire optionnel peut être ajouté' },
          { label: 'Rejeter', text: 'Rejeter la demande avec un motif obligatoire — la demande est immédiatement arrêtée' },
        ]
      },
      {
        title: 'Filtrage',
        items: [
          { label: 'En attente', text: 'Demandes en attente de votre examen' },
          { label: 'Approuvées', text: 'Demandes récemment approuvées' },
          { label: 'Rejetées', text: 'Demandes rejetées avec motifs' },
          { label: 'Total', text: 'Toutes les demandes quel que soit le statut' },
        ]
      },
    ],
    tips: [
      'Configurez les notifications par e-mail dans les politiques pour alerter les approbateurs lorsque de nouvelles demandes arrivent',
      'Chaque approbation/rejet est enregistré avec l\'utilisateur et l\'horodatage pour la conformité d\'audit',
    ],
    warnings: [
      'Tout rejet unique arrête la demande entière — c\'est intentionnel pour la sécurité',
    ],
  },
  helpGuides: {
    title: 'Demandes d\'approbation',
    content: `
## Vue d'ensemble

La page des approbations affiche toutes les demandes de certificats qui nécessitent une approbation manuelle avant l'émission. Les flux d'approbation sont configurés dans les **politiques** — lorsqu'une politique a « Approbation requise » activé, toute demande de certificat correspondante crée une demande d'approbation ici.

## Cycle de vie des demandes

### En attente
La demande est en attente d'examen. Le certificat ne peut pas être émis tant que le nombre requis d'approbateurs n'a pas approuvé. Les demandes en attente apparaissent en premier par défaut.

### Approuvée
Toutes les approbations requises ont été reçues. Le certificat sera émis automatiquement une fois approuvé.

### Rejetée
Tout rejet unique arrête immédiatement la demande. Le certificat ne sera pas émis. Un commentaire de rejet est requis pour expliquer le motif.

### Expirée
La demande n'a pas été examinée avant l'échéance. Les demandes expirées doivent être soumises à nouveau.

## Approuver une demande

1. Cliquez sur une demande en attente pour voir ses détails
2. Examinez les détails du certificat, le demandeur et la politique associée
3. Cliquez sur **Approuver** et ajoutez optionnellement un commentaire
4. L'approbation est enregistrée avec votre nom d'utilisateur et l'horodatage

## Rejeter une demande

1. Cliquez sur une demande en attente pour voir ses détails
2. Cliquez sur **Rejeter**
3. Entrez un **motif de rejet** (requis) — cela est enregistré pour la conformité d'audit
4. La demande est immédiatement arrêtée

> ⚠ Tout rejet unique arrête la demande entière. C'est intentionnel — si un examinateur identifie un problème, l'émission ne doit pas se poursuivre.

## Historique des approbations

Chaque demande maintient un historique d'approbation complet montrant :
- Qui a approuvé ou rejeté (nom d'utilisateur)
- Quand l'action a été effectuée (horodatage)
- Commentaire fourni (le cas échéant)

Cet historique est immuable et fait partie de la piste d'audit.

## Filtrage

Utilisez la barre de filtre de statut en haut pour afficher :
- **En attente** — Demandes en attente de votre examen
- **Approuvées** — Demandes récemment approuvées
- **Rejetées** — Demandes rejetées avec motifs
- **Total** — Toutes les demandes quel que soit le statut

## Permissions

- **read:approvals** — Voir les demandes d'approbation
- **write:approvals** — Approuver ou rejeter les demandes

> 💡 Configurez les notifications par e-mail dans les politiques pour alerter les approbateurs lorsque de nouvelles demandes arrivent.
`
  }
}
