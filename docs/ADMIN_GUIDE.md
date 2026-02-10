# UCM Admin Guide

Administration and configuration guide for Ultimate CA Manager.

---

## 🔧 Configuration Overview

UCM stores configuration in:
- **Database** - `/var/lib/ucm/ucm.db` (SQLite)
- **Data Directory** - `/var/lib/ucm/` (certificates, keys)
- **Logs** - `/var/log/ucm/` (application logs)

---

## ⚙️ Server Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `UCM_SECRET_KEY` | (generated) | JWT signing key |
| `UCM_HOST` | `0.0.0.0` | Bind address |
| `UCM_PORT` | `8443` | HTTPS port |
| `UCM_DATA_DIR` | `/var/lib/ucm` | Data storage |
| `UCM_LOG_LEVEL` | `INFO` | Logging verbosity |
| `UCM_HTTPS_CERT` | (auto) | Server certificate |
| `UCM_HTTPS_KEY` | (auto) | Server private key |

### Systemd Service

```bash
# Check status
sudo systemctl status ucm

# Restart service
sudo systemctl restart ucm

# View logs
sudo journalctl -u ucm -f

# Enable on boot
sudo systemctl enable ucm
```

### Log Rotation

Logs are rotated automatically via logrotate:
- Location: `/etc/logrotate.d/ucm`
- Rotation: Weekly, 4 copies kept
- Compression: gzip

---

## 🔒 Security Configuration

### HTTPS Certificate

UCM auto-generates a self-signed certificate on first run.

**Replace with trusted certificate:**

1. Go to **Settings** → **Security** tab
2. Select certificate from your CA
3. Click **Apply HTTPS Certificate**
4. Restart service: `sudo systemctl restart ucm`

**Or via files:**
```bash
# Copy your certificate and key
sudo cp /path/to/cert.pem /var/lib/ucm/https/server.crt
sudo cp /path/to/key.pem /var/lib/ucm/https/server.key
sudo chown ucm:ucm /var/lib/ucm/https/*
sudo systemctl restart ucm
```

### Session Security

Configure in **Settings** → **Security**:

| Setting | Default | Description |
|---------|---------|-------------|
| Session Timeout | 24h | Auto-logout after inactivity |
| Max Sessions | 5 | Per-user session limit |
| Require 2FA | No | Force MFA for all users |

### Authentication Methods

Enable/disable in **Settings** → **Security**:

- **Password** - Standard username/password
- **2FA TOTP** - Time-based one-time password
- **WebAuthn** - Hardware security keys
- **mTLS** - Client certificate authentication

---

## 💾 Backup & Restore

### Creating Backups

**Via UI:**
1. Go to **Settings** → **Backup** tab
2. Click **Create Backup**
3. Enter encryption password
4. Download `.ucmbkp` file

**Via CLI:**
```bash
cd /opt/ucm
./bin/ucm-backup --output backup.ucmbkp --password "YourPassword"
```

### Restoring Backups

**Via UI:**
1. Go to **Settings** → **Backup** tab
2. Click **Restore Backup**
3. Upload `.ucmbkp` file
4. Enter encryption password

**Via CLI:**
```bash
cd /opt/ucm
sudo systemctl stop ucm
./bin/ucm-restore --input backup.ucmbkp --password "YourPassword"
sudo systemctl start ucm
```

### Backup Contents

- All certificates and private keys
- CA hierarchy
- Users and settings
- Audit logs
- Templates

### Automated Backups

Create cron job:
```bash
# Daily backup at 2 AM
0 2 * * * /opt/ucm/bin/ucm-backup -o /backup/ucm-$(date +\%Y\%m\%d).ucmbkp -p "$BACKUP_PASSWORD"
```

---

## 📊 Database Management

### SQLite Database

Location: `/var/lib/ucm/ucm.db`

**Vacuum database:**
```bash
sudo systemctl stop ucm
sqlite3 /var/lib/ucm/ucm.db "VACUUM;"
sudo systemctl start ucm
```

**Export database:**
```bash
sqlite3 /var/lib/ucm/ucm.db ".dump" > ucm_dump.sql
```

### Database Tables

| Table | Purpose |
|-------|---------|
| `users` | User accounts |
| `certificates` | Certificate records |
| `certificate_authorities` | CA records |
| `audit_logs` | Activity audit trail |
| `settings` | Application settings |
| `templates` | Certificate templates |
| `acme_accounts` | ACME client accounts |
| `scep_requests` | SCEP enrollment requests |

---

## 📡 Protocol Administration

### CRL Distribution

**Configure CRL endpoint:**
1. CRL URL: `https://your-server:8443/crl/<ca-id>.crl`
2. Configure in CA settings → CRL tab
3. Set regeneration interval

**Manual CRL regeneration:**
```bash
curl -X POST https://localhost:8443/api/v2/crl/regenerate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"ca_id": 1}'
```

### OCSP Configuration

OCSP responder runs automatically:
- URL: `https://your-server:8443/ocsp`
- Signing: Uses issuing CA's certificate
- Caching: 5-minute response cache

### ACME Administration

**View ACME accounts:**
```bash
curl https://localhost:8443/api/v2/acme/accounts \
  -H "Authorization: Bearer $TOKEN"
```

**Revoke ACME certificate:**
```bash
curl -X POST https://localhost:8443/api/v2/acme/revoke \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"certificate_id": 123}'
```

### SCEP Administration

**View pending requests:**
```bash
curl https://localhost:8443/api/v2/scep/requests?status=pending \
  -H "Authorization: Bearer $TOKEN"
```

**Approve/reject requests:**
```bash
# Approve
curl -X POST https://localhost:8443/api/v2/scep/requests/1/approve \
  -H "Authorization: Bearer $TOKEN"

# Reject
curl -X POST https://localhost:8443/api/v2/scep/requests/1/reject \
  -H "Authorization: Bearer $TOKEN"
```

---

## 👥 User Administration

### Password Reset

**Admin reset:**
1. Go to **Users** page
2. Select user
3. Click **Reset Password**
4. Set temporary password
5. User must change on next login

**CLI reset:**
```bash
cd /opt/ucm
./bin/ucm-reset-password --user admin --password "NewPassword123"
```

### Role Management

| Role | Certificates | CAs | Users | Settings |
|------|--------------|-----|-------|----------|
| Admin | Full | Full | Full | Full |
| Operator | Full | Full | Read | Read |
| Viewer | Read | Read | None | None |

### API Keys

Users can create API keys for automation:
1. Go to **Account** → **API Keys**
2. Click **Generate Key**
3. Copy key (shown only once)
4. Use in Authorization header: `Bearer <api-key>`

---

## 📈 Monitoring

### Health Check

```bash
curl -k https://localhost:8443/api/v2/health
# {"status": "healthy", "version": "2.0.x", ...}
```

### Metrics

Key metrics to monitor:
- Certificate expiration dates
- CA validity periods
- Disk space for data directory
- Database size

### Audit Log

All actions are logged:
- Go to **Audit** page
- Filter by action, user, date
- Export CSV for compliance

---

## 🔄 Upgrades

### Standard Upgrade

```bash
# Docker
docker pull neyslim/ultimate-ca-manager:latest
docker-compose up -d

# Package
sudo apt update && sudo apt upgrade ucm

# Source
cd /opt/ucm
git pull
./bin/ucm-upgrade
```

### Migration Guide

See [UPGRADE.md](../UPGRADE.md) for version-specific migration steps.

---

## 🐛 Troubleshooting

### Service Won't Start

```bash
# Check logs
sudo journalctl -u ucm -n 100

# Check permissions
ls -la /var/lib/ucm/
sudo chown -R ucm:ucm /var/lib/ucm/

# Check port
sudo netstat -tlpn | grep 8443
```

### Database Locked

```bash
# Find locking process
fuser /var/lib/ucm/ucm.db

# Stop service and fix
sudo systemctl stop ucm
sqlite3 /var/lib/ucm/ucm.db "PRAGMA integrity_check;"
sudo systemctl start ucm
```

### Certificate Issues

```bash
# Verify certificate
openssl x509 -in /var/lib/ucm/https/server.crt -text -noout

# Check key match
openssl x509 -noout -modulus -in server.crt | md5sum
openssl rsa -noout -modulus -in server.key | md5sum
```

---

## 📚 References

- [User Guide](USER_GUIDE.md)
- [API Reference](API_REFERENCE.md)
- [Installation](installation/README.md)
- [Changelog](../CHANGELOG.md)
