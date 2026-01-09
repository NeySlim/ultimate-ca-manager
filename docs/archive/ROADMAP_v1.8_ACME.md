# UCM v1.8.0-beta - ACME with step-ca Integration

**Feature:** Local ACME server implementation with step-ca compatibility  
**Status:** Planning  
**Target:** v1.8.0-beta

---

## 🎯 Objectives

Provide a **local ACME server** compatible with standard ACME clients (certbot, acme.sh, etc.) and integrate with **step-ca** for advanced features.

### **Why ACME + step-ca?**

1. **Automatic certificate issuance** for internal infrastructure
2. **Let's Encrypt workflow** for private networks
3. **step-ca integration** for advanced CA features
4. **Auto-renewal** with standard ACME clients
5. **Zero-touch certificate management**

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    ACME Clients                         │
│  (certbot, acme.sh, lego, Traefik, nginx, etc.)       │
└─────────────────┬───────────────────────────────────────┘
                  │ HTTPS (RFC 8555)
                  ▼
┌─────────────────────────────────────────────────────────┐
│              UCM ACME Server                            │
│  ┌──────────────────────────────────────────────────┐  │
│  │  ACME Endpoints (RFC 8555)                       │  │
│  │  - /acme/directory                               │  │
│  │  - /acme/new-nonce                               │  │
│  │  - /acme/new-account                             │  │
│  │  - /acme/new-order                               │  │
│  │  - /acme/authz/{id}                              │  │
│  │  - /acme/challenge/{id}                          │  │
│  │  - /acme/finalize/{id}                           │  │
│  │  - /acme/cert/{id}                               │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Challenge Validators                            │  │
│  │  - HTTP-01 (http://.well-known/acme-challenge/) │  │
│  │  - DNS-01 (TXT _acme-challenge.example.com)     │  │
│  │  - TLS-ALPN-01 (optional)                        │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│              UCM Certificate Engine                     │
│  - CA selection                                         │
│  - Certificate signing (existing code)                  │
│  - Storage & tracking                                   │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│          Optional: step-ca Integration                  │
│  - Use step-ca as backend CA                           │
│  - Leverage step-ca provisioners                        │
│  - Advanced features (SSH certs, etc.)                  │
└─────────────────────────────────────────────────────────┘
```

---

## 📚 Implementation Phases

### **Phase 1: ACME Core (RFC 8555)**
*Duration: 2-3 weeks*

#### 1.1 ACME Directory & Nonces
- [ ] Implement `/acme/directory` endpoint (list of ACME endpoints)
- [ ] Implement `/acme/new-nonce` (replay protection)
- [ ] JWS signature validation
- [ ] Nonce storage and validation

#### 1.2 Account Management
- [ ] `/acme/new-account` - ACME account registration
- [ ] Account key binding (JWK)
- [ ] Contact information (email)
- [ ] Terms of Service agreement
- [ ] Account database schema
- [ ] Account key rollover support

#### 1.3 Order & Authorization
- [ ] `/acme/new-order` - Certificate order creation
- [ ] Order lifecycle (pending → ready → processing → valid)
- [ ] Authorization objects
- [ ] Identifier validation (DNS, IP)
- [ ] Order expiration handling

#### 1.4 Challenge System - HTTP-01
- [ ] HTTP-01 challenge generation
- [ ] Challenge token storage
- [ ] Validation endpoint (port 80 or custom)
- [ ] Challenge verification logic
- [ ] Challenge cleanup

#### 1.5 Certificate Issuance
- [ ] `/acme/finalize/{order}` - CSR submission
- [ ] CSR validation (key type, signature)
- [ ] Certificate signing via UCM CA
- [ ] `/acme/cert/{cert}` - Certificate download
- [ ] Certificate chain inclusion

---

### **Phase 2: DNS-01 Challenge**
*Duration: 1-2 weeks*

- [ ] DNS-01 challenge generation
- [ ] Integration with DNS providers APIs:
  - [ ] Cloudflare
  - [ ] PowerDNS
  - [ ] Bind9 (nsupdate)
  - [ ] Route53
  - [ ] Generic webhook
- [ ] TXT record validation
- [ ] Wildcard certificate support
- [ ] Multi-domain SAN support

---

### **Phase 3: step-ca Integration**
*Duration: 1-2 weeks*

#### 3.1 step-ca Backend Option
- [ ] Use step-ca as CA backend (optional)
- [ ] step-ca API client
- [ ] Provisioner mapping
- [ ] Certificate template integration

#### 3.2 Advanced Features
- [ ] SSH certificate support via step-ca
- [ ] OIDC/OAuth provisioning
- [ ] X.509 certificate templates
- [ ] Policy enforcement

---

### **Phase 4: Management UI**
*Duration: 1 week*

- [ ] ACME configuration page
  - [ ] Enable/disable ACME
  - [ ] Select CA for ACME
  - [ ] Configure challenges (HTTP-01, DNS-01)
  - [ ] DNS provider settings
- [ ] ACME accounts list
- [ ] Active orders monitoring
- [ ] Challenge status dashboard
- [ ] Certificate issued via ACME list
- [ ] Revocation via ACME

---

### **Phase 5: Client Integration Examples**
*Duration: 1 week*

#### Documentation & Examples
- [ ] certbot configuration example
- [ ] acme.sh integration
- [ ] Traefik ACME config
- [ ] nginx + acme.sh
- [ ] Docker auto-renewal
- [ ] Kubernetes cert-manager

---

## 🔧 Technical Stack

### **Python Libraries**
```python
# ACME Protocol
acme==2.9.0                 # Official ACME library
josepy==1.14.0              # JWS/JWK handling
cryptography>=46.0.3        # Already installed

# DNS Providers
dnspython==2.6.1           # DNS queries
python-cloudflare==0.0.5   # Cloudflare API
boto3==1.34.0              # AWS Route53
requests>=2.32.5           # Already installed
```

### **Database Schema**
```sql
-- ACME Accounts
CREATE TABLE acme_accounts (
    id INTEGER PRIMARY KEY,
    account_id TEXT UNIQUE NOT NULL,
    key_jwk TEXT NOT NULL,            -- JWK public key
    contact TEXT,                      -- JSON array of emails
    status TEXT DEFAULT 'valid',       -- valid, deactivated, revoked
    terms_agreed BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ACME Orders
CREATE TABLE acme_orders (
    id INTEGER PRIMARY KEY,
    order_id TEXT UNIQUE NOT NULL,
    account_id TEXT NOT NULL,
    status TEXT DEFAULT 'pending',     -- pending, ready, processing, valid, invalid
    identifiers TEXT NOT NULL,         -- JSON array
    not_before DATETIME,
    not_after DATETIME,
    error TEXT,
    certificate_id INTEGER,            -- FK to certificates table
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL,
    FOREIGN KEY (account_id) REFERENCES acme_accounts(account_id),
    FOREIGN KEY (certificate_id) REFERENCES certificates(id)
);

-- ACME Authorizations
CREATE TABLE acme_authorizations (
    id INTEGER PRIMARY KEY,
    authz_id TEXT UNIQUE NOT NULL,
    order_id TEXT NOT NULL,
    identifier TEXT NOT NULL,          -- domain or IP
    identifier_type TEXT NOT NULL,     -- dns, ip
    status TEXT DEFAULT 'pending',
    expires_at DATETIME NOT NULL,
    wildcard BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES acme_orders(order_id)
);

-- ACME Challenges
CREATE TABLE acme_challenges (
    id INTEGER PRIMARY KEY,
    challenge_id TEXT UNIQUE NOT NULL,
    authz_id TEXT NOT NULL,
    type TEXT NOT NULL,                -- http-01, dns-01, tls-alpn-01
    status TEXT DEFAULT 'pending',     -- pending, processing, valid, invalid
    token TEXT NOT NULL,
    key_authorization TEXT NOT NULL,
    validated_at DATETIME,
    error TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (authz_id) REFERENCES acme_authorizations(authz_id)
);

-- ACME Nonces (short-lived)
CREATE TABLE acme_nonces (
    nonce TEXT PRIMARY KEY,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL
);
CREATE INDEX idx_nonces_expires ON acme_nonces(expires_at);
```

---

## 🎨 UI Mockups

### ACME Configuration Page
```
┌────────────────────────────────────────────────────┐
│ ACME Server Configuration                          │
├────────────────────────────────────────────────────┤
│                                                    │
│ [✓] Enable ACME Server                            │
│                                                    │
│ ACME Directory URL:                                │
│ https://ucm.local:8443/acme/directory             │
│ [Copy URL]                                         │
│                                                    │
│ Default CA for ACME:                               │
│ [Select CA ▼] → Internal CA                       │
│                                                    │
│ Enabled Challenges:                                │
│ [✓] HTTP-01 (Port 80)                             │
│ [✓] DNS-01                                        │
│ [ ] TLS-ALPN-01                                   │
│                                                    │
│ DNS Provider Configuration:                        │
│ Provider: [Cloudflare ▼]                          │
│ API Token: [****************]                     │
│                                                    │
│ [Save Configuration]                               │
└────────────────────────────────────────────────────┘
```

---

## 📦 Deliverables (v1.8.0-beta)

### Minimum Viable Product (MVP)
- ✅ ACME directory endpoint
- ✅ Account registration
- ✅ HTTP-01 challenge
- ✅ Order/Authorization flow
- ✅ Certificate issuance
- ✅ Basic UI configuration

### Nice to Have
- 🎯 DNS-01 challenge
- 🎯 Multiple DNS providers
- 🎯 step-ca backend option
- 🎯 Wildcard certificates
- 🎯 Client examples documentation

---

## 🧪 Testing Plan

### Unit Tests
- JWS signature validation
- Nonce generation & validation
- Challenge token generation
- HTTP-01 validation logic
- DNS-01 validation logic

### Integration Tests
- certbot integration
- acme.sh integration
- Full ACME flow (account → order → challenge → cert)
- Multi-domain certificates

### Manual Testing
- Traefik auto-SSL
- nginx + acme.sh
- Kubernetes cert-manager

---

## 📖 References

- **RFC 8555**: Automatic Certificate Management Environment (ACME)
- **step-ca**: https://github.com/smallstep/certificates
- **certbot**: https://certbot.eff.org/
- **acme.sh**: https://github.com/acmesh-official/acme.sh
- **Traefik ACME**: https://doc.traefik.io/traefik/https/acme/

---

## 🚀 Timeline

- **Week 1-2**: Phase 1 - ACME Core implementation
- **Week 3**: Phase 2 - DNS-01 challenge
- **Week 4**: Phase 3 - step-ca integration (optional)
- **Week 5**: Phase 4 - Management UI
- **Week 6**: Phase 5 - Documentation & testing

**Total Duration**: ~6 weeks for full implementation  
**Beta Release**: Phase 1 complete (HTTP-01 only) = 2-3 weeks

---

## ❓ Open Questions

1. **step-ca deployment**: Include step-ca binary or use existing installation?
2. **Challenge validation port**: Use standard port 80 or configurable?
3. **DNS provider priority**: Which providers to support first?
4. **Certificate validity**: Default validity for ACME certs (90 days like Let's Encrypt)?
5. **Rate limiting**: Apply rate limits like Let's Encrypt?

---

**Status**: 📝 Planning  
**Next Step**: Start Phase 1 implementation  
**Updated**: 2026-01-08
