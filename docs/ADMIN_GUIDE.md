# UCM Admin Guide

Administration and configuration guide for Ultimate Certificate Manager.

---

## Configuration Overview

UCM stores data in:
- **Database** -- `/opt/ucm/data/ucm.db` (SQLite, default) or PostgreSQL via `DATABASE_URL`
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
| `DATABASE_URL` | (unset → SQLite) | SQLAlchemy URL. Set to `postgresql://user:pass@host:5432/dbname` to use PostgreSQL. When unset, UCM uses SQLite at `UCM_DATA_DIR/ucm.db`. |

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

#### Filesystem permissions (since v2.142)

UCM enforces `0o700` on its session directory at boot. If the directory is group- or world-readable, the service refuses to start:

```
RuntimeError: Refusing to boot: session dir <path> has perms 0o755, expected 0o700
```

Default paths:

| Install method | Path |
|----------------|------|
| DEB / RPM (systemd) | `/var/lib/ucm/sessions/` |
| Source / `/opt/ucm` | `/opt/ucm/data/sessions/` |
| Docker | `/app/data/sessions/` (inside container) |

DEB/RPM post-install scripts and the Docker entrypoint already set the right perms. After a manual `cp -r` or migration that lost ownership:

```bash
sudo chown -R ucm:ucm /var/lib/ucm/sessions
sudo chmod 0700 /var/lib/ucm/sessions
sudo systemctl restart ucm
```

The same recommendation applies to any directory holding TLS keys or HSM PINs (`/etc/ucm/`, `/var/lib/ucm/keys/`).

#### Reverse proxy & trusted_proxies (since v2.142)

If you terminate TLS on a reverse proxy (Nginx, Traefik, HAProxy, NPM) and forward client info to UCM via headers, declare the proxy CIDR(s) in **Settings → Security → Trusted proxies**:

```
security.trusted_proxies = 10.0.0.5/32, 192.168.10.0/24
```

This affects:

- **Audit log IP** — `X-Forwarded-For` is honoured **only** when the request comes from a trusted CIDR; otherwise the direct `remote_addr` is used. Spoofed XFF from untrusted networks is ignored.
- **mTLS / EST / SCEP** — proxy-injected `X-SSL-Client-*` headers are only accepted from trusted CIDRs. Direct deployments (UCM terminates TLS itself) are unaffected.

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

UCM supports two database backends:

- **SQLite** (default) — zero-config, file-based, suitable for single-node deployments
- **PostgreSQL 13+** — recommended for high availability, multi-instance, or when you already operate a managed PG cluster

The active backend is selected by the `DATABASE_URL` environment variable (or `/etc/ucm/ucm.env` on DEB/RPM):

- **Unset** → SQLite at `UCM_DATA_DIR/ucm.db`
- **`postgresql://user:pass@host:5432/dbname`** → PostgreSQL

### Switching Backend (UI)

**Settings → Database** shows the current backend, size, table count, and exposes:

- **Test connection** — validate a `DATABASE_URL` before switching
- **Switch backend** — persist `DATABASE_URL` to `/etc/ucm/ucm.env` and restart (DEB/RPM)
- **Migrate data** — copy all rows from the current backend to the target, then restart

The migration is **bidirectional** (SQLite ↔ PostgreSQL) and:

- Backs up the source first (`/opt/ucm/data/backups/db_migration/`)
- Creates the schema on the target via SQLAlchemy
- Disables FK checks during bulk load
- Intersects source/target columns (legacy columns are skipped with a warning)
- Resets PostgreSQL sequences after load

**Safety checks (fail fast, source untouched):**

- **Test connection** rejects PostgreSQL servers older than 13 (UCM minimum supported version).
- **Migrate** refuses if the target already contains UCM data (rows in `users`, `cas`, or `certificates`). Reset the target first:
  - PostgreSQL: `psql ... -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'`
  - SQLite: delete the target `.db` file
- If a migration fails mid-way, the source is untouched and a backup is available under `/opt/ucm/data/backups/db_migration/`. Reset the target before retrying.

> ⚠ Docker installs cannot persist `/etc/ucm/ucm.env` from inside the container. After running **Migrate** on Docker, the API returns the target URL — set `DATABASE_URL` in your `docker-compose.yml` or `docker run -e` and restart the container manually.

> **Admin lockout fix (v2.141).** Switching the active backend from PostgreSQL back to SQLite (or vice versa) no longer locks out the admin account. The bcrypt password hash is preserved across the swap and the in-process SQLAlchemy session pool is rebuilt before the next login attempt. Earlier releases could leave a stale connection pool pointing at the old backend, causing `Invalid credentials` on first login after the swap.

> **Backups now backend-aware (v2.141).** The **Backup** action and `/api/v2/system/backup` automatically dispatch to `pg_dump -Fc` when PostgreSQL is the active backend (custom format, suitable for `pg_restore`). SQLite continues to use file-copy snapshots. Restore handles both formats transparently.

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

### PostgreSQL Backend

UCM supports PostgreSQL 13+ as a drop-in replacement for SQLite. The schema is created automatically on first start.

**Recommended PostgreSQL setup:**
```sql
CREATE USER ucm WITH PASSWORD 'strong-password';
CREATE DATABASE ucm OWNER ucm;
GRANT ALL PRIVILEGES ON DATABASE ucm TO ucm;
```

**Activate PostgreSQL (DEB/RPM):**
```bash
echo 'DATABASE_URL=postgresql://ucm:strong-password@db.example.com:5432/ucm' | sudo tee -a /etc/ucm/ucm.env
sudo systemctl restart ucm
```

**Activate PostgreSQL (Docker):**
```yaml
# docker-compose.yml
services:
  ucm:
    image: neyslim/ultimate-ca-manager:latest
    environment:
      DATABASE_URL: postgresql://ucm:strong-password@db:5432/ucm
```

**Backup PostgreSQL:**
```bash
pg_dump -U ucm -h db.example.com ucm > ucm-pg-backup.sql
```

**Restore PostgreSQL:**
```bash
psql -U ucm -h db.example.com ucm < ucm-pg-backup.sql
```

> ℹ The `psycopg2-binary` driver is bundled with the DEB/RPM packages and the Docker image. No extra install step is needed.

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

Public CDP (HTTP, typically port 8080):

```text
http://your-server:8080/cdp/<ca_refid>.crl
http://your-server:8080/cdp/<ca_refid>-delta.crl   # when delta CRL is enabled
```

Management UI: **CA → CRL / CDP** tab (enable CDP, optional delta, regeneration interval).

### Publishing on TCP port 80

UCM is unprivileged. Prefer one of:

- **`HTTP_PROTOCOL_PORT=80`** in `/etc/ucm/ucm.env` **plus** `CAP_NET_BIND_SERVICE` on the service unit, **or**
- Keep UCM on **8080** and put a reverse proxy on **:80** (recommended).

Settings → HTTP protocol port in the GUI only allows **0** or **1024–65535**; use the environment for privileged 80. Details: [PUBLIC-ENDPOINTS.md](./testing/PUBLIC-ENDPOINTS.md) (Privileged protocol port 80).

**Regenerate via API** (requires `write:crl`):

```bash
curl -k -X POST -H "Authorization: Bearer $TOKEN" \
  https://your-server:8443/api/v2/crl/<ca_id>/regenerate
curl -k -X POST -H "Authorization: Bearer $TOKEN" \
  https://your-server:8443/api/v2/crl/<ca_id>/delta/regenerate
```

#### RFC 5280 profile (what UCM puts on the wire)

| Extension / rule | Behaviour | RFC |
|------------------|-----------|-----|
| **Authority Key Identifier** | Identifies the **signing CA key**: SKI of the issuing CA certificate (fallback: hash of the CA public key if SKI is absent). **Not** a copy of the CA certificate's own AKI (that points at the parent for intermediates). | §5.2.1 (#202) |
| **CRL Number** | Monotonic, non-critical; full and delta CRLs share one number sequence | §5.2.3 |
| **Delta CRL Indicator** | Critical on delta CRLs; `BaseCRLNumber` = last complete CRL | §5.2.4 |
| **Freshest CRL** | Non-critical on complete CRLs when delta+CDP are configured; points at the delta CDP URL | §5.2.6 |
| **Serials** | Entries with serials >159 bits are **skipped** (logged); no silent truncation | §4.1.2.2 |
| **Offline CA** | Cannot regenerate while `ca.offline` | ops |

**Intermediate CAs:** clients that match `CRL.AKI` to the intermediate's SKI will reject a CRL that incorrectly carried the parent's key id. After #202, regenerate CRLs for intermediates so published CDP objects pick up the corrected AKI.

**Verify with OpenSSL** (after fetching PEM from `GET /api/v2/crl/<ca_id>` or CDP):

```bash
openssl crl -in ca.crl -inform PEM -text -noout | grep -A2 'Authority Key Identifier'
openssl x509 -in intermediate.pem -noout -text | grep -A1 'Subject Key Identifier'
# keyIdentifier bytes must match the intermediate SKI, not the parent
```

**Since #204:** IDP omitted on both full and delta (§5.2.4 parity), FreshestCRL guarded when CDP is missing, and `reasonCode` hygiene (`unspecified` omitted; `removeFromCRL` on delta only).

**RFC 5280 profile (issuing CA + CRL):**
- CRL **Authority Key Identifier** identifies the **signing CA** Subject Key Identifier (§5.2.1).
- Base and delta CRLs both **omit** IssuingDistributionPoint (§5.2.4).
- **FreshestCRL** points at the delta URL when CDP + delta CRL are enabled (§5.2.6).
- Reason `unspecified` is omitted; `removeFromCRL` appears only on delta CRLs (§5.3.1).
- Optional revoke field **`invalidity_date`** is emitted as CRL entry `invalidityDate` (§5.3.2).
- Lifting a **certificateHold** (unhold) regenerates the full CRL; with delta CRL enabled, UCM first emits a delta entry with reason `removeFromCRL`.

**Certificate issuance profile:**
- CSR-supplied SKI/AKI extensions are **ignored**; SKI comes from the subject public key and AKI from the issuing CA’s SKI.
- Intermediate CAs inherit parent **AIA caIssuers** (and OCSP) when the parent has AIA/OCSP configured.

Lab scripts (repo root):
- `python3 scripts/lab_crl_openssl_verify.py`
- `python3 scripts/lab_rfc5280_cert_crl_profile.py`

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

### ACME client accounts — `preferred_chain` (RFC 8555 alternate chains)

UCM can select an *alternate* chain advertised by the CA via `Link: rel="alternate"` (RFC 8555 §7.4.2). This choice is driven by the `preferred_chain` field on **ACME client accounts**.

**What to put in `preferred_chain`**
- The **trust anchor CN** at the bottom of the target chain (e.g. `ISRG Root X1` for Let's Encrypt gen-Y).
- **Case-insensitive** comparison on the **last certificate's CN** in the PEM: match on **subject CN** *or* **issuer CN** (useful when the CA "shortens" the chain and **omits the root**).

**Constraints / semantics**
- Maximum length: **255** characters.
- Empty value (`""`) or unset: UCM keeps the CA's **default** chain (unchanged behavior).

**Scope (client + proxy)**
- The same registry (`AcmeClientAccount`) backs both the ACME client and the **ACME proxy**.

**API (example)**
- Update via `PATCH /api/v2/acme/client/accounts/<id>` (requires `write:acme`):
```bash
curl -k -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"preferred_chain":"ISRG Root X1"}' \
  https://localhost:8443/api/v2/acme/client/accounts/<id>
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
