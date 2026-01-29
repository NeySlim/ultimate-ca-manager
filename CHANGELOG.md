# Changelog

All notable changes to Ultimate CA Manager will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.0.0] - 2026-01-29

### 🎨 Complete React Frontend Rewrite (UCM V4)

#### Added
- **React 18 + Vite** - Modern frontend stack replacing HTMX/Alpine.js
- **Radix UI Components** - Accessible, professional UI primitives
- **6 Gradient Themes** - Dark Gray, Blue Ocean, Purple Night, Green Forest, Orange Sunset, Cyber Pink
- **Split-View Layout** - 56px sidebar | 320px explorer | flex details panel
- **TreeView for CAs** - Hierarchical display with Root CAs / Orphans sections
- **ErrorBoundary** - Graceful error handling with recovery option
- **Code Splitting** - React.lazy for optimized page loading (121KB main bundle)
- **Rate Limiting** - Flask-Limiter protection (200/min, 2000/hour)

#### Import/Export System
- **Unified Import** - Auto-detect PEM, DER, PKCS12, PKCS7 formats
- **Paste PEM/JSON** - Direct paste in import modals (no file needed)
- **Copy PEM** - One-click copy from detail views
- **Auto-Routing** - CA certificates (CA:TRUE) auto-routed to CAs table
- **Duplicate Detection** - Auto-update existing entries
- **Smart Navigation** - Redirects to correct page after import with selection

#### Certificate Management
- **Delete Certificate** - Remove certificates from system
- **Renew Certificate** - In-place renewal with new key pair (same ID)
- **Sorted List** - Default sort by Common Name (A-Z)
- **Server-side Sorting** - Consistent pagination across all pages

#### Authentication
- **WebAuthn/FIDO2** - Hardware security key support (YubiKey, etc.)
- **2FA TOTP** - Google Authenticator compatible with QR setup
- **mTLS** - Mutual TLS certificate authentication
- **Cascade Auth** - Automatic method detection and fallback

#### Audit Logging
- **Complete Audit Trail** - All actions logged with user, IP, details
- **Filter & Search** - By action type, user, date range
- **Export CSV** - Download audit logs for compliance
- **Statistics Dashboard** - Action counts and trends

#### API Enhancements
- **155+ Endpoints** - Complete REST API v2 (NO MORE STUBS)
- **Standardized Responses** - `{data, meta}` structure throughout
- **OCSP Responder** - RFC 6960 compliant certificate status

#### Code Quality (2026-01-29)
- **Centralized Constants** - `constants/config.js` for VALIDITY, PAGINATION, TIME
- **Shared Hooks** - `useModals`, `useDeleteHandler`, `usePagination`
- **Styled Dialogs** - `showConfirm()`, `showPrompt()` replace native JS popups
- **UI Consistency** - Standardized border-radius, padding, shadows across components
- **HTTPS Cert Display** - Real certificate info with CA-Signed/Self-Signed badge

#### Testing (104 total tests)
- **Vitest** - 39 frontend unit tests (components, services)
- **Pytest** - 51 backend API tests (auth, CAs, certs, SCEP)
- **Playwright** - 14 E2E tests (auth, certificates, settings)

#### Bug Fixes
- Delete CA/Certificate actually deletes (was stub)
- Export uses correct attribute (`descr` not `name`)
- Modal props fixed for Radix (`open` not `isOpen`)
- Select defaults fixed for Radix (`'auto'` not `''`)
- Certificate renewal now works (was stub returning fake data)
- CA lookup for renewal handles different refid formats
- All API stubs replaced with real implementations
- Dropdown component fixed (forwardRef + onSelect for Radix)
- HTTPS cert info displays real data instead of "Self-Signed"

---

## [1.8.3] - 2026-01-10

### 🚀 Installation & CI/CD Improvements

#### Added
- **Universal installer script** - One-line install for all Linux distributions
  - Auto-detects OS (Debian, Ubuntu, RHEL, Rocky, Alma, Fedora, openSUSE, Arch, Alpine)
  - Offers native package (DEB/RPM) when available
  - Falls back to source installation
  - Zero dependencies required (only bash)
- **Source tarballs in releases** - `ucm-{VERSION}.tar.gz` with full source code
- **Checksum files** - SHA256 and MD5 for all release assets (DEB, RPM, source)
- **Screenshots gallery** - 16 high-quality screenshots documenting all features
  - Organized docs/SCREENSHOTS.md
  - Preview table in README.md

#### Fixed
- **mTLS navigation** - "My Certificates" now uses `/my-account/mtls` route instead of anchor
- **GitHub Actions workflows** - Simplified DEB workflow with echo-based file generation (no heredoc issues)
- **Button visibility** - Improved btn-success and btn-warning classes across all themes
- **Theme indicator** - Active theme now visible on all pages, not just dashboard

#### Changed
- **Full English translation** - All remaining French text translated
  - Table search placeholders ("Rechercher..." → "Search...")
  - Orphaned CAs backend messages
  - Consistent language across entire interface
- **Documentation accuracy** - Updated all docs to reflect v1.8.3 reality
  - Removed mentions of non-implemented features (automated backups, restore UI)
  - Fixed Docker environment variables (removed UCM_BACKUP_* vars)
  - Updated version references from 1.8.0-beta to 1.8.3
- **Service management** - Auto-restart after HTTPS certificate changes

#### Documentation
- **INSTALLATION.md** - Comprehensive installation guide
- **ROADMAP.md** - Clear development plan through v2.0.0
- **Wiki updates** - Backup-Restore page rewritten, homepage updated
- All guides reflect accurate v1.8.3 feature set

---

## [1.8.2] - 2026-01-10

### 🐛 Critical Bug Fix - Nginx Dependency

#### Fixed
- **Nginx no longer required** - Package can now be installed without nginx (standalone mode)
- GitHub Actions workflow was generating incorrect `control` file with nginx in `Depends:`
- Updated workflow to match repository configuration:
  - **Depends:** python3, pip, venv, systemd (essentials only)
  - **Recommends:** flask-caching, redis (performance)
  - **Suggests:** nginx, apache2, certbot, gunicorn (optional)

#### Changed
- Enhanced package descriptions with complete feature list (ACME, SCEP, WebAuthn, mTLS, CRL, Email, REST API, 8 themes)
- Updated all documentation to v1.8.2 (README, UPGRADE, DOCKER_QUICKSTART)
- Clarified deployment options (standalone, reverse proxy, Docker)

---

## [1.8.0-beta] - 2026-01-10

### ✨ Major Features & Security Enhancements

#### Added
- **Complete export authentication** - All export formats (PEM, DER, PKCS#12) now authenticated with JWT
- **Visual theme preview cards** - 2×4 grid layout with miniature UI previews replacing simple buttons
- **Global PKCS#12 modal system** - Available across all pages including HTMX-loaded content
- **Docker/native path compatibility** - Dynamic path resolution for both deployment modes

#### Fixed
- **Export system authentication** (10 commits):
  - Missing Certificate import in backend/api/cert.py
  - CA and certificate export 401 errors
  - Dashboard missing JWT token
  - PKCS#12 modal not found in HTMX content
  - Broken global export functions (removed 114 lines)
  - Added global `window.exportWithToken()` with JWT
- **Hardcoded paths replaced** - `/opt/ucm` → `current_app.config[]` for Docker compatibility
- **HTTPS certificate type detection** - Fixed subject/issuer comparison
- **Certificate source synchronization** - Fixed race condition with Promises

#### Changed
- Moved PKCS#12 modal to base.html for global availability
- Moved `window.UCM_TOKEN` definition to base.html
- Enhanced theme selection with visual preview cards (8 themes in 2 rows of 4)
- Improved sidebar naming ("Settings" → "System Settings")

#### Statistics
- **17 commits total** (15 bug fixes, 2 features)
- **7 files modified** (3 backend, 4 frontend)
- **+450 lines added, -300 removed** (net +150)
- **8 tag iterations** during development

---

## [1.6.0] - 2026-01-05

### 🎨 Complete UI Redesign & Tailwind Removal - Production Ready

This release completes the transformation from Tailwind CSS to a custom theming system with full UI polish.

### Added
- **Custom Styled Scrollbars** - Theme-aware scrollbars for all 8 themes (light themes use dark scrollbars, dark themes use light scrollbars)
- **CRL Information Pages**:
  - Public page: `/cdp/{refid}/info` (no authentication)
  - Integrated page: `/crl/info/{refid}` (authenticated)
  - Complete CRL metadata display with RFC 5280 compliance
- Manual certificate and CA import endpoints
- Missing `services/__init__.py` with database models

### Changed
- **Modal System Improvements**:
  - Modal z-index to 1000 (above sidebar at 999)
  - Better modal positioning and backdrop behavior
  - Consistent styling across all themes
- Simplified README with redirect to comprehensive wiki
- Enhanced CI/CD with main branch triggers

### Fixed
- Scrollbar visibility when no modal is open
- Modal backdrop z-index conflicts
- Component style consistency across all 8 themes
- CI workflow permissions for releases

### Quality Assurance
- ✅ All 8 themes fully tested
- ✅ No Tailwind classes remaining
- ✅ No JavaScript console errors
- ✅ Responsive design verified on mobile/tablet/desktop
- ✅ Theme consistency across all pages
- ✅ All modals working correctly
- ✅ API endpoints validated

---

## [1.5.0] - 2026-01-05

### 🔐 CRL/CDP Implementation - RFC 5280 Compliant

Complete implementation of Certificate Revocation Lists and Distribution Points in 3 development phases (1h37 total).

#### Phase 1: Backend Infrastructure (1h13)

### Added
- **CRL Distribution Points (CDP)** - Full RFC 5280 compliant implementation
- **CRL Model** - `CRLMetadata` table for CRL history and metadata
- **CRL Service** - RFC 5280 compliant CRL generation and management
- **Database Migration** - CDP columns in CA table (`cdp_enabled`, `cdp_url`)
- **Private API Endpoints** (5 endpoints, authenticated):
  - `GET /api/v1/crl/` - List all CRLs
  - `GET /api/v1/crl/<ca_id>` - Get CRL metadata and history
  - `POST /api/v1/crl/<ca_id>/generate` - Generate/regenerate CRL
  - `GET /api/v1/crl/<ca_id>/download` - Download CRL (PEM/DER)
  - `GET /api/v1/crl/<ca_id>/revoked` - List revoked certificates
- **Public CDP Endpoints** (4 endpoints, no authentication):
  - `GET /cdp/<ca_refid>/crl.pem` - Download CRL (PEM format)
  - `GET /cdp/<ca_refid>/crl.der` - Download CRL (DER binary format)
  - `GET /cdp/<ca_refid>/crl.crl` - Download CRL (.crl alias)
  - `GET /cdp/<ca_refid>/info` - CRL metadata (JSON)

#### Phase 2: Certificate Integration (12min)

### Added
- **CDP Extension in Certificates** - All issued certificates include CDP extension
- **Auto-generation on Revocation** - CRL regenerates automatically when certificates are revoked
- **Serial Number Validation** - RFC 5280 compliance (159 bits maximum)

### Changed
- Certificate issuance injects CDP distribution point
- Revocation workflow triggers automatic CRL regeneration

### Fixed
- Serial number generation limited to 159 bits (RFC 5280 compliance)

#### Phase 3: UI Management (12min)

### Added
- **CRL Management Page** (`/crl`):
  - Table with all CAs, CDP status, CRL status, revoked count
  - Status badges: 🟢 Up-to-date, 🟡 Expiring soon, 🔴 Stale, ⚪ Never generated
  - Actions: Download PEM, Download DER, Force regenerate
  - Refresh all CRLs button
- **CA Detail CDP Section**:
  - Enable/disable CDP toggle
  - CDP URL template with `{ca_refid}` variable
  - Live URL preview
  - Quick actions: View CRL info, Download CRL, Configure
- **Sidebar Integration** - CRL Management menu link

### Technical Details
- **CRL Extensions**: CRL Number, Authority Key Identifier, Revocation Reason
- **MIME Types**: PEM (`application/x-pem-file`), DER (`application/pkix-crl`)
- **Caching**: CRLs stored in database (no per-request regeneration)
- **Access Control**: Public/authenticated endpoint separation
- **HTMX Integration**: Dynamic updates without page reload

### Tests Validated
- ✅ CDP extension in issued certificates (OpenSSL verified)
- ✅ CRL auto-generation on revocation
- ✅ Public CDP endpoints accessible
- ✅ RFC 5280 compliance verified
- ✅ CRL status badges working

---

## [1.4.0] - 2026-01-05

### 🎨 Login Redesign & Theme Flash Fix

### Added
- **Login Page Redesign**:
  - 8-theme selector available pre-authentication
  - Palette icon + moon/sun toggle
  - Persistent theme across login flow
  - Visual theme preview before authentication
- **Anti-FOUC Implementation**:
  - Inline script in `<head>` loads theme before render
  - Eliminates white flash on page load
  - Synchronous theme initialization

### Changed
- **SCEP Button Styling** - All 8 SCEP buttons properly styled with theme colors
- **Theme Loading** - Moved from DOMContentLoaded to immediate execution

### Fixed
- **Theme Flash Eliminated** - No white background flash during page load
- **Login Theme Persistence** - Theme selection survives authentication

---

## [1.3.0] - 2026-01-05

### 🎯 Complete Tailwind CSS Removal (~827 Classes)

Major migration from Tailwind utility classes to custom CSS system.

### Changed
- **BREAKING: Tailwind CSS Completely Removed**
- **8 Core Templates Migrated** (100% Tailwind-free):
  - `cas/detail.html` - 132 → 0 Tailwind classes
  - `scep.html` - 89 → 0 classes
  - `cas/list.html` - 61 → 0 classes
  - `dashboard.html` - 176 → 0 classes
  - `config/system.html` - 111 → 0 classes
  - `settings.html` - 121 → 83 custom classes
  - `certs/detail.html` - 96 → 32 custom classes
  - `certs/list.html` - 100 → 27 custom classes

### Added
- **Custom CSS Component System**:
  - Components: `.card`, `.btn`, `.btn-primary`, `.btn-secondary`, `.btn-danger`
  - Badges: `.badge-success`, `.badge-danger`, `.badge-warning`, `.badge-info`
  - Forms: `.form-input`, `.form-label`, `.form-select`, `.form-textarea`
  - Modals: `.modal-form-input`, `.modal-form-label`, `.modal-form-grid-2`
  - Stats: `.stat-card`, `.stat-value`, `.stat-label`
- **CSS Variable System**:
  - Colors: `--text-primary`, `--primary-color`, `--success-color`, `--danger-color`
  - Backgrounds: `--bg-primary`, `--bg-secondary`, `--card-bg`
  - UI: `--border-color`, `--modal-backdrop`, `--shadow-sm/md/lg/xl`

### Technical Details
- No Tailwind dependencies in build pipeline
- Theme-aware design system via CSS variables
- Semantic class names for maintainability
- Reduced CSS bundle size

---

## [1.2.0] - 2026-01-04

### 🎭 Modal System & Global Utilities

### Added
- **Global Modal Utilities** (`modal-utils.js`):
  - `openModal(modalId)` - Opens modal with scroll lock
  - `closeModal(modalId)` - Closes modal and restores scrolling
- **Body Scroll Lock** - Background scrolling disabled when modals open
- **HTMX Modal Integration** - Trigger support for modal opening

### Changed
- **Modal Z-Index Hierarchy**:
  - Modal backdrop: z-index 999
  - Modal container: z-index 1000 (above sidebar)
- Modal CSS improvements with better centering and transitions

### Fixed
- Modal positioning (no longer under sidebar)
- Scroll behavior when modals open/close
- HTMX triggers from sidebar
- Backdrop interaction blocking

### Documentation
- Docker migration guide
- Docker features and best practices
- Release summary v1.0.0 to v1.0.1

---

## [1.1.0] - 2026-01-04

### 🎨 Complete Theming System (8 Themes)

### Added
- **8 Complete Themes** (4 light + 4 dark):
  - Sentinel Light/Dark - Professional blue/gray
  - Amber Light/Dark - Warm orange/amber
  - Blossom Light/Dark - Pink/purple gradients
  - Nebula Light/Dark - Purple/magenta cosmic
- **CSS Variable Theming** - Centralized color management
- **Theme Switcher Component**:
  - Palette icon dropdown in header
  - Moon/Sun toggle for light/dark
  - Visual theme cards with preview
  - Instant theme application
- **Persistent Theme Storage** - localStorage with auto-load
- **Custom Scrollbars** - Theme-aware (dark/light contrasts)

### Changed
- **Login Page Complete Redesign**:
  - 8-theme selector grid (4x2)
  - Theme preview cards
  - Responsive design
- **Settings Page Redesign** (4 sections):
  - Profile Information (username, role badges)
  - Change Password form
  - Theme Preferences gallery
  - Session Information
- **Component Library** - Migrated to CSS variables

### Technical Details
- 8 theme CSS files in `static/css/themes/`
- `theme-switcher.js` for theme management
- Anti-FOUC script in `<head>`
- FontAwesome icon integration
- Responsive mobile-first design

### Quality Assurance
- ✅ All themes tested on major browsers
- ✅ Theme persistence verified
- ✅ Responsive on mobile/tablet/desktop
- ✅ WCAG AA color contrast compliant

---

## [1.0.1] - 2026-01-04

### 🐛 Critical Bug Fixes & Polish

### Added
- **Security Headers** - `Permissions-Policy` header
- **Favicon Integration** - `favicon.svg` with UCM branding
- **Global Toast Notifications** - `showToast()` available on all pages

### Fixed
- **7 Critical Bugs**:
  1. showToast() availability across all pages
  2. Permissions-Policy header missing
  3. Tailwind CDN console warning
  4. Favicon 404 error
  5. verify_ssl checkbox TypeError (null reference)
  6. Test Connection 400 error (OPNsense)
  7. Execute Import 500 error (credential handling)

### Changed
- Enhanced debug logging for OPNsense integration
- Improved error messages for API debugging

---

## [1.0.0] - 2026-01-04

### 🎉 Initial Production Release

### Core Features
- **Complete CA Management**:
  - Create root and intermediate CAs
  - Key types: RSA 2048/4096, ECDSA P-256/P-384/P-521
  - Hash algorithms: SHA-256, SHA-384, SHA-512
  - Customizable DN fields (CN, O, OU, C, ST, L)
  - CA lifecycle management
  
- **Certificate Operations**:
  - Manual certificate creation
  - CSR handling and signing
  - Certificate revocation
  - Export formats: PEM, DER, PKCS#12
  - Full metadata display
  
- **Security Infrastructure**:
  - HTTPS server with self-signed certificate
  - JWT authentication with expiration
  - bcrypt password hashing
  - Role-based access control (Admin/User)
  - Session management
  
- **SCEP Server**:
  - RFC 8894 compliant
  - Certificate enrollment
  - Approval/rejection workflow
  
- **Web UI**:
  - Responsive design
  - Dashboard with statistics
  - CA and certificate management pages
  - HTMX for dynamic updates
  
- **REST API**:
  - JWT-based authentication
  - Complete CRUD operations
  - CA, certificate, and user endpoints
  
- **Database**:
  - SQLite with SQLAlchemy ORM
  - Models for CA, certificates, users, trust store

### Development Phases
- Phase 1: HTTPS server, auth, database, API framework
- Phase 2: Trust Store, CA service, CA API
- Certificate Service: Create, CSR, sign, revoke, export

### Technology Stack
- Flask backend
- SQLAlchemy ORM
- Python cryptography library
- HTMX frontend
- SQLite database

### Pre-Release Fixes (6 bugs)
1. CA Details DN fields display
2. CA Details technical specs
3. CA menu overflow positioning
4. Certificate badges (CRT/KEY/CSR counts)
5. System paths to `/opt/ucm`
6. Managed certificate dropdown

---

## 📊 Version Summary

| Version | Date | Focus | Key Achievement |
|---------|------|-------|----------------|
| **1.0.0** | 2026-01-04 | Core PKI | Production-ready CA Manager |
| **1.0.1** | 2026-01-04 | Bug fixes | 7 critical bugs resolved |
| **1.1.0** | 2026-01-04 | Theming | 8 themes with full system |
| **1.2.0** | 2026-01-04 | Modals | Modal utilities & z-index |
| **1.3.0** | 2026-01-05 | CSS Migration | 827 Tailwind classes removed |
| **1.4.0** | 2026-01-05 | UX Polish | Login redesign, FOUC fix |
| **1.5.0** | 2026-01-05 | CRL/CDP | RFC 5280 compliance (9 endpoints) |
| **1.6.0** | 2026-01-05 | Final Polish | Production-ready UI |

---

## 🚀 Roadmap (Planned for v1.7.0+)

### Features Planned (Not Yet Implemented)
- **ACME Protocol** - RFC 8555 (Let's Encrypt compatibility)
- **Certificate Templates** - Pre-configured profiles
- **Email Notifications** - Expiry alerts, events
- **Webhook Support** - External integrations
- **Advanced Reporting** - Analytics, compliance reports
- **OCSP Responder** - Real-time status validation

### Enterprise (v2.0.0+)
- HSM Support
- LDAP/AD Integration
- High Availability clustering
- PostgreSQL/MySQL support
- Multi-tenancy

---

**Note**: Versions 1.0.1-1.5.0 were developed January 4-5, 2026, following repository damage. This changelog reconstructs the complete history from commits and session documentation.

## [1.6.0] - 2026-01-05

### 🎯 Major UI Overhaul - Production Ready

### Added
- **Custom Styled Scrollbars** - Theme-aware scrollbars for all 8 themes (light themes → dark scrollbars, dark themes → light scrollbars)
- **Modal Body Scroll Lock** - Prevents background scrolling when modals are open
- **Global Modal Utilities** - New `modal-utils.js` library with `openModal()` and `closeModal()` helpers
- **CRL Information Pages**:
  - Public page: `/cdp/{refid}/info` (no authentication required)
  - Integrated page: `/crl/info/{refid}` (with authentication)
  - Complete CRL metadata display
- **HTMX Modal Triggers** - Support for opening modals from sidebar links via HTMX
- Manual certificate and CA import endpoints
- Missing `services/__init__.py` with database models

### Changed
- **BREAKING: Complete Tailwind CSS Removal**
  - Removed ~827 Tailwind utility classes across 50+ files
  - Migrated to custom CSS with CSS variables system
  - All templates now use semantic custom classes
- **Enhanced Modal System**:
  - Modal z-index increased to 1000 (above sidebar at 999)
  - Improved modal positioning and backdrop behavior
  - Consistent modal styling across all themes
- **Theme Consistency** - Updated all 8 templates to use theme variables exclusively
- **Documentation** - Simplified README with redirect to comprehensive wiki

### Fixed
- **Modal Positioning Issues** - Modals no longer appear under sidebar
- **JavaScript Variable Conflicts** - Resolved redeclarations:
  - `pkcs12ExportId`, `pkcs12ExportType`, `pkcs12Params`
  - `IconSystem` and `SessionManager` scope conflicts
- **HTMX Integration** - Fixed sidebar modal triggers not working with HTMX
- **Theme Flash** - Eliminated white flash on page load (anti-FOUC implementation)
- **Scrollbar Visibility** - Corrected scrollbar display when no modal is open
- **CI Workflow** - Added proper permissions for GitHub releases

### Technical Details
- **Statistics**:
  - Files changed: 50+
  - Lines added: ~2,000
  - Lines removed: ~1,500
  - Tailwind classes removed: 827
  - New JS libraries: 1 (modal-utils.js)
  - New templates: 2 (CRL info pages)
- **Custom CSS Classes Created**:
  - Components: `.card`, `.btn`, `.btn-primary`, `.btn-secondary`, `.btn-danger`, `.btn-success`
  - Badges: `.badge-success`, `.badge-danger`, `.badge-warning`, `.badge-info`
  - Forms: `.form-input`, `.form-label`, `.form-select`, `.form-textarea`
  - Modals: `.modal-form-input`, `.modal-form-label`, `.modal-form-grid-2`
  - Stats: `.stat-card`, `.stat-value`, `.stat-label`
- **CSS Variables Used**:
  - Colors: `--text-primary`, `--text-secondary`, `--primary-color`, `--success-color`, `--danger-color`
  - Backgrounds: `--bg-primary`, `--bg-secondary`, `--card-bg`
  - Other: `--border-color`, `--modal-backdrop`, `--shadow-sm/md/lg/xl`
- HX-Trigger-After-Swap integration for modal workflows
- Z-index hierarchy properly defined throughout application
- Main branch trigger added to CI workflows

## [1.5.0] - 2026-01-05

### 🔐 CRL/CDP Implementation - RFC 5280 Compliant (3 Phases, 1h37)

#### Phase 1: Backend Infrastructure (1h13)

### Added
- **CRL Distribution Points (CDP)** - Complete RFC 5280 compliant implementation
- **CRL Model** - New `CRLMetadata` table for storing CRL history and metadata
- **CRL Service** - Full RFC 5280 compliant CRL generation and management
- **Database Migration** - CDP columns added to CA table (`cdp_enabled`, `cdp_url`)
- **Private API Endpoints** (5 endpoints, authenticated):
  - `GET /api/v1/crl/` - List all CRLs across all CAs
  - `GET /api/v1/crl/<ca_id>` - Get CRL metadata and generation history
  - `POST /api/v1/crl/<ca_id>/generate` - Manually generate/regenerate CRL
  - `GET /api/v1/crl/<ca_id>/download` - Download CRL in PEM or DER format
  - `GET /api/v1/crl/<ca_id>/revoked` - List all revoked certificates for a CA
- **Public CDP Endpoints** (4 endpoints, no authentication):
  - `GET /cdp/<ca_refid>/crl.pem` - Download CRL in PEM format
  - `GET /cdp/<ca_refid>/crl.der` - Download CRL in DER format (binary)
  - `GET /cdp/<ca_refid>/crl.crl` - Download CRL (.crl alias for compatibility)
  - `GET /cdp/<ca_refid>/info` - Get CRL metadata in JSON format

#### Phase 2: Certificate Integration (12min)

### Added
- **CDP Extension in Certificates** - All issued certificates now include CDP extension pointing to CRL
- **Auto-generation on Revocation** - CRL automatically regenerates when certificates are revoked
- **Serial Number Validation** - RFC 5280 compliance (159 bits maximum)

### Changed
- Certificate issuance now injects CDP distribution point
- Revocation workflow triggers automatic CRL regeneration

### Fixed
- Serial number generation limited to 159 bits (RFC 5280 compliance)

#### Phase 3: UI Management (12min)

### Added
- **CRL Management Page** (`/crl`):
  - Table displaying all CAs with CDP status, CRL status, revoked certificate count
  - Status badges: 🟢 Up-to-date, 🟡 Expiring soon, 🔴 Stale, ⚪ Never generated
  - Actions: Download PEM, Download DER, Force regenerate
  - Refresh all CRLs button
- **CA Detail - CDP Section**:
  - Enable/disable CDP toggle
  - CDP URL template input with `{ca_refid}` variable substitution
  - Live URL preview showing actual CDP URLs
  - Quick actions: View CRL info (public), Download CRL (PEM), Configure CDP
- **Sidebar Integration** - New "CRL Management" menu link with icon

### Technical Details
- **CRL Extensions**:
  - CRL Number (sequential, auto-increment)
  - Authority Key Identifier (links to issuing CA)
  - Revocation Reason (per certificate)
- **MIME Types**:
  - PEM: `application/x-pem-file`
  - DER: `application/pkix-crl`
- **Caching Strategy** - CRLs stored in database, no regeneration per request
- **Status Calculation** - Date-based logic for CRL freshness determination
- **URL Validation** - CDP URL template validation with variable preview
- **Access Control** - Public/authenticated endpoint separation
- **HTMX Integration** - Dynamic status updates without page reload

### Tests Validated
- ✅ CDP extension present in issued certificates (OpenSSL verified)
- ✅ CRL auto-generation on certificate revocation
- ✅ Public CDP download endpoints accessible without authentication
- ✅ RFC 5280 compliance verified
- ✅ Serial number validation (159-bit limit)
- ✅ CRL status badges update correctly

## [1.4.0] - 2026-01-05

### 🎨 Login Redesign & Theme Enhancements

### Added
- **Login Page Complete Redesign**:
  - 8-theme selector dropdown available pre-authentication
  - Palette icon + moon/sun toggle for theme switching
  - Persistent theme selection across login flow
  - Visual theme preview before authentication
- **Anti-FOUC (Flash of Unstyled Content) Implementation**:
  - Inline script in `<head>` loads theme before DOM rendering
  - Eliminates white flash on page load
  - Synchronous CSS loading via `document.write()`

### Changed
- **SCEP Configuration Button Styling**:
  - All 8 SCEP buttons properly styled with theme-aware classes
  - Buttons: Save Configuration, Configure, Manage, Approve, Reject, Test Connection, Execute Import, Use This
  - Consistent color scheme across all themes
- **Theme Loading Optimization**:
  - Theme script moved from DOMContentLoaded to immediate execution
  - Removed unnecessary CSS reload events
  - localStorage theme read happens before page render

### Fixed
- **Theme Flash Eliminated** - No more white background flash during page load
- **Login Theme Persistence** - Selected theme now persists through authentication

### Technical Details
- Script positioned inline in `<head>` for immediate execution
- Theme initialization occurs before DOM renders
- Optimized for performance (no CSS reload after page load)

## [1.3.0] - 2026-01-05

### 🎯 Tailwind CSS Complete Removal (~827 Classes)

### Changed
- **MAJOR: Complete Tailwind CSS Migration** - Removed all ~827 Tailwind utility classes
- **Templates Migrated** (8 core templates, 100% Tailwind-free):
  1. `cas/detail.html` - 132 → 0 Tailwind classes
  2. `scep.html` - 89 → 0 Tailwind classes
  3. `cas/list.html` - 61 → 0 Tailwind classes
  4. `dashboard.html` - 176 → 0 Tailwind classes
  5. `config/system.html` - 111 → 0 Tailwind classes
  6. `settings.html` - 121 → 83 custom classes (no Tailwind)
  7. `certs/detail.html` - 96 → 32 custom classes
  8. `certs/list.html` - 100 → 27 custom classes

### Added
- **Custom CSS Component System**:
  - **Components**: `.card`, `.btn`, `.btn-primary`, `.btn-secondary`, `.btn-danger`, `.btn-success`, `.btn-outline`
  - **Badges**: `.badge-success`, `.badge-danger`, `.badge-warning`, `.badge-info`, `.badge-secondary`
  - **Forms**: `.form-input`, `.form-label`, `.form-select`, `.form-textarea`, `.form-checkbox`
  - **Modals**: `.modal-form-input`, `.modal-form-label`, `.modal-form-grid-2`
  - **Stats**: `.stat-card`, `.stat-value`, `.stat-label`
  - **Utilities**: `.spinner`, `.info-box`, `.dropdown-item`, `.table-responsive`
- **CSS Variable System**:
  - **Colors**: `--text-primary`, `--text-secondary`, `--text-muted`, `--primary-color`, `--success-color`, `--danger-color`, `--warning-color`, `--info-color`
  - **Backgrounds**: `--bg-primary`, `--bg-secondary`, `--card-bg`, `--danger-bg`, `--success-bg`, `--warning-bg`, `--info-bg`
  - **UI Elements**: `--border-color`, `--hover-color`, `--modal-backdrop`, `--shadow-sm`, `--shadow-md`, `--shadow-lg`, `--shadow-xl`
  - **Layout**: `--sidebar-width`, `--header-height`, `--border-radius-sm/md/lg`

### Technical Details
- **Migration Strategy**:
  - Tailwind utilities replaced with semantic custom classes
  - Layout utilities (flexbox, grid) converted to inline CSS
  - Spacing and sizing moved to custom classes with CSS variables
- **No Tailwind Dependencies** - Completely removed from build pipeline
- **Theme-aware Design System** - All components respect CSS variable theming
- **Improved Maintainability** - Semantic class names improve code readability
- **Performance** - Reduced CSS bundle size by eliminating unused Tailwind classes

### Quality Assurance
- ✅ All 8 templates verified Tailwind-free
- ✅ All themes work correctly with new CSS system
- ✅ Responsive design maintained across all breakpoints
- ✅ No visual regressions detected
- ✅ Cross-browser compatibility verified

## [1.2.0] - 2026-01-04

### 🎭 Modal System Improvements & Z-Index Fixes

### Added
- **Global Modal Utilities Library** (`modal-utils.js`):
  - `openModal(modalId)` - Opens modal with scroll lock
  - `closeModal(modalId)` - Closes modal and restores scrolling
  - Global functions accessible from any page
- **Body Scroll Lock** - Background scrolling disabled when modals are open
- **HTMX Modal Integration** - Proper trigger support for modal opening from HTMX responses

### Changed
- **Modal Z-Index Hierarchy**:
  - Modal backdrop: z-index 999
  - Modal container: z-index 1000 (above sidebar at 999)
  - Ensures modals always appear above all other UI elements
- **Modal CSS Improvements**:
  - Consistent modal styling across all themes
  - Improved backdrop opacity and blur effects
  - Better modal centering and responsiveness

### Fixed
- **Modal Positioning** - Modals no longer appear under sidebar or other elements
- **Scroll Behavior** - Fixed scrolling issues when modals are open/closed
- **HTMX Triggers** - Modal triggers from sidebar and other HTMX elements now work correctly
- **Backdrop Handling** - Modal backdrop properly blocks background interactions

### Technical Details
- Z-index values standardized across application
- Modal utilities use native JavaScript (no jQuery dependency)
- HTMX event listeners integrated for modal workflows
- CSS transitions for smooth modal open/close animations

### Documentation
- Comprehensive Docker migration guide
- Docker features and best practices guide
- Complete release summary v1.0.0 to v1.0.1
- Docker deployment documentation

## [1.1.0] - 2026-01-04

### 🎨 Complete Theming System & UI Redesign

### Added
- **8 Complete Theme System** (4 light + 4 dark variants):
  - **Sentinel Light/Dark** - Professional blue/gray palette
  - **Amber Light/Dark** - Warm orange/amber tones
  - **Blossom Light/Dark** - Pink/purple gradients
  - **Nebula Light/Dark** - Purple/magenta cosmic theme
- **CSS Variable Theming Architecture**:
  - Centralized color management via CSS custom properties
  - Theme-specific variables for all UI elements
  - Dynamic theme switching without page reload
- **Theme Switcher Component**:
  - Palette icon dropdown in header
  - Moon/Sun toggle for light/dark mode switching
  - Visual theme cards with live preview
  - Instant theme application
- **Persistent Theme Storage**:
  - Theme preference saved to localStorage
  - Automatically loads user's preferred theme on page load
  - Survives browser sessions and restarts
- **Custom Scrollbars** - Theme-aware scrollbar styling:
  - Light themes: Dark scrollbars for contrast
  - Dark themes: Light scrollbars for visibility
  - Consistent styling across all browsers

### Changed
- **Login Page Complete Redesign**:
  - 8-theme selector grid (4x2 layout)
  - Theme preview cards with color indicators
  - Responsive design for mobile and desktop
  - Beautiful gradient backgrounds per theme
- **Settings Page Complete Redesign** (4 sections):
  - **Profile Information**: Username display with role badges (Admin/User)
  - **Change Password**: Secure password update form
  - **Theme Preferences**: Visual theme gallery with direct selection
  - **Session Information**: Active session status with logout button
  - Responsive 2/4 column grid layouts
- **Component Library Migration**:
  - All components migrated from hardcoded colors to CSS variables
  - Created reusable component classes (`.card`, `.btn-*`, `.badge-*`)
  - Form components standardized (`.form-input`, `.form-label`, `.form-select`)

### Technical Details
- **Theme Files Structure**:
  - `static/css/themes/sentinel-light.css`
  - `static/css/themes/sentinel-dark.css`
  - (6 more theme files)
- **JavaScript Integration**:
  - `theme-switcher.js` - Theme management and localStorage handling
  - Anti-FOUC script in `<head>` - Prevents flash of unstyled content
  - Theme initialization before DOM load
- **Icon Integration**:
  - FontAwesome icons for UI elements
  - Theme-specific icon colors via CSS variables
  - Hover effects and transitions
- **Responsive Design**:
  - Mobile-first approach
  - Breakpoints for tablet and desktop
  - Touch-friendly theme switcher on mobile

### Quality Assurance
- ✅ All 8 themes tested on Chrome, Firefox, Safari, Edge
- ✅ Dark/Light mode transitions smooth and instant
- ✅ Theme persistence verified across browser sessions
- ✅ Responsive design tested on mobile, tablet, desktop
- ✅ No visual regressions on existing pages
- ✅ Accessibility: Color contrast ratios verified (WCAG AA compliant)

### Documentation
- Multi-distribution installer support
- Docker containerization documentation
- Comprehensive v1.0.0 release documentation
- Docker deployment guides

## [1.0.1] - 2026-01-04

### 🐛 Critical Bug Fixes & Polish

### Added
- **Security Headers**:
  - `Permissions-Policy` header (camera, microphone, geolocation restrictions)
  - `@app.after_request` decorator for global header injection
- **Favicon Integration**:
  - Created `favicon.svg` with UCM branding
  - Integrated across all pages
  - Eliminates 404 errors in browser console
- **Global Toast Notifications**:
  - `showToast()` function now available on all pages
  - Consistent notification system across entire application

### Changed
- **Debug Logging Enhanced**:
  - Improved error messages for OPNsense debugging
  - Better credential handling in import service
  - More informative API error responses

### Fixed
- **7 Critical Bugs**:
  1. **showToast() Availability** - Toast notifications now accessible globally on all pages
  2. **Permissions-Policy Header** - Added explicit security policy header to prevent console warnings
  3. **Tailwind CDN Warning** - Suppressed development mode console warning
  4. **Favicon 404 Error** - Created and integrated favicon.svg
  5. **verify_ssl Checkbox TypeError** - Fixed null reference error, hardcoded to `false` for development
  6. **Test Connection 400 Error** - Improved error handling and messages for OPNsense connection testing
  7. **Execute Import 500 Error** - Fixed credential handling in import form submission

### Technical Details
- Added `@app.after_request` decorator for global header management
- Repositioned `showToast()` function to global scope in base template
- Enhanced error handling in OPNsense service with detailed logging
- Favicon format: SVG (scalable, theme-aware)

### Quality Assurance
- ✅ All 7 bugs verified fixed
- ✅ No console errors or warnings
- ✅ Toast notifications working on all pages
- ✅ Security headers present in all responses
- ✅ Favicon displays correctly in all browsers

### Documentation
- Docker containerization guides
- Multi-distribution installer documentation
- GitHub Actions CI/CD documentation
- Enhanced installation instructions

## [1.0.0] - 2026-01-04

### 🎉 Initial Production Release

### Added - Core Features
- **Complete Certificate Authority (CA) Management**:
  - Create root and intermediate CAs
  - Configure key types (RSA 2048/4096, ECDSA P-256/P-384/P-521)
  - Hash algorithms (SHA-256, SHA-384, SHA-512)
  - Customizable DN fields (CN, O, OU, C, ST, L)
  - Validity period configuration
  - CA lifecycle management (active/revoked status)
  
- **Certificate Issuance and Management**:
  - Manual certificate creation with DN configuration
  - Certificate Signing Request (CSR) handling
  - Certificate signing by selected CA
  - Certificate revocation with CRL generation
  - Certificate export formats:
    - PEM (certificate, private key, chain)
    - DER (binary format)
    - PKCS#12 (password-protected bundle)
  - Certificate detail view with full metadata
  
- **Trust Store Management**:
  - Centralized trust store service
  - Certificate chain validation
  - Root and intermediate CA storage
  - Trust relationship management

- **RESTful API**:
  - JWT-based authentication
  - Comprehensive API endpoints for all operations
  - API documentation (OpenAPI/Swagger)
  - Role-based access control (Admin/User)

- **Security Infrastructure**:
  - HTTPS server with self-signed certificate
  - Secure password hashing (bcrypt)
  - JWT token authentication with expiration
  - HTTPS-only communication enforced
  - Session management with timeout
  - Role-based authorization

- **Database Backend**:
  - SQLite database for data persistence
  - SQLAlchemy ORM for database operations
  - Models for CA, Certificates, Users, Trust Store
  - Database migrations support

- **SCEP (Simple Certificate Enrollment Protocol)**:
  - SCEP server implementation
  - Certificate enrollment endpoint
  - Request approval/rejection workflow
  - SCEP configuration management

- **Web-Based User Interface**:
  - Responsive design for mobile and desktop
  - Dashboard with statistics and overview
  - CA list and detail pages
  - Certificate list and detail pages
  - SCEP management interface
  - Settings and configuration pages
  - User authentication pages (login/logout)

- **Theming System**:
  - Professional UI design
  - Consistent color scheme
  - Icon integration (FontAwesome)
  - Responsive layouts
  - HTMX for dynamic UI updates

### Fixed - Pre-Release (6 bugs during v1.0.0 development)
1. **CA Details DN Fields** - CN, O, C, ST, L, OU now display correctly
2. **CA Details Technical Specs** - Key Type and Hash Algorithm properly shown
3. **CA Menu Overflow** - Fixed positioning of dropdown menus
4. **Certificate Badges** - Badge counts accurate (CRT: 30, KEY: 27, CSR: 1)
5. **System Paths** - Corrected all paths to `/opt/ucm`
6. **Managed Certificate Dropdown** - Now shows all 26 certificates correctly

### Technical Details - Foundation
- **Development Phases**:
  - **Phase 1**: HTTPS server, authentication, database, API framework
  - **Phase 2**: Trust Store service, CA service, CA API endpoints
  - **Certificate Service**: Create, CSR, sign, revoke, export functionality
  - All core features tested and validated

- **Technology Stack**:
  - **Backend**: Flask (Python web framework)
  - **ORM**: SQLAlchemy
  - **Cryptography**: Python `cryptography` library
  - **Frontend**: HTMX, vanilla JavaScript
  - **Authentication**: JWT (JSON Web Tokens)
  - **Database**: SQLite
  - **WSGI Server**: Flask development server (production: Gunicorn recommended)

- **File Structure**:
  ```
  /opt/ucm/
  ├── backend/
  │   ├── api/          # REST API endpoints
  │   ├── services/     # Business logic (CA, Cert, CRL, Trust Store)
  │   ├── models/       # Database models
  │   └── utils/        # Utilities (crypto, JWT, validators)
  ├── static/
  │   ├── css/          # Stylesheets
  │   └── js/           # JavaScript libraries
  ├── templates/        # Jinja2 HTML templates
  ├── data/
  │   ├── db/           # SQLite database
  │   ├── ca/           # CA certificates and keys
  │   └── certs/        # Issued certificates
  └── app.py            # Application entry point
  ```

### Quality Assurance
- ✅ All core features tested and working
- ✅ API endpoints validated
- ✅ Certificate operations verified with OpenSSL
- ✅ Security measures in place and tested
- ✅ Database operations stable
- ✅ UI responsive and functional
- ✅ SCEP enrollment workflow validated
- ✅ No critical bugs remaining

### Known Limitations (v1.0.0)
- Single-server deployment (no clustering)
- SQLite database (not recommended for high-load production)
- No LDAP/AD integration
- No HSM support
- Basic CRL support (no OCSP yet)
- No email notifications
- No certificate templates
- No automated backups

---

## 📊 Version History Summary

| Version | Date | Duration | Focus | Files Changed | Features | Bugs Fixed | Status |
|---------|------|----------|-------|---------------|----------|------------|--------|
| **1.0.0** | 2026-01-04 | 3 phases | Core CA Manager | - | Full PKI | 6 | ✅ Baseline |
| **1.0.1** | 2026-01-04 | 1 session | Bug fixes & polish | 10+ | 3 | 7 | ✅ Stable |
| **1.1.0** | 2026-01-04 | 1 session | Theming system | 20+ | 8 themes | 0 | ✅ Complete |
| **1.2.0** | 2026-01-04 | 1 session | Modal improvements | 5+ | Modal utils | 3 | ✅ Complete |
| **1.3.0** | 2026-01-05 | 2 sessions | Tailwind removal | 50+ | CSS system | 0 | ✅ 100% Clean |
| **1.4.0** | 2026-01-05 | 1 session | Login & theme polish | 8+ | FOUC fix | 2 | ✅ Complete |
| **1.5.0** | 2026-01-05 | 3 phases (1h37) | CRL/CDP RFC 5280 | 15+ | 9 endpoints | 1 | ✅ Complete |
| **1.6.0** | 2026-01-05 | 1 session | UI overhaul | 50+ | Scrollbars, cleanup | 6 | ✅ **READY** |

---

## 🎯 Feature Evolution Timeline

### Certificate Authority Features
- **v1.0.0**: Core CA creation, management, DN configuration, key types (RSA/ECDSA)
- **v1.5.0**: CRL generation, CDP distribution points, RFC 5280 compliance

### User Interface
- **v1.0.0**: Basic responsive UI, HTMX integration
- **v1.1.0**: 8-theme system, theme switcher, CSS variables
- **v1.2.0**: Modal utilities, z-index fixes, scroll lock
- **v1.3.0**: Complete Tailwind removal (~827 classes), custom CSS
- **v1.4.0**: Login redesign, anti-FOUC, theme persistence
- **v1.6.0**: Custom scrollbars, modal improvements, CRL info pages

### API & Backend
- **v1.0.0**: REST API, JWT auth, SQLite, Trust Store
- **v1.5.0**: CRL API (5 private + 4 public endpoints), auto-generation on revoke

### Security & Compliance
- **v1.0.0**: HTTPS, JWT, bcrypt, role-based access
- **v1.0.1**: Permissions-Policy header, security enhancements
- **v1.5.0**: RFC 5280 CRL compliance, CDP extensions

---

## 🚀 What's Next? (Planned for v1.7.0+)

### Short-term (v1.7.0 - v1.9.0)
- **ACME Protocol Support** (RFC 8555) - Let's Encrypt compatibility
- **Certificate Templates** - Pre-configured certificate profiles
- **Email Notifications** - Certificate expiry alerts, revocation notices
- **Webhook Support** - Integration with external systems
- **Advanced Reporting** - Certificate inventory, expiry reports, audit logs
- **Backup & Restore** - Automated backup system
- **OCSP Responder** - Real-time certificate status checking

### Long-term (v2.0.0+) - Enterprise Features
- **HSM Support** - Hardware Security Module integration
- **LDAP/AD Integration** - Enterprise authentication
- **High Availability** - Multi-server clustering
- **Database Options** - PostgreSQL, MySQL support
- **Audit Trail** - Comprehensive logging and compliance reporting
- **API Rate Limiting** - Enhanced security controls
- **Certificate Transparency** - CT log integration
- **Multi-tenancy** - Organization isolation

---

## 📝 Migration Notes

### Upgrading from v1.0.0 to v1.6.0
1. **Backup Database**: `cp /opt/ucm/data/db/ucm.db /opt/ucm/data/db/ucm.db.backup`
2. **Install New Version**: Follow standard installation procedure
3. **Database Migration**: Automatic (CRL tables added in v1.5.0)
4. **Configuration**: Review CDP settings in CA management
5. **Themes**: Select preferred theme (8 options available)

### Breaking Changes
- **v1.6.0**: Tailwind CSS removed - custom themes required if customized
- **v1.5.0**: CRL table schema added - automatic migration runs on first start

---

**Note on Version History**: Versions 1.0.1 through 1.5.0 were developed rapidly between January 4-5, 2026, following repository damage that lost intermediate version tags. This changelog has been reconstructed from commit messages, session notes, and context documentation to preserve the complete development history.

## [2.0.0-beta.5] - 2026-01-29

### Added
- **SCEP Page**: Complete SCEP management UI with configuration, request approval/rejection, and challenge passwords
- **Webhook System**: Full CRUD for webhooks with test functionality
- **Backup System**: Complete encrypted backup/restore with password protection (AES-256-GCM)

### Fixed
- Settings persistence to database (auto-backup, timezone, etc.)
- Fixed `current_user` placeholders in CRL and CSR endpoints
- Save Settings button position in backup section

### Changed
- SCEP configuration now persisted to database
- Webhooks stored as JSON in SystemConfig
- Improved backup file naming with timezone-aware dates
