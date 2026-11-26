# UCM API v2 - Complete Reference

> **Base URL**: `https://your-server:8443/api/v2`  
> **Coverage**: `backend/tests/test_api_reference_routes.py` checks this file against the application's route table.  
> **Operation format**: each operation is written `METHOD /path` at the start of a line (`{id}` marks a path parameter).

---

## Table of Contents

1. [Authentication](#authentication)
2. [Account Management](#account-management)
3. [Certificate Authorities](#certificate-authorities)
4. [Certificates](#certificates)
5. [User Certificates (mTLS)](#user-certificates-mtls)
6. [Certificate Signing Requests](#certificate-signing-requests)
7. [Templates](#templates)
8. [Trust Store](#trust-store)
9. [ACME Server](#acme-server)
10. [SCEP](#scep)
11. [EST](#est)
12. [Time Stamping (TSA)](#time-stamping-tsa)
13. [Windows Enrollment Profiles](#windows-enrollment-profiles)
14. [Active Directory Connectors](#active-directory-connectors)
15. [Microsoft CA](#microsoft-ca)
16. [SSH Certificates](#ssh-certificates)
17. [Deployment](#deployment)
18. [Discovery](#discovery)
19. [Key Recovery](#key-recovery)
20. [CRL & OCSP](#crl--ocsp)
21. [AIA CA Issuers](#aia-ca-issuers)
22. [Users](#users)
23. [Roles & Permissions (RBAC)](#roles--permissions-rbac)
24. [Dashboard](#dashboard)
25. [Audit Logs](#audit-logs)
26. [Settings](#settings)
27. [System](#system)
28. [Import/Export](#importexport)
29. [Certificate Tools](#certificate-tools)
30. [Global Search](#global-search)
31. [User Groups](#user-groups)
32. [Smart Import](#smart-import)
33. [DNS Providers](#dns-providers)
34. [ACME Client (Let's Encrypt)](#acme-client-lets-encrypt)
35. [ACME Domains](#acme-domains)
36. [SSO (LDAP/OAuth2/SAML)](#sso-ldapoauth2saml)
37. [HSM](#hsm)
38. [WebAuthn](#webauthn)
39. [Webhooks](#webhooks)
40. [Certificate Policies & Approvals](#certificate-policies--approvals)
41. [Reports](#reports)
42. [WebSocket](#websocket)
43. [Health](#health)
44. [Protocol and Health Endpoints](#protocol-and-health-endpoints)
45. [HTTP Status Codes](#http-status-codes)
46. [Rate Limiting](#rate-limiting)
47. [Permissions](#permissions)
48. [Examples](#examples)

---

## Response Format

All API responses follow this structure:

```json
// Success
{
  "data": { ... },
  "message": "Optional success message",
  "meta": { "page": 1, "per_page": 50, "total": 100 }  // For paginated responses
}

// Error
{
  "error": true,
  "code": 400,
  "message": "Error description"
}
```

### Sorting

The lists whose section below names a `sort_by` key sort with `sort_by` (a key the list names) and `sort_order` (`asc` or `desc`; an empty value takes the list's default). Text is compared without regard to ASCII letter case, byte by byte otherwise, the same on SQLite and PostgreSQL; rows with no value in the sorted column come last in both directions; ties are broken by `id` in the same direction, so two pages never share a row. A key or direction the list does not know answers `400`, with the keys it accepts in `details.allowed_sort_by`:

```json
{ "status": 400, "detail": "Unknown sort_by 'size'; allowed: created_at, name", "details": { "allowed_sort_by": ["created_at", "name"] } }
```

The other paged lists keep a fixed order and ignore `sort_by`: `/api/v2/cas`, `/api/v2/cas/{id}/certificates`, `/api/v2/ssh/cas`, `/api/v2/acme/client/orders`, `/api/v2/account/activity`, `/api/v2/webhooks/{id}/deliveries`, `/api/v2/settings/backup/history`, `/api/v2/settings/notifications/logs` and `/api/v2/settings/audit-logs`. The archive list (`/api/v2/system/backups`) sorts by its own `sort` parameter (`created_desc` by default, `created_asc`, `size_desc`, `size_asc`, `name_asc`, `name_desc`), and an unknown value takes the default.

---

## Authentication

UCM supports multiple authentication methods: Password, WebAuthn (Hardware Keys), and mTLS (Client Certificates).

### Login with Password
```http
POST /api/v2/auth/login/password
Content-Type: application/json

{
  "username": "admin",
  "password": "your-password"
}
```

**Response:**
```json
{
  "data": {
    "user": {
      "id": 1,
      "username": "admin",
      "email": "admin@ucm.local",
      "role": "admin"
    },
    "role": "admin",
    "permissions": ["*"],
    "auth_method": "password",
    "force_password_change": false
  },
  "message": "Login successful"
}
```

**Lockout.** Each attempt is counted before its password is checked, on every node: here on a known, active account; at `POST /api/v2/sso/ldap/login` on the local account the directory entry opens, active or not, whatever name the user filter matched, and an entry with no local account yet is not counted. After `max_login_attempts` attempts without a success, the next ones answer 401 `Invalid credentials` without checking the password, the right one included, until `lockout_duration` has passed. An account whose count already reached a lowered `max_login_attempts` is locked by its next attempt, refused unchecked. A bind that proves the password but opens no session (account disabled here or in the directory, not in the required groups, no role mapped) stays counted, except the attempt that armed the lock, while that lock still runs: it lifts it and is not counted, so such binds never lock the account by themselves. Each lock is logged and sends the `account_locked` alert once. A success resets the count, and so does a new password: reset by link, set by an administrator (`POST /api/v2/users/{id}/reset-password`) or changed in a session (`POST /api/v2/account/password`). The count and the lock are those of the password and the LDAP bind: a client certificate or a passkey is not refused by them, and its success neither resets the count nor lifts the lock. When the count cannot be stored, the login answers 500 `Failed to record login attempt`; when a success cannot reset it, 500 `Failed to update login stats`, with no session opened and a lock armed by that attempt left in place. Either answers 503 with `Retry-After` instead when another write holds the SQLite database.

**Forced password change.** While `force_password_change` is `true` (the first-boot `admin` account when its password was generated, for instance), the session may only set a new password with `POST /api/v2/account/password` and `{"new_password": "..."}`, or log out. Every other call answers `403` with `"must_change_password": true`. API keys are not affected: creating one already needs a session past the change.

### Login with WebAuthn
```http
# Step 1: Get authentication options
POST /api/v2/auth/login/webauthn/start
Content-Type: application/json

{
  "username": "admin"
}

# Step 2: Verify authentication
POST /api/v2/auth/login/webauthn/verify
Content-Type: application/json

{
  "username": "admin",
  "response": { ... }  // WebAuthn credential response
}
```

### Second factor after a password
When the password login answers `"requires_2fa": true`, its `methods` list says which second factors the account has: `totp` (code or recovery code) and/or `webauthn` (a registered security key). A security key also satisfies enforced 2FA in place of enrolling TOTP.
```http
# TOTP code or recovery code
POST /api/v2/auth/login/2fa
{ "code": "123456" }

# Security key: options bound to this login session, then one verification attempt per challenge
POST /api/v2/auth/login/2fa/webauthn/options
POST /api/v2/auth/login/2fa/webauthn/verify
{ "response": { ... } }  // from navigator.credentials.get()
```
Failures with either factor count toward the same 2FA lockout.

A user can also make a key the second factor of password logins without enforcement:
```http
PUT /api/v2/account/2fa/webauthn
{ "enabled": true }                          // needs an enabled key
{ "enabled": false, "password": "..." }      // the account password (local accounts)
```
`{"enabled": false}` answers 403 (`reason: last_second_factor`) when 2FA is enforced for the account, the key second factor is on, TOTP is not confirmed and the account has an enabled key: the key stays the account's second factor once enforcement is lifted. Otherwise the request goes ahead.
`GET /api/v2/account/profile` reports `webauthn_2fa`, `two_factor_enforced` and `two_factor_methods` (the factors a password login asks for).

Under enforced 2FA, a forced-enrolment session may register a key (`/api/v2/webauthn/register/*`) instead of confirming TOTP. `POST /api/v2/account/2fa/disable` and removing or disabling one's own last key answer 403 (`reason: last_second_factor`) when required 2FA (enforced, or a key turned on as second factor) would be left with neither TOTP nor an enabled key. `POST /api/v2/users/{id}/reset-2fa` also turns the key second factor off, as does removing or disabling the account's last enabled key.

An administrator (`write:users`) manages another user's keys, for instance to cut off a lost one, which would otherwise still sign in without a password:
```http
GET    /api/v2/users/{id}/webauthn                     // the user's keys
PATCH  /api/v2/users/{id}/webauthn/{key_id}            // { "enabled": false }
DELETE /api/v2/users/{id}/webauthn/{key_id}
```
Removing or disabling the last second factor of an account whose 2FA is required answers 409 (`reason: last_second_factor`); repeating the request with `?confirm=last_factor` goes ahead, and the user enrols a factor again at the next login, as after a 2FA reset. Each change is audited with the administrator, the account and the key. The own-key routes under `/api/v2/webauthn/credentials` only reach the caller's keys.

### Login with mTLS
```http
POST /api/v2/auth/login/mtls
# Requires client certificate in TLS handshake
```

### Get Available Auth Methods
```http
GET /api/v2/auth/methods
POST /api/v2/auth/methods
```
Public. Both forms answer the same whatever the body: nothing is revealed about a user before sign-in.

**Response:**
```json
{
  "data": {
    "password": true,
    "mtls": false,
    "mtls_status": "not_present",
    "webauthn": true,
    "webauthn_credentials": 0,
    "mtls_certificates": 0,
    "api_keys": true,
    "sso_providers": []
  }
}
```
`mtls_status` is `not_present`, `enrolled`, `present_not_enrolled`, `error`, or `auto_logged_in` when the TLS handshake already signed the caller in (`mtls_user` then names the account). `sso_providers` lists the enabled providers. The two credential counts are always `0` before sign-in.

### Legacy Login
```http
POST /api/v2/auth/login
```
Public. Kept for older clients: it delegates to `POST /api/v2/auth/login/password`, with the same body.

### Verify Session
```http
GET /api/v2/auth/verify
```
Public: answers `{"authenticated": false}` without a valid session or key. Signed in, it returns the session payload of the login responses with, besides:

```json
{
  "data": {
    "authenticated": true,
    "user": { "id": 3, "username": "alice", "email": "alice@example.com", "full_name": "Alice Martin", "role": "operator" },
    "auth_method": "sso",
    "auth_provider": "Company SSO",
    "mfa": { "enabled": true, "methods": ["totp", "webauthn"] },
    "session": { "idle_timeout_s": 1800, "expires_at": "2026-11-23T08:00:00Z" },
    "session_timeout": 1800
  }
}
```
`auth_method` is how the session was opened, kept from its login: `password` (with or without a second factor), `mtls` (certificate login), `certificate` (certificate auto-login), `webauthn`, `sso` (OIDC or SAML) or `ldap`; a call with an API key says `api_key`. `auth_provider` is the display name of the SSO or LDAP provider, else `null`. `mfa.methods` lists the second factors a password sign-in asks for (`totp`, `webauthn`). `session.idle_timeout_s` is the inactivity timeout and `session.expires_at` the end of the session's maximum lifetime, both `null` for an API key.

### Logout
```http
POST /api/v2/auth/logout
```

### Lock Session
```http
POST /api/v2/auth/lock
Content-Type: application/json
X-CSRF-Token: <token>

{
  "reason": "manual"
}
```
Locks the caller's session: it keeps its account, on every node of a shared session store, and serves nothing until that account unlocks it or signs out. Needs an interactive session and its CSRF token (an API key gets 403); locking a locked session again changes nothing. `reason` is `manual` (the default) or `idle` (the console's inactivity lock); the audit records `session_locked` with it. The WebSocket connections of this session (and of no other) are closed before the answer on the node that takes the request, and on the other nodes when the notice reaches them (see [HA.md](HA.md#session-affinity)); a locked session cannot open a new one.

`200` means the session store holds the lock. When it does not, the answer is `409` with the problem type `urn:ucm:problem:session-lock-not-stored`, `Retry-After: 1` and `details.cause`: `gone` (the session's record was removed by a sign-out, or moved to a new identifier by a password, second factor or passkey change, or by closing the other sessions, after the lock's session check) or `busy` (the session store did not take the write: the file store stayed held, an HA maintenance paused the writes of the shared store, or the record kept changing under the write). Nothing is locked or audited then: send the lock again, with the cookie the renewal set if any, and sign out if it keeps failing. A lock stored before such a renewal moves with the session to its new identifier.

While the session is locked, every route that needs a session answers `401` with the problem type `urn:ucm:problem:session-locked` (not `authentication-required`) and `details.username` and `details.reason` (`manual` or `inactivity`). A client certificate presented, an SSO return (`/login?error=session_locked`) or any sign-in door (`401` locked) never reopens or replaces it; `POST /api/v2/auth/logout` still ends it, and an API key sent with the cookie is its own credential. `GET /api/v2/auth/verify` answers `authenticated: false` with a `locked` block (`username`, `name`, `role`, `method`, `reason`, and `methods`: the unlock methods of the account on this instance, among `password`, `certificate`, `passkey`) and the CSRF token the unlock needs.

### Unlock Session
```http
POST /api/v2/auth/unlock/password
X-CSRF-Token: <token>

{
  "password": "..."
}
```
```http
POST /api/v2/auth/unlock/2fa
POST /api/v2/auth/unlock/2fa/webauthn/options
POST /api/v2/auth/unlock/2fa/webauthn/verify
POST /api/v2/auth/unlock/certificate
POST /api/v2/auth/unlock/webauthn/options
POST /api/v2/auth/unlock/webauthn/verify
```
Lifts the lock with a factor of the session's own account and opens a new session for it under a new identifier, answered like a sign-in (`user`, `permissions`, `auth_method`, `csrf_token`, and `requires_2fa_enrollment` when an enrolment is enforced). The password is checked locally, or at the account's LDAP directory for a session it opened or an account without a local password; when the account has a second factor the answer is `{"requires_2fa": true, "methods": [...]}` and the lock stays until `unlock/2fa` (TOTP or recovery code, body `{"code": "..."}`) or the security key (`unlock/2fa/webauthn/options`, then `verify` with `{"response": {...}}`). `unlock/certificate` takes the client certificate of the request, refused when it belongs to another account or mTLS is off (`400`). `unlock/webauthn/options` then `verify` (`{"response": {...}}`) take a passkey of the account. Password, second-factor and passkey attempts count against the same limits as at the sign-in (the account lockout; `429` with `Retry-After` for a second factor or a passkey), and every attempt is audited: `session_unlocked` with the method, `session_unlock_failure` with the method and the reason (a certificate or passkey of another account is named). `401` locked stays the answer of every other route until then; without a locked session the unlock routes answer `409` (session open) or `401`.

### Forgot Password
```http
POST /api/v2/auth/forgot-password
Content-Type: application/json

{
  "email": "user@example.com"
}
```

The answer is the same whether or not an account holds the address. No link is sent to an SSO account (linked to a provider or left without one) that has no local password: its provider alone opens it, and a token cannot set a password on it either. An administrator can still give it one.

### Reset Password
```http
POST /api/v2/auth/reset-password
Content-Type: application/json

{
  "token": "reset-token-from-email",
  "password": "NewSecurePassword123!"
}
```

### Check Email Configuration
```http
GET /api/v2/auth/email-configured
```

**Response:**
```json
{
  "data": {
    "configured": true
  }
}
```

---

## Account Management

### Profile

```http
# Get profile
GET /api/v2/account/profile

# Update profile
PATCH /api/v2/account/profile
Content-Type: application/json

{
  "full_name": "John Doe",
  "email": "john@example.com"
}

# Change password
POST /api/v2/account/password
Content-Type: application/json

{
  "current_password": "old-password",
  "new_password": "new-password"
}
```

### Two-Factor Authentication (2FA/TOTP)

```http
# Enable 2FA - returns QR code
POST /api/v2/account/2fa/enable

# Confirm 2FA with TOTP code
POST /api/v2/account/2fa/confirm
Content-Type: application/json

{
  "code": "123456"
}

# Disable 2FA
POST /api/v2/account/2fa/disable
Content-Type: application/json

{
  "code": "123456"
}

# Get recovery codes
GET /api/v2/account/2fa/recovery-codes

# Regenerate recovery codes
POST /api/v2/account/2fa/recovery-codes/regenerate
```

A code checked by `2fa/disable` or `2fa/recovery-codes/regenerate` counts against the same `max_login_attempts` as the second step of a login for that account; past it, both answer 429 until `lockout_duration` has passed, and a code accepted resets the count. `2fa/confirm` answers 409 once TOTP is enabled.

**Password checked in a session.** `POST /api/v2/account/password`, `PUT /api/v2/users/{id}` and `POST /api/v2/users/{id}/reset-password` on one's own account (`current_password`), and `PUT /api/v2/account/2fa/webauthn` with `"enabled": false` count each wrong password against the account, on a counter apart from the login's: after `max_login_attempts` failures they answer 429 (`Too many failed attempts. Try again later.`, with `Retry-After` and `details.retry_after` in seconds), even for the right password, until `lockout_duration` has passed. A right password before that resets the count, and the login is not locked by it.

**Other sessions closed.** Confirming or disabling TOTP, regenerating recovery codes, registering, deleting or toggling a security key (`/api/v2/webauthn/...`, or an administrator's `/api/v2/users/{id}/webauthn/{key_id}`) and `PUT /api/v2/account/2fa/webauthn` close every other session of the account, as a password change does; the session making the change stays. The response's `meta.other_sessions_closed` gives how many were closed (`null` when the session store cannot be listed), and so does the audit entry. A request that leaves the factors as they are (a key or the key second factor set to its current state, a TOTP setup dropped before it was confirmed) closes none and answers `other_sessions_closed: 0`. API keys are not affected.

### API Keys

```http
# List API keys
GET /api/v2/account/apikeys

# Create API key
POST /api/v2/account/apikeys
Content-Type: application/json

{
  "name": "CI/CD Integration",
  "expires_days": 365,
  "permissions": ["read:certificates", "write:certificates"]
}

# Get API key details
GET /api/v2/account/apikeys/{key_id}

# Update API key
PATCH /api/v2/account/apikeys/{key_id}
Content-Type: application/json

{
  "name": "Updated Name",
  "enabled": true
}

# Regenerate API key
POST /api/v2/account/apikeys/{key_id}/regenerate

# Delete API key
DELETE /api/v2/account/apikeys/{key_id}
```

The first `DELETE` revokes a key that still works (kept for the audit history); a second one, or one on an expired key, deletes it.

An administrator (`write:users`) lists another user's keys and revokes a leaked or unused one, with the same revoke-then-delete rule. The secret is never returned. Each change is audited with the administrator, the account and the key. An API key cannot revoke or delete through them a key of its own account.
```http
GET    /api/v2/users/{id}/apikeys                      // the user's keys
DELETE /api/v2/users/{id}/apikeys/{key_id}             // revoke, then delete
```

A key is sent as `X-API-Key: ucm_ak_...` or, equivalently, `Authorization: Bearer ucm_ak_...`. Both get the key's scopes and need no CSRF token; a key that fails is refused (401) even when a session cookie is present. A bearer token that does not start with `ucm_ak_` (an IdP token relayed by an authenticating proxy, for instance) is not taken for a key: it is ignored, gets no CSRF exemption, and the session cookie applies.

### WebAuthn Credentials

Security-key management for the signed-in account is served under `/api/v2/webauthn/`; see [WebAuthn](#webauthn). There is no `/api/v2/account/webauthn/` prefix.

### mTLS Certificates

Served under `/api/v2/mtls/` (not under `/account/`). Except for the two settings routes and the two GET lists (certificates, available-certificates), every route here needs an interactive session (`403` otherwise). A user works on their own enrolments; an admin may act on another user's where noted.

```http
GET /api/v2/mtls/settings
```
Permission `read:settings`. Returns `enabled`, `required`, `trusted_ca_id` and `trusted_ca` (`refid`, `name`, `valid_to`, `has_private_key`, or `null`).

```http
PUT /api/v2/mtls/settings
Content-Type: application/json

{ "enabled": true, "required": false, "trusted_ca_id": "<CA refid>" }
```
Permission `admin:system`. Every field is optional; an empty body answers `400`. Unknown `trusted_ca_id` when enabling answers `404`. `required: true` with `enabled: true` answers `400` while no active admin has an enabled enrolled certificate. The change reloads the TLS listener, in a container too (in HA mode a rolling restart is queued instead): the response carries `needs_restart`, `restart_message` and `listener_reload`, as for `POST /api/v2/system/https/apply`.

```http
GET /api/v2/mtls/certificates
```
Any authenticated user. The caller's enrolled certificates, newest first.

```http
POST /api/v2/mtls/certificates
Content-Type: application/json

{ "name": "My Laptop", "validity_days": 365, "organization": "UCM Users", "ca_id": 1 }
```
Permission `write:user_certificates`, session only. Issues a client certificate (CN `<username>@mtls`) from the configured mTLS CA and enrolls it. `ca_id` (numeric id or refid) overrides the configured CA and then also requires `write:cas` (`403`). `400` when no mTLS CA is configured and none is given, when `validity_days` is outside the allowed range, or when `organization` is not 1 to 64 letters, digits, spaces, dots or hyphens. Responds `201` with `id` (the enrolment id), `certificate_id`, `name`, `serial`, `certificate`, `private_key`, `created_at`, `expires_at`, `status`.

```http
DELETE /api/v2/mtls/certificates/{cert_id}
```
Session only. Removes an enrolment; `{cert_id}` is the enrolment id. `404` if unknown, `403` if it belongs to someone else and the caller is not an admin.

```http
GET /api/v2/mtls/certificates/{cert_id}/download?format=pem&include_chain=true&include_root=false
POST /api/v2/mtls/certificates/{cert_id}/download
Content-Type: application/json

{ "format": "pkcs12", "password": "at-least-8-chars", "include_chain": true, "include_root": false, "legacy": false }
```
Session only. `format` is `pem` (default) or `pkcs12` (also spelled `p12` or `pfx`, in any case); any other value answers `400`. A PEM download is the certificate alone; it adds the issuing chain (and the root with `include_root=true`) only when `include_chain` or `include_root` is sent in the request, and `include_chain=false` keeps the certificate alone. PKCS12 is refused on the query-string form with `400` (the password must travel in a POST JSON body); it also needs a stored private key. Options are read as described under Export Certificate (where the options go). Options of this route: `format`, `include_chain`, `include_root` and, in a POST body, `password` and `legacy`. `legacy` selects the 3DES/SHA-1 profile. Returns the file as a download. `404` when the enrolment is not the caller's (admins may download any).

```http
POST /api/v2/mtls/enroll
Content-Type: application/json

{ "name": "Work laptop" }
```
Session only. Enrolls the client certificate presented with the request: the TLS handshake's, or one forwarded by a trusted proxy. `400` when none is presented, it is expired, not yet valid, revoked, or its issuer is revoked or unknown; `409` when already enrolled.

```http
POST /api/v2/mtls/enroll-import
Content-Type: application/json

{ "pem": "-----BEGIN CERTIFICATE-----...", "name": "Work laptop", "user_id": 2 }
```
Session only. Imports a certificate issued by a CA of this server and enrolls it. `pem` is the PEM text, base64 of it, or `BASE64:` followed by the base64 of a DER file (a `.cer` or `.crt`). It is required; `user_id` is honoured for admins only. `400` for unparsable data, an expired or revoked certificate, or a foreign issuer; `409` when already enrolled. Responds `201`.

```http
GET /api/v2/mtls/available-certificates
```
Any authenticated user. User certificates (`usr_cert`, not revoked) that no account has enrolled. Non-admins see only the ones made for them.

```http
POST /api/v2/mtls/assign
Content-Type: application/json

{ "cert_id": 12, "name": "Work laptop", "user_id": 2 }
```
Session only. Enrolls an existing user certificate (`cert_id` is the certificate id, required). `user_id` is honoured for admins only; a non-admin may assign only a certificate made for their account (`403`). `400` when the certificate is not a user certificate or is revoked, `404` when unknown, `409` when already enrolled. Responds `201`.

### Preferences
```http
GET /api/v2/account/preferences
PUT /api/v2/account/preferences
Content-Type: application/json

{ "language": "fr", "theme_mode": "dark" }
```
Any authenticated user, for their own account. `PUT` replaces the stored preferences with the object sent; keys the server does not know are dropped and the persisted object is returned. `400` for a body that is not JSON, a `pins` list that is not at most 3 distinct module ids, a `notifications_read` list that is not distinct item keys, or an invalid `inspector` value.

### Sessions

```http
# List active sessions
GET /api/v2/account/sessions

# Revoke specific session
DELETE /api/v2/account/sessions/{session_id}

# Revoke all sessions except current
POST /api/v2/account/sessions/revoke-all
```

### Activity

```http
GET /api/v2/account/activity?limit=50
```

---

## Certificate Authorities

### List CAs
```http
GET /api/v2/cas
GET /api/v2/cas?page=1&per_page=20
```

**Response:**
```json
{
  "data": [
    {
      "id": 1,
      "name": "Root CA",
      "common_name": "UCM Root CA",
      "ca_type": "root",
      "serial_number": "0x1",
      "valid_from": "2025-01-01T00:00:00",
      "valid_until": "2035-01-01T00:00:00",
      "key_size": 4096,
      "signature_algorithm": "sha256WithRSAEncryption",
      "certificates_count": 42
    }
  ],
  "meta": { "page": 1, "per_page": 20, "total": 3 }
}
```

**Key fields** (CAs, certificates and CSRs): `key_type` (`"RSA 4096"`, `"EC secp384r1"`,
`"ML-DSA-65"`), `key_algorithm` (`"RSA"`, `"EC"`, `"ML-DSA-65"`), `key_size` (bits of an RSA key, `256`
or `448` for Ed25519 or Ed448; `0` for EC and `null` for a post-quantum key), `security_level` (NIST level
`2`, `3` or `5` for ML-DSA-44/65/87, `null` otherwise), `post_quantum` (boolean) and `verifiable` (`false`
for an SLH-DSA signature, which UCM reads but cannot check). An ML-DSA CA reports `signature_algorithm`
as its parameter set, e.g. `"ML-DSA-65"`, an EdDSA CA as `"Ed25519"` or `"Ed448"`. A certificate in a hybrid pair (RFC 9763) also
reports `related_certificate_id` (the other member) and `hybrid_role` (`"classical"` or `"pq"`);
both are `null` otherwise.

### Create CA
```http
POST /api/v2/cas
Content-Type: application/json

{
  "commonName": "My Root CA",
  "organization": "My Company",
  "country": "US",
  "state": "California",
  "locality": "San Francisco",
  "keyAlgo": "RSA",
  "keySize": 4096,
  "validityYears": 10,
  "type": "root"
}
```

`validityYears` takes 1 to 50 (default 10). `validityDays` (1 to 18250) sets a
duration that is not a whole number of years and takes precedence when both
are sent. An intermediate CA never outlives its parent. A CA of type
`external` takes neither: its signer decides.

`keyAlgo` is `RSA` (`keySize` 2048, 3072 or 4096), `ECDSA` or `EC` (`keySize` a curve:
`prime256v1`, `secp384r1`, `secp521r1`, or a Brainpool curve), `EdDSA` (`keySize` `Ed25519` or
`Ed448`) or `ML-DSA` (`keySize` 44, 65 or 87, required). A full label such as `RSA-3072`, `EC-P384`,
`Ed25519` or `ML-DSA-65` is also accepted,
and `keyType` is an alias of `keyAlgo`. An unknown `keyAlgo`, or a `keySize` that does not
belong to it, answers `400`. Without `keySize`, `RSA` gives RSA-2048, `ECDSA` P-256 and `EdDSA`
Ed25519; a request without any key field gets RSA-2048. An EdDSA CA key is generated in software
only (no HSM provider holds one), is refused in FIPS mode unless the loaded FIPS module approves
EdDSA (the `-fips` Docker image does) and signs without a separate digest,
like ML-DSA below. Web browsers (Chrome, Firefox, Safari), Windows (CryptoAPI/CNG) and SCEP clients
do not verify an Ed25519 or Ed448 signature on a certificate, so they reject anything such a CA issues,
whatever the leaf key: keep it for clients that do (OpenSSL, Go, Java 15 and later). SCEP refuses
any CA whose key is not RSA (EC, EdDSA and ML-DSA included) or is held by an HSM, XCEP refuses an
EdDSA CA, and an EdDSA CA cannot sign timestamps itself (it can issue the TSA signer). ML-DSA needs
OpenSSL 3.5 or later and is refused in FIPS mode unless the loaded FIPS module approves it (the
`-fips` Docker image does); `keyAlgo` generates it in software, and
an HSM-held ML-DSA key is chosen with `hsm_key_algorithm` on a provider that has it (see [HSM](#hsm)).
An ML-DSA key signs without a separate digest: a `digest` sent for it is ignored and named
in `meta.notices`. An intermediate under an ML-DSA parent likewise takes no digest; an
ML-DSA intermediate under an RSA or EC parent uses its parent's digest.

In HA mode, a CA on a SoftHSM or local smart card reader (OpenSC, YubiKey PIV) key (`hsm_key_id` of a key on such a provider, or a new key
through `hsm_provider_id`) answers `409` with code `ha_mode`, whatever the CA type.

An HSM key backs one authority: `hsm_key_id` of a key an X.509 or SSH CA already holds answers `409`, naming that CA.

A CA on an HSM key (`hsm_key_id`, or `hsm_provider_id` for a new key on the token), internal or `external`, requires `read:hsm` besides `write:cas`: `403` names the missing permission otherwise, before the key is looked up or generated.

Optional `namedUrls: true` gives the CA an immutable unique slug derived from
its name, used instead of the random id in CDP/AIA URL paths (both forms keep
resolving). Returned as `url_slug` (null when not opted in).

**For Intermediate CA:**
```json
{
  "commonName": "My Intermediate CA",
  "parentCAId": 1,
  "type": "intermediate",
  "validityDays": 1825,
  "keyAlgo": "RSA",
  "keySize": 4096
}
```

`parentCAId` is required for `type: intermediate`: without it the request answers `400` instead of creating a self-signed root. A `root` or `external` (CSR) CA takes none.

### Get CA Details
```http
GET /api/v2/cas/{ca_id}
```

### Update CA
```http
PATCH /api/v2/cas/{ca_id}
Content-Type: application/json

{
  "name": "Updated Name"
}
```

`issuanceHidden` (`true` or `false`, nothing else) keeps the CA out of the CA lists of the manual
issuance forms (Issue Certificate, Sign CSR, bulk CSR signing, user mTLS certificates, TSA signing
certificate), behind a
"show hidden CAs" link. It is presentation only: the CA still signs whatever it is asked to. The
CA object reads it back as `issuance_hidden`, and the change is audited.

`enforceUniqueSubject` (`true` or `false`) makes the CA refuse a certificate whose subject a
certificate of another entity already carries under it, whatever its status (RFC 5280 §4.1.2.6,
see the user guide for what makes the same entity). The CA object reads it back as
`enforce_unique_subject`, and the change is audited. The answer that turns it on carries
`shared_subjects`, the number of subjects certificates of the CA already carry for more than one
entity (rows joined by a shared key, lineage, recorded identity or SID being one entity), and
`shared_subject_examples`, the first 20 of them in issuance order:
`[{"subject": "CN=…", "serial_numbers": ["…", "…"]}]`. Those certificates stay. A renewal of any
of them (in place, automatic or by a protocol) is refused as it is; only a manual issuance or a
CSR signing of such a subject goes through, with the override below.

With the option on, `POST /api/v2/certificates` and `POST /api/v2/csrs/{id}/sign` answer `409`
when the subject is taken, with `details` `{"subject", "serial_number", "override_field":
"override_unique_subject"}`. Sending the request again with `"override_unique_subject": true`
(`write:certificates`) attests that this certificate is for the same entity as the one that
already carries this subject. When a single entity carries it, the new certificate is recorded
as that entity's, as a renewal would be, and the existing and the new certificates renew
afterwards without the override; when several do, the subject stays shared (see the user
guide). Either way the issuance writes a `certificate.subject_override` audit entry naming the
operator, the subject, the new certificate and the certificate whose entity it joins, or the
number of entities sharing the subject. A renewal refused for the same reason answers `409` and
has no override.

### Confirm a Parent Whose Signature Cannot Be Verified
```http
POST /api/v2/cas/{ca_id}/parent-confirmation
Content-Type: application/json

{
  "parent_id": 12,
  "confirm": true
}
```

A CA is linked to a parent on its own only when the parent's key verifies its signature. When
the parent's key or signature algorithm cannot be checked here (SLH-DSA, GOST), the CA is left
without a parent and its object carries `parent_candidate` (`id`, `name`, `algorithm`, `reason`:
`signature not verifiable here: <algorithm>`); `GET /api/v2/cas/{ca_id}` and the import responses
fill it, the list returns `null`. The candidate is a stored CA whose subject is the CA's issuer
(RFC 5280 name comparison) and whose SKI is the CA's AKI when both are present, the self-signed
record first.

The route needs `write:cas` and `"confirm": true` (the boolean, 400 otherwise). It checks again
that the CA has no parent, that `parent_id` is the candidate and that the signature still cannot
be checked, and answers 409 with the reason otherwise: a parent whose key does not verify the
signature is refused even confirmed, and one whose key verifies needs no confirmation. On success
it sets the parent, records `parent_confirmed_by` and `parent_confirmed_at`, writes the audit
entry `ca_parent_confirmed` and returns the CA.

```http
DELETE /api/v2/cas/{ca_id}/parent-confirmation
Content-Type: application/json

{ "confirm": true }
```

Withdraws a parent confirmed by hand (409 for any other link), audited as `ca_parent_unconfirmed`;
the CA is left without a parent and carries its `parent_candidate` again.

When the certificate of a CA changes (`POST /api/v2/cas/import`, `POST /api/v2/certificates/import`,
the certificate upload of a pending or renewing CA, `POST /api/v2/cas/{ca_id}/restore-primary`), the
CA takes the stored CA whose subject is the issuer name and whose key verifies the new certificate.
When none does, a parent linked without a confirmation stays unless the chain repair would drop it
(its subject is not the issuer name, or the key the authority key identifier names disproves the
signature), audited as `ca_parent_unlinked` when dropped; a revoked CA keeps its parent while the
certificate keeps its serial number.

`POST /api/v2/import/execute` (smart import), `POST /api/v2/import/opnsense/import` and the
result of the OPNsense file importer list such CAs in `unverifiable_parents`: `ca_id`, `ca_name`, `candidate`
(`id`, `name`), `algorithm` and `reason`. `POST /api/v2/cas/import` and
`POST /api/v2/certificates/import` return the CA object with its `parent_candidate`.

### Delete CA
```http
DELETE /api/v2/cas/{ca_id}
```

Answers `204`, or `409` with the reason while the CA is still in use: intermediate CAs or certificates under it, SCEP or Windows enrollment profiles, ACME domains, issuance policies, CRL deployments, or a setting that names it (the default SCEP, ACME issuing or EST CA, the TSA CA, the trusted mTLS CA, an EST label). The message says where to change it; the CA is deleted once nothing names it.

### List CA Certificates
```http
GET /api/v2/cas/{ca_id}/certificates
GET /api/v2/cas/{ca_id}/certificates?status=active&page=1&per_page=50
```

### Export CA
```http
GET /api/v2/cas/{ca_id}/export?format=pem
GET /api/v2/cas/{ca_id}/export?format=der
POST /api/v2/cas/{ca_id}/export

# Chain through a cross-certificate (POST accepts the same field in its JSON body)
GET /api/v2/cas/{ca_id}/export?format=pem&include_chain=true&chain_variant=cross:4
```

`POST` takes `format`, `include_key`, `include_chain`, `password` (required for the PKCS12, PFX and JKS formats; with `format=pem` and `include_key` or with `key`, it encrypts the key as PKCS#8) and `legacy` in a JSON body. `chain_variant` is `auto` (default: the chain UCM serves), `primary` (the self-signed root)
or `cross:<id>`; any other value, or one that is not part of the chain of this CA, answers 400.

Options are read as described under Export Certificate (where the options go). Options of this route: `format` (`pem` by default, `der`, `pkcs7`, `p7b`, `key`, `pkcs12`, `pfx`, `jks`), `include_key`, `include_chain`, `password`, `legacy`, `chain_variant`. A GET that asks for a private key (`include_key=true`, `format=key`, `pkcs12`, `pfx`, `jks`) answers `400`.

`include_key` with a format that carries no key (`der`, `p7b`, `pkcs7`) answers `400`. A `password` that is not a string, or outside the rule (8 to 256 characters, at most 1023 bytes in UTF-8), answers `400` whatever the format; a valid one is ignored when the output carries no private key (`der`, `p7b`, `pkcs7`, `pem` without `include_key`). The key of an offline CA kept under its offline password is exported as stored, already encrypted under that password, by its `pem` (with `include_key`) or `key` export without a `password`; with a `password`, or as `pkcs12`, `pfx` or `jks`, it answers `409`, as does any key export of an HSM-backed CA, once the password has passed the rule. A key export is audited as `private_key_exported`, `password-protected` (an offline CA's key included) or `unencrypted`. `legacy` applies to `pkcs12` and `pfx` only and is ignored for the other formats: a JKS keeps its own format, the Sun key protector for the key entry and a SHA-1 integrity digest, whatever `legacy` says.

### Export All CAs
```http
GET /api/v2/cas/export
GET /api/v2/cas/export?chain_variant=all
POST /api/v2/cas/export
```

`chain_variant` adds cross-certificates after each CA certificate: `primary` (default) adds none,
`auto` the served ones, `all` every attached one, `cross:<id>` that one.

An unreadable CA certificate (or cross-certificate, named `cross:<id>`) is skipped, logged, and named in `X-Skipped-CAs` (the first 100) with the total in `X-Skipped-CAs-Count`; the others are exported. When none is readable the answer is `404` in both PEM and P7B, with `details.skipped` (the first 100) and `details.skipped_count` (the total).

### Bulk Delete CAs
```http
POST /api/v2/cas/bulk/delete
Content-Type: application/json

{
  "ids": [1, 2, 3]
}
```

**Response:**
```json
{
  "data": {
    "success": [1, 2],
    "failed": [{"id": 3, "error": "default ACME issuing CA"}]
  }
}
```

Each CA is judged as `DELETE /api/v2/cas/{ca_id}` judges it; a refused one is listed in `failed` with the short reason and the others are still deleted.

### Bulk Export CAs
```http
POST /api/v2/cas/bulk/export
Content-Type: application/json

{
  "ids": [1, 2, 3]
}
```

Returns the selected CA certificates as `format` `pem` (default) or `p7b`. `X-Exported-Count` holds the number of certificates in the file: unknown ids and unreadable ones are not counted.

An unreadable CA certificate (or cross-certificate, named `cross:<id>`) is skipped, logged, and named in `X-Skipped-CAs` (the first 100) with the total in `X-Skipped-CAs-Count`; the others are exported. When none is readable the answer is `404` in both PEM and P7B, with `details.skipped` (the first 100) and `details.skipped_count` (the total).

### Cross-certificates

A cross-certificate carries a CA's subject and public key under another issuer. It is stored beside
the CA's own certificate, which is never replaced. At most one per CA is *served* (placed in the
default chain); a revoked, expired or not yet valid one is kept and exportable but never served.
Reading needs `read:cas`, everything else `write:cas`. Refusals carry `details.code`.

```http
GET    /api/v2/cas/{ca_id}/cross-certificates
POST   /api/v2/cas/{ca_id}/cross-certificates
GET    /api/v2/cas/{ca_id}/cross-certificates/{xid}
PATCH  /api/v2/cas/{ca_id}/cross-certificates/{xid}
DELETE /api/v2/cas/{ca_id}/cross-certificates/{xid}
POST   /api/v2/cas/{ca_id}/cross-certificates/{xid}/revoke
GET    /api/v2/cas/{ca_id}/cross-certificates/{xid}/export?format=pem|der
GET    /api/v2/cas/{ca_id}/chain-variants
GET    /api/v2/cas/{ca_id}/chain-usage
POST   /api/v2/cas/{ca_id}/cross-sign
```

**Attach** (`201`; `warnings` lists NameConstraints or PolicyConstraints the certificate carries):
```json
{"certificate": "-----BEGIN CERTIFICATE-----...", "served": false}
```

**Serve or stop serving** (`PATCH`): `{"served": true}`. Serving another one of the same CA un-serves the first.

**Revoke** (`POST .../revoke`): `{"reason": "superseded", "invalidity_date": "2026-10-01T00:00:00Z"}`.
The serial is published on the issuer's CRL and OCSP; the CA it certifies is not revoked.
A revocation under an approval policy answers with the approval request instead.

**Chain variants** (`GET .../chain-variants`): the chains the CA can present, `primary` and one per
cross-certificate on its path. Each entry has `id` (`primary` or `cross:<id>`), `ca_id`, `ca_name`,
`cross_certificate_id`, `issuer`, `valid_to`, `served`, `servable` and `default` (what a plain export of this CA returns).

**Chain usage** (`GET .../chain-usage`, needs `read:cas` and `read:certificates`): what still chains to the CA, to tell when
it can be retired. A chain depends on the CA when one of its links is a CA of its subtree (records of the same key included), or a
cross-certificate of such a CA or issued by one (the issuer is resolved by signature when `issuer_caref` is empty or dangling).
`issued`: unrevoked, unexpired, unarchived certificates issued by the CA or a CA below it, those with no `caref` included
(their issuer is found as an export does: AKI, then signature). A leaf issued directly by a root is counted there; its binding is not
counted under `deployments` unless the root is pushed (`include_root`). `via_cross`: the others whose default chain
goes through a servable cross-certificate that depends on the CA. `via_cross.cross_certificates` always lists the cross-certificates
issued by the CA, its subtree or a record of its key (`id`, `ca_id`, `ca_name`, `served`, `servable`), even when no certificate
uses them: a servable one can still be served, pinned or offered as an ACME alternate chain. `deployments`: enabled bindings with a
non-empty full chain path whose pushed chain depends on the CA. `subordinate_cas`: the active (unrevoked, unexpired) CAs below the
CA, its records of the same key left out; a CA that still has some is not ready to retire even with no certificate left.
`crl_deployments`: enabled CRL bindings on the CA, its records of the same key or a CA below it. Without `read:deploy`, `deployments.count`
and `crl_deployments.count` are returned but `items` is empty. Each section has `count`, `items` (at most 100; certificates, CAs and bindings soonest expiry first
with no expiry last, CRL bindings and `cross_certificates` by id) and `truncated`; `note` says UCM only sees what it issues and delivers. Items are certificates (`id`, `name`, `cn`,
`ca`, `ca_refid`, `valid_to`), CAs (`id`, `name`, `valid_to`), bindings (`id`, `target_id`, `target`, `certificate_id`, `certificate`,
`variant`) or CRL bindings (`id`, `target_id`, `target`, `ca_id`, `ca_name`, `crl_path`). An intermediate CA with no `caref` (not
linked to its parent yet) is not seen below the parent, so its certificates can read as zero until the hourly backfill links it.

**Cross-sign from UCM** (`POST /api/v2/cas/{issuer_id}/cross-sign`, `201`): signs the key of another
CA held in UCM with this one and stores the result on the subject CA.
```json
{"subject_ca_id": 5, "validity_days": 1825, "path_length": 0}
```
`validity_days` (default 1825, at most 3650) and `path_length` are optional.

**Findings and repairs** for records damaged before cross-certificates were modelled. Nothing runs by itself:
```http
GET  /api/v2/cas/cross-findings
POST /api/v2/cas/{ca_id}/convert-to-cross      # write:cas and delete:cas
POST /api/v2/cas/{ca_id}/restore-primary       # {"certificate": "<self-signed PEM>"}
```
`cross-findings` returns `{"findings": [...], "note": "..."}` with `kind` `shadowed_root` (a record whose
subject and key match a held self-signed root; action `convert_to_cross`) or `same_key_distinct_certs`
(action `restore_primary` when no self-signed record exists). `convert-to-cross` moves the record's child CAs,
issued certificates and settings to the root and deletes the duplicate; `restore-primary` puts a
self-signed certificate back and keeps the replaced one as a cross-certificate. A self-signed root that was
overwritten or deleted only comes back from a backup or through `restore-primary`.

### CAs Awaiting an External Certificate
A CA created from an external CSR holds no certificate until one is installed. Unknown CAs answer `404`.

```http
GET /api/v2/cas/{ca_id}/csr
POST /api/v2/cas/{ca_id}/certificate
POST /api/v2/cas/{ca_id}/key
POST /api/v2/cas/{ca_id}/crl
POST /api/v2/cas/{ca_id}/renew-csr
```
- `csr` (`read:cas`) downloads the outstanding CSR as PEM; `404` when there is none.
- `certificate` (`write:cas`) installs the signed certificate: a multipart `file`, or `pem_content` in a form field or a JSON body, and optionally `cross_mode` (`auto` or `replace`, else `400`). `409` when the CA is offline or the certificate conflicts with the CA's current one (the response details say how).
- `key` (`write:cas`) attaches the private key to a CA that holds only its certificate: JSON `key` (PEM or base64 PEM, required) and optional `passphrase`. `409` for a pending CA, `400` when the CA already has a key, lives in an HSM, is offline, or the key does not match the certificate or is refused as weak.
- `crl` (`write:crl`) installs a CRL generated elsewhere on a key-less or offline CA: a multipart `file` or `pem_content`. Returns the installed CRL's `next_update` and `revoked_count`; `409` or `400` when it is refused.
- `renew-csr` (`write:cas`) issues a new CSR from the CA's existing key. Optional `digest` (`sha256`, `sha384` or `sha512`). `409` when the CA is offline or revoked, `400` when it has no key.

### Offline CAs
```http
POST /api/v2/cas/{ca_id}/offline
POST /api/v2/cas/{ca_id}/restore
```
Both need `write:cas`. `offline` takes `{"password": "...", "mode": "password_protected"}`: the key is re-encrypted under the password and kept (`password_protected`, the default), or returned as a `.key` download and removed from UCM (`file_exported`, which also needs `read:private_keys`). The password must meet the password policy (`400`). `409` when the CA is already offline, revoked or pending; `400` when it has no key in UCM (HSM-backed, for instance). `restore` takes the `password` (JSON or form) and, for a `file_exported` CA, the uploaded `key_file`; `401` for a wrong password, `400` when the file is not this CA's key, `409` when the CA is not offline.

### Revoke a CA
```http
POST /api/v2/cas/{ca_id}/revoke
Content-Type: application/json

{ "reason": "keyCompromise", "invalidity_date": "2026-01-01T00:00:00Z" }
```
Permission `write:cas`. Revokes an intermediate CA from its parent. `reason` defaults to `unspecified`; `invalidity_date` (or `invalidity_at`) may not be in the future. `409` when the CA is already revoked, `400` for an invalid reason or date. When an approval policy applies, the answer carries `approval_required: true` and the approval instead (see [Certificate Policies & Approvals](#certificate-policies--approvals)).

### Delegated OCSP Responder
```http
GET /api/v2/cas/{ca_id}/ocsp-responder
POST /api/v2/cas/{ca_id}/ocsp-responder
DELETE /api/v2/cas/{ca_id}/ocsp-responder
GET /api/v2/cas/{ca_id}/eligible-ocsp-responders
```
`GET` (`read:cas`) returns `responder`, `null` when none is set. `POST` (`write:cas`) takes `{"certificate_id": 12}`: the certificate must be issued by this CA and able to sign OCSP responses (`400` with the reason otherwise); `409` while the CA awaits its certificate. `DELETE` needs `delete:cas` and answers `204`. `eligible-ocsp-responders` lists the certificates that pass those checks.

### Template Pins
```http
GET /api/v2/cas/{ca_id}/templates
POST /api/v2/cas/{ca_id}/templates/{template_id}/pin
DELETE /api/v2/cas/{ca_id}/templates/{template_id}/pin
```
`GET` needs `read:cas` and `read:templates` and returns `ca_id`, `ca_name` and every template with an `is_pinned` flag. `POST` and `DELETE` need `write:cas` and `write:templates`. When a CA has pinned templates, the issuance form offers only those by default. `POST` answers `201` (`400` when the pin is refused); `DELETE` answers `404` when the template is not pinned.

---

## Certificates

### List Certificates
```http
GET /api/v2/certificates
GET /api/v2/certificates?status=active&ca_id=1&page=1&per_page=50
GET /api/v2/certificates?status=expiring&per_page=10
GET /api/v2/certificates?search=example.com
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | string | Filter, repeatable: `valid`, `expiring`, `expired`, `revoked`, `orphan`, `archived` |
| `ca_id` | integer | Filter by issuing CA |
| `search` | string | Contained in the subject, issuer, display name (`descr`), comment or serial number, or a whole serial in hex |
| `sort_by` | string | `subject` (default; the CN, else the description), `subject_cn`, `descr`, `comment`, `issuer`, `valid_to`, `valid_from`, `created_at`, `serial_number`, `key_algo`, `source` (none reads `manual`), `revoked`, `status` (revoked, expired, expiring, valid), `compliance_grade`; see [Sorting](#sorting) |
| `sort_order` | string | `asc` (default) or `desc` |
| `page` | integer | Page number (default: 1) |
| `per_page` | integer | Items per page (default: 50, max: 100) |

### Issue Certificate
```http
POST /api/v2/certificates
Content-Type: application/json

{
  "common_name": "server.example.com",
  "ca_id": 2,
  "template_id": 1,
  "validity_days": 365,
  "key_size": 2048,
  "san": ["dns:server.example.com", "dns:www.example.com", "ip:192.168.1.10"],
  "key_usage": ["digitalSignature", "keyEncipherment"],
  "extended_key_usage": ["serverAuth", "clientAuth"]
}
```

`key_type` is `rsa` (default; `key_size` 2048, 3072 or 4096), `ec` (`key_size` 256, 384 or
521, or `curve`) or `ml-dsa` (`key_size` 44, 65 or 87); a label such as `ML-DSA-65` names
both at once. Without them, the template's key type applies. An unknown key type answers
`400`. A certificate for an ML-DSA key keeps only signature bits: `keyEncipherment`,
`dataEncipherment` and `keyAgreement` are removed from the key usage and named in
`meta.notices`. ML-DSA private keys cannot be exported as PKCS#12 or JKS: those exports
answer `400` with the reason `unsupported_for_key_algorithm`; PEM and DER work.

**Hybrid pair (RFC 9763).** `"hybrid": {"classical": "EC P-256", "pq": "ML-DSA-65"}` issues two
certificates from the same CA, with the same subject, names and validity: A for the classical key
and B for the post-quantum key. B carries the non-critical relatedCertificate extension naming A,
and the two rows name each other through `related_certificate_id`. `key_type` and `key_size`
are ignored; a `classical` member that is post-quantum, a `pq` member that is not, or an unknown
key type answers `400`, and so does a policy that requires approval. The response is
`201` with `data.certificate` (A) and `data.related` (B).

**Custom extensions.** `custom_extensions` takes the list described under [Templates](#templates). They join the template's; an entry with the OID of one of the template's replaces it. An invalid list answers `400` before anything is issued or queued for approval. A renewal keeps the extensions of the certificate it renews, the template's current entries replacing those of the same OID and joining the others; one the template no longer lists stays, since UCM cannot tell it from one the request added.

**Response:**
```json
{
  "data": {
    "id": 42,
    "serial_number": "0x2A",
    "common_name": "server.example.com",
    "status": "active",
    "valid_from": "2026-01-28T00:00:00",
    "valid_until": "2027-01-28T00:00:00",
    "private_key_available": true
  },
  "message": "Certificate issued successfully"
}
```

### Get Certificate Details
```http
GET /api/v2/certificates/{cert_id}
```

`extensions.other_extensions` lists the extensions without a section of their own, custom ones included: `[{oid, name, critical, value_hex}]`, `name` being null for an OID UCM cannot name. `GET /api/v2/cas/{ca_id}` returns the same under `extensions`, and `GET /api/v2/csrs/{csr_id}` lists under `other_extensions` the extensions of the request outside basic constraints, key usage, extended key usage, names, key identifiers, CRL distribution points, authority information access, certificate policies, name constraints and SCT.

### Export Certificate
```http
# PEM format (certificate only)
GET /api/v2/certificates/{cert_id}/export?format=pem

# PEM with private key: POST with a JSON body, as for every export carrying a key
POST /api/v2/certificates/{cert_id}/export
{"format": "pem", "include_key": true}

# PKCS12 (PFX): POST with a JSON body, the password never goes in the query string
POST /api/v2/certificates/{cert_id}/export
{"format": "pkcs12", "password": "export-password", "include_chain": true}

# Include the self-signed Root CA as an explicit opt-in
POST /api/v2/certificates/{cert_id}/export
{"format": "pkcs12", "password": "export-password", "include_chain": true, "include_root": true}

# PKCS12 compatibility profile (3DES/SHA-1) for Android 15 and earlier, macOS 14 and
# earlier, Windows Server 2016 and earlier, Java before 8u301 / 11.0.1 (#331)
POST /api/v2/certificates/{cert_id}/export
{"format": "pkcs12", "password": "export-password", "legacy": true}

# PEM with the private key encrypted (PKCS#8): POST only, 8 to 256 characters
POST /api/v2/certificates/{cert_id}/export
{"format": "pem", "include_key": true, "password": "export-password"}

# DER format
GET /api/v2/certificates/{cert_id}/export?format=der

# TLS chain: leaf plus intermediates, without the self-signed trust anchor
GET /api/v2/certificates/{cert_id}/export?format=pem&include_chain=true
```

`include_chain` applies to PEM, PKCS#7, PKCS#12/PFX and JKS exports. When it is
`true`, `include_root` controls whether the final self-signed Root CA is also
packaged. `include_root` defaults to `false`, because a TLS server normally sends
the leaf and intermediate certificates while clients keep the Root CA in their
trust store. Both options, as well as `include_key` and `legacy`, must be actual
JSON booleans in POST bodies; strings such as `"false"` are rejected.

`include_key` with `der`, `pkcs7` or `p7b`, and `include_chain` with `der`, answer `400`
naming the field: those formats carry no key, and DER a single certificate.

**Where the options go.** The exports that can return a private key (this route, Export CA, Export User Certificate, the CSR export, the mTLS download and the key recovery download) read only the options their section lists, spelled exactly: from the query string of a `GET`, which carries no body, or from the JSON object body (`Content-Type: application/json`) of a `POST`, whose query string stays empty. Anything else answers `400`: a body on a GET (chunked included), a POST body that is a form, `text/plain` or a JSON value that is not an object, a POST without a body, an option in the query string of a POST, a name the route does not list (named in the message, its value never repeated), an option given twice (in the query string, or as a name repeated in any object of the JSON body), a body that is not valid UTF-8 JSON, a value of another type and a format the route does not know. Booleans are JSON booleans in a body and `true` or `false` in a query string; `format`, `chain_variant` and `password` are strings (a `null` password reads as none). `password` and `legacy` are read from a POST body only. A HEAD is read like a GET and never returns a key.

Options of this route: `format` (`pem` by default, `der`, `pkcs7`, `p7b`, `key`, `pkcs12`, `pfx`, `jks`, `hybrid-bundle`), `include_key`, `include_chain`, `include_root`, `password`, `legacy`, `chain_variant`. A private key leaves it only through a POST: a GET that asks for one (`include_key=true`, `format=key`, `pkcs12`, `pfx`, `jks`) answers `400`.

The `password` encrypts every private key the response carries: required for `pkcs12`, `pfx` and `jks`; optional for `key`, `hybrid-bundle` and `pem` with `include_key`, where the key is PKCS#8 encrypted when one is given and written in clear when not. A `password` that is not a string, or outside the rule (8 to 256 characters and at most 1023 bytes in UTF-8, valid Unicode), answers `400` whatever the format, `der` and `pkcs7` included; a valid one is ignored when the output carries no private key (`der`, `pkcs7`/`p7b`, `pem` without `include_key`). The `private_key_exported` audit entry says `password-protected` or `unencrypted` accordingly. `legacy` applies to PKCS#12/PFX only: the JKS format keeps its own protection (Sun key protector and SHA-1 integrity digest) whatever `legacy` says.

`chain_variant` (`auto` by default, `primary`, or `cross:<id>`) picks the chain a cross-certificate makes
possible; it is read from the JSON body or the query string. The variants of a certificate are listed in
`chain_status.variants` of `GET /api/v2/certificates/{cert_id}`. An unknown value, or one that is not part of
the chain, answers 400.

`format=hybrid-bundle` returns a ZIP holding both members of a hybrid pair, named
`<hybrid_role>-<id>.crt`, plus `<hybrid_role>-<id>.key` with `include_key` (encrypted with
`password` when one is given). A certificate without a related one answers `400`, and so does
`include_key` when either member has no private key.

### Renew Certificate
```http
POST /api/v2/certificates/{cert_id}/renew
Content-Type: application/json

{
  "validity_days": 365
}
```

Renewing a member of a hybrid pair renews both, and the new B names the new A, since the
server holds both keys and renews the pair as one; the response
lists the other member in `related_renewed`. A certificate renewed alone names only the
certificate its original named (RFC 9763 §4.1): once that one is replaced, revoked, archived or
expired, the renewed certificate carries no `relatedCertificate` extension, leaves its pair, and
`meta.notices` says why. A renewal answers `409`, naming the certificate, when its own stored certificate, the other member's
certificate or the renewed certificate's own `relatedCertificate` extension cannot be read;
nothing is written and the pair stays as it is. When the two members require approval under
different policies, the renewal answers `409` and only an administrator can perform it. A
certificate or a pair link changed by another request while the renewal runs also answers
`409`: reload the certificate and retry. A certificate issued by a Microsoft CA is renewed through its connection; there, a Kerberos sign-in that fails answers `400` with its cause, and the certificate and its requests are left as they were.

### Revoke Certificate
```http
POST /api/v2/certificates/{cert_id}/revoke
Content-Type: application/json

{
  "reason": "keyCompromise",
  "comments": "Private key was exposed",
  "invalidity_date": "2026-07-10T12:00:00Z"
}
```

Optional **`invalidity_date`** / **`invalidity_at`** (ISO 8601): RFC 5280 §5.3.2 date on which the certificate became invalid (may precede revocation). Emitted as CRL entry `invalidityDate` when set.

**`revoke_related`** (JSON boolean, default `true`): revoking a member of a hybrid pair revokes the
other one too, reported as `related_revoked` (its id). `false` keeps it, except under a policy that
requires approval, which revokes both: such a request answers `400` for a non-administrator. Two
different approval policies on the two members answer `409`. When the other member could not be
revoked, the certificate stays revoked and the answer carries `related_not_revoked` (its id) and a
message asking to revoke it separately.

**Revocation Reasons** (RFC 5280 §5.3.1; an unknown value is rejected with `400`, snake_case spellings such as `key_compromise` are accepted and stored in the canonical form):
- `unspecified` (default when omitted)
- `keyCompromise`
- `cACompromise`
- `affiliationChanged`
- `superseded`
- `cessationOfOperation`
- `certificateHold` (temporary; can be lifted via unhold)
- `privilegeWithdrawn`
- `aACompromise`

### Unhold Certificate (lift certificateHold)
```http
POST /api/v2/certificates/{cert_id}/unhold
```

Requires reason `certificateHold` / `certificate_hold`. When the issuing CA has delta CRL enabled, UCM emits a delta entry with reason `removeFromCRL` (RFC 5280 §5.3.1) before regenerating the full CRL. Until the hold is lifted, OCSP and the full CRL still answer `certificateHold`.

**`unhold_related`** (JSON boolean, default `true`): lifting the hold on a member of a related pair also lifts
the other member when it is on hold for `certificateHold`; a partner revoked for another reason stays revoked.
The response carries `related_unheld` (the partner's id) when it was lifted, and each lifted certificate emits
a `certificate.unheld` event. A request body that is not a JSON object is refused with 400 (415 for a
non-JSON media type). `GET /api/v2/certificates/{cert_id}` reports in `related_on_hold_id` the partner an
unhold would lift, or `null`.

### Lift a Local Revocation
```http
POST /api/v2/certificates/{cert_id}/lift-local-revocation
Content-Type: application/json

{"confirm": true}
```

Requires `admin:system`. Lifts a revocation no relying party ever saw: the issuing CA is held in UCM
without its key (an imported public CA), is not offline, has no delegated OCSP responder, and held none
of them when the revocation was recorded or since, so UCM never signed a CRL or an OCSP answer carrying
it; an external CRL UCM serves for the CA does not list it. Every stored copy of the certificate (same serial
under the CA or a record of its key) becomes valid again and the serial's revocation records are
deleted, so neither an import nor the hourly repair revokes it again. Each lifted copy is audited
`certificate_local_revocation_lifted`. The answer is the certificate as `GET` returns it.

- `confirm` (JSON boolean, required `true`): `400` without it.
- `acknowledge_unknown_publication` (JSON boolean, default `false`): a record written before UCM noted
  whether it was published (an upgraded installation) is lifted only with it, since the CA may have held
  its key at the time; without it the answer is `409` and says the risk.
- `409` for a published revocation (the CA, or a record of its key, holds its key in UCM, software, HSM or
  key provider, is offline or has a delegated OCSP responder; or did at the write or since; or UCM signed
  a CRL for one of them after the revocation; or an external CRL it serves lists the serial): RFC 6960
  §2.2 and RFC 5280 §5.3.1 lift only a `certificateHold`, through unhold. Also `409` for a copy obtained
  from a Microsoft CA or over ACME (UCM tells that CA of the revocation), for a revoked certificate with no
  revocation record, for one linked to no CA in UCM, revoked again while the lift ran, or with a copy
  another operation is changing (try again); `400` for one not revoked. A key revoked as
  compromised stays refused after the lift; `500` when it could not be kept, nothing lifted.

`GET /api/v2/certificates/{cert_id}` reports `revocation_published` (whether a revocation reaches relying
parties: the issuing CA publishes revocations, the external CRL UCM serves for it lists the serial, or
the certificate comes from a Microsoft CA or over ACME; `false` lets a valid certificate be deleted
without revocation) and `local_revocation_lift`:
`local`, `unknown` (lift needs `acknowledge_unknown_publication`) or `null` (nothing to lift).

### Import Certificate
```http
POST /api/v2/certificates/import
Content-Type: application/json

{
  "certificate": "-----BEGIN CERTIFICATE-----\n...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...",
  "ca_id": 1
}
```

### Deploy Bindings Left Behind by a Renewal
```http
GET  /api/v2/deploy/bindings?certificate_id={id}
POST /api/v2/deploy/bindings/{binding_id}/reattach
```
When EST, SCEP or WSTEP renews a certificate into a new row whose key UCM does not hold, a binding that sends the
private key stays on the previous certificate. Each binding carries `needs_attention`, `null` or
`{reason: "successor_without_key", successor_id, successor_refid, successor_has_key, successor_archived,
can_reattach}`. `reattach` (scope `write:deploy`) moves the binding to the renewed certificate, clears the state and
deploys it; it answers 409 when the renewed certificate was itself superseded, while it has no key and the binding
sends one, or when the target is already bound to it. A later renewal of the renewed certificate moves the state to
the newest successor and sends a new `certificate.binding_left_behind` event when that one has no key either and the
binding sends the key; otherwise the state is cleared without an event and the binding moves to the successor, unless
its target is already bound to it. Uploading or
importing the renewed certificate's key moves such bindings on its own; deleting the binding or the renewed
certificate clears the state.

### Delete Certificate
```http
DELETE /api/v2/certificates/{cert_id}
```

A valid certificate is refused with `409` until it is revoked (by its row or by its serial's
revocation record), when its CA publishes revocations or it comes from a Microsoft CA or over ACME (UCM
tells that CA); any other certificate of a CA held without its key, or linked to no CA, is deleted
without revocation: no revocation would reach a relying party.
`POST /api/v2/certificates/bulk/delete` applies the same rule per id.

### Certificate Statistics
```http
GET /api/v2/certificates/stats
```

### Get Private Key
```http
POST /api/v2/certificates/{cert_id}/key
Content-Type: application/json

{
  "passphrase": "optional-passphrase"
}
```

### Export All Certificates
```http
GET /api/v2/certificates/export
POST /api/v2/certificates/export
```

An unreadable certificate is skipped, logged, and named in `X-Skipped-Certificates` (its first 100 ids) with the total in `X-Skipped-Certificates-Count`; the others are exported. When no certificate is readable the answer is `404` in both PEM and P7B, with `details.skipped` (the first 100) and `details.skipped_count` (the total).

### Bulk Revoke Certificates
```http
POST /api/v2/certificates/bulk/revoke
Content-Type: application/json

{
  "ids": [1, 2, 3],
  "reason": "keyCompromise",
  "revoke_related": true
}
```

`revoke_related` applies as for a single revocation; the ids of other members that could not be
revoked are listed in `related_not_revoked`, the certificates themselves counting as successes.
Bulk renewal also renews the other member of each hybrid pair; a member already renewed or
revoked with its pair counts as a success. What a renewal did on other terms, such as a
`relatedCertificate` extension left out, is listed in `notices` as `{"id", "notices"}` entries,
present only when there is one. A member whose pair cannot be read fails with the refusal of
a single renewal.

**Response:**
```json
{
  "data": {
    "success": [1, 2],
    "failed": [3]
  }
}
```

### Bulk Renew Certificates
```http
POST /api/v2/certificates/bulk/renew
Content-Type: application/json

{
  "ids": [1, 2, 3],
  "ca_id": 2
}
```

### Bulk Delete Certificates
```http
POST /api/v2/certificates/bulk/delete
Content-Type: application/json

{
  "ids": [1, 2, 3]
}
```

### Bulk Export Certificates
```http
POST /api/v2/certificates/bulk/export
Content-Type: application/json

{
  "ids": [1, 2, 3]
}
```

Returns the selected certificates as `format` `pem` (default) or `p7b`. `X-Exported-Count` holds the number of certificates in the file: unknown ids, certificate requests and unreadable ones are not counted.

An unreadable certificate is skipped, logged, and named in `X-Skipped-Certificates` (its first 100 ids) with the total in `X-Skipped-Certificates-Count`; the others are exported. When no certificate is readable the answer is `404` in both PEM and P7B, with `details.skipped` (the first 100) and `details.skipped_count` (the total).

### Certificate Metadata, Linting and Transparency
```http
PATCH /api/v2/certificates/{cert_id}
Content-Type: application/json

{ "descr": "Web server", "comment": "Owner: PKI team\nTicket INC-1234" }
```
Permission `write:certificates`. The display name and the comment change apart or together, and at least one of them is required. `descr` is a non-empty string of at most 255 characters. `comment` is plain text of at most 4,000 characters, kept as sent, with line feeds and tabs as its only control characters and no text direction control (U+061C, U+200E, U+200F, U+202A to U+202E, U+2066 to U+2069); `""`, `null` or a text of blanks only removes it. Neither field may hold a lone UTF-16 surrogate. An invalid field refuses the whole request with `400` and changes nothing; `404` for an unknown certificate. The answer is the certificate as `GET /api/v2/certificates/{id}` gives it. Every certificate read carries `comment` (`""` when there is none), and so does the `certificate` of every webhook event. A changed comment is audited as `certificate_comment_updated` with its former and new lengths, never its text.

```http
GET /api/v2/certificates/{cert_id}/lint?profile=rfc5280
GET /api/v2/certificates/lint/status
GET /api/v2/certificates/compliance
POST /api/v2/certificates/{cert_id}/submit-ct
POST /api/v2/certificates/export
```
- Reads need `read:certificates`. `lint` checks one stored certificate against `profile` (`rfc5280` by default, `cabf` or `etsi`; `400` for another); `422` when the certificate cannot be linted. `lint/status` reports which linters are available and the accepted `profiles`. `compliance` returns `average_score`, the grade `distribution` (`A+` to `F`) and `total` over the active certificates, named in `population` as on `/dashboard/compliance`, scored in SQL from the stored key, signature hash, SANs and dates.
- `submit-ct` (`write:certificates`) submits the certificate to the configured Certificate Transparency logs and returns the `logs` that accepted it with their `timestamp`. `400` when CT is not enabled in the [settings](#certificate-transparency), no valid log is configured, the certificate has no PEM, or no log accepted it.
- `POST /certificates/export` is the body form of `GET /certificates/export`: `format` (`pem` or `p7b`, else `400`), `password` and `include_chain`; `404` when there is nothing to export. The bulk export carries public certificates only, so `password` and `legacy` are ignored there, and `include_chain` is checked as a boolean (`400` otherwise) but adds nothing.

### Catalogs
```http
GET /api/v2/eku/known
GET /api/v2/revocation-reasons
GET /api/v2/export/password-policy
```
`eku/known` (`read:certificates`) returns the catalog of well-known Extended Key Usage OIDs. `revocation-reasons` (`read:certificates`) returns `reasons`, the CRLReason names the revocation routes accept (RFC 5280 section 5.3.1). `export/password-policy` (any authenticated user) returns `min_length` and `max_length`, the length rule every export route applies to its password.

---

## User Certificates (mTLS)

Manage mTLS client certificates enrolled via the Account page. These certificates are stored in the main `certificates` table (with `cert_type='usr_cert'`) and linked to users via `auth_certificates`.

**Permissions**: `read:user_certificates`, `write:user_certificates`, `delete:user_certificates`  
**Ownership**: Viewers see only their own certificates. Operators and admins see all.

### List User Certificates
```http
GET /api/v2/user-certificates
GET /api/v2/user-certificates?status=valid&page=1&per_page=50
```

**Query Parameters**:
| Param | Type | Description |
|-------|------|-------------|
| status | string | Filter by status: `valid`, `expiring`, `expired`, `revoked` (repeatable; `valid` does not include `expiring`). Applied before paging: `total` and `pages` count the matching rows only; an unknown value answers `400` |
| search | string | Name, subject or serial contains |
| sort_by | string | `created_at` (default), `name`, `valid_until`, `last_used_at`, `owner` (login), `status` (expired, expiring, valid, revoked, then a certificate no longer found); see [Sorting](#sorting) |
| sort_order | string | `asc` or `desc` (default); rows with no value in the sorted column come last in both directions |
| page | int | Page number (default: 1) |
| per_page | int | Items per page (default: 25) |

**Response** `200`:
```json
{
  "data": {
    "items": [
      {
        "id": 1,
        "cert_id": 52,
        "common_name": "admin@mtls",
        "cn": "admin@mtls",
        "status": "valid",
        "days_remaining": 364,
        "has_private_key": true,
        "created_at": "2026-02-20T19:05:19",
        "not_valid_after": "2027-02-20T19:05:19",
        "issuer": "CN=example.com,O=Example Org",
        "username": "admin"
      }
    ],
    "total": 1,
    "page": 1,
    "per_page": 50
  }
}
```

### User Certificate Stats
```http
GET /api/v2/user-certificates/stats
```

**Response** `200`:
```json
{
  "data": {
    "total": 5,
    "valid": 3,
    "expired": 1,
    "revoked": 1,
    "expiring_soon": 0
  }
}
```

### Get User Certificate
```http
GET /api/v2/user-certificates/{id}
```

**Response** `200`: Full certificate details including `common_name`, `cn`, `days_remaining`, `key_algorithm`, `signature_algorithm`, `serial_number`, `fingerprint`.

### Export User Certificate
```http
GET /api/v2/user-certificates/{id}/export?format=pem&include_chain=true
POST /api/v2/user-certificates/{id}/export
{"format": "pkcs12", "password": "mypassword", "include_chain": true, "include_root": false}
```

Options are read as described under Export Certificate (where the options go). Options of this route: those of the table below and `chain_variant`. A GET returns no key: its `include_key` defaults to false, and a request for a key there (`include_key=true`, `format=key`, `pkcs12`, `p12`, `pfx`, `jks`) answers `400`. With `format=pem` and `include_key`, a `password` (POST) encrypts the key as PKCS#8; without one the key is written in clear. `password` is not read when the output carries no private key (it is not checked either), the same rule applies to the ones that are read (400 for a value that is not a string, or outside 8 to 256 characters and 1023 bytes in UTF-8), and `legacy` applies to `pkcs12` only (a JKS keeps the Sun key protector and its SHA-1 integrity digest). Each export is audited as `user_certificate_exported`; an export of the key alone also writes `private_key_exported`.

**Query Parameters**:
| Param | Type | Description |
|-------|------|-------------|
| format | string | `pem` (default), `der`, `pkcs7` (or `p7b`), `key` (the private key alone, `.key`), `pkcs12` (`p12`, `pfx`) or `jks`; any other value is `400` |
| include_key | bool | Include private key (default: true in a POST, false for `der`, `pkcs7`, `p7b`, and false for a GET; `true` in a GET or with those formats is `400`) |
| include_chain | bool | Include CA chain (default: true, false for `der` and `key`; `true` with `der` is `400`) |
| include_root | bool | Include the final self-signed Root CA when the chain is included (default: false) |
| password | string | POST only. PKCS12 and JKS password (required, min 8 chars); optional for `key`, where it encrypts the key as PKCS#8 |
| legacy | bool | POST only. PKCS12 compatibility profile, 3DES/SHA-1 instead of AES-256/SHA-256 (default: false) |

**Response** `200`: Binary file download with `Content-Disposition` header. A name that is not ASCII is sent as an ASCII `filename` fallback plus `filename*=UTF-8''<percent-encoded name>` (RFC 6266); every export route named after an object does the same (a CRL keeps its ASCII name).

> **Note**: Auditors are explicitly blocked from exporting user certificates.

### Revoke User Certificate
```http
POST /api/v2/user-certificates/{id}/revoke
```

**Body**:
```json
{
  "reason": "unspecified"
}
```

**Reason values**: `unspecified`, `key_compromise`, `ca_compromise`, `affiliation_changed`, `superseded`, `cessation_of_operation`

**Response** `200`:
```json
{
  "message": "Certificate revoked successfully",
  "data": { ... }
}
```

### Delete User Certificate
```http
DELETE /api/v2/user-certificates/{id}
```

**Response** `204`: No content.

> **Note**: Only admins and operators can delete. Deletes both the `auth_certificates` link and the underlying certificate.

---

## Certificate Signing Requests

### List CSRs
```http
GET /api/v2/csrs
GET /api/v2/csrs?status=pending&page=1&per_page=50
```
Both CSR lists (this one and the [history](#csr-history-signed-csrs)) take `search` and sort by `sort_by`: `created_at` (default, with `sort_order` `desc`), `id`, `cn`, `requester`, `key_type`, `signed_at`, `valid_to`; see [Sorting](#sorting).

### Generate CSR
```http
POST /api/v2/csrs
Content-Type: application/json

{
  "cn": "server.example.com",
  "organization": "My Company",
  "country": "US",
  "state": "California",
  "locality": "San Francisco",
  "key_type": "EC P-256",
  "sans": ["DNS:server.example.com", "IP:192.168.1.10"]
}
```

UCM generates the key pair and keeps the private key. The subject takes `cn` (required), `organization`, `department` (OU), `country`, `state`, `locality` and `email` (a string, trimmed, an ASCII address); each is validated and a refused value answers `400`. `key_type` is `RSA 2048`, `RSA 3072`,
`RSA 4096`, an EC curve (`EC P-256`, `EC P-384`, `EC P-521`, Brainpool), or `ML-DSA-44`,
`ML-DSA-65` or `ML-DSA-87`; an unknown value answers `400`. To submit an existing CSR, use
`POST /api/v2/csrs/upload` below.

`related_to` (certificate id) adds an RFC 9763 relatedCertRequest signed by the key of that
certificate A, which UCM must hold; a revoked or unknown A, or one without its key, answers `400`.
It requires the `read:private_keys` permission (`403` otherwise), and each use of A's key is
audited as `certificate_key_used` on A.

### Get CSR Details
```http
GET /api/v2/csrs/{csr_id}
```

### Sign CSR (Issue Certificate)
```http
POST /api/v2/csrs/{csr_id}/sign
Content-Type: application/json

{
  "ca_id": 2,
  "validity_days": 365,
  "template_id": 1
}
```

`custom_extensions` adds extensions to the template's, as on `POST /api/v2/certificates`; the template's apply to end-entity certificates only. Extensions the CSR itself asks for outside the usual ones are not copied.

A CSR carrying a relatedCertRequest (RFC 9763), here or through ACME, EST or WSTEP, issues a
certificate linked to the A it names. A must be held here, valid, unrevoked and an end-entity
certificate issued by a CA of this instance whose chain passes RFC 5280 path checks now (validity,
`cA`, `pathLenConstraint`, `keyCertSign`), the request must be at most 7 days old and verify with
A's key, and the new certificate may assert no key usage or EKU that A lacks; otherwise `400`.
A request serves the first key it is presented with: the same key again (a retried enrolment) is
accepted, another key is refused with `400`. A's own link moves to the newest such certificate; the previous one keeps
naming A but no longer revokes or renews with it.

### Delete CSR
```http
DELETE /api/v2/csrs/{csr_id}
```

### Upload CSR (Multipart)
```http
POST /api/v2/csrs/upload
Content-Type: application/json

{
  "pem": "-----BEGIN CERTIFICATE REQUEST-----\n...",
  "name": "My Server CSR"
}
```

### Import CSR (File Upload)
```http
POST /api/v2/csrs/import
Content-Type: multipart/form-data

file: <CSR file>
name: "My Server CSR"
```

Alternatively, via JSON body:
```http
POST /api/v2/csrs/import
Content-Type: application/json

{
  "pem_content": "-----BEGIN CERTIFICATE REQUEST-----\n...",
  "name": "My Server CSR"
}
```

### CSR History (Signed CSRs)
```http
GET /api/v2/csrs/history
GET /api/v2/csrs/history?page=1&per_page=50
```

### Export CSR
```http
GET /api/v2/csrs/{csr_id}/export
```

Returns the CSR as a PEM file download.

### Attach Private Key to CSR
```http
POST /api/v2/csrs/{csr_id}/key
Content-Type: application/json

{
  "key": "-----BEGIN PRIVATE KEY-----\n...",
  "passphrase": "optional-passphrase"
}
```

### Bulk Sign CSRs
```http
POST /api/v2/csrs/bulk/sign
Content-Type: application/json

{
  "ids": [1, 2, 3],
  "ca_id": 2,
  "validity_days": 365
}
```

**Response:**
```json
{
  "data": {
    "success": [1, 2],
    "failed": [{"id": 3, "error": "Already signed"}]
  }
}
```

A request that met another write on SQLite is listed in `failed` with the error `The database is busy with another write: retry shortly.`: nothing was stored for it, and the requests after it are still signed. Send it again.

### Bulk Delete CSRs
```http
POST /api/v2/csrs/bulk/delete
Content-Type: application/json

{
  "ids": [1, 2, 3]
}
```

### CSR Export (body form) and Resubmission
```http
POST /api/v2/csrs/{csr_id}/export
Content-Type: application/json

{ "format": "csr" }
```
Permission `read:csrs`. `format` is `csr` (default) or `key` (the private key, with an optional `password` for an encrypted export, which follows the shared export password rule: 8 to 256 characters, `400` otherwise; an empty one means an unencrypted key). With `format=csr` a `password` is ignored: a request holds no secret. Options are read as described under Export Certificate (where the options go). Options of this route: `format` and, in a POST body, `password`. `GET /api/v2/csrs/{csr_id}/export?format=key` returns the key in clear; a password goes in a POST body only. `400` when the CSR has no private key for `key`; `404` for an unknown CSR.

```http
POST /api/v2/csrs/{csr_id}/resubmit
```
Permissions `write:csrs` and `read:certificates`. Puts a signed request back in the pending list so it can be signed again. `201` with the new pending request, `200` when one is already pending, `400` when the stored request cannot be read, `404` when the signed request is not found.

---

## Templates

### List Templates
```http
GET /api/v2/templates
```

### Create Template
```http
POST /api/v2/templates
Content-Type: application/json

{
  "name": "Web Server",
  "description": "Template for web server certificates",
  "validity_days": 365,
  "key_size": 2048,
  "key_usage": ["digitalSignature", "keyEncipherment"],
  "extended_key_usage": ["serverAuth"],
  "basic_constraints": {
    "ca": false
  }
}
```

`key_type` is a registry label (`RSA-2048`, `RSA-3072`, `RSA-4096`, `EC-P256`, `EC-P384`,
`EC-P521`, `EC-BP256`, `EC-BP384`, `EC-BP512`, `ML-DSA-44`, `ML-DSA-65`, `ML-DSA-87`). Other
spellings of these keys (`EC P-384`, `secp384r1`, `RSA 2048`) are normalised; an unknown key
answers `400`. `digest` is the issuing CA's signing hash, so it still applies to an
ML-DSA key under an RSA or EC CA, and an ML-DSA CA ignores it.

**qcStatements and policy OIDs (ETSI EN 319 412-5).** `extensions_template` accepts two optional keys, validated on create, update and import:

```json
"extensions_template": {
  "certificate_policies": ["0.4.0.194112.1.2"],
  "qc_statements": {
    "compliance": true,
    "type": "esign",
    "sscd": true,
    "pds": [{"url": "https://pki.example.com/pds-en.pdf", "language": "en"}],
    "retention_period": 15,
    "limit_value": {"currency": "EUR", "amount": 10000, "exponent": 0},
    "semantics": "eidas-natural"
  }
}
```

- `certificate_policies`: up to 20 dotted OIDs, added after the CA's CPS policy.
- `qc_statements`: `compliance` is QcCompliance and `cc_legislation` (ISO 3166 country codes, QcCClegislation) names the non-EU legal framework of a qualified certificate, left out for an EU one; `type` is `esign`, `eseal` or `web`; `pds` entries need an `https` URL and a two-letter language, at most one per language, and an EU qualified certificate (QcCompliance without QcCClegislation) needs one in English; `semantics` is `natural`, `legal`, `eidas-natural` or `eidas-legal` (RFC 3739 semantics identifier). Unknown keys are refused.
- Certificates issued from the UI, Sign CSR (single and bulk), ACME, SCEP and approvals carry both; renewals keep them. EST, WSTEP and mTLS enrollment do not add them. `GET /api/v2/certificates/{id}` decodes the extension under `extensions.qc_statements`, and `GET /api/v2/certificates/{id}/lint?profile=etsi` runs the ETSI EN 319 412 checks.

**Custom extensions (#437).** `custom_extensions` adds extensions UCM does not model, each given by its OID and the DER bytes of its value:

```json
"custom_extensions": [
  {"oid": "1.3.6.1.4.1.99999.1", "critical": false, "value": "0c0568656c6c6f"}
]
```

- `value` is the DER encoding of the extension value (the content of `extnValue`) in hex; colons and spaces are ignored. `value_base64` may be given instead. It must be a single DER element (tag, minimal definite length, content of that length); UCM checks nothing more and copies the bytes as they are. Stored and returned as lowercase hex in `value`.
- `critical` defaults to `false`. A client that does not recognise a critical extension must reject the certificate (RFC 5280, section 4.2): mark one critical only when every relying party understands it.
- `400` for an OID that is not dotted (`1.2.840...`), an empty value, a value above 4096 bytes, more than 20 entries, the same OID twice, or an extension UCM sets itself or parses (basic constraints, key usage, extended key usage, names, key identifiers, CRL distribution points, authority and subject information access, certificate policies, name constraints, TLS feature, OCSP no-check, SCT, qcStatements, relatedCertificate, the Microsoft template and SID extensions...): those keep their dedicated settings. The rule is "set by UCM or parsed by the X.509 library": any other OID is accepted, an unparsed `2.5.29.x` included.
- `[]` clears the list. Duplicate, export, import and backups carry it. A stored list that no longer validates (a restored or hand-edited row) is reported in `custom_extensions_error`, and issuance from the template is refused until it is fixed: `400` with the reason for an operator, `serverInternal` without the template's name for an ACME client, `badRequest` for SCEP (RFC 8894 has no server-side failInfo).
- Certificates issued from the template carry the list: issue form, Sign CSR (single and bulk, end-entity certificates only), ACME profiles bound to the template, SCEP profiles, WSTEP (the matched template) and approvals. EST and mTLS enrollment use no template and add none.

**Common name pattern (Windows enrollment).** `subject_cn_pattern` (text, at most 255 characters, `null` or blank for none) and `subject_cn_keep_path` (boolean, default `false`) set the CN of certificates issued over the WSTEP Kerberos binding, and of their renewals, for a template whose subject UCM builds: a computer type (`web_server`, `vpn_server`, `vpn_client`, `ocsp_signing`) or one with `ad_derived_subject`.

- Variables in braces, read from the requester's directory object: `{hostname}` and `{fqdn}` for a computer type; `{username}`, `{upn}`, `{mail}`, `{displayName}`, `{givenName}` and `{surname}` for a user template; `{domain}` and `{realm}` for both. `{{` and `}}` are literal braces.
- `400` on create, update and import (where the template is skipped with the reason) for an unknown variable, a variable of the other kind, a stray brace, a control character, or a pattern on a template whose requester supplies the subject. An update is judged on the template it leaves: changing `template_type` or `ad_derived_subject` under a pattern is refused the same way.
- Saving does not check that a pattern tells accounts apart; issuance does. A subject built by the pattern that a certificate of the same CA, whatever its status, already carries without the requester's SID in its SID extension is refused at issuance, renewal and approval (see the Administrator Guide, "Windows enrollment: common name pattern").
- Duplicate, export, import and backups carry both fields. With a pattern, the policy announces the template's SAN flags without the subject flag (`0x08000000` for a computer, `0x02000000` for a user).

### Get Template
```http
GET /api/v2/templates/{template_id}
```

### Update Template
```http
PUT /api/v2/templates/{template_id}
Content-Type: application/json

{
  "name": "Updated Web Server",
  "validity_days": 730
}
```

### Delete Template
```http
DELETE /api/v2/templates/{template_id}
```

### Bulk Delete Templates
```http
POST /api/v2/templates/bulk/delete
Content-Type: application/json

{
  "ids": [1, 2, 3]
}
```

### Export Single Template
```http
GET /api/v2/templates/{template_id}/export
```

Returns the template as a JSON file.

### Export All Templates
```http
GET /api/v2/templates/export
```

Returns all templates as a JSON array.

### Import Templates
```http
POST /api/v2/templates/import
Content-Type: multipart/form-data

file: <template JSON file>
update_existing: true
```

Alternatively, via JSON body:
```http
POST /api/v2/templates/import
Content-Type: application/json

{
  "json_content": "[{...}]",
  "update_existing": true
}
```

**Response:**
```json
{
  "data": {
    "imported": 2,
    "updated": 1,
    "skipped": 0
  }
}
```

### Duplicate a Template
```http
POST /api/v2/templates/{template_id}/duplicate
```
Permission `write:templates`. Creates a copy named `<name> (Copy)` (numbered when that name is taken); `201`, `404` for an unknown template.

---

## Trust Store

### List Trusted Certificates
```http
GET /api/v2/truststore
```

### Add Trusted Certificate
```http
POST /api/v2/truststore
Content-Type: application/json

{
  "certificate_pem": "-----BEGIN CERTIFICATE-----\n...",
  "name": "External Root CA",
  "description": "Third-party CA for partner integration"
}
```
The trust store holds certificates only: an entry that contains a private key (any `... PRIVATE KEY` block, encrypted or not, or a PuTTY key file) is refused with `400` and `A trust store holds certificates only; remove the private key`, and so is an entry with a `CERTIFICATE` (or legacy `X509 CERTIFICATE`) block that cannot be read or is left open; other blocks and the text around are left out. A certificate offered under the legacy label is stored and returned under `CERTIFICATE`. The entry is judged and fingerprinted by its first certificate and stored as its certificates re-encoded in PEM; other text is dropped. `certificate_pem` in the list and the detail holds only certificates. The same rules apply to the file upload below.

### Get Trusted Certificate
```http
GET /api/v2/truststore/{cert_id}
```

### Delete Trusted Certificate
```http
DELETE /api/v2/truststore/{cert_id}
```

### Sync with System
```http
POST /api/v2/truststore/sync
```

### Trust Store Statistics
```http
GET /api/v2/truststore/stats
```

**Response:**
```json
{
  "data": {
    "total": 25,
    "root_ca": 10,
    "intermediate_ca": 12,
    "expired": 3,
    "valid": 22
  }
}
```

### Import Trusted Certificate (File Upload)
```http
POST /api/v2/truststore/import
Content-Type: multipart/form-data

file: <certificate file>
name: "External Root CA"
purpose: "root_ca"
description: "Third-party CA"
notes: "Optional notes"
```
A PEM or DER file; a file that contains a private key is refused with `400` as above.

### Trust Store Bulk Operations
```http
POST /api/v2/truststore/add-from-ca/{ca_refid}
POST /api/v2/truststore/bulk/delete
GET /api/v2/truststore/expiring?days=90
GET /api/v2/truststore/export?format=pem&purpose=all
```
- `add-from-ca` (`write:truststore`) adds a managed CA's certificate. Optional body `purpose` (default `root_ca` for a root, else `intermediate_ca`) and `notes`. `201`; `409` when it is already there, `400` when the CA awaits its certificate or the purpose is invalid, `404` for an unknown CA.
- `bulk/delete` (`delete:truststore`) takes `{"ids": [1, 2]}` (a non-empty list of at most 100) and returns `success` (the removed ids) and `failed` (`{id, error}`).
- `expiring` (`read:truststore`) lists trusted certificates expiring within `days` (default 90).
- `export` (`read:truststore`) downloads a bundle: `format` `pem` (default) or `p7b`, `purpose` filters (default `all`; repeat it to keep several purposes) and `expiry` (`expired`, `expiring` or `valid`, repeatable, `400` for another value; under a day left counts as expired and up to 90 days as expiring, as the page lists them). `404` when nothing matches. Unreadable entries are skipped and named in `X-Skipped-Certificates` and `X-Skipped-Certificates-Count` (first 100 ids and the total); `404` also when none is readable, with `details.skipped` (the first 100) and `details.skipped_count` (the total).

---

## ACME Server

### Get Settings
```http
GET /api/v2/acme/settings
```

### Update Settings
```http
PATCH /api/v2/acme/settings
Content-Type: application/json

{
  "enabled": true,
  "issuing_ca_id": 2,
  "validity_days": 90,
  "require_approval": false,
  "profiles": {
    "mtls": {
      "description": "client certificate",
      "validity_days": 30,
      "digest": "sha256",
      "template_id": 4
    }
  }
}
```

`profiles` holds the certificate profiles advertised in the ACME directory (draft-ietf-acme-profiles), keyed by the name a client sends in `profile`. `template_id` (optional) binds a certificate template: its key usage and extended key usage govern every certificate issued under the profile, while validity and digest stay those of the profile. CA templates and templates carrying OCSP signing, timestamping, any-purpose or smartcard logon EKUs are refused (400), and a bound template cannot be deleted until the profile is unbound. `GET` returns the profiles with `template_id` (null when unbound).

### Alternate chains (RFC 8555 section 7.4.2)
```http
POST /acme/cert/{order_id}
POST /acme/cert/{order_id}/alt/{variant}
```

The certificate is served with the default chain (`auto`: the served cross-certificate when there is one,
otherwise the primary chain). Every other servable chain is offered in a `Link: <.../acme/cert/{order_id}/alt/{variant}>;rel="alternate"`
header, `variant` being `primary` or `cross:<id>`. The alternate route applies the same checks as the main
one (account, ownership, order state, exact URL, JWS) and answers `404` for a chain that is not offered.
A client picks one with `certbot --preferred-chain`, which matches the CN of the issuer of the topmost
certificate; `auto` is tried first.

### Get Statistics
```http
GET /api/v2/acme/stats
```

### List ACME Accounts
```http
GET /api/v2/acme/accounts?page=1&per_page=100&sort_by=created_at&sort_order=desc
```
`data` is the list of accounts; `meta` carries `total`, `page` and `per_page` (default 100, 100 at most). `sort_by`: `created_at` (default, newest first), `account_id`, `status` (valid, deactivated, revoked), `contact`, `orders` (the number of orders); see [Sorting](#sorting).

### List ACME Orders
```http
GET /api/v2/acme/orders
GET /api/v2/acme/orders/{order_pk}
```
The list filters on `status` and `domain`, pages with `page` and `per_page` (default 50) and sorts by `sort_by`: `created_at` (default, newest first), `expires`, `status` (pending, ready, processing, valid, invalid), `account`, `domain`; see [Sorting](#sorting). The second form reads one local order (`read:acme`), whatever its age; 404 when it does not exist.

### ACME Proxy Upstream Account
The proxy's upstream account is a CA account of the [ACME Client](#acme-client-lets-encrypt) (`acme_account_id`, or the one selected as proxy account).

```http
POST /api/v2/acme/client/proxy/register
Content-Type: application/json

{
  "email": "admin@example.com",
  "acme_account_id": 1
}
```
Permission `write:acme`. Registers the upstream account with its CA. `email` falls back to the account's own; it must be a valid address on a public domain (`400` for `.local`, `.lan`, `.internal`). `502` when the upstream CA refuses the registration. Returns `registered`, `email`, `account_url`, `acme_account_id` and `account`.

```http
POST /api/v2/acme/client/proxy/unregister
```
Permission `write:acme`. Body `acme_account_id` optional. Clears the upstream registration (the account row stays). Returns `registered: false`.

```http
POST /api/v2/acme/client/proxy/test-connection
```
Permission `read:acme`. Body `acme_account_id` or `url` optional (otherwise the proxy account's directory). The URL must be HTTPS and not target loopback or cloud metadata (`400`). Returns `connected`, `ca_name`, `directory_url`, `terms_of_service`, `website`, `eab_required` and `endpoints`; `502` when the directory cannot be fetched.

### ACME Server Accounts
`{account_id}` is the numeric id or the RFC 8555 account id. Unknown accounts answer `404`.

```http
POST /api/v2/acme/accounts
Content-Type: application/json

{ "email": "ops@example.com", "key_type": "...", "agree_tos": true }
```
Permission `write:acme`. `email` is required (`400`); `key_type` must be one of the accepted account key types (`400` lists them); an existing email answers `409`.

```http
GET /api/v2/acme/accounts/{account_id}
PATCH /api/v2/acme/accounts/{account_id}
DELETE /api/v2/acme/accounts/{account_id}
POST /api/v2/acme/accounts/{account_id}/deactivate
GET /api/v2/acme/accounts/{account_id}/orders
GET /api/v2/acme/accounts/{account_id}/challenges
```
`GET` (account, orders, challenges) needs `read:acme`. `PATCH` needs `write:acme` and a string `email` (the contact address; `400` when absent or too long). `DELETE` needs `delete:acme` and removes the account with its orders, authorizations and challenges. `deactivate` needs `write:acme`.

### ACME Server Orders and History
```http
DELETE /api/v2/acme/orders/{order_pk}
POST /api/v2/acme/orders/purge
GET /api/v2/acme/history?source=all
```
`DELETE` (`delete:acme`) removes one local order with its authorizations and challenges (`404` when unknown). `purge` (`delete:acme`) runs the expired-order purge now and returns the counts of orders, authorizations and challenges removed. `history` (`read:acme`) lists certificates issued through ACME, local and external CAs; `source` filters. `history` filters on `status` (`valid` or `revoked`), `ca` (an issuer name listed in `meta.cas`) and `search`, sorts by `sort_by` (`common_name`, `valid_to`, `source`, `status`, `created_at`; `status` puts valid before revoked) and `sort_order` (rows with no value come last in both directions), and pages with `page` and `per_page` (default 50, 100 at most); `meta` carries `total` and `cas`.

### External Account Binding
```http
GET /api/v2/acme/eab-credentials?status=active
POST /api/v2/acme/eab-credentials
GET /api/v2/acme/eab-credentials/{cred_id}
PATCH /api/v2/acme/eab-credentials/{cred_id}
DELETE /api/v2/acme/eab-credentials/{cred_id}
GET /api/v2/acme/eab-required
PATCH /api/v2/acme/eab-required
PUT /api/v2/acme/eab-required
```
Reads need `read:acme`, writes `write:acme`, `DELETE` `delete:acme`. `POST` body: optional `label` (255 characters at most), `expires_in_days` (a positive integer, `400` otherwise) and `allowed_domains` (a list of patterns, `["*"]` for any); the response carries the credential and, once only, its `hmac_key`. `PATCH` changes `allowed_domains` (never `null`) and `notes`. `DELETE` revokes an active credential (and its DNS UPDATE keys); a credential already revoked or used is deleted for good (`204`). The list never shows an `hmac_key`; it pages with `page` and `per_page` (default 200, 200 at most), `meta` carries `total`, and it sorts by `sort_by`: `created_at` (default, newest first), `label`, `kid`, `status`, `expires_at`, `used_at` (see [Sorting](#sorting)). `eab-required` reads or sets `{"eab_required": true}` (`PATCH` and `PUT` are the same route).

---

## SCEP

### Get Configuration
```http
GET /api/v2/scep/config
```

Response:
```json
{
  "data": {
    "enabled": true,
    "ca_id": 2,
    "auto_approve": false,
    "challenge_validity": 24
  }
}
```

### Update Configuration
```http
PATCH /api/v2/scep/config
Content-Type: application/json

{
  "enabled": true,
  "ca_id": 2,
  "auto_approve": false,
  "challenge_validity": 24
}
```

### Get Statistics
```http
GET /api/v2/scep/stats
```

### List Requests
```http
GET /api/v2/scep/requests
GET /api/v2/scep/requests?status=pending&search=host&page=2&per_page=50
GET /api/v2/scep/requests/{request_id}
```
The list is newest first and paged: `page` and `per_page` (default 50, 100 at most), `meta` carries `total` and `total_pages`; `sort_by` takes `created_at` (default), `status` (pending, approved, rejected), `subject`, `transaction_id` or `client_ip` (see [Sorting](#sorting)); `status` (repeatable: `pending`, `approved` or `rejected`, `400` for any other value) and `search` (subject, transaction ID or client address) filter before the page is cut. The last form reads any one request (`read:scep`), 404 when it does not exist.

### Approve Request
```http
POST /api/v2/scep/{request_id}/approve
```

### Reject Request
```http
POST /api/v2/scep/{request_id}/reject
Content-Type: application/json

{
  "reason": "Invalid device"
}
```

### List Challenge States
```http
GET /api/v2/scep/challenges
```
Needs `read:scep`. One entry per CA: `ca_id`, `configured`, `expired`, `generated_at` and `expires_at` (`null` when unknown). The secret is never returned and the listing writes no audit entry.

### Get Challenge Password
```http
GET /api/v2/scep/challenge/{ca_id}
```
Needs `write:scep`. Returns the secret and records one `scep_challenge_read` audit entry per call.

### Regenerate Challenge Password
```http
POST /api/v2/scep/challenge/{ca_id}/regenerate
```

### SCEP Profiles
A profile serves SCEP at `/scep/<url_slug>/pkiclient.exe` with its own CA, template and challenge. Reads need `read:scep`, changes `write:scep` (including `DELETE`). Challenge passwords are never returned.

```http
GET /api/v2/scep/profiles
POST /api/v2/scep/profiles
PATCH /api/v2/scep/profiles/{profile_id}
PUT /api/v2/scep/profiles/{profile_id}
DELETE /api/v2/scep/profiles/{profile_id}
POST /api/v2/scep/profiles/{profile_id}/challenge/regenerate
```
- Writable fields: `name` (required, 100 characters at most, unique), `url_slug` (1 to 64 lowercase letters, digits and hyphens, unique; derived from `name` when omitted), `description` (255 at most), `enabled` (default true), `ca_id` or `ca_refid` (required; the CA must be able to serve SCEP), `template_id` (not a CA template, not disabled), `auto_approve` (default false), `challenge_password`, `intune_enabled` and `intune_app_id`. `PATCH` and `PUT` are the same partial update. Each list item adds `ca_name` and `template_name`.
- `DELETE` answers `409` while requests that came through the profile are pending.
- `challenge/regenerate` returns a fresh `challenge` once.
- `400` carries the reason for an invalid field; `409` an Intune configuration conflict.

### Intune App Registrations
Microsoft Entra app registrations that SCEP profiles use to validate Intune requests. Client secrets are stored encrypted and never returned. Reads need `read:scep`, writes `write:scep`.

```http
GET /api/v2/scep/intune-apps
POST /api/v2/scep/intune-apps
PATCH /api/v2/scep/intune-apps/{app_id}
PUT /api/v2/scep/intune-apps/{app_id}
DELETE /api/v2/scep/intune-apps/{app_id}
POST /api/v2/scep/intune-apps/test
POST /api/v2/scep/profiles/test-intune-connection
```
- `POST` takes `name`, `tenant_id`, `client_id` and `client_secret` (all required: `400`); a name, or a tenant and client pair, already in use answers `409`. `PATCH` and `PUT` are the same partial update; a blank `client_secret` keeps the saved one. `DELETE` answers `409` while a profile uses the app.
- `test` checks the credentials, either the submitted `tenant_id`, `client_id` and `client_secret` or a saved app by `app_id`; `400` with the reason when the check fails.
- `profiles/test-intune-connection` is the older form of the same test, which takes the profile (`profile_id` or `intune_app_id`) or the `intune_tenant_id`, `intune_client_id` and `intune_client_secret` trio.

---

## EST

Management of the EST service (RFC 7030). The protocol itself is served under `/.well-known/est/`; see [Protocol and Health Endpoints](#protocol-and-health-endpoints).

```http
GET /api/v2/est/config
PATCH /api/v2/est/config
GET /api/v2/est/stats
```
- Reads need `read:est`, `PATCH` needs `write:est`.
- `GET` returns `enabled`, `ca_refid`, `ca_id`, `ca_name`, `username`, `password_set`, `validity_days`, `response_include_chain`, `csrattrs_legacy_encoding`, `allow_empty_username`, `ignore_challenge_password` and `labels` (RFC 7030 section 3.2.2 CA labels, each with `ca_refid` and `ca_name`).
- `PATCH` changes any of `enabled`, `ca_id` or `ca_refid` (`ca_id` wins when both are sent; `404` for an unknown CA, `400` when it cannot sign), `username`, `password` (stored hashed), `validity_days` (an integer), and `labels` (an object of at most 50 labels, each a CA refid or `{ca_refid}`). `csrattrs_legacy_encoding`, `allow_empty_username` and `ignore_challenge_password` must be JSON booleans (`400` otherwise).
- `stats` returns `total`, `successful` and `failed` enrollments counted from the audit log.

---

## Time Stamping (TSA)

Management of the RFC 3161 time-stamp authority. The protocol is served at `/tsa`; see [Protocol and Health Endpoints](#protocol-and-health-endpoints). Reads need `read:settings`, `PATCH` needs `write:settings`.

```http
GET /api/v2/tsa/config
PATCH /api/v2/tsa/config
GET /api/v2/tsa/signer-candidates
POST /api/v2/tsa/signer-certificate
GET /api/v2/tsa/stats
```
- `GET /config` returns `enabled`, `ca_refid`, `ca_id`, `ca_name`, `policy_oid`, `require_dedicated_cert` (`true` unless set to `false`: the CA certificate signs only then, which RFC 3161 does not allow), `signer_cert_refid` (empty when no dedicated signer is set) and `signer` (subject, serial, expiry, chain status and usability of the configured signer).
- `PATCH /config` changes any of `enabled`, `ca_id` or `ca_refid`, `policy_oid` (`400` unless a valid OID), `require_dedicated_cert` and `signer_cert_refid`; `400` when the chosen signer cannot sign time stamps, when the chosen CA cannot issue, or, with `require_dedicated_cert` off and no dedicated signer (including a request that turns it off), when the CA cannot sign time stamps.
- `signer-candidates` lists the certificates eligible as the dedicated signer.
- `signer-certificate` (`write:settings` and `write:certificates`) issues a dedicated TSA signing certificate in one step. Optional body: `ca_refid` or `ca_id`, `cn` (a string), `validity_days`, `key_type`, `key_size`, `curve`, and `select` (a boolean: make it the signer; defaults to selecting it when the current signer is not usable).
- `stats` returns `total`, `successful` and `failed` requests counted from the audit log.

---

## Windows Enrollment Profiles

One profile per Active Directory realm, served by XCEP, WSTEP and Kerberos. Reading needs `read:xcep`, changing needs `write:xcep`. Passwords and the keytab are never returned, only `*_password_set` and `keytab_set`.

```http
GET /api/v2/windows-profiles?q=corp&ca=<refid>&state=keytab_missing&page=1&per_page=25
GET /api/v2/windows-profiles/{id}
POST /api/v2/windows-profiles
PUT /api/v2/windows-profiles/{id}
PATCH /api/v2/windows-profiles/{id}
DELETE /api/v2/windows-profiles/{id}
POST /api/v2/windows-profiles/{id}/keytab
GET /api/v2/windows-profiles/settings
PATCH /api/v2/windows-profiles/settings
```

- `q` matches the name or the realm; `ca` a refid of the issuing, policy or a former renewal CA; `state` one of `complete`, `keytab_missing`, `connector_failing` (the connector's last probe says down) and `disabled`, else 400. Each profile carries its `state`, its connector's name, health and realm, and its `template_ids`; the detail (`GET /{id}`) adds `keytab_entries` (principal, realm, kvno, enctype). `per_page` is capped at 200; `meta` carries `total`, `page`, `per_page`, `total_pages`. `sort_by`: `name` (default, ascending), `realm`, `created_at`, `status` (connector failing, keytab missing, complete, disabled); see [Sorting](#sorting).
- `PUT` and `PATCH` are the same partial update: only the fields sent change.
- Each profile carries `policy_id` (the MS-XCEP policy identifier) and `policy_oid_root` (the root of its template OIDs, `<policy_oid_root>.1.<template id>`). Both are read-only: set at creation (at random, or the values 2.254 served for the default profile of an upgraded installation), never changed by a change of CA, and ignored in a `POST`, `PUT` or `PATCH` body. A replacing restore puts back the archived values; a merge keeps those of a profile that already exists.
- Writable fields: `name`, `realm` (upper-cased; refused when another profile holds it or the keytab does not name it; `null` clears it, an empty or blank string is a 400), `enabled` and `is_default` (JSON booleans, else 400; `is_default` is accepted at creation only, for the first default profile), `connector_id` (an integer or `null`) (its base DN domain must equal the realm), `issuing_ca_refid` (a string; must be able to sign), `policy_ca_refid` (a string; no EdDSA key), `validity_days`, `xcep_username`, `xcep_password`, `wstep_username`, `wstep_password`, `allowed_ad_group`, `pinned_subject_fields`, `template_ids` (the templates offered; empty: those of the CA), `renewal_ca_refids` (see below).
- `renewal_cas` lists the former issuing CAs whose certificates still renew under the profile (`refid`, `name`, `null` for a deleted CA). A change of `issuing_ca_refid` adds the outgoing CA, and a CA becoming the issuing one again leaves the list. `renewal_ca_refids` (a list of refids) may only remove entries: a refid not on the list, other than the outgoing CA of the same request, is a 400. The outgoing CA of a change of `issuing_ca_refid` is added after the list sent is applied, even when that list leaves it out (audited as listed); a later request removes it. A `PUT`, `PATCH` or `DELETE` that changes the former CAs the TLS listener trusts (mTLS on, not revoked, not under the mTLS CA) reloads the TLS listener, or queues a rolling restart in HA; its answer carries `needs_restart` and `restart_message`. It needs `admin:system` beside `write:xcep`, the permission of `PUT /api/v2/mtls/settings`: without it the request is a 403 whose message names that permission, and nothing is saved.
- `pinned_subject_fields` takes an object, or its JSON text, with the keys `O`, `OU`, `C` (two letters, upper-cased), `ST` and `L` only; an empty object, an empty string or `null` stores none, anything else is a 400. It is returned as JSON text.
- There is at most one default profile; it cannot be deleted (disable it) and `is_default` cannot be changed on an existing profile.
- A profile through which valid certificates were issued cannot be deleted (409 with the count); disable it instead.
- `POST /{id}/keytab` takes a multipart `file` (a keytab GSSAPI loads, 256 KiB at most; every entry must be `HTTP/<SPN host>@<realm of the profile>`, else 400) and replaces the profile's keytab; with the form field `dry_run=1` it stores nothing and lists the entries by realm, `foreign_entries` being those the server would refuse. It needs `write:xcep` and `write:kerberos`, the scope of the retired `POST /api/v2/kerberos/keytab`.
- `settings` holds what every profile shares: `xcep_enabled`, `wstep_enabled` (needs `read:wstep` / `write:wstep`; changing it reloads the TLS listener, which reads the TLS cap as it loads, and the answer carries `listener_reload`), `kerberos_enabled`, `kerberos_spn` (`read:kerberos` / `write:kerberos`), the state of the served keytab, and the `default_profile` with its realm.
- The single-row routes `/api/v2/xcep/config`, `/api/v2/wstep/config`, `/api/v2/kerberos/config`, `/api/v2/kerberos/keytab` and `/api/v2/ad-connector` (with `/test` and `/test-saved`) are gone since 3.0; the connectors are under `/api/v2/ad-connectors`. A refused connector deletion (409) lists the profiles that use it in `details.profiles` (50 names at most, by name) and their number in `details.total`.
- `PUT /api/v2/ad-connectors/{id}` that changes the domain of `base_dn` also moves the realm of the profiles that use the connector: a profile without keytab whose realm was the old domain takes the new one in the same transaction (the audit entry of `ad_connector_update` names it). A profile with no realm, or already on the new domain, is left as is. If any other profile has a keytab, has a realm other than the old domain, or the new realm is served by another profile, the answer is 409, the message names the profile and says to change its realm or connector first (`details.profiles` lists them with a `reason`, `details.total` counts them) and nothing is written.
- Each profile carries `connector_domain_mismatch`, true when its realm and the domain of its connector differ (list and detail); it is a warning only, such a profile still serves.

## Active Directory Connectors

One stored LDAP connection per forest or domain; a Windows enrollment profile points at one. Reading needs `read:ad_connector`, changing and testing need `write:ad_connector`. The bind password is never returned: it reads back as `***`, and sending `***` keeps the saved one.

```http
GET /api/v2/ad-connectors
GET /api/v2/ad-connectors/{id}
POST /api/v2/ad-connectors
PUT /api/v2/ad-connectors/{id}
DELETE /api/v2/ad-connectors/{id}
POST /api/v2/ad-connectors/{id}/test
POST /api/v2/ad-connectors/test
```

- Writable fields: `name` (required, unique, 100 characters at most), `servers` (the domain controllers; the older single `server` string is accepted), `port` (389 by default; 3268 and 3269, the global catalog, are refused), `use_ssl`, `verify_ssl`, `ca_bundle`, `base_dn` (must name the domain with DC components, such as `DC=corp,DC=example`, else 400; its domain is the realm of the connector), `bind_dn`, `bind_password`, `enabled` (`bind_dn` and `bind_password` are required while it is true) and `health_probe_interval` (seconds, bounded).
- Read-only fields: `id`, `domain_sid` (read from the directory on save and test, dropped when `base_dn` or the domain controllers change), `realm`, `health`, `health_fresh`, `health_stale_after`, `last_test_at`, `last_test_result`, `created_at`, `updated_at`, `created_by`.
- `POST /{id}/test` tests the saved connector and stores the verdict and the domain SID on its row; `POST /test` tests submitted values without saving them (an `id` in the body lends the saved password to a blank one, for the target it was saved for only).
- `DELETE` answers 204; it is refused with 409 while a profile uses the connector (`details.profiles`, `details.total`).
- A `PUT` that changes the domain of `base_dn` moves the realm of the profiles that use the connector, or is refused with 409: see the note under Windows Enrollment Profiles.

## Microsoft CA

Connections to Active Directory Certificate Services CAs, used to sign CSRs on a Windows CA and to keep UCM and that CA in step. These are separate from the [Active Directory Connectors](#active-directory-connectors), which are LDAP connections.

```http
GET /api/v2/microsoft-cas
GET /api/v2/microsoft-cas/enabled
POST /api/v2/microsoft-cas
GET /api/v2/microsoft-cas/{id}
PUT /api/v2/microsoft-cas/{id}
DELETE /api/v2/microsoft-cas/{id}
POST /api/v2/microsoft-cas/test
POST /api/v2/microsoft-cas/{id}/test
```
- Permissions: the list, `GET /{id}` need `read:settings`; `enabled` (the enabled connections, for the signing dialog) needs `read:certificates`; `POST`, `PUT` and the two tests need `write:settings`; `DELETE` needs `delete:settings`.
- `POST` fields: `name` (required, unique: `409`), `server` (required hostname), `auth_method` (`certificate` by default, `kerberos` or `basic`, else `400`), `ca_name`, `verify_ssl` (default true), `ca_bundle` (the PEM that signs the CA web server certificate, used while `verify_ssl` is true), `use_ssl` (stored but without effect: enrollment always uses HTTPS), `default_template` (`WebServer`), `enabled` (true), `username` and `password` (basic), `client_cert_pem` and `client_key_pem` (certificate), `kerberos_principal` (the identity Kerberos authenticates as, when the cache or keytab holds several, also on a Kerberos WinRM channel without `winrm_username`) and `kerberos_keytab_path` (the client keytab, used whenever set; a path inside the UCM data folder, or a keytab type other than `FILE:` or `WRFILE:`, answers `400`, on save and on both tests), `crl_sync_enabled`, `crl_url`, `inventory_sync_enabled`, and the WinRM admin channel fields `winrm_enabled`, `winrm_host`, `winrm_port`, `winrm_use_ssl`, `winrm_verify_ssl`, `winrm_transport`, `winrm_username`, `winrm_password`. `PUT` is a partial update of the same fields; a masked secret sent back keeps the stored one. A text field the request reads (the common ones and those of its `auth_method`) sent as `null` or another JSON type answers `400` naming it. A Kerberos connection signs in as an identity of the server (its keytab, or without one the tickets the process holds), so a save that leaves a Kerberos sign-in other than the saved one needs `admin:system`, judged on the connection as the save leaves it: creating a Kerberos connection or one with an enabled Kerberos WinRM channel, switching `auth_method` to Kerberos, turning on a Kerberos WinRM channel (`winrm_enabled` or `winrm_transport`), changing `kerberos_keytab_path` or `kerberos_principal`, and changing `server`, `use_ssl`, `verify_ssl`, `ca_bundle` or a WinRM target field (`winrm_host`, `winrm_port`, `winrm_use_ssl`, `winrm_verify_ssl`, `winrm_username`) while it signs in with Kerberos; a disabled WinRM channel does not count, so its fields may be set freely until it is turned on. Otherwise `403`, before anything is written. Leaving Kerberos while no remaining Kerberos sign-in changes (an enabled Kerberos WinRM channel that would follow the change answers `403`), and editing the other fields, stay with `write:settings`; switching to another method clears the keytab and principal.
- `DELETE` answers `204`, or `409` while requests are pending on the connection.
- `POST /test` checks the connection with the submitted values before saving (`server` required); `POST /{id}/test` checks a saved one. With no body it tests the saved values and records the result; with a JSON body of form values (`server`, `ca_name`, `auth_method`, `username`, `password`, `client_cert_pem`, `client_key_pem`, `kerberos_principal`, `kerberos_keytab_path`, `use_ssl`, `verify_ssl`, `ca_bundle`) it tests those, takes a secret left out or masked from the saved connection, saves nothing, and reads a blank `password` or `client_key_pem` as no secret. The saved password or client key only goes to the saved target: a body that leaves it out or masked and changes `server`, `use_ssl`, `verify_ssl`, `ca_bundle`, `auth_method` or, for `basic`, `username` is refused with `400` (`details.code` `secret_required_for_target`, `details.fields` the changed fields) unless the secret is retyped, and `PUT` applies the same rule. A Kerberos keytab path and principal are not secrets (a read returns them): a Kerberos test other than the saved one (another target, keytab or principal, or `auth_method` switched to `kerberos`) needs `admin:system` (`403`, before any request goes out), as does any Kerberos `POST /test`. The keytab and principal of a connection saved under another method are never used by these tests (the WinRM channel still reads them). Both answer `400` with the error when the check fails; a Kerberos sign-in that fails gives its cause (`Kerberos sign-in failed: Preauthentication failed`, for instance).

### Signing and Requests
```http
GET /api/v2/microsoft-cas/{id}/templates
POST /api/v2/microsoft-cas/{id}/sign/{csr_id}
GET /api/v2/microsoft-cas/{id}/requests/{request_id}
GET /api/v2/microsoft-cas/requests/pending?msca_id=1
```
- `templates` and both request reads need `read:certificates`; `sign` needs `write:certificates`. `templates` answers `400` with the cause when its Kerberos sign-in fails.
- `sign` submits the CSR `{csr_id}` to the CA. Optional body: `template` (defaults to the connection's `default_template`; `400` when none), `enrollee_name`, `enrollee_upn`. `404` when the connection or CSR is unknown, `400` when the connection is disabled, the CSR was already signed, is empty or its signature is invalid. The CA is reached with the saved connection only, whatever the body carries. A Kerberos sign-in that fails answers `400` with its cause, and no request is recorded. An issued certificate is imported into UCM ("Certificate issued by Microsoft CA"); a request the CA holds for approval answers "Request pending approval" and is tracked.
- `GET /{id}/requests/{request_id}` refreshes one request and imports the certificate once issued; `404` for an unknown request. A Kerberos sign-in that fails answers `400` with its cause, and the request is left as it was. A request the CA holds for approval reads `disposition_message` `Pending approval on the CA`.

### Synchronisation
```http
POST /api/v2/microsoft-cas/{id}/sync-crl
POST /api/v2/microsoft-cas/{id}/inventory-sync
POST /api/v2/microsoft-cas/{id}/publish-crl
GET /api/v2/microsoft-cas/{id}/reconciliation
```
- `sync-crl` (`write:certificates`) fetches the CA's CRL and revokes the matching UCM certificates, one way from the CA to UCM; `400` when the connection is disabled. It returns the counts `revoked` and `checked`.
- `inventory-sync` (`admin:system`) imports certificates issued directly on the CA that UCM does not know. Optional body `{"full": true}`. Returns the counts `imported`, `skipped` and `failed`. Needs the WinRM admin channel (`400` otherwise).
- `publish-crl` (`admin:system`) makes the CA publish a new CRL through the admin channel.
- `reconciliation` (`read:certificates`) compares the CA's issued certificates with the ones UCM knows, read-only.

### WinRM Admin Channel
```http
POST /api/v2/microsoft-cas/{id}/admin-channel/test
GET /api/v2/microsoft-cas/{id}/ca/health
GET /api/v2/microsoft-cas/{id}/ca/pending
POST /api/v2/microsoft-cas/{id}/ca/pending/{request_id}/approve
POST /api/v2/microsoft-cas/{id}/ca/pending/{request_id}/deny
```
All answer `404` for an unknown connection and `400` when the admin channel is not enabled or configured on it. `admin-channel/test` (`admin:system`) tests the channel (connection and CA service); its body may carry the `winrm_*` fields, `ca_config`, `kerberos_principal` and `kerberos_keytab_path` as overrides, and saves nothing. The saved NTLM password only goes to the saved channel: a body that changes the host (`winrm_host`, or the saved `server` it falls back to when blank), the port, `winrm_use_ssl`, `winrm_verify_ssl`, `winrm_transport` or the account is refused with `400` (`details.code` `secret_required_for_target`, `details.fields` the changed fields) unless it retypes `winrm_password`. A Kerberos channel signs in with the keytab and principal of the body, else the saved ones. A Kerberos sign-in that fails answers `400` with its cause. `ca/health` and `ca/pending` (`read:certificates`) return the CA's service, certificate and CRL state, and the requests awaiting a CA manager. `approve` and `deny` (`admin:system`) resubmit or refuse a pending request on the CA; `approve` imports the issued certificate.

---

## SSH Certificates

OpenSSH user and host certificates, signed by SSH CAs held in UCM. Permissions: `read:ssh`, `write:ssh`, `delete:ssh` for certificates; `read:ssh_cas`, `write:ssh_cas`, `delete:ssh_cas` for CAs. A missing CA or certificate answers `404`.

### SSH CAs
```http
GET /api/v2/ssh/cas?search=prod&type=user
POST /api/v2/ssh/cas
GET /api/v2/ssh/cas/{ca_id}
PUT /api/v2/ssh/cas/{ca_id}
DELETE /api/v2/ssh/cas/{ca_id}
POST /api/v2/ssh/cas/import
GET /api/v2/ssh/cas/{ca_id}/public-key
GET /api/v2/ssh/cas/{ca_id}/krl
GET /api/v2/ssh/cas/{ca_id}/setup-script?type=user&hostname=host.example.com&platform=unix
```
- `GET` list filters by `search` and by `type` (repeatable). Without `page` or `per_page` it returns every CA; with either it returns that page (`per_page` defaults to 20, 100 at most) and `meta` carries `total` and `total_pages`.
- `POST` creates a CA (`201`): `descr` (or `name`, required), `ca_type` (`user` by default, or `host`), `key_type`, `default_ttl`, `max_ttl` (default `0`), `default_extensions`, `allowed_principals` (a list of non-empty strings), `allow_any_principal` and `allow_custom_key_id` (JSON booleans, default off), `comment`. `400` for an invalid value.
- `POST` with `hsm_key_id` (a JSON integer above zero, `400` otherwise) creates a CA whose key stays on an HSM token: the key must be an RSA or NIST P-256, P-384 or P-521 signing key, `key_type` is read from it and the CA carries `key_source: "hsm"` and `hsm_key_id` (`"software"` and `null` for any other CA). It requires `read:hsm` besides `write:ssh_cas` (`403` naming the missing permission otherwise). An HSM key backs one authority: `409` names the X.509 or SSH CA that already holds it. A token that cannot be reached answers `503`, a key no longer on its token `409`, a misconfigured provider `400`, any other HSM failure `502`. In FIPS mode a key FIPS mode does not approve is refused before the CA is created; in HA mode a SoftHSM or local smart card reader (OpenSC, YubiKey PIV) key answers `409` with code `ha_mode`.
- `PUT` updates the same metadata (`descr`, `default_ttl`, `max_ttl`, `comment`, `default_extensions`, `allowed_principals`); `400` for an invalid value. `default_ttl` or `max_ttl` sent as `null` is emptied; a key left out is kept. Without a maximum nothing is capped; without a default a certificate is signed for the default of the CA type (24 hours for a user CA, 365 days for a host CA).
- `DELETE` answers `204`, or `409` when the service refuses (certificates still depend on the CA).
- `POST /import` imports an existing CA from `private_key` (required) with `descr`, `ca_type` (`user` or `host`), `default_ttl`, `max_ttl` and `comment`; `201`, or `400` for an unusable key.
- `public-key` downloads the CA public key in OpenSSH format. `krl` downloads the CA's key revocation list; a revoked certificate of serial 0, which OpenSSH reads as not numbered, is listed as `ssh-keygen -k` lists it, by its key ID under the CA, which revokes every certificate of the CA with that key ID, whatever its serial, an empty key ID included. Revoking it revokes those certificates too and lists them in `revoked_with`; issuing or importing a certificate with that key ID under the CA is refused with `400`. `setup-script` returns a server setup script for trusting the CA: `type` (`user` or `host`), `hostname` (validated, `400` when invalid) and `platform` (`unix` by default, or `windows`).

### SSH Certificates
```http
GET /api/v2/ssh/certificates?search=alice&status=valid&type=user&ca_id=1
POST /api/v2/ssh/certificates
POST /api/v2/ssh/certificates/generate
POST /api/v2/ssh/certificates/import
POST /api/v2/ssh/certificates/verify
GET /api/v2/ssh/certificates/{cert_id}
GET /api/v2/ssh/certificates/{cert_id}/export
POST /api/v2/ssh/certificates/{cert_id}/revoke
DELETE /api/v2/ssh/certificates/{cert_id}
GET /api/v2/ssh/stats
```
- The list is paginated and sorted by `sort_by` (`id`, `key_id`, `cert_type`, `serial`, `valid_from`, `valid_to` or `created_at`) and `sort_order` (`asc` or `desc`); `created_at` descending by default; `ca` (the CA's name) and `status` (expired, expiring within 7 days, valid, revoked) sort too, and an unknown key or direction answers `400` (see [Sorting](#sorting)). `status`, `type` and `ca_id` may be repeated, an unknown `status` answers `400`.
- `POST` signs a public key (`write:ssh`, `201`). Body: `ca_id` and `public_key` (required), `cert_type` (`user` by default, or `host`), `principals` (a list or a comma-separated string, at least one, no comma inside a name, 64 at most), `validity_seconds` (an integer from 60 to ten years), or a range `valid_from` and `valid_to` (ISO 8601, UTC when no offset is given; `valid_to` alone starts now; `valid_from` may lie at most five minutes in the past; the range lasts 60 seconds to ten years and ends at most ten years from now; a range beyond the CA's `max_ttl` is refused; not combined with `validity_seconds`), `key_id`, `extensions`, `critical_options`, `descr`. As an exception kept for existing scripts, a `validity_seconds` above the CA's `max_ttl` is capped to it without an error: the `valid_to` returned shows the end applied. `400` for any invalid field or a CA policy refusal.
- `POST /generate` takes the same fields without `public_key`, plus `key_type`: UCM creates the key pair and returns the certificate with the `private_key` once. Both answer `409` when the serial they take is held by another certificate of the CA even after its counter was moved past its certificates; try again.
- `POST /import` stores an existing certificate: `certificate` (required), optional `descr` and `ssh_ca_id`; `201`.
- `POST /verify` (`read:ssh`) decodes and verifies `certificate` (required) and returns the result.
- `export` returns the certificate in OpenSSH format. `revoke` takes an optional `reason` (default `unspecified`) and returns the certificate, with `revoked_with`: the ids of the other certificates of the CA that this revocation revoked with it, since the KRL revokes by serial, or by key ID for a certificate of serial 0: those holding the same serial, or bearing the same key ID whatever their serial (a certificate already revoked is not listed; empty but for a pair kept by an upgrade from 2.x or by the restore of a 2.x archive, and for a serial 0 certificate, which only an import brings), and `revoked_by`: the KRL entries that took them, in order, each `{"serial": n}` or `{"key_id": "..."}` (a key ID takes numbered certificates, whose serial then takes its other holders, so a serial 0 revocation may list its key ID and serials). Every certificate carries `serial_shared_with`, the ids of the other holders of its serial (always empty for serial 0). `DELETE` answers `204` or `409` when it cannot be deleted.
- `stats` returns the counts shown on the SSH dashboard.

### Public KRL

```
GET /ssh/krl/{refid}
```

The KRL of an SSH CA, without authentication, as a CRL is (`404` for an unknown CA). It is the KRL `GET /api/v2/ssh/cas/{ca_id}/krl` downloads: one per CA, stored in the database so every node of a cluster serves the same bytes. Its version (PROTOCOL.krl) changes only when the CA's revocations change, and a revocation publishes the new KRL at once. The response carries `ETag` (the version, quoted), `X-KRL-Version`, `Last-Modified` and `Cache-Control: public, no-cache`; a request whose `If-None-Match` names the current version gets `304` without a body. `503` with `Retry-After` when the KRL cannot be built.

### SSH Agent

```
GET /ssh/setup/{refid}/agent
```

A POSIX `sh` installer, without authentication, run on a server as `curl -fsSL https://<ucm>/ssh/setup/{refid}/agent | sudo sh` (`sh -s -- --interval 15 --cacert ca.pem` to pass options, `--uninstall` to remove it). It holds no secret: only the URL it was fetched from (`400` when that URL is not one a shell can hold) and the CA refid (`404` for an unknown CA). For a user CA it installs `/usr/local/sbin/ucm-ssh-agent`, downloads the KRL to `/etc/ssh/ucm/revoked_keys` before pointing `RevokedKeys` at it (in `/etc/ssh/sshd_config.d` when sshd_config includes it, else at the top of sshd_config), and a systemd timer, else a cron job, that runs `ucm-ssh-agent sync` every 15 minutes. A sync sends the installed version as `If-None-Match`, checks a new KRL with `ssh-keygen -Q` and refuses one older than the installed one, replaces the file atomically and reloads sshd only when the KRL changed and `sshd -t` passes. It needs `ssh-keygen` and `curl` or `wget`.

For a host CA the installer enrolls the server instead: `curl -fsSL https://<ucm>/ssh/setup/{refid}/agent | sudo UCM_ENROLL_TOKEN=ucmh_... sh` (the token is read from the environment only, never from an argument, which the process list would show), with `--principal NAME` (repeated) to ask for some of the token's names only, and `--host-key /etc/ssh/ssh_host_ecdsa_key` to pick a key (the first of Ed25519, ECDSA and RSA by default). The agent sends the public host key, checks that the certificate it gets certifies that key, writes it beside the key (`ssh_host_ed25519_key-cert.pub`; a file found there comes back at `--uninstall`), points `HostCertificate` at it and reloads sshd. The token is passed in the environment, never written to disk. One server may follow the KRL of one user CA and hold the host certificate of one host CA.

### SSH Hosts and Enrollment Tokens

```
GET /api/v2/ssh/enrollment-tokens?ca_id=1
POST /api/v2/ssh/enrollment-tokens
POST /api/v2/ssh/enrollment-tokens/{token_id}/revoke
GET /api/v2/ssh/hosts?ca_id=1&state=valid&search=web
GET /api/v2/ssh/hosts/{host_id}
POST /api/v2/ssh/hosts/{host_id}/revoke
POST /api/v2/ssh/hosts/{host_id}/auto-renew
POST /ssh/enroll/{refid}
POST /ssh/renew/{host_refid}/challenge
POST /ssh/renew/{host_refid}
```

- `POST /api/v2/ssh/enrollment-tokens` (`write:ssh`, `201`) creates a single-use enrollment token for a host CA: `ca_id` (`404` when unknown, `400` for a user CA) and `principals` (host names or IP addresses, 32 at most, each allowed by the CA), optional `validity_seconds` of the certificates (60 seconds to ten years, within the CA's `max_ttl`; the CA's default when absent), `lifetime_seconds` of the token (300 to 604800, 3600 by default), `renew_percent` (5 to 90, 30 by default: the share of its lifetime a certificate has left when the agent renews it) and `descr`. The answer carries the token in `token`, the only time it is shown: UCM keeps its SHA-256. A listed token shows its `token_prefix` and `state` (`active`, `used`, `expired` or `revoked`); `revoke` answers `409` for a token already used or revoked. Reading needs `read:ssh`.
- `POST /ssh/enroll/{refid}` (public, no session) exchanges a token for a host certificate: a JSON body with `token`, `public_key` (the host's OpenSSH public key; Ed25519, ECDSA, or RSA of 2048 bits at least; never a certificate), `signature` (the token signed with that key, `ssh-keygen -Y sign -n ucm-ssh-host-enrollment`, which proves the host holds it; `403` when missing or wrong, the token left unspent) and optional `principals`, which must all be names of the token (all of them by default). `201` answers `host_refid`, `certificate`, `principals`, `valid_to` and `renew_percent`, as JSON or, with `Accept: text/plain`, as `key=value` lines. A malformed, unknown, used, expired or revoked token, or one of another CA, answers `403` with the same message; the audit log records the reason. A token is spent by the first exchange whose body is valid, before the certificate is signed; when the CA then refuses the certificate (`400`), the token is given back. The same key enrolled again under the same CA for the same names keeps its host and refid; for other names it answers `409` until that host is revoked. Rate limited (10 requests per minute per address).
- `GET /api/v2/ssh/hosts` (`read:ssh`) lists the enrolled hosts, 25 per page, with `meta.counts` by `state` (`valid`, `expired`, `revoked`). A host carries its `principals`, key `fingerprint`, current certificate (`certificate_id`, `valid_from`, `valid_to`), `auto_renew`, `enrolled_at`, `last_renewed_at`, `last_seen_at` and `last_krl_sync_at`.
- Renewal is authenticated by the host key alone, never by a stored secret. `POST /ssh/renew/{host_refid}/challenge` (public) answers `due: 0` with `renew_after` while the current certificate has more than `renew_percent` of the lifetime it was issued with left, then `due: 1` with a `challenge` and the `namespace` `ucm-ssh-host-renewal`; a challenge stays the same for five minutes, however often it is asked for. `POST /ssh/renew/{host_refid}` takes `challenge` and `signature`, the `ssh-keygen -Y sign -n ucm-ssh-host-renewal` signature of the challenge made with the key the current certificate certifies (Ed25519, ECDSA, or RSA with SHA-2), and answers `200` with a new `certificate` for the same names and validity. The challenge is spent by the renewal that uses it. A revoked host or certificate, an expired certificate, another key, another namespace or an unknown challenge answers `403`, an unknown host `404`, each with a `state` (`revoked`, `expired`, `unknown`, `refused`) and an audit entry; a host whose renewals are switched off answers `403` with `state: disabled`, not audited, and the agent asks again at its next sync. Rate limited (30 requests per minute per address). The agent asks at every sync and stops asking once UCM answers `revoked`, `expired` or `unknown`; any other refusal, a proxy's `403` or `404` without that `state` included, is asked again at the next sync. `ucm-ssh-agent status` shows why it stopped. A KRL download with `?host={host_refid}` records the host's `last_krl_sync_at`, as the agent does when the server is enrolled: it is what the agent says, at most once a minute.
- `revoke` (`write:ssh`) revokes every unexpired certificate of the host's key under its CA, the current one and those a renewal or a new enrollment replaced, which the host CA's KRL then lists, and ends its renewals for good (`409` when already revoked); a revoked server enrolls again with a new token. `auto-renew` takes `{"enabled": false}` to stop the renewals of a host and `true` to resume them (`400` for a revoked host).

---

## Deployment

Pushes certificates and CRLs to targets: an SSH (SFTP) host, or an HTTP endpoint that receives a templated body. Reading needs `read:deploy`, creating, changing, pushing and testing `write:deploy`, deleting `delete:deploy`. A missing target, binding or delivery answers `404`. Bindings a renewal leaves on the previous certificate are described under [Deploy Bindings Left Behind by a Renewal](#deploy-bindings-left-behind-by-a-renewal); `GET /api/v2/deploy/bindings` is documented there.

### Targets
```http
GET /api/v2/deploy/targets
POST /api/v2/deploy/targets
GET /api/v2/deploy/targets/{target_id}
PATCH /api/v2/deploy/targets/{target_id}
DELETE /api/v2/deploy/targets/{target_id}
POST /api/v2/deploy/targets/{target_id}/test
```
- `POST` takes `kind`, `ssh` by default or `http` (it cannot be changed afterwards), and `name` (required, 120 characters at most, unique: `409`). `400` carries the reason for an invalid field.
- An SSH target takes `host` (required), `port` (1 to 65535), `username` (required), `enabled` and optionally `private_key` (UCM generates a key pair when absent; the response carries the public key). Changing `host` or `port`, or sending `reset_host_key`, forgets the pinned host key; it is pinned again on the next successful test.
- An HTTP target takes `url`, `http_method` (`POST`, `PUT` or `PATCH`; default `POST`), `http_headers`, `body_template` (required), `tls_ca_pem`, `allow_private_key` and `enabled`.
- `GET /{target_id}` adds the target's `bindings` and `crl_bindings`.
- `test` connects and authenticates without writing, and pins the host key of an SSH target on the first success; an HTTP target is probed. `409` or `502` carry the reason of a refusal or a failed connection.

### Certificate Bindings
```http
POST /api/v2/deploy/bindings
PATCH /api/v2/deploy/bindings/{binding_id}
DELETE /api/v2/deploy/bindings/{binding_id}
POST /api/v2/deploy/bindings/{binding_id}/deploy
```
- `POST` binds a certificate to a target: `target_id` and `certificate_id` (required, `404` when unknown), then for an SSH target `cert_path`, `key_path`, `fullchain_path` (absolute file paths of 512 characters at most; at least one is required and they must differ), `reload_command` (512 at most), `include_root`, `chain_variant` (default `auto`) and `enabled`. `key_path` needs a certificate whose private key UCM holds. On an HTTP target the paths and `reload_command` are refused (`400`) and a template that sends `key_pem` needs the key. The same pair twice answers `409`. A first push is queued on creation.
- `PATCH` changes the same fields; `DELETE` removes the binding.
- `deploy` pushes now and waits: `200` with the delivery, or `502` with its `last_error`.

### CRL Bindings
```http
GET /api/v2/deploy/crl-bindings?ca_id=1&target_id=2
POST /api/v2/deploy/crl-bindings
PATCH /api/v2/deploy/crl-bindings/{binding_id}
DELETE /api/v2/deploy/crl-bindings/{binding_id}
POST /api/v2/deploy/crl-bindings/{binding_id}/deploy
```
CRL bindings need an SSH target (`400` otherwise). `POST` takes `target_id` and `ca_id` (required), `crl_path` (an absolute file path, required), `format` (`pem` by default, or `der`), `include_parent_crls` (PEM only), `reload_command` and `enabled`; the same pair twice answers `409`. Each list item carries its `last_delivery`. `deploy` pushes now (`200`, or `502` with the error).

### Deliveries
```http
GET /api/v2/deploy/deliveries?binding_id=1&certificate_id=2&binding_type=certificate
POST /api/v2/deploy/deliveries/{delivery_id}/retry
```
`binding_type` is `certificate` (default) or `crl`, else `400`. `retry` requeues a failed delivery; any other status answers `400`.

---

## Discovery

TLS certificate discovery: scan hosts and subnets, then review what was found. Reading needs `read:certificates`; scanning and managing profiles need `admin:system`; deleting one record needs `delete:certificates`.

### Discovered Certificates
```http
GET /api/v2/discovery?limit=50&offset=0&profile_id=1&status=new&search=example
GET /api/v2/discovery/{disc_id}
DELETE /api/v2/discovery/{disc_id}
DELETE /api/v2/discovery?profile_id=1
GET /api/v2/discovery/export?format=csv&profile_id=1&status=new&search=example
GET /api/v2/discovery/stats?profile_id=1
POST /api/v2/discovery/bulk-resolve-dns
```
- The list returns `items` and `total`; it pages with `limit` (default 50, 200 at most) and `offset`, or with `page` and `per_page` when either is given. `status` may be repeated. `sort_by`: `last_seen` (default, most recent first), `first_seen`, `not_after`, `target`, `issuer`, `subject`, `status` (error, unmanaged, managed); see [Sorting](#sorting).
- `GET /{disc_id}` adds the parsed `extensions`, key and signature details and the SHA-1 and SHA-256 fingerprints; `404` when unknown. `DELETE /{disc_id}` answers `204`.
- `DELETE /api/v2/discovery` (`admin:system`) deletes every record, or those of `profile_id`, and returns `deleted`.
- `export` returns CSV (default) or JSON (`format=json`) as a download, for the same `profile_id`, `status` and `search` filters as the list (10 000 rows at most). A CSV text cell that starts with `=`, `+`, `-`, `@`, a tab or a carriage return is written with a leading `'`, so a spreadsheet does not run it as a formula.
- `bulk-resolve-dns` (`admin:system`) re-resolves reverse DNS for every record and returns the counts `updated` and `total`.

### Scan Profiles and Runs
```http
GET /api/v2/discovery/profiles
POST /api/v2/discovery/profiles
GET /api/v2/discovery/profiles/{profile_id}
PUT /api/v2/discovery/profiles/{profile_id}
DELETE /api/v2/discovery/profiles/{profile_id}
POST /api/v2/discovery/profiles/{profile_id}/scan
POST /api/v2/discovery/scan
GET /api/v2/discovery/runs?profile_id=1
GET /api/v2/discovery/runs/{run_id}
```
- `POST /profiles` (`201`): `name` (required, unique: `409`), `targets` (required, a non-empty list of at most 1000 hostnames, IP addresses or CIDR ranges), `ports` (a non-empty list of at most 100 integers from 1 to 65535), and optionally `description`, `schedule_enabled`, `schedule_interval_minutes` (1440 by default), `notify_on_new`, `notify_on_change`, `notify_on_expiry` (all true by default), `notify_email` (one valid address), `timeout` (1 to 30, default 5), `max_workers` (1 to 50, default 20) and `resolve_dns`. `PUT` updates the same fields; `DELETE` answers `204`.
- `PUT /profiles/{profile_id}`: a new `schedule_interval_minutes` on a scheduled profile, or `schedule_enabled` turned on again, sets `next_scan_at` to now plus the interval, as creation does; any other update leaves it.
- `POST /profiles/{profile_id}/scan` starts a scan with the profile's settings and returns `scan_run_id`.
- `POST /scan` scans without a saved profile: `targets` (at most 500) or `subnet` (at most 1024 addresses), one of the two being required, plus `ports` (default `[443]`), `timeout` (1 to 30, default 5), `max_workers` (1 to 50, default 20) and `resolve_dns`. It returns `scan_run_id`.
- `runs` lists scan runs (`items`, `total`); `runs/{run_id}` reads one, `404` when unknown.

---

## Key Recovery

Recovery of a certificate's archived private key goes through a request that an approver decides. Scopes: `write:key_recovery` opens a request and collects an approved key, `read:key_recovery` reads requests, `admin:key_recovery` approves and rejects. An unknown request answers `404`.

```http
POST /api/v2/certificates/{cert_id}/key-recovery
Content-Type: application/json

{ "reason": "Server rebuilt after a disk failure" }
```
Opens a request (`201`). `reason` is required and at most 2000 characters; `400` when missing or when the certificate has no archived private key; `404` for an unknown certificate.

```http
GET /api/v2/key-recovery?status=pending
GET /api/v2/key-recovery/{id}
```
The list returns `requests` and `dual_control`, whether the approver must differ from the requester; it pages with `page` and `per_page` (default 500, 500 at most), `meta` carries `total`, and it sorts by `sort_by`: `id` (default, newest first), `requested_at`, `status` (pending, approved, recovered, rejected, cancelled), `cert_cn`, `requested_by` (see [Sorting](#sorting)). `GET /{id}` reads one request whatever its age.

```http
POST /api/v2/key-recovery/{id}/approve
POST /api/v2/key-recovery/{id}/reject
Content-Type: application/json

{ "note": "Ticket 1234" }
```
`admin:key_recovery`. `note` is optional; a longer note is cut to its first 2000 characters. `409` when the request is no longer pending. `approve` answers `403` when dual control is on and the caller is the requester, and `410` when the certificate no longer exists.

```http
POST /api/v2/key-recovery/{id}/recover
Content-Type: application/json

{ "password": "at-least-8-chars", "legacy": false }
```
Returns the key and certificate as a PKCS#12 download, once, after approval. `password` is required (`400` when it does not meet the export password rules); `legacy` selects the 3DES/SHA-1 profile. These are the only options, in a JSON object body, read as described under Export Certificate (where the options go). `409` when the request is not approved, `403` unless the caller is the requester or holds `admin:key_recovery`, `410` when the certificate or key is gone.

---

## CRL & OCSP

### Get CRL List
```http
GET /api/v2/crl
```

### Get CRL for CA
```http
GET /api/v2/crl/{ca_id}
```

### Regenerate CRL
```http
POST /api/v2/crl/{ca_id}/regenerate
```

Requires `write:crl`. Offline CAs return `400`. Response metadata omits PEM by default; fetch PEM with `GET /api/v2/crl/{ca_id}`.

Generated CRLs include **Authority Key Identifier** = issuing CA **Subject Key Identifier** (RFC 5280 §5.2.1).

### Get Delta CRL
```http
GET /api/v2/crl/{ca_id}/delta
```

### Regenerate Delta CRL
```http
POST /api/v2/crl/{ca_id}/delta/regenerate
```

Requires CDP + delta CRL enabled on the CA, and an existing complete CRL.

### CRL Schedule
```http
GET /api/v2/crl/{ca_id}/config
POST /api/v2/crl/{ca_id}/config
```

Full CRL schedule per CA. `POST` accepts `validity_days` (1 to 365, default 7),
`publish_interval_hours` (1 to 8760 or null for the legacy regenerate near expiry
behaviour) and `digest` (`sha256`, `sha384`, `sha512`). The publish interval must
not exceed the validity window: publishing more often than the validity gives
relying parties a grace period. Responses include the computed `next_publish`,
also present in CRL metadata responses when a cadence is configured.

A CA whose key signs without a separate digest (ML-DSA, Ed25519, Ed448) has
`crl_digest: null`; a non-empty `digest` is refused with `400` and an empty one
clears the stored value. A digest stored before that was known is ignored when
signing and shown in the CA object as `crl_digest_ignored`, so it can be cleared
(`null` otherwise).

### OCSP Status
```http
GET /api/v2/ocsp/status
```

### OCSP Statistics
```http
GET /api/v2/ocsp/stats
```

### CRL Automation
```http
POST /api/v2/crl/{ca_id}/auto-regen
Content-Type: application/json

{ "enabled": true }
```
Permission `write:crl`. Turns the CA's CRL distribution point, and so automatic regeneration, on or off; `enabled` toggles the current state when omitted. Enabling without a CDP URL generates one from the protocol base URL; `400` when none is configured in Settings.

```http
POST /api/v2/crl/{ca_id}/delta-config
Content-Type: application/json

{ "enabled": true, "interval": 24 }
```
Permission `write:crl`. `interval` is the delta CRL period in hours, from 1 to 168 (`400` otherwise). Both fields are optional.

---

## AIA CA Issuers

Public endpoints for downloading CA certificates (RFC 5280 §4.2.2.1). No authentication required.

### Download CA Certificate (DER)
```http
GET /ca/{ca_refid}.cer
```

**Response**: `application/pkix-cert`: DER-encoded X.509 certificate

Also accepts legacy numeric CA ID: `GET /ca/{ca_id}.cer`

```bash
curl http://your-server:8080/ca/550e8400-e29b-41d4-a716-446655440000.cer -o ca.cer
openssl x509 -in ca.cer -inform DER -text -noout
```

### Download CA Certificate (PEM)
```http
GET /ca/{ca_refid}.pem
```

**Response**: `application/x-pem-file`: PEM-encoded X.509 certificate

```bash
curl http://your-server:8080/ca/550e8400-e29b-41d4-a716-446655440000.pem -o ca.pem
```

### Download CA Certificates Bundle (PKCS#7)
```http
GET /ca/{ca_refid}.p7c
```

**Response**: `application/pkcs7-mime`: certs-only CMS (RFC 5280 section 4.2.2.1) holding the CA certificate
and its servable cross-certificates. An unreadable certificate is left out and logged; `404` when none is readable.

### Download a Cross-certificate
```http
GET /ca/{ca_refid}/cross/{xid}.cer
```

**Response**: `application/pkix-cert`. A revoked, expired or not yet valid cross-certificate answers `404`.
`.cer` and `.pem` return the served cross-certificate when the CA has one, otherwise its own certificate. Responses are cached for 24 hours, so a change reaches clients after that delay.

### AIA CA Issuers Configuration

Per-CA toggle available via the CRL/OCSP management page or API:

```http
GET /api/v2/cas/{ca_id}          # Returns aia_ca_issuers_enabled, aia_ca_issuers_url
PATCH /api/v2/cas/{ca_id}        # Set aia_ca_issuers_enabled: true/false (write:cas)
```

When enabled, issued certificates include the CA Issuers URL in their Authority Information Access extension:

```
Authority Information Access:
    OCSP - URI:http://your-server:8080/ocsp
    CA Issuers - URI:http://your-server:8080/ca/{ca_refid}.cer
```

---

## Users

### List Users
```http
GET /api/v2/users
```

### Create User
```http
POST /api/v2/users
Content-Type: application/json

{
  "username": "newuser",
  "email": "newuser@example.com",
  "password": "SecurePassword123!",
  "role": "operator",
  "full_name": "New User"
}
```

### Get User
```http
GET /api/v2/users/{user_id}
```

### Update User
```http
PUT /api/v2/users/{user_id}
Content-Type: application/json

{
  "email": "updated@example.com",
  "role": "admin",
  "full_name": "Updated Name"
}
```

### Toggle User Status
```http
PATCH /api/v2/users/{user_id}/toggle
```

### Reset User Password
```http
POST /api/v2/users/{user_id}/reset-password
Content-Type: application/json

{
  "new_password": "NewSecurePassword123!"
}
```

### Import Users
```http
POST /api/v2/users/import
Content-Type: multipart/form-data

file=@users.csv
```
```csv
username,email,full_name,role,password
john.doe,john@example.com,John Doe,operator,SecurePass123!
```
- The `file` field holds a UTF-8 CSV file whose name ends in `.csv` (`400` otherwise), of 5 MB at most (`413`); the import stops after 10 000 rows and says so in `errors`. `username`, `email` and `password` are required on each row, `role` is one of the built-in roles (`viewer` when empty) and `full_name` is optional. Each account is local and created active with that password.
- A row is skipped, and named in `errors`, when a field is missing, the password fails the password policy, the role is unknown, the username exists or a local account already uses the e-mail (an SSO account's e-mail may be taken). The answer gives `imported`, `skipped` and `errors`; `409` names the e-mail or username another request took first, and nothing is imported then.
- It needs `write:users` and an admin caller (`403` otherwise). Audit action `user_import`.

### Delete User
```http
DELETE /api/v2/users/{user_id}
```

### More User Operations
```http
POST /api/v2/users/{user_id}/toggle-active
POST /api/v2/users/{user_id}/unlock
POST /api/v2/users/{user_id}/reset-2fa
GET /api/v2/users/{user_id}/sso-identities
POST /api/v2/users/{user_id}/sso-identities
POST /api/v2/users/{user_id}/sso-identities/{identity_id}/reset
DELETE /api/v2/users/{user_id}/sso-identities/{identity_id}
POST /api/v2/users/bulk/delete
GET /api/v2/users/password-policy
POST /api/v2/users/password-strength
```
- `toggle-active` is the same route as `PATCH /api/v2/users/{user_id}/toggle`. `403` for your own account, `409` when it would deactivate the last active admin. These routes need `write:users` and an admin caller (`403` otherwise); `404` for an unknown user.
- `unlock` clears a lockout and answers `Account is not locked` when there was none.
- `reset-2fa` clears the user's second factor, the break-glass for a locked-out user.
- `sso-identities` lists the providers that open the account (`read:users`): `id`, `provider_id`, `provider_name`, `provider_type`, `external_id` (the stable identity, `null` until the first sign-in binds it), `orphan_of` (the IdP key a deleted provider left, `provider_id` then `null`), `state` (`bound`, `pending` or `orphan`), `created_at`, `bound_at` and `created_by` (the administrator who attached it), `expected_tenant` (for a provider with accepted tenants, the only tenant whose sign-in may bind a pending attachment by username or e-mail; `null` for none) and `provider_tenants` (the tenants its provider accepts, `[]` for none). The user objects carry the same list as `sso_identities`, and `auth_source` is `local` (no row) or `sso`.
- `POST sso-identities` takes `{"provider_id": 1}` (required, `400` otherwise) and attaches that provider to any account; the providers it has keep opening it, and an orphan the same IdP left on it is taken back with its identity. It answers `201` with the user, `409` when the provider is already attached (reset its identity instead) or when the identity of that orphan already opens another account through the provider, `404` for an unknown user or provider. The next sign-in through the provider with the account's username or email binds its identity. A password the account has is kept unless `"remove_password": true` is sent (a boolean, `400` otherwise), which removes it and any pending reset link so no password login opens the account (the password reset by e-mail sends it no link either; `400` on the caller's own account), and an account without password is not asked to set one. For a provider with accepted tenants, `"expected_tenant"` names the tenant whose sign-in may bind the attachment by username or e-mail (one of the accepted tenants, `400` otherwise, and `400` for a provider without them); without it no sign-in binds it. Audit action `user_sso_attach`, which names the account's providers before.
- `POST sso-identities/{identity_id}/reset` clears the stable identity of that attachment (the IdP changed it): the next sign-in through the provider with the account's username or verified e-mail binds the new one. An attachment not bound yet is left as it is (`200`, nothing closed). For a provider with accepted tenants, the binding sign-in must come from the expected tenant: by default the tenant of the cleared `<tid>/<sub>` while the provider still accepts it, else none; `{"expected_tenant": "<tid>"}` sets another accepted one (`400` otherwise) and `null` none, also on an attachment not bound yet. Audit action `user_sso_reset`.
- `DELETE sso-identities/{identity_id}` detaches that provider; the account's other providers keep opening it. When the last one goes the account becomes local, and one without password must set one (`force_password_change`); `409` while a local account already uses its e-mail (e-mail is unique among local accounts). Audit action `user_sso_detach`; `404` for an attachment of another account.
- Attaching, resetting and detaching close the account's sessions (the caller's own session stays) and give their count in `meta.other_sessions_closed` (`null` when the session store cannot count them); API keys, security keys and mTLS certificates are kept. They need `write:users`, a permission reserved to the administrator role (`403` otherwise), and an API key cannot use them on its owner's account.
- `bulk/delete` needs `delete:users` and an admin caller, and takes `{"ids": [...]}` (a non-empty list of at most 100). Each user is deleted with the mTLS certificates it enrolled. The result lists `success` ids, `failed` entries (`{id, error}`: own account, last active admin, pending approval requests, not found) and `unrevoked` certificates left valid.
- `password-policy` and `password-strength` are public: the first returns the password requirements, the second takes `{"password": "..."}` and returns its strength.

### User mTLS Certificates (admin)
```http
GET /api/v2/users/{user_id}/mtls/certificates
POST /api/v2/users/{user_id}/mtls/certificates
DELETE /api/v2/users/{user_id}/mtls/certificates/{cert_id}
```
Permission `admin:users`. `POST` takes `mode`: `generate` (default) issues a certificate for the user from `ca_id` (or the configured mTLS CA; `validity_days` default 365, `name` optional) and returns the `certificate` and `private_key` once; `import` takes `pem` (required) and `name` and enrolls an existing certificate (`409` when it is already enrolled, `400` when revoked or invalid). `201` in both cases. `DELETE` removes the enrolment (`404` for an unknown user or certificate).

---

## Roles & Permissions (RBAC)

### List Roles
```http
GET /api/v2/rbac/roles
```

**Response:**
```json
{
  "data": {
    "roles": ["admin", "operator", "auditor", "viewer"],
    "role_permissions": {
      "admin": ["*"],
      "operator": ["read:*", "write:certificates", "write:cas", ...],
      "viewer": ["read:*"]
    }
  }
}
```

### Get Role Details
```http
GET /api/v2/rbac/roles/{role}
```

### List All Permissions
```http
GET /api/v2/rbac/permissions
```

### Update or Delete a Custom Role
```http
PUT /api/v2/rbac/roles/{role_id}
DELETE /api/v2/rbac/roles/{role_id}
```

Renaming or deleting a custom role that an SSO provider's `role_mapping` cites is refused with `409`; the message lists the providers. Update the mapping first. A user's `custom_role_source` is `"sso"` when the role came from the SSO role mapping and `null` when it was assigned by hand; writing `custom_role_id` through `PUT /api/v2/users/{user_id}` resets it to `null`.

### Custom Roles and Effective Permissions
```http
POST /api/v2/rbac/roles
GET /api/v2/rbac/effective-permissions/{user_id}
GET /api/v2/groups/available-permissions
```
Permission `admin:users` for the first two, `read:groups` for the third. `POST` creates a custom role: `name` (required, letters, digits, spaces, hyphens and underscores, not a built-in name: `409`; unique: `409`), `description`, `permissions` (a list drawn from `GET /api/v2/rbac/permissions`) and `inherits_from`. `effective-permissions` returns exactly what authorization applies to a user. `available-permissions` returns the sorted list of permissions a group may grant.

---

## Dashboard

### Get Statistics
```http
GET /api/v2/dashboard/stats
```

**Response:**
```json
{
  "data": {
    "total_certificates": 150,
    "active_certificates": 120,
    "expired_certificates": 25,
    "revoked_certificates": 5,
    "expiring_soon": 8,
    "total_cas": 3,
    "total_csrs": 12,
    "pending_csrs": 3
  }
}
```

### Get Expiring Certificates
```http
GET /api/v2/dashboard/expiring-certs?days=30&limit=10
```

### Get Recent CAs
```http
GET /api/v2/dashboard/recent-cas?limit=5
```

### Get Recent Activity
```http
GET /api/v2/dashboard/activity?limit=20&offset=0
```

A database failure returns 500, never an empty `activity` list.

### Get System Status
```http
GET /api/v2/dashboard/system-status
```

Any authenticated caller. Each service is a `{status, message}` pair, `status` being `online`, `warning` or `offline`: `database`, `acme`, `scep`, `est`, `ocsp`, `crl`, `tsa` and `core` for every caller, `key_encryption` only for a caller holding `admin:system`, and `smtp`, `webhooks` and `auto_renewal` only for a caller holding `read:settings` (the gate and the rules of the same witnesses on `/dashboard/health`; one that cannot be read is `{"status": "warning", "message": "Status unavailable"}`).

**Response:**
```json
{
  "data": {
    "database": { "status": "online", "message": "Connected" },
    "acme": { "status": "online", "message": "Enabled" },
    "smtp": { "status": "online", "message": "Host: mail.example.com" },
    "webhooks": { "status": "offline", "message": "No endpoints" },
    "auto_renewal": { "status": "online", "message": "Scheduled" },
    "core": { "status": "online", "message": "Operational" }
  }
}
```

### Get Certificate Trend
```http
GET /api/v2/dashboard/certificate-trend?days=30
```

**Response:**
```json
{
  "data": {
    "trend": [
      { "date": "2026-01-28", "issued": 5, "revoked": 1 },
      { "date": "2026-01-29", "issued": 3, "revoked": 0 }
    ]
  }
}
```

### Overview Aggregates
```http
GET /api/v2/dashboard/queue?limit=100
GET /api/v2/dashboard/queue?kind=crl_due&kind=crl_missing
GET /api/v2/dashboard/health?days=7
GET /api/v2/dashboard/compliance
GET /api/v2/dashboard/issuance?days=7
GET /api/v2/dashboard/expirations?days=90
GET /api/v2/dashboard/revocation?limit=10
```
Scope `read:dashboard`. A `days` outside its range is refused with 400.

`queue` lists `{kind, tier, id, label, due_at, href_hint}` items, critical first then by `due_at` (at most `limit`, 100); an expired trust anchor comes after the other critical items, the most recently expired first, with the full total per kind in `counts`. A repeated `kind` restricts the items, not the counts, to those kinds; an unknown kind is refused with 400:

| kind | critical | warning |
|------|----------|---------|
| `acme_order_failed` | invalid server order of the last 7 days | |
| `acme_client_renewal_failed` | client order with renewal failures | |
| `approval_pending` | expires within 24 h | otherwise |
| `scep_request_pending`, `key_recovery_pending` | | always |
| `crl_due` | newest full CRL stale | `next_update` within min(24 h, half the CA's CRL validity) |
| `crl_missing` | active CA with CDP and no CRL | |
| `manual_renewal_due` | expires within 24 h | expires within 30 days |
| `client_renewal_overdue` | | protocol certificate without a stored key, expires within 7 days |
| `auto_renewal_blocked` | due for auto-renewal (within `auto_renewal_days` of expiry and in the last third of its lifetime), its CA offline, revoked, expired or keyless | |
| `renewal_declined` | | renewal rejected by an approver during the current lifetime, expires within 30 days, not superseded by a live certificate |
| `ca_expiring` | expires within 90 days | expires within a year |
| `deploy_binding_left_behind` | deploy binding a renewal left on the previous certificate; `href_hint` is `/certificates/{certificate_id}?binding={id}` | |
| `https_binding_left_behind` | HTTPS binding a renewal left on the previous certificate | |
| `truststore_expiring` | trust anchor already expired, however long ago | trust anchor expiring within 90 days |

`truststore_expiring` needs `read:truststore`: without it the kind is neither listed nor counted. `href_hint` is `/truststore/{id}`.

Certificates counted are issued, not revoked, not archived and not expired. A certificate appears under one kind only, by precedence `auto_renewal_blocked` > `renewal_declined` > `manual_renewal_due` > `client_renewal_overdue`. `manual_renewal_due` leaves out what auto-renewal, the enrolling client (ACME, SCEP, EST, WSTEP without a stored key), UCM's ACME client or the delegated OCSP responder task renews, a declined renewal, and a certificate superseded by a live one beyond the 30 days with the same subject, DNS and IP SANs from the same CA.

`href_hint` carries the object in the query (`request`, `order`, `ca`) and the tab (`tab`) the page reads; `contracts/queue_links.json` lists them. `GET /api/v2/key-recovery/{id}` (`read:key_recovery`) reads one recovery request like the two reads above.

`health` gives per protocol (`acme`, `scep`, `est`, `tsa`, `scheduler`) the `basis` it is measured on and, for `acme`, `scep` and `est`, one `{date, ok, failed}` entry per UTC day (`days` 1 to 30) in `periods`; `periods` is null for `tsa` and `scheduler`. `tsa` is present while the TSA is enabled, with the `state`, `alert` and `severity` of the table below. `scheduler` carries `by_status` and `stale`, which the latest `last_status` does not replace. `smtp`, `webhooks` and `auto_renewal` are present only for a caller holding `read:settings`, with a `state` and no series: `smtp` is `not_configured`, `disabled`, `incomplete` (port or From address missing) or `ready`; `webhooks` is `not_configured`, `none_active` or `active` (`count`); `auto_renewal` is `enabled` or `disabled`; a witness whose read fails is `unavailable`, with `alert` true. `alert` is true for `disabled` and `incomplete` mail and for `none_active`, never for a setting that is simply not configured. `compliance` counts the live certificates by key algorithm and weakness; each counter, and each key algorithm, carries `filter_available` and a `filter_hint`: query parameters that the certificate list applies as given and that reproduce the count exactly (see below). `population` names the set counted, the one `GET /api/v2/certificates/compliance` scores: `{"definition": "active", "criteria": ["issued", "not_revoked", "not_archived", "not_expired"], "filter_hint": {"live": "true"}, "count": 211}`. `compliant` counts its certificates under none of the five counters. `score` is `{average, grade, distribution}`: the average compliance score (0 to 100, rounded), its grade (null on an empty set) and the number of certificates per grade `A+` to `F`, the figures of `/certificates/compliance`.

`issuance` gives per CA and per day (`days` 1 to 90) `issued` (by `created_at`) and `renewed` (in place, by `renewed_at`: the last renewal of each certificate in the window, so a certificate renewed several times counts once), and the issuances per source. `flow` counts issuances and in-place renewals together per UTC day and source group: `groups` maps `acme` (`acme`, `acme_client`, `letsencrypt`), `scep`, `est`, `wstep` and `import` to their sources, `manual` taking every other source, unset included; `periods` holds `{date, acme, scep, est, wstep, import, manual, total}` per day, `by_group` and `total` the window, and `previous` (`from`, `to`, `by_group`, `total`) the `days` days before it, where a certificate renewed in both periods counts in the later one only.

```json
"flow": {
  "groups": {"acme": ["acme", "acme_client", "letsencrypt"], "scep": ["scep"], "est": ["est"], "wstep": ["wstep"], "import": ["import"], "manual": null},
  "periods": [{"date": "2026-11-22", "acme": 4, "scep": 1, "est": 0, "wstep": 0, "import": 0, "manual": 2, "total": 7}],
  "by_group": {"acme": 121, "scep": 30, "est": 12, "wstep": 0, "import": 3, "manual": 18},
  "total": 184,
  "previous": {"from": "2026-09-24", "to": "2026-10-23", "by_group": {"acme": 98, "scep": 25, "est": 10, "wstep": 0, "import": 1, "manual": 17}, "total": 151}
}
```

`expirations` (`days` 1 to 365, 90 by default) counts, per UTC day from today to `days` - 1 days ahead, the issued certificates not revoked that expire that day, today from now on (archived ones included: the list's `valid` and `expiring` statuses together). Each `periods` entry is `{date, total, manual, automatic, signers, cas, infrastructure}`: `automatic` counts the sources in `automatic_sources` (`acme`, `letsencrypt`, `scep`, `est`, `wstep`, `acme_client`), `manual` the rest; `signers` the dedicated TSA signer and delegated OCSP responders among them; `cas` the active CAs (not revoked, not expired, holding their certificate) expiring that day, which are not certificates and not in `total`; `infrastructure` is true when `signers` or `cas` is. The top level repeats `days`, `from`, `to`, `after` (the instant counted from), the totals, and a `filter_hint` that reproduces the window in the certificate list; one day or week is the same `status` with `expires_from` set to its first day and `expires_to` to the day after its last.

```json
{
  "days": 90, "from": "2026-11-22", "to": "2027-02-19", "after": "2026-11-22T14:03:00.120000Z",
  "total": 64, "manual": 40, "automatic": 24, "cas": 1, "signers": 0,
  "automatic_sources": ["acme", "letsencrypt", "scep", "est", "wstep", "acme_client"],
  "filter_hint": {"status": ["valid", "expiring"], "expires_to": "2027-02-20"},
  "periods": [{"date": "2026-12-14", "total": 10, "manual": 8, "automatic": 2, "signers": 0, "cas": 0, "infrastructure": false}]
}
```

`revocation` sorts the active CAs (not revoked, not expired, holding their certificate) by their newest full CRL, as the queue's `crl_due` and `crl_missing` read it: `current` (next update ahead), `stale` (next update past), `missing` (distribution point, no CRL) and `no_cdp` (no distribution point), which add up to `total`; `ocsp_enabled` counts those with OCSP, `to_publish` is `stale` plus `missing`. `items` lists at most `limit` (10 by default, 100 at most) CAs with a distribution point, missing first, then stale by oldest next update, then current by next update: `{ca_id, name, state, next_update, ocsp_enabled, offline, can_publish, href_hint}`, `can_publish` false for an offline CA or one without a key.

```json
{
  "total": 136, "current": 126, "stale": 2, "missing": 1, "no_cdp": 7, "ocsp_enabled": 3, "to_publish": 3,
  "items": [{"ca_id": 12, "name": "Intermediate Tests", "state": "missing", "next_update": null, "ocsp_enabled": false,
             "offline": false, "can_publish": true, "href_hint": "/crl-ocsp?ca=12"}]
}
```

The tiles of CAs and HSM modules need no route of their own: `GET /api/v2/cas` gives each CA's validity, key (`uses_hsm`, `hsm_provider_id`, `hsm_provider_name`), `offline`, `ocsp_enabled` and `cdp_enabled`, `GET /api/v2/crl` its CRL's `next_update` and `is_stale`, `issuance?days=30` its activity per day, and `GET /api/v2/hsm/providers` each module's `status`, `last_tested_at` and `key_count`.

| `tsa` state | meaning | `alert` | `severity` |
|-------------|---------|---------|------------|
| `dedicated` | a dedicated signing certificate signs | false | null |
| `no_signer` | no dedicated signer configured and the CA certificate cannot sign in its place (a dedicated certificate is required, or no CA is designated, or the designated CA is not found, has no certificate or key, is offline, outside its validity period, revoked in its chain or has a key that does not sign timestamps): `/tsa` answers 503 | false | null |
| `ca_certificate` | the CA certificate signs (dedicated certificate no longer required): its tokens fail RFC 3161 §2.3 | true | `warning` |
| `expiring` | dedicated signer within 30 days of expiry, `days_left` | true | `critical` |
| `unusable` | dedicated signer that cannot sign, `reason`: `expired`, `revoked`, `key_unavailable` or `invalid` | true | `critical` |
| `unavailable` | the check itself failed | true | `critical` |

#### Certificate list filters

`GET /api/v2/certificates` accepts the filters below, ANDed with the existing ones. A counter and its filter are built from the same SQL expression (`services/dashboard_aggregates.py`). An unknown parameter is ignored; an invalid value of a known filter is refused with 400.

| Parameter | Meaning |
|-----------|---------|
| `live=true` | issued, not revoked, not archived, not expired (the set the compliance counters are taken over) |
| `key_algo` (repeatable) | exact `key_algo` value |
| `key_algo_prefix`, `key_bits_below` | key family (`RSA`) and a size threshold; RSA below 3072 bits is `key_algo_prefix=RSA&key_bits_below=3072`; `key_bits_below` from 0 to 1000000 |
| `sig_hash` (repeatable) | signature hash |
| `server=true`, `lifetime_over_days=N` | server certificate (type or `web_server` template), lifetime of more than N days, N from 0 to 100000 |
| `no_key=true`, `incomplete_chain=true` | no stored private key; issuing CA unknown to this instance |
| `renewal` (repeatable) | one of `manual_renewal_due`, `client_renewal_overdue`, `auto_renewal_blocked`, `renewal_declined`: the rows of that `queue` kind. `queue` returns `filter_hints` with this parameter for each |
| `expires_from`, `expires_to` | expiry from `expires_from` (included) to `expires_to` (excluded), each an ISO 8601 date (`2026-12-14`, midnight UTC) or date and time (an offset is converted to UTC) |
| `created_from`, `created_to` | creation (`created_at`) from `created_from` (included) to `created_to` (excluded), in the same forms; one day of the `issuance` flow is that day and the next. The flow also counts in-place renewals, which keep their creation date and are not in this list |

### Get Stats Overview
```http
GET /api/v2/stats/overview
```

**Response:**
```json
{
  "data": {
    "total_cas": 3,
    "total_certs": 150,
    "acme_accounts": 2,
    "active_users": 5
  }
}
```

---

## Audit Logs

### List Audit Logs
```http
GET /api/v2/audit/logs
GET /api/v2/audit/logs?page=1&per_page=50
GET /api/v2/audit/logs?username=admin&action=login_success
GET /api/v2/audit/logs?success=false&date_from=2026-01-01
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | integer | Page number |
| `per_page` | integer | Items per page (max: 100) |
| `username` | string | Filter by username |
| `action` | string | Filter by action type |
| `success` | boolean | Filter by success/failure |
| `date_from` | string | Start date (ISO format) |
| `date_to` | string | End date (ISO format) |
| `search` | string | Search in details |
| `sort_by` | string | `timestamp`, the only key (the filters do the rest) |
| `sort_order` | string | `desc` (default) or `asc`; see [Sorting](#sorting) |

**Response:**
```json
{
  "data": [
    {
      "id": 1,
      "timestamp": "2026-01-28T18:00:00",
      "username": "admin",
      "action": "login_success",
      "resource_type": "user",
      "resource_id": "1",
      "details": "Password login successful",
      "ip_address": "192.168.1.100",
      "user_agent": "Mozilla/5.0...",
      "success": true
    }
  ],
  "meta": { "page": 1, "per_page": 50, "total": 100 }
}
```

### Get Audit Log by ID
```http
GET /api/v2/audit/logs/{log_id}
```

### Get Audit Statistics
```http
GET /api/v2/audit/stats?days=30
```

**Response:**
```json
{
  "data": {
    "total_logs": 1250,
    "success_count": 1200,
    "failure_count": 50,
    "success_rate": 96.0,
    "top_actions": [
      { "action": "login_success", "count": 500 },
      { "action": "certificate_issued", "count": 200 }
    ],
    "top_users": [
      { "username": "admin", "count": 800 }
    ],
    "recent_failures": [...]
  }
}
```

### Get Available Actions
```http
GET /api/v2/audit/actions
```

### Export Audit Logs
```http
GET /api/v2/audit/export?format=json&limit=10000
GET /api/v2/audit/export?format=csv&date_from=2026-01-01
```

The export takes the filters of the list (`username`, `action` and `resource_type`, repeatable, `category`, `success`, `search`, `date_from`, `date_to`) and holds only the rows they select. A CSV text cell that starts with `=`, `+`, `-`, `@`, a tab or a carriage return is written with a leading `'`, so a spreadsheet does not run it as a formula.

### Cleanup Old Logs
```http
POST /api/v2/audit/cleanup
Content-Type: application/json

{
  "retention_days": 90
}
```

Permission `delete:audit`. `retention_days` is the number of days kept: a value under 30 is raised to 30, one above 3650 is refused with `400`.

### Verify Audit Log Integrity
```http
GET /api/v2/audit/verify
GET /api/v2/audit/verify?start_id=1&end_id=1000
POST /api/v2/audit/verify          {"start_id": 1, "end_id": 1000}
```

Permission `read:audit`. The verification runs as a [background job](#background-jobs) of
kind `audit_verify`. `GET` joins the verification already running over the same range, or
starts one; `POST` starts one and answers `409` while another runs (as does `GET` for another
range). A verification finished within 25 seconds answers `200` with the body below, as before;
a longer one answers `202 Accepted` with a `Location` to follow, its result then in the job's
`result.data`.

**Response:**
```json
{
  "data": {
    "status": "intact",
    "valid": true,
    "first_error_id": null,
    "first_error_code": null,
    "checked": 1000,
    "attested": 998,
    "unsealed": [12, 13],
    "error_count": 0,
    "errors": [],
    "protection": {
      "key_available": true,
      "protected": 600,
      "protected_from_id": 401,
      "not_attested": 400,
      "retired_key": 390,
      "key_rotation_id": 405,
      "rotation_attested": true
    }
  }
}
```

`status` is one of:

- `intact`: every entry from `protected_from_id` on is sealed by the master key, or bound by
  the first entry it sealed. `key_rotation_id` names the first entry under the current key
  when the key was changed; the `not_attested` entries before `protected_from_id` (sealed
  under a previous key, or never sealed) can no longer be attested.
- `broken`: `first_error_id` names the first entry that fails, `first_error_code` says how:
  `tampered`, `link` (does not follow the entry before it), `not_sealed_by_key` (written
  without the key after it took over), `unattested_key` (claims a key no rotation of the
  current one recorded), `truncated` (entries removed from the start outside a purge),
  `before_start` (an entry added before where the log started) or `unknown_version`. `errors` lists up to 1000 of the `error_count` violations.
- `unprotected`: no master key, or no entry sealed under it yet (entries are sealed with
  SHA-256 then, which anyone able to write the database can recompute), or entries under
  another key that this server has no record of rotating from (`rotation_attested: false`,
  for instance after a restore on another host).

`unsealed` lists entries written with no seal at all by older versions. The checks of where
the log starts apply only without `start_id` and `end_id`.

---

## Settings

### General Settings
```http
# Get settings
GET /api/v2/settings/general

# Update settings
PATCH /api/v2/settings/general
Content-Type: application/json

{
  "system_name": "pki-01",
  "default_validity_days": 365,
  "require_approval": false
}
```

Some keys need `admin:settings`: `enforce_2fa`, `session_timeout`, `session_max_lifetime`, `max_login_attempts`, `lockout_duration`, `metrics_token`, `key_recovery_dual_control`, the password policy (`min_password_length`, `max_password_length`, `password_require_uppercase`, `password_require_lowercase`, `password_require_numbers`, `password_require_special`), `hsts_enabled`, `hsts_include_subdomains`, `hsts_max_age`, the public addresses (`base_url`, `protocol_base_url`, `acme_public_vhost`, `acme_public_port`, `acme_public_tls_cert_id`), the whole backup schedule (`auto_backup_enabled`, `backup_frequency`, `backup_retention_days`, `backup_max_total_mb`, `backup_password`, `backup_kdf`, `clear_backup_password`), OCSP responder renewal (`ocsp_responder_auto_renew`, `ocsp_responder_renew_days`), the CRL housekeeping (`crl_auto_delete_expired_revoked`, `crl_auto_purge_stale_serials`), `audit_retention_days`, `admin_allowed_networks` and `compliance_profile_default`. Without it they are dropped, and the response lists them in `data.ignored_keys` (empty when nothing was dropped); a body made only of such keys is refused with 403.

### Email Settings
```http
# Get settings
GET /api/v2/settings/email

# Update settings
PATCH /api/v2/settings/email
Content-Type: application/json

{
  "enabled": true,
  "smtp_host": "smtp.example.com",
  "smtp_port": 587,
  "smtp_username": "alerts@example.com",
  "smtp_password": "password",
  "smtp_security": "starttls",
  "from_email": "alerts@example.com"
}

# Test email
POST /api/v2/settings/email/test
Content-Type: application/json

{
  "email": "test@example.com"
}
```

`smtp_security` is `none`, `starttls` or `ssl` (implicit TLS, usually port 465). The older booleans `smtp_tls` and `smtp_ssl` are still accepted and are ignored when `smtp_security` is present.

### Webhooks
See [Webhooks](#webhooks): `/api/v2/settings/webhooks` does not exist.

### Backup Settings
```http
# Get backup configuration
GET /api/v2/settings/backup

# Get backup schedule
# last_run: the latest reservation; last_outcome / last_outcome_at: the latest run that reported
# in_progress: true while a run reserved last_run and has not written its archive (two-hour lease);
#   last_run is then that run's, the outcome still the previous run's
# max_total_mb: the ceiling; stored_bytes / stored_count: what the archives retention counts take now
#   (every archive of the database in HA, the ucm_backup_*.ucmbkp files of the disk otherwise);
#   over_ceiling: true when they are above it; uncounted_count: other archive files of the directory
#   (0 in HA), neither counted nor removed by retention
# Retention (daily, or POST /api/v2/system/backups/run-retention, which returns "warning" while the
#   archives are still above the ceiling) removes the oldest archives over the ceiling and audits each
#   one (backup_delete). It never removes, on disk, the newest archive that matches its validation
#   record, up to 2 archives with no validation record and the backup_min_keep newest archives not
#   found altered; in HA, the backup_min_keep newest archives
GET /api/v2/settings/backup/schedule

# Update backup schedule
PATCH /api/v2/settings/backup/schedule
Content-Type: application/json

{
  "enabled": true,
  "frequency": "daily",
  "time": "02:00",
  "retention_days": 30,
  "max_total_mb": 0,              # size ceiling of all archives in MiB, 0 = none (400 when negative, above 1048576 or not a whole number)
  "kdf": "pbkdf2"                 # auto (default), pbkdf2 or argon2id; argon2id refused in FIPS mode
}

# Create backup ("kdf": "pbkdf2" writes an archive a FIPS-mode instance can restore)
# Removes nothing for the ceiling: "warning" is set when the archives are then above it, null otherwise
# A background job (see Background Jobs): 200 as before within 25 s, else 202. Without "password"
# one is generated and given in this answer only ("password", "password_generated"), 200 or 202:
# the job never holds it in clear and its result does not carry it
POST /api/v2/settings/backup/create
{
  "password": "...",
  "kdf": "pbkdf2"
}

# List backups (in HA, each item carries "node" and "sha256")
GET /api/v2/settings/backup/history

# Download backup (Range, ETag and Repr-Digest as for /api/v2/system/backup/{filename}/download)
GET /api/v2/settings/backup/{backup_id}/download

# Restore backup (in HA, as POST /api/v2/system/backup/restore: see Backup Operations)
# A background job, like the system route: 200 as before within 25 s, else 202 (see Background Jobs)
POST /api/v2/settings/backup/restore
Content-Type: multipart/form-data

# Delete backup
DELETE /api/v2/settings/backup/{backup_id}
```

### Certificate Transparency
```http
GET /api/v2/settings/ct
PATCH /api/v2/settings/ct
Content-Type: application/json

{ "enabled": true, "log_urls": ["https://ct.example.com/log"], "auto_submit": false, "embed_sct": false, "required": false }
```
`GET` needs `read:settings`, `PATCH` needs `admin:settings`; all fields are optional. `log_urls` is a list of http or https URLs that must resolve and not to loopback or a cloud metadata address, or `null` for the built-in list (`400` otherwise). The `GET` response has the same five fields. Submission of a single certificate is `POST /api/v2/certificates/{cert_id}/submit-ct`.

### Auto-Renewal
```http
GET /api/v2/settings/auto-renewal
PATCH /api/v2/settings/auto-renewal
POST /api/v2/settings/auto-renewal/run
```
`GET` (`read:settings`) and `PATCH` (`write:settings`) use `enabled`, `days_before_expiry` (an integer), `renewal_sources` (a list; default `manual`, `scep`, `acme`, `est`), `notify_on_renewal`, `notify_on_failure` (both default true) and `notify_emails` (a list of valid addresses); `400` for a wrongly typed value. `run` (`admin:settings`) triggers a renewal pass now and returns its counts `renewed`, `failed` and `skipped`.

### Notifications
```http
GET /api/v2/settings/notifications
PATCH /api/v2/settings/notifications
GET /api/v2/settings/notifications/logs?type=cert_expiring&page=1&per_page=50
```
All need `read:settings` (`write:settings` for `PATCH`). `GET` returns `configs`, each with `id`, `notification_type`, `enabled`, `recipients`, `threshold_days`, `alert_days` (expiry notifications only), `cooldown_hours` and `description`. `PATCH` identifies a config by `id` (`404` when unknown) or by `notification_type` (created when it does not exist; `400` when neither is sent) and changes `enabled`, `recipients`, `threshold_days` (an integer) and `cooldown_hours` (an integer from 0 to 8760). `logs` returns `logs` (`notification_type`, `recipient`, `subject`, `sent_at`, `status`, `error_message`, `retry_count`) and `pagination`.

### Email Templates and SMTP OAuth
```http
GET /api/v2/settings/email/template
PATCH /api/v2/settings/email/template
POST /api/v2/settings/email/template/preview
POST /api/v2/settings/email/template/reset
GET /api/v2/settings/email/oauth/providers
POST /api/v2/settings/email/oauth/authorize-url
GET /api/v2/settings/email/oauth/callback
POST /api/v2/settings/email/oauth/revoke
```
- `template` reads need `read:settings`, changes `write:settings`. `GET` returns the HTML `template` and `text_template` in force (the defaults when none is customized), `is_custom`, `is_text_custom` and the two defaults. `PATCH` takes `template` and/or `text_template` (`400` for an empty body). `preview` renders `template` of `type` `html` (default) or `text` with sample data and returns it under `html` or `text`. `reset` restores both defaults.
- `oauth/providers` (`read:settings`) returns the provider presets (`smtp_host`, `smtp_port`, TLS flags, `needs_tenant`, `default_tenant`).
- `oauth/authorize-url` (`write:settings`) builds the consent URL from the saved SMTP settings (`404` when none are saved) and returns `authorize_url` and `redirect_uri`; optional `redirect_uri` in the body. The state is kept in the caller's session.
- `oauth/callback` (`write:settings`) is the redirect target: it exchanges `code` for tokens, stores the refresh token and answers an HTML page saying whether authorization succeeded (state mismatch, missing parameters and provider errors are reported there).
- `oauth/revoke` (`write:settings`) drops the stored refresh and access tokens (`404` when no SMTP settings exist).

### Public Endpoints
```http
GET /api/v2/settings/public-endpoints
PATCH /api/v2/settings/public-endpoints
POST /api/v2/settings/public-endpoints/preflight
```
`GET` (`read:settings`) returns the effective public URLs, CORS origins and host-role status. `cors_origins` lists the origins the API's CORS answers, read from the settings at each request: `localhost`, the admin base URL as written and with the port UCM serves, and `CORS_EXTRA_ORIGINS` except an IPv6 origin, each with its scheme and host in lower case and without a default port (`https://ucm.example.com:443` is listed as `https://ucm.example.com`). The Socket.IO channel accepts these, the host's own names and an IPv6 origin of `CORS_EXTRA_ORIGINS`. `PATCH` (`write:settings`) updates the admin, protocol and ACME public endpoint settings with the same body and validation as `PATCH /api/v2/settings/general`. `preflight` (`write:settings`) runs DNS and TLS diagnostics for the configured admin and ACME hosts.

### Settings Audit Logs
```http
GET /api/v2/settings/audit-logs?user_id=1&action=login&start_date=2026-01-01&end_date=2026-02-01&page=1&per_page=50
```
Permission `admin:system`. Audit entries, newest first, with `meta` (`total`, `page`, `per_page`). `start_date` and `end_date` are ISO 8601 and ignored when unparsable. The fuller audit routes are under [Audit Logs](#audit-logs).

---

## System

### Background Jobs

Long operations (the manual backup, the audit chain verification) run outside the web
worker, in the scheduler process. The route that starts one waits at most 25 seconds:

- finished by then, it answers exactly what it answered before jobs existed (code, `message`,
  `data`);
- otherwise `202 Accepted`, a `Location: /api/v2/system/jobs/<id>` header and
  `{"data": {"job": {...}}}`.

`Prefer: respond-async` (RFC 7240) answers `202` at once, with
`Preference-Applied: respond-async`; `Prefer: wait=N` shortens the wait to `N` seconds (never
beyond 25). A second start while the job's slot is taken answers `409` with
`details.job` naming the active job (`id`, `kind`, `state`, `created_at`, `requested_by`).
One job is active per slot on the whole installation, HA cluster included. During an HA
cluster maintenance no job starts: `GET` and `POST` of a starting route both answer `503`
with `Retry-After: 30`, code `maintenance` and the message `A cluster maintenance is in
progress, no background job starts until it ends`, and no job is created. A `GET` that would
join a job already running answers `503` too: follow that job at `GET /api/v2/system/jobs/<id>`.

```http
GET  /api/v2/system/jobs                  # ?kind=backup|audit_verify&state=active|final&limit=20 (max 100)
GET  /api/v2/system/jobs/<id>
POST /api/v2/system/jobs/<id>/cancel
```

Each job is read and cancelled with its own permission (`admin:system` for `backup`,
`read:audit` for `audit_verify`); the
list shows only the kinds the caller may read, and the id of another kind answers `404`.

```json
{
  "data": {
    "id": "0b6f5c1e-...", "kind": "audit_verify", "state": "running", "reason": null,
    "phase": "verifying", "progress": {"done": 400000, "total": 1000000},
    "cancel_requested": false, "requested_by": {"id": 1, "username": "admin"},
    "created_at": "2026-11-16T10:00:00Z", "started_at": "2026-11-16T10:00:01Z",
    "finished_at": null,
    "result": null
  }
}
```

- `state`: `pending`, `running`, then one of `succeeded`, `failed`, `cancelled`.
- `reason` once final: `done`; `refused` (the operation answered a `4xx`, kept in `result`);
  `error` (the operation answered a `5xx`, kept in `result`, or its run failed, `result` then
  `null`); `cancelled`; `executor_lost` (the process running it stopped: run it again) or
  `not_taken` (no process took it within 5 minutes). A lost job is never started again on its own.
- A `restore` job that committed but could not finish (sessions not revoked, or a later step
  failed) ends `succeeded`, reason `done`, with `result.code` 500: the backup is restored, and `result.message`
  asks to restart the application before using it.
- `result` once final, for `done`, `refused` and an `error` the operation answered:
  `{"code", "message", "data"}`, the answer the starting route would have given, plus
  `problem_type` when that answer was a typed problem (RFC 9457 `type`, such as a refusal in FIPS
  mode); `null` otherwise.
- Cancel: a pending job ends at once (`200`, `Job cancelled`); a running one stops at its next
  page (`200`, `Cancellation requested`); an ended one answers `409`. A backup stops between two
  sections of the export, or within a second inside one: no archive is kept. During a cluster
  maintenance, or a restore on a single node, the cancel route answers the maintenance's `503`
  for every job but the restore holding it.

A job of an audited operation (the backup) writes one audit line when it ends. If that write
fails twice, the job still ends, without the line, and the service log records it at level
`ERROR` (`Background job <id> concluded without its audit line: ...`, with the line's action,
resource, success and phrase).

A finished job is kept 30 days, and the latest of each kind always.

A `restore` job (`admin:system`) holds every slot: nothing else runs beside it. Its `phase` is
`checking`, `reading`, `applying` and `committing`, then, once the restore has committed,
`committed`, `sessions_revoked`, `session_files_removed`, `caches_purged` and
`crls_regenerated` as each step after the commit is done; `progress` is empty while the archive
is read, then counts the steps passed and the rows written (`total`: the ten steps plus the rows
the archive carries) and reaches its total at the commit. While the restore's SQLite transaction
holds the database, `phase` and `progress` come from the restore's local state; from `committed`
on, and on PostgreSQL, from the job's row. It can be cancelled until its commit:
nothing is restored, and a cancellation is read inside the loops over the rows too. From
`committed` on, the cancel route answers `409` `The restore has committed: it can no longer be
cancelled`. A restore that commits revokes every session, the caller's included: following the
job then answers `401`; sign in again and read the job, whose `result` is the restore's answer.
A restore whose process stopped before its commit fails (`executor_lost`, `The restore stopped
before it committed: nothing was restored`); one that stopped after it is finished by the next
start of the scheduler process, each step done once. A restore refused by the HA maintenance
keeps its members in `result.problem` (`code`, and `nodes` for `maintenance_not_acknowledged`),
and the route answers them as before. Every audit line of a restore job names its archive, a
cancelled, lost or never started one included.

### Database Operations
```http
GET /api/v2/system/database/stats
```
Permission `read:settings`. Returns `size_mb`, `counts` (`cas`, `certificates`, `crls`, `ocsp_responses`), `last_vacuum` and `last_check` (a timestamp or `"Never"`).

```http
GET /api/v2/system/database/export
```
Permission `admin:system`. Downloads a SQL dump (`application/sql`). Only a SQLite database can be dumped; on PostgreSQL the call fails.

```http
POST /api/v2/system/database/optimize
```
Permission `admin:system`. Runs VACUUM and ANALYZE (SQLite and PostgreSQL). On SQLite, ANALYZE reads about 1,000 rows of each index (`PRAGMA analysis_limit`).

```http
POST /api/v2/system/database/integrity-check
```
Permission `admin:system`. Returns `passed`, `errors` and a message. On PostgreSQL the check verifies connectivity and counts the schema's tables.

```http
POST /api/v2/system/database/reset
```
Permission `admin:system`. Dangerous: drops and recreates every table, then seeds the configured administrator as at first start. No request body is read. `409` when the initial administrator password cannot be settled (nothing is dropped); `500` when the reset happened but the administrator could not be created.

### Database Backend
Moving UCM between SQLite and PostgreSQL. `switch` and `migrate` answer `409` in HA mode (`ha_mode`), `409` while a migration holds the lock or a switch awaits its restart, and `500` with a generic message on an unexpected failure. Connection URLs in responses and audit entries are redacted.

```http
GET /api/v2/database/status
```
Permission `read:settings`. The current backend: type, version, size, table count and health.

```http
POST /api/v2/database/test
Content-Type: application/json

{ "database_url": "postgresql://..." }
```
Permission `admin:settings`. Opens a test connection; returns `{success, message}`. `400` when `database_url` is missing.

```http
POST /api/v2/database/switch
Content-Type: application/json

{ "database_url": "postgresql://..." }
```
Permission `admin:settings`. Switches the backend without copying data: the auth, RBAC, SSO and MFA tables are bootstrapped to the empty target so administrators are not locked out, the configuration is persisted and the service restarts. An empty or null `database_url` reverts to the default SQLite file. `400` in a container (set `DATABASE_URL` on it instead) or when the target is unreachable; `503` on a transient bootstrap failure (retrying resumes). Returns `persisted`, `bootstrap`, `validation`, `restart_initiated`, `restart_message`.

```http
POST /api/v2/database/migrate
Content-Type: application/json

{ "database_url": "postgresql://..." }
```
Permission `admin:settings`. Copies all data from the current backend to the target and verifies it; `database_url` is required (`400`). On a native install the configuration is then persisted and the service restarts; in a container only the data moves (`docker: true`, `next_step` tells what to set). Returns `migrated`, `stats`, `proof`, `restart_initiated`. A refusal before anything was written to the target is `409`; a failure once the copy was under way is `500`.

### HTTPS Certificate
`cert-info` returns `bound_certificate.needs_attention` (`reason`, `successor_id`, `successor_refid`, `successor_descr`,
`successor_has_key`, `successor_archived`) when a renewal left the HTTPS binding on the previous certificate, else `null`; applying a
certificate or unbinding clears it, and importing the renewed certificate's key moves the binding to it.
Its `fingerprint` is the whole SHA-256 of the certificate, in colon-separated uppercase hex (`-` when no certificate could be read).
`served` compares it with the certificate the TLS listener presents, read on the server as the listener loaded its files:
`fingerprint` (same notation) and `matches`, `false` for a certificate written but not served yet, `null` (with a `null`
fingerprint) when the process answering serves no TLS listener.
`regenerate` and `apply` answer `listener_reload`: `reloading` (outside HA, in a container as under systemd, the gunicorn
master was sent SIGHUP: it re-reads its configuration and replaces its workers, which load the new files, without the
service stopping), `restarting` (DEB/RPM without a gunicorn master to signal: the service restarts), `rolling` (HA: a
rolling restart) or `failed`, with `error`, a message saying the listener was not reloaded and an error in the service log.
```http
# Get current certificate info
GET /api/v2/system/https/cert-info

# Regenerate self-signed certificate
POST /api/v2/system/https/regenerate
Content-Type: application/json

{
  "common_name": "ucm.example.com",
  "validity_days": 365
}

# Apply a managed certificate (with its private key) to HTTPS
POST /api/v2/system/https/apply
Content-Type: application/json

{
  "cert_id": 42
}
```
`password` opens an encrypted input (PKCS#12, encrypted key). `output_password` (the older name `pkcs12_password` is still accepted; two different values answer `400`) protects the OUTPUT: it is required for `pkcs12` and `jks`, and encrypts a private key written as `pem` (PKCS#8, 8 to 256 characters, else `400`). A `der` output that would carry a private key refuses an `output_password` with `400`; with a certificate or a request in `der`, a `pkcs7` output, or a `pem` without a key, it is ignored. A value that is not a string answers `400` whatever the output.

### Backup Operations
```http
# List backups (page, per_page, search, sort)
# In HA, meta.storage is "database" and each item carries "node" and "sha256";
# on a single node meta.storage is "disk" and meta carries the disk figures
GET /api/v2/system/backup/list
GET /api/v2/system/backups

# Create backup (body: "password", optional "kdf": "pbkdf2" or "argon2id"; POST /api/v2/system/backup is the same route)
# Removes nothing for the ceiling: "warning" is set when the
# archives are then above it, null otherwise; the next retention applies it
# A background job of kind "backup" (see Background Jobs): within 25 s the answer of before
# (200, or 400, 409 and 500 with their messages), else 202 with the job, its "result.data" once
# succeeded; 409 naming the job while another backup is active; the password is stored only
# encrypted until the job is taken, then cleared
POST /api/v2/system/backup/create
POST /api/v2/system/backup

# Download backup (in HA from any node, with a Repr-Digest: sha-256=:...: header)
# Resumable: a Range of one byte range answers 206 with Content-Range, 416 past the end;
# ETag, If-None-Match (304) and If-Range apply. In HA the ETag is the archive's SHA-256
# and a Range of several ranges gets the whole archive (200).
GET /api/v2/system/backup/{filename}/download

# Restore backup (POST /api/v2/system/restore is the same route; multipart "file", "password", optional "mode")
POST /api/v2/system/backup/restore
POST /api/v2/system/restore
```

In HA mode a restore holds the cluster maintenance (see [HA](HA.md#restoring-a-backup)). It answers `409` with
code `maintenance_in_progress` while another maintenance holds, `maintenance_not_acknowledged` when a node with a
fresh heartbeat did not acknowledge it within 30 s (`nodes` maps each one to the processes missing, `web` or
`scheduler`), and `maintenance_lost` when the maintenance ended or was lifted before the commit; in each case
nothing is restored. Both restore routes answer `409` "The restore was refused: this server cannot write to
<directories>. Nothing has been changed." when the CA, certificate or key directory is not writable, and `409`
when the backup lock cannot be taken. A restore writes no file: `data.files` gives the files `generation` it
committed and the number of `removals` listed, and each node then reconciles its files (see the
[Administration Guide](ADMIN_GUIDE.md#files-after-a-restore)). A successful restore answers `restart_detail` "Rolling restart requested: the nodes
restart one at a time". Both restore routes also answer `data.todo`, a list of strings with one line per warning
(sections not restored, a CA whose CRL could not be signed, a secret to enter again); it is empty when there is
nothing to do. The backup listing's `meta.restore_limits` gives `upload_bytes` (archives before v4) and
`archive_bytes` (v4, `0` for no ceiling), the sizes a restore accepts.

Both restore routes start a background job of kind `restore` (see Background Jobs). The route
keeps the uploaded archive in a file of its own, still encrypted, and answers what it answered
before when the restore ends within 25 seconds, failures included: a wrong password of a v4
archive is still refused at once, that of an older archive once the job has decrypted it, with
the same `400`. Past 25 seconds it answers `202`. While a restore runs, on a single node as in
HA, writes answer `503` with `Retry-After: 30`, code `maintenance` and the message `This UCM
instance is restoring a backup: writes are refused until the restore ends. Retry later.`
(single node); reads, OCSP, CRL, health and `GET /api/v2/system/jobs/<id>` are served. On a
single node with SQLite, while the restore's transaction holds the database (or its writes keep
it locked past a request's one-second wait), only the health probes, `GET /api/v2/system/jobs/<id>` and `POST /api/v2/system/jobs/<id>/cancel` of the restore
are answered, from its local state and for a session or API key checked during this restore
(same host; a session also sends its CSRF token; a start request still waiting when the restore
begins checks its caller again at that moment): a credential not checked since the restore began answers
`503`, a request with none `401`. A start request waits out the held database on the
restore's local state: a restore that ends within the wait answers its result, one still held when
the wait ends answers `202` with the job as its local state shows it. Every other request answers `503` with
`Retry-After: 30` and the message `This UCM instance is restoring a backup and its transaction
holds the database: only the health checks and the restore job are served until it ends. Retry
later.`; OCSP answers the `tryLater` status (RFC 6960 section 2.3). A request that meets a SQLite
lock outside a restore and would answer `500`, whether or not its route caught the error, answers
`503` with `Retry-After: 5` and the problem type `urn:ucm:problem:database-busy` instead; a route that answers another status for it keeps that status. Another
job, or a second restore, answers `409` naming the active job, and no archive file is kept.

```http
DELETE /api/v2/system/backup/{filename}
POST /api/v2/system/backups/bulk-delete
POST /api/v2/system/backups/run-retention
```
All need `admin:system`. The first deletes one archive (`400` for an invalid name, `404` when missing, `409` while a backup or restore holds the lock). The second takes `{"filenames": ["..."]}` (a non-empty list of at most 1000 names) and returns the counts `deleted`, `missing`, `invalid`, `failed`. The third applies the retention policy now and returns `removed` and `warning`.

### Cluster Maintenance (HA)
`admin:system`. A node in maintenance answers its writes with `503`, `Retry-After: 30` and code `maintenance`;
these three routes stay served. Outside HA, `POST` and `DELETE` answer `409`.
```http
# The maintenance (reason, phase, node_id, actor, started_at, expires_at, restored_at, or null),
# whether the answering node refuses writes, and each node's acknowledgement
GET /api/v2/system/maintenance

# Set it by hand (or extend a manual one), once every fresh node acknowledged it;
# 409 maintenance_not_acknowledged (with "nodes") or maintenance_in_progress otherwise
POST /api/v2/system/maintenance
Content-Type: application/json

{"lease_minutes": 60}

# Lift it, from any node; a restore that committed is completed first (sessions revoked,
# rolling restart requested)
DELETE /api/v2/system/maintenance
```

### Chain Repair
```http
# Get chain repair status and last run stats
GET /api/v2/system/chain-repair

# Response:
{
  "task": {
    "name": "ski_aki_backfill",
    "description": "Backfill SKI/AKI and repair certificate chain links",
    "enabled": true,
    "interval": 3600,
    "last_run": "2026-02-12T01:51:14.502202Z",
    "next_run": "2026-02-12T02:51:14.502204Z",
    "run_count": 2,
    "last_duration_ms": 9.2,
    "last_error": null
  },
  "stats": {
    "total_cas": 4,
    "total_certs": 39,
    "orphan_cas": 1,
    "orphan_certs": 1,
    "updated_cas": 0,
    "updated_certs": 0,
    "rechained_cas": 0,
    "rechained_certs": 0,
    "deduplicated": 0
  }
}

# Trigger chain repair immediately
POST /api/v2/system/chain-repair/run

# Response: same as GET with updated stats
```

### Security - Encryption Status
```http
GET /api/v2/system/security/encryption-status
```

**Response:**
```json
{
  "data": {
    "enabled": true,
    "version": 1
  }
}
```

### Security - Enable Encryption
```http
POST /api/v2/system/security/enable-encryption
Content-Type: application/json

{
  "master_password": "secure-master-password"
}
```

### Security - Disable Encryption
```http
POST /api/v2/system/security/disable-encryption
Content-Type: application/json

{
  "master_password": "secure-master-password"
}
```

`data.key_files` says what became of the plaintext key files the disable writes: `written`, `incomplete` (a file could not be written), or `pending` when the file directories were busy (another reconciliation, a restore, another node) or could not be locked; they are then written at the next start of the service, and `key_files_written` is `0`.

### Security - Generate Encryption Key
```http
GET /api/v2/system/security/generate-key
```

**Response:**
```json
{
  "data": {
    "key": "generated-encryption-key"
  }
}
```

### Security - Rotate Secrets
```http
POST /api/v2/system/security/rotate-secrets
Content-Type: application/json

{
  "new_secret": "optional, at least 32 characters"
}
```

With encryption enabled (in HA, the KEK every node holds) the key is stored in the database and every node reloads it without a restart; the previous key stays accepted until `previous_accepted_until`, and a second rotation before then answers 409. `reloaded: false` means the answering node did not load the new key yet and retries on its own. Without encryption `SECRET_KEY` is written to `ucm.env` and the service restarts (`auto_apply: false` returns the key with manual steps instead); in HA that mode answers 409 `ha_mode`.

**Response (encryption enabled):**
```json
{
  "data": {
    "rotated": true,
    "mode": "database",
    "reloaded": true,
    "previous_accepted_until": "2026-11-13T10:00:00Z"
  }
}
```

### Security - Secrets Status
```http
GET /api/v2/system/security/secrets-status
```

**Response:**
```json
{
  "data": {
    "session_secret": {
      "configured": true,
      "source": "database",
      "previous_accepted_until": "2026-11-13T10:00:00Z",
      "rotation": "database",
      "ha": false
    },
    "encryption_key": {"configured": true}
  }
}
```

### Security - Anomaly Detection
```http
GET /api/v2/system/security/anomalies
```

### Security - Rate Limit Configuration
```http
GET /api/v2/system/security/rate-limit
PUT /api/v2/system/security/rate-limit
GET /api/v2/system/security/rate-limit/stats
POST /api/v2/system/security/rate-limit/reset
```
`GET` (`read:settings`) returns `config` and `stats`. `PUT` (`admin:system`) takes any of:

```json
{
  "enabled": true,
  "custom_limits": { "/api/v2/certificates": { "rpm": 300, "burst": 50 } },
  "whitelist_add": ["192.0.2.10"],
  "whitelist_remove": ["192.0.2.11"]
}
```
`enabled` must be a boolean, `rpm` and `burst` integers of at least 1, and the whitelists lists of IP addresses (single addresses, not networks); anything else is a 400 that names the field and stores nothing. `burst` defaults to a third of `rpm`, at least 1. The change is stored in the database, so it survives a restart, and read again when UCM starts; in HA mode it is also applied on every node. Only the process that answers applies it at once; any other worker process reads it when it starts. `stats` (`read:settings`) returns the counters. `reset` (`admin:system`) clears the buckets, of one address with `{"ip": "..."}` or all, and the statistics too with `{"reset_stats": true}`.

### Audit Retention
```http
# Get retention settings
GET /api/v2/system/audit/retention

# Update retention settings
PUT /api/v2/system/audit/retention
Content-Type: application/json

{
  "retention_days": 90
}

# Manual cleanup
POST /api/v2/system/audit/cleanup
Content-Type: application/json

{
  "retention_days": 90
}
```

### Syslog Configuration
```http
# Get syslog settings
GET /api/v2/system/audit/syslog

# Update syslog settings
PUT /api/v2/system/audit/syslog
Content-Type: application/json

{
  "host": "syslog.example.com",
  "port": 514,
  "protocol": "udp",
  "enabled": true
}

# Test syslog connection
POST /api/v2/system/audit/syslog/test
```

### Expiry Alerts
```http
# Get alert configuration
GET /api/v2/system/alerts/expiry

# Update alert configuration
PUT /api/v2/system/alerts/expiry
Content-Type: application/json

{
  "days": 30,
  "enabled": true,
  "recipients": ["admin@example.com"]
}

# Trigger expiry check
POST /api/v2/system/alerts/expiry/check
```

### Updates
```http
# Check for updates (within the installed major version; the highest final release of the
# next major version (installed + 1) is reported apart in major_upgrade: {version, published_at,
# release_notes, html_url, download_url, package_name, checksum_url, assets}, null when
# there is none, never a release candidate)
GET /api/v2/system/updates/check

# Upgrade to the next major version reported by the check (502 with the message of a
# failed check, 400 without one or without
# version, 409 when version is not the one the check now reports; without
# "major_upgrade": true the route refuses any release of another major version)
POST /api/v2/system/updates/install
{"major_upgrade": true, "version": "<major_upgrade.version>"}

# Install update (HA mode: starts a rolling update of every node, 409 when one runs, a node
# has no package family (Docker, unknown), the release lacks a present family's package or
# SHA-256, or its full-stop-migrations.json is missing or names a migration not yet applied;
# Docker/Kubernetes: 400, the orchestrator updates; 502 with the message of a failed check)
POST /api/v2/system/updates/install

# HA rolling update state: {ha, campaign: {status (running|stopped|done), target, order,
# done, skipped, current: {node, since, state}, failed: {node, reason, at},
# packages: {family: {download_url, package_name, sha256}}, families: {node: family}} or null}
GET /api/v2/system/updates/campaign

# Resume a stopped rolling update from the node where it stopped (HA only; 409 otherwise)
POST /api/v2/system/updates/campaign/resume

# Get current version
GET /api/v2/system/updates/version
```

**Response (version):**
```json
{
  "data": {
    "version": "2.1.0",
    "build": "abc123",
    "release_date": "2026-02-01"
  }
}
```

### HSM Status
```http
GET /api/v2/system/hsm-status
```

### Service Management
```http
# Get service status (includes the crypto block below)
GET /api/v2/system/service/status

# "crypto" in the response: FIPS mode asked for (UCM_FIPS=1), in force,
# the OpenSSL library cryptography uses, the loaded FIPS provider and the
# approved-mode settings it reports (each null when the provider does not
# report it; the block is null without an active provider). UCM refuses
# to start when one is not 1 on the OpenSSL FIPS Provider; a distribution
# module follows its own security policy. "blockers": the blocker findings
# (id, severity, title, count, examples, remedy) of the FIPS readiness check
# this node ran when it started in FIPS mode, and "blockers_checked_at" when
# (ISO 8601 UTC); the same in every worker, never changed by fips-preflight,
# which answers a fresh report. Both null outside FIPS mode. Without
# admin:system each finding keeps only id, severity, title and count.
"crypto": {
  "fips_requested": true,
  "fips_active": true,
  "provider_active": true,
  "library": "OpenSSL 3.5.7 9 Jun 2026",
  "provider": {"name": "OpenSSL FIPS Provider", "version": "3.5.9", "buildinfo": "3.5.9"},
  "module_settings": {"security-checks": 1, "tls1-prf-ems-check": 1, "drbg-no-trunc-md": 1},
  "blockers": [],
  "blockers_checked_at": "2026-11-14T08:00:00Z"
}

# "cluster.nodes" in the response (HA mode): every registered node with node_id, leader,
# stale, stopped (released by a clean stop: never stale, never leader), version, started_at,
# heartbeat_at, command_seen, kek_fingerprint and package_family (deb, rpm-elN,
# rpm-fedora, container or unknown: the package a rolling update gives the node)

# Restart service
POST /api/v2/system/service/restart
Content-Type: application/json

{
  "service": "ucm"
}
```

### FIPS Readiness
```http
# What FIPS mode would refuse on this instance; reads only (admin:system).
# Same report as `python -m scripts.fips_preflight --json` run from backend/
# (exit code 1 with blockers, 2 when a check could not run or UCM_FIPS is set
# without the FIPS provider).
GET /api/v2/system/fips-preflight

# Response
{
  "data": {
    "fips_active": false,
    "module_known": true,           # false: no FIPS module was asked (no loaded module, no
                                    # build record of the -fips image), EdDSA and ML-DSA listed as refused
    "ready": false,                 # no blocker and every check ran
    "summary": {"blocker": 1, "warning": 0, "info": 0},
    "findings": [{
      "id": "users.password_scrypt",
      "severity": "blocker",        # blocker, warning or info
      "title": "Local users with an scrypt password hash: ...",
      "count": 3,
      "examples": ["alice (#2)", "bob (#5)", "carol (#9)"],   # at most 5
      "remedy": "Have each user sign in once before the switch: ..."
    }],
    "errors": [],                   # [{"id": "...", "error": "..."}] for a check that failed
    "checked": ["users.password_scrypt", "users.backup_codes_scrypt", "..."]
  }
}
```

Check ids: `users.password_scrypt`, `protocols.secret_scrypt`, `ca.eddsa_key`, `ca.weak_key`,
`ca.unapproved_algorithm`, `ssh_ca.eddsa_key`, `deploy.ssh_eddsa_key`, `tsa.signer_unapproved_key`, `dns.tsig_hmac_md5`,
`session.short_secret_key`, `msca.winrm_ntlm`, `msca.kerberos_outside_fips`, `kerberos.acceptor_outside_fips`,
`database.postgres_without_tls`,
`database.postgres_gssenc`, `https.unapproved_key` (blockers);
`users.backup_codes_scrypt`, `ocsp.responder_unapproved_key`, `templates.unapproved_key_type`,
`policies.unapproved_key_type`, `acme_client.unapproved_key_type`, `hsm.softhsm`, `hsm.gcp_grpc`,
`hsm.unapproved_keys`, `hmac.short_secret`, `backup.schedule_argon2id`, `backup.archives_argon2id` (warnings);
`certificates.unapproved_key`, `ssh_certificates.eddsa_key` (information).


### Compliance Profiles
```http
# The profiles and the rules they apply (any signed-in user): title, reference,
# key types, digests, signature schemes, horizons, HSM requirement
GET /api/v2/system/compliance-profiles

# Instance default for new CAs (admin:settings); empty string clears it
PATCH /api/v2/settings/general
{"compliance_profile_default": "bsi"}

# What a compliance profile (anssi, bsi or eu-acm) would refuse or advise against
# on this instance, or on one CA; reads only (admin:system). Same report shape as
# fips-preflight, plus the profile and the CA. 400 for an unknown profile or a
# malformed ca, 404 for a CA that does not exist.
# CLI: python -m scripts.compliance_preflight --profile bsi [--ca ID] [--json]
# (exit code 0 nothing blocks, 1 blockers, 2 a check could not run or unknown profile/CA)
GET /api/v2/system/compliance-preflight?profile=bsi
GET /api/v2/system/compliance-preflight?profile=bsi&ca=3

# Response
{
  "data": {
    "profile": {"name": "bsi", "title": "BSI", "reference": "BSI-TR-02102-1 2026-01"},
    "ca_id": null,
    "ready": false,
    "summary": {"blocker": 1, "warning": 0, "info": 0},
    "findings": [{
      "id": "ca.key_type",
      "severity": "blocker",
      "title": "Certificate authorities whose key type the profile does not allow",
      "count": 1,
      "examples": ["Root CA (#1): RSA-2048"],
      "remedy": "Create an authority with an allowed key type and move issuance to it; ..."
    }],
    "errors": [],
    "checked": ["ca.key_type", "ca.key_type.advisory", "..."]
  }
}
```

Check ids (each also exists with an `.advisory` suffix, at warning level, or information for
`ca.eddsa_key` and `certificates.key_horizon`, for what the profile only advises against):
`ca.key_type`, `ca.eddsa_key`, `ca.signature_scheme`, `ca.key_horizon`, `ca.key_protection`, `ca.hsm_certification` (blocker only, no advisory twin),
`certificates.key_horizon`, `templates.key_type`, `templates.digest`, `policies.key_type`,
`policies.digest`, `acme.digest`, `ocsp.responder_key`, `tsa.signer_key`; and the blocker
`policies.unknown_key_types_only`.

**CA profile.** `POST /api/v2/cas` accepts `complianceProfile` (`anssi`, `bsi`, `eu-acm`;
`null` or `""` for none; omitted means the instance default, the `compliance_profile_default`
system setting). The CA being created must meet the profile. `PATCH /api/v2/cas/{id}` with
`complianceProfile` attaches, changes or (with `null` or `""`) removes it; it binds future
issuance only, nothing issued is re-checked, and the change is audited. The API runs no preflight
(the interface does, and asks for confirmation): run it first.
Every CA object returns `compliance_profile` (string or `null`). A refusal by a profile names
the rule; a recommendation comes back in `meta.notices` of the issuance response.

**Policy rule keys.** Policies (`rules`) also accept `allowed_signature_schemes`
(`rsa_pkcs1v15`, `rsa_pss`, `ecdsa`, `eddsa`, `ml_dsa`, `slh_dsa`), `key_type_horizons` (`{"RSA-2048": "2030-12-31"}`:
the certificate must not be valid beyond the date), `key_type_issue_until` (no issuance of that
key type after the date), `require_hsm_ca_key` (boolean: software, SoftHSM and OpenBao CA keys refused, an Azure or Google
key accepted only when its protection level is HSM),
`hsm_certifications` (`{"eucc-high": null, "fips-140-3-l3": "2030-12-31"}`: when the CA key is in an
HSM, the certification declared for its provider must be listed and not past its last accepted date,
`null` meaning no end; the profile `eu-acm` carries `cc-eal4+`, `eucc-high` and `fips-140-3-l3` until
2030-12-31, values from the HSM provider list below),
`tsa_signer_key_types`, `pq_standalone` (boolean) and `advisories` (an object using the same
keys, producing notices instead of refusals). A policy whose `allowed_key_types` holds only
unknown labels refuses issuance.

```http
# Key types, digests, signature schemes and horizons left by the active policies
# (system policies included: FIPS mode, the compliance profile of the CA), null = unrestricted
GET /api/v2/policies/effective?ca_id=3&template_id=1

# Response
{
  "data": {
    "allowed_key_types": ["EC-P256", "EC-P384", "RSA-3072"],
    "allowed_digests": ["sha256", "sha384", "sha512"],
    "allowed_signature_schemes": ["rsa_pss", "ecdsa"],
    "key_type_horizons": {},
    "key_type_issue_until": {},
    "require_hsm_ca_key": false,
    "hsm_certifications": null,  # {"eucc-high": null, ...} when a policy sets the rule
    "tsa_signer_key_types": ["EC-P256", "EC-P384", "EC-P521"],
    "pq_standalone": false,      # true: a post-quantum key only as a member of a hybrid pair
    "ml_dsa": true,              # false when this build's OpenSSL has no ML-DSA
    "default_key_type": "RSA-3072",  # key issued when neither the request nor the template names one
    "baseline_key_type": "RSA-2048", # the starting candidate of that rule
    "fips": true,                # only present in FIPS mode
    "fips_key_types": ["RSA-2048", "RSA-3072", "RSA-4096", "EC-P256", "EC-P384", "EC-P521",
                       "ED25519", "ED448", "ML-DSA-44", "ML-DSA-65", "ML-DSA-87"]
                                 # FIPS mode only: what the loaded module approves (here 3.5.9)
  }
}
```

`default_key_type` is `null` when the policies leave no default candidate; `default_key_error` then holds the reason.

### System Logs
```http
GET /api/v2/system/logs?source=app&level=INFO&lines=200&q=text&exclude=text&component=name&since=...&until=...
GET /api/v2/system/logs/bundle
```
Permission `admin:system`. `logs` reads the tail of one source as filtered records: `source` is `app` (default), `access`, `error` or `journal`; `level` one of `DEBUG`, `INFO` (default), `WARNING`, `ERROR`, `CRITICAL`; `lines` an integer from 1 to 5000 (default 200); `q` and `exclude` are substrings (a `regex` parameter is refused); `component` filters by logger. Each invalid value answers `400`. `bundle` downloads a diagnostic ZIP.

### Scheduler
```http
GET /api/v2/system/scheduler
POST /api/v2/system/scheduler/{task_name}/run
```
`GET` (`read:settings`) lists the registered scheduler tasks with their live status and a `label`, sorted by label, with a count of tasks in warning and a `stale` flag. `run` (`admin:system`) runs a task now, or queues it; `404` for an unknown task.

### Update Settings
```http
GET /api/v2/system/updates/settings
PATCH /api/v2/system/updates/settings
GET /api/v2/system/updates/whatsnew
```
`GET` and `PATCH` need `admin:system`. `PATCH` takes `channel` (`stable` or `rc`), `hour` (an integer from 0 to 23, the hour of automatic installation), `auto_install` (a boolean; refused with `400` on a container install) and `popup_enabled` (a boolean); the response is the stored settings. `whatsnew` (any authenticated user) returns `{"enabled": false}` while the post-update popup is off, otherwise `version`, `baseline_version`, `installed_at`, `release_notes` and `published_at`.

### Encryption Key Operations
```http
GET /api/v2/system/security/master-key/download
POST /api/v2/system/security/encrypt-all-keys
POST /api/v2/system/security/rotate-encryption-key
POST /api/v2/system/https/unbind
```
All need `admin:system`.
- `master-key/download` returns the master key file (`ucm-master.key`, `no-store`) and audits the download. `400` when encryption is not enabled, `409` when the key is not stored as a file (it comes from `KEY_ENCRYPTION_KEY`, so it must be backed up by hand).
- `encrypt-all-keys` takes `{"dry_run": true}` (the default: nothing is written) and returns `dry_run`, `encrypted`, `skipped` and `errors`.
- `rotate-encryption-key` rotates the data-encryption key and rewrites every stored value under it; the master key does not change. `400` when encryption is not enabled. `200` when the rotation is done, `202` while some nodes have not loaded the new key yet (run it again to finish); `500` when interrupted (run it again to resume).
- `https/unbind` stops following renewals of the bound HTTPS certificate; `400` when none is bound.

---

## Import/Export

### Certificate Import (File Upload)
```http
POST /api/v2/certificates/import
Content-Type: multipart/form-data

file: <certificate file>          # Required: .pem, .crt, .cer, .der, .p12, .pfx
name: "My Certificate"            # Optional: display name
password: "pkcs12password"        # Optional: for PKCS12 files
ca_id: 1                          # Optional: link to this CA, which must have signed it (400 otherwise)
import_key: true                  # Optional: import private key (default: true)
cross_mode: auto                  # Optional: auto | attach | replace | refuse (default: auto)

# Response (201 Created)
{
  "data": {
    "id": 123,
    "refid": "uuid",
    "descr": "My Certificate",
    "subject": "CN=example.com",
    "issuer": "CN=My CA",
    ...
  },
  "message": "Certificate \"My Certificate\" imported successfully"
}

# If CA certificate detected (CA:TRUE basic constraint):
{
  "data": { ... },  # CA object, not certificate
  "message": "CA certificate \"My CA\" imported successfully (detected as CA)"
}
```

Without `ca_id`, the certificate is linked to the stored CA whose key verifies its signature (AKI, then issuer name, are only used to find candidates); with none it is stored as a third-party certificate.

**Features:**
- Auto-detects format: PEM, DER, PKCS12, PKCS7
- Handles PEM files with text before/after the certificate block
- Auto-detects CA certificates (CA:TRUE) and stores in CAs table
- Auto-links certificates to parent CA by issuer matching

### CA Import (File Upload)
```http
POST /api/v2/cas/import
Content-Type: multipart/form-data

file: <CA certificate file>       # Required
name: "My Root CA"                # Optional: display name
password: "pkcs12password"        # Optional: for PKCS12 files
import_key: true                  # Optional: import private key (default: true)

# Response (201 Created)
{
  "data": {
    "id": 5,
    "refid": "uuid",
    "descr": "My Root CA",
    "subject": "CN=My Root CA,O=Org",
    "is_root": true,
    ...
  },
  "message": "CA \"My Root CA\" imported successfully"
}
```

A certificate that carries the subject and key of a CA already held, under another issuer, is a
cross-certificate (#400). `cross_mode` decides what happens: `auto` attaches it to a self-signed root
and answers `409` for an intermediate, `attach` attaches it in both cases, `replace` lets an
intermediate be overwritten, `refuse` never attaches. The attached answer is `201` with the CA,
`cross_certificate` and `warnings`. The `409` carries `details.code = "cross_certificate_detected"`,
`details.ca_id` and `details.options` (`["attach"]` for a self-signed root, `["attach", "replace"]`
otherwise). Installing such a certificate on a CA that is not awaiting one, after **Renew via CSR**
(`POST /api/v2/cas/{ca_id}/certificate`), answers the same `409`; that route accepts only `cross_mode=auto` or `replace` (`400` otherwise). The same options apply to `POST /api/v2/certificates/import`.
With `cross_mode=auto`, an intermediate's certificate is taken for a cross-certificate when its issuer has another name, or the same name while UCM holds CAs of that name and none of them signed it (a homonym from another hierarchy). The same issuer name under a key UCM does not hold, or under a held new root, is a root rollover and replaces the certificate as a renewal does. A self-signed root is never replaced by another issuer's certificate, `attach` and `refuse` treat any such certificate as a cross-certificate, and a real revocation in the CA's chain lets `auto` replace it.

Smart Import (`POST /api/v2/import/execute`) attaches a cross-certificate found next to a held root and
reports it in `warning_details` with `code` `cross_certificate_attached` or `cross_certificate_skipped`
(the self-signed CA is kept in both cases); its `cas_imported` does not count it.

### OPNsense Import
```http
# Test connection
POST /api/v2/import/opnsense/test
Content-Type: application/json

{
  "host": "192.168.1.1",
  "api_key": "...",
  "api_secret": "..."
}

# Import certificates
POST /api/v2/import/opnsense/import
Content-Type: application/json

{
  "host": "192.168.1.1",
  "api_key": "...",
  "api_secret": "...",
  "import_cas": true,
  "import_certificates": true
}
```

---

## Certificate Tools

### Check SSL/TLS
```http
POST /api/v2/tools/check-ssl
Content-Type: application/json

{
  "hostname": "example.com",
  "port": 443
}
```

### Decode CSR
```http
POST /api/v2/tools/decode-csr
Content-Type: application/json

{
  "pem": "-----BEGIN CERTIFICATE REQUEST-----\n..."
}
```

### Decode Certificate
```http
POST /api/v2/tools/decode-cert
Content-Type: application/json

{
  "pem": "-----BEGIN CERTIFICATE-----\n..."
}
```

### Match Keys
```http
POST /api/v2/tools/match-keys
Content-Type: application/json

{
  "certificate": "-----BEGIN CERTIFICATE-----\n...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...",
  "csr": "-----BEGIN CERTIFICATE REQUEST-----\n...",
  "password": "optional-key-password"
}
```

### Convert Certificate Format
```http
POST /api/v2/tools/convert
Content-Type: application/json

{
  "pem": "-----BEGIN CERTIFICATE-----\n...",
  "input_type": "pem",
  "output_format": "pkcs12",
  "password": "input-password",
  "output_password": "output-password",
  "chain": "-----BEGIN CERTIFICATE-----\n...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n..."
}
```

`password` opens the input (a PKCS#12/PFX file or an encrypted PEM) and the separate `private_key`, and is never logged; `pkcs12_password` protects a PKCS#12 or JKS output. The web interface shows the password field as soon as a separate key, an encrypted PEM or a PKCS#12 file is given.

---

## Global Search

### Search All Resources
```http
GET /api/v2/search?q=example.com&limit=20
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `q` | string | Search query (required) |
| `limit` | integer | Max results per category (default: 5) |

Certificates match on their subject, issuer, display name and serial number, and on their comment for a user with `read:certificates`.

**Response:**
```json
{
  "data": {
    "certificates": [...],
    "cas": [...],
    "users": [...],
    "templates": [...],
    "acme_accounts": [...],
    "scep_profiles": [...]
  }
}
```

`users` needs `read:users`, `acme_accounts` (matched on contact and account ID, named by the first contact) needs `read:acme`, and `scep_profiles` (matched on name, URL path and description) needs `read:scep`; without the permission the group is empty.

---

## User Groups

### List Groups
```http
GET /api/v2/groups
GET /api/v2/groups?search=engineering
```

### Create Group
```http
POST /api/v2/groups
Content-Type: application/json

{
  "name": "Engineering",
  "description": "Engineering team",
  "permissions": ["read:certificates", "write:certificates"]
}
```

### Get Group
```http
GET /api/v2/groups/{group_id}
```

### Update Group
```http
PUT /api/v2/groups/{group_id}
Content-Type: application/json

{
  "name": "Engineering",
  "description": "Updated description",
  "permissions": ["read:*", "write:certificates"]
}
```

### Delete Group
```http
DELETE /api/v2/groups/{group_id}
```

### List Group Members
```http
GET /api/v2/groups/{group_id}/members
```

### Add Member to Group
```http
POST /api/v2/groups/{group_id}/members
Content-Type: application/json

{
  "user_id": 5,
  "role": "member"
}
```

### Remove Member from Group
```http
DELETE /api/v2/groups/{group_id}/members/{user_id}
```

### Group Statistics
```http
GET /api/v2/groups/stats
```

---

## Smart Import

### Analyze Content
```http
POST /api/v2/import/analyze
Content-Type: application/json

{
  "content": "-----BEGIN CERTIFICATE-----\n...",
  "password": "optional-password"
}
```

**Response:**
```json
{
  "data": {
    "type": "certificate",
    "format": "pem",
    "details": { ... }
  }
}
```

With `"include_pem": true` each `certificate` object of `data.objects` also carries its `pem`, and each `private_key` object its unencrypted PKCS#8 `pem` once the password opened it (a key still sealed has none). Without it no object has a `pem`. The request key is `content`, never `files`.

### Execute Import
```http
POST /api/v2/import/execute
Content-Type: application/json

{
  "content": "-----BEGIN CERTIFICATE-----\n...",
  "password": "optional-password",
  "options": { ... }
}
```

`options`: `import_cas`, `import_certs`, `import_csrs`, `import_keys` (each `true` by default),
`skip_duplicates`, `description_prefix`, and `selected_indices`, the positions in the analysis
`objects` list to import (all of them when absent; a position outside the list is refused).
`write:cas` is required only when a CA certificate is among the objects imported.

Both routes also take `file_passwords`, an object or a list of passwords (one per uploaded file,
32 in all with `password`): each is tried in turn on every encrypted key and PKCS#12 bundle.

### List Supported Formats
```http
GET /api/v2/import/formats
```

---

## DNS Providers

### List DNS Providers
```http
GET /api/v2/dns-providers
```

### List Provider Types
```http
GET /api/v2/dns-providers/types
```

### Create DNS Provider
```http
POST /api/v2/dns-providers
Content-Type: application/json

{
  "name": "Cloudflare",
  "provider_type": "cloudflare",
  "credentials": {
    "api_token": "..."
  },
  "is_default": true,
  "enabled": true
}
```

Cloudflare takes `api_token`, or `api_key` together with `email` (400 otherwise, on creation and on update). Alwaysdata takes `api_key`; `account` is optional and, when given, is sent with the token as `<token> account=<name>`.

### Get DNS Provider
```http
GET /api/v2/dns-providers/{provider_id}
```

### Update DNS Provider
```http
PATCH /api/v2/dns-providers/{provider_id}
Content-Type: application/json

{
  "name": "Updated Name",
  "credentials": { "api_token": "new-token" },
  "enabled": true,
  "is_default": false
}
```

Fields left out or blank keep their saved values. Saved credentials this node's database key cannot decrypt are never merged: `credentials` must then hold every required field, and a secret when the provider has one, in one request (400 naming the missing fields otherwise), and the entry replaces them whole, so an optional secret not sent again (INWX `shared_secret`, Cloudflare `api_key`) is no longer saved. A type without credential fields (`manual`, or one this release no longer knows) refuses any such entry, and a `manual` provider never reads its saved credentials.

### Delete DNS Provider
```http
DELETE /api/v2/dns-providers/{provider_id}
```

### Test DNS Provider
```http
POST /api/v2/dns-providers/{provider_id}/test
```

---

## ACME Client (Let's Encrypt)

UCM can act as an ACME client to obtain certificates from Let's Encrypt and other ACME-compatible CAs. This is distinct from the ACME Server section, which covers UCM acting as its own ACME server.

### Get Client Settings
```http
GET /api/v2/acme/client/settings
```

### Update Client Settings
```http
PATCH /api/v2/acme/client/settings
Content-Type: application/json

{
  "email": "admin@example.com",
  "environment": "production",
  "renewal_enabled": true,
  "renewal_days": 30
}
```

`renewal_days` (1 to 60) applies when the CA suggests no renewal window (ARI). When it is more
than two thirds of a certificate's lifetime, that certificate is renewed in the last third of
its lifetime instead.

Fields of the DNS UPDATE (RFC 2136) listener of the ACME proxy:

| Field | Method | Description |
|-------|--------|-------------|
| `dns_update_port` | GET, PATCH | Port of the listener (UDP and TCP). `0` = disabled (default). Otherwise 1024 to 65535, and not the HTTPS port, the HTTP protocol port or the TLS-ALPN-01 port. A change needs a restart. The PATCH response has `restart_required` (`true` only when the new value differs from the port the listener uses now and `UCM_DNS_UPDATE_PORT` is not set) and, when that variable is set, `dns_update_port_env_override: true` |
| `dns_update_port_env` | GET | Value of `UCM_DNS_UPDATE_PORT`, or `null` when it is not set or empty. When set, it wins over `dns_update_port` |
| `dns_update_listening` | GET | `true` when the listener is running now |
| `dns_update_port_effective` | GET | The port the listener uses at the next start: the environment variable when it is set, else `dns_update_port`; `0` when the value is invalid or the listener is off |

```http
PATCH /api/v2/acme/client/settings
Content-Type: application/json

{ "dns_update_port": 8053 }
```

### List Orders
```http
GET /api/v2/acme/client/orders
GET /api/v2/acme/client/orders?status=pending&environment=production
GET /api/v2/acme/client/orders?page=2&per_page=100
```

Newest first, 100 per page at most (`per_page`, default 100); `meta` gives `total`, `page`
and `total_pages`. Orders left `pending` for more than 7 days, whose order at the CA has expired
or whose expiry is unknown, are removed by the renewal task.

Each order carries `renewal_failures`, `renewal_retry_daily`, `last_error_at` and
`error_message`, and `upstream_revocations_owed`: the replaced certificates whose revocation the
CA has not confirmed yet (with `acme.revoke_on_renewal`). The renewal task sends them again
until the certificate expires, and each failure emits the `acme_order.revocation_failed`
webhook event (`order`, `serial_number`, `error`, `attempts`). Deleting the order abandons them;
its audit entry says how many.

### Get Order Details
```http
GET /api/v2/acme/client/orders/{order_id}
```

### Turn Automatic Renewal On or Off
```http
PATCH /api/v2/acme/client/orders/{order_id}
Content-Type: application/json

{
  "renewal_enabled": false
}
```

Takes a JSON boolean only (`400` otherwise). Refused with `409` on a proxy order and on an
order a renewal opened.

### Request Certificate
```http
POST /api/v2/acme/client/request
Content-Type: application/json

{
  "domains": ["example.com", "www.example.com"],
  "email": "admin@example.com",
  "challenge_type": "dns-01",
  "environment": "production",
  "dns_provider_id": 1
}
```

A CSR (`key_source: "csr"`) whose key was revoked as compromised is refused with `409` before
any order is opened at the CA.

`key_type` sets the certificate key UCM generates: `RSA-2048`, `RSA-4096`, `EC-P256`,
`EC-P384`, `EC-BP256`, `EC-BP384`, or `ML-DSA-44`, `ML-DSA-65`, `ML-DSA-87` when this build
has ML-DSA. Without it the `key_type` client setting applies (RSA-2048 when unset); a value
this instance cannot generate answers `400` and is never replaced by another type. FIPS mode
refuses Brainpool, and ML-DSA unless the loaded FIPS module approves it, with `400`, both as `key_type` and as the key of
`source_certificate_id` (`key_source: "reuse"`).

### Verify Challenge
```http
POST /api/v2/acme/client/orders/{order_id}/verify
Content-Type: application/json

{
  "domain": "example.com"
}
```

### Get Order Status
```http
GET /api/v2/acme/client/orders/{order_id}/status
```

### Finalize Order
```http
POST /api/v2/acme/client/orders/{order_id}/finalize
```

### Delete Order
```http
DELETE /api/v2/acme/client/orders/{order_id}
```

### Renew Order
```http
POST /api/v2/acme/client/orders/{order_id}/renew
```

A failure answers `409` when the renewal is blocked before the CA (account gone, key revoked
as compromised, DNS provider disabled) and `422` otherwise, with the reason; both are counted
on the order and emit `acme_order.renewal_failed`. `409` also answers while another renewal or
finalization of the order runs, and that one is not counted.

### Register ACME Account
```http
POST /api/v2/acme/client/account
Content-Type: application/json

{
  "email": "admin@example.com",
  "environment": "production"
}
```

### DNS UPDATE Keys (RFC 2136)

TSIG keys of the DNS UPDATE listener of the ACME proxy. A key belongs to one proxy account. Optionally it is linked to an EAB credential: it then accepts only values for orders of the ACME account bound to that credential.

```http
GET /api/v2/acme/client/accounts/{account_id}/dns-update-keys
```
Requires `read:acme`. Lists the keys. The response never contains the secret.

```http
POST /api/v2/acme/client/accounts/{account_id}/dns-update-keys
Content-Type: application/json

{
  "name": "proxy1-key.",
  "algorithm": "hmac-sha256",
  "eab_credential_id": 3,
  "notes": "cert-manager, cluster A"
}
```
Requires `write:acme`. All fields are optional: `name` is generated when omitted, `algorithm` is `hmac-sha256` (also `hmac-sha384`, `hmac-sha512`), `notes` has at most 1000 characters. Answers `201`. The response contains the base64 `secret` **once**; UCM stores it encrypted and cannot show it again. A name that exists already gives `409`. An account whose ACME proxy is off also gives `409`: a key of such an account would not work, so turn the proxy on first.

```http
DELETE /api/v2/acme/client/accounts/{account_id}/dns-update-keys/{key_id}
```
Requires `delete:acme`. An active key is revoked at once (answer `200` with the key). A revoked key is deleted (answer `204`).

Each account of `GET /api/v2/acme/client/accounts` has the integer field `dns_update_key_count`: the number of its DNS UPDATE keys of any status. It is `0` for an account without keys. The web interface uses it to show the keys of an account whose ACME proxy is off.

### ACME CA Accounts
Accounts UCM holds with external ACME CAs. Unknown accounts answer `404`.

```http
GET /api/v2/acme/client/accounts
POST /api/v2/acme/client/accounts
Content-Type: application/json

{
  "directory_url": "https://acme.example.com/directory",
  "label": "Production CA",
  "email": "ops@example.com",
  "account_key_algorithm": "ES256",
  "account_key_pem": "...",
  "is_default": false,
  "eab_kid": "...",
  "eab_hmac_key": "..."
}
```
`GET` needs `read:acme`; `POST` needs `write:acme` and answers `201`. Required: `directory_url` (HTTPS, 500 characters at most), `label` (100 at most, unique: `409`) and `email` (254 at most). `account_key_algorithm` defaults to `ES256`; `account_key_pem` imports an existing key (64 KB at most, `413` above).

```http
GET /api/v2/acme/client/accounts/{account_id}
PATCH /api/v2/acme/client/accounts/{account_id}
DELETE /api/v2/acme/client/accounts/{account_id}
POST /api/v2/acme/client/accounts/{account_id}/deactivate
POST /api/v2/acme/client/accounts/{account_id}/default
POST /api/v2/acme/client/accounts/{account_id}/register
```
`PATCH` (`write:acme`) updates `label`, `email`, `account_key_algorithm`, `eab_kid`, `eab_hmac_key` and `is_default`. `is_default: true` makes the account the default; `is_default: false` on the default account answers `400` (make another account the default instead). `account_key_algorithm` answers `400` when it differs from the algorithm of the key the account already holds, and is applied only while the account has no key. `DELETE` (`delete:acme`) answers `409` while issued orders still renew through the account. `deactivate` (`delete:acme`) deactivates the account at the CA (RFC 8555 section 7.3.6), then removes it; `502` when the CA refuses. `default` (`write:acme`) makes it the account used when a request names none. `register` (`write:acme`) registers or re-registers it with its CA; optional `email`, `400` without a valid contact.

### ACME Client Preflight
```http
POST /api/v2/acme/client/preflight
Content-Type: application/json

{ "domains": ["www.example.com"], "challenge_type": "dns-01", "mode": "full" }
```
Permission `write:acme`. Dry-run of a certificate request; returns a report with `ok` and per-step results. `domains` is required; `challenge_type` defaults to `dns-01`; `mode` is `full` (default) or `validate_only`; optional `email`, `acme_account_id`, `dns_provider_id` (integers), `key_source` (default `generate`), `csr_pem` and `verify_dns`. `key_type` is checked as the certificate request checks it: an unknown type, or one FIPS mode refuses, answers `400` before any step runs.

---

## ACME Domains

### List Domains
```http
GET /api/v2/acme/domains
```

### Get Domain
```http
GET /api/v2/acme/domains/{domain_id}
```

### Create Domain
```http
POST /api/v2/acme/domains
Content-Type: application/json

{
  "domain": "example.com",
  "dns_provider_id": 1,
  "is_wildcard_allowed": true,
  "auto_approve": false
}
```

### Update Domain
```http
PUT /api/v2/acme/domains/{domain_id}
Content-Type: application/json

{
  "dns_provider_id": 2,
  "is_wildcard_allowed": false,
  "auto_approve": true
}
```

### Delete Domain
```http
DELETE /api/v2/acme/domains/{domain_id}
```

### Resolve Domain
```http
GET /api/v2/acme/domains/resolve?domain=example.com
```

### Test Domain DNS
```http
POST /api/v2/acme/domains/test
Content-Type: application/json

{
  "domain": "example.com",
  "dns_provider_id": 1
}
```

### Local Domains
Maps a domain to the local CA that signs for it when UCM answers ACME requests itself.

```http
GET /api/v2/acme/local-domains
POST /api/v2/acme/local-domains
GET /api/v2/acme/local-domains/{domain_id}
PUT /api/v2/acme/local-domains/{domain_id}
DELETE /api/v2/acme/local-domains/{domain_id}
```
Reads need `read:acme`, `POST` and `PUT` `write:acme`, `DELETE` `delete:acme`. `POST` body: `domain` (required, `400` for an invalid name), `issuing_ca_id` (required; `404` unknown, `400` when that CA cannot sign) and optional `auto_approve` (default `false`). `PUT` changes `issuing_ca_id` and `auto_approve`.

---

## SSO (LDAP/OAuth2/SAML)

### List SSO Providers (admin)
```http
GET /api/v2/sso/providers
```

### Get SSO Provider (admin)
```http
GET /api/v2/sso/providers/{provider_id}
GET /api/v2/sso/providers/{provider_id}?include_secrets=true
```

### Create SSO Provider (admin)
```http
POST /api/v2/sso/providers
Content-Type: application/json

{
  "name": "corporate-ldap",
  "provider_type": "ldap",
  "display_name": "Corporate LDAP",
  "icon": "ldap",
  "enabled": true,
  "default_role": "viewer",
  "auto_create_users": true,
  "auto_update_users": false
}
```

Additional fields depend on `provider_type` (ldap, oauth2, saml).

`name` is required and must be text that is not blank; a creation or an update with an empty, blank, null or non-text `name` returns `400`.

For an `oauth2` provider, `oauth2_tenants` is the list of Microsoft Entra tenant IDs accepted through a multi-tenant authority (`oauth2_issuer` of `organizations` or `common`): GUIDs, given as a list or as text separated by commas or blanks, saved in lower case without repeats and returned as a list (`[]` when none). A value that is not a GUID (a wildcard, `common`, a name) returns `400`; so do tenants with `id_token_verify` false or without `oauth2_issuer`. An empty list clears them and the provider validates one issuer again. `oauth2_role_tenants` lists, in the same forms, the accepted tenants whose `roles` and `groups` claims the role mapping reads (`[]` by default): a tenant outside `oauth2_tenants` returns `400`, also when an update takes off the list a tenant still in it. When `role_mapping` has rules, a sign-in from an accepted tenant not listed is refused (`sso_unmapped`); without rules, every accepted tenant gets `default_role`. A stored value that does not read as a list is returned as it is.

#### Role mapping

`role_mapping` maps an external group to a UCM role. Each value is either a base role (`admin`, `operator`, `auditor`, `viewer`) or an object naming a base role, a custom role, or both:

```json
{
  "role_mapping": {
    "pki-admins": "admin",
    "pki-auditors": { "role": "auditor", "custom_role": "Certificate Reviewer" },
    "pki-helpdesk": { "custom_role": "Helpdesk" }
  }
}
```

Custom roles are referenced by name. Among the groups a user belongs to, the base role is the most privileged one given; the custom role is the first one, in mapping order, that names one. A custom role never grants the permissions reserved to administrators.

The mapping is checked when the provider is created or updated: an unknown base role, an unknown custom role, a malformed entry, or two keys the provider compares equal (an LDAP provider ignores case, edge spaces and the length of inner space runs) returns `400` and nothing is saved. A key is saved without its edge spaces. For an LDAP provider, `ldap_group_base_dn` sets where the groups are searched: an empty value clears it, a value that is not a DN returns `400`. `ldap_nested_groups` (boolean, default `false`; any other value returns `400`) adds, on Active Directory only, the groups above the user's groups at any depth, searched under the group base, and the primary group to the groups the rules apply to; elsewhere, when role mapping rules or required groups exist, the login is refused as groups unreadable. At login, a value that has become invalid is not trusted: an invalid base role counts as `viewer` and an unknown custom role is ignored.

With `sync_role_on_login` on, each login also updates the custom role, and removes it when no matching group names one, but only if it came from the mapping (`custom_role_source` is `"sso"`). A custom role assigned by hand is never replaced nor removed. System roles cannot be used as the custom role of a mapping. Changes are recorded in the audit log as `role_change`.

### Update SSO Provider (admin)
```http
PUT /api/v2/sso/providers/{provider_id}
Content-Type: application/json

{ ... }
```

### Delete SSO Provider (admin)
```http
DELETE /api/v2/sso/providers/{provider_id}
```

### Toggle SSO Provider (admin)
```http
POST /api/v2/sso/providers/{provider_id}/toggle
```

### Test SSO Provider (admin)
```http
POST /api/v2/sso/providers/{provider_id}/test
```

### Test an OIDC or SAML Sign-in (admin)
```http
POST /api/v2/sso/providers/{provider_id}/test-sign-in
GET /api/v2/sso/sign-in-tests/{test_id}
```
- `test-sign-in` (`write:sso`, no body) starts a sign-in test of the saved OIDC or SAML provider, enabled or not, and returns `id`, `url` (the IdP address to open in the browser) and `expires_at` (10 minutes); it sets a cookie that ties the test to this browser. The IdP returns to the login callback (`/api/v2/sso/callback/oauth2` or the ACS URL), which recognises the test by its server-side transaction, runs the login's checks and its account decision, opens no session and changes no account, and redirects to `/sso-test-complete?result=done` (`used`, `expired` or `other_browser` when the return is refused). At the expiry the report and the secrets of the test are erased, but its transaction is kept for 24 hours, so a late return still redirects to `result=expired` (`used` once it returned) and is audited as a failed `sso_sign_in_test`, never as a login. `400` for an LDAP provider or one without an authorization URL and client ID or a SAML SSO URL; `404` for an unknown provider; `503` with `Retry-After` during a cluster maintenance.
- `sign-in-tests/{test_id}` (`write:sso`) returns `state` (`pending`, `running` or `done`), `provider_id`, `protocol`, `expires_at` and, once done, `report`: `verdict` (`accepted` or `refused`), `stage` (`protocol` for a refusal of the IdP's answer, `account` for one of the account decision), `code` (the login page's error code), `reason`, `identity` (`username`, `email`, `fullname`, `external_id`), `groups` (at most 20 values of 64 characters, `groups_more` counts the rest), `group_source`, `candidates` (at most 20 names of received claims or attributes that may carry groups, when none was read), `diagnosis` and `detail` (the audit text of a refusal), `account` (`outcome`: `open`, `create`, `disabled` or `refused`, with `username`, and for `open` whether it `binds_identity`), `role`, `custom_role`, `role_change`, `not_verified` (compatibility mode), `provider_enabled` and `other_enabled_providers` (`id` and `name` of every other enabled provider of the same type, by `id`: empty, since the database holds one provider per type). No token, assertion, authorization code or PKCE verifier is part of it. `404` for a test another account started, an unknown one, or one whose 10 minutes after the return have passed.

### List SSO Sessions (admin)
```http
GET /api/v2/sso/sessions
```

### Get Available SSO Providers (public)
```http
GET /api/v2/sso/available
```

Returns enabled SSO providers for display on the login page. No authentication required.

### Initiate SSO Login (public)
```http
GET /api/v2/sso/login/{provider_id}
```

Redirects the user to the SSO provider's login page. No authentication required.

### SSO Callback (public)
```http
GET /api/v2/sso/callback/{provider_id}
POST /api/v2/sso/callback/{provider_id}
```

Handles the SSO provider's callback after authentication. POST is used for SAML responses. No authentication required.

### LDAP Login (public)
```http
POST /api/v2/sso/ldap/login
Content-Type: application/json

{
  "username": "jdoe",
  "password": "ldap-password",
  "provider_id": 1
}
```

No authentication required.

### SAML Service Provider and LDAP Mapping
```http
GET /api/v2/sso/saml/sp-info
GET /api/v2/sso/saml/certificates
GET /api/v2/sso/saml/metadata
POST /api/v2/sso/saml/metadata/fetch
POST /api/v2/sso/providers/{provider_id}/test-mapping
```
- `sp-info` (`read:sso`) returns the service provider URLs as UCM computes them, its `metadata_url` and `origin_configured` (whether they rest on a configured origin).
- `certificates` (`read:sso`) lists the valid certificates usable for the SP metadata, the HTTPS certificate included.
- `metadata` is public and returns the SAML 2.0 SP metadata XML to give the IdP.
- `metadata/fetch` (`write:sso`) fetches and parses IdP metadata from `{"metadata_url": "https://..."}` (required; http or https with a hostname, not loopback or a cloud metadata address: `400`); optional `provider_id`, `verify_ssl` (default true) and `ca_bundle` (PEM). Values sent win over the saved provider's `saml_verify_ssl` and `saml_ca_bundle`, which apply for each value left out.
- `test-mapping` (`write:sso`) is a dry run of an LDAP login past the password for `{"username": "..."}` (required), without creating a session: the same entry, groups and verdict as the login. `found: false` when the user filter finds no entry; otherwise `user_dn`, `username`, `email`, `groups`, `groups_readable`, `groups_error` (why the groups could not be read, else `null`), `access_allowed`, `refusal` (`null`, `account_disabled`, `groups_unreadable`, `group_denied`, `unmapped` or `no_default_role`), `resolved_role` and `resolved_custom_role` (`null` when refused), `group_source` (where the groups were read: the group search base, the `memberOf` attribute of the user entry, or not read), `diagnosis` (for `unmapped` and `no_default_role` only, else `null`: the groups read, bounded to 20 values of 64 characters, their source and the remedy, the same text as the audit entry of the login), `role_mapping`, `default_role`, `required_groups`, and `account_checked: false` with a `note`: the password and the UCM account the sign-in would open are not checked. `400` for a provider that is not LDAP, without `username` ("Username is required") or for a failed user lookup; `404` for an unknown provider.

---

## HSM

### List HSM Providers
```http
GET /api/v2/hsm/providers
```

### Create HSM Provider
```http
POST /api/v2/hsm/providers
Content-Type: application/json

{
  "name": "YubiHSM",
  "type": "yubihsm",
  "config": {
    "connector_url": "http://localhost:12345"
  },
  "certification": "eucc-high"
}
```

In HA mode a SoftHSM provider (a PKCS#11 module path or a name that says `softhsm`) answers `409`
with code `ha_mode`, and so does an update that points a provider at SoftHSM (see [HA](HA.md)).

`certification` is optional: the certification the operator declares for the hardware
(`cc-eal4+`, `eucc-high`, `fips-140-3-l3`, `fips-140-2-l3` or `other`; `null`, absent or `""` means
not declared). UCM does not verify it. Any other value is a 400. Providers return it as
`certification` (string or `null`). It is read by the `hsm_certifications` policy rule (see the
profile `eu-acm`) and by the preflight check `ca.hsm_certification`; it travels in backups.

### Get HSM Provider
```http
GET /api/v2/hsm/providers/{provider_id}
```

### Update HSM Provider
```http
PUT /api/v2/hsm/providers/{provider_id}
Content-Type: application/json

{
  "name": "Updated Name",
  "config": { ... },
  "certification": "fips-140-3-l3"
}
```

On update, an absent or `null` `certification` keeps the declared one and `""` clears it.

### Delete HSM Provider
```http
DELETE /api/v2/hsm/providers/{provider_id}
```

Deletes the provider and its keys. `409`, naming the authorities, while one of its keys backs an X.509 or SSH CA.

### Test HSM Provider
```http
POST /api/v2/hsm/providers/{provider_id}/test
```

### Sync HSM Provider
```http
POST /api/v2/hsm/providers/{provider_id}/sync
```

In HA mode, syncing a SoftHSM provider answers `409` with code `ha_mode`: its keys exist on one node only.

A key the token no longer lists is removed, except a key an X.509 or SSH CA holds (counted in `missing_kept`) or any key when the listing reported errors (`listing_errors`); the CA keeps its key and its signing fails until the key is back on the token.

### List HSM Keys
```http
GET /api/v2/hsm/keys
GET /api/v2/hsm/keys?provider_id=1
GET /api/v2/hsm/keys?unused=true
```

`unused=true` keeps the asymmetric signing keys no X.509 or SSH CA holds, through that key row or another row with the same public key (the same token key under a second provider).

### Create HSM Key
```http
POST /api/v2/hsm/providers/{provider_id}/keys
Content-Type: application/json

{
  "label": "ca-signing-key",
  "algorithm": "RSA-2048",
  "purpose": "signing",
  "extractable": false
}
```

`algorithm` also takes `EC-BP256`, `EC-BP384` and `EC-BP512` on a `pkcs11` provider, and
`ML-DSA-44`, `ML-DSA-65` and `ML-DSA-87` on a provider that signs with them: `pkcs11` (a
PKCS#11 3.2 token with the ML-DSA mechanisms), `openbao` (Transit `mldsa-*` keys) and
`google-kms` (`PQ_SIGN_ML_DSA_*` versions, mapped from the KMS API but not tested against the
service). `azure-keyvault` and `aws-cloudhsm` answer `400` for both families, and FIPS mode
refuses ML-DSA on every provider, whatever the loaded FIPS module approves: the provider signs, not the module. An ML-DSA key signs the data itself: no digest applies.
Google Cloud KMS signs at most 64 KiB of data with it, so a larger CRL fails with a message
that says so.

In HA mode, a key on a SoftHSM provider answers `409` with code `ha_mode`.

### Get HSM Key
```http
GET /api/v2/hsm/keys/{key_id}
```

### Delete HSM Key
```http
DELETE /api/v2/hsm/keys/{key_id}
```

`409`, naming the X.509 or SSH CA, while the key backs one.

### Get Public Key
```http
GET /api/v2/hsm/keys/{key_id}/public
```

### Sign with HSM Key
```http
POST /api/v2/hsm/keys/{key_id}/sign
Content-Type: application/json

{
  "data": "base64-encoded-data",
  "algorithm": "SHA256withRSA"
}
```

In FIPS mode only an RSA key of an even length from 2048 to 16384 bits or an ECDSA P-256/P-384/P-521 key signs: any other key answers `400`
with the `urn:ucm:problem:fips-restricted` problem type, as do certificate issuance and CRL
regeneration for a CA on such a key; its OCSP responder answers `unauthorized`.

### List Provider Types
```http
GET /api/v2/hsm/provider-types
```

### Check Dependencies
```http
GET /api/v2/hsm/dependencies
```

### Install Dependencies
```http
POST /api/v2/hsm/dependencies/install
Content-Type: application/json

{
  "provider": "pkcs11"
}
```

---

## WebAuthn

Credential management for the signed-in user's own security keys. Served under `/api/v2/webauthn/`; there is no `/api/v2/account/webauthn/` prefix. The login-time WebAuthn routes are under [Authentication](#authentication).

### List Credentials
```http
GET /api/v2/webauthn/credentials
```
Any authenticated user. Returns the caller's keys.

### Delete Credential
```http
DELETE /api/v2/webauthn/credentials/{credential_id}
```
Session only. Closes the account's other sessions; `meta.other_sessions_closed` carries the count. `404` when the key is not the caller's; refused when it is the last second factor of an account that requires one.

### Toggle Credential
```http
POST /api/v2/webauthn/credentials/{credential_id}/toggle
Content-Type: application/json

{
  "enabled": true
}
```
Session only. `enabled` defaults to `true`. Disabling the last enabled factor of an account that requires two-factor is refused. Leaving the key as it is changes nothing and closes no session.

### Register - Get Options
```http
POST /api/v2/webauthn/register/options
```
Session only. Returns the creation options for the host the request was made to.

### Register - Verify
```http
POST /api/v2/webauthn/register/verify
Content-Type: application/json

{
  "credential": { ... },
  "name": "YubiKey 5"
}
```
Session only. `name` defaults to `Security Key`. `400` when the attestation does not verify. Registering a key closes the account's other sessions.

---

## Webhooks

One webhook subsystem, served under `/api/v2/webhooks`. The old `/api/v2/settings/webhooks` routes no longer exist. Reads need `read:settings`, writes `write:settings`, delete `delete:settings`. Event names are dotted (`certificate.issued`); `events` defaults to `["*"]` (all) and an unknown name answers `400`. A name already in use answers `409`; a URL that targets cloud metadata services or loopback answers `400`.

### List Webhooks
```http
GET /api/v2/webhooks
```

### Get Webhook
```http
GET /api/v2/webhooks/{endpoint_id}
```

### Create Webhook
```http
POST /api/v2/webhooks
Content-Type: application/json

{
  "name": "Slack Notification",
  "url": "https://hooks.slack.com/...",
  "secret": "webhook-secret",
  "events": ["certificate.issued", "certificate.expiring"],
  "ca_filter": [1, 2],
  "enabled": true,
  "custom_headers": {
    "X-Custom": "value"
  }
}
```
`name` and `url` are required. `secret` is generated when omitted. Optional `auth_type` is one of `none`, `bearer`, `basic`, `api_key`, `custom`, with `auth_token` and related fields.

### Update Webhook
```http
PUT /api/v2/webhooks/{endpoint_id}
Content-Type: application/json

{
  "name": "Updated Name",
  "url": "https://hooks.slack.com/...",
  "events": ["certificate.issued"],
  "enabled": true
}
```

### Delete Webhook
```http
DELETE /api/v2/webhooks/{endpoint_id}
```

### Toggle Webhook
```http
POST /api/v2/webhooks/{endpoint_id}/toggle
```

### Test Webhook
```http
POST /api/v2/webhooks/{endpoint_id}/test
```

### Regenerate Webhook Secret
```http
POST /api/v2/webhooks/{endpoint_id}/regenerate-secret
```

### List Available Events
```http
GET /api/v2/webhooks/events
```
Returns `events` (the accepted names) and a `descriptions` map.

### List Deliveries
```http
GET /api/v2/webhooks/{endpoint_id}/deliveries?status=failed&page=1&per_page=25
```
Delivery history of one endpoint, newest first. `status` is `pending`, `delivered` or `failed`; `per_page` is at most 100. `404` for an unknown endpoint.

The `certificate` of a `certificate.*` event is the certificate as the API reads it, its `comment` included: a comment written for operators reaches every endpoint subscribed to the event.

### Retry Delivery
```http
POST /api/v2/webhooks/{endpoint_id}/deliveries/{delivery_id}/retry
```
Permission `write:settings`. Re-queues a delivery for immediate redelivery with its attempts reset. `404` when the delivery does not belong to the endpoint.

`certificate.binding_left_behind` is sent once per binding when an EST, SCEP or WSTEP renewal leaves a deploy
binding or the HTTPS binding on the previous certificate, after the renewal's commit: `certificate` is the renewed
certificate, `previous_certificate` `{id, refid, descr}`, `binding` `{type: "deploy", id, target_id, target_name}`
or `{type: "https"}`, and `reason` `successor_without_key`. It also reaches the WebSocket `certificates` room.

---

## Certificate Policies & Approvals

### List Policies
```http
GET /api/v2/policies
```

### Get Policy
```http
GET /api/v2/policies/{policy_id}
```

### Create Policy
```http
POST /api/v2/policies
Content-Type: application/json

{
  "name": "Production Certificate Policy",
  "description": "Requires approval for production certificates",
  "operations": ["issuance", "renewal", "revocation"],
  "ca_id": 2,
  "template_id": 1,
  "requires_approval": true,
  "approval_group_id": 1,
  "min_approvers": 2,
  "notify_on_violation": true,
  "is_active": true,
  "priority": 10,
  "rules": { ... },
  "notification_emails": ["security@example.com"]
}
```

`rules.allowed_key_types` takes registry labels: `RSA-2048`, `RSA-3072`, `RSA-4096`,
`EC-P256`, `EC-P384`, `EC-P521`, `EC-BP256`, `EC-BP384`, `EC-BP512`, `ML-DSA-44`,
`ML-DSA-65` and `ML-DSA-87`. In FIPS mode a rule allowing ML-DSA, Ed25519 or Ed448 is refused
unless the loaded FIPS module approves it, and `GET /api/v2/policies/effective` leaves such a key
type out. `allowed_digests` does not bind an ML-DSA CA,
which signs without a separate digest; use
`allowed_signature_schemes` (`ml_dsa`) for that.

`operations` lists what the policy governs: `issuance` (issue form, Sign CSR, bulk signing and the renewals an operator performs), `renewal` (operator renewals and the renewal scheduler) and `revocation` (certificate, bulk, user certificate and intermediate CA revocations). Without it, the legacy `policy_type` names a single operation; with neither, the policy governs `issuance`.

With `notify_on_violation`, a refusal by the policy's rules or a request held for approval is e-mailed to `notification_emails` (mailbox addresses, checked: `400` otherwise), or when empty to the policy's approvers; the same refusal is reported once per hour.

When a policy requires approval, `POST /certificates/{id}/revoke`, `POST /certificates/bulk/revoke` (under `pending_approval`), `POST /user-certificates/{id}/revoke` and `POST /cas/{id}/revoke` (held by the policies of the parent CA and of the CA itself) answer `approval_required: true` with the `approval_id` and the `request_type` (`revocation` or `ca_revocation`) instead of revoking; the approval revokes with the stored reason and invalidity date. ACME `revokeCert` answers `403 unauthorized` for such a certificate (it revokes the certificate presented and never its related one), and removing an mTLS enrolment `409` until its certificate is revoked (administrators bypass). A pending request whose requester performs the action directly, or approves a duplicate, is closed as `cancelled`.

### Update Policy
```http
PUT /api/v2/policies/{policy_id}
Content-Type: application/json

{ ... }
```

A field left out of the body keeps its value. `rules`, when sent, replaces the policy's rules as a whole: a rule key left out of it is removed.

### Delete Policy
```http
DELETE /api/v2/policies/{policy_id}
```

### Toggle Policy
```http
POST /api/v2/policies/{policy_id}/toggle
```

### List Approval Requests
```http
GET /api/v2/approvals
GET /api/v2/approvals?status=pending
```

### Get Approval Request
```http
GET /api/v2/approvals/{request_id}
```

Each request, listed or read, carries `decision_rights`: for `approve` and `reject`, `null` when the signed-in user may take that decision, else the reason the server would refuse it: `not_in_group` (the policy names an approver group the user is not in; an administrator passes), `already_voted`, or `own_request` (approve only: a requester may still reject, to withdraw, their own request).

### Approve Request
```http
POST /api/v2/approvals/{request_id}/approve
Content-Type: application/json

{
  "comment": "Approved for production use"
}
```

### Reject Request
```http
POST /api/v2/approvals/{request_id}/reject
Content-Type: application/json

{
  "comment": "Missing justification"
}
```

### Approval Statistics
```http
GET /api/v2/approvals/stats
```

---

## Reports

UCM provides 6 built-in report types, an executive PDF report, and a full report scheduler with email delivery.

**Available Report Types:**

| Type Key | Description |
|----------|-------------|
| `expiring_certificates` | Certificates expiring within N days |
| `revoked_certificates` | Certificates revoked within the period, with revocation date and reason |
| `ca_hierarchy` | CA tree with issued certificate counts |
| `audit_summary` | Audit log activity grouped by action type |
| `compliance_status` | Policy compliance across all certificates |
| `certificate_inventory` | Full certificate inventory with metadata |

### List Report Types
```http
GET /api/v2/reports/types
```

**Response:**
```json
{
  "data": [
    {
      "id": "expiring_certificates",
      "name": "Expiring Certificates",
      "description": "Certificates expiring within a specified number of days",
      "params": ["days"]
    },
    {
      "id": "revoked_certificates",
      "name": "Revoked Certificates",
      "description": "All revoked certificates with reason and date"
    },
    {
      "id": "ca_hierarchy",
      "name": "CA Hierarchy",
      "description": "Certificate Authority tree with counts"
    },
    {
      "id": "audit_summary",
      "name": "Audit Summary",
      "description": "Recent audit log activity by action type"
    },
    {
      "id": "compliance_status",
      "name": "Compliance Status",
      "description": "Policy compliance overview"
    },
    {
      "id": "certificate_inventory",
      "name": "Certificate Inventory",
      "description": "Full inventory of all certificates"
    }
  ]
}
```

### Generate Report
```http
POST /api/v2/reports/generate
Content-Type: application/json

{
  "report_type": "expiring_certificates",
  "params": {
    "days": 30
  }
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `report_type` | string | Yes | One of the 6 report type keys |
| `params.days` | integer | No | Look-ahead days for `expiring_certificates`, look-back period for `revoked_certificates` and `audit_summary` (default: 30) |
| `params.reason` | string | No | `revoked_certificates` only: keep one RFC 5280 reason (e.g. `keyCompromise`) |
| `params.format` | string | No | `json` (default) or `csv` |

**Response:**
```json
{
  "data": {
    "report_type": "expiring_certificates",
    "generated_at": "2026-01-15T08:00:00Z",
    "records": [ ... ],
    "total": 12
  }
}
```

### Download Executive PDF
```http
GET /api/v2/reports/executive-pdf
```

Returns a downloadable PDF document containing:
- Cover page with organization name and generation date
- Executive summary with key metrics
- Risk assessment
- Certificate inventory breakdown
- Compliance status
- Lifecycle analysis
- CA infrastructure overview
- Recommendations

**Response:** `application/pdf` binary (Content-Disposition: attachment)

### Get Report Schedules
```http
GET /api/v2/reports/schedule
```

**Response:**
```json
{
  "data": {
    "expiring_certificates": {
      "enabled": true,
      "frequency": "weekly",
      "time": "08:00",
      "day_of_week": 1,
      "day_of_month": 1,
      "recipients": ["admin@example.com"],
      "format": "csv"
    },
    "pdf_compliance": {
      "enabled": false,
      "frequency": "monthly",
      "time": "09:00",
      "day_of_week": 0,
      "day_of_month": 1,
      "recipients": [],
      "format": "pdf"
    }
  }
}
```

### Update Report Schedule
```http
PUT /api/v2/reports/schedule
Content-Type: application/json

{
  "expiring_certificates": {
    "enabled": true,
    "frequency": "weekly",
    "time": "08:00",
    "day_of_week": 1,
    "day_of_month": 1,
    "recipients": ["admin@example.com", "security@example.com"],
    "format": "json"
  }
}
```

The body maps schedule keys to their configuration. Keys are the report type keys, plus `pdf_<template>` for the PDF templates (`pdf_executive`, `pdf_certificate_inventory`, `pdf_compliance`, `pdf_ca_overview`, `pdf_security_audit`). The report is emailed as an attachment in the schedule's format: CSV or JSON for data reports, PDF for templates.

**Schedule Config Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `enabled` | boolean | Yes | Enable or disable the schedule |
| `frequency` | string | Yes | `daily`, `weekly`, or `monthly` |
| `time` | string | Yes | Execution time in `HH:MM` (24-hour format) |
| `day_of_week` | integer | No | For weekly: `0` (Mon) – `6` (Sun) |
| `day_of_month` | integer | No | For monthly: `1` – `28` |
| `recipients` | array | Yes | Email addresses (max 50) |
| `format` | string | No | `csv` (default) or `json`; always `pdf` for `pdf_<template>` keys |

### Send Test Report
```http
POST /api/v2/reports/send-test
Content-Type: application/json

{
  "report_type": "expiring_certificates",
  "recipient": "admin@example.com"
}
```

Generates the report immediately and sends it to the specified recipient, attached in the schedule's saved format. Use this to verify email delivery and report content before enabling a schedule. Answers 502 when the email could not be sent.

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `report_type` | string | Yes | A schedule key (report type or `pdf_<template>`) |
| `recipient` | string | Yes | Email address to send the test report to |
| `format` | string | No | `csv` or `json`, overrides the saved format |

### Report Downloads and PDF Templates
```http
GET /api/v2/reports/download/{report_type}?format=csv&days=30
GET /api/v2/reports/pdf/templates
POST /api/v2/reports/pdf/generate
```
- `download` needs `read:audit` and `export:audit`. `format` is `csv` (default) or `json`, `days` an integer from 1 to 3650 (default 30); `400` for an unknown `report_type` or invalid value. Returns the report as a download. A CSV text cell that starts with `=`, `+`, `-`, `@`, a tab or a carriage return is written with a leading `'`, so a spreadsheet does not run it as a formula.
- `pdf/templates` (`read:audit`) lists the PDF templates and sections.
- `pdf/generate` (`read:audit` and `export:audit`) builds a PDF from `template` (a template name) or an explicit `sections` list; `400` when no valid section results, `500` when PDF generation is not available.

---

## WebSocket

### WebSocket Status
```http
GET /api/v2/websocket/status
```

### List Connected Clients
```http
GET /api/v2/websocket/clients
```

### Broadcast Message
```http
POST /api/v2/websocket/broadcast
Content-Type: application/json

{
  "message": "System maintenance in 10 minutes",
  "alert_type": "warning",
  "severity": "medium"
}
```

### List Event Types
```http
GET /api/v2/websocket/events
```

---

## Health

These endpoints are served at `/api/v2/health` (primary) with backward-compatible aliases at `/api/health` and `/health`. They do not require authentication and are intended for load balancers, monitoring systems, and frontend reconnection detection.

### Basic Health Check
```http
GET /api/v2/health
```

**Response:**
```json
{
  "status": "ok",
  "service": "ucm",
  "version": "2.1.0",
  "started_at": 1707123456.789,
  "websocket": true,
  "fips_active": false,
  "ha": false,
  "node_id": "ucm-1",
  "leader": true
}
```

| Field | Description |
|-------|-------------|
| `status` | Always `"ok"` when the service is running |
| `service` | Service identifier (`"ucm"`) |
| `version` | Current application version |
| `started_at` | Unix timestamp when the service started |
| `websocket` | Indicates whether the WebSocket (Socket.IO) server is initialized and ready to accept connections |
| `fips_active` | `true` when FIPS mode is in force (`UCM_FIPS=1` on an active FIPS provider); versions are only in the authenticated service status |
| `ha` | `true` when the node runs with `UCM_HA` |
| `node_id` | Node identifier (`UCM_NODE_ID`, defaults to the hostname) |
| `leader` | `true` when this node runs the scheduler, `false` when it does not, `null` when unknown |
| `safe_mode`, `safe_mode_reason` | Present only in safe mode |

### Readiness Check
```http
GET /api/v2/health/ready
```

Verifies the application can serve traffic (database, filesystem, Redis when configured). Returns 200 if ready, 503 if not. The response also carries `ha`, `node_id` and `leader` as above. A database that does not answer `SELECT 1` within 5 seconds fails the check; once it failed nothing else is read from the database, so in HA mode `checks.cluster` is an error too and `leader` is `null`.

**Response:**
```json
{
  "status": "ready",
  "checks": {
    "database": { "status": "ok" },
    "filesystem": { "status": "ok" }
  },
  "ha": false,
  "node_id": "ucm-1",
  "leader": true
}
```

In safe mode, `status` is `"safe_mode"`, `reason` gives the cause and `checks` is still reported. The code is 503 with `UCM_HA` or when a check fails, otherwise 200 so a single node keeps serving the safe-mode UI.

### Liveness Check
```http
GET /api/v2/health/live
```

Returns 200 if the application process is alive, regardless of dependency status. Neither the route nor any request hook reads the database for it (nor for the readiness check, apart from its own checks), and neither response carries `Strict-Transport-Security`, whose settings are in the database.

**Response:**
```json
{
  "status": "alive",
  "service": "ucm"
}
```

### Metrics
```http
GET /api/v2/metrics
GET /metrics
```
Prometheus text exposition. Off until a `metrics_token` is configured: without one the route answers `404`. With one, `Authorization: Bearer <token>` is required (`401` otherwise). No session is used.

---

## Protocol and Health Endpoints

These endpoints are not part of the `/api/v2` management API. Clients such as ACME clients, SCEP and EST devices, OCSP and CRL consumers, time-stamp clients and Windows enrollment run them, and each protocol applies its own authentication. The admin access allowlist does not apply to them (see the [Admin guide](ADMIN_GUIDE.md#admin-access-allowlist)). The protocols are described in their own guides; only the paths are listed here. Rate limits: see [Rate Limiting](#rate-limiting).

| Protocol | Paths | Guide |
|----------|-------|-------|
| ACME (RFC 8555) | `/acme/directory`, `/acme/new-nonce`, `/acme/new-account`, `/acme/new-order`, `/acme/new-authz`, `/acme/order/{id}`, `/acme/order/{id}/finalize`, `/acme/authz/{id}`, `/acme/challenge/{id}`, `/acme/cert/{id}`, `/acme/cert/{id}/alt/{variant}`, `/acme/acct/{id}`, `/acme/acct/{id}/orders`, `/acme/key-change`, `/acme/revoke-cert`, `/acme/renewalInfo/{certid}`, `/acme/terms`, `/acme/health` | [User guide](USER_GUIDE.md#acme), [admin guide](ADMIN_GUIDE.md#acme-administration) |
| ACME proxy | `/acme/proxy/` and `/acme/proxy/{slug}/` followed by `directory`, `new-nonce`, `new-account`, `new-order`, `order/{id}`, `order/{id}/finalize`, `authz/{id}`, `challenge/{id}`, `cert/{id}`, `acct/{id}`, `acct/{id}/orders`, `key-change`, `revoke-cert`, `renewal-info/{certid}`; the proxy has no terms, health or new-authz route | [Admin guide](ADMIN_GUIDE.md#acme-administration), [proxy clients](integrations/acme-proxy-clients.md) |
| ACME HTTP-01 | `/.well-known/acme-challenge/{token}` | [Admin guide](ADMIN_GUIDE.md#acme-client-http-01-challenges) |
| SCEP | `/scep/pkiclient.exe`, `/scep/{profile_slug}/pkiclient.exe`, `/cgi-bin/pkiclient.exe` | [User guide](USER_GUIDE.md#scep), [admin guide](ADMIN_GUIDE.md#scep-administration), [Intune](integrations/intune-scep.md) |
| EST (RFC 7030) | `/.well-known/est/` and `/.well-known/est/{label}/` followed by `cacerts`, `csrattrs`, `simpleenroll`, `simplereenroll`, `serverkeygen`, `fullcmc` | [User guide](USER_GUIDE.md#est), [admin guide](ADMIN_GUIDE.md#est-administration) |
| OCSP (RFC 6960) | `/ocsp` (POST), `/ocsp/{encoded_request}` (GET) | [User guide](USER_GUIDE.md#crl--ocsp), [admin guide](ADMIN_GUIDE.md#ocsp-configuration) |
| CRL distribution | `/cdp/{ca_ref}.crl`, `/cdp/{ca_ref}-delta.crl` | [Admin guide](ADMIN_GUIDE.md#crl-distribution) |
| CA issuers (AIA) | `/ca/{ca_ref}.cer`, `/ca/{ca_ref}.pem`, `/ca/{ca_ref}.p7c`, `/ca/{ca_ref}/cross/{xid}.cer` | [AIA CA Issuers](#aia-ca-issuers) |
| Time stamping (RFC 3161) | `/tsa` (POST) | [Time Stamping (TSA)](#time-stamping-tsa) |
| Windows enrollment (XCEP and WSTEP) | `/ADPolicyProvider_CEP_Kerberos/service.svc`, `/ADPolicyProvider_CEP_UsernamePassword/service.svc`, `/ADCertificateService_CES_Kerberos/service.svc`, `/ADCertificateService_CES_UsernamePassword/service.svc`, `/ADCertificateService_CES_Certificate/service.svc` | [Admin guide](ADMIN_GUIDE.md#windows-autoenrollment-xcepwstep-kerberosspnego), [Windows Enrollment Profiles](#windows-enrollment-profiles) |
| SSH setup | `/ssh/setup/{refid}`, `/ssh/setup/{refid}/public-key`, `/ssh/setup/{refid}/agent` | [SSH Certificates](#ssh-certificates) |
| SSH KRL | `/ssh/krl/{refid}` | [Public KRL](#public-krl) |
| SSH host enrollment and renewal | `/ssh/enroll/{refid}`, `/ssh/renew/{host_refid}/challenge`, `/ssh/renew/{host_refid}` | [SSH Hosts and Enrollment Tokens](#ssh-hosts-and-enrollment-tokens) |

The routes are always served; a protocol turned off in Settings refuses its requests with `503` (ACME, SCEP, EST, TSA, XCEP and WSTEP).

### Probes
`GET /health`, `/health/ready`, `/health/live` and their `/api/health` and `/api/v2/health` forms are described under [Health](#health). `GET /metrics` and `GET /api/v2/metrics` expose Prometheus metrics, see [Metrics](#metrics). The interactive API description is served at `/api/docs`.

---

## HTTP Status Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 201 | Created |
| 204 | No Content (successful deletion) |
| 400 | Bad Request (invalid parameters) |
| 401 | Unauthorized (not authenticated). A request refused by the authentication check, before the route ran, carries the problem type `urn:ucm:problem:authentication-required` |
| 403 | Forbidden (insufficient permissions) |
| 404 | Not Found |
| 409 | Conflict (resource already exists) |
| 422 | Unprocessable Entity (validation error) |
| 500 | Internal Server Error |
| 503 | Service Unavailable. A write that met another one on SQLite answers with `Retry-After: 5` and the problem type `urn:ucm:problem:database-busy`: the request may be sent again |

---

## Rate Limiting

Two limiters run in every node, and a request must pass both. A refused request answers `429` with `Retry-After`, `X-RateLimit-Limit` and `X-RateLimit-Remaining` headers, whichever limiter refused it; a refusal by a route limit also carries `X-RateLimit-Reset`.

- **Route limits (flask-limiter).** 200 requests per minute and 2000 per hour per client address on every route without a limit of its own, and per-route limits on sign-in: `POST /api/v2/auth/login/password` 5 per minute, `POST /api/v2/auth/login/webauthn/verify` 5 per minute, `POST /api/v2/sso/ldap/login` 5 per minute, `POST /api/v2/auth/login/2fa`, `/auth/login/2fa/webauthn/options`, `/auth/login/2fa/webauthn/verify`, `/auth/login/mtls` and `/auth/login/webauthn/start` 10 per minute, `POST /api/v2/auth/forgot-password` 3 per hour and `POST /api/v2/auth/reset-password` 5 per hour.
- **Tiered limiter (API and protocol endpoints).** Rates by path prefix in four tiers (auth, heavy, standard, protocol), each with a requests-per-minute rate and a burst. The defaults are set with `RATE_LIMIT_{AUTH,HEAVY,STANDARD,PROTOCOL}_{RPM,BURST}`; `RATE_LIMIT_ENABLED=false` (or `0`, `no`, `off`, any case) turns off both limiters, this one and the route limits above. Settings > Security, or `PUT /api/v2/system/security/rate-limit`, changes the limit of a path, the switch and the whitelist; the switch acts on this limiter only, never on the route limits, and has no effect while `RATE_LIMIT_ENABLED` turns the limiters off.

Requests from private (RFC 1918), loopback and link-local addresses are exempt from both limiters unless `RATE_LIMIT_TRUST_LAN=false`. Counters are kept in memory, per node. Behind a proxy, set `UCM_BEHIND_PROXY` and `UCM_TRUSTED_PROXIES` so the limits see the client's address. The tier table is in [SECURITY.md](SECURITY.md#4-rate-limiting); the effect of several nodes is in [HA.md](HA.md#rate-limits).

---

## Permissions

| Permission | Description |
|------------|-------------|
| `*` | Full access (admin only) |
| `read:*` | Read access to all resources |
| `read:certificates` | Read certificates |
| `write:certificates` | Create/update certificates |
| `delete:certificates` | Delete/revoke certificates |
| `read:cas` | Read CAs |
| `write:cas` | Create/update CAs |
| `delete:cas` | Delete CAs |
| `read:ssh` | Read SSH certificates |
| `write:ssh` | Sign, import and revoke SSH certificates |
| `delete:ssh` | Delete SSH certificates |
| `read:ssh_cas` | Read SSH CAs, their public keys, KRLs and setup scripts |
| `write:ssh_cas` | Create, import and update SSH CAs |
| `delete:ssh_cas` | Delete SSH CAs |
| `read:users` | Read users |
| `write:users` | Create/update users |
| `delete:users` | Delete users |
| `read:audit` | View audit logs |
| `delete:audit` | Cleanup audit logs |
| `admin:system` | System administration |

---

## Examples

### cURL with Session Cookie
```bash
# Login and save cookie
# Replace localhost with your server FQDN for remote access
curl -sk -c cookies.txt \
  -X POST https://localhost:8443/api/v2/auth/login/password \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Your-Admin-Password"}'

# Use cookie for subsequent requests
curl -sk -b cookies.txt https://localhost:8443/api/v2/certificates
```

### Python Example
```python
import requests

# Login
session = requests.Session()
session.verify = False  # For self-signed certs

response = session.post('https://localhost:8443/api/v2/auth/login/password', 
    json={'username': 'admin', 'password': 'Your-Admin-Password'})

# List certificates
certs = session.get('https://localhost:8443/api/v2/certificates')
print(certs.json())
```

### JavaScript Example
```javascript
// Login
const login = await fetch('/api/v2/auth/login/password', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'admin', password: 'Your-Admin-Password' }),
  credentials: 'include'
});

// List certificates
const certs = await fetch('/api/v2/certificates', {
  credentials: 'include'
});
const data = await certs.json();
```

---

**Coverage**: `backend/tests/test_api_reference_routes.py` checks this file against the application's route table.
