export default {
  helpContent: {
    title: 'CRL & OCSP',
    subtitle: 'Services de révocation de certificats',
    overview: 'Gérez les listes de révocation de certificats (CRL) et les services OCSP (Online Certificate Status Protocol). Ces services permettent aux clients de vérifier si un certificat a été révoqué.',
    sections: [
      {
        title: 'Gestion des CRL',
        items: [
          { label: 'Auto-régénération', text: 'Activer la régénération automatique des CRL par CA' },
          { label: 'Régénération manuelle', text: 'Forcer la régénération immédiate de la CRL' },
          { label: 'Télécharger la CRL', text: 'Télécharger le fichier CRL au format DER ou PEM' },
          { label: 'URL CDP', text: 'URL du point de distribution CRL à intégrer dans les certificats' },
        ]
      },
      {
        title: 'Service OCSP',
        items: [
          { label: 'Statut', text: 'Indique si le répondeur OCSP est actif pour chaque CA' },
          { label: 'URL AIA', text: 'URL d\'accès aux informations de l\'autorité — Points de terminaison du répondeur OCSP et de téléchargement du certificat de l\'émetteur CA intégrés dans les certificats émis' },
          { label: 'Cache', text: 'Cache de réponses avec nettoyage automatique quotidien des entrées expirées' },
          { label: 'Total des requêtes', text: 'Nombre de requêtes OCSP traitées' },
        ]
      },
    ],
    tips: [
      'Activez l\'auto-régénération pour maintenir les CRL à jour après les révocations de certificats',
      'Copiez les URL CDP, OCSP et AIA CA Issuers pour les intégrer dans vos profils de certificat',
      'OCSP fournit une vérification de révocation en temps réel et est préféré aux CRL',
    ],
  },
  helpGuides: {
    title: 'CRL & OCSP',
    content: `
## Vue d'ensemble

Les listes de révocation de certificats (CRL) et le protocole OCSP (Online Certificate Status Protocol) permettent aux clients de vérifier si un certificat a été révoqué. UCM prend en charge les deux mécanismes.

## Gestion des CRL

### Qu'est-ce qu'une CRL ?
Une CRL est une liste signée de numéros de série de certificats révoqués, publiée par une CA. Les clients téléchargent la CRL et vérifient si le numéro de série d'un certificat y figure.

### CRL par CA
Chaque CA a sa propre CRL. La liste des CRL affiche toutes vos CA avec :
- **Nombre de révocations** — Nombre de certificats dans la CRL
- **Dernière régénération** — Quand la CRL a été reconstruite pour la dernière fois
- **Auto-régénération** — Si les mises à jour automatiques de la CRL sont activées

### Régénérer une CRL
Cliquez sur **Régénérer** pour reconstruire immédiatement la CRL d'une CA. C'est utile après avoir révoqué des certificats.

### Auto-régénération
Activez l'auto-régénération pour reconstruire automatiquement la CRL chaque fois qu'un certificat est révoqué. Basculez cette option par CA.

### Point de distribution CRL (CDP)
L'URL CDP est intégrée dans les certificats pour que les clients sachent où télécharger la CRL. Copiez l'URL depuis les détails de la CRL.

\`\`\`
http://votre-serveur:8080/cdp/{ca_refid}.crl
\`\`\`

> 💡 **Activé automatiquement** : Lorsque vous créez une nouvelle CA, le CDP est automatiquement activé si une URL de base de protocole ou un serveur de protocole HTTP est configuré. L'URL CDP est générée automatiquement — aucune étape manuelle nécessaire.

> ⚠️ **Important** : Les URL sont générées automatiquement en utilisant le port du protocole HTTP et le FQDN du serveur. Si vous accédez à UCM via \`localhost\`, l'URL ne peut pas être générée. Configurez d'abord votre **FQDN** ou l'**URL de base du protocole** dans Paramètres → Général.

### Télécharger les CRL
Téléchargez les CRL au format DER ou PEM pour la distribution aux clients ou l'intégration avec d'autres systèmes.

## Répondeur OCSP

### Qu'est-ce qu'OCSP ?
OCSP fournit une vérification de statut de certificat en temps réel. Au lieu de télécharger une CRL entière, les clients envoient une requête pour un certificat spécifique et obtiennent une réponse immédiate.

### Statut OCSP
La section OCSP affiche :
- **Statut du répondeur** — Actif ou inactif par CA
- **Total des requêtes** — Nombre de requêtes OCSP traitées
- **Cache** — Cache de réponses avec nettoyage automatique quotidien des entrées expirées

### Cache OCSP

UCM met en cache les réponses OCSP pour les performances. Le cache est :
- **Nettoyé automatiquement** — Les réponses expirées sont purgées quotidiennement par le planificateur
- **Invalidé à la révocation** — Lorsqu'un certificat est révoqué, sa réponse OCSP en cache est immédiatement supprimée
- **Invalidé à la levée de suspension** — Lorsqu'une suspension de certificat est levée, le cache OCSP est mis à jour

### URL AIA
L'extension AIA (Authority Information Access) est intégrée dans les certificats pour indiquer aux clients où trouver :

**Répondeur OCSP** — vérification de révocation en temps réel :
\`\`\`
http://votre-serveur:8080/ocsp
\`\`\`

**CA Issuers** (RFC 5280 §4.2.2.1) — téléchargement du certificat de la CA émettrice pour la construction de chaîne :
\`\`\`
http://votre-serveur:8080/ca/{ca_refid}.cer   (format DER)
http://votre-serveur:8080/ca/{ca_refid}.pem   (format PEM)
\`\`\`

Activez CA Issuers par CA dans la section **AIA CA Issuers** du panneau de détail. L'URL est générée automatiquement en utilisant le serveur de protocole HTTP et le FQDN configuré.

> ⚠️ **Prérequis** : Les URL de protocole (CDP, OCSP, AIA) nécessitent un **FQDN** valide ou une **URL de base du protocole** configurée dans Paramètres → Général. Si vous accédez à UCM via \`localhost\`, l'activation de ces fonctionnalités échouera — configurez d'abord le FQDN.

### OCSP vs CRL

| Caractéristique | CRL | OCSP |
|-----------------|-----|------|
| Fréquence de mise à jour | Périodique | Temps réel |
| Bande passante | Liste complète à chaque fois | Requête unique |
| Confidentialité | Pas de suivi | Le serveur voit les requêtes |
| Support hors ligne | Oui (en cache) | Nécessite une connexion |

> 💡 Bonne pratique : activez à la fois CRL et OCSP pour une compatibilité maximale.
`
  }
}
