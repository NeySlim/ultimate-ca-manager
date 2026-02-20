# UCM API v2.0 - Complete Reference

> **Version**: 2.2.x  
> **Base URL**: `https://your-server:8443/api/v2`  
> **Last Updated**: February 2026  
> **Total Endpoints**: ~276  
> **Note**: All endpoints are served from `api/v2/` (34 registered blueprints). There is no separate `features/` module.

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
    "auth_method": "password"
  },
  "message": "Login successful"
}
```

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

### Login with mTLS
```http
POST /api/v2/auth/login/mtls
# Requires client certificate in TLS handshake
```

### Get Available Auth Methods
```http
POST /api/v2/auth/methods
Content-Type: application/json

{
  "username": "admin"
}
```

**Response:**
```json
{
  "data": {
    "password": true,
    "webauthn": true,
    "webauthn_credentials": 2,
    "mtls": false,
    "mtls_status": "not_present",
    "totp_enabled": true
  }
}
```

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

### WebAuthn Credentials

```http
# Check WebAuthn availability
GET /api/v2/account/webauthn/available

# List credentials
GET /api/v2/account/webauthn/credentials

# Register new credential - Step 1
POST /api/v2/account/webauthn/register/options

# Register new credential - Step 2
POST /api/v2/account/webauthn/register/verify
Content-Type: application/json

{
  "name": "YubiKey 5",
  "response": { ... }  // WebAuthn attestation response
}

# Toggle credential
POST /api/v2/account/webauthn/credentials/{credential_id}/toggle

# Delete credential
DELETE /api/v2/account/webauthn/credentials/{credential_id}
```

### mTLS Certificates

```http
# List enrolled certificates
GET /api/v2/account/mtls/certificates

# List all certificates (admin)
GET /api/v2/account/mtls/certificates/all

# Create new mTLS certificate
POST /api/v2/account/mtls/certificates/create
Content-Type: application/json

{
  "name": "My Laptop",
  "validity_days": 365
}

# Enroll existing certificate
POST /api/v2/account/mtls/certificates/enroll

# Download certificate
GET /api/v2/account/mtls/certificates/{cert_id}/download?format=pem

# Enable/disable certificate
POST /api/v2/account/mtls/certificates/{cert_id}/enable
Content-Type: application/json

{
  "enabled": true
}

# Revoke certificate
POST /api/v2/account/mtls/certificates/{cert_id}/revoke

# Delete certificate
DELETE /api/v2/account/mtls/certificates/{cert_id}

# Get mTLS settings
GET /api/v2/account/mtls/settings

# Update mTLS settings
PUT /api/v2/account/mtls/settings
Content-Type: application/json

{
  "enabled": true,
  "issuing_ca_id": 1
}
```

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
      "is_active": true,
      "certificates_count": 42
    }
  ],
  "meta": { "page": 1, "per_page": 20, "total": 3 }
}
```

### Get CA Hierarchy (Tree View)
```http
GET /api/v2/cas/tree
```

**Response:**
```json
{
  "data": [
    {
      "id": 1,
      "name": "Root CA",
      "ca_type": "root",
      "children": [
        {
          "id": 2,
          "name": "Intermediate CA",
          "ca_type": "intermediate",
          "parent_id": 1,
          "children": []
        }
      ]
    }
  ]
}
```

### Create CA
```http
POST /api/v2/cas
Content-Type: application/json

{
  "common_name": "My Root CA",
  "organization": "My Company",
  "country": "US",
  "state": "California",
  "locality": "San Francisco",
  "key_size": 4096,
  "validity_days": 3650,
  "ca_type": "root",
  "key_algorithm": "RSA"
}
```

**For Intermediate CA:**
```json
{
  "common_name": "My Intermediate CA",
  "parent_id": 1,
  "ca_type": "intermediate",
  "validity_days": 1825,
  "key_size": 4096
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
  "name": "Updated Name",
  "is_active": true
}
```

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
```

### Export All CAs
```http
GET /api/v2/cas/export
```

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
| `status` | string | Filter: `active`, `expired`, `revoked`, `expiring` |
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

### Export Certificate
```http
# PEM format (certificate only)
GET /api/v2/certificates/{cert_id}/export?format=pem

# PEM with private key
GET /api/v2/certificates/{cert_id}/export?format=pem&include_key=true

# PKCS12 (PFX)
GET /api/v2/certificates/{cert_id}/export?format=pkcs12&password=export-password

# DER format
GET /api/v2/certificates/{cert_id}/export?format=der

# Full chain
GET /api/v2/certificates/{cert_id}/export?format=chain
```

### Renew Certificate
```http
POST /api/v2/certificates/{cert_id}/renew
Content-Type: application/json

{
  "validity_days": 365
}
```

### Revoke Certificate
```http
POST /api/v2/certificates/{cert_id}/revoke
Content-Type: application/json

{
  "reason": "keyCompromise",
  "comments": "Private key was exposed"
}
```

**Revocation Reasons:**
- `unspecified`
- `keyCompromise`
- `caCompromise`
- `affiliationChanged`
- `superseded`
- `cessationOfOperation`

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
```

### Bulk Revoke Certificates
```http
POST /api/v2/certificates/bulk/revoke
Content-Type: application/json

{
  "ids": [1, 2, 3],
  "reason": "keyCompromise"
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
        "issuer": "CN=lan.pew.pet,O=Pew Pet",
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
GET /api/v2/user-certificates/{id}/export?format=pkcs12&password=mypassword
```

**Query Parameters**:
| Param | Type | Description |
|-------|------|-------------|
| format | string | `pem` (default) or `pkcs12` |
| include_key | bool | Include private key (default: true) |
| include_chain | bool | Include CA chain (default: true) |
| password | string | PKCS12 password (required for pkcs12, min 8 chars) |

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

### Upload CSR
```http
POST /api/v2/csrs
Content-Type: application/json

{
  "csr": "-----BEGIN CERTIFICATE REQUEST-----\n...",
  "name": "My Server CSR"
}
```

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
  "require_approval": false
}
```

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
```

### Register with Let's Encrypt Proxy
```http
POST /api/v2/acme/proxy/register
Content-Type: application/json

{
  "email": "admin@example.com",
  "agree_tos": true
}
```

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
    "url": "/scep/pkiclient.exe",
    "ca_id": 2,
    "ca_ident": "ucm-ca",
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
  "ca_ident": "ucm-ca",
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
```

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

### OCSP Status
```http
GET /api/v2/ocsp/status
```

### OCSP Statistics
```http
GET /api/v2/ocsp/stats
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
    "valid": true,
    "checked": 1000,
    "errors": []
  }
}
```

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
  "site_name": "My PKI",
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
  "smtp_user": "alerts@example.com",
  "smtp_password": "password",
  "smtp_tls": true,
  "from_address": "alerts@example.com"
}

# Test email
POST /api/v2/settings/email/test
Content-Type: application/json

{
  "to": "test@example.com"
}
```

### LDAP Settings
```http
# Get settings
GET /api/v2/settings/ldap

# Update settings
PATCH /api/v2/settings/ldap
Content-Type: application/json

{
  "enabled": true,
  "server": "ldap.example.com",
  "port": 389,
  "use_tls": true,
  "base_dn": "dc=example,dc=com",
  "bind_dn": "cn=admin,dc=example,dc=com",
  "bind_password": "password"
}

# Test connection
POST /api/v2/settings/ldap/test
```

### Webhooks
```http
# List webhooks
GET /api/v2/settings/webhooks

# Create webhook
POST /api/v2/settings/webhooks
Content-Type: application/json

{
  "name": "Slack Notification",
  "url": "https://hooks.slack.com/...",
  "events": ["certificate_issued", "certificate_expiring"],
  "secret": "webhook-secret"
}

# Test webhook
POST /api/v2/settings/webhooks/{webhook_id}/test

# Delete webhook
DELETE /api/v2/settings/webhooks/{webhook_id}
```

### Backup Settings
```http
# Get backup configuration
GET /api/v2/settings/backup

# Get backup schedule
GET /api/v2/settings/backup/schedule

# Update backup schedule
PATCH /api/v2/settings/backup/schedule
Content-Type: application/json

{
  "enabled": true,
  "frequency": "daily",
  "time": "02:00",
  "retention_days": 30
}

# Create backup
POST /api/v2/settings/backup/create

# List backups
GET /api/v2/settings/backup/history

# Download backup
GET /api/v2/settings/backup/{backup_id}/download

# Restore backup
POST /api/v2/settings/backup/restore
Content-Type: multipart/form-data

# Delete backup
DELETE /api/v2/settings/backup/{backup_id}
```

---

## System

### Database Operations
```http
# Get database stats
GET /api/v2/system/db/stats

# Export database
GET /api/v2/system/db/export

# Optimize database
POST /api/v2/system/db/optimize

# Check integrity
POST /api/v2/system/db/integrity-check

# Reset database (dangerous!)
POST /api/v2/system/db/reset
Content-Type: application/json

{
  "confirm": true
}
```

### HTTPS Certificate
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
# List backups
GET /api/v2/system/backup/list

# Create backup
POST /api/v2/system/backup/create

# Download backup
GET /api/v2/system/backup/{filename}/download

# Restore backup
POST /api/v2/system/backup/restore
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
  "new_key": "optional-new-key"
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
    "rotated_at": "2026-01-28T00:00:00",
    "next_rotation": "2026-04-28T00:00:00"
  }
}
```

### Security - Anomaly Detection
```http
GET /api/v2/system/security/anomalies
```

### Security - Rate Limit Configuration
```http
# Get rate limit settings
GET /api/v2/system/security/rate-limit

# Update rate limit settings
PUT /api/v2/system/security/rate-limit
Content-Type: application/json

{
  "requests_per_minute": 100,
  "enabled": true
}

# Get rate limit statistics
GET /api/v2/system/security/rate-limit/stats

# Reset rate limit counters
POST /api/v2/system/security/rate-limit/reset
```

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

# Install update
POST /api/v2/system/updates/install

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
# Get service status
GET /api/v2/system/service/status

# Restart service
POST /api/v2/system/service/restart
Content-Type: application/json

{
  "service": "ucm"
}
```

---

## Import/Export

### Certificate Import (File Upload)
```http
POST /api/v2/certificates/import
Content-Type: multipart/form-data

file: <certificate file>          # Required: .pem, .crt, .cer, .der, .p12, .pfx
name: "My Certificate"            # Optional: display name
password: "pkcs12password"        # Optional: for PKCS12 files
ca_id: 1                          # Optional: link to specific CA (auto-detected if omitted)
import_key: true                  # Optional: import private key (default: true)

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
  "zones": ["example.com"],
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
  "zones": ["example.com", "example.org"],
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

### List Orders
```http
GET /api/v2/acme/client/orders
GET /api/v2/acme/client/orders?status=pending&environment=production
```

### Get Order Details
```http
GET /api/v2/acme/client/orders/{order_id}
```

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

### Register ACME Account
```http
POST /api/v2/acme/client/account
Content-Type: application/json

{
  "email": "admin@example.com",
  "environment": "production"
}
```

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
  }
}
```

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
  "config": { ... }
}
```

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

The `/api/v2/webauthn/` blueprint provides the same WebAuthn credential management functionality as the `/api/v2/account/webauthn/` routes. Both prefixes are available for convenience.

### List Credentials
```http
GET /api/v2/webauthn/credentials
```

### Delete Credential
```http
DELETE /api/v2/webauthn/credentials/{credential_id}
```

### Toggle Credential
```http
POST /api/v2/webauthn/credentials/{credential_id}/toggle
Content-Type: application/json

{
  "enabled": true
}
```

### Register - Get Options
```http
POST /api/v2/webauthn/register/options
```

### Register - Verify
```http
POST /api/v2/webauthn/register/verify
Content-Type: application/json

{
  "credential": { ... },
  "name": "YubiKey 5"
}
```

---

## Webhooks

These routes are also accessible under `/api/v2/settings/webhooks` as an alias.

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
  "events": ["certificate_issued", "certificate_expiring"],
  "ca_filter": [1, 2],
  "enabled": true,
  "custom_headers": {
    "X-Custom": "value"
  }
}
```

### Update Webhook
```http
PUT /api/v2/webhooks/{endpoint_id}
Content-Type: application/json

{
  "name": "Updated Name",
  "url": "https://hooks.slack.com/...",
  "events": ["certificate_issued"],
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
  "policy_type": "issuance",
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

### List Report Types
```http
GET /api/v2/reports/types
```

### Generate Report
```http
POST /api/v2/reports/generate
Content-Type: application/json

{
  "report_type": "expiry",
  "params": {
    "days": 30
  }
}
```

### Download Report
```http
GET /api/v2/reports/download/{report_type}?format=pdf&days=30
```

### Get Report Schedule
```http
GET /api/v2/reports/schedule
```

### Update Report Schedule
```http
PUT /api/v2/reports/schedule
Content-Type: application/json

{
  "expiry_report": {
    "enabled": true,
    "frequency": "weekly",
    "recipients": ["admin@example.com"]
  },
  "compliance_report": {
    "enabled": false
  }
}
```

### Send Test Report
```http
POST /api/v2/reports/send-test
Content-Type: application/json

{
  "report_type": "expiry",
  "recipient": "admin@example.com"
}
```

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
  "websocket": true
}
```

| Field | Description |
|-------|-------------|
| `status` | Always `"ok"` when the service is running |
| `service` | Service identifier (`"ucm"`) |
| `version` | Current application version |
| `started_at` | Unix timestamp when the service started |
| `websocket` | Indicates whether the WebSocket (Socket.IO) server is initialized and ready to accept connections |

### Readiness Check
```http
GET /api/v2/health/ready
```

Verifies the application can serve traffic (database, filesystem). Returns 200 if ready, 503 if not.

**Response:**
```json
{
  "status": "ready",
  "checks": {
    "database": { "status": "ok" },
    "filesystem": { "status": "ok" }
  }
}
```

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

- Default: 100 requests per minute per IP
- Auth endpoints: 10 requests per minute per IP
- Export endpoints: 10 requests per minute per user

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
curl -sk -c cookies.txt \
  -X POST https://localhost:8443/api/v2/auth/login/password \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"changeme123"}'

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
    json={'username': 'admin', 'password': 'changeme123'})

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
  body: JSON.stringify({ username: 'admin', password: 'changeme123' }),
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
