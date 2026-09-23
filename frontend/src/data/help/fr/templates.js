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
          { label: 'Valeurs par défaut du sujet', text: 'Préremplir Organisation, OU, Pays, État, Ville' },
          { label: 'Utilisation de la clé', text: 'Signature numérique, chiffrement de clé, etc.' },
          { label: 'Utilisation étendue de la clé', text: 'Authentification serveur, authentification client, signature de code, protection e-mail' },
          { label: 'Validité', text: 'Période de validité par défaut en jours' },
          { label: 'Dupliquer', text: 'Cloner un modèle existant et le modifier' },
          { label: 'Afficher système', text: 'Masquer les modèles intégrés pour ne travailler qu\'avec les vôtres. Mémorisé par navigateur' },
          { label: 'Importer/Exporter', text: 'Partager des modèles sous forme de fichiers JSON entre instances UCM' },
        ]
      },
      {
        title: 'Autoenrollment Windows',
        items: [
          { label: 'Autoriser l\'autoenrollment', text: 'Annonce le modèle avec autoEnroll=true dans la Certificate Enrollment Policy afin que les clients GPO/Kerberos le demandent automatiquement à l\'ouverture de session. Désactivé par défaut, l\'enrôlement manuel reste possible sans lui' },
          { label: 'Construire le sujet depuis Active Directory', text: 'Dériver le sujet et les SAN depuis l\'objet AD du demandeur (via le connecteur AD) au lieu d\'exiger que le client les fournisse, pour l\'autoenrollment GPO sans intervention' },
          { label: 'Restreindre l\'enrôlement à un groupe AD', text: 'Seuls les membres du groupe AD configuré (appartenance imbriquée incluse) peuvent enrôler via le point de terminaison Kerberos. Vide = tout principal authentifié. Non appliqué sur le point de terminaison Username/Password' },
          { label: 'Champs de sujet épinglés', text: 'Force les valeurs C/ST/L/O/OU sur chaque certificat émis via WSTEP, en écrasant le CSR ou la dérivation AD pour ces champs. Le CN et les SAN ne sont jamais affectés, laissez un champ vide pour le garder dynamique' },
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
4. Configurez les **valeurs par défaut du sujet** (O, OU, C, ST, L)
5. Sélectionnez les indicateurs d'**utilisation de la clé**
6. Sélectionnez les valeurs d'**utilisation étendue de la clé**
7. Définissez la **période de validité par défaut** en jours
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

## Dupliquer des modèles

Cliquez sur **Dupliquer** pour créer une copie d'un modèle existant. Modifiez la copie sans affecter l'original.

## Importer et exporter

### Exporter
Exportez les modèles au format JSON pour les partager entre instances UCM.

### Importer
Importez depuis :
- **Fichier JSON** : Téléversez un fichier JSON de modèle
- **Coller du JSON** : Collez le JSON directement dans la zone de texte

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
