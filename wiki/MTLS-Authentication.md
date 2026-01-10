# mTLS Authentication

**Version:** 1.8.2  
**Status:** ✅ Production Ready

---

## Overview

**Mutual TLS (mTLS)** enables client certificate authentication. Users present a certificate instead of (or in addition to) passwords. UCM supports both native Gunicorn mTLS and reverse proxy modes.

### What is mTLS?

Traditional TLS (HTTPS) authenticates the server to the client. **Mutual TLS** adds client authentication:
- Server authenticates to client (normal HTTPS)
- Client authenticates to server (certificate)
- Both parties verified

---

## Features

### ✅ Hybrid Deployment Support
- **Native Mode**: Gunicorn handles mTLS directly
- **Reverse Proxy**: Nginx/Apache terminates mTLS
- **Auto-Detection**: UCM detects certificate source
- **Zero Configuration**: Works with both modes

### 🔐 Security Benefits
- Stronger than passwords
- Phishing-resistant
- Non-repudiation
- Automated authentication

---

## Configuration

### Option 1: Native Gunicorn mTLS

**Enable in** `.env`:
```bash
MTLS_ENABLED=true
MTLS_CA_CERT=/opt/ucm/backend/data/ca/ca_cert.pem
MTLS_VERIFY_MODE=required  # or optional
```

**Restart UCM:**
```bash
sudo systemctl restart ucm
```

### Option 2: Reverse Proxy (Nginx)

**Nginx configuration:**
```nginx
server {
    listen 443 ssl;
    server_name ucm.example.com;
    
    ssl_certificate /path/to/server.crt;
    ssl_certificate_key /path/to/server.key;
    
    # Client certificate authentication
    ssl_client_certificate /path/to/ca.pem;
    ssl_verify_client optional;  # or on
    ssl_verify_depth 2;
    
    location / {
        proxy_pass https://localhost:8443;
        
        # Pass client cert info to UCM
        proxy_set_header X-SSL-Client-Cert $ssl_client_escaped_cert;
        proxy_set_header X-SSL-Client-Verify $ssl_client_verify;
        proxy_set_header X-SSL-Client-S-DN $ssl_client_s_dn;
    }
}
```

**UCM** `.env`:
```bash
MTLS_ENABLED=true
MTLS_MODE=proxy  # tells UCM to read headers
MTLS_VERIFY_MODE=optional
```

---

## User Certificate Creation

### Via UCM Web UI

1. **Navigate to Certificates**
2. **Create New Certificate**
   - **Template**: User Authentication
   - **Subject CN**: username
   - **Key Usage**: Digital Signature
   - **EKU**: Client Authentication
3. **Download PKCS#12**
   - Enter export password
   - Save `.p12` file

### Via API

```bash
curl -X POST https://ucm.example.com:8443/api/v1/certificates \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "common_name": "john.doe",
    "key_usage": ["digital_signature"],
    "extended_key_usage": ["client_auth"],
    "validity_days": 365
  }'
```

---

## Client Installation

### Windows

1. **Double-click `.p12` file**
2. **Certificate Import Wizard**:
   - Store Location: Current User
   - Enter password
   - Place in Personal store
3. **Verify**: certmgr.msc → Personal → Certificates

### macOS

1. **Double-click `.p12` file**
2. **Keychain Access opens**
3. **Enter password**
4. **Certificate added to login keychain**

### Linux

```bash
# Convert to PEM
openssl pkcs12 -in cert.p12 -out cert.pem -nodes

# Split certificate and key
openssl pkcs12 -in cert.p12 -clcerts -nokeys -out cert.crt
openssl pkcs12 -in cert.p12 -nocerts -nodes -out cert.key

# Use with curl
curl --cert cert.crt --key cert.key https://ucm.example.com:8443
```

### Browser Configuration

**Chrome/Edge:**
- Settings → Privacy and Security → Security
- Manage Certificates → Import
- Browse to `.p12` file

**Firefox:**
- Settings → Privacy & Security
- View Certificates → Your Certificates
- Import → Select `.p12`

---

## Login with mTLS

### Browser

1. **Navigate to UCM URL**
2. **Browser prompts for certificate**
3. **Select your certificate**
4. **Automatically logged in!**

### curl

```bash
curl --cert cert.pem --key key.pem \
  https://ucm.example.com:8443/api/v1/cas
```

### Python

```python
import requests

response = requests.get(
    'https://ucm.example.com:8443/api/v1/cas',
    cert=('cert.pem', 'key.pem'),
    verify='ca.pem'
)
```

---

## Verification Modes

### Required

```bash
MTLS_VERIFY_MODE=required
```
- Client MUST present valid certificate
- No certificate = access denied
- Invalid certificate = access denied

### Optional

```bash
MTLS_VERIFY_MODE=optional
```
- Client MAY present certificate
- Valid cert = auto-login
- No cert = show login page
- Invalid cert = access denied

### Off

```bash
MTLS_ENABLED=false
```
- mTLS disabled
- Standard password/WebAuthn only

---

## Certificate Mapping

UCM maps client certificates to users by:

1. **Subject CN** matches username
2. **Email** matches user email (if in SAN)
3. **Certificate serial** registered to user

### Map Certificate to User

**Via UI:**
1. User → My Account → Security
2. Upload certificate
3. UCM stores serial number

**Via API:**
```bash
POST /api/v1/users/{user_id}/certificates
{
  "certificate": "-----BEGIN CERTIFICATE-----..."
}
```

---

## Troubleshooting

### Certificate Not Accepted

**Check:**
```bash
# Verify certificate is signed by trusted CA
openssl verify -CAfile ca.pem client.pem

# Check expiration
openssl x509 -in client.pem -noout -enddate

# View certificate details
openssl x509 -in client.pem -text -noout
```

### Browser Doesn't Prompt

**Possible causes:**
1. Certificate not imported
2. Wrong certificate store (use "Personal" not "Trusted Root")
3. Certificate expired
4. Browser already cached "no cert" choice

**Fix:** Clear browser SSL state, restart browser.

### "Unknown CA" Error

```bash
# UCM doesn't trust issuing CA
# Add CA to UCM:
1. System Settings → Trusted CAs
2. Upload CA certificate
3. Enable "Trust for client authentication"
```

### Nginx Passes Wrong Headers

```nginx
# Ensure these are set:
proxy_set_header X-SSL-Client-Cert $ssl_client_escaped_cert;
proxy_set_header X-SSL-Client-Verify $ssl_client_verify;
proxy_set_header X-SSL-Client-S-DN $ssl_client_s_dn;

# Debug: Check what nginx receives
location /debug {
    return 200 "Verify: $ssl_client_verify\nDN: $ssl_client_s_dn\n";
}
```

---

## Security Best Practices

### Certificate Lifecycle

- **Validity**: 1 year maximum
- **Renewal**: Before expiration
- **Revocation**: On user termination/device loss
- **CRL/OCSP**: Enable for real-time revocation checking

### Private Key Protection

- ✅ Store in hardware (TPM, YubiKey PIV)
- ✅ Encrypt PKCS#12 with strong password
- ✅ Never email unencrypted keys
- ❌ Don't store on shared drives

### Access Control

- Use strong certificate policies
- Require PIN for key access
- Monitor certificate usage
- Revoke unused certificates

---

## Integration Examples

### API Access

```bash
# Automated service with certificate
curl --cert service.pem --key service.key \
  https://ucm.example.com:8443/api/v1/certificates/export/123
```

### VPN Integration

Use UCM certificates for VPN authentication:
- OpenVPN `--cert` and `--key`
- WireGuard client certificates
- IPsec certificate authentication

### Container Authentication

```dockerfile
# Docker container with mTLS
FROM alpine
COPY client.pem /etc/ssl/certs/
COPY client.key /etc/ssl/private/
RUN apk add curl
CMD curl --cert /etc/ssl/certs/client.pem \
         --key /etc/ssl/private/client.key \
         https://ucm.example.com:8443/api/v1/health
```

---

## Related Documentation

- [Certificate Operations](Certificate-Operations) - Create certificates
- [CA Management](CA-Management) - Manage trusted CAs
- [User Management](User-Management) - Map certs to users
- [Security](Security) - Best practices

---

**Need Help?** See [Troubleshooting](Troubleshooting) or [GitHub Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)
