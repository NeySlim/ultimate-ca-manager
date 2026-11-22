export default {
  helpContent: {
    title: 'Navigation',
    subtitle: 'La barre supérieure, le menu Modules et les modules épinglés',
    overview: 'La barre supérieure contient les pages principales (Vue d’ensemble, Certificats, Autorités et Activité, le journal d’audit pour qui peut le lire), jusqu’à trois modules que vous épinglez, le menu Modules, la recherche et votre compte. Le menu Modules liste toutes les autres pages que vous pouvez ouvrir, en quatre groupes avec leur nombre, chacune avec une ligne qui dit à quoi elle sert ; les pages auxquelles vous n’avez pas droit ne sont pas affichées.',
    sections: [
      {
        title: 'Menu Modules',
        items: [
          { label: 'Ouvrir', text: 'Sélectionnez Modules, ou appuyez sur la flèche Bas sur le bouton ; le focus passe à la première page' },
          { label: 'Se déplacer', text: 'Les flèches Haut et Bas, Début et Fin permettent de passer d’une page à l’autre ; Échap ferme le menu et revient au bouton' },
          { label: 'Épingler', text: 'Le bouton d’épingle à côté d’une page la garde dans la barre supérieure ; trois au maximum, et un message l’indique si vous en essayez une quatrième' },
          { label: 'Épinglés', text: 'Les modules épinglés s’affichent après Activité dans la barre principale ; l’en-tête du menu compte ses pages et vos épingles' },
        ]
      },
      {
        title: 'Recherche et raccourcis',
        items: [
          { label: 'Recherche', text: 'Appuyez sur Ctrl K (Cmd K sur macOS) ou sélectionnez le champ de recherche pour aller à toute page du menu que vous pouvez ouvrir (sous son nom de menu, son groupe en indication), lancer une action (Émettre un certificat ouvre son formulaire), ouvrir un onglet des pages ACME, SCEP, EST et TSA en tapant son nom (ACME : Fournisseurs DNS) ou trouver un certificat, une AC, un utilisateur, un modèle, un compte ACME ou un profil SCEP. Flèche bas passe du champ aux résultats, Flèche haut ramène du premier résultat au champ, et Entrée dans le champ ouvre le premier résultat. Un objet trouvé s’ouvre dans le détail de sa page' },
          { label: 'Adresse', text: 'L’objet ouvert dans le panneau de détail d’une page et sa section font partie de l’adresse : un rechargement ou un lien partagé les rouvre, et Précédent du navigateur referme le panneau' },
          { label: 'Aide', text: 'Appuyez sur ? hors d’un champ de texte, ou sélectionnez le bouton d’aide de la barre, pour ouvrir l’aide de la page courante ; sur un écran étroit, où la barre n’a pas de bouton d’aide, cherchez Aide de cette page' },
          { label: 'Largeur téléphone', text: 'La barre supérieure affiche une seule liste de pages au lieu des liens et du menu' },
          { label: 'Largeur des colonnes', text: 'Dans une liste, faites glisser le trait entre deux en-têtes de colonnes, ou atteignez-le avec Tab et utilisez les flèches Gauche et Droite (Maj pour un grand pas, Échap pour annuler), pour régler la largeur d’une colonne ; un double-clic ou Suppr la remet à sa largeur automatique, la largeur est gardée dans ce navigateur pour chaque liste, et Réinitialiser les colonnes, dans le pied de la liste ou dans le dialogue Colonnes des certificats, les efface toutes' },
          { label: 'Guide', text: 'Ouvrir dans un nouvel onglet, en haut de l’aide, ouvre tout le guide sur le chapitre de la page, à côté de la console ; Guide dans la recherche fait de même. Le guide liste tous les chapitres à gauche et les sections du chapitre lu sous Sur cette page, cherche dans l’ensemble, et imprime un chapitre ou tout le guide' },
        ]
      },
      {
        title: 'Menu du compte',
        items: [
          { label: 'Compte', text: 'Vos initiales à côté de votre nom, votre rôle et votre identifiant, puis ce que la console sait de votre session : e-mail, méthode de connexion et verrouillage après inactivité ; puis Mon compte, Paramètres (pour qui peut les ouvrir) et, à part, Se déconnecter ; au téléphone, la langue aussi. La langue se choisit par le bouton globe de la barre du haut, dans Mon compte et sur la page de connexion ; les Paramètres sont aussi dans le menu Modules et la recherche' },
        ]
      },
      {
        title: 'Session',
        items: [
          { label: 'Avertissement', text: 'Cinq minutes avant la fin du délai d’inactivité, un bandeau affiche le temps restant ; Prolonger garde la session et dit pour combien de temps, toute autre activité ne la prolonge plus' },
          { label: 'Verrouillage', text: 'À la fin, la session se ferme et l’écran se verrouille : rien de la console ne reste ouvert derrière' },
          { label: 'Retour', text: 'Reconnectez-vous avec le même compte pour revenir à la page où vous étiez ; Se connecter avec un autre compte repart de zéro' },
        ]
      },
      {
        title: 'Menu du thème',
        items: [
          { label: 'Choisir', text: 'Le bouton du thème propose deux groupes choisis à part : le thème, Atelier ou Aurore, et le mode, Système, Sombre ou Clair, les choix courants cochés ; Système suit votre appareil dans l’un ou l’autre thème, l’icône montre le mode appliqué (des étincelles pour Aurore)' },
          { label: 'Clavier', text: 'Les flèches Haut et Bas parcourent les options en boucle ; Échap ou Tab ferme le menu et revient au bouton' },
          { label: 'Enregistré', text: 'Le choix est celui de Paramètres, Apparence, et vous suit dans tous les navigateurs' },
        ]
      },
      {
        title: 'Notifications',
        items: [
          { label: 'Cloche', text: 'Le compteur est le nombre d’éléments non lus du panneau : éléments critiques et approbations de la file de la vue d’ensemble, et sauvegardes planifiées échouées, restaurations échouées ou sessions révoquées du journal d’audit' },
          { label: 'Ordre', text: 'Le panneau groupe les éléments par jour, du plus récent au plus ancien : aujourd’hui, hier, puis la date' },
          { label: 'Actions', text: 'Un renouvellement ACME échoué propose Relancer et une CRL à publier propose Publier, pour qui peut le faire ; les autres éléments ouvrent seulement leur page' },
          { label: 'Droits', text: 'Vous ne voyez que les éléments des sources que vous pouvez lire ; une source sur laquelle vous n’avez aucun droit n’affiche rien' },
          { label: 'Lu', text: 'Marquez un élément ou tous comme lus ; les marques sont enregistrées avec vos préférences, et un élément résolu quitte le panneau' },
          { label: 'Clavier', text: 'Échap ferme le panneau où que soit le focus et revient à la cloche ; un clic à l’extérieur ou un autre menu de la barre le ferme aussi. Un seul menu ou panneau de la barre est ouvert à la fois : en ouvrir un autre, l’aide ou la recherche ferme celui qui l’était. Après Marquer lu, le focus reste sur la ligne, après Tout marquer lu il va au titre' },
          { label: 'Ouvrir', text: 'Ouvrir mène à la page de l’élément et le marque lu ; les approbations se décident sur leur propre page' },
          { label: 'E-mail', text: 'Pour qui peut lire les paramètres, le pied du panneau dit si la notification par e-mail est activée et mène à ses réglages' },
        ]
      },
      {
        title: 'Haute disponibilité',
        items: [
          { label: 'Barre d’état', text: 'En mode haute disponibilité, la barre d’état affiche les nœuds, ou combien ne donnent plus de battement, et le nœud sur lequel vous êtes ; sélectionnez-la pour lister les nœuds' },
          { label: 'Approbations', text: 'Pour qui peut les lire, la barre d’état mène aux approbations qui attendent une décision, avec leur nombre' },
          { label: 'Dégradée', text: 'Quand un nœud ne donne plus de battement, un bandeau le dit avec ce qui fonctionne encore : lecture et émission sur les nœuds qui répondent, tâches planifiées sur le nœud leader' },
          { label: 'Maintenance', text: 'Pendant une maintenance de la grappe, une restauration par exemple, le serveur refuse toute écriture : le bandeau dit jusqu’à quand, et les boutons d’écriture de toutes les pages sont désactivés avec ce motif' },
          { label: 'Hors ligne', text: 'Quand le réseau est perdu, un bandeau le dit : la consultation continue avec les données déjà chargées, les boutons d’écriture de toutes les pages sont désactivés, et ils reviennent d’eux-mêmes avec le réseau' },
          { label: 'Connexion en direct', text: 'L’icône après l’état du service, dans la barre d’état, est la connexion en direct au serveur ; sélectionnez-la pour vous reconnecter' },
        ]
      },
      {
        title: 'Barre d’état et fenêtres détachées',
        items: [
          { label: 'Activité', text: 'Le milieu de la barre d’état résume ce qui se passe, pour ce que votre rôle peut lire : les approbations qui attendent une décision, une sauvegarde, une restauration ou une vérification du journal en cours, les interventions de la file de la vue d’ensemble, et les fenêtres détachées. Chaque élément mène à sa page ; quand tout est calme, la barre affiche Rien en attente. Elle est relue à chaque changement de données et une fois par minute' },
          { label: 'Détacher', text: 'Détacher dans une fenêtre, parmi les outils du détail d’un certificat, d’une autorité ou d’une demande, l’ouvre dans une fenêtre au-dessus de la page. Plusieurs fenêtres restent ouvertes à la fois, d’une page à l’autre, jusqu’à ce que vous les fermiez ou vous déconnectiez ; aucune ne s’ouvre au téléphone' },
          { label: 'Déplacer et redimensionner', text: 'Faites glisser la barre de titre pour déplacer une fenêtre, et un bord ou un coin pour la redimensionner. Au clavier, atteignez le bouton de déplacement de la barre de titre : les flèches déplacent la fenêtre, Maj et les flèches la redimensionnent. Une fenêtre reste dans la fenêtre du navigateur, et garde sa place et sa taille pendant la session' },
          { label: 'Premier plan et fermeture', text: 'La fenêtre que vous cliquez ou dans laquelle vous déplacez le focus passe devant ; la liste des fenêtres de la barre d’état en ramène une devant. La croix, ou Échap quand le focus est dans la fenêtre, la ferme' },
        ]
      },
      {
        title: 'Premier lancement',
        items: [
          { label: 'Configuration initiale', text: 'Sur une instance sans AC ni certificat, les administrateurs voient l’assistant Configuration initiale sur la vue d’ensemble et sur la liste des certificats : une racine, une AC émettrice, un protocole. Tant que ses étapes restent à faire, la liste des certificats vide et la page Autorités vide proposent Ouvrir l’assistant de configuration' },
          { label: 'Étapes', text: 'Chaque étape ouvre l’écran qui la réalise, et se coche dès que ce qu’elle crée existe' },
          { label: 'Plus tard et Masquer', text: 'Plus tard replie la carte en une ligne et Reprendre la rouvre ; Masquer ferme une configuration terminée, qui n’est plus montrée' },
        ]
      },
    ],
    tips: [
      'Vos épingles vous suivent dans tous les navigateurs et appareils depuis lesquels vous vous connectez',
      'Une page épinglée que vous n’avez plus le droit d’ouvrir est masquée, et revient si le droit est rétabli avant que vous ne changiez vos épingles',
    ],
  },
}
