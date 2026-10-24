# UCM Admin Guide

Administration and configuration guide for Ultimate Certificate Manager.

---

## Configuration Overview

UCM stores data in:
- **Database** -- `/opt/ucm/data/ucm.db` (SQLite, default) or PostgreSQL via `DATABASE_URL`
- **Data Directory** -- `/opt/ucm/data/` (certificates, keys, backups)
- **Config** -- `/etc/ucm/ucm.env` (DEB/RPM) or environment variables (Docker)
- **Logs** -- `/var/log/ucm/` (DEB/RPM), or stdout plus `/opt/ucm/data/ucm.log` (Docker)

---

## Server Configuration

### Environment Variables

Native installs (DEB/RPM) read `/etc/ucm/ucm.env`; the Docker image reads the `UCM_*` names and writes that file itself.

| ucm.env (DEB/RPM) | Docker | Default | Description |
|-------------------|--------|---------|-------------|
| `SECRET_KEY` | `UCM_SECRET_KEY` | (generated) | Session signing key |
| `HOST` | `HOST` | `0.0.0.0` | Listen address for HTTPS and the HTTP protocol port; `::` = IPv6 + IPv4 (dual-stack) |
| `HTTPS_PORT` | `UCM_HTTPS_PORT` | `8443` | HTTPS port |
| `DATA_DIR` | (fixed) | `/opt/ucm/data` | Data storage |
| `LOG_LEVEL` | `UCM_LOG_LEVEL` | `INFO` | Logging verbosity |
| `UCM_LOG_FILE` | `UCM_LOG_FILE` | `/var/log/ucm/ucm.log` | Application log file (native installs). Falls back to `DATA_DIR/ucm.log` when it cannot be opened |
| `UCM_LOG_MAX_BYTES` | `UCM_LOG_MAX_BYTES` | `10485760` | Size at which `ucm.log` is rotated by the application (10 MB) |
| `UCM_LOG_BACKUPS` | `UCM_LOG_BACKUPS` | `5` | Generations of `ucm.log` kept |
| `HTTPS_CERT_PATH` | `UCM_HTTPS_CERT` | (auto) | Server certificate: a file path natively, the PEM itself in Docker |
| `HTTPS_KEY_PATH` | `UCM_HTTPS_KEY` | (auto) | Server private key: a file path natively, the PEM itself in Docker |
| `DATABASE_URL` | `DATABASE_URL` | (unset → SQLite) | SQLAlchemy URL. Set to `postgresql://user:pass@host:5432/dbname` to use PostgreSQL. When unset, UCM uses SQLite at `DATA_DIR/ucm.db`. |
| `UCM_ADMIN_ALLOWED_NETWORKS` | `UCM_ADMIN_ALLOWED_NETWORKS` | (unset) | Comma-separated IP addresses or CIDR networks allowed to reach the web interface and the management API. When set, it wins over the setting in Settings > Security, which becomes read-only. See [Admin access allowlist](#admin-access-allowlist) |
| `UCM_ADMIN_ALLOWLIST_DISABLE` | `UCM_ADMIN_ALLOWLIST_DISABLE` | (unset) | `1` turns the admin access allowlist off (recovery after a lock-out); a warning is logged at startup |

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

The gunicorn access and error logs are rotated by logrotate, from a file the
Debian package and the RPM install:
- Location: `/etc/logrotate.d/ucm`
- Rotation: Daily, 14 copies kept
- Compression: gzip

The application log, `ucm.log`, is rotated by the application itself, ten
megabytes over five generations, on every kind of install. `UCM_LOG_MAX_BYTES`
and `UCM_LOG_BACKUPS` change those two numbers.

A container keeps writing everything to standard output, so `docker logs` is
unchanged, and also writes the same lines to `/opt/ucm/data/ucm.log` inside the
data volume. That file is what **System Logs** and the diagnostic bundle read
back, and it is why log history now survives the container.

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

- **Audit log IP**: `X-Forwarded-For` is honoured **only** when the request comes from a trusted CIDR; otherwise the direct `remote_addr` is used. Spoofed XFF from untrusted networks is ignored.
- **mTLS / EST / SCEP**: proxy-injected `X-SSL-Client-*` headers are only accepted from trusted CIDRs. Direct deployments (UCM terminates TLS itself) are unaffected.

#### Admin access allowlist

**Settings > Security > Admin access allowlist** restricts the web interface and the management API to a list of IPv4/IPv6 addresses and CIDR networks (one per line, up to 100). An empty list restricts nothing. IPv4 and IPv6 are listed separately: `0.0.0.0/0` does not admit an IPv6 client, and `::/0` does not admit an IPv4 client.

- **Blocked from other addresses**: the web interface and its assets, the login, every `/api/v2/...` call (API keys included), the API docs and the WebSocket channel. API calls get a `403` JSON error, the interface a plain `403` page.
- **Never blocked**: the PKI protocol endpoints (ACME and the ACME proxy, SCEP including `/cgi-bin/pkiclient.exe`, EST, OCSP, CRL and AIA under `/cdp` and `/ca`, TSA, XCEP/WSTEP, the SSH setup script) and the health and metrics endpoints, so devices and probes outside the list keep working. The session check `/api/v2/auth/verify` answers `200` and says in its body whether the caller is authenticated; for a refused client it answers `"authenticated": false` when the request comes from a proxy listed in `UCM_TRUSTED_PROXIES` (loopback by default), and `403` otherwise.
- **No lock-out from the screen**: the section shows the address the server sees for you, and a list that does not include it is refused. Each change is written to the audit log; refused requests are logged as warnings, once per address every few minutes.
- **Environment variable**: `UCM_ADMIN_ALLOWED_NETWORKS=10.20.0.0/24,2001:db8:20::/64` wins over the stored list and makes the field read-only. An entry that is not a valid address or network is ignored with a warning; a variable with no valid entry admits nobody. A backup restored meanwhile keeps its list in the database without applying it: that list takes over once the variable is removed.
- **Recovery**: if you are locked out, set `UCM_ADMIN_ALLOWLIST_DISABLE=1` in `/etc/ucm/ucm.env` (or the container environment) and restart UCM, fix the list, then remove the variable and restart again. While the variable is set, the list is saved even if it does not include your own address.
- **Restore**: a backup whose list would not admit the client restoring it (or holds no valid entry) comes back with an empty list, with a warning in the log, an audit entry and a note in the restore message. A restore run outside an HTTP request always empties a non-empty list. While `UCM_ADMIN_ALLOWLIST_DISABLE=1` is set, the restored list is kept as is.

The check uses the address of the TCP peer, or the client address resolved from `X-Forwarded-For` when the request comes from a proxy listed in `UCM_TRUSTED_PROXIES` (loopback by default) with `UCM_BEHIND_PROXY=1`. It never trusts the header from anyone else.

Recommended patterns:

| Setup | What to list |
|-------|--------------|
| Management VLAN | The management subnet, e.g. `10.20.0.0/24` |
| Bastion / jump host | The bastion address only |
| VPN | The VPN client pool, e.g. `10.8.0.0/24` |
| Reverse proxy | The client networks, **and** set `UCM_BEHIND_PROXY=1` plus `UCM_TRUSTED_PROXIES` to the proxy address. Without them every request appears to come from the proxy, and listing the proxy address would admit everyone who can reach it |

**Docker and Kubernetes**: with a port published in bridge mode and no proxy in front, UCM may see the address after Docker's NAT (often the bridge gateway, such as `172.17.0.1`) rather than the real client. Check the address shown in the section before saving; use host networking, or a reverse proxy declared in `UCM_TRUSTED_PROXIES`, to keep real client addresses. On Kubernetes, behind an ingress controller, set the chart's `proxy.behindProxy` and `proxy.trustedProxies` (the controller's pod network), and pass `UCM_ADMIN_ALLOWED_NETWORKS` through `extraEnv` if you want it fixed by the deployment. The health probes are exempt, so liveness and readiness checks keep working.

This is an application-level filter: it does not replace a firewall in front of the HTTPS port.

### Authentication Methods

Enable/disable in **Settings** > **Security**:

- **Password** -- Standard username/password
- **2FA TOTP** -- Time-based one-time password
- **WebAuthn** -- Hardware security keys
- **mTLS** -- Client certificate authentication

### mTLS Certificate Management

mTLS client certificates can be enrolled from the **Account → mTLS** tab. Once enrolled, certificates are fully managed by UCM:

- **User Certificates page** (`/user-certificates`): Dedicated page to list, export, revoke, and delete all mTLS client certificates
- **Export**: Download as PEM (with key and chain) or PKCS12 (password-protected)
- **Revoke**: Revoke with reason (key compromise, superseded, etc.)
- **RBAC**: Viewers see only their own certificates; operators and admins see all

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
- Responses are validated strictly: signature (SHA-256 or stronger), issuer, audience (the SP entity ID `https://your-server:8443/api/v2/sso`), Destination and Recipient (the ACS URL), validity window (five minutes of clock skew) and InResponseTo of the login started in the same browser; each assertion is accepted once. These URLs come from the admin Base URL (Settings > General), else from the `FQDN` setting, and only when neither is set from the address the request arrived with; set the Base URL, especially behind a reverse proxy, and compare them with `/api/v2/sso/saml/metadata`. Serve UCM on a host name of its own: the login is tied to the browser by a cookie, which a sibling site under the same parent domain could set.
- *Allow IdP-initiated login* accepts logins started from the IdP portal; such a response is checked like any other but cannot be tied to the browser. Providers that existed before this option keep it on, new providers have it off: turn it on only if users start from the IdP portal.
- *Sign authentication requests* signs each AuthnRequest with the key of the SP certificate (the HTTPS certificate or one held by UCM, RSA only); register that certificate at the IdP from the SP metadata first.
- *NameID format* is asked of the IdP in each request and published in the metadata; *persistent* gives UCM a stable identifier, a transient NameID is never used to recognise the account.

**Role mapping resolution:** when a user belongs to several groups that each match a mapping entry, the highest-privilege role wins (`admin` > `operator` > `auditor` > `viewer`); the order of the entries does not matter. This lets you map a broad access group to a low role and grant higher privileges through narrower groups. Users with no matching entry get the provider's default role at account creation; on later logins their stored role is kept unless *Sync role on each login* is enabled.

**Important:** After configuring SSO, test with a non-admin account first. Keep at least one local admin account as fallback.

---

## Email Notifications

### SMTP Configuration

Configure SMTP settings under **Settings → Email** to enable email notifications:

- **SMTP Host/Port**: Mail server address and port
- **Credentials**: Username and password (if required)
- **Encryption**: None, STARTTLS, or SSL/TLS
- **From Address**: Sender email for all notifications
- **Content Type**: HTML, Plain Text, or Both
- **Alert Recipients**: One or more email addresses for expiry alerts

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

- **SQLite** (default): zero-config, file-based, suitable for single-node deployments
- **PostgreSQL 13+**: recommended for high availability, multi-instance, or when you already operate a managed PG cluster

The active backend is selected by the `DATABASE_URL` environment variable (or `/etc/ucm/ucm.env` on DEB/RPM):

- **Unset** → SQLite at `DATA_DIR/ucm.db`
- **`postgresql://user:pass@host:5432/dbname`** → PostgreSQL

### Switching Backend (UI)

**Settings → Database** shows the current backend, size, table count, and exposes:

- **Test connection**: validate a `DATABASE_URL` before switching
- **Switch backend**: persist `DATABASE_URL` to `/etc/ucm/ucm.env` and restart (DEB/RPM)
- **Migrate data**: copy all rows from the current backend to the target, then restart

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

> ⚠ Docker installs cannot persist `/etc/ucm/ucm.env` from inside the container. After running **Migrate** on Docker, the API returns the target URL: set `DATABASE_URL` in your `docker-compose.yml` or `docker run -e` and restart the container manually.

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

**Named URLs (opt-in, per CA):** when a CA is created with *Use CA name in
protocol URLs* (Advanced), CDP/AIA paths use an immutable slug derived from the
CA name (`/cdp/my-issuing-ca.crl`) instead of the random id: easier to
configure manually in relying products. Both forms always resolve; the slug
cannot be changed after creation and reveals the CA name in URLs.

Management UI: **CA → CRL / CDP** tab (enable CDP, optional delta, regeneration interval).

#### Serving protocol endpoints on port 80

CDP/OCSP/AIA clients often expect plain HTTP on port **80**. UCM runs
unprivileged, so it cannot bind ports below 1024 by itself. Three options:

1. **Systemd capability**: let the service bind 80 directly:

   ```bash
   # /etc/ucm/ucm.env
   HTTP_PROTOCOL_PORT=80
   ```

   ```bash
   sudo systemctl edit ucm
   # add:
   # [Service]
   # AmbientCapabilities=CAP_NET_BIND_SERVICE
   sudo systemctl restart ucm
   ```

2. **Reverse proxy**: keep UCM on 8080 and forward `:80 → :8080` for the
   protocol paths (`/cdp/`, `/ocsp`, `/aia/`) with nginx/HAProxy/Caddy.

3. **Docker**: map the port at run time: `-p 80:8080`.

Whichever option you pick, set the CDP/OCSP/AIA URLs on the CA so issued
certificates embed the port-80 form of the URL.

**Regenerate via API** (requires `write:crl`):

```bash
curl -k -X POST -H "Authorization: Bearer $UCM_API_KEY" \
  https://your-server:8443/api/v2/crl/<ca_id>/regenerate
curl -k -X POST -H "Authorization: Bearer $UCM_API_KEY" \
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

### ACME client: HTTP-01 challenges

UCM serves the HTTP-01 file of its own pending orders at
`/.well-known/acme-challenge/<token>`, on the HTTP protocol port (8080 by
default) as well as on HTTPS. The CA always fetches it on port **80** of the
domain being certified, so make that path reach UCM:

- **Reverse proxy** in front of the domain: forward `/.well-known/acme-challenge/`
  to `http://<ucm-host>:8080`.
- **Port 80 on UCM itself**: same options as for CDP/OCSP above (systemd
  capability, or `-p 80:8080` with Docker).

Before submitting a challenge, UCM fetches the URL itself and refuses to submit
when the file is not served; *Force verification* bypasses this check when
UCM's view of the domain differs from the CA's (split-horizon DNS). Automatic
renewal of an HTTP-01 order relies on this hosting: when the URL does not
answer, the new order is left pending with the reason (the next attempt reuses
it), and the failure is recorded in the audit log.

### ACME DNS-01 resolvers

**ACME → Let's Encrypt → DNS-01 resolvers** chooses where UCM looks up
`_acme-challenge` TXT records, for the client, the proxy and the ACME server:

| Mode | Resolvers queried |
|------|-------------------|
| Automatic (default) | listed resolvers, then the zone's authoritative servers, then 9.9.9.9 / 8.8.8.8 / 1.1.1.1, then the system resolver |
| System resolver only | `/etc/resolv.conf` |
| Listed resolvers only | the list below |

Use a restricted mode when outbound DNS to public resolvers is blocked; the
public-endpoints preflight then skips its public DNS check as well. Entries
are comma-separated IPs with an optional port: `10.0.0.53, 127.0.0.1:5353,
[2001:db8::53]:5300`. API: `dns01_resolver_mode` and `dns01_nameservers` on
`PATCH /api/v2/acme/client/settings`.

### ACME client accounts: `preferred_chain` (RFC 8555 alternate chains)

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
curl -k -X PATCH -H "Authorization: Bearer $UCM_API_KEY" -H "Content-Type: application/json" \
  -d '{"preferred_chain":"ISRG Root X1"}' \
  https://localhost:8443/api/v2/acme/client/accounts/<id>
```

### ACME proxy: DNS UPDATE listener (RFC 2136)

**Purpose.** DNS-01 clients such as cert-manager, lego, certbot, acme.sh, win-acme and Posh-ACME can use the ACME proxy without a DNS API token of their own. They send a TSIG-signed DNS UPDATE (RFC 2136) to UCM. UCM checks the TXT value against the pending proxy order. Per-client settings are in [integrations/acme-proxy-dns-update.md](integrations/acme-proxy-dns-update.md).

> **Internal network only.** The listener answers unsigned SOA queries for names of pending orders. Put it on an internal network or a private address. Never publish it to the internet. Use `UCM_DNS_UPDATE_HOST` and a firewall (or the Helm `dnsUpdate.networkPolicy`) to limit who can reach it.

**Enable it.** The listener is **off by default**. A restart is needed after every change.

| Method | Value |
|--------|-------|
| Environment variable | `UCM_DNS_UPDATE_PORT=8053` (`/etc/ucm/ucm.env` natively, container environment in Docker). It wins over the setting. An empty value counts as not set. A value outside 0 to 65535 turns the listener off, with a warning in the log |
| Setting | `acme.proxy.dns_update_port`, API field `dns_update_port` of `PATCH /api/v2/acme/client/settings` |
| Off | unset, or `0` |

The port is 1024 to 65535. It cannot be the HTTPS port, the HTTP protocol port or the TLS-ALPN-01 port of the ACME client. UCM serves UDP and TCP on the same port. `GET /api/v2/acme/client/settings` shows `dns_update_listening` (`true` when the listener runs) and `dns_update_port_effective` (the port the next start uses).

**Bind address.** By default the listener uses the same address as the HTTP protocol port (`HOST`). Set `UCM_DNS_UPDATE_HOST` to bind it to one internal address only.

**Port 53.** DNS clients use port 53 by default. UCM runs without the right to bind port 53, so keep a high port (8053 is the suggestion) and map port 53 to it. The DEB and RPM service units are not changed.

| Deployment | How to map port 53 |
|------------|--------------------|
| Docker | `-p 53:8053/udp -p 53:8053/tcp` and `-e UCM_DNS_UPDATE_PORT=8053`. The image exposes `8053/udp` and `8053/tcp`. The entrypoint refuses a port below 1024 |
| Kubernetes | Helm `dnsUpdate.enabled=true`. The chart creates the separate Service `<fullname>-dns-update` (port 53 to container port 8053; `ucm-dns-update` for the release `ucm`). See the [chart README](../charts/ucm/README.md) |
| DEB, RPM | A firewall redirect on the UCM host, both protocols |

```bash
iptables -t nat -A PREROUTING -p udp --dport 53 -j REDIRECT --to-port 8053
iptables -t nat -A PREROUTING -p tcp --dport 53 -j REDIRECT --to-port 8053
```

Clients on the UCM host itself need the same rules in the `OUTPUT` chain. With nftables or firewalld, use an equivalent redirect. Some clients can send only to port 53 (win-acme), so map the port for them.

**Keys.** A TSIG key belongs to one ACME proxy account. There is no global key.

- Create a key with `POST /api/v2/acme/client/accounts/<id>/dns-update-keys` (also in the web interface). UCM shows the secret **once**. It stores the secret encrypted and cannot show it again.
- The default algorithm is `hmac-sha256`. `hmac-sha384` and `hmac-sha512` are possible.
- Revoke a key with `DELETE .../dns-update-keys/<key_id>`. A revoked key stops working at once (BADKEY). Another `DELETE` removes it. Deleting an ACME proxy account removes its keys.
- Optional link to an EAB credential (`eab_credential_id`). The key then accepts only values for orders of the ACME account that registered with that credential, so the credential must be used already. A key without the link accepts values for all orders of its proxy account. Revoking the EAB credential revokes the keys linked to it, and deleting the credential deletes them. The audit log has an entry for each key.
- `last_used_at` of a key shows when it last sent an accepted update.

**What the listener accepts and answers.**

- An UPDATE must be signed (TSIG). An unsigned UPDATE gets `REFUSED`.
- An update adds only a TXT record at `_acme-challenge.<name>`, with the exact value that UCM expects for a pending proxy order of the key's scope. The name must be in a zone that matches an entry in ACME Domains, or in a parent of one.
- Deletes (one record, or the whole TXT set of a name) always get `NOERROR`, also when the order is gone. A delete changes nothing.
- A message with prerequisites gets `REFUSED`.
- **The listener writes nothing to DNS.** UCM still publishes the challenge record through its DNS provider, as for every proxy order. The update only proves that the client holds the right value.
- It answers SOA queries for the zone of a pending order and for the names between that zone and the challenge name (the zone is the ACME Domains entry for the name). Unsigned and signed SOA queries are answered. A signed query gets a signed answer. The SOA record has fixed values and no host name.
- It refuses every other query (`REFUSED`). It does not recurse and does not serve any other data.
- Over UDP, an answer to a request without a valid signature is never larger than the request. Larger answers are cut (TC) or dropped. A signed request gets a normal DNS answer size. TCP has no such limit.
- Messages larger than 4096 bytes are ignored. The listener also limits the packet rate and the TCP connections, in total and per source (one IPv4 address, or one IPv6 /64 network). Behind NAT or kube-proxy SNAT, many clients can share one source address and one limit.

**Algorithms and time.** UCM accepts only `hmac-sha256`, `hmac-sha384` and `hmac-sha512`. The default algorithm of many clients is `hmac-md5` or `hmac-sha1`. UCM refuses them with `BADKEY`, so always set the algorithm in the client. The clock of the client must be within 300 seconds of the UCM clock, or UCM answers `BADTIME`. UCM also answers `BADTIME` to a request of a key that was signed earlier than the last request it accepted from that key (RFC 8945 §5.2.3, protection against replay). A retransmission of an answered request still gets its first answer.

**Audit log.** Accepted updates, and signed refusals (wrong key, wrong signature, wrong time, wrong value), are written to the audit log (actions `acme.dns_update.accepted`, `acme.dns_update.refused`, `acme.dns_update.rejected`). Unsigned and malformed packets are only written to the application log, sampled. To keep the log usable during a flood, the listener writes at most 120 accepted entries per key per minute, and at most one refusal entry per source address and cause per minute (20 per cause in total). It counts the entries it leaves out and writes the count in one `acme.dns_update.suppressed` entry.

**Troubleshooting.** The client output shows the DNS result code.

| Code | Meaning | What to check |
|------|---------|---------------|
| `BADKEY` | UCM does not know the key, or the key is not usable | Key name (with the trailing dot in some clients), key revoked, proxy account disabled, algorithm refused (`hmac-md5`, `hmac-sha1`: set `hmac-sha256`) |
| `BADSIG` | The signature does not match | Wrong secret (copy it again from the creation dialog), secret not base64, a different algorithm than the key has. win-acme with `hmac-sha384` signs wrongly: use `hmac-sha256` |
| `BADTIME` | The client clock is more than 300 s away from UCM, or the request was signed earlier than the last accepted request of the same key | Synchronize the time (NTP) on the client and on UCM. If the clocks are correct: several clients share one key, or parallel requests arrived out of order. Give each client its own key; the client normally retries |
| `REFUSED` | The request is understood but not allowed | Unsigned UPDATE; value does not match the pending order (new order, new value); no pending order for that name (the client must fetch the authorization first); name is not `_acme-challenge.<name>`; record type is not TXT; the message has prerequisites; for a query, the name is not covered by a pending order |
| `NOTAUTH` | The zone is not served | The domain (or a parent) is not in ACME Domains |
| `NOTZONE` | A name in the update is outside the zone of the message | The client sent a zone and a record name that do not fit |

If the client times out and gets no answer, check the port mapping, the firewall, `dns_update_listening`, and that the client uses UDP and TCP on the right port. UCM does not answer a packet that is shorter than a DNS header, larger than 4096 bytes, has too many records, or is itself a response.

The client message can differ from the name of the code:

- A TSIG error (`BADKEY`, `BADSIG`, `BADTIME`) has the code `NOTAUTH` in the message header and the TSIG error in the TSIG record (RFC 8945). A zone that is not in ACME Domains also gives `NOTAUTH`. cert-manager and lego use the Go library `miekg/dns`, which shows all of these as `bad authentication`. Use the audit log to find the cause: a TSIG error is `acme.dns_update.rejected`, a zone error is `acme.dns_update.refused` with the reason `not_authoritative`.
- `nsupdate` (acme.sh, Posh-ACME) first sends a signed SOA query. With a wrong secret, UCM answers `BADSIG`, and `nsupdate` then asks again without a signature. The final message can be `REFUSED` or `could not reach any name server`. Set the zone (`NSUPDATE_ZONE` in acme.sh, `DDNSZone` in Posh-ACME) to skip the SOA query and see `BADSIG` directly.

The audit log entry gives the cause in the field `reason` of its details:

| `reason` | Meaning |
|----------|---------|
| `badkey`, `badsig`, `badtime`, `badtrunc` | TSIG check failed (action `acme.dns_update.rejected`). A malformed TSIG record is only in the application log |
| `no_pending_order` | No pending proxy order of the key's scope expects a value for this name |
| `value_mismatch` | A pending order exists for the name, but the TXT value is different |
| `type_not_allowed` | The record is not TXT, or the name does not start with `_acme-challenge` |
| `not_authoritative` | The zone is not in ACME Domains (`NOTAUTH`) |
| `prerequisite`, `not_in_zone`, `format` | The message has prerequisites, a name outside its zone, or a malformed update section |

### SCEP Administration

View pending SCEP requests in the SCEP page, or via API:

```bash
curl -k -b cookies.txt https://localhost:8443/api/v2/scep/requests?status=pending
```

### EST Administration

EST (RFC 7030) is configured under **Operations → EST**:

1. **Enable EST** and select the issuing CA
2. **Authentication**: Configure client authentication (HTTP Basic or TLS mutual auth)
3. **Endpoint**: `https://your-server:8443/.well-known/est/`
4. **Operations**: Simple enroll, re-enroll, CA certs distribution
5. Monitor EST requests in the Operations page

### Discovery Administration

Configure certificate discovery under **Operations → Discovery**:

1. **Scan Profiles**: Create profiles with target hosts/CIDR ranges, port lists, and scan options
2. **Scheduling**: Enable scheduled scans with configurable intervals
3. **Results**: View discovered certificates, filter by status, expiry, issuer
4. **Quick Scan**: One-off scans without creating a profile
5. **SNI support**: Enable SNI for virtual host scanning

### Windows Autoenrollment (XCEP/WSTEP): Kerberos/SPNEGO

Configure under **Settings → Windows Autoenrollment**. Policy discovery (XCEP) and issuance (WSTEP) work out of the box for username/password and certificate-based binding. The **Kerberos** binding, used for silent GPO autoenrollment, needs one extra server-side dependency that is deliberately **not** installed by default: `pyspnego`'s `kerberos` extra pulls in `gssapi`, a C extension that requires the system's Kerberos development headers to build. Installing it by default would break `pip install -r requirements.txt` on hosts without a compiler or `libkrb5-dev`, so it's opt-in.

If the Kerberos section shows "Kerberos library not available", install the extra in the same Python environment UCM runs in, then restart the service:

```bash
# Debian/Ubuntu
apt-get install -y libkrb5-dev build-essential python3-dev
pip install pyspnego[kerberos]

# RHEL/Rocky/Alma
dnf install -y krb5-devel gcc python3-devel
pip install pyspnego[kerberos]
```

For a DEB/RPM install, run `pip install` inside `/opt/ucm/venv` (e.g. `/opt/ucm/venv/bin/pip install pyspnego[kerberos]`) as the `ucm` user. For Docker, add the same `apt-get`/`pip install` lines to a custom image built from `neyslim/ultimate-ca-manager`: the extra isn't baked into the published image either.

```bash
systemctl restart ucm
```

Once installed, `gssapi`/`spnego` are importable and the warning clears without any further configuration. This mirrors how `requests-kerberos` is handled for the MS CA WinRM/Kerberos admin channel (also excluded from the default install for the same reason).

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
4. Use in the `X-API-Key` header, or as `Authorization: Bearer <key>` (keys start with `ucm_ak_`; another bearer token, such as one an authenticating proxy relays, is ignored)

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
   - **Enabled**: Toggle schedule on/off
   - **Frequency**: `daily`, `weekly`, or `monthly`
   - **Time**: Execution time in `HH:MM` format (24-hour, server timezone)
   - **Day of Week**: For weekly: `0` (Monday) through `6` (Sunday)
   - **Day of Month**: For monthly: `1` through `28`
   - **Format**: Output format: `csv`, `json`, or `pdf`
   - **Recipients**: Email addresses to receive the report (max 50)
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

- **Reports not sending**: Check SMTP configuration in Settings > Email
- **Empty reports**: Verify the report type has data (e.g., no expiring certs if all are valid)
- **Wrong timezone**: Report time uses server timezone; check system clock
- **Recipient limit**: Maximum 50 email addresses per report schedule

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
