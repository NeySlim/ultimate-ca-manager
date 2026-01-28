# 🗺️ UCM Roadmap

**Current Version:** v2.0.0 (2026-01-28)  
**Status:** Production Ready

---

## ✅ v2.0.0 - React Frontend Rewrite (CURRENT)

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

### Pages ✅
- ✅ Dashboard - Stats, expiring certs, activity
- ✅ CAs - TreeView hierarchy, create, import
- ✅ Certificates - Table, issue, revoke, export
- ✅ CSRs - Upload, sign, export
- ✅ Templates - Create, edit, import/export
- ✅ Users - CRUD, roles, 2FA management
- ✅ ACME - Accounts, orders, challenges
- ✅ Settings - General, Email, Security, Backup
- ✅ Account - Profile, security, API keys
- ✅ Audit Logs - Full audit trail

---

## 🔄 v2.1.0 - Quality & Polish (February 2026)

### Testing
- [ ] E2E tests with Playwright
- [ ] Unit tests for React components
- [ ] API integration tests
- [ ] Coverage reports (target: 80%)

### Documentation
- [ ] User guide (getting started)
- [ ] Admin guide (configuration)
- [ ] OpenAPI/Swagger spec
- [ ] Video tutorials

### Polish
- [ ] Mobile responsive improvements
- [ ] Keyboard shortcuts (Cmd+K, etc.)
- [ ] Accessibility audit (WCAG 2.1)
- [ ] Performance optimization (lazy loading)

---

## 🚀 v2.2.0 - Enterprise Features (Q2 2026)

### RBAC Enhancement
- [ ] Custom roles
- [ ] Fine-grained permissions
- [ ] Role templates
- [ ] Permission inheritance

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

## 🌟 v3.0.0 - Advanced PKI (Q3-Q4 2026)

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
| v2.0.0  | 2026-01-28 | React 18 rewrite, Radix UI, import/export, 2FA/WebAuthn |
| v1.9.0  | 2026-01-16 | UI modernization, scheduler, CRL auto-regen |
| v1.8.3  | 2026-01-10 | Universal installer, screenshots |
| v1.8.0  | 2026-01-09 | mTLS auth, REST API, OPNsense import |
| v1.7.0  | 2026-01-08 | ACME server, WebAuthn, email notifications |
| v1.6.0  | 2026-01-03 | SCEP support, OCSP improvements |
| v1.0.0  | 2025-12-15 | First public release |

---

**Last Updated:** 2026-01-28
