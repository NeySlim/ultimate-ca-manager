# Changelog

All notable changes to Ultimate Certificate Manager will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Starting with v2.48, UCM uses Major.Build versioning (e.g., 2.48, 2.49). Earlier releases used Semantic Versioning.

---

## [Unreleased]

### Roadmap
- **Environment Variables** — Sync Docker env vars (SMTP, HSM, etc.) to database at startup; track `managed_by` source; mark UI fields as read-only when sourced from environment
- **Policy Enforcement on Protocols** — Apply certificate policies to ACME, SCEP, and EST protocol handlers (currently only enforced on REST API); add CA issuance restriction flags to prevent direct issuance from root/intermediate CAs

---

## [2.110] - 2026-04-09

### Added
- **ACME Auto-Supersede** — Automatically revoke previous certificates with reason 'superseded' when a new certificate is issued via ACME finalize (controlled by `revoke_on_renewal` setting)

### Fixed
- **DER File Upload Detection** — All file upload handlers (SmartImport, Cert Tools, mTLS) now detect PEM vs DER by content (`-----BEGIN` header) instead of file extension; fixes corrupted DER uploads for `.crt`/`.cer` files
- **CA Template in Certificates Page** — Remove incorrect "Certificate Authority" template from Certificates page template dropdown; CAs should only be created from the CAs page

---

## [2.109] - 2026-04-08

### Added
- **Multiple CDP/OCSP/AIA URLs** — Support multiple CRL Distribution Point, OCSP responder, and AIA URLs per CA with add/remove UI in the CRL/OCSP page; migration converts single-URL columns to JSON arrays with backward compatibility (#49)
- **Certificate Practice Statement (CPS)** — Per-CA CPS URI and Policy OID configuration; embedded in issued certificates as CertificatePolicies extension (RFC 5280 §4.2.1.4); toggle, URI input, and OID input in CRL/OCSP page (#49)
- **RFC 5280 Extensions** — PathLength constraints, NameConstraints (permitted/excluded subtrees), PolicyConstraints, InhibitAnyPolicy, Subject Information Access (SIA), OCSP Must-Staple
- **RFC 6844 CAA Checking** — Validate CAA DNS records before certificate issuance; NameConstraints enforcement on certificate creation; ACME account lifecycle (deactivate)
- **ACME Enhancements** — Order management, newAuthz endpoint, External Account Binding (EAB) support; EST csrattrs endpoint; SCEP GetNextCACert and renewal support
- **TSA (RFC 3161)** — Full Time Stamping Authority: backend API (`/api/v2/settings/tsa`), protocol endpoint (`/tsa`), frontend management page with signing CA, policy OID, hash algorithms, and accuracy settings
- **Certificate Transparency (RFC 6962)** — CT log URL management, enable/disable toggle, auto-submit on certificate creation, manual CT submission endpoint, SCT extension parsing and display in certificate details
- **OCSP Delegated Responder (RFC 5019)** — API to assign/remove delegated OCSP responders per CA with OCSPSigning EKU validation; eligible responder listing; UI section in CRL/OCSP page
- **In-App Help Translations** — 208 help content files across 8 languages (fr, de, es, it, ja, pt, uk, zh) for all 26 sections; per-section lazy loading with English fallback

### Security
- **6 CRITICAL fixes** — CSRF token rotation, password complexity enforcement, account lockout on all auth paths, audit log integrity, session security hardening, input sanitization
- **14 HIGH fixes** — Rate limiting on sensitive endpoints, generic error messages (no username enumeration), secure session cookie attributes, WebAuthn origin validation
- **18 MEDIUM fixes** — Content Security Policy headers, X-Frame-Options, request size limits, backup file access controls, password history enforcement

### Improved
- **Help Button** — Translated "Help" button text in all 9 languages
- **CT Settings UX** — Configure CT log URLs first, then enable — more intuitive workflow

---

## [2.108] - 2026-04-03

### Fixed
- **CRL Auto-Regeneration** — Fix scheduler silently returning no CAs: `has_private_key` is a Python `@property`, not a DB column; `filter_by(has_private_key=True)` returned empty results; replaced with Python-side filtering (Issue #52)
- **Centralized Logging** — Module-level loggers (`logging.getLogger(__name__)`) had no handlers; added root logger configuration in `app.py` with RotatingFileHandler (native) or stdout (Docker); all scheduler/service logs now visible in `/var/log/ucm/ucm.log`

### Improved
- **CRL/OCSP Page Redesign** — Replace text toggle headers with language-independent icon+tooltip headers; merge Status into CA Name column; merge Last Update + Next Update into single stacked Updates column; add `compact` column flag to ResponsiveDataTable for fixed-width toggle columns (48px); table reduced from 9 → 7 columns

---

## [2.107] - 2026-04-02

### Fixed
- **SoftHSM Status** — Fix HSM providers always showing "Disabled" in the UI: backend returned `status` string but frontend expected `enabled` boolean; add `enabled` field to `HsmProvider.to_dict()` (Discussion #26)
- **Key Encryption (Docker)** — Ensure `/etc/ucm/` directory exists with correct ownership in Docker entrypoint; improve error message with Docker-specific hints when permission denied writing master.key (Discussion #26)

### Added
- **CDP Auto-Enable** — Automatically enable CRL Distribution Point (CDP) on newly created CAs when a Protocol Base URL or HTTP protocol server is configured; users no longer need to manually enable CDP per CA (Discussion #26)
- **SoftHSM Auto-Register** — Automatically create an `SoftHSM-Default` HSM provider in the database when Docker entrypoint initializes a SoftHSM token; the provider appears immediately in the HSM page (Discussion #26)

---

## [2.106] - 2026-04-01

### Fixed
- **ACME Proxy** — Fix challenge validation staying pending when using certbot: proxy now only exposes dns-01 challenges (http-01/tls-alpn-01 cannot work through a proxy); add clear error messages when upstream CA has no dns-01 challenge, DNS provider is not configured, or no matching order found; replace all silent exception handling with proper logging (fixes #51)

### Added
- **ACME Proxy EAB** — Support External Account Binding for upstream CA registration (required by HARICA, Sectigo, etc.) via `acme.proxy.eab_kid` and `acme.proxy.eab_hmac_key` settings; auto-detect when upstream requires EAB and show clear error

### Security
- **Dependencies** — Update requests 2.32.5 → 2.33.1 (CVE-2026-25645), cbor2 5.8.0 → 5.9.0 (CVE-2026-26209), cryptography 46.0.5 → 46.0.6 (CVE-2026-34073)

---

## [2.105] - 2026-03-31

### Fixed
- **ACME Proxy** — Add missing route decorators on `authz`, `order`, `finalize`, `cert` endpoints (were unreachable dead code — certbot failed after `new-order`); add POST-as-GET empty payload validation (RFC 8555 §6.3); fix error responses to use `urn:ietf:params:acme:error` URN format with `application/problem+json` (RFC 7807); add `revoke-cert` and `key-change` stub endpoints (advertised in directory but missing) (fixes #50)
- **ACME Main API** — Add `Cache-Control: no-store` to all ACME responses (RFC 8555 §8); add POST-as-GET payload validation on order, authz, cert endpoints; fix `revoke-cert` success response missing `Replay-Nonce`, `Cache-Control`, `Link` headers
- **ACME Services** — Wrap all bare `db.session.commit()` calls with try/except + rollback + logging across acme_service, acme_proxy_service, acme_client_service; add input validation for identifiers in proxy `new_order()`
- **OCSP** — Add debug logging to silent CA cert parsing exception in issuer hash lookup
- **SCEP** — Use module-level logger instead of `current_app.logger` for consistency

### Fixed
- **Settings API** — `system_name`, `base_url`, `date_format`, `show_time` were missing from the GET response and PATCH allowed keys; frontend fields now properly persist (credit: f1lint, PR #47)

---

## [2.103] - 2026-03-27

### Fixed
- **Protocol URL regression** — OCSP and AIA CA Issuers URLs were incorrectly generated with `https://host:8443/...` instead of `http://host:8080/...` when enabling features; now uses configured FQDN and HTTP protocol port
- **Protocol URL auto-repair** — Toggling OCSP/CDP/AIA on now automatically regenerates any URL that incorrectly uses `https://`; migration 013 fixes existing bad URLs on upgrade
- **Localhost protection** — Protocol URL generation returns an error instead of generating unusable `localhost` URLs; FQDN or Protocol Base URL must be configured first

### Changed
- **CRL/OCSP page** — Removed `window.location.origin` fallbacks; URLs only shown when properly configured by backend; shows "URL not configured" message when enabled but no URL available
- **Help guides** — CDP and AIA sections now mention FQDN/Protocol Base URL prerequisite

---

## [2.102] - 2026-03-27

### Fixed
- **DEB/RPM packaging** — Added `gcc` and `python3-dev` as package dependencies to fix install failures on Ubuntu 24.04 and other minimal systems where C compiler is not present (needed to compile `twofish` extension for JKS export)
- **API key creation** — Fixed "Permissions are required" error when creating API keys from the UI; added permission scope selector (Full Access, Read Only, Read & Write, Certificates Only) to the creation form ([#46](https://github.com/NeySlim/ultimate-ca-manager/issues/46))

### Changed
- **Documentation** — Added AIA CA Issuers to README, API reference, in-app help, and wiki

---

## [2.101] - 2026-03-26

### Added
- **AIA CA Issuers** (RFC 5280 §4.2.2.1) — Public `/ca/{refid}.cer` and `.pem` endpoints serve CA certificates for chain building; CA Issuers URL embedded in Authority Information Access extension of issued certificates (#45)
- **AIA toggle & URLs** — CRL/OCSP page now has AIA CA Issuers toggle per CA with copy-to-clipboard URLs alongside CDP and OCSP

### Fixed
- **showWarning crash** — Creating wildcard certificates no longer crashes with "showWarning is not defined" toast error
- **Admin approval bypass** — Admin users now bypass approval policies when issuing certificates; previously admins were incorrectly subject to approval workflows
- **Wildcard policy default** — Wildcard certificate policy now seeded as inactive by default (was incorrectly active, blocking wildcard creation for all users)

---

## [2.100] - 2026-03-23

### Fixed
- **Migration system** — Upgrades from old versions (pre-v2.52) no longer fail; baseline migration now creates all tables unconditionally with `CREATE TABLE IF NOT EXISTS` instead of skipping schema for existing installs
- **Missing database columns** — Added fallback for columns missing after partial upgrades: `key_type`, delta CRL fields, `request_data`, EOBO fields, SAN fields on discovered certificates

### Added
- **docker-compose.simple.yml** — Minimal compose file for Portainer and quick deployments (just image, ports, volume)

### Changed
- **Docker Compose fixes** — Removed non-existent `development` build target from dev compose, removed deprecated `FLASK_ENV` (Flask 3.x), fixed nginx healthcheck and `depends_on` condition in prod compose

---

## [2.99] - 2026-03-20

### Added
- **JKS (Java KeyStore) export** — Export certificates and CAs as password-protected JKS files with optional CA chain inclusion; available in all export modals, detail panels, and certificate converter tool

### Fixed
- **Orphan certificate re-chaining** — SKI/AKI backfill now fixes certificates with stale CA references (e.g. after OPNsense migration) by matching AKI to existing CA SKI

---

## [2.98] - 2026-03-20

### Fixed
- **Security: socket.io-parser CVE-2026-33151** — Updated to 4.2.6, also fixed ajv ReDoS, flatted DoS, minimatch ReDoS, rollup path traversal (0 npm audit issues)

### Changed
- **Docker: HTTP port 8080** — Added missing HTTP port mapping for CRL/CDP and OCSP public endpoints to all Docker examples (docker-compose.hsm.yml, README, DockerHub, quickstart, installation docs)
- **Documentation** — Complete rewrite of features section across README, DockerHub README, and ucm.tools website to reflect all actual features (EST, ADCS, Discovery, Backup/Restore, Policies, Webhooks, etc.)
- **Website screenshots** — Updated all screenshots to dark mode with realistic data

---

## [2.97] - 2026-03-19

### Fixed
- **Certificate CA filter** — Filtering certificates by CA now works correctly; frontend was using nonexistent `ca_id` field instead of `caref`
- **Orphan certificate detection** — Orphan count and filter now properly compare `caref`/`refid` instead of missing `ca_id`
- **ACME order serialization** — Fixed `AcmeOrder.to_dict()` crash caused by referencing `self.expires_at` instead of `self.expires`
- **Trust store detail panel** — Subject and issuer fields now display correctly using actual API response fields
- **Trust store search** — Search now works on `subject`/`issuer` fields instead of nonexistent `subject_cn`/`issuer_cn`
- **Certificate subtitle** — Floating detail window now extracts issuer CN from full DN string
- **CA parent name** — CA history subtitle now resolves parent name from parent_id instead of missing `parent_name` field

---

## [2.96] - 2026-03-19

### Fixed
- **Timezone not applied on login** — All login endpoints (password, 2FA, mTLS, WebAuthn, LDAP) now return timezone, date_format, and show_time settings so the frontend applies them immediately without requiring a page refresh
- **Consistent date formatting** — Replaced 13 raw `toLocaleString`/`toLocaleDateString` calls with centralized `formatDate()` across 8 frontend files

---

## [2.95] - 2026-03-18

### Fixed
- **HTTPS certificate chain** — Apply managed certificate now includes full CA chain (leaf + intermediates + root) in https_cert.pem
- **EST enrollment chain** — simpleenroll, simplereenroll, and serverkeygen now return full CA chain in PKCS#7 response (RFC 7030 §4.2.3)
- **mTLS trust file** — mtls_ca.pem now includes parent CA hierarchy for intermediate CA trust

---

## [2.94] - 2026-03-18

### Added
- **Microsoft CA in-app documentation** — Help content and guide for MSCA integration, EOBO, connection setup
- **Wiki: Microsoft CA Integration** — Full wiki page covering connections, auth methods, EOBO, API reference

### Fixed
- **ACME EAB HMAC key input** — Field was not accepting typed input due to controlled component bug

---

## [2.93] - 2026-03-18

### Added
- **ADCS Enroll on Behalf Of (EOBO)** — Sign CSRs on behalf of other users via Microsoft AD CS enrollment agent certificates
- EOBO fields (Enrollee DN, Enrollee UPN) in sign CSR modal with checkbox activation
- Auto-prefill EOBO fields from CSR subject and SAN email data
- Migration 011 adds EOBO tracking columns to MSCA requests

---

## [2.92] - 2026-03-18

### Added
- **ACME ECDSA support** — Certificate keys: RSA-2048, RSA-4096, EC-P256, EC-P384; Account keys: ES256, ES384, RS256
- **ACME External Account Binding** — EAB support per RFC 8555 §7.3.4 for CAs requiring pre-registration (ZeroSSL, HARICA, Google Trust)
- **ACME custom server** — Configure any RFC 8555-compliant CA directory URL (not just Let's Encrypt)
- **ACME key type per order** — Each certificate request can specify its own key type (migration 010)

### Changed
- **In-app help** — Updated ACME guide with ECDSA/EAB/custom server documentation, certbot & acme.sh examples
- **Wiki** — Updated ACME-Support.md with custom CA table, EAB instructions, RFC compliance list

### Security
- **pyasn1** 0.6.2 → 0.6.3 — CVE-2026-30922 (HIGH)
- **pyOpenSSL** 25.3.0 → 26.0.0 — CVE-2026-27459 (HIGH), CVE-2026-27448 (LOW)

---

## [2.91] - 2026-03-18

### Fixed
- **RFC 5280 SAN compliance** — All code paths (CSR upload, import, MSCA, smart import, discovery) now extract and store all 4 SAN types: DNS, IP, Email (RFC822Name), URI
- **CSR import SAN storage** — Fixed `str(list)` → `json.dumps()` for proper JSON serialization of SANs
- **CSR Email SAN handling** — Emails in CSR SANs are now correctly stored as RFC822Name instead of being misclassified as DNS names
- **Certificate creation** — URI SANs now properly saved to database; URI: prefix correctly parsed
- **sign_csr() extensions** — SubjectKeyIdentifier and AuthorityKeyIdentifier now added as fallback when missing from CSR (RFC 5280 §4.2.1.1/§4.2.1.2)
- **SAN critical flag** — SAN extension now marked critical when certificate subject is empty (RFC 5280 §4.2.1.6)
- **Delta CRL** — Added mandatory IssuingDistributionPoint critical extension (RFC 5280 §5.2.5)
- **FreshestCRL URL** — Fixed delta CRL URL to use `ca.refid` instead of `ca.id` matching CDP route pattern
- **OCSP POST validation** — Content-Type `application/ocsp-request` now validated on POST requests (RFC 6960 §4.2.2)
- **CSR signature verification** — Upload and import endpoints now verify CSR signature before accepting (RFC 2986 §2.2)
- **Certificate import** — SANs now extracted and stored when importing certificates via file upload

### Added
- **Discovery SAN columns** — `san_emails` and `san_uris` columns added to discovered certificates (migration 009)

---

## [2.90] - 2026-03-18

### Added
- **ADCS badge** — Certificates signed by Microsoft CA now show a purple "ADCS" tag in the certificate list
- **EST badge** — Certificates issued via EST protocol now show a yellow "EST" tag in the certificate list

---

## [2.89] - 2026-03-18

### Fixed
- **SubCA CDP/OCSP embedding** — SubCA certificates now embed parent CA's CRL Distribution Point and OCSP URLs in extensions (Fixes #39)
- **Certificate CA filter crash** — Filtering certificates by specific CA caused 500 error due to using non-existent `ca_id` column instead of `caref` FK (Fixes #41)
- **DN subject field order** — Reordered all forms (CAs, Certificates, CSRs) and detail displays to follow OpenSSL standard order: C → ST → L → O → OU → Email (Fixes #40)

---

## [2.88] - 2026-03-17

### Fixed
- **ADCS cert import completely rewritten** — Previous code used 6 non-existent Certificate model fields (`cn`, `org`, `status`, `issuer_cn`, `not_before`, `not_after`, `cert_id`); now uses correct columns (`refid`, `descr`, `subject`, `subject_cn`, `issuer`, `valid_from`, `valid_to`, `source`, etc.)
- **ADCS cert import extracts SANs, AKI, SKI** — Full certificate metadata parsed and stored, matching UCM standard cert creation pattern
- **ADCS CSR update** — Populates `crt` field on original CSR record (converts CSR → full cert) instead of setting non-existent `status`/`cert_id` fields

---

## [2.87] - 2026-03-17

### Fixed
- **ADCS cert import "Incorrect padding"** — Handle certsrv base64-encoded DER (missing padding), full PEM, and PEM-wrapping fallback; robust cert parsing for all ADCS return formats

---

## [2.86] - 2026-03-17

### Fixed
- **ADCS cert bytes serialization** — `certsrv` returns `bytes` from `get_cert()`, `get_existing_cert()`, `get_ca_cert()`; now decoded to `str` for JSON responses and DB storage

---

## [2.85] - 2026-03-17

### Fixed
- **ADCS CSR signing crash** — Fixed `ImportError: cannot import name 'CSR' from 'models'`; CSRs use the `Certificate` model (no separate CSR class exists)
- **ADCS request status check** — Same CSR→Certificate fix for pending request polling

---

## [2.84] - 2026-03-17

### Fixed
- **ADCS CSR signing robustness** — certsrv import in exception handler no longer masks real errors; string-based error classification runs first, typed exceptions used only if available
- **ADCS error visibility** — 500 responses now return actual error message instead of generic "Internal server error"; all error paths log with full stack trace (`exc_info=True`)
- **ADCS DB resilience** — All `db.session.commit()` calls wrapped in try/except with rollback to prevent cascading failures
- **CSR validation** — Empty CSR data and bytes-vs-string mismatches now caught before submission

---

## [2.83] - 2026-03-17

### Fixed
- **ADCS template parsing** — Extract template name from compound ADCS values (`E;TemplateName;1;...`) instead of using raw string
- **ADCS CSR signing 500 error** — Proper certsrv exception handling (CertificatePendingException, RequestDeniedException) with full stack trace logging
- **ADCS submitted_by tracking** — Fixed username access (`g.current_user` instead of non-existent `request.current_user`)
- **Expiry alerts ignore disabled setting** — Scheduler now uses NotificationService (DB-backed) instead of in-memory settings; disabling alerts in UI actually stops emails
- **Expiry emails use custom template** — Alert emails now go through NotificationService with configured email template

---

## [2.82] - 2026-03-17

### Fixed
- **CDP URLs now use HTTP protocol** — CDP URL generation in CA API was hardcoded to HTTPS (`request.host_url`), now uses `get_protocol_base_url()` which respects HTTP protocol port configuration
- **CRL/OCSP page shows actual URLs** — Distribution Points section now displays the real CDP/OCSP URLs stored on the CA (with HTTP protocol) instead of hardcoded `window.location.origin` (HTTPS)
- **Migration updates existing CA URLs** — Existing CAs with HTTPS CDP/OCSP URLs are automatically migrated to HTTP when HTTP protocol port is enabled
- **Expiry alerts respect disabled setting** — Scheduler now uses NotificationService (DB-backed) instead of in-memory ExpiryAlertSettings; disabling alerts in UI actually stops emails
- **Expiry emails use custom template** — Alert emails now go through NotificationService which applies the configured email template
- **Missing i18n keys** — Added `details.subjectAltNames`, `common.enable`, `common.disable` across all 9 locales

---

## [2.81] - 2026-03-17

### Added
- **HTTP Protocol Server for CDP/OCSP** — Optional plain HTTP server (port 8080 by default) serving only CDP and OCSP endpoints, avoiding TLS verification loops when clients fetch CRLs
- **Refid-based CDP URLs** — CDP URLs now use CA refid (UUID) instead of sequential numeric IDs, preventing CA enumeration; legacy numeric IDs still supported
- **Protocol Base URL Setting** — Configurable base URL for protocol endpoints (CDP/OCSP) in Settings UI; auto-detects HTTP port when enabled
- **HTTP Protocol Port in UI** — Port configurable via Settings > General with validation (0=disabled, 1024-65535)
- **Global JSON Error Handlers** — All API errors (400, 404, 405, 413, 500) now return consistent JSON responses instead of HTML

### Fixed
- **Integer Overflow Crash** — Requesting certificates with absurdly large IDs no longer causes 500; returns 400 JSON
- **Unhandled Exception Logging** — All uncaught exceptions are now logged with full stack trace and return safe JSON error

---

## [2.80] - 2026-03-16

### Added
- **Approval Workflow Enforcement** — Certificate policies with `requires_approval` now actually block issuance until approved; approved requests auto-issue certificates with stored request data
- **Smart Policy Matching** — Approval policies evaluate request data (CN, SANs) against rules; wildcard policy only triggers for `*.domain` certificates, not all requests
- **X.509 Extensions for CA & Discovery** — Shared extension parser displays full X.509 details in CA detail and Discovery certificate views (reuses certificate extension components)

### Fixed
- **CDP/OCSP in Certificates (#39)** — CRL Distribution Points and OCSP URLs now embedded in all issued certificates (direct creation, CSR signing, SCEP, EST) when enabled on the CA
- **EST Protocol** — Implemented missing `CAService.sign_csr_from_crypto()` and `get_certificate_chain()` methods; all 5 EST endpoints now functional
- **Auto-Renewal Service** — Fixed same missing CAService methods that caused auto-renewal to crash at runtime
- **Scheduler Crash** — Removed reference to non-existent `SMTPConfig.admin_email` in expiry alerts and discovery notifications (used `smtp_from` instead)
- **CRL/OCSP URL Format** — Fixed frontend displaying wrong CDP/OCSP URLs; auto-generates correct URLs when toggles are enabled
- **Overbroad Seed Policies** — Deactivated "Code Signing" demo policy that had no narrowing rules and would block all certificate creation

---

## [2.77] - 2026-03-16

### Added
- **X.509 Certificate Extensions** — Full extension display in certificate detail view: Basic Constraints, Key Usage, Extended Key Usage, Subject Alternative Names (DNS/IP/Email/URI/UPN/DirName), Subject Key Identifier, Authority Key Identifier, CRL Distribution Points, Authority Information Access, Certificate Policies, Name Constraints
- **EKU OID Name Mapping** — 18 common Extended Key Usage OIDs resolved to human-readable names (IPsec, Microsoft, Netscape SGC, etc.) instead of "Unknown OID"
- **Typed SAN Badges** — Subject Alternative Name entries displayed with colored badges per type (DNS, IP, Email, URI, UPN, DirName)
- **Critical Extension Indicator** — Red badge for extensions marked as critical

---

## [2.76] - 2026-03-16

### Fixed
- **FK Cascade on Delete (#39)** — All DELETE endpoints now properly handle foreign key dependencies (CAs cascade CRL/OCSP records, certificates/policies clean up ApprovalRequests), with try/except + rollback preventing HTTP 500 on constraint failures
- **Protocol Middleware Exemptions (#39)** — CDP, OCSP, SCEP, ACME, and EST endpoints now exempt from FQDN redirect, HTTPS enforcement, and safe-mode middleware (was causing protocol clients to get HTML login page)
- **SPA Catch-All (#39)** — Added `/cdp/` and `/ocsp/` to SPA exclusion list so protocol endpoints aren't intercepted by React Router
- **i18n Completeness** — Replaced ~160 hardcoded English strings with `t()` calls across certificate discovery, website, and various UI components; all 9 locales updated (3086 keys each)

---

## [2.75] - 2026-03-15

### Added
- **Delta CRL Support (RFC 5280 §5.2.4)** — Generate delta CRLs containing only recent revocations, with DeltaCRLIndicator (CRITICAL), FreshestCRL on base CRLs, dedicated CDP endpoint, scheduler auto-generation, and full frontend management (toggle, detail, interval selector)
- **PDF Reports Tab** — PDF report templates with custom builder, purple icons, grid card layout, and scheduling support
- **Roadmap** — Added market comparison gaps (Clustering/HA, K8s/Helm, PQC, SSH, CMP, Key Archival, Code Signing) to README

### Fixed
- **Security Audit (76 findings)** — Fixed 38 issues across 6 audit phases: XXE/SSRF protection, str(e) leak prevention, RSA-512/1024 removal, ACME JWS bypass, EST timing-safe auth, SCEP decrypt fix, RBAC operator permission trimming, discovery rate limiting
- **PKI Protocol Hardening** — CSR signature verification, cert validity clamping to CA, parent CA expiry check, atomic ACME nonces, SCEP serial fix, EST reenroll subject check, serverkeygen fail-safe
- **RBAC** — Correct delete: permissions on DELETE endpoints, operator role trimmed to 23 permissions
- **Frontend Quality** — ARIA overlays, dashboard valid count, pie chart backend data, barrel exports, theme-safe colors, i18n completeness
- **Reports** — Sidebar tab layout, centered content matching Settings pattern
- **CDP** — Cache-Control and Last-Modified headers on CRL/delta CRL distribution points
- **SAN Normalization** — Certificate SAN field accepts both string and array formats
- **Black CVE** — Bumped black 26.1.0 → 26.3.1 (CVE-2026-32274)

### Security
- Content-Disposition filename sanitization
- Generic error messages (no internal detail leakage)
- Rate limiting on discovery scans
- Unique index on CRL numbers (race condition prevention)

---

## [2.74-dev] - 2026-03-13

### Fixed
- **MS CA Template Listing** — Implemented template scraping via certrqxt.asp (certsrv library has no template listing method)
- **MS CA Client Error Handler** — Fixed NameError (`verify` → `cafile`) in connection error cleanup
- **Certificate/CA Export Decryption** — Export endpoints now properly decrypt private keys before export (was exporting encrypted data)
- **Managed Cert Selection** — CertificateInput managed mode correctly fetches cert PEM + key via export endpoint
- **Cryptography Deprecation Warnings** — Replaced `not_valid_before`/`not_valid_after` with UTC-aware variants across all services

---

## [2.73] - 2026-03-13

### Added
- **CertificateInput Component** — Unified cert/key input with 3 modes: paste PEM, upload file (auto-detect via SmartImport), select from managed certificates
- **MS CA File Upload** — Client certificate for MS CA mTLS can now be uploaded or selected from managed certs (not just pasted)
- **Converter Password Guardrails** — PKCS12 input requires password, PKCS12 output requires password; clear error messages

### Changed
- **SSL Converter Refactored** — Uses SmartParser (same engine as Smart Import) instead of duplicated parsing logic
- **Converter UX Improved** — Password field appears when .p12/.pfx uploaded; textarea hidden for binary files; frontend validation before API call
- **SSO CA Bundle Fields** — Replaced raw HTML textareas with Textarea component for LDAP, OAuth2, SAML CA bundles
- **Export Modal Simplified** — Password field only shown for PKCS12 format (removed for PEM key export)

### Fixed
- **MS CA certsrv Client Params** — Fixed cert auth: `username`/`password` = cert/key paths, `cafile` = SSL CA bundle
- **MS CA SSL Verify** — `session.verify = False` when SSL verification disabled
- **Dashboard Chart Height** — Fixed `-1` height error with explicit container sizing
- **CertificateInput Select Import** — Fixed import path for SelectComponent

---

## [2.72] - 2026-03-13

### Added
- **Microsoft AD CS Setup Guide** — Help panel recommends client certificate (mTLS) auth, documents all three methods with setup steps
- **Current Version Release Notes** — Settings page shows release notes for the installed version (markdown rendered), respects update channel
- **Session Timeout from Backend** — Frontend fetches actual session timeout from server instead of using hardcoded 30min value

### Changed
- **Kerberos Made Optional** — `requests-kerberos` removed from default requirements; users install manually if needed. Eliminates `libkrb5-dev` build dependency and cross-compilation issues
- **Simplified Packaging** — Removed all precompiled wheels machinery from DEB/RPM/CI; smaller packages (~2MB vs ~5.6MB)
- **Product Name Unified** — "Ultimate CA Manager" → "Ultimate Certificate Manager" everywhere
- **Copyright Updated** — © Lionel Alarcon

### Fixed
- **False Session Expiration** — Frontend timer was 30min while backend defaults to 8h; now synced. Verifies with backend before logging out
- **Hardcoded Domain Removed** — Replaced `pew.pet` with `example.com` in templates and config
- **Kerberos UI Clarification** — Marked as "(Optional)" in MS CA auth dropdown with warning banner

---

## [2.70] - 2026-03-12

### Added
- **Microsoft AD CS Integration** (Experimental) — Sign CSRs via Microsoft Certificate Authority through certsrv Web Enrollment. Supports client certificate (mTLS), Kerberos, and Basic Auth over HTTPS. Dynamic template loading, permission detection, pending approval tracking with auto-import
- **Re-key from CSR** — Create new CSR/certificate from an existing CSR whose private key was lost, preserving subject and SAN fields with a fresh key pair
- **Update Channel Selector** — Replace checkboxes with a channel selector (Stable / Pre-release / Development) in Settings, with warning banner for unstable channels
- **Compliance Grade Sorting** — Sort certificates by compliance grade, configurable date format with time display
- **Precompiled Wheels** — DEB/RPM packages include precompiled Python wheels for x86_64 and aarch64, eliminating compilation at install time (no compiler or dev headers needed)

### Fixed
- **SCEP pytz Removal** — Replace deprecated `pytz.UTC` with stdlib `timezone.utc` in SCEP CertRep signing (fixes #38)
- **MS CA Foreign Key** — Fix `msca_requests.csr_id` FK referencing non-existent `csrs` table → `certificates`
- **Docker Path Alignment** — Align Docker container paths with DEB/RPM layout (`/app/` → `/opt/ucm/`), backward-compatible data migration for existing users
- **OCI/Incus Container Startup** — Fix gunicorn crash in non-Docker OCI containers (Incus/LXD) by checking `UCM_DOCKER` env var alongside `/.dockerenv` (fixes #36)
- **Update Cache Invalidation** — Force-refresh update cache when switching channels or clicking "Check Now"
- **Package Dependency Resolution** — DEB: always run `apt-get -f install` after dpkg; RPM: use dnf/yum for automatic dependency resolution
- **CI Build Dependencies** — Add `libkrb5-dev` for requests-kerberos/gssapi compilation in CI builds
- **Prerelease Filter** — Accept all non-dev prerelease formats (not just alpha/beta/rc)
- **Docker Migration Glob Safety** — Skip glob loops on empty directories in entrypoint
- **Code Review Fixes** — Security hardening for re-key feature (input validation, error handling)

### Changed
- **Minimum Python 3.12** — Drop Ubuntu 22.04 support, require Python 3.12+ (Ubuntu 24.04+)
- **No compiler required** — `libkrb5-dev` removed from runtime dependencies, only `libkrb5-3` needed

---

## [2.69] - 2026-03-10

### Added
- **Executive PDF Report** — New downloadable PDF with cover page, executive summary, risk assessment, certificate inventory, compliance status, lifecycle analysis, CA infrastructure, and recommendations (~1200 lines, fpdf2/matplotlib)
- **Full Report Scheduler** — 6 schedulable report types (expiring certs, revoked certs, CA hierarchy, audit summary, compliance status, certificate inventory) with configurable frequency, time, day, format (CSV/JSON/PDF), and email recipients
- **Reports Page Redesign** — List-based layout matching Dashboard/Certificates style with stat cards, inline schedule status, and mobile-responsive actions

### Fixed
- **Input Validation & Security Hardening** — Email regex validation, report type allowlist, time format validation, day range checks, max 50 recipients, file handle leak fix, info disclosure removal
- **EmailService Signature** — Fixed parameter mismatch (`to`→`recipients`, `body`→`body_html`) that prevented scheduled emails from sending
- **Accessibility** — Added `type="button"` to 18 native buttons, `aria-label` to 9 icon-only buttons across ResponsiveLayout and AppShell
- **i18n Completeness** — Replaced 7 hardcoded English strings with translation calls, added 8 new keys to all 9 locales
- **Performance** — Memoized `filteredMobileGroups` in AppShell, fixed N+1 query in CA hierarchy report (batch GROUP BY), replaced in-memory audit log aggregation with DB-level GROUP BY queries

---

## [2.68] - 2026-03-10

### Fixed
- **ACME Wildcard CSR Mismatch** — Wildcard certificate finalization failed with "CSR does not specify same identifiers as Order" because CN used stripped base domain instead of exact wildcard domain (fixes #34)
- **ACME Certificate Import** — Let's Encrypt certificates imported with missing metadata (no issuer, SANs, key algorithm, signature algorithm). Now delegates to CertificateService for proper chain splitting, base64 encoding, and full field extraction (fixes #35)
- **Infinite API Loop on User Click** — Clicking a user in management page triggered endless /certificates requests due to unstable useEffect dependencies; fixed with useRef guard
- **mTLS Certificate Hover Disappear** — Certificate item disappeared on hover due to native title tooltip; replaced with aria-label
- **mTLS Generate Missing Name** — API response for mTLS certificate generation was missing the `name` field
- **Reports Grid Spacing** — Report cards grid had no margin spacing; wrapped in space-y-4

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
