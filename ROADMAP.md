# UCM Roadmap

**Current Version:** See [latest release](https://github.com/NeySlim/ultimate-ca-manager/releases/latest)
**Status:** Stable

---

## v2.0.0 - Complete UI Rewrite (RELEASED)

### Frontend Rewrite
- [x] **React 18 + Vite** - Modern SPA replacing HTMX
- [x] **Radix UI Components** - Accessible, professional UI
- [x] **12 Theme Variants** - 6 colors x Light/Dark modes
- [x] **Split-View Layout** - Sidebar, explorer, details panels
- [x] **Responsive Design** - Mobile-first, works on all devices

### Core Features
- [x] **Certificate Management** - Full lifecycle (create, sign, revoke, renew)
- [x] **CA Hierarchy** - Root, Intermediate, Issuing CAs
- [x] **Certificate Templates** - Predefined configurations
- [x] **User Groups** - Permission-based organization
- [x] **Audit Logs** - Complete action logging with export

### Protocols
- [x] **SCEP** - RFC 8894 device enrollment
- [x] **OCSP** - RFC 6960 status checking
- [x] **ACME** - Let's Encrypt compatible (certbot, acme.sh)
- [x] **CRL/CDP** - Certificate revocation distribution

### Authentication
- [x] **Username/Password** - Standard login
- [x] **WebAuthn/FIDO2** - Hardware security keys
- [x] **TOTP 2FA** - Google Authenticator compatible
- [x] **mTLS** - Client certificate authentication

### Deployment
- [x] **DEB Package** - Debian/Ubuntu
- [x] **RPM Package** - RHEL/Fedora
- [x] **Docker** - Multi-arch images
- [x] **Auto-migration** - From v1.8.x

---

## v2.0.0 Stable (RELEASED - 2026-02-07)

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

## Advanced Features (Experimental)

### Security & Administration
- **HSM** - PKCS#11, AWS CloudHSM, Azure Key Vault, GCP KMS (UI + backend, needs real HSM testing)
- **RBAC** - Custom roles and permissions (UI + API, enforcement in progress)
- **SSO** - LDAP, OAuth2/OIDC, SAML 2.0 (UI + backend, needs production validation)
- [x] **Security Dashboard** - Secrets management, anomaly detection

### Planned for v2.1.0
- [ ] **Bulk Operations** - Revoke, renew, export multiple certificates at once
- [ ] **API Key Scoping** - Enforce per-key permissions (read-only, CA-specific)
- [ ] **Expiry Alerts UI** - Configure email alerts in Settings (backend ready)
- [x] **Webhook Management UI** - Configure webhook endpoints in Settings (backend ready)
- [ ] **Auto-Renewal UI** - Enable/configure auto-renewal per CA (backend ready)
- [ ] **Dashboard Widgets** - Expiring certs timeline, renewal status, webhook health

---

## v2.1.0 - Next Release

### Internationalization (i18n)
- [x] **English** (default)
- [x] **French** (Francais)
- [x] **German** (Deutsch)
- [x] **Spanish** (Espanol)
- [x] **Italian** (Italiano)
- [x] **Portuguese** (Portugues)
- [x] **Ukrainian**
- [x] **Chinese**
- [x] **Japanese**

### PKI Chain Intelligence
- [x] **AKI/SKI Chain Matching** - Cryptographic chain validation replacing DN-based matching
- [x] **Chain Repair Scheduler** - Hourly backfill, re-chain, and deduplication task
- [x] **Chain Repair Widget** - Visual progress on CAs page with manual run
- [x] **Smart Import Dedup** - Prevent duplicate CAs via SKI matching

### UI Overhaul
- [x] **Floating Detail Windows** - Draggable, resizable detail views with embedded content and action bar
- [x] **Window Manager** - Footer bar with stack/tile, same-window, close-on-navigate controls
- [x] **Themes Simplified** - 3 themes (Gray, Purple, Sunset) replacing 6 color schemes
- [x] **Dashboard Redesign** - New header with logo, diversified widget colors
- [x] **Mobile Improvements** - All dashboard charts render, scroll fixes
- [x] **Status Footer Bar** - Window management controls in bottom bar

### Trust Store
- [x] **Chain Validation** - Visual chain status (complete/partial/incomplete)
- [x] **Export Bundle** - PEM bundle export
- [x] **Add from Managed CAs** - Add CA certificates to trust store from managed CAs

### Service Reconnection
- [x] **Reconnect Overlay** - 30s countdown, health + WebSocket readiness check
- [x] **Auto-Redirect** - Redirect to login after service restart with cache invalidation
- [x] **Health API** - Consolidated `/api/v2/health` with WebSocket status

### Integrations (moved to v2.2.0)

### Microsoft AD CS Import
- [ ] **AD Discovery via LDAP** - Connect to Active Directory PKI containers, list all published CAs (root, issuing, policy)
- [ ] **CA Import (PKCS#12)** - Guided import following Microsoft's recommended `certutil -backupkey` / `Backup-CARoleService` procedure
- [ ] **Issued Certificates Import (CSV)** - Bulk import from `certutil -view csv` export
- [ ] **Migration Wizard** - Step-by-step UI: discovery → CA import → cert import → validation report
- [ ] **Chain Validation** - Post-import AKI/SKI chain verification with orphan detection
- [ ] **Rollback** - Batch-tagged imports with undo capability

### Security
- [ ] **LDAPS** - TLS-encrypted AD connection (port 636), warning on plain LDAP
- [ ] **In-memory key handling** - PKCS#12 passwords never persisted or logged
- [ ] **Audit trail** - All migration operations logged with batch IDs

### Integrations
- [ ] Kubernetes cert-manager issuer
- [ ] EST Protocol (RFC 7030)
- [ ] Certificate Transparency logs

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| v2.1.0-beta3 | 2026-02-15 | Floating detail windows, trust store chain validation, service reconnect, 3 themes |
| v2.1.0-beta2 | 2026-02-14 | Dashboard redesign, mobile fixes, status footer bar |
| v2.1.0-alpha | 2026-02-12 | AKI/SKI chain matching, chain repair, themed dialogs, auto-update fix |
| v2.0.6 | 2026-02-12 | Auto-update sudo fix, cumulative fixes since v2.0.1 |
| v2.0.1 | 2026-02-08 | SSO login, i18n sync, form fixes |
| v2.0.0 | 2026-02-06 | React 18 UI, 12 themes, templates, groups |
| v1.8.3 | 2026-01-10 | Standalone mode, packaging fixes |
| v1.7.0 | 2026-01-08 | ACME, WebAuthn |
| v1.0.0 | 2025-12-15 | Initial release |

---

**Last Updated:** 2026-02-15
