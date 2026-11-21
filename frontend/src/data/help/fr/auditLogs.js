export default {
  helpContent: {
    title: 'Activité',
    subtitle: 'Le journal d’audit de chaque opération',
    overview: 'Chaque opération effectuée dans UCM, du certificat au journal : qui a fait quoi, quand, d’où, avec quel résultat. La liste lit le serveur page par page ; les filtres, l’export, la vérification d’intégrité et le nettoyage portent sur tout le journal.',
    sections: [
      {
        title: 'Trouver une entrée',
        items: [
          { label: 'Recherche', text: 'Texte libre dans le nom d’utilisateur, le code d’action, les détails, le type de ressource et l’adresse IP ; le nom de la ressource lui-même n’est pas recherché' },
          { label: 'Type d’opération', text: 'Émissions, renouvellements, révocations, connexions, utilisateurs, paramètres et les autres types regroupent chacun des codes d’action du serveur' },
          { label: 'Filtres', text: 'Dates, utilisateur, résultat et codes d’action un par un ; chaque filtre actif apparaît en pastille sous la barre d’outils, avec son bouton pour le retirer' },
          { label: 'Raccourcis et filtres enregistrés', text: 'Connexions échouées ou tous les échecs en un clic ; les filtres en cours s’enregistrent sous un nom et se réappliquent (gardés dans ce navigateur)' },
          { label: 'Détail', text: 'Le nom de la ressource ou la flèche d’une ligne ouvre l’entrée : son texte, l’utilisateur, la date et l’heure, le résultat, le code d’action, l’adresse IP et le client ; Inspecter le certificat (ou Voir l’autorité) ouvre ce que l’entrée nomme. Sur un téléphone, chaque entrée est une carte qui s’ouvre d’un appui n’importe où' },
        ]
      },
      {
        title: 'Actions du journal',
        items: [
          { label: 'Exporter le journal', text: 'CSV ou JSON, avec la recherche et les filtres en cours, 10 000 entrées au plus ; sur un téléphone, dans le menu « ⋯ »' },
          { label: 'Vérifier l’intégrité', text: 'Dans le menu « ⋯ » : contrôle la chaîne d’empreintes du journal ; sur un gros journal, elle tourne en tâche de fond, son avancement et Annuler la vérification s’affichent dans la ligne de résumé' },
          { label: 'Nettoyer les anciens journaux', text: 'Dans le menu « ⋯ », avec le droit de supprimer le journal : supprime les entrées plus anciennes qu’une durée de conservation de 30 à 365 jours' },
        ]
      },
    ],
    tips: [
      'Exportez régulièrement le journal à des fins de conformité et d’archivage',
      'Les connexions échouées sont enregistrées avec leur adresse IP source, et chaque entrée avec son client (user agent)',
      'Le « Voir son activité » d’un certificat ouvre cette page sur une recherche de son nom',
    ],
    warnings: [
      'Le nettoyage est irréversible : un journal exporté ne peut pas être réimporté',
    ],
  },
  helpGuides: {
    title: 'Activité',
    content: `
## Vue d’ensemble

Chaque opération d’UCM s’inscrit au journal d’audit : émission de certificat, révocation, connexion, modification de paramètre. La page Activité le liste, du plus récent au plus ancien, avec qui, quoi, quand et le résultat. L’en-tête compte les entrées de tout le journal ; la ligne de résumé sous la barre d’outils compte celles que gardent les filtres, dit depuis quand remonte le journal et résume les 30 derniers jours.

## Une entrée

Chaque ligne montre l’heure (et le jour quand ce n’est pas aujourd’hui), l’opération (le pictogramme de son type et le code d’action), la ressource, l’utilisateur et le résultat (Réussi ou Échec, en toutes lettres). Le nom de la ressource ou la flèche ouvre le détail de l’entrée :
- **Texte** : ce que le serveur a enregistré (messages d’erreur, valeurs)
- **Ressource**, **Utilisateur**, **Date / heure**, **Résultat**
- **Action** : le code tel que le serveur le stocke
- **Adresse IP** et **Client** (user agent), quand ils ont été enregistrés

Quand l’entrée nomme un certificat ou une autorité, **Inspecter le certificat** (ou **Voir l’autorité**) l’ouvre dans l’inspecteur.

Sur un téléphone, chaque entrée est une carte qui montre les mêmes informations : un appui n’importe où sur elle, ou sur sa flèche, ouvre le détail.

## Trouver des entrées

### Recherche
Texte libre dans le nom d’utilisateur, le code d’action, les détails, le type de ressource et l’adresse IP ; le nom de la ressource lui-même n’est pas recherché.

### Type d’opération
La liste de la barre d’outils regroupe les codes d’action par type : émissions, renouvellements, révocations, exports, certificats et CSR, approbations, publications CRL, ACME, SCEP, connexions, utilisateurs, sauvegardes, paramètres, configuration, système. Seuls les types présents dans le journal sont proposés.

### Filtres
Le bouton **Filtres** ouvre les dates (**Du**, **Au**), l’**Utilisateur**, le **Résultat** et les codes d’action un par un (restreints au type choisi). Deux raccourcis posent **Connexions échouées** ou **Tous les échecs**. Les filtres en cours s’enregistrent sous un nom et se réappliquent plus tard ; ils sont gardés dans ce navigateur. Chaque filtre actif apparaît en pastille sous la barre d’outils, et **Réinitialiser les filtres** les retire tous.

La liste est lue page par page sur le serveur : 25, 50 ou 100 entrées par page, précédente et suivante, ou un numéro de page et **Aller**.

## Exportation

**Exporter le journal** télécharge les entrées que gardent la recherche et les filtres, 10 000 au plus :
- **CSV** : une ligne par entrée, pour un tableur
- **JSON** : données structurées, tous les champs

Sur un téléphone, le bouton de l’en-tête est masqué : l’export est dans le menu « ⋯ ».

## Nettoyage

Dans le menu « ⋯ », avec le droit de supprimer le journal :
1. Choisissez **Nettoyer les anciens journaux…**
2. Indiquez la durée de conservation en jours (30 à 365)
3. Choisissez **Supprimer les anciens journaux**

> ⚠ Le nettoyage est irréversible. Exportez d’abord les entrées utiles.

## Vérification d’intégrité

**Vérifier l’intégrité**, dans le menu « ⋯ », contrôle la chaîne du journal d’audit. UCM utilise le chaînage de hachages pour détecter une entrée modifiée ou supprimée à l’intérieur de la chaîne ; la suppression des dernières entrées ne laisse aucune trace dans la chaîne elle-même, c’est pourquoi le transfert syslog en garde une copie ailleurs.

Sur un gros journal, la vérification tourne en tâche de fond : la ligne de résumé indique combien d’entrées sont déjà contrôlées, **Annuler la vérification** l’arrête, et quitter ou recharger la page ne l’arrête pas (la page la reprend). Une seule vérification tourne à la fois.

## Transfert Syslog

Configurez le transfert syslog distant dans **Paramètres → Audit** pour envoyer les événements de journal à un serveur SIEM ou syslog externe en temps réel.

Tout événement d’audit est transmis par défaut. Décocher une catégorie (Certificats, AC, CSR, Utilisateurs, ACME, SCEP, Système) n’arrête que ses événements : ACME couvre tous les événements ACME, Utilisateurs couvre les connexions et déconnexions, SSO compris. Laisser toutes les cases décochées transmet tous les événements. Les modifications de compte (création, rôle, mot de passe, MFA, activation), les modifications du transfert syslog lui-même, les purges d’audit, les clés d’API, les rôles, les paramètres et les politiques sont toujours transmis. Sous Système, les téléchargements de clé maître, les changements de chiffrement, les restaurations, les réinitialisations et bascules de base de données, les paramètres de mise à jour, les suppressions de sauvegardes et les téléchargements de lots de journaux sont aussi toujours transmis. Une modification syslog est envoyée avec la configuration précédente : le collecteur dont le périmètre est réduit ou qui est désactivé la reçoit, et un collecteur nouvellement configuré la reçoit aussi.
`
  }
}
