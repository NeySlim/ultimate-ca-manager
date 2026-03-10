# Changelog

All notable changes to Ultimate CA Manager will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Starting with v2.48, UCM uses Major.Build versioning (e.g., 2.48, 2.49). Earlier releases used Semantic Versioning.

---

## [Unreleased]

---

## [2.67] - 2026-03-10

### Fixed
- **SSO CA Bundle Round-Trip Bug** — CA certificate PEM content was returned as boolean in API responses, causing PEM to be destroyed on re-save (fixes #33 follow-up)
- API now returns actual PEM content for ca_bundle fields instead of boolean presence indicator
- Update endpoint rejects non-string ca_bundle values to prevent data corruption

---

## [2.66] - 2026-03-09

### Added
- **SSO SSL Verification Controls** — Per-protocol SSL toggle and custom CA certificate (PEM) for OAuth2, SAML, and LDAP providers (fixes #33)
- Users with private/self-signed CA certificates can now connect to OIDC, SAML, and LDAP identity providers
- Custom CA bundle stored as PEM text in database — no filesystem dependency
- SSL warning banner when verification is disabled
- 4 new i18n keys across all 9 locales

### Security
- **SAML Silent Fallback Removed** — SAML metadata fetch no longer silently falls back to `verify=False` (MITM risk)

### Fixed
- All 5 outbound HTTPS requests in SSO module now respect SSL verification settings (3 OAuth2, 1 SAML, 3 LDAP)

---

## [2.65] - 2026-03-09

### Security
- **Unbounded Compliance Query** — `/api/v2/certificates/compliance` now processes certificates in batches of 200 instead of loading all into memory (DoS prevention)
- **LIKE Wildcard Injection** — Certificate search now escapes `%` and `_` wildcards in LIKE queries
- **HTML Injection in Emails** — Discovery notification emails now HTML-escape profile names
- **per_page Cap** — List certificates endpoint now caps `per_page` at 100

### Fixed
- **OCSP Stats Logging** — OCSP stats endpoint now logs query failures instead of silently swallowing errors
- **Compliance Breakdown Null Safety** — Certificate detail compliance breakdown handles malformed data gracefully
- **Unused Variable Cleanup** — Removed unused result variable in OCSP toggle handler

---

## [2.64] - 2026-03-08

### Added
- **Certificate Compliance Scoring** — A+ to F grading system based on key strength, signature algorithm, validity status, SAN presence, and certificate lifetime; grade badge in table and full breakdown in detail view
- **Discovery Expiry Notifications** — `notify_on_expiry` alerts count expiring certificates (≤30 days) after each scan and include them in email notifications
- **Notification Event Toggles** — Three per-profile toggles (new, changed, expiring) in discovery profile form, visible when schedule is enabled
- **Markdown Release Notes** — Update checker renders release notes as styled markdown using react-markdown
- **OCSP Per-CA Toggle** — CRL/OCSP page now has separate CRL and OCSP toggle switches per CA
- **Compliance Stats API** — `/api/v2/certificates/compliance` returns aggregate grade distribution

### Fixed
- **OCSP Dashboard Status** — Dashboard OCSP badge was always gray; `/ocsp/status` endpoint was hardcoded to `enabled: true` without checking DB — now queries actual `ocsp_enabled` flags
- **OCSP Detail Panel** — Detail panel showed global OCSP status instead of selected CA's `ocsp_enabled` state
- **OCSP Stats** — `/ocsp/stats` now returns real response counts from `ocsp_responses` table instead of hardcoded zeros

---

## [2.63] - 2026-03-08

### Added
- **Auto-SAN from CN** — Common Name is automatically included as SAN (DNS for server/combined, Email for email/combined certs) with visual indicator in the form
- **Wildcard base domain suggestion** — When CN is `*.example.com`, suggests adding `example.com` as additional SAN since wildcards don't cover the bare domain
- **Subject email auto-SAN** — Subject DN email field automatically included as Email SAN for email/combined certificates
- Backend auto-includes CN and subject email as SANs during certificate generation

---

## [2.62] - 2026-03-06

### Fixed
- **ACME Challenges Endpoint** — Fixed crash on `/api/v2/acme/accounts/{id}/challenges` caused by accessing non-existent `identifier_value` attribute; now correctly parses JSON `identifier` field

---

## [2.61] - 2026-03-06

### Fixed
- **Dashboard ACME Widget** — Fixed crash when ACME account contact is an array (`.replace()` TypeError)

### Improved
- **OCSP RFC 6960 Compliance** — Unknown certificate serials now return proper `UNKNOWN` status in a signed OCSP response instead of `UNAUTHORIZED` error; deduplicated GET/POST handlers; added `Cache-Control` and `Expires` headers
- **CRL/CDP RFC 5280 Compliance** — CDP endpoint now serves CRLs from database (auto-generates if missing) instead of filesystem; logs warning when serial numbers exceed 159 bits
- **SCEP RFC 8894 Compliance** — Error responses now include `failInfo` attribute; encryption upgraded from DES-CBC to AES-256-CBC (matching advertised capabilities); `GetCACert` returns PKCS#7 chain for intermediate CAs; replaced debug prints with proper logging
- **EST RFC 7030 Compliance** — `/simplereenroll` now requires mTLS only (no longer accepts Basic auth); `/serverkeygen` encrypts private key with client password when available

---

## [2.60] - 2026-03-06

### Fixed
- **ACME Finalize Response** — Certificate URL was missing from finalize order response, causing GitLab and other ACME clients to fail with "No certificate_url to collect the order"

### Improved
- **ACME RFC 8555 Compliance** — Comprehensive audit and fixes for full RFC compliance:
  - Error responses now use `application/problem+json` with `status` field (RFC 7807)
  - EC signature verification converts raw R||S to DER format (RFC 7518 §3.4) — fixes EC key clients
  - Challenge lookup uses proper URL suffix/ID matching instead of unreliable LIKE query
  - JWS signature verification enforced on finalize, order, authz, and cert endpoints
  - POST-as-GET pattern implemented on all resource endpoints (RFC 8555 §6.3)
  - `Retry-After` header on pending/processing order responses
- **ACME New Endpoints** — Added `revokeCert` (RFC 8555 §7.6) and `keyChange` (RFC 8555 §7.3.5) endpoints
- **ACME Account Management** — Support for `onlyReturnExisting` account lookup, contact updates, and account deactivation

---

## [2.59] - 2026-03-06

### Fixed
- **Audit Log Binding Error** — Fixed `sqlite3.InterfaceError` when signing CSRs; dict was passed as positional arg to audit logger instead of string
- **Missing i18n Keys** — Added 12 missing translation keys across all 9 locales (`common.deleted`, `common.dismiss`, `common.exportFailed`, `common.generating`, `common.createdBy`, `acme.renew`, `certificates.cnRequired`, `certificates.localityPlaceholder`, `certificates.statePlaceholder`, `csrs.generateFailed`, `operations.selectCA`, `userCertificates.exportError`)

### Improved
- Added safety guard in `AuditService.log_action()` to auto-serialize dict/non-string values, preventing future binding errors

---

## [2.58] - 2026-03-06

### Fixed
- **SAML IdP Certificate** — Fixed SAML certificate field showing "True" instead of PEM content; `to_dict()` was converting public cert to boolean
- **ACME Account Orders/Challenges** — Fixed queries using integer PK instead of string `account_id` FK, causing orders and challenges to never display
- **ACME Account Email Dedup** — Added email uniqueness check on UI account creation to prevent duplicate accounts
- **ACME Dashboard Widget** — Fixed `mailto:` prefix showing in account emails on dashboard
- **ACME History Environment** — Local ACME certificates now show "Local ACME" badge instead of incorrect "Staging"
- **ACME Domain Form CA Select** — Fixed Radix Select value type mismatch (integer vs string) causing selected CA to not display
- **ACME History Tab Placement** — Moved History tab to its own group since it contains both Local ACME and Let's Encrypt certificates

---

## [2.57] - 2026-03-05

### Fixed
- **CSR SAN Prefix Duplication** — Fixed generated CSRs embedding `DNS:` prefix in SAN values (e.g., `DNS:DNS:example.com`) when frontend sends typed SANs (#31)
- **CSR Key Upload Flash Error** — Fixed brief "Something went wrong" error during private key upload by reordering data refresh (#31)

### Documentation
- Updated UPGRADE.md with version-specific notes for v2.49–v2.56
- Updated USER_GUIDE with Discovery, EST, and Certificate Tools sections
- Updated ADMIN_GUIDE with SSO configuration, EST, and Discovery admin sections
- Updated SECURITY.md with v2.52+ security features (SSRF, WebAuthn, SSO audit)

---

## [2.56] - 2026-03-05

### Fixed
- **ACME/CSR Certificate Compatibility** — Certificates signed from CSRs (ACME, SCEP) now include Extended Key Usage (`serverAuth`) and populate CN from SAN when subject is empty, fixing Edge/Chrome rejection while Firefox accepted them

---

## [2.55] - 2026-03-05

### Fixed
- **Certificate DN Formatting** — Subject and issuer fields now use RFC 4514 abbreviations (CN, C, ST, O, L) instead of verbose Python OID names (commonName, countryName, etc.)
- **ACME Order Status Transitions** — Failed verifications reset to "pending" (retry allowed); successful verifications immediately poll Let's Encrypt for actual status (#29)
- **Auto-fix Migration** — New migration automatically corrects existing certificates with verbose DN format on upgrade

---

## [2.54] - 2026-03-05

### Fixed
- **ACME Client Orders Visibility** — Orders are now displayed in the Let's Encrypt tab with status, actions (verify, finalize, download, renew, delete), and error messages (#29)

---

## [2.53] - 2026-03-05

### Added
- **Intermediate CA Signing** — CSR signing now supports "Intermediate CA" certificate type with `BasicConstraints(CA:TRUE, pathlen:0)` and keyCertSign/crlSign key usage
- **DNS Challenge Warnings** — ACME certificate requests now surface DNS challenge setup failures as user-visible warnings instead of silently failing

### Fixed
- **ACME Account Creation** — Generate JWK key pair (RSA/EC) when creating accounts; previously failed with NOT NULL constraint on `jwk` field (#28)
- **ACME Order Status** — Orders no longer get stuck in "pending" when DNS challenge setup fails (#29)
- **DNS Provider Test Feedback** — Test button now correctly shows success/failure result to user (#30)
- **SSL Checker Local Networks** — Allow checking certificates on private/local networks (192.168.x, 10.x, loopback) — essential for self-hosted PKI
- **HTTPS Certificate Apply** — Show restart overlay when applying a new HTTPS certificate in Settings
- **IPv6 Resolution** — SSL checker uses `getaddrinfo` instead of `gethostbyname` for proper IPv6 support

### Changed
- Removed hardcoded version references from docker-compose files

---

## [2.52] - 2025-07-14

### Added
- **Certificate Discovery** — Network scanner to find TLS certificates on hosts, IPs, and CIDR subnets
- **Quick Scan** — Instant scan without saving a profile; enter targets and ports inline
- **Scan Profiles** — Save and manage reusable scan configurations with targets, ports, worker count
- **Discovered Certificates Inventory** — Track all found certs with managed/unmanaged/error/expired/expiring status
- **Scan History** — Browse past scan runs with duration, found/new/changed/error counts
- **CSV & JSON Export** — Export discovered certificates with all metadata
- **SNI Probing** — Multi-hostname TLS handshake (PTR, target, bare IP) for maximum coverage
- **SAN Extraction** — Extracts all Subject Alternative Names from discovered certificates
- **Bulk DNS Resolution** — Parallel PTR lookups for IP-based targets
- **WebSocket Progress** — Real-time scan progress updates in the UI
- **Split-View Layout** — Table + detail panel for discovered certs, profiles, and scan history
- **Clickable Stats** — Click stat cards to filter the table by status
- **Error Visibility** — Scan errors shown in results with troubleshooting hints
- **In-App Help** — Expanded help panel with scan profiles, filters, errors, export, and security docs
- **Wiki Documentation** — Certificate Discovery page and updated Security page

### Security
- **SSRF Protection** — Blocks scanning of loopback, link-local, multicast, and reserved IPs
- **DNS Rebinding Protection** — PTR hostname validated with forward DNS resolution
- **2FA Brute-Force Protection** — 5 attempt limit with 15-minute lockout for TOTP verification
- **WebAuthn Brute-Force Protection** — Same lockout pattern for FIDO2/WebAuthn verification
- **User Enumeration Prevention** — Generic error messages for WebAuthn credential lookup
- **SSO Audit Logging** — OAuth2/SAML login success/failure events logged to audit trail
- **LDAP Audit Logging** — LDAP authentication attempts logged with success/failure
- **LDAP Password Encryption** — LDAP bind passwords encrypted at rest using master key
- **mTLS Trusted Proxies** — `UCM_TRUSTED_PROXIES` env var limits proxy client cert injection
- **SSO Rate Limiting** — OAuth2 callback and LDAP login endpoints rate-limited
- **Discovery Input Validation** — Target format regex, port range validation, field length limits
- **API Error Sanitization** — ~150 error responses no longer expose internal details

---

## [2.51] - 2026-02-28

### Added
- **EST management page** — full EST (RFC 7030) configuration UI with config, stats, and endpoint info tabs; backend management API (`/api/v2/est/config`, `/stats`)
- **Certificate unhold** — `POST /certificates/<id>/unhold` endpoint to remove certificateHold status; frontend button in detail panel with confirmation dialog
- **Enriched system-status** — dashboard now shows 8 service badges: ACME, SCEP, EST, OCSP, CRL, Auto-Renewal (with pending count), SMTP, Webhooks
- **WebSocket real-time updates** — wired all backend emitters (certificate CRUD, CA, user, settings, audit) to push live updates to dashboard and tables
- **Accordion sidebar navigation** — collapsible section groups with smooth animations, polished styling (200px width), mobile bottom sheet
- **In-app help updates** — documentation for EST, certificate unhold, CSR generate, enriched system-status
- **CSR generation form** — generate CSR directly from the UI with full DN fields and key options
- **Enhanced certificate issuance form** — full options including key usage, extended key usage, SANs, and validity

### Changed
- **Global UI density harmonization** — unified component scale (~34px height): Input, Select, Textarea, SearchBar, Button all aligned; Card padding compacted; table rows tightened (13px font, reduced padding); icon frames 28→24px in tables
- **Settings sidebar** — harmonized with main nav (200px, 13px text, accent bar active state)
- **Dashboard chart curves** — switched from monotone to basis (B-spline) interpolation for smooth rounded lines
- **Sidebar navigation** — mega-menu flyout with hover groups, then refined to accordion pattern with persistent expand/collapse state

### Fixed
- **OCSP null cert crash** — use `add_response_by_hash` when certificate `.crt` data is missing instead of crashing
- **OCSP HSM signing** — added `_HsmPrivateKeyWrapper` to delegate OCSP response signing to HSM providers
- **Dashboard expired count** — backend now returns actual expired certificate count; `expiring_soon` excludes already-expired certs
- **System Health widget spacing** — fixed padding between header and content (desktop + mobile)
- **Flyout menu overlap** — prevented menu superposition on fast hover transitions with debounce
- **Post-install experience** — improved DEB/RPM post-install scripts with FQDN alternatives and correct API URLs
- **Orphan cleanup** — removed obsolete files and unused components

---

## [2.50] - 2026-02-22

### Added
- **Login architecture redesign** — complete rewrite of the authentication flow with state machine (init → username → auth → 2fa/ldap), automatic method detection, and zero-interaction mTLS auto-login
- **mTLS auto-login** — client certificate authentication now happens entirely in the TLS handshake via middleware; no explicit POST required, browser cert → session → auto-redirect to dashboard
- **AuthContext session check on all routes** — removed the `/login` skip guard; `checkSession()` now always calls `/auth/verify` on mount, enabling mTLS auto-login discovery
- **`sessionChecked` state** — new boolean in AuthContext exposed to components, prevents flash of login form during session verification
- **Enhanced `/auth/methods` endpoint** — returns `mtls_status` (auto_logged_in/present_not_enrolled/not_present), `mtls_user`, and `sso_providers` in a single call

### Changed
- **mTLS middleware** — clean rewrite with `_extract_certificate()` helper (DRY), `g.mtls_cert_info` for cross-endpoint reuse, proper stale session handling
- **LoginPage** — removed cascade login logic; each auth method is standalone with proper state transitions; WebAuthn auto-prompts after username entry if keys detected
- **App.jsx `/login` route** — shows `PageLoader` while session is being checked, then redirects if already authenticated

### Fixed
- **mTLS peercert injection** — custom Gunicorn worker (`MTLSWebSocketHandler`) extracts peercert DER bytes into WSGI environ
- **OpenSSL 3.x CA names** — ctypes hack in `gunicorn_config.py` to send client CA names in CertificateRequest
- **Timezone-aware datetime comparison** — fixed crash in `mtls_auth_service.py` when comparing naive vs aware datetimes
- **Serial number format mismatch** — normalized hex/decimal serial matching in `mtls_auth_service.py`
- **Scheduler SSL errors at startup** — added 30s grace period before first scheduled task execution
- **Stale sessions blocking mTLS** — middleware now validates existing sessions before skipping certificate processing
- **`checkSession()` false positive** — now properly checks `userData.authenticated` before setting `isAuthenticated=true`

---

## [2.49] - 2026-02-22

### Fixed
- **mTLS login endpoint** — `login_mtls()` was missing its `@bp.route` decorator, causing 404 on client certificate login
- **ACME account creation** — added missing `POST /acme/accounts` route; "Create Account" button was returning 404
- **ACME account deactivation** — added missing `POST /acme/accounts/<id>/deactivate` route
- **CRL generate** — `crlService.generate()` now calls the correct `/crl/<caId>/regenerate` backend endpoint

### Changed
- **CHANGELOG** — complete rewrite with accurate entries for all versions from 2.1.1 through 2.48 (extracted from git log)

---

## [2.48] - 2026-02-22

> Version jump from 2.1.6 to 2.48: UCM migrated from Semantic Versioning to Major.Build format.

### Added
- **Comprehensive backend test suite** — 1364 tests covering all 347 API routes (~95% route coverage)
- **mTLS client certificate management** — full lifecycle (list, export, revoke, delete) via `/api/v2/user-certificates` API (6 endpoints), User Certificates page, mTLS enrollment modal, PKCS12 export, dynamic Gunicorn mTLS config, admin per-user mTLS management
- **TOTP 2FA login flow** — complete two-factor authentication with QR code setup and verification at login
- **Experimental badges** — visual indicators for untested features (mTLS, HSM, SSO) in Settings and Account pages
- **ucm-watcher system** — systemd path-based service management replacing direct systemctl calls; handles restart requests and package updates via signal files
- **Auto-update mechanism** — backend checks GitHub releases API, downloads packages, triggers ucm-watcher for installation
- **Pre-commit checks** — i18n sync, frontend tests (450), backend tests (1364), icon validation — all run before every commit

### Changed
- **Versioning scheme** — migrated from Semantic Versioning (2.1.x) to Major.Build (2.48) for simpler release tracking
- **Single VERSION file** — removed `backend/VERSION` duplicate; repo root `VERSION` is sole source of truth
- **Service restart** — centralized via signal files (`/opt/ucm/data/.restart_requested`) instead of direct systemctl calls
- **Branch rename** — development branch renamed from `2.1.0-dev`/`2.2.0-dev` to `dev`
- **RPM packaging** — systemd units renamed from `ucm-updater` to `ucm-watcher` for consistency with DEB
- **Centralized `buildQueryString` utility** — all 10 frontend services now use `buildQueryString()` from `apiClient.js`
- **Tailwind opacity removal** — replaced `bg-x/40` patterns with `color-mix` CSS utilities

### Fixed
- **RPM build failure** — spec referenced non-existent `ucm-updater.path`/`ucm-updater.service` files
- **RPM changelog dates** — fixed incorrect weekday names causing bogus date warnings
- **CA tree depth** — recursive rendering for unlimited depth hierarchies
- **DN parsing** — support both short (`CN=`) and long (`commonName=`) field formats
- **Password change modal** — close button (X) now properly closes the modal
- **2FA enable endpoint** — fixed 500 error on `/api/v2/account/2fa/enable`
- **PEM export** — use real newlines in PEM concatenation
- **Export blob handling** — pages now correctly handle `apiClient` return value (data directly, not `{ data }` wrapper)
- **`groups.service.js` params bug** — was passing `{ params }` to `apiClient.get()` which silently ignored query parameters

### Security
- **1364 backend security tests** — all authentication, authorization, and RBAC endpoints tested
- **Rate limiting verified** — brute-force protection on all auth endpoints confirmed via tests
- **CSRF enforcement** — all state-changing endpoints verified to require CSRF tokens

---

## [2.1.6] - 2026-02-21

Versioning cleanup release — no code changes.

---

## [2.1.5] - 2026-02-21

### Fixed
- **SAN parsing** — parse SAN string into typed arrays (DNS, IP, Email, URI) for proper display and editing

---

## [2.1.4] - 2026-02-21

### Fixed
- **Encrypted key password** — password field now shown in SmartImport for encrypted private keys
- **Mobile navigation i18n** — use short translation keys for nav items on mobile
- **Missing mobile icons** — added Gavel, Stamp, ChartBar icons to AppShell mobile nav

---

## [2.1.3] - 2026-02-21

### Fixed
- **ECDSA key sizes** — correct key size options (256, 384, 521) and backend mapping (fixes #22)

---

## [2.1.2] - 2026-02-21

### Fixed
- **Sub CA creation** — fixed parent CA being ignored + DN fields lost + error detail leak + import crash

### Security
- **Flask 3.1.2 → 3.1.3** — CVE-2026-27205

---

## [2.1.1] - 2026-02-20

### Fixed
- **DB version sync** — `app.version` in database now synced from VERSION file on startup
- **OPNsense import** — fixed double JSON.stringify on API client POST, added type validation for nested JSON fields
- **DNS provider status** — fixed `status` kwarg in DNS provider endpoints
- **Screenshots** — replaced with correct dark theme 1920×1080 screenshots

### Changed
- Consolidated changelog — merged all 2.1.0 pre-release entries into single entry
- CI: exclude `rc` tags from Docker `latest` tag
- CI: auto-push DOCKERHUB_README.md to Docker Hub on release

---

## [2.1.0] - 2026-02-19

### Added
- **SSO authentication** — LDAP/Active Directory, OAuth2 (Google, GitHub, Azure AD), SAML 2.0 with group-to-role mapping
- **Governance module** — certificate policies, approval workflows, scheduled reports
- **Auditor role** — new system role with read-only access to all operational data except settings and user management
- **4-role RBAC** — Administrator, Operator, Auditor, Viewer with granular permissions + custom roles
- **ACME DNS providers** — 48 providers with card grid selector and official SVG logos
- **Floating detail windows** — click any table row to open draggable, resizable detail panel with actions (export, renew, revoke, delete)
- **Email template editor** — split-pane HTML source + live preview with 6 template variables
- **Certificate expiry alerts** — configurable thresholds, recipients, check-now button
- **SoftHSM integration** — automatic SoftHSM2 setup across DEB, RPM, and Docker with PKCS#11 key generation
- **AKI/SKI chain matching** — cryptographic chain relationships instead of fragile DN-based matching
- **Chain repair scheduler** — hourly background task to backfill SKI/AKI, re-chain orphans, deduplicate CAs
- **Backup v2.0** — complete backup/restore of all database tables (was only 5, now covers groups, RBAC, templates, trust store, SSO, HSM, API keys, SMTP, policies, etc.)
- **File regeneration** — startup service regenerates missing certificate/key files from database
- **Human-readable filenames** — `{cn-slug}-{refid}.ext` instead of UUID-only
- **Dashboard charts** — day selector, expired series, optimized queries, donut chart with gradients
- **SSO settings UI** — collapsible sections, LDAP test connection/mapping, OAuth2 provider presets, SAML metadata auto-fetch
- **Login page SSO buttons** — SSO authentication buttons before local auth form
- **Login method persistence** — remembers username + auth method across sessions
- **ESLint + Ruff linters** — catches stale closures, undefined variables, hook violations, import errors
- **SAML SP certificate selector** — choose which certificate to include in SP metadata
- **LDAP directory presets** — OpenLDAP, Active Directory, Custom templates
- **Template duplication** — clone endpoint: POST /templates/{id}/duplicate
- **Unified export actions** — reusable ExportActions component with inline P12 password field
- **Trust store chain validation** — visual chain status with export bundle
- **Service reconnection** — 30s countdown with health + WebSocket readiness check
- **Settings about** — version, system info, uptime, memory, links to docs
- **Webhooks** — management tab in Settings for webhook CRUD, test, and event filtering
- **Searchable Select** component
- **Complete i18n** — 2273+ keys across all 9 languages (EN, FR, DE, ES, IT, PT, UK, ZH, JA)

### Changed
- Renamed RBAC system role "User" → "Viewer" with restricted permissions
- Simplified themes to 3 families: Gray, Purple Night, Orange Sunset (× Light/Dark)
- Consolidated API routes — removed `features/` module; all routes under `api/v2/`
- No more Pro/Community distinction — all features are core
- SSO service layer extracted to `sso.service.js`
- Tables use proportional column sizing, actions moved to detail windows
- Mobile navbar with user dropdown, compact 5-column nav grid
- WebSocket/CORS auto-detect short hostname and dynamic port
- Default password is always `changeme123` (not random)
- Removed unnecessary gcc/build-essential from DEB/RPM dependencies

### Fixed
- **LDAP group filter malformed** when user DN contains special characters (`escape_filter_chars`)
- **17 bugs found by linters** — undefined variables, missing imports, conditional hooks across 6 files
- **CSRF token not stored** on multi-method login — caused 403 on POST/PUT/DELETE
- **Select dropdown hidden behind modals** — Radix portal z-index fix
- **SAML SP metadata schema-invalid** — now uses python3-saml builder
- **CORS origin rejection** breaking WebSocket on Docker and fresh installs
- **Dashboard charts** — width/height(-1) errors, gradient IDs, react-grid-layout API
- **6 broken API endpoints** — schema mismatches between models and database
- **z-index conflicts** between confirm dialogs, toasts, and floating windows
- **CSR download** — endpoint mismatch (`/download` → `/export`)
- **PFX/P12 export** — missing password prompt in floating detail windows
- **Auto-update DEB postinst** — updater systemd units were never enabled
- Fixed force_password_change not set on fresh admin creation
- Fixed infinite loop in reports from canWrite in useCallback deps
- Removed 23 console.error statements from production code

### Security
- **JWT removal** — session cookies + API keys only (reduces attack surface)
- **cryptography** upgraded from 46.0.3 to 46.0.5 (CVE-2026-26007)
- SSO rate limiting on LDAP login attempts with account lockout
- CSRF token validation on all SSO endpoints
- RBAC permission enforcement across all frontend pages and floating windows
- SQL injection fixes and debug leak prevention
- Referrer-Policy security header added
- Role validation against allowed roles list
- Internal error details no longer leaked to API clients
- 28 new SSO security tests

---

## [2.0.7] - 2026-02-13

### Fixed
- **Packaging** — ensure scripts are executable after global `chmod 644`
- **Auto-update** — replace shell command injection with systemd trigger
- **Packaging** — restart service on upgrade instead of start

---

## [2.0.6] - 2026-02-12

### Fixed
- **OPNsense import** — import button not showing after connection test

### Security
- **cryptography** upgraded from 46.0.3 to 46.0.5 (CVE-2026-26007)

---

## [2.0.4] - 2026-02-11

### Fixed
- **Certificate issue form** — broken Select options and field names
- **SSL/gevent** — early gevent monkey-patch for Python 3.13 recursion bug, safe_requests in OPNsense import
- **Docker** — fix data directory names and migration, use `.env.docker.example`
- **VERSION** — centralize VERSION file as single source of truth

---

## [2.0.1] - 2026-02-08

### Fixed
- **HTTPS cert paths** — use `DATA_DIR` dynamically instead of hardcoded paths
- **Docker** — WebSocket `worker_class` (geventwebsocket), HTTPS cert restart uses `SIGTERM`
- **Service restart** — reliable restart via sudoers for HTTPS cert apply
- **WebSocket** — connect handler accepts auth parameter
- **Version** — single source of truth from `frontend/package.json`

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
