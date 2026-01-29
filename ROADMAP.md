# 🗺️ UCM Roadmap

**Current Version:** v2.0.0 (2026-01-29)  
**Status:** Production Ready

---

## ✅ v2.0.0 - Complete PKI Platform (CURRENT)

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
- ✅ **Duplicate Detection** - Auto-update existing entries
- ✅ **Smart Navigation** - Redirect to correct page after import

### Authentication ✅
- ✅ **WebAuthn/FIDO2** - Hardware security key support
- ✅ **2FA TOTP** - Google Authenticator with QR setup
- ✅ **mTLS** - Client certificate authentication
- ✅ **Cascade Auth** - Automatic method detection

### Audit Logging ✅
- ✅ **Complete Audit Trail** - All actions logged
- ✅ **Filter & Search** - By action, user, date range
- ✅ **Export CSV** - Download for compliance
- ✅ **Statistics** - Action counts and trends

### Code Quality ✅
- ✅ **Centralized Constants** - `constants/config.js` with VALIDITY, PAGINATION, TIME
- ✅ **Shared Hooks** - `useModals`, `useDeleteHandler`, `usePagination`
- ✅ **Styled Dialogs** - `showConfirm()`, `showPrompt()` replace native JS popups
- ✅ **UI Consistency** - Standardized border-radius, padding, shadows

### Testing ✅
- ✅ **Vitest** - 39 frontend unit tests
- ✅ **Pytest** - 51 backend API tests
- ✅ **Playwright** - 14 E2E tests (auth, certificates, settings)

### Pages ✅
- ✅ Dashboard, CAs, Certificates, CSRs, Templates
- ✅ Users, ACME, SCEP, Settings, Account, Audit Logs

### Remaining for v2.0.0
- [ ] Coverage reports (target: 80%)
- [ ] User guide (getting started)
- [ ] Admin guide (configuration)
- [ ] OpenAPI/Swagger spec
- [ ] Mobile responsive improvements
- [ ] Keyboard shortcuts (Cmd+K, etc.)

---

## 🚀 v2.0.0 Pro - Enterprise Features

### RBAC Enhancement
- [ ] Custom roles
- [ ] Fine-grained permissions
- [ ] Role templates
- [ ] Permission inheritance

### Group Management
- [ ] User groups (teams, departments)
- [ ] Group-based permissions
- [ ] CA/Certificate ownership by group
- [ ] Group administrators

### High Availability
- [ ] PostgreSQL support
- [ ] Redis session store
- [ ] Load balancer ready
- [ ] Database replication

### SSO Integration
- [ ] SAML 2.0 (Okta, Azure AD)
- [ ] OAuth2/OIDC
- [ ] LDAP/Active Directory
- [ ] Auto-provisioning

### Compliance
- [ ] Certificate policies
- [ ] Approval workflows
- [ ] Scheduled reports
- [ ] Enhanced email notifications

---

## 🌟 v2.1.0 Pro - Advanced PKI

### HSM Integration
- [ ] PKCS#11 support
- [ ] YubiHSM
- [ ] AWS CloudHSM
- [ ] Azure Key Vault

### Advanced Protocols
- [ ] EST (RFC 7030)
- [ ] CMPv2 (RFC 4210)
- [ ] Certificate Transparency

### Automation
- [ ] Certificate auto-renewal daemon
- [ ] Scheduled CRL generation
- [ ] API webhooks
- [ ] Terraform provider

---

## 💡 Ideas Backlog

### Integrations
- [ ] Kubernetes cert-manager
- [ ] HashiCorp Vault connector
- [ ] Let's Encrypt staging mirror
- [ ] DigiCert/Sectigo proxy

### UI Enhancements
- [ ] Certificate chain visualization
- [ ] Drag & drop CA hierarchy
- [ ] Bulk operations UI
- [ ] Custom dashboard widgets

### Security
- [ ] Encrypted database at rest
- [ ] Key ceremony support
- [ ] Air-gapped mode
- [ ] Signed audit logs

---

## 📊 Version History

| Version | Date | Highlights |
|---------|------|------------|
| v2.0.0  | 2026-01-29 | React 18 rewrite, Radix UI, import/export, 2FA/WebAuthn, 104 tests |
| v1.9.0  | 2026-01-16 | UI modernization, scheduler, CRL auto-regen |
| v1.8.3  | 2026-01-10 | Universal installer, screenshots |
| v1.8.0  | 2026-01-09 | mTLS auth, REST API, OPNsense import |
| v1.7.0  | 2026-01-08 | ACME server, WebAuthn, email notifications |
| v1.6.0  | 2026-01-03 | SCEP support, OCSP improvements |
| v1.0.0  | 2025-12-15 | First public release |

---

**Last Updated:** 2026-01-29
