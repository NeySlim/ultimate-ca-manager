export default {
  helpContent: {
    title: 'Hôtes SSH',
    subtitle: 'Enrôler des serveurs et renouveler leurs certificats d’hôte',
    overview: 'L’agent SSH installé sur un serveur tient sshd à jour avec UCM : il récupère la KRL d’une AC utilisateur et, avec un jeton d’enrôlement à usage unique, obtient un certificat d’hôte pour la clé du serveur, qu’il renouvelle ensuite seul. Cette page liste les serveurs enrôlés et les jetons d’enrôlement.',
    sections: [
      {
        title: 'Enrôlement',
        items: [
          { label: 'Jeton', text: 'Créez un jeton pour une AC hôte et les noms d’hôte du serveur. Il est affiché une fois, sert une fois et expire après la durée choisie, une heure par défaut.' },
          { label: 'Commande', text: 'Lancez en root sur le serveur la commande affichée avec le jeton : l’agent envoie la clé publique d’hôte du serveur et installe le certificat d’hôte reçu comme HostCertificate.' },
          { label: 'Noms', text: 'Le serveur peut demander une partie des noms du jeton ; un nom que le jeton ne liste pas est refusé.' },
        ]
      },
      {
        title: 'Renouvellement',
        items: [
          { label: 'Quand', text: 'Dès qu’un certificat n’a plus que 30 % de sa durée de vie (réglé par jeton), l’agent demande un défi à UCM à sa synchronisation suivante, toutes les 15 minutes.' },
          { label: 'Preuve', text: 'L’agent signe le défi avec la clé d’hôte que le certificat certifie. UCM ne garde aucun secret de l’hôte : la clé est la preuve.' },
          { label: 'Suspendre et révoquer', text: 'Suspendre le renouvellement arrête les renouvellements jusqu’à leur reprise. Révoquer l’hôte révoque son certificat, que la KRL liste alors, et met fin à ses renouvellements.' },
        ]
      },
      {
        title: 'États',
        items: [
          { label: 'Valide, expiré, révoqué', text: 'L’état du certificat que l’hôte présente maintenant.' },
          { label: 'Dernière récupération de la KRL', text: 'Quand l’agent du serveur a téléchargé une KRL pour la dernière fois, tel que l’agent le déclare. Non déclaré quand le serveur ne suit aucune KRL.' },
        ]
      },
    ],
    tips: [
      'Donnez aux certificats d’hôte une validité de semaines ou de mois : l’agent les renouvelle, et révoquer un hôte l’arrête aussitôt.',
      'Créez un jeton par serveur, avec la durée nécessaire pour l’y lancer.',
    ],
    warnings: [
      'Un jeton est affiché une fois : UCM n’en garde que l’empreinte.',
      'Retirer l’agent d’un serveur ne révoque pas l’hôte : révoquez-le ici.',
    ],
  },
  helpGuides: {
    title: 'Hôtes SSH',
    content: `
## Vue d’ensemble

L’agent SSH est un script shell POSIX qu’UCM sert à vos serveurs. Il ne contient aucun secret et ne fait que tirer depuis UCM : UCM ne se connecte jamais à un serveur. Il fait deux choses :

- il tient sshd sur la **KRL** d’une AC utilisateur, pour qu’un certificat utilisateur révoqué soit refusé en quelques minutes ;
- il **enrôle** le serveur auprès d’une AC hôte, avec un jeton à usage unique, et **renouvelle** seul le certificat d’hôte.

Il demande \`ssh-keygen\` et \`curl\` ou \`wget\`, et tourne par un minuteur systemd, ou une tâche cron, toutes les 15 minutes. L’enrôlement et le renouvellement d’un hôte demandent aussi OpenSSH 8.1 ou plus, pour \`ssh-keygen -Y sign\`.

## Suivre une KRL

Ouvrez l’AC utilisateur dans **AC SSH**, onglet **Installation rapide**, et lancez la commande **Agent SSH** en root sur le serveur :

\`\`\`bash
curl -fsSL https://ucm.example.com:8443/ssh/setup/<refid>/agent | sudo sh
\`\`\`

L’agent télécharge d’abord la KRL dans \`/etc/ssh/ucm/revoked_keys\`, puis ajoute \`RevokedKeys\` à sshd (dans \`/etc/ssh/sshd_config.d\` quand sshd_config l’inclut, sinon en tête de sshd_config) et vérifie le résultat avec \`sshd -t\`. À chaque synchronisation il ne télécharge la KRL que si sa version a changé, la vérifie avec \`ssh-keygen\`, refuse une KRL plus ancienne que celle installée, remplace le fichier en une étape et recharge sshd.

La KRL est publique, comme une CRL : \`/ssh/krl/<refid>\`. Sa version ne change que lorsqu’un certificat de l’AC est révoqué.

## Enrôler un serveur

1. Ouvrez **Hôtes SSH**, puis **Nouveau jeton d’enrôlement**
2. Choisissez l’AC hôte et saisissez les noms d’hôte du serveur (par exemple \`web01.example.com, web01\`)
3. Choisissez si besoin la validité des certificats, la durée de vie du jeton et le moment du renouvellement
4. Copiez la commande affichée avec le jeton et lancez-la en root sur le serveur, avant l’expiration du jeton

\`\`\`bash
curl -fsSL https://ucm.example.com:8443/ssh/setup/<refid>/agent | UCM_ENROLL_TOKEN=ucmh_... sudo --preserve-env=UCM_ENROLL_TOKEN sh
\`\`\`

L’agent envoie la clé publique d’hôte du serveur (Ed25519 d’abord, puis ECDSA, puis RSA ; \`--host-key\` en choisit une autre) avec le jeton signé par cette clé, ce qui prouve que le serveur la détient, vérifie que le certificat reçu certifie cette clé, l’écrit à côté de la clé et y fait pointer \`HostCertificate\`. Ajoutez \`-s -- --principal web01\` pour ne demander qu’une partie des noms du jeton.

Le jeton est affiché une fois et sert une fois. Le serveur ne le conserve jamais : l’agent le passe à curl par un tube (à wget, qui ne lit pas de tube, par un fichier que seul root peut lire, effacé après la requête). Un jeton inutilisé peut être révoqué dans **Jetons d’enrôlement**.

Les clients font confiance à l’AC hôte par une ligne de \`known_hosts\` :

\`\`\`
@cert-authority *.example.com ssh-ed25519 AAAA...
\`\`\`

## Renouvellement

Dès que le certificat d’hôte n’a plus que 30 % de sa durée de vie (la part se règle par jeton), l’agent demande un défi à UCM, le signe avec la clé d’hôte (\`ssh-keygen -Y sign\`) et reçoit un nouveau certificat pour les mêmes noms. UCM vérifie la signature avec la clé que le certificat en cours certifie : aucun mot de passe ni jeton n’est gardé pour l’hôte.

Un renouvellement est refusé quand l’hôte ou son certificat est révoqué, quand le certificat a expiré, ou quand le renouvellement est suspendu. Après un tel refus l’agent cesse de demander, sauf pour une suspension ; \`ucm-ssh-agent status\` en donne la raison. Un serveur refusé définitivement s’enrôle de nouveau avec un nouveau jeton.

## La page Hôtes SSH

| Colonne | Signification |
|---------|---------------|
| Principaux | Les noms du certificat d’hôte |
| Expiration | La fin du certificat en cours |
| Renouvellement automatique | Actif, ou Suspendu |
| Dernière récupération de la KRL | Quand l’agent a téléchargé une KRL pour la dernière fois, tel qu’il le déclare |
| État | Valide, Expiré ou Révoqué |

**Suspendre le renouvellement** arrête les renouvellements jusqu’à **Reprendre le renouvellement**. **Révoquer l’hôte** révoque tous les certificats non expirés de sa clé, celui en cours et ceux que ses renouvellements ont remplacés, que la KRL de l’AC hôte liste alors, et met fin aux renouvellements. Chaque enrôlement, renouvellement et refus figure dans le journal d’audit.

## Retirer l’agent

\`\`\`bash
curl -fsSL https://ucm.example.com:8443/ssh/setup/<refid>/agent | sudo sh -s -- --uninstall
\`\`\`

L’agent retire son minuteur, ses réglages sshd, la KRL et le certificat qu’il a installé, et remet en place un certificat trouvé à cet endroit. L’hôte reste listé dans UCM : révoquez-le là.
`
  }
}
