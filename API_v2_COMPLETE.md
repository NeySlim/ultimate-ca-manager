# UCM API v2.0 - Complete Documentation

**Ultimate Certificate Manager** - REST API Reference

**Version:** 2.0  
**Base URL:** `https://your-domain:8443/api/v2`  
**Authentication:** JWT Bearer Token  
**Content-Type:** `application/json`

---

## Table of Contents

1. [Authentication](#authentication)
2. [Dashboard](#dashboard)
3. [Certificate Authorities (CAs)](#certificate-authorities)
4. [Certificates](#certificates)
5. [Certificate Signing Requests (CSRs)](#certificate-signing-requests)
6. [Certificate Revocation Lists (CRLs)](#certificate-revocation-lists)
7. [ACME](#acme)
8. [SCEP](#scep)
9. [Templates](#templates)
10. [TrustStore](#truststore)
11. [Users](#users)
12. [Settings](#settings)
13. [Account](#account)
14. [System](#system)
15. [Response Formats](#response-formats)
16. [Error Codes](#error-codes)

---

## Authentication

### Login
```http
POST /api/v2/auth/login
```

**Request:**
```json
{
  "username": "admin",
  "password": "admin123"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
    "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
    "user": {
      "id": 1,
      "username": "admin",
      "email": "admin@ucm.local",
      "role": "admin"
    }
  }
}
```

**cURL Example:**
```bash
curl -X POST https://localhost:8443/api/v2/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' \
  -k
```

### Verify Token
```http
GET /api/v2/auth/verify
Authorization: Bearer <token>
```

### Refresh Token
```http
POST /api/v2/auth/refresh
Authorization: Bearer <refresh_token>
```

### Logout
```http
POST /api/v2/auth/logout
Authorization: Bearer <token>
```

---

## Dashboard

### Get Statistics
```http
GET /api/v2/dashboard/stats
Authorization: Bearer <token>
```

**Response:**
```json
{
  "success": true,
  "data": {
    "total_cas": 5,
    "total_certificates": 42,
    "expiring_soon": 3,
    "revoked": 1,
    "pending_csrs": 2,
    "acme_renewals": 4
  }
}
```

### Get Activity Log
```http
GET /api/v2/dashboard/activity
Authorization: Bearer <token>
```

**Query Parameters:**
- `limit` (int): Number of entries (default: 10)

### Get System Status
```http
GET /api/v2/dashboard/system-status
```

**Response:**
```json
{
  "success": true,
  "data": {
    "database": "online",
    "acme_service": "online",
    "scep_service": "online",
    "core_service": "online"
  }
}
```

---

## Certificate Authorities

### List CAs
```http
GET /api/v2/cas
Authorization: Bearer <token>
```

**Query Parameters:**
- `page` (int): Page number
- `per_page` (int): Items per page (max 100)
- `type` (string): `root` or `intermediate`

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "refid": "ca-abc123",
      "common_name": "My Root CA",
      "is_root": true,
      "valid_from": "2024-01-01T00:00:00",
      "valid_to": "2034-01-01T00:00:00",
      "serial_number": "1",
      "issuer": null,
      "created_at": "2024-01-01T00:00:00"
    }
  ],
  "meta": {
    "page": 1,
    "per_page": 20,
    "total": 5
  }
}
```

### Create CA
```http
POST /api/v2/cas
Authorization: Bearer <token>
Content-Type: application/json
```

**Request:**
```json
{
  "common_name": "My Root CA",
  "is_root": true,
  "key_size": 4096,
  "validity_days": 3650,
  "country": "US",
  "state": "California",
  "locality": "San Francisco",
  "organization": "My Company",
  "organizational_unit": "IT"
}
```

### Get CA Details
```http
GET /api/v2/cas/{ca_id}
Authorization: Bearer <token>
```

### Update CA
```http
PATCH /api/v2/cas/{ca_id}
Authorization: Bearer <token>
```

### Delete CA
```http
DELETE /api/v2/cas/{ca_id}
Authorization: Bearer <token>
```

### Get CA Tree
```http
GET /api/v2/cas/tree
Authorization: Bearer <token>
```

**Response:**
```json
{
  "success": true,
  "data": {
    "roots": [
      {
        "id": 1,
        "common_name": "Root CA",
        "children": [
          {
            "id": 2,
            "common_name": "Intermediate CA",
            "children": []
          }
        ]
      }
    ],
    "orphans": []
  }
}
```

---

## Certificates

### List Certificates
```http
GET /api/v2/certificates
Authorization: Bearer <token>
```

**Query Parameters:**
- `page` (int): Page number
- `per_page` (int): Items per page
- `ca_id` (int): Filter by CA
- `status` (string): `valid`, `expired`, `revoked`

### Create Certificate
```http
POST /api/v2/certificates
Authorization: Bearer <token>
```

**Request:**
```json
{
  "ca_id": 1,
  "common_name": "server.example.com",
  "cert_type": "server",
  "validity_days": 365,
  "san_dns": ["www.example.com", "api.example.com"],
  "san_ip": ["192.168.1.100"],
  "key_size": 2048
}
```

### Get Certificate
```http
GET /api/v2/certificates/{cert_id}
Authorization: Bearer <token>
```

### Revoke Certificate
```http
POST /api/v2/certificates/{cert_id}/revoke
Authorization: Bearer <token>
```

**Request:**
```json
{
  "reason": "keyCompromise"
}
```

### Download Certificate
```http
GET /api/v2/certificates/{cert_id}/download
Authorization: Bearer <token>
```

**Query Parameters:**
- `format` (string): `pem`, `der`, `p12`, `bundle`

---

## Certificate Signing Requests

### List CSRs
```http
GET /api/v2/csrs
Authorization: Bearer <token>
```

### Create CSR
```http
POST /api/v2/csrs
Authorization: Bearer <token>
```

### Get CSR
```http
GET /api/v2/csrs/{csr_id}
Authorization: Bearer <token>
```

### Sign CSR
```http
POST /api/v2/csrs/{csr_id}/sign
Authorization: Bearer <token>
```

**Request:**
```json
{
  "ca_id": 1,
  "validity_days": 365
}
```

---

## Certificate Revocation Lists

### List CRLs
```http
GET /api/v2/crl
Authorization: Bearer <token>
```

### Get CRL for CA
```http
GET /api/v2/crl/{ca_id}
Authorization: Bearer <token>
```

### Regenerate CRL
```http
POST /api/v2/crl/{ca_id}/regenerate
Authorization: Bearer <token>
```

### Download CRL
```http
GET /api/v2/crl/{ca_id}/download
Authorization: Bearer <token>
```

**Query Parameters:**
- `format` (string): `pem` or `der`

---

## ACME

### Get ACME Settings
```http
GET /api/v2/acme/settings
Authorization: Bearer <token>
```

**Response:**
```json
{
  "success": true,
  "data": {
    "enabled": true,
    "issuing_ca_id": "ca-abc123",
    "issuing_ca_name": "ACME Issuing CA",
    "provider": "Built-in ACME Server",
    "contact_email": "admin@ucm.local"
  }
}
```

### Update ACME Settings
```http
PATCH /api/v2/acme/settings
Authorization: Bearer <token>
```

**Request:**
```json
{
  "enabled": true,
  "issuing_ca_id": "ca-abc123"
}
```

### Get ACME Statistics
```http
GET /api/v2/acme/stats
Authorization: Bearer <token>
```

### List ACME Accounts
```http
GET /api/v2/acme/accounts
Authorization: Bearer <token>
```

### List ACME Orders
```http
GET /api/v2/acme/orders
Authorization: Bearer <token>
```

**Query Parameters:**
- `status` (string): `pending`, `valid`, `invalid`

### ACME Directory Endpoints

**Internal ACME Server:**
```
GET /acme/directory
```

**Let's Encrypt Proxy:**
```
GET /acme/proxy/directory
```

---

## SCEP

### Get SCEP Configuration
```http
GET /api/v2/scep/config
Authorization: Bearer <token>
```

### Update SCEP Configuration
```http
PATCH /api/v2/scep/config
Authorization: Bearer <token>
```

### List SCEP Requests
```http
GET /api/v2/scep/requests
Authorization: Bearer <token>
```

### Get SCEP Statistics
```http
GET /api/v2/scep/stats
Authorization: Bearer <token>
```

---

## Templates

### List Templates
```http
GET /api/v2/templates
Authorization: Bearer <token>
```

### Get Template
```http
GET /api/v2/templates/{template_id}
Authorization: Bearer <token>
```

### Delete Template
```http
DELETE /api/v2/templates/{template_id}
Authorization: Bearer <token>
```

---

## TrustStore

### List Trusted Certificates
```http
GET /api/v2/truststore
Authorization: Bearer <token>
```

### Get Trusted Certificate
```http
GET /api/v2/truststore/{cert_id}
Authorization: Bearer <token>
```

### Remove from TrustStore
```http
DELETE /api/v2/truststore/{cert_id}
Authorization: Bearer <token>
```

---

## Users

### List Users
```http
GET /api/v2/users
Authorization: Bearer <token>
```

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "username": "admin",
      "email": "admin@ucm.local",
      "role": "admin",
      "active": true,
      "created_at": "2024-01-01T00:00:00"
    }
  ]
}
```

### Delete User
```http
DELETE /api/v2/users/{user_id}
Authorization: Bearer <token>
```

### Toggle User Status
```http
PATCH /api/v2/users/{user_id}/toggle
Authorization: Bearer <token>
```

---

## Settings

### Get General Settings
```http
GET /api/v2/settings/general
Authorization: Bearer <token>
```

### Update General Settings
```http
PATCH /api/v2/settings/general
Authorization: Bearer <token>
```

**Request:**
```json
{
  "app_name": "My CA Manager",
  "default_validity_days": 365,
  "enable_notifications": true
}
```

### Get All Settings (25+ endpoints)
See individual modules:
- `/api/v2/settings/security`
- `/api/v2/settings/smtp`
- `/api/v2/settings/backup`
- `/api/v2/settings/audit`
- And more...

---

## Account

### Get Profile
```http
GET /api/v2/account/profile
Authorization: Bearer <token>
```

### List API Keys
```http
GET /api/v2/account/apikeys
Authorization: Bearer <token>
```

### Create API Key
```http
POST /api/v2/account/apikeys
Authorization: Bearer <token>
```

### Delete API Key
```http
DELETE /api/v2/account/apikeys/{key_id}
Authorization: Bearer <token>
```

---

## System

### Database Statistics
```http
GET /api/v2/system/db/stats
Authorization: Bearer <token>
```

### Optimize Database
```http
POST /api/v2/system/db/optimize
Authorization: Bearer <token>
```

### Integrity Check
```http
POST /api/v2/system/db/integrity-check
Authorization: Bearer <token>
```

---

## Response Formats

### Success Response
```json
{
  "success": true,
  "data": { ... },
  "message": "Operation completed successfully"
}
```

### Error Response
```json
{
  "success": false,
  "error": "Error type",
  "message": "Detailed error message"
}
```

### Paginated Response
```json
{
  "success": true,
  "data": [ ... ],
  "meta": {
    "page": 1,
    "per_page": 20,
    "total": 100,
    "pages": 5
  }
}
```

---

## Error Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 409 | Conflict |
| 422 | Validation Error |
| 500 | Internal Server Error |

---

## Rate Limiting

- Default: 100 requests per minute per IP
- Authenticated: 1000 requests per minute per user
- Headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`

---

## Webhooks

UCM supports webhooks for events:
- Certificate issued
- Certificate revoked
- Certificate expiring
- CA created
- User login

Configure at: `/api/v2/settings/webhooks`

---

## Interactive Documentation

**Swagger UI:** `https://your-domain:8443/api/docs`

Try out all endpoints directly from your browser!

---

**Generated:** 2026-01-23  
**Version:** 2.0.0  
**Total Endpoints:** 121
