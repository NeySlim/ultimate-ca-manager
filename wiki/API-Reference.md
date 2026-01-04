# 🔌 REST API Reference

Complete documentation for the Ultimate CA Manager REST API.

---

## 📋 Table of Contents

1. [Introduction](#introduction)
2. [Authentication](#authentication)
3. [CA Endpoints](#ca-endpoints)
4. [Certificate Endpoints](#certificate-endpoints)
5. [SCEP Endpoints](#scep-endpoints)
6. [Error Codes](#error-codes)
7. [Examples](#examples)

---

## 🎯 Introduction

### Base URL

```
https://<your-server>:8443/api/v1
```

### Format

- **Request**: JSON
- **Response**: JSON
- **Encoding**: UTF-8

### Required Headers

```http
Content-Type: application/json
Authorization: Bearer <token>
```

---

## 🔐 Authentication

### Obtain a Token

**Endpoint**: `POST /api/v1/auth/login`

**Request**:
```json
{
  "username": "admin",
  "password": "your_password"
}
```

**Response**:
```json
{
  "success": true,
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expires_in": 3600,
  "user": {
    "id": 1,
    "username": "admin",
    "role": "admin"
  }
}
```

### Using the Token

```bash
curl -H "Authorization: Bearer eyJhbGc..." \
     https://localhost:8443/api/v1/cas
```

### Refresh the Token

**Endpoint**: `POST /api/v1/auth/refresh`

**Headers**:
```http
Authorization: Bearer <old_token>
```

**Response**:
```json
{
  "token": "eyJhbGc...",
  "expires_in": 3600
}
```

---

## 🏛️ CA Endpoints

### List CAs

**Endpoint**: `GET /api/v1/cas`

**Query Parameters**:
```
?status=active          # active, revoked, all
?type=root             # root, intermediate
?page=1
&limit=20
```

**Response**:
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "common_name": "My Root CA",
      "serial_number": "1A2B3C4D5E6F",
      "type": "root",
      "status": "active",
      "key_type": "RSA",
      "key_size": 4096,
      "not_before": "2026-01-01T00:00:00Z",
      "not_after": "2046-01-01T00:00:00Z",
      "issued_certs": 45,
      "created_at": "2026-01-01T00:00:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 20,
    "total": 3,
    "pages": 1
  }
}
```

### Get a CA

**Endpoint**: `GET /api/v1/cas/{id}`

**Response**:
```json
{
  "success": true,
  "data": {
    "id": 1,
    "common_name": "My Root CA",
    "organization": "Example Inc.",
    "country": "FR",
    "serial_number": "1A2B3C4D5E6F",
    "type": "root",
    "parent_ca_id": null,
    "status": "active",
    "key_type": "RSA",
    "key_size": 4096,
    "hash_algorithm": "SHA384",
    "not_before": "2026-01-01T00:00:00Z",
    "not_after": "2046-01-01T00:00:00Z",
    "subject_dn": "CN=My Root CA,O=Example Inc.,C=FR",
    "issuer_dn": "CN=My Root CA,O=Example Inc.,C=FR",
    "certificate_pem": "-----BEGIN CERTIFICATE-----\n...",
    "crl_url": "http://pki.example.com/crl/1.crl",
    "ocsp_url": "http://ocsp.example.com",
    "issued_certificates": 45,
    "revoked_certificates": 2,
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z"
  }
}
```

### Create a CA

**Endpoint**: `POST /api/v1/cas`

**Request**:
```json
{
  "type": "intermediate",
  "parent_ca_id": 1,
  "common_name": "My Issuing CA",
  "organization": "Example Inc.",
  "organizational_unit": "PKI Services",
  "country": "FR",
  "state": "Ile-de-France",
  "locality": "Paris",
  "key_type": "RSA",
  "key_size": 4096,
  "hash_algorithm": "SHA256",
  "validity_days": 3650,
  "path_length": 0
}
```

**Response**:
```json
{
  "success": true,
  "message": "CA created successfully",
  "data": {
    "id": 2,
    "serial_number": "7F8E9D0C1B2A",
    "certificate_pem": "-----BEGIN CERTIFICATE-----\n..."
  }
}
```

### Export a CA

**Endpoint**: `GET /api/v1/cas/{id}/export`

**Query Parameters**:
```
?format=pem            # pem, der, pkcs12
&include_key=false     # true/false (admin only)
&include_chain=true    # true/false
&password=xxx          # required if include_key=true
```

**Response**:
```json
{
  "success": true,
  "data": {
    "format": "pem",
    "certificate": "-----BEGIN CERTIFICATE-----\n...",
    "chain": "-----BEGIN CERTIFICATE-----\n...",
    "filename": "my-issuing-ca.pem"
  }
}
```

### Revoke a CA

**Endpoint**: `POST /api/v1/cas/{id}/revoke`

**Request**:
```json
{
  "reason": "key_compromise"
}
```

**Reasons**:
- `unspecified`
- `key_compromise`
- `ca_compromise`
- `affiliation_changed`
- `superseded`
- `cessation_of_operation`

**Response**:
```json
{
  "success": true,
  "message": "CA revoked successfully"
}
```

---

## 📜 Certificate Endpoints

### List Certificates

**Endpoint**: `GET /api/v1/certificates`

**Query Parameters**:
```
?status=active              # active, revoked, expired
?type=server               # server, client, code_signing, email
?issuer_id=1
&search=example.com        # CN, serial, subject
&page=1
&limit=20
&sort_by=created_at        # created_at, expiry_date, serial_number
&sort_order=desc           # asc, desc
```

**Response**:
```json
{
  "success": true,
  "data": [
    {
      "id": 123,
      "serial_number": "4F5E6D7C8B9A",
      "common_name": "www.example.com",
      "type": "server",
      "status": "active",
      "issuer_ca_id": 2,
      "issuer_cn": "My Issuing CA",
      "not_before": "2026-01-01T00:00:00Z",
      "not_after": "2027-01-01T00:00:00Z",
      "days_until_expiry": 365,
      "subject_alternative_names": [
        "www.example.com",
        "example.com"
      ],
      "created_at": "2026-01-01T00:00:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 20,
    "total": 150,
    "pages": 8
  }
}
```

### Get a Certificate

**Endpoint**: `GET /api/v1/certificates/{id}`

**Response**:
```json
{
  "success": true,
  "data": {
    "id": 123,
    "serial_number": "4F5E6D7C8B9A",
    "common_name": "www.example.com",
    "organization": "Example Inc.",
    "type": "server",
    "status": "active",
    "issuer_ca_id": 2,
    "key_type": "RSA",
    "key_size": 2048,
    "hash_algorithm": "SHA256",
    "not_before": "2026-01-01T00:00:00Z",
    "not_after": "2027-01-01T00:00:00Z",
    "subject_dn": "CN=www.example.com,O=Example Inc.,C=FR",
    "issuer_dn": "CN=My Issuing CA,O=Example Inc.,C=FR",
    "subject_alternative_names": [
      "DNS:www.example.com",
      "DNS:example.com"
    ],
    "key_usage": ["digitalSignature", "keyEncipherment"],
    "extended_key_usage": ["serverAuth"],
    "certificate_pem": "-----BEGIN CERTIFICATE-----\n...",
    "revocation_date": null,
    "revocation_reason": null,
    "created_at": "2026-01-01T00:00:00Z"
  }
}
```

### Issue a Certificate

**Endpoint**: `POST /api/v1/certificates`

**Request**:
```json
{
  "issuer_ca_id": 2,
  "certificate_type": "server",
  "common_name": "www.example.com",
  "organization": "Example Inc.",
  "organizational_unit": "IT",
  "country": "FR",
  "state": "Ile-de-France",
  "locality": "Paris",
  "email": null,
  "subject_alternative_names": [
    "DNS:www.example.com",
    "DNS:example.com",
    "IP:192.168.1.100"
  ],
  "key_type": "RSA",
  "key_size": 2048,
  "hash_algorithm": "SHA256",
  "validity_days": 365,
  "key_usage": ["digitalSignature", "keyEncipherment"],
  "extended_key_usage": ["serverAuth"]
}
```

**Response**:
```json
{
  "success": true,
  "message": "Certificate issued successfully",
  "data": {
    "id": 124,
    "serial_number": "9A8B7C6D5E4F",
    "certificate_pem": "-----BEGIN CERTIFICATE-----\n...",
    "private_key_pem": "-----BEGIN PRIVATE KEY-----\n..."
  }
}
```

### Sign a CSR

**Endpoint**: `POST /api/v1/certificates/sign-csr`

**Request**:
```json
{
  "issuer_ca_id": 2,
  "csr_pem": "-----BEGIN CERTIFICATE REQUEST-----\n...",
  "certificate_type": "server",
  "validity_days": 365,
  "subject_alternative_names": [
    "DNS:www.example.com"
  ]
}
```

**Response**:
```json
{
  "success": true,
  "message": "CSR signed successfully",
  "data": {
    "id": 125,
    "serial_number": "3E4F5A6B7C8D",
    "certificate_pem": "-----BEGIN CERTIFICATE-----\n..."
  }
}
```

### Export a Certificate

**Endpoint**: `GET /api/v1/certificates/{id}/export`

**Query Parameters**:
```
?format=pkcs12         # pem, der, pkcs12
&include_chain=true    # true/false
&password=xxx          # required for pkcs12
```

### Renew a Certificate

**Endpoint**: `POST /api/v1/certificates/{id}/renew`

**Request**:
```json
{
  "validity_days": 365,
  "reuse_key": false
}
```

### Revoke a Certificate

**Endpoint**: `POST /api/v1/certificates/{id}/revoke`

**Request**:
```json
{
  "reason": "key_compromise"
}
```

---

## 🔄 SCEP Endpoints

### List SCEP Endpoints

**Endpoint**: `GET /api/v1/scep/endpoints`

### Create a SCEP Endpoint

**Endpoint**: `POST /api/v1/scep/endpoints`

**Request**:
```json
{
  "name": "Mobile Devices",
  "description": "SCEP for iOS/Android",
  "issuer_ca_id": 2,
  "challenge_type": "dynamic",
  "challenge_password": "auto",
  "certificate_type": "client",
  "validity_days": 365,
  "auto_approval": true,
  "auto_renewal": true,
  "renewal_window_days": 30
}
```

### Generate SCEP Challenge

**Endpoint**: `POST /api/v1/scep/endpoints/{id}/generate-challenge`

**Response**:
```json
{
  "success": true,
  "data": {
    "challenge": "A1B2C3D4E5F6",
    "scep_url": "https://pki.example.com:8443/scep/mobile-devices?challenge=A1B2C3D4E5F6",
    "expires_at": "2026-01-02T00:00:00Z"
  }
}
```

---

## ❌ Error Codes

| Code | Message | Description |
|------|---------|-------------|
| 200 | OK | Success |
| 201 | Created | Resource created |
| 400 | Bad Request | Invalid parameters |
| 401 | Unauthorized | Missing/invalid token |
| 403 | Forbidden | Permission denied |
| 404 | Not Found | Resource not found |
| 409 | Conflict | Conflict (e.g., serial exists) |
| 422 | Unprocessable Entity | Validation failed |
| 500 | Internal Server Error | Server error |

**Error Format**:
```json
{
  "success": false,
  "error": {
    "code": "INVALID_PARAMETER",
    "message": "Invalid key size for ECDSA",
    "details": {
      "field": "key_size",
      "provided": "2048",
      "allowed": ["256", "384", "521"]
    }
  }
}
```

---

## 💡 Examples

### Python

```python
import requests

# Login
response = requests.post(
    'https://localhost:8443/api/v1/auth/login',
    json={'username': 'admin', 'password': 'admin'},
    verify=False  # Only for dev/test
)
token = response.json()['token']

# Headers
headers = {'Authorization': f'Bearer {token}'}

# List CAs
cas = requests.get(
    'https://localhost:8443/api/v1/cas',
    headers=headers,
    verify=False
).json()

# Issue certificate
cert = requests.post(
    'https://localhost:8443/api/v1/certificates',
    headers=headers,
    json={
        'issuer_ca_id': 2,
        'certificate_type': 'server',
        'common_name': 'api.example.com',
        'key_type': 'RSA',
        'key_size': 2048,
        'validity_days': 365
    },
    verify=False
).json()

print(f"Certificate serial: {cert['data']['serial_number']}")
```

### Bash/cURL

```bash
#!/bin/bash

BASE_URL="https://localhost:8443/api/v1"

# Login
TOKEN=$(curl -sk -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' \
  | jq -r '.token')

# List certificates expiring in 30 days
curl -sk "$BASE_URL/certificates?expiring_in=30" \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.data[] | {cn: .common_name, expiry: .not_after}'

# Revoke certificate
curl -sk -X POST "$BASE_URL/certificates/123/revoke" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason":"key_compromise"}' \
  | jq '.'
```

### JavaScript/Node.js

```javascript
const axios = require('axios');

const API = axios.create({
  baseURL: 'https://localhost:8443/api/v1',
  httpsAgent: new (require('https').Agent)({ rejectUnauthorized: false })
});

async function main() {
  // Login
  const { data: auth } = await API.post('/auth/login', {
    username: 'admin',
    password: 'admin'
  });
  
  API.defaults.headers.common['Authorization'] = `Bearer ${auth.token}`;
  
  // Create certificate
  const { data: cert } = await API.post('/certificates', {
    issuer_ca_id: 2,
    certificate_type: 'server',
    common_name: 'app.example.com',
    key_type: 'ECDSA',
    key_size: 256,
    validity_days: 90
  });
  
  console.log('Certificate created:', cert.data.serial_number);
}

main();
```

---

## 🔗 Resources

- **OpenAPI Spec**: `/api/v1/openapi.json` (coming soon)
- **Postman Collection**: Available in `/docs/postman/`
- **Rate Limiting**: 100 req/min per IP

---

**More info**: [User Manual](User-Manual) | [Troubleshooting](Troubleshooting)
