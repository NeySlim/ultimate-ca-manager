export default {
  helpContent: {
    title: 'Authentification unique',
    subtitle: 'Authentification fédérée',
    overview: 'Configurez SSO pour permettre aux utilisateurs de s\'authentifier avec le fournisseur d\'identité de leur organisation. UCM prend en charge SAML 2.0, OAuth2/OIDC et LDAP.',
    sections: [
      {
        title: 'Protocoles',
        items: [
          { label: 'SAML 2.0', text: 'Norme d\'entreprise pour SSO basé sur navigateur avec échange de métadonnées XML' },
          { label: 'OAuth2 / OIDC', text: 'Protocole d\'authentification moderne avec flux basé sur les jetons' },
          { label: 'LDAP', text: 'Authentification par annuaire (Active Directory, OpenLDAP)' },
        ]
      },
      {
        title: 'Configuration SAML',
        items: [
          { label: 'URL de métadonnées SP', text: 'Fournissez cette URL à votre IDP pour la configuration automatique' },
          { label: 'Métadonnées IDP', text: 'URL ou XML de votre fournisseur d\'identité' },
          { label: 'Mappage d\'attributs', text: 'Mapper les attributs IDP aux champs utilisateur UCM (nom d\'utilisateur, e-mail, groupes)' },
        ]
      },
      {
        title: 'Configuration OAuth2',
        items: [
          { label: 'URL de redirection', text: 'L\'URL de callback que votre fournisseur OAuth2 doit autoriser' },
          { label: 'Client ID / Secret', text: 'Identifiants du fournisseur OAuth2' },
          { label: 'Scopes', text: 'Scopes OpenID Connect (openid, profile, email)' },
          { label: 'Création automatique d\'utilisateurs', text: 'Créer automatiquement un compte UCM à la première connexion SSO' },
        ]
      },
      {
        title: 'Configuration LDAP',
        items: [
          { label: 'Serveur', text: 'Nom d\'hôte et port (389 LDAP / 636 LDAPS)' },
          { label: 'DN de liaison', text: 'Identifiants du compte de service pour les recherches de répertoire' },
          { label: 'DN de base', text: 'Base de recherche pour les recherches d\'utilisateurs' },
          { label: 'Filtre utilisateur', text: 'Filtre LDAP pour la correspondance des utilisateurs (par ex. sAMAccountName={username})' },
        ]
      },
    ],
    tips: [
      'Conservez toujours un compte admin local comme repli en cas de panne SSO',
      'Testez SSO avec un compte non-admin avant d\'en faire la méthode d\'authentification principale',
      'Utilisez le bouton Tester la connexion pour vérifier la configuration avant d\'activer un fournisseur',
    ],
    warnings: [
      'Le certificat HTTPS d\'UCM doit être approuvé par l\'IDP pour que les métadonnées SAML fonctionnent',
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
- **Entity ID** — Identifiant du fournisseur de services UCM
- **URL ACS** — Point de terminaison du service de consommation d'assertions (HTTP-POST)
- **URL SLO** — Point de terminaison du service de déconnexion unique
- **Certificat de signature** — Certificat HTTPS d'UCM pour la vérification de signature
- **Format NameID** — Format d'identifiant de nom demandé

Copiez cette URL dans la configuration « Ajouter un fournisseur de services » ou « Application SAML » de votre IDP.

> ⚠️ **Important :** Le certificat HTTPS d'UCM doit être **approuvé par l'IDP**. Si l'IDP ne peut pas valider le certificat (par ex. auto-signé ou émis par une CA privée), il rejettera les métadonnées comme invalides. Importez le certificat CA d'UCM dans le magasin de confiance de l'IDP, ou utilisez un certificat signé par une CA publiquement approuvée.

### Configuration
1. Obtenez l'URL de métadonnées IDP ou le fichier XML de votre fournisseur d'identité
2. Dans UCM, allez dans **Paramètres → SSO**
3. Cliquez sur **Ajouter un fournisseur** → SAML
4. Entrez l'**URL de métadonnées IDP** — UCM remplit automatiquement l'Entity ID, les URL SSO/SLO et le certificat
5. Ou collez directement le XML de métadonnées IDP
6. Configurez le **mappage d'attributs** (nom d'utilisateur, e-mail, groupes)
7. Cliquez sur **Enregistrer** et **Activer**

### Mappage d'attributs
Mappez les attributs SAML de l'IDP aux champs utilisateur UCM :
- \`username\` → Nom d'utilisateur UCM (requis)
- \`email\` → E-mail UCM (requis)
- \`groups\` → Appartenance aux groupes UCM (optionnel)

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
Lorsqu'elle est activée, un nouveau compte utilisateur UCM est automatiquement créé à la première connexion SSO, en utilisant les attributs fournis par l'IDP. Le rôle par défaut est attribué.

## LDAP

### Configuration
1. Dans UCM, allez dans **Paramètres → SSO**
2. Cliquez sur **Ajouter un fournisseur** → LDAP
3. Entrez le **serveur LDAP** nom d'hôte et **port** (389 pour LDAP, 636 pour LDAPS)
4. Activez **Utiliser SSL** pour les connexions chiffrées
5. Entrez le **DN de liaison** et le **mot de passe de liaison** (identifiants du compte de service)
6. Entrez le **DN de base** (base de recherche pour les recherches d'utilisateurs)
7. Configurez le **filtre utilisateur** (par ex. \`(uid={username})\` ou \`(sAMAccountName={username})\` pour AD)
8. Mappez les attributs LDAP : **nom d'utilisateur**, **e-mail**, **nom complet**
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
