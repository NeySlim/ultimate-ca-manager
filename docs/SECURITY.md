# Security Documentation

Ultimate CA Manager implements comprehensive security features to protect your PKI infrastructure.

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
| 2.1.0 | 2026-02-19 | SSO (LDAP/OAuth2/SAML) with rate limiting, LDAP filter injection fix, CSRF on SSO endpoints, 4-role RBAC (admin/operator/auditor/viewer), 28 SSO security tests |
| 2.0.2 | 2026-01-31 | Private key encryption, CSRF, password policy, rate limiting |
| 2.0.0 | 2026-01-29 | Initial security framework, session auth, RBAC |
