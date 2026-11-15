export default {
  helpContent: {
    title: "Journaux système",
    subtitle: "Le journal applicatif du serveur",
    overview: "Relit ce que UCM a écrit, sans accès shell à l'hôte. C'est le journal qui explique un échec de protocole dont aucun enregistrement n'a été créé : une inscription SCEP refusée à la validation est rejetée avant qu'une ligne de demande existe, et n'apparaît donc qu'ici.",
    sections: [
      {
        title: "Sources",
        items: [
          { label: "Application", text: "Le journal propre à UCM. Seule source à porter des composants" },
          { label: "Accès", text: "Journal d'accès Gunicorn, avec les requêtes HTTP et les codes de statut, installations natives uniquement" },
          { label: "Erreurs", text: "Journal d'erreurs Gunicorn, avec le démarrage des workers et les traces non gérées, natives uniquement" },
          { label: "Journal", text: "Le journal de l'unité systemd, là où l'utilisateur du service peut le lire" },
        ]
      },
      {
        title: "Filtres",
        items: [
          { label: "Source", text: "Quel journal est lu. Seules les sources réellement présentes sont proposées" },
          { label: "Composant", text: "Un sous-système du journal applicatif, ou tous. Tous y figurent, pas seulement ceux affichés" },
          { label: "Niveau de journal", text: "Un plancher, pas une correspondance exacte. WARNING montre aussi erreurs et critiques" },
          { label: "Recherche", text: "Insensible à la casse, sur le message et le nom du composant. C'est du texte, pas un motif" },
          { label: "Exclure", text: "Retire les lignes correspondantes, le plus rapide pour faire taire un battement" },
          { label: "Date", text: "Une fenêtre De/À, appliquée sur le serveur" },
          { label: "Lignes", text: "Combien de lignes correspondantes renvoyer, de la plus récente à la plus ancienne" },
        ]
      },
      {
        title: "Journaux en direct",
        items: [
          "Interroge toutes les cinq secondes ; la ligne la plus récente est la première",
          "Efface la fenêtre de dates, qui pose la question inverse",
        ]
      },
    ],
    tips: [
      "Les horodatages sont à l'heure locale du serveur sans décalage ; la zone est indiquée en bas de page",
      "Une ligne sans format connu est tout de même affichée, sans niveau, plutôt que masquée",
      "Une trace est une entrée, pas une par ligne : la cellule du message se replie et l'affiche en entier",
      "Les secrets sont expurgés côté serveur avant toute sortie du processus",
    ],
    warnings: [
      "Un composant sans écriture récente reste listé : le choisir peut ne rien renvoyer",
      "La lecture est réservée aux administrateurs et n'est volontairement pas auditée : la piste d'audit est répercutée dans ce même journal, et consigner chaque lecture enfouirait les lignes qu'elle existe pour mettre en évidence",
    ],
  },
  helpGuides: {
    title: "Journaux système",
    content: `
## Vue d'ensemble

Relit ce qu'UCM a lui-même écrit, sans accès shell à l'hôte. C'est le journal qui explique un échec pour lequel aucun enregistrement n'a jamais été créé : une inscription SCEP refusée à la validation est rejetée avant qu'une ligne de demande existe, elle apparaît donc ici et nulle part ailleurs.

Les lignes sont affichées de la plus récente à la plus ancienne, et tous les filtres s'appliquent côté serveur : un filtre ne masque donc jamais des lignes simplement non récupérées.

## Sources

**Source** et **Composant** sont dans le panneau de filtres : choisissez le journal, puis restreignez à un sous-système.

- **Application** : le journal propre à UCM. Seule source à porter des composants.
- **Accès** : le journal d'accès Gunicorn, qui contient les requêtes HTTP et les codes de statut. Installations natives uniquement.
- **Erreurs** : le journal d'erreurs Gunicorn, qui contient le démarrage des workers et les tracebacks non gérés. Installations natives uniquement.
- **Journal** : le journal de l'unité systemd, là où l'utilisateur du service peut le lire.

Seules les sources que ce déploiement possède réellement sont proposées. Une source sans rien derrière est omise plutôt qu'affichée vide.

### Composants

**Tous les composants** désigne le journal applicatif entier. La liste contient tous les sous-systèmes depuis lesquels UCM peut écrire (\`services\`, \`api\`, \`utils\`, \`security\` et les autres), qu'ils aient écrit récemment ou non, ainsi que les loggers précis d'où viennent les lignes affichées.

En choisir un prend tout ce qui est dessous. \`services\` couvre \`services.scep.scep_service\` et tout autre service ; \`services.scep\` restreint au sous-arbre SCEP.

## Filtres

### Niveau de journal
Un plancher, pas une correspondance exacte : **WARNING** montre les avertissements, les erreurs et les critiques. **DEBUG** montre tout.

Une ligne dont le niveau n'a pas pu être lu n'est jamais masquée par ce filtre : sa gravité est inconnue, et la deviner masquerait les lignes qui méritent le plus d'être vues.

### Recherche et Exclure
Les deux parcourent le message et le nom du composant, sans tenir compte de la casse. **Exclure** retire ce qui correspond : le moyen le plus rapide de faire taire un battement qui revient chaque minute et enfouit l'unique erreur.

Les deux sont du texte littéral et non des motifs : \`.*\` ne trouve que ces deux caractères. Un motif venu du navigateur serait un travail sans borne pour l'unique worker qui répond à ACME, SCEP et OCSP depuis ce même processus.

### Date
Une fenêtre **De**/**À**, appliquée côté serveur. Contrairement au plancher de niveau, une ligne sans horodatage est exclue dès qu'une borne est définie : une fenêtre demande un instant, et une telle ligne n'en a pas.

### Lignes
Combien de lignes correspondantes renvoyer, de 100 à 5000. Le pied de page indique quand des lignes plus anciennes ont été laissées de côté, et combien correspondaient au total.

## Journaux en direct

Interroge toutes les cinq secondes. Efface la fenêtre de dates, qui pose la question inverse, et c'est le moyen le plus rapide de suivre une inscription ou un renouvellement en temps réel.

## Copier

**Tout copier** prend toutes les lignes affichées. Cochez la case à côté d'une ligne et l'action devient **Copier la sélection**. Les deux copient une ligne telle que le fichier l'écrit : heure, composant, niveau, message. Ce qui arrive dans le presse-papiers se lit comme un journal, et le recoller dans cette page s'analyse comme tel.

## Lire le pied de page

Le pied de la page nomme le fichier lu, le fuseau horaire dans lequel ses horodatages sont écrits, et si quelque chose a été coupé :

- **Affichage des N lignes les plus récentes sur M correspondantes** : davantage de lignes correspondaient que ne l'autorise **Lignes**. Augmentez-le pour remonter plus loin.
- **Seule la partie la plus récente du fichier a été lue** : le fichier dépasse la fenêtre que parcourt le lecteur, les lignes plus anciennes sont donc hors d'atteinte quel que soit le nombre de lignes.

Les horodatages ne portent pas de décalage propre : c'est l'heure locale du serveur, et le fuseau est indiqué à côté du chemin.

## Accès

La lecture de ce journal exige des droits d'administrateur. Elle n'est volontairement pas auditée : la piste d'audit s'écrit dans ce même journal, et consigner chaque lecture enfouirait les lignes que la page existe pour mettre en évidence. Le lot de diagnostic de **Paramètres → À propos** est audité, étant un acte rare et délibéré qui repart avec une copie du fichier.
`
  }
}
