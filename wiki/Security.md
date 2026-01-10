# Security

Ultimate CA Manager v1.8.2 implements comprehensive security features to protect your Certificate Authority infrastructure.

## Authentication Methods

### Password Authentication

**Requirements:**
- Minimum 8 characters
- Password hashing with Werkzeug (PBKDF2/SHA-256)
- Session management with secure cookies

**Best Practices:**
```python
# Strong password requirements (recommended)
- Minimum 12+ characters
- Mix of uppercase, lowercase, numbers, symbols
- No dictionary words
- Unique per user
```

### WebAuthn/FIDO2 (Passwordless)

**Supported Authenticators:**
- YubiKey (all models)
- Touch ID (macOS/iOS)
- Windows Hello
- Google Titan
- Any FIDO2-certified device

**Setup:**
1. Navigate to User Settings → Security
2. Click "Register Security Key"
3. Follow browser prompts
4. Name your key for identification

**Features:**
- Phishing-resistant authentication
- Hardware-backed credentials
- Biometric support
- Multiple keys per user

See: [WebAuthn Support](WebAuthn-Support.md)

### mTLS Client Certificates

**Configuration:**
- Native Gunicorn mTLS support
- Reverse proxy delegation (nginx/Apache)
- Automatic user mapping

**Setup (Native):**
```bash
# Generate client certificate
ucm-cli create-cert --type client --cn "admin@example.com"

# Configure Gunicorn
GUNICORN_CERTFILE=/path/to/server.crt
GUNICORN_KEYFILE=/path/to/server.key
GUNICORN_CA_CERTS=/path/to/ca.crt
GUNICORN_VERIFY_MODE=CERT_REQUIRED
```

**Setup (Nginx Proxy):**
```nginx
server {
    ssl_client_certificate /path/to/ca.crt;
    ssl_verify_client on;
    
    location / {
        proxy_set_header X-Client-Cert $ssl_client_cert;
        proxy_pass http://ucm-backend;
    }
}
```

See: [mTLS Authentication](MTLS-Authentication.md)

## Authorization & Access Control

### Role-Based Access Control (RBAC)

**Built-in Roles:**
- **Admin**: Full system access
- **Operator**: Certificate management, no system config
- **Viewer**: Read-only access

**Permission Matrix:**

| Action | Admin | Operator | Viewer |
|--------|-------|----------|--------|
| Create certificates | ✅ | ✅ | ❌ |
| Revoke certificates | ✅ | ✅ | ❌ |
| View certificates | ✅ | ✅ | ✅ |
| Manage users | ✅ | ❌ | ❌ |
| System config | ✅ | ❌ | ❌ |
| Export CA keys | ✅ | ❌ | ❌ |

### API Authentication

**JWT Token-Based:**
```bash
# Get token
curl -X POST https://ca.example.com/api/auth/login \
  -d '{"username":"admin","password":"secret"}'

# Use token
curl -H "Authorization: Bearer eyJ0eXAiOiJKV1..." \
  https://ca.example.com/api/certificates
```

**Token Security:**
- 1-hour expiration (configurable)
- Refresh token support
- Automatic revocation on logout
- Per-user token tracking

## Cryptographic Security

### Private Key Protection

**Storage Security:**
- AES-256 encryption at rest
- Encrypted with master key
- Restricted file permissions (600)
- No keys in database

**Master Key Management:**
```bash
# Location (protect this!)
/opt/ucm/instance/master.key

# Permissions
chmod 600 /opt/ucm/instance/master.key
chown ucm:ucm /opt/ucm/instance/master.key
```

### Key Generation

**RSA Keys:**
- Minimum 2048 bits (default 4096)
- Secure random number generation
- OpenSSL-based

**ECDSA Keys:**
- P-256, P-384, P-521 curves
- Preferred for performance
- Recommended: P-384

**Generation Example:**
```python
# Strong RSA key
openssl genrsa -out ca.key 4096

# ECDSA key (faster, smaller)
openssl ecparam -name secp384r1 -genkey -out ca.key
```

### Certificate Validation

**Signature Verification:**
- All certificates validated against CA chain
- CRL/OCSP checking for revocation
- Extension validation (key usage, EKU)

**ACME Security:**
- Challenge validation (HTTP-01, DNS-01)
- Account key verification
- Rate limiting per account

## Network Security

### HTTPS Configuration

**TLS Settings (Production):**
```python
# Flask-Talisman security headers
FORCE_HTTPS = True
STRICT_TRANSPORT_SECURITY = True
HSTS_MAX_AGE = 31536000  # 1 year
HSTS_INCLUDE_SUBDOMAINS = True
```

**Cipher Suites:**
```nginx
# Recommended (nginx)
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers 'ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384';
ssl_prefer_server_ciphers on;
```

### Firewall Rules

**Required Ports:**
```bash
# Web interface
ufw allow 443/tcp

# OCSP responder (if enabled)
ufw allow 2560/tcp

# ACME/SCEP (via HTTPS)
# No additional ports needed
```

**Recommended Restrictions:**
```bash
# Limit to specific networks
ufw allow from 10.0.0.0/8 to any port 443 proto tcp
ufw allow from 192.168.0.0/16 to any port 443 proto tcp
```

## Session Security

### Session Management

**Configuration:**
```python
SESSION_COOKIE_SECURE = True      # HTTPS only
SESSION_COOKIE_HTTPONLY = True    # No JavaScript access
SESSION_COOKIE_SAMESITE = 'Lax'   # CSRF protection
PERMANENT_SESSION_LIFETIME = 3600  # 1 hour
```

**Session Features:**
- Automatic timeout after inactivity
- Secure cookie encryption
- CSRF token protection
- Session invalidation on logout

### CSRF Protection

**Automatic Protection:**
- All POST/PUT/DELETE requests protected
- Token embedded in forms
- Flask-WTF integration

**API Exemptions:**
```python
# API endpoints use JWT, not CSRF
/api/*  # Exempt from CSRF (uses Bearer token)
```

## Data Security

### Database Encryption

**Sensitive Data:**
- Private keys: AES-256 encrypted
- Passwords: PBKDF2/SHA-256 hashed
- API tokens: Hashed with salt

**Encryption at Rest:**
```bash
# Enable full disk encryption (recommended)
cryptsetup luksFormat /dev/sdb
cryptsetup open /dev/sdb ucm-data
mkfs.ext4 /dev/mapper/ucm-data
```

### Backup Security

**Backup Encryption:**
```bash
# Encrypted backup
cd /opt/ucm
./backup.sh --encrypt --password "strong-password"

# Restore encrypted backup
./restore.sh --decrypt ucm-backup-*.tar.gz.enc
```

**Backup Storage:**
- Store offsite in secure location
- Encrypt backups at rest
- Restrict access to backup files
- Test restoration regularly

See: [Backup & Restore](Backup-Restore.md)

## Audit Logging

### Security Events Logged

**Authentication:**
- Successful/failed logins
- WebAuthn registration/usage
- mTLS certificate authentication
- Password changes

**Certificate Operations:**
- Certificate issuance
- Certificate revocation
- CRL generation
- OCSP queries

**Administrative:**
- User creation/deletion
- Role changes
- System configuration changes
- Backup/restore operations

### Log Locations

```bash
# Application logs
/opt/ucm/logs/ucm.log

# System logs
journalctl -u ucm

# Nginx access logs (if using proxy)
/var/log/nginx/access.log
```

### Log Monitoring

```bash
# Monitor authentication failures
grep "Failed login" /opt/ucm/logs/ucm.log

# Recent certificate operations
grep "Certificate" /opt/ucm/logs/ucm.log | tail -20

# Administrative actions
grep "Admin" /opt/ucm/logs/ucm.log
```

## Security Hardening

### System Hardening

**User Isolation:**
```bash
# Run as dedicated user
sudo useradd -r -s /bin/false ucm
sudo chown -R ucm:ucm /opt/ucm

# Restrict permissions
chmod 700 /opt/ucm/instance
chmod 600 /opt/ucm/instance/*.key
```

**SELinux/AppArmor:**
```bash
# Example AppArmor profile
/opt/ucm/bin/gunicorn {
  /opt/ucm/** r,
  /opt/ucm/instance/** rw,
  /opt/ucm/logs/** w,
}
```

### Application Hardening

**Rate Limiting:**
```python
# Login rate limit (built-in)
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = 900  # 15 minutes

# API rate limit
RATELIMIT_ENABLED = True
RATELIMIT_DEFAULT = "100/hour"
```

**Input Validation:**
- All user input sanitized
- SQL injection prevention (SQLAlchemy ORM)
- XSS protection (Jinja2 autoescaping)
- Path traversal prevention

**Security Headers:**
```python
# Flask-Talisman (enabled by default)
Content-Security-Policy
X-Frame-Options: SAMEORIGIN
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
```

### Reverse Proxy Hardening

**Nginx Security:**
```nginx
# Hide version
server_tokens off;

# Rate limiting
limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;

location /login {
    limit_req zone=login burst=10;
}

# Additional headers
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
```

## Vulnerability Management

### Security Updates

**Update Strategy:**
1. Monitor security advisories
2. Test updates in staging
3. Apply during maintenance window
4. Verify functionality post-update

**Update Commands:**
```bash
# Update UCM
cd /opt/ucm
git pull origin main
source venv/bin/activate
pip install --upgrade -r requirements.txt
flask db upgrade
sudo systemctl restart ucm
```

### Dependency Scanning

```bash
# Check for vulnerabilities
pip-audit

# Update dependencies
pip install --upgrade pip
pip install --upgrade -r requirements.txt
```

## Compliance & Standards

### Industry Standards

**Compliance:**
- RFC 5280 (X.509 certificates)
- RFC 6960 (OCSP)
- RFC 8555 (ACME)
- RFC 8894 (SCEP)
- FIPS 140-2 (cryptographic modules)

### Best Practices

1. **Key Management:**
   - Rotate CA certificates before expiration
   - Use hardware security modules (HSM) for production CAs
   - Implement key ceremony procedures

2. **Access Control:**
   - Enforce principle of least privilege
   - Regular access reviews
   - Multi-factor authentication for admins

3. **Monitoring:**
   - Real-time security event monitoring
   - Automated alerting for suspicious activity
   - Regular security audits

4. **Incident Response:**
   - Document incident response procedures
   - Test recovery procedures
   - Maintain offline backups

## Security Checklist

### Pre-Production

- [ ] Change default admin password
- [ ] Enable HTTPS with valid certificate
- [ ] Configure firewall rules
- [ ] Enable WebAuthn/FIDO2
- [ ] Set up mTLS (if required)
- [ ] Configure audit logging
- [ ] Encrypt backups
- [ ] Restrict file permissions
- [ ] Enable rate limiting
- [ ] Configure security headers

### Ongoing

- [ ] Monitor security logs daily
- [ ] Review user access monthly
- [ ] Update dependencies monthly
- [ ] Test backups monthly
- [ ] Audit certificate usage quarterly
- [ ] Review security policies annually
- [ ] Conduct penetration testing annually

## Incident Response

### Suspected Compromise

**Immediate Actions:**
1. Isolate system from network
2. Review audit logs
3. Identify compromised certificates
4. Revoke affected certificates
5. Update CRL/OCSP
6. Notify affected parties

**Investigation:**
```bash
# Check recent logins
grep "login" /opt/ucm/logs/ucm.log | tail -50

# Recent certificate operations
grep "issued\|revoked" /opt/ucm/logs/ucm.log

# System access
last -a | head -20
```

### Recovery

1. Restore from clean backup
2. Regenerate compromised keys
3. Issue new certificates
4. Update security controls
5. Document lessons learned

## See Also

- [WebAuthn Support](WebAuthn-Support.md) - Passwordless authentication
- [mTLS Authentication](MTLS-Authentication.md) - Client certificate auth
- [User Management](User-Management.md) - User administration
- [Backup & Restore](Backup-Restore.md) - Backup security
- [Monitoring](Monitoring.md) - Security monitoring
