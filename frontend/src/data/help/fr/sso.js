export default {
  helpContent: {
    title: 'Authentification unique',
    subtitle: 'Intégration SAML, OAuth2 et LDAP',
    overview: 'Configurez l\'authentification unique pour permettre aux utilisateurs de s\'authentifier via le fournisseur d\'identité de leur organisation. Prend en charge les protocoles SAML 2.0, OAuth2/OIDC et LDAP.',
    sections: [
      {
        title: 'SAML 2.0',
        items: [
          { label: 'Fournisseur d\'identité', text: 'Configurer l\'URL de métadonnées IDP ou téléverser le XML' },
          { label: 'URL de métadonnées SP', text: 'Fournissez cette URL à votre IDP pour configurer automatiquement UCM comme fournisseur de services' },
          { label: 'Certificat SP', text: 'Certificat HTTPS d\'UCM inclus dans les métadonnées, doit être approuvé par l\'IDP sinon les métadonnées seront rejetées' },
          { label: 'Entity ID', text: 'Identifiant d\'entité du fournisseur de services UCM' },
          { label: 'URL ACS', text: 'URL de callback du service de consommation d\'assertions (Assertion Consumer Service)' },
          { label: 'Mappage d\'attributs', text: 'Colonne de gauche : le nom de l\'attribut envoyé par l\'IDP. Colonne de droite : le champ UCM qu\'il renseigne (username, email, fullname ou groups). Exemple : user.userprincipalname → username.' },
          { label: 'Groupes pour le mappage de rôles', text: 'Lus dans les attributs mappés vers groups, sinon dans groups et dans les claims de groupes et de rôles de Microsoft Entra ID / AD FS. Quand Entra ID envoie groups.link au lieu des groupes (utilisateurs membres de plus de 150 groupes), un avertissement est journalisé et le rôle par défaut s\'applique : n\'émettez que les groupes attribués à l\'application, ou des rôles d\'application.' },
          { label: 'Connexion initiée par l\'IdP', text: 'Accepte les connexions lancées depuis le portail de l\'IdP, contrôlées comme toute autre réponse. Activée pour les providers créés avant la 2.243, désactivée pour les nouveaux : à activer seulement si les utilisateurs partent du portail de l\'IdP.' },
          { label: 'Format NameID', text: 'Non spécifié (défaut de l\'IdP), Persistent, Adresse e-mail ou Transitoire : envoyé dans chaque requête de connexion et publié dans les métadonnées SP. Persistent donne un identifiant stable ; un NameID transitoire ne sert jamais à reconnaître le compte.' },
          { label: 'Déconnexion unique', text: 'Une LogoutRequest signée par l\'IdP et envoyée à l\'URL SLO des métadonnées SP (HTTP-Redirect) ferme la session UCM de ce NameID dans ce navigateur, sauf si son SessionIndex désigne une autre session. Une LogoutResponse repart vers l\'URL SLO de l\'IdP, signée avec la clé SP (non signée quand le certificat SP n\'est pas RSA, ce qu\'un IdP strict refuse) ; sans URL SLO de l\'IdP, le navigateur retourne à la page de connexion. Une requête non signée, falsifiée, périmée ou rejouée, ou sans Destination, est refusée.' },
        ]
      },
      {
        title: 'OAuth2 / OIDC',
        items: [
          { label: 'URL d\'autorisation', text: 'Point de terminaison d\'autorisation OAuth2' },
          { label: 'URL de jeton', text: 'Point de terminaison de jeton OAuth2' },
          { label: 'Client ID/Secret', text: 'Identifiants client OAuth2 fournis par votre IDP' },
          { label: 'Scopes', text: 'Scopes OAuth2 à demander (openid, profile, email)' },
          { label: 'Création automatique d\'utilisateurs', text: 'Créer automatiquement des comptes UCM à la première connexion SSO' },
        ]
      },
      {
        title: 'Provisionnement des rôles (#81)',
        items: [
          { label: 'Correspondance d\'identité', text: 'Une connexion ouvre le compte lié à l\'identifiant de l\'IdP (sub OIDC, NameID persistant SAML, entryUUID ou objectGUID LDAP). Un nom d\'utilisateur ou un e-mail ne correspond qu\'à un compte du même fournisseur pas encore lié ; un compte local, ou lié à une autre identité, est refusé à la connexion. Pour fusionner un compte local, utilisez d\'abord Lier au SSO dans Utilisateurs : sa prochaine connexion via ce fournisseur lie l\'identifiant.' },
          { label: 'Rôle par défaut', text: 'Donné aux comptes créés à la première connexion SSO quand le fournisseur n\'a aucune règle de mappage de rôles, et comme rôle de base d\'un nouveau compte dont la règle ne donne qu\'un rôle personnalisé (viewer si Aucun). Aucun : personne ne se connecte sans règle. Les changements de rôle faits ensuite dans UCM sont préservés.' },
          { label: 'Mappage de rôles', text: 'Mapper les groupes externes (Azure AD, Okta, LDAP) → rôles UCM (admin / operator / auditor / viewer) ou rôles personnalisés. Avec au moins une règle, un utilisateur qu\'aucune règle ne retient est refusé à chaque connexion SSO (OIDC, SAML, LDAP), compte nouveau ou existant ; une connexion par passkey ou certificat n\'est pas contrôlée. Utilisé à la création de l\'utilisateur, et à chaque connexion quand la synchronisation des rôles est activée. Quand plusieurs groupes correspondent, le rôle au privilège le plus élevé l\'emporte (admin > operator > auditor > viewer) : l\'ordre des entrées n\'a pas d\'importance (#221). Chaque groupe peut aussi nommer un rôle personnalisé (choisi parmi les rôles personnalisés existants) : il s\'ajoute au rôle de base, ou s\'utilise seul. Si plusieurs groupes correspondants donnent un rôle personnalisé, le premier de la liste l\'emporte. Avec la synchronisation des rôles activée, un rôle personnalisé défini par le SSO est retiré quand aucun groupe n\'en donne ; un rôle personnalisé attribué à la main dans UCM n\'est jamais touché. Les rôles système ne peuvent pas servir de rôle personnalisé.' },
          { label: 'Synchroniser le rôle à chaque connexion', text: 'OFF (par défaut) : le SSO n\'écrase jamais les rôles gérés dans UCM. ON : le rôle est re-synchronisé depuis role_mapping à chaque connexion ; une règle correspondante qui ne donne aucun rôle de base conserve celui qui est stocké (default_role n\'est jamais ré-appliqué).' },
          { label: 'Imposer la 2FA', text: 'Les utilisateurs de ce fournisseur doivent enrôler un second facteur. Les connexions LDAP demandent un code TOTP ou une clé de sécurité enrôlés, comme les connexions locales, avec ou sans cette option ; les connexions OIDC et SAML exigent seulement l\'enrôlement et s\'en remettent à l\'IdP pour la MFA.' },
          { label: 'Mise à jour automatique des utilisateurs', text: 'Met à jour l\'e-mail et le nom complet à chaque connexion. Ne touche PAS au rôle.' },
        ]
      },
      {
        title: 'LDAP',
        items: [
          { label: 'Serveur', text: 'Nom d\'hôte et port du serveur LDAP (389 ou 636 pour SSL)' },
          { label: 'StartTLS', text: 'Sur un port LDAP en clair, passe la connexion en TLS avant tout bind, avec la même vérification de certificat que LDAPS. Activé par défaut pour un nouveau fournisseur sans SSL/TLS. Sans SSL/TLS ni StartTLS, le bind et les mots de passe des utilisateurs circulent en clair sur le réseau.' },
          { label: 'DN de liaison', text: 'Nom distinctif (DN) pour l\'authentification bind LDAP' },
          { label: 'DN de base', text: 'Base de recherche pour les recherches d\'utilisateurs' },
          { label: 'Filtre utilisateur', text: 'Filtre LDAP pour la correspondance des utilisateurs (par ex. (uid={username}))' },
          { label: 'Mappage d\'attributs', text: 'Mapper les attributs LDAP au nom d\'utilisateur, e-mail et nom complet' },
          { label: 'Attribut d\'ID unique', text: 'Identifiant immuable qui reconnaît le compte (entryUUID, objectGUID). Un compte lié par son DN passe à cet identifiant à sa prochaine connexion ; passer d\'un attribut d\'identifiant à un autre refuse tous les utilisateurs liés jusqu\'à Délier puis Lier au SSO.' },
        ]
      },
    ],
    tips: [
      'Testez SSO avec un compte non-admin d\'abord pour éviter les verrouillages',
      'Conservez la connexion admin locale disponible comme repli',
      'Mappez l\'attribut e-mail de l\'IDP pour garantir une identification unique des utilisateurs',
      'Utilisez l\'URL de métadonnées SP pour configurer automatiquement votre IDP (SAML)',
      'Le certificat HTTPS d\'UCM doit être approuvé par l\'IDP pour que les métadonnées SAML soient acceptées',
    ],
    warnings: [
      'Un SSO mal configuré peut verrouiller tous les utilisateurs : conservez toujours un admin local',
    ],
  },
  helpGuides: {
    title: 'Authentification unique',
    content: `
## Vue d'ensemble

SSO permet aux utilisateurs de s'authentifier en utilisant le fournisseur d'identité (IDP) de leur organisation, éliminant le besoin d'identifiants UCM séparés. UCM prend en charge **SAML 2.0**, **OAuth2/OIDC** et **LDAP**.

## SAML 2.0

### URL de métadonnées SP

UCM fournit une **URL de métadonnées du fournisseur de services (SP)** que vous pouvez donner à votre IDP pour la configuration automatique :

\`\`\`
https://votre-hote-ucm:8443/api/v2/sso/saml/metadata
\`\`\`

Cette URL retourne un document XML conforme SAML 2.0 contenant :
- **Entity ID** : Identifiant du fournisseur de services UCM
- **URL ACS** : Point de terminaison du service de consommation d'assertions (HTTP-POST)
- **URL SLO** : Point de terminaison du service de déconnexion unique
- **Certificat de signature** : Certificat HTTPS d'UCM pour la vérification de signature
- **Format NameID** : Le réglage **Format du NameID** du fournisseur (Non spécifié, Persistent, Adresse e-mail ou Transitoire), aussi envoyé dans chaque requête de connexion. Persistent donne un identifiant stable ; un NameID transitoire ne sert jamais à reconnaître le compte

Copiez cette URL dans la configuration « Ajouter un fournisseur de services » ou « Application SAML » de votre IDP.

> ⚠️ **Important :** Le certificat HTTPS d'UCM doit être **approuvé par l'IDP**. Si l'IDP ne peut pas valider le certificat (par ex. auto-signé ou émis par une CA privée), il rejettera les métadonnées comme invalides. Importez le certificat CA d'UCM dans le magasin de confiance de l'IDP, ou utilisez un certificat signé par une CA publiquement approuvée.

### Configuration
1. Obtenez l'URL de métadonnées IDP ou le fichier XML de votre fournisseur d'identité
2. Dans UCM, allez dans **Paramètres → SSO**
3. Cliquez sur **Ajouter un fournisseur** → SAML
4. Entrez l'**URL de métadonnées IDP** : UCM remplit automatiquement l'Entity ID, les URL SSO/SLO et le certificat
5. Ou collez directement le XML de métadonnées IDP
6. Configurez le **mappage d'attributs** (nom d'utilisateur, e-mail, groupes)
7. Cliquez sur **Enregistrer** et **Activer**

### Mappage d'attributs
Mappez les attributs SAML de l'IDP aux champs utilisateur UCM :
- \`username\` → Nom d'utilisateur UCM (requis)
- \`email\` → E-mail UCM (requis)
- \`groups\` → lu par les règles de mappage de rôles (optionnel) ; il ne rend pas l'utilisateur membre de groupes UCM

### Déconnexion unique
Quand l'IdP termine une session, il envoie une **LogoutRequest** signée via le navigateur à l'URL SLO. UCM vérifie la signature de l'IdP, l'émetteur, la Destination (obligatoire), l'IssueInstant (dans la fenêtre d'horloge) et que la requête n'a pas déjà servi, ferme la session UCM de ce NameID dans ce navigateur (quand la requête porte des SessionIndex, seulement une session qu'ils désignent), puis envoie une **LogoutResponse** à l'URL SLO de l'IdP, signée avec la clé SP ; un certificat SP qui n'est pas RSA l'envoie non signée, ce qu'un IdP strict comme AD FS refuse. Sans URL SLO de l'IdP, le navigateur retourne à la page de connexion UCM. Une LogoutRequest non signée ou falsifiée est refusée et la session reste ouverte.

### Connexion initiée par l'IdP
Une connexion lancée depuis le portail de l'IdP arrive sans requête d'UCM. **Autoriser la connexion initiée par l'IdP** l'accepte, avec les mêmes contrôles de signature, d'audience, de Destination, de validité et d'anti-rejeu. Les providers créés avant la 2.243 la gardent activée ; les nouveaux l'ont désactivée. Activez-la seulement si les utilisateurs partent du portail de l'IdP.

## OAuth2 / OIDC

### Configuration
1. Enregistrez UCM comme client dans votre fournisseur OAuth2/OIDC
2. Définissez l'**URI de redirection** à : \`https://votre-hote-ucm:8443/api/v2/sso/callback/oauth2\`
3. Copiez le **Client ID** et le **Client Secret**
4. Dans UCM, allez dans **Paramètres → SSO**
5. Cliquez sur **Ajouter un fournisseur** → OAuth2
6. Entrez l'**URL d'autorisation** et l'**URL de jeton**
7. Entrez l'**URL d'info utilisateur** (pour récupérer les attributs utilisateur après la connexion)
8. Entrez le Client ID et le Secret
9. Configurez les scopes (openid, profile, email)
10. Cliquez sur **Enregistrer** et **Activer**

### Création automatique d'utilisateurs
Lorsqu'elle est activée, un nouveau compte utilisateur UCM est automatiquement créé à la première connexion SSO, en utilisant les attributs fournis par l'IDP, avec le rôle que donne sa règle de mappage, sinon le rôle par défaut.

## Qui peut se connecter

### Correspondance d'identité
Une connexion ouvre le compte lié à l'identifiant de l'IdP : \`sub\` OIDC, NameID persistant SAML, \`entryUUID\` ou \`objectGUID\` LDAP. Un nom d'utilisateur ou un e-mail ne correspond qu'à un compte du même fournisseur qui n'est pas encore lié (créé avant les identifiants stables, ou lié par un administrateur) ; un e-mail que l'IdP OIDC marque non vérifié (\`email_verified\` faux) ne correspond à aucun. Un compte local, ou lié à une autre identité, n'est jamais ouvert par une connexion SSO : la connexion est refusée et consignée dans le journal d'audit. Pour fusionner un compte local dans une identité SSO, utilisez d'abord **Lier au SSO** sur cet utilisateur ; sa prochaine connexion via ce fournisseur lie l'identifiant de l'IdP.

Quand un fournisseur est supprimé, ses utilisateurs sont conservés : un fournisseur recréé pour le même IdP (même émetteur, entity ID, ou serveur LDAP et DN de base) les reprend à leur prochaine connexion. Sinon, et pour les utilisateurs qu'une restauration a laissés sans fournisseur, utilisez **Délier** puis **Lier au SSO** sur chaque compte.

### Règles de mappage de rôles
- **Au moins une règle** : un utilisateur qu'aucune règle ne retient est refusé à chaque connexion SSO (OIDC, SAML, LDAP), que le compte soit nouveau ou existe déjà ; une connexion par passkey ou certificat n'est pas contrôlée
- **Aucune règle** : tout utilisateur que le fournisseur authentifie peut se connecter ; les nouveaux comptes reçoivent le **Rôle par défaut**
- Une règle qui ne donne qu'un rôle personnalisé : un nouveau compte reçoit le **Rôle par défaut** comme rôle de base (viewer si Aucun)
- **Rôle par défaut : Aucun** sans règle : personne ne peut se connecter via le fournisseur

La section **Provisionnement des utilisateurs** s'ouvre d'elle-même et affiche un avertissement quand le fournisseur n'a aucune règle.

## LDAP

### Configuration
1. Dans UCM, allez dans **Paramètres → SSO**
2. Cliquez sur **Ajouter un fournisseur** → LDAP
3. Entrez le **serveur LDAP** nom d'hôte et **port** (389 pour LDAP, 636 pour LDAPS)
4. Activez **Utiliser SSL/TLS** (LDAPS, port 636) ou, sur le port 389, **Utiliser StartTLS** : la connexion passe en TLS avant tout bind, avec la même vérification de certificat. Sans l'un ni l'autre, le bind et les mots de passe des utilisateurs circulent en clair sur le réseau
5. Entrez le **DN de liaison** et le **mot de passe de liaison** (identifiants du compte de service)
6. Entrez le **DN de base** (base de recherche pour les recherches d'utilisateurs)
7. Configurez le **filtre utilisateur** (par ex. \`(uid={username})\` ou \`(sAMAccountName={username})\` pour AD)
8. Mappez les attributs LDAP : **nom d'utilisateur**, **e-mail**, **nom complet**, et l'**attribut d'ID unique** (\`entryUUID\`, \`objectGUID\`). Un compte lié par son DN passe à cet identifiant à sa prochaine connexion ; passer d'un attribut d'identifiant à un autre refuse tous les utilisateurs liés jusqu'à **Délier** puis **Lier au SSO**
9. Cliquez sur **Tester la connexion** pour vérifier, puis **Enregistrer** et **Activer**

### Active Directory
Pour Microsoft Active Directory, utilisez :
- Port : **389** (ou 636 avec SSL)
- Filtre utilisateur : \`(sAMAccountName={username})\`
- Attribut nom d'utilisateur : \`sAMAccountName\`
- Attribut e-mail : \`mail\`
- Attribut nom complet : \`displayName\`

## Flux de connexion
1. L'utilisateur clique sur **Se connecter avec SSO** sur la page de connexion UCM (ou entre les identifiants LDAP)
2. Pour SAML/OAuth2 : l'utilisateur est redirigé vers l'IDP, s'authentifie, puis est redirigé
3. Pour LDAP : les identifiants sont vérifiés directement contre le serveur LDAP
4. UCM crée ou met à jour le compte utilisateur
5. L'utilisateur est connecté

> ⚠ Conservez toujours au moins un compte admin local comme repli en cas de mauvaise configuration SSO qui verrouille tout le monde.

> 💡 Testez SSO avec un compte non-admin avant d'en faire la méthode d'authentification principale.

> 💡 Utilisez le bouton **Tester la connexion** pour vérifier votre configuration avant d'activer un fournisseur.
`
  }
}
