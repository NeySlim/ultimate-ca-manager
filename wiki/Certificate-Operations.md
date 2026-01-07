# Certificate Operations Guide

Complete guide to certificate lifecycle management in UCM.

---

## 📜 Creating Certificates

### Method 1: Manual Certificate Creation

#### Step 1: Navigate to Certificates
1. Click **"Certificates"** in sidebar
2. Click **"+ Create Certificate"** button

#### Step 2: Configure Certificate

**Distinguished Name (DN)**:
- **Common Name (CN)** - Required (e.g., "*.example.com", "vpn.company.com")
- **Organization (O)** - Company name
- **Organizational Unit (OU)** - Department
- **Country (C)** - 2-letter code
- **State/Province (ST)** - State name
- **Locality (L)** - City name

**Certificate Settings**:
- **Issuer CA** - Select which CA will sign this certificate
- **Validity Days** - Certificate lifetime (e.g., 365, 730)
- **Key Type** - RSA 2048, RSA 4096, ECDSA P-256, etc.
- **Hash Algorithm** - SHA-256 (recommended), SHA-384, SHA-512

**Extensions**:
- **Key Usage** - Digital Signature, Key Encipherment, etc.
- **Extended Key Usage**:
  - `Server Authentication` - Web servers (HTTPS)
  - `Client Authentication` - VPN clients, user auth
  - `Code Signing` - Software signing
  - `Email Protection` - S/MIME
- **Subject Alternative Names (SANs)**:
  - DNS names: `example.com`, `*.example.com`
  - IP addresses: `192.168.1.1`, `10.0.0.1`
  - Email addresses: `admin@example.com`

#### Step 3: Generate Certificate
1. Review all settings
2. Click **"Create Certificate"**
3. Certificate is generated with private key
4. Download or export as needed

---

### Method 2: Certificate Signing Request (CSR)

#### For External CSR
1. Generate CSR externally:
   ```bash
   openssl req -new -newkey rsa:2048 -nodes \
     -keyout private.key -out request.csr \
     -subj "/CN=example.com/O=Company/C=US"
   ```

2. In UCM:
   - Go to **Certificates** → **"Sign CSR"**
   - Upload or paste CSR content
   - Select Issuer CA
   - Configure validity and extensions
   - Click **"Sign CSR"**
   - Download signed certificate

---

## 📋 Viewing Certificate Details

### Access Certificate Details
1. Go to **Certificates** page
2. Click on certificate row or **"View"** button

### Information Available

**Basic Information**:
- Subject DN (CN, O, OU, C, ST, L)
- Issuer CA name
- Serial Number
- Status (Active/Revoked)
- Validity period (Not Before / Not After)

**Technical Details**:
- Key Type and Size
- Hash Algorithm
- Public Key (PEM format)
- Fingerprints (SHA-256, SHA-1)
- Subject Key Identifier
- Authority Key Identifier

**Extensions**:
- Key Usage flags
- Extended Key Usage
- Subject Alternative Names
- CRL Distribution Points (if enabled on CA)
- Authority Information Access

**Files Available**:
- Certificate (PEM/DER)
- Private Key (PEM) ⚠️ Sensitive
- Certificate Chain
- PKCS#12 bundle

---

## 📤 Exporting Certificates

### Export Formats

#### 1. PEM Format (Recommended)
- **Certificate Only**:
  ```bash
  # Download from UI or via API
  curl -k https://your-server:8443/api/v1/certificates/{id}/export?format=pem
  ```
  
- **Certificate + Private Key**:
  - Click **"Export → PEM (with key)"**
  - ⚠️ Keep private key secure!

- **Full Chain**:
  - Certificate + Intermediate CA(s) + Root CA
  - Click **"Export → Chain (PEM)"**

#### 2. DER Format
- Binary format
- Use for: Windows Certificate Store, some Java applications
- Click **"Export → DER"**

#### 3. PKCS#12 (.p12/.pfx)
- Password-protected bundle
- Contains: Certificate + Private Key + Chain
- Use for: Windows, browsers, email clients
- Steps:
  1. Click **"Export → PKCS#12"**
  2. Enter password (strong password required)
  3. Re-enter password
  4. Download `.p12` file

### Use Cases

**Web Server (Apache/Nginx)**:
```bash
# PEM format (certificate + key + chain)
# Apache:
SSLCertificateFile /path/to/certificate.pem
SSLCertificateKeyFile /path/to/private.key
SSLCertificateChainFile /path/to/chain.pem

# Nginx:
ssl_certificate /path/to/fullchain.pem;  # cert + chain
ssl_certificate_key /path/to/private.key;
```

**VPN Server (OpenVPN)**:
```bash
# PEM format
cert /path/to/server.crt
key /path/to/server.key
ca /path/to/ca.crt
```

**Email Client (Thunderbird/Outlook)**:
```bash
# PKCS#12 format
# Import .p12 file with password
# Settings → Security → Certificates → Import
```

**Browser (Chrome/Firefox)**:
```bash
# PKCS#12 format
# Settings → Privacy & Security → Certificates → Import
```

---

## 🔄 Renewing Certificates

### Before Expiration
1. Go to **Certificates** page
2. Find certificate nearing expiration
3. Note the DN and settings
4. Create new certificate with same DN
5. Update server/application configuration
6. Revoke old certificate (optional)

### Auto-Renewal (via SCEP)
- SCEP clients can auto-renew
- See [SCEP Server Guide](SCEP-Server)

---

## 🗑️ Revoking Certificates

### When to Revoke
- ✅ Private key compromised
- ✅ Certificate no longer needed
- ✅ Information in certificate incorrect
- ✅ Organizational change
- ✅ Security incident

### How to Revoke
1. Go to Certificate Details page
2. Click **"Revoke Certificate"** button
3. Select **Revocation Reason**:
   - `Unspecified`
   - `Key Compromise` ⚠️ Most serious
   - `CA Compromise`
   - `Affiliation Changed`
   - `Superseded` - Certificate replaced
   - `Cessation of Operation`
   - `Certificate Hold` - Temporary
4. Confirm revocation

### After Revocation
- ✅ Certificate status → "Revoked"
- ✅ CRL automatically regenerated (if CDP enabled)
- ✅ OCSP status updated (if OCSP enabled)
- ✅ Certificate cannot be un-revoked (except "Certificate Hold")

---

## 📊 Certificate Management Best Practices

### Certificate Lifetime
- **Web Servers**: 1-2 years (365-730 days) ✨ Recommended
- **VPN Servers**: 1-3 years
- **User Certificates**: 1 year
- **Code Signing**: 3 years
- **Internal Services**: 2-5 years

### Key Type Selection
- **RSA 2048**: Standard, widely compatible ✨ Recommended
- **RSA 4096**: Higher security, slightly larger
- **ECDSA P-256**: Modern, efficient, smaller certificates

### Subject Alternative Names (SANs)
Always include SANs for:
- ✅ DNS names (required for HTTPS)
- ✅ IP addresses (if accessing by IP)
- ✅ Wildcard domains (`*.example.com`)

Example:
```
CN=example.com
SANs:
  - DNS: example.com
  - DNS: www.example.com
  - DNS: *.example.com
  - IP: 192.168.1.100
```

### Security
1. ✅ **Never share private keys** - Keep them secure
2. ✅ **Use strong passwords** for PKCS#12 exports
3. ✅ **Revoke immediately** if key compromised
4. ✅ **Monitor expiration** - Set reminders 30 days before
5. ✅ **Regular audits** - Review active certificates monthly

---

## 🔍 Troubleshooting

### Certificate Not Trusted
- ✅ Import Root CA into client trust store
- ✅ Verify certificate chain is complete
- ✅ Check CA is not revoked
- ✅ Verify certificate validity dates

### Private Key Mismatch
- ✅ Re-export certificate with matching key
- ✅ Verify certificate and key are from same generation
- ✅ Test: `openssl rsa -in key.pem -check`

### SAN Not Working
- ✅ Verify SAN extension is present: `openssl x509 -in cert.pem -text -noout`
- ✅ Check DNS name matches exactly (case-sensitive)
- ✅ Wildcard certificates: `*.example.com` matches `sub.example.com` but NOT `example.com`

### Export PKCS#12 Fails
- ✅ Use strong password (min 8 chars, mixed case, numbers, symbols)
- ✅ Check private key is available
- ✅ Verify certificate is not revoked

---

## 📚 Related Pages

- [CA Management](CA-Management)
- [Certificate Export](Certificate-Export)
- [SCEP Server](SCEP-Server)
- [API Reference - Certificate Endpoints](API-Reference#certificate-endpoints)

---

**Last Updated**: 2026-01-07
