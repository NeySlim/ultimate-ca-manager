export default {
  helpContent: {
    title: 'Modèles de certificat',
    subtitle: 'Profils de certificat réutilisables',
    overview: 'Définissez des profils de certificat réutilisables avec des champs de sujet préconfigurés, l\'utilisation de la clé, l\'utilisation étendue de la clé, les périodes de validité et d\'autres extensions. Appliquez les modèles lors de l\'émission ou de la signature de certificats.',
    sections: [
      {
        title: 'Origine',
        definitions: [
          { term: 'Système', description: 'Fournis à l\'installation. Dupliquez-en un pour obtenir une copie modifiable : lui-même ne peut être ni modifié ni supprimé' },
          { term: 'Personnalisé', description: 'Créés ou importés ici, et les seuls qui peuvent être modifiés ou supprimés' },
        ]
      },
      {
        title: 'Fonctionnalités',
        items: [
          { label: 'Type', text: 'Web Server, Email, VPN Server ou Client, Code Signing, Client Auth, OCSP Signing, Smartcard Logon ou Custom. Définit les valeurs par défaut d\'utilisation de la clé, d\'EKU et de SAN' },
          { label: 'Valeurs par défaut du sujet', text: 'Préremplir Organisation, OU, Pays, État, Ville et Email. Sur les certificats Email (S/MIME) et Serveur + Client (Combiné), l\'Email devient aussi un SAN' },
          { label: 'Utilisation de la clé', text: 'Signature numérique, chiffrement de clé, etc.' },
          { label: 'Utilisation étendue de la clé', text: 'Tout usage connu du serveur : authentification serveur, authentification client, signature de code, protection e-mail, Smartcard Logon, horodatage, signature OCSP, IPsec, Microsoft RDP et autres' },
          { label: 'Types de SAN', text: 'Les types de noms (DNS, IP, Email, URI, UPN) qu\'une demande faite avec le modèle peut porter. Avec « Appliquer les types de SAN autorisés » activé, le formulaire d\'émission, la signature de CSR, les protocoles d\'enrôlement, les renouvellements et les approbations refusent tout autre type, et un nom seulement déduit du CN est omis. Les nouveaux modèles l\'ont activé ; les anciens et les modèles intégrés l\'ont désactivé. Aucune case cochée : tous les types sont permis' },
          { label: 'Validité', text: 'Période de validité par défaut en jours' },
          { label: 'Dupliquer', text: 'Cloner un modèle existant et le modifier' },
          { label: 'Afficher système', text: 'Masquer les modèles intégrés pour ne travailler qu\'avec les vôtres. Mémorisé par navigateur' },
          { label: 'Désactiver', text: 'Un modèle désactivé, intégré ou non, n\'est plus proposé par le formulaire Émettre un certificat ni à l\'auto-inscription Windows, et affiche un badge Inactif. Activer le remet en service. Un modèle intégré peut être désactivé, pas modifié : dupliquez-le pour le changer' },
          { label: 'Importer/Exporter', text: 'Partager des modèles sous forme de fichiers JSON entre instances UCM : la page exporte un modèle à la fois, et un fichier d\'import peut en contenir un ou plusieurs' },
          { label: 'Type de clé', text: 'RSA-2048, RSA-3072, RSA-4096, EC-P256, EC-P384 ou EC-P521, avec un condensat SHA-256, SHA-384 ou SHA-512, ou ML-DSA-44, ML-DSA-65 ou ML-DSA-87. Le condensat est le hachage de signature de la CA émettrice, pas celui de la clé finale : il s\'applique toujours à une clé finale ML-DSA sous une CA RSA ou EC, et une CA ML-DSA l\'ignore' },
          { label: "Préférence de condensat (v2.251)", text: "Tout chemin qui émet depuis le template (formulaire d'émission, Sign CSR, ACME, SCEP, WSTEP, signataire TSA ; EST n'utilise aucun modèle) signe avec son condensat, relevé à celui qui correspond à la clé de l'AC : SHA-384 pour P-384, SHA-512 pour P-521. Quand une politique l'interdit, le condensat plus fort le plus proche autorisé signe à la place, et le résultat indique « Signature digest X replaced by Y by policy »" },
          { label: 'qcStatements', text: 'Déclarations ETSI EN 319 412-5 facultatives ajoutées à chaque certificat émis depuis le modèle : QcCompliance, QcType (signature, cachet ou site web), QcSSCD, QcPDS (URL HTTPS et langue à deux lettres), QcRetentionPeriod, QcLimitValue, QcCClegislation (pour un certificat qualifié selon un cadre juridique hors UE) et l\'identifiant de sémantique. Non appliquées à l\'émission EST, WSTEP ou mTLS, et une extension qcStatements présente dans une CSR est ignorée. QcIdentMethod, QcQSCDlegislation et les déclarations PSD2 ne sont pas prises en charge' },
          { label: 'OID de politique', text: 'OID de politique de certificat supplémentaires (par exemple les politiques ETSI QCP-n, QCP-l, QCP-n-qscd, QCP-l-qscd et QCP-w), ajoutés après la politique propre à la CA' },
          { label: 'Extensions personnalisées', text: 'Extensions qu\'UCM ne modélise pas, chacune un OID, un indicateur critique et la valeur DER en hexadécimal, ajoutées telles quelles à chaque certificat émis depuis le modèle (formulaire d\'émission, signature de CSR, ACME, SCEP, WSTEP, approbations ; les renouvellements les gardent). Le formulaire d\'émission peut en ajouter ou remplacer celle de même OID. Les extensions qu\'UCM pose lui-même sont refusées : passez par leurs propres réglages. Un client qui ne reconnaît pas une extension critique rejette le certificat' },
          { label: 'Brainpool', text: 'EC-BP256, EC-BP384 et EC-BP512 (RFC 5639, regroupés sous Brainpool dans les listes de types de clé, masqués en mode FIPS). OpenSSL et Windows lisent leurs chaînes et signatures, mais Chrome, Firefox, Go, rustls, GnuTLS et Java sans Bouncy Castle les refusent pour TLS, et Windows Schannel ne les active pas par défaut. Sur un HSM, seuls les fournisseurs PKCS#11 les conservent' },
        ]
      },
      {
        title: 'Autoenrollment Windows',
        items: [
          { label: 'Autoriser l\'autoenrollment', text: 'Annonce le modèle avec autoEnroll=true dans la Certificate Enrollment Policy afin que les clients GPO/Kerberos le demandent automatiquement à l\'ouverture de session. Désactivé par défaut, l\'enrôlement manuel reste possible sans lui' },
          { label: 'Construire le sujet depuis Active Directory', text: 'Dériver le sujet et les SAN depuis l\'objet AD du demandeur (via le connecteur AD) au lieu d\'exiger que le client les fournisse, pour l\'autoenrollment GPO sans intervention' },
          { label: 'Restreindre l\'enrôlement à un groupe AD', text: 'Seuls les membres du groupe AD configuré (appartenance imbriquée incluse) peuvent enrôler via le point de terminaison Kerberos. Vide = tout principal authentifié. Non appliqué sur le point de terminaison Username/Password' },
          { label: 'Champs de sujet épinglés', text: 'Force les valeurs C/ST/L/O/OU sur chaque certificat émis via WSTEP, en écrasant le CSR ou la dérivation AD pour ces champs. Le CN et les SAN ne sont jamais affectés, laissez un champ vide pour le garder dynamique' },
          { label: 'Motif du nom commun', text: 'Construit le CN à partir de texte fixe et de variables de l\'annuaire, par exemple {hostname}-WiFi ou {displayName}, pour un modèle dont UCM construit le sujet. Seul le CN change : les SAN et l\'extension SID restent ceux de l\'annuaire. Une variable vide ou un CN de plus de 64 caractères refuse la demande' },
        ]
      },
    ],
    tips: [
      'Créez des modèles séparés pour les serveurs TLS, les clients et la signature de code',
      'Utilisez l\'action Dupliquer pour créer rapidement des variantes d\'un modèle, y compris d\'un modèle système',
      'Les modèles avec indicateurs d\'autoenrollment affichent des badges AD / Auto / ACL / Épinglé dans la liste',
    ],
  },
  helpGuides: {
    title: 'Modèles de certificat',
    content: `
## Vue d'ensemble

Les modèles définissent des profils de certificat réutilisables. Au lieu de configurer manuellement l'utilisation de la clé, l'utilisation étendue de la clé, la validité et les champs du sujet à chaque fois, appliquez un modèle pour tout préremplir.

## Système et personnalisé

Chaque modèle est l'un ou l'autre, comme l'indique la colonne **Origine**.

### Système
Les modèles fournis à l'installation : Web Server (TLS/SSL), Email Certificate (S/MIME), VPN Server, VPN Client, Code Signing, OCSP Signing, Client Authentication et Smartcard Logon. Modifier et Supprimer leur sont refusés, dans l'interface comme par l'API. **Dupliquer** vous donne une copie modifiable comme point de départ.

### Personnalisé
Tout ce qui est créé ou importé ici. Ces modèles peuvent être modifiés et supprimés librement.

Désactivez **Afficher système** dans la barre d'outils pour masquer les modèles intégrés et ne travailler qu'avec les vôtres. Le choix est mémorisé, sauf si vous n'avez encore aucun modèle personnalisé, auquel cas les modèles intégrés restent visibles.

Les autorités de certification ne se créent pas à partir de modèles : créez-les sur la page **Autorités de certification**.

## Créer un modèle

1. Cliquez sur **Créer un modèle**
2. Entrez un **nom** et une description optionnelle
3. Sélectionnez le **type** de modèle : Web Server, Email, VPN Server, VPN Client, Code Signing, Client Auth, OCSP Signing, Smartcard Logon ou Custom. Il définit les valeurs par défaut d'utilisation de la clé, d'utilisation étendue de la clé et de SAN, que vous pouvez ensuite modifier
4. Configurez les **valeurs par défaut du sujet** (O, OU, C, ST, L, CN, Email). Sur les certificats Email (S/MIME) et Serveur + Client (Combiné), l'Email devient aussi un SAN
5. Sélectionnez les indicateurs d'**utilisation de la clé**
6. Sélectionnez les valeurs d'**utilisation étendue de la clé** parmi les usages connus du serveur (Smartcard Logon, Time Stamping, Microsoft RDP et autres)
7. Définissez le **type de clé** (RSA-2048, RSA-3072, RSA-4096, EC-P256, EC-P384, EC-P521, Brainpool EC-BP256/384/512 ou ML-DSA-44/65/87), le condensat et la **période de validité par défaut** en jours. Le condensat est le hachage de signature de la CA émettrice : il s'applique donc toujours à une clé ML-DSA sous une CA RSA ou EC ; une CA ML-DSA l'ignore
8. Cliquez sur **Créer**

## Utiliser les modèles

Lors de l'émission d'un certificat ou de la signature d'une CSR, sélectionnez un modèle dans la liste déroulante. Le modèle prérempli :
- Les champs du sujet (vous pouvez les modifier)
- L'utilisation de la clé et l'utilisation étendue de la clé
- La période de validité

## Indicateurs d'autoenrollment Windows

Les modèles portent trois indicateurs opt-in utilisés par les protocoles d'autoenrollment Windows (XCEP/WSTEP, configurés dans **Paramètres → Autoenrollment Windows**) :

- **Autoriser l'autoenrollment** : Annonce le modèle avec \`autoEnroll=true\` dans la Certificate Enrollment Policy, afin que les clients authentifiés GPO/Kerberos le demandent automatiquement à l'ouverture de session, sans action de l'utilisateur. Désactivé par défaut : comme sur un vrai ADCS, un modèle peut toujours être enrôlé manuellement (MMC « Demander un nouveau certificat », \`certreq\`) sans cet indicateur, puisque Enroll et Autoenroll sont des permissions distinctes.
- **Construire le sujet depuis Active Directory** : Pour l'autoenrollment GPO sans intervention : dérive le sujet et les SAN du certificat depuis l'objet AD du demandeur (via le connecteur AD) au lieu d'exiger que le client les fournisse.
- **Restreindre l'enrôlement à un groupe AD** : Seuls les principaux appartenant au groupe Active Directory configuré (appartenance imbriquée incluse) peuvent enrôler avec ce modèle via le point de terminaison authentifié Kerberos. Saisissez un nom de groupe ou un DN complet ; laissez vide pour autoriser tout principal authentifié, comme le défaut d'un vrai ADCS. Non appliqué sur le point de terminaison Username/Password, qui n'a pas d'identité par requête à vérifier.

Les modèles portant ces indicateurs affichent des badges **AD**, **Auto** et **ACL** dans la liste des modèles.

## Champs de sujet épinglés

Un modèle peut **épingler** les champs organisationnels du sujet : **C, ST, L, O, OU** : pour les certificats émis via WSTEP. Une valeur épinglée est imposée sur chaque certificat émis, quelle que soit la valeur fournie par le CSR du client ou par la dérivation Active Directory pour ce champ.

- **Le Common Name et les Subject Alternative Names ne sont jamais affectés** : ils restent dynamiques par demandeur
- Laissez un champ vide pour le garder dynamique
- Les modèles avec champs épinglés affichent un badge **Épinglé**, et les valeurs épinglées apparaissent dans le panneau de détails du modèle

Utilisez cette fonction pour garantir une identité organisationnelle uniforme (p. ex. un \`O\` et un \`C\` fixes) sur un parc autoenrôlé, indépendamment de ce que chaque client Windows soumet.

## Motif du nom commun

Pour l'enrôlement Windows, un modèle dont UCM construit le sujet (un modèle machine, ou un modèle utilisateur avec **Construire le sujet depuis Active Directory**) peut tirer son CN d'un motif : du texte fixe et des variables entre accolades, lues dans l'objet de l'annuaire du demandeur, jamais dans la demande.

- **Modèles machine** : \`{hostname}\` (le nom du compte sans \`$\`), \`{fqdn}\` (son dNSHostName)
- **Modèles utilisateur** : \`{username}\` (sAMAccountName), \`{upn}\`, \`{mail}\`, \`{displayName}\`, \`{givenName}\`, \`{surname}\`
- **Les deux** : \`{domain}\` (les composants DC du DN de l'objet), \`{realm}\` (le royaume du profil)
- \`{{\` et \`}}\` donnent une accolade littérale. Une variable inconnue, une variable de l'autre type, ou un motif sur un modèle dont le demandeur fournit le sujet est refusé à l'enregistrement du modèle
- **Conserver le chemin d'annuaire** décoché : le sujet est le CN seul, plus les champs épinglés. Coché : le DN de l'objet après son propre nom suit le CN (pour un utilisateur, l'attribut e-mail reste comme sans motif)
- **Seul le CN change** : les SAN (le nom DNS de la machine, l'UPN et l'e-mail de l'utilisateur) et l'extension SID restent comme sans motif, et un motif n'ajoute jamais de SAN
- **Refusé, jamais tronqué** : une variable que l'annuaire laisse vide, un résultat de plus de 64 caractères ou contenant un caractère de contrôle refuse la demande ; la raison nomme le modèle et la variable et figure dans le journal d'audit
- \`{displayName}\`, \`{givenName}\`, \`{surname}\` et \`{mail}\` ne sont pas uniques : deux comptes peuvent recevoir le même CN
- **Le renouvellement** avec le certificat prend le motif en vigueur, pour le compte que nomme le SID du certificat ; il est refusé quand aucun connecteur du profil ne trouve ce compte
- Le point de terminaison Username/Password n'a pas d'identité d'annuaire : le motif ne s'y applique pas et le client fournit le sujet

## Extensions personnalisées

Un modèle peut ajouter des extensions pour lesquelles UCM n'a aucun réglage. Chacune est un **OID**, un indicateur **Critique** et la **valeur** : l'encodage DER de la valeur de l'extension, en hexadécimal. UCM copie les octets tels quels et ne les analyse jamais : vérifiez d'abord l'encodage avec vos propres outils.

- Tout certificat émis depuis le modèle les porte : formulaire d'émission, Sign CSR, profils ACME liés au modèle, profils SCEP, WSTEP et approbations. Les renouvellements les conservent
- Le formulaire d'émission peut en ajouter d'autres pour un seul certificat ; une entrée ayant l'OID de l'une de celles du modèle la remplace
- Les extensions qu'UCM pose lui-même (usage de la clé, EKU, noms, identifiants de clé, pointeurs CRL et OCSP, politiques, contraintes de noms, qcStatements...) sont refusées : utilisez leurs propres réglages
- Un client qui ne reconnaît pas une extension **critique** doit rejeter le certificat (RFC 5280, section 4.2). Laissez-la non critique sauf si toutes les parties utilisatrices la comprennent

L'inspecteur liste ces extensions pour les certificats et les CA sous **Autres extensions**, dans l'onglet Extensions, avec leur OID, leur nom s'il est connu, leur criticité et leur valeur.

## Dupliquer des modèles

Cliquez sur **Dupliquer** pour créer une copie d'un modèle existant. Modifiez la copie sans affecter l'original.

## Importer et exporter

### Exporter
Exportez les modèles au format JSON pour les partager entre instances UCM.

### Importer
Importez depuis :
- **Fichier JSON** : Téléversez un fichier JSON de modèle, un modèle ou plusieurs dans un fichier
- **Coller du JSON** : Collez le JSON directement dans la zone de texte

Un modèle dont le nom existe déjà est ignoré, et l'import indique lesquels.

## Exemples de modèles courants

### Serveur TLS
- Utilisation de la clé : Signature numérique, chiffrement de clé
- Utilisation étendue de la clé : Authentification serveur
- Validité : 365 jours

### Authentification client
- Utilisation de la clé : Signature numérique
- Utilisation étendue de la clé : Authentification client
- Validité : 365 jours

### Signature de code
- Utilisation de la clé : Signature numérique
- Utilisation étendue de la clé : Signature de code
- Validité : 365 jours
`
  }
}
