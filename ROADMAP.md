# 🗺️ UCM Roadmap

**Current Version:** v2.0.0-beta1  
**Status:** Beta Testing

---

## ✅ v2.0.0-beta1 - Complete UI Rewrite (CURRENT)

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

## 🚀 v2.0.0 Stable (PLANNED)

### Polish & Stability
- [ ] Docker image published to GHCR
- [ ] Extended E2E test coverage
- [ ] Performance optimization
- [ ] Documentation updates

### Bug Fixes
- [ ] Address beta feedback
- [ ] Cross-browser testing
- [ ] Accessibility audit

---

## 🔮 v2.1.0 - Pro Features (FUTURE)

### Pro Feature UIs
- [ ] **Policies Page** - Certificate policy management
- [ ] **Approval Workflows** - Multi-approver requests
- [ ] **Webhooks Page** - Event notifications
- [ ] **Reports Page** - Scheduled reports

### Enterprise Integration (Pro)
- [ ] **SSO** - SAML, OAuth2, LDAP (backend ready)
- [ ] **HSM** - PKCS#11, Cloud HSM (backend ready)
- [ ] **RBAC** - Custom roles (backend ready)

### High Availability (Pro)
- [ ] **PostgreSQL** - External database (code ready)
- [ ] **Redis Sessions** - Distributed sessions (code ready)

---

## 🌟 v2.2.0+ - Future Ideas

- [ ] Kubernetes cert-manager issuer
- [ ] HashiCorp Vault connector
- [ ] EST Protocol (RFC 7030)
- [ ] Certificate Transparency logs
- [ ] CMPv2 (RFC 4210)

---

## 📊 Version History

| Version | Date | Highlights |
|---------|------|------------|
| v2.0.0-beta1 | 2026-02-06 | React 18 UI, 12 themes, templates, groups |
| v1.8.3 | 2026-01-10 | Standalone mode, packaging fixes |
| v1.7.0 | 2026-01-08 | ACME, WebAuthn |
| v1.0.0 | 2025-12-15 | Initial release |

---

**Last Updated:** 2026-02-06
