# API Documentation

Ultimate CA Manager v1.8.2 provides a comprehensive REST API for certificate management and automation.

## Overview

**Base URL:**
```
https://ca.example.com/api
```

**Authentication:**
- JWT Bearer tokens
- Token expiration: 1 hour (configurable)
- Refresh token support

**Content Type:**
```
Content-Type: application/json
```

## Authentication

### Login

**Get Access Token:**

```bash
POST /api/auth/login
```

**Request:**
```json
{
  "username": "admin",
  "password": "your-password"
}
```

**Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "expires_in": 3600,
  "user": {
    "id": 1,
    "username": "admin",
    "role": "admin"
  }
}
```

**Example:**
```bash
curl -X POST https://ca.example.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"secret"}'
```

### Refresh Token

**Renew Access Token:**

```bash
POST /api/auth/refresh
```

**Headers:**
```
Authorization: Bearer <refresh_token>
```

**Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "expires_in": 3600
}
```

### Logout

**Invalidate Token:**

```bash
POST /api/auth/logout
```

**Headers:**
```
Authorization: Bearer <access_token>
```

## Certificates

### List Certificates

**Get all certificates:**

```bash
GET /api/certificates
```

**Query Parameters:**
- `status`: Filter by status (valid, expired, revoked)
- `type`: Filter by type (server, client, ca)
- `limit`: Results per page (default: 50)
- `offset`: Pagination offset

**Response:**
```json
{
  "certificates": [
    {
      "id": 1,
      "common_name": "server.example.com",
      "serial_number": "01",
      "type": "server",
      "status": "valid",
      "not_before": "2024-01-01T00:00:00Z",
      "not_after": "2025-01-01T00:00:00Z",
      "issuer": "Example CA",
      "subject_alt_names": ["server.example.com", "www.example.com"],
      "created_at": "2024-01-01T00:00:00Z"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

**Example:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  https://ca.example.com/api/certificates?status=valid&limit=10
```

### Get Certificate

**Get certificate details:**

```bash
GET /api/certificates/{id}
```

**Response:**
```json
{
  "id": 1,
  "common_name": "server.example.com",
  "serial_number": "01",
  "type": "server",
  "status": "valid",
  "not_before": "2024-01-01T00:00:00Z",
  "not_after": "2025-01-01T00:00:00Z",
  "issuer": "Example CA",
  "subject": {
    "CN": "server.example.com",
    "O": "Example Org",
    "C": "US"
  },
  "subject_alt_names": ["server.example.com", "www.example.com"],
  "key_usage": ["digitalSignature", "keyEncipherment"],
  "extended_key_usage": ["serverAuth"],
  "pem": "-----BEGIN CERTIFICATE-----\n...",
  "created_at": "2024-01-01T00:00:00Z",
  "created_by": "admin"
}
```

**Example:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  https://ca.example.com/api/certificates/1
```

### Create Certificate

**Issue new certificate:**

```bash
POST /api/certificates
```

**Request:**
```json
{
  "common_name": "server.example.com",
  "type": "server",
  "validity_days": 365,
  "subject": {
    "O": "Example Org",
    "OU": "IT Department",
    "C": "US",
    "ST": "California",
    "L": "San Francisco"
  },
  "subject_alt_names": [
    "server.example.com",
    "www.example.com",
    "IP:192.168.1.100"
  ],
  "key_type": "rsa",
  "key_size": 4096,
  "key_usage": ["digitalSignature", "keyEncipherment"],
  "extended_key_usage": ["serverAuth", "clientAuth"],
  "ocsp_must_staple": false
}
```

**Response:**
```json
{
  "id": 2,
  "common_name": "server.example.com",
  "serial_number": "02",
  "certificate": "-----BEGIN CERTIFICATE-----\n...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...",
  "chain": "-----BEGIN CERTIFICATE-----\n...",
  "created_at": "2024-01-01T00:00:00Z"
}
```

**Example:**
```bash
curl -X POST https://ca.example.com/api/certificates \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "common_name": "server.example.com",
    "type": "server",
    "validity_days": 365,
    "subject_alt_names": ["server.example.com", "www.example.com"]
  }'
```

### Revoke Certificate

**Revoke a certificate:**

```bash
POST /api/certificates/{id}/revoke
```

**Request:**
```json
{
  "reason": "keyCompromise",
  "reason_text": "Private key was exposed"
}
```

**Revocation Reasons:**
- `unspecified`
- `keyCompromise`
- `cACompromise`
- `affiliationChanged`
- `superseded`
- `cessationOfOperation`
- `certificateHold`

**Response:**
```json
{
  "id": 1,
  "serial_number": "01",
  "status": "revoked",
  "revocation_date": "2024-01-15T00:00:00Z",
  "revocation_reason": "keyCompromise"
}
```

**Example:**
```bash
curl -X POST https://ca.example.com/api/certificates/1/revoke \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "keyCompromise"}'
```

### Download Certificate

**Download certificate files:**

```bash
GET /api/certificates/{id}/download
```

**Query Parameters:**
- `format`: Output format (pem, der, pfx, p12)
- `include_key`: Include private key (true/false)
- `include_chain`: Include CA chain (true/false)
- `password`: Password for PKCS#12 (if format=pfx/p12)

**Example:**
```bash
# Download PEM bundle with key and chain
curl -H "Authorization: Bearer $TOKEN" \
  "https://ca.example.com/api/certificates/1/download?format=pem&include_key=true&include_chain=true" \
  -o cert-bundle.pem

# Download PKCS#12 with password
curl -H "Authorization: Bearer $TOKEN" \
  "https://ca.example.com/api/certificates/1/download?format=p12&password=secret123" \
  -o cert.p12
```

## Certificate Authority

### Get CA Information

**Get CA certificate and details:**

```bash
GET /api/ca
```

**Response:**
```json
{
  "common_name": "Example Root CA",
  "serial_number": "00",
  "not_before": "2024-01-01T00:00:00Z",
  "not_after": "2034-01-01T00:00:00Z",
  "subject": {
    "CN": "Example Root CA",
    "O": "Example Org",
    "C": "US"
  },
  "key_type": "rsa",
  "key_size": 4096,
  "certificate": "-----BEGIN CERTIFICATE-----\n...",
  "chain": "-----BEGIN CERTIFICATE-----\n..."
}
```

### Get CRL

**Download Certificate Revocation List:**

```bash
GET /api/ca/crl
```

**Query Parameters:**
- `format`: Output format (pem, der)

**Example:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  https://ca.example.com/api/ca/crl > ca.crl
```

## ACME Integration

### ACME Account Statistics

**Get ACME account stats:**

```bash
GET /api/acme/stats
```

**Response:**
```json
{
  "total_accounts": 5,
  "total_orders": 23,
  "active_orders": 2,
  "certificates_issued": 21,
  "recent_orders": [
    {
      "id": 1,
      "status": "valid",
      "identifiers": ["example.com"],
      "created": "2024-01-01T00:00:00Z"
    }
  ]
}
```

### List ACME Accounts

**Get all ACME accounts:**

```bash
GET /api/acme/accounts
```

**Response:**
```json
{
  "accounts": [
    {
      "id": 1,
      "kid": "https://ca.example.com/acme/acct/1",
      "status": "valid",
      "contact": ["mailto:admin@example.com"],
      "created_at": "2024-01-01T00:00:00Z",
      "certificates_count": 5
    }
  ]
}
```

## SCEP Integration

### List SCEP Profiles

**Get SCEP enrollment profiles:**

```bash
GET /api/scep/profiles
```

**Response:**
```json
{
  "profiles": [
    {
      "id": 1,
      "name": "ios-devices",
      "challenge": "secret123",
      "validity_days": 365,
      "certificate_type": "client",
      "enabled": true,
      "enrollments_count": 42
    }
  ]
}
```

### Create SCEP Profile

**Create new SCEP enrollment profile:**

```bash
POST /api/scep/profiles
```

**Request:**
```json
{
  "name": "android-devices",
  "challenge": "secret-challenge",
  "validity_days": 365,
  "certificate_type": "client",
  "key_usage": ["digitalSignature"],
  "subject_template": {
    "O": "Example Org",
    "OU": "Mobile Devices"
  }
}
```

## OCSP Status

### OCSP Statistics

**Get OCSP responder stats:**

```bash
GET /api/ocsp/stats
```

**Response:**
```json
{
  "total_queries": 1523,
  "queries_24h": 89,
  "good_responses": 1520,
  "revoked_responses": 3,
  "unknown_responses": 0,
  "average_response_time": "12ms"
}
```

## Users

### List Users (Admin only)

**Get all users:**

```bash
GET /api/users
```

**Response:**
```json
{
  "users": [
    {
      "id": 1,
      "username": "admin",
      "email": "admin@example.com",
      "role": "admin",
      "created_at": "2024-01-01T00:00:00Z",
      "last_login": "2024-01-15T12:00:00Z",
      "webauthn_enabled": true
    }
  ]
}
```

### Create User (Admin only)

**Create new user:**

```bash
POST /api/users
```

**Request:**
```json
{
  "username": "operator",
  "email": "operator@example.com",
  "password": "secure-password",
  "role": "operator"
}
```

## System

### System Health

**Get system status:**

```bash
GET /api/health
```

**Response:**
```json
{
  "status": "healthy",
  "database": "connected",
  "ca_available": true,
  "version": "1.8.2",
  "uptime": 86400,
  "certificates": {
    "total": 45,
    "expiring_30d": 3
  }
}
```

### System Statistics

**Get system stats:**

```bash
GET /api/stats
```

**Response:**
```json
{
  "certificates": {
    "total": 45,
    "valid": 42,
    "expired": 2,
    "revoked": 1,
    "by_type": {
      "server": 20,
      "client": 23,
      "ca": 2
    }
  },
  "acme": {
    "accounts": 5,
    "orders": 23,
    "certificates": 21
  },
  "scep": {
    "profiles": 2,
    "enrollments": 42
  },
  "ocsp": {
    "queries_24h": 89
  }
}
```

## Error Responses

**Standard Error Format:**
```json
{
  "error": "invalid_request",
  "message": "Missing required field: common_name",
  "status_code": 400
}
```

**HTTP Status Codes:**
- `200` - Success
- `201` - Created
- `400` - Bad Request
- `401` - Unauthorized (invalid/missing token)
- `403` - Forbidden (insufficient permissions)
- `404` - Not Found
- `409` - Conflict (duplicate resource)
- `422` - Unprocessable Entity (validation error)
- `500` - Internal Server Error

## Rate Limiting

**Default Limits:**
- Authentication: 5 requests/minute
- API endpoints: 100 requests/hour
- Certificate creation: 10 requests/minute

**Rate Limit Headers:**
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1704067200
```

**Rate Limit Exceeded:**
```json
{
  "error": "rate_limit_exceeded",
  "message": "Too many requests. Try again in 3600 seconds.",
  "status_code": 429,
  "retry_after": 3600
}
```

## Pagination

**Query Parameters:**
- `limit`: Results per page (default: 50, max: 100)
- `offset`: Pagination offset (default: 0)

**Response Headers:**
```
X-Total-Count: 150
X-Page-Limit: 50
X-Page-Offset: 0
Link: <https://ca.example.com/api/certificates?limit=50&offset=50>; rel="next"
```

## Code Examples

### Python

```python
import requests

# Login
response = requests.post(
    'https://ca.example.com/api/auth/login',
    json={'username': 'admin', 'password': 'secret'}
)
token = response.json()['access_token']

# Create certificate
headers = {'Authorization': f'Bearer {token}'}
cert_data = {
    'common_name': 'server.example.com',
    'type': 'server',
    'validity_days': 365,
    'subject_alt_names': ['server.example.com', 'www.example.com']
}
response = requests.post(
    'https://ca.example.com/api/certificates',
    headers=headers,
    json=cert_data
)
certificate = response.json()

# Save certificate
with open('server.crt', 'w') as f:
    f.write(certificate['certificate'])
with open('server.key', 'w') as f:
    f.write(certificate['private_key'])
```

### JavaScript

```javascript
// Login
const response = await fetch('https://ca.example.com/api/auth/login', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({username: 'admin', password: 'secret'})
});
const {access_token} = await response.json();

// Create certificate
const certResponse = await fetch('https://ca.example.com/api/certificates', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${access_token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    common_name: 'server.example.com',
    type: 'server',
    validity_days: 365,
    subject_alt_names: ['server.example.com', 'www.example.com']
  })
});
const certificate = await certResponse.json();
```

### Go

```go
package main

import (
    "bytes"
    "encoding/json"
    "net/http"
)

func main() {
    // Login
    loginData := map[string]string{
        "username": "admin",
        "password": "secret",
    }
    body, _ := json.Marshal(loginData)
    resp, _ := http.Post(
        "https://ca.example.com/api/auth/login",
        "application/json",
        bytes.NewBuffer(body),
    )
    var result map[string]interface{}
    json.NewDecoder(resp.Body).Decode(&result)
    token := result["access_token"].(string)
    
    // Create certificate
    certData := map[string]interface{}{
        "common_name": "server.example.com",
        "type": "server",
        "validity_days": 365,
        "subject_alt_names": []string{"server.example.com", "www.example.com"},
    }
    body, _ = json.Marshal(certData)
    req, _ := http.NewRequest(
        "POST",
        "https://ca.example.com/api/certificates",
        bytes.NewBuffer(body),
    )
    req.Header.Set("Authorization", "Bearer "+token)
    req.Header.Set("Content-Type", "application/json")
    
    client := &http.Client{}
    resp, _ = client.Do(req)
}
```

## See Also

- [ACME Support](ACME-Support.md) - ACME protocol integration
- [SCEP Server](SCEP-Server.md) - SCEP enrollment
- [Security](Security.md) - API security best practices
- [Configuration](Configuration.md) - API configuration options
