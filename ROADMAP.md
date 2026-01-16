# 🗺️ UCM Roadmap

**Current Version:** v1.9.0 (2026-01-11)  
**Status:** Production Ready

---

## ✅ Completed (Since v1.6.1)

### v1.7.0 - ACME Protocol & Email Notifications
- ✅ **ACME Server** - RFC 8555 compliant (Let's Encrypt compatible)
- ✅ **Email Notifications** - Certificate expiration alerts
- ✅ **WebAuthn/FIDO2** - Hardware key passwordless authentication
- ✅ **CRL Enhancements** - Auto-generation, improved UI
- ✅ **SCEP Improvements** - Better device enrollment

### v1.8.0-v1.9.0 - UI & System Enhancements
- ✅ **mTLS Authentication** - Client certificate browser auth
- ✅ **REST API Completion** - Full JWT API coverage
- ✅ **OPNsense Import** - Direct CA/cert import from firewalls
- ✅ **Docker Multi-arch** - amd64/arm64 support
- ✅ **Theme System** - 8 beautiful themes (4 colors × light/dark)
- ✅ **Icon System Migration** - 220+ inline SVG → UCM icons
- ✅ **Login Page Redesign** - Modern UI with stats sidebar
- ✅ **Backup/Restore UI** - Complete web interface for backups
- ✅ **Smooth Animations** - Global transitions and polish

### v1.8.1 - v1.8.3 - Refinements
- ✅ **UI Consistency** - Unified button styles, theme indicators
- ✅ **Internationalization** - Full English translation
- ✅ **Auto-restart** - Service auto-restart after config changes
- ✅ **Workflow Optimization** - CI/CD improvements, source tarballs
- ✅ **Screenshots Gallery** - Complete visual documentation
- ✅ **Universal Installer** - One-line install for all Linux distros

---

## ✅ Completed

### v1.9.0 - UI Modernization & System Enhancements (Beta: 2026-01-16)

**Priority: High**

#### UI/UX Improvements ✅
- ✅ **Icon System Migration** - 220+ inline SVG → UCM icons (100% coverage)
- ✅ **Login Page Redesign** - Modern design with stats sidebar, theme dropdown
- ✅ **Theme System Enhancement** - Nebula purple variant, gradient palette icon
- ✅ **Smooth Animations** - Global transitions and page animations
- ✅ **Modal Optimization** - Reduced modal sizes (1400px → 650-750px)

#### Database Management ✅
- ✅ **Backup UI** - Web interface to create encrypted backups
  - Password-protected AES-256-GCM encryption
  - Selective backup options
  - Download .ucm-backup file
- ✅ **Restore UI** - Web interface to restore backups
  - Upload backup file
  - Password decryption
  - Selective restore options
  - Automatic service restart after restore

#### System Improvements ✅
- ✅ **Health Check API** - `/api/health` endpoint for monitoring
  - `/api/health` - Basic health status
  - `/api/health/detailed` - Full metrics (DB, CPU, memory, disk)
  - `/api/health/readiness` - Kubernetes readiness probe
  - `/api/health/liveness` - Kubernetes liveness probe
- ✅ **Database Optimization** - Automatic VACUUM scheduling
  - Weekly auto-VACUUM (Sundays 3 AM)
  - Manual optimization button in Settings
  - Smart skipping (DB < 10MB or fragmentation < 5%)
- ✅ **Log Rotation** - Automated log management
  - Daily rotation for application logs (14 days retention)
  - Automatic compression (gzip, ~80% space savings)
  - Systemd journal integration
- ✅ **CRL Auto-Regeneration** - Automated CRL maintenance
  - Background scheduler checks CRL expiration hourly
  - Automatically regenerates CRLs 24h before expiration
  - Dashboard stats for CRL health

**Status:** Beta (v1.9.0-beta1) deployed to dev  
**Total Development Time:** ~10 hours  
**Commits:** 20+

---

## 📅 Planned Features

### v1.10.0 - Advanced Certificate Management (ETA: 1-2 weeks)

**Priority: Medium**

#### SSO & Authentication
- [ ] **Single Sign-On (SSO)** - Enterprise authentication (8-10h)
  - SAML 2.0 support (Okta, Azure AD, Google Workspace)
  - OAuth2/OIDC integration
  - LDAP/Active Directory authentication
  - Auto-provisioning from IdP
  - Group/role mapping

#### Certificate Templates
- [ ] **Certificate Templates** - Pre-configured cert profiles
  - Web server template (serverAuth)
  - Email template (emailProtection)
  - Code signing template (codeSigning)
  - VPN template (ipsecUser)
  - Custom templates with saved extensions

#### Bulk Operations
- [ ] **Bulk Certificate Operations**
  - Multi-select certificates
  - Bulk revocation
  - Bulk export (ZIP archive)
  - Bulk renewal

#### Enhanced Monitoring
- [ ] **Certificate Monitoring Dashboard**
  - Expiration timeline visualization
  - OCSP request statistics
  - CRL download statistics
  - Top CAs by certificate count

**Estimated Time:** 30-40 hours

---

### v1.10.0 - Enterprise Features (ETA: 1 month)

**Priority: Medium**

#### Multi-tenancy
- [ ] **Organization Support** - Multi-org with isolation
  - Organization management
  - User-to-org assignment
  - CA-to-org assignment
  - Cross-org restrictions

#### Advanced Security
- [ ] **Hardware Security Module (HSM)** - PKCS#11 support
  - HSM key storage for root CAs
  - YubiHSM integration
  - SoftHSM for testing

#### Audit & Compliance
- [ ] **Audit Log System**
  - Full activity logging
  - Certificate lifecycle events
  - User action tracking
  - Exportable reports (PDF/CSV)

#### API Enhancements
- [ ] **GraphQL API** - Alternative to REST
- [ ] **Webhooks** - Event notifications
- [ ] **Rate Limiting** - API throttling

**Estimated Time:** 60-80 hours

---

### v2.0.0 - Major Overhaul (ETA: 2-3 months)

**Priority: Low**

#### Performance
- [ ] **PostgreSQL Default** - Replace SQLite for production
- [ ] **Redis Caching** - Session & data caching
- [ ] **Celery Tasks** - Async job processing

#### Scalability  
- [ ] **High Availability** - Multi-instance support
- [ ] **Load Balancing** - Nginx/HAProxy configs
- [ ] **Kubernetes Deployment** - Helm charts

#### UI Modernization
- [ ] **Vue.js Frontend** - Modern SPA (optional)
- [ ] **Mobile App** - React Native companion app
- [ ] **Advanced Charts** - Comprehensive analytics

**Estimated Time:** 200+ hours

---

## 💡 Feature Requests & Ideas

### Community Suggestions (vote on GitHub Discussions)
- [ ] S/MIME certificate generation
- [ ] Smart card enrollment (PIV/CAC)
- [ ] Certificate pinning management
- [ ] EST protocol support (RFC 7030)
- [ ] Certificate transparency log submission
- [ ] Cross-certification support
- [ ] Multi-language support (French, German, Spanish)
- [ ] Certificate auto-renewal for ACME clients
- [ ] Certificate request approval workflow
- [ ] External CA connector (DigiCert, Let's Encrypt Proxy)

---

## 🔧 Technical Debt

### Code Quality
- [ ] Increase test coverage to 80%+
- [ ] Refactor large route files (split ui_routes.py)
- [ ] Add type hints (Python 3.11+ typing)
- [ ] Implement proper logging levels

### Documentation
- [ ] API reference (OpenAPI/Swagger complete)
- [ ] Administrator guide
- [ ] Developer contributing guide
- [ ] Video tutorials

### Security
- [ ] Security audit by external firm
- [ ] Penetration testing
- [ ] OWASP compliance verification
- [ ] CVE monitoring automation

---

## 📊 Version History

| Version | Release Date | Highlights |
|---------|-------------|------------|
| v1.9.0-b1| 2026-01-16 | UI Modernization, Scheduler, CRL Auto-regen (Beta) |
| v1.8.3  | 2026-01-10  | Universal installer, UI fixes, screenshots |
| v1.8.2  | 2026-01-10  | Service management utilities, HTTPS auto-restart |
| v1.8.0  | 2026-01-09  | mTLS auth, full REST API, OPNsense import |
| v1.7.0  | 2026-01-08  | ACME server, WebAuthn, email notifications |
| v1.6.2  | 2026-01-05  | CRL improvements, packaging fixes |
| v1.6.1  | 2026-01-04  | UI refinements, bug fixes |
| v1.6.0  | 2026-01-03  | SCEP support, OCSP improvements |
| v1.0.1  | 2025-12-20  | Docker support, initial release |
| v1.0.0  | 2025-12-15  | First public release |

---

## 🎯 Release Cadence

- **Patch releases (v1.x.y):** Weekly - Bug fixes, minor improvements
- **Minor releases (v1.x.0):** Monthly - New features, enhancements  
- **Major releases (v2.0.0):** Quarterly - Breaking changes, major rewrites

---

## 🤝 Contributing

Want to help with the roadmap?

1. **Vote on features** - GitHub Discussions
2. **Submit PRs** - See CONTRIBUTING.md
3. **Report bugs** - GitHub Issues
4. **Sponsor development** - GitHub Sponsors (coming soon)

---

**Last Updated:** 2026-01-11  
**Next Review:** 2026-02-01
