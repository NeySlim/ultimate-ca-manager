# Changelog

All notable changes to Ultimate CA Manager will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.1.0-rc2] - 2026-02-18

### New Features
- ***SSO authentication: full SAML/OAuth2 support with Keycloak tested***
- ***Governance module: certificate policies, approval workflows, scheduled reports***
- ***ACME DNS providers: 48 providers with card grid selector and official SVG logos***
- ***Unified ExportModal with RBAC permission guards***
- ***Dashboard charts: day selector, expired series, optimized queries***
- ***Complete i18n: all 9 languages with 2273 keys each***

### Security
- RBAC permission enforcement across all frontend pages and floating windows
- SQL injection fixes and debug leak prevention
- Referrer-Policy security header added
- Hide sidebar pages based on user permissions

### Improvements
- WebSocket/CORS: auto-detect short hostname and dynamic port for reliable connections
- Close all floating panels and detail windows on logout
- Table refresh after floating window actions (revoke/renew/delete)
- Rich table preview for reports instead of raw JSON
- Searchable Select component

### Bug Fixes
- Fixed CORS origin rejection breaking WebSocket on Docker and fresh installs
- Fixed force_password_change not set on fresh admin creation
- Fixed infinite loop in reports from canWrite in useCallback deps
- Fixed 403 console errors and chart sizing issues
- Fixed z-index conflicts between confirm dialogs, toasts, and floating windows

### Packaging
- Removed unnecessary gcc/build-essential from DEB/RPM dependencies
- Fixed backend/VERSION not updated during CI builds
- Default password is now always `changeme123` (not random)

## [2.1.0-rc1] - 2026-02-15

### Improvements
- Template editor button disabled on mobile with tooltip (desktop-only feature)
- Cleaned up unused mobile full-screen editor code
- Comprehensive API smoke test: 96/97 endpoints verified

### Bug Fixes
- Fixed `isMobile` reference error in SettingsPage email tab
- Fixed 6 broken API endpoints (schema mismatches between models and database)
- Migration 030: added missing columns to user_sessions, approval_requests, certificate_policies
- Fixed `User.two_factor_enabled` → `User.totp_confirmed` attribute in account API
- Fixed `AuditLog.created_at` → `AuditLog.timestamp` in audit log queries

## [2.1.0-beta4] - 2026-02-15

### New Features
- Email template editor with split-pane HTML source + live preview
- Plain text template tab for non-HTML email clients
- Customizable email templates with UCM branding and 6 template variables
- TagsInput component for alert recipients (type + Enter, paste multiple)
- Certificate expiry alert settings (thresholds, recipients, check now)
- SMTP settings: content type selector (HTML/Text/Both), test email recipient field

### Improvements
- Floating window: resize from left/top edge keeps opposite edge fixed
- Floating window: pointer-events disabled on body during resize (iframe fix)
- Input field: "Set" badge no longer misaligns adjacent fields
- Email settings: consistent field widths with DetailGrid layout
- SMTP gate: real error messages displayed inline (not just "check settings")

### Bug Fixes
- TagsInput background color matches regular input fields (bg-secondary)
- Removed broken Tailwind opacity syntax on CSS variables in TagsInput
- Placeholder comma removed from alert recipients field

### Documentation
- In-app help: email template editor section with variables and instructions
- Admin guide: new Email Notifications section (SMTP, template, alerts)
- Wiki: Email & Notifications section in Configuration page

### Cleanup
- Removed dead EmailTemplateEditor.jsx (TipTap WYSIWYG, replaced by source editor)
- Uninstalled 14 unused TipTap npm packages

## [2.1.0-beta3] - 2026-02-15

### New Features

- **Floating Detail Windows** - Click any table row to open draggable, resizable detail window with embedded content
- **Detail Action Bar** - Export (multi-format dropdown: PEM, DER, PKCS#12, chain), Renew, Revoke, Delete actions in detail windows
- **Window Manager** - Footer bar with stack/tile, same-window, close-on-navigate options
- **Trust Store Chain Validation** - Visual chain status (complete/partial/incomplete), export bundle, add from managed CAs
- **Service Reconnection** - 30s countdown, health + WebSocket readiness check, automatic redirect to login
- **Health Endpoint** - Consolidated to `/api/v2/health` with WebSocket readiness status, backward-compatible aliases
- **ACME Account Delete** - DELETE `/api/v2/acme/accounts/{id}` with cascade cleanup (challenges→authorizations→orders)
- **Settings About** - Version, system info, uptime, memory, links to docs/wiki/issues
- **Template Duplication** - Clone endpoint: POST /templates/{id}/duplicate
- **Unified Export Actions** - Reusable `ExportActions` component with inline contextual password field for P12

### UI/UX

- **Dashboard** - Redesigned header with logo, diversified widget colors, donut chart with gradient/shadow effects
- **Dashboard Mobile** - Compact header with watermark logo, no redundancy with navbar
- **Logo** - Shield outline, larger on dashboard, smaller in sidebar
- **Themes** - Simplified to 3 themes: Gray, Purple, Sunset (was 6)
- **Tables** - Proportional column sizing, actions moved from table to detail windows
- **Status Footer Bar** - Window management controls, theme-aware design
- **Mobile Navbar** - User dropdown menu with account, settings, language selector, logout
- **Mobile Nav Grid** - Short i18n labels for 5-column grid (all 9 languages)
- **Reconnect Overlay** - Circular countdown ring, connection progress bar, redirect status
- **Export Consistency** - Uniform PEM/DER/P7B/P12 formats across all detail panels, inline password field replaces modal

### i18n

- **Full Coverage** - 1930+ keys across all 9 languages, 0 missing
- **Short Mobile Labels** - 16 `*Short` keys per language for compact mobile navigation
- **New Namespaces** - `reconnect.*`, `table.*`, `windows.*`, `details.daysShort`
- **Hardcoded Strings** - 20+ user-facing strings replaced with `t()` calls

### Bug Fixes

- **Health Endpoint** - Removed duplicate route from app.py, consolidated in health_routes.py
- **FloatingHelpPanel** - Defined missing SOFT_MAX_W constant (was causing runtime crash)
- **Dashboard Charts** - Fixed width/height(-1) errors with absolute positioning wrapper
- **Dashboard Donut** - Fixed gradient IDs using translated names (SVG invalid refs)
- **Dashboard** - Fixed react-grid-layout v2.2.2 dragConfig/resizeConfig API
- **Dashboard** - Fixed Card.Body ignoring style prop
- **Toast Notifications** - Stack vertically instead of overlapping
- **Radix Select** - Filter empty value options
- **SCEP Nav** - Normalize URL for active state detection
- **OPNsense** - Wrapped password inputs in form element (DOM warning)
- **Tests** - Mock useWindowManager in PageRendering tests
- **Mobile Slide-Over** - Fixed detail panels not showing for sidebar pages (ACME, Users, CSRs)
- **CSR Download** - Fixed endpoint mismatch (`/download` → `/export`)
- **PFX/P12 Export** - Fixed missing password prompt in floating detail windows
- **Password Autofill** - Prevent password managers from autofilling non-login fields (CSS text-security masking)

### Code Quality

- Removed dead system.service methods (getHealth, getVersion, getInfo)
- Removed unused LanguageSelector import
- Removed 23 console.error statements from production code
- Removed P12 password modals (replaced by inline ExportActions)

---

## [2.1.0-alpha3] - 2026-02-13

### Security

- **Auto-Update** - Fixed DEB postinst: updater systemd units were never enabled (wrong path check)

### Bug Fixes

- **Truststore** - Delete now returns 200 with message instead of broken 204 (was causing UI to not refresh)
- **CRL** - Returns null data instead of 404 when CRL not yet generated for a CA
- **i18n** - Fixed certificate decoder translation key (tools.certDecoder -> tools.decoder)
- **Server** - Suppress noisy SSL tracebacks from reverse proxy health checks

### Improvements

- **Auto-Update** - Clean unused imports, daily scheduled update check
- **Documentation** - Complete API reference (~270 endpoints), README audit, refreshed screenshots

---

## [2.1.0-dev] - 2026-02-12

### Architecture Refactor

- **Consolidated API routes** - Removed `features/` module entirely; all routes now registered under `api/v2/` (33 blueprints total)
- **Consolidated models** - Removed `models/features/`; models (rbac.py, sso.py, policy.py) moved to `models/`
- **Moved encryption utils** - `features/encryption.py` → `utils/encryption.py`
- **Replaced roles endpoint** - `api/v2/roles.py` removed, replaced by `api/v2/rbac.py` with expanded RBAC support
- **No more Pro/Community distinction** - All features are core; no separate feature modules

### New Features

- ***Backup v2.0*** - Complete backup overhaul: exports/restores all database tables (was only 5, now covers groups, RBAC roles, templates, trust store, SSO, HSM, API keys, SMTP, notifications, policies, auth certificates, DNS providers, ACME domains, HTTPS server files)
- **File regeneration** - Startup service that regenerates missing certificate/key files from database, ensuring filesystem consistency after restore or data loss
- **Human-readable file names** - Certificate and CA files now named `{cn-slug}-{refid}.ext` instead of UUID-only (e.g., `www.example.com-550e8400.crt`)
- ***SoftHSM integration*** - Automatic SoftHSM2 setup across DEB, RPM, and Docker deployments with PKCS#11 key generation
- **Webhooks** - Management tab in Settings for webhook CRUD, test, and event filtering
- ***AKI/SKI Chain Matching*** - Certificate chain relationships now use cryptographic Authority Key Identifier / Subject Key Identifier matching instead of fragile DN-based matching. Reliable across imports, machines, and environments
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

- ***JWT removal*** - Removed JWT authentication entirely; UCM now uses session cookies + API keys only. Reduces attack surface and eliminates token-related complexity
- ***cryptography*** - Upgraded from 46.0.3 to 46.0.5 (CVE-2026-26007)

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
