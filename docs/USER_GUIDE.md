# UCM User Guide

A tour of the Ultimate Certificate Manager console: where each module lives and what it does. Each module has a built-in help page (the help button in the top bar, or `?` outside a text field) with the full detail of its fields.

---

## Getting Started

### First Login

1. Navigate to `https://your-server:8443`
2. Login as `admin` with the password you provided at installation, or the generated one (see [First access](installation/README.md#first-access))
3. Set a new password when asked: until then the server refuses every other request of that session, API included

### Navigation

A menu path in this guide such as **Modules** > **PKI** > **Certificates** means: open the **Modules** menu in the top bar, pick the group, then the page. The top bar holds:

- the UCM logo, which goes back to the Dashboard
- **Dashboard**, **Certificates** and **Certificate Authorities**, always present; a count badge next to Certificates shows how many certificates are expiring or expired, and selecting it dismisses it until the count changes
- up to three modules you pinned
- the **Modules** menu, which lists every module you may open in four groups: **PKI**, **Protocols**, **Governance** and **Administration**. Modules you have no right to are not shown. The pin button next to a module keeps it in the bar
- search (`Ctrl K`), the help button, the live-link indicator, the theme menu, the notification bell and your account menu

The bell lists what needs your attention: critical items and pending approvals from the To handle queue (ACME order failed, ACME renewal failed, Approval pending, CRL due, CRL missing, Manual renewal due, Automatic renewal blocked, CA expiring, Deployment left on the old certificate, HTTPS left on the old certificate, Trust store certificate expiring or expired), plus Backup failed, Restore failed, Session revoked and Sessions revoked from the audit log. Queue entries open the page of the item, audit entries open the audit log, and a queue entry without a path has no link; nothing is approved or retried from the bell itself. Mark an item, or all of them, as read.

A status bar shows whether the service is running and the UCM version; on an instance in HA mode it also names the node and whether it is the leader.

On a page, the **list** holds the items and the **details** show the selected item, beside the list on wide screens and over the page on narrower ones.

### Dashboard

Open **Dashboard** in the top bar. The overview opens on four figures (certificates, items to handle, expired certificates, and the ACME, SCEP and EST failures of the current UTC day), followed by eight cards, each loading on its own: **To handle**, **Automation health**, **Hierarchy**, **Expiry horizon**, **Certificate activity**, **Status distribution**, **Compliance** and **Latest operations**. The header offers **Issue**, **New CA** and **Network discovery**, each shown only with the permission it needs.

- The **Operator** and **Manager** presets of the header choose which cards are shown; **Cards** opens a dialog to tick the cards, move them up and down or apply a preset (**All cards** shows them all in the initial order). On the page itself, drag a card by the grip at the left of its title onto the place of another card, or focus the grip and press an arrow key; the menu of a card also moves or hides it. The layout follows your account.
- **To handle** lists the six most urgent items, critical first, and a button under them shows the others. Each row gives the name, its type and the cause, then the delay with the exact date. The name opens the object it names: the approval, the SCEP or key recovery request, the ACME order, the CA or its CRL; if someone handled it meanwhile, a message says so. A button acts where UCM can: **Renew** for a manual renewal, **Retry** for a renewal the ACME client failed, **Publish now** for a CRL due or missing, each with the matching write permission; any other row has a link. The chips filter by type, and what needs no action today is counted on a line of its own that **Show** unfolds.
- With the right to read the trust store, **To handle** also lists the trust store certificates that expire within 90 days (warning) and those already expired, however long ago (critical); each opens its detail in the Trust Store page.
- **Automation health** shows, per protocol (ACME, SCEP, EST), the successes and failures of the day and of the period with a curve when there is something to draw (a protocol without any operation over the period reads as one line, with its last operation), then the TSA signer and the scheduler. The TSA line appears while the TSA is enabled; until a signer is set up it reads "Not configured", without alert; while the CA certificate signs (**Require a dedicated TSA certificate** turned off, as an upgrade from 2.x keeps it for a TSA that signed with its CA) it is a warning, since those tokens do not satisfy RFC 3161; it turns red when the signer is expired, revoked, without its key or within 30 days of expiry. The Scheduler line turns red when a task failed or when its state is no longer published, even if the latest run was fine.
- The **Email**, **Webhooks** and **Auto-Renewal** lines of the health card appear only with the right to read settings. A setting that is not configured is shown as information; email that is configured but disabled or missing its port or From address, and webhooks with none active, show as alerts. These lines read the settings when the page opens, when you return to the tab or on a refresh.
- **Hierarchy** draws at most ten CAs, the trees that issued most over 7 days first, each under its parent with its CRL and OCSP state and the certificates it issued over 7 days when there are any; each opens its page, and **See all** opens the Certificate Authorities page.
- **Expiry horizon** counts the expiring and expired certificates and lists the six next to expire, the TSA signer and delegated OCSP responder certificates included, each with the days left and a bar for the validity already spent. **Compliance** counts live certificates by key algorithm and weakness. Their counters open the certificate list filtered to what they count.
- **Certificate activity** draws the certificates issued, revoked and expired per day over 7, 15 or 30 days; pointing at the chart, or focusing it and pressing the left and right arrow keys, reads one day at a time. **Status distribution** shows the valid, expiring, expired and revoked certificates as a ring, each line opening its list.
- Cards reload by themselves when certificates or CAs change, when the live link comes back and when you return to the tab. The refresh button of the header reloads them all at once. While the live link is down, cards reload once a minute.

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl/Cmd + K` | Open search: jump to a page or find a certificate |
| `?` | Open the help of the current page (outside a text field) |
| `Escape` | Close the open menu or the search |

In the **Modules** menu, the arrow keys, `Home` and `End` move between pages.

---

## PKI

### Certificates

Open **Modules** > **PKI** > **Certificates**, or **Certificates** in the top bar.

**Issuing.** Click **Issue**, fill in the common name, subject alternative names, issuing CA, template and validity, then confirm. Certificates can also be imported (PEM, DER or PKCS#12). A hybrid pair (a classical certificate and an ML-DSA one, RFC 9763) is issued from the same form.

**Exporting.** Select a certificate and use **Export** in its details: PEM, DER, PKCS#12 or JKS. Set a password for PKCS#12.

**Renewing.** **Renew** replaces the certificate in place: same identifier, new serial and validity. A revoked certificate cannot be renewed, nor one whose private key the server does not hold (enrolled by a device, or imported without its key): renew it through its enrollment protocol, sign a new request or issue a new certificate.

**Revoking.** Select the certificate, click **Revoke** and choose a reason. The certificate appears in the CRL and answers OCSP as revoked. A certificate revoked with the reason Certificate Hold can be released with **Remove Hold**.

### Certificate Authorities

Open **Modules** > **PKI** > **Certificate Authorities**, or **Certificate Authorities** in the top bar.

**Creating a CA.** Click **Create** (**Create CA** when the list is empty). The dialog chooses what to make: a self-signed root, an intermediate signed by a parent CA, or a CA signed by an external CA (CSR). Set the common name, organization, key type and validity. RSA 4096 or ECDSA P-384 are sensible choices; ML-DSA keys are offered too. EdDSA (Ed25519, Ed448) suits only clients that verify it (OpenSSL, Go, Java 15 and later): web browsers, Windows (CryptoAPI/CNG) and SCEP clients reject what such a CA issues. **Import** brings in an existing CA certificate, with or without its private key.

**Views.** The page opens on the trust hierarchy as a tree: each root with its sub-authorities, folded beyond the first level, each node with its state and the number of its certificates and sub-authorities; roots without a sub-authority take one line each, and those without a certificate either fold into one group once there are many. The tabs (All, Roots, Intermediates, Expired, and Offline, Revoked or Awaiting certificate when there are some) and the search field filter it, and two buttons switch to columns (one per level) or to a flat list. Select a CA, or press Enter on it in the tree, to see its details and issued certificates. The chain repair strip shows by itself when there is something to repair; otherwise the **Chain Repair** button opens it.

**Algorithms and profiles.** The key type and validity are chosen at creation, and a CA can sign RSA certificates with RSA-PSS instead of PKCS#1 v1.5 (**Sign with RSA-PSS** in its details). A **Compliance profile** (ANSSI, BSI or EU ACM) binds what the CA issues: key types, digests, RSA scheme and date horizons. Pick one at creation or attach it from the CA details; the rules apply to future issuance only. Templates and policies carry their own key types and digests (see Templates and Policies below), and the protocols sign with those of the profile or template they use.

### Taking a CA Offline

Offline mode prevents a CA from signing anything (CSRs, certificates, intermediate CAs, new CRLs). Useful for Root CAs that should only be brought online during planned signing events.

1. Open the CA detail panel
2. Click **Take Offline**
3. Confirm, then enter and confirm a password (12+ chars, mixed case, digit, symbol: same policy as user passwords)
4. Choose a mode:
   - **Password Protected**: key stays in the database, re-wrapped under your password (plus the master key on top). Restore = enter password.
   - **Key File Exported**: key is exported as a password-encrypted PKCS#8 PEM and **deleted from UCM**. Restore = re-upload file + password. The downloaded file is the only copy: store it safely.

The CA list shows an **Offline** badge while offline. Existing CRLs continue to be served via CDP; new CRLs cannot be signed until restore.

### Restoring an Offline CA

1. Open the offline CA's detail panel
2. Click **Restore CA**
3. Enter the offline password
4. If the CA was exported to file, also select the previously downloaded `.key.pem` file
5. The CA returns to its previous status and resumes signing

⚠️ Lose the password (or the file in file-exported mode) and the CA is unrecoverable: there is no master override.

### Unique Subject

RFC 5280 §4.1.2.6 requires a CA to give each distinct entity it certifies a distinct subject name. **Enforce** next to **Unique subject**, in the CA details (`write:cas`), makes the CA refuse a certificate whose subject a certificate of another entity already carries under that CA. It is off by default, including on CAs carried over from 2.254.

Every certificate of the CA counts, whatever its status: valid, expired, revoked or superseded. A name once certified stays bound to its entity, so that a relying party that saw it on one certificate never finds it on another entity's later.

The rule is the issuer's ("the one CA as defined by the issuer field"), not the record's: when UCM holds several records of one issuer, same subject and same key (a root and its cross-certificate, a CA imported twice), the option on one of them counts the certificates of all of them for what that record issues. Two of those records issuing the same subject at the same moment never both succeed.

The issuance is the same entity's, and goes through, when one of these holds:

| Proof | Paths |
|-------|-------|
| The request carries the public key of a certificate of that subject | every path |
| It renews a certificate of that subject, or one renewed from it | **Renew**, automatic renewal, EST `simplereenroll`, SCEP `RenewalReq`, WSTEP renewal |
| It is authenticated by a client certificate of the CA that carries that subject | EST `serverkeygen` over mTLS |
| The same ACME account | ACME |
| The same Windows SID | XCEP/WSTEP |
| The same UCM user | user mTLS certificates |

EST `serverkeygen` generates a new key on every request and renews nothing: authenticated by Basic credentials, or by a client certificate of another subject or another CA, it proves no entity, so once a certificate of the subject exists the CA refuses it. A certificate recorded without an identity (imported, issued from a CSR or the issue form, or by 2.x outside ACME, whose certificates take their order's account at the upgrade) belongs to another entity unless the key or a renewal links it. Not checked: an empty subject, CA certificates (sub-CAs and cross-signing), the pre-certificate submitted to Certificate Transparency logs next to its final certificate, the two certificates of a hybrid pair, and the certificates UCM issues to its own services (OCSP responder, TSA signer, EST key generation signer).

A refused manual issuance or CSR signing names the certificate that carries the subject (serial number) and offers **Issue to the same entity**. Confirming it is the operator's attestation that the new certificate is for the same entity as the one that already carries the subject, the one case RFC 5280 §4.1.2.6 allows ("A CA MAY issue more than one certificate with the same DN to the same subject entity"). When one entity carries the subject, the new certificate joins it as a renewal would: the existing certificates and the new one then renew without any confirmation, automatic renewal included. The audit log records the attestation (`certificate.subject_override`): the operator, the subject, the new certificate and the one whose entity it joins. Protocols have no override: ACME answers `badCSR`, SCEP a failure with `badRequest`, EST a `400` with the reason, WSTEP a fault. Every refusal is audited: `certificate.subject_taken` (an automatic renewal adds `certificate.auto_renewal_failed`), or on WSTEP exactly one `windows_enrollment.refused` entry (for a request held for approval, the entry that closes the approval). A request held for approval is checked again when it is approved.

Certificates linked by any proof of the table (a shared key, a renewal, an identity, a SID) are one entity, even when the link runs through a third certificate. A renewal that changes the key keeps that link: the renewed certificate and those of its old key record one holder. The exception is two certificates that each record a different identity and share only a key: once one of them renews with a new key they are two entities, and the subject is shared. When several entities already carry the subject (certificates issued before the option was turned on, or imported), nothing tells which of them the operator attests. A confirmed CSR signing that names a related certificate A it proves the key of (an RFC 9763 related certificate request) joins A's entity; any other confirmed issuance adds one more entity. The subject stays shared either way: renewals of its certificates are refused as they are (only a manual issuance or a CSR signing goes through, with the confirmation), so **Renew** answers `409` and automatic renewal fails for them, every day, until the certificates of the other entities are gone from the CA or the subject changes.

Turning the option on is allowed when subjects are already shared. UCM answers with how many subjects are in that case and names the first 20 of them with the serial numbers of their certificates, so that they can be reissued under distinct subjects, or left to fail their renewals knowingly, before they are due.

### Certificate Signing Requests

Open **Modules** > **PKI** > **Certificate Signing Requests**.

1. Click **Import** and, in the **Upload CSR** dialog, give a PEM file or paste the PEM text; or click **Generate CSR** to make a CSR with its key pair in UCM
2. Select the request in the **Pending** tab and review its subject, names and key
3. Click **Sign**, then choose the issuing CA, the template and the validity
4. Confirm with **Sign CSR**, then download or copy the signed certificate

Signed requests move to **History**, where **Sign again** puts one back in Pending.

### Templates

Open **Modules** > **PKI** > **Templates**. A template holds reusable certificate settings: type, subject defaults, key usage, extended key usage, name types, validity, key type and digest.

Click **New** to make one, or select a template and click **Copy** to start from it. The built-in templates (Web Server, Email, Client Auth, Code Signing, among others) are marked System: they cannot be edited or deleted, only copied. A deactivated template is no longer offered by the Issue Certificate form or to Windows autoenrollment.

### Trust Store

Open **Modules** > **PKI** > **Trust Store**. It keeps trusted root and intermediate CA certificates; a certificate's chain view and exports complete the chain with a trust store certificate whose subject matches the issuer. **Sync** imports the operating system's trusted CAs, **Export** downloads one certificate, and **Export Bundle** in the toolbar downloads all of them as one PEM file. An entry that contains a private key is refused: the trust store keeps certificates only. When the bundle or another export leaves out unreadable entries, a warning gives their number.

### User Certificates

Open **Modules** > **PKI** > **User Certificates**. It lists the mutual TLS client certificates enrolled from **My Account**: view, export (PEM or PKCS#12), revoke or delete them. A viewer sees only their own.

### Certificate Tools

Open **Modules** > **PKI** > **Certificate Tools**:

- **SSL Checker**: test the certificate of a remote server
- **CSR Decoder**: inspect the subject, names, key type and extensions of a CSR
- **Certificate Decoder**: view all the fields of a PEM certificate
- **Key Matcher**: verify that a key, a certificate and a CSR match
- **SSL Converter**: convert between PEM, DER, PKCS#12 and PKCS#7

---

## Protocols

### ACME

Open **Modules** > **Protocols** > **ACME**. The page covers two modes: the ACME client, which obtains certificates from public CAs such as Let's Encrypt (the **Let's Encrypt**, **Let's Encrypt orders**, **DNS Providers** and **Domains** tabs), and the local ACME server for your own PKI.

For the server, open the **Local ACME** tab, enable it and choose the default CA. Clients use `https://your-server:8443/acme/directory`. The **Local Domains**, **Local orders**, **Accounts** and **EAB Credentials** tabs manage the domains it may issue for, the orders, the client accounts and external account bindings. Certificate profiles chosen per order bind a template and a validity. To put UCM in front of a public ACME CA, see [ACME proxy clients](integrations/acme-proxy-clients.md).

### SCEP

Open **Modules** > **Protocols** > **SCEP**. SCEP enrolls network devices and MDM solutions with a challenge password. The **Configuration** tab enables the server and chooses the CA; the **Challenges** tab shows and regenerates the challenge password of each CA, and the **Information** tab summarizes the setup; devices use `https://your-server:8443/scep/pkiclient.exe`.

The **Profiles** tab creates named endpoints, each with its own URL (`/scep/<segment>/pkiclient.exe`), CA, template and challenge, and the **Intune app registrations** tab lets a profile validate Microsoft Intune challenges (see [Intune SCEP](integrations/intune-scep.md)). The **Requests** tab lists the requests; pending ones are approved or rejected there.

### EST

Open **Modules** > **Protocols** > **EST**. RFC 7030 enrollment over HTTPS with mutual TLS or HTTP Basic authentication. In the **Settings** tab, enable EST and choose the signing CA and the credentials; **EST Endpoints** lists the URLs, under `https://your-server:8443/.well-known/est`: `/cacerts`, `/simpleenroll`, `/simplereenroll`, `/csrattrs` and `/serverkeygen`.

### TSA

Open **Modules** > **Protocols** > **TSA**. The RFC 3161 time stamp authority: enable it, choose the signing CA and set the policy OID (the default is a placeholder: use one from your organization's arc). A dedicated signing certificate is required by default: until one is set, `/tsa` answers 503. **Generate a signing certificate** issues one from the signing CA, with the timeStamping EKU alone and critical (RFC 3161), and selects it when no usable signer is set. Turning off **Require a dedicated TSA certificate** lets the CA certificate sign, which is not RFC 3161 compliant and which the overview shows as a warning. The **TSA Endpoint** tab shows the URL and OpenSSL examples.

### CRL & OCSP

Open **Modules** > **Protocols** > **CRL & OCSP**. CRL regeneration is toggled per CA, with manual regeneration, download, validity and CRL distribution point URL. The OCSP responder is served at `https://your-server:8443/ocsp`; its URL and the CA Issuers URL are the ones embedded in issued certificates. A delegated responder certificate can sign the answers instead of the CA key.

### Windows enrollment (XCEP and WSTEP)

Native Windows enrollment, with policy discovery by MS-XCEP and issuance by MS-WSTEP, is configured under **Settings** > **Windows Autoenrollment** (see Settings below). Enrollment is organized in profiles, one per Active Directory realm: each has its own issuing CA, template subset, Active Directory connector and keytab, and a client is routed to a profile by the realm of its Kerberos principal. The form of each profile lists what it still lacks (realm, CA, keytab, a reachable connector, a template that allows autoenrollment, the profile enabled).

### Approvals on protocols

When a policy requires approval, an ACME finalize, an EST enrollment, a SCEP request or a WSTEP enrollment or renewal is held: the client is told the request is pending and polls, and the approval issues the certificate through that protocol. A rejection or an expiry is reported to the client as a refusal. See Approvals below.

---

## Governance

### Policies

Open **Modules** > **Governance** > **Policies**. A policy governs issuance, renewal or revocation: maximum validity, allowed key types, signature schemes and hashes, name restrictions, and an approval workflow (an approval group and a minimum number of approvers). Policies are evaluated in priority order and can be scoped to CAs.

### Approvals

Open **Modules** > **Governance** > **Approvals**. When a policy requires approval, the operation waits until the required approvers have decided: an issue form, CSR signing, a renewal, a revocation, a renewal queued by the scheduler or a protocol enrollment. One rejection stops the request, a request not decided within seven days expires, and nobody approves their own request. Administrators bypass the queue. Open requests are grouped by deadline; several can be approved or rejected together, each in turn, with the outcome of each, and a rejection needs a reason.

### Key Recovery

Open **Modules** > **Governance** > **Key Recovery**. It recovers the archived private key of an issued certificate under dual control. A user asks from the certificate (**Recover key**) with a reason; an approver other than the requester approves; the key is then released as a password-protected PKCS#12 file. Dual control is on by default, and every step is audited. A key that was never archived cannot be recovered.

### Reports

Open **Modules** > **Governance** > **Reports**. The scheduled reports are grouped by their next run, and those without a schedule are folded below. A report downloads at once (CSV or JSON for a data report), and its detail shows its schedule, the current figure and a preview. The data reports are:

- **Certificate Inventory**: every certificate with its status
- **Expiring Certificates**: certificates expiring within a time window
- **Revoked Certificates**: certificates revoked during the period, with date and reason
- **CA Hierarchy**: the authorities and their statistics
- **Audit Summary**: the most frequent actions and the most active users
- **Compliance Status**: three checks (active certificates, expired CAs, certificates expiring within 30 days); certificate policies are not read

The PDF templates, the executive report among them, download the same way, **Build a PDF…** composes one from chosen sections, and **Schedule a report** sends any report by e-mail daily, weekly or monthly.

### Certificate Discovery

Open **Modules** > **Governance** > **Certificate Discovery**. It scans your network for TLS certificates and matches them against the inventory.

1. In **Scan Profiles**, create a scan profile with targets (hosts, IPs, CIDR subnets), ports and a schedule
2. Run it manually or let it run on schedule
3. Review **Discovered**: each certificate is Managed, Unmanaged or in Error, and a changed certificate is flagged
4. **History** lists past runs

**Quick Scan** scans targets without saving a profile. Running scans and managing profiles requires administrator rights.

---

## Administration

### Operations

Open **Modules** > **Administration** > **Operations** (administrators). The **Import** tab imports certificates from files or from OPNsense (Smart Import detects the file type), **Export** downloads bundles and **Bulk Actions** acts on many items at once.

### Users

Open **Modules** > **Administration** > **Users** (administrators).

1. Click **Create User**
2. Give the username, e-mail, role and initial password
3. Confirm

The **Groups** tab defines groups of users: a group grants permissions to every member on top of their own role. A user's source (local, LDAP, OAuth2 or SAML) is shown next to the account.

| Role | Permissions |
|------|-------------|
| **Admin** | Full access |
| **Operator** | Manages certificates, CAs, CSRs, ACME and SSH; templates and groups read-only; no access to users or access control |
| **Auditor** | Read-only access to operational data, for compliance and audit |
| **Viewer** | Read-only access to certificates, user certificates, CAs, CSRs, templates, the trust store, SSH CAs and SSH certificates |

### Access Control

Open **Modules** > **Administration** > **Access Control** (administrators). Custom roles are built from a permission matrix by category; the four system roles are built in.

### HSM Management

Open **Modules** > **Administration** > **HSM Management**. Providers hold CA private keys in hardware or a key service: PKCS#11, AWS CloudHSM, Azure Key Vault, Google Cloud KMS and OpenBao/Vault Transit. **New Provider** configures one, **Test** checks it and a key can be generated directly on the module. **Sync keys** in the provider details reads the keys of the token again: it adds the new ones and removes those gone from the token, except keys a CA uses, which are kept; if the token listing fails, nothing is removed. The message gives the counts of each case. In a Docker deployment see [HSM in Docker](HSM_DOCKER.md).

Creating a CA on an HSM key, an existing one or one generated for it, needs the `read:hsm` permission besides `write:cas` (`write:ssh_cas` for an SSH CA).

### Audit Logs

Open **Modules** > **Administration** > **Audit Logs**. Every operation is recorded: who did what, when and from where. Filter by action, user, status and date, search the text, export as JSON or CSV, purge old entries with a retention, and **Verify Integrity** checks the log chain for tampering.

### System Logs

Open **Modules** > **Administration** > **System Logs** (administrators). It reads back the server's own log without shell access: the application log, and on native installs the access and error logs and the service journal. Filter by component, level, text and date. It explains failures that never reached a record, such as a SCEP enrollment refused during validation.

### SSH CAs and SSH Certificates

Open **Modules** > **Administration** > **SSH CAs** to create user and host CAs (Ed25519, ECDSA or RSA 4096, or on an RSA or NIST ECDSA key of an HSM provider) and to download a setup script that makes sshd trust the CA and a key revocation list. Open **Modules** > **Administration** > **SSH Certificates** to issue certificates by signing a public key you paste, or by generating a key pair, with principals, a validity and extensions.

A key revocation list names the certificates of a CA by serial number, so UCM gives out each serial once per SSH CA, after restores, imports and changes of database as well. An installation upgraded from 2.x, or one that restored a 2.x archive, may hold two certificates of one CA sharing a serial: the list marks them **Shared serial**, and revoking one revokes them all; when one of them was already revoked, the upgrade or the restore revokes the others with it. Revoke them and issue new certificates.

An SSH CA on an HSM key keeps its private key on the token and needs the `read:hsm` permission besides `write:ssh_cas`. An HSM key backs one authority, X.509 or SSH, user or host: the key list offers only unused keys, and a key already held is refused with the name of the CA that holds it, and neither the key nor its provider can be deleted while the CA exists.

### Settings

Open **Modules** > **Administration** > **Settings** (administrators), or **Settings** in the account menu. The tabs are: General, Appearance & Language, Email, Security, SSO, Backup, Audit, Database, HTTPS, Updates, Scheduler, Webhooks, CT, Auto-Renewal, Deployment, Microsoft CA, Active Directory, Windows Autoenrollment and About; a tab you have no right to is not shown.

- **Backup** takes and restores archives. In HA mode they are stored in PostgreSQL.
- **Updates** installs updates; in HA mode on DEB and RPM it updates the nodes one at a time.
- **Scheduler** shows the scheduled tasks, with their last run and a **Run now**.
- **Windows Autoenrollment** holds the XCEP and WSTEP profiles described above.
- **About** shows system information and, for administrators, **Check FIPS readiness** and **Check profile** (the compliance profile check), which list what would be refused and change nothing; **Default profile for new CAs** sets the profile a CA receives when none is chosen.

---

## Single Sign-On (SSO)

UCM supports external identity providers for authentication:

- **LDAP / Active Directory**: Bind-based authentication with group-to-role mapping
- **OAuth2**: Google, GitHub, Azure AD, or any OpenID Connect provider
- **SAML 2.0**: Enterprise identity providers (Okta, Azure AD, ADFS)

Configure SSO in **Settings** > **SSO** (administrators only). Each provider type supports automatic role mapping based on group membership.

---

## My Account

Open **My Account** from the account menu (your name, right end of the top bar). Its tabs are **Profile** (name, e-mail, account information), **Security** (password, two-factor authentication, security keys, client certificates for mutual TLS) and **API Keys** (create a key with a scope, optionally expiring, and revoke it). The account menu also holds the **Language** choice and **Sign Out**, and **Settings** for administrators.

### Enabling 2FA (TOTP)

1. Open **My Account** > **Security**
2. Click **Enable 2FA**
3. Scan QR code with authenticator app
4. Enter verification code
5. Save backup codes securely

### Adding WebAuthn Key

1. Open **My Account** > **Security**
2. Click **Add Key**
3. Insert and touch your hardware key
4. Name the key for identification

With 2FA enabled (or enforced by an administrator), a registered key can answer the second step of a password login: choose **Use a security key** instead of typing a code.

When an administrator enforces 2FA, registering a key fulfils it as well as a TOTP app does; the account must keep at least one of the two.

Without enforcement, turn on **Security key as second factor** under **My Account** > **Security** to have every password login ask for one of your keys. Keys used only for passwordless login change nothing until you do. Under enforcement, it cannot be turned off while the account has no TOTP.

### Changes that sign out your other sessions

Enabling or disabling 2FA, regenerating recovery codes, adding, removing, enabling or disabling a security key, and turning **Security key as second factor** on or off sign out every other session of your account, as a password change does. The session you make the change from stays open.

Pages that ask for your current password (password change, turning off the security key as second factor) refuse it for a while after too many wrong tries, the right one included, with the same limit and duration as the login's second step. Signing in again is not blocked by it.

---

## Themes

The sun or moon button in the top bar opens the theme menu:

1. Pick a **Color Theme**
2. Pick an **Appearance Mode**: Light, Dark, or **Follow System** to match your OS light/dark preference

The choice is saved with your account and follows you to every browser.

---

## High Availability

UCM can run on two or more nodes that share one PostgreSQL database, started with `UCM_HA=1`. Sessions and locks live in the database and a single node, the leader, runs the scheduler; the status bar names the node you are on and its role. Requirements, the three deployment methods and what is refused in HA mode are in [High availability](HA.md).

---

## FIPS Mode

An instance started with `UCM_FIPS=1` enforces FIPS mode, in force only while the cryptographic libraries run on an active FIPS provider; otherwise it refuses to start. The `-fips` Docker image provides that module. In FIPS mode the algorithms the module does not approve are not offered (Brainpool curves, for example, and ML-DSA or EdDSA when the module does not approve them), and Argon2id backups cannot be restored. Before switching, **Settings** > **About** > **Check FIPS readiness** lists what FIPS mode would refuse on the instance, with a remedy for each.

---

## Mobile Usage

On a narrow screen the top bar shows a single list of pages in place of the links and the menu, and the details of an item open over the page.

---

## Troubleshooting

### Can't Login

1. Check username/password
2. Clear browser cache
3. Try incognito mode
4. Check server logs: `journalctl -u ucm -f`, or **Modules** > **Administration** > **System Logs**

### Certificate Creation Fails

1. Verify CA has valid private key
2. Check CA validity period
3. Review error message in notification

### SCEP/ACME Not Working

1. Verify the protocol is enabled on its page
2. Check firewall allows port 8443
3. Verify DNS/hostname configuration
4. Test with `curl https://server:8443/scep/pkiclient.exe?operation=GetCACaps`

---

## More Resources

- [API Reference](API_REFERENCE.md)
- [Administrator Guide](ADMIN_GUIDE.md)
- [High availability](HA.md)
- [Installation Guide](installation/README.md)
- [Docker Guide](installation/docker.md)
- [Changelog](../CHANGELOG.md)
