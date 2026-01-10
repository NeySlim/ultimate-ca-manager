# 🔧 Troubleshooting - UCM

Troubleshooting guide to resolve common issues.

---

## 📑 Table of Contents

1. [Installation](#installation)
2. [Login and Authentication](#login-and-authentication)
3. [Certificates](#certificates)
4. [SCEP](#scep)
5. [Performance](#performance)
6. [Database](#database)
7. [Docker](#docker)

---

## 🔨 Installation

### Issue: Installer fails

**Symptoms**:
```
ERROR: Unsupported distribution
```

**Solution**:
```bash
# Check distribution
cat /etc/os-release

# Supported distributions:
# - Debian 11/12
# - Ubuntu 20.04/22.04/24.04
# - RHEL/Rocky/Alma 8/9
# - Fedora 38+
# - openSUSE Leap 15+
# - Arch Linux
```

### Issue: Python 3.10+ not available

**Symptoms**:
```
ERROR: Python 3.10 or higher is required
```

**Ubuntu/Debian solution**:
```bash
# Add deadsnakes PPA
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.11 python3.11-venv python3.11-dev
```

**RHEL/Rocky 8 solution**:
```bash
# Enable Python 3.11
sudo dnf install python3.11 python3.11-devel
```

### Issue: Port 8443 already in use

**Symptoms**:
```
ERROR: Address already in use: 0.0.0.0:8443
```

**Solution**:
```bash
# Find process using the port
sudo lsof -i :8443
sudo netstat -tlnp | grep 8443

# Stop the process or change UCM port
# Edit /opt/ucm/.env:
UCM_HTTPS_PORT=9443
```

---

## 🔐 Login and Authentication

### Issue: "Certificate not trusted" in browser

**Cause**: Self-signed certificate during initial installation

**Temporary solution**:
```
1. Click "Advanced"
2. Click "Proceed to site" or "Continue to site"
```

**Permanent solution**:
```
1. Download the self-signed certificate
2. Add it to browser trusted authorities
   
   OR
   
3. Generate a certificate with your own CA
4. Replace /opt/ucm/ssl/server.crt and server.key
5. Restart UCM
```

### Issue: Forgotten password

**Solution for admin**:
```bash
# Reset admin password
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

### Issue: "Account locked"

**Cause**: Too many failed login attempts (5 by default)

**Solution**:
```bash
# Unlock account
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

## 📜 Certificates

### Issue: Certificate rejected by browser

**Symptoms**:
```
NET::ERR_CERT_COMMON_NAME_INVALID
```

**Cause**: Missing SANs (Subject Alternative Names)

**Solution**:
```
Modern browsers IGNORE CN and use SANs only.

When issuing, ALWAYS add:
- SANs → DNS Names → www.example.com
- SANs → DNS Names → example.com

Then revoke and reissue the certificate.
```

### Issue: "Certificate has expired"

**Verification**:
```bash
# Check validity
openssl x509 -in certificate.pem -noout -dates

notBefore=Jan  1 00:00:00 2025 GMT
notAfter=Jan  1 00:00:00 2024 GMT  # ← EXPIRED!
```

**Solution**:
```
1. UCM → Certificates → Select certificate
2. Actions → Renew
3. Choose new validity (e.g., 365 days)
4. Export and redeploy
```

### Issue: "unable to get local issuer certificate"

**Cause**: Incomplete certificate chain

**Solution**:
```bash
# Verify chain
openssl verify -CAfile root-ca.pem intermediate-ca.pem

# Export full chain from UCM
Export → Full chain (PEM)

# Chain should contain:
# 1. Server certificate
# 2. Intermediate CA
# 3. Root CA (optional but recommended)
```

### Issue: PKCS#12 certificate won't open

**Symptoms**:
```
Error: Invalid password or corrupted file
```

**Solutions**:
```bash
# Verify file
openssl pkcs12 -info -in certificate.pfx

# If "mac verify error":
# → Incorrect password

# If "asn1 encoding routines":
# → Corrupted file, regenerate from UCM

# Convert to PEM for debugging
openssl pkcs12 -in cert.pfx -out cert.pem -nodes
```

---

## 🔄 SCEP

### Issue: iOS refuses SCEP profile

**Symptoms**:
```
"Profile Installation Failed"
"Cannot verify server identity"
```

**Solution**:
```
1. UCM HTTPS certificate must be trusted
2. Options:
   a) First install Root CA on iOS
   b) Use public certificate (Let's Encrypt)
   
3. Verify SCEP URL:
   https://<FQDN>:8443/scep/endpoint-name
   ↑ Full FQDN, not IP
```

### Issue: "Challenge password incorrect"

**Verification**:
```
1. UCM → SCEP → Endpoint → View Details
2. Check Challenge Password
3. Type: Dynamic or Static?

If Dynamic:
- Each enrollment generates a new password
- Use "Generate enrollment URL" to get URL with correct challenge

If Static:
- Same password for all
- Copy-paste exactly (watch for spaces)
```

### Issue: SCEP enrollment stuck "Pending"

**Cause**: Auto-approval disabled

**Solution**:
```
1. UCM → SCEP → Endpoint → Settings
2. Auto-approve: ✅ Enabled
3. Save

OR manually:
1. UCM → Certificates → Pending Requests
2. Review → Approve
```

### Issue: Automatic renewal doesn't work

**Verification**:
```
1. SCEP Endpoint → Auto-renewal: ✅ Enabled?
2. Renewal window: 30 days (default)
3. Device must have network access to UCM
4. Logs: /opt/ucm/logs/scep.log

tail -f /opt/ucm/logs/scep.log
```

---

## ⚡ Performance

### Issue: UCM slow / timeout

**Diagnostic**:
```bash
# Check load
htop
top

# Check Gunicorn workers
ps aux | grep gunicorn

# Recommended workers:
# (2 × CPU cores) + 1
# Example: 8 cores = 17 workers
```

**Solution**:
```bash
# Adjust workers in /opt/ucm/gunicorn.conf.py
workers = 17  # Increase if CPU available

# Or via environment variable
echo "UCM_WORKERS=17" >> /opt/ucm/.env

# Restart
sudo systemctl restart ucm
```

### Issue: Database slow

**Symptoms**:
```
Queries > 5 seconds
Timeout when listing certificates
```

**SQLite solution** (default):
```bash
# SQLite limited to ~2000 certificates
# Migration to PostgreSQL recommended

# Optimize temporarily:
cd /opt/ucm
sqlite3 instance/ucm.db "VACUUM; REINDEX;"
```

**Migration to PostgreSQL**:
```bash
# See: docs/MIGRATION_EXAMPLE.md
docker-compose -f docker-compose.postgres.yml up -d
```

---

## 💾 Database

### Issue: "database is locked"

**Cause**: SQLite + multiple workers + concurrent writes

**Immediate solution**:
```bash
# Restart UCM
sudo systemctl restart ucm
```

**Permanent solution**:
```bash
# Migrate to PostgreSQL
# See docker-compose.postgres.yml
```

### Issue: Corrupted database

**Symptoms**:
```
sqlite3.DatabaseError: database disk image is malformed
```

**Recovery**:
```bash
# Backup first!
cp /opt/ucm/instance/ucm.db /tmp/ucm.db.backup

# Attempt repair
cd /opt/ucm/instance
sqlite3 ucm.db "PRAGMA integrity_check;"

# If errors:
sqlite3 ucm.db ".recover" | sqlite3 ucm_recovered.db
mv ucm.db ucm.db.corrupted
mv ucm_recovered.db ucm.db

# Restart
sudo systemctl restart ucm
```

**If recovery fails**:
```bash
# Restore from backup
# Automatic backups in: /opt/ucm/backups/
ls -lh /opt/ucm/backups/

# Restore most recent
cp /opt/ucm/backups/ucm-backup-2026-01-04.db /opt/ucm/instance/ucm.db
sudo systemctl restart ucm
```

---

## 🐳 Docker

### Issue: Container won't start

**Diagnostic**:
```bash
# Container logs
docker-compose logs ucm

# Status
docker-compose ps

# Inspect
docker-compose exec ucm /bin/bash
```

### Issue: Permission denied on volumes

**Symptoms**:
```
PermissionError: [Errno 13] Permission denied: '/data'
```

**Solution**:
```bash
# Check ownership
ls -ld ./data

# Fix (UID 1000 = ucm user in container)
sudo chown -R 1000:1000 ./data
sudo chown -R 1000:1000 ./postgres-data

# Restart
docker-compose down
docker-compose up -d
```

### Issue: Port already in use

**Symptoms**:
```
Error: port is already allocated
```

**Solution**:
```bash
# Edit .env
UCM_HTTPS_PORT=9443

# Or docker-compose.yml
ports:
  - "9443:8443"

# Restart
docker-compose up -d
```

### Issue: Host migration fails

**Solution**:
```bash
# On old server
docker-compose down
tar czf ucm-backup.tar.gz data/ postgres-data/ .env docker-compose.yml

# Transfer
scp ucm-backup.tar.gz user@new-server:/opt/

# On new server
cd /opt
tar xzf ucm-backup.tar.gz
docker-compose up -d

# Verify
docker-compose ps
docker-compose logs
```

---

## 🔍 General Debugging

### Enable debug mode

**⚠️ DO NOT use in production!**

```bash
# .env
FLASK_ENV=development
FLASK_DEBUG=True
LOG_LEVEL=DEBUG

# Restart
sudo systemctl restart ucm
```

### Check logs

```bash
# System logs
sudo journalctl -u ucm -f

# Application logs
tail -f /opt/ucm/logs/ucm.log
tail -f /opt/ucm/logs/error.log

# SCEP logs
tail -f /opt/ucm/logs/scep.log

# Docker
docker-compose logs -f ucm
```

### Verify configuration

```bash
# Environment
cat /opt/ucm/.env

# Gunicorn
cat /opt/ucm/gunicorn.conf.py

# Systemd
systemctl status ucm
systemctl cat ucm
```

---

## 📞 Getting Help

If the problem persists:

1. **Check complete logs**
2. **Consult the [FAQ](FAQ)**
3. **Search in [GitHub Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)**
4. **Create a new issue** with:
   - UCM version
   - OS and version
   - Complete error logs
   - Steps to reproduce

---

**Related sections**: [FAQ](FAQ) | [Installation Guide](Installation-Guide) | [System Configuration](System-Configuration)
