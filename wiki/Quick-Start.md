# 🚀 Quick Start - UCM

Guide de démarrage rapide pour être opérationnel en 10 minutes.

---

## ⏱️ Installation Rapide (5 minutes)

### Option 1: Docker (Recommandé)

```bash
# Télécharger docker-compose.yml
curl -O https://raw.githubusercontent.com/NeySlim/ultimate-ca-manager/main/docker-compose.yml

# Démarrer UCM
docker-compose up -d

# Vérifier le statut
docker-compose ps
```

**Accès**: https://localhost:8443

### Option 2: Linux Installation

```bash
# Télécharger l'installeur
curl -LO https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.0.1/install.sh

# Rendre exécutable et installer
chmod +x install.sh
sudo ./install.sh

# Démarrer UCM
sudo systemctl start ucm
```

**Accès**: https://localhost:8443

---

## 🔐 Première Connexion (2 minutes)

1. **Ouvrir le navigateur**
   ```
   https://localhost:8443
   ```

2. **Accepter le certificat auto-signé**
   - Cliquez sur "Avancé" ou "Advanced"
   - Puis "Continuer vers le site" ou "Proceed"

3. **Connexion**
   ```
   Utilisateur: admin
   Mot de passe: admin
   ```

4. **⚠️ Changer le mot de passe**
   - Menu utilisateur (haut droite) → Profile
   - Security → Change Password
   - Nouveau mot de passe: min 8 caractères

---

## 🏛️ Créer votre PKI (3 minutes)

### Étape 1: Créer une Root CA

```
Menu → Certificate Authorities → Create New CA

Configuration:
├─ CA Type: Root CA
├─ Key Type: RSA 4096 bits
├─ Hash: SHA-384
├─ Validity: 7300 jours (20 ans)
└─ Common Name: My Company Root CA

Cliquer "Create CA"
```

### Étape 2: Créer une Intermediate CA

```
Create New CA

Configuration:
├─ CA Type: Intermediate CA
├─ Parent CA: My Company Root CA
├─ Key Type: RSA 4096 bits
├─ Hash: SHA-256
├─ Validity: 3650 jours (10 ans)
└─ Common Name: My Company Issuing CA

Cliquer "Create CA"
```

✅ **Votre PKI est prête !**

---

## 📜 Émettre votre Premier Certificat

### Certificat Serveur Web

```
Menu → Certificates → Issue New Certificate

Configuration:
├─ Issuing CA: My Company Issuing CA
├─ Certificate Type: Server Certificate
├─ Common Name: www.example.com
├─ Organization: My Company Inc.
├─ Key Type: RSA 2048
├─ Validity: 365 jours
│
└─ Subject Alternative Names (SANs):
   ├─ www.example.com
   └─ example.com

Cliquer "Issue Certificate"
```

### Télécharger le Certificat

```
1. Le certificat apparaît dans la liste
2. Cliquer sur Actions → Export
3. Format: PKCS#12 (.pfx)
4. Mot de passe: ******** (choisir un mot de passe fort)
5. Download
```

✅ **Vous avez votre premier certificat !**

---

## 🔄 Configurer SCEP (Optionnel)

Pour l'enrollment automatique (iOS, Android, etc.)

```
Menu → SCEP → New Endpoint

Configuration:
├─ Endpoint Name: Mobile Devices
├─ Issuing CA: My Company Issuing CA
├─ Challenge Password: ****************
├─ Certificate Type: Client Certificate
├─ Validity: 365 jours
└─ Auto-renewal: ✅ Activé

Cliquer "Create Endpoint"
```

**URL SCEP générée**:
```
https://<votre-serveur>:8443/scep/mobile-devices
```

---

## 📊 Vérifier le Tableau de Bord

Retournez au Dashboard pour voir:

- ✅ Nombre de CAs créées
- ✅ Certificats émis
- ✅ Endpoints SCEP actifs
- ✅ Graphiques d'activité

---

## 🎯 Prochaines Étapes

Maintenant que votre PKI est opérationnelle:

1. **[Lire le Manuel Utilisateur](User-Manual)** - Documentation complète
2. **[Configurer CRL/OCSP](System-Configuration)** - Révocation de certificats
3. **[Créer des utilisateurs](User-Management)** - Déléguer des tâches
4. **[Configurer les backups](System-Configuration#backup)** - Sécuriser vos données
5. **[Déployer en production](Installation-Guide#production-deployment)** - Bonnes pratiques

---

## 🆘 Besoin d'Aide ?

- **[Troubleshooting](Troubleshooting)** - Problèmes courants
- **[FAQ](FAQ)** - Questions fréquentes
- **[GitHub Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)** - Support communauté

---

## ✅ Checklist Démarrage Rapide

- [ ] UCM installé et accessible
- [ ] Mot de passe admin changé
- [ ] Root CA créée
- [ ] Intermediate CA créée
- [ ] Premier certificat émis
- [ ] Certificat téléchargé et testé
- [ ] SCEP configuré (si nécessaire)
- [ ] Dashboard vérifié

**Félicitations ! Vous êtes prêt à utiliser UCM ! 🎉**

---

**Temps total**: ~10 minutes  
**Niveau**: Débutant  
**Prérequis**: Aucun

[← Retour à l'accueil](Home) | [Manuel Utilisateur →](User-Manual)
