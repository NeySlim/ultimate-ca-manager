# Configuration

**Version:** 1.8.2

Quick guide to UCM configuration options.

## Environment Variables

Main configuration in `.env` file (Docker) or system environment (native).

### Core Settings
```bash
BASE_DIR=/opt/ucm              # Installation directory
DATA_DIR=/opt/ucm/data         # Data storage
FQDN=ucm.example.com           # Server FQDN
HTTPS_PORT=8443                # HTTPS port
HTTP_PORT=8080                 # HTTP port (redirects to HTTPS)
```

### Database
```bash
SQLALCHEMY_DATABASE_URI=sqlite:///data/ucm.db
```

### Security
```bash
SECRET_KEY=your-secret-key           # Flask sessions
JWT_SECRET_KEY=your-jwt-secret       # API tokens
SESSION_TIMEOUT=3600                 # 1 hour
```

### Features
```bash
SCEP_ENABLED=true
ACME_ENABLED=true
OCSP_ENABLED=true
CRL_AUTO_REGEN=true
EMAIL_NOTIFICATIONS=true
```

See [System-Config](System-Config) for web UI configuration.
