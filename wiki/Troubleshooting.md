# 🔧 Troubleshooting - UCM

Guide de dépannage pour résoudre les problèmes courants.

---

## 📑 Table des Matières

1. [Installation](#installation)
2. [Connexion et Authentification](#connexion-et-authentification)
3. [Certificats](#certificats)
4. [SCEP](#scep)
5. [Performance](#performance)
6. [Base de Données](#base-de-données)
7. [Docker](#docker)

---

## 🔨 Installation

### Problème: L'installeur échoue

**Symptômes**:
```
ERROR: Unsupported distribution
```

**Solution**:
```bash
# Vérifier la distribution
cat /etc/os-release

# Distributions supportées:
# - Debian 11/12
# - Ubuntu 20.04/22.04/24.04
# - RHEL/Rocky/Alma 8/9
# - Fedora 38+
# - openSUSE Leap 15+
# - Arch Linux
```

### Problème: Python 3.10+ non disponible

**Symptômes**:
```
ERROR: Python 3.10 or higher is required
```

**Solution Ubuntu/Debian**:
```bash
# Ajouter le PPA deadsnakes
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.11 python3.11-venv python3.11-dev
```

**Solution RHEL/Rocky 8**:
```bash
# Activer Python 3.11
sudo dnf install python3.11 python3.11-devel
```

### Problème: Port 8443 déjà utilisé

**Symptômes**:
```
ERROR: Address already in use: 0.0.0.0:8443
```

**Solution**:
```bash
# Trouver le processus utilisant le port
sudo lsof -i :8443
sudo netstat -tlnp | grep 8443

# Arrêter le processus ou changer le port UCM
# Modifier /opt/ucm/.env:
UCM_HTTPS_PORT=9443
```

---

## 🔐 Connexion et Authentification

### Problème: "Certificate not trusted" dans le navigateur

**Cause**: Certificat auto-signé lors de la première installation

**Solution temporaire**:
```
1. Cliquer "Avancé" ou "Advanced"
2. Cliquer "Continuer vers le site" ou "Proceed to site"
```

**Solution permanente**:
```
1. Télécharger le certificat auto-signé
2. L'ajouter aux autorités de confiance du navigateur
   
   OU
   
3. Générer un certificat avec votre propre CA
4. Remplacer /opt/ucm/ssl/server.crt et server.key
5. Redémarrer UCM
```

### Problème: Mot de passe oublié

**Solution pour l'admin**:
```bash
# Réinitialiser le mot de passe admin
cd /opt/ucm
source venv/bin/activate
python3 << EOF
from app import create_app, db
from app.models import User
from werkzeug.security import generate_password_hash

app = create_app()
with app.app_context():
    admin = User.query.filter_by(username='admin').first()
    admin.password_hash = generate_password_hash('newpassword')
    db.session.commit()
    print("Password reset to: newpassword")
EOF
```

### Problème: "Account locked"

**Cause**: Trop de tentatives de connexion échouées (5 par défaut)

**Solution**:
```bash
# Débloquer le compte
cd /opt/ucm
source venv/bin/activate
python3 << EOF
from app import create_app, db
from app.models import User

app = create_app()
with app.app_context():
    user = User.query.filter_by(username='john.doe').first()
    user.failed_login_attempts = 0
    user.locked_until = None
    db.session.commit()
    print(f"Account {user.username} unlocked")
EOF
```

---

## 📜 Certificats

### Problème: Certificat rejeté par le navigateur

**Symptômes**:
```
NET::ERR_CERT_COMMON_NAME_INVALID
```

**Cause**: SANs (Subject Alternative Names) manquants

**Solution**:
```
Les navigateurs modernes IGNORENT le CN et utilisent uniquement les SANs.

Lors de l'émission, TOUJOURS ajouter:
- SANs → DNS Names → www.example.com
- SANs → DNS Names → example.com

Puis révoquer et réémettre le certificat.
```

### Problème: "Certificate has expired"

**Vérification**:
```bash
# Vérifier la validité
openssl x509 -in certificate.pem -noout -dates

notBefore=Jan  1 00:00:00 2025 GMT
notAfter=Jan  1 00:00:00 2024 GMT  # ← EXPIRÉ !
```

**Solution**:
```
1. UCM → Certificates → Sélectionner le certificat
2. Actions → Renew
3. Choisir nouvelle validité (ex: 365 jours)
4. Export et redéploiement
```

### Problème: "unable to get local issuer certificate"

**Cause**: Chaîne de certificats incomplète

**Solution**:
```bash
# Vérifier la chaîne
openssl verify -CAfile root-ca.pem intermediate-ca.pem

# Exporter la chaîne complète depuis UCM
Export → Full chain (PEM)

# La chaîne doit contenir:
# 1. Certificat serveur
# 2. Intermediate CA
# 3. Root CA (optionnel mais recommandé)
```

### Problème: Certificat PKCS#12 ne s'ouvre pas

**Symptômes**:
```
Error: Invalid password or corrupted file
```

**Solutions**:
```bash
# Vérifier le fichier
openssl pkcs12 -info -in certificate.pfx

# Si erreur "mac verify error":
# → Mot de passe incorrect

# Si erreur "asn1 encoding routines":
# → Fichier corrompu, régénérer depuis UCM

# Convertir en PEM pour debug
openssl pkcs12 -in cert.pfx -out cert.pem -nodes
```

---

## 🔄 SCEP

### Problème: iOS refuse le profil SCEP

**Symptômes**:
```
"Profile Installation Failed"
"Cannot verify server identity"
```

**Solution**:
```
1. Le certificat HTTPS de UCM doit être de confiance
2. Options:
   a) Installer d'abord le Root CA sur iOS
   b) Utiliser un certificat public (Let's Encrypt)
   
3. Vérifier l'URL SCEP:
   https://<FQDN>:8443/scep/endpoint-name
   ↑ FQDN complet, pas d'IP
```

### Problème: "Challenge password incorrect"

**Vérification**:
```
1. UCM → SCEP → Endpoint → View Details
2. Vérifier le Challenge Password
3. Type: Dynamic ou Static?

Si Dynamic:
- Chaque enrollment génère un nouveau password
- Utiliser "Generate enrollment URL" pour obtenir l'URL avec le bon challenge

Si Static:
- Même password pour tous
- Copier-coller exactement (attention aux espaces)
```

### Problème: SCEP enrollment bloqué "Pending"

**Cause**: Auto-approval désactivé

**Solution**:
```
1. UCM → SCEP → Endpoint → Settings
2. Auto-approve: ✅ Enabled
3. Save

OU manuellement:
1. UCM → Certificates → Pending Requests
2. Review → Approve
```

### Problème: Renouvellement automatique ne fonctionne pas

**Vérification**:
```
1. SCEP Endpoint → Auto-renewal: ✅ Enabled?
2. Renewal window: 30 jours (par défaut)
3. Le device doit avoir accès réseau à UCM
4. Logs: /opt/ucm/logs/scep.log

tail -f /opt/ucm/logs/scep.log
```

---

## ⚡ Performance

### Problème: UCM lent / timeout

**Diagnostic**:
```bash
# Vérifier la charge
htop
top

# Vérifier les workers Gunicorn
ps aux | grep gunicorn

# Nombre de workers recommandé:
# (2 × CPU cores) + 1
# Exemple: 8 cores = 17 workers
```

**Solution**:
```bash
# Ajuster workers dans /opt/ucm/gunicorn.conf.py
workers = 17  # Augmenter si CPU disponible

# Ou via variable d'environnement
echo "UCM_WORKERS=17" >> /opt/ucm/.env

# Redémarrer
sudo systemctl restart ucm
```

### Problème: Base de données lente

**Symptômes**:
```
Requêtes > 5 secondes
Timeout lors de la liste des certificats
```

**Solution SQLite** (défaut):
```bash
# SQLite limité à ~2000 certificats
# Migration vers PostgreSQL recommandée

# Optimiser temporairement:
cd /opt/ucm
sqlite3 instance/ucm.db "VACUUM; REINDEX;"
```

**Migration vers PostgreSQL**:
```bash
# Voir: docs/MIGRATION_EXAMPLE.md
docker-compose -f docker-compose.postgres.yml up -d
```

---

## 💾 Base de Données

### Problème: "database is locked"

**Cause**: SQLite + plusieurs workers + écritures concurrentes

**Solution immédiate**:
```bash
# Redémarrer UCM
sudo systemctl restart ucm
```

**Solution permanente**:
```bash
# Migrer vers PostgreSQL
# Voir docker-compose.postgres.yml
```

### Problème: Base corrompue

**Symptômes**:
```
sqlite3.DatabaseError: database disk image is malformed
```

**Récupération**:
```bash
# Backup d'abord !
cp /opt/ucm/instance/ucm.db /tmp/ucm.db.backup

# Tenter réparation
cd /opt/ucm/instance
sqlite3 ucm.db "PRAGMA integrity_check;"

# Si erreurs:
sqlite3 ucm.db ".recover" | sqlite3 ucm_recovered.db
mv ucm.db ucm.db.corrupted
mv ucm_recovered.db ucm.db

# Redémarrer
sudo systemctl restart ucm
```

**Si récupération échoue**:
```bash
# Restaurer depuis backup
# Backups automatiques dans: /opt/ucm/backups/
ls -lh /opt/ucm/backups/

# Restaurer le plus récent
cp /opt/ucm/backups/ucm-backup-2026-01-04.db /opt/ucm/instance/ucm.db
sudo systemctl restart ucm
```

---

## 🐳 Docker

### Problème: Container n'démarre pas

**Diagnostic**:
```bash
# Logs du container
docker-compose logs ucm

# Status
docker-compose ps

# Inspecter
docker-compose exec ucm /bin/bash
```

### Problème: Permission denied sur volumes

**Symptômes**:
```
PermissionError: [Errno 13] Permission denied: '/data'
```

**Solution**:
```bash
# Vérifier ownership
ls -ld ./data

# Corriger (UID 1000 = user ucm dans container)
sudo chown -R 1000:1000 ./data
sudo chown -R 1000:1000 ./postgres-data

# Redémarrer
docker-compose down
docker-compose up -d
```

### Problème: Port déjà utilisé

**Symptômes**:
```
Error: port is already allocated
```

**Solution**:
```bash
# Modifier .env
UCM_HTTPS_PORT=9443

# Ou docker-compose.yml
ports:
  - "9443:8443"

# Redémarrer
docker-compose up -d
```

### Problème: Migration de host échoue

**Solution**:
```bash
# Sur ancien serveur
docker-compose down
tar czf ucm-backup.tar.gz data/ postgres-data/ .env docker-compose.yml

# Transférer
scp ucm-backup.tar.gz user@new-server:/opt/

# Sur nouveau serveur
cd /opt
tar xzf ucm-backup.tar.gz
docker-compose up -d

# Vérifier
docker-compose ps
docker-compose logs
```

---

## 🔍 Debugging Général

### Activer le mode debug

**⚠️ NE PAS utiliser en production !**

```bash
# .env
FLASK_ENV=development
FLASK_DEBUG=True
LOG_LEVEL=DEBUG

# Redémarrer
sudo systemctl restart ucm
```

### Consulter les logs

```bash
# Logs système
sudo journalctl -u ucm -f

# Logs applicatifs
tail -f /opt/ucm/logs/ucm.log
tail -f /opt/ucm/logs/error.log

# Logs SCEP
tail -f /opt/ucm/logs/scep.log

# Docker
docker-compose logs -f ucm
```

### Vérifier la configuration

```bash
# Environnement
cat /opt/ucm/.env

# Gunicorn
cat /opt/ucm/gunicorn.conf.py

# Systemd
systemctl status ucm
systemctl cat ucm
```

---

## 📞 Obtenir de l'Aide

Si le problème persiste:

1. **Vérifier les logs** complets
2. **Consulter la [FAQ](FAQ)**
3. **Chercher dans [GitHub Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)**
4. **Créer un nouveau issue** avec:
   - Version UCM
   - OS et version
   - Logs d'erreur complets
   - Steps pour reproduire

---

**Sections connexes**: [FAQ](FAQ) | [Installation Guide](Installation-Guide) | [System Configuration](System-Configuration)
