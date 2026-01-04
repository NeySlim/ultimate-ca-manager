# 📖 Manuel Utilisateur UCM

Guide complet d'utilisation de Ultimate CA Manager.

---

## 📑 Table des Matières

1. [Connexion et Interface](#connexion-et-interface)
2. [Tableau de Bord](#tableau-de-bord)
3. [Gestion des CA](#gestion-des-ca)
4. [Gestion des Certificats](#gestion-des-certificats)
5. [Serveur SCEP](#serveur-scep)
6. [Gestion des Utilisateurs](#gestion-des-utilisateurs)
7. [Paramètres Système](#paramètres-système)
8. [Opérations Courantes](#opérations-courantes)

---

## 🔐 Connexion et Interface

### Première Connexion

1. **Accéder à UCM**
   ```
   https://<votre-serveur>:8443
   ```

2. **Identifiants par défaut**
   - **Utilisateur**: `admin`
   - **Mot de passe**: `admin`
   
   ⚠️ **Important**: Changez le mot de passe immédiatement après la première connexion !

3. **Accepter le certificat auto-signé**
   - Votre navigateur affichera un avertissement
   - Cliquez sur "Paramètres avancés" → "Continuer vers le site"
   - C'est normal pour la première connexion

### Interface Utilisateur

L'interface UCM est composée de :

- **Barre de navigation** (haut) - Accès rapide aux sections
- **Menu latéral** (gauche) - Navigation principale
- **Zone de contenu** (centre) - Zone de travail principale
- **Barre d'état** (bas) - Informations système

### Thèmes

UCM supporte deux thèmes :
- **Clair** ☀️ - Par défaut
- **Sombre** 🌙 - Dans Paramètres → Profil → Thème

---

## 📊 Tableau de Bord

Le tableau de bord affiche une vue d'ensemble de votre PKI.

### Statistiques Affichées

1. **Autorités de Certification**
   - Nombre total de CAs
   - CAs actives vs révoquées
   - Répartition Root CA / Intermediate CA

2. **Certificats**
   - Total des certificats émis
   - Certificats actifs
   - Certificats révoqués
   - Certificats expirés

3. **Expirations à Venir**
   - Certificats expirant dans 30 jours
   - Certificats expirant dans 90 jours
   - Alertes d'expiration

4. **Activité SCEP**
   - Endpoints SCEP actifs
   - Enrollments récents
   - Renouvellements automatiques

### Graphiques

- **Timeline d'émission** - Certificats émis par période
- **Répartition par type** - Server, Client, Code Signing, etc.
- **Statut des certificats** - Valides, Expirés, Révoqués

---

## 🏛️ Gestion des CA

### Créer une Root CA

1. **Navigation**: Menu → Certificate Authorities → Create New CA

2. **Paramètres de base**
   ```
   CA Type: Root CA
   Key Type: RSA 4096 bits (recommandé pour Root CA)
   Hash Algorithm: SHA-384 ou SHA-512
   Validity: 20 ans (7300 jours)
   ```

3. **Distinguished Name (DN)**
   ```
   Common Name (CN): My Company Root CA
   Organization (O): My Company Inc.
   Organizational Unit (OU): IT Security
   Country (C): FR
   State (ST): Ile-de-France
   Locality (L): Paris
   ```

4. **Options avancées**
   - ✅ **CA Certificate** - Obligatoire
   - ✅ **Certificate Sign** - Obligatoire
   - ✅ **CRL Sign** - Obligatoire
   - ⬜ **Digital Signature** - Optionnel

5. **Cliquer sur "Create CA"**

### Créer une Intermediate CA

1. **Prérequis**: Une Root CA doit exister

2. **Configuration**
   ```
   CA Type: Intermediate CA
   Parent CA: Sélectionner votre Root CA
   Key Type: RSA 4096 bits
   Hash Algorithm: SHA-384
   Validity: 10 ans (3650 jours)
   ```

3. **Distinguished Name**
   ```
   CN: My Company Issuing CA 1
   O: My Company Inc.
   OU: PKI Services
   C: FR
   ```

4. **Path Length Constraint**
   - `0` = Cette Intermediate CA ne peut pas créer d'autres Intermediate CAs
   - `1` = Peut créer 1 niveau d'Intermediate CAs supplémentaires
   - Vide = Pas de limite

### Importer une CA Existante

1. **Menu → Import CA**

2. **Formats supportés**
   - **PEM** - Fichiers .pem, .crt, .key
   - **PKCS#12** - Fichiers .pfx, .p12

3. **Import PEM**
   ```
   Certificate File: ca-cert.pem
   Private Key File: ca-key.pem
   Private Key Password: (si chiffré)
   ```

4. **Import PKCS#12**
   ```
   PKCS#12 File: ca.pfx
   Password: ****
   ```

### Exporter une CA

1. **Liste des CAs → Actions → Export**

2. **Choisir le format**
   - **Certificate only (PEM)** - Pour distribution publique
   - **Full chain (PEM)** - Certificat + chaîne complète
   - **PKCS#12** - Certificat + clé privée (⚠️ sécurisé)

3. **Pour PKCS#12**
   ```
   Export Password: ********
   Confirm Password: ********
   ```

### Révoquer une CA

⚠️ **Attention**: Opération irréversible !

1. **Liste des CAs → Sélectionner CA → Revoke**

2. **Raison de révocation**
   - Key Compromise (clé compromise)
   - Superseded (remplacée)
   - Cessation of Operation (arrêt)
   - Unspecified (non spécifié)

3. **Conséquences**
   - Tous les certificats émis par cette CA deviennent invalides
   - La CA apparaît dans la CRL
   - Opération non réversible

---

## 📜 Gestion des Certificats

### Émettre un Nouveau Certificat

1. **Menu → Certificates → Issue New Certificate**

2. **Sélectionner la CA émettrice**
   ```
   Issuing CA: My Company Issuing CA 1
   ```

3. **Type de certificat**
   - **Server Certificate** - Serveurs web, VPN, etc.
   - **Client Certificate** - Authentification utilisateur
   - **Code Signing** - Signature de code
   - **Email Certificate** - S/MIME

4. **Informations du sujet**
   
   Pour un certificat serveur :
   ```
   Common Name (CN): www.example.com
   Organization (O): Example Inc.
   OU: Web Services
   Country (C): FR
   ```
   
   Pour un certificat client :
   ```
   CN: John Doe
   Email: john.doe@example.com
   O: Example Inc.
   ```

5. **Configuration de la clé**
   ```
   Key Type: RSA 2048 bits (standard)
            ou ECDSA P-256 (moderne, plus rapide)
   Hash Algorithm: SHA-256 (standard)
   Validity: 395 jours (13 mois, max pour navigateurs)
   ```

6. **Subject Alternative Names (SANs)**
   
   Pour certificats serveur (important !) :
   ```
   DNS Names:
   - www.example.com
   - example.com
   - mail.example.com
   
   IP Addresses (si nécessaire):
   - 192.168.1.100
   ```

7. **Key Usage**
   
   Certificat serveur :
   - ✅ Digital Signature
   - ✅ Key Encipherment
   - Extended: Server Authentication
   
   Certificat client :
   - ✅ Digital Signature
   - ✅ Key Agreement
   - Extended: Client Authentication
   
   Code Signing :
   - ✅ Digital Signature
   - Extended: Code Signing

8. **Cliquer sur "Issue Certificate"**

### Importer et Signer un CSR

1. **Menu → Certificates → Sign CSR**

2. **Uploader le fichier CSR**
   ```
   Drag & Drop ou Browse: request.csr
   ```

3. **UCM affiche automatiquement**
   - Subject DN du CSR
   - Clé publique et type
   - Extensions demandées

4. **Sélectionner la CA** et **configurer**
   ```
   Issuing CA: My Company Issuing CA 1
   Validity: 365 jours
   ```

5. **Vérifier/Ajouter SANs si nécessaire**

6. **Signer le CSR**

### Renouveler un Certificat

1. **Liste des Certificats → Sélectionner → Renew**

2. **Options de renouvellement**
   - **Réutiliser la même clé** - Conserve la clé existante
   - **Générer nouvelle clé** - Recommandé pour sécurité

3. **Ajuster la validité si besoin**
   ```
   Validity: 395 jours
   ```

4. **Le nouveau certificat**
   - Garde le même Subject DN
   - Garde les même SANs
   - Nouveau numéro de série
   - Nouvelle période de validité

### Révoquer un Certificat

1. **Liste → Sélectionner certificat → Revoke**

2. **Raison de révocation**
   ```
   - Key Compromise (clé compromise) ⚠️
   - CA Compromise (CA compromise) ⚠️⚠️
   - Affiliation Changed (changement affiliation)
   - Superseded (remplacé)
   - Cessation of Operation (arrêt utilisation)
   - Certificate Hold (suspension temporaire)
   - Remove from CRL (retirer de CRL)
   - Privilege Withdrawn (privilèges retirés)
   ```

3. **Effet immédiat**
   - Certificat ajouté à la CRL
   - OCSP retourne "revoked"
   - Invalide pour toute utilisation

### Exporter un Certificat

1. **Liste → Sélectionner → Export**

2. **Formats disponibles**

   **PEM (Base64 ASCII)**
   ```
   - Certificate only (.pem)
   - Certificate + Chain (.pem)
   - Full chain (.pem)
   ```
   
   **DER (Binaire)**
   ```
   - Certificate only (.der, .cer)
   ```
   
   **PKCS#12**
   ```
   - Certificate + Private Key + Chain (.pfx, .p12)
   - Protégé par mot de passe ⚠️
   ```

3. **Export PKCS#12** (inclut clé privée)
   ```
   Export Password: ********
   Friendly Name: www.example.com
   Include Chain: ✅ Recommandé
   ```

### Rechercher des Certificats

**Barre de recherche**
```
Recherche par:
- Common Name (CN)
- Serial Number
- Subject DN
- Issuer DN
- Email
```

**Filtres avancés**
```
Status: Active / Revoked / Expired
Type: Server / Client / Code Signing
Issuer: Sélectionner une CA
Validity: Expiring in 30/60/90 days
```

---

## 🔄 Serveur SCEP

SCEP (Simple Certificate Enrollment Protocol) permet l'enrollment automatique de certificats.

### Créer un Endpoint SCEP

1. **Menu → SCEP → New Endpoint**

2. **Configuration de base**
   ```
   Endpoint Name: Mobile Devices SCEP
   Description: SCEP pour iOS/Android
   Issuing CA: My Company Issuing CA 1
   ```

3. **Paramètres SCEP**
   ```
   Challenge Password: ****************
   Challenge Type: Dynamic (recommandé)
                  ou Static
   
   Validity: 365 jours
   Auto-renewal: ✅ Activé
   Renewal Window: 30 jours avant expiration
   ```

4. **Template de certificat**
   ```
   Certificate Type: Client Certificate
   Key Type: RSA 2048 ou ECDSA P-256
   Hash Algorithm: SHA-256
   
   Key Usage:
   - ✅ Digital Signature
   - ✅ Key Agreement
   
   Extended Key Usage:
   - ✅ Client Authentication
   - ✅ Email Protection (si nécessaire)
   ```

5. **URL SCEP générée**
   ```
   https://<serveur>:8443/scep/mobile-devices
   ```

### Configuration iOS

1. **Créer un profil de configuration (.mobileconfig)**

   UCM génère automatiquement le profil :
   
   ```
   Menu SCEP → Endpoint → Generate iOS Profile
   ```

2. **Paramètres du profil**
   ```
   Profile Name: Company PKI
   Organization: My Company Inc.
   Description: Enterprise Certificate Enrollment
   ```

3. **Distribuer le profil**
   - Email
   - MDM (Mobile Device Management)
   - URL de téléchargement
   - AirDrop

4. **Installation sur iOS**
   ```
   Settings → Profile Downloaded → Install
   Enter Challenge Password: ****
   ```

### Configuration Android

1. **Télécharger l'app de gestion SCEP**
   - Utiliser une app compatible SCEP
   - Ou intégration MDM

2. **Configuration manuelle**
   ```
   SCEP URL: https://<serveur>:8443/scep/mobile-devices
   Challenge Password: ****
   ```

### Configuration Windows

1. **Via GPO (Group Policy)**
   ```
   Computer Configuration
   → Policies
   → Windows Settings
   → Security Settings
   → Public Key Policies
   → Certificate Services Client - Auto-Enrollment
   ```

2. **Configuration NDES-like**
   ```
   SCEP URL: https://<serveur>:8443/scep/windows
   Challenge: ****
   ```

### Monitoring SCEP

**Menu SCEP → Endpoint → Activity**

Affiche :
- Enrollments réussis
- Échecs et raisons
- Renouvellements automatiques
- Révocations

---

## 👥 Gestion des Utilisateurs

UCM utilise un système RBAC (Role-Based Access Control).

### Rôles Disponibles

1. **Admin** 👑
   - Accès complet
   - Gestion des CAs
   - Gestion des utilisateurs
   - Configuration système

2. **Operator** 🔧
   - Émettre des certificats
   - Révoquer des certificats
   - Exporter des certificats
   - Voir les CAs (lecture seule)

3. **Viewer** 👁️
   - Voir les CAs
   - Voir les certificats
   - Télécharger les certificats publics
   - Aucune modification

### Créer un Utilisateur

1. **Menu → Settings → Users → Add User**

2. **Informations utilisateur**
   ```
   Username: john.doe
   Full Name: John Doe
   Email: john.doe@example.com
   Role: Operator
   ```

3. **Mot de passe**
   ```
   Password: ********** (min 8 caractères)
   Confirm: **********
   
   Exigences:
   - 8+ caractères
   - Majuscule + minuscule
   - Au moins 1 chiffre
   - 1 caractère spécial recommandé
   ```

4. **Options**
   ```
   ✅ Force password change on first login
   ✅ Account enabled
   ⬜ API access enabled
   ```

### Modifier un Utilisateur

1. **Liste des utilisateurs → Edit**

2. **Modifications possibles**
   - Nom complet
   - Email
   - Rôle
   - Statut du compte
   - Réinitialiser mot de passe

### Changer son Mot de Passe

1. **Menu utilisateur (haut droite) → Profile**

2. **Security → Change Password**
   ```
   Current Password: ****
   New Password: ********
   Confirm New Password: ********
   ```

---

## ⚙️ Paramètres Système

### Configuration Générale

**Menu → Settings → System**

```
System Name: My Company PKI
Base URL: https://pki.example.com:8443
Administrator Email: pki-admin@example.com
Organization: Example Inc.
```

### CRL (Certificate Revocation List)

```
CRL Update Interval: 24 heures
CRL Distribution Point: http://pki.example.com:8080/crl/<ca-id>.crl
Next CRL Update: 7 jours
```

### OCSP (Online Certificate Status Protocol)

```
OCSP Responder: ✅ Enabled
OCSP URL: http://ocsp.example.com:8080
OCSP Signing Certificate: Auto-generated
Response Validity: 7 jours
```

### Session et Sécurité

```
Session Timeout: 30 minutes
Max Login Attempts: 5
Lockout Duration: 15 minutes
Force HTTPS: ✅ Enabled
HSTS: ✅ Enabled
```

### Backup et Maintenance

**Backup automatique**
```
Backup Interval: Daily
Backup Time: 02:00 AM
Retention: 7 jours
Backup Path: /opt/ucm/backups/
```

**Maintenance**
```
Auto-cleanup expired certificates: ✅ 90 jours après expiration
Auto-cleanup revoked certificates: ❌ Conserver
Database optimization: Weekly
```

---

## 🎯 Opérations Courantes

### Cas d'usage 1: Certificat Serveur Web

**Scénario**: Sécuriser www.example.com

```
1. Certificates → Issue New Certificate
2. Issuing CA: Intermediate CA
3. Certificate Type: Server Certificate
4. Subject DN:
   CN: www.example.com
   O: Example Inc.
5. SANs:
   - www.example.com
   - example.com
6. Key: RSA 2048, SHA-256
7. Validity: 395 jours
8. Issue → Export PKCS#12
9. Installer sur serveur web
```

### Cas d'usage 2: VPN Client Certificates

**Scénario**: Authentification VPN par certificat

```
1. Certificates → Issue New Certificate
2. Type: Client Certificate
3. Subject:
   CN: john.doe
   Email: john.doe@example.com
4. Key Usage:
   - Digital Signature
   - Key Agreement
   - Client Authentication
5. Export PKCS#12 avec mot de passe
6. Envoyer de manière sécurisée à l'utilisateur
7. Configurer VPN pour accepter cette CA
```

### Cas d'usage 3: Code Signing

**Scénario**: Signer des applications

```
1. Certificates → Issue New Certificate
2. Type: Code Signing
3. Subject:
   CN: Example Inc. Code Signing
   O: Example Inc.
4. Key: RSA 4096 (recommandé pour code signing)
5. Validity: 3 ans maximum
6. Extended Key Usage: Code Signing
7. Export PKCS#12
8. Utiliser avec signtool, jarsigner, etc.
```

### Cas d'usage 4: Email S/MIME

**Scénario**: Signer et chiffrer emails

```
1. Certificates → Issue New Certificate
2. Type: Email Certificate
3. Subject:
   CN: John Doe
   Email: john.doe@example.com
4. SANs:
   Email: john.doe@example.com
5. Key Usage:
   - Digital Signature
   - Key Encipherment
   - Email Protection
6. Export PKCS#12
7. Importer dans client email (Outlook, Thunderbird)
```

### Cas d'usage 5: Enrollment SCEP iOS

**Scénario**: Déployer certificats sur 100 iPads

```
1. SCEP → New Endpoint
2. Name: iPad Fleet
3. Type: Client Certificate
4. Challenge: Dynamic
5. Auto-renewal: ✅
6. Generate iOS Profile
7. Distribuer via MDM
8. Les iPads s'enregistrent automatiquement
9. Renouvellement auto 30 jours avant expiration
```

---

## 📋 Checklist de Mise en Production

### Avant le Déploiement

- [ ] Root CA créée avec clé 4096 bits et validité 20 ans
- [ ] Intermediate CA créée pour émission quotidienne
- [ ] Backup de la Root CA effectué et stocké hors ligne
- [ ] Root CA stockée hors ligne (cold storage)
- [ ] Mot de passe admin changé
- [ ] Utilisateurs créés avec rôles appropriés
- [ ] Configuration HTTPS avec certificat valide
- [ ] CRL et OCSP configurés et accessibles
- [ ] Backup automatique configuré
- [ ] Firewall configuré (port 8443 HTTPS, 8080 HTTP pour CRL/OCSP)

### Après le Déploiement

- [ ] Test d'émission de certificat
- [ ] Test de révocation et vérification CRL
- [ ] Test OCSP
- [ ] Test SCEP enrollment
- [ ] Test de renouvellement
- [ ] Vérification des backups
- [ ] Documentation des procédures
- [ ] Formation des opérateurs

---

## 🆘 Aide et Support

- **Documentation**: [GitHub Wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki)
- **Issues**: [GitHub Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)
- **Discussions**: [GitHub Discussions](https://github.com/NeySlim/ultimate-ca-manager/discussions)

---

**Prochaine section**: [Troubleshooting](Troubleshooting) | [API Reference](API-Reference)
