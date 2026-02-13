# Changelog

All notable changes to Ultimate CA Manager will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.0.7] - 2026-02-13

### Security

- **Auto-Update** - Replaced shell command injection vulnerability with systemd path-activated updater

### Bug Fixes

- **Packaging** - Restart service on upgrade instead of start (preserves running state)

### Improvements

- **Auto-Update** - Download to DATA_DIR/updates instead of /tmp (PrivateTmp-safe)
- **Auto-Update** - Daily scheduled update check (logs available updates)
- **Packaging** - DEB/RPM now install and enable ucm-updater.path systemd unit

---

## [2.0.6] - 2026-02-12

### New Features

- ***SSO Login*** - OAuth2/OIDC, SAML 2.0, LDAP/Active Directory authentication
- **i18n** - All 9 locales synchronized (1799 translation keys)

### Security

- ***CVE-2026-26007*** - Upgraded cryptography 46.0.3 → 46.0.5
- **DN Validation** - Hardened across all endpoints (CAs, Certificates, CSRs)

### Bug Fixes

- ***Auto-Update*** - Fixed sudo permissions for package install (DEB/RPM), added sudoers entries
- **Docker** - Fixed Python 3.13 recursion bug, unified data path to `/opt/ucm/data`
- **OPNsense Import** - Import button not showing after connection test
- **Certificate Form** - Fixed broken Select options and field names
- **CA Creation** - Fixed crash with null validity/keySize values

### Improvements

- **VERSION Centralization** - Single source of truth for all platforms
- **Auto-Update Logging** - Now logs to `/var/log/ucm/update.log`

---

## [2.0.4] - 2026-02-11

### Bug Fixes

- **Update Check Fix** - Fixed "maximum recursion depth exceeded" error on Docker (gevent + Python 3.13 SSL compatibility)
- **Edition Detection** - Removed stale Pro edition detection that caused update checks to query archived private repo

### Improvements

- **VERSION Centralization** - Single `VERSION` file at project root, read by all platforms (DEB, RPM, Docker)
- **Docker Directory Fix** - Fixed `cas/` → `ca/` mismatch; automatic migration on container upgrade
- **Safe HTTP Sessions** - Added `safe_requests.py` utility for consistent SSL handling
- **Early Monkey-Patch** - `gevent.monkey.patch_all()` called before imports in gunicorn configs

### Packaging

- DEB/RPM packages now include `VERSION` file at `/opt/ucm/VERSION`
- Docker image copies `VERSION` to `/app/VERSION`
- Added missing `crl/` and `scep/` data directories to DEB/RPM postinst

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

- **Dynamic Version Display** - Shows current version with Pro/Community badge
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
