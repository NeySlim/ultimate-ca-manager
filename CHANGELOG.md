# Changelog

All notable changes to Ultimate CA Manager will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.7.4.1] - 2026-01-08

### Fixed
- **CI/CD**: Prevent create-release workflow from triggering on non-tag pushes
  - Added explicit check to only run when pushing tags
  - Eliminates false workflow failure notifications
  - Workflow now properly skips execution on main branch commits

---

## [1.7.4] - 2026-01-08

### Fixed
- **First Install**: Database tables not created on fresh installation (#4)
  - Import all models in models/__init__.py so db.create_all() creates all tables
  - Fixes "no such table: webauthn_credentials" error on first Docker run
  - Previously only User and SystemConfig models were imported
  - Now imports WebAuthn, AuthCertificate, and Email notification models
- **Auto-Migration**: Automatic database migration now works seamlessly
  - Removed manual migration detection warnings
  - db.create_all() automatically creates missing tables
  - Works for both fresh installs and v1.6.x → v1.7.x upgrades

---

## [1.7.3] - 2026-01-08

### Fixed
- **Database Migration**: Missing webauthn_credentials table when upgrading from v1.6.x (#4)
  - Enhanced migrate_v1_7_0_auth.py to create WebAuthn tables
  - Added automatic detection of missing tables on startup
  - Application now displays migration instructions in logs
  - Created comprehensive MIGRATION_GUIDE_v1.7.0.md

### Added
- **Migration Detection**: Startup check for missing database tables
  - Helpful error messages with Docker and system install instructions
  - Links to migration guide and GitHub issue
- **Documentation**: Complete migration guide for v1.7.0 upgrades
  - Docker and system installation instructions
  - Troubleshooting common migration issues
  - Database backup recommendations

---

## [1.7.2] - 2026-01-08

### Fixed
- **Docker Startup**: Add missing webauthn and cbor2 dependencies (#3)
  - Application now starts correctly in Docker
  - Fixes ModuleNotFoundError for webauthn module
  - Added webauthn==2.2.0 and cbor2==5.6.5 to requirements.txt

---

## [1.7.1] - 2026-01-08

### Fixed
- **Database Initialization**: Prevent UNIQUE constraint violation on first startup in multi-worker environments (#2)
  - Added IntegrityError handling for concurrent initialization
  - Check existing SystemConfig entries before creation
  - Early constraint detection with flush() before commit

---

## [1.7.0] - 2026-01-08

### 🎉 Major Feature Release

This release introduces three major authentication methods (Email Notifications, WebAuthn/FIDO2, mTLS), enhanced UI navigation, and significant UX improvements.

### Added - Major Features

#### 📧 Email Notifications System
- **SMTP Configuration**: Full SMTP server setup with TLS/SSL support
- **Alert Rules**: Configurable notifications for certificate and CRL expiration
  - Customizable threshold in days before expiration
  - Per-rule recipient email lists
- **Notification History**: Complete log of sent notifications with success/failure tracking
- **Statistics Dashboard**: View sent/failed counts for last 30 days
- **Test Email Function**: Verify SMTP configuration before deployment
- **Manual Check**: Trigger immediate expiration checks on-demand
- **New UI Page**: `/config/notifications` for complete notification management
- **New API Endpoints**: 7 endpoints for SMTP config, rules, history, and stats
- **Database Tables**: `smtp_config`, `notification_config`, `notification_log`

#### 🔐 WebAuthn/FIDO2 Support
- **Passwordless Authentication**: Login with security keys (YubiKey, Windows Hello, Touch ID, Face ID)
- **Multiple Credentials**: Register and manage multiple security keys per user
- **Credential Management**:
  - View all registered keys with metadata (name, registration date, last used, sign counter)
  - Enable/disable individual credentials
  - Delete unused credentials
- **Security Features**:
  - Challenge-response authentication protocol
  - Replay protection via sign counter
  - Domain-scoped credentials (RP ID)
  - User verification support (PIN/biometrics)
- **Hardware Token Support**: YubiKey, Titan Key, all FIDO2-compliant devices
- **Browser Biometric Support**: Windows Hello, Touch ID, Face ID
- **New UI Page**: `/config/webauthn` for security key management
- **Enhanced Login**: "Sign in with Security Key" button on login page
- **New API Endpoints**: 7 endpoints for registration, authentication, and credential management
- **Database Table**: `webauthn_credentials`

#### 🛡️ mTLS Client Certificate Authentication
- **Certificate-Based Login**: Authenticate using X.509 client certificates
- **Auto-Login**: Automatic authentication when valid certificate is detected
- **Hybrid Mode**: Simultaneous support for mTLS and password authentication
- **Certificate Management**:
  - Associate certificates with user accounts
  - Enable/disable individual certificates
  - View certificate details (issuer, subject, serial, expiration)
  - Auto-detect current client certificate
- **Reverse Proxy Integration**:
  - Nginx configuration generator with copy-to-clipboard
  - Apache configuration generator with copy-to-clipboard
  - Automatic header parsing (X-SSL-Client-*)
- **Security Features**:
  - Certificate chain validation
  - CRL/OCSP revocation checking
  - Subject DN validation
  - Serial number tracking
- **New UI Page**: `/config/mtls` for certificate management
- **New API Endpoints**: 5 endpoints for certificate management and auto-detection
- **Database Table**: `auth_certificates`

#### 🎨 Enhanced UI Navigation & Organization
- **Collapsible Sidebar Submenus**:
  - Certificate Authorities, Certificates, and SCEP sections with expandable/collapsible submenus
  - Smooth chevron rotation animations (0deg → 180deg)
  - State persisted in localStorage (`sidebar-{section}-expanded`)
  - Auto-expand when child page is active
  - HTMX-aware: reinitialize after content swaps
- **Submenu Icons**: 14×14px SVG icons for all submenu items with hover effects
- **My Account Section**: User-specific settings grouped at bottom of sidebar
  - Email Notifications, mTLS Authentication, Security Keys
  - Visual separator with border-top for clear distinction
- **My Account Page**: New dedicated `/my-account` page
  - Profile information (username, role)
  - Password change form
  - Theme preferences (8 themes × 2 variants)
  - Session configuration (duration, login method, logout)
- **Settings Page Reorganization**: 
  - Now reserved for administrators only
  - Clear separation of user preferences and admin settings
  - Visual headers with icons for each section

#### 🎭 Themed Modal System
- **Custom Modals**: Replace browser native `alert()`, `confirm()`, `prompt()`
- **Theme Integration**: Automatic adaptation to all 8 UCM themes
- **Promise-Based API**: Modern async/await support
- **Customizable Options**: Custom buttons, danger mode, icons, multi-step confirmations
- **Animations**: Smooth fade-in/slide-in animations
- **Keyboard Support**: Escape to close, Enter to confirm
- **Click Outside**: Close modal by clicking overlay
- **New File**: `frontend/static/js/modal-system.js`

### Added - UI/UX Improvements
- **Button System Fixes**: Fixed 33 buttons across 5 pages with missing base `btn` class
  - Corrected colors (was pink/salmon, now theme colors)
  - Added missing padding and borders
  - Fixed invisible icons
- **Icon System Standardization**: Complete migration to native UCM SVG icons
  - Replaced FontAwesome classes with `<use href="#icon-name"/>`
  - Better performance (no JS replacement)
  - Theme-aware gradient support
  - New icon classes: `.btn-icon`, `.btn-icon-primary/danger/success/warning`
- **Form Style Unification**: Standardized form inputs across all pages
  - Consistent padding, spacing, borders, backgrounds
  - Theme-aware hover and focus states
  - Unified label positioning and typography
- **Certificate Display Improvements**:
  - Better certificate selection highlighting
  - Improved visual hierarchy in lists
  - Enhanced metadata display
  - Icon filtering for operations
- **Tooltip Preparation**: Added `data-tooltip` attributes to all sidebar links

### Changed
- **Optimized Sidebar Width**: Reduced from 240-260px to uniform 220px across all 8 themes
  - Provides 20-40px more space for main content
  - Standardized width improves consistency
- **Improved Sidebar Layout**: Flexbox-based layout with spacer to push My Account section to bottom
- **JavaScript Architecture**: New `sidebar-toggle.js` module for submenu management (165 lines)
- **Navigation Structure**: Reorganized sidebar with user settings at bottom

### Fixed
- Sidebar submenu persistence across page navigations
- Submenu icon opacity on hover (0.7 → 1.0 transition)
- Button theming inconsistencies across multiple pages
- HTMX content swap duplicate token error (wrapped scripts in IIFE)
- Icon visibility issues in various UI components

### Technical Details
- **New Files Created** (16 files):
  - `frontend/static/js/sidebar-toggle.js` - Submenu management
  - `frontend/static/js/modal-system.js` - Modal system
  - `frontend/templates/my_account.html` - User account page
  - `frontend/templates/config/notifications.html` - Email notifications UI
  - `frontend/templates/config/webauthn.html` - WebAuthn management UI
  - `frontend/templates/config/mtls.html` - mTLS configuration UI
  - `backend/models/email_notification.py` - Email models
  - `backend/models/webauthn.py` - WebAuthn model
  - `backend/models/auth_certificate.py` - mTLS model
  - `backend/services/email_service.py` - SMTP service
  - `backend/services/notification_service.py` - Notification scheduler
  - `backend/api/notification_api.py` - Notification API
  - `backend/api/webauthn_api.py` - WebAuthn API
  - `backend/api/mtls_api.py` - mTLS API
  - `migrations/migrate_email_notifications.py`
  - `migrations/migrate_webauthn.py`
  - `migrations/migrate_mtls.py`
- **Modified Files**: `base.html`, `settings.html`, `login.html`, `components.css`, all theme CSS files, `ui_routes.py`, `settings.py`
- **Database**: 5 new tables (smtp_config, notification_config, notification_log, webauthn_credentials, auth_certificates)
- **Modified CSS**: ~300 lines added to `components.css`
- **Theme Updates**: All 8 themes updated with 220px sidebar width
- **State Management**: localStorage keys for submenu states and theme preferences

### Security
- WebAuthn FIDO2 compliance with challenge-response protocol
- mTLS certificate chain validation with CRL/OCSP support
- Replay protection via sign counter tracking
- Domain-scoped credential storage

### Notes
- Sidebar collapse feature (icon-only mode) explored but disabled due to layout complexity
- Code preserved in comments for future implementation
- All changes tested across 8 themes (Sentinel, Amber, Blossom, Nebula - Light/Dark)
- Email notifications require SMTP server configuration and database migration
- WebAuthn requires HTTPS and modern browser support
- mTLS requires reverse proxy configuration (Nginx/Apache)

---

## [1.6.2] - 2026-01-07

### 🐛 Critical Bugfixes

### Fixed
- **OPNsense Import Page**: Fixed critical JavaScript errors preventing configuration imports
  - Added global `showToast()` function to base template for reliable toast notifications
  - Fixed "showToast is not defined" error in HTMX-loaded content
  - Removed authentication method toggle, now uses API Key only (simplified UX)
  - Improved error handling and user feedback during import process
- **Import Statistics Display**: Fixed toast message showing "0 CA 0 Cert" after successful import
  - Corrected response data parsing in import completion handler
  - Enhanced import result feedback with proper counts

### Changed
- Simplified OPNsense import authentication to API Key only (removed username/password option)
- Improved toast notification system with consistent styling across all themes

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
