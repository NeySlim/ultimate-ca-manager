# Ultimate CA Manager

![Version](https://img.shields.io/github/v/release/NeySlim/ultimate-ca-manager?label=version&color=brightgreen)
![Docker](https://img.shields.io/badge/docker-multi--arch-blue.svg)

**Web-based Certificate Authority management with PKI protocol support.**

UCM provides certificate lifecycle management, CA hierarchy, and industry-standard protocols (SCEP, OCSP, ACME, CRL/CDP) with multi-factor authentication.

**Multi-arch:** `linux/amd64`, `linux/arm64`

![Dashboard](https://raw.githubusercontent.com/NeySlim/ultimate-ca-manager/main/docs/screenshots/dashboard-dark.png)

---

## Quick Start

```bash
docker run -d \
  --name ucm \
  -p 8443:8443 \
  -v ucm-data:/opt/ucm/data \
  --restart unless-stopped \
  neyslim/ultimate-ca-manager:latest
```

**Access:** https://localhost:8443
**Credentials:** admin / changeme123 -- change immediately.

### Docker Compose

```yaml
services:
  ucm:
    image: neyslim/ultimate-ca-manager:latest
    container_name: ucm
    ports:
      - "8443:8443"
    volumes:
      - ucm-data:/opt/ucm/data
    environment:
      - UCM_FQDN=ucm.example.com
    restart: unless-stopped

volumes:
  ucm-data:
```

---

## Features

- **CA Management** -- Root and intermediate CAs, hierarchy view, import/export
- **Certificate Lifecycle** -- Issue, sign, revoke, renew, export (PEM, DER, PKCS#12)
- **CSR Management** -- Create, import, sign Certificate Signing Requests
- **Certificate Templates** -- Server, client, code signing, email presets
- **Certificate Toolbox** -- SSL checker, CSR/cert decoder, key matcher, format converter
- **Trust Store** -- Manage trusted root CA certificates
- **Chain Repair** -- AKI/SKI-based chain validation with automatic repair
- **SCEP** -- RFC 8894 device auto-enrollment
- **ACME** -- Let's Encrypt compatible (certbot, acme.sh)
- **OCSP** -- RFC 6960 real-time certificate status
- **CRL/CDP** -- Certificate Revocation List distribution
- **HSM** -- SoftHSM included, PKCS#11, Azure Key Vault, Google Cloud KMS
- **Authentication** -- Password, WebAuthn/FIDO2, TOTP 2FA, mTLS, API keys
- **SSO** -- LDAP/Active Directory, OAuth2 (Google, GitHub, Azure AD), SAML 2.0
- **RBAC** -- 4 system roles (Admin, Operator, Auditor, Viewer) + custom roles
- **Audit Logs** -- Action logging with integrity verification and remote syslog forwarding
- **6 Themes** -- 3 color schemes (Gray, Purple Night, Orange Sunset) × Light/Dark
- **i18n** -- 9 languages (EN, FR, DE, ES, IT, PT, UK, ZH, JA)
- **Real-time** -- WebSocket live updates

---

## Architecture

| Component | Technology |
|-----------|------------|
| Frontend | React 18, Vite, Radix UI |
| Backend | Python 3.11+, Flask, SQLAlchemy |
| Database | SQLite (PostgreSQL supported) |
| Server | Gunicorn + gevent WebSocket |
| Auth | Session cookies, WebAuthn/FIDO2, TOTP, mTLS |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `UCM_FQDN` | `ucm.example.com` | Server FQDN |
| `UCM_HTTPS_PORT` | `8443` | HTTPS port |
| `UCM_SECRET_KEY` | auto-generated | Session secret |
| `UCM_ACME_ENABLED` | `true` | Enable ACME protocol |
| `UCM_SMTP_ENABLED` | `false` | Enable email notifications |

---

## Tags

- `latest` -- Latest stable release
- Version tags (e.g. `2.48`, `2.49`)

## Image Details

- Base: Python 3.11 Alpine
- User: Non-root (UID 1000)
- Server: Gunicorn production WSGI
- Platforms: linux/amd64, linux/arm64

---

## Data Persistence

Mount `/opt/ucm/data` as a volume:

```bash
docker run -v ucm-data:/opt/ucm/data ...
```

Contents: SQLite database, HTTPS certificates, CA files, backups.

---

## Backup & Restore

```bash
# Backup
docker run --rm -v ucm-data:/data -v $(pwd):/backup \
  alpine tar czf /backup/ucm-backup.tar.gz -C /data .

# Restore
docker run --rm -v ucm-data:/data -v $(pwd):/backup \
  alpine tar xzf /backup/ucm-backup.tar.gz -C /data
```

---

## Migration Between Hosts

```bash
# Source
docker stop ucm
docker run --rm -v ucm-data:/data -v $(pwd):/backup \
  alpine tar czf /backup/ucm-data.tar.gz -C /data .
scp ucm-data.tar.gz user@new-host:~/

# Destination
docker volume create ucm-data
docker run --rm -v ucm-data:/data -v $(pwd):/backup \
  alpine tar xzf /backup/ucm-data.tar.gz -C /data
# Then start container as usual
```

---

## Documentation

- [README](https://github.com/NeySlim/ultimate-ca-manager)
- [Wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki)
- [CHANGELOG](https://github.com/NeySlim/ultimate-ca-manager/blob/main/CHANGELOG.md)
- [Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)

---

## License

BSD 3-Clause License
