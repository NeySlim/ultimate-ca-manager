# 🗺️ UCM Roadmap

**Current Version:** v2.0.0 (2026-02-02)  
**Status:** Production Ready

---

## ✅ v2.0.0 - Complete Enterprise PKI Platform (CURRENT)

### Complete Frontend Rewrite ✅
- ✅ **React 18 + Vite** - Modern SPA replacing HTMX/Alpine.js
- ✅ **Radix UI Components** - Accessible, professional UI primitives
- ✅ **6 Gradient Themes** - Dark Gray, Blue Ocean, Purple Night, Green Forest, Orange Sunset, Cyber Pink
- ✅ **Split-View Layout** - 56px sidebar | 320px explorer | flex details

### Import/Export System ✅
- ✅ **Multi-format Import** - PEM, DER, PKCS12, PKCS7 auto-detection
- ✅ **Paste PEM/JSON** - Direct paste in import modals
- ✅ **Copy PEM** - One-click copy from detail views
- ✅ **Auto-Routing** - CA certs (CA:TRUE) → CAs table

### Authentication ✅
- ✅ **WebAuthn/FIDO2** - Hardware security key support
- ✅ **2FA TOTP** - Google Authenticator with QR setup
- ✅ **mTLS** - Client certificate authentication
- ✅ **Cascade Auth** - Automatic method detection

### RBAC & Groups ✅
- ✅ **Custom Roles** - Create/edit roles with fine-grained permissions
- ✅ **44 Permissions** - Full coverage (CAs, Certs, Users, Groups, HSM, SSO, etc.)
- ✅ **User Groups** - Teams, departments organization
- ✅ **Group-based Permissions** - Assign roles to groups

### SSO Integration ✅
- ✅ **SAML 2.0** - Okta, Azure AD, OneLogin
- ✅ **OAuth2/OIDC** - Google, GitHub, custom providers
- ✅ **LDAP/Active Directory** - Enterprise directory integration
- ✅ **Auto-provisioning** - Create users on first login

### HSM Integration ✅
- ✅ **PKCS#11 Support** - Generic HSM interface
- ✅ **AWS CloudHSM** - Cloud HSM integration
- ✅ **Azure Key Vault** - Microsoft cloud key management
- ✅ **Google Cloud KMS** - GCP key management

### High Availability ✅
- ✅ **PostgreSQL Support** - Production database with migrations
- ✅ **Redis Session Store** - Distributed sessions
- ✅ **Load Balancer Ready** - X-Forwarded-* headers support

### Protocols ✅
- ✅ **EST (RFC 7030)** - Enrollment over Secure Transport
- ✅ **SCEP** - Simple Certificate Enrollment Protocol
- ✅ **ACME** - Let's Encrypt compatible server
- ✅ **OCSP** - Online Certificate Status Protocol

### Compliance (Backend) ✅
- ✅ **Certificate Policies** - Define issuance rules
- ✅ **Approval Workflows** - Multi-step approval
- ✅ **Scheduled Reports** - Automated report generation
- ✅ **Webhooks** - Event notifications
- ✅ **Audit Logging** - Complete audit trail with export

### Testing ✅
- ✅ **Vitest** - 77 frontend unit tests
- ✅ **Pytest** - 12 backend unit tests
- ✅ **Playwright** - 26 E2E tests

### Pages ✅
- ✅ Dashboard, CAs, Certificates, CSRs, Templates
- ✅ Users & Groups, ACME, SCEP, Settings, Account
- ✅ Import/Export, TrustStore, CRL/OCSP, Audit Logs
- ✅ RBAC, HSM, SSO (Pro)

---

## 🚀 v2.0.1 - UI Completion (PLANNED)

### Pro Feature UIs
- [ ] **PoliciesPage.jsx** - Certificate policy management UI
- [ ] **ApprovalsPage.jsx** - Approval workflow UI
- [ ] **WebhooksPage.jsx** - Webhook configuration UI
- [ ] **ReportsPage.jsx** - Report generation and scheduling UI

### UI Enhancements
- [ ] Certificate chain visualization
- [ ] Drag & drop CA hierarchy
- [ ] Bulk operations UI
- [ ] Custom dashboard widgets

---

## 🌟 v2.0.2 - Integrations (FUTURE)

### Kubernetes & Cloud
- [ ] Kubernetes cert-manager issuer
- [ ] HashiCorp Vault connector
- [ ] Terraform provider (full)

### Additional Protocols
- [ ] CMPv2 (RFC 4210)
- [ ] Certificate Transparency logs

### Security
- [ ] Encrypted database at rest
- [ ] Key ceremony support
- [ ] Air-gapped mode

---

## 📊 Version History

| Version | Date | Highlights |
|---------|------|------------|
| v2.0.0  | 2026-02-02 | React 18, Radix UI, HSM, SSO, RBAC, Groups, EST, PostgreSQL, Redis, 26 E2E tests |
| v1.9.0  | 2026-01-16 | UI modernization, scheduler, CRL auto-regen |
| v1.8.0  | 2026-01-09 | mTLS auth, REST API, OPNsense import |
| v1.7.0  | 2026-01-08 | ACME server, WebAuthn, email notifications |
| v1.0.0  | 2025-12-15 | First public release |

---

## 📁 Pro Feature Status

| Feature | Backend | Frontend | Status |
|---------|---------|----------|--------|
| RBAC | ✅ | ✅ `RBACPage.jsx` | Complete |
| Groups | ✅ | ✅ `GroupsPage.jsx` | Complete |
| SSO | ✅ | ✅ `SSOPage.jsx` | Complete |
| HSM | ✅ | ✅ `HSMPage.jsx` | Complete |
| Policies | ✅ | ❌ Planned | v2.0.1 |
| Webhooks | ✅ | ❌ Planned | v2.0.1 |
| Reports | ✅ | ❌ Planned | v2.0.1 |

---

**Last Updated:** 2026-02-02
