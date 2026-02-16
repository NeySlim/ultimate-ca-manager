/**
 * Detailed help guides for all UCM pages — v2.1.0
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
- CRL auto-regeneration
- OCSP responder
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
2. Choose a revocation reason (Key Compromise, CA Compromise, etc.)
3. Confirm the revocation

Revoked certificates are published in the CRL on next regeneration.

> ⚠ Revocation is permanent — a revoked certificate cannot be un-revoked.

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

1. Select a pending CSR
2. Click **Sign**
3. Choose the **Signing CA** (must have a private key)
4. Set the **validity period** in days
5. Optionally apply a template for Key Usage and extensions
6. Click **Sign**

The resulting certificate appears in the Certificates page.

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
https://your-server:8443/api/v2/crl/{ca_id}
\`\`\`

### Downloading CRLs
Download CRLs in DER or PEM format for distribution to clients or integration with other systems.

## OCSP Responder

### What is OCSP?
OCSP provides real-time certificate status checking. Instead of downloading an entire CRL, clients send a query for a specific certificate and get an immediate response.

### OCSP Status
The OCSP section shows:
- **Responder status** — Active or inactive
- **Total queries** — Number of OCSP requests processed
- **Cache hit rate** — Percentage of queries served from cache

### AIA URL
The Authority Information Access (AIA) URL is embedded in certificates to tell clients where the OCSP responder is located.

\`\`\`
https://your-server:8443/api/v2/crl/ocsp
\`\`\`

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

- **Let's Encrypt Client** — Obtain public TLS certificates from Let's Encrypt (or any ACME CA)
- **Local ACME Server** — Built-in ACME server for internal PKI automation with multi-CA support

## Let's Encrypt

### Client Tab
Manage your Let's Encrypt account:
- Register a new account or use an existing one
- View active orders and their status
- Request new certificates via ACME protocol

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

## Using certbot with UCM

\`\`\`
# Register account
certbot register --server https://your-server:8443/acme/directory \\
  --agree-tos --email admin@example.com

# Request certificate
certbot certonly --server https://your-server:8443/acme/directory \\
  --standalone -d myserver.internal.corp

# Renew
certbot renew --server https://your-server:8443/acme/directory
\`\`\`

## Using acme.sh with UCM

\`\`\`
acme.sh --server https://your-server:8443/acme/directory \\
  --issue -d myserver.local --standalone
\`\`\`

> ⚠ For internal ACME, clients must trust the UCM CA. Install the Root CA certificate in the client's trust store.
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
5. Select a **role** (Admin, Operator, Viewer, or custom)
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
- **Viewer** — Read-only access

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

Three built-in roles that cannot be modified or deleted:

- **Admin** — Full access to everything
- **Operator** — Manage certificates, CAs, CSRs, templates. No access to system settings, users, or RBAC
- **Viewer** — Read-only access to certificates and CAs

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
- Upload or link to IDP metadata XML
- Configure Entity ID and ACS URL
- Map IDP attributes to UCM user fields (username, email, role)

### OpenID Connect (OIDC)
- Discovery URL (/.well-known/openid-configuration)
- Client ID and Client Secret
- Scopes (openid, profile, email)
- Auto-create users on first SSO login

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
Include the key in the \`Authorization\` header:

\`\`\`
Authorization: Bearer <your-api-key>
\`\`\`

Or use the \`X-API-Key\` header:

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

SSO allows users to authenticate using their organization's Identity Provider (IDP), eliminating the need for separate UCM credentials.

## SAML 2.0

### Configuration
1. Obtain the IDP metadata URL or XML file from your identity provider
2. In UCM, go to **Settings → SSO**
3. Click **Add Provider** → SAML
4. Enter the **IDP Metadata URL** or upload the XML
5. UCM auto-populates Entity ID and ACS URL
6. Configure **attribute mapping** (username, email, groups)
7. Click **Save** and **Enable**

### Attribute Mapping
Map IDP SAML attributes to UCM user fields:
- \`username\` → UCM username
- \`email\` → UCM email
- \`groups\` → UCM group membership (optional)

## OpenID Connect

### Configuration
1. Register UCM as a client in your OIDC provider
2. Copy the **Client ID** and **Client Secret**
3. In UCM, go to **Settings → SSO**
4. Click **Add Provider** → OIDC
5. Enter the **Discovery URL** (e.g., \`https://idp.example.com/.well-known/openid-configuration\`)
6. Enter Client ID and Secret
7. Configure scopes (openid, profile, email)
8. Click **Save** and **Enable**

### Auto-Create Users
When enabled, a new UCM user account is automatically created on first SSO login, using the IDP-provided attributes. The default role is assigned.

## Login Flow
1. User clicks **Login with SSO** on the UCM login page
2. User is redirected to the IDP
3. After authentication, IDP redirects back to UCM
4. UCM creates or updates the user account
5. User is logged in

> ⚠ Always keep at least one local admin account as fallback in case SSO misconfiguration locks everyone out.

> 💡 Test SSO with a non-admin account first before making it the primary authentication method.
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

## Generating Reports

1. Find the report card you want to generate
2. Click **▶ Generate** to create a preview
3. The preview appears below the cards as formatted JSON
4. Click **Close** to dismiss the preview

## Downloading Reports

Each report card has two download buttons:
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
Before enabling schedules, use the ✈️ button on any report card to send a test report to a specific email address. This verifies that SMTP is configured correctly and the report format meets your needs.

> ⚠ Scheduled reports require SMTP to be configured in **Settings → Email**. Test send will fail if SMTP is not set up.

## Permissions

- **read:reports** — Generate and download reports
- **write:settings** — Configure report schedules

> 💡 Schedule the expiry report first — it's the most operationally valuable and helps prevent certificate-related outages.
`
  },
}

export default helpGuides
