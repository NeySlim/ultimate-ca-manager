export default {
  helpContent: {
    title: 'Navigation',
    subtitle: 'La barre supérieure, le menu Modules et les modules épinglés',
    overview: 'La barre supérieure contient les pages principales, jusqu\'à trois modules que vous épinglez, le menu Modules, la recherche et votre compte. Le menu Modules liste toutes les pages que vous pouvez ouvrir, en quatre groupes ; les pages auxquelles vous n\'avez pas droit ne sont pas affichées.',
    sections: [
      {
        title: 'Menu Modules',
        items: [
          { label: 'Ouvrir', text: 'Sélectionnez Modules, ou appuyez sur la flèche Bas sur le bouton ; le focus passe à la première page' },
          { label: 'Se déplacer', text: 'Les flèches Haut et Bas, Début et Fin permettent de passer d\'une page à l\'autre ; Échap ferme le menu et revient au bouton' },
          { label: 'Épingler', text: 'Le bouton d\'épingle à côté d\'une page la garde dans la barre supérieure ; trois au maximum, et le menu l\'indique si vous en essayez une quatrième' },
        ]
      },
      {
        title: 'Recherche et raccourcis',
        items: [
          { label: 'Recherche', text: 'Appuyez sur Ctrl K (Cmd K sur macOS) ou sélectionnez le champ de recherche pour aller à une page ou trouver un certificat' },
          { label: 'Aide', text: 'Appuyez sur ? hors d\'un champ de texte pour ouvrir l\'aide de la page courante' },
          { label: 'Largeur téléphone', text: 'La barre supérieure affiche une seule liste de pages au lieu des liens et du menu' },
        ]
      },
      {
        title: 'Menu du compte',
        items: [
          { label: 'Compte', text: 'Votre profil et vos paramètres, la langue et la déconnexion' },
        ]
      },
      {
        title: 'Menu du thème',
        items: [
          { label: 'Choisir', text: 'Le bouton soleil ou lune définit le thème de couleurs et le mode ; Système suit votre appareil, et l\'icône montre le mode appliqué' },
          { label: 'Clavier', text: 'Les flèches Haut et Bas parcourent les options en boucle ; Échap ou Tab ferme le menu et revient au bouton' },
          { label: 'Enregistré', text: 'Le choix est celui de Paramètres, Apparence, et vous suit dans tous les navigateurs' },
        ]
      },
      {
        title: 'Notifications',
        items: [
          { label: 'Cloche', text: 'Le compteur est le nombre d\'éléments non lus du panneau : éléments critiques et approbations de la file de la vue d\'ensemble, et sauvegardes planifiées échouées ou sessions révoquées du journal d\'audit' },
          { label: 'Ordre', text: 'Les éléments de la file viennent en premier, puis ceux du journal d\'audit, du plus récent au plus ancien' },
          { label: 'Droits', text: 'Vous ne voyez que les éléments des sources que vous pouvez lire ; une source sur laquelle vous n\'avez aucun droit n\'affiche rien' },
          { label: 'Lu', text: 'Marquez un élément ou tous comme lus ; les marques sont enregistrées avec vos préférences, et un élément résolu quitte le panneau' },
          { label: 'Ouvrir', text: 'Ouvrir mène à la page de l\'élément ; rien n\'est approuvé ni relancé depuis le panneau' },
        ]
      },
    ],
    tips: [
      'Vos épingles vous suivent dans tous les navigateurs et appareils depuis lesquels vous vous connectez',
      'Une page épinglée que vous n\'avez plus le droit d\'ouvrir est masquée, et revient si le droit est rétabli avant que vous ne changiez vos épingles',
    ],
  },
}
