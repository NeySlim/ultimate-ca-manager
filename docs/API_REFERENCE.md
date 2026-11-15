# UCM API v2 - Complete Reference

> **Version**: 2.48+  
> **Base URL**: `https://your-server:8443/api/v2`  
> **Last Updated**: February 2026  
> **Coverage**: `backend/tests/test_api_reference_routes.py` checks this file against the application's route table.  
> **Operation format**: each operation is written `METHOD /path` at the start of a line (`{id}` marks a path parameter).

---

## Table of Contents

1. [Authentication](#authentication)
2. [Account Management](#account-management)
3. [Certificate Authorities (CAs)](#certificate-authorities)
4. [Certificates](#certificates)
5. [User Certificates (mTLS)](#user-certificates-mtls)
6. [Certificate Signing Requests (CSRs)](#certificate-signing-requests)
6. [Templates](#templates)
7. [Trust Store](#trust-store)
8. [ACME Server](#acme-server)
9. [SCEP](#scep)
10. [CRL & OCSP](#crl--ocsp)
11. [Users](#users)
12. [Roles & Permissions (RBAC)](#roles--permissions-rbac)
13. [Dashboard](#dashboard)
14. [Audit Logs](#audit-logs)
15. [Settings](#settings)
16. [System](#system)
17. [Import/Export](#importexport)
18. [Certificate Tools](#certificate-tools)
19. [Global Search](#global-search)
20. [User Groups](#user-groups)
21. [Smart Import](#smart-import)
22. [DNS Providers](#dns-providers)
23. [ACME Client (Let's Encrypt)](#acme-client-lets-encrypt)
24. [ACME Domains](#acme-domains)
25. [SSO (LDAP/OAuth2/SAML)](#sso-ldapoauth2saml)
26. [HSM](#hsm)
27. [WebAuthn](#webauthn)
28. [Webhooks](#webhooks)
29. [Certificate Policies & Approvals](#certificate-policies--approvals)
30. [Reports](#reports)
31. [WebSocket](#websocket)
32. [Health](#health)

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

### Logout
```http
POST /api/v2/auth/logout
```

### Forgot Password
```http
POST /api/v2/auth/forgot-password
Content-Type: application/json

{
  "email": "user@example.com"
}
```

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

Served under `/api/v2/mtls/` (not under `/account/`). Except for the two settings routes, every route here refuses API keys: it needs an interactive session (`403` otherwise). A user works on their own enrolments; an admin may act on another user's where noted.

```http
GET /api/v2/mtls/settings
```
Permission `read:settings`. Returns `enabled`, `required`, `trusted_ca_id` and `trusted_ca` (`refid`, `name`, `valid_to`, `has_private_key`, or `null`).

```http
PUT /api/v2/mtls/settings
Content-Type: application/json

{ "enabled": true, "required": false, "trusted_ca_id": "<CA refid>" }
```
Permission `admin:system`. Every field is optional; an empty body answers `400`. Unknown `trusted_ca_id` when enabling answers `404`. `required: true` with `enabled: true` answers `400` while no active admin has an enabled enrolled certificate. The change needs a service restart: the response carries `needs_restart` and `restart_message` (in HA mode a rolling restart is queued instead).

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
Session only. `format` is `pem` (default) or `pkcs12`/`p12`. PKCS12 is refused on the query-string form with `400` (the password must travel in a POST body); it also needs a stored private key. `legacy` selects the 3DES/SHA-1 profile. Returns the file as a download. `404` when the enrolment is not the caller's (admins may download any).

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
Session only. Imports a PEM certificate (plain or base64 of the PEM) issued by a CA of this server and enrolls it. `pem` is required; `user_id` is honoured for admins only. `400` for unparsable data, an expired or revoked certificate, or a foreign issuer; `409` when already enrolled. Responds `201`.

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
whatever the leaf key: keep it for clients that do (OpenSSL, Go, Java 15 and later). SCEP and XCEP
refuse an EdDSA CA, and an EdDSA CA cannot sign timestamps itself (it can issue the TSA signer). ML-DSA needs
OpenSSL 3.5 or later and is refused in FIPS mode unless the loaded FIPS module approves it (the
`-fips` Docker image does); `keyAlgo` generates it in software, and
an HSM-held ML-DSA key is chosen with `hsm_key_algorithm` on a provider that has it (see [HSM](#hsm)).
An ML-DSA key signs without a separate digest: a `digest` sent for it is ignored and named
in `meta.notices`. An intermediate under an ML-DSA parent likewise takes no digest; an
ML-DSA intermediate under an RSA or EC parent uses its parent's digest.

In HA mode, a CA on a SoftHSM key (`hsm_key_id` of a key on a SoftHSM provider, or a new key
through `hsm_provider_id`) answers `409` with code `ha_mode`, whatever the CA type.

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

### List CA Certificates
```http
GET /api/v2/cas/{ca_id}/certificates
GET /api/v2/cas/{ca_id}/certificates?status=active&page=1&per_page=50
```

### Export CA
```http
GET /api/v2/cas/{ca_id}/export?format=pem
GET /api/v2/cas/{ca_id}/export?format=der
GET /api/v2/cas/{ca_id}/export?format=chain
POST /api/v2/cas/{ca_id}/export

# Chain through a cross-certificate (POST accepts the same field in its JSON body)
GET /api/v2/cas/{ca_id}/export?format=pem&include_chain=true&chain_variant=cross:4
```

`POST` takes `format`, `include_key`, `include_chain`, `password` (required for the PKCS12, PFX and JKS formats) and `legacy` in a JSON body. `chain_variant` is `auto` (default: the chain UCM serves), `primary` (the self-signed root)
or `cross:<id>`; any other value, or one that is not part of the chain of this CA, answers 400.

### Export All CAs
```http
GET /api/v2/cas/export
GET /api/v2/cas/export?chain_variant=all
POST /api/v2/cas/export
```

`chain_variant` adds cross-certificates after each CA certificate: `primary` (default) adds none,
`auto` the served ones, `all` every attached one, `cross:<id>` that one.

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
    "failed": [3]
  }
}
```

### Bulk Export CAs
```http
POST /api/v2/cas/bulk/export
Content-Type: application/json

{
  "ids": [1, 2, 3]
}
```

Returns a ZIP file containing the exported CA certificates.

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
| `search` | string | Search in CN, SANs |
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

# PEM with private key
GET /api/v2/certificates/{cert_id}/export?format=pem&include_key=true

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

Renewing a member of a hybrid pair renews both, and the new B names the new A; the response
lists the other member in `related_renewed`. When the two members require approval under
different policies, the renewal answers `409` and only an administrator can perform it.

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
revoked with its pair counts as a success.

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

Returns a ZIP file containing the exported certificates.

### Certificate Metadata, Linting and Transparency
```http
PATCH /api/v2/certificates/{cert_id}
Content-Type: application/json

{ "descr": "Web server" }
```
Permission `write:certificates`. Only the display name is mutable: `descr` is required, a non-empty string of at most 255 characters (`400` otherwise); `404` for an unknown certificate.

```http
GET /api/v2/certificates/{cert_id}/lint?profile=rfc5280
GET /api/v2/certificates/lint/status
GET /api/v2/certificates/compliance
POST /api/v2/certificates/{cert_id}/submit-ct
POST /api/v2/certificates/export
```
- Reads need `read:certificates`. `lint` checks one stored certificate against `profile` (`rfc5280` by default, `cabf` or `etsi`; `400` for another); `422` when the certificate cannot be linted. `lint/status` reports which linters are available and the accepted `profiles`. `compliance` returns aggregate compliance statistics (score and grade) across all certificates.
- `submit-ct` (`write:certificates`) submits the certificate to the configured Certificate Transparency logs and returns the `logs` that accepted it with their `timestamp`. `400` when CT is not enabled in the [settings](#certificate-transparency), no valid log is configured, the certificate has no PEM, or no log accepted it.
- `POST /certificates/export` is the body form of `GET /certificates/export`: `format` (`pem` or `p7b`, else `400`), `password` and `include_chain`; `404` when there is nothing to export.

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
| status | string | Filter by status: `valid`, `expired`, `revoked` |
| page | int | Page number (default: 1) |
| per_page | int | Items per page (default: 50) |

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
GET /api/v2/user-certificates/{id}/export?format=pem&include_key=true&include_chain=true
POST /api/v2/user-certificates/{id}/export
{"format": "pkcs12", "password": "mypassword", "include_chain": true, "include_root": false}
```

**Query Parameters**:
| Param | Type | Description |
|-------|------|-------------|
| format | string | `pem` (default) or `pkcs12` |
| include_key | bool | Include private key (default: true) |
| include_chain | bool | Include CA chain (default: true) |
| include_root | bool | Include the final self-signed Root CA when the chain is included (default: false) |
| password | string | PKCS12 password (required for pkcs12, min 8 chars) |
| legacy | bool | PKCS12 compatibility profile, 3DES/SHA-1 instead of AES-256/SHA-256 (default: false) |

**Response** `200`: Binary file download with `Content-Disposition` header.

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

### Generate CSR
```http
POST /api/v2/csrs
Content-Type: application/json

{
  "cn": "server.example.com",
  "organization": "My Company",
  "country": "US",
  "key_type": "EC P-256",
  "sans": ["DNS:server.example.com", "IP:192.168.1.10"]
}
```

UCM generates the key pair and keeps the private key. `key_type` is `RSA 2048`, `RSA 3072`,
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
    "failed": [3]
  }
}
```

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
Permission `read:csrs`. `format` is `csr` (default) or `key` (the private key, with an optional `password` for an encrypted export); the `GET` form refuses a `password` in the query string (`400`). `400` when the CSR has no private key for `key`; `404` for an unknown CSR.

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
  "certificate": "-----BEGIN CERTIFICATE-----\n...",
  "name": "External Root CA",
  "description": "Third-party CA for partner integration"
}
```

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
purpose: "trust_anchor"
description: "Third-party CA"
notes: "Optional notes"
```

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
- `export` (`read:truststore`) downloads a bundle: `format` `pem` (default) or `p7b`, `purpose` filters (default `all`). `404` when nothing matches.

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
GET /api/v2/acme/accounts
```

### List ACME Orders
```http
GET /api/v2/acme/orders
GET /api/v2/acme/orders/{order_pk}
```
The second form reads one local order (`read:acme`), whatever its age; 404 when it does not exist.

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
`DELETE` (`delete:acme`) removes one local order with its authorizations and challenges (`404` when unknown). `purge` (`delete:acme`) runs the expired-order purge now and returns the counts of orders, authorizations and challenges removed. `history` (`read:acme`) lists certificates issued through ACME, local and external CAs; `source` filters.

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
Reads need `read:acme`, writes `write:acme`, `DELETE` `delete:acme`. `POST` body: optional `label` (255 characters at most), `expires_in_days` (a positive integer, `400` otherwise) and `allowed_domains` (a list of patterns, `["*"]` for any); the response carries the credential and, once only, its `hmac_key`. `PATCH` changes `allowed_domains` (never `null`) and `notes`. `DELETE` revokes an active credential (and its DNS UPDATE keys); a credential already revoked or used is deleted for good (`204`). The list holds at most 200, newest first, and never shows an `hmac_key`. `eab-required` reads or sets `{"eab_required": true}` (`PATCH` and `PUT` are the same route).

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
GET /api/v2/scep/requests?status=pending
GET /api/v2/scep/requests/{request_id}
```
The list holds the latest 50; the last form reads any one request (`read:scep`), 404 when it does not exist.

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

### Get Challenge Password
```http
GET /api/v2/scep/challenge/{ca_id}
```

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
- `GET /config` returns `enabled`, `ca_refid`, `ca_id`, `ca_name`, `policy_oid`, `require_dedicated_cert`, `signer_cert_refid` (empty when the CA certificate signs) and `signer` (subject, serial, expiry, chain status and usability of the configured signer).
- `PATCH /config` changes any of `enabled`, `ca_id` or `ca_refid`, `policy_oid` (`400` unless a valid OID), `require_dedicated_cert` and `signer_cert_refid`; `400` when the chosen CA or signer cannot sign time stamps.
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

- `q` matches the name or the realm; `ca` a refid of the issuing or policy CA; `state` one of `complete`, `keytab_missing`, `connector_failing` (the connector's last probe says down) and `disabled`, else 400. Each profile carries its `state`, its connector's name, health and realm, and its `template_ids`; the detail (`GET /{id}`) adds `keytab_entries` (principal, realm, kvno, enctype). `per_page` is capped at 200; `meta` carries `total`, `page`, `per_page`, `total_pages`.
- `PUT` and `PATCH` are the same partial update: only the fields sent change.
- Each profile carries `policy_id` (the MS-XCEP policy identifier) and `policy_oid_root` (the root of its template OIDs, `<policy_oid_root>.1.<template id>`). Both are read-only: set at creation (at random, or the values 2.254 served for the default profile of an upgraded installation), never changed by a change of CA, and ignored in a `POST`, `PUT` or `PATCH` body. A replacing restore puts back the archived values; a merge keeps those of a profile that already exists.
- Writable fields: `name`, `realm` (upper-cased; refused when another profile holds it or the keytab does not name it; `null` clears it, an empty or blank string is a 400), `enabled` and `is_default` (JSON booleans, else 400; `is_default` is accepted at creation only, for the first default profile), `connector_id` (an integer or `null`) (its base DN domain must equal the realm), `issuing_ca_refid` (a string; must be able to sign), `policy_ca_refid` (a string; no EdDSA key), `validity_days`, `xcep_username`, `xcep_password`, `wstep_username`, `wstep_password`, `allowed_ad_group`, `pinned_subject_fields`, `template_ids` (the templates offered; empty: those of the CA).
- `pinned_subject_fields` takes an object, or its JSON text, with the keys `O`, `OU`, `C` (two letters, upper-cased), `ST` and `L` only; an empty object, an empty string or `null` stores none, anything else is a 400. It is returned as JSON text.
- There is at most one default profile; it cannot be deleted (disable it) and `is_default` cannot be changed on an existing profile.
- A profile through which valid certificates were issued cannot be deleted (409 with the count); disable it instead.
- `POST /{id}/keytab` takes a multipart `file` (a keytab GSSAPI loads, 256 KiB at most; every entry must be `HTTP/<SPN host>@<realm of the profile>`, else 400) and replaces the profile's keytab; with the form field `dry_run=1` it stores nothing and lists the entries by realm, `foreign_entries` being those the server would refuse. It needs `write:xcep` and `write:kerberos`, the scope of the retired `POST /api/v2/kerberos/keytab`.
- `settings` holds what every profile shares: `xcep_enabled`, `wstep_enabled` (needs `read:wstep` / `write:wstep`; changing it restarts the service, the TLS cap being read at startup), `kerberos_enabled`, `kerberos_spn` (`read:kerberos` / `write:kerberos`), the state of the served keytab, and the `default_profile` with its realm.
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
- `POST` fields: `name` (required, unique: `409`), `server` (required hostname), `auth_method` (`certificate` by default, `kerberos` or `basic`, else `400`), `ca_name`, `use_ssl` and `verify_ssl` (both default true), `ca_bundle`, `default_template` (`WebServer`), `enabled` (true), `username` and `password` (basic), `client_cert_pem` and `client_key_pem` (certificate), `kerberos_principal` and `kerberos_keytab_path`, `crl_sync_enabled`, `crl_url`, `inventory_sync_enabled`, and the WinRM admin channel fields `winrm_enabled`, `winrm_host`, `winrm_port`, `winrm_use_ssl`, `winrm_verify_ssl`, `winrm_transport`, `winrm_username`, `winrm_password`. `PUT` is a partial update of the same fields; a masked secret sent back keeps the stored one.
- `DELETE` answers `204`, or `409` while requests are pending on the connection.
- `POST /test` checks the connection with the submitted values before saving (`server` required); `POST /{id}/test` checks a saved one. Both answer `400` with the error when the check fails.

### Signing and Requests
```http
GET /api/v2/microsoft-cas/{id}/templates
POST /api/v2/microsoft-cas/{id}/sign/{csr_id}
GET /api/v2/microsoft-cas/{id}/requests/{request_id}
GET /api/v2/microsoft-cas/requests/pending?msca_id=1
```
- `templates` and both request reads need `read:certificates`; `sign` needs `write:certificates`.
- `sign` submits the CSR `{csr_id}` to the CA. Optional body: `template` (defaults to the connection's `default_template`; `400` when none), `enrollee_name`, `enrollee_upn`. `404` when the connection or CSR is unknown, `400` when the connection is disabled, the CSR was already signed, is empty or its signature is invalid. An issued certificate is imported into UCM ("Certificate issued by Microsoft CA"); a request the CA holds for approval answers "Request pending approval" and is tracked.
- `GET /{id}/requests/{request_id}` refreshes one request and imports the certificate once issued; `404` for an unknown request.

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
All answer `404` for an unknown connection and `400` when the admin channel is not enabled or configured on it. `admin-channel/test` (`admin:system`) tests the channel (connection and CA service); its body may carry the `winrm_*` fields and `ca_config` as overrides. `ca/health` and `ca/pending` (`read:certificates`) return the CA's service, certificate and CRL state, and the requests awaiting a CA manager. `approve` and `deny` (`admin:system`) resubmit or refuse a pending request on the CA; `approve` imports the issued certificate.

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
- `GET` list filters by `search` and by `type` (repeatable).
- `POST` creates a CA (`201`): `descr` (or `name`, required), `ca_type` (`user` by default, or `host`), `key_type`, `default_ttl`, `max_ttl` (default `0`), `default_extensions`, `allowed_principals` (a list of non-empty strings), `allow_any_principal` and `allow_custom_key_id` (JSON booleans, default off), `comment`. `400` for an invalid value.
- `PUT` updates the same metadata (`descr`, `default_ttl`, `max_ttl`, `comment`, `default_extensions`, `allowed_principals`); `400` for an invalid value.
- `DELETE` answers `204`, or `409` when the service refuses (certificates still depend on the CA).
- `POST /import` imports an existing CA from `private_key` (required) with `descr`, `ca_type` (`user` or `host`), `default_ttl`, `max_ttl` and `comment`; `201`, or `400` for an unusable key.
- `public-key` downloads the CA public key in OpenSSH format. `krl` downloads the CA's key revocation list. `setup-script` returns a server setup script for trusting the CA: `type` (`user` or `host`), `hostname` (validated, `400` when invalid) and `platform` (`unix` by default, or `windows`).

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
- The list is paginated; `status`, `type` and `ca_id` may be repeated, an unknown `status` answers `400`.
- `POST` signs a public key (`write:ssh`, `201`). Body: `ca_id` and `public_key` (required), `cert_type` (`user` by default, or `host`), `principals` (a list or a comma-separated string, at least one, no comma inside a name, 64 at most), `validity_seconds` (an integer from 60 to ten years), `key_id`, `extensions`, `critical_options`, `descr`. `400` for any invalid field or a CA policy refusal.
- `POST /generate` takes the same fields without `public_key`, plus `key_type`: UCM creates the key pair and returns the certificate with the `private_key` once.
- `POST /import` stores an existing certificate: `certificate` (required), optional `descr` and `ssh_ca_id`; `201`.
- `POST /verify` (`read:ssh`) decodes and verifies `certificate` (required) and returns the result.
- `export` returns the certificate in OpenSSH format. `revoke` takes an optional `reason` (default `unspecified`) and returns the certificate. `DELETE` answers `204` or `409` when it cannot be deleted.
- `stats` returns the counts shown on the SSH dashboard.

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
GET /api/v2/discovery/export?format=csv&profile_id=1&status=new
GET /api/v2/discovery/stats?profile_id=1
POST /api/v2/discovery/bulk-resolve-dns
```
- The list returns `items` and `total`; `limit` defaults to 50 (200 at most), `status` may be repeated.
- `GET /{disc_id}` adds the parsed `extensions`, key and signature details and the SHA-1 and SHA-256 fingerprints; `404` when unknown. `DELETE /{disc_id}` answers `204`.
- `DELETE /api/v2/discovery` (`admin:system`) deletes every record, or those of `profile_id`, and returns `deleted`.
- `export` returns CSV (default) or JSON (`format=json`) as a download.
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
The list returns `requests` (newest first, the latest 500) and `dual_control`, whether the approver must differ from the requester. `GET /{id}` reads one request whatever its age.

```http
POST /api/v2/key-recovery/{id}/approve
POST /api/v2/key-recovery/{id}/reject
Content-Type: application/json

{ "note": "Ticket 1234" }
```
`admin:key_recovery`. `note` is optional (2000 characters at most). `409` when the request is no longer pending. `approve` answers `403` when dual control is on and the caller is the requester, and `410` when the certificate no longer exists.

```http
POST /api/v2/key-recovery/{id}/recover
Content-Type: application/json

{ "password": "at-least-8-chars", "legacy": false }
```
Returns the key and certificate as a PKCS#12 download, once, after approval. `password` is required (`400` when it does not meet the export password rules); `legacy` selects the 3DES/SHA-1 profile. `409` when the request is not approved, `403` unless the caller is the requester or holds `admin:key_recovery`, `410` when the certificate or key is gone.

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
and its servable cross-certificates.

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
Content-Type: application/json

{
  "users": [
    {
      "username": "user1",
      "email": "user1@example.com",
      "role": "viewer"
    }
  ],
  "send_invites": true
}
```

### Delete User
```http
DELETE /api/v2/users/{user_id}
```

### More User Operations
```http
POST /api/v2/users/{user_id}/toggle-active
POST /api/v2/users/{user_id}/unlock
POST /api/v2/users/{user_id}/reset-2fa
POST /api/v2/users/{user_id}/link-sso
POST /api/v2/users/{user_id}/unlink-sso
POST /api/v2/users/bulk/delete
GET /api/v2/users/password-policy
POST /api/v2/users/password-strength
```
- `toggle-active` is the same route as `PATCH /api/v2/users/{user_id}/toggle`. `403` for your own account, `409` when it would deactivate the last active admin. These routes need `write:users` and an admin caller (`403` otherwise); `404` for an unknown user.
- `unlock` clears a lockout and answers `Account is not locked` when there was none.
- `reset-2fa` clears the user's second factor, the break-glass for a locked-out user.
- `link-sso` takes `{"provider_id": 1}` (required) and links a local account to an SSO provider; `400` when the user is already linked, `404` for an unknown provider. `unlink-sso` turns an SSO-linked account back into a local one (`400` when it is not linked).
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

**Response:**
```json
{
  "data": {
    "status": "healthy",
    "database": "connected",
    "disk_usage": {
      "used": "2.1GB",
      "total": "50GB",
      "percent": 4.2
    },
    "uptime": "15 days, 3:42:15",
    "version": "2.x"
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
```
Scope `read:dashboard`. A `days` outside its range is refused with 400.

`queue` lists `{kind, tier, id, label, due_at, href_hint}` items, critical first then by `due_at` (at most `limit`, 100), with the full total per kind in `counts`. A repeated `kind` restricts the items, not the counts, to those kinds; an unknown kind is refused with 400:

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

Certificates counted are issued, not revoked, not archived and not expired. A certificate appears under one kind only, by precedence `auto_renewal_blocked` > `renewal_declined` > `manual_renewal_due` > `client_renewal_overdue`. `manual_renewal_due` leaves out what auto-renewal, the enrolling client (ACME, SCEP, EST, WSTEP without a stored key), UCM's ACME client or the delegated OCSP responder task renews, a declined renewal, and a certificate superseded by a live one beyond the 30 days with the same subject, DNS and IP SANs from the same CA.

`href_hint` carries the object in the query (`request`, `order`, `ca`) and the tab (`tab`) the page reads; `contracts/queue_links.json` lists them. `GET /api/v2/key-recovery/{id}` (`read:key_recovery`) reads one recovery request like the two reads above.

`health` gives per protocol (`acme`, `scep`, `est`, `tsa`, `scheduler`) the `basis` it is measured on and, for `acme`, `scep` and `est`, one `{date, ok, failed}` entry per UTC day (`days` 1 to 30) in `periods`; `periods` is null for `tsa` and `scheduler`. `tsa` is present while the TSA is enabled: `state` is `ca_certificate` or `dedicated` (healthy), `no_signer` (no signer configured, not an alert: `/tsa` answers 503 until one is), `expiring` (dedicated signer within 30 days of expiry, `days_left`), `unusable` (`reason`: `expired`, `revoked`, `key_unavailable` or `invalid`) or `unavailable`; `alert` is true for `expiring`, `unusable` and `unavailable`. `scheduler` carries `by_status` and `stale`, which the latest `last_status` does not replace. `compliance` counts the live certificates by key algorithm and weakness; each counter, and each key algorithm, carries `filter_available` and a `filter_hint`: query parameters that the certificate list applies as given and that reproduce the count exactly (see below). `issuance` gives per CA and per day (`days` 1 to 90) `issued` (by `created_at`) and `renewed` (in place, by `renewed_at`: the last renewal of each certificate in the window, so a certificate renewed several times counts once), and the issuances per source.

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

### Cleanup Old Logs
```http
POST /api/v2/audit/cleanup
Content-Type: application/json

{
  "retention_days": 90
}
```

### Verify Audit Log Integrity
```http
GET /api/v2/audit/verify
GET /api/v2/audit/verify?start_id=1&end_id=1000
```

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
POST /api/v2/settings/backup/restore
Content-Type: multipart/form-data

# Delete backup
DELETE /api/v2/settings/backup/{backup_id}
```

---

## System

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
Permission `admin:system`. Runs VACUUM and ANALYZE (SQLite and PostgreSQL).

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

# Apply new certificate
POST /api/v2/system/https/apply
Content-Type: application/json

{
  "certificate": "-----BEGIN CERTIFICATE-----\n...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n..."
}
```

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
nothing is restored. A successful restore answers `restart_detail` "Rolling restart requested: the nodes
restart one at a time". Both restore routes also answer `data.todo`, a list of strings with one line per warning
(sections not restored, a CA whose CRL could not be signed, a secret to enter again); it is empty when there is
nothing to do. The backup listing's `meta.restore_limits` gives `upload_bytes` (archives before v4) and
`archive_bytes` (v4, `0` for no ceiling), the sizes a restore accepts.

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
`burst` defaults to a third of `rpm`. In HA mode the change is stored and applied on every node. `stats` (`read:settings`) returns the counters. `reset` (`admin:system`) clears the buckets, of one address with `{"ip": "..."}` or all, and the statistics too with `{"reset_stats": true}`.

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
# Check for updates
GET /api/v2/system/updates/check

# Install update (HA mode: starts a rolling update of every node, 409 when one runs, a node
# has no package family (Docker, unknown), the release lacks a present family's package or
# SHA-256, or its full-stop-migrations.json is missing or names a migration not yet applied;
# Docker/Kubernetes: 400, the orchestrator updates)
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
# stale, version, started_at, heartbeat_at, command_seen and package_family (deb, rpm-elN,
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
`session.short_secret_key`, `msca.winrm_ntlm`, `database.postgres_without_tls`, `https.unapproved_key` (blockers);
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
  "password": "output-password",
  "pkcs12_password": "pkcs12-password",
  "chain": "-----BEGIN CERTIFICATE-----\n...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n..."
}
```

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

**Response:**
```json
{
  "data": {
    "certificates": [...],
    "cas": [...],
    "csrs": [...],
    "users": [...]
  }
}
```

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
`PATCH` (`write:acme`) updates `label`, `email`, `account_key_algorithm`, `eab_kid`, `eab_hmac_key` and `is_default`. `DELETE` (`delete:acme`) answers `409` while issued orders still renew through the account. `deactivate` (`delete:acme`) deactivates the account at the CA (RFC 8555 section 7.3.6), then removes it; `502` when the CA refuses. `default` (`write:acme`) makes it the account used when a request names none. `register` (`write:acme`) registers or re-registers it with its CA; optional `email`, `400` without a valid contact.

### ACME Client Preflight
```http
POST /api/v2/acme/client/preflight
Content-Type: application/json

{ "domains": ["www.example.com"], "challenge_type": "dns-01", "mode": "full" }
```
Permission `write:acme`. Dry-run of a certificate request; returns a report with `ok` and per-step results. `domains` is required; `challenge_type` defaults to `dns-01`; `mode` is `full` (default) or `validate_only`; optional `email`, `acme_account_id`, `dns_provider_id` (integers), `key_source` (default `generate`), `csr_pem` and `verify_dns`.

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

The mapping is checked when the provider is created or updated: an unknown base role, an unknown custom role or a malformed entry returns `400` and nothing is saved. At login, a value that has become invalid is not trusted: an invalid base role counts as `viewer` and an unknown custom role is ignored.

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
- `metadata/fetch` (`write:sso`) fetches and parses IdP metadata from `{"metadata_url": "https://..."}` (required; http or https with a hostname, not loopback or a cloud metadata address: `400`); optional `provider_id`, `verify_ssl` (default true) and `ca_bundle`.
- `test-mapping` (`write:sso`) is a dry run of the LDAP group lookup for `{"username": "..."}` (required) without creating a session. `400` for a provider that is not LDAP or a failed lookup.

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

### Test HSM Provider
```http
POST /api/v2/hsm/providers/{provider_id}/test
```

### Sync HSM Provider
```http
POST /api/v2/hsm/providers/{provider_id}/sync
```

In HA mode, syncing a SoftHSM provider answers `409` with code `ha_mode`: its keys exist on one node only.

### List HSM Keys
```http
GET /api/v2/hsm/keys
GET /api/v2/hsm/keys?provider_id=1
```

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
- `download` needs `read:audit` and `export:audit`. `format` is `csv` (default) or `json`, `days` an integer from 1 to 3650 (default 30); `400` for an unknown `report_type` or invalid value. Returns the report as a download.
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

Verifies the application can serve traffic (database, filesystem, Redis when configured). Returns 200 if ready, 503 if not. The response also carries `ha`, `node_id` and `leader` as above.

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

Returns 200 if the application process is alive, regardless of dependency status.

**Response:**
```json
{
  "status": "alive",
  "service": "ucm"
}
```

---

## HTTP Status Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 201 | Created |
| 204 | No Content (successful deletion) |
| 400 | Bad Request (invalid parameters) |
| 401 | Unauthorized (not authenticated) |
| 403 | Forbidden (insufficient permissions) |
| 404 | Not Found |
| 409 | Conflict (resource already exists) |
| 422 | Unprocessable Entity (validation error) |
| 500 | Internal Server Error |

---

## Rate Limiting

Two limiters run in every node, and a request must pass both. A refused request answers `429`; the second limiter adds `Retry-After`, `X-RateLimit-Limit` and `X-RateLimit-Remaining` headers.

- **Route limits (flask-limiter).** Fixed in code: 200 requests per minute and 2000 per hour per client address on every route without a limit of its own, and per-route limits on sign-in: `POST /api/v2/auth/login/password` 5 per minute, `POST /api/v2/auth/login/webauthn/verify` 5 per minute, `POST /api/v2/sso/ldap/login` 5 per minute, `POST /api/v2/auth/login/2fa`, `/auth/login/2fa/webauthn/options`, `/auth/login/2fa/webauthn/verify`, `/auth/login/mtls` and `/auth/login/webauthn/start` 10 per minute, `POST /api/v2/auth/forgot-password` 3 per hour and `POST /api/v2/auth/reset-password` 5 per hour.
- **Tiered limiter (API and protocol endpoints).** Rates by path prefix in four tiers (auth, heavy, standard, protocol), each with a requests-per-minute rate and a burst. The defaults are set with `RATE_LIMIT_{AUTH,HEAVY,STANDARD,PROTOCOL}_{RPM,BURST}`; `RATE_LIMIT_ENABLED=false` turns this limiter off. Settings > Security, or `PUT /api/v2/system/security/rate-limit`, changes the limit of a path, the switch and the whitelist.

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

**Documentation generated**: February 2026  
**API Version**: 2.2.x  
**Total Endpoints**: ~276
