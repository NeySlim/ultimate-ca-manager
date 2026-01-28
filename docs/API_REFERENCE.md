# UCM API v2.0 - Complete Reference

> **Version**: 2.0.0  
> **Base URL**: `https://your-server:8443/api/v2`  
> **Last Updated**: January 2026  
> **Total Endpoints**: 155

---

## Table of Contents

1. [Authentication](#authentication)
2. [Account Management](#account-management)
3. [Certificate Authorities (CAs)](#certificate-authorities)
4. [Certificates](#certificates)
5. [Certificate Signing Requests (CSRs)](#certificate-signing-requests)
6. [Templates](#templates)
7. [Trust Store](#trust-store)
8. [ACME](#acme)
9. [SCEP](#scep)
10. [CRL & OCSP](#crl--ocsp)
11. [Users](#users)
12. [Roles & Permissions](#roles--permissions)
13. [Dashboard](#dashboard)
14. [Audit Logs](#audit-logs)
15. [Settings](#settings)
16. [System](#system)
17. [Import/Export](#importexport)

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

### Refresh Token
```http
POST /api/v2/auth/refresh
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

---

## ACME

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

### Update Configuration
```http
PATCH /api/v2/scep/config
Content-Type: application/json

{
  "enabled": true,
  "issuing_ca_id": 2,
  "challenge_password": "secret123",
  "validity_days": 365
}
```

### Get Statistics
```http
GET /api/v2/scep/stats
```

### List Pending Requests
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

## Roles & Permissions

### List Roles
```http
GET /api/v2/roles
```

**Response:**
```json
{
  "data": {
    "roles": ["admin", "operator", "viewer"],
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
GET /api/v2/roles/{role}
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
    "version": "2.0.0"
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

---

## Import/Export

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

**Documentation generated**: January 28, 2026  
**API Version**: 2.0.0  
**Total Endpoints**: 155
