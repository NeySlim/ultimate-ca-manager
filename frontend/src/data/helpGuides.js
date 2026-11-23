/**
 * Detailed help guides for all UCM pages: v2.50
 * Each entry: { title, content (markdown string) }
 * Markdown supports: ## h2, ### h3, #### h4, **bold**, `code`, *italic*,
 *   - lists, 1. numbered, > blockquotes, ``` code blocks
 */

export const helpGuides = {

  // ===================================================================
  dashboard: {
    title: 'Overview',
    content: `
## Overview

The Overview is the home page: a strip of four figures, then the cards of the overview over the live data of your PKI. Each card loads on its own and shows its own loading, empty, error or missing-permission state.

## First steps
On an instance without any certificate, an administrator sees three steps above the figures: create a root CA, then an issuing CA, then set up a protocol (ACME, SCEP or EST). Each step leads to the screen that does it; a step waits for the one before. **Later** folds the steps into one line that keeps the progress, **Resume** brings them back. Once the three are done, **Issue a first certificate** opens the certificate form and **Hide** closes the steps for good.

## Figures
Four figures head the page, each with what situates it. **Certificates**: the full inventory, a curve of the certificates issued per day over 30 days, how many were issued and how many are active (valid or expiring). **To handle**: the items to handle, split in a bar into critical, to do and to watch. **Expiring within 30 days**: the certificates that expire in the coming 30 days, the next 30 UTC days in weekly columns with the busiest day named, and those already expired under it. **Failures today**: the ACME, SCEP and EST failures of the current UTC day, 14 days in columns and the gap with yesterday, a rise in red. Pointing at a figure, or focusing it, shows its details. Certificates and Expiring open the certificate list; To handle shows the To handle card, bringing it back if you had hidden it; the failures show the same card on its ACME rows. A figure the server did not give reads as a dash.

## Cards

### To handle
The interventions by urgency, critical first, then by due date; six are shown and **Show the others** lists the rest. Each row has two lines: the name with its type, then the cause. On the right, a short delay ("in 12 d", "overdue by 3 d") with the exact date under it, and a button: **Renew** for a manual renewal, **Retry** for a renewal the ACME client failed, **Publish now** for a CRL due or missing, each with the matching write permission; then the name opens the record. Any other row has **Review** (a request waiting for approval), **View the CA** or **Open**. A Retry or a publication that fails leaves a message with **Retry**, to start it again. A deadline still to come carries, under its date, a thin bar that empties over its last 30 days, in the colour of its delay. The chips above the list filter by type and carry the total of each, and a link in the head of the card opens the manual renewals due. What needs no action today (certificates their client renews, authorities and trust anchors still far from expiry) is counted on a line of its own, **Show** unfolds it; a critical item is never put there. With the right to read the trust store, the trust store certificates that expire within 90 days or have already expired are listed too (the expired ones as critical).

### Automation health
Per protocol (ACME, SCEP, EST), over 30 UTC days: the last operation, one bar per day, the successes rising in the colour of the protocol and the failures dropping in red, a day without operation as a grey dash, and the success rate with the successes and failures of the period. Pointing at a day, or focusing the chart and pressing the arrow keys (Home and End for the ends), shows the figures of that day; Escape closes them. The ACME success rate opens the To handle card on its ACME rows; a day with ACME failures opens the Audit Logs page on that UTC day's failed ACME operations, or the To handle card for who may not read the audit trail. A failed or unknown last state is said beside the name. Below, as pills, the TSA signer while the TSA is enabled (a warning while the CA certificate signs, since those tokens do not satisfy RFC 3161), the scheduler with its number of tasks and its last run, its pill pulsing when a reload brings a newer run, and, with the right to read settings, whether email, webhooks and auto-renewal are set up: a setting that is not configured is information, not an alert; email configured but disabled or incomplete, or webhooks with none active, show as alerts. A line under the card counts the lines that report a problem.

### Hierarchy
At most ten authorities, whatever the installation holds, one column per root: the trees that issued most over 7 days come first, then the largest. A root gives its offline mark, its CRL and the cross-signing; each authority under it gives its CRL, its OCSP responder and its issuances over 7 days. An authority whose children are not all shown says how many are below, and the line under the title says how many are shown. Each authority opens its page; **Explore** opens the Certificate Authorities page.

### Expiry horizon
The expirations to come over 30 days, 90 days or a year, counted in UTC days. One column per week, Monday to Sunday, the current week starting today: the automatic renewals at the bottom, the manual ones hatched above, the busiest week labelled. Under the columns, a calendar with one square per day, the darker the more certificates expire that day, and a diamond on a day an authority or a signer expires. Picking a day or a week, with the pointer or the keyboard (up and down a day, left and right a week, Home and End for the ends), shows beside the calendar how many expire, how many their client renews and how many authorities, the first five certificates, and a link that opens the Certificates page on exactly that interval.

### Compliance
A ring gives the average compliance score out of 100 with its grade, and a bar the grades A+ to F with their counts; the score, its grades and the gauges count the same certificates. Then one gauge per rule over the active certificates: RSA keys of at least 3072 bits, server validity of 398 days at most, safe signature hash, complete chain, private key kept in UCM. Each gauge gives the share that conforms and the count (22/211), the gap counted under its name, and its state as an icon: conform, to watch (90% and more conform), major gap; the private key is information only. A rule opens the certificate list filtered on its gaps.

### Latest operations
The most recent operations on a timeline grouped by day (today, yesterday, then the date), one line each with the icon of its family, the operation, the object, who did it and the time; the exact date shows when pointing at it. Successive sign-ins of one user fold into one line, such as 5 sign-ins by admin, with their time span. Without **read:audit** you only see your own operations; with it, the object opens the Audit Logs page searched on that operation and **See all** opens the whole trail. **All**, **PKI** and **Access**, at the top of the card, keep every operation, the PKI operations only, or the sign-ins and account changes only; a filter that keeps nothing says so in one line.

### Issuances by source
The certificates issued and renewed per UTC day over 7, 30 or 90 days, stacked by source: ACME, SCEP, EST, WSTEP, import and manual, WSTEP and import hatched in the colour of a neighbour. Above the chart, the total of the period, its gap with the period before and the share issued through a protocol. Pointing at a day, or focusing the chart and pressing the arrow keys, gives its figures per source; picking a day opens the Certificates page on the certificates created that day (a renewal that kept its certificate counts in the chart, not in that list). A period without any issuance shows a sentence instead of an empty chart.

### Authorities and HSM
Six tiles at most: the authorities in alert first (revoked, expired, CRL overdue or missing, expiring within 90 days), then the most active over 7 days, then by name; the HSM modules after them, two places at least when there are any. An authority tile gives its state in a word, its algorithm, where its key is kept, the validity spent (amber in its last third) and what is left, its CRL, its OCSP and its issuances over 7 days, and opens its page. A module tile gives its state, its type, its keys, the authorities it serves and its last test; **Test**, with the right to write HSM, tests it again. **Explore the hierarchy** opens the Certificate Authorities page.

### Revocation coverage
The share of active authorities whose CRL is current, then the whole as a bar of three parts: current CRL, CRL to publish (overdue or missing) and no distribution point, each counted in the legend. Under it, the authorities to publish first, five at most: each opens its CRL page, and **Publish**, with the right to write CRLs, publishes a CRL for an authority that can sign one; an offline authority is said so instead.

## Charts and their tables
The menu of a card with a chart (Automation health, Expiry horizon, Issuances by source, Compliance, Revocation coverage) has **Table view**: the card shows its figures as tables, for a screen reader or to copy them, and **Download as CSV** saves them; **Chart view** brings the chart back. Every chart reads the same way: pointing at a mark or focusing it shows one tooltip, the value first, and Escape closes it. When the system asks for reduced motion, the charts appear without animation.

## Opening a filtered list
Every figure that has a list opens the Certificates page filtered to exactly the certificates it counts. The filter appears as a chip above the table; remove it with its x. An interval picked on the expiry horizon or on the issuances (a day, a week) reads as one chip giving its dates, whose x removes both bounds.

## Choosing and ordering the cards
Pick the **Operator** preset (To handle, Automation health, Hierarchy, Expiry horizon) or the **Manager** preset (Compliance, Expiry horizon, Hierarchy, Latest operations) in the page header, or open **Cards** to tick the cards to show, move them up and down, or apply a preset (**All cards** shows every card in the initial order). The menu of a card hides it, the Cards button showing it again, or opens the same dialog. The order and the hidden cards are saved with your account and follow you across browsers; with every card hidden, the page says so and offers the Cards button.

## Quick actions
The header offers **Issue**, which opens the certificate form, to who may issue certificates.

## Refreshing
Cards load when the page opens and reload on their own, without leaving the page, when certificates or CAs change, when the live link comes back and when you return to the tab; the refresh button of the header reloads them all at once. While the live link is down they reload once a minute. A card that could not read says why (the status and the request) and offers **Retry**, and **View the log** for who may read it. The connection icon in the top bar shows the state of the live link, and the status bar at the bottom shows the version and whether the service answers.
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

The tabs under the title count the CAs (All, Roots, Intermediates, Expired, then Offline, Revoked and Awaiting certificate when there are some) and filter the page; the tab is part of the address. The search field filters on the name, the common name and the subject. Hierarchy and List, next to it, switch between the two views; the authority shown in the side panel is part of the address.

### Tree View
The default view. Each root that heads a hierarchy is drawn with its sub-authorities on its right, folded beyond the first level; a node gives its state, the number of its certificates and of its sub-authorities, and a dotted line joins a CA to the one that cross-certified it. A root without a sub-authority takes a single line, and the roots that have no certificate either fold into one group once there are many. The arrow keys move through the tree, right and left unfold and fold, and Enter or a click selects the CA.

### Side panel
Beside the tree (under it on a phone) the selected CA shows its identity, its key, what it issued and its revocation: issuer, sub-authorities and cross-certificates are links that select them, the CRL gives its number, its publication and its next update (with a warning a day ahead), and the OCSP responder reads active or inactive. **View certificates** opens the certificate list on this CA, **Issue with this CA** opens the issue form on it (disabled, with the reason, when the CA cannot sign), **Download the chain** downloads its PEM chain, and **Other actions** holds export, CSR, revocation, taking offline, restore, template pins and deletion. The other details (constraints, extensions, fingerprints, PEM, metadata) are folded below. A CA opened from another page opens here.

### List View
Flat table with sortable columns, beside the side panel, 25 authorities a page (10, 50 or 100 on choice). A row carries one action (download the certificate) and a chevron that shows the CA in the panel. On a phone each CA is a card with the same facts and its chevron; a tap anywhere on it shows the CA.

## Creating a CA

### Create Root CA
1. Click **Create CA** and choose the root type in the dialog
2. Fill in the Subject fields (CN, O, OU, C, ST, L)
3. Select the key algorithm (RSA 2048/3072/4096, ECDSA P-256/P-384/P-521, ML-DSA 44/65/87, EdDSA Ed25519/Ed448): RSA-3072 by default
4. Set the validity period: 1, 2, 3, 5, 10, 15 or 20 years, or **Custom (days)** up to 50 years (typically 10-20 years for Root CAs)
5. Click **Create**

### Create Intermediate CA
1. Click **Create CA** and choose the intermediate type in the dialog
2. Select the **Parent CA** (must have a private key)
3. Fill in Subject fields
4. Set the validity period (typically 5-10 years)
5. Click **Create**

> ⚠ The Intermediate CA validity cannot exceed its parent CA's validity.

The form flags an RSA-2048 CA that would outlive 2030: ANSSI accepts RSA-2048 until the end of 2030, ETSI TS 119 312 until the end of 2026. Choose RSA-3072 or larger. Under **Advanced Constraints (RFC 5280)**, permitted and excluded subtrees (DNS, IP range, email) limit the names the CA may certify.

### Post-quantum CAs (ML-DSA)
**ML-DSA-44**, **ML-DSA-65** and **ML-DSA-87** (FIPS 204) are listed with their NIST security level (2, 3 and 5). The key is generated in software, or on an HSM provider that holds ML-DSA (see HSM-backed CAs); in FIPS mode only a software key is offered, when the FIPS module approves ML-DSA (the \`-fips\` Docker image does, RHEL 9 and Ubuntu 24.04 do not).

- An ML-DSA key signs without a separate digest: the digest field disappears, and a digest sent through the API is ignored with a notice. CRLs and OCSP responses of the CA follow the same rule.
- Hierarchies can mix: an ML-DSA root can sign an RSA or EC intermediate, and an RSA or EC CA can sign an ML-DSA intermediate, which then uses its parent's digest.
- An ML-DSA CA exports as PEM or DER, not as PKCS#12 or JKS. Clients without ML-DSA support (OpenSSL before 3.5, most browsers today) cannot verify what it signs.

### EdDSA CAs (Ed25519, Ed448)
**Ed25519** and **Ed448** keys can be generated for a root, intermediate or external CA, or imported with or after the CA certificate. The key is a software key (no HSM provider signs EdDSA), and in FIPS mode the algorithm is offered only when the FIPS module approves it (the \`-fips\` Docker image does, RHEL 9 and Ubuntu 24.04 do not).

- An EdDSA key signs without a digest, like ML-DSA: the digest field disappears and CRLs and OCSP responses follow the same rule.
- Hierarchies can mix: an EdDSA CA can sign RSA, EC or ML-DSA intermediates and leaves, and the reverse.
- Browsers, Windows (CryptoAPI/CNG) and SCEP clients do not accept certificates signed by an EdDSA CA, whatever the leaf key. SCEP and XCEP/WSTEP refuse such a CA. Use it where the consumers are OpenSSL, Go or Java 15+.

### Create an externally-signed CA (CSR mode, v2.214)
For the offline-root pattern: the issuing CA's key lives in UCM, its certificate is signed elsewhere:
1. Click **Create** → type **Signed by external CA (CSR)**
2. Fill in the Subject and key settings (local or HSM): validity is decided by the external signer
3. Submit: UCM generates the key pair and a CA-type CSR (downloads automatically)
4. Have the CSR signed by your external/offline root CA
5. Back on the CA (badge **Awaiting certificate**), click **Upload certificate** and provide the signed certificate (PEM or DER)

UCM only activates the CA if the certificate's public key matches the stored private key and the CA constraints hold. The chain links automatically when the issuer is known to UCM: import the external root (certificate only) for a complete chain. Until activation, the pending CA cannot sign, be exported, be a parent CA or go offline.

To renew, use **Renew via CSR**: a new CSR is issued **from the same key** (the SKI stays stable), signed externally, and uploaded through the same flow.

## Importing a CA

Import existing CA certificates via:
- **PEM file**: Certificate in PEM format
- **DER file**: Binary DER format
- **PKCS#12**: Certificate + private key bundle (requires password)

When importing without a private key, the CA can verify certificates but cannot sign new ones.

A certificate that carries the subject and key of a CA already in UCM, under another issuer, is a cross-certificate and never replaces the CA's own certificate. On a self-signed root it is attached as a cross-certificate. On an intermediate, and when uploaded after **Renew via CSR**, the import is refused (409) and offers **Attach as cross certificate** or **Replace**; a root rollover (same issuer name, new key) replaces the certificate as a renewal does. Smart Import attaches one found next to a held root and lists it in the result; one it cannot attach is left out and reported as skipped.

## Exporting a CA

Export formats:
- **PEM**: Base64-encoded certificate
- **DER**: Binary format
- **PKCS#12 (P12/PFX)**: Certificate + private key + chain, password-protected

When a cross-certificate offers another path, the export dialog shows **Chain to present**: the default chain UCM serves, the self-signed root, or a cross-certificate.

> 💡 PKCS#12 export includes the full certificate chain and is ideal for backup.

## Cross-certificates

A cross-certificate carries a CA's subject and key under the signature of another CA. Clients that trust only the other root build a path to your CA through it, which is how a root is renewed or migrated without breaking them. It sits beside the CA's own certificate, which is never replaced. A CA that carries one shows a **Cross-signed** badge.

In the CA details, **Cross certificates** lists them:
- **Attach**: paste or pick a certificate issued by another CA for this CA's key (PEM or DER). Name or policy constraints it carries are reported.
- **Cross-sign**: sign this CA's key with another CA held in UCM; choose the validity and the path length.
- **Serve / Stop serving**: at most one per CA is served, in the default chain of TLS, PKCS#12, ACME, WSTEP, TSA and deployments, and by the AIA \`.cer\` and \`.pem\` URLs. A revoked, expired or not yet valid one is kept and exportable but never served.
- **Export** and **Detach**.

Exports and deploy bindings can pin another chain (**Chain to present** / **Chain variant**). The ACME server offers the other chains as alternates, selected by a client with \`--preferred-chain\`. Changes reach clients after the next issuance or deployment, and after the 24 hour cache of the AIA URLs.

### Repairing damaged records

A bar under the CA statistics lists records an older import left behind: a duplicate record holding the cross-certificate of a root that is also held (**Convert to cross-certificate** moves its children and certificates to the root and deletes the duplicate), or a key shared by distinct certificates with no self-signed record (**Restore as primary** takes the self-signed certificate). Nothing is changed without a click. A self-signed root that was overwritten or deleted only comes back from a backup or through **Restore as primary**.

## Private Keys

CAs with a **key icon** (🔑) have a private key stored in UCM and can sign certificates. CAs without a key are trust-only: they validate chains but cannot issue.

### Key Storage
Private keys are stored in the UCM database, encrypted under the master key that UCM creates at its first start (see Settings › Security). For higher security, consider using an HSM provider (see HSM page).

## Chain Repair

If parent-child relationships are broken (e.g., after import), use **Chain Repair** to automatically rebuild the hierarchy based on Issuer/Subject matching. Its strip shows by itself while a CA is orphaned, a record waits for its repair or a repair runs; otherwise the **Chain Repair** button of the page head opens it.

## Renewing a CA

UCM does not re-issue the certificate of a CA it signed: to replace a CA nearing its expiry, create a new CA and issue under it. A CA signed by an external CA is renewed with **Renew via CSR**, which re-issues a CSR from the same key for the external CA to sign (see Externally-signed CAs).

## Revoking an Intermediate CA

An intermediate CA whose key is compromised or that is decommissioned is revoked from its parent, like a certificate:

1. Select the intermediate CA and click **Revoke CA**
2. Choose the RFC 5280 reason (key compromise, CA compromise, cessation of operation, ...)
3. Confirm: the revocation is permanent

What happens next:
- The CA's serial is published on the **parent CA's CRL** (regenerated immediately) and the parent's **OCSP responder** answers \`revoked\` with the reason
- The revoked CA **can no longer sign** anything: certificates, CSRs, renewals, sub-CAs, and neither can the CAs below it
- Certificates it issued are no longer trusted by clients that validate the chain; its own CRL and OCSP keep being served until the CA is deleted
- Deleting the revoked CA keeps its entry on the parent's CRL until the certificate's original expiry

> ⚠ A root CA cannot be revoked from UCM (self-signed: relying parties remove it from their trust stores), and an intermediate signed by an external root is revoked at that root. Its CRL can then be served from UCM (see Offline Mode).

## Deleting a CA

Deletion is refused (409) while the CA has intermediate CAs, has issued certificates, or is bound to a SCEP profile or another service. Revoke and delete its certificates and delete its children first.

## HSM-backed CAs

UCM can store a CA's signing key on an external Hardware Security Module instead of the local encrypted database. This is the recommended option for production Root and Intermediate CAs.

### When to use
- Compliance requirements (FIPS 140-2/3, eIDAS, Common Criteria)
- Defense-in-depth: keys cannot be exfiltrated even if the UCM host is compromised
- Centralized key custody across multiple PKI tools

### Prerequisites
1. Open **HSM Management** and configure a provider (PKCS#11 / OpenBao / etc.)
2. Verify the provider is **Active** and **Connected**

### Step by step
1. Open **Create CA**
2. Fill in the Subject and validity as usual
3. In **Key Storage**, switch from *Local* to **HSM**
4. Pick the HSM provider
5. Choose a key mode:
   - **Generate new key**: provide a label (letters/digits/_/-) and pick the algorithm (RSA-2048/3072/4096 or EC-P256/P384/P521, RSA-3072 by default; Brainpool on PKCS#11, ML-DSA on the providers listed under HSM Management)
   - **Use existing key**: pick an unused signing key already present on the HSM
6. Submit. UCM creates the CA certificate and binds it to the HSM key.

### Limitations
- HSM-backed private keys **cannot be exported**. PKCS#12, JKS and key-only export options are hidden for HSM CAs. Only the certificate (PEM/DER/P7B) can be exported.
- There is **no in-place migration** between Local and HSM. To "move" an existing local CA onto an HSM, create a new CA on the HSM and re-issue certificates.
- Existing keys offered in *Use existing key* are filtered to signing-capable asymmetric keys not yet bound to an authority, X.509 or SSH: an HSM key backs one authority only.
- Creating a CA on an HSM key needs the \`read:hsm\` permission besides \`write:cas\`; without it the **HSM** choice is disabled.

## Offline Mode

Take a CA's signing key out of runtime use without deleting the CA. The certificate, the chain and the last CRL stay served; signing operations (CSR sign, certificate issue, renewal, new CRLs) are blocked. OCSP answers through a delegated responder, otherwise only from responses already cached, until their nextUpdate.

This is the standard way to protect a Root CA between rare ceremonies, while keeping its trust anchor and revocation infrastructure online.

### Two modes

**Password protected**: the private key stays in the UCM database, wrapped (PKCS#8) under a password you choose. To bring the CA back online, click **Restore** and re-enter the password. Fast and convenient; security depends on the password's strength and on UCM not being compromised.

**File exported**: the private key is exported as a password-encrypted PEM file that downloads once. The key is then **removed from the database**. To bring the CA back online, click **Restore**, upload the file and enter the password. This is the strongest option (true air-gap) but you are fully responsible for the file: lose it and the key is unrecoverable.

### Password rules
The password follows the standard UCM password complexity policy: minimum length, mix of character classes, no trivial sequences. The same rules as user passwords.

### Step by step. Take offline
1. Open the CA in the inspector
2. Click **Take offline**
3. Read the explanation, click **Continue**
4. Pick a mode (*Password protected* or *File exported*)
5. Enter the password twice
6. Confirm. For *File exported*, the encrypted key downloads immediately: store it safely.

### Step by step. Restore
1. Open the offline CA in the inspector
2. Click **Restore**
3. Enter the password
4. For *File exported*: also select the previously downloaded key file
5. Confirm. Signing operations resume immediately.

### Effect on operations
| Operation | Online | Offline |
|---|---|---|
| Issue certificate | Allowed | **Blocked** |
| Sign CSR | Allowed | **Blocked** |
| Renew issued certificate | Allowed | **Blocked** |
| Serve the last CRL | Allowed | Allowed (upload a new one signed next to the key) |
| OCSP | Allowed | Delegated responder, or cached responses until nextUpdate |
| Export certificate / chain | Allowed | Allowed |
| Delete CA | Allowed | Allowed |

> ⚠ Offline-mode passwords are **not recoverable**. Store them in your password manager / vault before confirming. Lost password = unusable CA = full re-issuance of subordinate hierarchy.
`
  },

  // ===================================================================
  certificates: {
    title: 'Certificates',
    content: `
## Overview

Central management for all X.509 certificates. Issue new certificates, import existing ones, track expiry dates, handle renewals and revocations.

## Certificate Status

- **Valid**: Within validity period and not revoked
- **To renew**: Will expire within 30 days
- **Expired**: Past the "Not After" date
- **Revoked**: Explicitly revoked, published in CRL
- **Orphan**: Issuing CA no longer exists in UCM
- **Archived**: Superseded by a renewal or re-enrolment that kept the old record for history (SCEP, EST, WSTEP, ACME, OCSP responder)

## Issuing a Certificate

1. Click **Issue Certificate**
2. Select the **Signing CA** (must have a private key)
3. Fill in the Subject (CN is required, other fields optional)
4. Add Subject Alternative Names (SANs): DNS names, IPs, emails. A DNS name follows RFC 5280: dot-separated labels, a wildcard only as the first label, no space or trailing dot; an internationalized name is issued as its A-label. A server or combined CN holding an underscore (\`my_host.example.com\`) is refused when it would be the certificate's DNS name, that is with no SAN given and a template allowing DNS names. An email address in the subject also goes into the SAN, whatever the type
5. Choose key type and size
6. Set validity period
7. Optionally apply a **Template** to pre-fill settings
8. Click **Issue Certificate**

### Using Templates
Templates pre-fill Key Usage, Extended Key Usage, subject defaults, and validity. Select a template before filling the form to save time.

## Importing Certificates

Supported formats:
- **PEM**: Single or bundled certificates
- **DER**: Binary format
- **PKCS#12 (P12/PFX)**: Certificate + key + chain (password required)
- **PKCS#7 (P7B)**: Certificate chain without keys

## Renewing a Certificate

Since v2.214, renewal updates the certificate **in place**:
- Same record: **id, refid and creation date never change**: integrations keep their references
- Same Subject and SANs; new serial number and validity period
- Renew from the page generates a **new key**; the automatic renewal keeps the key
- A certificate whose key UCM does not hold (SCEP, EST, WSTEP or ACME enrolment, import without the key) is refused (409): renew it through its enrollment protocol or sign a new request
- The **superseded serial stays published on the CRL** (reason \`superseded\`) and answers \`revoked\` over OCSP until the old certificate's original expiry
- \`renewed_at\` / \`renewed_times\` track the renewal history
- A revoked certificate cannot be renewed (409): issue a new one instead
- **Renew** asks for the validity of the new certificate in days, prefilled with the current duration; issuance policies and the CA's expiry still cap it
- **Renewal through EST, SCEP or WSTEP** stores a new certificate: its deployments and the HTTPS binding move to it. A deployment that sends the private key, and the HTTPS binding, stay on the previous certificate when UCM does not hold the new key: the deployment shows **Not following the renewal**, the bell and the overview list it, and the \`certificate.binding_left_behind\` event is sent. **Reattach to the renewed certificate** once UCM holds its key or the deployment stops sending the key; importing the key of the renewed certificate moves them on its own

**Deleting**: a valid, non-revoked certificate cannot be deleted on its own: **Delete** explains why and offers **Revoke, then delete**, so relying parties see the change. Revocations are persisted independently of the certificate record and survive deletion.

## Revoking a Certificate

1. Select the certificate → **Revoke**
2. Choose a revocation reason (Key Compromise, CA Compromise, Affiliation Changed, Superseded, Cessation of Operation, Certificate Hold, etc.)
3. Confirm the revocation

Revoked certificates are published in the CRL on next regeneration.

A certificate obtained over ACME (by the ACME client, or by the proxy under an upstream account UCM holds) is also revoked at that CA, whether it is revoked alone, in bulk, by an approved request, as a user certificate, with the enrolment or user it belongs to, as the related member of a pair, or by its key at UCM's own ACME server. If the CA does not confirm, the revocation is kept owed and sent again by the renewal task until the CA confirms or the certificate expires; a hold stays in UCM, ACME having none. If no account of UCM can speak for it, the revocation stays local and a warning says to revoke it with the CA directly. The reason is sent when it is keyCompromise, affiliationChanged, superseded, cessationOfOperation or privilegeWithdrawn.

> ⚠ Revocation is generally permanent: except for **Certificate Hold** which can be removed.

### Remove Hold (Unhold)

If a certificate was revoked with the **Certificate Hold** reason, it can be restored to valid status:

1. Open the revoked certificate in the inspector
2. The **Remove Hold** button appears in the action bar (only for Certificate Hold revocations)
3. Click **Remove Hold** to restore the certificate
4. The certificate returns to valid status, the CRL is regenerated, and the OCSP cache is updated

> 💡 Certificate Hold is useful for temporary suspensions (e.g., lost device, pending investigation).

### Revoking a Held Certificate for Good

A certificate on hold can be revoked with another reason (for example Key Compromise once the investigation confirms it) from the same **Revoke** button, without being made valid in between. The CRL and OCSP give the new reason; unless an invalidity date is given, the start of the hold is recorded as the date the certificate became invalid.


## Exporting Certificates

Export formats:
- **PEM**: Certificate only
- **PEM + Chain**: Certificate with its issuing CAs (**Include CA chain**); the root CA is added only when **Include Root CA** is ticked
- **DER**: Binary format
- **PKCS#12**: Certificate + key + chain, password-protected

> ⚠ Exporting the **private key** (PKCS#12/PFX, JKS, or key file) requires the admin-only **read:private_keys** permission. Roles without it, including the built-in Operator role, must retrieve archived keys through the approval-gated **Key Recovery** workflow instead.

## Hybrid Certificate Pairs (RFC 9763)

A hybrid pair links a classical certificate (**A**, RSA or EC) and a post-quantum one (**B**, ML-DSA) for the same subject. B carries the non-critical **relatedCertificate** extension, which names A by its hash, so a relying party can require both.

- **Issuing**: tick **Issue a hybrid pair** in the Issue Certificate form (or send \`hybrid\` in \`POST /api/v2/certificates\`) to issue both from the same CA, with the same subject, names and validity. B copies A's extensions with its own key identifier and key usage, and asserts no key usage or EKU that A lacks. Under the ANSSI, BSI and EU ACM compliance profiles, ML-DSA-65 and ML-DSA-87 are accepted only as B: never alone, and ML-DSA-44 not at all
- **Linking by request**: a CSR carrying a **relatedCertRequest** signed by A's key issues a B linked to A, through Sign CSR, ACME, EST or WSTEP. A must be held by UCM, valid, unrevoked, an end-entity certificate issued by a CA of this instance whose chain is valid now, and the request must be at most 7 days old. A newer certificate that names the same A takes over the pair, and the previous one leaves it. A certificate given inline in the request's location must be A; other locations are not fetched
- **Revoking** either member, alone or in bulk, revokes the other unless **Also revoke the linked certificate** is unticked. Under a policy that requires approval, the pair goes together, and two different approval policies on the two members leave the revocation to an administrator. If the other member cannot be revoked, the answer says so (\`related_not_revoked\`) and it must be revoked separately. ACME revokeCert revokes only the certificate presented (RFC 8555)
- **Renewing** either member, by hand, in bulk or automatically, renews both, and the new B names the new A: UCM holds both keys and renews the pair as one. A member renewed alone names only the certificate its original named: once that one is renewed since, revoked, archived or expired, the renewed member carries no relatedCertificate extension and leaves the pair, and the renewal says why (a warning after a renewal from this page, the audit log in every case). The other member also leaves the pair when one is deleted. A renewal is refused, and nothing changes, when the other member or the relatedCertificate extension cannot be read
- **Exporting**: the **hybrid-bundle** format is a ZIP of both certificates, and of both private keys when the key is included; it is refused when neither certificate names the other any more

> ⚠ A policy that requires approval refuses to issue a hybrid pair for now: issue it under a policy without approval.

## Favorites

Star ⭐ important certificates to bookmark them. Favorites are listed in the command palette (Ctrl+K).

## Comparing Certificates

Tick two to four certificates in the list and click **Compare** in the selection bar to see them side by side in a detached window (a dialog on a phone): subject, issuer, validity, key algorithm and size, alternative names, key usages, fingerprints, serial number and the other extensions, one column per certificate. A line identical for all is merged into one cell marked *Identical*; a line that differs is marked by a stroke beside its label, and in a list (names, usages, extensions) **+** marks the element not every certificate has. **Show only the differences** hides the identical lines.

**Detach into a window**, among the tools of the inspector, opens the certificate in a window over the page with the same sections and actions. Several windows stay open at once, even on other pages: drag one by its title bar, resize it by an edge or a corner, or use the move button at the start of its title bar with the arrow keys (Shift and the arrow keys resize). Its maximize button, or a double-click on the title bar, spreads it between the top bar and the status bar, and gives back its place and size the next time; the comparison window has the same button. The status bar lists the open windows to bring one back in front; the cross or Escape closes it.

## Filtering & Search

- **State tabs**: All, To renew, Valid, Expired, Revoked and Archived, plus Orphans when there are some; each shows its count, except Archived. The tab is part of the address, so a reload or a shared link keeps it
- **CA filter**: Show certificates from a specific CA
- **Source filter**: Filter by how the certificate entered UCM (issued, imported, ACME, SCEP, etc.)
- **Template filter** (in the **Filters** dialog at the end of the toolbar, a chip once on): Find certificates **modified from template**: issued from a template but with the key type or validity explicitly overridden at request time. The divergent fields are listed on the certificate detail; the record is frozen at issuance
- **Text search**: Search by subject, issuer, display name or serial number (SANs are not searched); the search runs once you stop typing and says how many results it found
- **Saved filters**: the **Filters** dialog at the end of the toolbar saves the search, the state and the filters under a name in this browser, and applies a saved set again
- **Export the list**: the export button of the toolbar exports every result, the selection bar's **Export…** the ticked certificates: in PEM, or their metadata in CSV or JSON. Once the whole page is ticked, **Select all N results** extends the selection to every result
- **Sorting**: By name, expiry date, creation date, status
- **Columns**: Common name, description, state, issuer, source, expiry and key algorithm by default; the **Columns** button adds the compliance grade, the hybrid link and the creation date
- **Row actions**: Export on the row; the other actions in the inspector a click on the row opens: Export and Renew in its heading, Rename, Revoke, Delete and the rest in its ⋯ menu
- **Inspector**: opens under the list, inside the page margins, or on its right from 1200 px wide; its place and size follow your account on every page. A certificate opened from another page (the search, an approval, an authority) comes here, in this inspector. Drag its edge or use the arrow keys on it to resize it, fold it to its tab strip, enlarge it. Open certificates stay as tabs; those that do not fit go into a +N menu. Its tabs are Overview, Chain, Extensions, History and PEM; History lists the dates of the record and, with read:audit, the audit entries of this certificate among the latest 100 on certificates

## Conformance linting

The **Lint** action (certificate detail) checks X.509 standards conformance. Informative only.

- **RFC 5280**: IETF X.509 profile, always relevant
- **CA/Browser Forum**: Baseline Requirements for public TLS certs (expect noise on internal PKI)
- Severities: fatal / error / warning / notice / info
- Engine: pkilint (+ zlint when present): optional server dependency, degrades gracefully when absent
`
  },

  // ===================================================================
  'user-certificates': {
    title: 'User Certificates',
    content: `
## Overview

The User Certificates page manages mTLS client certificates enrolled from **My Account → Security**, section **Client Certificates (mTLS)**. Unlike regular certificates, these are specifically tied to user accounts for mutual TLS authentication.

Certificates here are fully managed by UCM: they are stored in the database with private keys, and can be exported, revoked, or deleted at any time.

## Enrolling a Certificate

1. Go to **My Account → Security**, section **Client Certificates (mTLS)**
2. Click **Add Certificate**, keep **Generate** and click **Generate Certificate**
3. The system generates a key pair and issues a client certificate signed by your mTLS CA
4. The certificate appears on this page and can be used for mTLS login

## Certificate Status

- **Valid**: Within validity period and not revoked
- **Expiring**: Will expire within 30 days
- **Expired**: Past the "Not After" date
- **Revoked**: Explicitly revoked, published in CRL

## Exporting a Certificate

1. Click the certificate's name: its detail opens under the list
2. Click **Export** and choose the format:
   - **PEM**: Certificate, with the CA chain and the private key when ticked, in text format
   - **PKCS#12**: Binary bundle, password-protected (min 8 characters)
3. Click **Download**

**Export the list** in the page header saves every certificate the search and the state filter keep, as CSV or JSON.

The exported file can be imported into browsers, operating systems, or API clients for mTLS authentication.

> ⚠ PKCS#12 password must be at least 8 characters.

## Revoking a Certificate

1. Open the certificate, then its **⋯** menu → **Revoke**
2. Choose a revocation reason:
   - Key Compromise
   - Affiliation Changed
   - Superseded
   - Cessation of Operation
   - Unspecified
3. Confirm the revocation

> ⚠ Revoking a certificate immediately prevents mTLS login with that certificate. Revocation is permanent.

## Deleting a Certificate

Delete, in the **⋯** menu of the certificate's detail, removes both the certificate and the user-certificate association. Only admins and operators can delete.

> ⚠ Deletion is permanent and cannot be undone.

## Permissions

| Role | View | Export | Revoke | Delete |
|------|------|--------|--------|--------|
| Admin | All | All | All | All |
| Operator | All | All (another user's private key needs read:private_keys) | All | All |
| Auditor | All | Certificate only, no private key | ✗ | ✗ |
| Viewer | Own only | Own only | ✗ | ✗ |

### Required Permissions

- **read:user_certificates**: View certificate list and details
- **write:user_certificates**: Revoke certificates
- **delete:user_certificates**: Delete certificates

> 💡 Enroll new mTLS certificates from the Account page. This page is for managing existing certificates.
`
  },

  // ===================================================================
  csrs: {
    title: 'Certificate Signing Requests',
    content: `
## Overview

Certificate Signing Requests (CSRs) allow external systems to request certificates without exposing their private keys. The CSR contains the public key and subject information; the private key stays with the requester.

## States

The chips above the list switch between the two lists, each counted.

### Pending
CSRs awaiting review and signing. New CSRs appear here after upload.

### Signed
Signed requests, each with the certificate it produced. **Download certificate** and, in the **⋯** menu, **Download CSR** get either one, and **Sign again** puts the request back in Pending.

## Generating a CSR

UCM can generate a CSR and key pair directly:

1. Click **Generate CSR**
2. Fill in the Subject fields (CN required)
3. Add Subject Alternative Names if needed
4. Select key type and size (RSA 2048/4096, ECDSA P-256/P-384/P-521, Brainpool, ML-DSA-44/65/87)
5. Click **Generate**

The CSR and private key are created and stored in UCM. The CSR appears in the Pending tab ready for signing.

> 💡 This is convenient when you want UCM to manage the entire lifecycle. CSR, signing, and key storage.

A certificate signed for an **ML-DSA** key keeps only signature bits: keyEncipherment, dataEncipherment and keyAgreement asked by the template are removed, and the result names what was removed.

### Related certificate requests (RFC 9763)

Through the API, \`related_to\` names an existing certificate **A** whose private key UCM holds; it needs the \`read:private_keys\` permission, and each use of A's key is audited. The generated CSR then carries a **relatedCertRequest** signed by A's key. Signing it issues a certificate linked to A, the second member of a hybrid pair, which revokes and renews with A. Signing is refused when A is revoked, expired or not an end-entity certificate, or when the new certificate asserts a key usage or EKU that A lacks.

## Uploading a CSR

1. Click **Upload CSR**
2. Either paste PEM text or upload a PEM file
3. UCM validates the CSR signature and displays the details
4. The CSR appears in the Pending tab

## Reviewing a CSR

Click a request's name: its detail opens under the list, with:
- **Subject**: CN, O, OU, C, etc.
- **SANs**: DNS names, IP addresses, emails
- **Key info**: Algorithm, size, public key fingerprint
- **Signature**: Algorithm and validity

## Signing a CSR

### Local CA Signing

1. Select a pending CSR
2. Click **Sign**
3. Choose the **Signing CA** (must have a private key)
4. Select the **Certificate Type** (server, client, code signing, email)
5. Set the **validity period** in days
6. Optionally **Add names** (email, DNS, IP, URI) to those of the request
7. Click **Sign**

In Microsoft CA mode, the AD CS template is chosen instead of the certificate type.

The resulting certificate appears in the Certificates page.

> 💡 A request generated on a smart card often carries only a CN. For an S/MIME certificate, choose the Email type and add the address: it becomes the certificate's subject alternative name. Added names pass the CA name constraints, issuance policies and approval like any other, and the approver sees them.

What a request may carry is checked as on the issue form, and a refusal names its reason:
- **Subject**: CN, O and OU at most 64 characters, L and ST 128, C a two-letter country code as a PrintableString (RFC 5280 appendix A)
- **DNS names**: letters, digits and hyphens in dot-separated labels (no underscore), a wildcard only as the whole first label, no trailing dot, a last label not all digits, never an IP address. An internationalized name typed in the form is issued as its A-label (\`xn--\`)
- **Names from the CN**: a request without SAN gets a DNS name from its CN only when the CN is in DNS name syntax (never \`John Doe\`); a single label such as \`intranet\` counts for a server or device certificate only, not for client, email or code signing, and an email (S/MIME) certificate gets none, even from a dotted CN such as \`john.doe\`; a host-like server CN that gives none is named in a notice, and a sub-CA gets none
- **Email in the subject**: a valid emailAddress is also added to the SAN as an email name, for every certificate type
- **Key Usage**: a request without Key Usage gets its type's, as on the issue form (client, code signing and email included)
- A parent CA with pathLen 0, or a name outside the CA name constraints, is refused with that reason; the dotted CN of an email certificate is checked as a DNS name only when the certificate also carries Server Auth

### Microsoft CA Signing

If Microsoft CA connections are configured, a **Microsoft CA** tab appears in the sign modal:

1. Select a pending CSR and click **Sign**
2. Switch to the **Microsoft CA** tab
3. Select the **MS CA connection**
4. Select the **certificate template** (auto-loaded from the CA)
5. Click **Sign**

If the template requires manager approval, the request stays Pending in UCM. Open it in **Pending** and click **Check status** in its **⋯** menu to fetch the certificate once the CA has issued it (also needs the permission to sign CSRs), or approve it from the CA Control Panel of the connection.

### Enroll on Behalf Of (EOBO)

When signing via Microsoft CA, you can enroll on behalf of another user:

1. Select the MS CA connection and template
2. Check **Enroll on Behalf Of (EOBO)**
3. The **Enrollee DN** and **Enrollee UPN** fields auto-fill from the CSR subject and SAN email
4. Adjust the values if needed and click **Sign**

> ⚠️ EOBO requires an enrollment agent certificate configured on the AD CS server, and the template must allow enrollment on behalf of other users.

### External CA Signing

For a certificate from a public or third-party CA, keep the key in UCM and send only the request:

1. **Generate CSR** in UCM, then **Download CSR** and submit it to the external CA
2. When the certificate comes back, import it on the Certificates page (**Import**, file or pasted PEM) or through **Operations → Smart Import**
3. UCM recognises the certificate by its public key, completes the pending CSR and keeps its private key: the certificate then exports with the key (PEM, PKCS#12, JKS) like any other

The CSR moves from **Pending** to **History**. If the certificate must be installed elsewhere, **Download Private Key** on the pending CSR provides the key (requires the read:private_keys permission, like every direct key export).

> 💡 The match is made on the key pair, so it still works when the CA rewrites the subject (many public CAs keep only the CN).

## Signing a Request Again

A device that keeps its key, such as a smart card, often cannot produce the same request twice. In **History**, **Sign again** puts the stored request back in **Pending**, with the same public key, to sign it once more with other EKUs, names or validity. The certificate already issued is left as it is: revoke it if it should no longer be used.

> 💡 Renewal stays refused for a certificate whose private key UCM does not hold, since it would revoke the serial the device still presents.

## Adding a Private Key

Before signing, **Upload Key** (in the **⋯** menu of the request) attaches the private key to a pending CSR, so the signed certificate can be exported as PKCS#12. A signed request is no longer offered this action.

> 💡 This is useful when the requester sends both the CSR and the key securely.

## Deleting CSRs

Delete removes a pending CSR from UCM. A signed request is its certificate: it is deleted from the Certificates page, not from here.
`
  },

  // ===================================================================
  templates: {
    title: 'Certificate Templates',
    content: `
## Overview

Templates define reusable certificate profiles. Instead of manually configuring Key Usage, Extended Key Usage, validity, and subject fields each time, apply a template to pre-fill everything.

## System and Custom

Every template is one or the other, shown in the **Source** column.

### System
The templates seeded at install: Web Server (TLS/SSL), Email Certificate (S/MIME), VPN Server, VPN Client, Code Signing, OCSP Signing, Client Authentication and Smartcard Logon. Edit and Delete are refused for them, in the interface and by the API. **Copy** gives you an editable copy to build on.

### Custom
Everything created or imported here. These can be edited and deleted freely.

Choose **Custom** in the source filter of the toolbar to hide the built-in templates and work with your own only. The choice is remembered; with no custom template yet, the list says so and **Clear all filters** brings the built-in ones back.

Certificate authorities are not made from templates: create them on the **CAs** page.

## Creating a Template

1. Click **Create Template**
2. Enter a **name** and optional description
3. Select the template **type**: Web Server, Email, VPN Server, VPN Client, Code Signing, Client Auth, OCSP Signing, Smartcard Logon or Custom. It sets the Key Usage, Extended Key Usage and SAN defaults, which you can then change
4. Configure **Subject defaults** (O, OU, C, ST, L, CN, Email). The Email also becomes an email SAN, whatever the certificate type
5. Select **Key Usage** flags
6. Select **Extended Key Usage** values from the purposes the server knows (Smartcard Logon, Time Stamping, Microsoft RDP and others)
7. Set the **Key Type** (RSA-2048, RSA-3072, RSA-4096, EC-P256, EC-P384, EC-P521, Brainpool EC-BP256/384/512 or ML-DSA-44/65/87), the digest and the **default validity** period in days. The digest is the issuing CA's signing hash, so it still applies to an ML-DSA key under an RSA or EC CA; an ML-DSA CA ignores it
8. Click **Create**

## Using Templates

When issuing a certificate or signing a CSR, select a template from the dropdown. The template pre-fills:
- Subject fields (you can override them)
- Key Usage and Extended Key Usage
- Validity period

## Windows Autoenrollment Flags

Templates carry three opt-in flags used by the Windows autoenrollment protocols (XCEP/WSTEP, configured per realm under **Settings → Windows Autoenrollment**):

- **Allow autoenrollment**: Advertise the template as \`autoEnroll=true\` in Certificate Enrollment Policy, so GPO/Kerberos-authenticated clients request it automatically at logon with no user action. Off by default: like real ADCS, a template can still be enrolled manually (MMC "Request New Certificate", \`certreq\`) without this, since Enroll and Autoenroll are separate permissions.
- **Build subject from Active Directory**: For unattended GPO autoenrollment: derive the certificate's subject and SAN from the requester's AD object (via the AD Connector) instead of requiring the client to supply one. On the Kerberos endpoints a subject named in the request is ignored and computer accounts are refused; machine templates always take the computer's DNS name.
- **Restrict enrollment to AD group**: Only principals belonging to the configured Active Directory group (nested membership included) may enroll against this template over the Kerberos-authenticated endpoint. Enter a group name or full DN; leave blank to allow any authenticated principal, matching real ADCS's default. Not enforced on the Username/Password endpoint, which has no per-request identity to check.

Templates with these flags list **AD**, **Auto** and **ACL** under **Marks** in their detail.

## Pinned Subject Fields

A template can **pin** the organizational subject fields: **C, ST, L, O, OU**: for certificates issued over WSTEP. A pinned value is forced onto every issued certificate, overriding whatever the client's CSR or the Active Directory derivation supplies for that field.

- **Common Name and Subject Alternative Name are never affected**: they stay dynamic per requester
- Leave a field blank to leave it dynamic
- Templates with pinned fields list **Pinned** under **Marks**, and the pinned values appear in the **Enrollment** tab of the template's detail

Use this to guarantee a uniform organizational identity (e.g. a fixed \`O\` and \`C\`) across an autoenrolled fleet, regardless of what each Windows client submits.

## Common Name Pattern

For Windows enrollment, a template whose subject UCM builds (a computer template, or a user template with **Build subject from Active Directory**) can take its CN from a pattern: fixed text and variables in braces, read from the requester's directory object, never from the request.

- **Computer templates**: \`{hostname}\` (the account name without \`$\`), \`{fqdn}\` (its dNSHostName)
- **User templates**: \`{username}\` (sAMAccountName), \`{upn}\`, \`{mail}\`, \`{displayName}\`, \`{givenName}\`, \`{surname}\`
- **Both**: \`{domain}\` (the DC components of the object's DN), \`{realm}\` (the realm of the profile)
- Write \`{{\` and \`}}\` for a literal brace. An unknown variable, a variable of the other kind, or a pattern on a template whose requester supplies the subject is refused when the template is saved
- **Keep the directory path** off: the subject is the CN alone, plus the pinned fields. On: the object's DN after its own name follows the CN (for a user, the e-mail attribute stays as without a pattern)
- **Only the CN changes**: the SAN (the computer's DNS name, the user's UPN and e-mail) and the SID extension stay as without a pattern, and a pattern never adds a SAN
- **Refused, never shortened**: a variable the directory leaves empty, a result longer than 64 characters or one holding a control character refuses the request; the reason names the template and the variable and is in the audit log
- **One subject per account** (RFC 5280), checked at issuance: a subject that a certificate of the same CA, whatever its status, already carries for another account is refused (case and extra spaces ignored), and the audit names that certificate's serial; the same account renews and enrolls again
- \`{displayName}\`, \`{givenName}\`, \`{surname}\` and \`{mail}\` are not unique, nor is \`{username}\` or \`{hostname}\` across domains: add \`{upn}\`, \`{fqdn}\`, or \`{username}\`/\`{hostname}\` with \`{domain}\` or **Keep the directory path**
- **Renewal** with the certificate takes the pattern in force, for the account the certificate's SID names; it is refused when no connector of the profile finds that account
- The Username/Password endpoint has no directory identity: the pattern does not apply there and the client supplies the subject

## Custom Extensions

A template can add extensions UCM has no setting for. Each one is an **OID**, a **Critical** flag and the **value**: the DER encoding of the extension value, in hex. UCM copies the bytes as given and never parses them, so check the encoding with your own tools first.

- Every certificate issued from the template carries them: issue form, Sign CSR, ACME profiles bound to the template, SCEP profiles, WSTEP and approvals. Renewals keep them
- The issue form can add more for one certificate; an entry with the OID of one of the template's replaces it
- Extensions UCM sets itself (key usage, EKU, names, key identifiers, CRL and OCSP pointers, policies, name constraints, qcStatements...) are refused: use their own settings
- A client that does not recognise a **critical** extension must reject the certificate (RFC 5280, section 4.2). Leave it non-critical unless every relying party understands it

The inspector lists such extensions for certificates and CAs on the Extensions tab, each with its OID, name when known, criticality and value; for a certificate, a button copies the whole value.

## Copying Templates

Open a template, then in its **⋯** menu click **Copy** to create a copy of it. Modify the copy without affecting the original.

## Import & Export

### Export
Export templates as JSON for sharing between UCM instances.

### Import
Import from:
- **JSON file**: Upload a template JSON file, one template or several in one file
- **JSON paste**: Paste JSON directly into the text area

A template whose name already exists is skipped, and the import says which ones were.

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
- **Revoked count**: Number of certificates in the CRL
- **Last regenerated**: When the CRL was last rebuilt
- **Auto-regeneration**: Whether automatic CRL updates are enabled

### Regenerating a CRL
Click **Regenerate** to rebuild a CA's CRL immediately. This is useful after revoking certificates.

### Auto-Regeneration
Enable auto-regeneration to automatically rebuild the CRL whenever a certificate is revoked. Toggle this per CA.

### CRL Validity
The CRL schedule (per CA) sets how long each published CRL remains valid. Options range from **1 day to 5 years**: 1d, 2d, 3d, 7d, 14d, 30d, 90d, 180d, 1y, 3y, 5y.

- **Online CAs** should keep a short validity (days) so relying parties pick up revocations quickly
- **Offline CAs** (typically a Root that cannot re-sign CRLs on schedule) are the intended use case for the long options: 90d up to 5y
- A warning is shown past one year: relying parties may keep stale revocation data for the whole validity window

### CRL Numbers
Every CRL carries a CRL number (RFC 5280 §5.2.3). A CA's base and delta CRLs share one increasing sequence, and no number is ever given to two CRLs, even when a revocation and the scheduler generate one at the same time.

The highest number reached is kept for each CA name and key, outside the CA itself, and is carried by backups. A CA restored on another server, or deleted and imported again, continues from it instead of starting over at 1.

### CRL Distribution Point (CDP)
The CDP URL is embedded in certificates so clients know where to download the CRL. Copy the URL from the CRL details.

\`\`\`
http://your-server:8080/cdp/{ca_refid}.crl
\`\`\`

> 💡 **Auto-enabled**: When you create a new CA, CDP is automatically enabled if a Protocol Base URL or HTTP protocol server is configured. The CDP URL is auto-generated, no manual steps needed.

> ⚠️ **Important**: URLs are auto-generated using the HTTP protocol port and server FQDN. If you access UCM via \`localhost\`, the URL cannot be generated. Configure your **FQDN** or **Protocol Base URL** in Settings → General first.

### Downloading CRLs
The download button saves the CRL as PEM (a .crl file). The CDP URL serves it as DER for clients and other systems.

## OCSP Responder

### What is OCSP?
OCSP provides real-time certificate status checking. Instead of downloading an entire CRL, clients send a query for a specific certificate and get an immediate response.

### OCSP Status
The OCSP section shows:
- **Responder status**: Active or inactive per CA
- **Total queries**: Number of OCSP requests answered since the service started, and how many came from the cache
- **Cache**: Response cache with automatic daily cleanup of expired entries

### OCSP Cache

UCM caches OCSP responses for performance. The cache is:
- **Automatically cleaned**: Expired responses are purged daily by the scheduler
- **Invalidated on revocation**: When a certificate is revoked, its cached OCSP response is immediately cleared
- **Invalidated on unhold**: When a Certificate Hold is removed, the OCSP cache is updated

### Delegated OCSP Responder

By default, OCSP responses are signed with the CA key itself. A **delegated responder** uses a dedicated certificate with the **OCSPSigning** EKU instead. Assign one per CA from the **Delegated Responder** section of the CA selected in the list on this page (only certificates carrying the OCSPSigning EKU and a private key are eligible).

**Automatic renewal**: a daily task re-issues the responder certificate before it expires, same key pair and extensions, renewed at par, and rebinds the CA's responder configuration to the new certificate. Short-lived OCSP signing certificates (e.g. a 90-day template) rotate without manual action. Enabled by default; it can be disabled and the renewal window tuned in Settings › Security.

### AIA URLs
The Authority Information Access (AIA) extension is embedded in certificates to tell clients where to find:

**OCSP Responder**: real-time revocation checking:
\`\`\`
http://your-server:8080/ocsp
\`\`\`

**CA Issuers** (RFC 5280 §4.2.2.1): download the issuing CA certificate for chain building:
\`\`\`
http://your-server:8080/ca/{ca_refid}.cer   (DER format)
http://your-server:8080/ca/{ca_refid}.pem   (PEM format)
\`\`\`

Enable CA Issuers per CA in the **AIA CA Issuers** section of that CA's panel on this page. The URL is automatically generated using the HTTP protocol server and the configured FQDN.

> ⚠️ **Prerequisite**: Protocol URLs (CDP, OCSP, AIA) require a valid **FQDN** or a configured **Protocol Base URL** in Settings → General. If you access UCM via \`localhost\`, enabling these features will fail, set the FQDN first.

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

The Simple Certificate Enrollment Protocol (SCEP) enables network devices: routers, switches, firewalls, MDM-managed endpoints, to automatically request and obtain certificates.

## Tabs

### Requests
View all SCEP enrollment requests:
- **Pending**: Awaiting manual approval (if auto-approve is off)
- **Approved**: Successfully issued
- **Rejected**: Denied by an administrator

### Configuration
Configure the SCEP server:
- **Enable/Disable**: Toggle the SCEP service
- **Signing CA**: Select which CA signs SCEP-enrolled certificates. Devices encrypt their request to this CA, so it must hold an RSA key in software: EC, HSM-backed, keyless, offline and revoked CAs are not listed (v2.248)
- **Auto-Approve**: Automatically approve requests with valid challenge passwords, or renewals signed by a certificate the same endpoint issued
- **Serve on plain HTTP**: off by default. Also answers SCEP on the HTTP protocol port (8080 by default) for clients that cannot use HTTPS, such as sscep. RFC 8894 §7.10: SCEP messages are already protected, so TLS is not required; the CMS envelope keeps the challenge password private

### Profiles
Named enrollment endpoints, each served at its own URL:

\`\`\`
https://your-server:8443/scep/<profile>/pkiclient.exe
\`\`\`

Each profile is bound to:
- **Its own CA**: different device fleets can enroll against different CAs
- **An optional certificate template**: when bound, the template's key usage, extended key usage and validity govern every certificate issued through the profile
- **Purposes no enrollee may hold**: a template bound to a profile cannot carry OCSP signing, timestamping, any purpose or Smartcard Logon, and a SCEP renewal never carries them over; Smartcard Logon is allowed when the profile validates against Intune, which vouches for the identity
- **A per-profile challenge password**: stored encrypted, with the same expiry window as the global challenge (or Microsoft Intune validation, see below)
- **An approval policy**: auto-approve or manual review per profile

Point each device fleet, MDM profile, or tenant at its own profile URL. The unlabelled \`/scep/pkiclient.exe\` endpoint keeps serving the global configuration unchanged.

### Challenge Passwords
The **Challenges of the authorities** view shows the challenge passwords. Devices must include a valid challenge password in their enrollment request to authenticate.

- **View password**: Show the current challenge for a CA
- **Regenerate**: Create a new challenge password (invalidates the old one for new enrollments)

A renewal (RenewalReq) signed by a certificate that the same endpoint (profile or global) issued is authenticated by that certificate: its challenge password is not checked, so a regenerated secret does not stop enrolled devices from renewing (RFC 8894 §2.4). A certificate issued elsewhere, by another profile, ACME, EST or the UI, still needs the endpoint's challenge. An EC device still sends a password, which keys the encryption of its reply.

### Information
Displays the SCEP endpoint URL and integration instructions.

## SCEP Enrollment Flow

1. Device sends a **GetCACert** request to get the CA certificate
2. Device generates a key pair and creates a CSR
3. Device wraps the CSR with the **challenge password** and sends a **PKCSReq**
4. UCM validates the challenge password
5. If auto-approve is on, UCM signs and returns the certificate
6. If auto-approve is off, an admin reviews and approves/rejects

### Device keys
The device signs its PKCSReq with its own key: RSA, ECDSA, Ed25519 or ML-DSA. An ML-DSA signature is checked per RFC 9882 (SHA-512 digest, the key's own algorithm identifier, no parameters). Ed448 signatures are refused, and ML-DSA ones too in FIPS mode when the FIPS module does not approve ML-DSA. The request is still encrypted to the RSA signing CA.

## SCEP URLs

\`\`\`
https://your-server:8443/scep/pkiclient.exe            (configured CA)
https://your-server:8443/scep/<profile>/pkiclient.exe  (per-profile endpoint)
https://your-server:8443/cgi-bin/pkiclient.exe         (configured CA, legacy path)
http://your-server:8080/scep/pkiclient.exe             (with Serve on plain HTTP)
\`\`\`

Devices need the URL to enroll; \`/scep\` alone is the web interface, not a SCEP endpoint. Use a profile URL to target that profile's CA, template and challenge password.

### CA rollover (GetNextCACert)
GetNextCACert serves the successor of the endpoint's CA, signed by the current CA: another CA with the same parent and the same subject DN, not revoked, not offline, holding a software RSA key, and expiring later. A CA that only shares the display name is never served; without a successor the answer is 404.

## Approving/Rejecting Requests

For pending requests (auto-approve disabled):
1. Review the request details (subject, transaction ID, status, CSR)
2. Click **Approve** to sign and issue the certificate
3. Or click **Reject** with a reason

A request that came through a profile is issued with that profile's template (validity, key usages), exactly as auto-approval would.

> The challenge password belongs in the CSR, which travels inside the CMS envelope encrypted to the CA (RFC 8894 §2.4), so plain HTTP does not expose it. A client that sends it as a signed attribute outside the envelope exposes it: keep such clients on HTTPS.

## Device Integration

### Cisco IOS
\`\`\`
crypto pki trustpoint UCM
  enrollment url https://your-server:8443/scep/pkiclient.exe
  password <challenge-password>
\`\`\`

### JAMF
Configure the SCEP profile with:
- Server URL: \`https://your-server:8443/scep/pkiclient.exe\`, or a profile's \`/scep/<profile>/pkiclient.exe\`
- Challenge: the password from UCM

### Microsoft Intune
Intune doesn't support a static challenge password: it issues its own encrypted, per-device challenge that only Intune's API can validate. On a SCEP **profile** (not the global endpoint), enable **Microsoft Intune SCEP challenge validation** and provide an Entra app registration's tenant ID, client ID and client secret:

1. In Microsoft Entra ID, register an app and grant it **Intune API → SCEP challenge validation** (\`scep_challenge_provider\`) and **Microsoft Graph → Application.Read.All**, both application permissions, admin-consented
2. Under **Intune app registrations**, add the app registration once (name, tenant ID, client ID, client secret) and **Test Connection** to confirm UCM can reach Intune; then pick it in the profile's **App registration** selector. Profiles of the same tenant share it, so the secret is rotated in one place
3. In Intune, point the device SCEP profile's server URL at this profile's \`/scep/<segment>/pkiclient.exe\` endpoint

Intune-enabled profiles must have **Auto-Approve** on. Intune's enrollment flow is a synchronous validate-then-issue round trip, with no queue on Intune's side for a human to review.
`
  },

  // ===================================================================
  acme: {
    title: 'ACME',
    content: `
## Overview

UCM supports ACME (Automated Certificate Management Environment) in two modes:

- **ACME Client**: Obtain certificates from any RFC 8555-compliant CA (Let's Encrypt, ZeroSSL, HARICA, or custom)
- **Local ACME Server**: Built-in ACME server for internal PKI automation with multi-CA support

## ACME Client

### Client Settings
Manage your ACME client configuration:
- **Environment**: Staging (testing) or Production (live certificates)
- **Contact Email**: Required for account registration
- **Auto-Renewal**: Automatically renew certificates before expiry
- **Certificate Key Type**: RSA-2048, RSA-4096, ECDSA P-256, ECDSA P-384, Brainpool P-256 or P-384, ML-DSA-44, ML-DSA-65 or ML-DSA-87. ML-DSA is not offered on a build without it, nor in FIPS mode when the FIPS module does not approve it. A configured type this instance cannot generate fails the order instead of falling back to RSA-2048
- **Account Key Algorithm**: ES256, ES384, or RS256 for ACME account signing
- **Renewal in place** (v2.251): a renewal keeps the certificate's id and refid, so its HTTPS binding, deployment bindings and webhooks follow it
- **Failed renewals** (v2.251): the order list shows the failure count and the last error; after 5 failed scheduled renewals an order is retried once a day. The **Automatic renewal** switch of a selected order stops or resumes its renewal
- **Orders list** (v2.251): every order is loaded, four pages at a time; a page still missing after its retries leaves a notice that the list is partial
- **Compromised keys** (v2.251): a key revoked as compromised is refused (409) at the request and before any renewal opens an order
- **Revocation at the CA**: A certificate obtained over ACME (by the ACME client, or by the proxy under an upstream account UCM holds) is also revoked at that CA, whether it is revoked alone, in bulk, by an approved request, as a user certificate, with the enrolment or user it belongs to, as the related member of a pair, or by its key at UCM's own ACME server. If the CA does not confirm, the revocation is kept owed and sent again by the renewal task until the CA confirms or the certificate expires; a hold stays in UCM, ACME having none. If no account of UCM can speak for it, the revocation stays local and a warning says to revoke it with the CA directly. The reason is sent when it is keyCompromise, affiliationChanged, superseded, cessationOfOperation or privilegeWithdrawn.

### Custom ACME Server
Use any RFC 8555-compliant CA, not just Let's Encrypt:

| CA Provider | Directory URL |
|---|---|
| **Let's Encrypt** | *(default, leave empty)* |
| **ZeroSSL** | \`https://acme.zerossl.com/v2/DV90\` |
| **HARICA** | \`https://acme-v02.harica.gr/acme/<token>/directory\` |
| **Google Trust** | \`https://dv.acme-v02.api.pki.goog/directory\` |

Set your CA's directory URL as the **ACME Directory URL** of its account in **Certificate Authorities (CA)**.

### Certificate Authorities (CA)
Manage every external CA account UCM registers with:

- **Multiple accounts per CA allowed**: several accounts can share the same directory URL (e.g. two Let's Encrypt accounts with different contact emails for administrative separation, useful alongside dns-persist-01). The account row, not the URL, is the identity.
- **Empty Directory URL**: defaults to Let's Encrypt Production.
- **Default account**: picked when a request selects no CA account; URL-based lookups resolve to the default.
- **Import**: bring an existing account's private key at creation: PKCS#8, SEC1/X9.62 (\`BEGIN EC PRIVATE KEY\`) and PKCS#1 (\`BEGIN RSA PRIVATE KEY\`) envelopes are all accepted; the algorithm is derived automatically.
- **Per-account proxy endpoint**: each account can expose \`/acme/proxy/<slug>/directory\` with its own slug.

### External Account Binding (EAB)
Some CAs require EAB credentials to link your ACME account with an existing account at the CA:

1. Register at your CA's portal to obtain **EAB Key ID** and **HMAC Key**
2. Enter both values (**EAB Key ID**, **EAB HMAC Key**) on the CA account in **Certificate Authorities (CA)**
3. The HMAC key is base64url-encoded (provided by the CA)

> 💡 EAB is required by ZeroSSL, HARICA, Google Trust Services, and most enterprise CAs.

### ECDSA vs RSA Keys

| Key Type | Size | Security | Performance |
|---|---|---|---|
| **RSA-2048** | 2048 bit | Standard | Baseline |
| **RSA-4096** | 4096 bit | Higher | Slower |
| **ECDSA P-256** | 256 bit | ≈ RSA-3072 | Much faster |
| **ECDSA P-384** | 384 bit | ≈ RSA-7680 | Faster |

ECDSA keys are recommended for modern deployments: smaller, faster, and equally secure.

### Key Source
When requesting a certificate, choose where the private key comes from:

- **Generate new key** *(default)*: UCM creates a fresh key pair for each order
- **Reuse key on renewal**: keep the same private key across renewals (needed for DANE/TLSA records and key pinning); the first issuance generates the key, renewals reload it
- **Provide external CSR**: paste a PEM CSR generated elsewhere; UCM submits it at finalize and the private key never enters UCM. CSR domains must exactly match the order identifiers

In FIPS mode, reusing the key of a source certificate is refused when FIPS does not approve that key (ML-DSA included).

### Preflight (dry run)
**Run Preflight** on the request form validates the whole request against the Let's Encrypt **staging** directory, without consuming production rate limits:

- Checks domain syntax, contact email, ACME account / EAB and CA connectivity
- **Full** mode creates a staging order and previews the exact \`_acme-challenge\` TXT records to publish
- **Validate only** checks configuration and connectivity without creating an order
- Optionally verifies DNS TXT propagation after you added the records

> 💡 Custom CAs have no staging endpoint: preflight then validates configuration and connectivity only.

### DNS Providers
Configure DNS-01 challenge providers for domain validation. Supported providers include:
- Cloudflare
- AWS Route 53
- Azure DNS
- Google Cloud DNS
- DigitalOcean
- OVH
- Tencent Cloud DNSPod
- Plesk (XML API): **Verify TLS Certificate** can be turned off for a self-signed panel, and a DNS propagation delay added
- And more

Each provider requires API credentials specific to the DNS service.

Cleanup removes only the TXT value of its order, so another order, or the wildcard and apex sharing the name, keep theirs; DuckDNS, Hurricane Electric and FreeDNS hold one value per name, so they clear it only when no other order in progress uses it and refuse an order for a domain and its wildcard (v2.252). Vercel takes an optional **Team ID** for domains owned by a team, and RcodeZero needs a token with zone read and write access. A provider name already in use is refused (v2.251). The RFC 2136 provider accepts a host name as DNS server and uses a filled-in **Zone** for the names inside it; otherwise the zone comes from the SOA the configured server returns (v2.252).

#### Custom Command provider
For DNS services without a native driver, the **Custom Command** provider runs admin-configured local commands for TXT record create/delete. Record details are passed as environment variables:

- \`DOMAIN\`: base domain being validated
- \`RECORD_NAME\`: full TXT record name (\`_acme-challenge.example.com\`)
- \`RECORD_VALUE\`: TXT content (challenge digest)
- \`TTL\`: record TTL in seconds
- \`ACTION\`: \`create\` or \`delete\`

The command requires an **absolute binary path**, runs without a shell (no pipes or expansion), and is killed after a configurable timeout (5-300 s, default 60). Use a small wrapper script to bridge any external DNS tooling.

### Custom DNS Resolvers
**DNS-01 resolvers** chooses where UCM looks up \`_acme-challenge\` TXT records: **Automatic** (listed resolvers, then the zone's authoritative servers, then public resolvers, then the system resolver), **System resolver only**, or **Listed resolvers only**. The restricted modes never query public resolvers, for networks that block them. Entries are comma-separated IPs with an optional port, e.g. \`127.0.0.1:5353\` or \`[2001:db8::53]:5300\`.

### HTTP-01 Challenges
UCM serves the challenge file of its pending orders at \`/.well-known/acme-challenge/<token>\`, on the HTTP protocol port (8080 by default). The CA fetches it on port 80 of the domain, so forward that path to UCM from your reverse proxy, or bind UCM to port 80. **Verify Challenge** fetches the file first and does not submit when it is not served; **Force verification** submits anyway. HTTP-01 orders renew automatically.

### Domains
Map your domains to DNS providers. When requesting a certificate for a domain, UCM uses the mapped provider to create DNS-01 challenge records.

1. Click **Add Domain**
2. Enter the domain name (e.g., \`example.com\` or \`*.example.com\`)
3. Select the DNS provider
4. Click **Save**

> 💡 Wildcard certificates (\`*.example.com\`) require DNS-01 validation.

## ACME Proxy Mode

ACME Proxy lets internal clients request certificates from a public CA (Let's Encrypt, ZeroSSL, etc.) through UCM, without direct internet access. UCM acts as an intermediary, handling DNS-01 challenges and forwarding requests to the upstream CA.

### When to Use Proxy Mode
- Internal servers that cannot reach the internet directly
- Centralized DNS-01 challenge handling through UCM's configured DNS providers
- Audit and tracking of all public certificate issuance

### Configuration
1. Open **ACME**, view **Client settings**
2. Scroll down to the **ACME Proxy** section
3. Select an **Upstream CA account** from **Certificate Authorities (CA)** (Let's Encrypt, Actalis, ZeroSSL, custom directory URL, EAB)
4. Click **Test Connection** to verify connectivity with the upstream CA
5. Register the upstream account if needed (email + **Register Account**)
6. UCM automatically registers an account on first proxy request if not already done

### Dedicated proxy paths (multi-CA)
Each external CA account can expose its own ACME proxy endpoint:

1. Open the **Upstream CAs** view
2. Edit or create a CA account
3. Enable **Expose via ACME proxy**
4. Set a unique **Proxy path (slug)**: e.g. \`actalis-production\`, \`letsencrypt-staging\`
5. Save: the URL appears in the proxy section and on the account card

Clients use:
\`\`\`
https://your-ucm-server:8443/acme/proxy/<slug>/directory
\`\`\`

The legacy default path remains available for the account selected in proxy settings:
\`\`\`
https://your-ucm-server:8443/acme/proxy/directory
\`\`\`

Reserved slugs (cannot be used): \`directory\`, \`new-order\`, \`challenge\`, \`acct\`, etc.

### Account Management
- The **account status badge** shows whether UCM is registered with the upstream CA
- Each CA account keeps its own upstream registration: switching the upstream account uses that account's, registered on the first proxy request if needed
- Use the **Reset Account** button to manually clear credentials if needed
- **Test Connection** checks if the upstream directory is reachable and whether EAB is required

### Prune Replaced Certificates
Each proxy renewal imports a fresh certificate into the inventory, so replaced ones pile up over time. The **Purge replaced certificates** toggle (proxy settings) cleans up automatically: when a proxy order finalizes, certificates previously imported by proxy orders for the **exact same domain set** are deleted.

- **Revoked certificates are always kept**: the revocation record stays intact
- Certificates not issued through the proxy are never touched
- Off by default

### Using the Proxy
Point your internal ACME clients to the proxy directory for the target CA.

**Per-CA slug URL** (recommended when several CAs are exposed):
\`\`\`
https://your-ucm-server:8443/acme/proxy/<slug>/directory
\`\`\`

**Default URL** (uses the account selected in proxy settings):
\`\`\`
https://your-ucm-server:8443/acme/proxy/directory
\`\`\`

Example with certbot (replace \`<slug>\` with your CA slug):
\`\`\`
certbot certonly \\
  --server https://your-ucm-server:8443/acme/proxy/<slug>/directory \\
  --preferred-challenges dns-01 \\
  --authenticator manual \\
  --manual-auth-hook /bin/true \\
  --manual-cleanup-hook /bin/true \\
  --non-interactive --agree-tos -m you@example.com \\
  -d subdomain.example.com
\`\`\`

> 💡 The EAB credentials of the upstream CA account are separate from client EAB: they authenticate UCM with the upstream CA, not your clients with UCM. Set them on that account in **Certificate Authorities (CA)**.

> ⚠ Prerequisite: the domain (or a parent domain covering subdomains) must be configured in ACME Domains with a DNS provider. The proxy supports dns-01 only.

> ⚠ Avoid concurrent requests for the same FQDN (Certbot + UCM UI): the second TXT record may overwrite the first.

Errors of the upstream CA reach the client with their ACME type, status and Retry-After (a rate limit is a 429 \`rateLimited\`, not a proxy failure). A profile, \`notBefore\` and \`notAfter\` are passed upstream; a profile the upstream CA does not list is refused with \`invalidProfile\`. When the DNS provider refuses the TXT record, the challenge is not submitted upstream and the order turns invalid, with the provider's message in the logs. When the upstream CA refuses the challenge response, or answers a 5xx or nothing and the authorization does not show the challenge taken, the order also turns invalid for good with the upstream error and its TXT records are removed, so the client's next order is validated again. A CSR that does not name exactly the order's identifiers is refused with \`badCSR\` before reaching the upstream CA (v2.252).

> ℹ️ In lab/self-signed deployments, add \`--no-verify-ssl\` to Certbot.

### DNS UPDATE (RFC 2136)
Clients that can use only a standard rfc2136 solver can use the ACME proxy too. They send the DNS update to UCM, and UCM creates the TXT record with its own DNS provider.

#### Set up
1. Enable **Expose via ACME proxy** on the CA account and set a proxy path (see above)
2. In the **ACME Proxy** section, set the **DNS UPDATE listener port** (0 disables it, 1024 to 65535). Restart UCM to apply it
3. Make the port reachable from the internal network only. For port 53, map it to the listener in Docker or Kubernetes, or with a firewall redirect
4. On the CA account card, click **DNS UPDATE keys (RFC 2136)**, then **New key**
5. Pick an algorithm (hmac-sha256 is the default) and, if needed, an EAB credential
6. Copy the secret and the configuration snippet for your client. UCM shows the secret once

#### What UCM accepts
- Only TXT records under \`_acme-challenge\` with the value that UCM expects for the order
- UCM always answers a delete with NOERROR
- A key works for the proxy account it belongs to. With an EAB link, it works only for orders of the ACME account registered with that credential
- Revoke a key to stop it at once. Delete a revoked key to remove it

#### Client notes
- **Algorithm**: UCM refuses the defaults of many clients (HMAC-MD5, hmac-sha1). Set hmac-sha256 (or sha512) in every client
- **certbot**: \`dns_rfc2136_server\` must be an IP address. Set \`dns_rfc2136_algorithm = HMAC-SHA256\`
- **lego**: set \`DNSUPDATE_TSIG_ALGORITHM\`. The default is hmac-sha1. Use \`--dns.propagation-wait\` if lego cannot see the public zone
- **cert-manager**: supports HMACSHA256 and HMACSHA512 only, not sha384. It finds the zone with its recursive resolvers: set \`--dns01-recursive-nameservers\` to a resolver that sees the public zone
- **acme.sh**: use \`dns_nsupdate\` with \`NSUPDATE_KEY\` that points to the BIND key file. Use \`--dnssleep\` if the public DNS checks fail
- **win-acme**: always sends the update to port 53 (\`--serverport\` is used as a timeout), so map port 53 to the UCM listener. It computes hmac-sha384 wrongly: use sha256
- **Posh-ACME**: \`DDNSNameserver\` is required. Without it, nsupdate sends the update to the zone MNAME on port 53

Example (acme.sh):
\`\`\`
export NSUPDATE_SERVER="ucm.example.com"
export NSUPDATE_SERVER_PORT="8053"
export NSUPDATE_KEY="/etc/ucm-tsig.key"
acme.sh --issue --dns dns_nsupdate --server https://ucm.example.com/acme/proxy/<slug>/directory -d www.example.com --dnssleep 30
\`\`\`

> ⚠ Use the listener in the internal network only. Do not publish it on the internet.

## Local ACME Server

### Configuration
- **Enable/Disable**: Toggle the built-in ACME server
- **Default CA**: Select which CA signs certificates by default
- **Terms of Service**: Optional title and Markdown text, served by UCM and linked from the directory

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
1. **Local Domain mapping**: Exact match, then parent domain match
2. **DNS Domain mapping**: The CA configured for the DNS provider
3. **Global default**: The CA set in ACME server configuration
4. **First available**: Any CA with a private key

### EAB Credentials (Server-side)
When UCM is the ACME server (or proxy), you can require **External Account Binding**: clients must present a pre-issued kid + HMAC key to register an account. Issue and revoke credentials from **ACME → EAB Credentials**.

Each credential can be restricted to the **domains it may request certificates for**:
- \`*\`: any domain (the default for new and pre-existing credentials)
- \`*.example.com\`: the domain and all its sub-domains
- An explicit list of domains
- An **empty list blocks issuance entirely** for that credential

Restrictions are enforced on new-order and new-authz, on both the built-in ACME server and the proxy. They are only meaningful when **EAB is required**: otherwise clients can simply register without a credential.

### Accounts
View registered ACME client accounts:
- Account ID and contact email
- Registration date
- Number of orders

### History
Browse the certificates issued through ACME:
- Common name
- Status
- Issuer
- Expiry date
- Source

### Requested dates
An order may carry \`notBefore\` and \`notAfter\` (cert-manager with a \`duration\`, lego \`--not-after\`). The certificate is issued with exactly those dates, or the request is refused as \`malformed\`: a window longer than the profile's validity (15 minutes of clock skew aside), outside the issuing CA's validity, or already past. A window longer than a policy's maximum validity is refused at finalize as \`malformed\` and the order becomes invalid; one ending past a key type horizon is refused as \`badCSR\` and the order stays ready for a CSR with another key. Without them the profile's validity applies.

### Revocation
A client revokes with its account key or with the certificate's own key, and the certificate it sends must match the stored one byte for byte: a serial number alone is never enough. An account holding valid, unexpired authorizations for every name and IP address of a certificate this ACME server issued may revoke it too, whoever ordered it; authorizations granted by auto-approval do not count. Only an RSA or EC P-256, P-384 or P-521 key can sign an ACME request, so an ML-DSA, EdDSA or Brainpool certificate is revoked with the account that ordered it; UCM says so in the refusal.

## IP Address Certificates (RFC 8738)

The local ACME server can issue certificates for **IP addresses** (IPv4 and IPv6), not only DNS names. This is useful for internal services, appliances, and hosts addressed directly by IP.

### Ordering an IP certificate
Use the \`ip\` identifier type in the ACME order:
\`\`\`json
{
  "identifiers": [
    { "type": "ip", "value": "192.0.2.10" },
    { "type": "ip", "value": "2001:db8::1" }
  ]
}
\`\`\`
Mixed DNS + IP orders are also supported.

### Validation
- **HTTP-01** and **TLS-ALPN-01** are the only challenges offered for IP identifiers. **DNS-01 is forbidden** for IPs by RFC 8738.
- **HTTP-01** connects directly to the IP (IPv6 literals are bracketed, e.g. \`http://[2001:db8::1]/...\`).
- **TLS-ALPN-01** uses the reverse-DNS form of the IP (\`in-addr.arpa\` / \`ip6.arpa\`) as the SNI hostname.

- **TLS-ALPN-01** requires the validation certificate's SubjectAltName to hold exactly the validated name or IP, nothing else.

### Issued certificate
The signed certificate contains an **iPAddress** SubjectAltName entry for each validated IP. The CSR may also put one of the order's IP addresses in its common name.

> 💡 Internal addresses (RFC1918, loopback) validate out of the box. UCM's primary deployment model. Cloud-metadata IPs remain blocked.

## Persistent DNS Validation (dns-persist-01)

The local ACME server supports **dns-persist-01** (draft-ietf-acme-dns-persist): validation through a **persistent** TXT record bound to the ACME account, renewals need no DNS writes.

### Setup
1. Enable it under **ACME → Local ACME → Persistent DNS Validation** (off by default).
2. Create the record once:
\`\`\`
_validation-persist.app.example.com. IN TXT "ca.example.com; accounturi=https://ca.example.com/acme/acct/<id>"
\`\`\`
The challenge object advertises the expected \`accounturi\` and \`issuer-domain-names\`.

### Options
- \`policy=wildcard\`: also authorizes wildcard certificates and subdomains of the validated name (a record on a parent domain covers its children)
- \`persistUntil=<unix-timestamp>\`: stops new validation attempts after that time

> ⚠️ The record grants issuance capability to the ACME account key for as long as it exists: delete the TXT record to revoke it.

## Using certbot

\`\`\`
# Register account (Let's Encrypt: default)
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

## Renewal Information (ARI, RFC 9773)

The local ACME server advertises \`renewalInfo\` in its directory and serves a per-certificate **suggested renewal window**.

- Window centered before expiry → renewals spread over time
- Revoked certificate → window in the past (renew now)
- Unauthenticated GET on \`/acme/renewalInfo/<certID>\`
- ACME proxy: the upstream CA's window is relayed with its Retry-After for a certificate issued through the proxy; computed locally when the CA has none or does not answer
`
  },

  // ===================================================================
  est: {
    title: 'EST Protocol',
    content: `
## Overview

Enrollment over Secure Transport (EST) is defined in **RFC 7030** and provides certificate enrollment, re-enrollment, and CA certificate retrieval over HTTPS. EST is the modern replacement for SCEP, offering stronger security through mutual TLS (mTLS) authentication.

## Configuration

### Configuration

1. **Enable EST**: Toggle the EST protocol on or off
2. **Signing CA**: Select which Certificate Authority signs EST-enrolled certificates
3. **Authentication**: Configure HTTP Basic Auth credentials (username and password)
4. **Certificate Validity**: Default validity period for EST-issued certificates (in days)
5. **CA labels**: serve other CAs under \`/.well-known/est/<label>/\`. An operation name (\`cacerts\`, \`simpleenroll\`, \`simplereenroll\`, \`fullcmc\`, \`serverkeygen\`, \`csrattrs\`) cannot be a label (RFC 7030 §3.2.2, v2.252)

### Saving Configuration

Click **Save** to apply changes. The EST endpoints become available immediately when enabled.

## Authentication

EST supports two authentication methods:

### Mutual TLS (mTLS): Recommended

The client presents a certificate during the TLS handshake. UCM validates the certificate and authenticates the client automatically.

- **Strongest method**: cryptographic client identity
- **Required for** \`/simplereenroll\`: the client must present its current certificate
- **Port 8443**: when UCM terminates TLS, the handshake accepts certificates of the mTLS trusted CA (Settings → Security) and of the CAs below it only; to re-enroll certificates of an EST CA outside that branch, trust a CA above both (v2.252)
- **Presented certificate**: for \`/simpleenroll\` and \`/serverkeygen\`, a certificate signed by the EST CA must be one it still holds: revoked, superseded or deleted certificates are refused (RFC 7030 §3.3.2). A certificate another CA of this server issued is refused once it or a CA above it is revoked, or once expired (v2.252); one from an authority this server does not hold is left to the TLS layer
- **tls-unique linking**: a CSR with a \`challengePassword\` must carry the \`tls-unique\` value of its TLS 1.2 connection to UCM (RFC 7030 §3.5), and is refused with 400 when the value differs or cannot be verified (TLS 1.3, a proxy in front); \`/csrattrs\` does not ask for one. \`ignore_challenge_password\`, set through \`PATCH /api/v2/est/config\`, skips the check for a client that puts a password there (v2.252)
- **Depends on** proper TLS termination config (reverse proxy must pass \`SSL_CLIENT_CERT\` to UCM)

### HTTP Basic Auth. Fallback

Username and password authentication over HTTPS. Configured in EST Settings.

- **Simpler to set up**: no client certificate needed
- **Less secure**: credentials transmitted per request (protected by HTTPS)
- **Use when** mTLS infrastructure is not available
- **Password only**: with \`allow_empty_username\` set through \`PATCH /api/v2/est/config\`, a client may send an empty username with the password (RFC 7030 §3.2.3, v2.252)

A CSR whose key was revoked as compromised is refused with 400, and every enrollment refusal, rate limiting included, comes as a plain-text message saying why (RFC 8951 §5, v2.252).

## EST Endpoints

All endpoints are under \`/.well-known/est/\`:

### GET /cacerts
Retrieve the CA certificate chain. **No authentication required.**

Use this to bootstrap trust: clients fetch the CA cert before enrollment.

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
Renew an existing certificate. **Requires mTLS**: the client must present the certificate being renewed, or gets 403. A CSR without SubjectAltName renews the certificate's own names, or none when it had none, not a name built from the CN (RFC 7030 §4.2.2, v2.252).

\`\`\`bash
curl -k --cert client.pem --key client.key \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @csr.pem \\
  https://your-server:8443/.well-known/est/simplereenroll
\`\`\`

### GET /csrattrs
Get the CSR attributes recommended by the server: keyUsage, subjectAltName and extKeyUsage as bare OIDs, the form RFC 9908 §5.2 gives for an OID asked for without a value (v2.252). A client that needs the former shape (the OIDs inside an extensionRequest attribute) gets it back with \`csrattrs_legacy_encoding\` set through \`PATCH /api/v2/est/config\`.

### POST /serverkeygen
Server generates a key pair and returns the certificate along with the private key. Useful when the client cannot generate keys locally.

The generated key takes the issuing CA's strength: the family of the request's key when it is RSA or EC (its size or curve is ignored), else the CA's, moved to the closest type the policies allow.

The private key comes as unencrypted PKCS#8 (\`application/pkcs8\`), protected by TLS. To get it encrypted, authenticate with mTLS and put the client certificate's key identifier in the CSR (AsymmetricDecryptKeyIdentifier): the key then arrives in an RFC 5958 key package enveloped for that certificate, by key transport for an RSA certificate of 2048 bits or more asserting keyEncipherment or by key agreement (ECDH) for an EC certificate asserting keyAgreement, with the key transport or key agreement and content algorithms taken from the CSR's SMIMECapabilities in the client's order. The package is signed by an "EST key generator" certificate that the issuing CA issues on first use and renews by itself; it chains to the CA that \`/cacerts\` serves and has the CA's key family, Ed25519 under an Ed448 CA (v2.252).

## Endpoints

The detail of an endpoint displays:
- **Endpoint URLs**: Copy-paste ready URLs for each EST operation
- **Enrollment Statistics**: total, successful and failed enrollments

## Integration Examples

### Using est client (libest)
Use \`estclient\` with HTTP Basic credentials (\`-u\` and \`-h\`) or a client certificate. Its TLS-SRP options do not apply: UCM does not offer TLS-SRP.

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
  base64 -d | openssl pkcs7 -inform DER -print_certs -out client.pem
\`\`\`

The answer is a base64 PKCS#7 (certs-only), not a bare certificate: read it with \`openssl pkcs7\`, not \`openssl x509\`.

### Windows
Windows has no built-in EST client: \`certutil -enrollmentServerURL\` registers a certificate enrollment web service (WSTEP), not an EST server. For Windows machines, use Windows Autoenrollment (XCEP/WSTEP).

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

1. **Client creates a timestamp request**: hashes a file with SHA-256/SHA-512 and creates a \`TimeStampReq\` (ASN.1 DER-encoded)
2. **Client sends request to TSA**: HTTP POST to the \`/tsa\` endpoint with \`Content-Type: application/timestamp-query\`
3. **UCM signs the timestamp**: the dedicated signing certificate signs the hash + current time into a \`TimeStampResp\`. The configured CA's own certificate signs only when **Require a dedicated TSA certificate** is turned off
4. **Client receives and stores the response**: the \`.tsr\` file can later prove the document existed at that time

## Configuration

### Configuration

1. **Enable TSA**: Toggle the TSA server on or off
2. **Signing CA**: Select which Certificate Authority signs timestamp tokens
3. **Policy OID**: Object Identifier for the TSA policy, included in every timestamp response
4. **Require a dedicated TSA certificate**: On by default: refuse to sign timestamps with the CA certificate itself, so \`/tsa\` answers 503 until a dedicated end-entity signing certificate with a **critical timeStamping EKU** (RFC 3161) is set. **Generate a signing certificate** issues one from the signing CA and selects it. Turning the option off lets the CA certificate sign, which is not RFC 3161 compliant; an installation upgraded from 2.x whose TSA signed with its CA keeps it off, and the overview shows a warning

### Choosing a Signing CA

The signing CA's private key is used to sign every timestamp token. Best practices:

- Use a **dedicated sub-CA** for timestamping rather than your root CA
- RFC 3161 §2.3 requires a signer whose only, critical EKU is **id-kp-timeStamping** (OID 1.3.6.1.5.5.7.3.8), which a CA certificate cannot carry without losing its other uses. Tokens signed by the CA certificate are refused by strict verifiers: \`openssl ts -verify\` fails with "unsuitable certificate purpose" and jarsigner with "Certificate is not valid for timestamping". The configuration warns while the CA certificate signs: **generate a dedicated signing certificate** there for these clients
- Ensure the CA certificate has **sufficient validity**: timestamps must remain verifiable for years. A CA outside its validity period does not sign: \`/tsa\` answers 503
- Keep **Require a dedicated TSA certificate** on to enforce this at signing time

### Policy OID

The Policy OID identifies the TSA policy under which timestamps are issued. It is embedded in every \`TimeStampResp\`.

- Default: \`1.2.3.4.1\` (placeholder: OpenSSL's example OID, assigned to no one; the configuration warns while it is in use)
- For production, register an OID under your organization's arc or use one from your CP/CPS

## Endpoint

The detail of the service displays:

- **TSA Endpoint URL**: Copy-paste ready URL for client configuration
- **Usage Examples**: OpenSSL commands for creating requests, sending them, and verifying responses
- **Statistics**: Total timestamp requests processed (successful and failed); every rejected request is audited as \`tsa.timestamp_rejected\` with its failure code

## Usage Examples

### Create a Timestamp Request

\`\`\`bash
# Hash a file and create a timestamp request (-cert: embed the signer certificate)
openssl ts -query -data file.txt -sha256 -cert -out request.tsq
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

\`openssl ts -verify\` needs a dedicated signing certificate (a token signed by the CA certificate fails) and checks RSA and ECDSA tokens only. An ML-DSA token verifies with \`openssl cms -verify\` (OpenSSL 3.5 or later); then compare its message imprint with the hash of the file.

### Code Signing with Timestamps

When signing code, add the TSA URL to ensure signatures remain valid after certificate expiry. Configure a dedicated signing certificate first: jarsigner refuses a token signed by the CA certificate ("Certificate is not valid for timestamping").

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
| Hash Algorithms | SHA-256, SHA-384, SHA-512 (SHA-1 and MD5 refused with badAlg) |
| Request extensions | None accepted: any extension, critical or not, is refused with unacceptedExtension |
| Malformed request | badDataFormat (trailing bytes included) |
| genTime / accuracy | Whole seconds, accuracy 1 second |
| Message imprint | Copied from the request as sent |
| Authentication | None (public endpoint) |
| Transport | HTTP or HTTPS |

## Security Considerations

- The TSA endpoint is **public**: no authentication is required (same as CRL/OCSP)
- Each timestamp response is **signed** by the dedicated signer or the CA key: clients verify the signature to ensure authenticity
- Use **SHA-256 or stronger** hash algorithms when creating requests (SHA-1 is refused)
- The TSA does **not** see the original document: only the hash is transmitted
- Consider **rate limiting** if the TSA endpoint is exposed to the internet

> 💡 Timestamps are essential for code signing: they ensure your signed software remains trusted even after the signing certificate expires.
`
  },

  // ===================================================================
  truststore: {
    title: 'Trust Store',
    content: `
## Overview

The Trust Store keeps trusted CA certificates. Fill it from the CAs UCM manages or from the operating system's trust store.

## Certificate Categories

- **Root CA**: Self-signed trust anchors
- **Intermediate**: CAs signed by root or other intermediates
- **System**: Imported from the operating system trust store
- **Code Signing**: Certificates for code signature verification
- **Email**: Certificates for S/MIME
- **Custom**: Manually categorized certificates

## Adding Certificates

### From managed CAs
**Add** lists the CAs UCM manages: select those to trust.

### External certificates
The page has no upload form for a certificate from outside UCM. Add it through the API: \`POST /api/v2/truststore\` with its PEM, or \`POST /api/v2/truststore/import\` with a PEM or DER file. An entry that contains a private key is refused: the trust store holds certificates only, and only the certificates of a file are kept.

### Sync from System
Import the trusted CAs of the operating system's trust store (e.g., Mozilla's CA bundle on Linux), up to the chosen count: 500 by default, 1000 at most.

> 💡 Sync from System is a one-time import. Changes to the OS trust store are not automatically reflected.

## Managing Entries

- **Filter by type**: Narrow the list by certificate category; the chips count Valid, Expiring soon and Expired entries
- **Usage**: The list shows each entry's description as its usage; a name opens its detail (Overview, Details, PEM) under the list
- **Search**: Find certificates by subject name
- **Export**: Download individual certificates in PEM format
- **Delete**: Remove a certificate from the trust store
- **Delete selected**: Select several certificates and remove them together, for instance the system CAs filtered as expired; only the rows the current filters show are removed

## Use Cases

### Chains
A certificate's chain view, and its exports with the chain, take a trust store certificate whose subject matches the issuer name to complete the chain. No signature is verified against the trust store.

The trust store plays no part in mTLS client authentication (which uses the trusted CA chosen under Settings › Security) or in the ACME client's connection to its CA.
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
- **Active**: Can log in and perform actions
- **Disabled**: Cannot log in, data is preserved

Toggle a user's status without deleting their account.

### Password Reset
Admins can reset any user's password. The user is not asked to change it at the next login: give them the new password and ask them to change it under My Account.

### Security Keys
In a user's details, administrators see that user's security keys and can disable or remove one, typically a lost key, which otherwise still signs in without a password. Removing the last second factor of an account that requires one asks for a second confirmation; the user then enrols a factor again at the next login.

### Deleting a User
Deleting a user revokes the certificates they enrolled for mTLS (reason cessationOfOperation), then deletes them. A certificate the CA cannot revoke does not block the deletion: it stays valid, the warning and the audit log name it, and you revoke it under Certificates. If the deletion fails after some revocations, the message names the certificates already revoked: they stay revoked.

### API Keys
Each user can have multiple API keys for programmatic access. API keys inherit the user's role permissions. See the Account page for managing your own keys.

## Groups Tab

### Creating a Group
1. Click **Create Group**
2. Enter a **name** and optional description
3. Select the **permissions** the group grants (members receive them on top of their own role)
4. Click **Create**

### Managing Members
- Click a group to see its members
- Use the **transfer panel** to add/remove users
- Users can belong to multiple groups

### Group Permissions
A user's effective permissions are the **union** of:
- Their directly assigned role's permissions
- Their custom role's permissions, if any
- The permissions granted by every group they belong to

## Roles

### System Roles
- **Admin**: Full access to all features
- **Operator**: Can manage certificates, CAs, CSRs, ACME, SSH and system settings; templates and groups read-only, no access to users or RBAC
- **Auditor**: Read-only access to all operational data for compliance and audit
- **Viewer**: Read-only access to certificates, CAs, and templates

### Custom Roles
Create roles with granular permissions on the **RBAC** page.

> 💡 Use groups to manage team permissions rather than assigning roles to individual users.

## Authentication Source

The **Source** column shows what opens each account:
- **Local**: created and managed in UCM (local password)
- **LDAP / OAuth2 / SAML**: one entry per provider attached to the account, by type and name (e.g. \`LDAP · Corporate AD\`); an account may have several.

Since v2.133, roles changed manually in UCM for SSO users are **preserved** between logins, unless **"Sync role on every login"** is enabled on the provider (see **Settings → SSO**).

The account panel lists its **Single sign-on providers**, each linked, waiting for its first sign-in, or left by a deleted provider. **Attach a provider** adds one: the providers already attached keep opening the account, and the next sign-in through the new one with the account's username or email binds its identity. **Reset identity** clears the identity of one provider whose IdP changed it, and **Detach** removes one provider, each after a confirmation; attaching, resetting and detaching close every session of the account. To move an account to another provider, attach the new one, then detach the old one. A password the account has is kept unless the box that removes it is ticked, after which no password login opens the account; an account without a password is asked to set one only when its last provider is detached, and then becomes a local account.
`
  },

  // ===================================================================
  rbac: {
    title: 'Role-Based Access Control',
    content: `
## Overview

RBAC provides fine-grained permission management. Define custom roles with specific permissions and assign them to users; a group grants its own permission set to its members.

## System Roles

Four built-in roles that cannot be modified or deleted. The RBAC page shows each with the permissions UCM applies to it:

- **Admin**: Full access to everything
- **Operator**: Manage certificates, CAs, CSRs, ACME, SSH and system settings; templates and groups read-only. No access to users or RBAC
- **Auditor**: Read-only access to all operational data (certificates, CAs, ACME, SCEP, HSM, audit logs, policies, groups) but not settings or user management
- **Viewer**: Basic read-only access to certificates, CAs, CSRs, templates, and trust store

## Custom Roles

### Creating a Custom Role
1. Click **Create Role**
2. Enter a **name** and optional description
3. Configure permissions using the **permission matrix**
4. Click **Create**

### Permission Matrix
Permissions are organized by category:
- **CAs**: Create, read, update, delete, import, export (certificate only: see Private Keys)
- **Certificates**: Issue, read, revoke, renew, delete, export (certificate only: see Private Keys)
- **Private Keys**: Direct private-key export of a certificate or a CA (\`read:private_keys\`). No built-in role except Admin holds it; a custom role can grant it. Roles without it go through Key Recovery
- **CSRs**: Create, read, sign, delete
- **Templates**: Create, read, update, delete
- **Users**: Read (account management is reserved for administrators)
- **Groups**: Read (creating, editing and deleting groups is reserved for administrators)
- **Settings**: Read, update
- **Audit**: Read, export (cleanup is reserved for administrators)
- **ACME**: Configure, manage accounts
- **SCEP**: Configure, approve requests
- **Trust Store**: Manage trusted certificates
- **HSM**: View, delete (adding or changing providers is reserved for administrators)
- **SSH**: Manage SSH CAs and certificates
- **Policies**: View certificate policies
- **Approvals**: View and decide approval requests
- **Key Recovery**: Request recoveries and view requests (approval is admin-only)

A custom role can grant every permission UCM checks except those kept for administrators: full access and wildcards, every administration action (approving key recoveries, system and user administration), account management, SSO, deployments, AD connector and HSM provider changes, system-wide events and deleting the audit trail. A stored permission the role cannot grant is shown as ignored and kept as it is.

### Category Toggles
Click a category header to enable/disable all permissions in that category at once.

### Coverage Indicator
A bar and an n/N count show how much of the total permission set the role covers.

## Assigning Roles

Roles are assigned:
- **Directly**: On the Users page, edit a user and select a built-in role and, optionally, a custom role that adds to it. Changes apply from the user's next request
- **Via Groups**: A group grants a permission set; every member receives it in addition to their own role

## Effective Permissions

A user's effective permissions are computed as the union of:
1. Their built-in role's permissions
2. Their custom role's permissions, including the roles it inherits from
3. The permissions granted by groups they belong to

The most permissive rule wins (additive model, no deny rules).

> ⚠ System roles cannot be edited or deleted. Create custom roles for specific needs.
`
  },

  // ===================================================================
  systemLogs: {
    title: 'System Logs',
    content: `
## Overview

Reads back what UCM itself wrote, without shell access to the host. It is the log that explains a failure no record was ever created for: a SCEP enrolment refused during validation is rejected before a request row exists, so it appears here and nowhere else.

Lines are shown newest first, and every filter is applied on the server, so a filter never hides lines that were simply not fetched.

## Sources

**Source** and **Component** live in the **Filters** dialog: pick the log, then narrow it to one subsystem. Each filter chosen shows under the toolbar, and its cross removes it.

- **Application**: UCM's own log. This is the only source with components.
- **Access**: the gunicorn access log, holding HTTP requests and status codes. Native installs only.
- **Errors**: the gunicorn error log, holding worker startup and unhandled tracebacks. Native installs only.
- **Journal**: the systemd unit journal, where the service user is able to read it.

Only sources this deployment actually has are offered. A source with nothing behind it is left out rather than shown empty.

### Components

**All components** is the whole application log. The list holds every subsystem UCM can log from (\`services\`, \`api\`, \`utils\`, \`security\` and the rest), whether or not it has logged recently, plus the specific loggers the lines on screen came from.

Choosing one takes everything beneath it. \`services\` matches \`services.scep.scep_service\` and every other service; \`services.scep\` narrows to the SCEP subtree.

## Filtering

### Log level
A floor, not an exact match. **WARNING** shows warnings, errors and critical. **DEBUG** shows everything.

A record whose level could not be read is never hidden by this filter: its severity is unknown, and guessing it would hide the lines most worth seeing.

### Search and Exclude
Both match the message and the component name, and both are case-insensitive. **Exclude** removes what matches: the quickest way to silence a heartbeat that repeats every minute and buries the one error.

Both are literal text rather than patterns, so \`.*\` finds those two characters and nothing else. A pattern from the browser is unbounded work for the single worker that answers ACME, SCEP and OCSP from this same process.

### Date
A **From**/**To** window, applied on the server. Unlike the level floor, a record carrying no timestamp is left out when a bound is set: a window asks for an instant, and such a record has none.

### Lines
How many matching lines to return, from 100 to 5000. The footer says when older lines were left off, and how many matched in total.

## Live logs

Polls every five seconds. It clears the date window, which asks the opposite question, and is the quickest way to watch an enrolment or a renewal as it happens.

## Copy

**Copy all**, in the page head, takes every line on screen. Tick the box beside any line and the selection bar offers **Copy selected**. Both copy a line the way the file writes it: time, component, level, message. What lands on the clipboard reads as a log, and pasting it back into this page parses as one.

## Reading the footer

The foot of the page names the file being read, the time zone its timestamps are written in, and whether anything was cut:

- **Showing the N most recent of M matching lines**: more matched than the **Lines** setting allows. Raise it to see further back.
- **Only the most recent part of the file was scanned**: the file is larger than the window the reader scans, so older lines are out of reach at any line count.

Timestamps carry no offset of their own; they are the server's local time, and the zone is named beside the path.

## Access

Reading this log requires administrator rights. It is deliberately not audited: the audit trail is written to this same log, so recording every read would bury the lines the page exists to surface. The diagnostic bundle in **Settings → About** is audited, being a rare and deliberate act that leaves with a copy of the file.
`
  },

  auditLogs: {
    title: 'Activity',
    content: `
## Overview

Every operation in UCM is recorded in the audit log: certificate issuance, revocation, sign-in, setting change. The Activity page lists it, newest first, with who, what, when and the result. The head counts the entries of the whole log; the summary line under the toolbar counts those the filters keep, says since when the log goes back, and sums up the last 30 days.

## An entry

Each row shows the time (the day too when it is not today), the operation (its type pictogram and the action code), the resource, the user and the result (Succeeded or Failed, in words). The resource name or the arrow opens the detail of the entry:
- **Text**: what the server recorded (error messages, values)
- **Resource**, **User**, **Date / time**, **Result**
- **Action**: the code as the server stores it
- **IP address** and **Client** (user agent), when they were recorded

When the entry names a certificate or an authority, **Inspect the certificate** (or **View the authority**) opens it in the inspector.

On a phone each entry is a card with the same facts: a tap anywhere on it, or on its arrow, opens the detail.

## Finding entries

### Search
Free text in the user name, action code, details, resource type and IP address; the resource name itself is not searched.

### Operation type
The select of the toolbar groups the action codes by type: issuances, renewals, revocations, exports, certificates and CSRs, approvals, CRL publications, ACME, SCEP, sign-ins, users, backups, settings, configuration, system. Only the types the log contains are offered.

### Filters
The **Filters** button opens the dates (**From**, **To**), the **User**, the **Result** and the individual action codes (narrowed to the chosen type). Two shortcuts set **Failed logins** or **All failures**. The current filters can be saved under a name and applied again later; they are kept in this browser. Every active filter shows as a chip under the toolbar, and **Reset the filters** clears them all.

The list is read page by page from the server: 25, 50 or 100 entries per page, previous and next, or a page number and **Go**.

## Export

**Export the log** downloads the entries the search and the filters keep, at most 10,000:
- **CSV**: one row per entry, for a spreadsheet
- **JSON**: structured data, every field

On a phone the head button is hidden: the export is in the « ⋯ » menu.

## Cleanup

In the « ⋯ » menu, with the right to delete the log:
1. Choose **Clean up old logs…**
2. Set the retention in days (30 to 365)
3. Choose **Delete old logs**

> ⚠ Cleaning up is irreversible. Export the entries you need first.

## Integrity Verification

**Verify integrity**, in the « ⋯ » menu, checks the audit log chain. UCM uses hash chaining to detect an entry modified or removed inside the chain; removing the latest entries leaves no trace in the chain itself, which is why syslog forwarding keeps a copy elsewhere.

On a large log the verification runs in the background: the summary line shows how many entries are checked so far, **Cancel verification** stops it, and leaving or reloading the page does not stop it (the page picks it up again). One verification runs at a time.

## Syslog Forwarding

Configure remote syslog forwarding in **Settings → Audit** to send log events to an external SIEM or syslog server in real-time.

Every audit event is forwarded by default. Unchecking a category (Certificates, CAs, CSRs, Users, ACME, SCEP, System) stops only its events: ACME covers every ACME event, Users covers sign-ins and logouts, SSO included. Leaving every box unchecked forwards every event. Account changes (creation, role, password, MFA, activation), changes to syslog forwarding itself, audit purges, API keys, roles, settings and policies are always forwarded. Under System, master key downloads, encryption changes, restores, database resets and switches, update settings, backup deletions and log bundle downloads are always forwarded too. A syslog change is sent with the previous configuration, so the collector being narrowed or turned off receives it, and a newly configured collector receives it as well.
`
  },

  // ===================================================================
  settings: {
    title: 'Settings',
    content: `
## Overview

System-wide configuration organized into tabs. Changes take effect immediately unless noted otherwise.

## General

- **Syslog hostname**: Sent as HOSTNAME in forwarded syslog messages; the machine hostname when empty
- **Base URL**: Canonical HTTPS URL of the admin interface and API; other hostnames and IPs redirect to it. Password reset e-mails link to it, else to the server FQDN (\`UCM_FQDN\`); with neither, the login page hides Forgot password and the reset is refused
- **Protocol Base URL**: Base URL written into CDP and OCSP addresses; use http:// to avoid TLS verification loops, or leave empty to use the Base URL
- **HTTP Protocol Port**: Plain HTTP port that serves CDP and OCSP, and SCEP when its Serve on plain HTTP option is on; 0 disables it, a change needs a restart
- **Public ACME vhost**: Concrete hostname in ACME directory URLs (e.g. \`acme.ucm.example.com\`: not \`*.ucm.example.com\`). A wildcard \`*.ucm.example.com\` **TLS certificate SAN** covers both \`admin.ucm.example.com\` and \`acme.ucm.example.com\`. Configure DNS and TLS for the ACME vhost **before** saving: clients that re-read the directory switch URLs immediately.

## Appearance

- **Theme**: Light, Dark, or System (follows OS preference)
- **Accent Color**: Primary color used for buttons, links, and highlights
- **Force Desktop Mode**: Disable responsive mobile layout

## SMTP

Configure SMTP for email notifications (expiry alerts, user invitations):
- **SMTP Host** and **Port**
- **Username** and **Password**
- **Encryption**: None, STARTTLS, or SSL/TLS
- **From Address**: Sender email address
- **Content Type**: HTML, Plain Text, or Both
- **Alert Recipients**: One or more addresses separated by commas; an invalid address is named under the field and not kept

Click **Test** to send a test email and verify the configuration.

### Email Template Editor

Click **Edit Template** to open the template editor, a wide dialog with the source beside its live preview (on a wide screen only):
- **HTML**: Edit the HTML email template; the preview on the right follows as you type
- **Plain Text**: Edit the plain text version for email clients that don't support HTML
- The variables of the chosen format are listed above the source: \`{{title}}\`, \`{{content}}\`, \`{{datetime}}\`, \`{{instance_url}}\`, plus \`{{logo}}\` and \`{{title_color}}\` in HTML
- **Reset to Default**, shown for a custom template, restores the built-in UCM-branded template after a confirmation
- **Save** keeps both versions; **Close** or Escape leaves without saving

### Expiry Alerts

When SMTP is configured, enable automatic certificate expiry alerts:
- Toggle alerts on/off
- Select warning thresholds (90d, 60d, 30d, 14d, 7d, 3d, 1d)
- Run **Check Now** to trigger an immediate scan
- **Skip certificates issued over ACME**: leaves out the certificates issued by UCM's ACME server, which their clients renew; off by default

## Security

### Password Policy
- Minimum length (6-32 characters)
- Require uppercase, numbers, special characters

### Session Management
- Session duration (hours, whatever the activity); the inactivity timeout is under General

### Account Lockout
- Max login attempts and lockout duration, under General: they lock the account, not the IP address

### Admin Access Allowlist
Limit the web interface and the management API to listed IP addresses and CIDR networks; PKI protocols stay reachable from anywhere. See the Security Settings guide.

### 2FA Enforcement
Require all users to enable two-factor authentication.

### Private Key Encryption
Encrypt all private keys stored in the database with AES-128 (Fernet, with HMAC-SHA256), protected by a master key file. The section shows the encryption status and the **encrypted / unencrypted** key counters. Two opt-in environment variables make missing keys fatal at startup: \`UCM_REQUIRE_DB_ENCRYPTION_KEY\` (integration-secret encryption) and \`UCM_REQUIRE_KEY_ENCRYPTION\` (private-key encryption).
A new installation creates the master key at its first start (in a container, only when \`/etc/ucm\` is a volume of its own); the Security section of Settings shows the encryption status, and the Overview shows a banner while no key is loaded.

> 💡 Security-sensitive settings (session, lockout, HSTS, public URL, password policy) require the **admin:settings** permission, the fields are locked for operators.

> ⚠ A list that does not include your own address is refused. If you lose access anyway, set \`UCM_ADMIN_ALLOWLIST_DISABLE=1\` and restart UCM.

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
Click **Create Backup** to generate a database snapshot. Backups include the certificates, CAs, keys and settings; the audit log and other history tables are not included.

A manual backup runs on the server: the dialog shows its progress, can cancel it (no archive is kept) and offers the archive for download when it is ready; closing the dialog or reloading the page does not stop it. One manual backup runs at a time on the whole installation.

### Scheduled Backup
Configure automatic backups:
- Frequency (daily, weekly, monthly, or Off, not recommended, which stops the scheduled backups)
- Retention in days: older backups are pruned (30 by default)
- **Key derivation**: Automatic (Argon2id when available, PBKDF2 in FIPS mode), PBKDF2-HMAC-SHA256 or Argon2id. Archives written with Argon2id cannot be restored on an instance in FIPS mode

### Restore
Upload a backup file to restore UCM to a previous state.

- Backups and restores share one lock: a restore is refused (409) while a backup runs, and a manual backup waits for a running restore
- In HA mode, a restore from any node first has every node refuse writes (503) and leave the balancer's rotation until it ends; it is refused, naming the node, when a node does not acknowledge within 30 s. The nodes then restart one at a time, and each serves the restored state once restarted
- An archive created since 3.0 is restored in chunks, with no size limit unless \`BACKUP_MAX_ARCHIVE_MB\` sets one; an older archive is accepted up to \`BACKUP_MAX_UPLOAD_MB\` (512 MB by default). Both are set in the server environment; a reverse proxy in front of UCM keeps its own body limit
- The restore runs in the background: past 25 seconds its dialog follows it and can cancel it until it commits; meanwhile every write is refused (503), on a single node too, and the report shows after the sign-in its end asks for
- Archives carry ACME client orders, approval requests and key recovery requests (v2.251)
- A DNS provider, ACME CA account or webhook whose name another row holds here is restored as \`name (2)\`
- The API also accepts \`mode=merge\`, which adds the archive to the data here instead of replacing it

> ⚠ Restoring a backup replaces ALL current data.

## Audit

- **Log retention**: Auto-cleanup old logs after N days
- **Syslog forwarding**: Send events to a remote syslog server over TLS (RFC 5425), TCP or UDP
- **Integrity verification**: Check the hash chain that links every audit entry; the chain is always on, there is nothing to enable

## Database

UCM supports two database backends:

- **SQLite** (default): file-based, zero-config, ideal for single-node
- **PostgreSQL 13+**: recommended for HA, multi-instance, or when you already operate a managed PG cluster

The active backend is selected by the \`DATABASE_URL\` environment variable. When unset, UCM uses SQLite at \`DATA_DIR/ucm.db\`.

### Status panel
- Active backend (sqlite / postgresql) and its engine version
- Database size and table count

### Test connection
Validate a \`DATABASE_URL\` (e.g. \`postgresql://user:pass@host:5432/ucm\`) before switching. The test opens a real connection and reports any error. PostgreSQL servers older than 13 are rejected, UCM requires PostgreSQL 13 or newer.

### Switch backend
Persists \`DATABASE_URL\` to \`/etc/ucm/ucm.env\` (DEB/RPM) and restarts UCM. Only the accounts, roles, SSO and MFA tables are copied to the new backend, so you can still sign in; use **Migrate** first if you want to keep your other data.

### Migrate data
Copies all rows from the current backend to the target. Works in both directions (SQLite ↔ PostgreSQL):

1. The source database is backed up to \`/opt/ucm/data/backups/db_migration/\`
2. The schema is created on the target via SQLAlchemy
3. FK checks are disabled during the bulk load
4. Columns are matched by name; only the known legacy columns are dropped, and any other column the target lacks refuses the migration
5. PostgreSQL sequences are reset after load
6. The service restarts automatically (DEB/RPM): on Docker, set \`DATABASE_URL\` in your compose file and restart the container manually

**Safety checks (fail fast, source untouched):**
- The target must be empty. If any of its tables already contains rows, the migration is refused with HTTP 409 and a cleanup hint:
  - PostgreSQL: \`psql ... -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'\`
  - PostgreSQL in a schema other than \`public\` (a \`search_path\` in the URL): the hint names that schema, whose sequences the migration realigns (v2.251)
  - SQLite: delete the target \`.db\` file
- If the migration fails mid-way, the source is left untouched and the error message points to the source backup. Reset the target before retrying.

> ⚠ Always take a full UCM backup (Settings → Backup) before migrating between backends.

## HTTPS

Manage the TLS certificate used by the UCM web interface:
- View the current certificate details
- Import a new certificate (PEM or PKCS#12)
- Generate a self-signed certificate
- When the bound certificate is renewed through a protocol without its key reaching UCM, the page says so: HTTPS keeps serving the previous certificate until the key of the renewed one is imported, which applies it

- Applying, regenerating or renewing the certificate reloads the TLS listener without stopping the service, in a container too (HA: a rolling restart of the nodes)
- *Renewed, not served yet* means the listener still presents another certificate than the one on disk: the service log says why the reload failed

## Updates

- Check for new UCM versions from GitHub releases
- View the changelog for available updates
- Current version and build information
- **Auto-update**: on supported installations (DEB/RPM), click **Install Update** to download and install the latest version automatically
- **HA mode**: on DEB/RPM, **Install Update** and the auto-install update the nodes one at a time, and the screen follows the rolling update (nodes done, node in progress, package of each node, node where it stopped and why, **Resume**)
- **Update channel**: stable, pre-release (release candidates) or dev

## Webhooks

Configure HTTP webhooks to notify external systems on events:

### Supported Events
- Certificate issued, revoked, renewed, expiring, expired, imported, deleted
- CA created, updated, deleted
- CSR submitted, approved, rejected
- Template created, updated
- ACME preflight, renewal failed, revocation failed
- Update available, initiated, installed, failed

Certificate imports and template changes made from the web interface do not emit their event.

### Authentication

Optional outbound authentication (all apply in addition to the optional HMAC signature):

- **None**: No auth header (public webhooks)
- **Bearer**: Authorization: Bearer {token}
- **Basic**: Authorization: Basic base64(username:password)
- **API Key**: Custom header (e.g. X-Api-Key: {token})
- **Custom**: Authorization: {scheme} {token} (e.g. auth-key VALUE)

Tokens are stored encrypted and never returned in the UI.

### Creating a Webhook
1. Click **Add Webhook**
2. Enter the **URL** (HTTPS recommended; http:// is accepted)
3. Select the **events** to subscribe to
4. Choose **authentication type** and provide credentials (optional)
5. Optionally set a **secret** for HMAC signature verification
6. Click **Create**

### Testing
Click **Test** to send a sample event to the webhook URL and verify it's reachable.

## Prometheus metrics

Opt-in, token-gated **\`/metrics\`** endpoint.

- Enable it by setting a metrics token (Settings › General); without a token → 404
- Scrape with the \`Authorization: Bearer <token>\` header
- Exposes \`ucm_certificates\`, \`ucm_certificate_authorities\`, \`ucm_scheduler_task_*\`, \`ucm_webhook_deliveries\`, \`ucm_acme_*\`

## Webhook delivery history

Open the history (clock icon) on a webhook to see its deliveries.

- **pending / delivered / failed** statuses with last HTTP code and error
- **Retry** a delivery manually
- Durable queue with exponential backoff (up to 5 attempts)

## Scheduler view

Settings › Scheduler surfaces the background tasks.

- Task list with **status**, **last run**, **duration** and **failures**
- **Run now** on any task: it waits up to 30 seconds, and a task still running then is reported as started, its result showing on a later refresh
- Covers expiry, CRL, webhook delivery, backups, auto-renewal…
- **Scheduler process** (v2.251): the tasks run in a process of their own, started with the service and restarted within seconds after a crash or a reload, so a long task delays neither requests nor workers. A warning shows when it has not reported for a while

## Auto-renewal
The auto-renewal settings drive the renewal scheduler.
- **Sources**: the scheduler renews certificates whose private key the server holds: by default those issued from the form or a signed request ("manual"), and SCEP, ACME and EST enrolments with a server-generated key. Devices holding their own key renew through their protocol
- **Awaiting approval**: a certificate whose renewal is queued for approval is left to that decision, as long as it can come before the certificate expires
- **Renewed meanwhile**: a certificate an operator renewed during the batch is not renewed a second time; one deleted during the batch is skipped
- **Run now**: runs a renewal pass at once and reports the expiring certificates it left alone, counted by reason: not yet in the last third of their lifetime, private key not held by the server, source not selected

## Scheduled backups

Settings › Backup enables automatic backups.

- **Daily / weekly / monthly** cadence
- **Retention**: backups older than the set number of days are pruned
- **Size ceiling**: a ceiling in MB for all archives (0 for none); the oldest are removed, each audited, until the total fits. Retention never removes, on a single node, the newest archive that matches its validation record, up to 2 archives with no validation record and the minimum kept, and in HA the minimum kept, so the total can stay above the ceiling, which is reported
- Backups are **encrypted** with the backup password
- **High availability**: the archives are stored in PostgreSQL, so every node lists them, with the node that wrote them, and downloads them; retention runs on the leader. They are lost with the database: download the ones you keep out of the cluster, and back PostgreSQL up with its own tools

## Active Directory Connector

UCM's own LDAP connection to Active Directory, independent of any LDAP provider configured under SSO. That one is for logging into UCM; this one is used for certificate-related AD lookups and works whether or not SSO is configured at all.

- **Connectors**: One per directory (forest or domain), listed under Settings → Active Directory with its name, its realm, the domain SID that was read and its health. A Windows enrollment profile names the connector that serves its realm; a connector that profiles use cannot be deleted, and the refusal lists them
- **Purpose**: Resolves a Kerberos machine or user principal to its AD object, so UCM can derive a certificate subject/SAN the same way a real Windows CA would
- **Domain Controllers**: One per row, each by its own hostname, without port or scheme, tried in order: lookups fail over to the next one when a DC is down. A bare domain name fails certificate verification, since a domain controller certificate names only its own host
- **LDAPS**: Toggle to use LDAP over SSL/TLS; **Verify SSL Certificate** validates the DC's certificate (optionally against a custom CA bundle when it isn't publicly trusted)
- **Base DN** and **Bind DN / Password**: the domain's base DN, with its DC components (\`DC=corp,DC=example\`, which also names the Kerberos realm served) on a domain controller port (389 or 636, not a Global Catalog), and the service account used for lookups; Bind DN and password are both required while the connector is enabled
- **Test Connection**: Verify connectivity and credentials before saving
- **Health Check Interval**: Each domain controller is probed with a real bind at this interval; an unreachable one is skipped at enrollment time until it recovers. The verdict shows on the connector's row and against each DC
- **Disabled connector**: A disabled connector looks nothing up, but its base DN still names the realm of the default profile as a last resort, when no enabled connector, SPN or keytab does

The Certificate Enrollment Policy URLs to register in Group Policy are the same for every profile and are shown under Settings → Windows Autoenrollment.

## Windows Autoenrollment (XCEP/WSTEP)

Native Windows certificate enrollment via **MS-XCEP** (policy discovery) and **MS-WSTEP** (certificate issuance and renewal): the same protocols real ADCS uses for MMC "Request New Certificate", \`certreq\`, and unattended GPO autoenrollment.

### Profiles

One **profile per Active Directory realm**. UCM routes a client to its profile by the realm of its Kerberos principal, so every profile has its own issuing CA, policy CA, templates, AD connector and keytab; the UsernamePassword accounts belong to the default profile. The list is paginated and filtered by the server (name or realm, CA, state), so a hundred profiles open as fast as one:
- **Realm**: In capital letters, exactly as the KDC writes it (\`CORP.EXAMPLE\`): a KDC compares realms character by character, so a lowercase name never matches a ticket. The form refuses it and says why
- **Connector**: The AD connector that serves the realm. When its domain differs from the realm of the profile, the form warns, without blocking; the server checks the pair when either is chosen
- **Issuing CA** and **Policy CA**: The CA that issues, and the one XCEP announces (the issuing CA when empty). The policy identifier and the template OIDs belong to the profile: set at its creation, they do not change when either CA does
- **Templates**: The subset offered; none selected offers the templates of the CA. A required AD group and pinned subject fields can replace the template's own for the whole profile
- **State**: Complete, Keytab missing, Connector failing or Disabled. A disabled profile refuses the machines of its realm; its keys stay in the served keytab so that the refusal is made and audited by realm

The **default profile** is the one a 2.x installation turned into; it serves the UsernamePassword binding and holds its accounts. A new installation has none: while no profile is the default, the profile editor offers **Default profile** (on a new profile or a saved one), and the accounts appear once it is checked. The default is then neither withdrawn nor moved, from this screen or the API. Without a realm, Kerberos is refused until one is set (in capitals, or read from its keytab); the screen says so.

### Setup Checklist, per profile

The profile form lists what that profile still lacks: realm, issuing CA, keytab, a reachable connector when one is chosen, a template with autoenrollment allowed, and the profile being enabled.

### Policy Discovery (XCEP)

- **Certificate Authority**: The CA whose templates are advertised and that issues certificates through the profile
- **Validity (days)**: Validity of certificates issued via WSTEP when the request matches no template; a matched template's own validity applies otherwise

A template with an **ML-DSA** key type is announced by its key algorithm OID, with the Microsoft Software Key Storage Provider and a signature-only key spec. It is hidden in FIPS mode when the FIPS module does not approve ML-DSA, and enrollment from a real Windows client has not been tested yet.

An **ECDSA** template is announced in policy schema 3 with its curve (\`ECDSA_P256\`, \`ECDSA_P384\`, \`ECDSA_P521\`) as a signature key and a request hash, the stronger of the template digest and the one matching the curve; RSA templates outside FIPS mode stay schema 2, which names no request hash: Windows then signs its CMC request with SHA-1, which UCM accepts as those clients require; a plain PKCS#10 signed with SHA-1 is still refused. The request key must fit the template it is issued under: the same curve or ML-DSA set, or an RSA key at least as long (v2.251).

A request that names its template, by OID (\`szOID_CERTIFICATE_TEMPLATE\`) or by name (\`szOID_ENROLL_CERTTYPE\`), is issued under that template; a template the CA does not offer or that is inactive, two names for two templates, or EKUs the template does not issue are refused. Each policy announces its template's \`szOID_CERTIFICATE_TEMPLATE\` extension, which Windows CertEnroll copies into its request, so two templates with the same EKUs are told apart (v2.252). A request naming none is matched to a template by its EKUs. A template whose EKUs are all never issued to an enrollee, such as OCSP Signing, is not announced, and a request for it is refused. The certificate carries the EKUs of its template, not the ones the request asks for.

WSTEP serves the Issue request type only, renewals included, and refuses a message whose \`wsu:Timestamp\` expired more than 5 minutes ago. A plain PKCS#10 or a CMC request is recognised by its content whatever its ValueType, and every answer carries the CMC Full PKI Response next to the certificate.

### Kerberos / SPNEGO

Binds the Kerberos-authenticated XCEP/WSTEP endpoints used for silent GPO autoenrollment, so machines and users are authenticated by their Kerberos ticket instead of a credential prompt:
- **Service Principal Name (SPN)**: e.g. \`HTTP/ucm.example.com@EXAMPLE.COM\`, shared by every profile with the XCEP, WSTEP and Kerberos switches
- **Keytab**: One per profile, generated with \`ktpass\` or \`ktutil\` on the domain controller of its realm. Every entry must be \`HTTP/<host>@<realm of the profile>\`; the form lists the entries of the chosen file by realm and flags a realm that is not the profile's. The keytabs of all profiles are served as one file

> ⚠ Kerberos requires the server-side **\`gssapi\` backend** (the Python \`gssapi\` library plus the system Kerberos libraries): the base SPNEGO package alone is not enough. Without it, Kerberos authentication won't work even when enabled here, and the Kerberos binding is not advertised; a warning is shown on the tab.

The Docker images ship this backend since v2.251.

### Enrollment Policy URLs

The same for every profile: routing is by realm, not by URL.
- **Username/Password**: Prompts for credentials; for interactive "Request New Certificate" enrollment, doesn't require Active Directory
- **Kerberos**: No credential prompt; requires a domain-joined client and GPO configuration

### Certificate Renewal Binding

Besides Username/Password and Kerberos, WSTEP supports **client-certificate renewal**, mirroring real ADCS CES endpoints: the renewal request (RST) must be XML-DSig-signed with the private key of a certificate **UCM itself issued**. The presented certificate is matched **byte-for-byte** against the stored certificate for the configured CA, serial number or subject alone are never enough. This lets Windows clients renew unattended using their current certificate, without credentials or a Kerberos ticket.

XML-DSig has no ML-DSA signature method, so an **ML-DSA** certificate cannot renew this way: UCM names the key in its refusal, and the client enrolls a new certificate instead.

Windows can also renew with \`certreq ... Renew\`, authenticated by the certificate being renewed as TLS client certificate: enable mTLS with the WSTEP CA, or one of its ancestors, trusted. A renewal keeps the template and EKUs of the certificate it renews (v2.248). Since 3.0 only a certificate issued through Windows enrollment renews this way: one signed in the interface is refused (\`not issued through Windows enrollment\`) and must be reissued through Windows enrollment.

Since 3.0 a renewal by certificate is served by the profile the certificate records (a 2.x WSTEP certificate: the default profile), under that profile's issuing CA, and refused when the profile was deleted or is disabled; each refusal is audited with the profile and the reason. Only the SID is checked again, by the profile's connector: revoke the certificate of a computer removed from the group. The TLS client certificate works only for a profile whose issuing CA is the mTLS CA or a CA under it, and for a former CA the profile lists (below): a certificate the listener does not trust is refused during the TLS handshake, before UCM sees a request, so nothing is audited by UCM (read the client output and the service log). The other profiles renew over Kerberos only (the profile of the principal's realm serves and the new certificate records it), and when Kerberos refuses (requester removed from the AD group, profile disabled) they cannot renew. The Kerberos keytab keeps the keys of disabled profiles, so their requests are refused with an audit entry: only deleting the profile removes them.

Over Kerberos, a request signed by the requester's own valid certificate of the profile renews it when it names that certificate's template (or the certificate carries none, as one issued before 3.0): the renewed certificate is marked superseded by the new one, as on the Certificate binding, the audit entry is \`certificate.renewed\` and the webhook \`cert.renewed\`, and a second renewal of it is refused on either binding (\`Renewed certificate superseded by a newer one\`). A request naming another template is an enrollment (\`certificate.issued\`), even when the certificate that signs it was renewed already. After a change of the profile's issuing CA, a certificate of the former CA renews the same way: the new CA issues it, and the audit entry \`certificate.renewed\` names the old serial and the old CA.

After a change of the profile's issuing CA, the outgoing CA is listed on the profile under **Former CAs that still renew**, and the change audit says so. A certificate UCM issued under the profile by a listed CA renews on both bindings under the same rules (same template, same subject, valid, on record): the current CA issues the new certificate, the old one is marked superseded, and \`certificate.renewed\` names the old serial and the old CA. A former CA taken off the list, revoked or deleted renews nothing from that moment: the Certificate binding refuses the renewal, and over Kerberos the request is judged as an enrollment. The list only shrinks: remove a CA to stop its renewals, for example after its compromise; a CA that never was the profile's issuing CA cannot be listed. With mTLS on, the TLS listener also trusts each listed former CA that is not under the mTLS CA, so that \`certreq ... Renew\` with a certificate of that CA reaches UCM; a save that changes what it trusts restarts the service (a rolling restart in HA). A client certificate the listener lets through on a former CA alone serves WSTEP renewal and nothing else: certificate login, EST and every other route do not see it, and while a former CA is trusted this holds for any client certificate whose issuer is not a CA of UCM under the mTLS CA.

### SID Security Extension (KB5014754)

On **Kerberos-authenticated issuance**, UCM embeds the requester's AD SID in the Microsoft SID security extension (\`szOID_NTDS_CA_SECURITY_EXT\`) of the issued certificate. Domain controllers use it for **strong certificate mapping** (KB5014754): required since AD enforcement of strong mapping for certificate-based authentication (smartcard logon, PKINIT). With the AD Connector enabled, a request whose SID cannot be resolved is refused rather than issued without it, including a principal of a realm other than the connector's domain. A WSTEP, EST or SCEP renewal carries over the SID extension of the certificate it renews, never one from the CSR; with the AD Connector enabled, that SID must still name a directory account.

### AD-Derived Subjects

A certificate template can opt into **Build subject from Active Directory** (Templates → Enrollment): for unattended GPO autoenrollment, the subject and SAN are derived from the requester's AD object via the AD Connector instead of requiring the client to supply one, matching how a real ADCS template is configured for autoenrollment. On the Kerberos endpoints, the subject of such a template and of every machine template (Web Server, VPN, OCSP Signing types) always comes from Active Directory, whatever the request names: a machine template takes the computer's DNS name, is refused to a user account, and a "Build subject from Active Directory" template is refused to a computer. A template without either keeps the subject the client supplies, provided it configures its EKUs, and so does every template on the Username/Password endpoints, which have no directory identity to build one from. On the Kerberos endpoints a request matching no template gets its subject from Active Directory too: a computer's DNS name, a user's only when a template opted in, otherwise it is refused. Independently, **Allow autoenrollment** advertises the template as \`autoEnroll=true\` in Certificate Enrollment Policy so GPO/Kerberos-authenticated clients request it automatically at logon.

## About

- **System Information**, **Links & Resources** and the **Support UCM** link to Ko-fi. Administrators also see a dismissible Ko-fi card once per UCM version
- **Check FIPS readiness** (admin:system): lists what FIPS mode would refuse on this instance (scrypt password hashes, Ed25519 authorities on a module without EdDSA, Argon2id backups, PostgreSQL without TLS, HMAC secrets under 14 bytes...), with a remedy for each. Nothing is changed. In FIPS mode its blockers are also written to the log at each start, one error line each with its remedy, and the service status carries them; UCM starts anyway and refuses each affected operation when it is used
`
  },

  // ===================================================================
  account: {
    title: 'My Account',
    content: `
## Overview

Manage your personal profile, security settings, and API keys.

## Profile

- **Full Name**: Your display name shown across UCM
- **Email**: Used for notifications and password recovery
- **Account Information**: Creation date, last login timestamp, total login count

## Security

### Password Change
Change your current password. Must comply with the system password policy (minimum length, complexity requirements). Your other sessions are signed out; the one you changed it from stays. An admin password reset or 2FA reset signs out every session of the user.

When UCM asks for a new password at login (the first-boot \`admin\` account when UCM generated its password, for instance), the change comes before anything else: until it is made, the server refuses every other request of that session, API included.

### Two-Factor Authentication (TOTP)
Add a time-based one-time password using any authenticator app:

1. Click **Enable 2FA**
2. Scan the QR code with your authenticator app (Google Authenticator, Authy, 1Password, etc.)
3. Enter the 6-digit code to confirm
4. Save the **backup codes**: they are shown only once

> ⚠ If you lose access to your authenticator and backup codes, an admin must disable your 2FA.

To move 2FA to a new authenticator, disable it first: enabling it again while it is on is refused.

Each code is accepted once (RFC 6238): a code used to sign in cannot confirm another action or a second login, so wait for the next one.

### Security Keys (WebAuthn/FIDO2)
Register hardware security keys or biometric authenticators:
- YubiKey
- Fingerprint reader
- Windows Hello
- Touch ID

1. Click **Add Key**
2. Enter a name for the key
3. Follow the browser prompt to authenticate
4. The key appears in your registered credentials list

With 2FA enabled or enforced, a registered key can also answer the second step of a password login: choose **Use security key instead**.

Without an authenticator app, turn on **Security key as second factor** in the Two-Factor Authentication section: every password login then asks for one of your keys, and the last key cannot be removed while it is on.

### mTLS Certificates
Manage client certificates for mutual TLS authentication:
- Upload a client certificate
- Download your registered certificates
- Delete old certificates

## API Keys

### Creating an API Key
1. Click **Create Key**
2. Enter a **name** (descriptive, e.g., "CI/CD Pipeline")
3. Optionally set an expiry in **days**
4. Click **Create**
5. Copy the key immediately: it is shown only once

### Using API Keys
Include the key in the \`X-API-Key\` header:

\`\`\`
X-API-Key: <your-api-key>
\`\`\`

Or send it as a bearer token: \`Authorization: Bearer <your-api-key>\`.

### Permissions
Each key carries the scope chosen at creation (**Full Access**, **Read Only**, **Read & Write**, **Certificates Only**) and never more access than your account. **Certificates Only** issues X.509 and SSH certificates and reads the CAs, SSH CAs and CRLs, but cannot create or change a CA. A key can create or regenerate only a key whose permissions it holds itself, and that key expires no later than the one asking. Regenerating a key, offered by the API only (\`POST /api/v2/account/apikeys/<id>/regenerate\`), keeps its permissions and lifetime; a revoked or expired key cannot be regenerated.

API keys, even Full Access ones, cannot change your profile, password, 2FA, security keys, mTLS certificates or sessions, nor reach your own account through the user administration actions: these need an interactive session.

### Revoking Keys
The first **Delete** revokes an API key at once: requests with it are refused from then on. A second Delete on the revoked key removes it.

> 💡 Use short-lived API keys for CI/CD and automation.
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
- **PEM**: Single or bundled certificates, CAs, and keys
- **DER**: Binary certificate or key
- **PKCS#12 (P12/PFX)**: Certificate + key + chain (requires password)
- **PKCS#7 (P7B)**: Certificate chain without keys

### How It Works
1. Click **Import** or drag files onto the drop zone
2. UCM analyzes each file and identifies its contents
3. Review the detected items (CAs, certificates, keys)
4. Click **Import** to add them to UCM

> 💡 Smart Import handles PEM bundles with multiple certificates in a single file. It automatically distinguishes CAs from end-entity certificates.

### Post-quantum certificates
**ML-DSA** (FIPS 204) and **SLH-DSA** (FIPS 205) certificates import as PEM or DER, and so do ML-DSA private keys. They are shown with their security level, e.g. *ML-DSA-65 (level 3)*, and a **Post-quantum** badge. UCM cannot read an ML-DSA key from a PKCS#12 file yet: import the certificate and the key as PEM.

## OPNsense Integration

Import certificates and CAs from an OPNsense firewall, on demand (UCM does not keep them in sync):

### Setup
1. In OPNsense, create an API key (System → Access → Users → API Keys)
2. In UCM, enter the OPNsense host and port, API key, and API secret
3. Click **Test Connection**: it verifies the connection and lists the available certificates and CAs

### Import
1. Select the items you want to import
2. Click **Import N selected** (N counts the selected items)

UCM imports certificates with their private keys (if available) and preserves the CA hierarchy.

## Export Certificates

Bulk export all certificates:
- **PEM**: All certificates in a single PEM bundle
- **P7B Bundle**: All certificates in a single PKCS#7 file

## Export CAs

Bulk export all Certificate Authorities:
- **PEM**: Certificate chain in PEM format
- **Full chain**: Root → Intermediate → Sub-CA

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
3. Click **Check SSL**

Results include:
- Certificate subject and issuer
- Validity dates
- SANs (Subject Alternative Names)
- Key type and size
- TLS protocol version

Only the certificate the server presents is read, not the rest of its chain.

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
2. Paste the **private key** PEM (optionally encrypted: provide password)
3. Optionally paste a **CSR** PEM
4. Click **Match Keys**

UCM compares the public keys (RSA, EC, EdDSA, ML-DSA). A match confirms they form a valid pair. An ML-DSA private key must carry its seed: a key file holding only the expanded form is refused.

## Post-quantum keys

The decoders and the SSL Checker name an **ML-DSA** or **SLH-DSA** key with its NIST security level, e.g. *ML-DSA-65 (level 3)*. These keys have no size in bits. UCM cannot yet write an ML-DSA key into PKCS#12 or JKS, so the export dialog greys them out: export PEM with the private key instead.

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

## Import Tab

**Import files…** opens the Smart Import wizard in its dialog. Under it, the OPNsense integration: connect, test the connection, choose the items found and import them.

## Export Tab

Bulk export of certificates and CAs.

## Bulk Actions

Perform batch operations on multiple resources at once.

### How It Works
1. Select the **resource type** (Certificates, CAs, CSRs, Templates, Users)
2. Tick the items in the table; **Selection** shows the ticked items alone, from every page
3. Choose the **action** to perform
4. Confirm and execute

### Available Actions by Resource

#### Certificates
- **Bulk Revoke**: Revoke multiple certificates at once
- **Bulk Renew**: Renew multiple certificates
- **Bulk Export**: Download selected certificates as a bundle
- **Bulk Delete**: Permanently remove selected certificates

#### CAs
- **Bulk Export**: Download selected CAs
- **Bulk Delete**: Remove selected CAs (must have no children)

#### CSRs
- **Bulk Sign**: Sign multiple CSRs with a selected CA
- **Bulk Delete**: Remove selected CSRs

#### Templates
- **Bulk Delete**: Remove selected templates

#### Users
- **Bulk Delete**: Permanently remove selected users

> ⚠ Bulk operations are irreversible. Always create a backup before performing bulk deletes or revocations.

> 💡 Use the search and filters above the table to quickly find specific items.
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

> 💡 **Docker**: SoftHSM is pre-installed in the Docker image. On first start, a default token is auto-initialized and registered as the \`SoftHSM-Default\` provider, ready to use immediately. In FIPS mode SoftHSM is not a validated module: the default provider is not created and a SoftHSM provider is refused, unless \`UCM_FIPS_ALLOW_SOFTHSM=1\` allows one for tests.

Configuration:
- **Library Path**: Path to the PKCS#11 shared library (.so/.dll)
- **Token Label**: Label of the token to use (required)
- **Slot**: HSM slot number (optional)
- **PIN**: User PIN for authentication

### AWS CloudHSM
Amazon Web Services cloud-based HSM:
- **Cluster ID**: CloudHSM cluster identifier
- **Token Label**: label of the CloudHSM PKCS#11 token
- **Crypto User / Crypto Password**: the crypto user (CU) UCM logs in as; no AWS access key is needed

### Azure Key Vault
Microsoft Azure managed key storage:
- **Vault URL**: Azure Key Vault endpoint
- **Tenant ID**: Azure AD tenant
- **Client ID/Secret**: Service principal credentials

### Google Cloud KMS
Google Cloud Key Management Service:
- **Project**: GCP project ID
- **Location**: KMS key ring location
- **Key Ring**: Name of the key ring
- **Credentials**: Service account JSON key

### OpenBao / Vault Transit
OpenBao or HashiCorp Vault Transit Secrets Engine. Keys are managed remotely via the Transit API, no PKCS#11 library required.

Configuration:
- **URL**: Server address (e.g., \`https://openbao.example.com:8200\`)
- **Token**: Authentication token
- **Mount Path**: Transit engine mount point (default: \`transit\`)
- **Namespace**: Optional namespace for multi-tenant setups
- **TLS Skip Verify**: Skip TLS certificate verification (for self-signed certs)

Supported key types:
- RSA 2048, 3072, 4096
- ECDSA P-256, P-384, P-521
- ML-DSA-44, ML-DSA-65, ML-DSA-87 (Transit \`mldsa-*\` keys, on an OpenBao release that has them)
- AES-256-GCM (symmetric)

> 💡 OpenBao is a community-maintained fork of HashiCorp Vault. UCM works with both OpenBao and Vault.

> 💡 For development, run OpenBao in dev mode: \`docker run -d -p 8200:8200 -e BAO_DEV_ROOT_TOKEN_ID=test-token quay.io/openbao/openbao:latest server -dev\`

## Managing Providers

### Adding a Provider
1. Click **New Provider**
2. Select the **provider type**
3. Enter the connection details
4. Click **Create**
5. Click **Test** on the new provider to verify the connection

### Testing Connection
Always test the connection after creating or modifying a provider. UCM verifies it can communicate with the HSM and authenticate. For a PKCS#11 module, the test also records what the module reports (library, manufacturer, library and firmware versions), shown on the provider's page.

### Provider Status
Each provider shows a connection status indicator:
- **Connected**: HSM is reachable and authenticated
- **Disconnected**: Cannot reach the HSM
- **Error**: Authentication or configuration issue

## Key Management

### Generating Keys
1. Select a connected provider
2. Click **Generate**
3. Choose the algorithm (RSA 2048/4096, ECDSA P-256/P-384)
4. Enter a key label/alias
5. Click **Generate**

The key is created directly on the HSM. UCM stores only a reference.

### ML-DSA keys
ML-DSA-44, ML-DSA-65 and ML-DSA-87 (FIPS 204) are offered only on providers that sign with them:
- **PKCS#11**: a token implementing PKCS#11 3.2 with the ML-DSA mechanisms
- **OpenBao / Vault Transit**: key types \`mldsa-44\`, \`mldsa-65\` and \`mldsa-87\`
- **Google Cloud KMS**: \`PQ_SIGN_ML_DSA_*\` key versions, mapped from the KMS API but not yet tested against the service. KMS signs at most 64 KiB of data, so a CRL larger than that cannot be signed

Azure Key Vault and AWS CloudHSM providers hold no ML-DSA key, and FIPS mode refuses ML-DSA on every provider. An ML-DSA key signs the data itself, so no digest is chosen.

### Synchronizing keys
Click **Sync keys** in the provider details to read the keys of the token again.
- New keys are added.
- Keys gone from the token are removed, except keys a CA uses: they are kept.
- If the token listing fails, nothing is removed.

The message gives the counts, the number of keys kept because a CA uses them, the number of unreadable keys and the number of keys used by a CA whose material changed on the token. The button is disabled while the synchronization runs.
### Using HSM Keys
When creating a CA, select an HSM provider and key instead of generating a software key. The CA's signing operations are performed on the HSM.

An HSM key backs one authority, X.509 or SSH. Creating a CA on an HSM key needs the \`read:hsm\` permission besides \`write:cas\` (\`write:ssh_cas\` for an SSH CA), and a key a CA holds cannot be deleted.

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
- **Entity ID**: UCM's service provider identifier
- **ACS URL**: Assertion Consumer Service endpoint (HTTP-POST)
- **SLO URL**: IdP endpoint that takes the LogoutResponse by HTTP-Redirect; metadata import keeps the ResponseLocation of the HTTP-Redirect Single Logout Service, else its Location. See Single Logout below
- **Signing Certificate**: UCM's HTTPS certificate for signing verification
- **NameID Format**: The provider's **NameID format** setting (Unspecified, Persistent, Email address or Transient), also sent in each login request. Persistent gives a stable identifier; a transient NameID is never used to recognise the account

Copy this URL into your IDP's "Add Service Provider" or "SAML Application" configuration.

> ⚠️ **Important:** UCM's HTTPS certificate must be **trusted by the IDP**. If the IDP cannot validate the certificate (e.g., self-signed or issued by a private CA), it will reject the metadata as invalid. Import UCM's CA certificate into the IDP's trust store, or use a certificate signed by a publicly trusted CA.

### Configuration
1. Obtain the IDP metadata URL or XML file from your identity provider
2. In UCM, go to **Settings → SSO**
3. On the **SAML 2.0** card, click **Configure**
4. Enter the **IDP Metadata URL**: UCM auto-populates Entity ID, SSO/SLO URLs, and certificate
5. Or paste the IDP metadata XML directly
6. Configure **attribute mapping** (username, email, groups)
7. Click **Save** and **Enable**

### Attribute Mapping
Map IDP SAML attributes to UCM user fields:
- \`username\` → UCM username (required)
- \`email\` → UCM email (required)
- \`groups\` → read by the role mapping rules (optional); it does not make the user a member of UCM groups

Groups are read from the attributes mapped to \`groups\`, else from \`groups\` and the Microsoft claim URIs. Keycloak sends roles in \`Role\` and groups in \`member\`, Shibboleth sends \`urn:oid:1.3.6.1.4.1.5923.1.5.1.1\` (isMemberOf), other IdPs \`memberOf\`: these are read only once mapped to \`groups\`. The buttons under the attribute mapping add such a row, which takes effect once you save it. An attribute is matched by its Name, never by its FriendlyName (SAML Core 2.0 §2.7.3.1): map \`urn:oid:1.3.6.1.4.1.5923.1.5.1.1\`, not \`isMemberOf\`. A row of the new form (\`attribute → groups\`) replaces a row of the legacy form (\`groups → attribute\`), which is then no longer read; the screen names, under the mapping, the attributes no row reads any more. To keep reading both, replace the legacy row with a row \`attribute → groups\`.

### Single Logout
When the IdP ends a session, it sends a signed **LogoutRequest** through the browser to the SLO URL. UCM checks the IdP signature, issuer, Destination (required), IssueInstant (within the clock window) and that the request was not used before, closes the UCM session of that NameID in this browser (when the request carries SessionIndex values, only a session they name), then sends a **LogoutResponse** to the IdP's SLO URL, signed with the SP key; an SP certificate that is not RSA sends it unsigned, which a strict IdP such as AD FS refuses. Without an IdP SLO URL, the browser returns to the UCM login page. An unsigned or forged LogoutRequest is refused and the session stays open.

### IdP-initiated login
A login started from the IdP portal reaches UCM without a request from UCM. **Allow IdP-initiated login** accepts it, with the same signature, audience, Destination, validity and replay checks. Providers created before 2.243 keep it on; new providers have it off. Turn it on only if users start from the IdP portal.

## OAuth2 / OIDC

### Configuration
1. Register UCM as a client in your OAuth2/OIDC provider
2. Set the **Redirect URI** to: \`https://your-ucm-host:8443/api/v2/sso/callback/oauth2\`
3. Copy the **Client ID** and **Client Secret**
4. In UCM, go to **Settings → SSO**
5. On the **OAuth2 / OIDC** card, click **Configure**
6. Enter the **Authorization URL** and **Token URL**
7. Enter the **User Info URL** (for fetching user attributes after login)
8. Enter Client ID and Secret
9. Configure scopes (openid, profile, email)
10. Click **Save** and **Enable**

### Presets
- **Microsoft Entra ID** (single tenant) fills the URLs and the issuer \`https://login.microsoftonline.com/{tenant}/v2.0\`: replace \`{tenant}\` with the directory (tenant) ID in all three. A provider saved with \`{tenant}\` left in is refused. For a multi-tenant application, set the issuer to \`https://login.microsoftonline.com/organizations/v2.0\` (or \`common\`), the URLs with the same authority, and list the tenant IDs (GUIDs) under **Accepted tenants**: a token is accepted only when its \`tid\` is listed, its issuer is the discovery template \`https://login.microsoftonline.com/{tenantid}/v2.0\` with that \`tid\`, and its signing key, when it names an issuer, names that one. There is no wildcard: the personal Microsoft accounts tenant is accepted only when listed, and ID token verification must stay on. An identity belongs to its tenant: the same \`sub\` in two tenants is two accounts, and a tenant taken off the list no longer signs in. An account bound before the provider accepted several tenants keeps its bare \`sub\`: reset its SSO identity and choose its tenant so that its next sign-in binds the tenant one. Accepting a tenant trusts its administrators, who choose the usernames and e-mails of their users: an attached account not bound yet is bound by its username or e-mail only by a sign-in from the **Expected tenant** chosen when attaching the provider or resetting the identity (by default the tenant of the former identity), and an attachment without one is bound by no sign-in. The role mapping reads the roles and groups of the tenants listed under **Tenants whose roles are honoured** only, which entrusts their administrators with UCM roles. When the role mapping has rules, a user of another accepted tenant matches none and is refused at sign-in, an existing account included; without rules, every accepted tenant gets the default role, so an administrator default role makes every new account of every accepted tenant an administrator.
- **Google** fills the issuer \`https://accounts.google.com\`.
- **GitHub** is not an OpenID Connect provider and issues no ID token: the preset turns **Verify ID token signature** off and maps \`login\` to the username. The account is recognised by its numeric GitHub \`id\` (UCM reads the UserInfo \`sub\`, else \`id\`), never by the login or the email.
- Switching preset puts back the issuer and the verification setting the previous one set, unless they were changed since.

### ID token signature
RS256, RS384, RS512, PS256, PS384, PS512, ES256, ES384, ES512 and EdDSA (Ed25519, Ed448) are accepted, never \`none\` nor HS256, HS384 or HS512. The signing key must be of the type and curve the algorithm names, its \`alg\` and \`use\`, when present, the token's algorithm and \`sig\`, and an RSA key 2048 bits or more. Without a JWKS URI, the algorithm must also be listed in the discovery document. In FIPS mode, EdDSA is accepted only when the FIPS module approves it, and an RSA key must have an even size of 2048 to 16384 bits. A refused algorithm is named in the audit entry.

### Auto-Create Users
When enabled, a new UCM user account is automatically created on first SSO login, using the IDP-provided attributes, with the role its mapping rule gives, else the default role.

### Groups for role mapping
Role mapping rules compare their keys with the values of the **roles** and **groups** claims, read from the ID token of the login and from the UserInfo response together. Microsoft Entra ID sends groups and app roles only in the ID token: in the application registration, add the groups claim under **Token configuration** (the values are group object IDs, so the mapping keys are these IDs), or define app roles and map their values. A user in more than about 200 groups gets no groups claim from Entra ID: UCM logs a warning and only the app roles can match. Emit only the groups assigned to the application, or app roles. With **Verify ID token signature** off, the groups of the ID token count only when the Token URL is HTTPS with TLS verification on, and the issuer and client ID are set and match the token.

A row \`claim → groups\` in the attribute mapping makes that claim the source of the groups, in the ID token and in UserInfo under the same conditions, in place of **roles** and **groups**. The name is looked up as it is first (\`https://example.com/groups\`), then as a dotted path through nested objects: for Keycloak, \`realm_access.roles\` for realm roles and \`resource_access.<client id>.roles\` for client roles. A value that is neither a string nor a list of strings gives no group. A row of the new form (\`attribute → groups\`) replaces a row of the legacy form (\`groups → attribute\`), which is then no longer read; the screen names, under the mapping, the attributes no row reads any more. To keep reading both, replace the legacy row with a row \`attribute → groups\`.

## Who can sign in

### Identity matching
A login opens the account bound to the IdP identifier: OIDC \`sub\`, SAML persistent NameID, LDAP \`entryUUID\` or \`objectGUID\`. A username or email matches only an account of the same provider that is not bound yet (created before stable identifiers, or linked by an administrator); an email the OIDC IdP marks unverified (\`email_verified\` false) matches none. A local account, or one bound to another identity, is never opened by an SSO login: the login is refused and recorded in the audit log. When no account matches, a sign-in whose email belongs to an account attached to other providers only or left by another or an unknown IdP (after a restore, for instance), or, while the email is unverified, to one attached to this provider and not bound yet, is refused rather than given a second account. An account may be attached to several providers, each with its own identity, and no sign-in attaches a provider to an existing account by its name or email: an administrator does, with **Attach a provider** on that user. It accepts a local account and one of other providers, which keep opening it; **Reset identity** clears the identity of an attachment the IdP changed. The next sign-in through that provider binds the IdP identifier, and an account without a local password is not asked for one.

When a provider is deleted, its attachments are kept as orphans and the other providers of each account keep opening it: a provider created again for the same IdP (same issuer, entity ID, or LDAP server and base DN) takes them back at their next sign-in. Otherwise, and for attachments a restore could not place, use **Attach a provider** on each account.

### Role mapping rules
- **At least one rule**: a user no rule matches is refused at every SSO sign-in (OIDC, SAML, LDAP), whether the account is new or already exists; a passkey or certificate sign-in is not checked
- **No rule**: every user the provider authenticates can sign in; new accounts get the **Default Role**
- A rule that gives only a custom role: a new account gets the **Default Role** as its base role (viewer when None)
- **Default Role: None** with no rule: nobody can sign in through the provider

The **User Provisioning** section opens by itself and shows a warning when the provider has no rule.

### Diagnosing a refused sign-in
A sign-in refused because no rule matches, or because the provider has no rule and no default role, is recorded in the **Audit Logs** as a failed login (quick filter **Failed Logins**). The entry gives the group values UCM read (at most 20, each cut at 64 characters) and where they were read: the ID token, UserInfo or both for OIDC, with the reason the ID token was not used; the attributes read for SAML; the group search base or \`memberOf\` for LDAP. When nothing was read through OIDC or SAML, it names the claims or attributes received that look like group lists, never their values: map one of them to \`groups\`. Then add a role mapping rule for one of the values, or set a default role. The refused user sees only the refusal message (no rule matched, or no default role and no role mapping rule), never the group values.

### Testing a sign-in
**Test sign-in**, beside **Test Connection** on a saved OIDC or SAML provider, enabled or not, opens the IdP in a new window: sign in there with the identity to try. The IdP returns to the same redirect URI or ACS URL as a sign-in, and UCM runs the same checks and the same account decision. The provider screen then shows the identity and groups read, the verdict, the role, the account that would be opened or created and, for a refusal, its reason with the attributes to map to \`groups\`. Nobody is signed in and no account changes; the window only says the test is over. The test uses the saved provider (unsaved changes are announced, not sent); only the administrator who started it reads the result, for 10 minutes. The audit log records it as \`sso_sign_in_test\`, apart from sign-ins.

## LDAP

### Configuration
1. In UCM, go to **Settings → SSO**
2. On the **LDAP / Active Directory** card, click **Configure**
3. Enter the **LDAP Server** hostname and **Port** (389 for LDAP, 636 for LDAPS)
4. Enable **Use SSL/TLS** (LDAPS, port 636) or, on port 389, **Use StartTLS**: the connection switches to TLS before any bind, with the same certificate verification. Without either, the bind and user passwords cross the network in clear
5. Enter the **Bind DN** and **Bind Password** (service account credentials)
6. Enter the **Base DN** (search base for user lookups)
7. Configure the **User Filter** (e.g., \`(uid={username})\` or \`(sAMAccountName={username})\` for AD)
8. Map LDAP attributes: **username**, **email**, **full name**, and the **unique ID attribute** (\`entryUUID\`, \`objectGUID\`). An account bound by its DN moves to this id at its next sign-in; changing it from one id attribute to another refuses every bound user until **Reset identity** on each account
9. Click **Test Connection** to verify, then **Save** and **Enable**

### Groups
- **memberOf**: read from the user's own entry (a base search on its DN); the group filter is not used
- **member / uniqueMember**: searched under the Group Search Base alone when it is set; otherwise under the parent of the Base DN when the directory holds it, then under the Base DN if that search fails, with the group filter (\`(objectClass=*)\` when empty); groups beside the users (\`ou=groups\` next to \`ou=people\`) are found
- **Direct membership only** by default: nested groups and the Active Directory primary group (usually RID 513, Domain Users on an English-language domain) are not seen
- **Nested groups and primary group** (Active Directory only, off by default): adds every group above the user's groups at any depth (matching rule 1.2.840.113556.1.4.1941) and the primary group, read by its SID wherever it lies, so parent groups give their roles. The parent groups are searched under the same bases as a member search (with memberOf too); the primary group's own name counts only under that base and through the group filter. Distribution groups are followed too: the group filter (&(objectClass=group)(groupType:1.2.840.113556.1.4.803:=2147483648)) keeps only the security groups this search finds. With rules or required groups, on another directory, or when the search fails, times out or passes 1000 groups, the sign-in is refused, never limited to the direct groups
- **Matching**: group names compare with rules and required groups ignoring case and edge spaces, a run of inner spaces counting as one
- **Unreadable groups**: with rules or required groups, a sign-in whose groups cannot be read is refused with "your groups could not be read from the directory"
- **Test Mapping** reads the groups and decides as the sign-in does, without the password; it shows a role only for an admitted user

### Active Directory
For Microsoft Active Directory, use:
- Port: **389** (or 636 with SSL)
- User Filter: \`(sAMAccountName={username})\`
- Username attr: \`sAMAccountName\`
- Email attr: \`mail\`
- Full name attr: \`displayName\`

## Login Flow
1. User clicks the button of their provider on the UCM login page (or enters LDAP credentials)
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

## Private Key Encryption

Encrypt all CA and certificate private keys stored in the database with AES-128 (Fernet, with HMAC-SHA256), protected by a master key file kept outside the database.

- **Status and counters**: The section shows whether encryption is enabled and how many keys are currently **encrypted** vs **unencrypted**
- **First start**: An installation without a master key creates \`/etc/ucm/master.key\` (mode 0600) at startup and encrypts the keys and secrets already stored. In a container this happens only when \`/etc/ucm\` is a named volume or a host directory, never an anonymous volume. It does not happen when \`KEY_ENCRYPTION_KEY\` is set, when the database already holds encrypted keys (safe mode) or an audit chain sealed under a previous key, after encryption was disabled here, or with \`UCM_AUTO_MASTER_KEY=false\`. It also removes the plaintext key copies under \`data/private\`. At each start a loaded key also encrypts the values still stored unencrypted, and a key that does not decrypt them puts UCM in safe mode until the previous one is restored. Back up the key file: UCM backups do not need it, but a copy of the database cannot be decrypted without it
- **Enable Encryption**: Generates the master key file and encrypts all stored private keys, when no key was created at first start; refused in a container whose \`/etc/ucm\` would not outlive it. Back up the key file immediately: without it, encrypted keys are permanently lost
- **Disable Encryption**: Decrypts all private keys back to plaintext storage (confirmation required). UCM then creates no key at later starts, until encryption is enabled again
- **Encrypt remaining keys**: Shown while encryption is enabled and some keys or secrets are still stored unencrypted; encrypts them, leaving those already encrypted as they are

### Startup Enforcement

Without a configured encryption key, UCM logs a warning at startup but keeps running. Two **opt-in environment variables** turn that into a hard failure:

- \`UCM_REQUIRE_DB_ENCRYPTION_KEY\`: refuse to start without an explicit database encryption key (otherwise integration secrets fall back to a key derived from the machine id)
- \`UCM_REQUIRE_KEY_ENCRYPTION\`: refuse to start unless private-key encryption is enabled

Both accept \`1\`/\`true\`/\`yes\`/\`on\`. An invalid key is treated as fatal instead of silently falling back to plaintext.

## Password Policy

### Complexity Requirements
- **Minimum length**: 6 to 32 characters (8 by default)
- **Require uppercase**: At least one uppercase letter
- **Require numbers**: At least one digit
- **Require special characters**: At least one symbol

UCM has no password expiry and no password history setting.

## Session Management

### Session Timeout
Under **Settings › General**: close the session of users after N minutes of inactivity. Five minutes before, a banner offers to extend it; at the end the screen locks, and signing in again with the same account returns to the page that was open. Applies to web UI sessions only, not API keys.

### Session Duration
Maximum session length in hours, whatever the activity. The number of simultaneous sessions per user is not limited.

## Login Protection

### Max Login Attempts
Under **Settings › General**: the number of failed logins after which the **account** is locked.

### Lockout Duration
How long the account stays locked, in minutes.
A locked account answers a password or LDAP login with the same "Invalid credentials" as an unknown name until the lockout ends, so the answer does not reveal that the account exists; the lock is recorded in the audit log.

### Request Rate Limits
Requests are also limited per client IP address, by the \`RATE_LIMIT_*\` environment variables (authentication, heavy, standard and protocol buckets; private network clients exempt with \`RATE_LIMIT_TRUST_LAN\`). The login routes have their own limit, 5 attempts per minute, named with \`Retry-After\` in the 429 answer.

## Admin Access Allowlist

Limit the web interface and the management API to a list of IP addresses and CIDR networks, IPv4 or IPv6, one per line (up to 100). An empty list restricts nothing. IPv4 and IPv6 are listed separately: \`0.0.0.0/0\` does not admit an IPv6 client, and \`::/0\` does not admit an IPv4 client.

- **Blocked from other addresses**: the web interface and its assets, the login, every \`/api/v2\` call (API keys included) and the WebSocket channel answer **403**
- **Always reachable**: ACME and the ACME proxy, SCEP, EST, OCSP, CRL and AIA, TSA, XCEP/WSTEP, the SSH setup script, and the health and metrics endpoints, so devices and probes keep working
- **Your address**: the section shows the address the server sees for you. A list that does not include it is refused, so a save cannot lock you out
- **Audit**: each change of the list is written to the audit log

### Environment Variables
- \`UCM_ADMIN_ALLOWED_NETWORKS\`: comma-separated list that wins over the setting and makes the field read-only
- \`UCM_ADMIN_ALLOWLIST_DISABLE=1\`: turns the check off after a restart; use it to recover from a lock-out, then remove it

### Reverse Proxy, Docker and Kubernetes
Behind a reverse proxy, set \`UCM_BEHIND_PROXY=1\` and list the proxy in \`UCM_TRUSTED_PROXIES\`, otherwise every request appears to come from the proxy. With Docker in bridge mode and no proxy, the address seen may be the one after Docker's NAT: check the address shown before saving.

> ⚠ This filter works at the application level. Keep a firewall in front of the HTTPS port as well.

## Two-Factor Authentication

### Enforcement
Require all users to enable 2FA. Users who haven't set up 2FA will be prompted on their next login. A TOTP app or a registered security key satisfies it, at enrolment and at login. While it is enforced, TOTP can be turned off only if a security key remains, and the last key removed only if TOTP remains. A user whose key became their second factor keeps it when enforcement is lifted.

### Supported Methods
- **TOTP**: Time-based one-time passwords (authenticator apps)
- **WebAuthn**: Hardware security keys and biometrics

> 💡 Enforce 2FA for admin accounts at minimum. Consider enforcing it for all users in security-sensitive environments.

## mTLS Authentication

Let users log in with a client certificate instead of a password:

- **Trusted CA**: The CA whose client certificates are accepted at login, and the default issuer when a user generates one. Any CA whose certificate is not revoked can be chosen, keyless or offline included: such a CA issues nothing, so its users upload certificates issued elsewhere (v2.248). It is the only trust anchor of the HTTPS port: a client certificate from its parent or from a sibling CA is refused at the TLS handshake, so trust a root to accept its whole hierarchy (v2.252)
- **Require client certificate**: Optionally make mTLS mandatory for the web UI
- Changing mTLS settings requires a service restart
- **Revoked issuer**: A client certificate issued under a revoked CA, at any level of its chain, opens no session and can be neither enrolled nor imported (v2.252)

## Required Permissions

Security-sensitive settings: session, lockout, HSTS, public URL, and password policy, require the **admin:settings** permission. For operators (write:settings only), those fields are shown locked; the rest saves through the page's save bar.
`
  },

  // ===== GOVERNANCE =====

  policies: {
    title: 'Certificate Policies',
    content: `
## Overview

Certificate policies define the rules and constraints enforced when certificates are issued, renewed, or revoked. Policies are evaluated in **priority order** (lower number = higher precedence) and can be scoped to specific CAs.

## The list

The policies are listed in the order the server applies them, by priority then by name, with their scope, operations, priority, approval and state (**Applied** or **Disabled**); the chips filter by state, the search and the operation filter narrow the list. A name opens the policy in the inspector, with its properties, rules and approval; **Edit**, **Disable** or **Enable** ask for write:policies, **Delete Policy…** for delete:policies and a confirmation.

## Operations

A policy governs one or more operations: its approval requirement and its rules apply to those.

### Issuance
The issue form, CSR signing and bulk signing, and the renewals an operator performs. This is the most common choice. Controls key types, validity periods, SAN restrictions, and whether approval is required.

### Renewal
Renewals by an operator, one or in bulk, and by the scheduler. Under a renewal policy that requires approval, the scheduler queues the renewal instead of performing it, and the approval re-signs the key the server holds.

### Revocation
Revocations of certificates (one, in bulk, from the user certificates) and of intermediate CAs. Scoped by the issuing CA, the template and the DNS pattern; a CA's revocation is also held by the policies scoped on that CA, since every certificate it issued falls with it. The other rules do not apply. An ACME client cannot wait for a decision: its revocation is refused, and left to the operators. Removing an mTLS enrolment is refused until its certificate is revoked, whoever holds it; administrators bypass.

A policy created before operations existed keeps what it did: an issuance policy stays one, and a renewal or revocation type, never enforced, governs nothing until you choose its operations.

## Rules Configuration

### Max Validity
Maximum certificate lifetime in days. Common values:
- **90 days**: Short-lived automation (ACME-style)
- **397 days**: CA/Browser Forum baseline for public TLS
- **730 days**: Internal/private PKI
- **365 days**: Code signing

### Allowed Key Types
Restrict which key algorithms and sizes can be used:
- **RSA-2048**: Minimum for public trust
- **RSA-3072**: The default key size for new CAs
- **RSA-4096**: Higher security, larger certificates
- **EC-P256**: Modern, fast, recommended
- **EC-P384**: Higher security elliptic curve
- **EC-P521**: Maximum security (rarely needed)
- **ML-DSA-44 / ML-DSA-65 / ML-DSA-87**: Post-quantum (FIPS 204), NIST levels 2, 3 and 5; removed in FIPS mode when the FIPS module does not approve them

The \`allowed_signature_schemes\` rule, set through the API only (the policy form does not show it), restricts how the signing CA signs (PKCS#1 v1.5, RSA-PSS, ECDSA, EdDSA, ML-DSA, SLH-DSA). Allowed Signature Hashes do not bind an ML-DSA CA, which signs without a separate digest.

**Allowed Signature Hashes** restricts the signature hash the same way (SHA-256, SHA-384, SHA-512); none selected allows any. When nobody chose the hash, the default applies if allowed, else the weakest allowed one. The issue form offers only the allowed key types, Create CA only the allowed key types and hashes.

### SAN Restrictions
- **Max SANs**: Limit the number of DNS names in the SAN; IP, e-mail and URI entries are not counted. Over ACME, a DNS name the CN alone carries counts too (RFC 8555 §7.4)
- **DNS Pattern**: Scopes the policy to the requests whose CN or DNS SANs match, label by label and ignoring case: \`*.company.com\` covers the names under company.com, \`company.com\` covers company.com as well. Other names are not refused: the policy does not apply to them

## Approval Workflows

When **Require Approval** is enabled, certificate issuance is paused until the required number of approvers from the assigned group have approved the request.

### Configuration
- **Approval Group**: Select a user group responsible for approvals
- **Min Approvers**: Number of approvals required (e.g. 2 of 3 group members)
- **Notifications**: e-mail when the policy refuses an operation (a rule broken) or holds one for approval. They go to the policy's notification addresses, else to its approvers (the members of its approval group, or every user who may approve). Each held request is reported once, with a link to it; the same refusal repeated, by an ACME client retrying for instance, once per hour. SMTP must be configured

> 💡 Use approval workflows for high-value certificates like code signing and wildcard certificates.

## Priority System

Policies are evaluated in priority order. Lower numbers have higher precedence:
- **1-10**: Critical security policies (code signing, wildcard)
- **10-20**: Standard compliance (public TLS, internal PKI)
- **20+**: Permissive defaults

When multiple policies match a certificate request, the highest-priority (lowest number) policy decides the approval; the rules of every matching policy apply together (the smallest maximum validity, the intersection of the allowed key types, and so on).

## Scope

### All CAs
Policy applies to every CA in the system. Use for organization-wide rules.

### Specific CA
Policy applies only to certificates issued by the selected CA. Use for granular control.

## Default Policies

A new installation has no policy: create those your organization needs. An installation upgraded from an older release may list five example policies (Code Signing, Wildcard Certificates, Web Server TLS, Short-Lived Automation, Internal PKI), all disabled.
`
  },

  approvals: {
    title: 'Approval Requests',
    content: `
## Overview

The Approvals page shows all certificate requests that require manual approval before issuance. Approval workflows are configured in **Policies**: when a policy has "Require Approval" enabled, any matching certificate request creates an approval request here.

## Request Lifecycle

### Pending
The request is awaiting review. The certificate cannot be issued until the required number of approvers have approved it. Pending requests appear first by default.

### Approved
All required approvals have been received. The certificate will be issued automatically once approved.

### Rejected
Any single rejection immediately stops the request. The certificate will not be issued. A rejection comment is required to explain the reason.

### Expired
The request was not decided within seven days. Expired requests must be re-submitted.

### Cancelled
Its requester performed the action directly, or approved another request for the same target: nobody approves their own request, so it is closed without a vote.

## Where requests come from
Beyond the issue form, a policy that requires approval also queues:
- **Sign CSR** and **bulk signing** from Operations: the approval performs the signing
- **Renew** and **bulk renew**: the approval performs the renewal; a renewal that could not be honoured (revoked certificate, key not held by the server) is refused at once instead of queued
- **Revoke** (a certificate, in bulk, a user certificate, an intermediate CA) under a revocation policy: the approval revokes with the reason and invalidity date asked for, once checked again (a certificate renewed since the request is not revoked)
- The **renewal scheduler**, under a renewal policy: it queues the renewal once, and the approval performs it as the scheduler would have

Administrators bypass the queue on every path.

## Requests closed for you
- A queued request whose target an administrator **signed or renewed directly** meanwhile is closed as approved by that action and linked to the certificate
- A request whose target was **deleted or revoked** is closed as rejected; a certificate hold keeps the renewal request waiting for the unhold
- Approving a request **already satisfied** closes it on the existing certificate; approving one of several requests for the same target closes the others as approved by you
- Approving a request whose stored request, certificate or CA **no longer exists** closes it as rejected
- A queued revocation whose certificate was **revoked directly** is closed as approved (cancelled when its requester revoked it); one whose certificate was **renewed** since is closed as rejected when approved; approved during a certificate hold, it makes the hold final with its reason

A closure as rejected notifies the webhooks as a rejection does; a closure as approved sends no webhook.

## Deadline
A request waits **seven days** for a decision. Past that it is closed as expired, is never counted as pending, and the renewal scheduler resumes for its certificate. While a renewal awaits approval, the scheduler leaves the certificate to that decision, as long as it can come before the certificate expires; under a renewal policy it never renews without one.

## The queue

Open requests are grouped by their deadline: **To handle within 48 h** and **Later**, each with its count. A request past its deadline is expired: it moves to **Recently handled** and can no longer be decided. A row gives what the request asks for and its subject, a pill naming its source (CSR, certificate, renewal, revocation, CA, ACME, EST, SCEP, WSTEP), who asked and when, the policy, the authority, and the deadline in short form above its exact date. A subject opens the request in the inspector, with its **Request** and **Log** sections.

## Approving a Request

1. Click **Approve…** on its row, or in the inspector
2. Optionally give a reason: it is recorded with the decision
3. Confirm: what the approval issued opens in its page, a certificate in the inspector of the Certificates page, a CA in the Authorities page

## Rejecting a Request

1. Click **Reject…** on its row, or in the inspector
2. Enter a **reason** of at least five characters (required): it is kept in the request's timeline; a rejection writes no audit log entry
3. Confirm: the request is immediately stopped

> ⚠ Any single rejection stops the entire request. This is intentional: if any reviewer identifies a problem, issuance should not proceed.

## Deciding several requests

Tick several rows, or a whole group from its head, then **Approve…** or **Reject…** in the bar that replaces the hint. There is no bulk route: each request is decided in turn. When all went through, one message says so; otherwise the outcome lists those that went through and why the others did not (already voted, expired, issuance failed).

## Approval History

Each request maintains a complete approval timeline showing:
- Who approved or rejected (username)
- When the action was taken (timestamp)
- Comment provided (if any)

This history is stored with the request, not in the audit log.

## Recently handled

Decided requests (approved, rejected, expired, cancelled) are folded at the bottom of the page under **Recently handled**, newest first, with who decided, when and why.

## Permissions

- **read:approvals**: View approval requests
- **write:approvals**: Approve or reject requests

> 💡 Set up email notifications in policies so approvers are alerted when new requests arrive.
`
  },

  keyRecovery: {
    title: 'Key Recovery',
    content: `
## Overview

Key Recovery retrieves the **archived private key** of a previously issued certificate through an approval-gated, fully audited workflow. It is meant for keys that were **not exported at issuance time**: the preset did not allow export, or it was simply skipped, and are needed later, with an approval trail attached to the retrieval.

Recovery only works when the private key was archived (stored in the database) at issuance. It cannot reconstruct a key that was never kept.

## Workflow

### 1. Request
A user opens a recovery request for a specific certificate and provides a reason. The request is recorded and enters the pending state.

### 2. Approve (four-eyes)
An administrator reviews the request and approves it. With dual control on (the default), the requester **cannot approve their own request**: request and approval are separate actions by different people.

### 3. Download
Once approved, the archived key is released as a **password-protected PKCS#12** bundle. The download is recorded in the audit trail.

## The queue

The page lists the requests **to approve** (with dual control on, **to approve by another administrator**), then the keys **to recover**; closed requests (recovered, rejected, cancelled) are folded under **Recently handled**. A row offers only what the server would accept from you: **Approve…** and **Reject…** with admin:key_recovery, never the approval of your own request while dual control is on; **Recover…** for the requester or an administrator of key recovery. Several requests can be approved or rejected together: each is decided in turn; one message says when all went through, otherwise the outcome lists them one by one. A rejection takes a reason of five characters at least, an approval an optional note; either stays with the decision. A certificate name opens the request in the inspector, with its **Request** and **Log** sections.

## Requirements

- **Archived key**: the certificate's private key must be present in the database. Certificates whose key was never archived cannot be recovered.
- **Dual control**: on by default, the request and the approval are distinct steps performed by different users. An administrator can turn it off, and then approve their own request.

## Permissions

- **read:key_recovery**: View requests
- **write:key_recovery**: Request a recovery
- **admin**: Approve or deny a pending recovery request
- **read:private_keys**: Required for *direct* private-key export from the Certificates page (bypassing this workflow). Of the built-in roles only Admin holds it; a custom role can grant it

## What it is (and isn't)

Key Recovery adds an **approval trail** to retrieving an archived key after issuance. Direct private-key export is gated behind the **read:private_keys** scope: roles without it (including the built-in Operator role) must go through Key Recovery. An administrator, or a custom role granted that scope, exports the key directly, without approval, so the four-eyes approval binds only the roles without it.

> 💡 Every request, approval and download is written to the audit trail for compliance.
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
Certificates expiring within a specified time window (default: 30 days). Critical for avoiding outages, review this report regularly or schedule it for daily delivery.

### CA Hierarchy
Certificate Authority structure showing parent-child relationships and certificate counts per CA. Useful for understanding your PKI topology.

### Audit Summary
The ten most frequent actions and the ten most active users over the period.

### Compliance Status
Three checks with a count and a severity: active certificates, expired CAs, and certificates expiring within 30 days. It does not read the certificate policies.

### Revoked Certificates
Certificates revoked during the chosen period (default: 30 days), with revocation date and reason. Review it to follow revocations and their causes.

## Executive PDF Report

The **Executive Summary** template is one of the reports of the page: its **Download** button generates the PDF, suitable for management reviews, board presentations, and compliance audits. **Build a PDF…** in the page head (under the queue on a phone) composes one from the sections you choose.

### Contents
The PDF report includes 9 sections:
1. **Cover Page**: Key metrics, risk gauge, and key findings at a glance
2. **Table of Contents**: Quick navigation
3. **Executive Summary**: Overall PKI health, certificate distribution, and risk level
4. **Risk Assessment**: Critical findings, expiring certificates, weak algorithms
5. **Certificate Inventory**: Breakdown by status, key type, and issuing CA
6. **Compliance Analysis**: Score distribution, grade breakdown, category scores
7. **Certificate Lifecycle**: Expiration timeline and automation rate
8. **CA Infrastructure**: Root and intermediate CA details, hierarchy
9. **Recommendations**: Actionable items based on current PKI state

### Charts & Visuals
The report includes visual elements: risk gauge bar, status distribution, compliance grade breakdown, and expiration timeline, designed for non-technical stakeholders.

> 💡 The PDF report is generated from live data. Download it before meetings for the most current snapshot.

## The queue

Scheduled reports are grouped by their next run: **Next run within 24 h**, then **Scheduled**. A row gives the report, its frequency and time in a pill (in your timezone; a weekly or monthly run that would fall on another day for you keeps its UTC time, said), the current figure when the certificate counters hold it (Expiring Certificates) or else its format, its recipients, and the next run in short form above its exact date. The reports without a schedule are folded under **Not scheduled**, each with **Download** and **Schedule…**.

## Viewing a report

A report's name opens it in the inspector:
- **Report**: its schedule and the current figure: for Expiring Certificates, the counters' figure (the 30-day window of the overview, revoked certificates left out); for the other data reports, **Compute**; the inventory, expiring and revoked reports offer **See these certificates**
- **Runs**: the server serves no run history; the schedule and the next run are what is known
- **Preview**: **Generate** builds the report now and shows its rows (the first 200; the download holds them all)

## Downloading Reports

**Download** on a row, or in the inspector, generates the report now in the format of its schedule: CSV by default, JSON when chosen, PDF for a template. Ticking several rows downloads them one after the other: one message when all went through, otherwise the outcome says which failed.

> 💡 CSV reports are easier for non-technical stakeholders. JSON is better for scripts and API integrations.

## Scheduling Reports

### What can be scheduled
Every data report and every PDF template can be scheduled, each with its own frequency, time and recipients. Schedule **Expiring Certificates** daily to catch expiring certificates before they cause outages.

### Frequency
**Daily**, **Weekly** (choose the day of week) or **Monthly** (choose the day of month). The scheduler runs in UTC: the time is typed in your timezone, as the queue shows it, and converted when saved; a weekly or monthly run whose day the conversion would change is typed in UTC, as the dialog says.

### Configuration
1. Click **Schedule a report**, or **Schedule…** on a report folded under **Not scheduled**
2. Choose the content, the frequency and its day, the sending time (in your timezone) and, for a data report, the format (CSV or JSON)
3. Give one or more recipients, separated by commas: without a recipient, nothing is sent
4. Click **Schedule**

Each scheduled report is attached to the email in its format: CSV or JSON for data reports, PDF for the PDF templates. **Change the schedule…** and **Suspend the schedule** are in the « ⋯ » menu of the inspector; ticking several rows suspends them together, in one update.

### Test Send
Before relying on a schedule, use **Send a test…** in the « ⋯ » menu of a report's inspector to send it to one email address. This verifies that SMTP is configured correctly and the report format meets your needs.

> ⚠ Scheduled reports require SMTP to be configured in **Settings → Email**. Test send will fail if SMTP is not set up.

## Permissions

- **read:audit**: Generate and view reports; downloading also needs **export:audit**
- **read:audit + export:audit**: Download PDF executive report
- **write:settings**: Configure report schedules

> 💡 Schedule the Expiring Certificates report first: it's the most operationally valuable and helps prevent certificate-related outages.
`
  },

  // ===================================================================
  discovery: {
    title: 'Certificate Discovery',
    content: `
## Overview

Certificate Discovery scans your network to find TLS certificates deployed on servers and endpoints, and matches them against your managed PKI inventory. Use it to locate untracked certificates, detect changes, and watch for expiring certificates outside UCM's control.

## Views

### Analyses
The page opens on the analyses, one per scan profile: its range, what its last run found and when, and the state of that run (**Completed**, **Failed**, **Running**, **Scheduled**, **Never run**). A name opens the analysis in the dock: **Overview** gives its properties and description, **Runs** its runs; **Analyse now**, **Edit…** and **Delete…** need admin:system. **New analysis…** creates one.

### Found certificates
Every certificate the scans met, with host, issuer, expiry and state. A name opens the certificate in the dock: its subject, issuer, validity, extensions and fingerprints, and, for one in error, the error and a hint on its cause.

### Run history
Every run, of an analysis or a quick scan, newest first, with what it found, the targets scanned and its duration.

## Quick Scan

Run an ad-hoc scan without saving a profile:

1. Click **Quick scan…**
2. Enter the **range**, one target per line or separated by commas: hostname, IP, IPv4 range (\`192.0.2.0/24\`), or \`host:port\` (\`mail.example.com:465\`). A DNS wildcard, an IPv6 range and an IPv4 range of more than 65,536 hosts are refused in the form
3. Enter **ports**: comma-separated TCP ports (e.g. \`443, 8443, 636\`), or pick the common-ports preset
4. Optionally tune **advanced options**: reverse DNS resolution (PTR records), timeout, concurrency
5. Click **Start Scan**: progress updates live via WebSocket

## Scan Profiles

Profiles save a target configuration for repeated use:

- **Targets and ports**: same formats as Quick Scan
- **Schedule**: manual, or automatic every 1h / 6h / 12h / 24h / 7d
- **Notifications**: email alerts when new certificates are discovered, when a certificate changes on an endpoint, or when discovered certificates are expiring. A certificate found through SNI on an IP target is counted as new at every scan

Run an analysis on demand with **Analyse now** in its dock, or let the scheduler run it at the configured interval.

## Result Statuses

- **In UCM**: The certificate's SHA-256 fingerprint matches a certificate in UCM's inventory
- **Unknown to UCM**: Found on the network but not in the inventory: a candidate for bringing under management
- **In error**: The endpoint answered but its TLS handshake or certificate failed (SNI rejected, unreadable certificate). A refused connection, a timeout, a DNS or network failure is not recorded

### Change Detection
When an endpoint presents a different certificate than the previous scan, the change is recorded (previous fingerprint kept, **Last changed** timestamp) and can trigger a notification.

## Filtering & Export

- **State chips**: All, In UCM, Unknown to UCM, In error
- **Profile filter**: Restrict results to one scan profile
- **Export**: Download, as CSV, the found certificates the search, state and analysis filters show
- **Retry**: Re-scan individual error targets, or **Retry all errors** shown on the current page
- **Resolve DNS**: Bulk reverse-DNS resolution for discovered IPs

## Limits & Security

- A profile subnet is capped at 1024 addresses (a /22 IPv4 equivalent), a CIDR entered as a target at 65,536 hosts; up to 1000 targets per profile scan
- Private RFC1918 ranges and loopback are scannable: UCM's on-prem deployment model; link-local, multicast, and reserved ranges are blocked
- Scans started by hand and profile changes are audit-logged; scheduled runs are not

## Permissions

- **read:certificates**: View discovered certificates, profiles, and history
- **admin:system**: Create/edit profiles and run scans
- **delete:certificates**: Delete discovered results

> 💡 Schedule a daily scan of your server subnets and enable the new-certificate notification: it catches certificates deployed outside your PKI process.
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
4. Optionally enter the **CA Common Name** (the server hostname is used if empty)
5. Select the **Authentication Method**
6. Enter the credentials for your chosen method
7. Click **Test Connection** to verify
8. Set a **Default Template** and click **Save**

## Authentication Methods

| Method | Requirements | Best For |
|--------|-------------|----------|
| **Client Certificate (mTLS)** | Client cert/key PEM from the CA | Production, no domain join needed |
| **Basic Auth** | Username + password, HTTPS | Simple setups: enable basic auth in IIS certsrv |
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
UCM saves the request as **Pending** and tracks the MS CA request ID. Open the CSR in **CSRs → Pending** and click **Check status**: if the CA issued the certificate (approved on the Windows CA console, for instance), UCM imports it into the request; if the CA denied it, the request becomes Denied; otherwise it stays Pending. Approving from the **CA Control Panel** imports the certificate too. **Inventory sync** completes pending requests the same way, and reports them as completed, apart from the certificates it imports. A request whose CSR is signed elsewhere (a local CA, an import) is closed; if its details are still open, **Check status** shows *This CSR was signed elsewhere: its Microsoft CA request is closed*. A certificate the CA still issues for it enters as a separate certificate when the request is approved from the **CA Control Panel**, or through a full inventory sync (\`full: true\` on \`POST /api/v2/microsoft-cas/{id}/inventory-sync\`): **Import from CA now** and the scheduled sync are incremental and can miss it.

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
   - **Enrollee DN**: from the CSR subject (e.g., CN=John Doe,OU=Users,DC=corp,DC=local)
   - **Enrollee UPN**: from the CSR SAN email (e.g., john.doe@corp.local)
4. Adjust the values if needed
5. Click **Sign**

UCM passes these as ADCS request attributes:
- EnrolleeObjectName:<DN>: identifies the target user in AD
- EnrolleePrincipalName:<UPN>: the user's login name

### EOBO vs Direct Enrollment

| Feature | Direct Enrollment | EOBO |
|---------|-------------------|------|
| Who signs | User themselves | Enrollment agent on behalf |
| Private key | User's machine | Can be on UCM (CSR model) |
| Template permission | Standard enroll | Requires enrollment agent rights |
| Use case | Self-service | Centralized PKI management |

## Certificate Lifecycle

### Renewing an AD CS certificate
Renewal does **not** re-sign locally (the issuing key lives on the Windows CA). UCM resubmits the certificate's original CSR: same key, subject and SANs, to the connection and template that issued it, and updates the certificate in place. If the CA holds the renewal for manager approval, it is tracked as a pending request.

### Revoking an AD CS certificate
AD CS Web Enrollment has no revocation endpoint. Revoking an AD CS-issued certificate:
- **Without the WinRM admin channel**: marks it revoked in UCM only; the Windows CA is not notified. Revoke it on the CA as well.
- **With the WinRM admin channel**: UCM propagates the revocation to the Windows CA (certutil -revoke + CRL publish). Lifting a certificateHold propagates the unrevoke too.

## WinRM Admin Channel (optional)

The admin channel lets UCM run management operations on the Windows CA that Web Enrollment cannot: revoke/unrevoke, publish CRL, inventory, and approve/deny pending requests. It uses PowerShell remoting + certutil.

### Requirements
- **WinRM enabled** on the CA (Enable-PSRemoting; HTTPS listener on 5986 recommended)
- The optional **pywinrm** package installed in UCM (pip install pywinrm)
- An account allowed to **manage certificates** on the CA ("Issue and Manage Certificates")

### Configuration
1. Edit the connection and enable **WinRM admin channel**
2. Set the host (defaults to the connection server), port, and transport
3. **Transport**: Kerberos (recommended, reuses the connection keytab) or NTLM, over HTTP or HTTPS
4. **Credentials**: leave empty to reuse the connection's own (Basic/Kerberos). mTLS connections have no reusable WinRM credential, set a dedicated account
5. Click **Test admin channel**

| Enroll auth mode | Reuses credentials for WinRM? |
|------------------|-------------------------------|
| Kerberos (keytab) | Yes: same principal/keytab |
| Basic (user/pass) | Yes: password to NTLM/Kerberos |
| Certificate (mTLS) | No: set a dedicated WinRM account |

## CRL Revocation Sync

Enable **Sync revocations from the CA's CRL** on the connection so UCM periodically fetches the CA's CRL and marks certificates revoked on the CA as revoked in UCM. This is strictly one-way (CA to UCM) and never un-revokes a certificate revoked in UCM. The CRL URL is taken from the connection or auto-detected from issued certificates' CRL Distribution Point, and its signature is verified against the CA certificate before anything is applied. Runs hourly, plus a **Sync CRL now** action.

## CA Inventory Sync

Enable **Import certificates issued directly on the CA** to bring certificates issued outside UCM (native tools, autoenrollment, or before UCM existed) into UCM's store, so UCM tracks the whole lifecycle. It reads the CA database with certutil -view, imports certificates UCM doesn't already have (deduplicated by serial), and is incremental by request id (with a full-rescan option). A **reconciliation** view lists certificates present on the CA but not in UCM, and vice versa. Runs every 6 hours plus an **Import from CA now** action. Requires the WinRM admin channel.

## CA Control Panel

The control panel (opened from the connection, requires the admin channel) manages requests awaiting CA manager approval and shows CA health:
- **Pending requests**: list, **Approve** (certutil -resubmit; the issued certificate is imported automatically) or **Deny** (certutil -deny)
- **Health**: CA service status, CA certificate expiry, CRL next-update, and pending-request count

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Connection test fails | Verify hostname, port 443, and that certsrv is accessible |
| No templates found | Check that the UCM account has enrollment permissions on the CA |
| EOBO denied | Verify enrollment agent certificate and template permissions |
| Request stuck pending | Click Check status on the CSR, or run an Inventory sync; or approve it from the CA Control Panel |
| Admin channel test fails | Verify WinRM is enabled on the CA, the port/transport, and that pywinrm is installed |
| Revocation not on the CA | Enable the WinRM admin channel, without it, revocation is local to UCM |
| Pending not detected (non-English CA) | Fixed in v2.192. UCM now recognizes localized AD CS pending pages |

> 💡 Use the **Test Connection** button to verify authentication and discover available templates before signing. Enable the **WinRM admin channel** to manage revocation, CRLs, inventory and pending requests directly from UCM.
`
  },

  // ===== SSH CAS =====
  sshCas: {
    title: 'SSH Certificate Authorities',
    content: `
## Overview

SSH Certificate Authorities (CAs) are the foundation of SSH certificate-based authentication. Instead of distributing individual public keys to every server, you create a CA and configure servers to trust it. Any certificate signed by the CA is then automatically accepted.

UCM supports the OpenSSH certificate format (RFC 4253 + OpenSSH extensions), which is natively understood by OpenSSH 5.4+, no additional software needed on servers or clients.

## CA Types

### User CA
A User CA signs certificates that authenticate **users to servers**. When a server trusts a User CA, any user presenting a valid certificate signed by that CA is allowed to log in (subject to principal matching).

**Server configuration:**
\`\`\`
# /etc/ssh/sshd_config
TrustedUserCAKeys /etc/ssh/user_ca.pub
\`\`\`

### Host CA
A Host CA signs certificates that authenticate **servers to clients**. When a client trusts a Host CA, it can verify that the server it connects to is legitimate: eliminating "trust on first use" (TOFU) warnings.

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
   - **Ed25519**: Recommended. Fast, small keys, modern security.
   - **ECDSA P-256/P-384/P-521**: Good compatibility and security.
   - **RSA 4096**: Broadest compatibility, larger keys.
5. Optionally set max validity and default extensions
6. List the allowed principals, or tick **Allow any principal**
7. Click **Create**

### On an HSM key

An SSH CA can keep its private key on an HSM provider.

1. In **Create SSH CA**, set **Key Storage** to **HSM**
2. Pick the **HSM Provider**, then the **Existing HSM Key**: only unused RSA and ECDSA P-256/P-384/P-521 signing keys are listed
3. Click **Create**. The CA takes its key type from the key, and the private key never leaves the token

Good to know:
- An SSH CA on an HSM takes an RSA or ECDSA P-256, P-384 or P-521 key. Ed25519 keys are not offered: UCM's HSM signing does not cover EdDSA, so an Ed25519 SSH CA is a software key. Brainpool and ML-DSA keys are not offered either: UCM signs with them on an HSM for X.509 CAs, but OpenSSH certificates have no key type for them.
- An HSM key backs one authority, X.509 or SSH. A key a CA already holds is refused with the name of that CA, and neither the key nor its provider can be deleted while the CA exists.
- It needs \`write:ssh_cas\` and \`read:hsm\`. Without \`read:hsm\` the **HSM** choice is disabled.
- In FIPS mode a key that FIPS mode refuses is not offered. In HA mode a key on SoftHSM or on a local smart card reader is refused, as it exists on one node only.
- If the provider cannot be reached when the CA is created, nothing is created.
### Allowed Principals

The **Allowed Principals** field restricts the names a CA signs for, as comma-separated patterns (\`deploy\`, \`team-*\`, \`web??.example.com\`). Every principal in a request must match one of them.

A CA with an empty list signs nothing unless **Allow any principal** is ticked: it then signs for any name, \`root\` included. CAs created before 2.245 without a list behaved that way implicitly; the upgrade ticks the option for them, so they keep working.

### Key ID

sshd logs a certificate's key ID as the holder's identity. The CA sets it to \`principals@CA name\`, and refuses a request that sets another one, unless **Let requesters set the key ID** is ticked. The option is off for every CA, existing ones included since 2.249.

### TTL Formats

The **Default TTL** and **Max TTL** fields accept human-readable durations:

- Suffixed values: \`24h\`, \`7d\`, \`365d\` (accepted suffixes: \`s\`, \`m\`, \`h\`, \`d\`, \`w\`, \`y\`)
- Bare numbers: interpreted as **seconds** (e.g. \`3600\` = 1 hour)

Malformed values are rejected with an error naming the accepted formats.

> 💡 Use separate CAs for user and host certificates. Never use one CA for both purposes.

## Server Setup

### Automatic Setup Script

UCM generates a POSIX shell script that automatically configures your server:

1. Open the CA, then its **Quick Install** tab
2. Click **Download .sh (Linux/macOS)**
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
| Backup | Keep UCM backups: the CA private key cannot be exported on its own |
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

> ⚠ **Download the private key immediately**: it is not stored in UCM and cannot be recovered.

**Workflow:**
1. Select a CA and fill in the certificate details
2. Choose "Generate" mode
3. Click **Issue Certificate**
4. Download all three files:
   - Private key (\`keyid\`): **Save securely!**
   - Certificate (\`keyid-cert.pub\`)
   - Public key (\`keyid.pub\`)

## Certificate Fields

### Key ID
An identifier embedded in the certificate. The SSH server logs it when the certificate is used, as the holder's identity.

The CA sets it to \`principals@CA name\` (e.g. \`deploy@Production User CA\`). A requester can choose another one only on a CA where **Let requesters set the key ID** is ticked; elsewhere such a request is refused.

**Good key IDs, where allowed:** \`jdoe-prod-2025\`, \`webserver-01\`, \`deploy-ci-pipeline\`

### Principals
Principals define **who** (user certs) or **what** (host certs) the certificate is valid for:

- **User certificates**: list of usernames the holder can log in as (e.g., \`deploy\`, \`admin\`)
- **Host certificates**: list of hostnames/IPs the server is known by (e.g., \`web01.example.com\`, \`10.0.1.5\`)

> 💡 At least one principal is required: list the user or host names the certificate is valid for.

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

Short-lived certificates (8h-24h) are recommended for human users. Longer validity is acceptable for automated service accounts.

A certificate is valid from 5 minutes before it is issued, so a server whose clock lags slightly behind accepts it at once; the lifetime still counts from issuance (v2.252).

### Extensions (User Certificates Only)

| Extension | Description |
|-----------|-------------|
| permit-pty | Allow interactive terminal sessions |
| permit-agent-forwarding | Allow SSH agent forwarding |
| permit-X11-forwarding | Allow X11 display forwarding |
| permit-port-forwarding | Allow TCP port forwarding |
| permit-user-rc | Allow execution of ~/.ssh/rc on login |

### Critical Options (User Certificates Only)

| Option | Description |
|--------|-------------|
| force-command | Restrict the certificate to a single command |
| source-address | Restrict to source addresses or CIDR networks, comma-separated (\`10.0.0.0/8,2001:db8::/32\`) |
| verify-required | Require a FIDO key that verified the user (PIN or biometric), no value |

A server refuses a certificate carrying a critical option it does not know, so UCM signs only these and vendor options named \`name@domain\`. OpenSSH defines no critical option for host certificates: a host request carrying one is refused (v2.252).

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

A revoked certificate stays in the KRL, and in the list, until it expires: deleting it earlier is refused, since the KRL is built from these records and the certificate would be accepted again. Each KRL download carries a higher version number (v2.252).

The KRL names a certificate by its serial number, which UCM gives out once per CA. An installation upgraded from 2.x, or one that restored a 2.x archive, may hold two certificates of one CA sharing a serial: the list marks them **Shared serial**, and revoking one revokes them all; when one of them was already revoked, the others are revoked with it. Revoke them and issue new certificates. A certificate of serial 0, which OpenSSH reads as not numbered (an imported one, for instance), is listed in the KRL by its key ID once revoked, as OpenSSH does: every certificate of the CA with that key ID, whatever its serial, is refused with it, and UCM revokes them with it. A certificate with that key ID can then no longer be issued or imported under the CA. The key itself and certificates from other CAs stay valid.

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
