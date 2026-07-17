# UCM User Guide

Quick start guide for using Ultimate Certificate Manager.

---

## Getting Started

### First Login

1. Navigate to `https://your-server:8443`
2. Login with default credentials: `admin` / `changeme123`
3. **Important:** Change your password immediately in Account settings

### Navigation

UCM uses a 3-panel layout:
- **Sidebar** (left, 52px) -- Main navigation icons
- **Explorer** -- List of items for current page
- **Details** (flex) -- Selected item details and actions

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Cmd/Ctrl + K` | Open Command Palette |
| `Escape` | Close modals/menus |

---

## Certificate Management

### Creating a Certificate

1. Go to **Certificates** page
2. Click **+ New Certificate** button
3. Fill in the form:
   - **Common Name** - Primary identifier (e.g., `www.example.com`)
   - **Subject Alternative Names** - Additional domains/IPs
   - **Issuing CA** - Select parent CA
   - **Template** - Use preset or custom settings
   - **Validity** - Certificate lifetime
4. Click **Create**

### Exporting Certificates

1. Select a certificate in the table
2. In the details panel, click **Export**
3. Choose format:
   - **PEM** - Standard format (certificate + key)
   - **PKCS12** - Windows/Java compatible bundle
   - **DER** - Binary format
4. Set password (for PKCS12)
5. Download or copy to clipboard

### Revoking Certificates

1. Select the certificate
2. Click **Revoke** in details panel
3. Select revocation reason
4. Confirm action
5. Certificate is added to CRL automatically

---

## CA Management

### Creating a Root CA

1. Go to **Certificate Authorities** page
2. Click **+ New CA**
3. Select **Root CA** type
4. Configure:
   - **Common Name** - CA identifier
   - **Organization** - Your organization name
   - **Key Type** - RSA 4096 or ECDSA P-384 recommended
   - **Validity** - 10-20 years typical for Root
5. Click **Create**

### Creating an Intermediate CA

1. Go to **Certificate Authorities** page
2. Click **+ New CA**
3. Select **Intermediate CA** type
4. Choose **Parent CA** from your Root CAs
5. Configure settings (5-10 year validity typical)
6. Click **Create**

### CA Hierarchy View

- Toggle between **Grid** and **Tree** view using the view switcher
- Tree view shows parent-child relationships
- Click any CA to see its details and issued certificates

### Taking a CA Offline

Offline mode prevents a CA from signing anything (CSRs, certificates, intermediate CAs, new CRLs). Useful for Root CAs that should only be brought online during planned signing events.

1. Open the CA detail panel
2. Click **Take Offline**
3. Confirm, then enter and confirm an **offline password** (12+ chars, mixed case, digit, symbol — same policy as user passwords)
4. Choose a mode:
   - **Keep in UCM** — key stays in the database, re-wrapped under your password (plus the master key on top). Restore = enter password.
   - **Download file** — key is exported as a password-encrypted PKCS#8 PEM and **deleted from UCM**. Restore = re-upload file + password. The downloaded file is the only copy — store it safely.

The CA list shows an **Offline** badge while offline. Existing CRLs continue to be served via CDP; new CRLs cannot be signed until restore.

### Restoring an Offline CA

1. Open the offline CA's detail panel
2. Click **Restore**
3. Enter the offline password
4. If the CA was exported to file, also select the previously downloaded `.key.pem` file
5. The CA returns to its previous status and resumes signing

⚠️ Lose the password (or the file in file-exported mode) and the CA is unrecoverable — there is no master override.

---

## CSR Management

### Signing a CSR

1. Go to **CSRs** page
2. Upload CSR file or paste PEM content
3. Select in the list
4. Click **Sign**
5. Choose:
   - **Issuing CA** - Which CA will sign
   - **Template** - Certificate profile
   - **Validity** - Override template default
6. Click **Sign CSR**
7. Download or copy the signed certificate

---

## Templates

Templates define default settings for certificates.

### Creating a Template

1. Go to **Templates** page
2. Click **+ New Template**
3. Configure:
   - **Name** - Descriptive name
   - **Key Usage** - Digital Signature, Key Encipherment, etc.
   - **Extended Key Usage** - Server Auth, Client Auth, etc.
   - **Default Validity** - Days/months/years
   - **Digest** - Signature hash for issued certificates (`sha256` default; `sha384` / `sha512` also supported)
   - **Subject Constraints** - Required/allowed fields
4. Click **Save**

When you issue a certificate from **Certificates → Issue** and select a template, UCM applies that template’s digest (and validity defaults) and records the template on the certificate. The Templates page shows a live **usage count** of certificates issued with each template.

### Built-in Templates

| Template | Use Case |
|----------|----------|
| Web Server | HTTPS certificates |
| Client Auth | User certificates |
| Code Signing | Software signing |
| Email (S/MIME) | Email encryption |

---

## User Management

### Creating Users

1. Go to **Users** page (requires admin)
2. Click **+ New User**
3. Fill in:
   - **Username** - Login name
   - **Email** - For notifications
   - **Role** - Admin, Operator, Auditor, or Viewer
   - **Temporary Password** - User changes on first login
4. Click **Create**

### Roles & Permissions

| Role | Permissions |
|------|-------------|
| **Admin** | Full access, user management, settings |
| **Operator** | Create/manage certs, CAs, CSRs, protocols |
| **Auditor** | Read-only access to all resources (except users/settings) |
| **Viewer** | Read-only access to certificates, CAs, CSRs, templates, truststore |

---

## Single Sign-On (SSO)

UCM supports external identity providers for authentication:

- **LDAP / Active Directory** — Bind-based authentication with group-to-role mapping
- **OAuth2** — Google, GitHub, Azure AD, or any OpenID Connect provider
- **SAML 2.0** — Enterprise identity providers (Okta, Azure AD, ADFS)

Configure SSO in **Settings** → **SSO** tab (admin only). Each provider type supports automatic role mapping based on group membership.

---

## Security Settings

### Enabling 2FA (TOTP)

1. Go to **Account** → **Security** tab
2. Click **Enable 2FA**
3. Scan QR code with authenticator app
4. Enter verification code
5. Save backup codes securely

### Adding WebAuthn Key

1. Go to **Account** → **Security** tab
2. Click **Add Security Key**
3. Insert and touch your hardware key
4. Name the key for identification

---

## Protocol Configuration

### ACME Server

Enable Let's Encrypt-compatible certificate issuance:

1. Go to **Settings** → **ACME** tab
2. Enable ACME server
3. Configure:
   - **Base URL** - Public URL for challenges
   - **Default CA** - CA for issued certificates
   - **Allowed Domains** - Restrict issuance
4. Clients use: `https://your-server:8443/acme/directory`

### SCEP Server

Enable device auto-enrollment:

1. Go to **Settings** → **SCEP** tab
2. Enable SCEP server
3. Configure:
   - **Challenge Password** - Enrollment secret
   - **CA for Signing** - Issuing CA
   - **Certificate Template** - Default profile
4. Devices use: `https://your-server:8443/scep`

### OCSP Responder

Real-time certificate validation:

1. Enable OCSP per CA on the **CRL & OCSP** page (or CA settings)
2. Public URL (typical): `http://your-server:8080/ocsp` on the protocol HTTP port, or via reverse proxy
3. Configure CDP/AIA URLs on the CA so issued certificates advertise the responder

### CRL distribution (CDP)

1. Go to **CRL & OCSP**
2. Select a CA and enable **Auto-Regen** / CDP as needed
3. In the detail panel, use **Full CRL schedule** to set:
   - **CRL validity** — `nextUpdate` window on the published CRL (default 7 days)
   - **Publish interval** — when UCM should republish (`next_publish`; independent of validity)
   - **CRL signature digest** — hash used when signing the CRL (default SHA-256)
4. Optional: enable **Delta CRL** and its interval
5. Relying parties fetch: `http://your-server:8080/cdp/<ca_refid>.crl` (download name is human-readable; URL stays refid-based)
6. Optional: under **CDP / OCSP URL transport**, choose **HTTP (port 8080)** or **HTTPS (admin port)** for that CA’s embedded CDP/OCSP/AIA URLs

Issued certificates use a short **notBefore** backdate (~15 minutes) so clients with slightly skewed clocks still accept fresh certs.

On a certificate detail page you can edit **description** and **friendly name** after issuance (metadata only). The certificates list shows the **template used** when a template was selected at issue time.

When creating a CA, validity presets go up to **100 years**, or you can set a custom end date.

For privileged protocol port **80**, reverse-proxy notes, and API details, see [ADMIN_GUIDE.md](./ADMIN_GUIDE.md) (Protocol Administration).

### EST Server

RFC 7030 device enrollment:

1. Go to **Operations > EST**
2. Enable EST and assign a CA
3. Devices use: `https://your-server:8443/.well-known/est`
4. Supports simple enrollment and re-enrollment

---

## Certificate Discovery

Scan your network for certificates:

1. Go to **Operations > Discovery**
2. Create a **Scan Profile** with target hosts/networks, ports, and schedule
3. Run a scan manually or let it run on schedule
4. Review discovered certificates — status, expiry, issuer, SAN
5. Import discovered certificates into UCM or flag them for tracking

### Quick Scan

For one-off checks, use the **Quick Scan** button to scan a single host or range without creating a profile.

---

## Certificate Tools

The **Tools** section provides utilities for working with certificates:

- **SSL Checker** — Test SSL/TLS configuration of any server (public or internal)
- **CSR Decoder** — Paste a CSR to inspect subject, SANs, key type, and extensions
- **Certificate Decoder** — Paste a PEM certificate to view all fields
- **Key Matcher** — Verify that a certificate and private key match
- **Format Converter** — Convert between PEM, DER, and PKCS#12 formats

---

## Reports

The **Reports** page provides on-demand and scheduled reporting for your PKI environment.

### Reports Overview

The reports page shows:
- **Stat cards** — Quick counts for certificates, CAs, expiring soon, and revoked
- **Report list** — All available report types with generate/download actions
- **Schedule status** — Which reports are scheduled and their next run time

### Generating On-Demand Reports

1. Go to **Reports** page
2. Select a report type from the list:
   - **Expiring Certificates** — Certificates expiring within a configurable number of days
   - **Revoked Certificates** — All revoked certificates with reason and date
   - **CA Hierarchy** — Certificate Authority tree with issued certificate counts
   - **Audit Summary** — Recent audit log activity grouped by action type
   - **Compliance Status** — Policy compliance overview across all certificates
   - **Certificate Inventory** — Full inventory of all certificates with status and metadata
3. Click **Generate** to create the report
4. Choose output format: **CSV**, **JSON**, or **PDF**

### Executive PDF Report

The executive PDF report provides a comprehensive, downloadable document for management review:

1. Go to **Reports** page
2. Click **Download Executive PDF**
3. The PDF includes:
   - **Cover page** with organization name and generation date
   - **Executive summary** with key metrics
   - **Risk assessment** highlighting urgent issues
   - **Certificate inventory** breakdown by status
   - **Compliance status** across all policies
   - **Lifecycle analysis** of certificate age and renewal patterns
   - **CA infrastructure** overview
   - **Recommendations** based on current state

### Understanding Report Data

- **Expiring Certificates** — Use the `days` parameter to control the look-ahead window (default: 30 days)
- **Revoked Certificates** — Includes revocation reason (key compromise, CA compromise, affiliation changed, etc.)
- **CA Hierarchy** — Shows parent-child relationships and certificate counts per CA
- **Audit Summary** — Groups actions by type (create, revoke, delete, login, etc.) with counts
- **Compliance Status** — Shows pass/fail per policy with affected certificate details
- **Certificate Inventory** — Full list with serial number, CN, issuer, validity dates, and status

---

## Themes

Change the UI theme:

1. Click your **user avatar** (bottom of sidebar) to open the user menu
2. Select **Theme** submenu
3. Choose from 3 color schemes, each with Light and Dark variants:
   - Gray (default)
   - Purple Night
   - Orange Sunset
4. Or select **Follow System** to match your OS light/dark preference

Theme persists across sessions.

---

## Mobile Usage

UCM is mobile-responsive:

- **Bottom Sheet** - Tap the peek bar to see explorer list
- **Swipe** - Drag to resize the explorer
- **Tap to Select** - Touch items to view details
- **Auto-Close** - Sheet closes when item selected

---

## Troubleshooting

### Can't Login

1. Check username/password
2. Clear browser cache
3. Try incognito mode
4. Check server logs: `journalctl -u ucm -f`

### Certificate Creation Fails

1. Verify CA has valid private key
2. Check CA validity period
3. Review error message in notification
4. If clients reject a *just-issued* certificate as “not yet valid”, check client clock skew (UCM backdates `notBefore` by ~15 minutes)

### CRL / CDP Not Updating

1. Confirm CDP / Auto-Regen is enabled for the CA on **CRL & OCSP**
2. Check **Full CRL schedule** — publish interval vs validity (publish can be due before `nextUpdate`)
3. Offline CAs cannot sign new CRLs (existing CDP content may still be served)
4. Protocol HTTP must be reachable (default port 8080; port 80 needs bind capability or a reverse proxy)

### SCEP/ACME Not Working

1. Verify service is enabled in Settings
2. Check firewall allows port 8443
3. Verify DNS/hostname configuration
4. Test with `curl https://server:8443/scep`

---

## More Resources

- [API Reference](API_REFERENCE.md)
- [Installation Guide](installation/README.md)
- [Docker Guide](installation/docker.md)
- [Changelog](../CHANGELOG.md)
