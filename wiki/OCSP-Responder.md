# OCSP Responder

**Version:** 1.8.2  
**Status:** ✅ Production Ready  
**RFC:** [RFC 6960](https://datatracker.ietf.org/doc/html/rfc6960)

---

## Overview

**Online Certificate Status Protocol (OCSP)** provides real-time certificate revocation status. UCM includes a built-in OCSP responder for instant certificate validation.

### What is OCSP?

OCSP is a faster alternative to CRL:
- **Real-time**: Check certificate status instantly
- **Lightweight**: Query single certificate, not entire list
- **Efficient**: Less bandwidth than downloading CRLs

---

## Features

### ✅ RFC 6960 Compliant
- OCSP request/response handling
- Certificate status: good, revoked, unknown
- Revocation reason codes
- Nonce support (replay protection)

### 🔐 Security
- OCSP responses signed by CA
- Optional nonce validation
- SHA-256 signing (configurable)

---

## Configuration

### Enable OCSP

1. **Navigate to CA Settings**
   - Select your CA
   - Go to "OCSP Configuration" tab

2. **Enable OCSP Responder**
   ```
   ☑ Enable OCSP Responder
   OCSP URL: http://ocsp.example.com/ocsp
   ```

3. **Configure Options**
   - **Response Validity**: 7 days (how long responses are cached)
   - **Nonce Required**: Optional (replay protection)
   - **Signing Algorithm**: SHA256 (recommended)

### OCSP URL

```
http://ocsp.example.com/ocsp/{ca_id}
```

**Important:** OCSP typically uses HTTP (not HTTPS) for performance and to avoid circular dependencies.

---

## Usage

### Test with OpenSSL

```bash
# Get certificate to check
CERT=server.pem

# Get issuer (CA) certificate  
ISSUER=ca.pem

# Check OCSP status
openssl ocsp \
  -issuer $ISSUER \
  -cert $CERT \
  -url http://ocsp.example.com/ocsp/1 \
  -resp_text

# Output:
# Response verify OK
# server.pem: good
#   This Update: Jan 10 12:00:00 2026 GMT
#   Next Update: Jan 17 12:00:00 2026 GMT
```

### Test with curl

```bash
# Build OCSP request
openssl ocsp -issuer ca.pem -cert server.pem -reqout request.der

# Send to OCSP responder
curl -X POST \
  -H "Content-Type: application/ocsp-request" \
  --data-binary @request.der \
  http://ocsp.example.com/ocsp/1 \
  -o response.der

# Parse response
openssl ocsp -respin response.der -resp_text
```

---

## Certificate Configuration

### Add OCSP URL to Certificates

When creating certificates, include OCSP URL:

**Via UI:**
1. Create/Edit Certificate
2. Extensions tab
3. Authority Information Access
   ```
   OCSP - URI: http://ocsp.example.com/ocsp/1
   ```

**Via Template:**
```json
{
  "extensions": {
    "authority_info_access": {
      "ocsp": ["http://ocsp.example.com/ocsp/1"]
    }
  }
}
```

### Verify OCSP URL in Certificate

```bash
openssl x509 -in cert.pem -text -noout | grep -A2 "Authority Information Access"

# Output:
# Authority Information Access:
#     OCSP - URI:http://ocsp.example.com/ocsp/1
```

---

## Response Statuses

### Good

Certificate is valid and not revoked:
```
Status: good
This Update: Jan 10 12:00:00 2026 GMT
Next Update: Jan 17 12:00:00 2026 GMT
```

### Revoked

Certificate has been revoked:
```
Status: revoked
Revocation Time: Jan 5 10:30:00 2026 GMT
Revocation Reason: keyCompromise
This Update: Jan 10 12:00:00 2026 GMT
```

### Unknown

OCSP responder doesn't know about certificate:
```
Status: unknown
This Update: Jan 10 12:00:00 2026 GMT
```

---

## Browser Integration

Modern browsers automatically check OCSP if URL is in certificate.

### Chrome

1. **Settings → Privacy and security → Security**
2. **Advanced → Manage certificates**
3. Chrome checks OCSP automatically
4. View in DevTools → Security tab

### Firefox

1. **Settings → Privacy & Security**
2. **Certificates → Query OCSP responder servers**
3. ☑ to confirm current certificate validity

### Safari

1. **Preferences → Privacy → Manage Website Data**
2. Safari checks OCSP by default
3. Uses soft-fail (if OCSP unreachable, allows connection)

---

## Monitoring

### OCSP Statistics

Dashboard shows:
- Total OCSP requests (last 24h/7d/30d)
- Response distribution (good/revoked/unknown)
- Average response time
- Error rate

### Logs

View OCSP activity:
```bash
sudo journalctl -u ucm | grep OCSP
```

Shows:
- Incoming requests (certificate serial, IP)
- Response status sent
- Errors (invalid requests, signing failures)

---

## Performance

### Response Caching

UCM caches OCSP responses:
- **Duration**: Configurable (default 7 days)
- **Invalidation**: On certificate revocation
- **Benefits**: Faster responses, reduced load

### High Availability

For production:
1. **Multiple OCSP URLs**: List multiple in certificate
   ```
   OCSP - URI:http://ocsp1.example.com/ocsp/1
   OCSP - URI:http://ocsp2.example.com/ocsp/1
   ```

2. **Load Balancer**: Distribute OCSP traffic
3. **Geographic Distribution**: OCSP servers in different regions

---

## Troubleshooting

### OCSP Request Fails

**Check connectivity:**
```bash
curl -I http://ocsp.example.com/ocsp/1
# Should return: HTTP/1.1 200 OK
```

**Check certificate has OCSP URL:**
```bash
openssl x509 -in cert.pem -text -noout | grep OCSP
```

**Test with verbose OpenSSL:**
```bash
openssl ocsp -issuer ca.pem -cert cert.pem \
  -url http://ocsp.example.com/ocsp/1 \
  -resp_text -VAfile ca.pem
```

### "Unauthorized" Response

```
OCSP response: unsuccessful (6)
Response status: unauthorized
```

**Causes:**
- OCSP responder not configured for this CA
- Invalid CA ID in URL
- OCSP disabled for CA

**Fix:**
- Enable OCSP in CA settings
- Verify correct CA ID in URL

### "Malformed Request"

```
OCSP response: unsuccessful (1)
Response status: malformedRequest
```

**Causes:**
- Invalid OCSP request format
- Corrupted certificate data
- Wrong content-type header

**Fix:**
- Verify request generation
- Use OpenSSL to test
- Check Content-Type: application/ocsp-request

---

## Security Considerations

### HTTP vs HTTPS

**OCSP uses HTTP because:**
- Certificate validation can't depend on valid certificates (circular dependency)
- Responses are cryptographically signed (integrity protected)
- Performance (no TLS handshake)

### Nonce Protection

Enable nonces to prevent replay attacks:
```
☑ Require Nonce
```

Request includes random nonce, response echoes it back.

### Privacy

OCSP reveals which certificates you're checking:
- **OCSP Stapling** (TLS extension) improves privacy
- Server fetches OCSP response, staples to TLS handshake
- Client doesn't contact OCSP directly

---

## Integration Examples

### Nginx with OCSP Stapling

```nginx
server {
    listen 443 ssl;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    ssl_trusted_certificate /path/to/ca.pem;
    
    # Enable OCSP stapling
    ssl_stapling on;
    ssl_stapling_verify on;
    ssl_stapling_responder http://ocsp.example.com/ocsp/1;
}
```

### Apache with OCSP Stapling

```apache
SSLUseStapling on
SSLStaplingCache shmcb:/tmp/stapling_cache(128000)
SSLStaplingResponderTimeout 5
SSLStaplingReturnResponderErrors off
```

### Python Script

```python
from cryptography.x509 import ocsp
from cryptography import x509
from cryptography.hazmat.backends import default_backend
import requests

# Load certificates
cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
issuer = x509.load_pem_x509_certificate(ca_pem, default_backend())

# Build OCSP request
builder = ocsp.OCSPRequestBuilder()
builder = builder.add_certificate(cert, issuer, hashes.SHA256())
req = builder.build()

# Send to OCSP responder
response = requests.post(
    'http://ocsp.example.com/ocsp/1',
    data=req.public_bytes(serialization.Encoding.DER),
    headers={'Content-Type': 'application/ocsp-request'}
)

# Parse response
ocsp_response = ocsp.load_der_ocsp_response(response.content)
print(f"Certificate status: {ocsp_response.certificate_status}")
```

---

## Related Documentation

- [CRL & CDP](CRL-CDP) - Alternative revocation method
- [Certificate Operations](Certificate-Operations) - Certificate management
- [CA Management](CA-Management) - Configure OCSP per CA

---

## Standards Compliance

- ✅ **RFC 6960** - OCSP
- ✅ **RFC 5019** - Lightweight OCSP Profile
- ✅ **RFC 6066** - TLS Extensions (OCSP Stapling)

---

**Need Help?** See [Troubleshooting](Troubleshooting) or [GitHub Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)
