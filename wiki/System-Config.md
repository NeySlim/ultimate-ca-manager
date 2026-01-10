# System Configuration

**Version:** 1.8.2

## Overview

System-wide configuration via Web UI (System Settings).

## Categories

### General
- FQDN
- Ports (HTTPS/HTTP)
- Session timeout
- UI language

### Authentication
- Password policy (length, complexity)
- Session duration
- ☑ Require WebAuthn
- ☑ Allow password reset

### ACME
- ☑ Enable ACME server
- Challenge timeout
- Rate limiting
- Default CA for ACME

### SCEP
- ☑ Enable SCEP server
- ☑ Auto-approve from IP ranges
- Challenge password
- Default certificate validity

### OCSP
- ☑ Enable OCSP per CA
- Response validity period
- ☑ Require nonce

### CRL
- ☑ Auto-generate on revocation
- CDP URL template
- CRL validity period

### Email
- SMTP server
- Port (25, 587, 465)
- TLS/SSL
- From address
- ☑ Enable expiration notifications

### Backup
- Backup schedule
- Retention period
- Storage location
- ☑ Include private keys (encrypted)

See [Configuration](Configuration) for environment variables.
