# UCM Admin Guide

Administration and configuration guide for Ultimate Certificate Manager.

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

### mTLS Certificate Management

mTLS client certificates can be enrolled from the **Account → mTLS** tab. Once enrolled, certificates are fully managed by UCM:

- **User Certificates page** (`/user-certificates`) — Dedicated page to list, export, revoke, and delete all mTLS client certificates
- **Export** — Download as PEM (with key and chain) or PKCS12 (password-protected)
- **Revoke** — Revoke with reason (key compromise, superseded, etc.)
- **RBAC** — Viewers see only their own certificates; operators and admins see all

### Single Sign-On (SSO)

Configure SSO under **Settings → SSO**. UCM supports three SSO providers:

**LDAP / Active Directory:**
- Server URL, bind DN, search base, user/group filters
- Group-to-role mapping (map AD groups to UCM roles)
- Test connection before saving

**OAuth2 (Azure AD, Google, GitHub):**
- Client ID, Client Secret, Authorization/Token/UserInfo URLs
- Callback URL: `https://your-server:8443/api/v2/auth/sso/oauth2/callback`
- Role claim mapping from token attributes

**SAML 2.0:**
- IdP Metadata URL or manual XML upload
- Entity ID, ACS URL, certificate configuration
- Attribute mapping for username, email, roles

**Important:** After configuring SSO, test with a non-admin account first. Keep at least one local admin account as fallback.

---

## Email Notifications

### SMTP Configuration

Configure SMTP settings under **Settings → Email** to enable email notifications:

- **SMTP Host/Port** — Mail server address and port
- **Credentials** — Username and password (if required)
- **Encryption** — None, STARTTLS, or SSL/TLS
- **From Address** — Sender email for all notifications
- **Content Type** — HTML, Plain Text, or Both
- **Alert Recipients** — One or more email addresses for expiry alerts

Use the **Test** button to send a test email and verify connectivity.

### Email Template Editor

Customize the notification email template via the built-in editor:

1. Navigate to **Settings → Email → Email Template**
2. Click **Edit Template** to open the floating editor window
3. Switch between **HTML** and **Plain Text** tabs
4. Edit the template source on the left, see the live preview on the right
5. Available variables: `{{title}}`, `{{content}}`, `{{datetime}}`, `{{instance_url}}`, `{{logo}}`, `{{title_color}}`
6. Click **Save** to apply, or **Reset to Default** to restore the UCM default template

### Expiry Alerts

When SMTP is configured, enable automatic certificate expiry alerts:

- Toggle notifications on/off
- Select warning thresholds (90, 60, 30, 14, 7, 3, 1 days before expiry)
- **Check Now** triggers an immediate scan of all certificates

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

### EST Administration

EST (RFC 7030) is configured under **Operations → EST**:

1. **Enable EST** and select the issuing CA
2. **Authentication** — Configure client authentication (HTTP Basic or TLS mutual auth)
3. **Endpoint** — `https://your-server:8443/.well-known/est/`
4. **Operations** — Simple enroll, re-enroll, CA certs distribution
5. Monitor EST requests in the Operations page

### Discovery Administration

Configure certificate discovery under **Operations → Discovery**:

1. **Scan Profiles** — Create profiles with target hosts/CIDR ranges, port lists, and scan options
2. **Scheduling** — Enable scheduled scans with configurable intervals
3. **Results** — View discovered certificates, filter by status, expiry, issuer
4. **Quick Scan** — One-off scans without creating a profile
5. **SNI support** — Enable SNI for virtual host scanning

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
| Auditor | Read | Read | None | None |
| Viewer | Read (limited) | Read | None | None |

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
# Or remotely: curl -k https://your-server-fqdn:8443/api/health
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

## Report Scheduler

UCM includes a full report scheduler that can automatically generate and email reports on a recurring basis.

> **Prerequisite:** Email delivery must be configured first. Go to **Settings** > **Email** and configure your SMTP server before enabling scheduled reports.

### Available Report Types

| Report Type | Description |
|-------------|-------------|
| `expiring_certificates` | Certificates expiring within N days |
| `revoked_certificates` | All revoked certificates with reason and date |
| `ca_hierarchy` | CA tree with issued certificate counts |
| `audit_summary` | Audit log activity grouped by action type |
| `compliance_status` | Policy compliance across all certificates |
| `certificate_inventory` | Full certificate inventory with metadata |

### Configuring a Schedule

1. Go to **Reports** page
2. Click the **schedule icon** next to any report type
3. Configure:
   - **Enabled** — Toggle schedule on/off
   - **Frequency** — `daily`, `weekly`, or `monthly`
   - **Time** — Execution time in `HH:MM` format (24-hour, server timezone)
   - **Day of Week** — For weekly: `0` (Monday) through `6` (Sunday)
   - **Day of Month** — For monthly: `1` through `28`
   - **Format** — Output format: `csv`, `json`, or `pdf`
   - **Recipients** — Email addresses to receive the report (max 50)
4. Click **Save**

### Example Schedule Configuration

A weekly expiring certificates report sent every Monday at 8 AM:

```
Report Type: Expiring Certificates
Frequency:   Weekly
Time:        08:00
Day of Week: Monday
Format:      CSV
Recipients:  admin@example.com, security@example.com
```

### Testing Scheduled Reports

Before relying on a schedule, send a test report:

1. Configure the schedule as desired
2. Click **Send Test** on the report row
3. A one-time report is generated and emailed to all configured recipients
4. Verify the email arrives and the content is correct

### Troubleshooting Schedules

- **Reports not sending** — Check SMTP configuration in Settings > Email
- **Empty reports** — Verify the report type has data (e.g., no expiring certs if all are valid)
- **Wrong timezone** — Report time uses server timezone; check system clock
- **Recipient limit** — Maximum 50 email addresses per report schedule

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
