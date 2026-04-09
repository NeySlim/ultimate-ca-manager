/**
 * Detailed help guides for all UCM pages — v2.50
 * Each entry: { title, content (markdown string) }
 * Markdown supports: ## h2, ### h3, #### h4, **bold**, `code`, *italic*,
 *   - lists, 1. numbered, > blockquotes, ``` code blocks
 */

export const helpGuides = {

  // ===================================================================
  dashboard: {
    title: 'Dashboard',
    content: `
## Overview

The Dashboard is your central monitoring hub. It displays real-time metrics, charts, and alerts about your entire PKI infrastructure through customizable widgets.

## Widgets

### Statistics Card
Displays four key counters:
- **Total CAs** — Root and Intermediate Certificate Authorities
- **Active Certificates** — Valid, non-revoked certificates
- **Pending CSRs** — Certificate Signing Requests awaiting approval
- **Expiring Soon** — Certificates expiring within 30 days

### Certificate Trend
A line chart showing certificate issuance over time. Hover over data points to see exact counts.

### Status Distribution
Pie chart showing the breakdown of certificate states:
- **Valid** — Within validity period and not revoked
- **Expiring** — Expires within 30 days
- **Expired** — Past the "Not After" date
- **Revoked** — Explicitly revoked

### Next Expiry
Lists certificates expiring soonest. Click any certificate to navigate to its details. Configure the threshold in **Settings → General**.

### System Status
Shows the health of UCM services:
- ACME server (enabled/disabled)
- SCEP server
- EST protocol (enabled/disabled, assigned CA)
- CRL auto-regeneration with CDP count
- OCSP responder
- Auto-renewal status
- Service uptime

### Recent Activity
A live feed of the latest operations: certificate issuance, revocations, imports, user logins. Updates in real-time via WebSocket.

### Certificate Authorities
Quick view of all CAs with their type (Root/Intermediate) and certificate count.

### ACME Accounts
Lists registered ACME client accounts and their order counts.

## Customization

### Rearranging Widgets
Drag any widget by its header to reposition it. The layout uses a responsive grid that adapts to your screen size.

### Showing/Hiding Widgets
Click the **eye icon** in the page header to toggle individual widget visibility. Hidden widgets are remembered across sessions.

### Layout Persistence
Your layout configuration is saved per-user in the browser. It persists across sessions and devices sharing the same browser profile.

## Real-Time Updates
The dashboard receives live updates via WebSocket. No manual refresh is needed — new certificates, status changes, and activity entries appear automatically.

> 💡 If WebSocket is disconnected, a yellow indicator appears in the sidebar. Data will refresh on reconnection.
`
  },

  // ===================================================================
  cas: {
    title: 'Certificate Authorities',
    content: `
## Overview

Certificate Authorities (CAs) form the foundation of your PKI. UCM supports multi-level CA hierarchies with Root CAs, Intermediate CAs, and Sub-CAs.

## CA Types

### Root CA
A self-signed certificate that serves as the trust anchor. Root CAs should ideally be kept offline in production environments. In UCM, a Root CA has no parent.

### Intermediate CA
Signed by a Root CA or another Intermediate CA. Used for day-to-day certificate signing. Intermediate CAs limit the blast radius if compromised.

### Sub-CA
Any CA signed by an Intermediate CA, creating deeper hierarchy levels.

## Views

### Tree View
Displays the full CA hierarchy as a collapsible tree. Parent-child relationships are visualized with indentation and connecting lines.

### List View
Flat table with sortable columns: Name, Type, Status, Certificates issued, Expiry date.

### Organization View
Groups CAs by their Organization (O) field. Useful for multi-tenant setups where different departments manage separate CA trees.

## Creating a CA

### Create Root CA
1. Click **Create** → **Root CA**
2. Fill in the Subject fields (CN, O, OU, C, ST, L)
3. Select the key algorithm (RSA 2048/4096, ECDSA P-256/P-384)
4. Set the validity period (typically 10-20 years for Root CAs)
5. Optionally select a certificate template
6. Click **Create**

### Create Intermediate CA
1. Click **Create** → **Intermediate CA**
2. Select the **Parent CA** (must have a private key)
3. Fill in Subject fields
4. Set the validity period (typically 5-10 years)
5. Click **Create**

> ⚠ The Intermediate CA validity cannot exceed its parent CA's validity.

## Importing a CA

Import existing CA certificates via:
- **PEM file** — Certificate in PEM format
- **DER file** — Binary DER format
- **PKCS#12** — Certificate + private key bundle (requires password)

When importing without a private key, the CA can verify certificates but cannot sign new ones.

## Exporting a CA

Export formats:
- **PEM** — Base64-encoded certificate
- **DER** — Binary format
- **PKCS#12 (P12/PFX)** — Certificate + private key + chain, password-protected

> 💡 PKCS#12 export includes the full certificate chain and is ideal for backup.

## Private Keys

CAs with a **key icon** (🔑) have a private key stored in UCM and can sign certificates. CAs without a key are trust-only — they validate chains but cannot issue.

### Key Storage
Private keys are encrypted at rest in the UCM database. For higher security, consider using an HSM provider (see HSM page).

## Chain Repair

If parent-child relationships are broken (e.g., after import), use **Chain Repair** to automatically rebuild the hierarchy based on Issuer/Subject matching.

## Renewing a CA

Renewing re-issues the CA certificate with:
- Same subject and key
- New validity period
- New serial number

Existing certificates signed by the CA remain valid.

## Deleting a CA

> ⚠ Deleting a CA removes it from UCM but does NOT revoke certificates it has issued. Revoke certificates first if needed.

Deletion is blocked if the CA has child CAs. Delete or re-parent children first.
`
  },

  // ===================================================================
  certificates: {
    title: 'Certificates',
    content: `
## Overview

Central management for all X.509 certificates. Issue new certificates, import existing ones, track expiry dates, handle renewals and revocations.

## Certificate Status

- **Valid** — Within validity period and not revoked
- **Expiring** — Will expire within 30 days (configurable)
- **Expired** — Past the "Not After" date
- **Revoked** — Explicitly revoked, published in CRL
- **Orphan** — Issuing CA no longer exists in UCM

## Issuing a Certificate

1. Click **Issue Certificate**
2. Select the **Signing CA** (must have a private key)
3. Fill in the Subject (CN is required, other fields optional)
4. Add Subject Alternative Names (SANs): DNS names, IPs, emails
5. Choose key type and size
6. Set validity period
7. Optionally apply a **Template** to pre-fill settings
8. Click **Issue**

### Using Templates
Templates pre-fill Key Usage, Extended Key Usage, subject defaults, and validity. Select a template before filling the form to save time.

## Importing Certificates

Supported formats:
- **PEM** — Single or bundled certificates
- **DER** — Binary format
- **PKCS#12 (P12/PFX)** — Certificate + key + chain (password required)
- **PKCS#7 (P7B)** — Certificate chain without keys

## Renewing a Certificate

Renewal creates a new certificate with:
- Same Subject and SANs
- New key pair (generated automatically)
- New validity period
- New serial number

The original certificate remains valid until it expires or is revoked.

## Revoking a Certificate

1. Select the certificate → **Revoke**
2. Choose a revocation reason (Key Compromise, CA Compromise, Affiliation Changed, Superseded, Cessation of Operation, Certificate Hold, etc.)
3. Confirm the revocation

Revoked certificates are published in the CRL on next regeneration.

> ⚠ Revocation is generally permanent — except for **Certificate Hold** which can be removed.

### Remove Hold (Unhold)

If a certificate was revoked with the **Certificate Hold** reason, it can be restored to valid status:

1. Open the revoked certificate details
2. The **Remove Hold** button appears in the action bar (only for Certificate Hold revocations)
3. Click **Remove Hold** to restore the certificate
4. The certificate returns to valid status, the CRL is regenerated, and the OCSP cache is updated

> 💡 Certificate Hold is useful for temporary suspensions (e.g., lost device, pending investigation).

### Revoke & Replace
Combines revocation with immediate re-issuance. The new certificate inherits the same Subject and SANs.

## Exporting Certificates

Export formats:
- **PEM** — Certificate only
- **PEM + Chain** — Certificate with full issuer chain
- **DER** — Binary format
- **PKCS#12** — Certificate + key + chain, password-protected

## Favorites

Star ⭐ important certificates to bookmark them. Favorites appear first in filtered views and are accessible from the favorites filter.

## Comparing Certificates

Select two certificates and click **Compare** to see a side-by-side diff of their Subject, SANs, Key Usage, validity, and extensions.

## Filtering & Search

- **Status filter** — Valid, Expiring, Expired, Revoked, Orphan
- **CA filter** — Show certificates from a specific CA
- **Text search** — Search by CN, serial number, or SAN
- **Sorting** — By name, expiry date, creation date, status
`
  },

  // ===================================================================
  'user-certificates': {
    title: 'User Certificates',
    content: `
## Overview

The User Certificates page manages mTLS client certificates enrolled via the **Account → mTLS** tab. Unlike regular certificates, these are specifically tied to user accounts for mutual TLS authentication.

Certificates here are fully managed by UCM — they are stored in the database with private keys, and can be exported, revoked, or deleted at any time.

## Enrolling a Certificate

1. Go to **Account → mTLS** tab
2. Click **Enroll Certificate**
3. The system generates a key pair and issues a client certificate signed by your mTLS CA
4. The certificate appears on this page and can be used for mTLS login

## Certificate Status

- **Valid** — Within validity period and not revoked
- **Expiring** — Will expire within 30 days
- **Expired** — Past the "Not After" date
- **Revoked** — Explicitly revoked, published in CRL

## Exporting a Certificate

1. Select a certificate → **Export**
2. Choose format:
   - **PEM** — Certificate + private key + CA chain in text format
   - **PKCS#12** — Binary bundle, password-protected (min 8 characters)
3. Click **Download**

The exported file can be imported into browsers, operating systems, or API clients for mTLS authentication.

> ⚠ PKCS#12 password must be at least 8 characters.

## Revoking a Certificate

1. Select a certificate → **Revoke**
2. Choose a revocation reason:
   - Key Compromise
   - Affiliation Changed
   - Superseded
   - Cessation of Operation
   - Unspecified
3. Confirm the revocation

> ⚠ Revoking a certificate immediately prevents mTLS login with that certificate. Revocation is permanent.

## Deleting a Certificate

Delete removes both the certificate and the user-certificate association. Only admins and operators can delete.

> ⚠ Deletion is permanent and cannot be undone.

## Permissions

| Role | View | Export | Revoke | Delete |
|------|------|--------|--------|--------|
| Admin | All | All | All | All |
| Operator | All | All | All | All |
| Auditor | All | ✗ | ✗ | ✗ |
| Viewer | Own only | Own only | ✗ | ✗ |

### Required Permissions

- **read:user_certificates** — View certificate list and details
- **write:user_certificates** — Revoke certificates
- **delete:user_certificates** — Delete certificates

> 💡 Enroll new mTLS certificates from the Account page. This page is for managing existing certificates.
`
  },

  // ===================================================================
  csrs: {
    title: 'Certificate Signing Requests',
    content: `
## Overview

Certificate Signing Requests (CSRs) allow external systems to request certificates without exposing their private keys. The CSR contains the public key and subject information; the private key stays with the requester.

## Tabs

### Pending
CSRs awaiting review and signing. New CSRs appear here after upload.

### History
Previously signed or rejected CSRs, with links to the resulting certificates.

## Generating a CSR

UCM can generate a CSR and key pair directly:

1. Click **Generate CSR**
2. Fill in the Subject fields (CN required)
3. Add Subject Alternative Names if needed
4. Select key type and size (RSA 2048/4096, ECDSA P-256/P-384)
5. Click **Generate**

The CSR and private key are created and stored in UCM. The CSR appears in the Pending tab ready for signing.

> 💡 This is convenient when you want UCM to manage the entire lifecycle — CSR, signing, and key storage.

## Uploading a CSR

1. Click **Upload CSR**
2. Either paste PEM text or upload a PEM/DER file
3. UCM validates the CSR signature and displays the details
4. The CSR appears in the Pending tab

## Reviewing a CSR

Click a CSR to view:
- **Subject** — CN, O, OU, C, etc.
- **SANs** — DNS names, IP addresses, emails
- **Key info** — Algorithm, size, public key fingerprint
- **Signature** — Algorithm and validity

## Signing a CSR

### Local CA Signing

1. Select a pending CSR
2. Click **Sign**
3. Choose the **Signing CA** (must have a private key)
4. Select the **Certificate Type** (server, client, code signing, email)
5. Set the **validity period** in days
5. Optionally apply a template for Key Usage and extensions
6. Click **Sign**

The resulting certificate appears in the Certificates page.

### Microsoft CA Signing

If Microsoft CA connections are configured, a **Microsoft CA** tab appears in the sign modal:

1. Select a pending CSR and click **Sign**
2. Switch to the **Microsoft CA** tab
3. Select the **MS CA connection**
4. Select the **certificate template** (auto-loaded from the CA)
5. Click **Sign**

If the template requires manager approval, UCM tracks the pending request. Check its status from the CSR detail panel.

### Enroll on Behalf Of (EOBO)

When signing via Microsoft CA, you can enroll on behalf of another user:

1. Select the MS CA connection and template
2. Check **Enroll on Behalf Of (EOBO)**
3. The **Enrollee DN** and **Enrollee UPN** fields auto-fill from the CSR subject and SAN email
4. Adjust the values if needed and click **Sign**

> ⚠️ EOBO requires an enrollment agent certificate configured on the AD CS server, and the template must allow enrollment on behalf of other users.

## Adding a Private Key

After signing, you can attach a private key to the certificate for PKCS#12 export. Click **Add Key** on the signed certificate.

> 💡 This is useful when the requester sends both the CSR and the key securely.

## Deleting CSRs

Delete removes the CSR from UCM. If the CSR was already signed, the resulting certificate is not affected.
`
  },

  // ===================================================================
  templates: {
    title: 'Certificate Templates',
    content: `
## Overview

Templates define reusable certificate profiles. Instead of manually configuring Key Usage, Extended Key Usage, validity, and subject fields each time, apply a template to pre-fill everything.

## Template Types

### End-Entity Templates
For server certificates, client certificates, code signing, and email protection. These templates typically set:
- **Key Usage** — Digital Signature, Key Encipherment
- **Extended Key Usage** — Server Auth, Client Auth, Code Signing, Email Protection

### CA Templates
For creating Intermediate CAs. These set:
- **Key Usage** — Certificate Sign, CRL Sign
- **Basic Constraints** — CA:TRUE, optional path length

## Creating a Template

1. Click **Create Template**
2. Enter a **name** and optional description
3. Select the template **type** (End-Entity or CA)
4. Configure **Subject defaults** (O, OU, C, ST, L)
5. Select **Key Usage** flags
6. Select **Extended Key Usage** values
7. Set the **default validity** period in days
8. Click **Create**

## Using Templates

When issuing a certificate or signing a CSR, select a template from the dropdown. The template pre-fills:
- Subject fields (you can override them)
- Key Usage and Extended Key Usage
- Validity period

## Duplicating Templates

Click **Duplicate** to create a copy of an existing template. Modify the copy without affecting the original.

## Import & Export

### Export
Export templates as JSON for sharing between UCM instances.

### Import
Import from:
- **JSON file** — Upload a template JSON file
- **JSON paste** — Paste JSON directly into the text area

## Common Template Examples

### TLS Server
- Key Usage: Digital Signature, Key Encipherment
- Extended Key Usage: Server Authentication
- Validity: 365 days

### Client Authentication
- Key Usage: Digital Signature
- Extended Key Usage: Client Authentication
- Validity: 365 days

### Code Signing
- Key Usage: Digital Signature
- Extended Key Usage: Code Signing
- Validity: 365 days
`
  },

  // ===================================================================
  crlocsp: {
    title: 'CRL & OCSP',
    content: `
## Overview

Certificate Revocation Lists (CRL) and Online Certificate Status Protocol (OCSP) allow clients to verify whether a certificate has been revoked. UCM supports both mechanisms.

## CRL Management

### What is a CRL?
A CRL is a signed list of revoked certificate serial numbers, published by a CA. Clients download the CRL and check if a certificate's serial number appears in it.

### CRL per CA
Each CA has its own CRL. The CRL list shows all your CAs with:
- **Revoked count** — Number of certificates in the CRL
- **Last regenerated** — When the CRL was last rebuilt
- **Auto-regeneration** — Whether automatic CRL updates are enabled

### Regenerating a CRL
Click **Regenerate** to rebuild a CA's CRL immediately. This is useful after revoking certificates.

### Auto-Regeneration
Enable auto-regeneration to automatically rebuild the CRL whenever a certificate is revoked. Toggle this per CA.

### CRL Distribution Point (CDP)
The CDP URL is embedded in certificates so clients know where to download the CRL. Copy the URL from the CRL details.

\`\`\`
http://your-server:8080/cdp/{ca_refid}.crl
\`\`\`

> 💡 **Auto-enabled**: When you create a new CA, CDP is automatically enabled if a Protocol Base URL or HTTP protocol server is configured. The CDP URL is auto-generated — no manual steps needed.

> ⚠️ **Important**: URLs are auto-generated using the HTTP protocol port and server FQDN. If you access UCM via \`localhost\`, the URL cannot be generated. Configure your **FQDN** or **Protocol Base URL** in Settings → General first.

### Downloading CRLs
Download CRLs in DER or PEM format for distribution to clients or integration with other systems.

## OCSP Responder

### What is OCSP?
OCSP provides real-time certificate status checking. Instead of downloading an entire CRL, clients send a query for a specific certificate and get an immediate response.

### OCSP Status
The OCSP section shows:
- **Responder status** — Active or inactive per CA
- **Total queries** — Number of OCSP requests processed
- **Cache** — Response cache with automatic daily cleanup of expired entries

### OCSP Cache

UCM caches OCSP responses for performance. The cache is:
- **Automatically cleaned** — Expired responses are purged daily by the scheduler
- **Invalidated on revocation** — When a certificate is revoked, its cached OCSP response is immediately cleared
- **Invalidated on unhold** — When a Certificate Hold is removed, the OCSP cache is updated

### AIA URLs
The Authority Information Access (AIA) extension is embedded in certificates to tell clients where to find:

**OCSP Responder** — real-time revocation checking:
\`\`\`
http://your-server:8080/ocsp
\`\`\`

**CA Issuers** (RFC 5280 §4.2.2.1) — download the issuing CA certificate for chain building:
\`\`\`
http://your-server:8080/ca/{ca_refid}.cer   (DER format)
http://your-server:8080/ca/{ca_refid}.pem   (PEM format)
\`\`\`

Enable CA Issuers per CA in the **AIA CA Issuers** section of the detail panel. The URL is automatically generated using the HTTP protocol server and the configured FQDN.

> ⚠️ **Prerequisite**: Protocol URLs (CDP, OCSP, AIA) require a valid **FQDN** or a configured **Protocol Base URL** in Settings → General. If you access UCM via \`localhost\`, enabling these features will fail — set the FQDN first.

### OCSP vs CRL

| Feature | CRL | OCSP |
|---------|-----|------|
| Update frequency | Periodic | Real-time |
| Bandwidth | Full list each time | Single query |
| Privacy | No tracking | Server sees queries |
| Offline support | Yes (cached) | Requires connectivity |

> 💡 Best practice: enable both CRL and OCSP for maximum compatibility.
`
  },

  // ===================================================================
  scep: {
    title: 'SCEP Server',
    content: `
## Overview

The Simple Certificate Enrollment Protocol (SCEP) enables network devices — routers, switches, firewalls, MDM-managed endpoints — to automatically request and obtain certificates.

## Tabs

### Requests
View all SCEP enrollment requests:
- **Pending** — Awaiting manual approval (if auto-approve is off)
- **Approved** — Successfully issued
- **Rejected** — Denied by an administrator

### Configuration
Configure the SCEP server:
- **Enable/Disable** — Toggle the SCEP service
- **Signing CA** — Select which CA signs SCEP-enrolled certificates
- **CA Identifier** — The identifier devices use to locate the correct CA
- **Auto-Approve** — Automatically approve requests with valid challenge passwords

### Challenge Passwords
Manage per-CA challenge passwords. Devices must include a valid challenge password in their enrollment request to authenticate.

- **View password** — Show the current challenge for a CA
- **Regenerate** — Create a new challenge password (invalidates the old one)

### Information
Displays the SCEP endpoint URL and integration instructions.

## SCEP Enrollment Flow

1. Device sends a **GetCACert** request to get the CA certificate
2. Device generates a key pair and creates a CSR
3. Device wraps the CSR with the **challenge password** and sends a **PKCSReq**
4. UCM validates the challenge password
5. If auto-approve is on, UCM signs and returns the certificate
6. If auto-approve is off, an admin reviews and approves/rejects

## SCEP URL

\`\`\`
https://your-server:8443/scep
\`\`\`

Devices need this URL plus the CA identifier to enroll.

## Approving/Rejecting Requests

For pending requests (auto-approve disabled):
1. Review the request details (subject, key type, challenge)
2. Click **Approve** to sign and issue the certificate
3. Or click **Reject** with a reason

> ⚠ Challenge passwords are transmitted in the SCEP request. Always use HTTPS for the SCEP endpoint.

## Device Integration

### Cisco IOS
\`\`\`
crypto pki trustpoint UCM
  enrollment url https://your-server:8443/scep
  password <challenge-password>
\`\`\`

### Microsoft Intune / JAMF
Configure the SCEP profile with:
- Server URL: \`https://your-server:8443/scep\`
- Challenge: the password from UCM
`
  },

  // ===================================================================
  acme: {
    title: 'ACME',
    content: `
## Overview

UCM supports ACME (Automated Certificate Management Environment) in two modes:

- **ACME Client** — Obtain certificates from any RFC 8555-compliant CA (Let's Encrypt, ZeroSSL, Buypass, HARICA, or custom)
- **Local ACME Server** — Built-in ACME server for internal PKI automation with multi-CA support

## ACME Client

### Client Settings
Manage your ACME client configuration:
- **Environment** — Staging (testing) or Production (live certificates)
- **Contact Email** — Required for account registration
- **Auto-Renewal** — Automatically renew certificates before expiry
- **Certificate Key Type** — RSA-2048, RSA-4096, ECDSA P-256, or ECDSA P-384
- **Account Key Algorithm** — ES256, ES384, or RS256 for ACME account signing

### Custom ACME Server
Use any RFC 8555-compliant CA, not just Let's Encrypt:

| CA Provider | Directory URL |
|---|---|
| **Let's Encrypt** | *(default, leave empty)* |
| **ZeroSSL** | \`https://acme.zerossl.com/v2/DV90\` |
| **Buypass** | \`https://api.buypass.com/acme/directory\` |
| **HARICA** | \`https://acme-v02.harica.gr/acme/<token>/directory\` |
| **Google Trust** | \`https://dv.acme-v02.api.pki.goog/directory\` |

Set your CA's directory URL in **Settings** → **Custom ACME Server**.

### External Account Binding (EAB)
Some CAs require EAB credentials to link your ACME account with an existing account at the CA:

1. Register at your CA's portal to obtain **EAB Key ID** and **HMAC Key**
2. Enter both values in **Settings** → **Custom ACME Server**
3. The HMAC key is base64url-encoded (provided by the CA)

> 💡 EAB is required by ZeroSSL, HARICA, Google Trust Services, and most enterprise CAs.

### ECDSA vs RSA Keys

| Key Type | Size | Security | Performance |
|---|---|---|---|
| **RSA-2048** | 2048 bit | Standard | Baseline |
| **RSA-4096** | 4096 bit | Higher | Slower |
| **ECDSA P-256** | 256 bit | ≈ RSA-3072 | Much faster |
| **ECDSA P-384** | 384 bit | ≈ RSA-7680 | Faster |

ECDSA keys are recommended for modern deployments — smaller, faster, and equally secure.

### DNS Providers
Configure DNS-01 challenge providers for domain validation. Supported providers include:
- Cloudflare
- AWS Route 53
- Google Cloud DNS
- DigitalOcean
- OVH
- And more

Each provider requires API credentials specific to the DNS service.

### Domains
Map your domains to DNS providers. When requesting a certificate for a domain, UCM uses the mapped provider to create DNS-01 challenge records.

1. Click **Add Domain**
2. Enter the domain name (e.g., \`example.com\` or \`*.example.com\`)
3. Select the DNS provider
4. Click **Save**

> 💡 Wildcard certificates (\`*.example.com\`) require DNS-01 validation.

## Local ACME Server

### Configuration
- **Enable/Disable** — Toggle the built-in ACME server
- **Default CA** — Select which CA signs certificates by default
- **Terms of Service** — Optional ToS URL for clients

### ACME Directory URL
\`\`\`
https://your-server:8443/acme/directory
\`\`\`

Clients like certbot, acme.sh, or Caddy use this URL to discover the ACME endpoints.

### Local Domains (Multi-CA)
Map internal domains to specific CAs. This allows different domains to be signed by different CAs.

1. Click **Add Domain**
2. Enter the domain (e.g., \`internal.corp\` or \`*.dev.local\`)
3. Select the **Issuing CA**
4. Enable/disable **Auto-Approve**
5. Click **Save**

### CA Resolution Order
When an ACME client requests a certificate, UCM determines the signing CA in this order:
1. **Local Domain mapping** — Exact match, then parent domain match
2. **DNS Domain mapping** — The CA configured for the DNS provider
3. **Global default** — The CA set in ACME server configuration
4. **First available** — Any CA with a private key

### Accounts
View registered ACME client accounts:
- Account ID and contact email
- Registration date
- Number of orders

### History
Browse all certificate issuance orders:
- Order status (pending, valid, invalid, ready)
- Domain names requested
- Signing CA used
- Issuance timestamp

## Using certbot

\`\`\`
# Register account (Let's Encrypt — default)
certbot register --agree-tos --email admin@example.com

# Register with custom ACME CA + EAB
certbot register \\
  --server 'https://acme.zerossl.com/v2/DV90' \\
  --eab-kid 'your-key-id' \\
  --eab-hmac-key 'your-hmac-key' \\
  --agree-tos --email admin@example.com

# Request certificate with ECDSA key
certbot certonly --server https://your-server:8443/acme/directory \\
  --standalone -d myserver.internal.corp \\
  --key-type ecdsa --elliptic-curve secp256r1

# Renew
certbot renew --server https://your-server:8443/acme/directory
\`\`\`

## Using acme.sh

\`\`\`
# Default (Let's Encrypt)
acme.sh --issue -d example.com --standalone

# Custom ACME CA with EAB and ECDSA
acme.sh --issue \\
  --server 'https://acme-v02.harica.gr/acme/TOKEN/directory' \\
  --eab-kid 'your-key-id' \\
  --eab-hmac-key 'your-hmac-key' \\
  --keylength ec-256 \\
  -d example.com --standalone
\`\`\`

> ⚠ For internal ACME, clients must trust the UCM CA. Install the Root CA certificate in the client's trust store.
`
  },

  // ===================================================================
  est: {
    title: 'EST Protocol',
    content: `
## Overview

Enrollment over Secure Transport (EST) is defined in **RFC 7030** and provides certificate enrollment, re-enrollment, and CA certificate retrieval over HTTPS. EST is the modern replacement for SCEP, offering stronger security through mutual TLS (mTLS) authentication.

## Configuration

### Settings Tab

1. **Enable EST** — Toggle the EST protocol on or off
2. **Signing CA** — Select which Certificate Authority signs EST-enrolled certificates
3. **Authentication** — Configure HTTP Basic Auth credentials (username and password)
4. **Certificate Validity** — Default validity period for EST-issued certificates (in days)

### Saving Configuration

Click **Save** to apply changes. The EST endpoints become available immediately when enabled.

## Authentication

EST supports two authentication methods:

### Mutual TLS (mTLS) — Recommended

The client presents a certificate during the TLS handshake. UCM validates the certificate and authenticates the client automatically.

- **Strongest method** — cryptographic client identity
- **Required for** \`/simplereenroll\` — the client must present its current certificate
- **Depends on** proper TLS termination config (reverse proxy must pass \`SSL_CLIENT_CERT\` to UCM)

### HTTP Basic Auth — Fallback

Username and password authentication over HTTPS. Configured in EST Settings.

- **Simpler to set up** — no client certificate needed
- **Less secure** — credentials transmitted per request (protected by HTTPS)
- **Use when** mTLS infrastructure is not available

## EST Endpoints

All endpoints are under \`/.well-known/est/\`:

### GET /cacerts
Retrieve the CA certificate chain. **No authentication required.**

Use this to bootstrap trust — clients fetch the CA cert before enrollment.

\`\`\`bash
curl -k https://your-server:8443/.well-known/est/cacerts | \\
  base64 -d | openssl pkcs7 -inform DER -print_certs
\`\`\`

### POST /simpleenroll
Submit a PKCS#10 CSR and receive a signed certificate.

Requires authentication (mTLS or Basic Auth).

\`\`\`bash
# Using curl with Basic Auth
curl -k --user est-user:est-password \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @csr.pem \\
  https://your-server:8443/.well-known/est/simpleenroll
\`\`\`

### POST /simplereenroll
Renew an existing certificate. **Requires mTLS** — the client must present the certificate being renewed.

\`\`\`bash
curl -k --cert client.pem --key client.key \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @csr.pem \\
  https://your-server:8443/.well-known/est/simplereenroll
\`\`\`

### GET /csrattrs
Get the CSR attributes (OIDs) recommended by the server.

### POST /serverkeygen
Server generates a key pair and returns the certificate along with the private key. Useful when the client cannot generate keys locally.

## Information Tab

The Information tab displays:
- **Endpoint URLs** — Copy-paste ready URLs for each EST operation
- **Enrollment Statistics** — Number of enrollments, re-enrollments, and errors
- **Last activity** — Most recent EST operations from audit logs

## Integration Examples

### Using est client (libest)
\`\`\`bash
estclient -s your-server -p 8443 \\
  --srp-user est-user --srp-password est-password \\
  -o /tmp/certs --enroll
\`\`\`

### Using OpenSSL
\`\`\`bash
# Fetch CA certs
curl -k https://your-server:8443/.well-known/est/cacerts | \\
  base64 -d > cacerts.p7

# Generate CSR
openssl req -new -newkey rsa:2048 -nodes \\
  -keyout client.key -out client.csr \\
  -subj "/CN=my-device/O=MyOrg"

# Enroll (Basic Auth)
curl -k --user est-user:est-password \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @<(openssl req -in client.csr -outform DER | base64) \\
  https://your-server:8443/.well-known/est/simpleenroll | \\
  base64 -d | openssl x509 -inform DER -out client.pem
\`\`\`

### Windows (certutil)
\`\`\`cmd
certutil -enrollmentServerURL add \\
  "https://your-server:8443/.well-known/est" \\
  kerberos
\`\`\`

## EST vs SCEP

| Feature | EST | SCEP |
|---------|-----|------|
| Transport | HTTPS (TLS) | HTTP or HTTPS |
| Authentication | mTLS + Basic Auth | Challenge password |
| Standard | RFC 7030 (2013) | RFC 8894 (2020, but legacy) |
| Key generation | Server-side option | Client-only |
| Renewal | mTLS re-enrollment | Re-enrollment |
| Security | Strong (TLS-based) | Weaker (shared secret) |
| Recommendation | ✅ Preferred for new | Legacy devices only |

> 💡 Use EST for new deployments. Use SCEP only for legacy network devices that don't support EST.
`
  },

  // ===================================================================
  tsa: {
    title: 'TSA Protocol',
    content: `
## Overview

Time Stamp Authority (TSA) implements **RFC 3161** to provide trusted timestamps that cryptographically prove a document, hash, or digital signature existed at a specific point in time. TSA is widely used for code signing, legal compliance, long-term archival, and audit trails.

## How It Works

1. **Client creates a timestamp request** — hashes a file with SHA-256/SHA-512 and creates a \`TimeStampReq\` (ASN.1 DER-encoded)
2. **Client sends request to TSA** — HTTP POST to the \`/tsa\` endpoint with \`Content-Type: application/timestamp-query\`
3. **UCM signs the timestamp** — the configured CA signs the hash + current time into a \`TimeStampResp\`
4. **Client receives and stores the response** — the \`.tsr\` file can later prove the document existed at that time

## Configuration

### Settings Tab

1. **Enable TSA** — Toggle the TSA server on or off
2. **Signing CA** — Select which Certificate Authority signs timestamp tokens
3. **Policy OID** — Object Identifier for the TSA policy (e.g., \`1.2.3.4.1\`), included in every timestamp response

### Choosing a Signing CA

The signing CA's private key is used to sign every timestamp token. Best practices:

- Use a **dedicated sub-CA** for timestamping rather than your root CA
- The CA certificate should include the **id-kp-timeStamping** Extended Key Usage (OID 1.3.6.1.5.5.7.3.8)
- Ensure the CA certificate has **sufficient validity** — timestamps must remain verifiable for years

### Policy OID

The Policy OID identifies the TSA policy under which timestamps are issued. It is embedded in every \`TimeStampResp\`.

- Default: \`1.2.3.4.1\` (placeholder)
- For production, register an OID under your organization's arc or use one from your CP/CPS

## Information Tab

The Information tab displays:

- **TSA Endpoint URL** — Copy-paste ready URL for client configuration
- **Usage Examples** — OpenSSL commands for creating requests, sending them, and verifying responses
- **Statistics** — Total timestamp requests processed (successful and failed)

## Usage Examples

### Create a Timestamp Request

\`\`\`bash
# Hash a file and create a timestamp request
openssl ts -query -data file.txt -sha256 -no_nonce -out request.tsq
\`\`\`

### Send Request to TSA

\`\`\`bash
# Send the request and receive a timestamp response
curl -s -H "Content-Type: application/timestamp-query" \\
  --data-binary @request.tsq \\
  https://your-server:8443/tsa -o response.tsr
\`\`\`

### Verify a Timestamp

\`\`\`bash
# Verify the timestamp response against the original file
openssl ts -verify -data file.txt -in response.tsr \\
  -CAfile ca-chain.pem
\`\`\`

### Code Signing with Timestamps

When signing code, add the TSA URL to ensure signatures remain valid after certificate expiry:

\`\`\`bash
# Sign with timestamp (osslsigncode)
osslsigncode sign -certs cert.pem -key key.pem \\
  -ts https://your-server:8443/tsa \\
  -in app.exe -out app-signed.exe

# Sign with timestamp (signtool.exe on Windows)
signtool sign /fd SHA256 /tr https://your-server:8443/tsa \\
  /td SHA256 /f cert.pfx app.exe
\`\`\`

### PDF Document Timestamps

\`\`\`bash
# Create a detached timestamp for a PDF
openssl ts -query -data document.pdf -sha256 -cert \\
  -out document.tsq

curl -s -H "Content-Type: application/timestamp-query" \\
  --data-binary @document.tsq \\
  https://your-server:8443/tsa -o document.tsr
\`\`\`

## Protocol Details

| Property | Value |
|----------|-------|
| RFC | 3161 (Internet X.509 PKI TSP) |
| Endpoint | \`/tsa\` (POST) |
| Content-Type | \`application/timestamp-query\` |
| Response Type | \`application/timestamp-reply\` |
| Hash Algorithms | SHA-256, SHA-384, SHA-512, SHA-1 (legacy) |
| Authentication | None (public endpoint) |
| Transport | HTTP or HTTPS |

## Security Considerations

- The TSA endpoint is **public** — no authentication is required (same as CRL/OCSP)
- Each timestamp response is **signed** by the CA key — clients verify the signature to ensure authenticity
- Use **SHA-256 or stronger** hash algorithms when creating requests (SHA-1 is accepted but discouraged)
- The TSA does **not** see the original document — only the hash is transmitted
- Consider **rate limiting** if the TSA endpoint is exposed to the internet

> 💡 Timestamps are essential for code signing: they ensure your signed software remains trusted even after the signing certificate expires.
`
  },

  // ===================================================================
  truststore: {
    title: 'Trust Store',
    content: `
## Overview

The Trust Store manages trusted CA certificates used for chain validation. Import root and intermediate CAs from external sources or synchronize with the operating system's trust store.

## Certificate Categories

- **Root CA** — Self-signed trust anchors
- **Intermediate** — CAs signed by root or other intermediates
- **Client Auth** — Certificates for mTLS client authentication
- **Code Signing** — Certificates for code signature verification
- **Custom** — Manually categorized certificates

## Importing Certificates

### From File
Upload certificate files in these formats:
- **PEM** — Base64-encoded (single or bundled)
- **DER** — Binary format
- **PKCS#7 (P7B)** — Certificate chain

### From URL
Fetch a certificate from a remote HTTPS endpoint. UCM downloads and imports the server's certificate chain.

### Paste PEM
Paste PEM-encoded certificate text directly into the text area.

### Sync from System
Import all trusted CAs from the operating system's trust store. This populates UCM with the same root CAs trusted by the OS (e.g., Mozilla's CA bundle on Linux).

> 💡 Sync from System is a one-time import. Changes to the OS trust store are not automatically reflected.

## Managing Entries

- **Filter by purpose** — Narrow the list by certificate category
- **Search** — Find certificates by subject name
- **Export** — Download individual certificates in PEM format
- **Delete** — Remove a certificate from the trust store

## Use Cases

### Chain Validation
When verifying a certificate chain, UCM checks the trust store for recognized root CAs.

### mTLS
Client certificates presented during mutual TLS authentication are validated against the trust store.

### ACME
When UCM acts as an ACME client (Let's Encrypt), the trust store is used to verify the ACME CA's certificate.
`
  },

  // ===================================================================
  usersGroups: {
    title: 'Users & Groups',
    content: `
## Overview

Manage user accounts, groups, and role assignments. Users authenticate to UCM via password, SSO, WebAuthn, or mTLS. Groups allow bulk permission management.

## Users Tab

### Creating a User
1. Click **Create User**
2. Enter **username** (unique, cannot be changed later)
3. Enter **email** (used for notifications and recovery)
4. Set an **initial password**
5. Select a **role** (Admin, Operator, Auditor, Viewer, or custom)
6. Click **Create**

### User Status
- **Active** — Can log in and perform actions
- **Disabled** — Cannot log in, data is preserved

Toggle a user's status without deleting their account.

### Password Reset
Admins can reset any user's password. The user will be prompted to change it on next login.

### API Keys
Each user can have multiple API keys for programmatic access. API keys inherit the user's role permissions. See the Account page for managing your own keys.

## Groups Tab

### Creating a Group
1. Click **Create Group**
2. Enter a **name** and optional description
3. Assign a **role** (group members inherit this role)
4. Click **Create**

### Managing Members
- Click a group to see its members
- Use the **transfer panel** to add/remove users
- Users can belong to multiple groups

### Role Inheritance
A user's effective permissions are the **union** of:
- Their directly assigned role
- All roles from groups they belong to

## Roles

### System Roles
- **Admin** — Full access to all features
- **Operator** — Can manage certificates, CAs, CSRs but not system settings
- **Auditor** — Read-only access to all operational data for compliance and audit
- **Viewer** — Read-only access to certificates, CAs, and templates

### Custom Roles
Create roles with granular permissions on the **RBAC** page.

> 💡 Use groups to manage team permissions rather than assigning roles to individual users.
`
  },

  // ===================================================================
  rbac: {
    title: 'Role-Based Access Control',
    content: `
## Overview

RBAC provides fine-grained permission management. Define custom roles with specific permissions and assign them to users or groups.

## System Roles

Four built-in roles that cannot be modified or deleted:

- **Admin** — Full access to everything
- **Operator** — Manage certificates, CAs, CSRs, templates. No access to system settings, users, or RBAC
- **Auditor** — Read-only access to all operational data (certificates, CAs, ACME, SCEP, HSM, audit logs, policies, groups) but not settings or user management
- **Viewer** — Basic read-only access to certificates, CAs, CSRs, templates, and trust store

## Custom Roles

### Creating a Custom Role
1. Click **Create Role**
2. Enter a **name** and optional description
3. Configure permissions using the **permission matrix**
4. Click **Create**

### Permission Matrix
Permissions are organized by category:
- **CAs** — Create, read, update, delete, import, export
- **Certificates** — Issue, read, revoke, renew, export, delete
- **CSRs** — Create, read, sign, delete
- **Templates** — Create, read, update, delete
- **Users** — Create, read, update, delete
- **Groups** — Create, read, update, delete
- **Settings** — Read, update
- **Audit** — Read, export, cleanup
- **ACME** — Configure, manage accounts
- **SCEP** — Configure, approve requests
- **Trust Store** — Manage trusted certificates
- **HSM** — Manage providers and keys
- **Backup** — Create, restore

### Category Toggles
Click a category header to enable/disable all permissions in that category at once.

### Coverage Indicator
A percentage badge shows how much of the total permission set the role covers. 100% = Admin equivalent.

## Assigning Roles

Roles are assigned:
- **Directly** — On the Users page, edit a user and select a role
- **Via Groups** — Assign a role to a group; all members inherit it

## Effective Permissions

A user's effective permissions are computed as the union of:
1. Their directly assigned role's permissions
2. All roles from groups they belong to

The most permissive rule wins (additive model, no deny rules).

> ⚠ System roles cannot be edited or deleted. Create custom roles for specific needs.
`
  },

  // ===================================================================
  auditLogs: {
    title: 'Audit Logs',
    content: `
## Overview

Complete audit trail of all operations in UCM. Every action — certificate issuance, revocation, user login, setting change — is logged with details about who, what, when, and where.

## Log Entry Details

Each log entry records:
- **Timestamp** — When the action occurred
- **User** — Who performed the action
- **Action** — What was done (create, update, delete, login, etc.)
- **Resource** — What was affected (certificate, CA, user, etc.)
- **Status** — Success or failure
- **IP Address** — Source IP of the request
- **User Agent** — Client application identifier
- **Details** — Additional context (error messages, changed values)

## Filtering

### By Action Type
Filter by operation category:
- Certificate operations (issue, revoke, renew, export)
- CA operations (create, import, delete)
- User operations (login, logout, create, update)
- System operations (settings change, backup, restore)

### By User
Show only actions performed by a specific user.

### By Status
- **Success** — Operations that completed successfully
- **Failed** — Operations that failed (authentication failures, permission denied, errors)

### By Date Range
Set **From** and **To** dates to narrow the time window.

### Text Search
Free-text search across all log fields.

## Export

Export filtered logs in:
- **JSON** — Machine-readable, includes all fields
- **CSV** — Spreadsheet-compatible, includes key fields

Exports include only the currently filtered results.

## Cleanup

Purge old logs based on retention period:
1. Click **Cleanup**
2. Set the retention period in days
3. Confirm the cleanup

> ⚠ Log cleanup is irreversible. Export important logs before purging.

## Integrity Verification

Click **Verify Integrity** to check the audit log chain. UCM uses hash chaining to detect if any log entries have been tampered with or deleted.

## Syslog Forwarding

Configure remote syslog forwarding in **Settings → Audit** to send log events to an external SIEM or syslog server in real-time.
`
  },

  // ===================================================================
  settings: {
    title: 'Settings',
    content: `
## Overview

System-wide configuration organized into tabs. Changes take effect immediately unless noted otherwise.

## General

- **Instance Name** — Displayed in the browser title and emails
- **Hostname** — The server's fully qualified domain name
- **Default Validity** — Default certificate validity period in days
- **Expiry Warning Threshold** — Days before expiry to trigger warnings

## Appearance

- **Theme** — Light, Dark, or System (follows OS preference)
- **Accent Color** — Primary color used for buttons, links, and highlights
- **Force Desktop Mode** — Disable responsive mobile layout
- **Sidebar Behavior** — Collapsed or expanded by default

## Email (SMTP)

Configure SMTP for email notifications (expiry alerts, user invitations):
- **SMTP Host** and **Port**
- **Username** and **Password**
- **Encryption** — None, STARTTLS, or SSL/TLS
- **From Address** — Sender email address
- **Content Type** — HTML, Plain Text, or Both
- **Alert Recipients** — Add multiple recipients using the tag input

Click **Test** to send a test email and verify the configuration.

### Email Template Editor

Click **Edit Template** to open the split-pane template editor in a floating window:
- **HTML tab** — Edit the HTML email template with live preview on the right
- **Plain Text tab** — Edit the plain text version for email clients that don't support HTML
- Available variables: \`{{title}}\`, \`{{content}}\`, \`{{datetime}}\`, \`{{instance_url}}\`, \`{{logo}}\`, \`{{title_color}}\`
- Click **Reset to Default** to restore the built-in UCM-branded template
- The window is resizable and draggable for comfortable editing

### Expiry Alerts

When SMTP is configured, enable automatic certificate expiry alerts:
- Toggle alerts on/off
- Select warning thresholds (90d, 60d, 30d, 14d, 7d, 3d, 1d)
- Run **Check Now** to trigger an immediate scan

## Security

### Password Policy
- Minimum length (8-32 characters)
- Require uppercase, lowercase, numbers, special characters
- Password expiry (days)
- Password history (prevent reuse)

### Session Management
- Session timeout (minutes of inactivity)
- Maximum concurrent sessions per user

### Rate Limiting
- Login attempt limit per IP
- Lockout duration after exceeding the limit

### IP Restrictions
Allow or deny access from specific IP addresses or CIDR ranges.

### 2FA Enforcement
Require all users to enable two-factor authentication.

> ⚠ Test IP restrictions carefully before applying them. Incorrect rules can lock out all users.

## SSO (Single Sign-On)

### SAML 2.0
- Provide your IDP with the **SP Metadata URL**: \`/api/v2/sso/saml/metadata\`
- Or manually configure: upload/link IDP metadata XML, configure Entity ID and ACS URL
- Map IDP attributes to UCM user fields (username, email, role)

### OAuth2 / OIDC
- Authorization URL and Token URL
- Client ID and Client Secret
- User Info URL (for attribute retrieval)
- Scopes (openid, profile, email)
- Auto-create users on first SSO login

### LDAP
- Server hostname, port (389/636), SSL toggle
- Bind DN and password (service account)
- Base DN and user filter
- Attribute mapping (username, email, full name)

> 💡 Always keep a local admin account as fallback in case SSO breaks.

## Backup

### Manual Backup
Click **Create Backup** to generate a database snapshot. Backups include all certificates, CAs, keys, settings, and audit logs.

### Scheduled Backup
Configure automatic backups:
- Frequency (daily, weekly, monthly)
- Retention count (number of backups to keep)

### Restore
Upload a backup file to restore UCM to a previous state.

> ⚠ Restoring a backup replaces ALL current data.

## Audit

- **Log retention** — Auto-cleanup old logs after N days
- **Syslog forwarding** — Send events to a remote syslog server (UDP/TCP/TLS)
- **Integrity verification** — Enable hash chaining for tamper detection

## Database

Information about the UCM database:
- Path on disk
- File size
- Migration version
- SQLite version

## HTTPS

Manage the TLS certificate used by the UCM web interface:
- View the current certificate details
- Import a new certificate (PEM or PKCS#12)
- Generate a self-signed certificate

> ⚠ Changing the HTTPS certificate requires a service restart.

## Updates

- Check for new UCM versions from GitHub releases
- View the changelog for available updates
- Current version and build information
- **Auto-update**: on supported installations (DEB/RPM), click **Update Now** to download and install the latest version automatically
- **Include pre-releases**: toggle to also check for release candidates (rc)

## Webhooks

Configure HTTP webhooks to notify external systems on events:

### Supported Events
- Certificate issued, revoked, expired, renewed
- CA created, deleted
- User login, logout
- Backup created

### Creating a Webhook
1. Click **Add Webhook**
2. Enter the **URL** (must be HTTPS)
3. Select the **events** to subscribe to
4. Optionally set a **secret** for HMAC signature verification
5. Click **Create**

### Testing
Click **Test** to send a sample event to the webhook URL and verify it's reachable.
`
  },

  // ===================================================================
  account: {
    title: 'My Account',
    content: `
## Overview

Manage your personal profile, security settings, and API keys.

## Profile

- **Full Name** — Your display name shown across UCM
- **Email** — Used for notifications, password recovery, and ACME registration
- **Account Info** — Creation date, last login timestamp, total login count

## Security

### Password Change
Change your current password. Must comply with the system password policy (minimum length, complexity requirements).

### Two-Factor Authentication (TOTP)
Add a time-based one-time password using any authenticator app:

1. Click **Enable 2FA**
2. Scan the QR code with your authenticator app (Google Authenticator, Authy, 1Password, etc.)
3. Enter the 6-digit code to confirm
4. Save the **recovery codes** — they are shown only once

> ⚠ If you lose access to your authenticator and recovery codes, an admin must disable your 2FA.

### Security Keys (WebAuthn/FIDO2)
Register hardware security keys or biometric authenticators:
- YubiKey
- Fingerprint reader
- Windows Hello
- Touch ID

1. Click **Register Security Key**
2. Enter a name for the key
3. Follow the browser prompt to authenticate
4. The key appears in your registered credentials list

### mTLS Certificates
Manage client certificates for mutual TLS authentication:
- Upload a client certificate
- Download your registered certificates
- Delete old certificates

## API Keys

### Creating an API Key
1. Click **Create API Key**
2. Enter a **name** (descriptive, e.g., "CI/CD Pipeline")
3. Optionally set an **expiration date**
4. Click **Create**
5. Copy the key immediately — it is shown only once

### Using API Keys
Include the key in the \`X-API-Key\` header:

\`\`\`
X-API-Key: <your-api-key>
\`\`\`

### Permissions
API keys inherit your user role's permissions. They cannot have more access than your account.

### Revoking Keys
Click **Delete** to immediately invalidate an API key. Active sessions using the key will be terminated.

> 💡 Use short-lived API keys with expiration dates for CI/CD and automation.
`
  },

  // ===================================================================
  importExport: {
    title: 'Import & Export',
    content: `
## Overview

Import certificates from external sources and export your PKI data for backup or migration.

## Smart Import

The Smart Import wizard auto-detects file types and processes them:

### Supported Formats
- **PEM** — Single or bundled certificates, CAs, and keys
- **DER** — Binary certificate or key
- **PKCS#12 (P12/PFX)** — Certificate + key + chain (requires password)
- **PKCS#7 (P7B)** — Certificate chain without keys

### How It Works
1. Click **Import** or drag files onto the drop zone
2. UCM analyzes each file and identifies its contents
3. Review the detected items (CAs, certificates, keys)
4. Click **Import** to add them to UCM

> 💡 Smart Import handles PEM bundles with multiple certificates in a single file. It automatically distinguishes CAs from end-entity certificates.

## OPNsense Integration

Sync certificates and CAs from an OPNsense firewall:

### Setup
1. In OPNsense, create an API key (System → Access → Users → API Keys)
2. In UCM, enter the OPNsense URL, API key, and API secret
3. Click **Test Connection** to verify

### Import
1. Click **Connect** to fetch available certificates and CAs
2. Select the items you want to import
3. Click **Import Selected**

UCM imports certificates with their private keys (if available) and preserves the CA hierarchy.

## Export Certificates

Bulk export all certificates:
- **PEM** — Individual PEM files
- **P7B Bundle** — All certificates in a single PKCS#7 file
- **ZIP** — All certificates as individual PEM files in a ZIP archive

## Export CAs

Bulk export all Certificate Authorities:
- **PEM** — Certificate chain in PEM format
- **Full chain** — Root → Intermediate → Sub-CA

## Migration Between UCM Instances

To migrate from one UCM instance to another:
1. Create a **backup** on the source (Settings → Backup)
2. Install UCM on the destination
3. **Restore** the backup on the destination

This preserves all data: certificates, CAs, keys, users, settings, and audit logs.
`
  },

  // ===================================================================
  certTools: {
    title: 'Certificate Tools',
    content: `
## Overview

A toolkit for inspecting, converting, and verifying certificates without leaving UCM.

## SSL Checker

Inspect a remote server's SSL/TLS certificate:

1. Enter the **hostname** (e.g., \`google.com\`)
2. Optionally change the **port** (default: 443)
3. Click **Check**

Results include:
- Certificate subject and issuer
- Validity dates
- SANs (Subject Alternative Names)
- Key type and size
- Full certificate chain
- TLS protocol version

## CSR Decoder

Parse and display CSR contents:

1. Paste a CSR in PEM format
2. Click **Decode**

Shows: Subject, SANs, key algorithm, key size, signature algorithm.

## Certificate Decoder

Parse and display certificate details:

1. Paste a certificate in PEM format
2. Click **Decode**

Shows: Subject, Issuer, SANs, validity, serial number, key usage, extensions, fingerprints.

## Key Matcher

Verify that a certificate, CSR, and private key belong together:

1. Paste the **certificate** PEM
2. Paste the **private key** PEM (optionally encrypted — provide password)
3. Optionally paste a **CSR** PEM
4. Click **Match**

UCM compares the modulus (RSA) or public key (EC) hashes. A match confirms they form a valid pair.

## Converter

Convert between certificate and key formats:

### PEM → DER
Converts a Base64-encoded PEM to binary DER format.

### PEM → PKCS#12
Creates a password-protected P12/PFX file from:
- Certificate PEM
- Private key PEM
- Optional chain certificates
- Password for the P12 file

### PKCS#12 → PEM
Extracts certificate, key, and chain from a P12 file:
- Upload the P12 file
- Enter the password
- Download the extracted PEM components

### PEM → PKCS#7
Bundles multiple certificates into a single P7B file (no keys).

> 💡 The converter preserves the full certificate chain when creating PKCS#12 files.
`
  },

  // ===================================================================
  operations: {
    title: 'Operations',
    content: `
## Overview

Bulk operations and data management. Perform batch actions across multiple resources simultaneously.

## Import/Export Tab

Same as the Import/Export page — Smart Import wizard and bulk export functionality.

## OPNsense Tab

Same as the Import/Export OPNsense integration — connect, browse, and import from OPNsense.

## Bulk Actions

Perform batch operations on multiple resources at once.

### How It Works
1. Select the **resource type** (Certificates, CAs, CSRs, Templates, Users)
2. Browse available items in the **left panel**
3. Move items to the **right panel** (selected) using the transfer arrows
4. Choose the **action** to perform
5. Confirm and execute

### Available Actions by Resource

#### Certificates
- **Bulk Revoke** — Revoke multiple certificates at once
- **Bulk Renew** — Renew multiple certificates
- **Bulk Export** — Download selected certificates as a bundle
- **Bulk Delete** — Permanently remove selected certificates

#### CAs
- **Bulk Export** — Download selected CAs
- **Bulk Delete** — Remove selected CAs (must have no children)

#### CSRs
- **Bulk Sign** — Sign multiple CSRs with a selected CA
- **Bulk Delete** — Remove selected CSRs

#### Templates
- **Bulk Export** — Export as JSON
- **Bulk Delete** — Remove selected templates

#### Users
- **Bulk Disable** — Deactivate selected user accounts
- **Bulk Delete** — Permanently remove selected users

> ⚠ Bulk operations are irreversible. Always create a backup before performing bulk deletes or revocations.

> 💡 Use the search and filter in the left panel to quickly find specific items.
`
  },

  // ===================================================================
  hsm: {
    title: 'Hardware Security Modules',
    content: `
## Overview

Hardware Security Modules (HSMs) provide tamper-resistant storage for cryptographic keys. Private keys stored on an HSM never leave the hardware, providing the highest level of key protection.

## Supported Providers

### PKCS#11
The industry standard HSM interface. Supported devices:
- **Thales Luna** / **SafeNet**
- **Entrust nShield**
- **SoftHSM** (software-based, for testing)
- Any PKCS#11-compliant device

> 💡 **Docker**: SoftHSM is pre-installed in the Docker image. On first start, a default token is auto-initialized and registered as the \`SoftHSM-Default\` provider — ready to use immediately.

Configuration:
- **Library Path** — Path to the PKCS#11 shared library (.so/.dll)
- **Slot** — HSM slot number
- **PIN** — User PIN for authentication

### AWS CloudHSM
Amazon Web Services cloud-based HSM:
- **Cluster ID** — CloudHSM cluster identifier
- **Region** — AWS region
- **Credentials** — AWS access key and secret

### Azure Key Vault
Microsoft Azure managed key storage:
- **Vault URL** — Azure Key Vault endpoint
- **Tenant ID** — Azure AD tenant
- **Client ID/Secret** — Service principal credentials

### Google Cloud KMS
Google Cloud Key Management Service:
- **Project** — GCP project ID
- **Location** — KMS key ring location
- **Key Ring** — Name of the key ring
- **Credentials** — Service account JSON key

## Managing Providers

### Adding a Provider
1. Click **Add Provider**
2. Select the **provider type**
3. Enter the connection details
4. Click **Test Connection** to verify
5. Click **Save**

### Testing Connection
Always test the connection after creating or modifying a provider. UCM verifies it can communicate with the HSM and authenticate.

### Provider Status
Each provider shows a connection status indicator:
- **Connected** — HSM is reachable and authenticated
- **Disconnected** — Cannot reach the HSM
- **Error** — Authentication or configuration issue

## Key Management

### Generating Keys
1. Select a connected provider
2. Click **Generate Key**
3. Choose the algorithm (RSA 2048/4096, ECDSA P-256/P-384)
4. Enter a key label/alias
5. Click **Generate**

The key is created directly on the HSM. UCM stores only a reference.

### Using HSM Keys
When creating a CA, select an HSM provider and key instead of generating a software key. The CA's signing operations are performed on the HSM.

> ⚠ Keys generated on an HSM cannot be exported. If you lose access to the HSM, you lose the keys.

> 💡 Use SoftHSM for development and testing before deploying with physical HSMs.
`
  },

  // ===================================================================
  sso: {
    title: 'Single Sign-On',
    content: `
## Overview

SSO allows users to authenticate using their organization's Identity Provider (IDP), eliminating the need for separate UCM credentials. UCM supports **SAML 2.0**, **OAuth2/OIDC**, and **LDAP**.

## SAML 2.0

### SP Metadata URL

UCM provides a **Service Provider (SP) Metadata URL** that you can give to your IDP for automatic configuration:

\`\`\`
https://your-ucm-host:8443/api/v2/sso/saml/metadata
\`\`\`

This URL returns a SAML 2.0 compliant XML document containing:
- **Entity ID** — UCM's service provider identifier
- **ACS URL** — Assertion Consumer Service endpoint (HTTP-POST)
- **SLO URL** — Single Logout Service endpoint
- **Signing Certificate** — UCM's HTTPS certificate for signing verification
- **NameID Format** — Requested name identifier format

Copy this URL into your IDP's "Add Service Provider" or "SAML Application" configuration.

> ⚠️ **Important:** UCM's HTTPS certificate must be **trusted by the IDP**. If the IDP cannot validate the certificate (e.g., self-signed or issued by a private CA), it will reject the metadata as invalid. Import UCM's CA certificate into the IDP's trust store, or use a certificate signed by a publicly trusted CA.

### Configuration
1. Obtain the IDP metadata URL or XML file from your identity provider
2. In UCM, go to **Settings → SSO**
3. Click **Add Provider** → SAML
4. Enter the **IDP Metadata URL** — UCM auto-populates Entity ID, SSO/SLO URLs, and certificate
5. Or paste the IDP metadata XML directly
6. Configure **attribute mapping** (username, email, groups)
7. Click **Save** and **Enable**

### Attribute Mapping
Map IDP SAML attributes to UCM user fields:
- \`username\` → UCM username (required)
- \`email\` → UCM email (required)
- \`groups\` → UCM group membership (optional)

## OAuth2 / OIDC

### Configuration
1. Register UCM as a client in your OAuth2/OIDC provider
2. Set the **Redirect URI** to: \`https://your-ucm-host:8443/api/v2/sso/callback/oauth2\`
3. Copy the **Client ID** and **Client Secret**
4. In UCM, go to **Settings → SSO**
5. Click **Add Provider** → OAuth2
6. Enter the **Authorization URL** and **Token URL**
7. Enter the **User Info URL** (for fetching user attributes after login)
8. Enter Client ID and Secret
9. Configure scopes (openid, profile, email)
10. Click **Save** and **Enable**

### Auto-Create Users
When enabled, a new UCM user account is automatically created on first SSO login, using the IDP-provided attributes. The default role is assigned.

## LDAP

### Configuration
1. In UCM, go to **Settings → SSO**
2. Click **Add Provider** → LDAP
3. Enter the **LDAP Server** hostname and **Port** (389 for LDAP, 636 for LDAPS)
4. Enable **Use SSL** for encrypted connections
5. Enter the **Bind DN** and **Bind Password** (service account credentials)
6. Enter the **Base DN** (search base for user lookups)
7. Configure the **User Filter** (e.g., \`(uid={username})\` or \`(sAMAccountName={username})\` for AD)
8. Map LDAP attributes: **username**, **email**, **full name**
9. Click **Test Connection** to verify, then **Save** and **Enable**

### Active Directory
For Microsoft Active Directory, use:
- Port: **389** (or 636 with SSL)
- User Filter: \`(sAMAccountName={username})\`
- Username attr: \`sAMAccountName\`
- Email attr: \`mail\`
- Full name attr: \`displayName\`

## Login Flow
1. User clicks **Login with SSO** on the UCM login page (or enters LDAP credentials)
2. For SAML/OAuth2: user is redirected to the IDP, authenticates, then redirected back
3. For LDAP: credentials are verified directly against the LDAP server
4. UCM creates or updates the user account
5. User is logged in

> ⚠ Always keep at least one local admin account as fallback in case SSO misconfiguration locks everyone out.

> 💡 Test SSO with a non-admin account first before making it the primary authentication method.

> 💡 Use the **Test Connection** button to verify your configuration before enabling a provider.
`
  },

  // ===================================================================
  security: {
    title: 'Security Settings',
    content: `
## Overview

System-wide security configuration affecting all user accounts and access patterns.

## Password Policy

### Complexity Requirements
- **Minimum length** — 8 to 32 characters
- **Require uppercase** — At least one uppercase letter
- **Require lowercase** — At least one lowercase letter
- **Require numbers** — At least one digit
- **Require special characters** — At least one symbol

### Password Expiry
Force users to change their password after a set number of days. Set to 0 to disable.

### Password History
Prevent reuse of the last N passwords. Users cannot set a password matching any of their previous N passwords.

## Session Management

### Session Timeout
Automatically log out users after N minutes of inactivity. Applies to web UI sessions only, not API keys.

### Concurrent Sessions
Limit the number of simultaneous sessions per user. Additional logins will terminate the oldest session.

## Rate Limiting

### Login Attempts
Limit failed login attempts per IP address within a time window. After exceeding the limit, the IP is temporarily blocked.

### Lockout Duration
How long an IP is blocked after exceeding the login attempt limit.

## IP Restrictions

### Allow List
Only allow connections from specified IPs or CIDR ranges. All other IPs are blocked.

### Deny List
Block specific IPs or CIDR ranges. All other IPs are allowed.

> ⚠ Be extremely careful with IP restrictions. Misconfiguration can lock out all users, including admins. Always test with a single IP first.

## Two-Factor Authentication

### Enforcement
Require all users to enable 2FA. Users who haven't set up 2FA will be prompted on their next login.

### Supported Methods
- **TOTP** — Time-based one-time passwords (authenticator apps)
- **WebAuthn** — Hardware security keys and biometrics

> 💡 Enforce 2FA for admin accounts at minimum. Consider enforcing it for all users in security-sensitive environments.
`
  },

  // ===== GOVERNANCE =====

  policies: {
    title: 'Certificate Policies',
    content: `
## Overview

Certificate policies define the rules and constraints enforced when certificates are issued, renewed, or revoked. Policies are evaluated in **priority order** (lower number = higher precedence) and can be scoped to specific CAs.

## Policy Types

### Issuance Policies
Rules applied when new certificates are created. This is the most common type. Controls key types, validity periods, SAN restrictions, and whether approval is required.

### Renewal Policies
Rules applied when certificates are renewed. Can enforce shorter validity on renewal or require re-approval.

### Revocation Policies
Rules applied when certificates are revoked. Can require approval before revocation of critical certificates.

## Rules Configuration

### Max Validity
Maximum certificate lifetime in days. Common values:
- **90 days** — Short-lived automation (ACME-style)
- **397 days** — CA/Browser Forum baseline for public TLS
- **730 days** — Internal/private PKI
- **365 days** — Code signing

### Allowed Key Types
Restrict which key algorithms and sizes can be used:
- **RSA-2048** — Minimum for public trust
- **RSA-4096** — Higher security, larger certificates
- **EC-P256** — Modern, fast, recommended
- **EC-P384** — Higher security elliptic curve
- **EC-P521** — Maximum security (rarely needed)

### SAN Restrictions
- **Max DNS Names** — Limit the number of Subject Alternative Names
- **DNS Pattern** — Restrict to specific domain patterns (e.g. \`*.company.com\`)

## Approval Workflows

When **Require Approval** is enabled, certificate issuance is paused until the required number of approvers from the assigned group have approved the request.

### Configuration
- **Approval Group** — Select a user group responsible for approvals
- **Min Approvers** — Number of approvals required (e.g. 2 of 3 group members)
- **Notifications** — Alert administrators when policies are violated

> 💡 Use approval workflows for high-value certificates like code signing and wildcard certificates.

## Priority System

Policies are evaluated in priority order. Lower numbers have higher precedence:
- **1–10** — Critical security policies (code signing, wildcard)
- **10–20** — Standard compliance (public TLS, internal PKI)
- **20+** — Permissive defaults

When multiple policies match a certificate request, the highest-priority (lowest number) policy wins.

## Scope

### All CAs
Policy applies to every CA in the system. Use for organization-wide rules.

### Specific CA
Policy applies only to certificates issued by the selected CA. Use for granular control.

## Default Policies

UCM ships with 5 built-in policies reflecting real-world PKI best practices:
- **Code Signing** (priority 5) — Strong keys, approval required
- **Wildcard Certificates** (priority 8) — Approval required, max 10 SANs
- **Web Server TLS** (priority 10) — CA/B Forum compliant, 397-day max
- **Short-Lived Automation** (priority 15) — 90-day ACME-style
- **Internal PKI** (priority 20) — 730-day, relaxed rules

> 💡 Customize or disable default policies to match your organization's requirements.
`
  },

  approvals: {
    title: 'Approval Requests',
    content: `
## Overview

The Approvals page shows all certificate requests that require manual approval before issuance. Approval workflows are configured in **Policies** — when a policy has "Require Approval" enabled, any matching certificate request creates an approval request here.

## Request Lifecycle

### Pending
The request is awaiting review. The certificate cannot be issued until the required number of approvers have approved it. Pending requests appear first by default.

### Approved
All required approvals have been received. The certificate will be issued automatically once approved.

### Rejected
Any single rejection immediately stops the request. The certificate will not be issued. A rejection comment is required to explain the reason.

### Expired
The request was not reviewed before the deadline. Expired requests must be re-submitted.

## Approving a Request

1. Click a pending request to view its details
2. Review the certificate details, requester, and associated policy
3. Click **Approve** and optionally add a comment
4. The approval is recorded with your username and timestamp

## Rejecting a Request

1. Click a pending request to view its details
2. Click **Reject**
3. Enter a **rejection reason** (required) — this is logged for audit compliance
4. The request is immediately stopped

> ⚠ Any single rejection stops the entire request. This is intentional — if any reviewer identifies a problem, issuance should not proceed.

## Approval History

Each request maintains a complete approval timeline showing:
- Who approved or rejected (username)
- When the action was taken (timestamp)
- Comment provided (if any)

This history is immutable and part of the audit trail.

## Filtering

Use the status filter bar at the top to show:
- **Pending** — Requests awaiting your review
- **Approved** — Recently approved requests
- **Rejected** — Rejected requests with reasons
- **Total** — All requests regardless of status

## Permissions

- **read:approvals** — View approval requests
- **write:approvals** — Approve or reject requests

> 💡 Set up email notifications in policies so approvers are alerted when new requests arrive.
`
  },

  reports: {
    title: 'Reports',
    content: `
## Overview

Generate, download, and schedule PKI compliance reports. Reports provide visibility into your certificate infrastructure for auditing, compliance, and operational planning.

## Report Types

### Certificate Inventory
Complete list of all certificates managed by UCM. Includes subject, issuer, serial number, validity dates, key type, and current status. Use for compliance audits and infrastructure documentation.

### Expiring Certificates
Certificates expiring within a specified time window (default: 30 days). Critical for avoiding outages — review this report regularly or schedule it for daily delivery.

### CA Hierarchy
Certificate Authority structure showing parent-child relationships, certificate counts per CA, and CA status. Useful for understanding your PKI topology.

### Audit Summary
Security events and user activity summary. Includes login attempts, certificate operations, policy violations, and configuration changes. Essential for security audits.

### Compliance Status
Policy compliance and violation summary. Shows which certificates comply with your policies and which ones violate them. Required for regulatory compliance.

## Executive PDF Report

Click **Download PDF** in the top-right to generate a professional executive report suitable for management reviews, board presentations, and compliance audits.

### Contents
The PDF report includes 9 sections:
1. **Cover Page** — Key metrics, risk gauge, and key findings at a glance
2. **Table of Contents** — Quick navigation
3. **Executive Summary** — Overall PKI health, certificate distribution, and risk level
4. **Risk Assessment** — Critical findings, expiring certificates, weak algorithms
5. **Certificate Inventory** — Breakdown by status, key type, and issuing CA
6. **Compliance Analysis** — Score distribution, grade breakdown, category scores
7. **Certificate Lifecycle** — Expiration timeline and automation rate
8. **CA Infrastructure** — Root and intermediate CA details, hierarchy
9. **Recommendations** — Actionable items based on current PKI state

### Charts & Visuals
The report includes visual elements: risk gauge bar, status distribution, compliance grade breakdown, and expiration timeline — designed for non-technical stakeholders.

> 💡 The PDF report is generated from live data. Download it before meetings for the most current snapshot.

## Generating Reports

1. Find the report you want in the list
2. Click **▶ Generate** to create a preview
3. The preview appears below as a formatted table
4. Click **Close** to dismiss the preview

## Downloading Reports

Each report row has download buttons:
- **CSV** — Spreadsheet format for Excel, Google Sheets, or LibreOffice
- **JSON** — Structured data for automation and integration

> 💡 CSV reports are easier for non-technical stakeholders. JSON is better for scripts and API integrations.

## Scheduling Reports

### Expiry Report (Daily)
Automatically sends a certificate expiry report every day to configured recipients. Enable this to catch expiring certificates before they cause outages.

### Compliance Report (Weekly)
Sends a policy compliance summary every week. Useful for ongoing compliance monitoring without manual effort.

### Configuration
1. Click **Schedule Reports** in the top-right
2. Enable the reports you want to schedule
3. Add recipient email addresses (press Enter or click Add)
4. Click Save

### Test Send
Before enabling schedules, use the ✈️ button on any report row to send a test report to a specific email address. This verifies that SMTP is configured correctly and the report format meets your needs.

> ⚠ Scheduled reports require SMTP to be configured in **Settings → Email**. Test send will fail if SMTP is not set up.

## Permissions

- **read:reports** — Generate and download reports
- **read:audit + export:audit** — Download PDF executive report
- **write:settings** — Configure report schedules

> 💡 Schedule the expiry report first — it's the most operationally valuable and helps prevent certificate-related outages.
`
  },

  // ===================================================================
  msca: {
    title: 'Microsoft AD CS Integration',
    content: `
## Overview

UCM integrates with Microsoft Active Directory Certificate Services (AD CS) to sign CSRs using your existing Windows PKI infrastructure. This bridges your internal CA with UCM's certificate lifecycle management.

## Setting Up a Connection

1. Go to **Settings → Microsoft CA**
2. Click **Add Connection**
3. Enter the **Connection Name** and **CA Server Hostname**
4. Optionally enter the **CA Common Name** (auto-detected if empty)
5. Select the **Authentication Method**
6. Enter the credentials for your chosen method
7. Click **Test Connection** to verify
8. Set a **Default Template** and click **Save**

## Authentication Methods

| Method | Requirements | Best For |
|--------|-------------|----------|
| **Client Certificate (mTLS)** | Client cert/key PEM from the CA | Production — no domain join needed |
| **Basic Auth** | Username + password, HTTPS | Simple setups — enable basic auth in IIS certsrv |
| **Kerberos** | Domain-joined machine + keytab | Enterprise AD environments |

### Client Certificate Setup (Recommended)

1. On your Windows CA, create a certificate for the UCM service account
2. Export as PFX, then convert to PEM:
   \`\`\`bash
   openssl pkcs12 -in client.pfx -out client-cert.pem -clcerts -nokeys
   openssl pkcs12 -in client.pfx -out client-key.pem -nocerts -nodes
   \`\`\`
3. Paste the cert and key PEM content into the UCM connection form

## Signing CSRs via Microsoft CA

1. Navigate to **CSRs → Pending**
2. Select a CSR and click **Sign**
3. Switch to the **Microsoft CA** tab
4. Select the connection and certificate template
5. Click **Sign**

### Auto-Approved Templates
The certificate is returned immediately and imported into UCM.

### Manager Approval Templates
UCM saves the request as **Pending** and tracks the MS CA request ID. Once approved on the Windows CA, check the status from the CSR detail panel to import the certificate.

## Enroll on Behalf Of (EOBO)

EOBO allows an enrollment agent to request certificates on behalf of other users. This is common in enterprise environments where a PKI administrator manages certificates for end users.

### Prerequisites

- The UCM service account needs an **enrollment agent certificate** issued by the CA
- The certificate template must have **"Enroll on behalf of other users"** permission enabled
- The template's security tab must grant the enrollment agent the right to enroll

### Using EOBO in UCM

1. In the sign modal, select the Microsoft CA connection and template
2. Check the **Enroll on Behalf Of (EOBO)** checkbox
3. The fields auto-populate from the CSR:
   - **Enrollee DN** — from the CSR subject (e.g., CN=John Doe,OU=Users,DC=corp,DC=local)
   - **Enrollee UPN** — from the CSR SAN email (e.g., john.doe@corp.local)
4. Adjust the values if needed
5. Click **Sign**

UCM passes these as ADCS request attributes:
- EnrolleeObjectName:<DN> — identifies the target user in AD
- EnrolleePrincipalName:<UPN> — the user's login name

### EOBO vs Direct Enrollment

| Feature | Direct Enrollment | EOBO |
|---------|-------------------|------|
| Who signs | User themselves | Enrollment agent on behalf |
| Private key | User's machine | Can be on UCM (CSR model) |
| Template permission | Standard enroll | Requires enrollment agent rights |
| Use case | Self-service | Centralized PKI management |

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Connection test fails | Verify hostname, port 443, and that certsrv is accessible |
| No templates found | Check that the UCM account has enrollment permissions on the CA |
| EOBO denied | Verify enrollment agent certificate and template permissions |
| Request stuck pending | Approve on the Windows CA console, then refresh status in UCM |

> 💡 Use the **Test Connection** button to verify authentication and discover available templates before signing.
`
  },

  // ===== SSH CAS =====
  sshCas: {
    title: 'SSH Certificate Authorities',
    content: `
## Overview

SSH Certificate Authorities (CAs) are the foundation of SSH certificate-based authentication. Instead of distributing individual public keys to every server, you create a CA and configure servers to trust it. Any certificate signed by the CA is then automatically accepted.

UCM supports the OpenSSH certificate format (RFC 4253 + OpenSSH extensions), which is natively understood by OpenSSH 5.4+ — no additional software needed on servers or clients.

## CA Types

### User CA
A User CA signs certificates that authenticate **users to servers**. When a server trusts a User CA, any user presenting a valid certificate signed by that CA is allowed to log in (subject to principal matching).

**Server configuration:**
\`\`\`
# /etc/ssh/sshd_config
TrustedUserCAKeys /etc/ssh/user_ca.pub
\`\`\`

### Host CA
A Host CA signs certificates that authenticate **servers to clients**. When a client trusts a Host CA, it can verify that the server it connects to is legitimate — eliminating "trust on first use" (TOFU) warnings.

**Client configuration:**
\`\`\`
# ~/.ssh/known_hosts
@cert-authority *.example.com ssh-ed25519 AAAA...
\`\`\`

## Creating a CA

1. Click **Create SSH CA**
2. Enter a descriptive name (e.g., "Production User CA")
3. Select the CA type: **User** or **Host**
4. Choose the key algorithm:
   - **Ed25519** — Recommended. Fast, small keys, modern security.
   - **ECDSA P-256/P-384** — Good compatibility and security.
   - **RSA 2048/4096** — Broadest compatibility, larger keys.
5. Optionally set max validity and default extensions
6. Click **Create**

> 💡 Use separate CAs for user and host certificates. Never use one CA for both purposes.

## Server Setup

### Automatic Setup Script

UCM generates a POSIX shell script that automatically configures your server:

1. Open the CA detail panel
2. Click **Download Setup Script**
3. Transfer the script to your server
4. Run it:

\`\`\`bash
chmod +x setup-ssh-ca.sh
sudo ./setup-ssh-ca.sh
\`\`\`

The script:
- Detects your OS and init system
- Backs up sshd_config before any changes
- Installs the CA public key
- Adds TrustedUserCAKeys (user CA) or HostCertificate (host CA)
- Validates the config with \`sshd -t\`
- Restarts sshd only if validation passes
- Supports \`--dry-run\` to preview changes

### Manual Setup

#### User CA
\`\`\`bash
# Copy the CA public key to the server
echo "ssh-ed25519 AAAA... user-ca" | sudo tee /etc/ssh/user_ca.pub

# Add to sshd_config
echo "TrustedUserCAKeys /etc/ssh/user_ca.pub" | sudo tee -a /etc/ssh/sshd_config

# Restart sshd
sudo systemctl restart sshd
\`\`\`

#### Host CA
\`\`\`bash
# Sign the server's host key
# Then add to sshd_config:
echo "HostCertificate /etc/ssh/ssh_host_ed25519_key-cert.pub" | sudo tee -a /etc/ssh/sshd_config
sudo systemctl restart sshd
\`\`\`

## Key Revocation Lists (KRL)

SSH CAs support Key Revocation Lists to invalidate compromised certificates:

1. Revoke certificates from the SSH Certificates page
2. Download the updated KRL from the CA detail panel
3. Deploy the KRL file to servers:

\`\`\`bash
# Add to sshd_config
RevokedKeys /etc/ssh/revoked_keys
\`\`\`

> ⚠ Servers must be configured to check the KRL. Revocation does not take effect until the KRL is deployed.

## Best Practices

| Practice | Recommendation |
|----------|---------------|
| Separate CAs | Use distinct CAs for user and host certificates |
| Key algorithm | Ed25519 for new deployments, RSA 4096 for legacy compatibility |
| CA lifetime | Keep CAs long-lived; use short-lived certificates instead |
| Backup | Export and securely store the CA private key |
| Principal mapping | Map principals to specific usernames, not wildcards |
`
  },

  // ===== SSH CERTIFICATES =====
  sshCertificates: {
    title: 'SSH Certificates',
    content: `
## Overview

SSH certificates are signed SSH public keys with metadata: identity, validity period, permitted principals, and extensions. They replace the traditional \`authorized_keys\` approach with centralized, time-limited, auditable access control.

UCM issues OpenSSH-format certificates compatible with OpenSSH 5.4+ on any platform.

## Issuance Modes

### Sign Mode (Recommended)
The user generates their own key pair and provides only the **public key** to UCM. The private key never leaves the user's machine.

**User workflow:**
\`\`\`bash
# 1. Generate a key pair (user's machine)
ssh-keygen -t ed25519 -f ~/.ssh/id_work -C "jdoe@example.com"

# 2. Copy the public key content
cat ~/.ssh/id_work.pub

# 3. Paste into UCM's sign form
# 4. Download the signed certificate
# 5. Save as ~/.ssh/id_work-cert.pub

# 6. Connect
ssh -i ~/.ssh/id_work user@server
\`\`\`

### Generate Mode
UCM generates both the key pair and the certificate. Use this when you need to provision credentials centrally.

> ⚠ **Download the private key immediately** — it is not stored in UCM and cannot be recovered.

**Workflow:**
1. Select a CA and fill in the certificate details
2. Choose "Generate" mode
3. Click **Issue**
4. Download all three files:
   - Private key (\`keyid\`) — **Save securely!**
   - Certificate (\`keyid-cert.pub\`)
   - Public key (\`keyid.pub\`)

## Certificate Fields

### Key ID
A unique identifier embedded in the certificate. It appears in SSH server logs when the certificate is used, making it essential for auditing.

**Good key IDs:** \`jdoe-prod-2025\`, \`webserver-01\`, \`deploy-ci-pipeline\`

### Principals
Principals define **who** (user certs) or **what** (host certs) the certificate is valid for:

- **User certificates**: list of usernames the holder can log in as (e.g., \`deploy\`, \`admin\`)
- **Host certificates**: list of hostnames/IPs the server is known by (e.g., \`web01.example.com\`, \`10.0.1.5\`)

> 💡 If no principals are specified, the certificate works for any principal — which is usually too permissive.

### Validity

Choose a preset or set custom duration:

| Preset | Use Case |
|--------|----------|
| 1 hour | CI/CD pipelines, one-time tasks |
| 8 hours | Standard workday access |
| 24 hours | Extended access |
| 7 days | Sprint-based access |
| 30 days | Monthly rotation |
| 365 days | Long-lived service accounts |

Short-lived certificates (8h–24h) are recommended for human users. Longer validity is acceptable for automated service accounts.

### Extensions (User Certificates Only)

| Extension | Description |
|-----------|-------------|
| permit-pty | Allow interactive terminal sessions |
| permit-agent-forwarding | Allow SSH agent forwarding |
| permit-X11-forwarding | Allow X11 display forwarding |
| permit-port-forwarding | Allow TCP port forwarding |
| permit-user-rc | Allow execution of ~/.ssh/rc on login |

### Critical Options

| Option | Description |
|--------|-------------|
| force-command | Restrict the certificate to a single command |
| source-address | Restrict to specific source IP addresses/CIDRs |

**Example:** A certificate with \`force-command=ls\` and \`source-address=10.0.0.0/8\` can only run \`ls\` and only from the 10.x.x.x network.

## Using Certificates

### User Certificate
\`\`\`bash
# Place certificate alongside the private key
# If key is ~/.ssh/id_work, certificate must be ~/.ssh/id_work-cert.pub
cp downloaded-cert.pub ~/.ssh/id_work-cert.pub

# SSH automatically uses the certificate
ssh user@server
\`\`\`

### Host Certificate
\`\`\`bash
# On the server: place the host certificate
sudo cp host-cert.pub /etc/ssh/ssh_host_ed25519_key-cert.pub

# Add to sshd_config
echo "HostCertificate /etc/ssh/ssh_host_ed25519_key-cert.pub" | sudo tee -a /etc/ssh/sshd_config
sudo systemctl restart sshd
\`\`\`

On clients, add the Host CA to known_hosts:
\`\`\`
@cert-authority *.example.com ssh-ed25519 AAAA...
\`\`\`

## Revocation

1. Select a certificate in the table
2. Click **Revoke** in the detail panel
3. The certificate is added to the CA's Key Revocation List (KRL)
4. Download and deploy the updated KRL to servers (from SSH CAs page)

> ⚠ Revocation only takes effect when servers check the KRL via \`RevokedKeys\` in sshd_config.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Permission denied (publickey) | Verify the CA is trusted on the server (TrustedUserCAKeys) |
| Certificate not used | Ensure the cert file is named \`<key>-cert.pub\` next to the private key |
| Principal mismatch | The username you SSH as must be listed in the certificate's principals |
| Certificate expired | Issue a new certificate with appropriate validity |
| Host verification failed | Add the Host CA to known_hosts with @cert-authority |
`
  },
}

export default helpGuides
