# 📖 UCM User Manual

Complete guide for using Ultimate CA Manager.

---

## 📑 Table of Contents

1. [Login and Interface](#login-and-interface)
2. [Dashboard](#dashboard)
3. [CA Management](#ca-management)
4. [Certificate Management](#certificate-management)
5. [SCEP Server](#scep-server)
6. [User Management](#user-management)
7. [System Settings](#system-settings)
8. [Common Operations](#common-operations)

---

## 🔐 Login and Interface

### First Login

1. **Access UCM**
   ```
   https://<your-server>:8443
   ```

2. **Default credentials**
   - **Username**: `admin`
   - **Password**: `admin`
   
   ⚠️ **Important**: Change the password immediately after first login!

3. **Accept self-signed certificate**
   - Your browser will display a warning
   - Click on "Advanced settings" → "Continue to site"
   - This is normal for the first login

### User Interface

The UCM interface consists of:

- **Navigation bar** (top) - Quick access to sections
- **Sidebar menu** (left) - Main navigation
- **Content area** (center) - Main workspace
- **Status bar** (bottom) - System information

### Themes

UCM supports two themes:
- **Light** ☀️ - Default
- **Dark** 🌙 - In Settings → Profile → Theme

---

## 📊 Dashboard

The dashboard displays an overview of your PKI.

### Displayed Statistics

1. **Certificate Authorities**
   - Total number of CAs
   - Active vs revoked CAs
   - Root CA / Intermediate CA breakdown

2. **Certificates**
   - Total certificates issued
   - Active certificates
   - Revoked certificates
   - Expired certificates

3. **Upcoming Expirations**
   - Certificates expiring within 30 days
   - Certificates expiring within 90 days
   - Expiration alerts

4. **SCEP Activity**
   - Active SCEP endpoints
   - Recent enrollments
   - Automatic renewals

### Charts

- **Issuance timeline** - Certificates issued by period
- **Type distribution** - Server, Client, Code Signing, etc.
- **Certificate status** - Valid, Expired, Revoked

---

## 🏛️ CA Management

### Create a Root CA

1. **Navigation**: Menu → Certificate Authorities → Create New CA

2. **Basic settings**
   ```
   CA Type: Root CA
   Key Type: RSA 4096 bits (recommended for Root CA)
   Hash Algorithm: SHA-384 or SHA-512
   Validity: 20 years (7300 days)
   ```

3. **Distinguished Name (DN)**
   ```
   Common Name (CN): My Company Root CA
   Organization (O): My Company Inc.
   Organizational Unit (OU): IT Security
   Country (C): FR
   State (ST): Ile-de-France
   Locality (L): Paris
   ```

4. **Advanced options**
   - ✅ **CA Certificate** - Required
   - ✅ **Certificate Sign** - Required
   - ✅ **CRL Sign** - Required
   - ⬜ **Digital Signature** - Optional

5. **Click "Create CA"**

### Create an Intermediate CA

1. **Prerequisite**: A Root CA must exist

2. **Configuration**
   ```
   CA Type: Intermediate CA
   Parent CA: Select your Root CA
   Key Type: RSA 4096 bits
   Hash Algorithm: SHA-384
   Validity: 10 years (3650 days)
   ```

3. **Distinguished Name**
   ```
   CN: My Company Issuing CA 1
   O: My Company Inc.
   OU: PKI Services
   C: FR
   ```

4. **Path Length Constraint**
   - `0` = This Intermediate CA cannot create other Intermediate CAs
   - `1` = Can create 1 additional level of Intermediate CAs
   - Empty = No limit

### Import an Existing CA

1. **Menu → Import CA**

2. **Supported formats**
   - **PEM** - .pem, .crt, .key files
   - **PKCS#12** - .pfx, .p12 files

3. **PEM import**
   ```
   Certificate File: ca-cert.pem
   Private Key File: ca-key.pem
   Private Key Password: (if encrypted)
   ```

4. **PKCS#12 import**
   ```
   PKCS#12 File: ca.pfx
   Password: ****
   ```

### Export a CA

1. **CA list → Actions → Export**

2. **Choose format**
   - **Certificate only (PEM)** - For public distribution
   - **Full chain (PEM)** - Certificate + complete chain
   - **PKCS#12** - Certificate + private key (⚠️ secure)

3. **For PKCS#12**
   ```
   Export Password: ********
   Confirm Password: ********
   ```

### Revoke a CA

⚠️ **Warning**: Irreversible operation!

1. **CA list → Select CA → Revoke**

2. **Revocation reason**
   - Key Compromise
   - Superseded
   - Cessation of Operation
   - Unspecified

3. **Consequences**
   - All certificates issued by this CA become invalid
   - The CA appears in the CRL
   - Non-reversible operation

---

## 📜 Certificate Management

### Issue a New Certificate

1. **Menu → Certificates → Issue New Certificate**

2. **Select issuing CA**
   ```
   Issuing CA: My Company Issuing CA 1
   ```

3. **Certificate type**
   - **Server Certificate** - Web servers, VPN, etc.
   - **Client Certificate** - User authentication
   - **Code Signing** - Code signing
   - **Email Certificate** - S/MIME

4. **Subject information**
   
   For a server certificate:
   ```
   Common Name (CN): www.example.com
   Organization (O): Example Inc.
   OU: Web Services
   Country (C): FR
   ```
   
   For a client certificate:
   ```
   CN: John Doe
   Email: john.doe@example.com
   O: Example Inc.
   ```

5. **Key configuration**
   ```
   Key Type: RSA 2048 bits (standard)
            or ECDSA P-256 (modern, faster)
   Hash Algorithm: SHA-256 (standard)
   Validity: 395 days (13 months, browser max)
   ```

6. **Subject Alternative Names (SANs)**
   
   For server certificates (important!):
   ```
   DNS Names:
   - www.example.com
   - example.com
   - mail.example.com
   
   IP Addresses (if needed):
   - 192.168.1.100
   ```

7. **Key Usage**
   
   Server certificate:
   - ✅ Digital Signature
   - ✅ Key Encipherment
   - Extended: Server Authentication
   
   Client certificate:
   - ✅ Digital Signature
   - ✅ Key Agreement
   - Extended: Client Authentication
   
   Code Signing:
   - ✅ Digital Signature
   - Extended: Code Signing

8. **Click "Issue Certificate"**

### Import and Sign a CSR

1. **Menu → Certificates → Sign CSR**

2. **Upload CSR file**
   ```
   Drag & Drop or Browse: request.csr
   ```

3. **UCM automatically displays**
   - CSR Subject DN
   - Public key and type
   - Requested extensions

4. **Select CA** and **configure**
   ```
   Issuing CA: My Company Issuing CA 1
   Validity: 365 days
   ```

5. **Verify/Add SANs if needed**

6. **Sign the CSR**

### Renew a Certificate

1. **Certificate list → Select → Renew**

2. **Renewal options**
   - **Reuse same key** - Keeps existing key
   - **Generate new key** - Recommended for security

3. **Adjust validity if needed**
   ```
   Validity: 395 days
   ```

4. **The new certificate**
   - Keeps the same Subject DN
   - Keeps the same SANs
   - New serial number
   - New validity period

### Revoke a Certificate

1. **List → Select certificate → Revoke**

2. **Revocation reason**
   ```
   - Key Compromise ⚠️
   - CA Compromise ⚠️⚠️
   - Affiliation Changed
   - Superseded
   - Cessation of Operation
   - Certificate Hold (temporary suspension)
   - Remove from CRL
   - Privilege Withdrawn
   ```

3. **Immediate effect**
   - Certificate added to CRL
   - OCSP returns "revoked"
   - Invalid for any use

### Export a Certificate

1. **List → Select → Export**

2. **Available formats**

   **PEM (Base64 ASCII)**
   ```
   - Certificate only (.pem)
   - Certificate + Chain (.pem)
   - Full chain (.pem)
   ```
   
   **DER (Binary)**
   ```
   - Certificate only (.der, .cer)
   ```
   
   **PKCS#12**
   ```
   - Certificate + Private Key + Chain (.pfx, .p12)
   - Password protected ⚠️
   ```

3. **PKCS#12 export** (includes private key)
   ```
   Export Password: ********
   Friendly Name: www.example.com
   Include Chain: ✅ Recommended
   ```

### Search Certificates

**Search bar**
```
Search by:
- Common Name (CN)
- Serial Number
- Subject DN
- Issuer DN
- Email
```

**Advanced filters**
```
Status: Active / Revoked / Expired
Type: Server / Client / Code Signing
Issuer: Select a CA
Validity: Expiring in 30/60/90 days
```

---

## 🔄 SCEP Server

SCEP (Simple Certificate Enrollment Protocol) enables automatic certificate enrollment.

### Create a SCEP Endpoint

1. **Menu → SCEP → New Endpoint**

2. **Basic configuration**
   ```
   Endpoint Name: Mobile Devices SCEP
   Description: SCEP for iOS/Android
   Issuing CA: My Company Issuing CA 1
   ```

3. **SCEP settings**
   ```
   Challenge Password: ****************
   Challenge Type: Dynamic (recommended)
                  or Static
   
   Validity: 365 days
   Auto-renewal: ✅ Enabled
   Renewal Window: 30 days before expiration
   ```

4. **Certificate template**
   ```
   Certificate Type: Client Certificate
   Key Type: RSA 2048 or ECDSA P-256
   Hash Algorithm: SHA-256
   
   Key Usage:
   - ✅ Digital Signature
   - ✅ Key Agreement
   
   Extended Key Usage:
   - ✅ Client Authentication
   - ✅ Email Protection (if needed)
   ```

5. **Generated SCEP URL**
   ```
   https://<server>:8443/scep/mobile-devices
   ```

### iOS Configuration

1. **Create a configuration profile (.mobileconfig)**

   UCM automatically generates the profile:
   
   ```
   SCEP Menu → Endpoint → Generate iOS Profile
   ```

2. **Profile settings**
   ```
   Profile Name: Company PKI
   Organization: My Company Inc.
   Description: Enterprise Certificate Enrollment
   ```

3. **Distribute the profile**
   - Email
   - MDM (Mobile Device Management)
   - Download URL
   - AirDrop

4. **Installation on iOS**
   ```
   Settings → Profile Downloaded → Install
   Enter Challenge Password: ****
   ```

### Android Configuration

1. **Download SCEP management app**
   - Use a SCEP-compatible app
   - Or MDM integration

2. **Manual configuration**
   ```
   SCEP URL: https://<server>:8443/scep/mobile-devices
   Challenge Password: ****
   ```

### Windows Configuration

1. **Via GPO (Group Policy)**
   ```
   Computer Configuration
   → Policies
   → Windows Settings
   → Security Settings
   → Public Key Policies
   → Certificate Services Client - Auto-Enrollment
   ```

2. **NDES-like configuration**
   ```
   SCEP URL: https://<server>:8443/scep/windows
   Challenge: ****
   ```

### SCEP Monitoring

**SCEP Menu → Endpoint → Activity**

Displays:
- Successful enrollments
- Failures and reasons
- Automatic renewals
- Revocations

---

## 👥 User Management

UCM uses an RBAC (Role-Based Access Control) system.

### Available Roles

1. **Admin** 👑
   - Full access
   - CA management
   - User management
   - System configuration

2. **Operator** 🔧
   - Issue certificates
   - Revoke certificates
   - Export certificates
   - View CAs (read-only)

3. **Viewer** 👁️
   - View CAs
   - View certificates
   - Download public certificates
   - No modifications

### Create a User

1. **Menu → Settings → Users → Add User**

2. **User information**
   ```
   Username: john.doe
   Full Name: John Doe
   Email: john.doe@example.com
   Role: Operator
   ```

3. **Password**
   ```
   Password: ********** (min 8 characters)
   Confirm: **********
   
   Requirements:
   - 8+ characters
   - Uppercase + lowercase
   - At least 1 digit
   - 1 special character recommended
   ```

4. **Options**
   ```
   ✅ Force password change on first login
   ✅ Account enabled
   ⬜ API access enabled
   ```

### Modify a User

1. **User list → Edit**

2. **Possible modifications**
   - Full name
   - Email
   - Role
   - Account status
   - Reset password

### Change Your Password

1. **User menu (top right) → Profile**

2. **Security → Change Password**
   ```
   Current Password: ****
   New Password: ********
   Confirm New Password: ********
   ```

---

## ⚙️ System Settings

### General Configuration

**Menu → Settings → System**

```
System Name: My Company PKI
Base URL: https://pki.example.com:8443
Administrator Email: pki-admin@example.com
Organization: Example Inc.
```

### CRL (Certificate Revocation List)

```
CRL Update Interval: 24 hours
CRL Distribution Point: http://pki.example.com:8080/crl/<ca-id>.crl
Next CRL Update: 7 days
```

### OCSP (Online Certificate Status Protocol)

```
OCSP Responder: ✅ Enabled
OCSP URL: http://ocsp.example.com:8080
OCSP Signing Certificate: Auto-generated
Response Validity: 7 days
```

### Session and Security

```
Session Timeout: 30 minutes
Max Login Attempts: 5
Lockout Duration: 15 minutes
Force HTTPS: ✅ Enabled
HSTS: ✅ Enabled
```

### Backup and Maintenance

**Automatic backup**
```
Backup Interval: Daily
Backup Time: 02:00 AM
Retention: 7 days
Backup Path: /opt/ucm/backups/
```

**Maintenance**
```
Auto-cleanup expired certificates: ✅ 90 days after expiration
Auto-cleanup revoked certificates: ❌ Keep
Database optimization: Weekly
```

---

## 🎯 Common Operations

### Use Case 1: Web Server Certificate

**Scenario**: Secure www.example.com

```
1. Certificates → Issue New Certificate
2. Issuing CA: Intermediate CA
3. Certificate Type: Server Certificate
4. Subject DN:
   CN: www.example.com
   O: Example Inc.
5. SANs:
   - www.example.com
   - example.com
6. Key: RSA 2048, SHA-256
7. Validity: 395 days
8. Issue → Export PKCS#12
9. Install on web server
```

### Use Case 2: VPN Client Certificates

**Scenario**: VPN authentication by certificate

```
1. Certificates → Issue New Certificate
2. Type: Client Certificate
3. Subject:
   CN: john.doe
   Email: john.doe@example.com
4. Key Usage:
   - Digital Signature
   - Key Agreement
   - Client Authentication
5. Export PKCS#12 with password
6. Send securely to user
7. Configure VPN to accept this CA
```

### Use Case 3: Code Signing

**Scenario**: Sign applications

```
1. Certificates → Issue New Certificate
2. Type: Code Signing
3. Subject:
   CN: Example Inc. Code Signing
   O: Example Inc.
4. Key: RSA 4096 (recommended for code signing)
5. Validity: 3 years maximum
6. Extended Key Usage: Code Signing
7. Export PKCS#12
8. Use with signtool, jarsigner, etc.
```

### Use Case 4: S/MIME Email

**Scenario**: Sign and encrypt emails

```
1. Certificates → Issue New Certificate
2. Type: Email Certificate
3. Subject:
   CN: John Doe
   Email: john.doe@example.com
4. SANs:
   Email: john.doe@example.com
5. Key Usage:
   - Digital Signature
   - Key Encipherment
   - Email Protection
6. Export PKCS#12
7. Import into email client (Outlook, Thunderbird)
```

### Use Case 5: iOS SCEP Enrollment

**Scenario**: Deploy certificates on 100 iPads

```
1. SCEP → New Endpoint
2. Name: iPad Fleet
3. Type: Client Certificate
4. Challenge: Dynamic
5. Auto-renewal: ✅
6. Generate iOS Profile
7. Distribute via MDM
8. iPads enroll automatically
9. Auto-renewal 30 days before expiration
```

---

## 📋 Production Deployment Checklist

### Before Deployment

- [ ] Root CA created with 4096-bit key and 20-year validity
- [ ] Intermediate CA created for daily issuance
- [ ] Root CA backup performed and stored offline
- [ ] Root CA stored offline (cold storage)
- [ ] Admin password changed
- [ ] Users created with appropriate roles
- [ ] HTTPS configured with valid certificate
- [ ] CRL and OCSP configured and accessible
- [ ] Automatic backup configured
- [ ] Firewall configured (port 8443 HTTPS, 8080 HTTP for CRL/OCSP)

### After Deployment

- [ ] Certificate issuance test
- [ ] Revocation test and CRL verification
- [ ] OCSP test
- [ ] SCEP enrollment test
- [ ] Renewal test
- [ ] Backup verification
- [ ] Procedure documentation
- [ ] Operator training

---

## 🆘 Help and Support

- **Documentation**: [GitHub Wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki)
- **Issues**: [GitHub Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)
- **Discussions**: [GitHub Discussions](https://github.com/NeySlim/ultimate-ca-manager/discussions)

---

**Next section**: [Troubleshooting](Troubleshooting) | [API Reference](API-Reference)
