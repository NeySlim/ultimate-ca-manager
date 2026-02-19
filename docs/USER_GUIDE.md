# UCM User Guide

Quick start guide for using Ultimate CA Manager.

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
   - **Subject Constraints** - Required/allowed fields
4. Click **Save**

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

1. OCSP is enabled automatically
2. URL: `https://your-server:8443/ocsp`
3. Configure in CA settings for CDP/AIA extensions

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
