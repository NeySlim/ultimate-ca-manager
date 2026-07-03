# Changelog

All notable changes to Ultimate Certificate Manager will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Starting with v2.48, UCM uses Major.Build versioning (e.g., 2.48, 2.49). Earlier releases used Semantic Versioning.

---


## [Unreleased]
- **WebSocket handshake fails when if HTTPS_PORT was set to 443** - `CORS_ORIGINS` always appended `:{HTTPS_PORT}` to every allowed origin, so on port 443 the list contained entries such as `https://ucm.example.com:443`. Browsers omit the port number from the `Origin` header when it is the scheme default so it would never match. As Socket.IO performs server-side checks on `Origin`, WebSocket connections would be silently rejected. `CORS_ORIGINS` now omits the port suffix when `HTTPS_PORT` is 443.


## [2.182] - 2026-07-02

### Added
- **Per-CA ACME timing settings and robust DNS-01 TXT verification** — each external ACME CA account now carries its own order poll timeout, poll interval and HTTP timeout (migration `048` adds `acme_client_accounts.order_poll_timeout_sec`, `order_poll_interval_sec`, `http_timeout_sec`), so a slow authority no longer inherits the global hardcoded values. The DNS-01 challenge self-check now resolves the expected TXT record through the authoritative nameservers first, then public resolvers, with per-resolver diagnostic logging, and invalid ACME authorizations are detected during polling instead of stalling until timeout. The Gandi DNS provider was also hardened (URL-encoding of record values, post-create verification, missing `Any` import) (#150).

### Fixed
- **ACME auto-renewal no longer crashes when refreshing the order expiry** — the renewal service read `new_cert.not_after` to copy the new certificate's expiry onto the order's `expires_at`, but the `Certificate` model exposes that date as `valid_to`. The `AttributeError` aborted the renewal right after the new certificate had been issued and imported, so `expires_at` was never updated and the scheduler re-requested the same certificate on every tick. The renewal path now reads `valid_to`, and `expires_at` is updated correctly so a renewed certificate is not renewed again until its next due window.

### Added
- **Multi-CA management for the ACME client** — UCM can now issue certificates from several external ACME authorities (Let's Encrypt, Actalis, ZeroSSL, Google Trust Services, HARICA…) instead of a single one. ACME CA accounts are managed from the UI (CRUD, per-account External Account Binding, default selection, registration status), each certificate request picks its issuing CA, and the order is pinned to that account so renewals stay on the same authority. The `AcmeClientOrder.acme_client_account_id` foreign key (migration `047`) links each order to its external CA account; `AcmeClientService.for_issuance(environment, account_id=)` resolves explicit account > configured custom directory > Let's Encrypt environment, and `for_order(order)` reuses the pinned account on verify/finalize/status/renewal (#149).


## [2.180] - 2026-06-30

### Fixed
- **Custom ACME CA directory and EAB are now honored for issuance and renewal** — when a custom ACME directory URL was configured in Settings → ACME client (e.g. Actalis, ZeroSSL, Google Trust Services) together with External Account Binding credentials, certificate issuance and renewal still went to Let's Encrypt instead of the configured CA. The custom directory and the EAB persisted in `SystemConfig` were never used by the issuance/renewal path; `acme.client.directory_url` was effectively dead for issuance. A new `AcmeClientService.for_issuance()` factory reads the configured custom directory (over the Let's Encrypt staging/production mapping) and backfills legacy EAB from `SystemConfig` onto the `AcmeClientAccount` row, and `for_order()` resolves the issuing account from the order's recorded `account_url` so an order keeps its CA across changes to the directory setting. All issuance, verify, finalize, status, auto-poll and renewal entry points now route through these factories (#147).


## [2.179] - 2026-06-27

### Fixed
- **Dashboard could not be scrolled on smaller desktop viewports** — on laptops where the sidebar narrowed the grid below the large breakpoint, the dashboard rendered a non-scrollable multi-row grid clipped inside a fixed-height container, so the lower widgets (Recent Activity, System Health, ACME Accounts, Trust Store) were unreachable. The grid container now scrolls vertically when the layout overflows instead of being clipped (#144).
- **Certificate linting no longer spawns a cascade of error toasts** — the conformance-lint modal (`CertificateLintModal`) retriggered its own fetch in a loop whenever a lint call failed, because the toast-dispatch callbacks it depended on were recreated on every render. Toast / notification callbacks are now stable, and the modal guards against concurrent lint calls, so a failed lint surfaces a single error instead of an unbounded stack (#145).

### Added
- **Downloadable diagnostic log bundle** — Settings → About → Diagnostic exposes an admin-only button that downloads a ZIP of the most relevant logs (`ucm.log`, `error.log`, `access.log`, the last lines of the systemd journal when available) plus a short secret-free system diagnostic (version, DB backend, migration number, services status). Sensitive tokens (Bearer credentials, passwords, API tokens, JWTs, PEM private-key blocks) are redacted before packaging, and each log file is capped so the bundle stays lightweight.


## [2.178] - 2026-06-23

### Fixed
- **OCSP responder now echoes the request CertID hash algorithm** — the OCSP responder previously always built the `SingleResponse` CertID with SHA-256, regardless of the hash algorithm used in the request. Strict RFC 6960 clients (notably Cisco ASA) send a SHA-1 CertID and reject a response whose CertID they cannot match back to their request, causing OCSP validation to fail despite a valid `good` status. The responder now uses the request's hash algorithm (SHA-1, SHA-256, SHA-384, SHA-512) and recomputes the issuer name/key hashes accordingly, and the response cache is keyed per hash algorithm to avoid cross-algorithm cache collisions (#143).


## [2.177] - 2026-06-21

### Fixed
- **HSM-backed CA certificate issuance** — issuing, renewing, bulk-reissuing, or approval-flow issuing a certificate against an HSM-backed CA (Vault Transit / OpenBao / PKCS#11 / Azure Key Vault / GCP KMS) no longer fails with `CA private key not available`. Every certificate-issuance path now goes through the HSM-aware `get_ca_signing_key` loader instead of reading the local `ca.prv` column (which is empty for HSM CAs), and gates on `has_private_key` rather than on `ca.prv` (#142).
- **EST and auto-renewal signing** — `sign_csr_from_crypto` (the EST enrollment and automatic-renewal signing path) was loading the CA key directly from `ca.prv` and crashed on HSM-backed CAs; it now routes through the same HSM key loader as the rest of the codebase (#142).
- **SCEP with HSM-backed CAs** — the SCEP factory no longer crashes when the configured CA is HSM-backed. SCEP requires RSA envelope decryption (RFC 8894 §3.4), which is not available for HSM-resident keys, so the service now returns a clear `SCEP is not supported for HSM-backed CAs` error at configuration time instead of failing opaquely at runtime (#142).

### Changed
- **Dead code removed** — the unused `CAOperationsMixin.generate_crl` implementation (all callers use `CRLService.generate_crl`, which is already HSM-aware) and the orphaned `get_ca_private_key_pem` helper have been removed.


## [2.176] - 2026-06-18

### Added
- **Forced 2FA enrolment** — local and SSO logins can be required to enrol a TOTP authenticator before the session is fully usable. A restricted session is established until enrolment is complete (only the 2FA enrolment and logout endpoints are reachable). Global enforcement is a single *Enforce Two-Factor Authentication* toggle for local accounts; each SSO provider has its own `enforce_2fa` switch, independent of the global one. Individual users can be exempted (e.g., a break-glass admin). mTLS and WebAuthn logins are never additionally forced, since they are already a strong second factor (#141).


## [2.175] - 2026-06-17

### Fixed
- **Manual DNS-01 is usable again** — the ACME client no longer waits a fixed 10s then auto-submits. For a **Manual** DNS provider the order stays pending so you can add the TXT record and click **Verify Challenge** (which self-checks DNS before submitting, so it never burns the token; a force option bypasses the check). For **automated** providers the client self-checks propagation (configurable *DNS propagation timeout* in ACME → Let's Encrypt settings) and runs validation in the background so the request never blocks (#140).

### Fixed
- **Duplicate webhook notifications** — `certificate.expiring` (and other events) could be delivered twice with an identical payload while the delivery log showed a single event. Webhook deliveries are now claimed atomically (exactly-once) and the background scheduler runs in a single process, so each delivery is sent once even under concurrent workers (#139).

### Security
- Updated `cryptography` to 48.0.1 (GHSA-537c-gmf6-5ccf, vulnerable OpenSSL in wheels) and forced `ws` to 8.21.0 (CVE-2026-48779, WebSocket DoS).


## [2.173] - 2026-06-17

### Changed
- **SSO identity is now the directory's stable identifier**, never the email — OIDC `sub`, SAML persistent `NameID`, or LDAP `entryUUID`/`objectGUID` (configurable per provider, auto-detected by default). Accounts are recognised across username/email changes, and the email is never an authentication key (removes account-takeover risk). An SSO login whose email matches a local account now provisions a separate SSO account instead of erroring; an administrator can still merge them via *Link to SSO*, which no longer renames the local username (#136, #138).
- **Backups** — the backup list is paginated, searchable and sortable, with multi-select bulk delete, a usage summary (count, total size, free disk) and a *Clean up now* action. Retention is always visible (no longer hidden behind the automatic-backup toggle) and is enforced daily even when automatic backups are off.

### Fixed
- **Backups could fill the disk** — pre-migration database snapshots are now capped to the most recent few, and backup retention runs as its own scheduled task (previously it only ran after a scheduled backup, so manual backups accumulated indefinitely).


## [2.172] - 2026-06-16

### Fixed
- **SSO login with an email that already exists** — an SSO (LDAP/OAuth2/SAML) login whose email matches an existing account no longer returns an Internal Server Error. Instead of silently merging on email (an account-takeover risk) or creating a duplicate, the login is refused with a clear message, and an administrator can deliberately link the two from Users › *Link to SSO* (new `link-sso`/`unlink-sso` actions). One account per email is preserved (#136).
- **Key-recovery dual control is now configurable** — a Settings › Security toggle enables/disables four-eyes control for private-key recovery, and `KEY_RECOVERY_DUAL_CONTROL` in the service environment overrides it (an explicit `false`/`0`/`no` disables it, and the toggle is shown read-only). Previously the setting could not be changed from the UI and the environment value was ignored (#137).


## [2.171] - 2026-06-15

### Added
- **Key archival & recovery** — a dual-control workflow to recover an archived private key: request (with reason) → admin approve (four-eyes; the approver must differ from the requester, configurable) → download as PKCS#12, once, fully audited. New Governance → Key Recovery page and a per-certificate "Recover key" action. Migration 042 (`key_recovery_requests`).
- **Code-signing EKUs** — the Extra-EKU picker now ships the well-known code-signing key purposes (Authenticode individual/commercial, lifetime signing, Windows kernel-mode, macOS code signing / Developer ID Application) on top of the base `codeSigning` EKU, for issuing Windows/JAR/macOS code-signing certificates. New [Code Signing](https://github.com/NeySlim/ultimate-ca-manager/wiki/Code-Signing) wiki guide.
- **Helm chart** — `charts/ucm/` packages UCM for in-cluster deployment (Deployment, Service, Ingress, PVCs, generated/persisted secrets). Single-instance by design; persistent `/etc/ucm` master.key volume (retained on uninstall); SQLite by default or an external PostgreSQL via `database.databaseUrl`.

## [2.170] - 2026-06-13

### Added
- **Certificate conformance linting** — a per-certificate "Lint" action runs the certificate through standards linters (pkilint, plus zlint when available) and shows structured findings, with selectable RFC 5280 and CA/Browser Forum profiles. Informative only; pkilint is an optional dependency and the feature degrades gracefully when it is absent.
- **ACME Renewal Information (ARI)** — the ACME server now advertises and serves a `renewalInfo` resource (RFC 9773), returning a per-certificate suggested renewal window so clients can spread renewals and react immediately to revocation.
- **Prometheus metrics** — opt-in, bearer-gated `/metrics` endpoint exposing certificate, CA, scheduler, webhook and ACME counters in Prometheus exposition format, configurable from Settings › General (generate/rotate/disable the token).
- **Webhook delivery history** — per-endpoint delivery log with status, attempts and manual retry, backed by a durable async delivery queue with exponential backoff.
- **Scheduler admin view** — Settings › System now lists background tasks with their status, last run and a run-now action.
- **Scheduled backups** — automatic encrypted backups on a configurable cadence with retention.
- **In-app help** — contextual help panels and guides now cover the new features (linting, ARI, metrics, webhook delivery history, scheduler, scheduled backups) in every supported language.

### Fixed
- **Pagination** — list pages that paginated client-side (Users, Templates, SCEP, SSH CAs, CRL/OCSP, CSRs, ACME accounts, Discovery) now correctly page through their rows instead of rendering the full list on one page.
- **Layout** — list tables and toolbars no longer overflow into a horizontal scrollbar in split view, modals no longer show a double scrollbar, and the CA "columns" view wraps to fill the width instead of scrolling sideways.
- **Lifecycle events** — issuing, renewing or revoking a certificate (or creating/updating a CA) no longer risks an intermittent error when a webhook endpoint is configured, which could previously surface as a 500.

### Changed
- **Notifications** — email and WebSocket notifications are now fanned out through an in-process event bus, removing duplicated call-sites.

## [2.169] - 2026-06-12

### Added
- **Syslog source field** — remote syslog messages now populate the RFC 5424 HOSTNAME field from the configured System Name (falling back to the machine hostname), so audit events are attributable in log aggregators (#135).

### Fixed
- **LDAP required groups** — the required-groups restriction now saves correctly and is enforced at login; group matching is case-insensitive and previously stored values are repaired automatically (#133).
- **ACME IP certificates** — IP-only orders now honor the configured default issuing CA instead of falling back to the first available CA (#134).

### Security
- **ACME server** — settled challenges (valid/invalid) are no longer re-validated when re-submitted, and key rollover now rejects a key already bound to another account (keyConflict, RFC 8555).
- **Syslog** — structured-data values and message text are escaped/sanitized (RFC 5424), preventing log injection via certificate or user fields.
- **Email** — subjects and recipients are stripped of CR/LF to prevent SMTP header injection.
- **DNS providers** — provider error logs no longer leak API tokens that are transmitted as URL parameters.
- **Filesystem** — private-key and database-backup directories are tightened to owner-only permissions at startup.
- **Audit** — security-alert and audit events now record the real client IP when behind a trusted reverse proxy.

### Changed
- **Outbound services** — webhook, email, and Microsoft CA connectors hardened against partial failures, socket leaks, and logging errors.

## [2.168] - 2026-06-11

### Fixed
- **User deletion** — the delete endpoint now permanently removes the account (with full FK cleanup: sessions, WebAuthn, mTLS certs, SSO sessions, API keys, group memberships) instead of only disabling it. Blocks deletion when pending approval requests exist; audit history is preserved (#132).

## [2.167] - 2026-06-10

### Added
- **ACME IP address certificates (RFC 8738)** — the local ACME server can issue certificates for IPv4 and IPv6 identifiers. Only HTTP-01 and TLS-ALPN-01 are offered (DNS-01 is excluded per spec); TLS-ALPN-01 uses the reverse-DNS form as SNI; the issued certificate carries an `iPAddress` SAN; mixed DNS + IP orders are supported (#131).
- **LDAP required groups & disabled-account handling** — restrict SSO/LDAP login to members of configured required groups, reject disabled accounts, plus login hardening (#129).

### Fixed
- **ACME HTTP-01 for IPv6** — bracket IPv6 literals in challenge URLs per RFC 3986 (previously `InvalidURL`).
- **Rate limiter** — exempt RFC1918/loopback/link-local peers from the per-endpoint login limits, matching the global LAN-trust bypass; brute-force protection remains enforced via account lockout.
- **In-app help** — corrected ACME help section ordering across all locales and documented IP-certificate support.

### Changed
- **CI** — GitHub Actions bumped to Node 24 runtimes.

## [2.166] - 2026-06-10

### Fixed
- **ACME ToS XSS** — HTML-escape terms of service content before rendering in React (#125).
- **Password policy bypass** — removed hardcoded `len < 8` check that could be bypassed with custom policy; policy enforcement now uses the full `validate_password()` result.
- **Migration transaction** — explicit `rollback()` after FK disable failure prevents `InFailedSqlTransaction` poison in psycopg2 connections.
- **Netcup DNS** — multi-part TLD support in `_split_domain_and_host` (e.g. `co.uk`).
- **Policy config cache** — `@lru_cache` on policy config to avoid repeated DB reads; removed dead code from legacy password checks.
- **ACME EAB** — proper notes field on EAB credentials, persisted in DB.
- **Auto-renewal** — fixed source validation (whitelist check) preventing valid sources from being rejected.
- **ExportDropdown** — hardcoded English strings replaced with `t()` interpolation (all 9 locales synced).

## [2.165] - 2026-06-09

### Added
- **ACME DNS-01 auto-poll** — after TXT record creation, automatically wait for DNS propagation (30s), submit challenges, poll ACME status every 5s, and auto-finalize when order is ready (#127).

### Fixed
- **Database migration** — rollback connection after FK disable failure to prevent `InFailedSqlTransaction` when non-superuser runs SQLite → PostgreSQL migration (#126).
- **SSH CA setup script** — remove backslash-quotes from `CA_PUB_KEY` template that caused bash to execute the key as a command (`not found`) (#125).
- **Password complexity error** — `validate_password()` returns `List[dict]` but callers were passing the raw dict to `error_response()`, displaying `[object Object]` in the UI (#128).
- **SSH CA setup** — strip newlines from public key before embedding in shell script.
- **ACME DNS** — Netcup read-modify-write + nested subdomain resolution; Cloudflare scoped token `test_connection` fix.

## [2.164] - 2026-06-08

### Fixed
- **Netcup DNS** — read-modify-write on `create_txt_record` (no more zone overwrite), nested subdomain resolution (`_split_domain_and_host`), deletion uses internal record IDs.
- **Cloudflare DNS** — `test_connection()` uses zone-scoped `/zones?per_page=1` instead of `/user/tokens/verify` (fixes false-positive with scoped API tokens).

## [2.163] - 2026-06-07

### Added
- **ACME Terms of Service** (#120 point 4) — `GET /acme/terms` public endpoint returns HTML-rendered ToS (RFC 8555 §7.1.1). Settings API (`GET/PATCH /api/v2/acme/settings`) manages title + body JSON. Frontend ConfigTab has scrollable preview card + edit modal with live preview. Migration 039 seeds default ToS on fresh installs.

### Fixed
- **ACME /acme/terms endpoint** — returns raw `text/html` instead of JSON wrapper. No more escaped characters in HTML.
- **ACME directory** — `meta.termsOfService` URL points to `/acme/terms` for ACME clients.

## [2.162] - 2026-06-06

### Fixed
- ACME domain form (#123) — Radix Select fields (DNS provider, issuing CA) now display correctly instead of appearing blank. Values kept as strings in state (Radix requirement), converted to integers only on submit.
- ACME domain form — initial state for `dns_provider_id` now safely handles undefined values via optional chaining.
- Policies form — Radix Select values for CA and approval group now display correctly (strings for Radix compat).
- Duplicate CHANGELOG entries in 2.161 cleaned up.

## [2.161] - 2026-06-05

### Added
- **CI semver normalization** — RC tags (`2.161-rc1`) are auto-normalized to valid semver (`2.161.0-rc1`) for `npm ci` in build workflows.
- **EAB credential notes** (#120) — free-form notes column on `acme_eab_credentials` table (migration 038), editable in ACME EAB tab.

### Changed
- **CI pipeline hardened** — `npm ci` now works reliably on RC tags; lockfile integrity preserved (no more blanket `sed` corruption).

### Fixed
- Password policy centralization (#121) — all validation moved to `security/password_policy.py`, enforced across login, password change, account creation, and force-change flows. Admin bypass retained.
- Discovery profiles (#122) — corrected field name mismatches (`schedule_enabled`, `schedule_interval_minutes`) in `DiscoveryPage.jsx` and `ProfileDetailPanel.jsx`; profile list now refreshes after create/update.
- All `db.session.commit()` calls wrapped in `safe_commit()` — prevents 500 crashes from IntegrityError.
- GitHub code scanning alerts: `react-router` → `6.30.4`, batch-updated Python dependencies.
- Frontend quality check: removed React 18 false-positive hook provider tests (479 tests clean).

## [2.160] - 2026-06-04

### Fixed
- ACME challenge responses no longer fail with an internal error when auditing an authorization identifier stored as JSON.
- Hardened ACME authorization identifier handling across challenge validation, authorization responses, wildcard detection, and ACME admin views.

## [2.159] - 2026-06-03

### Added
- **CA-template pinning** (#118) — pin templates to specific CAs for quick access in certificate issuance form. Pinned templates appear with pushpin icon at top of dropdown, with option to show all templates. Backend API endpoints for pin/unpin operations, migration 037 adds `ca_template_pins` table.
- Manage Pins button in CA floating window action bar for quick access to template pinning modal.

### Fixed
- Template pinning UI: replaced emoji with PushPin icon from phosphor-icons for consistency.
- i18n interpolation in "Show all X templates" button now correctly displays template count.
- FloatingDetailWindow: fixed canWrite/canDelete props passing to CADetails component, preventing ReferenceError.
- CA details floating window now properly displays action buttons (Export, Manage Pins, Take Offline, Delete).

### Security
- Updated frontend dependencies to fix security vulnerabilities: engine.io-client (moderate), picomatch (high), brace-expansion (moderate), @vitest/coverage-v8 (critical).

## [2.158] - 2026-06-03

### Fixed
- SSH certificate issuance: cast TTL values to int to prevent str/int comparison error (#119)
- SSH setup script: fix import path after module reorganization (#119)
- mTLS certificate generation: use correct CertificateService method signature (#119)

## [2.157] - 2026-05-13

### Fixed
- Webhook form: empty `auth_username` and `auth_header_name` fields now sent as `null` instead of `""`, preventing 400 validation errors when the field is optional for the selected auth type (#117).

## [2.156] - 2026-05-12

### Added
- **Webhook custom authentication** (#116) — five auth types per webhook: `none`, `bearer`, `basic`, `api_key`, `custom`. Tokens encrypted at rest, never returned in API responses (only `auth_token_set` boolean). PUT semantics: omitted token preserves existing, null clears, empty string is rejected.
- Migration 036 adds `auth_type`, `auth_token` (encrypted), `auth_username`, `auth_header_name` columns to `webhooks` (dual-backend SQLite + PostgreSQL).
- Webhook form UI: auth type selector with conditional fields (token, username, header name), live request-preview pane with token masking, explicit clear-token control.
- Audit events: `webhook.auth_configured`, `webhook.auth_disabled`, `webhook.auth_token_rotated`, `webhook.auth_token_invalid`.
- 18 backend integration tests + 20 frontend tests covering all 5 auth types, PUT semantics, validation errors, and token masking.
- Webhook auth documentation in settings help page (all 9 languages).

### Security
- `Authorization` header value blocked when `auth_type=api_key` (forces operator to use bearer/basic for that scheme).
- Token capped at 8192 bytes.
- Tokens stored using the same encrypted-property pattern as other secrets (master key in `/etc/ucm/master.key`).

### Fixed
- `DELETE /api/v2/webhooks/<id>` now returns 204 No Content (was 200 with body), aligning with the project DELETE convention.

## [2.155] - 2026-05-10

Auto-renewal UI, PostgreSQL migration recovery (closes [#115](https://github.com/NeySlim/ultimate-ca-manager/issues/115)), LAN-friendly rate limiting, and master-key backup safeguards.
Validated 6/6 across SQLite and PostgreSQL on Debian, RHEL/Fedora, and Docker.

### Added
- **Auto-renewal settings UI** — dedicated section in Settings to configure global renewal threshold, retry policy, scheduler interval, and per-CA overrides. Backend endpoints `GET/PUT /api/v2/settings/auto-renewal` with full validation.
- **Master-key backup UX** — new `GET /api/v2/system/security/master-key/download` endpoint (admin-only, audited). `enable-encryption` now returns the master key inline (one-time) with `backup_required: true`. Settings → Security shows a "Back Up Master Key" action when the key is file-sourced. A confirm-gated modal forces the operator to download and acknowledge before dismissal. The endpoint returns 409 when the key is supplied via environment variable (operator must back it up out-of-band).
- Dockerfile now declares `VOLUME ["/etc/ucm", "/opt/ucm/data"]` so master.key survives container recreation when no explicit bind mount is provided.

### Fixed
- **PostgreSQL migrations** ([#115](https://github.com/NeySlim/ultimate-ca-manager/issues/115)) — migrations 029, 031, 032, 033, 034 are now dual-backend (SQLite + PostgreSQL). Adds reconcile migration `035_reconcile_pg_schema.py` to repair PG instances that booted on a SQLite-only release. The migration runner now refuses to start in strict mode if SQLite-only migrations would be skipped on PostgreSQL past the 020 boundary.

### Changed
- **Rate limiter** — LAN clients (RFC1918 + loopback) bypass rate limits by default (`RATE_LIMIT_TRUST_LAN=true`). Standard tier raised from 300/min to 600/min and from 60 burst to 100, removing false positives on busy on-prem deployments.

## [2.154] - 2026-05-10

Fixes OPNsense 26.1.x certificate import (closes [#114](https://github.com/NeySlim/ultimate-ca-manager/issues/114)).
Validated 6/6 across SQLite and PostgreSQL on Debian, RHEL/Fedora, and Docker.

### Fixed
- **OPNsense import** — three bugs prevented the API-based import path from working against OPNsense 26.1.x:
  - Frontend service did not unwrap `success_response.data`, so the items list was empty after `Connect` and the `Import Selected` button never rendered.
  - Backend stored OPNsense `uuid` as UCM `refid`, breaking the `caref` linkage between certificates and their CA (OPNsense uses the 13-char `refid` as cross-reference, not the 36-char `uuid`).
  - Imported private keys were stored raw instead of going through `store_pem_bytes()`, bypassing encryption-at-rest.
- Importer now performs a 2-pass import (CAs before certificates), resolves `caref` against in-flight CAs, extracts SAN/SKI/AKI/serial, falls back to `crt_payload`/`prv_payload` when `crt`/`prv` are absent, and treats an empty selection as "import all".
- Added regression test `test_opnsense_import.py` covering refid storage, caref linkage, and encrypted private-key round-trip.

## [2.153] - 2026-05-10

Adds CA offline mode (closes [#106](https://github.com/NeySlim/ultimate-ca-manager/issues/106)).
Validated 6/6 across SQLite and PostgreSQL on Debian, RHEL/Fedora, and Docker.

### Added
- **CA offline mode** — take any CA offline to block signing while keeping the public certificate usable for chain validation, CDP and OCSP. Two modes:
  - **Password-protected** — private key re-wrapped with a user-supplied password (PKCS#8) on top of the existing master-key wrap, restore requires the password.
  - **File-exported** — private key returned as a password-encrypted PKCS#8 PEM and removed from the database, restore requires re-uploading the file plus the password.
- Sign/issue/CRL paths gate on `ca.offline` (`csrs.py`, `services/cert/mixins/csr.py`, `services/ca/ca_signing.py`, `crl.py`). The legacy `update_ca` backdoor is closed — only the dedicated take-offline / restore endpoints can flip the flag.
- Frontend: `TakeOfflineModal`, `RestoreModal`, offline-aware `StatusBadge` + dedicated `OfflineBadge` across all 4 CA list views, action buttons in `CADetailsPanel` and the floating detail window.
- Audit actions: `ca.offline.password_protected`, `ca.offline.file_exported`, `ca.restore.password_protected`, `ca.restore.file_exported`.
- In-app help, GitHub wiki page (`CA-Offline-Mode`), and documentation in `USER_GUIDE.md` + `SECURITY.md` threat model.
- Migration `034_add_ca_offline.py` adds `offline`, `offline_reason`, `offline_mode` columns.

## [2.152] - 2026-05-08

Security and RFC-compliance hardening pass across all PKI protocols and resource APIs.
Smoke-tested across SQLite and PostgreSQL on Debian, RHEL/Fedora, and Docker (33 migrations from-scratch on PG verified).

### Security
- **Certificate authorities** — whitelist key params, cap validity at 3650 days, lock HSM-bound key, validate URLs (CRL DP / AIA / OCSP / IDP), cap bulk and list operations, harden create/update/export. CSR signing now verifies `is_signature_valid` (proof of possession). EC curve restricted to a whitelist.
- **Certificates** — whitelist key params, cap validity, fix unhold bugs.
- **CSRs** — cap validity, validate keys, verify CSR pubkey ↔ submitted match, cap PEM size 64 KB.
- **Templates** — cap validity_days, whitelist key_type/digest, fix import NULL.
- **Policies / approvals** — enforce group gate, expiry and validity reclamp.
- **Users** — require current password for self-change, protect last admin (≥1 active admin invariant).
- **RBAC** — validate role payload, reject reserved names (`admin`/`operator`/`viewer`), permission whitelist with wildcard.
- **SSO** — add PKCE (S256) and nonce to OIDC auth flow.
- **HSM** — encrypt provider secrets at rest, cap sign payload at 1 MiB, FK-guard deletes; runtime `pip install` disabled by default (opt-in via `UCM_ALLOW_RUNTIME_PIP=1`).
- **Microsoft CA** — fail-closed encryption, EOBO admin gate, audit, size caps.
- **Webhooks** — encrypt secret at rest, validate event names against allowlist, lock reserved headers, cap events per webhook.
- **Discovery** — validate ports, IPv6 subnet cap (≤1024), gate `update_profile`.
- **Audit** — trusted-proxy XFF (only honour `X-Forwarded-For` from configured proxies), fix invalid kwargs in ACME audit, post-cleanup integrity check.
- **Reports** — cap generate params dict size (DoS guard).
- **SSH** — validate sign/generate payload (caps on principals ≤64, extensions/options ≤32, validity 60 s – 10 y).
- **Trust store** — whitelist purpose, cap PEM size 256 KB, sync limit 1–1000.
- **ACME (server)** — close 6 RFC 8555 auth bypasses (account binding, order ownership, authz state machine, finalize URL, key change, deactivation).
- **ACME (proxy)** — block SSRF via forged proxy IDs; finalize ownership check.
- **ACME (client)** — validate domain syntax, cap inputs, harden commits.
- **EAB** — encrypt HMAC keys at rest.
- **EST** — proof of possession, serialize bug fixes, config bound validation.
- **SCEP** — tighten challenge auth, audit reads, validate config bounds.

### Fixed (RFC compliance)
- **OCSP (RFC 6960)** — handle mixed-format serials in DB lookup (decimal / lower hex / upper hex), invalidate cache on revoke, correct `keyHash` calculation, honour `nonce` extension (skip cache when present), refuse delegated responder cert without `id-pkix-ocsp-nocheck`.
- **CRL (RFC 5280)** — handle mixed-format serials, drop silent truncation of serials >159 bits, auto-regen expired CRL on CDP fetch.
- **Certificate profile (RFC 5280)** — 5 issues fixed in CA/CSR signing paths (SKI/AKI format, BasicConstraints encoding, EKU consistency, KU bit ordering, validity bounds).
- **ACME (RFC 8555 / 8737)** — EAB JWK match via thumbprint, JWS algorithm allowlist (asymmetric only), wildcard domain restricted to DNS-01, ALPN extension marked critical, case-insensitive domain handling. Pre-authorisation flow (§7.4.1) — `acme_authorizations.order_id` now nullable (migration 033).
- **TSA (RFC 3161 / 5035)** — `signing-certificate-v2` ESS attribute now mandatory, request body capped at 64 KiB, correct `PKIStatus` separation from `PKIFailureInfo`.
- **EST (RFC 7030)** — `serverkeygen` encrypts the server-generated key under the **client mTLS pubkey**, not under the newly issued cert.
- **SCEP (RFC 8894)** — reject renewal when signer cert is expired or not yet valid.

### Fixed (other)
- **Imports** — CA and certificate import endpoints now encrypt private keys via `encrypt_private_key` instead of storing base64-plain (silent regression introduced when import paths bypassed the lifecycle mixin).

### Added
- **`tools/decode-csr` and `tools/decode-cert`** — input capped at 256 KiB → `413` (DoS guard).

### Tests
- 1676 backend tests + 461 frontend tests pass.
- 2 encryption-related tests made hermetic to host `master.key` (monkeypatch `MASTER_KEY_PATH` and use `is_string_encrypted()`).

## [2.151] - 2026-05-07

### Fixed
- **ACME proxy did not enforce External Account Binding (#112)** — when `acme_eab_required` was enabled, the proxy directory at `/acme/proxy/directory` advertised upstream Let's Encrypt's `meta` as-is (which does not require EAB), so clients like win-acme reported "server does not indicate that this is required" and proceeded to register an account without an `externalAccountBinding`. The proxy `POST /acme/proxy/new-account` likewise never inspected the payload for an EAB field and accepted any registration. The proxy now (1) overrides `meta.externalAccountRequired` with the local UCM policy in its directory, and (2) validates the `externalAccountBinding` JWS in `/new-account` exactly like the local server, rejecting registrations without a valid HMAC binding when EAB is required.
- **Local `/acme/new-account` returned 500 on empty body** — `request.get_json()` raised on requests with `Content-Type: application/jose+json` and an empty body instead of producing a clean `400 malformed`. Now uses `force=True, silent=True` so empty/invalid payloads return the documented ACME error.
- **ACME admin UI 404 on account detail (#113)** — the admin routes `GET/DELETE /api/v2/acme/accounts/<id>`, `POST .../deactivate`, `GET .../orders`, `GET .../challenges` only resolved by numeric primary key, but the UI passes the public `account_id` string. New `resolve_acme_account()` helper accepts either form and is used by all five admin routes; protocol routes (RFC 8555) are unchanged.
- **`refactor(acme): bind directory_url to account key via AcmeClientAccount table`** — landed in this release: the on-disk account key file is now selected by joining `AcmeAccount.directory_url` to the matching `AcmeClientAccount` row, removing the previous heuristic that looked up the key by directory URL string match alone.

### Tests
- **`tests/conftest.py::create_user`** — made the factory idempotent on session-DB collisions, so a test that re-uses a user hint (or a sharded CI re-run) no longer fails with HTTP 500 on the second create. The full backend suite (1676 + 209 ACME + frontend 461) is green on all three distros.

## [2.150] - 2026-05-07

### Fixed
- **ACME default environment ignored when payload omits it (#26)** — `POST /api/v2/acme/client/accounts` and `POST /api/v2/acme/client/orders` always defaulted to staging (`environment='staging'`) when the request body did not specify one, even though Settings → ACME → Let's Encrypt let operators pin a default environment via `acme.client.environment`. New ACME accounts and on-demand orders created from the frontend (which never sends `environment` in the body) silently went to staging instead of production. Both endpoints now read `SystemConfig['acme.client.environment']` when the field is omitted, falling back to `'staging'` only if no default is configured. The frontend `ACMEPage` modal now also waits for `clientSettings` to load before opening, eliminating a race that briefly defaulted the dropdown to staging at mount.
- **DELETE on templates and certificates failed on FK violation** — `DELETE /api/v2/templates/<id>` did not check if the template was referenced by certificates or policies before issuing the delete, raising `IntegrityError` (HTTP 500) when the template was in use. Now blocks with `409 Conflict` and a "used by N certificate(s) / N policy/policies" message; operators must remove the dependents first. `delete_certificate` in `services/cert/mixins/lifecycle.py` did not clean up `ApprovalRequest` rows pointing to the certificate, hitting the same FK class of failure on certs that had ever been the subject of an approval workflow. Cleanup is now wrapped in a try/except with explicit rollback.
- **Unprotected `db.session.commit()` in 39 service-layer call sites** — bare commits across 20 service modules (acme_renewal, audit/query, auto_renewal, backup/restore_core, ca/{ca_creation,ca_crud,ca_operations,ca_signing}, cert/mixins/{csr,import_export,lifecycle}, crl/generation, discovery/{profiles,query,scanner}, hsm/hsm_service, opnsense/config, policy_service, ski_aki_backfill, template_service) had no surrounding `try/except`. On any commit failure (constraint violation, disconnected DB, deadlock) SQLAlchemy left the session in a broken-transaction state, causing every subsequent request handled by the same worker to fail with `PendingRollbackError` until the worker recycled. All 39 sites are now wrapped: `try: db.session.commit(); except Exception as e: db.session.rollback(); logger.error(..., exc_info=True); raise` — same caller-side behavior, just a guaranteed rollback.
- **PostgreSQL upgrades crashed at boot on migration 030 (#111)** — `030_add_certificate_san_upn._upgrade_pg(engine)` opened `with engine.begin() as conn:` but the migration runner already passes the live, transactional `Connection` to `mod.upgrade(conn)` (fixed in #103/#104). Calling `.begin()` on an already-bound `Connection` raises `sqlalchemy.exc.InvalidRequestError: a transaction is already begun on this connection`, killing the boot of every PostgreSQL install upgrading to v2.149. Reported by @Hemsby. Migration 030 now uses the runner-supplied `Connection` directly. The same latent bug existed in eight earlier `pg_compatible` migrations (020, 021, 022, 023, 024, 025, 026, 027 EAB, 027 backfill SAN email) — they were invisible because previously applied installs never re-ran them, but a fresh PostgreSQL install would have hit the same crash on first migration. All nine are converted to the `_upgrade_pg(conn)` shape and use the supplied connection directly.
- **Test guard against future regressions** — added `test_pg_migrations_do_not_open_nested_transactions` in `tests/test_migration_runner_pg.py` that AST-scans every `pg_compatible` migration and rejects any call to `engine.begin()` / `conn.begin()`. The pre-commit hook will catch any new migration that re-introduces the pattern. End-to-end check `test_pg_migration_runs_against_real_postgres` was rerun against a real PostgreSQL 15 container and passes.

## [2.149] - 2026-05-06

### Added
- **Microsoft UPN SAN support (1.3.6.1.4.1.311.20.2.3)** — CSRs and certificates can now carry User Principal Names in the Subject Alternative Name extension, the format Microsoft Active Directory expects for smart-card / certificate-based logon. UPN values are validated (`user@domain` form, no whitespace), DER-encoded as `OtherName(UPN_OID, UTF8String)` via `asn1crypto`, persisted in a new `certificates.san_upn` column (JSON array, migration `030_add_certificate_san_upn.py`, multi-backend SQLite + PostgreSQL), and surfaced in the UI through a new `UPN` option in the SAN editor on both the CSR creation page and the issue-certificate form. Internal CA issuance, ACME, EST, SCEP, and the `POST /api/v2/csrs` and `POST /api/v2/certificates` endpoints all accept UPN entries via the `UPN:` prefix in the unified `san` array. The detail panel renders them in `san_combined` as `UPN:user@corp.local`. Read-side parser already supports them via `utils/cert_extensions.py`.
- **EOBO auto-fill prefers UPN SAN** — when enabling Enroll-On-Behalf-Of in the Microsoft CA submission flow, the enrollee UPN field now auto-populates from the CSR's UPN SAN first, then falls back to SAN email, then to the subject `emailAddress`. Operators no longer have to retype the UPN that was already encoded in the CSR.

### Fixed
- **Microsoft CA issuance created a duplicate Certificate row** — `_import_signed_cert` in `api/v2/msca.py` issued an `INSERT` for a brand-new `Certificate` (with `source='msca'`) AND an in-place `UPDATE` of the originating CSR row, leaving two records for the same certificate (the CSR-derived one without `source`, so it was missing the `ADCS` tag in the UI). Now the CSR row is upgraded in-place into a full certificate (subject, issuer, serial, AKI/SKI, validity, SANs refreshed from the issued cert, `source='msca'`) and `MSCARequest.cert_id` points to it. The fallback `INSERT` path is kept for the (currently unused) case where there is no originating CSR.
- **ACME default environment Select didn't persist** — the Select on Settings → ACME → Let's Encrypt always reverted to Staging after reload. Frontend was reading/writing `default_environment` and `contact_email`, but `GET/PATCH /api/v2/acme/client/settings` uses the keys `environment` and `email`. The PATCH was silently dropped (unknown key) and the GET response was never read on the UI side, so the dropdown could never reflect a saved value. Aligned `LetsEncryptTab` and `ACMEPage` on the actual backend keys (#110).

## [2.148] - 2026-05-06

### Fixed
- **SSO connection test endpoint crash** — `POST /api/v2/sso/providers/<id>/test` raised `NameError: name '_test_saml_connection' is not defined` (and the OAuth2/LDAP variants), making the "Test connection" button unusable for every SSO provider type. Discovered while smoke-testing v2.147 in production. Audit of the whole `api/v2/sso/` package surfaced six more files missing imports after the modular refactor — `connection_tests` (`http_requests`, `utc_isoformat`, `validate_url_not_cloud_metadata`), `ldap_routes` (`session`, `urllib`, `_ldap_authenticate_user`), `login_routes` (`http_requests`, `json`, `_get_ssl_verify`, `_cleanup_ssl_verify`, `_parse_json_field`, `_get_or_create_sso_user`, `_get_saml_auth`), `mapping_tests` (`_decrypt_ldap_password`, `_build_ldap_tls`), `saml_routes` (`safe_fromstring`, `utc_now`, `utc_isoformat`), plus `providers` itself. None of these endpoints were exercised by unit tests, so the regressions only surfaced on real production traffic.
- **Project-wide static audit** — added `backend/scripts/audit_undefined_names.py` (AST-based detection of names referenced but never defined or imported, taking nested-tuple destructuring into account) and `backend/scripts/audit_imports.py` (smoke-imports every backend module to catch `NameError` / `ImportError` at load time before any HTTP request hits the route). Both checks are now wired into the pre-commit hook (`scripts/pre-commit`), so a refactor that drops an import is rejected at commit time instead of being discovered in production.
- **`services/opnsense/parser.py` import crash** — the module imported `defusedxml.ElementTree as ET` then referenced `ET.Element` in type annotations, but `defusedxml.ElementTree` does not expose an `Element` class (`AttributeError` at import time). Now imports `Element` from the stdlib `xml.etree.ElementTree` for typing while keeping `defusedxml` for parsing. Caught by the new import-smoke audit.
- **`api/v2/certificates/bulk.py` missing imports** — used `os`, `subprocess` and `tempfile` (PKCS#7 export via OpenSSL CLI fallback) without importing them. Caught by the new audit.

## [2.147] - 2026-05-06

### Fixed
- **ACME account detail tabs** — Orders and Challenges counts always rendered as 0 and the Orders/Challenges tabs were empty. Frontend was reading `res.data.orders` / `res.data.challenges` but the API returns the array directly under `res.data`; backend endpoints `GET /api/v2/acme/accounts/<account_id>/{orders,challenges,deactivate}` and `GET|DELETE /api/v2/acme/accounts/<account_id>` were also using `Query.get(account_id)` against an integer primary key when `account_id` is the public string identifier, so every lookup returned 404 (#109).
- **Local ACME history challenge type** — entries from the local ACME server always reported `challenge_type=http-01`. Now resolved from the first validated `AcmeChallenge` of the order so DNS-01 / TLS-ALPN-01 issuances are reported correctly (#109).
- **SSO SAML login crash** — `/api/v2/sso/login/saml` and `/api/v2/sso/callback/saml` raised `NameError: name 'logger' is not defined` (and `_get_saml_auth` / `traceback`) on the first error path, masking the real failure. Added the missing `logging`, `traceback`, and `_get_saml_auth` imports in `api/v2/sso/login_routes.py`, plus `logger` in `api/v2/sso/mapping_tests.py` and `api/v2/sso/connection_tests.py` (audit confirmed no other runtime modules were affected).

## [2.146] - 2026-05-05

### Fixed
- **Release workflow** — validate stable tags against `main` and prerelease tags against `test`, and stamp `VERSION` / frontend package metadata before every frontend build so published DEB, RPM, and Docker artefacts embed the correct UI version (#108).

## [2.145] - 2026-05-04

### Fixed
- **ACME Local server tab** — restored the `GET`/`PATCH /api/v2/acme/settings` endpoint and passed the missing `cas` prop to `ConfigTab`, fixing a `TypeError: Cannot read properties of undefined (reading 'map')` that crashed the Local ACME tab on click (#107).
- **Boot import** — re-exported `commit_or_rollback` from `utils/db_transaction` (lost during a refactor) so the service starts cleanly.

## [2.144] - 2026-05-03

### Added
- **`utils/key_codec.py`** — `load_pem_bytes(prv, *, context)` / `store_pem_bytes(pem)` helpers that consolidate the previously duplicated `base64.b64decode(decrypt_private_key(model.prv))` pattern across 26 sites in `api/v2/*` and `services/*`. Errors now surface a caller-supplied context (`"CA 42"`, `"certificate 17"`) instead of an opaque `binascii.Error` when a stored `.prv` is malformed or was encrypted with a different `KEY_ENCRYPTION_KEY`.
- **`utils/db_transaction.commit_or_rollback()`** — boolean-returning service-layer counterpart to `safe_commit()` (which is Flask-response-returning). Replaces 10 bare `db.session.commit()` calls in `auth/unified.py`, `services/mtls_auth_service.py`, `services/webauthn_service.py` that previously could leak partial transactions on integrity errors.
- **`security/encryption.encrypt_text()` / `decrypt_text()`** — text-oriented helpers (PEM, JSON blobs, plain strings) that share the same wire format as `encrypt_string()` but never confuse the caller about the input contract. The mixed `encrypt()` (expects base64) vs `encrypt_string()` (expects text) split caused #105.
- **Generic release tooling** — `scripts/smoke_release.py` (auth/CDP/OCSP/EST/health probe), `scripts/release_publish.sh` (tag + GitHub release publish), `scripts/wiki_release_notes.py` (changelog → wiki page generator). Lab-specific hostnames removed; everything is parameterised via `UCM_BASE` env var.
- **CI workflows** — `.github/workflows/tests.yml` runs the backend suite against both SQLite and PostgreSQL on every push (closes the gap that let #103 ship). `.github/workflows/release-smoke.yml` runs `smoke_release.py` against the published artefacts after every `v*` tag.
- **Pytest `postgres` marker** — opt-in marker for tests that require a live PostgreSQL backend; skipped by default locally, always run in CI.

### Fixed
- **Silent `except Exception: pass` blocks in critical auth/security paths now log with `exc_info=True`.** Specifically: `auth/unified.py` (4 sites: lockout config read, account-locked notification, login/logout WebSocket broadcasts, SMTP probe), `api/v2/auth.py` (7 sites: password policy import, password reset audit, etc.), `security/csrf.py` (CSRF token extraction failures), `security/encryption.py`, `config/https_manager.py`, `services/audit/core.py`, `services/email_service.py`, `services/syslog_service.py`, `utils/backup_codes.py`. These were not bugs in themselves but made post-mortem debugging of auth failures effectively impossible.
- **Latent #105-class regressions** — 4 additional sites that round-tripped PEM through `encrypt()`/`decrypt()` were migrated to `encrypt_text()`/`decrypt_text()`.
- **10 bare `db.session.commit()` sites** in auth/mTLS/WebAuthn paths now wrap in `commit_or_rollback()` and rollback cleanly on `IntegrityError`.

### Changed
- **26-site refactor** to `utils/key_codec.load_pem_bytes()`. Behaviour-preserving (asserted by `TestEquivalenceWithLegacyPattern` test class); reduces import footprint (single `utils.key_codec` import vs `base64` + `security.encryption`).

### Tests
- `tests/test_key_codec.py` (8 tests) — round-trip with/without `KEY_ENCRYPTION_KEY`, error messages with caller context, byte-for-byte equivalence with the legacy inline pattern.
- `tests/test_db_transaction.py` (5 tests) — `commit_or_rollback()` returns False + rolls back on `IntegrityError`, returns True on success, no double-rollback when called twice.
- `tests/test_pem_encryption_helpers.py`, `tests/test_acme_proxy_key_encrypted.py`, `tests/test_key_encryption_pem_passthrough.py`, `tests/test_migration_runner_pg.py` — regression coverage for #103/#104/#105 to prevent re-introduction.

### Internal
- Backend suite: 1645 passed / 1 skipped (was 1632 / 1 in v2.143).
- Frontend suite: 461 passed.

## [2.143] - 2026-05-03

### Fixed
- **PostgreSQL migration runner crashed on startup** when applying any pending migration written for the legacy `Engine` interface. `_run_pending_pg()` now opens a single transactional `Connection` via `engine.begin()` and passes it to `mod.upgrade(conn)`, matching the SQLite path and the migration module signatures (#103, #104). Without this fix, fresh PostgreSQL deployments couldn't boot past first start, and existing PG instances couldn't apply any future migration.
- **ACME proxy account private key was stored in plaintext in `system_config`.** It is now encrypted at rest with the application key via `encrypt_private_key()` / `decrypt_private_key()`, and existing plaintext keys are migrated transparently on first read (#105).
- **`KeyEncryption.decrypt()` no longer raises `binascii.Error` on PEM-formatted input** that was never encrypted in the first place. The probe now isolates base64 detection from Fernet decryption so legacy plaintext keys round-trip cleanly through the new ACME proxy decrypt path.

### Changed
- **Cross-target release validation now covers PostgreSQL** in addition to SQLite for every supported package (DEB, RPM, Docker). The PostgreSQL backend is now part of the mandatory pre-release smoke matrix because the #103 regression only manifested on PostgreSQL and would have shipped silently against a SQLite-only matrix.

## [2.142] - 2026-05-02

### Security
- **EST `/cacerts`, `/simpleenroll`, `/simplereenroll`, `/serverkeygen`, `/csrattrs` now enforce `est_enabled` on every request** and short-circuit with `503 EST disabled` instead of falling through to the SPA. The `/serverkeygen` body is also size-capped and stricter about content negotiation.
- **EST and SCEP mTLS client certificates are only honoured when the request comes from a trusted reverse proxy** (`security.trusted_proxies`). Direct hits without TLS termination by UCM no longer accept proxy-injected client cert headers.
- **mTLS login route gated behind trusted-proxy check.** Same protection as EST/SCEP — header-based mTLS is rejected unless the request originates from a trusted proxy.
- **2FA backup codes are now hashed at rest** (Argon2id) and consumed atomically; plaintext codes are returned only at generation time and never stored.
- **Approval quorum is race-safe and idempotent.** Concurrent approvals on the same request can no longer over-approve; double-submits are deduplicated.
- **On-demand CRL generation is serialised per-CA** with a per-CA lock and `503 Retry-After: 5` under contention — closes a CPU/IO DoS vector when many clients hit `/cdp/<ca>.crl` simultaneously.
- **Outbound webhooks revalidate the resolved IP at delivery time** (DNS-rebinding window closed) and reject cloud-metadata IPs (`169.254.169.254`, GCP/Azure/Alibaba equivalents) and loopback. RFC1918 / `.lan` / `.local` targets remain allowed by design (UCM is on-prem).
- **SSO/IdP, ACME proxy and webhook URL fields all share the same SSRF helper** (`validate_url_not_cloud_metadata`) — cloud metadata is blocked everywhere.
- **CSV bulk user-import capped at 5 MB / 10 000 rows** with `413` on overflow.
- **Runtime HSM `pip install` disabled by default**, returns `403` with a hint to set `UCM_ALLOW_RUNTIME_PIP=1` or install the dependency via the system package manager.
- **SCEP CSRs no longer copy arbitrary KU/EKU bits** — only a whitelist (`digitalSignature`, `keyEncipherment`, `serverAuth`, `clientAuth`) is honoured.
- **SCEP RFC 8894 P0/P1/P2 hardening** — stricter PKCS#7 parsing, transaction-ID validation, signed/encrypted response envelope checks; iOS/macOS enrollment fixes (#102).
- **ACME account private keys encrypted at rest** with the application key.
- **Password change endpoint ignores client-supplied `force_change`** (only operators can clear that flag).
- **CSRF token entropy increased**; password hash algorithm tightened; database migration identifiers validated against an allow-list.
- **`ProxyFix` is opt-in** via `security.trusted_proxies` — prevents unauthenticated `X-Forwarded-For` spoofing on direct deployments.
- **Filesystem session directory is now created/enforced at mode `0o700`** and the application refuses to boot if it has group/world-readable bits.
- **EST audit lines use the trusted-proxy-aware client IP** instead of the raw socket address.

### Added
- `utils/trusted_proxy.py` — shared `is_request_from_trusted_proxy()` / `client_ip()` / `reject_untrusted_proxy_headers()` helpers used by EST, SCEP, mTLS login and audit.
- `utils/ssrf_protection.py` — single source of truth for `validate_url_not_cloud_metadata` and `validate_host_not_cloud_metadata`, used by webhooks, SSO, ACME proxy, OPNsense import.
- `utils/safe_commit.py`, `utils/require_json_body`, `utils/parse_request_pagination`, `utils/safe_call`, `utils/audit_event` — small composable helpers applied across `api/v2/*` to remove boilerplate and silence intermittent rollback bugs.
- `useCRUDPage` frontend hook covering 4 list/create/edit pages.

### Changed
- **Massive backend modularisation.** `system.py` (1556 l), `certificates.py` (2220 l), `cas.py` (1245 l), `ssh_cas.py` (1607 l), `database_admin` (817 l), `discovery_service`, `pdf_generator`, `scep_service` (981 l), `acme_service` (1456 l → 7 mixins ≤350 l), `trust_store` (1487 l), `ca_service` (788 l), `restore_mixin`, `notification_service`, `audit_service`, `crl_service`, `ssh_cert_service`, `msca_service`, `account.py`, `acme.py`, `tools.py`, `acme_client.py`, `users.py`, `settings.py`, `opnsense_import` and `models/__init__.py` were split into focused submodules. Behaviour is unchanged; module size, test isolation and review surface improve.
- **Frontend modularisation.** `CAsPage`, `CertificatesPage`, `DiscoveryPage`, `ACMEPage`, `SettingsPage` and `SsoProviderForm` split into per-section sub-components under `pages/<feature>/`.
- All `api/v2/*` `db.session.commit()` calls now go through `safe_commit()` — consistent rollback + error logging on every write path.

### Fixed
- **PKCS12/PFX export now honours the `include_chain` flag** (#100). Previously the CA chain was always included, regardless of the request.
- **Dashboard chart cards no longer overflow the grid** and System Health gained an internal scrollbar (#99).
- iOS/macOS SCEP enrollment regressions (#102).

### Internal
- ~20 test files de-duplicated against `conftest.py`; pre-commit i18n + 461 frontend + 1613 backend tests gate every commit.
- RC validated end-to-end on Debian (`pve:8445`), Fedora (`fedor:8443`) and Docker (`pve:8444`): smoke API 8/8 and Playwright use-cases 10/10 on all three targets.

## [2.141] - 2026-04-29

### Fixed
- **Admin lockout prevented on database backend switch** (#96). Switching the database backend (SQLite ↔ PostgreSQL) no longer locks the admin out. Boolean and JSON columns are now coerced correctly when migrating rows from SQLite to PostgreSQL, the migration runs per-table in its own transaction so a single bad row no longer aborts the whole switch, and the active admin session survives the cutover.
- **PostgreSQL backups via `pg_dump`.** The Docker image now ships `postgresql-client`, so PostgreSQL-backed instances can produce native `pg_dump` backups during backend migrations and scheduled backups.

### Changed
- **In-app help covers v2.128–v2.140 features** in English plus all 8 translated languages (fr, de, es, it, ja, pt, uk, zh).
- **README features and roadmap refreshed** for v2.128 → v2.140.

### Internal
- CI: backend test collection no longer fails on missing `SECRET_KEY` / `JWT_SECRET_KEY` — workflow now exports test-mode env vars before pytest runs.

## [2.140] - 2026-04-27

### Fixed
- **Certificate SAN database columns now derived from the final SAN list** (#94). When a CN is auto-promoted to an `rfc822Name` SAN at issuance, the `san_email` / `san_dns` / `san_ip` / `san_uri` columns are now written from the canonical SAN list instead of the raw form payload, so DB queries match the X.509 extension. Migration `027_backfill_san_email` re-parses existing certificate PEMs and backfills any rows that were out of sync (idempotent on SQLite and PostgreSQL). Thanks @Hemsby.
- **Certificate and CA files written to disk on creation** (#95). Added SQLAlchemy `after_insert` listeners on the `Certificate` and `CA` models that immediately materialize `.crt` / `.key` files under `data/certs/` and `data/cas/` for every creation path (UI, CSR signing, ACME, SCEP, import). The startup file-regeneration scan is kept as a safety net. File-write errors are logged but never abort the database transaction. Thanks @Hemsby.

## [2.139] - 2026-04-27

### Added
- **ACME External Account Binding (EAB) — RFC 8555 §7.3.4.** Full EAB credentials manager (backend models, API, UI under ACME → EAB Credentials). Operators can issue, list, rotate and revoke `kid` / `hmac` pairs; clients (cert-manager, certbot, acme.sh) bind their account on `newAccount` via JWS over the MAC key. Brings UCM in line with public ACME CAs (Let's Encrypt EAB, ZeroSSL, Google Trust Services).
- **ACME custom DNS resolvers for DNS-01 validation.** Per-account override of system resolvers when validating `_acme-challenge` TXT records. Useful for split-horizon DNS, internal authoritatives, or when public resolvers cache stale records during automated renewals.
- **ACME on internal / private IPs — gated by `acme.allow_private_ips` SystemConfig (default `true`).** HTTP-01 and TLS-ALPN-01 validation now works out of the box for RFC1918, loopback, `.lan` / `.local` / `.corp` targets — UCM's primary deployment model. Cloud metadata IPs (`169.254.169.254`) remain blocked unconditionally.
- **Kubernetes & cert-manager integration.** Reference manifests under `examples/kubernetes/cert-manager/` (HTTP-01 ClusterIssuer, DNS-01 ClusterIssuer with EAB, sample Certificate, EAB Secret template, README). Full integration guide on the wiki and on https://ucm.tools/docs.

### Changed
- **ACME audit & RBAC hardening.** Challenge state transitions now produce audit records on terminal states (`valid` / `invalid`) instead of every poll, eliminating audit log noise. `account.key_change` (RFC 8555 §7.3.5) is audited. `delete:acme` permission added to the `operator` role to match `write:acme`.
- **ACME backup/restore parity.** `acme_eab_credentials` is now exported and restored alongside `acme_accounts`; full account fields (contact, status, terms-of-service, external-account-binding metadata) are now round-tripped end-to-end.

### Fixed
- `backend/services/ssh_cas.py` — converted f-strings containing escape sequences to raw f-strings to silence Python `SyntaxWarning: invalid escape sequence` on 3.12+.

## [2.138] - 2026-04-25

### Fixed
- **CAs page silently dropped CAs beyond the first 20 (#89)** — `GET /api/v2/cas` defaulted to `per_page=20` even when no pagination parameters were supplied, so a fresh import of 24 CAs only displayed 20 in `Certificate Authorities`. The endpoint now returns the full set when no pagination is requested, and continues to honour `page` / `per_page` when they are explicitly provided.
- **API key creation UX & no-expiration support (#90)** — three regressions in `Account → API Keys`:
  - Newly issued keys are now shown in a dedicated modal with the full key in a `<code>` block, an explicit copy button, and a warning that the key won't be shown again. The previous toast disappeared too quickly and its copy button copied the literal string `undefined`.
  - The list view's per-key "copy" affordance now renders the real key prefix (e.g. `ucm_ak_AbC1`) instead of `undefined…`. Backed by a new `key_prefix` column persisted at creation time. Migration `026_add_api_key_prefix` adds the column on SQLite and PostgreSQL; legacy keys without a stored prefix render an "unavailable (legacy key)" placeholder.
  - Leaving the expiration field empty now creates a key that **never expires**, matching the field's helper text. The backend distinguishes "field absent" (keeps the historical 365-day default for API/CLI compatibility) from explicit `null` / `0` / `""` (no expiration). Validation rejects negative or non-integer values with HTTP 400.

## [2.137] - 2026-04-24

### Fixed
- **Datetime serialisation now consistently UTC across the API (#87)** — every `datetime.isoformat()` returned by the backend now carries an explicit `Z` suffix via the new `utc_isoformat()` helper. Frontend components (audit log viewer, dashboards, certificate detail) consistently render in the user's local timezone without ambiguity. Backend-wide sweep: 84 auto-fixed call sites + 9 manual fixes; full backend test suite (1558 tests) green.
- **Windows SSH Host/User CA setup script — clearer diagnostics on `Add-WindowsCapability` failure (#75).** When OpenSSH Server install fails on a domain-joined / WSUS-managed machine (typical errors `0x8024500c WU_E_PT_WMT_MISSING`, `0x800f0954`, WU connectivity codes), the script now prints a labelled diagnostic block: classifies the error, reports the detected `UseWUServer` / `WUServer` group-policy values, and lists three policy-compliant remediation paths (WSUS approval / FoD-from-WU policy / offline FoD ISO / manual install via Optional Features). The script never modifies WSUS or update policy itself — it explains the problem so the Windows / AD team can fix it.

## [2.136] - 2026-04-24

### Fixed
- **Smart Import duplicate detection (#85)** — duplicate detection across `Smart Import`, `Auto-Renewal`, and mTLS enrollment previously matched only on `serial_number`. Per RFC 5280, serials are only unique per-issuer, so two unrelated certs from different CAs that happened to share a serial were flagged as duplicates (or worse, the wrong cert was returned).
  - New helper `find_existing_cert_by_identity()` uses an indexed `(serial_number, issuer DN)` pre-filter (RFC 5280) and confirms with the **SHA-256 fingerprint of the DER bytes** — globally unique, immune to PEM reformatting, 0% false positives.
  - Applied to: `services/smart_import/validator._check_duplicate_cert()`, `services/smart_import/importer` (CA + leaf cert paths), `api/v2/users` mTLS import, `api/v2/mtls` mTLS enrollment.
  - Auto-renewal lookup now also scopes by `caref` to disambiguate identical serials issued by different CAs.
## [2.135] - 2026-04-23

### Fixed
- **Database Stats panel on PostgreSQL (#83)** — `Settings → Database` previously showed `-` for size and `Never` for `Last Optimized` on PostgreSQL deployments, and the panel never refreshed after `Optimize` / `Integrity Check`.
  - `get_db_stats()` now queries `pg_database_size(current_database())` on PostgreSQL (was using `os.path.getsize` on the SQLite file path → always `0` → frontend rendered `-`).
  - `Last Optimized` and `Last Integrity Check` timestamps are persisted via `SystemConfig` (`db_last_optimized`, `db_last_integrity_check`) and surfaced from `get_db_stats()` (was hardcoded `Never` with a TODO).
  - `SettingsPage` now re-runs `loadDbStats()` after `Optimize` and `Integrity Check` succeed.
- **Certificate Activity chart on PostgreSQL (#84)** — the dashboard chart always rendered all-zero bars on PostgreSQL.
  - Replaced SQLite-only boolean comparisons (`revoked = 0`, `is_active = 1`, `ocsp_enabled = 1`, `cdp_enabled = 1`, `active = 1`) with `IS NOT TRUE` / `= true`, which work on both SQLite and PostgreSQL.
  - Replaced SQLite-only `datetime('now', '+30 days')` in the auto-renewal status query with Python-computed bounds passed as parameters.
  - Without these fixes, the shared `try` block in `get_certificate_trend()` raised `operator does not exist: boolean = integer` on PostgreSQL and the `except` handler returned an empty trend for all three series.

## [2.134] - 2026-04-23

### Added
- **SMTP OAuth2 (XOAUTH2) for Gmail, Outlook.com & Microsoft 365 (#67)** — modern OAuth2 authentication for outbound mail, replacing legacy app-password flows that Microsoft and Google are deprecating.
  - Three provider presets (Gmail / Outlook.com / Microsoft 365) auto-fill SMTP host, port, scopes and authorization endpoints. A "Custom OAuth2" option remains for power users who need to register their own Entra/Workspace app.
  - Outlook.com personal accounts use a simplified flow that does not require tenant ID / client secret — the user just authorizes UCM with their Microsoft account.
  - Microsoft 365 (Entra) flow keeps the full tenant-id / client-id / client-secret form for org admins.
  - Per-provider helpers display the exact redirect URI to register, and the UI surfaces clear guidance when a refresh token is missing or unverified.
  - Tokens are stored encrypted; refresh is automatic on send.
- **Friendlier Windows SSH CA setup (#75)** — the PowerShell script generated by `/ssh/setup` no longer closes the prompt before the user can read the output, and ships with a self-elevating one-liner that downloads the script, opens an elevated `-NoExit` PowerShell, and bypasses `ExecutionPolicy` for that single run. Works around hosts where `.ps1` files are blocked by policy.

### Fixed
- **Database maintenance & integrity check on PostgreSQL (#82)** — `Optimize Database` and `Check Integrity` previously assumed SQLite and failed on PostgreSQL deployments.
  - `optimize_db()` now branches on the configured backend: SQLite runs `VACUUM` + `ANALYZE` via the standard session, PostgreSQL runs `VACUUM ANALYZE` on a dedicated `AUTOCOMMIT` connection (PG forbids VACUUM inside a transaction).
  - `check_integrity()` runs `PRAGMA integrity_check` / `foreign_key_check` on SQLite, and a connectivity + `information_schema.tables` probe on PostgreSQL.
  - Frontend `handleIntegrityCheck` was reading the response payload at the wrong nesting level, so the success toast never fired even on SQLite — now reads `response.data.passed` consistently with the rest of the API surface.
  - Both endpoints continue to use the standard `success_response` envelope.

## [2.133] - 2026-04-23

### Fixed
- **SSO Default Role overrides UCM-managed roles on every login (#81)** — until v2.132, `_resolve_role` was called inside `auto_update_users` for existing users and always fell back to `default_role` when no `role_mapping` matched. The result: any role change made in the UCM UI (e.g. promoting a user to `admin`) was silently reverted to the provider's `default_role` on the next SSO login. Two semantically separate concerns — userinfo sync (email/full name) and role sync — were also conflated under a single toggle.
  - `auto_update_users` now controls **userinfo only** (email, full name) and never touches the role.
  - `default_role` is now strictly a **creation-time** value.
  - Role re-sync at login is opt-in via a new `sync_role_on_login` flag (default `false`). When enabled, the role is updated only if `role_mapping` resolves the user's external groups to a UCM role; if no mapping matches, the stored role is preserved (no `default_role` fallback for existing users).
  - New backend helper `_resolve_role_from_mapping()` returns `None` when no mapping match is found, making the existing-user code path explicit.
  - DB migration `023_sso_sync_role_on_login` adds the new column to `pro_sso_providers` (SQLite + PostgreSQL).
  - SSO settings UI gains a "Sync role from SSO on each login" toggle on LDAP, OAuth2 and SAML provider forms, with explanatory help text.
  - Help content updated (in-app help + 9 i18n locales).
  - Backend tests added covering the four behaviours: existing user role preserved, mapped sync, no-match no-op, userinfo without role, creation uses `default_role`.

### Added
- **User authentication source tracking** — every user record now exposes its origin (`local` / `ldap` / `oauth2` / `saml`) plus the originating SSO provider when applicable. New `auth_source` and `sso_provider_id` columns on the `users` table, populated automatically when SSO provisions an account, and backfilled for existing SSO users by migration `024_user_auth_source` (SQLite + PostgreSQL) and an in-place fallback in `_get_or_create_sso_user`. The Users & Groups page gains a colour-coded **Source** column showing both the auth method and the provider name (e.g. `LDAP · Corporate AD`).
- **Wiki: dedicated SSO-Authentication page** covering LDAP / OAuth2 / SAML setup, role mapping, `sync_role_on_login`, `auth_source` tracking, and audit events.

## [2.132] - 2026-04-23

### Fixed
- **HSM provider dropdown empty in Create CA wizard (#80)** — `CAsPage` filtered HSM providers on `is_active && is_connected`, fields that don't exist on the `/api/v2/hsm/providers` response. The dropdown was therefore always empty, displaying "No connected HSM provider" even when an HSM was correctly configured and successfully tested. Now uses the actual `enabled` field returned by the backend (computed as `status === 'connected'`). Test fixture in `CertificatesForms.test.jsx` updated to match the real API contract.

## [2.131] - 2026-04-22

### Fixed
- **PostgreSQL backend on DEB/RPM (#78)** — `psycopg2-binary` is now declared in `backend/requirements.txt` so the runtime install pulls the driver automatically. `Test connection` and `Switch to PostgreSQL` no longer fail with `No module named 'psycopg2'` on a fresh DEB/RPM install.
- **SSO callback crash on role auto-update (#79)** — the audit log call after a role change in `api/v2/sso.py` used keyword arguments not accepted by `AuditService.log_action()` (`status='success'`) and passed the username as a positional `resource_type`. Rewritten with the correct kwargs (`action='role_change'`, `resource_type='user'`, `resource_name=<username>`, `username=<username>`, `success=True`). SSO logins that change a user's role no longer raise `TypeError`.
- **PostgreSQL URL examples harmonized** — in-app help, guides and admin docs now show `postgresql://user:pass@host:5432/ucm` (consistent with the UI placeholder) instead of mixing in `postgresql+psycopg2://`. Both forms remain accepted by the backend validator.

### Also in this release (carried over from cancelled v2.131-rc)
- **HSM warning is now provider-aware** — the "SoftHSM not detected" banner only shows when SoftHSM is actually the configured provider. Users running OpenBao or a vendor PKCS#11 module no longer see a misleading warning.

## [2.130] - 2026-04-22

### Added
- **HSM-backed Certificate Authorities (#77.3)** — the CA's private signing key can now be generated or stored inside an HSM and never leaves it. The Create CA wizard exposes a **Key Storage** toggle (Local / HSM); in HSM mode you can generate a new key in the HSM (RSA-2048/3072/4096, EC-P256/P384/P521) or pick an existing unused signing key. All certificate issuance, CRL generation and OCSP responses for the CA are signed by the HSM. PKCS#12, JKS and raw-key export endpoints return HTTP 409 for HSM-backed CAs. CA list and detail views show an "HSM" badge. In-app help and wiki updated in all 9 UI languages.

### Security
- **`python-dotenv` upgraded to 1.2.2** to pick up the latest CVE patches.

### Notes
- HSM-backed CAs are backed by the existing HSM provider plumbing (PKCS#11, AWS CloudHSM, Azure Key Vault, GCP KMS, OpenBao/Vault Transit). Only OpenBao is exercised in CI; the other providers share the same code path but are not yet end-to-end tested.
- In-place migration of existing local CAs to HSM and HSM key rotation for existing HSM CAs are intentionally out of scope and tracked as separate follow-up items.

## [2.129] - 2026-04-21

### Security
- **ACME client and proxy now offer user-controlled SSL verification** — both the ACME client (upstream CA directory) and the ACME proxy (target ACME server) expose `verify_ssl` / `proxy_verify_ssl` toggles persisted via `/api/v2/acme/client/settings`. Default is **on**; the UI shows a warning banner when disabled. The proxy "Test connection" endpoint now uses the persisted flag (no per-request override) and rejects cloud metadata IPs and loopback targets.
- **Outbound HTTP sessions now verify TLS by default** — `utils.safe_requests.create_session()` defaults to `verify_ssl=True`. Callers must opt out explicitly when targeting an internal endpoint with a self-signed certificate.
- **CSRF exemptions narrowed for SSO and mTLS** — previously any `/api/v2/sso/*` or `/api/v2/mtls/*` route was CSRF-exempt. Exemptions are now restricted to the specific public callback/handshake subpaths; admin-write endpoints under those prefixes are now CSRF-protected.
- **WebSocket admin endpoints require `admin:system` permission** — `/api/v2/websocket/clients` and `/api/v2/websocket/broadcast` now require admin scope instead of any authenticated session.
- **Forgot-password endpoint is now rate-limited** to mitigate enumeration and brute-force.
- **API keys linked to deactivated users are now rejected** — `auth/unified.py` checks the `is_active` flag in addition to the key's own validity.

### Fixed
- **Service no longer starts silently when database migrations fail** — `run_all_migrations()` failures now block startup with a clear error instead of leaving the app half-initialized.
- **Database migration runner uses `DATABASE_URL` as single source of truth** — eliminates the SQLite path mismatch that could arise when `DATABASE_URL` and `DATABASE_PATH` disagreed.
- **Database migration target check is now fail-closed** — if the emptiness check on the target database raises, migration aborts instead of continuing. The `_migrations` bookkeeping table DDL is now PostgreSQL-compatible (`SERIAL`/`IDENTITY` instead of SQLite `INTEGER PRIMARY KEY`).
- **Audit logs for background tasks no longer appear as `anonymous`** — actions performed without a Flask request context (CRL auto-regeneration, ACME auto-approve, scheduler tasks, startup work) are now correctly labelled `system`, `scheduler`, or `acme`. `anonymous` is reserved for genuinely unauthenticated HTTP requests.

## [2.128.1] - 2026-04-21

### Fixed
- **Service fails to start after upgrading to v2.128 on SQLite installs** — the new v2.128 database migrations did not apply on upgrade and the service stayed in a failed state. Fresh installs were not affected.

## [2.128] - 2026-04-21

### Added
- **Custom Extended Key Usage (EKU) OIDs when issuing certificates and signing CSRs (RFC 5280 §4.2.1.12)** — the *Issue Certificate* form and the *Sign CSR* modal now expose an "Extra EKUs" multi-select that combines a dropdown of well-known EKUs (Microsoft RDP `1.3.6.1.4.1.311.54.1.2`, smartcard logon `1.3.6.1.4.1.311.20.2.2`, document signing, IPsec, Kerberos PKINIT, etc. — 18 catalog entries via the new `GET /api/v2/eku/known` endpoint) with a free-text input that accepts any well-formed dotted OID. The cert_type's default EKUs (e.g. `serverAuth` for server certs) remain locked-in as chips and the extras are merged on top — never replaced. Backend validation (`utils/eku_validation.py`) enforces a 16-OID cap, the `^[0-2](?:\.(?:0|[1-9]\d*)){1,15}$` OID regex, and explicitly rejects `anyExtendedKeyUsage` (2.5.29.37.0). For CSR signing, if the CSR already carries an EKU extension it is rebuilt with the merged set. Fixes [#76](https://github.com/NeySlim/ultimate-ca-manager/issues/76).
- **Active filter state persisted across reloads** — applying a filter on Certificates, CAs, Audit Logs, Templates, Policies, TrustStore, HSM, RBAC, SSH Certificates, SSH CAs, Users/Groups, or User Certificates now saves the live selection to `localStorage` (one key per filter, e.g. `ucm-filter-certs-status`). Reloading the page or navigating away and back instantly restores the same filter, with no flash of unfiltered data — the new `usePersistedState` hook reads the value synchronously in the React state initializer. Clearing a filter through the UI also removes the corresponding `localStorage` entry, so empty state stays clean. Works alongside the existing named filter presets (which keep using a separate `…-presets` key). Fixes [#57](https://github.com/NeySlim/ultimate-ca-manager/issues/57).
- **Windows quick-install script for SSH CA trust** — the SSH CA setup script endpoint now accepts a `?platform=windows` query parameter and returns a PowerShell (`.ps1`) script that configures the Windows OpenSSH Server to trust the CA (writes the public key to `%ProgramData%\ssh`, locks down ACLs, adds `TrustedUserCAKeys`/`HostCertificate` directives to `sshd_config`, validates with `sshd -T`, and restarts the `sshd` service). Supports both user and host CAs, includes a `-DryRun` switch, and works on the public unauthenticated `/ssh/setup/<refid>` endpoint too. The SSH CA detail panel now shows two download buttons (Linux/macOS `.sh` + Windows `.ps1`) and two Quick Install one-liners (`curl … | bash` for Linux/macOS, `iwr … | iex` for Windows). Fixes [#75](https://github.com/NeySlim/ultimate-ca-manager/issues/75).
- **User UI preferences persisted server-side** — language, theme family, and theme mode are now saved per-user in the database (`users.preferences` JSON column) instead of only in the browser's `localStorage`. New endpoints `GET/PUT /api/v2/account/preferences` (whitelist-validated, admin or self) store the preferences, and `/api/v2/auth/verify` returns them so they are applied on every page load. Logging in from a fresh browser, a different device, or after clearing site data now restores the user's chosen language and theme instead of falling back to the browser locale and default theme. Migration `022` adds the column on both SQLite and PostgreSQL. Fixes [#73](https://github.com/NeySlim/ultimate-ca-manager/issues/73).
- **ACME proxy orders linked to local accounts** — proxy order rows now record which local `AcmeAccount` initiated them (FK `account_id` resolved from the client JWK thumbprint). The proxy order list now displays the account email/short id beside each order, and the account detail "Orders" tab now merges local + proxy orders with a "Proxy" badge so operators can see all activity per account in one place. Migration `021` backfills `account_id` for existing proxy orders by joining on `acme_accounts.jwk_thumbprint`. Fixes [#71](https://github.com/NeySlim/ultimate-ca-manager/issues/71).

### Fixed
- **ACME renewal storm with Let's Encrypt** — `AcmeClientOrder.expires_at` was being set from the ACME order resource's `expires` field (RFC 8555 §7.1.3, ~7 days for LE) instead of the issued certificate's `notAfter` (typically 90 days). The renewal scheduler then re-issued the same certificate every tick, hitting the LE production rate limits. `finalize_order` now stores the leaf certificate's `notAfter`, and migration `020` backfills `expires_at` for all already-issued orders. Fixes [#74](https://github.com/NeySlim/ultimate-ca-manager/issues/74).

### Changed
- **No more compilation toolchain required at install time** — `gcc` and `python3-dev` (DEB) / `python3-devel` (RPM) have been removed from package dependencies. Previously they were needed to build the `twofish` C extension pulled in transitively by `pyjks` (Java KeyStore export). Investigation confirmed `twofish` is only used by pyjks for the BKS UBER keystore format, which UCM never produces — UCM only exports JKS. `pyjks` is now installed via `pip install --no-deps pyjks==20.0.0` in the postinst scripts (with its actual runtime deps `javaobj-py3` + `pycryptodomex` listed in `requirements.txt`), keeping the install pure-wheel and ~30 MB lighter on RPM systems.

## [2.127] - 2026-04-21

### Added
- **PostgreSQL 13+ as a native database backend (alongside SQLite)** — UCM now supports PostgreSQL via the `DATABASE_URL` environment variable (e.g. `postgresql://user:pass@host:5432/ucm`). When unset, UCM falls back to the bundled SQLite at `UCM_DATA_DIR/ucm.db`. The schema is created automatically on first start; no manual SQL required. The `psycopg2-binary` driver is bundled in DEB/RPM/Docker.
- **Settings → Database** — new UI section showing the active backend (sqlite/postgresql), database size, table count, and migration version. Operators can:
  - **Test** an arbitrary `DATABASE_URL` before switching
  - **Switch** the backend (persists to `/etc/ucm/ucm.env` on DEB/RPM and triggers restart)
  - **Migrate data** between backends in either direction (SQLite → PostgreSQL or PostgreSQL → SQLite)
- **Bidirectional database migration** (`/api/v2/database/migrate`) — backs up the source first, creates the schema on the target via SQLAlchemy, disables FK checks during bulk load (PostgreSQL `session_replication_role`, SQLite `PRAGMA foreign_keys`), intersects source/target columns to handle legacy schema drift, normalizes `memoryview`/JSON values across drivers, and resets PostgreSQL sequences after load. Verified end-to-end with 47 tables / 3800+ rows in both directions.
- **Migration safety checks** — `Test connection` rejects PostgreSQL servers older than 13 (UCM minimum supported version) with a clear message. `Migrate` performs a pre-flight check on the target and refuses (HTTP 409) if `users`, `cas`, or `certificates` already contain rows, with a cleanup hint (`DROP SCHEMA public CASCADE; CREATE SCHEMA public;` for PG, file delete for SQLite). On mid-way failure, the source is left untouched and the error message points the admin to the source backup so recovery is straightforward.
- **Documentation** — `docs/ADMIN_GUIDE.md` and `docs/installation/docker.md` updated with PostgreSQL setup, `DATABASE_URL` reference, and migration workflow. In-app **Help** (Quick Help + Guide) updated for the Database section in all 9 languages.

### Notes
- Docker installs cannot persist `/etc/ucm/ucm.env` from inside the container. After running **Migrate** on Docker, the API returns the target URL and operators must set `DATABASE_URL` in their `docker-compose.yml` / `docker run -e` and restart the container manually.
- The migration runner's `_migrations` bookkeeping table is created on the target if missing (it is bootstrapped outside SQLAlchemy metadata).

## [2.126] - 2026-04-19

### Fixed
- **Local ACME refused HTTP-01 / TLS-ALPN-01 for internal domains (CRITICAL for on-prem use)** — The Phase 2 SSRF hardening unconditionally rejected RFC1918 / loopback / link-local / reserved targets in HTTP-01 and TLS-ALPN-01 validators. UCM's local ACME exists precisely to issue certificates for internal infrastructure (`.lan`, `.local`, `.corp`), which by definition resolves to private addresses. The check is now gated by a new `acme.allow_private_ips` setting (default `true`). Operators issuing only for public domains can flip it to `false`.
- **OPNsense import refused LAN hosts** — `import_opnsense.py` rejected any RFC1918 OPNsense host. OPNsense is a LAN firewall by design. Replaced the broad SSRF check with the narrow guard (`validate_url_not_cloud_metadata`) that only blocks cloud metadata services and loopback.
- **Webhooks refused internal targets** — Creating or testing a webhook pointing at an internal Slack-compatible / Mattermost / Teams self-hosted / Jenkins / Gitea / Home Assistant / n8n endpoint was rejected. UCM is on-prem; internal automation is the primary use case. Both `api/v2/webhooks.py` and the legacy `api/v2/settings.py` webhook routes now use the narrow guard.
- **Discovery scans could not include `127.0.0.1`** — Loopback was unconditionally blocked, preventing operators from discovering certificates of services bound to localhost on the UCM host itself. Loopback is now allowed; only link-local / multicast / reserved remain blocked.

### Security
- The narrow SSRF guard (`validate_url_not_cloud_metadata`) still blocks the highest-impact targets in the on-prem context: cloud instance metadata services (AWS `169.254.169.254`, GCP `metadata.google.internal`, Azure, Alibaba) and loopback. These remain rejected for webhook/OPNsense/SSO/ACME-proxy outbound traffic.

## [2.125] - 2026-04-17

### Security
- **Backup format v2 (encrypted container, magic header, Argon2id KDF)** — The backup system now emits a versioned binary container with `UCMB` magic bytes, explicit format version byte, feature flags (gzip on by default), and KDF identifier. Key derivation uses Argon2id (`time_cost=3`, `memory_cost=64 MiB`, `parallelism=4`, 32‑byte output) instead of PBKDF2‑HMAC‑SHA256 at 100k iterations, providing memory‑hard resistance against GPU/ASIC brute force. Ciphertext is AES‑256‑GCM with a 12‑byte random nonce, and the magic prefix is bound as additional authenticated data so a tampered header fails decryption. If Argon2id is unavailable at runtime, v2 falls back to PBKDF2‑HMAC‑SHA256 at 600 000 iterations (6× previous). v1 backups remain fully restorable for backward compatibility; restore auto‑detects the format.
- **Backup passwords must be ≥ 12 characters** — Enforced server‑side via `_validate_password`.

### Fixed
- **Backup silently dropped certificate revocation state (CRITICAL)** — The previous `_export_certificates` did not include `revoked`, `revoked_at`, `revoke_reason`, or `archived`. Restoring from a backup silently resurrected revoked certificates as valid, a significant security issue for any CA that had issued revocations. These fields are now exported and restored.
- **Backup excluded 15+ model types** — Previously only 20 categories were exported; SSH CAs, SSH certificates, Microsoft ADCS connections and requests, scan profiles / runs / discovered certificates, certificate approval requests, HSM keys, ACME client orders (including proxy state), SCEP requests, and audit logs were all missing. All are now exported in v2 backups. Restore is implemented for SSH CAs (with private‑key re‑encryption), SSH certificates, Microsoft CAs, scan profiles, HSM keys, approval requests, and ACME client orders.
- **Backup `.ucmbkp` extension rejected by upload validator** — `BACKUP_EXTENSIONS` only allowed `.zip` / `.enc`, breaking restore via the UI for the format the system itself produced. `.ucmbkp` is now accepted.

### Changed
- **Every export call is now wrapped in a `_safe()` helper** — Missing tables (e.g. optional feature models on a minimal install) or transient failures log a warning and return `[]` instead of aborting the entire backup.
- **SSH CA private keys are re‑encrypted with the master key on export and decrypted + re‑encrypted on restore**, matching the pattern used for certificate private keys.
- **Backups are gzip‑compressed before encryption**, reducing container size ~5× on typical installs.

### Testing
- Round‑trip restore verified end‑to‑end via `/api/v2/system/backup/restore`: 60 certs, 9 CAs, 5 policies, 3 SSO providers, 7 custom roles, 6 API keys, 52 trusted CAs restored from live v2 backup (329 KB container, magic `UCMB\x02\x01\x02`).
- Backend: 1483 pass.

### Fixed (ACME)
- **ACME proxy badNonce retry (#70)** — The proxy did not implement RFC 8555 §6.5 nonce retry. Lenient upstream CAs (Let's Encrypt staging/production) accepted stale nonces silently, but strict implementations (Pebble, HARICA, and any CA with strict anti-replay) rejected them with `urn:ietf:params:acme:error:badNonce`, leaving orders stuck pending while authz fetches returned 400. The proxy now detects `badNonce`, extracts the fresh nonce from the error response's `Replay-Nonce` header, and retries the signed request once. Verified end-to-end with Pebble + EAB (custom upstream mode).

### Changed (ACME)
- **ACME domain `auto_approve` is now functional (#69)** — Previously the toggle on ACME Domains and Local Domains was stored in the database and exposed in the UI but never consulted by the ACME service, so every order still required full challenge validation. When `auto_approve=True` is now set on a matching domain entry (exact match or any parent domain, wildcard prefixes stripped), UCM skips HTTP-01/DNS-01/TLS-ALPN-01 validation: authorizations are created directly in the `valid` state, orders move straight to `ready`, and an `acme_auto_approve` audit event is logged. This applies to both order-driven authorizations and RFC 8555 pre-authorizations (`newAuthz`). Only affects local UCM issuance, not the ACME proxy.

### Security / Migration
- **`auto_approve` defaults flipped to `False`** — Historically the column defaulted to `True`, which had no effect because the flag was unused. Now that the flag is honored, existing rows with `auto_approve=True` would silently start skipping challenge validation on upgrade. Migration `019_acme_auto_approve_safe_default` resets every existing `AcmeDomain` and `AcmeLocalDomain` row to `False`. Model defaults and API create defaults are also `False`. Administrators must explicitly opt in per domain after upgrading. A UI warning banner is shown when the toggle is enabled.

### Roadmap
- **PostgreSQL support** — Abstract the data layer so deployments can back UCM with PostgreSQL instead of SQLite, for multi-instance HA and larger certificate inventories
- **Environment Variables** — Sync Docker env vars (SMTP, HSM, etc.) to database at startup; track `managed_by` source; mark UI fields as read-only when sourced from environment
- **Policy Enforcement on Protocols** — Apply certificate policies to ACME, SCEP, and EST protocol handlers (currently only enforced on REST API); add CA issuance restriction flags to prevent direct issuance from root/intermediate CAs

---

## [2.124] - 2026-04-17

### Fixed
- **ACME proxy — Let's Encrypt "contact email has invalid domain" (#68)** — The proxy registered its upstream LE account with a synthesized `admin@<FQDN>` address, ignoring the email configured by the admin via `POST /api/v2/acme/client/proxy/register`. On typical installs the FQDN resolves to a private TLD (`.lan`, `.local`, `.internal`), which LE rejects against its Public Suffix List, breaking every proxied order (win-acme, certbot, etc.). The proxy now reads `acme.proxy_email` as the contact address and no longer synthesizes internal addresses.
- **`register_proxy_account` was a no-op** — The endpoint only stored the email in config; actual upstream registration happened lazily on the first client order, using the wrong address. It now validates the email format, rejects non-public TLDs (`.local`, `.lan`, `.home`, `.internal`, `.corp`, `.test`, `.invalid`, `.localhost`) server-side, clears any stale `acme.proxy.account_url`, and triggers real registration against the upstream CA so EAB-required / unreachable-CA / forbidden-domain errors surface immediately. The response now includes the upstream account URL.
- **`unregister_proxy_account` left zombie credentials** — Removed `acme.proxy_email` but not the cached `acme.proxy.account_url`, so the next registration attempt reused a deactivated account. Unregister now cleans all proxy account state.
- **ACME proxy nonce / JWS hangs** — `_get_nonce()` and `_post_jws()` issued requests with no timeout and could hang indefinitely if the upstream was unresponsive. Explicit timeouts added (15 s / 30 s).
- **Wildcard domain lookup used `lstrip('*.')`** — `lstrip` strips characters, not a prefix, so `*abc.example.com` would incorrectly become `example.com`. Replaced with a proper `startswith('*.')` + slice.
- **Upstream response body leaked to clients** — `RuntimeError(f"...: {resp.text}")` in the proxy surfaced raw upstream bodies to end clients. Errors are now logged server-side with a truncated body; clients see only the upstream `detail` field or a generic message.

### Testing
- 5 new unit tests covering PSL validation (accept public, reject private TLDs), email format validation, and mocked upstream registration flow.
- Backend: 1476 pass (+5). Frontend: 450 pass.
- Functional verification on netsuit against LE staging: valid public email registers successfully, private-TLD emails rejected with HTTP 400, unregister fully cleans credentials.



---

## [2.123] - 2026-04-18

### Security (Phase 2 — unified SSRF + error hygiene)
- **ACME directory URL SSRF** — `PATCH /api/v2/acme/client/settings` now validates `directory_url` and `proxy_upstream_url` against cloud-metadata endpoints (AWS `169.254.169.254`, GCP `metadata.google.internal`, Alibaba `100.100.100.200`) and loopback addresses. RFC1918 private ranges remain allowed so internal ACME CAs keep working.
- **OAuth2 discovery SSRF** — `_test_oauth2_connection()` now guards the well-known endpoint URL before issuing the HEAD request, with the same narrow cloud-metadata + loopback policy.
- **SAML metadata SSRF consistency** — `fetch_idp_metadata()` replaced the literal-IP-only filter (trivially bypassed via hostnames) with a unified resolver-aware check. Internal IdPs on private networks remain fetchable; only cloud metadata + loopback are blocked.
- **Error message hygiene** — removed `str(e)` / stack-trace leaks in MSCA CSR submission, SSH CA KRL generation, webhook URL validation, and ACME DNS access testing. Exceptions are now logged server-side and clients receive generic messages.

### Fixed
- **Policy approval self-check bypassed (HIGH)** — `approve_request()` read `request.current_user` (which is always None; Flask's `request` has no such attribute), so the "creator cannot approve own request" guard never triggered. Now uses `g.current_user`.
- **Policy audit trail wrong actor** — `reject_request()` always logged `'system'` as the rejector for the same reason; now logs the real username.
- **Policy `created_by` always null** — `create_policy()` set `created_by = request.current_user` (always None). Now reads from `g.current_user`.

---

## [2.122] - 2026-04-17


### Security (Phase 1 — critical hotfixes)
- **SAML authentication bypass (CRITICAL)** — removed unsigned-XML fallback parser in `/api/v2/sso/saml/callback`. Any `process_response()` exception or validation error now hard-rejects with `saml_validation_failed` instead of trusting attributes from un-verified XML.
- **Webhook SSRF (CRITICAL)** — `POST /api/v2/settings/webhooks` and `POST /api/v2/settings/webhooks/:id/test` now validate destination URL via `validate_url_not_private()`, rejecting private/loopback/link-local/metadata IPs (the parallel `/api/v2/webhooks` endpoints were already protected; the legacy duplicate is now on par).
- **P12 password leak via URL (HIGH)** — `GET /api/v2/certificates/:id/export` and `GET /api/v2/user_certificates/:id/export` refuse `password=` query params and PKCS12/PFX/JKS formats. Password-bearing exports must use `POST` with a JSON body (matches what the UI already does) to keep secrets out of reverse-proxy / web-server access logs.
- **Brute-force protection activated (HIGH)** — `init_rate_limiter(app)` is now wired up in `create_app()`. Auth/login endpoints are rate-limited (default 30 rpm, configurable via `RATE_LIMIT_AUTH_RPM`). Previously the rate-limit module was fully implemented but never registered as middleware.
- **Rate limiter** — added `/.well-known/est/` to the protocol whitelist bucket (EST endpoints get the same permissive limits as ACME/SCEP instead of falling through to the default).

### Fixed
- **Auto-renewal crash (CRITICAL)** — `services/auto_renewal_service.py` referenced columns that do not exist on the `Certificate` model (`not_before`, `not_after`, `ca_id`, `status`, `superseded_by`). The 12-hour scheduler pass silently crashed on every run, so nothing was ever auto-renewed. Rewrote the query + renewal logic against the real schema (`caref`, `valid_from`, `valid_to`, `revoked`, `archived`, `source`), and old certificates are now marked `archived = true` when a successful renewal is issued.

---


## [2.121] - 2026-04-16

### Fixed (ACME code review — 7 bugs)
- **EAB validation** — fixed `SystemConfig.set()` call on non-existent method (EAB validation was always failing, blocking external account bindings)
- **Manual renewal endpoint** — `renew_certificate()` now returns `(bool, str)` tuple as caller expects (manual renewal via API no longer crashes)
- **ACME server base URL** — service instantiated per-request instead of cached globally, fixing stale base URLs behind reverse proxies or multi-hostname setups
- **key-change endpoint (RFC 8555 §7.3.5)** — properly decode and verify inner JWS signed with the new key (was unconditionally failing)
- **HTTP-01 / TLS-ALPN-01 SSRF protection** — reject challenge validations against domains resolving to private/loopback/link-local IPs
- **DNS-01 exact match** — TXT record validation uses exact equality over `rdata.strings` instead of substring match (prevents false positives)
- **Order/Authorization POST-as-GET** — enforce account ownership per RFC 8555 §7.4/§7.5 (reject cross-account reads with 403)

---

## [2.120] - 2026-04-16

### Fixed
- **ACME proxy directory resilience** — Proxy `/directory` endpoint no longer fails with 500 when the upstream ACME server is unreachable; account registration is now lazy (only when placing orders), with proper timeouts and detailed error messages (#66)
- **ACME auto-renewal crash** — Fixed `create_order() missing 1 required positional argument: 'email'` error in the renewal service; rewrote renewal to use current AcmeClientService API with proper email sourcing, challenge verification, and order finalization (#66)

---

## [2.119] - 2026-04-16

### Fixed
- **CSR excluded from certificates list** — Signed CSRs no longer appear in the certificates list, stats, or compliance endpoints; only records with an issued certificate are shown
- **SAN auto-generation from CN** — When signing a CSR that has no SAN extension, UCM now auto-adds the CN as a DNS SAN (and subject emailAddress as RFC822Name SAN), ensuring modern browser/TLS compatibility
- **MSCA UPN auto-fill improvement** — EOBO enrollee UPN now also tries the CSR subject emailAddress when SAN email is empty; UPN field is required when EOBO is enabled

---

## [2.118] - 2026-04-16

### Added
- **ACME proxy settings UX overhaul** — Unified mode selector (Let's Encrypt Staging / Production / Custom), inline account status indicator, connection test, and CA/account mismatch detection (#64)
- **Collapsible ACME sections** — Custom ACME Directory and Proxy EAB Credentials sections with chevron indicators and bordered containers for better discoverability (#64)

### Fixed
- **ACME proxy stale account recovery** — Auto-re-registers upstream account when CA returns "Account is not valid" (e.g., LE staging cleanup); applied to all 8 proxy operations (#65)
- **ACME proxy empty URL fallback** — Proxy now falls back to default upstream URL when stored URL is empty, preventing crashes after custom mode reset (#65)
- **ACME proxy custom mode credential clearing** — Switching to custom mode now properly clears stale upstream URL and credentials (#64)
- **ACME challenge initiation** — Moved challenge initiation to authorization phase for correct RFC 8555 flow (#63)

### Documentation
- Added OpenBao HSM and ACME proxy documentation

---

## [2.117] - 2026-04-15

### Added
- **OpenBao HSM provider** — Native Transit Secrets Engine integration for OpenBao/HashiCorp Vault; supports RSA, ECDSA, AES key types with full key lifecycle management (#60)
- **ACME proxy EAB support** — External Account Binding fields for upstream ACME proxy connections (#61)

### Fixed
- **ACME proxy authorization URL rewriting** — `get_order` and `finalize_order` now correctly proxy authorization URLs, preventing stateless clients from bypassing the proxy (#62)

---

## [2.116] - 2026-04-15

### Added
- **Multi-select filters with chips** — All page filters now support multi-select with visual chips across certificates, CAs, SSH, discovery, audit, users, operations, CSRs, reports, and policies pages (#58)
- **CA multi-select filters** — CA type and status filters on CAs page now support multi-select with proper filtering logic
- **Copy-to-clipboard** — Detail panels across pages now include clipboard copy buttons for key fields
- **Keyboard shortcut tooltips** — Toolbar buttons show keyboard shortcuts on hover
- **Table density toggle** — Configurable row density with persistent storage per page
- **Filter presets** — Tables support filter preset keys for quick filter switching
- **Accessibility** — Added aria-labels to all icon-only buttons across the frontend

### Fixed
- **CAs page status filter was dead code** — Filter dropdown was rendered but completely ignored in filtering logic; now properly filters Active/Expired CAs
- **Dashboard duplicate quick actions** — Quick action buttons were duplicated in header and below header; consolidated into single header bar with RBAC guards
- **SSH status display and stats** — Corrected status field reading and statistics computation on SSH certificates page
- **MultiSelectFilter prop mismatch** — Fixed prop names (`filterType` vs `type`) causing filters to silently fail in ResponsiveDataTable
- **ACME proxy async DNS setup** — `respond_challenge` refactored to use background thread for DNS propagation, preventing Traefik timeouts on slow DNS providers (PR #59, @C0DEbrained)

### Security
- **pytest bump 9.0.2 → 9.0.3** — Fixes CVE-2025-71176

---

## [2.115] - 2026-04-14

### Fixed
- **ACME settings: text inputs saved on every keystroke** — Directory URL, contact email, and EAB fields fired an API call on each keystroke, causing validation errors mid-typing (e.g., "h" rejected as non-HTTPS). Text inputs now save on blur instead (issue #56).

### Added
- **ACME proxy upstream URL** — New UI field and API endpoint to configure the upstream ACME directory URL for the Let's Encrypt proxy. Previously only configurable via database.
- **4 new backend tests** for proxy upstream URL PATCH/GET validation.

---

## [2.114] - 2026-04-14

### Fixed
- **ACME Proxy: Account not found after KID fix** — Proxy `new-account` returned a hardcoded static account ID that didn't exist in the database after the KID verification refactor (issue #55). Now creates real persistent `AcmeAccount` records with proper JWK storage and deduplication via thumbprint. Certbot and other ACME clients work correctly again with the proxy.

### Added
- **ACME proxy protocol tests** — 6 new regression tests covering account creation, deduplication, KID-based JWS verification, and wrong-key rejection to prevent future proxy breakage.

---

## [2.113] - 2026-04-13

### Fixed
- **ACME Private Network Support** — Removed SSRF filter that blocked ACME challenge validation on private networks (10.x, 172.16.x, 192.168.x), which is the primary self-hosted use case
- **CSR Intermediate CA Signing** — Signing a CSR as "Intermediate CA" now correctly creates a Certificate Authority record instead of leaving it as a regular certificate ([#54](https://github.com/NeySlim/ultimate-ca-manager/issues/54))

### Added
- **Configurable Lockout Settings** — Account lockout duration and max login attempts are now configurable from the Settings page instead of hardcoded constants; applies to password, LDAP, and 2FA authentication
- **Admin User Unlock** — New `POST /api/v2/users/{id}/unlock` endpoint allows administrators to unlock locked-out user accounts

---

## [2.112] - 2026-04-10

### Added
- **SSH Certificate Authority** — Full SSH CA support: create ED25519/RSA/ECDSA SSH CAs, sign host and user certificates with configurable validity and principals, manage and revoke SSH certificates; RBAC-enforced with 6 dedicated permissions; dashboard widget shows SSH certificate stats; curl-friendly setup script endpoint (`/api/v2/ssh/cas/:id/setup-script`) for one-command client trust configuration
- **SSH Import** — Import existing SSH CAs (public+private key) and SSH certificates with full validation; supports OpenSSH key formats
- **HTTPS Certificate Picker** — Settings HTTPS certificate selection now uses a searchable modal with pagination instead of a limited dropdown; supports filtering by name, subject, or issuer across all certificates

### Security
- **Session Fixation Prevention** — Added `session.clear()` before session assignment in OAuth2, SAML, LDAP, and mTLS login paths
- **Export Password Protection** — Certificate/CA export endpoints now accept POST with password in request body instead of GET with password in URL query string
- **EST Password Hashing** — EST authentication password stored with `generate_password_hash()` instead of plaintext; seamless migration for existing deployments
- **LDAP Settings Allowlist** — LDAP configuration endpoint restricted to known keys, preventing arbitrary SystemConfig injection
- **LIKE Injection Prevention** — Search wildcards (`%`, `_`) properly escaped in groups, users, templates, truststore, and user-certificates endpoints
- **Self-Approval Prevention** — Users cannot approve their own certificate requests
- **OPNsense Credentials** — Moved from persistent `localStorage` to session-scoped `sessionStorage`
- **RBAC Hardening** — Added audit logging and try/except to all RBAC and policy write operations; Discovery profile edit/delete buttons now gated by permissions

### Fixed
- **Dependency Update** — Bumped `cryptography` 46.0.6 → 46.0.7 (CVE-2026-39892)
- **SSH i18n** — Navigation menu items and help content translated in all 8 languages

---

## [2.111] - 2026-04-09

### Fixed
- **PKCS7/PKCS12 Decode Support** — Certificate decoder now handles DER/PEM PKCS7 bundles (.p7b/.p7c) and passwordless PKCS12 files in addition to standard PEM/DER certificates; returns chain info when multiple certs found in a bundle

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
