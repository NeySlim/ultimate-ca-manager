export default {
  helpContent: {
    title: 'Découverte de certificats',
    subtitle: 'Trouver les certificats TLS sur votre réseau',
    overview: 'Analysez votre réseau pour trouver les certificats TLS déployés sur les serveurs et terminaux, et rapprochez-les de votre inventaire PKI géré. Localisez les certificats non suivis, détectez les changements et surveillez les certificats en voie d\'expiration hors du contrôle d\'UCM.',
    sections: [
      {
        title: 'Onglets',
        items: [
          { label: 'Découverts', text: 'Tous les certificats trouvés par les scans, avec statut, expiration et détails du terminal' },
          { label: 'Profils', text: 'Configurations de scan enregistrées, cibles, ports, planification, notifications' },
          { label: 'Historique', text: 'Exécutions passées avec durée, cibles analysées et certificats trouvés' },
        ]
      },
      {
        title: 'Analyse',
        items: [
          { label: 'Scan rapide', text: 'Scan ponctuel sans enregistrer de profil, saisissez cibles et ports, les résultats arrivent en direct' },
          { label: 'Cibles', text: 'Saisies sous forme d\'étiquettes, une par cible : nom d\'hôte, IP, sous-réseau CIDR (192.168.1.0/24) ou host:port (10.0.0.1:8443)' },
          { label: 'Ports', text: 'Ports TCP séparés par des virgules (p. ex. 443, 8443, 636), ou le préréglage des ports courants' },
          { label: 'Options avancées', text: 'Résolution DNS inverse (enregistrements PTR), délai d\'attente et concurrence' },
          { label: 'Planification', text: 'Les profils s\'exécutent manuellement ou automatiquement toutes les 1h / 6h / 12h / 24h / 7j' },
          { label: 'Notifications', text: 'Alertes e-mail sur nouveaux certificats, changements de certificat ou expiration imminente. Un certificat trouvé via SNI sur une cible IP est compté comme nouveau à chaque scan' },
        ]
      },
      {
        title: 'Statuts des résultats',
        items: [
          { label: 'Géré', text: 'L\'empreinte SHA-256 du certificat correspond à un certificat de l\'inventaire UCM' },
          { label: 'Non géré', text: 'Trouvé sur le réseau mais absent de l\'inventaire, candidat à une prise en gestion' },
          { label: 'Erreur', text: 'Le terminal a répondu mais sa poignée de main TLS ou son certificat a échoué (SNI rejeté, certificat illisible). Une connexion refusée, un délai dépassé, un échec DNS ou réseau ne laisse aucune ligne. Relancez une ligne, ou Réessayer toutes les erreurs de la page courante' },
          { label: 'Modifié', text: 'Un terminal présentant un certificat différent du scan précédent est signalé avec un horodatage Dernier changement' },
        ]
      },
    ],
    tips: [
      'Filtrez les résultats avec les pastilles de statut : Tous, Géré, Non géré, Erreur',
      'L\'export télécharge tous les certificats découverts en CSV, quels que soient les filtres',
      'Planifiez un scan quotidien de vos sous-réseaux serveurs avec la notification de nouveau certificat activée',
    ],
    warnings: [
      'Lancer des scans et gérer les profils exige des permissions admin ; un sous-réseau de profil est plafonné à 1024 adresses (/22), un CIDR saisi comme cible à 65 536 hôtes',
    ],
  },
  helpGuides: {
    title: 'Découverte de certificats',
    content: `
## Vue d'ensemble

La découverte de certificats analyse votre réseau pour trouver les certificats TLS déployés sur les serveurs et terminaux, et les rapproche de votre inventaire PKI géré. Utilisez-la pour localiser les certificats non suivis, détecter les changements et surveiller les certificats en voie d'expiration hors du contrôle d'UCM.

## Onglets

### Découverts
Tous les certificats trouvés par les scans, avec statut, expiration et détails du terminal. Cliquez sur une ligne pour ouvrir le panneau de détails avec les informations du certificat, les Subject Alternative Names et l'historique de scan (première détection, dernière détection, dernier changement).

### Profils
Configurations de scan enregistrées pour les analyses récurrentes : cibles, ports, planification et notifications.

### Historique
Exécutions passées avec durée, cibles analysées et certificats trouvés.

## Scan rapide

Lancez un scan ponctuel sans enregistrer de profil :

1. Cliquez sur **Scan rapide**
2. Saisissez les **cibles**, chacune sous forme d'étiquette : nom d'hôte, IP, sous-réseau CIDR (\`192.168.1.0/24\`) ou \`host:port\` (\`10.0.0.1:8443\`)
3. Saisissez les **ports** : ports TCP séparés par des virgules (p. ex. \`443, 8443, 636\`), ou choisissez le préréglage des ports courants
4. Ajustez éventuellement les **options avancées** : résolution DNS inverse (enregistrements PTR), délai d'attente, concurrence
5. Cliquez sur **Démarrer le scan** : la progression s'affiche en direct via WebSocket

## Profils de scan

Les profils enregistrent une configuration de cibles pour un usage répété :

- **Cibles et ports** : mêmes formats que le scan rapide
- **Planification** : manuelle, ou automatique toutes les 1h / 6h / 12h / 24h / 7j
- **Notifications** : alertes e-mail lorsque de nouveaux certificats sont découverts, lorsqu'un certificat change sur un terminal, ou lorsque des certificats découverts arrivent à expiration. Un certificat trouvé via SNI sur une cible IP est compté comme nouveau à chaque scan

Exécutez un profil à la demande avec **Scanner**, ou laissez le planificateur le lancer à l'intervalle configuré.

## Statuts des résultats

- **Géré** : L'empreinte SHA-256 du certificat correspond à un certificat de l'inventaire UCM
- **Non géré** : Trouvé sur le réseau mais absent de l'inventaire : candidat à une prise en gestion
- **Erreur** : Le terminal a répondu mais sa poignée de main TLS ou son certificat a échoué (SNI rejeté, certificat illisible). Une connexion refusée, un délai dépassé, un échec DNS ou réseau n'est pas enregistré

### Détection des changements
Lorsqu'un terminal présente un certificat différent du scan précédent, le changement est enregistré (empreinte précédente conservée, horodatage **Dernier changement**) et peut déclencher une notification.

## Filtrage et export

- **Pastilles de filtre par statut** : Tous, Géré, Non géré, Erreur
- **Filtre par profil** : Restreindre les résultats à un profil de scan
- **Export** : Télécharger tous les certificats découverts en CSV, quels que soient les filtres
- **Réessayer** : Relancer individuellement les cibles en erreur, ou **Réessayer toutes les erreurs** affichées sur la page courante
- **Résoudre le DNS** : Résolution DNS inverse en masse des IP découvertes

## Limites et sécurité

- Un sous-réseau de profil est plafonné à 1024 adresses (équivalent d'un /22 IPv4), un CIDR saisi comme cible à 65 536 hôtes ; jusqu'à 1000 cibles par scan de profil
- Les plages privées RFC1918 et le loopback sont analysables : modèle de déploiement on-prem d'UCM ; les plages link-local, multicast et réservées sont bloquées
- Les scans lancés à la main et les modifications de profils sont journalisés dans l'audit ; les exécutions planifiées ne le sont pas

## Permissions

- **read:certificates** : Consulter les certificats découverts, les profils et l'historique
- **admin:system** : Créer/modifier des profils et lancer des scans
- **delete:certificates** : Supprimer des résultats découverts

> 💡 Planifiez un scan quotidien de vos sous-réseaux serveurs et activez la notification de nouveau certificat : cela repère les certificats déployés en dehors de votre processus PKI.
`
  }
}
