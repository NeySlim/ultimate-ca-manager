export default {
  helpContent: {
    title: 'Importation et exportation',
    subtitle: 'Migration de données et sauvegarde',
    overview: 'Importez des certificats depuis des sources externes et exportez vos données PKI. L\'importation intelligente détecte automatiquement les types de fichiers. L\'intégration OPNsense permet la synchronisation directe avec votre pare-feu.',
    sections: [
      {
        title: 'Importation',
        items: [
          { label: 'Importation intelligente', text: 'Téléversez n\'importe quel fichier de certificat — UCM détecte automatiquement le format (PEM, DER, P12, P7B)' },
          { label: 'Synchronisation OPNsense', text: 'Connectez-vous au pare-feu OPNsense et importez ses certificats et CA' },
        ]
      },
      {
        title: 'Exportation',
        items: [
          { label: 'Exporter les certificats', text: 'Téléchargement en masse des certificats en bundle PEM ou PKCS#7' },
          { label: 'Exporter les CA', text: 'Téléchargement en masse des certificats et chaînes de CA' },
        ]
      },
      {
        title: 'Intégration OPNsense',
        items: [
          { label: 'Connexion', text: 'Fournir l\'URL OPNsense, la clé API et le secret API' },
          { label: 'Tester la connexion', text: 'Vérifier la connectivité avant l\'importation' },
          { label: 'Sélectionner les éléments', text: 'Choisir quels certificats et CA importer' },
        ]
      },
    ],
    tips: [
      'L\'importation intelligente gère les bundles PEM avec plusieurs certificats dans un seul fichier',
      'Testez la connexion OPNsense avant d\'exécuter une importation complète',
      'Les fichiers PKCS#12 nécessitent le mot de passe correct pour importer les clés privées',
    ],
  },
  helpGuides: {
    title: 'Importation et exportation',
    content: `
## Vue d'ensemble

Importez des certificats depuis des sources externes et exportez vos données PKI pour la sauvegarde ou la migration.

## Importation intelligente

L'assistant d'importation intelligente détecte automatiquement les types de fichiers et les traite :

### Formats pris en charge
- **PEM** — Certificats, CA et clés simples ou groupés
- **DER** — Certificat ou clé binaire
- **PKCS#12 (P12/PFX)** — Certificat + clé + chaîne (nécessite un mot de passe)
- **PKCS#7 (P7B)** — Chaîne de certificats sans clés

### Comment ça fonctionne
1. Cliquez sur **Importer** ou glissez des fichiers sur la zone de dépôt
2. UCM analyse chaque fichier et identifie son contenu
3. Examinez les éléments détectés (CA, certificats, clés)
4. Cliquez sur **Importer** pour les ajouter à UCM

> 💡 L'importation intelligente gère les bundles PEM avec plusieurs certificats dans un seul fichier. Elle distingue automatiquement les CA des certificats d'entité finale.

## Intégration OPNsense

Synchronisez les certificats et CA depuis un pare-feu OPNsense :

### Configuration
1. Dans OPNsense, créez une clé API (Système → Accès → Utilisateurs → Clés API)
2. Dans UCM, entrez l'URL OPNsense, la clé API et le secret API
3. Cliquez sur **Tester la connexion** pour vérifier

### Importation
1. Cliquez sur **Connecter** pour récupérer les certificats et CA disponibles
2. Sélectionnez les éléments que vous souhaitez importer
3. Cliquez sur **Importer la sélection**

UCM importe les certificats avec leurs clés privées (si disponibles) et préserve la hiérarchie des CA.

## Exporter les certificats

Exportation en masse de tous les certificats :
- **PEM** — Fichiers PEM individuels
- **Bundle P7B** — Tous les certificats dans un seul fichier PKCS#7
- **ZIP** — Tous les certificats en fichiers PEM individuels dans une archive ZIP

## Exporter les CA

Exportation en masse de toutes les autorités de certification :
- **PEM** — Chaîne de certificats au format PEM
- **Chaîne complète** — Racine → Intermédiaire → Sous-CA

## Migration entre instances UCM

Pour migrer d'une instance UCM à une autre :
1. Créez une **sauvegarde** sur la source (Paramètres → Sauvegarde)
2. Installez UCM sur la destination
3. **Restaurez** la sauvegarde sur la destination

Cela préserve toutes les données : certificats, CA, clés, utilisateurs, paramètres et journaux d'audit.
`
  }
}
