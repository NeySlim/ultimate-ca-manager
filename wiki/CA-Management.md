# CA Management Guide

Complete guide to managing Certificate Authorities in UCM.

---

## 🔐 Creating a New CA

### Step 1: Navigate to CA Management

1. Login to UCM web interface
2. Click **"CAs"** in the sidebar
3. Click **"+ Create CA"** button

### Step 2: Configure CA Details

#### Distinguished Name (DN)
- **Common Name (CN)** - Required, CA identifier (e.g., "Root CA", "Intermediate CA")
- **Organization (O)** - Your organization name
- **Organizational Unit (OU)** - Department or division
- **Country (C)** - 2-letter country code (e.g., "US", "FR", "DE")
- **State/Province (ST)** - State or province name
- **Locality (L)** - City name

#### Cryptographic Settings
- **Key Type**:
  - `RSA 2048` - Standard, widely compatible
  - `RSA 4096` - Higher security, slower
  - `ECDSA P-256` - Modern, efficient (recommended)
  - `ECDSA P-384` - Higher security
  - `ECDSA P-521` - Maximum security
  
- **Hash Algorithm**:
  - `SHA-256` - Standard (recommended)
  - `SHA-384` - Higher security
  - `SHA-512` - Maximum security

#### Validity Period
- **Validity Days** - How long the CA will be valid (e.g., 3650 = 10 years)
- Recommendation:
  - Root CA: 10-20 years (3650-7300 days)
  - Intermediate CA: 5-10 years (1825-3650 days)

#### CA Type
- **Root CA** - Self-signed, top of the trust chain
- **Intermediate CA** - Signed by another CA (select parent CA)

### Step 3: Create CA

1. Review all settings
2. Click **"Create CA"**
3. CA is generated and stored securely in `/opt/ucm/data/ca/`

---

## 📋 Viewing CA Details

### Access CA Details
1. Go to **CAs** page
2. Click on any CA row or **"View"** button

### Information Available
- **Basic Information**:
  - Common Name, Organization, Country, etc.
  - Status (Active/Revoked)
  - Validity dates (Not Before / Not After)
  
- **Technical Specifications**:
  - Key Type (RSA 2048, ECDSA P-256, etc.)
  - Hash Algorithm (SHA-256, SHA-384, etc.)
  - Serial Number
  - Subject Key Identifier
  
- **Statistics**:
  - Issued Certificates count
  - Revoked Certificates count
  - Active Certificates count
  
- **CRL/CDP Configuration**:
  - CDP Enabled status
  - CDP URL template
  - Last CRL generation time
  - CRL status (Up-to-date, Stale, etc.)

---

## 🔄 CRL Distribution Points (CDP)

### Enable CDP for a CA

1. Go to CA Details page
2. Scroll to **"CRL Distribution Points"** section
3. Toggle **"Enable CDP"** to ON
4. Configure **CDP URL Template**:
   ```
   https://your-server:8443/cdp/{ca_refid}/crl.pem
   ```
   - `{ca_refid}` is automatically replaced with CA's reference ID
   
5. Click **"Save Configuration"**

### CDP Features
- **Public Access** - CRL accessible without authentication
- **Multiple Formats**:
  - `/cdp/{ca_refid}/crl.pem` - PEM format (text)
  - `/cdp/{ca_refid}/crl.der` - DER format (binary)
  - `/cdp/{ca_refid}/crl.crl` - Generic CRL extension
  - `/cdp/{ca_refid}/info` - JSON metadata
  
- **Auto-Generation** - CRL regenerates automatically when certificates are revoked
- **RFC 5280 Compliant** - Standard-compliant CRL format

### View CRL Information
1. In CA Details, click **"View CRL Info"**
2. See:
   - CRL version and status
   - Last update and next update times
   - Number of revoked certificates
   - Issuer information
   - Download links (PEM/DER)

---

## 📤 Exporting a CA

### Export CA Certificate

1. Go to CA Details page
2. Click **"Export"** button
3. Choose format:
   - **PEM** - Text format, Base64 encoded
   - **DER** - Binary format
   - **PKCS#12** - Password-protected bundle (certificate + private key)

### Export Use Cases
- **PEM**: Import into browsers, operating systems, applications
- **DER**: Some Windows applications
- **PKCS#12**: Backup with private key (⚠️ Keep secure!)

---

## 🗑️ Revoking a CA

### When to Revoke
- CA private key compromised
- CA no longer needed
- Organizational change
- Security incident

### How to Revoke
1. Go to CA Details page
2. Click **"Revoke CA"** button
3. Confirm revocation
4. **Effect**: CA status changes to "Revoked", can no longer issue certificates

⚠️ **Warning**: Revocation is irreversible! All certificates issued by this CA should be considered untrusted.

---

## 📊 CA Management Best Practices

### Root CA Security
1. ✅ Store Root CA offline when possible
2. ✅ Use maximum key size (RSA 4096 or ECDSA P-521)
3. ✅ Long validity period (10-20 years)
4. ✅ Only use for signing Intermediate CAs
5. ✅ Backup private key securely (encrypted PKCS#12)

### Intermediate CA Usage
1. ✅ Use for daily certificate issuance
2. ✅ Shorter validity (5-10 years)
3. ✅ Enable CDP for revocation checking
4. ✅ Monitor certificate count and expiration

### Key Type Selection
- **RSA 2048**: Maximum compatibility, good security
- **RSA 4096**: Higher security, slightly slower
- **ECDSA P-256**: Modern standard, fast, smaller certificates ✨ Recommended
- **ECDSA P-384**: Enhanced security
- **ECDSA P-521**: Maximum security

### Hash Algorithm Selection
- **SHA-256**: Standard, recommended for most use cases ✨
- **SHA-384**: Enhanced security
- **SHA-512**: Maximum security (larger signatures)

---

## 🔍 Troubleshooting

### CA Creation Fails
- Check disk space in `/opt/ucm/data/ca/`
- Verify all required DN fields (CN is mandatory)
- Check logs: `journalctl -u ucm -n 100`

### CDP URLs Not Working
- Verify CDP is enabled for the CA
- Check URL template includes `{ca_refid}`
- Ensure firewall allows port 8443
- Test public endpoint: `curl -k https://your-server:8443/cdp/{ca_refid}/crl.pem`

### CRL Status Shows "Stale"
- Click **"Generate CRL"** to force regeneration
- Check last update time
- Verify auto-generation is working (revoke a test certificate)

---

## 📚 Related Pages

- [Certificate Operations](Certificate-Operations)
- [CRL & CDP Distribution](CRL-CDP)
- [Security Best Practices](Security)
- [API Reference - CA Endpoints](API-Reference#ca-endpoints)

---

**Last Updated**: 2026-01-07
