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
| `SECRET_KEY` | `UCM_SECRET_KEY` | (generated) | Session signing key (signs the CSRF tokens). Once rotated with encryption enabled, the key stored in the database signs and this value is only the fallback; see [Session key rotation](#session-key-rotation) |
| `HOST` | `HOST` | `0.0.0.0` | Listen address for HTTPS and the HTTP protocol port; `::` = IPv6 + IPv4 (dual-stack) |
| `HTTPS_PORT` | `UCM_HTTPS_PORT` | `8443` | HTTPS port |
| `DATA_DIR` | (fixed) | `/opt/ucm/data` | Data storage |
| `UCM_CONFIG_DIR` | `UCM_CONFIG_DIR` | `/etc/ucm` | Directory holding `ucm.env` and `master.key`. Set it in the process environment (the service unit or the shell), not in `ucm.env`, which is read from it; the packages leave it unset |
| `LOG_LEVEL` | `UCM_LOG_LEVEL` | `INFO` | Logging verbosity |
| `UCM_LOG_FILE` | `UCM_LOG_FILE` | `/var/log/ucm/ucm.log` | Application log file (native installs). Falls back to `DATA_DIR/ucm.log` when it cannot be opened |
| `UCM_LOG_MAX_BYTES` | `UCM_LOG_MAX_BYTES` | `10485760` | Size at which `ucm.log` is rotated by the application (10 MB) |
| `UCM_LOG_BACKUPS` | `UCM_LOG_BACKUPS` | `5` | Generations of `ucm.log` kept |
| `HTTPS_CERT_PATH` | `UCM_HTTPS_CERT` | (auto) | Server certificate: a file path natively, the PEM itself in Docker |
| `HTTPS_KEY_PATH` | `UCM_HTTPS_KEY` | (auto) | Server private key: a file path natively, the PEM itself in Docker |
| `DATABASE_URL` | `DATABASE_URL` | (unset → SQLite) | SQLAlchemy URL. Set to `postgresql://user:pass@host:5432/dbname` to use PostgreSQL. When unset, UCM uses SQLite at `DATA_DIR/ucm.db`. |
| `UCM_ADMIN_ALLOWED_NETWORKS` | `UCM_ADMIN_ALLOWED_NETWORKS` | (unset) | Comma-separated IP addresses or CIDR networks allowed to reach the web interface and the management API. When set, it wins over the setting in Settings > Security, which becomes read-only. See [Admin access allowlist](#admin-access-allowlist) |
| `UCM_ADMIN_ALLOWLIST_DISABLE` | `UCM_ADMIN_ALLOWLIST_DISABLE` | (unset) | `1` turns the admin access allowlist off (recovery after a lock-out); a warning is logged at startup |
| `UCM_HA` | `UCM_HA` | (unset) | `1` enables HA mode in preview: settings and restarts propagate to every node, operations that only change the local host are refused; full high availability arrives in later releases. Requires PostgreSQL, `SECRET_KEY` and `KEY_ENCRYPTION_KEY`, identical on every node (the native packages generate a random key per node); the node exits at startup when one is missing (the Docker image also refuses to generate `UCM_SECRET_KEY`) |
| `INITIAL_ADMIN_PASSWORD_FILE` | `UCM_INITIAL_ADMIN_PASSWORD_FILE` (or `INITIAL_ADMIN_PASSWORD_FILE`) | (unset) | File holding the first administrator's password (a secret), read at the first start only. See [Initial administrator password](#initial-administrator-password) |
| `INITIAL_ADMIN_PASSWORD` | `UCM_INITIAL_ADMIN_PASSWORD` (or `INITIAL_ADMIN_PASSWORD`) | (unset: generated) | The first administrator's password, read at the first start only. No default |
| `INITIAL_ADMIN_PASSWORD_FORCE_CHANGE` | `INITIAL_ADMIN_PASSWORD_FORCE_CHANGE` | (unset) | `1`: the provided password was drawn by a deployment tool, nobody chose it; it must be changed at first login. The Helm chart sets it for the value it generates |
| `INITIAL_ADMIN_USERNAME` / `INITIAL_ADMIN_EMAIL` | `UCM_INITIAL_ADMIN_USERNAME` / `UCM_INITIAL_ADMIN_EMAIL` | `admin` / `admin@localhost` | Identity of the first administrator |
| `UCM_NODE_ID` | `UCM_NODE_ID` | hostname | Node name reported as `node_id` by `/health` and `/health/ready` |
| `BACKUP_MAX_UPLOAD_MB` | `BACKUP_MAX_UPLOAD_MB` | `512` | Largest archive written before 3.0 (format v1 to v3) a restore accepts and reads, in MB; its decompressed content may be four times that. Archives written since 3.0 (v4) are read in chunks and not bound by it. Every other request keeps the 50 MB limit |
| `BACKUP_MAX_ARCHIVE_MB` | `BACKUP_MAX_ARCHIVE_MB` | `0` | Largest v4 archive a restore accepts, in MB; `0` accepts any size |

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

#### Session store

On PostgreSQL without Redis, sessions are in the database (`flask_sessions` table) and shared between nodes; with `REDIS_URL` they are in Redis; otherwise they are files on disk, as below.

The database session store opens its own connection pool, so a worker process can hold up to 2x (`DB_POOL_SIZE` + `DB_MAX_OVERFLOW`) connections: size PostgreSQL `max_connections` accordingly. Without Redis, each web worker also keeps one more connection, outside both pools, listening for real-time event notifications (HA or not).

#### Session key rotation

`SECRET_KEY` signs the CSRF tokens of the web interface; the session id is a random server-side record, not signed with it. **Settings > Security > Session key** (`POST /api/v2/system/security/rotate-secrets`) rotates it:

- **Encryption enabled** (in HA, under the KEK every node holds): the new key is stored in `system_config` (`session.secret_key`), encrypted under the data key like the other secrets and rewritten by a data key rotation. Every node loads it without a restart (cluster command `reload_secret_key`; outside HA the single web worker reloads it at once). The previous key stays accepted for 24 hours, the lifetime of a CSRF token, then is dropped from the database and from every process; a second rotation is refused until then. Nobody is logged out. The key never appears in a response, the audit log or a cluster command.
- **Encryption disabled**: on a single node, unchanged, the new `SECRET_KEY` is written to `ucm.env` and the service restarts; in HA the rotation is refused (409 `ha_mode`), enable encryption first. The key is never stored in the database in the clear; a disable of encryption removes a stored key once it succeeds (a failed one keeps it) and `SECRET_KEY` signs again: pages opened before must be reloaded.

At startup the stored key is read after the master key and before the first request is served. A stored key that does not decrypt (a database restored from another installation, another master key) is ignored with a warning in the log, and the environment's `SECRET_KEY` signs; rotate again to store a new one. This fallback holds at startup only: a running node whose reload fails keeps the keys it has and tries again before its next requests. Backups never carry the stored key: a restore keeps the target's own.

In HA, `SECRET_KEY` stays required and identical on every node: it is the key every node starts with before any rotation and the fallback after one. To change it, set the same new value on every node and restart them one at a time; the stored key, if any, keeps signing.

#### Filesystem permissions (since v2.142)

When sessions are files, UCM enforces `0o700` on its session directory at boot. If the directory is group- or world-readable, the service refuses to start:

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

### Private-Key Encryption (KEK and DEK)

Private keys and stored secrets are encrypted with a data-encryption key (DEK). The DEK is stored in the database (`encryption_keys`), wrapped with AES-256-GCM by the key-encryption key (KEK): `master.key` in `UCM_CONFIG_DIR`, or `KEY_ENCRYPTION_KEY`. The KEK is still the only secret to back up: a database copy plus its KEK restores everything; a database copy without its KEK is unreadable. Settings > Security shows the KEK fingerprint (a truncated hash, never the key) and the DEK version.

- **Upgrade.** An installation encrypted before 3.0 keeps its data as it is: its key is DEK version 1, nothing is re-encrypted. The first DEK rotation or KEK change stores the DEK in the database.
- **Rotating the DEK.** Settings > Security > Rotate data key, or `POST /api/v2/system/security/rotate-encryption-key`, creates a new DEK and re-encrypts every stored value under it in batches. A short grace period follows: until every live node has loaded the new DEK (at once outside HA), then 2 minutes (every process re-reads the DEKs within 2 seconds of a change); a node that has not loaded it after 10 minutes holds the grace until it does or stops. Another rotation, or disabling encryption, waits for the end of that grace only (409 naming it, or saying that it waits for every node); Settings > Security then shows the rotation as possible. The old DEK is kept for reading only for 7 days (retention), so a value a long transaction (restore, bulk import, background job) encrypted under it and commits late stays readable. Several old DEKs can be kept at once: two rotations within a week leave three readable DEKs, listed with their deletion date. A daily sweep (scheduled task `dek_sweep`, the leader in HA) rewrites under the current DEK every value still under an old one; past its retention an old DEK is dropped (task `dek_retire`, every minute) under the key-state lock once a sweep finds no value under it, otherwise it is kept one more day. The KEK does not change. If the rotation is interrupted, both DEKs stay in the database and every value stays readable; it finishes at the next start (outside HA) or when you run it again. A value that no DEK opens stops the rotation (409) with the old DEK kept.
- **HA.** Enabling, disabling and rotating work from any node: the other nodes reload the DEKs within seconds (cluster command `reload_encryption`). A rotation re-encrypts only once every live node has loaded the new DEK; otherwise it answers 202 and you run it again. Every node publishes its KEK fingerprint in `cluster_nodes`, also while in safe mode; a node whose fingerprint differs from a live peer's refuses to start and names that peer, unless the database names its KEK and not the peer's. Enabling encryption is refused (409, naming the node) while a live node holds another KEK, and a node that found its KEK is not the cluster's stays in safe mode until it restarts.
- **Disabling** decrypts every value; the DEKs are then kept for reading only through the same 7-day retention, so a value a process encrypted before it saw the disable stays readable, and the daily sweep decrypts it (rewriting its plaintext `.key` mirror). Enabling again waits only for the short grace (409 naming its end, or saying that it waits for every node); enabled during the retention, encryption starts under a new DEK and the kept DEKs go on opening late values until their date. Outside HA, the `master.key` file is removed in the step that drops the last kept DEK, after a sweep found nothing under it: it wraps those DEKs, and once they are gone no stored value is encrypted, so nothing it opened is left. While DEKs are kept, enabling with a new `master.key` is refused (409): restore the one that wraps them. A `KEY_ENCRYPTION_KEY` (or the `master.key` of HA nodes) stays configured but unused until encryption is enabled again.
- **Backups** never carry `encryption_keys`: an archive holds the private keys in the clear under the backup password, and the target encrypts them under its own DEK. An archive taken during a retention, including a value still under an old DEK, restores without that DEK.

#### Changing the KEK by hand

The KEK never changes from the interface. To replace it:

1. Back up the database and the current `master.key` (or `KEY_ENCRYPTION_KEY`).
2. Stop UCM (every node in HA).
3. Move the current key to `master.key.previous` beside `master.key`, or set it in `KEY_ENCRYPTION_KEY_PREVIOUS`.
4. Install the new key as `master.key` (0600, owned by the service user) or `KEY_ENCRYPTION_KEY`, identical on every node.
5. Start UCM (one node first in HA). It rewraps the DEKs under the new KEK, rewrites no stored value, logs and audits `encryption_kek_changed`.
6. Remove `master.key.previous` or `KEY_ENCRYPTION_KEY_PREVIOUS`, start the other nodes, and back up the new key.

The audit chain is sealed with a key derived from the KEK: after a KEK change, entries sealed before it are reported as under a retired key, attested by `audit-chain.keys`. A DEK rotation leaves every seal verifiable. If the old KEK leaked, also rotate the DEK once the change is done: until then the data stays under the old DEK. A new KEK started without the previous one puts UCM in safe mode while values are encrypted, and nothing is written. With encryption disabled, outside HA UCM stays disabled under the new KEK until you enable it again; in HA the node stays in safe mode until it has the cluster's KEK. During the 7-day retention after a disable, a new KEK started without the previous one cannot open the kept DEKs: UCM starts in safe mode, they are never dropped and encryption cannot be enabled again (409, or 503 in safe mode); follow the steps above with the previous KEK to leave that state.

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

The `certificate.expired` webhooks of a pass cover what expired since the previous pass, at most 30 days back: after a longer outage the older expiries are not announced and the log gives their number. A first pass covers the last day.

---

## Backup & Restore

### Creating Backups

**Via UI:**
1. Go to **Settings** > **Backup** tab
2. Click **Create Backup**
3. Enter encryption password
4. Download `.ucmbkp` file

Backups, retention and restores take the same lock, so an archive never holds half of a restore: a manual backup started meanwhile waits up to 30 seconds, then answers 409; the scheduled one runs at the next minute.

**Via command line (SQLite):**
```bash
sudo systemctl stop ucm
sudo cp /opt/ucm/data/ucm.db ~/ucm-backup-$(date +%Y%m%d).db
sudo systemctl start ucm
```
On PostgreSQL, use `pg_dump` instead. A copy of the database is not a `.ucmbkp` archive: the private keys stay under this installation's key-encryption key.

### Restoring Backups

**Via UI:**
1. Go to **Settings** > **Backup** tab
2. Click **Restore Backup**
3. Upload `.ucmbkp` file
4. Enter encryption password

A restore **replaces** the instance with the archive: for every section the archive carries, the rows it does not hold are removed. Sections the archive left out are not touched, and an archive whose user list is empty is refused. `POST /api/v2/system/restore` also takes `mode=merge`, which adds and updates the archived rows and removes nothing.

- The restore is one transaction: on any error nothing is changed, the answer names the row the database refused, and no file on disk is touched. The certificate, CSR and key files are published once the rows are in, and those of the removed rows are deleted with them.
- A row of a table the archive does not carry that points at a removed row loses the link where it is optional, and goes with it in a regenerable table (CRL metadata, OCSP cache, sessions, in-flight ACME server orders); any other refuses the restore, named.
- Rows are matched by identity (name, refid, fingerprint), never by number. Each archive carries the identifier of the database it was taken from, and row numbers are trusted only when restoring onto that same database.
- An archive written by an older version is repaired as the migrations repaired the source: legacy EAB keys, dead and `ldap_*` settings, SAML providers, group permissions, duplicated ACME renewal orders.
- ACME client orders: a merge keeps the order here when it is further along, was renewed or is being finalized since the archive was taken; a replacement restores the archived one and names the certificate it gives up.
- Revocations: a merge never lowers a final revocation made here, of a certificate or a CA; a suspension is reversible, so one carried by the certificate alone (no revocation record) is lifted by an archive in which the certificate is valid.
- Every session is revoked and a restart is requested. A restore is refused (409) while a backend migration, another restore or a backup is running.

Archives are written as format v4: a sequence of chunks of at most 8 MB, each authenticated on its own, so a backup is created and read section by section without ever being held whole. The upload is spooled to `DATA_DIR/tmp` and each section is kept there, encrypted under a key held only in memory, until the restore needs it. When `DATA_DIR/tmp` is missing and cannot be created, or is not writable, the upload is spooled to the system temporary directory and the sections to a directory of the instance's own under it, named after a hash of `DATA_DIR`. At startup each worker removes stale stores from the directory its restores use, and only after taking the backup lock: when the lock cannot be taken, nothing is removed. Decryption and the checks made before the restore plan hold about one section at a time; the plan and the writes hold every section the archive carries. A v4 archive has no size limit unless `BACKUP_MAX_ARCHIVE_MB` sets one. Archives written before 3.0 (v1 to v3) are still restored, up to `BACKUP_MAX_UPLOAD_MB` (512 MB by default), their decompressed content up to four times that, and one JSON object per 100 bytes of it. A reverse proxy in front of UCM applies its own body limit.

### Backup Contents

- All certificates and private keys
- CA hierarchy, cross-certificates and revocation records
- Users, groups, roles, API keys, client certificates and settings
- Templates, policies, SSO, HSM, SMTP, notification, deployment, webhook and ACME configuration
- SSH CAs and certificates, Microsoft CA connections, SCEP profiles and Intune apps, DNS providers, discovery profiles
- ACME client orders, with the key of a finalization in progress, approval requests and key recovery requests
- The HTTPS certificate and key the server presents
- Settings that name a CA, a certificate or an ACME account carry that row's identity, and are renumbered on restore. One whose row is not on the target is emptied, or left out when the number is in its name (`scep_challenge_<n>`, `ocsp_responder_cert_<n>`, `cert_scts_<n>`), with a warning

Secrets travel decrypted inside the encrypted archive and are encrypted again with the target's keys. Histories (audit log, discovery scans and results, SCEP and Microsoft CA request logs) are not in the archives UCM writes, and a restore leaves them as they are. Live state is not carried either: lockout counters, sessions, CRL and OCSP caches, delivery queues.

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
- Copies the migration registry (`_migrations`), so the target starts as the source would
- Disables FK checks during bulk load
- Intersects source/target columns (legacy columns are skipped with a warning)
- Resets PostgreSQL sequences after load

**Safety checks (fail fast, source untouched):**

- **Test connection** rejects PostgreSQL servers older than 13 (UCM minimum supported version).
- **Migrate** refuses if the target already contains UCM data (rows in `users`, `cas`, or `certificates`). Reset the target first:
  - PostgreSQL: `psql ... -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'`
  - SQLite: delete the target `.db` file
- **Switch backend** refuses (409, `ucm.env` unchanged) a target the service would refuse to start: accounts without a migration registry, a registry missing migrations of 2.254, or a 2.254 database without accounts. Switching back to SQLite checks the file `DATABASE_PATH` names the same way. Retrying a switch cut short on the same target resumes it; after a failed verification of the copied accounts, reset the target first. A target that already holds accounts keeps them and nothing is copied: if it already runs this release, its id counters are moved up to the current database's; a 2.254 database is taken as it is.
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

> ℹ The psycopg 3 driver is bundled with the DEB/RPM packages and the Docker image. No extra install step is needed.

### HA mode (preview): scheduler and startup

With `UCM_HA=1`, every node runs against the same PostgreSQL database and names itself with `UCM_NODE_ID` (default: the host name, which must differ between nodes).

- **Leader.** One node at a time runs the scheduled tasks: the one whose scheduler process holds a PostgreSQL session advisory lock on a dedicated connection. The lock is checked before every task; if that connection drops, the node stops starting tasks (a task already running finishes) and another node takes over within `LOCK_RETRY_SECONDS` (5 s). If the leader's host vanishes without closing it (power loss, network partition), PostgreSQL drops the session after about a minute of silence (server-side TCP keepalives and user timeout set on that session), then another node takes over. No file is shared between nodes.
- **Takeover delay.** When the leader's process dies, PostgreSQL frees the lock at once and another node leads within `LOCK_RETRY_SECONDS` (5 s); when its host vanishes, add the minute PostgreSQL takes to drop the silent session. `/health` names the new leader as soon as it holds the lock, and stops naming a leader that went silent after `STALE_PASSES` passes (3 × 60 s): the bound is therefore 5 s + 180 s, which the HA bench (`docs/testing/ha-bench.md`) waits at most.
- **Heartbeat.** Each node's scheduler process writes its row in `cluster_nodes` once per pass (60 s); a row older than three passes counts as stale. `/health` reports `leader` (this node) and, in HA mode only, `cluster: {leader_node_id, nodes, stale}`. `/health/ready` answers 503 until this node has ever registered in `cluster_nodes`: a row left by an earlier run counts, so a restarted node is ready before its new scheduler process writes again. Staleness compares node clocks: keep them synchronised (NTP).
- **Run now.** From any node, except for the per-node tasks (see Local files below), Settings > Scheduler > Run now queues a request in `scheduler_requests`; the leader claims it on its next poll (about one second), runs it once and deletes it. The page waits up to 30 s for the result, then shows the task as started. The leader also publishes the tasks' status in `system_config` (`scheduler.state`), which every node shows. A request claimed by a leader that disappears is dropped, not replayed: ask again.
- **Startup.** Migrations and the first schema creation run under a second advisory lock: a node starting while another one migrates waits for it (at most 120 s, then refuses to start with an explicit error) and then finds nothing left to apply.
- **Discovery scans.** Each scan run records the node that runs it. A new leader marks as failed the scans of nodes without a fresh heartbeat and the scheduled scans a live node started before its current scheduler process; the other scans of live nodes are kept (a former leader that only lost its lock connection still runs them). The leader also fails, on every pass, the scans of nodes that have gone stale since and the scheduled scans a live node's former scheduler process left, and a node's web process fails that node's own scans when it starts: under gunicorn the master does it once, before forking its workers (`preload_app = True`); without preload each worker would do it again and fail the scans its siblings already run.
- **Settings across nodes.** A setting change writes a row in `cluster_commands`, in the same transaction; every node applies the new rows in id order within a few seconds (it polls every 2 s) and records the last one in `cluster_nodes.command_seen`, which `/health` reports for the answering node under `cluster.command_seen`; `GET /api/v2/system/service/status` (authenticated) lists every node with its heartbeat, `command_seen` and `package_family`. A row committed late, behind a newer one, is still applied if it commits within about 10 minutes. Applied without a restart: rate limits (Settings > Security; the changes are stored in the database and each node adds them to its own `RATE_LIMIT_*` environment, also when it starts), syslog forwarding and the admin allowlist. Read from the database on every use, so already shared: the password policy, HSTS, session timeouts. The session key, once rotated, is stored in the database and reloaded by every node (see [Session key rotation](#session-key-rotation)). The leader deletes commands older than 24 hours.
- **Rolling restart.** A restart (Settings > Service, or the one mTLS and WSTEP changes ask for) restarts every node in turn, in `UCM_NODE_ID` order: a node goes once every node before it is back (its heartbeat carries a start time later than the request) or after 120 s per node ahead of it, so a dead node holds the others back no longer than that. A node waiting for its turn keeps applying setting changes, and a second restart requested meanwhile adds no restart of its own: the node still restarts once, after every node before it is back from the later request. A one-node cluster restarts at once, and a node is left alone by a request already committed when it read its settings at start; a request committed later restarts it. When the restart itself fails (for example the signal file cannot be written), the node logs it and tries again after 2 s, then waits twice as long after each new failure, up to 60 s between attempts, also when it went without a node ahead that was not back (the 120 s per node are not waited again); it keeps applying setting changes meanwhile. DEB/RPM nodes restart through their own `ucm-watcher`; a container exits with code 0 and its orchestrator starts it again only under the restart policy `always` or `unless-stopped` (`on-failure` and `no` leave it stopped).
- **HTTPS certificate.** Applying a managed certificate, regenerating the self-signed one or a renewal of the bound certificate writes the files on the node that handles it, stores what every node must serve in the database, and requests a rolling restart. Before its TLS socket opens, each node's gunicorn master writes the certificate (with the chain stored with it) and its key from the database, decrypted with the master key, when its files are missing or differ: a node without TLS files, or restored from a backup, serves the bound certificate at its next start. A node that cannot read the key (no master key) logs why and keeps its files. Without a binding the files are left alone, as before. A certificate copied by hand into the files is not shared.
- **Kerberos keytab.** Each Windows enrollment profile stores its keytab in the database under the master key; UCM composes the keytabs of all profiles into one file (`shared_files`) that every node writes to its disk within seconds (`reload_keytab`) and at each start, so the composition is rebuilt on every node. On a single node, a keytab uploaded before 3.0 is taken by the default profile at the first start; in HA, a keytab that only one node holds is not shared: upload it again. The profiles' keytabs travel in the backup archives of 3.0, re-encrypted on restore; an archive of 2.x never carried the keytab, so the one of the installation stays with the default profile.
- **Rolling update.** On DEB/RPM, installing an update from System > Updates or the scheduled automatic install updates the nodes one at a time: each node downloads and verifies the package of its own family (DEB, RPM EL9, RPM EL10, RPM Fedora) itself, and the next one starts once the previous one beats again on the new version. A node not back within 15 minutes stops the campaign until an admin resumes it. Docker and Kubernetes refuse it: the orchestrator updates the image. See [HA.md](HA.md#rolling-update-from-the-web-interface-debrpm).
- **Deployment, prerequisites and refused operations.** See [HA.md](HA.md). Encryption works from any node: see [Private-Key Encryption](#private-key-encryption-kek-and-dek).
- **Local files.** Scheduled backups are written by the leader only, under its own data directory, while their retention runs on every node; the certificate files mirrored by renewals and session file cleanup run on the leader only.
- **Per-node tasks.** Two tasks run on every node, leader or not: backup retention prunes the archives on the node's own disk, and `update_result` reports the outcome of an update installed on that node. Settings > Scheduler shows the runs of these two tasks on the node that answers, and Run now runs them on that node; every other task shows the leader's runs and Run now asks the leader.
- **A pass held by another node.** When the expiry alerts or a CA's scheduled CRL are skipped because another node holds their lease (10 and 15 minutes), the leader runs them once more 30 seconds after the lease ends, however many passes were skipped; the run finds nothing left to do when the holder finished.
- **Real-time events without Redis.** Every web worker and the scheduler process write their WebSocket events to the `websocket_relay` table; each worker emits to its own browsers the rows written by others (its own events reach its browsers at once) and reads the table every 2 s. On PostgreSQL a `NOTIFY` on channel `ucm_ws_relay` wakes the workers as soon as a row commits, through one extra connection per worker outside the pool, reopened if it drops. Rows are kept 10 minutes and hold what the browsers receive (event type, ids, names, the user and source IP of a login). With `REDIS_URL` set, Redis carries the events and the table is not used.
- **Scheduled backup.** A run reserves its slot in `system_config` (`backup.last_run`) before writing, so two nodes do not both write it. A run that never concludes (node killed mid-export) is retried after a two-hour lease. The lease is not refreshed while the export runs: an export lasting longer than two hours can be started again by another leader, giving two archives on two nodes. Archives carry neither `backup.last_run` nor `backup.concluded_run`: a restore keeps the target's own schedule.

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

## CA Hierarchy

### A parent whose signature cannot be verified

An imported CA is linked to a parent only when the parent's key verifies its signature. When the
parent's key or signature algorithm is one this server cannot check (SLH-DSA, GOST), the CA is left
without a parent, and neither the hourly chain repair nor a re-import links it.

Its details then name the probable parent: a stored CA whose subject is the CA's issuer and, when
both carry one, whose subject key identifier is the CA's authority key identifier, with the
algorithm that could not be checked. Every import path reports it too (the CA import, the
certificate import, the smart import, the OPNsense import). **Link to this parent** asks for an
explicit confirmation; UCM checks everything again at that moment and refuses a CA that already has
a parent, a parent other than the one proposed and a signature that does not verify. The link is
recorded with who confirmed it and when, and audited (`ca_parent_confirmed`). **Withdraw the link**
removes it (`ca_parent_unconfirmed`) and the CA is proposed its parent again. Both need `write:cas`.

Once linked, the CA follows that parent like any other: it is revoked in chain when the parent is,
the parent's OCSP responder and revocation records find it, and the chain export, EST `/cacerts`,
SCEP `GetCACert` (when the chain is served) and the hierarchy views include the parent. The AIA
files serve the CA's own certificate and are not affected. The hourly chain repair keeps the link;
a re-import or a renewal certificate installed on the CA keeps it while that parent is still the
one proposed, and drops the confirmation otherwise (audited as `ca_parent_unconfirmed`). If a later version can check the algorithm and finds the signature false, the parent no
longer counts for the revocation status, but the recorded link still orders the chains served:
withdraw it.

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

These settings apply to UCM only. ACME clients that use the ACME proxy run their
own DNS checks. For per-client setup (certbot, acme.sh, lego, cert-manager,
win-acme, Posh-ACME) and for the resolver limits of those clients, see
[Using the ACME proxy from hosts without DNS API access](integrations/acme-proxy-clients.md).

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

> **Internal network only.** The listener answers unsigned SOA queries for names of orders (see below). Put it on an internal network or a private address. Never publish it to the internet. Use `UCM_DNS_UPDATE_HOST` and a firewall (or the Helm `dnsUpdate.networkPolicy`) to limit who can reach it. A peer that opens many TCP connections from enough addresses can hold the whole pool of 128 TCP connections, so the listener belongs on the internal network.

**Enable it.** The listener is **off by default**. A restart is needed after every change.

**Reload and restart.** `systemctl reload` (HUP) starts a new worker while the old worker still holds the port. The new worker tries to bind the port again until it succeeds, first after 0.25 seconds, then after a wait that doubles each time up to 1 second (0.5 seconds, then every second). The old worker can hold the port longer than `graceful_timeout` while a long connection (for example the WebSocket of the web interface) is open. When the port is still busy after `graceful_timeout` + 5 seconds (35 seconds by default), UCM logs an error once and keeps trying. The listener starts as soon as the port is free. Another bind error (for example a wrong `UCM_DNS_UPDATE_HOST`) stops the retries, and the log shows it. `GET /api/v2/acme/client/settings` shows `dns_update_listening`.

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
- The keys of an account whose ACME proxy is off stay in the database. They do not work (BADKEY). The **DNS UPDATE keys** button stays in the web interface for an account that has keys, with a warning. You can revoke and delete the keys there, but not create new ones: the API answers `409` to a new key for an account whose proxy is off. `GET /api/v2/acme/client/accounts` gives `dns_update_key_count` for each account (keys of any status).
- `last_used_at` of a key shows when it last sent an accepted update.

**What the listener accepts and answers.**

- An UPDATE must be signed (TSIG). An unsigned UPDATE gets `REFUSED`.
- An update adds only a TXT record at `_acme-challenge.<name>`, with the exact value that UCM expects for a pending proxy order of the key's scope. An add needs a pending order.
- The zone section of an UPDATE must be an entry in ACME Domains, a parent of one (not a top-level domain), or a name below one. Every record of the update must be in that zone. A record outside the zone gets `NOTZONE`.
- Deletes always get `NOERROR`, also when the order is gone. A delete can remove one record, the whole TXT set of a name, or all RRsets of a name. `update delete <name>` without a type means all RRsets (RFC 2136 §2.5.3). UCM accepts it for `_acme-challenge` names. It changes nothing, like the other deletes.
- A message with prerequisites gets `REFUSED`.
- UCM stores the expected value when a client fetches the authorization while the challenge is pending or processing. This covers sibling orders (#307).
- **The listener writes nothing to DNS.** UCM still publishes the challenge record through its DNS provider, as for every proxy order. The update only proves that the client holds the right value.
- It answers SOA queries for the zone of an order and for the names between that zone and the challenge name (the zone is the ACME Domains entry for the name). UCM answers the SOA query while a challenge is pending. It also answers for 24 hours after the expected value expires. This is also true after the validation failed or the certificate was downloaded. Clients can then find the zone again when they clean up. Adding a record still needs a pending order. Unsigned and signed SOA queries are answered. A signed query gets a signed answer. The SOA record has fixed values and no host name.
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
| `REFUSED` | The request is understood but not allowed | Unsigned UPDATE; value does not match the pending order (new order, new value); no pending order for that name (the client must fetch the authorization first; an add needs a pending order, also when the SOA query was answered); name is not `_acme-challenge.<name>`; record type is not TXT (a delete without a type is accepted for `_acme-challenge` names); the message has prerequisites; for a query, no order covers the name (the order is pending, or its expected value expired less than 24 hours ago) |
| `NOTAUTH` | The zone is not served | The zone section is not an ACME Domains entry, a parent of one, or a name below one |
| `NOTZONE` | A record of the update is outside the zone of the message | Every record must be in the zone. The client sent a zone and a record name that do not fit |

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

A renewal is a RenewalReq, or a PKCSReq signed by a valid certificate issued through the same SCEP endpoint: both are checked as renewals (subject and SANs kept, signer not revoked, expired, superseded or of a Windows enrollment profile) and replace the old certificate, a PKCSReq still needs the endpoint's challenge, expired or not, and Intune-bound profiles treat a PKCSReq as a new enrollment.

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

Configure under **Settings → Windows Autoenrollment** (the profiles and the switches shared by all of them) and **Settings → Active Directory** (the connectors). Policy discovery (XCEP) and issuance (WSTEP) work out of the box for username/password and certificate-based binding. The **Kerberos** binding, used for silent GPO autoenrollment, needs one extra server-side dependency that is deliberately **not** installed by default: `pyspnego`'s `kerberos` extra pulls in `gssapi`, a C extension that requires the system's Kerberos development headers to build. Installing it by default would break `pip install -r requirements.txt` on hosts without a compiler or `libkrb5-dev`, so it's opt-in.

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

### Windows enrollment profiles: one per realm

A **profile** is the enrollment setup of one Active Directory realm: its issuing CA and policy CA, the templates it offers, its AD connector, its keytab and its required AD group. One profile per realm (each AD domain is a realm): N realms need N profiles. One profile is the **default**: it cannot be deleted (disable it instead), and the UsernamePassword binding is served by it alone. The shared UsernamePassword accounts (`xcep_username`, `xcep_password`, `wstep_username`, `wstep_password`) therefore belong to the default profile: the API refuses them on any other profile (400) and the editor shows them for the default one only. A new installation has no default profile until one is designated. While no profile is the default, the profile editor offers **Default profile**, on a new profile or a saved one, and shows the shared accounts as soon as it is checked; the API takes `"is_default": true` in the same case, on `POST /api/v2/windows-profiles` or `PUT`/`PATCH /api/v2/windows-profiles/{id}`. Once a profile is the default, the box is no longer offered and the API refuses another designation with 409 naming the default profile; of two designations made at the same moment, one wins and the other gets that 409. The default is neither withdrawn nor moved to another profile this way (`"is_default": false` on it is refused with 409). The import of a keytab held by a 2.x installation at its first start also makes one, and an installation upgraded from 2.x already has one.

- **Routing.** A Kerberos request is served by the profile whose realm is the realm of the authenticated principal, compared exactly and case-sensitively, as a KDC does (RFC 4120). Realms are stored in capitals (`CORP.EXAMPLE`); two profiles cannot hold the same realm. There is no fallback: the default profile never serves the realm of another profile. The Certificate binding is served by the profile recorded on the presented certificate (see the renewal section below).
- **One keytab per profile, one file for the acceptor.** Upload each profile's keytab in its editor (or `POST /api/v2/windows-profiles/{id}/keytab`). UCM composes the entries of every profile's keytab into the single file the Kerberos acceptor reads, and rewrites it whenever a keytab is uploaded or a profile that held one is deleted; there is no file to merge by hand. Every entry must be `HTTP/<SPN host>@<realm of the profile>`; the editor lists the entries of the selected file by realm before it is stored, and the server refuses a file with an entry outside the profile's realm (400). Set the realm of each profile yourself: Kerberos is refused for a profile without one, and the realm that a profile left empty takes by itself (that of its enabled connector, else of the SPN, else the single realm of its keytab) is only a convenience for an upgraded installation.
- **One SPN for all profiles.** The service principal name is a shared setting (**Settings → Windows Autoenrollment**, shared settings, `kerberos_spn`): `HTTP/ucm.example.com`, with or without `@REALM`. Its service and host are the same in every forest, so each forest resolves that name to its own service account and issues its own key; the realm is told apart by the key, not by the name. The same switches (XCEP, WSTEP, Kerberos) apply to all profiles.
- **Disabled profiles keep their keys.** A disabled profile's keys stay in the composed file, so that its machines authenticate and are refused by realm, and audited, instead of failing with a bare 401.

#### Setting up a forest, step by step

Before the steps:

- **The clients trust the HTTPS certificate of the server.** The enrollment URLs are built from the address the client used to reach UCM, so enroll over the HTTPS URL of the server and make the clients trust the CA that issued its certificate.
- **WSTEP needs a restart to be switched.** Enabling or disabling WSTEP in the shared settings restarts the service because the TLS behavior is read at startup. The API answers that the service is restarting; in Docker it answers `requires_container_restart` and you restart the container yourself; in HA a rolling restart of the nodes is requested.
- **Computer certificates need machine templates open to autoenrollment.** A request from a computer account is served by templates of a machine type (web server, VPN server, VPN client, OCSP signing); a template whose subject is built from the user's directory entry is refused to computers (`is issued to users, not computers`). Offer at least one machine template with automatic enrollment enabled in the profile, or the machine context finds nothing to enroll.

1. **Install the Kerberos library** (above) once per UCM, then enable Kerberos and set the SPN in the shared settings. Windows clients must reach UCM by the host name of that SPN.
2. **Create the AD connector** (**Settings → Active Directory → Add connector**): servers, bind account and a base DN that names the domain with DC components (`DC=corp,DC=example`). The realm of the forest comes from it. **Test** the connector: the domain SID is read then.
3. **Create the service account and register the SPN** in the forest: `setspn -S HTTP/ucm.example.com CORP\svc-ucm`, then export a keytab for `HTTP/ucm.example.com@CORP.EXAMPLE` (`ktpass`, or `ktutil` when the account must not be modified). Check it with `kinit` and `kvno -k` on a Linux host. The keytab of each forest holds only that forest's key.
4. **Add the profile** (**Settings → Windows Autoenrollment → Add profile**): name, realm in capitals, the connector of step 2, the issuing CA, the templates to offer, and optionally the AD group the requester must belong to, which replaces the one the template requires.
5. **Upload the keytab** of step 3 in the profile. The checklist of the editor turns green once the realm, issuing CA, keytab, connector and templates are set; the list flags a profile whose keytab is missing, whose connector fails, or whose realm differs from the domain of its connector.
6. **Repeat** steps 2 to 5 for each forest. No trust between the forests is needed, and a profile only serves its own realm. In a forest, only the domain whose account holds the SPN is served, and clients of the forest's other domains are refused (see below). Domains linked by trusts and child domains of a forest have not been tested.
7. **Check** from a domain-joined client of each forest: `Get-Certificate -Url <Kerberos policy URL> -Template <template>`, or wait for the GPO. Automatic enrollment needs the Windows autoenrollment policy enabled on the client (group policy **Certificate Services Client - Auto-Enrollment**): with the policy server registered but that policy off, Windows reads the policy and requests nothing, with no error on either side.

The CA that Kerberos clients see is the policy CA of the profile that serves them; the policy and enrollment URLs are the same for every profile. The policy identifier and the template identifiers that clients cache derive from that CA: once it changes, clients already registered fail to enroll (`0x8007000d`) until the policy server is registered on them again.

#### When a request is refused

| Case | What the client gets | Where the reason is |
| --- | --- | --- |
| No keytab of any profile holds a key for that realm (no profile, or its profile has no keytab and no other keytab carries its realm) | A 401 Negotiate challenge: the client's authentication fails and nothing reaches the profile logic | The service log only (`no key for this realm`), **no audit entry**. For a profile that exists, `kerberos_refusal` in `GET /api/v2/windows-profiles/{id}` says `no key for realm ...` |
| The client realm differs from the realm of the key that accepted the ticket | A 401 Negotiate challenge | The service log only (`client realm ... does not match the realm ... of the key that accepted it`), no audit entry |
| A key of that realm is served but no profile has the realm (a keytab that carries several realms, or a keyed profile whose realm is not set), the profile is disabled (its keys stay in the composed keytab), or the principal names no realm | HTTP 400 with the SOAP fault `The requester's realm is not served` | The audit entry `windows_enrollment.refused` |
| The profile has no realm (the default profile after an upgrade that could not name one) | Kerberos is not advertised in the policy and is refused | The profile screen, `kerberos_refusal` in `GET /api/v2/windows-profiles/{id}` |
| A Kerberos request that names no template (certificate template extension, by OID or name) and whose Extended Key Usages match none the profile offers, as AD CS refuses it (`CERTSRV_E_NO_CERT_TYPE`); the policy announces each template's extension for CertEnroll to copy into its request. The renewal of a certificate that carries no template extension (issued before 3.0) is still served when that certificate is valid, was issued by Windows enrollment under the same profile and belongs to the requester (its SID, else its subject or the computer's `dNSHostName` in the directory); held for approval, it is refused once that certificate is revoked | HTTP 400 with the SOAP fault `The request names no certificate template and its Extended Key Usages match none this profile offers`; when its Extended Key Usages fit only a template of another key type, the fault names that template's key instead (`Template '<name>' issues <key> keys, not <key>`) | The audit entry `windows_enrollment.refused` |
| The AD connector cannot resolve the requester (no such account, or an account without `userPrincipalName`), or the requester is not in the AD group of the profile (or of the template, when the profile sets none) | A SOAP fault on issuance, whose text says which | The service log and the audit entry |

Windows shows its own error for a SOAP fault (for example `WS_E_ENDPOINT_FAULT_RECEIVED`, `0x803d0013`), never the text of the reason. To find the reason of a refusal that reached the profile logic, open **Audit** and filter on the action `windows_enrollment.refused` (resource type `windows_profile`): its details give the binding (CEP or CES), the source address, the reason, the principal, its realm and the profile. EST and SCEP renewals refused for a Windows profile certificate are audited under the same action. The audit log is not the whole story: a realm without key (first row) leaves no entry, and neither does a renewal with the TLS client certificate that the listener refuses during the TLS handshake (see the renewal section): for those, read the client (the `certreq` output and the Windows event log) and the service log.

### Windows enrollment profiles: renewal

Every certificate issued over WSTEP (Kerberos, UsernamePassword, Certificate binding, deferred approval) records the profile that issued it. A `wstep` certificate recording none, issued before profiles existed, belongs to the default profile.

- **Certificate binding.** The renewal is served by the profile recorded on the presented certificate, under that profile's issuing CA, whatever the state of the default profile. It is refused when that profile was deleted or is disabled, when the certificate was not issued through Windows enrollment, or when it no longer comes from the profile's issuing CA. Each refusal of a certificate stored here is audited (`certificate.renewed`, failed) with the profile and the reason; the renewed certificate records the same profile.
- **What is checked again.** Only the SID of the certificate, by the connector of its profile: an enabled connector of the SID's domain (or of a domain not read yet) must still find the account; a profile without enabled connector, or whose connector is of another domain, keeps the SID as it is. Group membership is not checked again: a computer or user removed from the group keeps renewing until its certificate is revoked, so revoke it when you remove it.
- **TLS client certificate.** The TLS trust of the server is not widened for the profiles: the listener trusts the mTLS CA alone (**Settings → mTLS**). Renewal with the TLS client certificate therefore works only for a profile whose issuing CA is the mTLS CA or a CA under it; it is refused otherwise, as is mTLS authentication on EST for such a certificate. Domain-joined Windows renews over Kerberos first and only falls back to the Certificate binding when Kerberos is refused, so the other profiles renew over Kerberos (or behind a proxy that terminates TLS and forwards the verified certificate). A certificate that the listener does not trust is refused during the TLS handshake, before UCM sees a request: nothing is audited by UCM. To tell in advance, compare the issuing CA of the certificate (its Windows profile is shown in the certificate detail) with the mTLS CA.
- **No other way to renew.** A certificate of a profile outside the mTLS CA renews over Kerberos only. When Kerberos refuses (the requester was removed from the AD group, the profile is disabled, the directory cannot answer), there is no renewal until the cause is lifted.
- **Kerberos binding.** A renewal there is an issuance routed by the realm of the principal: when that realm belongs to another profile than the certificate being renewed, the realm's profile serves it, under its own CA, and the new certificate records that profile.
- **Deferred approval.** A request held for approval records its profile by name and its CA by refid, and is replayed by them; after a restore on another installation, a request whose profile or CA does not exist there is closed with a message saying so (the profile is named). A profile renamed while a request is held keeps it, even when another profile takes the name: the request then falls back on the profile's id, provided that profile still has the request's realm.
- **Not over EST or SCEP.** EST `/simplereenroll` and SCEP RenewalReq refuse to renew a certificate of a Windows enrollment profile (enabled, disabled or deleted since, or a `wstep` certificate recording none), answering 403 and FAILURE with `badMessageCheck`, and audit the refusal (`windows_enrollment.refused`) with the profile and the reason; such a certificate renews over WSTEP only.
- **Keytab.** The keytab served to the Kerberos acceptor holds the keys of every profile, disabled ones included, so that a request of a disabled profile's realm authenticates and gets the refusal fault and its audit entry. Disabling a profile does not remove its keys from that file, and no route removes the keytab of a profile: to remove them, delete the profile (allowed unless it is the default one or has valid issued certificates).

### Windows enrollment: common name pattern

A template whose subject UCM builds on the Kerberos binding (a computer template: web server, VPN server, VPN client, OCSP signing; or a user template with **Build subject from Active Directory**) can take the CN of its certificates from a pattern (**Templates**, subject section, **Common name pattern**). The pattern is fixed text and variables in braces, read from the requester's object in the directory of the profile, never from the request: `{hostname}-WiFi`, `{username}`, `{displayName} ({username})`. An empty pattern keeps the subject described above.

| Variable | Templates | Value |
| --- | --- | --- |
| `{hostname}` | computer | `sAMAccountName` without its trailing `$` |
| `{fqdn}` | computer | `dNSHostName` |
| `{username}` | user | `sAMAccountName` |
| `{upn}` | user | `userPrincipalName` |
| `{mail}` | user | `mail`, when it is a valid address |
| `{displayName}`, `{givenName}`, `{surname}` | user | `displayName`, `givenName`, `sn` |
| `{domain}` | both | the `DC` components of the object's DN, joined with dots |
| `{realm}` | both | the realm of the profile |

- **Saving.** `{{` and `}}` write a literal brace. An unknown variable, a variable of the other kind of template, a stray brace, or a pattern on a template whose requester supplies the subject is refused when the template is saved (create, update, import), with a message naming it. Changing the type of a template, or switching off **Build subject from Active Directory**, under a pattern that no longer fits is refused the same way.
- **The subject.** With **Keep the directory path** off (the default), the subject is `CN=<pattern>` alone, plus the template's pinned fields. On, the object's DN after its own name follows the CN (`CN=<pattern>,OU=Laptops,DC=corp,DC=example`), and a user's subject keeps the e-mail attribute it has without a pattern. A value goes into the CN as text: a comma, `=` or `+` in a `displayName` adds no RDN.
- **What does not change.** The SAN (the computer's DNS name; the user's UPN and e-mail) and the SID extension are those issued without a pattern; a pattern never makes a SAN, so `{hostname}-WiFi` is never a DNS name of the certificate. The directory is searched as often as without a pattern: the attributes join the search already made for the subject.
- **Refusals.** A variable the directory leaves empty, a result longer than 64 characters (the bound of a CN, RFC 5280) or one holding a control character refuses the request, which is the requester's fault (SOAP `s:Sender`); nothing is shortened. The reason, `Template '<name>' cannot build its common name: {displayName} has no value in the directory for the requester`, is in the audit entry `windows_enrollment.refused`. A directory that cannot answer stays a server fault, as without a pattern.
- **One subject per account, checked at issuance.** RFC 5280 wants a distinct subject for each entity a CA certifies. Saving a pattern does not check it; issuing does. Before storing a certificate whose subject a pattern built (issuance, renewal, a held request once approved), UCM looks for the certificates of the same CA carrying that subject, whatever their status (valid, expired, revoked, superseded), compared as RFC 5280 §7.1 says: case and extra spaces are ignored, so `John Smith` and `john  smith` are one subject. The request is served when each of them carries the requester's SID in its SID extension, so an account renews and enrolls again under its own name. Otherwise it is refused as the requester's fault (SOAP `s:Sender`), with `Template '<name>' builds the subject CN=John Smith, which a certificate of another account already carries`, naming no account; the audit entry `windows_enrollment.refused` adds the serial of that certificate. A certificate without SID extension (issued by hand or over ACME, or a SCEP or EST certificate that carries none) proves no account and refuses too; certificates of other CAs do not count. Of two accounts asking for one subject at the same time, one is served and the other refused. The check comes after the signature: with Certificate Transparency embedding on, a refused request can leave a precertificate in the logs. A held request refused this way at approval is closed: the approver sees the reason with the serial, the client the usual refusal of a closed request.
- **Getting out of a refusal.** `{displayName}`, `{givenName}`, `{surname}` and `{mail}` can be shared by several accounts (the editor warns about them), and `{username}` or `{hostname}` alone by the accounts of two domains, or by a user `pc1` and a computer `PC1$` under two templates of one CA. Add a variable that tells the accounts apart: `{upn}` or `{fqdn}`, or `{username}` or `{hostname}` with `{domain}` or **Keep the directory path**. Issued certificates keep their subject: a refused account is served once the pattern builds a subject no other account's certificate carries.
- **Renewal.** A Kerberos renewal is an issuance and takes the pattern in force. A renewal with the certificate (Certificate binding) is still recognized by its profile and SID, and the request must still repeat the subject of the renewed certificate; the new certificate takes the CN of the pattern in force, for the account the certificate's SID names, found by the connector of the profile (one more search). It is refused when no connector of the profile finds that account, or when the directory leaves a variable empty. Without a pattern, the renewed subject is kept as before.
- **Username/Password binding.** It has no directory identity: the pattern does not apply there, and the client supplies the subject, as the policy of that binding announces.
- **Policy.** With a pattern, the policy announces the template's SAN flags without a subject flag (`0x08000000` for a computer template, `0x02000000` for a user template, instead of `0x18000000` and `0x82000000`): MS-CRTD has no flag for a CN of the CA's choosing, and the request's subject is still ignored. This announcement has not been tried against a Windows client yet.

### Windows enrollment profiles: changing the domain of a connector

When a save of an AD connector (**Settings → Active Directory**) changes the domain of its base DN, each profile that uses the connector is looked at first. A profile without keytab whose realm was the old domain takes the new domain as its realm, in the same save, and the audit entry of the connector names it. A profile with no realm, or already on the new domain, is left as is. Any other profile refuses the save (409) with its name: a profile with a keytab, whose keytab fixes its realm; a profile whose realm was not the old domain; a profile that cannot take the new realm because another profile serves it. Nothing is written then, not even for the profiles that could follow. The 409 says what to do: for a profile with a keytab, whose realm can only be moved to another realm of its keytab or cleared, give it another connector (or none); for the others, change the realm of the profile or give it another connector. Then move the connector.

Nothing is refused at the moment of serving: a profile whose realm differs from the domain of its connector (for example after the connector was disabled and the realm came from the SPN) keeps serving. The profile list and the editor flag it (`connector_domain_mismatch`), and the setup checklist of the editor warns.

---

## User Administration

### Initial administrator password

UCM has no default password. When the database holds no user, the start creates the first administrator, `INITIAL_ADMIN_USERNAME` (`admin`), exempt from forced 2FA enrolment, with a password from one source:

| Source | Set by | Forced change | File written |
|--------|--------|---------------|--------------|
| `INITIAL_ADMIN_PASSWORD_FILE` | path of a file holding the password (Docker, Compose or Kubernetes secret); the line endings (CR, LF) at its end are dropped, any other character is kept | no | no |
| `INITIAL_ADMIN_PASSWORD` | the value itself | no | no |
| either one, with `INITIAL_ADMIN_PASSWORD_FORCE_CHANGE=1` | a deployment tool that drew the value (the Helm chart, for the one it generates) | yes, at first login | no |
| generated | neither is set | yes, at first login | `DATA_DIR/initial-admin-password` |

- **Priority.** None: both set refuses the start (`INITIAL_ADMIN_PASSWORD and INITIAL_ADMIN_PASSWORD_FILE are both set: keep only one`), since which one was meant cannot be guessed. A `_FILE` that cannot be read or is empty refuses the start too, naming the path; UCM never falls back to generating a password the operator did not expect.
- **Password policy.** A provided password is used as provided, as before: the policy (Settings > Security) applies to every later change, and the start logs a warning, without the value, when the provided one does not meet it.
- **Generated password.** 24 characters drawn with Python `secrets` from 56 letters and digits without `0 O o 1 l I` (about 139 bits, no character to misread when copied). It is written atomically (temporary file, `fsync`, rename), mode 0600, owned by the service user, before the account exists: if the file cannot be written, the start fails with the reason and no account is created with a password nobody could read. Read it with `sudo cat /opt/ucm/data/initial-admin-password` (DEB/RPM) or `docker exec <container> cat /opt/ucm/data/initial-admin-password`.
- **First login.** The generated password opens a session that can only change its password (or log out), API and WebSocket included. The first successful change of that account's password, whichever way it is made (Account > Password, the API, an emailed reset link, another administrator's reset), deletes the file once the change is committed. Nothing deletes it after a delay.
- **Read once.** Once an account exists, none of the variables is read again, not even at a later start: a value left in `ucm.env` or in a secret neither blocks the start nor changes the account. Remove it after the first start.
- **Database reset.** Settings > Database > Reset Database (`POST /api/v2/system/database/reset`) recreates the administrator through the same rules, from the configuration at that moment. The source is settled before anything is dropped: an unreadable `_FILE` or an unwritable data directory answers 409 and resets nothing. The answer gives the command to read a generated password, never the value.
- **HA.** The account is created once, in the database, by the first node to start, under the startup lock: one node generates, one file exists. A row in `system_config` (`initial_admin.generated_password`) names the account and that node; it holds no password. At each start every node logs where the file is: `generated password in <path>` on the node that holds it, `its generated password file is on node <id>` on the others. A change made through another node removes the file through the cluster command `drop_initial_password` (no payload); a node that was down then removes it at its next start. Each start and each such command keeps the local file only while its content still opens the account the row names.
- **Why nothing is logged.** Logs, journald and container output are copied to collectors, support bundles and screens; a password there outlives the file. The log, the installation message and the reset answer therefore give the path and the command, never the value. The value never reaches an API answer, the audit log or a cluster command either.

#### Initial password lost before the first login

Nobody can log in to use the database reset or another administrator's password reset, and nothing has been configured yet: start again from an empty database. Stop UCM, remove the SQLite file `DATA_DIR/ucm.db` (with PostgreSQL, drop and recreate the database), start UCM: the first start creates the administrator and a new file. Once someone has logged in, the usual procedures apply: **Users > Reset Password** by another administrator, or the emailed reset link.


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
