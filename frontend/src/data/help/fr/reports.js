export default {
  helpContent: {
    title: 'Rapports',
    subtitle: 'Rapports de conformité et opérationnels',
    overview: 'Générez, téléchargez et programmez des rapports de conformité PKI. Les rapports fournissent une visibilité sur votre infrastructure de certificats pour l\'audit, la conformité et la planification opérationnelle.',
    sections: [
      {
        title: 'Types de rapports',
        items: [
          { label: 'Inventaire des certificats', text: 'Liste complète de tous les certificats avec les détails et le statut' },
          { label: 'Certificats expirants', text: 'Certificats expirant dans la fenêtre temporelle configurée' },
          { label: 'Hiérarchie des CA', text: 'Structure de l\'autorité de certification avec les comptages et le statut' },
          { label: 'Résumé d\'audit', text: 'Événements de sécurité et résumé de l\'activité des utilisateurs' },
          { label: 'Statut de conformité', text: 'Résumé de la conformité et des violations de politique' },
        ]
      },
      {
        title: 'Actions',
        items: [
          { label: 'Générer', text: 'Créer un aperçu sous forme de tableau formaté' },
          { label: 'Télécharger CSV', text: 'Exporter au format tableur pour Excel ou Google Sheets' },
          { label: 'Télécharger JSON', text: 'Exporter en données structurées pour l\'automatisation' },
          { label: 'Télécharger PDF', text: 'Rapport exécutif professionnel avec graphiques et recommandations' },
        ]
      },
      {
        title: 'Rapports programmés',
        items: [
          { label: 'Rapport d\'expiration (quotidien)', text: 'Vérification quotidienne automatique des certificats expirants avec notification par e-mail' },
          { label: 'Rapport de conformité (hebdomadaire)', text: 'Résumé hebdomadaire de la conformité aux politiques' },
          { label: 'Envoi test', text: 'Envoyer un rapport test à un destinataire pour vérifier la configuration SMTP' },
        ]
      },
    ],
    tips: [
      'Programmez le rapport d\'expiration en premier — c\'est le plus important pour la prévention des pannes',
      'Les rapports CSV sont plus faciles pour les parties prenantes non techniques',
      'Le rapport PDF inclut des éléments visuels (jauge de risque, distribution, chronologie) pour les présentations',
      'Les rapports programmés nécessitent que SMTP soit configuré dans Paramètres → E-mail',
    ],
  },
  helpGuides: {
    title: 'Rapports',
    content: `
## Vue d'ensemble

Générez, téléchargez et programmez des rapports de conformité PKI. Les rapports fournissent une visibilité sur votre infrastructure de certificats pour l'audit, la conformité et la planification opérationnelle.

## Types de rapports

### Inventaire des certificats
Liste complète de tous les certificats gérés par UCM. Inclut le sujet, l'émetteur, le numéro de série, les dates de validité, le type de clé et le statut actuel. À utiliser pour les audits de conformité et la documentation d'infrastructure.

### Certificats expirants
Certificats expirant dans une fenêtre temporelle spécifiée (par défaut : 30 jours). Critique pour éviter les pannes — consultez ce rapport régulièrement ou programmez-le pour une livraison quotidienne.

### Hiérarchie des CA
Structure de l'autorité de certification montrant les relations parent-enfant, les comptages de certificats par CA et le statut des CA. Utile pour comprendre votre topologie PKI.

### Résumé d'audit
Résumé des événements de sécurité et de l'activité des utilisateurs. Inclut les tentatives de connexion, les opérations de certificat, les violations de politique et les changements de configuration. Essentiel pour les audits de sécurité.

### Statut de conformité
Résumé de la conformité et des violations de politique. Montre quels certificats sont conformes à vos politiques et lesquels les violent. Requis pour la conformité réglementaire.

## Rapport PDF exécutif

Cliquez sur **Télécharger PDF** en haut à droite pour générer un rapport exécutif professionnel adapté aux revues de direction, présentations et audits de conformité.

### Contenu
Le rapport PDF comprend 9 sections :
1. **Page de couverture** — Métriques clés, jauge de risque et conclusions principales
2. **Table des matières** — Navigation rapide
3. **Résumé exécutif** — Santé globale de la PKI, distribution des certificats et niveau de risque
4. **Évaluation des risques** — Conclusions critiques, certificats expirants, algorithmes faibles
5. **Inventaire des certificats** — Répartition par statut, type de clé et CA émettrice
6. **Analyse de conformité** — Distribution des scores, répartition des notes, scores par catégorie
7. **Cycle de vie des certificats** — Chronologie d'expiration et taux d'automatisation
8. **Infrastructure CA** — Détails des CA racines et intermédiaires, hiérarchie
9. **Recommandations** — Actions concrètes basées sur l'état actuel de la PKI

### Graphiques et visuels
Le rapport inclut des éléments visuels : barre de jauge de risque, distribution des statuts, répartition des notes de conformité et chronologie d'expiration — conçus pour les parties prenantes non techniques.

> 💡 Le rapport PDF est généré à partir des données en direct. Téléchargez-le avant les réunions pour l'instantané le plus récent.

## Générer des rapports

1. Trouvez le rapport souhaité dans la liste
2. Cliquez sur **▶ Générer** pour créer un aperçu
3. L'aperçu apparaît ci-dessous sous forme de tableau formaté
4. Cliquez sur **Fermer** pour fermer l'aperçu

## Télécharger des rapports

Chaque ligne de rapport a des boutons de téléchargement :
- **CSV** — Format tableur pour Excel, Google Sheets ou LibreOffice
- **JSON** — Données structurées pour l'automatisation et l'intégration

> 💡 Les rapports CSV sont plus faciles pour les parties prenantes non techniques. JSON est mieux adapté pour les scripts et les intégrations API.

## Programmer des rapports

### Rapport d'expiration (quotidien)
Envoie automatiquement un rapport d'expiration de certificats chaque jour aux destinataires configurés. Activez ceci pour détecter les certificats expirants avant qu'ils ne causent des pannes.

### Rapport de conformité (hebdomadaire)
Envoie un résumé de conformité aux politiques chaque semaine. Utile pour un suivi continu de la conformité sans effort manuel.

### Configuration
1. Cliquez sur **Programmer les rapports** en haut à droite
2. Activez les rapports que vous souhaitez programmer
3. Ajoutez les adresses e-mail des destinataires (appuyez sur Entrée ou cliquez sur Ajouter)
4. Cliquez sur Enregistrer

### Envoi test
Avant d'activer les programmations, utilisez le bouton ✈️ sur n'importe quelle ligne de rapport pour envoyer un rapport test à une adresse e-mail spécifique. Cela vérifie que SMTP est correctement configuré et que le format du rapport répond à vos besoins.

> ⚠ Les rapports programmés nécessitent que SMTP soit configuré dans **Paramètres → E-mail**. L'envoi test échouera si SMTP n'est pas configuré.

## Permissions

- **read:reports** — Générer et télécharger des rapports
- **read:audit + export:audit** — Télécharger le rapport PDF exécutif
- **write:settings** — Configurer les programmations de rapports

> 💡 Programmez le rapport d'expiration en premier — c'est le plus précieux opérationnellement et aide à prévenir les pannes liées aux certificats.
`
  }
}
