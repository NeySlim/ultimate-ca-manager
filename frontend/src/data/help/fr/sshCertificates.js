export default {
  helpContent: {
    title: 'Certificats SSH',
    subtitle: 'Émettre et gérer des certificats OpenSSH',
    overview: 'Émettez des certificats SSH signés par vos AC SSH. Les certificats remplacent la gestion manuelle d\'authorized_keys en offrant un accès limité dans le temps, restreint par principal, avec expiration automatique. Les certificats utilisateur et hôte sont pris en charge.',
    sections: [
      {
        title: 'Modes d\'émission',
        items: [
          { label: 'Mode signature', text: 'Collez une clé publique SSH existante pour la signer. La clé privée reste sur la machine de l\'utilisateur, UCM ne la voit jamais.' },
          { label: 'Mode génération', text: 'UCM génère une nouvelle paire de clés et signe le certificat. Téléchargez la clé privée immédiatement, elle ne pourra pas être récupérée ultérieurement.' },
        ]
      },
      {
        title: 'Champs du certificat',
        items: [
          { label: 'Key ID', text: 'Identifiant que sshd journalise pour le titulaire. L\'AC le définit à principals@AC name, sauf si elle laisse les demandeurs le choisir.' },
          { label: 'Principals', text: 'Noms d\'utilisateur (certificat utilisateur) ou noms d\'hôte (certificat hôte) pour lesquels ce certificat est valide. Séparés par des virgules.' },
          { label: 'Validité', text: 'Durée de vie du certificat. Choisissez un préréglage (1h, 8h, 24h, 7j, 30j, 90j, 365j) ou définissez une durée personnalisée en secondes. Valide dès 5 minutes avant l\'émission, pour les serveurs dont l\'horloge retarde (v2.252).' },
          { label: 'Extensions', text: 'Extensions SSH telles que permit-pty, permit-agent-forwarding. Applicables uniquement aux certificats utilisateur.' },
          { label: 'Critical Options', text: 'Certificats utilisateur uniquement : force-command, source-address (adresses ou réseaux CIDR, séparés par des virgules) et verify-required, plus les options de fournisseur nommées name@domain. Les certificats d\'hôte n\'en portent aucune, et toute autre option est refusée (v2.252).' },
        ]
      },
      {
        title: 'Types de certificats',
        items: [
          { label: 'Certificat utilisateur', text: 'Authentifie un utilisateur auprès d\'un serveur. Le serveur doit faire confiance à l\'AC signataire via TrustedUserCAKeys.' },
          { label: 'Certificat d\'hôte', text: 'Authentifie un serveur auprès des clients. Les clients font confiance à l\'AC via @cert-authority dans known_hosts.' },
        ]
      },
      {
        title: 'Gestion',
        items: [
          { label: 'Révoquer', text: 'Ajoute un certificat à la liste de révocation de clés (KRL) de la CA. Les serveurs doivent être configurés pour vérifier la KRL. Un certificat révoqué reste dans la KRL et ne peut pas être supprimé avant son expiration (v2.252).' },
          { label: 'Télécharger', text: 'Téléchargez le certificat, la clé publique ou la clé privée (mode génération uniquement).' },
        ]
      },
    ],
    tips: [
      'Utilisez des certificats éphémères (8h-24h) pour l\'accès utilisateur afin de minimiser l\'impact d\'une compromission de clé.',
      'Le mode signature est préférable : la clé privée de l\'utilisateur ne quitte jamais sa machine.',
      'Lorsqu\'une AC laisse les demandeurs définir le key ID, gardez-le descriptif (ex. : « jdoe-prod-2025 ») pour faciliter l\'audit des journaux.',
      'Pour les certificats d\'hôte, le principal doit correspondre au nom d\'hôte utilisé par les clients pour se connecter.',
    ],
    warnings: [
      'En mode génération, téléchargez la clé privée immédiatement : elle n\'est pas stockée et ne peut pas être récupérée.',
      'La révocation d\'un certificat ne fonctionne que si les serveurs sont configurés pour vérifier le fichier KRL de la CA.',
    ],
  },
  helpGuides: {
    title: 'Certificats SSH',
    content: `
## Vue d'ensemble

Les certificats SSH sont des clés publiques SSH signées avec des métadonnées : identité, période de validité, principals autorisés et extensions. Ils remplacent l'approche traditionnelle \`authorized_keys\` par un contrôle d'accès centralisé, limité dans le temps et auditable.

UCM émet des certificats au format OpenSSH compatibles avec OpenSSH 5.4+ sur toutes les plateformes.

## Modes d'émission

### Mode signature (recommandé)
L'utilisateur génère sa propre paire de clés et ne fournit que la **clé publique** à UCM. La clé privée ne quitte jamais la machine de l'utilisateur.

**Procédure utilisateur :**
\`\`\`bash
# 1. Générer une paire de clés (machine de l'utilisateur)
ssh-keygen -t ed25519 -f ~/.ssh/id_work -C "jdoe@example.com"

# 2. Copier le contenu de la clé publique
cat ~/.ssh/id_work.pub

# 3. Coller dans le formulaire de signature de UCM
# 4. Télécharger le certificat signé
# 5. Enregistrer sous ~/.ssh/id_work-cert.pub

# 6. Se connecter
ssh -i ~/.ssh/id_work user@server
\`\`\`

### Mode génération
UCM génère à la fois la paire de clés et le certificat. Utilisez ce mode lorsque vous devez provisionner des identifiants de manière centralisée.

> ⚠ **Téléchargez la clé privée immédiatement** : elle n'est pas stockée dans UCM et ne peut pas être récupérée.

**Procédure :**
1. Sélectionnez une AC et remplissez les détails du certificat
2. Choisissez le mode « Générer »
3. Cliquez sur **Émettre un certificat**
4. Téléchargez les trois fichiers :
   - Clé privée (\`keyid\`) : **Conservez-la en lieu sûr !**
   - Certificat (\`keyid-cert.pub\`)
   - Clé publique (\`keyid.pub\`)

## Champs du certificat

### Key ID
Un identifiant intégré dans le certificat. Le serveur SSH le journalise lorsque le certificat est utilisé, comme identité du titulaire.

L'AC le définit à \`principals@CA name\` (ex. \`deploy@Production User CA\`). Un demandeur ne peut en choisir un autre que sur une AC où **Laisser les demandeurs définir l'identifiant de clé** est coché ; ailleurs, une telle demande est refusée.

**Bons exemples de Key ID, là où c'est autorisé :** \`jdoe-prod-2025\`, \`webserver-01\`, \`deploy-ci-pipeline\`

### Principals
Les principals définissent **qui** (certificats utilisateur) ou **quoi** (certificats hôte) le certificat autorise :

- **Certificats utilisateur** : liste des noms d'utilisateur sous lesquels le titulaire peut se connecter (ex. : \`deploy\`, \`admin\`)
- **Certificats d'hôte** : liste des noms d'hôte ou IP par lesquels le serveur est connu (ex. : \`web01.example.com\`, \`10.0.1.5\`)

> 💡 Au moins un principal est requis : listez les noms d'utilisateur ou d'hôte pour lesquels le certificat est valide.

### Validité

Choisissez un préréglage ou définissez une durée personnalisée :

| Préréglage | Cas d'usage |
|------------|-------------|
| 1 heure | Pipelines CI/CD, tâches ponctuelles |
| 8 heures | Accès pour une journée de travail standard |
| 24 heures | Accès étendu |
| 7 jours | Accès par sprint |
| 30 jours | Rotation mensuelle |
| 365 jours | Comptes de service à longue durée de vie |

Les certificats éphémères (8h-24h) sont recommandés pour les utilisateurs humains. Une validité plus longue est acceptable pour les comptes de service automatisés.

Un certificat est valide dès 5 minutes avant son émission, si bien qu'un serveur dont l'horloge retarde légèrement l'accepte aussitôt ; la durée de vie compte toujours à partir de l'émission (v2.252).

### Extensions (certificats utilisateur uniquement)

| Extension | Description |
|-----------|-------------|
| permit-pty | Autorise les sessions de terminal interactif |
| permit-agent-forwarding | Autorise le transfert d'agent SSH |
| permit-X11-forwarding | Autorise le transfert d'affichage X11 |
| permit-port-forwarding | Autorise le transfert de port TCP |
| permit-user-rc | Autorise l'exécution de ~/.ssh/rc à la connexion |

### Options critiques (certificats utilisateur uniquement)

| Option | Description |
|--------|-------------|
| force-command | Restreint le certificat à une seule commande |
| source-address | Restreint à des adresses sources ou des réseaux CIDR, séparés par des virgules (\`10.0.0.0/8,2001:db8::/32\`) |
| verify-required | Exige une clé FIDO ayant vérifié l'utilisateur (PIN ou biométrie), sans valeur |

Un serveur refuse un certificat portant une option critique qu'il ne connaît pas : UCM ne signe donc que celles-ci et les options de fournisseur nommées \`name@domain\`. OpenSSH ne définit aucune option critique pour les certificats d'hôte : une demande d'hôte qui en porte une est refusée (v2.252).

**Exemple :** Un certificat avec \`force-command=ls\` et \`source-address=10.0.0.0/8\` ne peut exécuter que \`ls\` et uniquement depuis le réseau 10.x.x.x.

## Utilisation des certificats

### Certificat utilisateur
\`\`\`bash
# Placez le certificat à côté de la clé privée
# Si la clé est ~/.ssh/id_work, le certificat doit être ~/.ssh/id_work-cert.pub
cp downloaded-cert.pub ~/.ssh/id_work-cert.pub

# SSH utilise automatiquement le certificat
ssh user@server
\`\`\`

### Certificat d'hôte
\`\`\`bash
# Sur le serveur : placez le certificat d'hôte
sudo cp host-cert.pub /etc/ssh/ssh_host_ed25519_key-cert.pub

# Ajoutez à sshd_config
echo "HostCertificate /etc/ssh/ssh_host_ed25519_key-cert.pub" | sudo tee -a /etc/ssh/sshd_config
sudo systemctl restart sshd
\`\`\`

Sur les clients, ajoutez la Host AC à known_hosts :
\`\`\`
@cert-authority *.example.com ssh-ed25519 AAAA...
\`\`\`

## Révocation

1. Sélectionnez un certificat dans le tableau
2. Cliquez sur **Révoquer** dans le panneau de détail
3. Le certificat est ajouté à la liste de révocation de clés (KRL) de l'AC
4. Téléchargez et déployez la KRL mise à jour sur les serveurs (depuis la page AC SSH)

Un certificat révoqué reste dans la KRL, et dans la liste, jusqu'à son expiration : le supprimer plus tôt est refusé, puisque la KRL est construite à partir de ces enregistrements et que le certificat serait de nouveau accepté. Chaque téléchargement de la KRL porte un numéro de version plus élevé (v2.252).

> ⚠ La révocation ne prend effet que lorsque les serveurs vérifient la KRL via \`RevokedKeys\` dans sshd_config.

## Dépannage

| Problème | Solution |
|----------|----------|
| Permission denied (publickey) | Vérifiez que l'AC est approuvée sur le serveur (TrustedUserCAKeys) |
| Certificat non utilisé | Assurez-vous que le fichier certificat est nommé \`<key>-cert.pub\` à côté de la clé privée |
| Non-correspondance de principal | Le nom d'utilisateur SSH doit figurer dans les principals du certificat |
| Certificat expiré | Émettez un nouveau certificat avec une validité appropriée |
| Échec de vérification de l'hôte | Ajoutez la Host AC à known_hosts avec @cert-authority |
`
  }
}
