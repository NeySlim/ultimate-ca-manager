export default {
  helpContent: {
    title: 'Rapports',
    subtitle: 'Rapports de conformité et d\'inventaire PKI',
    overview: 'Générez, téléchargez et programmez des rapports pour l\'audit de conformité. Les rapports couvrent l\'inventaire des certificats, les certificats expirants, la hiérarchie des AC, l\'activité d\'audit et le statut de conformité aux politiques. Téléchargez un rapport PDF exécutif pour les revues de direction.',
    sections: [
      {
        title: 'Types de rapports',
        items: [
          { label: 'Inventaire des certificats', text: 'Liste complète de tous les certificats avec leur statut' },
          { label: 'Certificats expirants', text: 'Certificats expirant dans une fenêtre temporelle spécifiée' },
          { label: 'Hiérarchie des AC', text: 'Structure et statistiques des autorités de certification' },
          { label: 'Résumé d\'audit', text: 'Les actions les plus fréquentes et les utilisateurs les plus actifs sur la période' },
          { label: 'Statut de conformité', text: 'Trois contrôles : certificats actifs, AC expirées et certificats expirant dans les 30 jours ; les politiques de certificat ne sont pas lues' },
          { label: 'Certificats révoqués', text: 'Certificats révoqués sur la période, avec date et raison' },
        ]
      },
      {
        title: 'Rapport PDF exécutif',
        items: [
          { label: 'Télécharger', text: 'Chaque modèle PDF est un rapport de la page : Télécharger le génère ; Composer un PDF… en assemble un à partir des sections choisies' },
          { label: 'Contenu', text: 'Résumé exécutif, évaluation des risques, inventaire des certificats, scores de conformité, infrastructure AC, activité d\'audit et recommandations' },
          { label: 'Graphiques et visuels', text: 'Inclut jauge de risque, distribution des statuts, chronologie d\'expiration et répartition de la conformité' },
        ]
      },
      {
        title: 'Programmation',
        items: [
          { label: 'Planifier un rapport', text: 'Choisissez n\'importe quel rapport de données ou modèle PDF, puis sa fréquence (quotidienne, hebdomadaire ou mensuelle), son heure (saisie et affichée dans votre fuseau ; une exécution hebdomadaire ou mensuelle qui tomberait un autre jour pour vous garde son heure UTC, signalée), son format et ses destinataires ; les rapports planifiés sont groupés par prochaine exécution' },
          { label: 'Pièce jointe', text: 'Le rapport est joint à l\'e-mail dans son format : CSV ou JSON pour les rapports de données, PDF pour les modèles PDF' },
        ]
      },
    ],
    tips: [
      'Utilisez le rapport PDF exécutif pour les revues de direction et les audits de conformité.',
      'Téléchargez les rapports en CSV pour l\'analyse en tableur ou en JSON pour l\'automatisation.',
      'Utilisez la fonction d\'envoi test pour vérifier la livraison des e-mails avant d\'activer les programmations.',
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
Certificats expirant dans une fenêtre temporelle spécifiée (par défaut : 30 jours). Critique pour éviter les pannes, consultez ce rapport régulièrement ou programmez-le pour une livraison quotidienne.

### Hiérarchie des AC
Structure de l'autorité de certification montrant les relations parent-enfant, les comptages de certificats par AC. Utile pour comprendre votre topologie PKI.

### Résumé d'audit
Les dix actions les plus fréquentes et les dix utilisateurs les plus actifs sur la période.

### Statut de conformité
Trois contrôles avec un nombre et une gravité : certificats actifs, AC expirées et certificats expirant dans les 30 jours. Il ne lit pas les politiques de certificat.

### Certificats révoqués
Certificats révoqués sur la période choisie (30 jours par défaut), avec la date et la raison de révocation. Consultez-le pour suivre les révocations et leurs causes.

## Rapport PDF exécutif

Le modèle **Résumé exécutif** est l'un des rapports de la page : son bouton **Télécharger** génère le PDF, adapté aux revues de direction, présentations et audits de conformité. **Composer un PDF…** dans l'en-tête de la page (sous la file sur un téléphone) en assemble un à partir des sections choisies.

### Contenu
Le rapport PDF comprend 9 sections :
1. **Page de couverture** : Métriques clés, jauge de risque et conclusions principales
2. **Table des matières** : Navigation rapide
3. **Résumé exécutif** : Santé globale de la PKI, distribution des certificats et niveau de risque
4. **Évaluation des risques** : Conclusions critiques, certificats expirants, algorithmes faibles
5. **Inventaire des certificats** : Répartition par statut, type de clé et AC émettrice
6. **Analyse de conformité** : Distribution des scores, répartition des notes, scores par catégorie
7. **Cycle de vie des certificats** : Chronologie d'expiration et taux d'automatisation
8. **Infrastructure AC** : Détails des AC racines et intermédiaires, hiérarchie
9. **Recommandations** : Actions concrètes basées sur l'état actuel de la PKI

### Graphiques et visuels
Le rapport inclut des éléments visuels : barre de jauge de risque, distribution des statuts, répartition des notes de conformité et chronologie d'expiration, conçus pour les parties prenantes non techniques.

> 💡 Le rapport PDF est généré à partir des données en direct. Téléchargez-le avant les réunions pour l'instantané le plus récent.

## La file

Les rapports planifiés sont groupés par prochaine exécution : **Prochaine exécution sous 24 h**, puis **Planifiés**. Une ligne donne le rapport, sa fréquence et son heure dans une pastille (dans votre fuseau ; une exécution hebdomadaire ou mensuelle qui tomberait un autre jour pour vous garde son heure UTC, signalée), le chiffre actuel quand les compteurs des certificats le donnent (Certificats expirants) ou sinon son format, ses destinataires, et la prochaine exécution en forme courte au-dessus de sa date exacte. Les rapports sans planification sont repliés sous **Non planifiés**, chacun avec **Télécharger** et **Planifier…**.

## Consulter un rapport

Le nom d'un rapport l'ouvre dans l'inspecteur :
- **Rapport** : sa planification et le chiffre actuel : pour les certificats expirants, celui des compteurs (la fenêtre de 30 jours de la vue d’ensemble, hors certificats révoqués) ; pour les autres rapports de données, **Calculer** ; l'inventaire, les certificats expirants et les certificats révoqués offrent **Voir ces certificats**
- **Exécutions** : le serveur ne fournit pas d'historique des exécutions ; la planification et la prochaine exécution sont ce qui est connu
- **Aperçu** : **Générer** produit le rapport maintenant et montre ses lignes (les 200 premières ; le téléchargement les contient toutes)

## Télécharger des rapports

**Télécharger** sur une ligne, ou dans l'inspecteur, génère le rapport maintenant dans le format de sa planification : CSV par défaut, JSON s'il est choisi, PDF pour un modèle. Cocher plusieurs lignes les télécharge l'une après l'autre : un seul message quand toutes sont passées, sinon le bilan dit lesquelles ont échoué.

> 💡 Les rapports CSV sont plus faciles pour les parties prenantes non techniques. JSON est mieux adapté pour les scripts et les intégrations API.

## Programmer des rapports

### Ce qui peut être planifié
Chaque rapport de données et chaque modèle PDF peut être planifié, avec sa propre fréquence, son heure et ses destinataires. Planifiez **Certificats expirants** chaque jour pour détecter les certificats expirants avant qu'ils ne causent des pannes.

### Fréquence
**Quotidienne**, **Hebdomadaire** (choisissez le jour de la semaine) ou **Mensuelle** (choisissez le jour du mois). Le planificateur tourne en UTC : l’heure se saisit dans votre fuseau, comme la file l’affiche, et se convertit à l’enregistrement ; une exécution hebdomadaire ou mensuelle dont la conversion changerait le jour se saisit en UTC, comme le dialogue le dit.

### Configuration
1. Cliquez sur **Planifier un rapport**, ou sur **Planifier…** sur un rapport replié sous **Non planifiés**
2. Choisissez le contenu, la fréquence et son jour, l’heure d’envoi (dans votre fuseau) et, pour un rapport de données, le format (CSV ou JSON)
3. Indiquez un ou plusieurs destinataires, séparés par des virgules : sans destinataire, rien n'est envoyé
4. Cliquez sur **Planifier**

Chaque rapport programmé est joint à l'e-mail dans son format : CSV ou JSON pour les rapports de données, PDF pour les modèles PDF. **Modifier la planification…** et **Suspendre la planification** sont dans le menu « ⋯ » de l'inspecteur ; cocher plusieurs lignes les suspend ensemble, en une seule mise à jour.

### Envoi test
Avant de compter sur une planification, utilisez **Envoyer un test…** dans le menu « ⋯ » de l'inspecteur d'un rapport pour l'envoyer à une adresse e-mail. Cela vérifie que SMTP est correctement configuré et que le format du rapport répond à vos besoins.

> ⚠ Les rapports programmés nécessitent que SMTP soit configuré dans **Paramètres → E-mail**. L'envoi test échouera si SMTP n'est pas configuré.

## Permissions

- **read:audit** : Générer et consulter des rapports ; le téléchargement exige aussi **export:audit**
- **read:audit + export:audit** : Télécharger le rapport PDF exécutif
- **write:settings** : Configurer les programmations de rapports

> 💡 Programmez d'abord le rapport Certificats expirants : c'est le plus précieux opérationnellement et aide à prévenir les pannes liées aux certificats.
`
  }
}
