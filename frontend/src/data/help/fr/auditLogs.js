export default {
  helpContent: {
    title: 'Journaux d\'audit',
    subtitle: 'Suivi des activités et conformité',
    overview: 'Piste d\'audit complète de toutes les opérations effectuées dans UCM. Suivez qui a fait quoi, quand et d\'où. Prend en charge le filtrage, la recherche, l\'exportation et la vérification d\'intégrité.',
    sections: [
      {
        title: 'Filtres',
        items: [
          { label: 'Type d\'action', text: 'Filtrer par type d\'opération (créer, mettre à jour, supprimer, connexion, etc.)' },
          { label: 'Utilisateur', text: 'Filtrer par l\'utilisateur qui a effectué l\'action' },
          { label: 'Statut', text: 'Afficher uniquement les opérations réussies ou échouées' },
          { label: 'Plage de dates', text: 'Définir des dates de/à pour restreindre la fenêtre temporelle' },
          { label: 'Recherche', text: 'Recherche textuelle libre dans toutes les entrées du journal' },
        ]
      },
      {
        title: 'Actions',
        items: [
          { label: 'Exporter', text: 'Télécharger les journaux au format JSON ou CSV' },
          { label: 'Nettoyage', text: 'Purger les anciens journaux avec une rétention configurable (jours)' },
          { label: 'Vérifier l\'intégrité', text: 'Vérifier l\'intégrité de la chaîne de journaux pour détecter les altérations' },
        ]
      },
    ],
    tips: [
      'Exportez régulièrement les journaux à des fins de conformité et d\'archivage',
      'Les tentatives de connexion échouées sont enregistrées avec l\'adresse IP source pour la surveillance de sécurité',
      'Les entrées de journal incluent le User Agent pour identifier les applications clientes',
    ],
    warnings: [
      'Le nettoyage des journaux est irréversible — les données exportées ne peuvent pas être réimportées',
    ],
  },
  helpGuides: {
    title: 'Journaux d\'audit',
    content: `
## Vue d'ensemble

Piste d'audit complète de toutes les opérations dans UCM. Chaque action — émission de certificat, révocation, connexion utilisateur, modification de paramètre — est enregistrée avec des détails sur qui, quoi, quand et d'où.

## Détails des entrées de journal

Chaque entrée de journal enregistre :
- **Horodatage** — Quand l'action a eu lieu
- **Utilisateur** — Qui a effectué l'action
- **Action** — Ce qui a été fait (créer, mettre à jour, supprimer, connexion, etc.)
- **Ressource** — Ce qui a été affecté (certificat, CA, utilisateur, etc.)
- **Statut** — Succès ou échec
- **Adresse IP** — IP source de la requête
- **User Agent** — Identifiant de l'application cliente
- **Détails** — Contexte supplémentaire (messages d'erreur, valeurs modifiées)

## Filtrage

### Par type d'action
Filtrer par catégorie d'opération :
- Opérations de certificat (émettre, révoquer, renouveler, exporter)
- Opérations de CA (créer, importer, supprimer)
- Opérations utilisateur (connexion, déconnexion, créer, mettre à jour)
- Opérations système (modification de paramètres, sauvegarde, restauration)

### Par utilisateur
Afficher uniquement les actions effectuées par un utilisateur spécifique.

### Par statut
- **Succès** — Opérations terminées avec succès
- **Échec** — Opérations ayant échoué (échecs d'authentification, permission refusée, erreurs)

### Par plage de dates
Définissez des dates **De** et **À** pour restreindre la fenêtre temporelle.

### Recherche textuelle
Recherche textuelle libre dans tous les champs du journal.

## Exportation

Exportez les journaux filtrés en :
- **JSON** — Lisible par machine, inclut tous les champs
- **CSV** — Compatible avec les tableurs, inclut les champs clés

Les exportations incluent uniquement les résultats actuellement filtrés.

## Nettoyage

Purgez les anciens journaux selon la période de rétention :
1. Cliquez sur **Nettoyage**
2. Définissez la période de rétention en jours
3. Confirmez le nettoyage

> ⚠ Le nettoyage des journaux est irréversible. Exportez les journaux importants avant la purge.

## Vérification d'intégrité

Cliquez sur **Vérifier l'intégrité** pour contrôler la chaîne de journaux d'audit. UCM utilise le chaînage de hachages pour détecter si des entrées de journal ont été altérées ou supprimées.

## Transfert Syslog

Configurez le transfert syslog distant dans **Paramètres → Audit** pour envoyer les événements de journal à un serveur SIEM ou syslog externe en temps réel.
`
  }
}
