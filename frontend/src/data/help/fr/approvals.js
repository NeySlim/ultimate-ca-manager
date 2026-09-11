export default {
  helpContent: {
    title: 'Demandes d\'approbation',
    subtitle: 'Gestion du flux d\'approbation de certificats',
    overview: 'Examinez et gérez les demandes d\'approbation de certificats. Lorsqu\'une politique exige une approbation, l\'émission du certificat est suspendue jusqu\'à ce que le nombre requis d\'approbateurs aient examiné et approuvé la demande.',
    sections: [
      {
        title: 'Cycle de vie des demandes',
        items: [
          { label: 'En attente', text: 'En attente d\'examen — le certificat ne peut pas encore être émis' },
          { label: 'Approuvée', text: 'Toutes les approbations requises ont été reçues — le certificat peut être émis' },
          { label: 'Rejetée', text: 'Tout rejet arrête immédiatement la demande' },
          { label: 'Expirée', text: 'Non décidée sous sept jours ; clôturée comme expirée et jamais comptée comme en attente' },
        ]
      },
      {
        title: 'Origine des demandes',
        items: [
          { label: 'Formulaire d\'émission', text: 'Une demande de certificat correspondant à une politique qui exige une approbation' },
          { label: 'Signature de CSR et signature en masse', text: 'La signature d\'une requête stockée, seule ou depuis Opérations, est mise en file de la même façon ; l\'approbation effectue la signature' },
          { label: 'Renouvellement', text: 'Le renouvellement d\'un certificat, seul ou en masse, est également mis en file ; un renouvellement impossible à honorer (révoqué, clé non détenue par le serveur) est refusé immédiatement' },
          { label: 'Administrateurs', text: 'Contournent la file sur tous les chemins, comme sur le formulaire d\'émission' },
        ]
      },
      {
        title: 'Demandes clôturées à votre place',
        items: [
          { label: 'Signée ou renouvelée directement', text: 'Une demande en file dont la cible a entre-temps été signée ou renouvelée par un administrateur est clôturée comme approuvée par cette action et liée au certificat' },
          { label: 'Supprimée ou révoquée', text: 'Une demande dont la cible a été supprimée ou révoquée est clôturée comme rejetée ; une suspension de certificat laisse la demande de renouvellement en attente jusqu\'à la levée de la suspension' },
          { label: 'Déjà satisfaite', text: 'Approuver une demande déjà satisfaite la clôture sur le certificat existant ; approuver l\'une de plusieurs demandes pour la même cible clôture les autres comme approuvées par vous' },
          { label: 'Cible disparue', text: 'Approuver une demande dont la requête stockée, le certificat ou la CA n\'existe plus la clôture comme rejetée' },
          { label: 'Échéance', text: 'Une demande attend sept jours ; passé ce délai, elle est clôturée comme expirée, jamais comptée comme en attente, et le planificateur de renouvellement reprend pour son certificat' },
        ]
      },
    ],
    tips: [
      'Tout rejet unique arrête immédiatement l\'approbation — c\'est intentionnel pour la sécurité.',
      'Tant qu\'un renouvellement attend une approbation, le planificateur laisse le certificat à cette décision, tant qu\'elle peut intervenir avant l\'expiration du certificat.',
      'Les commentaires d\'approbation sont enregistrés dans la piste d\'audit pour la conformité.',
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
La demande n'a pas été décidée sous sept jours. Les demandes expirées doivent être soumises à nouveau.

## Origine des demandes

Au-delà du formulaire d'émission, une politique qui exige une approbation met aussi en file :
- **Signature de CSR** et **signature en masse** depuis Opérations : l'approbation effectue la signature
- **Renouvellement** et **renouvellement en masse** : l'approbation effectue le renouvellement ; un renouvellement impossible à honorer (certificat révoqué, clé non détenue par le serveur) est refusé immédiatement au lieu d'être mis en file

Les administrateurs contournent la file sur tous les chemins.

## Demandes clôturées à votre place

- Une demande en file dont la cible a entre-temps été **signée ou renouvelée directement** par un administrateur est clôturée comme approuvée par cette action et liée au certificat
- Une demande dont la cible a été **supprimée ou révoquée** est clôturée comme rejetée ; une suspension de certificat laisse la demande de renouvellement en attente jusqu'à la levée de la suspension
- Approuver une demande **déjà satisfaite** la clôture sur le certificat existant ; approuver l'une de plusieurs demandes pour la même cible clôture les autres comme approuvées par vous
- Approuver une demande dont la requête stockée, le certificat ou la CA **n'existe plus** la clôture comme rejetée

Les webhooks sont notifiés de ces clôtures comme pour un rejet.

## Échéance

Une demande attend **sept jours** une décision. Passé ce délai, elle est clôturée comme expirée, n'est jamais comptée comme en attente, et le planificateur de renouvellement reprend pour son certificat. Tant qu'un renouvellement attend une approbation, le planificateur laisse le certificat à cette décision, tant qu'elle peut intervenir avant l'expiration du certificat.

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
