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
          { label: 'Mappage d\'attributs', text: 'Colonne de gauche : le nom de l\'attribut envoyé par l\'IDP. Colonne de droite : le champ UCM qu\'il renseigne (username, email, fullname ou groups). Exemple : user.userprincipalname → username. Un attribut tient sur une ligne : une seconde ligne du même nom est signalée et le fournisseur ne s\'enregistre pas tant que l\'une des deux n\'est pas changée ou retirée.' },
          { label: 'Groupes pour le mappage de rôles', text: 'Lus dans les attributs mappés vers groups, sinon dans groups et dans les claims de groupes et de rôles de Microsoft Entra ID / AD FS. Quand Entra ID envoie groups.link au lieu des groupes (utilisateurs membres de plus de 150 groupes), un avertissement est journalisé et, quand des règles de mappage de rôles existent, l\'utilisateur est refusé : n\'émettez que les groupes attribués à l\'application, ou des rôles d\'application.' },
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
          { label: 'Groupes pour le mappage de rôles', text: 'Les valeurs des claims roles et groups, lues ensemble dans le jeton d\'identité de la connexion et dans la réponse UserInfo. Microsoft Entra ID ne les envoie que dans le jeton d\'identité : ajoutez le claim de groupes dans la configuration du jeton de l\'application (ses valeurs sont les identifiants d\'objet des groupes, les clés de mappage sont donc ces identifiants), ou utilisez des rôles d\'application. Un utilisateur membre de plus de 200 groupes environ ne reçoit pas de claim de groupes d\'Entra ID : un avertissement est journalisé et seuls les rôles d\'application peuvent correspondre. N\'émettez que les groupes attribués à l\'application, ou des rôles d\'application.' },
        ]
      },
      {
        title: 'Provisionnement des rôles (#81)',
        items: [
          { label: 'Correspondance d\'identité', text: 'Une connexion ouvre le compte lié à l\'identifiant de l\'IdP (sub OIDC, NameID persistant SAML, entryUUID ou objectGUID LDAP). Un nom d\'utilisateur ou un e-mail ne correspond qu\'à un compte rattaché à ce fournisseur et pas encore lié ; un compte local, un compte rattaché à d\'autres fournisseurs seulement, ou lié à une autre identité, est refusé à la connexion. Rattacher un fournisseur, dans Utilisateurs, ajoute un fournisseur à tout compte, que ses autres fournisseurs continuent d\'ouvrir : sa prochaine connexion via le nouveau lie l\'identifiant.' },
          { label: 'Rôle par défaut', text: 'Donné aux comptes créés à la première connexion SSO quand le fournisseur n\'a aucune règle de mappage de rôles, et comme rôle de base d\'un nouveau compte dont la règle ne donne qu\'un rôle personnalisé (viewer si Aucun). Aucun : personne ne se connecte sans règle. Les changements de rôle faits ensuite dans UCM sont préservés.' },
          { label: 'Mappage de rôles', text: 'Mapper les groupes externes (Azure AD, Okta, LDAP) → rôles UCM (admin / operator / auditor / viewer) ou rôles personnalisés. Avec au moins une règle, un utilisateur qu\'aucune règle ne retient est refusé à chaque connexion SSO (OIDC, SAML, LDAP), compte nouveau ou existant ; une connexion par passkey ou certificat n\'est pas contrôlée. Utilisé à la création de l\'utilisateur, et à chaque connexion quand la synchronisation des rôles est activée. Quand plusieurs groupes correspondent, le rôle au privilège le plus élevé l\'emporte (admin > operator > auditor > viewer) : l\'ordre des entrées n\'a pas d\'importance (#221). Chaque groupe peut aussi nommer un rôle personnalisé (choisi parmi les rôles personnalisés existants) : il s\'ajoute au rôle de base, ou s\'utilise seul. Si plusieurs groupes correspondants donnent un rôle personnalisé, le premier de la liste l\'emporte. Avec la synchronisation des rôles activée, un rôle personnalisé défini par le SSO est retiré quand aucun groupe n\'en donne ; un rôle personnalisé attribué à la main dans UCM n\'est jamais touché. Les rôles système ne peuvent pas servir de rôle personnalisé.' },
          { label: 'Synchroniser le rôle à chaque connexion', text: 'OFF (par défaut) : le SSO n\'écrase jamais les rôles gérés dans UCM. ON : le rôle est re-synchronisé depuis role_mapping à chaque connexion ; une règle correspondante qui ne donne aucun rôle de base conserve celui qui est stocké (default_role n\'est jamais ré-appliqué). Un compte rattaché à plusieurs fournisseurs suit les règles de celui par lequel il s\'est connecté en dernier.' },
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
          { label: 'Attribut d\'ID unique', text: 'Identifiant immuable qui reconnaît le compte (entryUUID, objectGUID). Un compte lié par son DN passe à cet identifiant à sa prochaine connexion ; passer d\'un attribut d\'identifiant à un autre refuse tous les utilisateurs liés jusqu\'à Réinitialiser l\'identité sur chaque compte.' },
          { label: 'Groupes', text: 'Avec memberOf, lus sur l\'entrée de l\'utilisateur ; avec member ou uniqueMember, cherchés sous la base de recherche des groupes si elle est renseignée, sinon sous le parent du DN de base quand l\'annuaire le contient, puis sous le DN de base si cette recherche échoue, à défaut sous le DN de base ; avec (objectClass=*) comme filtre de groupe par défaut. Appartenance directe seulement, sauf si l\'option Groupes imbriqués et groupe principal est active : sur Active Directory elle ajoute tous les groupes au-dessus de ceux de l\'utilisateur, à toute profondeur, cherchés sous les mêmes bases qu\'une recherche par member (avec memberOf aussi), et le groupe principal (en général le RID 513, Domain Users sur un domaine anglais, Utilisateurs du domaine sur un domaine français), dont le nom ne compte que sous cette base et à travers le filtre de groupe ; quand des règles ou des groupes requis existent, sur un autre annuaire, ou quand cette recherche échoue ou dépasse 1000 groupes, la connexion est refusée. Les noms se comparent aux règles et aux groupes requis sans tenir compte de la casse, des espaces de bord ni de la longueur des suites d\'espaces internes. Quand des règles ou des groupes requis existent et que les groupes ne peuvent pas être lus, la connexion est refusée en le disant. « Tester le mapping » lit les groupes et décide comme la connexion.' },
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
https://your-ucm-host:8443/api/v2/sso/saml/metadata
\`\`\`

Cette URL retourne un document XML conforme SAML 2.0 contenant :
- **Entity ID** : Identifiant du fournisseur de services UCM
- **URL ACS** : Point de terminaison du service de consommation d'assertions (HTTP-POST)
- **URL SLO** : Point de terminaison de l'IdP qui reçoit la LogoutResponse par HTTP-Redirect ; l'import des métadonnées conserve le ResponseLocation du service de déconnexion unique HTTP-Redirect, sinon son Location. Voir Déconnexion unique ci-dessous
- **Certificat de signature** : Certificat HTTPS d'UCM pour la vérification de signature
- **Format NameID** : Le réglage **Format du NameID** du fournisseur (Non spécifié, Persistent, Adresse e-mail ou Transitoire), aussi envoyé dans chaque requête de connexion. Persistent donne un identifiant stable ; un NameID transitoire ne sert jamais à reconnaître le compte

Copiez cette URL dans la configuration « Ajouter un fournisseur de services » ou « Application SAML » de votre IDP.

> ⚠️ **Important :** Le certificat HTTPS d'UCM doit être **approuvé par l'IDP**. Si l'IDP ne peut pas valider le certificat (par ex. auto-signé ou émis par une AC privée), il rejettera les métadonnées comme invalides. Importez le certificat AC d'UCM dans le magasin de confiance de l'IDP, ou utilisez un certificat signé par une AC publiquement approuvée.

### Configuration
1. Obtenez l'URL de métadonnées IDP ou le fichier XML de votre fournisseur d'identité
2. Dans UCM, allez dans **Paramètres → SSO**
3. Sur la carte **SAML 2.0**, cliquez sur **Configurer**
4. Entrez l'**URL de métadonnées IDP** : UCM remplit automatiquement l'Entity ID, les URL SSO/SLO et le certificat
5. Ou collez directement le XML de métadonnées IDP
6. Configurez le **mappage d'attributs** (nom d'utilisateur, e-mail, groupes)
7. Cliquez sur **Enregistrer** et **Activer**

### Mappage d'attributs
Mappez les attributs SAML de l'IDP aux champs utilisateur UCM :
- \`username\` → Nom d'utilisateur UCM (requis)
- \`email\` → E-mail UCM (requis)
- \`groups\` → lu par les règles de mappage de rôles (optionnel) ; il ne rend pas l'utilisateur membre de groupes UCM

Les groupes sont lus dans les attributs mappés vers \`groups\`, sinon dans \`groups\` et les URI de claims de Microsoft. Keycloak envoie les rôles dans \`Role\` et les groupes dans \`member\`, Shibboleth envoie \`urn:oid:1.3.6.1.4.1.5923.1.5.1.1\` (isMemberOf), d'autres IdP \`memberOf\` : ils ne sont lus qu'une fois mappés vers \`groups\`. Les boutons sous le mappage d'attributs ajoutent une telle ligne, qui prend effet une fois enregistrée. Un attribut est reconnu par son Name, jamais par son FriendlyName (SAML Core 2.0 §2.7.3.1) : mappez \`urn:oid:1.3.6.1.4.1.5923.1.5.1.1\`, pas \`isMemberOf\`. Une ligne de la nouvelle forme (\`attribut → groups\`) remplace une ligne de l'ancienne forme (\`groups → attribut\`), qui n'est alors plus lue ; l'écran nomme, sous le mapping, les attributs qu'aucune ligne ne lit plus. Pour garder les deux, remplacez l'ancienne ligne par une ligne \`attribut → groups\`.

### Déconnexion unique
Quand l'IdP termine une session, il envoie une **LogoutRequest** signée via le navigateur à l'URL SLO. UCM vérifie la signature de l'IdP, l'émetteur, la Destination (obligatoire), l'IssueInstant (dans la fenêtre d'horloge) et que la requête n'a pas déjà servi, ferme la session UCM de ce NameID dans ce navigateur (quand la requête porte des SessionIndex, seulement une session qu'ils désignent), puis envoie une **LogoutResponse** à l'URL SLO de l'IdP, signée avec la clé SP ; un certificat SP qui n'est pas RSA l'envoie non signée, ce qu'un IdP strict comme AD FS refuse. Sans URL SLO de l'IdP, le navigateur retourne à la page de connexion UCM. Une LogoutRequest non signée ou falsifiée est refusée et la session reste ouverte.

### Connexion initiée par l'IdP
Une connexion lancée depuis le portail de l'IdP arrive sans requête d'UCM. **Autoriser la connexion initiée par l'IdP** l'accepte, avec les mêmes contrôles de signature, d'audience, de Destination, de validité et d'anti-rejeu. Les providers créés avant la 2.243 la gardent activée ; les nouveaux l'ont désactivée. Activez-la seulement si les utilisateurs partent du portail de l'IdP.

## OAuth2 / OIDC

### Configuration
1. Enregistrez UCM comme client dans votre fournisseur OAuth2/OIDC
2. Définissez l'**URI de redirection** à : \`https://your-ucm-host:8443/api/v2/sso/callback/oauth2\`
3. Copiez le **Client ID** et le **Client Secret**
4. Dans UCM, allez dans **Paramètres → SSO**
5. Sur la carte **OAuth2 / OIDC**, cliquez sur **Configurer**
6. Entrez l'**URL d'autorisation** et l'**URL de jeton**
7. Entrez l'**URL d'info utilisateur** (pour récupérer les attributs utilisateur après la connexion)
8. Entrez le Client ID et le Secret
9. Configurez les scopes (openid, profile, email)
10. Cliquez sur **Enregistrer** et **Activer**

### Préréglages
- **Microsoft Entra ID** (un seul locataire) remplit les URL et l'émetteur \`https://login.microsoftonline.com/{tenant}/v2.0\` : remplacez \`{tenant}\` par l'identifiant de l'annuaire (locataire) dans les trois. Un fournisseur enregistré avec \`{tenant}\` laissé tel quel est refusé. Pour une application multi-locataire, mettez l'émetteur \`https://login.microsoftonline.com/organizations/v2.0\` (ou \`common\`), les URL de la même autorité, et listez les identifiants de locataires (GUID) sous **Locataires acceptés** : un jeton n'est accepté que si son \`tid\` est listé, si son émetteur est le gabarit de la découverte \`https://login.microsoftonline.com/{tenantid}/v2.0\` avec ce \`tid\`, et si sa clé de signature, quand elle nomme un émetteur, nomme celui-là. Il n'y a pas de joker : le locataire des comptes Microsoft personnels n'est accepté que s'il est listé, et la vérification du jeton d'identité doit rester active. Une identité appartient à son locataire : le même \`sub\` dans deux locataires fait deux comptes, et un locataire retiré de la liste ne se connecte plus. Un compte lié avant que le fournisseur n'accepte plusieurs locataires garde son \`sub\` seul : réinitialisez son identité SSO en choisissant son locataire pour que sa prochaine connexion lie celle du locataire. Accepter un locataire, c'est faire confiance à ses administrateurs, qui choisissent les noms et les e-mails de leurs utilisateurs : un compte rattaché et pas encore lié n'est lié par son nom d'utilisateur ou son e-mail que par une connexion depuis le **Locataire attendu** choisi au rattachement du fournisseur ou à la réinitialisation de l'identité (par défaut le locataire de l'ancienne identité), et un rattachement sans locataire attendu n'est lié par aucune connexion. L'association des rôles ne lit les rôles et les groupes que des locataires listés sous **Locataires dont les rôles sont honorés**, ce qui confie à leurs administrateurs l'attribution des rôles d'UCM. Quand l'association des rôles a des règles, l'utilisateur d'un autre locataire accepté n'en satisfait aucune et est refusé à la connexion, compte existant compris ; sans règle, tout locataire accepté reçoit le rôle par défaut, si bien qu'un rôle par défaut d'administrateur fait de tout nouveau compte de tout locataire accepté un administrateur.
- **Google** remplit l'émetteur \`https://accounts.google.com\`.
- **GitHub** n'est pas un fournisseur OpenID Connect et n'émet pas de jeton d'identité : le préréglage désactive **Vérifier la signature de l'ID token** et associe \`login\` au nom d'utilisateur. Le compte est reconnu par son identifiant GitHub numérique \`id\` (UCM lit le \`sub\` de UserInfo, sinon \`id\`), jamais par le login ni l'e-mail.
- Changer de préréglage remet l'émetteur et le réglage de vérification que le précédent avait posés, sauf s'ils ont été modifiés depuis.

### Signature du jeton d'identité
RS256, RS384, RS512, PS256, PS384, PS512, ES256, ES384, ES512 et EdDSA (Ed25519, Ed448) sont acceptés, jamais \`none\` ni HS256, HS384 ou HS512. La clé de signature doit être du type et de la courbe que l'algorithme nomme, son \`alg\` et son \`use\`, s'ils sont présents, l'algorithme du jeton et \`sig\`, et une clé RSA doit faire 2048 bits ou plus. Sans URI JWKS, l'algorithme doit aussi figurer dans le document de découverte. En mode FIPS, EdDSA n'est accepté que si le module FIPS l'approuve, et une clé RSA doit avoir une taille paire de 2048 à 16384 bits. Un algorithme refusé est nommé dans l'entrée d'audit.

### Création automatique d'utilisateurs
Lorsqu'elle est activée, un nouveau compte utilisateur UCM est automatiquement créé à la première connexion SSO, en utilisant les attributs fournis par l'IDP, avec le rôle que donne sa règle de mappage, sinon le rôle par défaut.

### Groupes pour le mappage de rôles
Les règles de mappage de rôles comparent leurs clés aux valeurs des claims **roles** et **groups**, lues ensemble dans le jeton d'identité de la connexion et dans la réponse UserInfo. Microsoft Entra ID n'envoie les groupes et les rôles d'application que dans le jeton d'identité : dans l'inscription de l'application, ajoutez le claim de groupes sous **Configuration de jeton** (les valeurs sont les identifiants d'objet des groupes, les clés de mappage sont donc ces identifiants), ou définissez des rôles d'application et mappez leurs valeurs. Un utilisateur membre de plus de 200 groupes environ ne reçoit pas de claim de groupes d'Entra ID : UCM journalise un avertissement et seuls les rôles d'application peuvent correspondre. N'émettez que les groupes attribués à l'application, ou des rôles d'application. Avec **Vérifier la signature de l'ID token** désactivé, les groupes du jeton d'identité ne comptent que si l'URL de jeton est en HTTPS avec la vérification TLS active, et que l'émetteur et l'identifiant client sont renseignés et correspondent au jeton.

Une ligne \`claim → groups\` du mappage d'attributs fait de ce claim la source des groupes, dans le jeton d'identité et dans UserInfo aux mêmes conditions, à la place de **roles** et **groups**. Le nom est d'abord cherché tel quel (\`https://example.com/groups\`), puis comme un chemin par points à travers des objets imbriqués : pour Keycloak, \`realm_access.roles\` pour les rôles du realm et \`resource_access.<client id>.roles\` pour les rôles d'un client. Une valeur qui n'est ni une chaîne ni une liste de chaînes ne donne aucun groupe. Une ligne de la nouvelle forme (\`attribut → groups\`) remplace une ligne de l'ancienne forme (\`groups → attribut\`), qui n'est alors plus lue ; l'écran nomme, sous le mapping, les attributs qu'aucune ligne ne lit plus. Pour garder les deux, remplacez l'ancienne ligne par une ligne \`attribut → groups\`.

## Qui peut se connecter

### Correspondance d'identité
Une connexion ouvre le compte lié à l'identifiant de l'IdP : \`sub\` OIDC, NameID persistant SAML, \`entryUUID\` ou \`objectGUID\` LDAP. Un nom d'utilisateur ou un e-mail ne correspond qu'à un compte du même fournisseur qui n'est pas encore lié (créé avant les identifiants stables, ou lié par un administrateur) ; un e-mail que l'IdP OIDC marque non vérifié (\`email_verified\` faux) ne correspond à aucun. Un compte local, ou lié à une autre identité, n'est jamais ouvert par une connexion SSO : la connexion est refusée et consignée dans le journal d'audit. Quand aucun compte ne correspond, une connexion dont l'e-mail appartient à un compte rattaché à d'autres fournisseurs seulement ou laissé par un autre IdP ou un IdP inconnu (après une restauration, par exemple), ou, quand l'e-mail n'est pas vérifié, à un compte rattaché à ce fournisseur et pas encore lié à une identité, est refusée au lieu de recevoir un second compte. Un compte peut être rattaché à plusieurs fournisseurs, chacun avec sa propre identité, et aucune connexion ne rattache un fournisseur à un compte existant par son nom ou son e-mail : un administrateur le fait, avec **Rattacher un fournisseur** sur cet utilisateur. Cette action accepte un compte local et un compte d'autres fournisseurs, qui continuent de l'ouvrir ; **Réinitialiser l'identité** efface l'identité d'un rattachement que l'IdP a changée. La prochaine connexion via ce fournisseur lie l'identifiant de l'IdP, et aucun mot de passe local n'est demandé à un compte qui n'en a pas.

Quand un fournisseur est supprimé, ses rattachements sont conservés comme orphelins et les autres fournisseurs de chaque compte continuent de l'ouvrir : un fournisseur recréé pour le même IdP (même émetteur, même entity ID, ou même serveur LDAP et DN de base) les reprend à leur prochaine connexion. Sinon, et pour les rattachements qu'une restauration n'a pas pu placer, utilisez **Rattacher un fournisseur** sur chaque compte.

### Règles de mappage de rôles
- **Au moins une règle** : un utilisateur qu'aucune règle ne retient est refusé à chaque connexion SSO (OIDC, SAML, LDAP), que le compte soit nouveau ou existe déjà ; une connexion par passkey ou certificat n'est pas contrôlée
- **Aucune règle** : tout utilisateur que le fournisseur authentifie peut se connecter ; les nouveaux comptes reçoivent le **Rôle par défaut**
- Une règle qui ne donne qu'un rôle personnalisé : un nouveau compte reçoit le **Rôle par défaut** comme rôle de base (viewer si Aucun)
- **Rôle par défaut : Aucun** sans règle : personne ne peut se connecter via le fournisseur

La section **Provisionnement des utilisateurs** s'ouvre d'elle-même et affiche un avertissement quand le fournisseur n'a aucune règle.

### Diagnostiquer une connexion refusée
Une connexion refusée parce qu'aucune règle ne correspond, ou parce que le fournisseur n'a ni règle ni rôle par défaut, est consignée dans les **Journaux d'audit** comme connexion échouée (filtre rapide **Connexions échouées**). L'entrée donne les valeurs de groupes lues par UCM (20 au plus, chacune coupée à 64 caractères) et l'endroit où elles ont été lues : le jeton d'identité, UserInfo ou les deux pour OIDC, avec la raison pour laquelle le jeton d'identité n'a pas servi ; les attributs lus pour SAML ; la base de recherche des groupes ou \`memberOf\` pour LDAP. Quand rien n'a été lu par OIDC ou SAML, elle nomme les claims ou attributs reçus qui ressemblent à des listes de groupes, jamais leurs valeurs : mappez l'un d'eux vers \`groups\`. Ajoutez ensuite une règle de mappage de rôles pour l'une des valeurs, ou définissez un rôle par défaut. L'utilisateur refusé ne voit que le message de refus (aucune règle ne correspond, ou ni rôle par défaut ni règle de mappage de rôles), jamais les valeurs de groupes.

### Essayer une connexion
**Essai de connexion**, à côté de **Tester la connexion** sur un fournisseur OIDC ou SAML enregistré, activé ou non, ouvre l'IdP dans une nouvelle fenêtre : connectez-vous-y avec l'identité à essayer. L'IdP revient à la même URI de redirection ou URL ACS qu'une connexion, et UCM applique les mêmes contrôles et la même décision sur le compte. L'écran du fournisseur montre alors l'identité et les groupes lus, le verdict, le rôle, le compte qui serait ouvert ou créé et, en cas de refus, sa raison avec les attributs à associer à \`groups\`. Personne n'est connecté et aucun compte ne change ; la fenêtre dit seulement que l'essai est terminé. L'essai porte sur le fournisseur enregistré (les modifications non enregistrées sont signalées, pas envoyées) ; seul l'administrateur qui l'a lancé en lit le résultat, pendant 10 minutes. Le journal d'audit le consigne comme \`sso_sign_in_test\`, à part des connexions.

## LDAP

### Configuration
1. Dans UCM, allez dans **Paramètres → SSO**
2. Sur la carte **LDAP / Active Directory**, cliquez sur **Configurer**
3. Entrez le **serveur LDAP** nom d'hôte et **port** (389 pour LDAP, 636 pour LDAPS)
4. Activez **Utiliser SSL/TLS** (LDAPS, port 636) ou, sur le port 389, **Utiliser StartTLS** : la connexion passe en TLS avant tout bind, avec la même vérification de certificat. Sans l'un ni l'autre, le bind et les mots de passe des utilisateurs circulent en clair sur le réseau
5. Entrez le **DN de liaison** et le **mot de passe de liaison** (identifiants du compte de service)
6. Entrez le **DN de base** (base de recherche pour les recherches d'utilisateurs)
7. Configurez le **filtre utilisateur** (par ex. \`(uid={username})\` ou \`(sAMAccountName={username})\` pour AD)
8. Mappez les attributs LDAP : **nom d'utilisateur**, **e-mail**, **nom complet**, et l'**attribut d'ID unique** (\`entryUUID\`, \`objectGUID\`). Un compte lié par son DN passe à cet identifiant à sa prochaine connexion ; passer d'un attribut d'identifiant à un autre refuse tous les utilisateurs liés jusqu'à **Réinitialiser l'identité** sur chaque compte
9. Cliquez sur **Tester la connexion** pour vérifier, puis **Enregistrer** et **Activer**

### Groupes
- **memberOf** : lus sur l'entrée de l'utilisateur (recherche de portée base sur son DN) ; le filtre de groupe ne sert pas
- **member / uniqueMember** : cherchés sous la base de recherche des groupes seule quand elle est renseignée ; sinon sous le parent du DN de base quand l'annuaire le contient, puis sous le DN de base si cette recherche échoue, avec le filtre de groupe (\`(objectClass=*)\` s'il est vide) ; les groupes placés à côté des utilisateurs (\`ou=groups\` à côté de \`ou=people\`) sont trouvés
- **Appartenance directe seulement** par défaut : les groupes imbriqués et le groupe principal d'Active Directory (en général le RID 513, Domain Users sur un domaine anglais, Utilisateurs du domaine sur un domaine français) ne sont pas vus
- **Groupes imbriqués et groupe principal** (Active Directory seulement, désactivée par défaut) : ajoute tous les groupes au-dessus de ceux de l'utilisateur, à toute profondeur (règle de correspondance 1.2.840.113556.1.4.1941), et le groupe principal, lu par son SID où qu'il soit, si bien que les groupes parents donnent leurs rôles. Les groupes parents sont cherchés sous les mêmes bases qu'une recherche par member (avec memberOf aussi) ; le nom du groupe principal ne compte que sous cette base et à travers le filtre de groupe. Les groupes de distribution sont suivis aussi : le filtre de groupe (&(objectClass=group)(groupType:1.2.840.113556.1.4.803:=2147483648)) ne garde que les groupes de sécurité que trouve cette recherche. Avec des règles ou des groupes requis, sur un autre annuaire, ou quand la recherche échoue, expire ou dépasse 1000 groupes, la connexion est refusée, jamais réduite aux groupes directs
- **Comparaison** : les noms de groupe se comparent aux règles et aux groupes requis sans tenir compte de la casse ni des espaces de bord, une suite d'espaces internes valant un espace
- **Groupes illisibles** : avec des règles ou des groupes requis, une connexion dont les groupes ne peuvent pas être lus est refusée avec « your groups could not be read from the directory »
- **Tester le mapping** lit les groupes et décide comme la connexion, sans le mot de passe ; il n'affiche un rôle que pour un utilisateur admis

### Active Directory
Pour Microsoft Active Directory, utilisez :
- Port : **389** (ou 636 avec SSL)
- Filtre utilisateur : \`(sAMAccountName={username})\`
- Attribut nom d'utilisateur : \`sAMAccountName\`
- Attribut e-mail : \`mail\`
- Attribut nom complet : \`displayName\`

## Flux de connexion
1. L'utilisateur clique sur le bouton de son fournisseur sur la page de connexion UCM (ou entre les identifiants LDAP)
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
