# Security Documentation

Ultimate Certificate Manager implements comprehensive security features to protect your PKI infrastructure.

## Security Features

### 1. Private Key Encryption

All private keys (CA and certificate) are encrypted at rest using **Fernet** encryption (AES-256-CBC with HMAC-SHA256).

#### Configuration

Private key encryption is managed from **Settings** > **Security** in the web UI. The master key is stored at `/etc/ucm/master.key`.

Alternatively, via API (using session cookies):

```bash
# Encrypt existing keys (dry run first)
curl -k -b cookies.txt -X POST https://localhost:8443/api/v2/system/security/encrypt-all-keys \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'

# Then actually encrypt
curl -k -b cookies.txt -X POST https://localhost:8443/api/v2/system/security/encrypt-all-keys \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}'
```

#### Key Storage
- Keys stored encrypted in database with `ENC:` prefix
- Decrypted only when needed (export, signing)
- Original keys never logged

---

### 2. CSRF Protection

Cross-Site Request Forgery protection for all state-changing requests.

#### Token Flow
1. Login/verify response includes `csrf_token`
2. Client stores token in `sessionStorage`
3. Client sends `X-CSRF-Token` header on POST/PUT/DELETE/PATCH
4. Server validates token signature and expiry

#### Token Format
```
timestamp:nonce:hmac_signature
```
- Valid for 24 hours
- Signed with SECRET_KEY

#### Exempt Paths
- `/api/v2/auth/login` (needs to get token)
- `/acme/`, `/scep/`, `/ocsp`, `/cdp/` (protocol endpoints)
- `/api/health` (monitoring)

---

### 3. Password Policy

Strong password enforcement for all user accounts.

#### Requirements
| Rule | Value |
|------|-------|
| Minimum length | 8 characters |
| Maximum length | 128 characters |
| Uppercase required | Yes |
| Lowercase required | Yes |
| Digit required | Yes |
| Special character required | Yes |
| Special chars allowed | `!@#$%^&*()_+-=[]{}|;:,.<>?` |

#### Blocked Patterns
- Common passwords (password123, admin, etc.)
- 4+ sequential characters (abcd, 1234)
- 4+ repeated characters (aaaa, 1111)

#### API Endpoints
```bash
# Get policy
GET /api/v2/users/password-policy

# Check strength (returns score 0-100)
POST /api/v2/users/password-strength
{"password": "MyP@ssw0rd!"}
```

---

### 4. Rate Limiting

Protection against brute force and DoS attacks.

#### Default Limits

| Endpoint Pattern | Requests/min | Burst |
|-----------------|--------------|-------|
| `/api/v2/auth/login` | 10 | 3 |
| `/api/v2/auth/register` | 5 | 2 |
| `/api/v2/certificates/issue` | 30 | 5 |
| `/api/v2/cas` | 30 | 5 |
| `/api/v2/backup` | 5 | 2 |
| `/api/v2/users` | 60 | 10 |
| `/api/v2/certificates` | 120 | 20 |
| `/acme/`, `/scep/` | 300 | 50 |
| `/ocsp`, `/cdp/` | 500 | 100 |
| Default | 120 | 20 |

#### Response Headers
```
X-RateLimit-Limit: 120
X-RateLimit-Remaining: 115
X-RateLimit-Reset: 1706789123
```

#### When Limited (429)
```json
{
  "success": false,
  "error": "Rate limit exceeded",
  "retry_after": 45
}
```

#### Configuration
```bash
# Get config and stats
GET /api/v2/system/security/rate-limit

# Add IP whitelist
PUT /api/v2/system/security/rate-limit
{"whitelist_add": ["192.168.1.100"]}

# Reset counters for IP
POST /api/v2/system/security/rate-limit/reset
{"ip": "192.168.1.50"}
```

---

### 5. Audit Logging

Comprehensive logging of all security-relevant actions.

#### Logged Actions
- Authentication (login, logout, failures)
- User management (create, update, delete)
- Certificate operations (issue, revoke, export)
- CA operations (create, delete, sign)
- Settings changes
- Security events (rate limited, permission denied)

#### Retention Policy
```bash
# Get retention settings
GET /api/v2/system/audit/retention

# Update retention (days)
PUT /api/v2/system/audit/retention
{"retention_days": 365, "auto_cleanup": true}

# Manual cleanup
POST /api/v2/system/audit/cleanup
{"retention_days": 90}
```

Default: 90 days, auto-cleanup daily at midnight.

---

### 6. Certificate Expiry Alerts

Proactive email notifications before certificates expire.

#### Alert Schedule
- 30 days before expiry
- 14 days before expiry
- 7 days before expiry
- 1 day before expiry

#### Configuration
```bash
# Get settings
GET /api/v2/system/alerts/expiry

# Update settings
PUT /api/v2/system/alerts/expiry
{
  "enabled": true,
  "alert_days": [30, 14, 7, 1],
  "recipients": ["admin@example.com"]
}

# List expiring certificates
GET /api/v2/system/alerts/expiring-certs?days=30

# Manual check
POST /api/v2/system/alerts/expiry/check
```

Requires SMTP configuration in Settings > Email.

---

### 7. SSRF Protection (v2.52+)

Network scan endpoints (discovery, SSL checker) are protected against SSRF attacks:

- Private/loopback IP ranges blocked by default (127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
- DNS rebinding protection — resolved IPs are validated against the blocklist
- Configurable allowlist for internal network scanning use cases
- Cloud metadata endpoints (169.254.169.254) always blocked

### 8. WebAuthn Brute-Force Protection (v2.52+)

WebAuthn authentication includes rate limiting:

- Failed attempts tracked per user
- Account lockout after repeated failures
- Separate rate limit from password login

### 9. SSO Audit Logging (v2.52+)

All SSO authentication events are logged:

- Login attempts (success/failure) with provider type
- LDAP bind errors (generic messages to prevent enumeration)
- OAuth2/SAML token validation failures
- Session creation from SSO providers

### 10. v2.142 hardening pass

A consolidated audit landed in v2.142. All changes are operator-transparent except where noted in the right column.

| Area | Change | Action required |
|------|--------|-----------------|
| **HSM runtime installer** | `POST /api/v2/hsm/install-dependencies` is opt-in (`UCM_ALLOW_RUNTIME_PIP=1`), returns `403` by default | Set env var **or** install `python3-pkcs11` / `PyKCS11` via OS package manager. See [HSM_DOCKER.md](./HSM_DOCKER.md). |
| **Session directory perms** | Boot refuses to start if perms are not `0o700` (`RuntimeError: Refusing to boot: session dir <path> has perms <oct>, expected 0o700`) | DEB/RPM/Docker handle this; manual installs must `chown ucm:ucm <dir> && chmod 0700 <dir>` |
| **Reverse-proxy mTLS** (mTLS / EST / SCEP) | Proxy-injected `X-SSL-Client-*` headers only honoured from CIDRs in `security.trusted_proxies` | Set `security.trusted_proxies` if you terminate TLS on a reverse proxy; direct deployments unaffected |
| **CSV bulk import** (`/api/v2/users/import`) | Capped at 5 MB / 10 000 rows, returns `413` on overflow | Split larger imports |
| **CRL on-demand** (`/cdp/<ca>.crl`) | Per-CA serialisation lock, returns `503` + `Retry-After: 5` under contention | None — clients honour `Retry-After`. Cached CRL endpoint unaffected. |
| **Webhooks** | DNS revalidated at delivery time (closes DNS-rebinding window between config and delivery) | None — RFC1918/.lan/.local still allowed by design (on-prem) |
| **2FA backup codes** | Hashed at rest (Argon2id), atomic single-use consumption (`UPDATE ... WHERE hash = ? AND used_at IS NULL`) | None — re-generate codes after upgrade for fresh hashes |
| **Approval quorum** | Per-request DB lock, recount-in-transaction, idempotent re-submit | None |
| **ACME account keys** | Encrypted at rest with master key | None — migrated transparently on first read |
| **Audit IP** | `client_ip()` honours `X-Forwarded-For` only behind trusted proxy | None — same as mTLS row |
| **SCEP CSR copy** | KU/EKU stripped to whitelist (`digitalSignature`, `keyEncipherment`, `serverAuth`, `clientAuth`); arbitrary client-supplied bits are dropped | Use templates/policies for non-default usages |
| **EST endpoints** | Per-request `est_enabled` check returns `503 EST disabled` instead of falling through to SPA HTML | None |
| **Database commits** | All `api/v2/*` go through `safe_commit()` (rollback + log on failure) | None |

### Backend security helpers

The hardening pass also exposed reusable helpers in `backend/utils/`:

| Helper | Module | Purpose |
|--------|--------|---------|
| `is_request_from_trusted_proxy()` | `trusted_proxy` | Bool — true only if request comes from `security.trusted_proxies` CIDR |
| `client_ip()` | `trusted_proxy` | Resolves XFF only behind trusted proxy, else `remote_addr` |
| `reject_untrusted_proxy_headers()` | `trusted_proxy` | 401 helper for routes consuming proxy-injected headers |
| `validate_url_not_cloud_metadata()` | `ssrf_protection` | Default for user-supplied outbound URLs (webhooks, SSO, ACME proxy, imports) |
| `validate_url_not_private()` | `ssrf_protection` | Strict — only when target MUST be public Internet (rare) |
| `safe_commit()` | `safe_commit` | Wrapped `db.session.commit()` with rollback + log |
| `audit_event(action=..., ip=client_ip(), ...)` | `audit` | Shorthand for `AuditService.log_action` |
| `require_json_body` | `validation` | Decorator — 400 if body is missing/invalid JSON |
| `parse_request_pagination()` | `validation` | `(page, per_page)` from query string with bounds |

> **SSRF policy reminder.** UCM is on-prem. RFC1918, loopback, `.lan`/`.local`/`.corp` are the **primary use case**, not an attack vector. Use `validate_url_not_cloud_metadata` (blocks cloud-metadata + loopback only) for any user-supplied outbound URL — never `validate_url_not_private`, which would break LAN webhooks, internal SSO, and local ACME validation.

### 11. v2.152 hardening pass

Second consolidated audit. Operator-transparent unless noted.

| Area | Change | Action required |
|------|--------|-----------------|
| **OCSP (RFC 6960)** | Mixed-format serial lookup, cache invalidation on revoke, correct `keyHash`, `nonce` bypasses cache, delegated responder must carry `id-pkix-ocsp-nocheck` | None |
| **CRL (RFC 5280)** | AKI from signing CA SKI; IDP omitted on base+delta; FreshestCRL guarded; omit `unspecified` reasonCode; `removeFromCRL` delta-only; optional `invalidityDate`; unhold emits delta `removeFromCRL` when delta CRL enabled | Full relying-party path validation (§6) is out of scope |
| **Cert profile (RFC 5280)** | SKI/AKI never copied from CSR (forced from subject key + issuer SKI); EE/CA AKI from issuer SKI; CA AIA includes `caIssuers` when configured; BasicConstraints/KU hardening on CSR path | NameConstraints IP subset and policy/`anyPolicy` product choices remain |
| **ACME (RFC 8555/8737)** | EAB JWK match via thumbprint, JWS algorithm allowlist (asymmetric only), wildcard restricted to DNS-01, ALPN extension marked critical, case-insensitive domains; pre-authz §7.4.1 (migration `033`) | None |
| **TSA (RFC 3161/5035)** | `signing-certificate-v2` mandatory, body cap 64 KiB, correct `PKIStatus` separation | None |
| **EST (RFC 7030)** | `serverkeygen` encrypts the generated key under the **client mTLS pubkey**, not the issued cert | None |
| **SCEP (RFC 8894)** | Renewal rejected when signer cert expired or not yet valid | None |
| **CA/cert/CSR APIs** | Whitelisted key params, capped validity (≤3650 d), URL validation (CRL DP / AIA / OCSP / IDP), HSM key lock on bind, EC curve whitelist, CSR proof-of-possession (`is_signature_valid`) | None |
| **RBAC** | Reserved role names rejected (`admin`/`operator`/`viewer`), permission whitelist with wildcard, system roles immutable | Use custom role names |
| **SSO OIDC** | PKCE (S256) + nonce on auth flow | None |
| **HSM** | Provider secrets encrypted at rest, sign payload cap 1 MiB, FK-guarded deletes | None |
| **MSCA** | Fail-closed encryption, EOBO admin gate, audit, size caps | None |
| **Webhooks** | Secret encrypted at rest, event allowlist, reserved headers locked, events ≤64 per webhook | None |
| **Discovery** | Port validation, IPv6 subnet cap (≤1024), `update_profile` gated | None |
| **Audit** | Trusted-proxy XFF, post-cleanup integrity check | None |
| **Reports / SSH / Trust store** | Param caps, principal/extension caps, PEM size cap (256 KB), sync limit 1–1000 | None |
| **EAB** | HMAC keys encrypted at rest | None |
| **Imports** | CA / certificate import paths now encrypt private keys (silent regression fix) | None |
| **Decoder tools** | `tools/decode-csr` and `tools/decode-cert` capped at 256 KiB → `413` | None |
| **Users** | Self-change requires current password; `≥1 active admin` invariant enforced | None |

### 12. CA Offline Mode (v2.153)

Operators can now take any CA offline to prevent unauthorized signing. Two modes are exposed:

| Mode | Where the key lives | Restore input |
|------|--------------------|---------------|
| `password_protected` | UCM database, re-wrapped with `BestAvailableEncryption(password)` (PKCS#8) under the existing master-key wrap (two layers at rest) | Password only |
| `file_exported` | Returned to the operator as a single-layer password-encrypted PKCS#8 PEM; `ca.prv` set to `NULL` in the database | Password + re-uploaded `.key.pem` |

Threat model:
- **Stolen DB only** — `password_protected` keys remain encrypted under both the master key and the offline password. `file_exported` keys are absent entirely.
- **Stolen DB + master key** — `password_protected` keys still require the offline password. `file_exported` keys are absent.
- **Stolen offline file** — useless without the password (PKCS#8 password-encrypted; standard cryptography library hardening).
- **Forgotten password** — no recovery. The CA is unrecoverable. This is by design.

Sign/issue/CRL paths gate on `ca.offline` (see `services/ca/ca_signing.py:31`, `csrs.py:689`, `services/cert/mixins/csr.py`, `crl.py:97`). The `update_ca` endpoint can no longer flip the `offline` flag — only the dedicated `take_offline` / `restore` endpoints do, both of which require the password.

Audit actions: `ca.offline.password_protected`, `ca.offline.file_exported`, `ca.restore.password_protected`, `ca.restore.file_exported`. The legacy free-text "offline reason" field is no longer collected — the mode IS the audit record.

Password policy for the offline password is the same as the user password policy (12+ chars, mixed classes, no 4+ sequential).

---

## Security Best Practices

### 1. Initial Setup
```bash
# 1. Change default admin password immediately
# 2. Generate and set encryption key
# 3. Configure HTTPS with proper certificate
# 4. Set strong SECRET_KEY in /etc/ucm/ucm.env
```

### 2. Environment Variables
```bash
# /etc/ucm/ucm.env
SECRET_KEY=<random-64-char-string>
KEY_ENCRYPTION_KEY=<fernet-key>
FLASK_ENV=production
```

### 3. Network Security
- Run behind reverse proxy (nginx, Caddy)
- Enable firewall, restrict access to port 8443
- Use proper TLS certificate (not self-signed in production)

### 4. Backup Security
- Encrypted backups include encryption key
- Store backups securely off-server
- Test restore procedures regularly

---

## Security Monitoring

### Audit Dashboard
Access security metrics at Settings > Audit Logs:
- Failed login attempts
- Rate limited requests
- Permission denied events
- Certificate operations

### Scheduled Tasks
| Task | Interval | Description |
|------|----------|-------------|
| `audit_log_cleanup` | Daily | Remove old audit logs |
| `cert_expiry_alerts` | Daily | Send expiry notifications |
| `crl_auto_regen` | Hourly | Regenerate expiring CRLs |

---

## Reporting Security Issues

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT** create a public GitHub issue
2. Open a [GitHub Security Advisory](https://github.com/NeySlim/ultimate-ca-manager/security/advisories)
3. Include: description, steps to reproduce, impact assessment
4. Allow 90 days for fix before public disclosure

---

## Security Changelog

| Version | Date | Changes |
|---------|------|---------|
| Unreleased | 2026-07-17 | CSR SKI/AKI never copied from enrollee CSR; EE/CA AKI from issuer SKI; CA AIA `caIssuers`; CRL `invalidityDate`; unhold → delta `removeFromCRL` |
| 2.56 | 2026-07-17 | ACME/CSR certificates now include Extended Key Usage (serverAuth), empty subject populated from SAN |
| 2.55 | 2026-07-17 | DN format fix (RFC 4514), auto-migration corrects existing records |
| 2.52 | 2026-07-14 | SSRF protection, DNS rebinding prevention, WebAuthn brute-force protection, SSO audit logging, certificate discovery security |
| 2.1.0 | 2026-02-19 | SSO (LDAP/OAuth2/SAML) with rate limiting, LDAP filter injection fix, CSRF on SSO endpoints, 4-role RBAC (admin/operator/auditor/viewer), 28 SSO security tests |
| 2.0.2 | 2026-01-31 | Private key encryption, CSRF, password policy, rate limiting |
| 2.0.0 | 2026-01-29 | Initial security framework, session auth, RBAC |
