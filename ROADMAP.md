# 🗺️ UCM Roadmap

**Current Version:** v2.0.0  
**Status:** Beta Testing

---

## ✅ v2.0.0 - Complete UI Rewrite (RELEASED)

### Frontend Rewrite ✅
- ✅ **React 18 + Vite** - Modern SPA replacing HTMX
- ✅ **Radix UI Components** - Accessible, professional UI
- ✅ **12 Theme Variants** - 6 colors × Light/Dark modes
- ✅ **Split-View Layout** - Sidebar, explorer, details panels
- ✅ **Responsive Design** - Mobile-first, works on all devices

### Core Features ✅
- ✅ **Certificate Management** - Full lifecycle (create, sign, revoke, renew)
- ✅ **CA Hierarchy** - Root, Intermediate, Issuing CAs
- ✅ **Certificate Templates** - Predefined configurations
- ✅ **User Groups** - Permission-based organization
- ✅ **Audit Logs** - Complete action logging with export

### Protocols ✅
- ✅ **SCEP** - RFC 8894 device enrollment
- ✅ **OCSP** - RFC 6960 status checking
- ✅ **ACME** - Let's Encrypt compatible (certbot, acme.sh)
- ✅ **CRL/CDP** - Certificate revocation distribution

### Authentication ✅
- ✅ **Username/Password** - Standard login
- ✅ **WebAuthn/FIDO2** - Hardware security keys
- ✅ **TOTP 2FA** - Google Authenticator compatible
- ✅ **mTLS** - Client certificate authentication

### Deployment ✅
- ✅ **DEB Package** - Debian/Ubuntu
- ✅ **RPM Package** - RHEL/Fedora
- ✅ **Docker** - Multi-arch images
- ✅ **Auto-migration** - From v1.8.x

---

## ✅ v2.0.0 Stable (RELEASED - 2026-02-07)

### Polish & Stability
- [x] Docker image published to GHCR and Docker Hub
- [x] Extended E2E test coverage (132 tests)
- [x] Performance optimization
- [x] Documentation updates

### Bug Fixes
- [x] Address beta feedback
- [x] Cross-browser testing
- [x] Accessibility audit

---

## ✅ Pro Features (v2.0.0)

### Enterprise Security ✅
- ✅ **HSM** - PKCS#11, AWS CloudHSM, Azure Key Vault
- ✅ **RBAC** - Custom roles and permissions
- ✅ **SSO** - SAML, OAuth2, LDAP integration
- ✅ **Security Dashboard** - Secrets management, anomaly detection

### Coming in Pro v2.1.0
- [ ] **Policies Page** - Certificate policy management
- [ ] **Approval Workflows** - Multi-approver requests
- [ ] **Reports Page** - Scheduled reports

### High Availability (Planned)
- [ ] **PostgreSQL** - External database
- [ ] **Redis Sessions** - Distributed sessions

---

## 🌟 v2.1.0 - Next Release

### Internationalization (i18n)
- [ ] **French** (Français)
- [ ] **German** (Deutsch)
- [ ] **Spanish** (Español)
- [ ] **Italian** (Italiano)
- [ ] **Portuguese** (Português)
- [ ] **Ukrainian** (Українська)
- [ ] **Chinese** (中文)
- [ ] **Japanese** (日本語)

### Integrations
- [ ] Kubernetes cert-manager issuer
- [ ] HashiCorp Vault connector
- [ ] EST Protocol (RFC 7030)
- [ ] Certificate Transparency logs
- [ ] CMPv2 (RFC 4210)

---

## 📊 Version History

| Version | Date | Highlights |
|---------|------|------------|
| v2.0.0 | 2026-02-06 | React 18 UI, 12 themes, templates, groups |
| v1.8.3 | 2026-01-10 | Standalone mode, packaging fixes |
| v1.7.0 | 2026-01-08 | ACME, WebAuthn |
| v1.0.0 | 2025-12-15 | Initial release |

---

**Last Updated:** 2026-02-06
