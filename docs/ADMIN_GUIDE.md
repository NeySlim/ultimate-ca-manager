# UCM Admin Guide

Administration and configuration guide for Ultimate CA Manager.

---

## Configuration Overview

UCM stores data in:
- **Database** -- `/opt/ucm/data/ucm.db` (SQLite)
- **Data Directory** -- `/opt/ucm/data/` (certificates, keys, backups)
- **Config** -- `/etc/ucm/ucm.env` (DEB/RPM) or environment variables (Docker)
- **Logs** -- `/var/log/ucm/` (DEB/RPM) or stdout (Docker)

---

## Server Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `UCM_SECRET_KEY` | (generated) | Session signing key |
| `UCM_HOST` | `0.0.0.0` | Bind address |
| `UCM_PORT` | `8443` | HTTPS port |
| `UCM_DATA_DIR` | `/opt/ucm/data` | Data storage |
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

The service runs as user `ucm` with restricted permissions (NoNewPrivileges, ProtectSystem=strict).

### Log Rotation

Logs are rotated automatically via logrotate:
- Location: `/etc/logrotate.d/ucm`
- Rotation: Daily, 14 copies kept
- Compression: gzip

See [LOG_ROTATION.md](LOG_ROTATION.md) for details.

---

## Security Configuration

### HTTPS Certificate

UCM auto-generates a self-signed certificate on first run.

**Replace with trusted certificate:**

1. Go to **Settings** > **Security** tab
2. Select certificate from your CA
3. Click **Apply HTTPS Certificate**
4. Restart service: `sudo systemctl restart ucm`

**Or via files:**
```bash
sudo cp /path/to/cert.pem /opt/ucm/data/https_cert.pem
sudo cp /path/to/key.pem /opt/ucm/data/https_key.pem
sudo chown ucm:ucm /opt/ucm/data/https_*.pem
sudo systemctl restart ucm
```

### Session Security

Configure in **Settings** > **Security**:

| Setting | Default | Description |
|---------|---------|-------------|
| Session Timeout | 24h | Auto-logout after inactivity |
| Max Sessions | 5 | Per-user session limit |
| Require 2FA | No | Force MFA for all users |

### Authentication Methods

Enable/disable in **Settings** > **Security**:

- **Password** -- Standard username/password
- **2FA TOTP** -- Time-based one-time password
- **WebAuthn** -- Hardware security keys
- **mTLS** -- Client certificate authentication

---

## Backup & Restore

### Creating Backups

**Via UI:**
1. Go to **Settings** > **Backup** tab
2. Click **Create Backup**
3. Enter encryption password
4. Download `.ucmbkp` file

**Via command line:**
```bash
sudo systemctl stop ucm
sudo cp /opt/ucm/data/ucm.db ~/ucm-backup-$(date +%Y%m%d).db
sudo systemctl start ucm
```

### Restoring Backups

**Via UI:**
1. Go to **Settings** > **Backup** tab
2. Click **Restore Backup**
3. Upload `.ucmbkp` file
4. Enter encryption password

### Backup Contents

- All certificates and private keys
- CA hierarchy
- Users and settings
- Audit logs
- Templates

---

## Database Management

### SQLite Database

Location: `/opt/ucm/data/ucm.db`

**Vacuum database:**
```bash
sudo systemctl stop ucm
sqlite3 /opt/ucm/data/ucm.db "VACUUM;"
sudo systemctl start ucm
```

**Export database:**
```bash
sqlite3 /opt/ucm/data/ucm.db ".dump" > ucm_dump.sql
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

## Protocol Administration

### CRL Distribution

**Configure CRL endpoint:**
1. CRL URL: `https://your-server:8443/crl/<ca-id>.crl`
2. Configure in CA settings > CRL tab
3. Set regeneration interval

### OCSP Configuration

OCSP responder runs automatically:
- URL: `https://your-server:8443/ocsp`
- Signing: Uses issuing CA's certificate
- Caching: 5-minute response cache

### ACME Administration

View ACME accounts and orders in the ACME page, or via API:

```bash
curl -k -b cookies.txt https://localhost:8443/api/v2/acme/accounts
```

### SCEP Administration

View pending SCEP requests in the SCEP page, or via API:

```bash
curl -k -b cookies.txt https://localhost:8443/api/v2/scep/requests?status=pending
```

---

## User Administration

### Password Reset

**Admin reset:**
1. Go to **Users** page
2. Select user
3. Click **Reset Password**
4. Set temporary password
5. User must change on next login

### Role Management

| Role | Certificates | CAs | Users | Settings |
|------|--------------|-----|-------|----------|
| Admin | Full | Full | Full | Full |
| Operator | Full | Full | Read | Read |
| Viewer | Read | Read | None | None |

### API Keys

Users can create API keys for automation:
1. Go to **Account** > **API Keys**
2. Click **Generate Key**
3. Copy key (shown only once)
4. Use in `X-API-Key` header

---

## Monitoring

### Health Check

```bash
curl -k https://localhost:8443/api/health
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

## Upgrades

See [UPGRADE.md](../UPGRADE.md) for version-specific migration steps.

---

## Troubleshooting

### Service Won't Start

```bash
# Check logs
sudo journalctl -u ucm -n 100

# Check permissions
ls -la /opt/ucm/data/
sudo chown -R ucm:ucm /opt/ucm/data/

# Check port
sudo netstat -tlpn | grep 8443
```

### Database Locked

```bash
# Find locking process
fuser /opt/ucm/data/ucm.db

# Stop service and fix
sudo systemctl stop ucm
sqlite3 /opt/ucm/data/ucm.db "PRAGMA integrity_check;"
sudo systemctl start ucm
```

---

## References

- [User Guide](USER_GUIDE.md)
- [API Reference](API_REFERENCE.md)
- [Installation](installation/README.md)
- [Changelog](../CHANGELOG.md)
