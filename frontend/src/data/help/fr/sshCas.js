export default {
  helpContent: {
    title: 'Autorités de certification SSH',
    subtitle: 'Gérer les CA SSH pour l\'authentification des utilisateurs et des hôtes',
    overview: 'Créez et gérez des autorités de certification SSH conformes aux standards OpenSSH. Les CA SSH éliminent la nécessité de distribuer les clés publiques individuellement — les serveurs et les utilisateurs font confiance à la CA, et la CA signe des certificats qui accordent l\'accès.',
    sections: [
      {
        title: 'Types de CA',
        items: [
          { label: 'User CA', text: 'Signe des certificats utilisateur pour la connexion SSH. Les serveurs font confiance à cette CA et acceptent tout certificat signé par elle.' },
          { label: 'Host CA', text: 'Signe des certificats d\'hôte pour prouver l\'identité du serveur. Les clients font confiance à cette CA pour vérifier qu\'ils se connectent au bon serveur.' },
        ]
      },
      {
        title: 'Algorithmes de clé',
        items: [
          { label: 'Ed25519', text: 'Moderne, rapide, petites clés (256 bits). Recommandé pour les nouveaux déploiements.' },
          { label: 'ECDSA P-256 / P-384', text: 'Clés à courbe elliptique, largement prises en charge. Bon équilibre entre sécurité et compatibilité.' },
          { label: 'RSA 2048 / 4096', text: 'Algorithme traditionnel. Utilisez 4096 bits pour les CA à longue durée de vie. Compatibilité la plus large avec les anciens systèmes.' },
        ]
      },
      {
        title: 'Configuration du serveur',
        items: [
          { label: 'Script de configuration', text: 'Téléchargez un script shell POSIX qui configure automatiquement sshd pour faire confiance à cette CA. Compatible avec toutes les principales distributions Linux.' },
          { label: 'Configuration manuelle', text: 'Copiez la clé publique de la CA et ajoutez TrustedUserCAKeys (User CA) ou HostCertificate (Host CA) dans sshd_config.' },
        ]
      },
      {
        title: 'Révocation de clés',
        items: [
          { label: 'KRL (Key Revocation List)', text: 'Format binaire compact pour révoquer des certificats individuels. Configuré via RevokedKeys dans sshd_config.' },
          { label: 'Télécharger la KRL', text: 'Téléchargez le fichier KRL actuel depuis le panneau de détail de la CA.' },
        ]
      },
    ],
    tips: [
      'Utilisez des CA distinctes pour les certificats utilisateur et hôte — ne les mélangez jamais.',
      'Ed25519 est recommandé pour les nouveaux déploiements grâce à sa rapidité et sa sécurité.',
      'Téléchargez le script de configuration pour une mise en place facile du serveur — il gère automatiquement la sauvegarde et la validation.',
    ],
    warnings: [
      'Supprimer une CA ne révoque pas les certificats qu\'elle a signés — révoquez-les d\'abord ou mettez à jour la confiance des serveurs.',
      'Si la clé privée de la CA est compromise, tous les certificats signés par celle-ci doivent être considérés comme non fiables.',
    ],
  },
  helpGuides: {
    title: 'Autorités de certification SSH',
    content: `
## Vue d'ensemble

Les autorités de certification SSH (CA) constituent le fondement de l'authentification par certificats SSH. Au lieu de distribuer des clés publiques individuelles à chaque serveur, vous créez une CA et configurez les serveurs pour lui faire confiance. Tout certificat signé par la CA est alors automatiquement accepté.

UCM prend en charge le format de certificat OpenSSH (RFC 4253 + extensions OpenSSH), nativement reconnu par OpenSSH 5.4+ — aucun logiciel supplémentaire n'est nécessaire sur les serveurs ou les clients.

## Types de CA

### User CA
Une User CA signe des certificats qui authentifient les **utilisateurs auprès des serveurs**. Lorsqu'un serveur fait confiance à une User CA, tout utilisateur présentant un certificat valide signé par cette CA est autorisé à se connecter (sous réserve de correspondance des principals).

**Configuration du serveur :**
\`\`\`
# /etc/ssh/sshd_config
TrustedUserCAKeys /etc/ssh/user_ca.pub
\`\`\`

### Host CA
Une Host CA signe des certificats qui authentifient les **serveurs auprès des clients**. Lorsqu'un client fait confiance à une Host CA, il peut vérifier que le serveur auquel il se connecte est légitime — éliminant les avertissements TOFU (Trust On First Use).

**Configuration du client :**
\`\`\`
# ~/.ssh/known_hosts
@cert-authority *.example.com ssh-ed25519 AAAA...
\`\`\`

## Créer une CA

1. Cliquez sur **Créer une CA SSH**
2. Saisissez un nom descriptif (ex. : « CA utilisateur Production »)
3. Sélectionnez le type de CA : **User** ou **Host**
4. Choisissez l'algorithme de clé :
   - **Ed25519** — Recommandé. Rapide, petites clés, sécurité moderne.
   - **ECDSA P-256/P-384** — Bonne compatibilité et sécurité.
   - **RSA 2048/4096** — Compatibilité la plus large, clés plus volumineuses.
5. Définissez optionnellement la validité maximale et les extensions par défaut
6. Cliquez sur **Créer**

> 💡 Utilisez des CA distinctes pour les certificats utilisateur et hôte. N'utilisez jamais une même CA pour les deux.

## Configuration du serveur

### Script de configuration automatique

UCM génère un script shell POSIX qui configure automatiquement votre serveur :

1. Ouvrez le panneau de détail de la CA
2. Cliquez sur **Télécharger le script de configuration**
3. Transférez le script sur votre serveur
4. Exécutez-le :

\`\`\`bash
chmod +x setup-ssh-ca.sh
sudo ./setup-ssh-ca.sh
\`\`\`

Le script :
- Détecte votre système d'exploitation et votre système d'init
- Sauvegarde sshd_config avant toute modification
- Installe la clé publique de la CA
- Ajoute TrustedUserCAKeys (User CA) ou HostCertificate (Host CA)
- Valide la configuration avec \`sshd -t\`
- Redémarre sshd uniquement si la validation réussit
- Supporte \`--dry-run\` pour prévisualiser les modifications

### Configuration manuelle

#### User CA
\`\`\`bash
# Copiez la clé publique de la CA sur le serveur
echo "ssh-ed25519 AAAA... user-ca" | sudo tee /etc/ssh/user_ca.pub

# Ajoutez à sshd_config
echo "TrustedUserCAKeys /etc/ssh/user_ca.pub" | sudo tee -a /etc/ssh/sshd_config

# Redémarrez sshd
sudo systemctl restart sshd
\`\`\`

#### Host CA
\`\`\`bash
# Signez la clé d'hôte du serveur
# Puis ajoutez à sshd_config :
echo "HostCertificate /etc/ssh/ssh_host_ed25519_key-cert.pub" | sudo tee -a /etc/ssh/sshd_config
sudo systemctl restart sshd
\`\`\`

## Listes de révocation de clés (KRL)

Les CA SSH prennent en charge les listes de révocation de clés pour invalider les certificats compromis :

1. Révoquez les certificats depuis la page Certificats SSH
2. Téléchargez la KRL mise à jour depuis le panneau de détail de la CA
3. Déployez le fichier KRL sur les serveurs :

\`\`\`bash
# Ajoutez à sshd_config
RevokedKeys /etc/ssh/revoked_keys
\`\`\`

> ⚠ Les serveurs doivent être configurés pour vérifier la KRL. La révocation ne prend effet qu'après le déploiement de la KRL.

## Bonnes pratiques

| Pratique | Recommandation |
|----------|---------------|
| CA distinctes | Utilisez des CA séparées pour les certificats utilisateur et hôte |
| Algorithme de clé | Ed25519 pour les nouveaux déploiements, RSA 4096 pour la compatibilité avec les anciens systèmes |
| Durée de vie de la CA | Gardez les CA à longue durée de vie ; utilisez des certificats éphémères |
| Sauvegarde | Exportez et stockez la clé privée de la CA en lieu sûr |
| Correspondance des principals | Associez les principals à des noms d'utilisateur spécifiques, pas à des jokers |
`
  }
}
