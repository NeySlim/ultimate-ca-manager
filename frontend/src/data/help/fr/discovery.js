export default {
  helpContent: {
    title: 'Découverte de certificats',
    subtitle: 'Trouver les certificats TLS sur votre réseau',
    overview: 'Analysez votre réseau pour trouver les certificats TLS déployés sur les serveurs et terminaux, et rapprochez-les de votre inventaire PKI géré. Localisez les certificats non suivis, détectez les changements et surveillez les certificats en voie d’expiration hors du contrôle d’UCM.',
    sections: [
      {
        title: 'Vues',
        items: [
          { label: 'Analyses', text: 'La page s’ouvre sur les analyses, une par profil de scan : sa plage, ce que sa dernière exécution a trouvé et quand, et l’état de cette exécution (Terminée, En échec, En cours, Planifiée, Jamais lancée). Un nom l’ouvre dans le panneau de détail, avec Analyser maintenant, Modifier… et Supprimer…' },
          { label: 'Certificats trouvés', text: 'Tous les certificats rencontrés par les analyses, avec hôte, émetteur, expiration et état ; la recherche, les pastilles d’état et le filtre par analyse sont appliqués par le serveur' },
          { label: 'Historique des analyses', text: 'Chaque exécution, d’une analyse ou d’une analyse rapide, de la plus récente à la plus ancienne, avec ce qu’elle a trouvé, les cibles analysées et sa durée' },
        ]
      },
      {
        title: 'Analyse',
        items: [
          { label: 'Scan rapide', text: 'Scan ponctuel sans enregistrer de profil, saisissez cibles et ports, les résultats arrivent en direct' },
          { label: 'Cibles', text: 'Une par ligne, ou séparées par des virgules : nom d’hôte, IP, plage IPv4 (192.0.2.0/24) ou hôte:port (mail.example.com:465). Un joker DNS (*.example.com), une plage IPv6 et une plage IPv4 de plus de 65 536 hôtes sont refusés dans le formulaire : l’analyse n’atteint aucun hôte pour les deux premiers et refuse le troisième' },
          { label: 'Ports', text: 'Ports TCP séparés par des virgules (p. ex. 443, 8443, 636), ou le préréglage des ports courants' },
          { label: 'Options avancées', text: 'Résolution DNS inverse (enregistrements PTR), délai d’attente et concurrence' },
          { label: 'Planification', text: 'Les profils s’exécutent manuellement ou automatiquement toutes les 1h / 6h / 12h / 24h / 7j' },
          { label: 'Notifications', text: 'Alertes e-mail sur nouveaux certificats, changements de certificat ou expiration imminente. Un certificat trouvé via SNI sur une cible IP est compté comme nouveau à chaque scan' },
        ]
      },
      {
        title: 'Statuts des résultats',
        items: [
          { label: 'Dans UCM', text: 'L’empreinte SHA-256 du certificat correspond à un certificat de l’inventaire UCM' },
          { label: 'Inconnu d’UCM', text: 'Trouvé sur le réseau mais absent de l’inventaire, candidat à une prise en gestion' },
          { label: 'En erreur', text: 'Le terminal a répondu mais sa poignée de main TLS ou son certificat a échoué (SNI rejeté, certificat illisible). Une connexion refusée, un délai dépassé, un échec DNS ou réseau ne laisse aucune ligne. Relancez une ligne, ou Réessayer toutes les erreurs de la page courante' },
          { label: 'Modifié', text: 'Un terminal présentant un certificat différent du scan précédent est signalé avec un horodatage Dernier changement' },
        ]
      },
    ],
    tips: [
      'Filtrez les certificats trouvés avec les pastilles d’état : Tous, Dans UCM, Inconnu d’UCM, En erreur',
      'L’export télécharge en CSV les certificats trouvés que montrent la recherche, l’état et le filtre par analyse',
      'Planifiez un scan quotidien de vos sous-réseaux serveurs avec la notification de nouveau certificat activée',
    ],
    warnings: [
      'Lancer des scans et gérer les profils exige des permissions admin ; un sous-réseau de profil est plafonné à 1024 adresses (/22), un CIDR saisi comme cible à 65 536 hôtes',
    ],
  },
  helpGuides: {
    title: 'Découverte de certificats',
    content: `
## Vue d’ensemble

La découverte de certificats analyse votre réseau pour trouver les certificats TLS déployés sur les serveurs et terminaux, et les rapproche de votre inventaire PKI géré. Utilisez-la pour localiser les certificats non suivis, détecter les changements et surveiller les certificats en voie d’expiration hors du contrôle d’UCM.

## Vues

### Analyses
La page s’ouvre sur les analyses, une par profil de scan : sa plage, ce que sa dernière exécution a trouvé et quand, et l’état de cette exécution (**Terminée**, **En échec**, **En cours**, **Planifiée**, **Jamais lancée**). Un nom ouvre l’analyse dans le panneau de détail : **Aperçu** donne ses propriétés et sa description, **Exécutions** ses exécutions ; **Analyser maintenant**, **Modifier…** et **Supprimer…** demandent admin:system. **Nouvelle analyse…** en crée une.

### Certificats trouvés
Tous les certificats rencontrés par les analyses, avec hôte, émetteur, expiration et état. Un nom ouvre le certificat dans le panneau de détail : sujet, émetteur, validité, extensions et empreintes, et, pour un certificat en erreur, l’erreur et une indication sur sa cause.

### Historique des analyses
Chaque exécution, d’une analyse ou d’une analyse rapide, de la plus récente à la plus ancienne, avec ce qu’elle a trouvé, les cibles analysées et sa durée.

## Scan rapide

Lancez un scan ponctuel sans enregistrer de profil :

1. Cliquez sur **Analyse rapide…**
2. Saisissez la **plage**, une cible par ligne ou séparées par des virgules : nom d’hôte, IP, plage IPv4 (\`192.0.2.0/24\`) ou \`hôte:port\` (\`mail.example.com:465\`). Un joker DNS, une plage IPv6 et une plage IPv4 de plus de 65 536 hôtes sont refusés dans le formulaire
3. Saisissez les **ports** : ports TCP séparés par des virgules (p. ex. \`443, 8443, 636\`), ou choisissez le préréglage des ports courants
4. Ajustez éventuellement les **options avancées** : résolution DNS inverse (enregistrements PTR), délai d’attente, concurrence
5. Cliquez sur **Démarrer le scan** : la progression s’affiche en direct via WebSocket

## Profils de scan

Les profils enregistrent une configuration de cibles pour un usage répété :

- **Cibles et ports** : mêmes formats que le scan rapide
- **Planification** : manuelle, ou automatique toutes les 1h / 6h / 12h / 24h / 7j
- **Notifications** : alertes e-mail lorsque de nouveaux certificats sont découverts, lorsqu’un certificat change sur un terminal, ou lorsque des certificats découverts arrivent à expiration. Un certificat trouvé via SNI sur une cible IP est compté comme nouveau à chaque scan

Lancez une analyse à la demande avec **Analyser maintenant** dans son panneau de détail, ou laissez le planificateur la lancer à l’intervalle configuré.

## Statuts des résultats

- **Dans UCM** : L’empreinte SHA-256 du certificat correspond à un certificat de l’inventaire UCM
- **Inconnu d’UCM** : Trouvé sur le réseau mais absent de l’inventaire : candidat à une prise en gestion
- **En erreur** : Le terminal a répondu mais sa poignée de main TLS ou son certificat a échoué (SNI rejeté, certificat illisible). Une connexion refusée, un délai dépassé, un échec DNS ou réseau n’est pas enregistré

### Détection des changements
Lorsqu’un terminal présente un certificat différent du scan précédent, le changement est enregistré (empreinte précédente conservée, horodatage **Dernier changement**) et peut déclencher une notification.

## Filtrage et export

- **Pastilles d’état** : Tous, Dans UCM, Inconnu d’UCM, En erreur
- **Filtre par profil** : Restreindre les résultats à un profil de scan
- **Export** : Télécharger en CSV les certificats trouvés que montrent la recherche, l’état et le filtre par analyse
- **Réessayer** : Relancer individuellement les cibles en erreur, ou **Réessayer toutes les erreurs** affichées sur la page courante
- **Résoudre le DNS** : Résolution DNS inverse en masse des IP découvertes

## Limites et sécurité

- Un sous-réseau de profil est plafonné à 1024 adresses (équivalent d’un /22 IPv4), un CIDR saisi comme cible à 65 536 hôtes ; jusqu’à 1000 cibles par scan de profil
- Les plages privées RFC1918 et le loopback sont analysables : modèle de déploiement on-prem d’UCM ; les plages link-local, multicast et réservées sont bloquées
- Les scans lancés à la main et les modifications de profils sont journalisés dans l’audit ; les exécutions planifiées ne le sont pas

## Permissions

- **read:certificates** : Consulter les certificats découverts, les profils et l’historique
- **admin:system** : Créer/modifier des profils et lancer des scans
- **delete:certificates** : Supprimer des résultats découverts

> 💡 Planifiez un scan quotidien de vos sous-réseaux serveurs et activez la notification de nouveau certificat : cela repère les certificats déployés en dehors de votre processus PKI.
`
  }
}
