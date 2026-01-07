# CRL & CDP Distribution Guide

Complete guide to Certificate Revocation Lists (CRL) and Distribution Points (CDP) in UCM.

---

## 📋 What are CRLs?

**Certificate Revocation List (CRL)** is a signed list of revoked certificates published by a Certificate Authority.

### Why CRLs Matter
- ✅ Clients can verify if a certificate has been revoked
- ✅ Standard method for revocation checking (RFC 5280)
- ✅ Public access without authentication
- ✅ Distributed via HTTP for easy access

### RFC 5280 Compliance
UCM implements RFC 5280-compliant CRLs with:
- CRL Number extension (sequential versioning)
- Authority Key Identifier (links to CA)
- Revocation Reason codes
- Next Update time

---

## 🔐 Enabling CDP for a CA

### Step 1: Navigate to CA Details
1. Go to **CAs** page
2. Click on the CA you want to configure
3. Scroll to **"CRL Distribution Points"** section

### Step 2: Enable CDP
1. Toggle **"Enable CDP"** to ON
2. The CDP URL template field appears

### Step 3: Configure CDP URL Template

Enter the template URL where CRLs will be published:
```
https://your-server:8443/cdp/{ca_refid}/crl.pem
```

**Template Variables**:
- `{ca_refid}` - Automatically replaced with CA's reference ID
- Example: `{ca_refid}` = `a1b2c3d4` → URL becomes `https://your-server:8443/cdp/a1b2c3d4/crl.pem`

**Multiple URLs** (optional):
```
https://primary-server:8443/cdp/{ca_refid}/crl.pem
http://backup-server/crl/{ca_refid}.crl
```

### Step 4: Save Configuration
1. Click **"Save Configuration"**
2. CDP is now enabled for this CA
3. All future certificates will include CDP extension

---

## 📤 CRL Distribution Endpoints

UCM provides **4 public endpoints** per CA (no authentication required):

### 1. PEM Format (Text)
```bash
GET https://your-server:8443/cdp/{ca_refid}/crl.pem
```
- Content-Type: `application/x-pem-file`
- Base64-encoded DER CRL
- Readable in text editor
- Standard format for most applications

### 2. DER Format (Binary)
```bash
GET https://your-server:8443/cdp/{ca_refid}/crl.der
```
- Content-Type: `application/pkix-crl`
- Binary DER-encoded CRL
- Smaller file size
- Used by some Windows applications

### 3. Generic CRL Extension
```bash
GET https://your-server:8443/cdp/{ca_refid}/crl.crl
```
- Alias for PEM format
- Provides `.crl` file extension for compatibility

### 4. JSON Metadata
```bash
GET https://your-server:8443/cdp/{ca_refid}/info
```
- Returns CRL metadata in JSON format
- No authentication required
- Includes:
  - CRL version and status
  - Last update / Next update times
  - Number of revoked certificates
  - Issuer information
  - Download URLs

**Example Response**:
```json
{
  "ca_name": "Intermediate CA",
  "ca_refid": "a1b2c3d4",
  "crl_number": 42,
  "last_update": "2026-01-07T14:30:00Z",
  "next_update": "2026-01-12T14:30:00Z",
  "revoked_count": 3,
  "status": "up-to-date",
  "download_urls": {
    "pem": "https://your-server:8443/cdp/a1b2c3d4/crl.pem",
    "der": "https://your-server:8443/cdp/a1b2c3d4/crl.der"
  }
}
```

---

## 🔄 CRL Generation

### Automatic Generation

CRLs are **automatically generated** when:
1. ✅ A certificate is revoked
2. ✅ CRL "Next Update" time is reached (7 days)
3. ✅ Manual regeneration is triggered

### Manual Generation

#### Method 1: From CRL Management Page
1. Go to **CRL Management** (sidebar)
2. Find the CA in the table
3. Click **"Generate CRL"** button
4. CRL is regenerated immediately

#### Method 2: From CA Details Page
1. Go to CA Details
2. Scroll to CDP section
3. Click **"Generate CRL"** button

#### Method 3: Via API
```bash
curl -X POST https://your-server:8443/api/v1/crl/{ca_id}/generate \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

## 📊 CRL Management Page

Access: **Sidebar → CRL Management**

### Features

**Table Columns**:
- **CA Name** - Certificate Authority name
- **CDP Status** - Enabled/Disabled badge
- **CRL Status** - Up-to-date/Expiring Soon/Stale/Never Generated
- **Revoked Certificates** - Count of revoked certs
- **Last Update** - When CRL was last generated
- **Actions** - Download PEM, Download DER, Generate

**Status Badges**:
- 🟢 **Up-to-date** - CRL is fresh, valid until Next Update
- 🟡 **Expiring Soon** - Less than 24 hours until Next Update
- 🔴 **Stale** - Next Update time has passed
- ⚪ **Never Generated** - No CRL created yet

**Bulk Actions**:
- **Refresh All** - Regenerate CRLs for all CAs with CDP enabled

---

## 🔍 Viewing CRL Information

### Public CRL Info Page
**URL**: `https://your-server:8443/cdp/{ca_refid}/info`
- No authentication required
- Public access for revocation checking
- JSON format

### Integrated CRL Info Page (Authenticated)
**URL**: `https://your-server:8443/crl/info/{ca_refid}`
- Requires authentication
- Full CRL metadata with administrative details
- Revoked certificates list with reasons
- Download links
- Generation history

**Access**:
1. Go to CA Details page
2. Click **"View CRL Info"** in CDP section

---

## 📜 CRL Contents

### What's in a CRL?

```
Certificate Revocation List (CRL):
    Version: 2 (0x1)
    Signature Algorithm: ecdsa-with-SHA256
    Issuer: CN=Intermediate CA, O=Company, C=US
    Last Update: Jan  5 14:30:00 2026 GMT
    Next Update: Jan 12 14:30:00 2026 GMT
    CRL extensions:
        X509v3 CRL Number: 42
        X509v3 Authority Key Identifier:
            keyid:AB:CD:EF:12:34:56:78:90:...

Revoked Certificates:
    Serial Number: 1A2B3C4D5E6F7890
        Revocation Date: Jan  4 10:15:30 2026 GMT
        CRL entry extensions:
            X509v3 CRL Reason Code: Key Compromise
    Serial Number: 9876543210ABCDEF
        Revocation Date: Jan  5 09:22:11 2026 GMT
        CRL entry extensions:
            X509v3 CRL Reason Code: Superseded
```

### Extensions Included

**CRL Extensions** (apply to entire CRL):
- **CRL Number** - Sequential version number (auto-increment)
- **Authority Key Identifier** - Links CRL to issuing CA
- **Issuing Distribution Point** (optional) - Scope of this CRL

**Entry Extensions** (per revoked certificate):
- **Revocation Reason** - Why certificate was revoked
  - Key Compromise
  - CA Compromise
  - Affiliation Changed
  - Superseded
  - Cessation of Operation
  - Certificate Hold
  - Privilege Withdrawn
  - AA Compromise

---

## 🛠️ Testing CRL Distribution

### Test 1: Download CRL
```bash
# PEM format
curl -k https://your-server:8443/cdp/{ca_refid}/crl.pem -o crl.pem

# DER format
curl -k https://your-server:8443/cdp/{ca_refid}/crl.der -o crl.der

# Info (JSON)
curl -k https://your-server:8443/cdp/{ca_refid}/info | jq
```

### Test 2: Verify CRL Signature
```bash
# Extract CA certificate
openssl x509 -in ca.pem -out ca.crt

# Verify CRL was signed by CA
openssl crl -in crl.pem -CAfile ca.crt -noout
# Output: "verify OK" if valid
```

### Test 3: View CRL Contents
```bash
# Human-readable format
openssl crl -in crl.pem -text -noout

# Check revoked certificates
openssl crl -in crl.pem -text -noout | grep -A5 "Serial Number"
```

### Test 4: Check Certificate for CDP Extension
```bash
# View certificate
openssl x509 -in certificate.pem -text -noout | grep -A3 "CRL Distribution"

# Should show:
#   X509v3 CRL Distribution Points:
#       Full Name:
#           URI:https://your-server:8443/cdp/a1b2c3d4/crl.pem
```

---

## 📊 Best Practices

### CRL Lifetime
- **Next Update**: 7 days (UCM default)
- **Rationale**: Balance between freshness and load
- **Recommendation**: 
  - High-security: 24 hours
  - Standard: 7 days ✨
  - Low-risk: 30 days

### CDP URL Configuration
1. ✅ Use HTTPS for security (or HTTP if firewall-protected)
2. ✅ Ensure URL is publicly accessible
3. ✅ Test URL from external network
4. ✅ Use reliable hostname (not IP address)
5. ✅ Consider CDN for high-traffic scenarios

### CRL Regeneration
- ✅ Automatic regeneration on revocation (recommended)
- ✅ Manual regeneration for immediate updates
- ✅ Scheduled regeneration for predictable updates

### Monitoring
1. ✅ Check CRL status regularly (CRL Management page)
2. ✅ Monitor for "Stale" CRLs
3. ✅ Verify public endpoints are accessible
4. ✅ Set up alerts for CRL generation failures

---

## 🔍 Troubleshooting

### CRL Shows "Never Generated"
- ✅ Click "Generate CRL" manually
- ✅ Verify CDP is enabled
- ✅ Check logs: `journalctl -u ucm -n 100`

### CRL Shows "Stale"
- ✅ Click "Generate CRL" to force regeneration
- ✅ Check if auto-generation is working (revoke test cert)
- ✅ Verify database connectivity

### CDP URL Not Accessible
- ✅ Verify firewall allows port 8443
- ✅ Test locally: `curl -k https://localhost:8443/cdp/{ca_refid}/crl.pem`
- ✅ Check DNS resolution
- ✅ Verify HTTPS certificate is valid (or use `-k` for testing)

### Certificate Doesn't Include CDP Extension
- ✅ CDP must be enabled **before** certificate issuance
- ✅ Existing certificates don't get CDP extension (reissue required)
- ✅ Verify in certificate: `openssl x509 -in cert.pem -text -noout | grep CRL`

### CRL Signature Verification Fails
- ✅ Ensure using correct CA certificate for verification
- ✅ Check CA is not revoked
- ✅ Verify CRL was generated by the right CA

---

## 📚 Related Pages

- [CA Management](CA-Management)
- [Certificate Operations](Certificate-Operations)
- [OCSP Responder](OCSP-Responder)
- [API Reference - CRL Endpoints](API-Reference#crl-endpoints)

---

**Last Updated**: 2026-01-07
