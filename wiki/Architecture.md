# Architecture

Ultimate CA Manager v1.8.2 is built on a modern, modular architecture designed for security, scalability, and maintainability.

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Web Interface (HTTPS)                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │Dashboard │  │  Certs   │  │  Users   │  │ Settings │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                      Flask Application                       │
│  ┌────────────────────────────────────────────────────────┐ │
│  │               Authentication Layer                      │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐            │ │
│  │  │ Password │  │ WebAuthn │  │   mTLS   │            │ │
│  │  └──────────┘  └──────────┘  └──────────┘            │ │
│  └────────────────────────────────────────────────────────┘ │
│                              │                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                  Core Modules                          │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐│ │
│  │  │   CA     │  │   ACME   │  │   SCEP   │  │  OCSP  ││ │
│  │  │  Engine  │  │  Server  │  │  Server  │  │Responder││ │
│  │  └──────────┘  └──────────┘  └──────────┘  └────────┘│ │
│  │                                                        │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐│ │
│  │  │  Crypto  │  │   API    │  │  Email   │  │  CRL   ││ │
│  │  │ Library  │  │ Handler  │  │  Notify  │  │  Gen   ││ │
│  │  └──────────┘  └──────────┘  └──────────┘  └────────┘│ │
│  └────────────────────────────────────────────────────────┘ │
│                              │                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              Data Access Layer (SQLAlchemy)            │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    Storage Layer                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   SQLite DB  │  │  Cert Store  │  │   Key Store  │      │
│  │  (Metadata)  │  │   (PEM/DER)  │  │  (Encrypted) │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

## Technology Stack

### Backend Framework

**Flask 3.0+**
- Lightweight WSGI web framework
- Modular blueprint architecture
- Jinja2 templating
- Werkzeug security utilities

**Key Extensions:**
- `Flask-SQLAlchemy`: ORM for database
- `Flask-Login`: User session management
- `Flask-WTF`: Form handling and CSRF protection
- `Flask-Migrate`: Database migrations

### Database

**SQLite (Default)**
- File-based database (`instance/ucm.db`)
- Zero configuration
- Suitable for small-to-medium deployments

**Schema Design:**
```
Users
├── id (PK)
├── username (unique)
├── password_hash
├── email
├── role (admin/operator/viewer)
└── webauthn_credentials (JSON)

Certificates
├── id (PK)
├── serial_number (unique)
├── common_name
├── type (server/client/ca)
├── status (valid/expired/revoked)
├── not_before
├── not_after
├── pem_data
├── created_by (FK → Users)
└── revocation_date

CertificateKeys
├── id (PK)
├── certificate_id (FK → Certificates)
└── encrypted_key (AES-256)

ACMEAccounts
├── id (PK)
├── kid (unique)
├── jwk (JSON)
└── contact (JSON)

ACMEOrders
├── id (PK)
├── account_id (FK → ACMEAccounts)
├── status
└── certificate_id (FK → Certificates)

SCEPProfiles
├── id (PK)
├── name (unique)
├── challenge
└── settings (JSON)
```

### Cryptographic Library

**cryptography (Python)**
- X.509 certificate generation
- Key pair generation (RSA, ECDSA, Ed25519)
- Certificate signing
- CRL generation
- OCSP response signing

**pyOpenSSL**
- Legacy certificate operations
- PKCS#12 export
- Certificate validation

**Key Features:**
- Constant-time operations (timing attack prevention)
- Secure random number generation
- FIPS 140-2 compliant algorithms

### Web Server

**Development: Flask Dev Server**
```bash
flask run --host=0.0.0.0 --port=5000
```

**Production: Gunicorn**
```bash
gunicorn --workers 4 \
  --bind 0.0.0.0:8443 \
  --certfile server.crt \
  --keyfile server.key \
  "app:create_app()"
```

**Features:**
- Multi-worker process management
- Native HTTPS support
- mTLS client certificate verification
- Graceful worker restart
- Request buffering

## Core Components

### CA Engine (`app/ca/engine.py`)

**Responsibilities:**
- Root/Intermediate CA initialization
- Certificate signing requests (CSR) processing
- Certificate issuance
- Certificate revocation
- CRL generation

**Key Methods:**
```python
class CAEngine:
    def create_certificate(self, csr, validity_days, extensions)
    def revoke_certificate(self, serial_number, reason)
    def generate_crl(self)
    def sign_ocsp_response(self, cert_status)
```

### ACME Server (`app/acme/`)

**RFC 8555 Implementation:**
- Account registration
- Order creation
- Authorization challenges (HTTP-01, DNS-01)
- Certificate issuance
- Certificate renewal

**Endpoints:**
```
/acme/directory         - Service discovery
/acme/new-nonce        - Nonce generation
/acme/new-account      - Account registration
/acme/new-order        - Order creation
/acme/authz/{id}       - Authorization
/acme/challenge/{id}   - Challenge validation
/acme/cert/{id}        - Certificate download
```

**Challenge Types:**
- **HTTP-01**: File on web server
- **DNS-01**: TXT record (external validation)

### SCEP Server (`app/scep/`)

**RFC 8894 Implementation:**
- PKI message processing
- Device enrollment
- Certificate renewal
- Challenge-based authentication

**Operations:**
```
GetCACert    - Retrieve CA certificate
PKIOperation - Enrollment/renewal requests
GetCRL       - CRL distribution
```

**Enrollment Flow:**
```
Device → GetCACert → Verify CA
       → Generate CSR
       → PKIOperation (CSR + Challenge)
       → Receive encrypted certificate
       → Install certificate
```

### OCSP Responder (`app/ocsp/`)

**RFC 6960 Implementation:**
- Real-time certificate status queries
- Signed responses
- Nonce support (replay prevention)

**Response Types:**
```
good     - Certificate valid
revoked  - Certificate revoked
unknown  - Certificate not found
```

**Performance:**
- In-memory status cache
- Asynchronous response signing
- Rate limiting

### Authentication System

**Multi-Factor Support:**

1. **Password (Primary)**
   - PBKDF2-SHA256 hashing
   - Salted hashes
   - Minimum complexity enforcement

2. **WebAuthn/FIDO2 (Optional)**
   - Public key cryptography
   - Challenge-response authentication
   - Attestation verification
   - Multiple authenticators per user

3. **mTLS (Optional)**
   - X.509 client certificates
   - DN-to-user mapping
   - Certificate chain validation

**Session Management:**
- Secure HTTP-only cookies
- 1-hour timeout (configurable)
- CSRF protection
- Session invalidation on logout

### API Layer (`app/api/`)

**RESTful Design:**
```
GET    /api/certificates       - List certificates
POST   /api/certificates       - Create certificate
GET    /api/certificates/{id}  - Get certificate details
DELETE /api/certificates/{id}  - Revoke certificate
POST   /api/auth/login         - Authenticate
POST   /api/auth/refresh       - Renew token
```

**Authentication:**
- JWT Bearer tokens
- 1-hour access token
- 7-day refresh token
- Token blacklist on logout

**Rate Limiting:**
- Token bucket algorithm
- Per-user quotas
- Configurable limits

## Data Flow

### Certificate Issuance Flow

```
User Request → Flask Route → Input Validation
    ↓
Form Processing → WTForms Validation
    ↓
Business Logic → Certificate Service
    ↓
Crypto Operations → CA Engine
    ├── Generate Key Pair (RSA/ECDSA)
    ├── Create Certificate
    ├── Sign with CA Key
    └── Store Certificate
    ↓
Database Persistence → SQLAlchemy ORM
    ├── Save Certificate Metadata
    └── Save Encrypted Private Key
    ↓
File Storage → Write PEM/DER Files
    ↓
Response → Return Certificate to User
```

### ACME Certificate Issuance

```
ACME Client → POST /acme/new-order
    ↓
Order Creation → Generate Authorizations
    ↓
Client → GET Authorization → Challenge Details
    ↓
Client → Fulfill Challenge (HTTP-01/DNS-01)
    ↓
Client → POST Challenge Ready
    ↓
Server → Validate Challenge
    ├── HTTP-01: Fetch /.well-known/acme-challenge/{token}
    └── DNS-01: Query _acme-challenge.{domain} TXT
    ↓
Validation Success → Update Order Status
    ↓
Client → POST Finalize Order (CSR)
    ↓
Server → Issue Certificate
    ↓
Client → GET Certificate
```

## Security Architecture

### Defense in Depth

**Layer 1: Network**
- HTTPS/TLS 1.2+ only
- Strong cipher suites
- Certificate pinning support
- Firewall rules

**Layer 2: Application**
- Input validation
- Output encoding
- CSRF protection
- Security headers (CSP, HSTS, X-Frame-Options)

**Layer 3: Authentication**
- Multi-factor authentication
- Strong password requirements
- Session timeout
- Account lockout

**Layer 4: Authorization**
- Role-based access control
- API token scoping
- Resource-level permissions

**Layer 5: Data**
- Encryption at rest (AES-256)
- Encrypted backups
- Secure key storage
- Audit logging

### Cryptographic Key Management

```
Master Key (AES-256)
    └── Stored: /opt/ucm/instance/master.key
    └── Permissions: 600 (ucm user only)
    └── Used to encrypt:
        ├── CA Private Key
        ├── Certificate Private Keys
        └── ACME Account Keys

CA Private Key (RSA 4096/ECDSA P-384)
    └── Encrypted with Master Key
    └── Stored in database
    └── Loaded to memory only when needed
    └── Cleared after use

Certificate Private Keys
    └── Encrypted individually
    └── Decrypted only for export
    └── Never logged
```

## Scalability Considerations

### Horizontal Scaling

**Current Limitations:**
- SQLite (single-file database)
- File-based certificate storage
- In-process OCSP cache

**Future Enhancements:**
- PostgreSQL/MySQL support
- Distributed certificate storage (S3/MinIO)
- Redis-based OCSP cache
- Multi-instance deployment

### Performance Optimization

**Database:**
- Indexed queries (serial_number, common_name)
- Connection pooling
- Query optimization

**Caching:**
- CA certificate caching
- OCSP response caching
- Static asset caching (nginx)

**Asynchronous Operations:**
- Email notifications (background tasks)
- CRL generation (scheduled)
- Certificate expiration checks (cron)

## Deployment Architectures

### Standalone Mode

```
┌──────────────────────┐
│   UCM Application    │
│  (Gunicorn + Flask)  │
│   Built-in HTTPS     │
│    Port 8443/tcp     │
└──────────────────────┘
```

**Use Case:** Small deployments, testing

### Reverse Proxy Mode

```
┌──────────────────────┐
│   Nginx/Apache       │
│   (HTTPS, mTLS)      │
│    Port 443/tcp      │
└──────────────────────┘
          │
          ↓
┌──────────────────────┐
│   UCM Application    │
│  (Gunicorn + Flask)  │
│   HTTP localhost     │
│    Port 8000/tcp     │
└──────────────────────┘
```

**Use Case:** Production deployments, load balancing

### Container Mode

```
┌────────────────────────────────────┐
│         Docker/Kubernetes          │
│  ┌──────────────┐  ┌────────────┐ │
│  │     UCM      │  │  Nginx     │ │
│  │  Container   │  │ Sidecar    │ │
│  └──────────────┘  └────────────┘ │
│         │                          │
│  ┌──────────────┐                 │
│  │   Volumes    │                 │
│  │ (Persistent) │                 │
│  └──────────────┘                 │
└────────────────────────────────────┘
```

**Use Case:** Cloud deployments, orchestration

## Directory Structure

```
/opt/ucm/
├── app/                      # Application code
│   ├── __init__.py          # Flask app factory
│   ├── models.py            # Database models
│   ├── routes/              # Route blueprints
│   │   ├── auth.py
│   │   ├── certificates.py
│   │   ├── dashboard.py
│   │   └── api.py
│   ├── ca/                  # CA engine
│   │   ├── engine.py
│   │   └── crypto.py
│   ├── acme/                # ACME server
│   │   ├── server.py
│   │   └── challenges.py
│   ├── scep/                # SCEP server
│   │   └── server.py
│   ├── ocsp/                # OCSP responder
│   │   └── responder.py
│   └── utils/               # Utilities
│       ├── email.py
│       ├── validators.py
│       └── decorators.py
├── instance/                # Instance-specific data
│   ├── ucm.db              # SQLite database
│   ├── certs/              # Certificate storage
│   │   ├── ca.crt
│   │   ├── ca.key (encrypted)
│   │   └── issued/
│   ├── master.key          # Master encryption key
│   └── config.py           # Instance config
├── migrations/              # Database migrations
├── static/                  # Static assets
│   ├── css/
│   ├── js/
│   └── themes/
├── templates/               # Jinja2 templates
│   ├── base.html
│   ├── dashboard.html
│   └── certificates/
├── logs/                    # Application logs
│   ├── ucm.log
│   ├── access.log
│   └── error.log
├── venv/                    # Python virtual environment
├── requirements.txt         # Python dependencies
└── config.py               # Configuration
```

## Extension Points

### Custom Authentication

```python
# app/auth/custom_provider.py
class CustomAuthProvider:
    def authenticate(self, username, password):
        # Custom logic (LDAP, OAuth, etc.)
        pass
```

### Custom Certificate Validators

```python
# app/ca/validators.py
class CustomValidator:
    def validate_csr(self, csr):
        # Custom CSR validation
        pass
```

### Webhook Integration

```python
# app/webhooks/handler.py
class WebhookHandler:
    def on_certificate_issued(self, cert):
        # Send webhook notification
        pass
```

## See Also

- [Building](Building.md) - Build instructions
- [Configuration](Configuration.md) - Configuration options
- [Security](Security.md) - Security architecture details
- [Contributing](Contributing.md) - Development guidelines
