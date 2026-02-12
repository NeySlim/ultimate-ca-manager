# Changelog

All notable changes to Ultimate CA Manager will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.1.0-dev] - 2026-02-12

### Architecture Refactor

- **Consolidated API routes** - Removed `features/` module entirely; all routes now registered under `api/v2/` (33 blueprints total)
- **Consolidated models** - Removed `models/features/`; models (rbac.py, sso.py, policy.py) moved to `models/`
- **Moved encryption utils** - `features/encryption.py` → `utils/encryption.py`
- **Replaced roles endpoint** - `api/v2/roles.py` removed, replaced by `api/v2/rbac.py` with expanded RBAC support
- **No more Pro/Community distinction** - All features are core; no separate feature modules

### New Features

- **Backup v2.0** - Complete backup overhaul: exports/restores all database tables (was only 5, now covers groups, RBAC roles, templates, trust store, SSO, HSM, API keys, SMTP, notifications, policies, auth certificates, DNS providers, ACME domains, HTTPS server files)
- **File regeneration** - Startup service that regenerates missing certificate/key files from database, ensuring filesystem consistency after restore or data loss
- **Human-readable file names** - Certificate and CA files now named `{cn-slug}-{refid}.ext` instead of UUID-only (e.g., `www.example.com-550e8400.crt`)
- **SoftHSM integration** - Automatic SoftHSM2 setup across DEB, RPM, and Docker deployments with PKCS#11 key generation
- **Webhooks** - Management tab in Settings for webhook CRUD, test, and event filtering
- **AKI/SKI Chain Matching** - Certificate chain relationships now use cryptographic Authority Key Identifier / Subject Key Identifier matching instead of fragile DN-based matching. Reliable across imports, machines, and environments
- **Chain Repair Scheduler** - Hourly background task that: backfills missing SKI/AKI fields from PEM data, re-chains orphan CAs and certificates via AKI→SKI matching, deduplicates CAs with identical Subject Key Identifiers
- **Chain Repair Widget** - Visual progress bar on CAs page showing chain integrity status with countdown to next repair and manual "Run Now" button
- **Smart Import Deduplication** - Certificate import detects and prevents duplicate CAs based on Subject Key Identifier

### Improvements

- **Pre-release filter** - Update checker only considers alpha, beta, and rc tags as pre-releases
- **RBAC-Users integration** - Users can be assigned custom roles with granular permissions
- **Startup migration** - Automatic SKI/AKI population for certificates imported before v2.1.0
- **Orphan detection accuracy** - Root CAs (self-signed) correctly excluded from orphan counts

### Bug Fixes

- **HSM frontend** - Fixed field name alignment with `api/v2/hsm.py` backend
- **Dashboard expiration colors** - Updated thresholds: ≤7 days red, ≤15 days orange, ≤30 days yellow
- **ACME DNS test** - Fixed import error for `get_dns_provider_instance`
- **i18n cleanup** - Removed unused ACME translation keys, fixed hardcoded strings
- **UTC timezone handling** - API timestamps now include 'Z' suffix for correct browser timezone parsing
- **Certificate name cleanup** - Removed spurious "Imported:" prefix from CA and certificate names

### Security

- **JWT removal** - Removed JWT authentication entirely; UCM now uses session cookies + API keys only. Reduces attack surface and eliminates token-related complexity
- **cryptography** - Upgraded from 46.0.3 to 46.0.5 (CVE-2026-26007)

### Documentation

- Removed decorative emojis from all documentation and wiki (kept functional markers only)

---

## [2.0.3] - 2026-02-10

### Bug Fixes

- **CA Creation Fix** - Fixed crash when creating CA with null `validityYears` or `keySize` values (Docker/fresh installs)
- **DN Field Validation** - Country code now auto-uppercased across all endpoints (CAs, Certificates, CSRs)
- **CSR Validation** - Added missing Distinguished Name validation to CSR creation endpoint

### Docker Improvements

- **Unified Data Path** - All Docker data now stored in `/opt/ucm/data` (same as DEB/RPM installs)
- **Migration Support** - Automatic migration from old path (`/app/backend/data`) on container upgrade
- **Volume Mount Simplified** - Single volume mount: `-v ucm-data:/opt/ucm/data`

### Documentation

- Updated Docker installation guides with correct volume paths
- Updated docker-compose examples

---

## [2.0.0] - 2026-02-07

### Security Enhancements (from beta2)

- **Password Show/Hide Toggle** - All password fields now have visibility toggle
- **Password Strength Indicator** - Visual strength meter with 5 levels (Weak → Strong)
- **Forgot Password Flow** - Email-based password reset with secure tokens
- **Force Password Change** - Admin can require password change on next login
- **Session Timeout Warning** - 5-minute warning before session expires with extend option

### Dashboard Improvements

- **Dynamic Version Display** - Shows current version
- **Update Available Indicator** - Visual notification when updates are available
- **Fixed Layout** - Proper padding and spacing in all dashboard widgets

### Bug Fixes

- Fixed dashboard scroll issues
- Fixed padding in System Health widget
- Fixed padding in Certificate Activity charts
- Restored hierarchical CA view

---

## [2.0.0-beta1] - 2026-02-06

### Complete UI Redesign

Major release with a completely new React 18 frontend replacing the legacy HTMX UI.

#### New Frontend Stack
- **React 18** with Vite for fast builds
- **Radix UI** for accessible components
- **Custom CSS** with theme variables
- **Split-View Layout** with responsive design

#### New Features
- **12 Theme Variants** - 6 color themes (Gray, Ocean, Purple, Forest, Sunset, Cyber) × Light/Dark modes
- **User Groups** - Organize users with permission-based groups
- **Certificate Templates** - Predefined certificate configurations
- **Smart Import** - Intelligent parser for certs, keys, CSRs
- **Certificate Tools** - SSL checker, CSR decoder, certificate decoder, key matcher, format converter
- **Command Palette** - Ctrl+K global search with quick actions
- **Trust Store** - Manage trusted CA certificates
- **ACME Management** - Account tracking, order history, challenge status
- **Audit Logs** - Full action logging with filtering, export, and integrity verification
- **Dashboard Charts** - Certificate trend (7 days), status distribution pie chart
- **Activity Feed** - Real-time recent actions display

#### UI Improvements
- **Responsive Design** - Mobile-first with adaptive layouts
- **Mobile Navigation** - Grid menu with swipe support
- **Keyboard Navigation** - Full keyboard accessibility
- **Real-time Updates** - WebSocket-based live refresh
- **Inter + JetBrains Mono** fonts
- **Contextual Help** - Help modals on every page

#### Backend Improvements
- **API v2** - RESTful JSON API under `/api/v2/`
- **Unified Paths** - Same structure for DEB/RPM/Docker (`/opt/ucm/`)
- **Auto-migration** - Seamless v1.8.x → v2.0.0 upgrade with backup
- **CRL Auto-regeneration** - Background scheduler for CRL refresh
- **Health Check API** - System monitoring endpoints
- **WebSocket Support** - Real-time event notifications

#### Deployment
- **Unified CI/CD** - Single workflow for DEB/RPM/Docker
- **Tested Packages** - DEB (Debian 12) and RPM (Fedora 43) verified
- **Python venv** - Isolated dependencies

---

## [1.8.3] - 2026-01-10

### Bug Fixes

#### Fixed
- **Nginx Dependency** - Nginx is now truly optional
- **Standalone Mode** - UCM runs without reverse proxy
- **Packaging** - Fixed GitHub Actions workflow

#### Documentation
- All guides updated to v1.8.3
- Clear deployment options documented

---

## [1.8.2] - 2026-01-10

### Improvements

- Export authentication for all formats (PEM, DER, PKCS#12)
- Visual theme previews with live preview grid
- Docker/Native path compatibility
- Global PKCS#12 export modal

---

## [1.8.0-beta] - 2026-01-09

### Major Features

- **mTLS Authentication** - Client certificate login
- **REST API v1** - Full API for automation
- **OPNsense Import** - Direct import from firewalls
- **Email Notifications** - Certificate expiry alerts

---

## [1.7.0] - 2026-01-08

### Features

- **ACME Server** - Let's Encrypt compatible
- **WebAuthn/FIDO2** - Hardware security key support
- **Collapsible Sidebar** - Improved navigation
- **Theme System** - 8 beautiful themes

---

## [1.6.0] - 2026-01-05

### UI Overhaul

- Complete Tailwind CSS removal
- Custom themed scrollbars
- CRL Information pages
- Full responsive design

---

## [1.0.0] - 2025-12-15

### Initial Release

- Certificate Authority management
- Certificate lifecycle (create, sign, revoke)
- SCEP server
- OCSP responder
- CRL/CDP distribution
- Web-based administration
