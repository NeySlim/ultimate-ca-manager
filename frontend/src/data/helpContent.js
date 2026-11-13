/**
 * Help content for all UCM pages: v2.50
 * Each entry: { title, subtitle, overview, sections[], tips[], warnings[], related[] }
 * Section: { title, icon, content?, items?[], definitions?[], example? }
 * Item: string | { label, text }
 */

import {
  TreeStructure, Certificate, FileText, ClockCounterClockwise,
  ShieldCheck, Key, Users, Gear, Database, Lock, Globe,
  ListChecks, CloudArrowUp, HardDrive, UsersFour, Fingerprint,
  ArrowClockwise, Wrench, Stack, Robot, Gavel, CalendarBlank, FilePdf,
  WindowsLogo, UserSwitch, Clock, UserPlus, ShieldWarning
} from '@phosphor-icons/react'

export const helpContent = {

  // ===== DASHBOARD =====
  dashboard: {
    title: 'Overview',
    subtitle: 'What needs action, and the state of the PKI',
    overview: 'Six independent cards over the live data of your PKI. Each card loads on its own and shows its own loading, empty, error or missing-permission state. Every counter that has a list opens the certificate list filtered to exactly the certificates it counts.',
    sections: [
      {
        title: 'Cards',
        icon: ListChecks,
        items: [
          { label: 'To handle', text: 'The six most urgent items, critical first, each linking to its record; a folded tier gives the total per kind, and the four renewal kinds open the certificate list' },
          { label: 'Automation health', text: 'Per protocol (ACME, SCEP, EST) the daily successes and failures, and the scheduler state' },
          { label: 'Hierarchy', text: 'The authorities as a tree under their parent, with CRL and OCSP state, an offline or cross-signed mark, and the certificates each issued over 7 days; each authority opens its page' },
          { label: 'Expiry horizon', text: 'The expiring and expired counters, each opening its list, and the five certificates that expire next' },
          { label: 'Compliance', text: 'Live certificates by key algorithm and weakness (RSA below 3072 bits, weak signature hash, server certificates over 398 days, incomplete chain, no private key); each counter opens the matching list' },
          { label: 'Latest operations', text: 'The five most recent operations; with the audit permission, a link opens the whole trail' },
        ]
      },
    ],
    tips: [
      'Pick the Operator, Manager or All cards preset in the header to choose which cards are shown',
      'The layout is saved with your account and follows you across browsers',
      'On the certificate list, filters coming from the overview appear as chips; remove one with its x',
    ],
    related: ['Certificates', 'CAs', 'Settings']
  },

  // ===== NAVIGATION =====
  navigation: {
    title: 'Navigation',
    subtitle: 'The top bar, the Modules menu and pinned modules',
    overview: 'The top bar holds the main pages, up to three modules you pin, the Modules menu, search and your account. The Modules menu lists every page you may open, in four groups; pages you have no right to are not shown.',
    sections: [
      {
        title: 'Modules menu',
        icon: ListChecks,
        items: [
          { label: 'Open', text: 'Select Modules, or press Down Arrow on the button; focus moves to the first page' },
          { label: 'Move', text: 'Up Arrow, Down Arrow, Home and End move between pages; Escape closes the menu and returns to the button' },
          { label: 'Pin', text: 'The pin button next to a page keeps it in the top bar; three at most, and the menu says so when you try a fourth' },
        ]
      },
      {
        title: 'Search and shortcuts',
        icon: Stack,
        items: [
          { label: 'Search', text: 'Press Ctrl K (Cmd K on macOS) or select the search field to jump to a page or find a certificate' },
          { label: 'Help', text: 'Press ? outside a text field to open the help of the current page' },
          { label: 'Phone width', text: 'The top bar shows a single list of pages instead of the links and the menu' },
        ]
      },
      {
        title: 'Account menu',
        icon: Users,
        items: [
          { label: 'Account', text: 'Your profile and settings, language and sign out' },
        ]
      },
      {
        title: 'Theme menu',
        icon: Stack,
        items: [
          { label: 'Choose', text: 'The sun or moon button sets the color theme and the mode; System follows your device, and the icon shows the mode applied' },
          { label: 'Keyboard', text: 'Up Arrow and Down Arrow loop over the options; Escape or Tab closes the menu and returns to the button' },
          { label: 'Saved', text: 'The choice is the one under Settings, Appearance, and follows you to every browser' },
        ]
      },
      {
        title: 'Notifications',
        icon: Stack,
        items: [
          { label: 'Bell', text: 'The count is the number of unread items in the panel: critical items and approvals from the overview queue, and failed scheduled backups, failed restores or revoked sessions from the audit log' },
          { label: 'Order', text: 'The queue items come first, then the audit log items, newest first' },
          { label: 'Rights', text: 'You only see items from sources you may read; a source you have no right on shows nothing' },
          { label: 'Read', text: 'Mark an item or all of them read; the marks are saved with your preferences, and an item that resolves leaves the panel' },
          { label: 'Open', text: 'Open goes to the page of the item; nothing is approved or retried from the panel' },
        ]
      },
    ],
    tips: [
      'Your pins follow you to every browser and device you sign in from',
      'A pinned page you lose the right to open is hidden, and returns if the right is restored before you change your pins',
    ],
    related: ['Overview', 'Certificates', 'Settings']
  },

  // ===== CERTIFICATE AUTHORITIES =====
  cas: {
    title: 'Certificate Authorities',
    subtitle: 'Manage your PKI hierarchy',
    overview: 'Create and manage Root and Intermediate Certificate Authorities. Build a complete trust chain for your organization. CAs with private keys can sign certificates directly.',
    sections: [
      {
        title: 'Views',
        icon: TreeStructure,
        items: [
          { label: 'Organigramme view', text: 'Hierarchy drawn as a chart, each CA under its parent' },
          { label: 'Columns view', text: 'Hierarchy browsed level by level, one column per level' },
          { label: 'List view', text: 'Flat table view with sorting and filtering' },
        ]
      },
      {
        title: 'Actions',
        icon: Certificate,
        items: [
          { label: 'Create CA', text: 'One button; the dialog chooses a self-signed root, an intermediate signed by a parent CA, or a CA signed by an external CA (CSR)' },
          { label: 'Import CA', text: 'Import existing CA certificate (with or without private key)' },
          { label: 'Export', text: 'PEM, DER, or PKCS#12 (P12/PFX) with password protection' },
          { label: 'Revoke', text: 'Revoke an intermediate CA from its parent: published on the parent\'s CRL and OCSP, and the CA can no longer sign (permanent)' },
          { label: 'Chain Repair', text: 'Fix broken parent-child relationships automatically' },
          { label: 'Import private key', text: 'Attach the private key of a CA that holds only its certificate, so it can sign' },
          { label: 'Key and validity', text: 'RSA-3072 by default, local or HSM. Validity of 1, 2, 3, 5, 10, 15 or 20 years, or Custom (days) up to 50 years. An RSA-2048 CA that would outlive 2030 is flagged: ANSSI accepts RSA-2048 until the end of 2030, ETSI TS 119 312 until the end of 2026' },
          { label: 'Post-quantum (ML-DSA)', text: 'ML-DSA-44, ML-DSA-65 or ML-DSA-87 (FIPS 204, NIST levels 2, 3 and 5), generated in software or on an HSM provider that holds ML-DSA, and hidden in FIPS mode. An ML-DSA key signs without a separate digest, so the CA, its CRLs and its OCSP responses have no digest to choose. An ML-DSA CA can sign RSA or EC certificates, and an RSA or EC CA can sign an ML-DSA intermediate' },
          { label: 'EdDSA (Ed25519, Ed448)', text: 'Ed25519 or Ed448 keys for a root, intermediate or external CA, in software only (no HSM provider signs EdDSA) and hidden in FIPS mode. Like ML-DSA, an EdDSA key signs without a digest, and the hierarchy can mix with RSA, EC or ML-DSA. Browsers, Windows (CryptoAPI/CNG) and SCEP clients do not accept what an EdDSA CA signs, whatever the leaf key: reserve it for OpenSSL, Go or Java 15+ consumers. SCEP and XCEP refuse such a CA' },
          { label: 'EdDSA import (v2.251)', text: 'An Ed25519 or Ed448 CA key can be imported with its certificate, or afterwards with Import private key' },
          { label: 'Default digest (v2.251)', text: 'Under a P-384 or P-521 CA, what is signed without a chosen digest (EST, SCEP, WSTEP, Sign CSR, the issue form, ACME orders without one, CRLs) uses SHA-384 or SHA-512; the policies bound the certificates, not the CRLs. CRLs already issued are unchanged: the next one follows' },
          { label: 'No private key (v2.247)', text: 'A CA held without its private key is marked No private key, with an Import private key action. The CA pickers say how many CAs they leave out because they cannot sign' },
          { label: 'Name constraints', text: 'Advanced Constraints (RFC 5280): permitted and excluded subtrees (DNS, IP range, email) limit the names the CA may certify. For an externally-signed CA they are set by the signing CA' },
          { label: 'RSA signature scheme', text: 'PKCS#1 v1.5 by default, or RSA-PSS (salt as long as the hash) for an RSA CA with a local, PKCS#11 or OpenBao key. It applies to the certificates, CRLs, OCSP responses and SCEP replies the CA signs; timestamps stay PKCS#1 v1.5, the scheme openssl ts -verify checks. "Sign with RSA-PSS" in the CA details switches an existing CA either way: certificates already issued keep their signature' },
          { label: 'Compliance profile', text: 'ANSSI, BSI or EU ACM: rules aligned with a reference text bind what the CA issues (key types, digests, RSA scheme, date horizons, and for EU ACM an HSM-held CA key). Pick one at creation (an intermediate CA is offered its parent profile, otherwise the default set in Settings, About). On an existing CA, the field in the details attaches, changes or removes it: the profile check runs on that CA first, its findings are listed, and you confirm that the rules apply to future issuance only, nothing already issued is re-signed. Needs write:cas, and admin:system to attach or change' },
          { label: 'Issuance pickers', text: 'Hide from issuance, in the CA details, keeps a CA (a root, typically) out of the CA lists of Issue Certificate, Sign CSR, the bulk signing of CSRs and the user mTLS certificates (My Account, Users & Groups) and the TSA signing certificate. A link under those lists, Show hidden CAs, brings it back when needed, and a CA already chosen stays listed. Protocol settings (ACME, EST, SCEP, XCEP/WSTEP), the parent of a new CA and cross-signing still list it. Needs write:cas' },
          { label: 'Unverifiable parent', text: 'A CA whose parent\'s key UCM cannot check (SLH-DSA, GOST) is imported without a parent. Its details name the probable parent (same subject as its issuer, same key identifier when both carry one) and the algorithm; Link to this parent asks for an explicit confirmation, checks everything again and records who confirmed it and when. Chain repair keeps the link, a re-import too while that CA is still the probable parent, and Withdraw the link removes it. A signature that does not verify is never linked. Needs write:cas' },
        ]
      },
      {
        title: 'Externally-signed CAs (CSR mode, v2.214)',
        icon: Certificate,
        content: 'The "Signed by external CA (CSR)" creation type covers the offline-root pattern: the key pair lives in UCM, the certificate is signed elsewhere. The private key never leaves UCM.',
        items: [
          { label: 'Create', text: 'UCM generates the key pair (local or HSM) and a CA-type CSR, the CSR downloads automatically' },
          { label: 'Awaiting certificate', text: 'The pending CA cannot sign, be exported, be a parent or go offline until its certificate is installed' },
          { label: 'Upload certificate', text: 'Paste or upload the externally signed certificate (PEM/DER). Its public key must match the stored private key; CA constraints are enforced' },
          { label: 'Chain', text: 'Linked automatically when the issuer is known to UCM, import the external root (certificate only) for a complete chain' },
          { label: 'Renew via CSR', text: 'Re-issues a CSR from the same key (stable SKI); sign it externally and upload the new certificate' },
          { label: 'After renewal', text: 'The superseded certificate stays valid until its notAfter, UCM shows its serial after the upload; revoke it at the external root if it should no longer be trusted' },
        ]
      },
      {
        title: 'Cross certificates',
        icon: Certificate,
        content: 'A cross-certificate carries a CA\'s subject and key under another issuer, so clients that trust only that other root can still build a path. It sits beside the CA\'s own certificate and never replaces it.',
        items: [
          { label: 'Where', text: 'CA details › Cross certificates; a CA that carries one shows a Cross-signed badge' },
          { label: 'Attach', text: 'Paste or pick a certificate (PEM or DER) issued by another CA for this CA\'s key; name or policy constraints it carries are reported' },
          { label: 'Cross-sign', text: 'Sign this CA\'s key with another CA held in UCM, with a validity and a path length' },
          { label: 'Serve', text: 'At most one per CA is served in the default chain (TLS, PKCS#12, ACME, WSTEP, TSA, deployments, AIA .cer and .pem). A revoked, expired or not yet valid one is never served' },
          { label: 'Chain to present', text: 'Exports and deploy bindings can pin the default chain, the self-signed root or one cross-certificate. ACME offers the other chains as alternates (certbot --preferred-chain)' },
          { label: 'Import', text: 'A certificate over a held CA\'s key is attached to a self-signed root; on an intermediate the 409 offers Attach as cross certificate or Replace. Smart Import attaches it next to a held root or reports it as skipped' },
          { label: 'Still chaining', text: 'CA details › Still chaining to this CA lists the certificates, active sub-CAs, deploy bindings and CRL pushes that still depend on the CA, directly or through a cross-certificate, to tell when an old root can be retired; a client that cached a chain is not counted' },
          { label: 'Repair', text: 'The bar under the statistics lists records an older import damaged: Convert to cross-certificate (needs delete:cas) and Restore as primary. Nothing runs by itself' },
        ]
      },
      {
        title: 'HSM-backed CAs',
        icon: Key,
        items: [
          { label: 'Key Storage', text: 'Choose Local (in the database, encrypted under the master key) or HSM at CA creation time' },
          { label: 'Generate new key', text: 'Create a fresh signing key on the selected HSM provider' },
          { label: 'Use existing key', text: 'Bind the CA to an unused signing key already on the HSM' },
          { label: 'No private key export', text: 'HSM-backed keys never leave the HSM, PKCS#12, JKS and key-only exports are disabled' },
          { label: 'Prerequisite', text: 'Configure and connect an HSM provider in HSM Management first' },
        ]
      },
      {
        title: 'Offline Mode',
        icon: ShieldWarning,
        items: [
          { label: 'Purpose', text: 'Protect a CA private key (typically a Root) from runtime use while keeping its certificate, chain and last CRL available' },
          { label: 'Password protected', text: 'Key is wrapped with a user-supplied password (PKCS#8) and stays in the database. Restore by entering the password.' },
          { label: 'File exported', text: 'Key is exported as a password-protected PEM download and removed from the database. Restore by re-uploading the file with the password.' },
          { label: 'Password policy', text: 'The password follows the UCM password complexity rules (length and character classes). Lose it and the key is unrecoverable.' },
          { label: 'Effect on signing', text: 'CSR signing, certificate issuance and renewal are blocked while offline. The last CRL stays served until you upload a new one signed next to the key; OCSP answers through a delegated responder, otherwise only from responses already cached, until their nextUpdate.' },
          { label: 'Sub-CAs', text: 'Both Root and Intermediate CAs can be taken offline independently' },
        ]
      },
      {
        title: 'External CRLs for key-less CAs (v2.215)',
        icon: ListChecks,
        content: 'A CA whose key UCM cannot use (offline CA, certificate-only import) cannot sign its own CRL, upload one generated next to the offline key instead.',
        items: [
          { label: 'Where', text: 'CA detail view › Revocation list (CRL): shows the served CRL number, entry count, this/next update, and a warning once nextUpdate has passed' },
          { label: 'Upload', text: 'PEM or DER, complete (non-delta) CRLs only. The signature must verify against the CA certificate and the issuer must match its subject' },
          { label: 'Monotonicity', text: 'An upload older than the currently served CRL (CRL number or thisUpdate) is refused, issue it with a higher CRL number' },
          { label: 'Serving', text: "The uploaded CRL is served at the CA's existing CDP path, and OCSP answers revoked for the serials it lists" },
          { label: 'Workflow', text: 'Revoke at the offline root, generate the root CRL in the air-gapped environment, upload it here, the root key never goes online' },
        ]
      },
    ],
    tips: [
      'CAs with a key icon (🔑) have a private key and can sign certificates',
      'Take the Root CA offline as soon as your Intermediates are operational',
      'Use "File exported" for the strongest air-gap; use "Password protected" for fast in-place restore',
      'PKCS#12 export includes the full chain and is ideal for backup',
    ],
    warnings: [
      'An ML-DSA CA cannot be exported as PKCS#12 or JKS yet: export the certificate and the private key as PEM. Clients without ML-DSA support (OpenSSL before 3.5, most browsers today) cannot verify what it signs',
      'A CA cannot be deleted while it has intermediate CAs or issued certificates: revoke and delete them first',
      'Private keys are stored encrypted under the master key; losing the database, or the master key without a UCM backup, means losing the keys',
      'Offline-mode passwords are NOT recoverable: store them in your password manager / vault before confirming',
      'A cross-certificate never replaces a CA\'s own certificate: an intermediate that would be re-certified under another issuer is refused (409) unless you attach it as a cross certificate or replace the current one; a root rollover under the same issuer name replaces it',
      'A self-signed root that was overwritten or deleted is not recovered by Convert to cross-certificate: restore it from a backup, or give its certificate to Restore as primary',
    ],
    related: ['Certificates', 'Templates', 'CRL/OCSP']
  },

  // ===== CERTIFICATES =====
  certificates: {
    title: 'Certificates',
    subtitle: 'Issue, manage, and monitor certificates',
    overview: 'Central management for all X.509 certificates. Issue new certificates from your CAs, import existing ones, track expiry dates, and handle renewals and revocations.',
    sections: [
      {
        title: "Conformance linting",
        content: "The Lint action on a certificate's detail runs it through standards linters and shows the findings. Informative only, it never blocks issuance.",
        items: [
          { label: "Profiles", text: "RFC 5280 (always relevant), CA/Browser Forum Baseline Requirements (TLS server certificates) and ETSI EN 319 412 (qualified and eIDAS-related certificates, including qcStatements)" },
          { label: "Severities", text: "Findings are graded fatal, error, warning, notice, info" },
          { label: "Engine", text: "Powered by pkilint (and zlint when its binary is present): an optional server dependency" },
          { label: "Internal PKI", text: "CA/Browser Forum rules target public certificates; expect non-applicable findings on an internal PKI" },
        ]
      },
      {
        title: 'Certificate Status',
        icon: Certificate,
        definitions: [
          { term: 'Valid', description: 'Within validity period and not revoked' },
          { term: 'Expiring', description: 'Will expire within 30 days' },
          { term: 'Expired', description: 'Past the "Not After" date' },
          { term: 'Revoked', description: 'Explicitly revoked (published in CRL)' },
          { term: 'Orphan', description: 'Issuing CA no longer exists in the system' },
          { term: 'Archived', description: 'Superseded by a renewal or re-enrolment that kept the old record for history (SCEP, EST, WSTEP, ACME, OCSP responder); listed with the "Archived" status filter' },
        ]
      },
      {
        title: 'Actions',
        icon: Key,
        items: [
          { label: 'Issue', text: 'Create a new certificate signed by one of your CAs' },
          { label: 'Import', text: 'Import an existing certificate (PEM, DER, or PKCS#12)' },
          { label: 'Renew', text: 'In-place since v2.214: same id/refid, new serial and validity, the superseded serial stays on the CRL until the old expiry. A revoked certificate cannot be renewed. Asks for the validity of the new certificate in days, prefilled with the current duration; policies and the CA\'s expiry still cap it' },
          { label: 'Rename', text: 'Set a display name independent from the CN (defaults to CN or first SAN DNS name for CN-less certificates)' },
          { label: 'Revoke', text: 'Mark as revoked with a reason, will appear in CRL' },
          { label: 'Remove Hold', text: 'Unhold a certificate revoked with "Certificate Hold" reason, restores it to valid status' },
          { label: 'Revoke a held certificate', text: 'A certificate on hold can also be revoked for good with another reason, without passing through valid. The CRL and OCSP then give the new reason, and the invalidity date is the start of the hold unless one is given' },
          { label: 'Revocation at the ACME CA', text: 'Revoking a certificate obtained over ACME (by the client, or by the proxy under an upstream account UCM holds) also revokes it at that CA, whether it is revoked alone, in bulk, by an approved request, as a user certificate, with the enrolment or user it belongs to, as the related member of a pair, or by its key at UCM\'s own ACME server. If the CA does not confirm, the revocation is kept owed and sent again by the renewal task; a hold stays in UCM, ACME having none. If no account of UCM can speak for it, it stays local and a warning says to revoke it with the CA directly. The reason is sent when it is keyCompromise, affiliationChanged, superseded, cessationOfOperation or privilegeWithdrawn' },
          { label: 'Export', text: 'Download in PEM, DER, PKCS#12, or JKS format' },
          { label: 'PKCS#12 compatibility mode (v2.222)', text: 'The export dialogs offer a 3DES/SHA-1 profile for importers that reject the default AES-256 archive as a wrong password: Android 15 and earlier, macOS 14 and earlier, Windows Server 2016 and earlier, old Java. Off by default, it protects the file less well' },
          { label: 'Compare', text: 'Side-by-side comparison of two certificates' },
          { label: 'Other extensions (v2.251)', text: 'The certificate and CA details list the extensions UCM has no section for under Other extensions, with their OID, name when known, criticality and raw value. The issue form can add custom extensions on top of the template\'s' },
          { label: 'Compromised keys (v2.251)', text: 'A key revoked as keyCompromise stays known after its certificate is deleted, whatever CA issued it, Let\'s Encrypt included: the ACME client refuses it at the request, the renewal and the finalization, and EST refuses a CSR carrying it. The other issuance paths do not consult this list' },
          { label: 'ACME client certificates (v2.251)', text: 'A certificate obtained by the ACME client is renewed in place too, keeping its id and refid. The copies earlier renewals imported as new rows stay in the inventory until archived or deleted' },
        ]
      },
      {
        title: 'Custom Extra EKUs (RFC 5280 §4.2.1.12)',
        icon: ShieldCheck,
        content: 'The Issue Certificate form and the Sign CSR modal expose an "Extra EKUs" multi-select that lets you add Extended Key Usage OIDs on top of the cert type defaults:',
        items: [
          { label: 'Catalog', text: '26 well-known EKUs in a dropdown: Microsoft RDP (1.3.6.1.4.1.311.54.1.2), smartcard logon, document signing, IPsec, Kerberos PKINIT, etc.' },
          { label: 'Free-text OIDs', text: 'Any well-formed dotted OID matching ^[0-2](?:\\.(?:0|[1-9]\\d*)){1,15}$' },
          { label: 'Limit', text: 'Up to 16 OIDs total per certificate' },
          { label: 'Merged, never replaced', text: 'The cert type\'s default EKUs (e.g. serverAuth) stay locked-in as chips, extras are added on top' },
          { label: 'Rejected', text: 'anyExtendedKeyUsage (2.5.29.37.0) is explicitly disallowed' },
        ]
      },
      {
        title: 'Hybrid certificate pairs (RFC 9763)',
        icon: Stack,
        content: 'A classical certificate (A) and an ML-DSA one (B) for the same subject, linked: B carries the relatedCertificate extension naming A by its hash. Clients that know ML-DSA check both; the others keep using A.',
        items: [
          { label: 'Issue', text: 'Tick "Issue a hybrid pair" in the Issue Certificate form and choose the classical key and the ML-DSA level; both come from the same CA, with the same subject, names and validity, and B asserts no key usage or EKU that A lacks. Offered only when the policies of the CA allow both, never in FIPS mode. Under the ANSSI, BSI and EU ACM profiles, ML-DSA-65 and ML-DSA-87 are offered in the pair only. A policy that requires approval refuses the pair for now' },
          { label: 'Linked by request', text: 'A CSR carrying a relatedCertRequest signed by A\'s key (Sign CSR, ACME, EST, WSTEP) issues a B linked to A. A must be held here, valid, unrevoked and an end-entity certificate; a newer B naming the same A takes over the pair' },
          { label: 'Linked', text: 'Each member carries a Linked badge in the list and in its details, with a link that opens the other member' },
          { label: 'Revoke', text: 'Revoking one member, alone or in a bulk operation, also revokes the other unless you untick "Also revoke the linked certificate", e.g. to keep A when only the ML-DSA key is compromised; under a policy that requires approval both go together. A warning names the other member when it could not be revoked. ACME revocation revokes only the certificate presented' },
          { label: 'Renew', text: 'Renewing either member renews both, manually, in bulk or automatically, and the new B names the new A. A member renewed alone, the other being revoked, leaves the pair' },
          { label: 'Export', text: 'The Hybrid bundle format downloads a ZIP of both certificates, and of both keys when you include the key and may export keys' },
        ]
      },
      {
        title: 'On-disk certificate files (v2.140)',
        icon: HardDrive,
        items: [
          { label: 'Auto-materialized', text: '.crt / .key files are written under data/certs/ on every creation path (UI, CSR signing, ACME, SCEP, import)' },
          { label: 'CAs too', text: 'CA .crt / .key files are written under data/cas/ via the same mechanism' },
          { label: 'Safety net', text: 'A startup file-regeneration scan rebuilds any missing file from the database' },
          { label: 'Non-blocking', text: 'File-write errors are logged but never abort the database transaction' },
        ]
      },
      {
        title: 'Deployment (v2.215)',
        icon: CloudArrowUp,
        content: 'Push this certificate to remote hosts over SSH/SFTP or to an HTTP API, admin-only, targets are managed in Settings › Deployment.',
        items: [
          { label: 'Attach target', text: 'From the certificate detail view: pick a deploy target and set absolute destination paths for the certificate, private key and/or full chain (at least one). The full chain leaves out the root CA unless Include Root CA is ticked' },
          { label: 'HTTP API (v2.252)', text: 'An HTTP target takes no paths: on issuance, renewal and Deploy now, UCM sends one request built from the target\'s body template (certificate, chain, subject, serial, and the private key only when the target allows it)' },
          { label: 'Same host', text: 'To deploy on the UCM host itself, use an SFTP target at 127.0.0.1 with a dedicated SSH account; the sandboxed service cannot write outside its data directory' },
          { label: 'Automatic', text: 'On issuance and renewal, the bound files are pushed again and that deployment\'s optional reload command runs; deliveries are queued with retries' },
          { label: 'Files', text: 'Written atomically at the exact configured paths (parent directory must exist): key 0600, certificate/chain 0644' },
          { label: 'Deploy now', text: 'Manual push from the detail view, with the delivery status and last error shown per target' },
          { label: 'Renewal without the key', text: 'An EST, SCEP or WSTEP renewal moves deployments to the new certificate, except one that sends the private key when UCM does not hold the new key: it shows Not following the renewal, appears in the bell and the overview, and offers Reattach to the renewed certificate once UCM holds the key or the deployment stops sending it. Importing the key moves it on its own' },
        ]
      },
    ],
    tips: [
      'Star ⭐ important certificates to add them to your favorites list',
      'Use filters to quickly find certificates by status, CA, or search text: your selection is persisted across reloads',
      'Renewing keeps the same record (id, refid, creation date). Renew from the page generates a new key; the automatic renewal keeps the key. A certificate whose key UCM does not hold (SCEP, EST, WSTEP or ACME enrolment, import without the key) is refused (409): renew it through its protocol or sign a new request',
      'Need a non-standard EKU (Microsoft RDP, smartcard logon, document signing)? Add it via "Extra EKUs" instead of editing templates',
      'When a policy or the issuing CA\'s expiry shortens the requested validity, the result says so: "Issued for N day(s) instead of the M requested", with the reason',
      'An RSA-PSS signature is shown with its hash and salt length, e.g. RSASSA-PSS SHA-256 (salt 32)',
      'In a link view (opened from the overview), the Clear all filters button shown when nothing matches empties the link\'s statuses and the search and keeps the link\'s other filters; removing a chip drops that filter, the Clear button of the chip row leaves the link view, and your saved filters are left untouched',
    ],
    warnings: [
      'Revocation is generally permanent: except for "Certificate Hold" which can be removed (unhold) or made permanent with another reason',
      'A valid, non-revoked certificate cannot be deleted on its own: Delete explains why and offers "Revoke, then delete", so the revocation reaches CRL/OCSP; revocations survive deletion',
      'UCM signs with SHA-256, SHA-384 or SHA-512 only: SHA-224 and unknown hash names are refused instead of being replaced by SHA-256',
    ],
    related: ['CAs', 'CSRs', 'Templates', 'CRL/OCSP']
  },

  // ===== USER CERTIFICATES =====
  'user-certificates': {
    title: 'User Certificates',
    subtitle: 'Manage mTLS client certificates',
    overview: 'Dedicated management for mTLS client certificates enrolled via the Account page. View, export, revoke, and delete certificates issued to users for mutual TLS authentication.',
    sections: [
      {
        title: 'Certificate Status',
        icon: Certificate,
        definitions: [
          { term: 'Valid', description: 'Within validity period and not revoked' },
          { term: 'Expiring', description: 'Will expire within 30 days' },
          { term: 'Expired', description: 'Past the "Not After" date' },
          { term: 'Revoked', description: 'Explicitly revoked by an operator or admin' },
        ]
      },
      {
        title: 'Actions',
        icon: Key,
        items: [
          { label: 'Export', text: 'Download as PEM (with key and chain) or PKCS#12 (password-protected)' },
          { label: 'Revoke', text: 'Revoke with a reason, the certificate will appear in the CRL' },
          { label: 'Delete', text: 'Remove the certificate and its user association from UCM' },
        ]
      },
      {
        title: 'Permissions',
        icon: ShieldCheck,
        items: [
          { label: 'Viewers', text: 'Can see only their own certificates' },
          { label: 'Operators', text: 'Can view, export, revoke and delete all user certificates; exporting the private key of another user\'s certificate needs read:private_keys, which the role lacks' },
          { label: 'Admins', text: 'Full access, private keys included' },
          { label: 'Auditors', text: 'Can view and export certificates, without their private key' },
        ]
      },
    ],
    tips: [
      'Enroll new mTLS certificates from Account → mTLS tab',
      'Certificates are stored and managed by UCM like any other certificate',
      'Use the stats bar to quickly filter by status',
      'Click a row to view full certificate details in the inspector',
    ],
    warnings: [
      'Revoking a user certificate immediately prevents mTLS login with that certificate',
      'Deleting removes the certificate permanently: it cannot be recovered',
    ],
    related: ['Certificates', 'Account', 'Settings']
  },

  // ===== CSRs =====
  csrs: {
    title: 'Certificate Signing Requests',
    subtitle: 'Manage CSR workflow',
    overview: 'Upload, review, and sign Certificate Signing Requests. CSRs allow external systems to request certificates from your CAs without exposing private keys.',
    sections: [
      {
        title: 'Workflow',
        icon: FileText,
        items: [
          { label: 'Generate CSR', text: 'Create a new CSR with key pair directly in UCM: RSA, EC, Brainpool or ML-DSA-44/65/87' },
          { label: 'Upload CSR', text: 'Accept PEM-encoded CSR files or paste PEM text' },
          { label: 'Review', text: 'Inspect subject, SANs, key type, and signature before signing' },
          { label: 'Sign', text: 'Select a CA, certificate type, set validity period, and issue the certificate' },
          { label: 'Request checks', text: 'The subject and names of the request are held to the issue form\'s rules: CN at most 64 characters, C two letters, DNS names in RFC 5280 syntax (no space, underscore, trailing dot, IP address, all-digit last label, or wildcard past the first label). A CN in DNS name syntax gives a DNS name (a single label only for a server or device certificate, none for S/MIME); another gives none, with a notice when a server CN looks like a host. A sub-CA gets none, and a valid emailAddress in the subject is added to the SAN. Each refusal names its reason' },
          { label: 'Add names', text: 'When signing, add email, DNS, IP or URI names to those of the request, for instance the email address of an S/MIME certificate requested from a smart card. They pass the CA name constraints, issuance policies and approval like any other' },
          { label: 'Sign again', text: 'In History, put a signed request back in Pending to sign it once more with other EKUs, names or validity, without generating a new key' },
          { label: 'Download', text: 'Download the original CSR in PEM format' },
          { label: 'Download key', text: 'Download the private key of a CSR generated in UCM, to deploy it next to a certificate issued by an external CA (requires the read:private_keys permission)' },
        ]
      },
      {
        title: 'Tabs',
        icon: ListChecks,
        items: [
          { label: 'Pending', text: 'CSRs awaiting review and signing' },
          { label: 'History', text: 'Signed requests with their certificate: download either one, or sign the request again. Both tabs page, search and sort across every request; History also searches by signing CA' },
        ]
      },
    ],
    tips: [
      'CSRs preserve the requester\'s private key: it never leaves their system',
      'Upload Key attaches a private key to a pending CSR, so the signed certificate can be exported as PKCS#12',
      'A certificate imported for a CSR generated in UCM completes that CSR: the record keeps its private key, so the certificate exports with it',
      'Use Microsoft CA mode to sign CSRs via AD CS when connected to a Windows PKI',
      'A certificate for an ML-DSA key keeps only signature bits: keyEncipherment, dataEncipherment and keyAgreement asked by the template are removed, and the result says so',
      'A CSR generated with related_to (API, needs read:private_keys) names an existing certificate A: signing it issues a certificate linked to A (RFC 9763), refused if it asserts a key usage or EKU A lacks',
      'When signing, use "Extra EKUs" to add Microsoft RDP, smartcard logon, IPsec or any other dotted OID: the CSR\'s existing EKU is rebuilt with the merged set',
      'When a policy or the issuing CA\'s expiry shortens the requested validity, the result says so: "Issued for N day(s) instead of the M requested", with the reason',
    ],
    related: ['Certificates', 'CAs', 'Templates', 'Microsoft CA']
  },

  // ===== TEMPLATES =====
  templates: {
    title: 'Certificate Templates',
    subtitle: 'Reusable certificate profiles',
    overview: 'Define reusable certificate profiles with pre-configured subject fields, key usage, extended key usage, validity periods, and other extensions. Apply templates when issuing or signing certificates.',
    sections: [
      {
        title: 'Source',
        icon: FileText,
        definitions: [
          { term: 'System', description: 'Seeded at install. Duplicate one for an editable copy: it cannot be edited or deleted itself' },
          { term: 'Custom', description: 'Created or imported here, and the only kind that can be edited or deleted' },
        ]
      },
      {
        title: 'Features',
        icon: Gear,
        items: [
          { label: 'Type', text: 'Web Server, Email, VPN Server or Client, Code Signing, Client Auth, OCSP Signing, Smartcard Logon or Custom. Sets the Key Usage, EKU and SAN defaults' },
          { label: 'Subject Defaults', text: 'Pre-fill Organization, OU, Country, State, City and Email. The Email also becomes a SAN, whatever the certificate type' },
          { label: 'Key Usage', text: 'Digital Signature, Key Encipherment, etc.' },
          { label: 'Extended Key Usage', text: 'Any purpose the server knows: Server Auth, Client Auth, Code Signing, Email Protection, Smartcard Logon, Time Stamping, OCSP Signing, IPsec, Microsoft RDP and others' },
          { label: 'SAN types', text: 'The name types (DNS, IP, Email, URI, UPN) a request made with the template may carry. With "Enforce the allowed SAN types" on, the issue form, Sign CSR, the enrollment protocols, renewals and approvals refuse any other type, and a name only implied by the CN is left out. New templates have it on; older ones and the built-in ones have it off. None checked: every type is allowed' },
          { label: 'Validity', text: 'Default validity period in days' },
          { label: 'Duplicate', text: 'Clone an existing template and modify it' },
          { label: 'Show system', text: 'Hide the built-in templates to work with your own only. Remembered per browser' },
          { label: 'Deactivate', text: 'A deactivated template, built-in ones included, is no longer offered by the Issue Certificate form nor to Windows autoenrollment, and shows an Inactive badge. Activate brings it back. A built-in template can be deactivated, not edited: duplicate it to change it' },
          { label: 'Import/Export', text: 'Share templates as JSON files between UCM instances: the page exports one template at a time, and an import file may hold one or several' },
          { label: 'qcStatements', text: 'Optional ETSI EN 319 412-5 statements added to every certificate issued from the template: QcCompliance, QcType (signature, seal or website), QcSSCD, QcPDS (HTTPS URL and two-letter language), QcRetentionPeriod, QcLimitValue, QcCClegislation (for a certificate qualified under a non-EU legal framework) and the semantics identifier. Not applied to EST, WSTEP or mTLS issuance, and a qcStatements extension in a CSR is ignored. QcIdentMethod, QcQSCDlegislation and PSD2 statements are not supported' },
          { label: 'Policy OIDs', text: 'Extra certificate policy OIDs (for example the ETSI QCP-n, QCP-l, QCP-n-qscd, QCP-l-qscd and QCP-w policies), added after the CA\'s own policy' },
          { label: 'Custom extensions', text: 'Extensions UCM does not model, each an OID, a critical flag and the DER value in hex, added as given to every certificate issued from the template (issue form, Sign CSR, ACME, SCEP, WSTEP, approvals; renewals keep them). The issue form can add more or replace one of the same OID. Extensions UCM sets itself are refused: use their own settings. A client that does not recognise a critical extension rejects the certificate' },
          { label: 'Key Type', text: 'RSA-2048, RSA-3072, RSA-4096, EC-P256, EC-P384 or EC-P521, with a SHA-256, SHA-384 or SHA-512 digest, or ML-DSA-44, ML-DSA-65 or ML-DSA-87. The digest is the issuing CA\'s signing hash, not the leaf key\'s: it still applies to an ML-DSA leaf under an RSA or EC CA, and an ML-DSA CA ignores it' },
          { label: 'Digest preference (v2.251)', text: 'Every path that issues from the template (issue form, Sign CSR, ACME, SCEP, WSTEP, TSA signer; EST uses no template) signs with its digest, raised to the one matching the CA key: SHA-384 for P-384, SHA-512 for P-521. When a policy forbids it, the closest stronger digest allowed signs instead, and the result says "Signature digest X replaced by Y by policy"' },
          { label: 'Brainpool', text: 'EC-BP256, EC-BP384 and EC-BP512 (RFC 5639, listed under Brainpool in key type lists, hidden in FIPS mode). OpenSSL and Windows read their chains and signatures, but Chrome, Firefox, Go, rustls, GnuTLS and Java without Bouncy Castle refuse them for TLS, and Windows Schannel does not enable them by default. On an HSM, only PKCS#11 providers hold them' },
        ]
      },
      {
        title: 'Windows Autoenrollment',
        icon: WindowsLogo,
        items: [
          { label: 'Allow autoenrollment', text: 'Advertise the template as autoEnroll=true in Certificate Enrollment Policy so GPO/Kerberos clients request it automatically at logon. Off by default, manual enrollment stays possible without it' },
          { label: 'Build subject from Active Directory', text: 'Derive the subject and SAN from the requester\'s AD object (via the AD Connector) instead of requiring the client to supply one, for unattended GPO autoenrollment. On the Kerberos endpoints a subject named in the request is ignored and computer accounts are refused; machine templates always take the computer\'s DNS name' },
          { label: 'Restrict enrollment to AD group', text: 'Only members of the configured AD group (nested membership included) may enroll over the Kerberos endpoint. Blank = any authenticated principal. Not enforced on the Username/Password endpoint' },
          { label: 'Pinned subject fields', text: 'Force C/ST/L/O/OU values onto every certificate issued over WSTEP, overriding the CSR or AD derivation for those fields. CN and SAN are never affected, leave a field blank to keep it dynamic' },
          { label: 'Common name pattern', text: 'Builds the CN from fixed text and directory variables, e.g. {hostname}-WiFi or {displayName}, for a template whose subject UCM builds. Only the CN changes: the SAN and the SID extension stay the directory\'s. A variable left empty or a CN over 64 characters refuses the request, and so does a subject that a certificate of the same CA already carries for another account' },
        ]
      },
    ],
    tips: [
      'Create separate templates for TLS servers, clients, and code signing',
      'Use the Duplicate action to quickly create variations of a template, including of a system one',
      'Templates with autoenrollment flags show AD / Auto / ACL / Pinned badges in the list',
    ],
    related: ['Certificates', 'CSRs', 'CAs']
  },

  // ===== CRL/OCSP =====
  crlocsp: {
    title: 'CRL & OCSP',
    subtitle: 'Certificate revocation services',
    overview: 'Manage Certificate Revocation Lists (CRL) and Online Certificate Status Protocol (OCSP) services. These services allow clients to verify whether a certificate has been revoked.',
    sections: [
      {
        title: 'CRL Management',
        icon: ClockCounterClockwise,
        items: [
          { label: 'Auto-Regeneration', text: 'Toggle automatic CRL regeneration per CA' },
          { label: 'Manual Regenerate', text: 'Force CRL regeneration immediately' },
          { label: 'Download CRL', text: 'Download the CRL as PEM (.crl file); the DER form is served at the CDP URL' },
          { label: 'CRL deployment', text: 'Attach an SSH/SFTP target to push every regenerated CRL automatically. Each binding selects PEM or DER, its destination path, optional parent CRLs and its own reload command' },
          { label: 'CDP URL', text: 'CRL Distribution Point URL to embed in certificates' },
          { label: 'Validity', text: 'Per-CA CRL validity from 1 day up to 5 years (90d/180d/1y/3y/5y for offline CAs that cannot re-sign on schedule). A warning appears past one year, relying parties may keep stale revocation data for the whole window' },
          { label: 'Signature digest', text: 'SHA-256, SHA-384 or SHA-512 for an RSA or EC CA. An Ed25519, Ed448 or ML-DSA CA signs without one: a digest stored for it earlier is shown as ignored, with a Clear button' },
          { label: 'Default digest (v2.251)', text: 'Without a digest set, a P-384 or P-521 CA signs its CRLs with SHA-384 or SHA-512. CRLs already issued keep theirs: the next one follows' },
          { label: 'External CRL', text: 'Key-less/offline CAs cannot self-sign a CRL, upload one generated next to the offline key from the CA detail view; it is validated (signature, issuer, monotonicity) and served at the same CDP URL (v2.215)' },
          { label: 'Delta CRL', text: 'When delta CRLs are enabled, a new delta is generated right after each complete CRL, so the delta served always refers to the latest base' },
          { label: 'CRL number', text: 'Base and delta CRLs of a CA share one increasing number, never given to two CRLs, even when two generations run at once. The highest number reached is kept per CA name and key and travels in backups, so a CA restored on another server, or deleted and imported again, continues from it' },
        ]
      },
      {
        title: 'OCSP Service',
        icon: Globe,
        items: [
          { label: 'Status', text: 'Indicates whether the OCSP responder is active for each CA' },
          { label: 'AIA URL', text: 'Authority Information Access URLs, OCSP responder and CA Issuers certificate download endpoints embedded in issued certificates' },
          { label: 'Cache', text: 'Response cache with automatic daily cleanup of expired entries' },
          { label: 'Total Queries', text: 'Number of OCSP requests answered since the service started, and how many were served from the cache' },
          { label: 'HTTP caching', text: 'An answer without a nonce can be kept by HTTP caches until its nextUpdate, an hour at most (RFC 5019 §6.2: Expires, Last-Modified, ETag); an answer with a nonce is not reused' },
          { label: 'Delegated Responder', text: 'Sign responses with a dedicated OCSPSigning certificate instead of the CA key, assign one per CA from its panel on this page' },
          { label: 'Responder Auto-Renewal', text: 'A daily task re-issues the delegated responder certificate before expiry (same key pair, renewed at par) and rebinds it, enabled by default. The switch and its window (days before expiry, default 30) are in Settings › Security' },
        ]
      },
    ],
    tips: [
      'Enable auto-regeneration to keep CRLs fresh after certificate revocations',
      'Copy CDP, OCSP, and AIA CA Issuers URLs to embed them in your certificate profiles',
      'OCSP provides real-time revocation checking and is preferred over CRL',
    ],
    related: ['Certificates', 'CAs']
  },

  // ===== SCEP =====
  scep: {
    title: 'SCEP',
    subtitle: 'Simple Certificate Enrollment Protocol',
    overview: 'SCEP enables network devices (routers, switches, firewalls) and MDM solutions to automatically request and obtain certificates. Devices authenticate using a challenge password.',
    sections: [
      {
        title: 'Tabs',
        icon: ListChecks,
        items: [
          { label: 'Requests', text: 'Pending, approved, and rejected SCEP enrollment requests' },
          { label: 'Configuration', text: 'SCEP server settings: CA selection, auto-approve' },
          { label: 'Profiles', text: 'Named enrollment endpoints, each with its own URL, CA, template and challenge' },
          { label: 'Intune app registrations', text: 'Entra app registrations (tenant ID, client ID, client secret) shared by the profiles that validate Intune challenges; an empty secret on edit keeps the current one, Test connection requests a token and discovers the service without consuming any challenge, and an app still used by a profile cannot be deleted' },
          { label: 'Challenges', text: 'View and regenerate the challenge passwords for device enrollment' },
          { label: 'Information', text: 'SCEP endpoint URLs and integration instructions' },
        ]
      },
      {
        title: 'Configuration',
        icon: Gear,
        items: [
          { label: 'Signing CA', text: 'Select which CA signs SCEP-enrolled certificates. Devices encrypt their request to this CA, so it must hold an RSA key in software: EC, HSM-backed, keyless, offline and revoked CAs are not listed (v2.248)' },
          { label: 'Auto-Approve', text: 'Automatically approve requests with valid challenge passwords, or renewals signed by a certificate the same endpoint issued' },
          { label: 'Serve on plain HTTP', text: 'Off by default. Also answers SCEP on the HTTP protocol port (8080 by default), at http://your-server:8080/scep/pkiclient.exe and the profile URLs, for clients such as sscep that cannot use HTTPS. RFC 8894 §7.10: SCEP messages are already protected, the CMS envelope keeps the challenge password private' },
          { label: 'Challenge Password', text: 'Shared secret that devices use to authenticate enrollment. A renewal (RenewalReq) signed by a certificate that the same endpoint (profile or global) issued is authenticated by that certificate, so its challenge is not checked and rotating the secret does not stop enrolled devices from renewing (RFC 8894 §2.4). Any other certificate still needs the endpoint\'s challenge' },
          { label: 'Device keys (v2.248)', text: 'A device signs its request with an RSA, ECDSA, Ed25519 or ML-DSA key; an ML-DSA signature follows RFC 9882 (SHA-512 digest). Ed448 is refused, and ML-DSA too in FIPS mode' },
          { label: 'Request names', text: 'A request whose subject or DNS names break RFC 5280 (a CN over 64 characters, a DNS name with a space, apostrophe or underscore, such as an iOS device name) is refused with its reason, once its challenge is checked and before it is queued, and Intune is told of the refusal; a renewal keeps the names its certificate carries. Build an Intune SAN DNS from a DNS-safe value' },
        ]
      },
      {
        title: 'Profiles',
        icon: Gear,
        items: [
          { label: 'URL segment', text: 'Each profile is served at /scep/<segment>/pkiclient.exe, point each device fleet or MDM profile at its own URL' },
          { label: 'Certificate template', text: 'When a template is bound, its key usage, extended key usage and validity govern every certificate issued through the profile' },
          { label: 'Signature digest (v2.251)', text: 'Certificates issued through a profile are signed with its template\'s digest, raised to the one matching the CA key, as a preference the policies can override. Without a template, the CA key\'s digest applies' },
          { label: 'Per-profile challenge', text: 'Each profile has its own challenge password, stored encrypted, with the same expiry window as the global challenge' },
          { label: 'Default endpoint', text: 'The unlabelled /scep/pkiclient.exe endpoint keeps serving the global configuration' },
          { label: 'Microsoft Intune validation', text: 'A profile can validate against Intune\'s own per-device SCEP challenge instead of a static password: pick an app registration from the Intune app registrations tab (SCEP challenge validation + Application.Read.All permissions), Auto-Approve stays required; on upgrade each existing profile gets an app named after it, deduplicated by tenant and client' },
          { label: 'Manual approval', text: 'A request that came through a profile is approved with that profile\'s template (validity, key usages), exactly as auto-approval would issue it' },
          { label: 'Purposes no enrollee may hold', text: 'A template bound to a profile cannot carry OCSP signing, timestamping, any purpose or Smartcard Logon, and a SCEP renewal never carries them over; Smartcard Logon is allowed when the profile validates against Intune, which vouches for the identity' },
        ]
      },
    ],
    tips: [
      'Use unique challenge passwords per CA for better security auditing',
      'Auto-approve is convenient but review requests manually in high-security environments',
      'SCEP URL: https://your-server:8443/scep/pkiclient.exe for the configured CA, https://your-server:8443/scep/<profile>/pkiclient.exe for a profile',
      'Intune profiles need Auto-Approve on. Intune\'s enrollment is a synchronous validate-then-issue round trip with no approval queue on its side',
    ],
    warnings: [
      'The challenge password belongs in the CSR, which travels inside the CMS envelope encrypted to the CA (RFC 8894 §2.4), so plain HTTP does not expose it; a client that sends it as a signed attribute outside the envelope does, over HTTP and to anything that logs the request',
    ],
    related: ['Certificates', 'CAs']
  },

  // ===== EST =====
  est: {
    title: 'EST',
    subtitle: 'Enrollment over Secure Transport',
    overview: 'EST (RFC 7030) provides secure certificate enrollment over HTTPS with mutual TLS (mTLS) or HTTP Basic authentication. Ideal for modern enterprise environments requiring standards-based enrollment with strong transport security.',
    sections: [
      {
        title: 'Tabs',
        icon: ListChecks,
        items: [
          { label: 'Settings', text: 'Enable EST, select signing CA, configure authentication credentials and certificate validity' },
          { label: 'EST Endpoints', text: 'EST endpoint URLs for integration and enrollment statistics' },
        ]
      },
      {
        title: 'Authentication',
        icon: ShieldCheck,
        items: [
          { label: 'mTLS (Mutual TLS)', text: 'Client presents a certificate during TLS handshake, strongest authentication method' },
          { label: 'HTTP Basic Auth', text: 'Username/password fallback when mTLS is not available. With allow_empty_username set through PATCH /api/v2/est/config, a client may also send an empty username with the password (RFC 7030 §3.2.3, v2.252)' },
          { label: 'Presented certificate', text: 'For /simpleenroll and /serverkeygen over mTLS, a certificate signed by the EST CA must be one it still holds: revoked, superseded or deleted certificates are refused (RFC 7030 §3.3.2). A certificate another CA of this server issued is refused once it or a CA above it is revoked, or once expired (v2.252); one from an authority this server does not hold is left to the TLS layer' },
          { label: 'tls-unique linking', text: 'A CSR with a challengePassword must carry the tls-unique value of its TLS 1.2 connection to UCM (RFC 7030 §3.5); it is refused with 400 when the value differs or cannot be verified (TLS 1.3, a proxy in front). /csrattrs does not ask for one. ignore_challenge_password, set through PATCH /api/v2/est/config, skips the check for a client that puts a password there (v2.252)' },
          { label: 'Compromised keys', text: 'A CSR whose key was revoked as compromised (keyCompromise) is refused with 400 (v2.252)' },
        ]
      },
      {
        title: 'Endpoints',
        icon: Globe,
        items: [
          { label: '/cacerts', text: 'Retrieve the CA certificate chain (no authentication required)' },
          { label: '/simpleenroll', text: 'Submit a CSR and receive a signed certificate' },
          { label: '/simplereenroll', text: 'Renew an existing certificate (requires mTLS; without a client certificate: 403). A CSR without SubjectAltName renews the certificate\'s own names, or none when it had none, instead of a name built from the CN (RFC 7030 §4.2.2, v2.252)' },
          { label: '/csrattrs', text: 'Get CSR attributes recommended by the server: keyUsage, subjectAltName and extKeyUsage as bare OIDs (RFC 9908 §5.2, v2.252). csrattrs_legacy_encoding, set through PATCH /api/v2/est/config, serves the former shape (the OIDs inside an extensionRequest) for a client that needs it' },
          { label: 'Errors', text: 'Enrollment refusals, rate limiting included, come as a plain-text message (text/plain, RFC 8951 §5) saying why, such as a body that is not base64 or not a PKCS#10 CSR, or the CA\'s name constraints (v2.252)' },
          { label: '/serverkeygen', text: 'Server generates a key pair and returns certificate + key. The key takes the issuing CA\'s strength, in the family of the request\'s key when RSA or EC (its size or curve is ignored), else the CA\'s, moved to the closest type the policies allow. The key comes as unencrypted PKCS#8 under TLS; a CSR naming the mTLS certificate\'s key (AsymmetricDecryptKeyIdentifier) gets it encrypted to that certificate, by key transport for RSA of 2048 bits or more (keyEncipherment) or key agreement for EC (keyAgreement), with the algorithms the CSR\'s SMIMECapabilities list, in a key package signed by an EST key generator certificate that the issuing CA issues for this purpose (Ed25519 under an Ed448 CA, v2.252)' },
        ]
      },
    ],
    tips: [
      'EST is the modern replacement for SCEP: prefer EST for new deployments',
      'Use mTLS authentication for highest security. Basic Auth is a fallback',
      'The /simplereenroll endpoint requires the client to present its current certificate via mTLS',
      'Copy endpoint URLs from the EST Endpoints tab to configure your EST clients',
    ],
    warnings: [
      'EST requires HTTPS: the client must trust the UCM server certificate or CA',
      'mTLS authentication requires proper TLS termination config (reverse proxy must forward client certs)',
    ],
    related: ['Certificates', 'CAs', 'SCEP', 'ACME']
  },

  // ===== TSA =====
  tsa: {
    title: 'TSA',
    subtitle: 'Time Stamp Authority',
    overview: 'TSA (RFC 3161) provides trusted timestamps that prove a document or hash existed at a specific point in time. Used for code signing, legal compliance, and audit trails.',
    sections: [
      {
        title: 'Tabs',
        icon: ListChecks,
        items: [
          { label: 'Settings', text: 'Enable TSA, select the signing CA, and configure the TSA policy OID' },
          { label: 'TSA Endpoint', text: 'TSA endpoint URL, usage examples with OpenSSL, and request statistics' },
        ]
      },
      {
        title: 'Configuration',
        icon: Gear,
        items: [
          { label: 'Signing CA', text: 'The CA whose own certificate signs timestamp tokens when no dedicated signing certificate is set. A CA outside its validity period does not sign: /tsa answers 503. Strict verifiers (openssl ts -verify, jarsigner) refuse tokens signed by a CA certificate, and the page warns while the CA signs' },
          { label: 'Policy OID', text: 'Object Identifier for the TSA policy, included in every timestamp response. The default 1.2.3.4.1 is OpenSSL\'s example OID, a placeholder the page warns about: use an OID from your organization\'s arc' },
          { label: 'Enable/Disable', text: 'Toggle the TSA endpoint on or off without losing configuration' },
          { label: 'Require dedicated certificate', text: 'Opt-in: refuse to sign timestamps with the CA certificate itself, requires a dedicated end-entity signing certificate with a critical timeStamping EKU (RFC 3161)' },
                  { label: 'Signing certificate (v2.217)', text: 'Sign tokens with a dedicated end-entity certificate picked from issued certificates (timeStamping EKU, RSA, ECDSA or ML-DSA key held by UCM; Ed25519 and Ed448 certificates are not offered, nor ML-DSA in FIPS mode). Renewals are followed automatically; an expired or revoked signer fails requests with 503 and never falls back to the CA certificate' },
                  { label: 'Generate a signing certificate (v2.218)', text: 'One-click issuance of a purpose-built RFC 3161 signer: CA:FALSE, KeyUsage digitalSignature only, and a critical exclusive timeStamping EKU, the shape strict verifiers (openssl ts -verify) require. Issued from the configured TSA CA and selected automatically when no usable signer is set. The certificate has source "manual": add "manual" to the auto-renewal sources or renew it yourself before expiry' },
        ]
      },
      {
        title: 'Usage',
        icon: Clock,
        items: [
          { label: 'Create Request', text: 'openssl ts -query -data file.txt -sha256 -cert -out request.tsq (-cert asks for the signer certificate in the response, which openssl ts -verify needs)' },
          { label: 'Send to TSA', text: 'curl -H "Content-Type: application/timestamp-query" --data-binary @request.tsq https://your-server/tsa -o response.tsr' },
          { label: 'Verify', text: 'openssl ts -verify -data file.txt -in response.tsr -CAfile ca-chain.pem (dedicated RSA or ECDSA signer; a token signed by the CA certificate fails with "unsuitable certificate purpose"). An ML-DSA token fails openssl ts -verify: check its signature with openssl cms -verify (OpenSSL 3.5 or later), then compare the message imprint with the hash of the file' },
        ]
      },
    ],
    tips: [
      'TSA timestamps are used in code signing to ensure signatures remain valid after certificate expiry',
      'The TSA endpoint accepts HTTP POST with Content-Type: application/timestamp-query (or application/octet-stream)',
      'A request carrying any extension is refused with unacceptedExtension, and a malformed one with badDataFormat (RFC 3161 §2.4.1)',
      'Tokens carry genTime in whole seconds with a declared accuracy of 1 second, and the request message imprint copied as sent',
      'Use SHA-256 or stronger hash algorithms when creating timestamp requests',
      'No authentication is required: the TSA endpoint is publicly accessible like CRL/OCSP',
    ],
    warnings: [
      'A valid signing CA must be configured before enabling TSA',
      'openssl ts -verify and jarsigner refuse tokens signed by the CA certificate: RFC 3161 requires a dedicated signer with a critical, exclusive timeStamping EKU. Generate one on the Settings tab',
      'The TSA endpoint is a public protocol endpoint: do not put sensitive data in timestamp requests',
    ],
    related: ['CAs', 'Certificates', 'CRL & OCSP']
  },

  // ===== ACME =====
  acme: {
    title: 'ACME',
    subtitle: 'Automated Certificate Management',
    overview: 'UCM supports two ACME modes: ACME client for public certificates from any RFC 8555-compliant CA (Let\'s Encrypt, ZeroSSL, HARICA, etc.), and Local ACME server for internal PKI automation with multi-CA domain mapping.',
    sections: [
      {
        title: "Renewal Information (ARI, RFC 9773)",
        content: "The local ACME server advertises a renewalInfo resource so clients learn the ideal moment to renew each certificate.",
        items: [
          { label: "Suggested window", text: "Returns a start/end window centered before expiry so renewals spread over time" },
          { label: "Revocation", text: "A revoked certificate returns a window in the past so compliant clients renew immediately" },
          { label: "Unauthenticated", text: "renewalInfo is a plain GET, no account or JWS required (RFC 9773)" },
          { label: "ACME proxy (v2.252)", text: "For a certificate issued through the proxy, the upstream CA's window is relayed with its Retry-After, kept up to an hour. The window is computed locally when the CA announces no renewalInfo or gives no usable answer, or when the certificate is revoked in UCM" },
        ]
      },
      {
        title: 'ACME Client',
        icon: Globe,
        items: [
          { label: 'Client', text: 'Request certificates from any ACME CA, Let\'s Encrypt, ZeroSSL, HARICA, or custom' },
          { label: 'Orders tab (v2.219)', text: 'The client orders have their own "Let\'s Encrypt orders" sidebar tab with a visible/total count and a status filter, mirroring the Local orders view' },
          { label: 'External CA Accounts', text: 'One or more accounts per CA, several accounts can share the same CA directory URL (e.g. two Let\'s Encrypt accounts for administrative separation); an empty Directory URL defaults to Let\'s Encrypt Production' },
          { label: 'Custom Server', text: 'Set a custom ACME directory URL to use any RFC 8555-compliant CA' },
          { label: 'EAB', text: 'External Account Binding support for CAs that require pre-registration (ZeroSSL, HARICA, etc.)' },
          { label: 'Key Types', text: 'RSA-2048, RSA-4096, ECDSA P-256, ECDSA P-384, Brainpool P-256 or P-384, ML-DSA-44, ML-DSA-65 or ML-DSA-87 for certificate keys; ML-DSA is not offered in FIPS mode or on a build without it. A configured default this instance cannot generate fails the order instead of falling back to RSA-2048 (v2.248)' },
          { label: 'Reused key in FIPS mode', text: 'Reusing the key of a source certificate is refused when FIPS mode does not approve that key, ML-DSA included (v2.248)' },
          { label: 'Account Keys', text: 'ES256 (P-256), ES384 (P-384), or RS256 algorithms for ACME account keys' },
          { label: 'DNS Providers', text: 'Configure DNS-01 challenge providers (Cloudflare, Route53, Tencent DNSPod, Plesk, etc.). Plesk goes through its XML API; Verify TLS Certificate can be turned off for a self-signed panel and a DNS propagation delay added' },
          { label: 'Custom Command', text: 'DNS provider type running admin-configured local commands for TXT create/delete, record details passed via DOMAIN, RECORD_NAME, RECORD_VALUE, TTL, ACTION environment variables. Absolute binary path required, no shell, configurable timeout' },
          { label: 'Domains', text: 'Map domains to DNS providers for automatic validation' },
          { label: 'HTTP-01', text: 'UCM serves the challenge file of its pending orders at /.well-known/acme-challenge/ on the HTTP protocol port (8080 by default): forward that path from port 80 of the domain to UCM. Verify checks the file first, and HTTP-01 orders renew automatically' },
          { label: 'Renewal in place (v2.251)', text: 'A renewal keeps the certificate\'s id and refid, so the HTTPS binding, deployment bindings and webhooks follow it. Certificates that earlier renewals imported as new rows stay in the inventory: archive or delete them by hand' },
          { label: 'Interrupted orders (v2.251)', text: 'An order left processing by a restart goes back to pending with a message, ready for Verify Challenge, within about 15 minutes. A certificate the CA issued before a restart or a failed import is fetched by Check Status, the finalization or the next renewal' },
          { label: 'Stale pending orders (v2.251)', text: 'The renewal task removes the orders left pending for more than 7 days whose order at the CA has expired, or whose expiry is unknown, with their TXT records, and audits each removal. The TXT records of an order whose validation failed are removed once it is invalid' },
          { label: 'Order list (v2.251)', text: 'The Let\'s Encrypt orders tab loads every order, up to 5000, four pages at a time, and retries a page refused with 429 after its Retry-After. A page still missing leaves the orders obtained, with a notice that the list is partial' },
          { label: 'Renewal failures (v2.251)', text: 'An order shows its failed renewal count, with the last error and its date. After 5 failed scheduled renewals it is retried once a day, and each failure, manual ones included, emits the acme_order.renewal_failed event' },
          { label: 'Automatic renewal per order (v2.251)', text: 'A selected order shows an Automatic renewal switch that stops or resumes its renewal. Deleting a certificate after revoking it turns its order\'s renewal off, with a message' },
          { label: 'One renewal at a time (v2.251)', text: 'A renewal or finalization holds its order: a second one started meanwhile gets a 409, and the scheduler skips the order' },
          { label: 'Missing account or provider (v2.251)', text: 'An order whose CA account was deleted, whose DNS provider is disabled, or that reuses the key of a deleted certificate stops before the CA with a message saying what to do. Deleting or deactivating a CA account is refused (409) while issued orders renew through it' },
          { label: 'Compromised keys (v2.251)', text: 'A key revoked as compromised, whatever CA issued its certificate, is refused (409) at the request and before a renewal opens an order, even after that certificate was deleted. A renewal set to reuse such a key generates a new one' },
          { label: 'Revocation at the CA', text: 'Revoking a certificate obtained over ACME (by the client, or by the proxy under an upstream account UCM holds) also revokes it at that CA, whether it is revoked alone, in bulk, by an approved request, as a user certificate, with the enrolment or user it belongs to, as the related member of a pair, or by its key at UCM\'s own ACME server. If the CA does not confirm, the revocation is kept owed and sent again by the renewal task; a hold stays in UCM, ACME having none. If no account of UCM can speak for it, it stays local and a warning says to revoke it with the CA directly. The reason is sent when it is keyCompromise, affiliationChanged, superseded, cessationOfOperation or privilegeWithdrawn' },
          { label: 'Revoke on renewal (v2.251)', text: 'With Revoke old certificate after renewal on (Local ACME › Renewal Policy), the CA receives the local reason when it is keyCompromise, affiliationChanged, superseded or cessationOfOperation, and none otherwise. A failed revocation is retried by the renewal task until the certificate expires, emitting acme_order.revocation_failed' },
          { label: 'Renewal threshold (v2.249)', text: 'Days before expiry applies when the CA suggests no renewal window (ARI). A certificate whose lifetime is shorter than 1.5 times that threshold renews in its last third instead' },
          { label: 'Long names (v2.249)', text: 'A first name over 64 characters goes in the subject alternative name alone, marked critical, instead of failing the finalization' },
          { label: 'Domain and wildcard (v2.252)', text: 'An order for a domain and its wildcard gets one TXT value per authorization under the shared name, and the DNS providers add each value next to the others. DuckDNS, Hurricane Electric and FreeDNS keep one value per name, so such an order is refused before the CA is asked, as is a DuckDNS order naming two hosts under one subdomain: request them in separate orders, one after the other' },
          { label: 'TXT cleanup (v2.252)', text: 'Cleanup removes only the TXT value of its order, so another order, or the wildcard and apex sharing the name, keep theirs. DuckDNS, Hurricane Electric and FreeDNS hold one value per name: they clear it only when no other order in progress uses the name' },
          { label: 'Unique names (v2.251)', text: 'A DNS provider or External CA Account name already in use is refused (409), on creation and on rename. The upgrade renamed earlier duplicates "name (2)", "name (3)", oldest first' },
          { label: 'Vercel team (v2.251)', text: 'The Vercel provider takes an optional Team ID for domains owned by a team' },
          { label: 'RFC 2136 provider (v2.252)', text: 'The DNS server can be a host name. A filled-in Zone is used for the names inside it; for other names, or when it is empty, the zone is read from the SOA the configured server returns, then from the system resolver' },
          { label: 'ARI renewal time (v2.252)', text: 'When the CA suggests a renewal window, each certificate renews at the last 6-hour pass before a random moment drawn once inside it. The window is checked again after the CA\'s Retry-After, kept between one minute and one day, and never once the certificate has expired (RFC 9773)' },
          { label: 'CA errors (v2.252)', text: 'A CA error page that is not an ACME problem (an HTML 503) is reported with its HTTP status and Retry-After' },
          { label: 'RcodeZero token (v2.251)', text: 'RcodeZero needs an API token with zone read and write access, not one limited to the ACME permission' },
          { label: 'Checkdomain (v2.251)', text: 'Checkdomain removes a value by rewriting the zone\'s records without it, as its API documents, after reading every page. The SOA, the apex NS and the generated www copies are left out of that rewrite' },
        ]
      },
      {
        title: 'Local ACME Server',
        icon: HardDrive,
        items: [
          { label: 'Configuration', text: 'Enable/disable the built-in ACME server, select default CA' },
          { label: 'Local Domains', text: 'Map internal domains to specific CAs for multi-CA issuance' },
          { label: 'Accounts', text: 'View and manage registered ACME client accounts' },
          { label: 'Account e-mail (v2.218)', text: 'The contact e-mail of a local account can be edited from its detail panel. Per RFC 8555 the contact belongs to the ACME client, so its next account update may overwrite the value' },
          { label: 'History', text: 'Track all ACME certificate issuance orders' },
                  { label: 'Local orders (v2.217)', text: 'The Local orders tab lists the built-in server orders with a status filter, per-order delete and a purge action; expired non-issued orders are purged automatically every 6 hours, and a default signing digest applies to orders without a profile. Since v2.218 the purge also removes leftover pending sibling challenges of already-validated authorizations, and since v2.252 the expired and used nonces' },
                  { label: 'Profiles and templates (v2.221)', text: 'Certificate profiles (draft-ietf-acme-profiles) are advertised in the directory and selected by the client per order. Each profile sets validity and digest and can bind a certificate template, whose key usage and extended key usage then govern the issued certificate' },
                  { label: 'Default profile', text: 'Most clients request no profile. The default profile, chosen under the profiles, applies to their orders; without one they get 90 days and the default digest' },
                  { label: 'Revocation (v2.248)', text: 'The certificate a client sends to revoke must match the stored one byte for byte. Only an RSA or EC P-256, P-384 or P-521 certificate key can sign the request itself: revoke an ML-DSA, EdDSA or Brainpool certificate with the account that ordered it' },
                  { label: 'Revocation by authorizations (v2.252)', text: 'An account holding valid, unexpired authorizations for every name and IP address of a certificate this ACME server issued may revoke it, even if another account ordered it (RFC 8555 §7.6). Authorizations granted by auto-approval do not count' },
                  { label: 'Requested dates (v2.252)', text: 'An order may ask for notBefore and notAfter (cert-manager duration, lego --not-after): the certificate carries exactly those dates. A window longer than the profile\'s validity, outside the issuing CA\'s, forbidden by a policy or already past is refused instead of issued with other dates' },
                  { label: 'Expiry (v2.252)', text: 'An order past its expiry, or whose valid authorization has expired, can no longer be finalized: it becomes invalid and the client places a new order. An expired valid authorization reads expired' },
                  { label: 'Challenges (v2.252)', text: 'Reading a challenge with an empty payload never starts its validation: the client posts {} for that. A tls-alpn-01 certificate must carry exactly the validated name or IP address as its subject alternative name' },
                  { label: 'CAA identities (v2.252)', text: 'The directory advertises the configured CAA identifiers as caaIdentities, else the public ACME host, the same list finalize checks the CAA records against' },
        ]
      },
      {
        title: 'ACME Proxy',
        icon: Globe,
        items: [
          { label: 'Upstream CA account', text: 'Select one of the External CA Accounts: its directory URL (Let\'s Encrypt, ZeroSSL, any RFC 8555 CA) and EAB credentials are set on that account' },
          { label: 'Account Status', text: 'Shows whether UCM is registered with the upstream CA. Accounts are auto-registered on first proxy request' },
          { label: 'Test Connection', text: 'Verify connectivity to the upstream CA and check if EAB credentials are required' },
          { label: 'Reset Account', text: 'Clear the upstream registration of the selected CA account to force a new registration' },
          { label: 'EAB Credentials', text: 'External Account Binding credentials for CAs that require them (e.g., ZeroSSL, Google Trust), entered on the CA account in External CA Accounts' },
          { label: 'DNS Challenges', text: 'UCM handles DNS-01 challenges on behalf of clients using configured DNS providers' },
          { label: 'Purge replaced certificates', text: 'Opt-in toggle: when a proxy order finalizes, certificates previously imported by proxy orders for the exact same domain set are deleted. Revoked certificates are always kept; non-proxy certificates are never touched. Off by default' },
                  { label: 'Client pre-checks (v2.217)', text: 'The proxy also publishes the dns-01 TXT values computed with each client account key, so lego/Traefik/Caddy propagation pre-checks pass without being disabled, except on DuckDNS, Hurricane Electric and FreeDNS, which hold one value: disable the client pre-check there; a retried new-order returns the account still-pending order' },
          { label: 'Client compatibility (v2.246)', text: 'With EAB required, an onlyReturnExisting lookup and a new-account with a registered key return the existing account (cert-manager). The account URL answers reads, contact updates and deactivation, authorization deactivation is accepted (lego), and challenge responses carry Link rel="up"' },
          { label: 'Upstream errors (v2.252)', text: 'An error of the upstream CA reaches the client with its type (rateLimited, badCSR, rejectedIdentifier, alreadyRevoked...), status, subproblems and Retry-After. Errors about the proxy\'s own upstream account stay serverInternal' },
          { label: 'Profiles and validity (v2.252)', text: 'The directory lists the upstream CA\'s profiles. A profile, notBefore and notAfter requested by the client are passed upstream, a retried new-order reuses a pending order only when it carries them, and a profile the upstream CA does not offer is refused with invalidProfile' },
          { label: 'Refused TXT record (v2.252)', text: 'When the DNS provider refuses the TXT record, the challenge is not submitted upstream: the order, its authorizations and challenges turn invalid, none of its other challenges is submitted, and the provider\'s message is logged and kept on the order. TXT records of an invalid or deactivated order are removed' },
          { label: 'Failed challenge submission (v2.252)', text: 'When the upstream CA refuses the challenge response (a nonce refused more than three times, a rate limit), or answers a 5xx or nothing and the authorization does not show the challenge taken, the order turns invalid with the upstream error and stays invalid even if the CA validates it later. Its TXT records are removed (two minutes later while the CA may still read one, or at the 15-minute order housekeeping pass when a restart interrupted that delay); the client\'s next order on the same names is validated again, or is ready at once when the CA already validated them' },
          { label: 'CSR checks (v2.252)', text: 'At finalization the CSR must name exactly the order\'s identifiers, in its CN or SAN (RFC 8555 §7.4): otherwise it is refused with badCSR before anything reaches the upstream CA' },
          { label: 'Deactivated authorization (v2.252)', text: 'An order whose authorization the client deactivated stays invalid and gets no certificate, even when the order of another account on the same upstream order is issued (RFC 8555 §7.5.2)' },
          { label: 'Unknown URLs (v2.252)', text: 'A URL or method no route serves under /acme or /acme/proxy gets a malformed problem document linking the directory, as 405 with Allow when another method is served, such as a GET on a POST-only resource (RFC 8555 §6.3)' },
          { label: 'Challenge reads (v2.252)', text: 'The proxy reads a challenge through its authorization, never with a POST-as-GET on the challenge, which starts the validation on some CAs before the TXT record exists. Key rollover is not offered by the proxy directory' },
        ]
      },
      {
        title: 'DNS UPDATE (RFC 2136) for the ACME proxy',
        items: [
          { label: 'What it is', text: 'Clients use their standard rfc2136 solver (certbot, lego, cert-manager, acme.sh, win-acme, Posh-ACME) and point it at UCM. UCM still creates the TXT record through its own DNS provider' },
          { label: 'Keys', text: 'Create keys for each proxy account under External CA Accounts. A key can be linked to an EAB credential: it then works only for orders of the ACME account registered with that credential. UCM shows the secret once' },
          { label: 'Accepted changes', text: 'UCM accepts only a TXT record under _acme-challenge with the value it expects for the order. It refuses other changes. It always answers a delete with NOERROR' },
          { label: 'Port and network', text: 'Set the listener port in the ACME proxy section (0 disables it, 1024 to 65535, a restart is needed). Use it in the internal network only. To use port 53, map it in Docker or Kubernetes, or with a firewall redirect' },
          { label: 'Algorithms', text: 'hmac-sha256, hmac-sha384 and hmac-sha512. UCM refuses md5 and sha1, the defaults of many clients: set the algorithm in every client. cert-manager does not support sha384, and win-acme computes it wrongly' },
          { label: 'Zone discovery (SOA)', text: 'Clients ask for the SOA record to find the zone, and UCM answers it. win-acme sends test updates instead, and always uses port 53' },
          { label: 'Client DNS checks', text: 'Some clients check the TXT record in public DNS before they continue (lego, cert-manager, acme.sh). They need a resolver that sees the public zone, or a wait time: --dns.propagation-wait (lego), --dnssleep (acme.sh), --dns01-recursive-nameservers (cert-manager)' },
        ]
      },
      {
        title: 'EAB Credentials (Server-side)',
        icon: Key,
        content: 'When UCM acts as an ACME server, External Account Binding (RFC 8555 §7.3.4) lets you require pre-issued credentials before clients can register accounts:',
        items: [
          { label: 'Issue', text: 'Generate a new kid + HMAC key pair from ACME → EAB Credentials' },
          { label: 'Distribute', text: 'Hand the kid + HMAC to the client (cert-manager, certbot, acme.sh)' },
          { label: 'Bind', text: 'The client signs a JWS over the MAC key on newAccount to bind its ACME account' },
          { label: 'Revoke', text: 'Revoke a kid at any time, existing accounts continue to work, new bindings are refused. To rotate, create a new kid and revoke the old one' },
          { label: 'Audit', text: 'Issuance, rotation and revocation are audited under the operator who performed them' },
          { label: 'Domain restrictions', text: 'Limit a credential to the domains it may request: * (any), *.example.com (all sub-domains), or an explicit list, an empty list blocks issuance entirely. Enforced on new-order/new-authz, server and proxy; only meaningful when EAB is required' },
        ]
      },
      {
        title: 'Custom DNS Resolvers (DNS-01)',
        icon: Globe,
        items: [
          { label: 'Mode', text: 'ACME → Let\'s Encrypt → DNS-01 resolvers: Automatic (listed, authoritative, public, then system), System resolver only, or Listed resolvers only. The restricted modes never query public resolvers, for networks that block them' },
          { label: 'Split-horizon', text: 'Useful when your authoritative server is internal but the public view is cached elsewhere' },
          { label: 'Stale records', text: 'Avoids public-resolver caching during fast automated renewals' },
          { label: 'host:port entries', text: 'Comma-separated IPs with an optional port (127.0.0.1:5353, [2001:db8::53]:5300), each resolver keeping its own port: e.g. a loopback-only BIND or dnsmasq on an alternate port' },
        ]
      },
      {
        title: 'ACME on Internal / Private IPs',
        icon: ShieldCheck,
        content: 'HTTP-01 and TLS-ALPN-01 validation works out of the box for RFC1918, loopback, .lan / .local / .corp targets, UCM\'s primary deployment model.',
        items: [
          { label: 'Toggle', text: 'ACME → Local ACME → Allow private and internal addresses (default: on)' },
          { label: 'Toggle', text: 'Let\'s Encrypt tab → Allow loopback ACME CA, opt in for a colocated CA on 127.0.0.1 (default: off)' },
          { label: 'Always blocked', text: 'Cloud metadata IPs (169.254.169.254, fd00:ec2::254, etc.) are blocked unconditionally' },
        ]
      },
      {
        title: 'Multi-CA Resolution',
        icon: TreeStructure,
        content: 'When an ACME client requests a certificate, UCM resolves the signing CA in this order:',
        items: [
          '1. Local Domain mapping: exact domain match, then parent domain',
          '2. DNS Domain mapping: checks the issuing CA configured for the DNS provider',
          '3. Global default: the CA set in ACME server configuration',
          '4. First available CA with a private key',
        ]
      },
      {
        title: 'IP Address Certificates (RFC 8738)',
        icon: Globe,
        content: 'The local ACME server can issue certificates for IPv4 and IPv6 addresses, not just DNS names. Use the "ip" identifier type in the order.',
        items: [
          { label: 'Identifier', text: 'Order with { "type": "ip", "value": "192.0.2.10" } (IPv4) or an IPv6 literal like 2001:db8::1' },
          { label: 'Challenges', text: 'Only HTTP-01 and TLS-ALPN-01 are offered, DNS-01 is forbidden for IP identifiers per RFC 8738' },
          { label: 'TLS-ALPN-01 SNI', text: 'Validation uses the reverse-DNS form (in-addr.arpa / ip6.arpa) as the SNI hostname' },
          { label: 'Issued SAN', text: 'The certificate carries an iPAddress SAN; mixed DNS + IP orders are supported' },
          { label: 'Internal IPs', text: 'RFC1918 and loopback addresses validate out of the box, UCM\'s primary deployment model' },
        ]
      },
      {
        title: 'Persistent DNS Validation (dns-persist-01)',
        icon: ArrowClockwise,
        content: 'The local ACME server can validate domains through a persistent TXT record bound to the ACME account (draft-ietf-acme-dns-persist): clients renew without writing DNS records. Opt-in, off by default.',
        items: [
          { label: 'Record', text: 'Create _validation-persist.<domain> TXT "<issuer-domain>; accounturi=<account URL>", the challenge object advertises both expected values' },
          { label: 'Enable', text: 'ACME → Local ACME → Persistent DNS Validation (dns-persist-01)' },
          { label: 'Wildcard / subdomains', text: 'Append policy=wildcard to also authorize wildcard certificates and subdomains of the validated name' },
          { label: 'persistUntil', text: 'Optional persistUntil=<unix timestamp> stops new validations after that time' },
          { label: 'Security', text: 'The record grants the account key issuance capability for as long as it exists, delete the TXT record to revoke' },
        ]
      },
    ],
    tips: [
      'ACME directory URL: https://your-server:port/acme/directory',
      'Use a custom directory URL to connect to ZeroSSL, HARICA, or any RFC 8555 CA',
      'EAB credentials (Key ID + HMAC Key) are provided by your CA upon registration',
      'When UCM is the ACME server, issue your own EAB credentials in ACME → EAB Credentials',
      'For Kubernetes/cert-manager: see the reference manifests under examples/kubernetes/cert-manager/',
      'ECDSA P-256 keys offer equivalent security to RSA-2048 with much smaller size',
      'Use Local Domains to assign different CAs to different internal domains',
      'Any CA with a private key can be selected as the issuing CA',
      'Wildcard domains (*.example.com) require DNS-01 validation',
      'Each CA account keeps its own upstream registration: switching the proxy to another account uses that account\'s',
      'Use the proxy URL with certbot: certbot certonly --server https://your-server:port/acme/proxy/directory',
    ],
    warnings: [
      'Domain validation is required: your server must be reachable or DNS configured',
      'Changing account key type requires re-registering your ACME account',
    ],
    related: ['Certificates', 'CAs', 'DNS Providers']
  },

  // ===== TRUST STORE =====
  truststore: {
    title: 'Trust Store',
    subtitle: 'Manage trusted certificates',
    overview: 'Keep trusted root and intermediate CA certificates. A certificate\'s chain view and its exports complete the chain with a trust store certificate whose subject matches the issuer name. The store can be filled from the operating system trust store or from the CAs UCM manages.',
    sections: [
      {
        title: 'Certificate Types',
        icon: ShieldCheck,
        definitions: [
          { term: 'Root CA', description: 'Self-signed top-level trust anchor' },
          { term: 'Intermediate', description: 'CA certificate signed by a root or another intermediate' },
          { term: 'System', description: 'Imported from the operating system trust store' },
          { term: 'Code Signing', description: 'Certificate used for code signature verification' },
          { term: 'Email', description: 'Certificate used for S/MIME' },
          { term: 'Custom', description: 'Manually categorized trusted certificate' },
        ]
      },
      {
        title: 'Actions',
        icon: CloudArrowUp,
        items: [
          { label: 'Add', text: 'Add certificates of the CAs UCM manages. An external certificate is added through the API (POST /api/v2/truststore with PEM, or /api/v2/truststore/import with a PEM or DER file)' },
          { label: 'Sync from System', text: 'Import OS trusted CAs into UCM, up to the chosen count (500 by default, 1000 at most)' },
          { label: 'Export', text: 'Download trusted certificates individually' },
          { label: 'Delete selected', text: 'Select several certificates and remove them together, for instance the system CAs filtered as expired; only the rows the current filters show are removed' },
        ]
      },
    ],
    tips: [
      'Use "Sync from System" to quickly populate the trust store with OS-level CAs',
      'Filter by purpose to focus on specific certificate categories',
    ],
    related: ['CAs', 'Certificates']
  },

  // ===== USERS & GROUPS =====
  usersGroups: {
    title: 'Users & Groups',
    subtitle: 'Identity and access management',
    overview: 'Manage user accounts and group memberships. Assign roles to control access to UCM features. Groups allow bulk permission management for teams.',
    sections: [
      {
        title: 'Users',
        icon: Users,
        items: [
          { label: 'Create User', text: 'Add a new user with username, email, and initial password' },
          { label: 'Roles', text: 'Assign system or custom roles to control permissions' },
          { label: 'Status', text: 'Enable or disable user accounts' },
          { label: 'Password Reset', text: 'Reset a user\'s password (admin action). The user\'s open sessions are signed out, as they are by a 2FA reset' },
          { label: 'Delete User', text: 'Deleting a user revokes the certificates they enrolled for mTLS (cessationOfOperation), then deletes them. A certificate the CA cannot revoke does not block the deletion: it stays valid, is named in the warning and the audit log, and must be revoked under Certificates. A failure after some revocations keeps the user and names the certificates already revoked. Removing a user or one of its mTLS certificates warns when the ACME CA that issued a certificate was not told of its revocation' },
          { label: 'API Keys', text: 'In a user\'s details, list their API keys and revoke a leaked or unused one: it stops working at once, and a revoked or expired key can then be deleted. Owners create their keys on their Account page' },
          { label: 'Source', text: 'Shows where each user comes from: Local (managed in UCM) or LDAP / OAuth2 / SAML (provisioned by an SSO provider). The badge displays the originating provider name.' },
        ]
      },
      {
        title: 'Groups',
        icon: UsersFour,
        items: [
          { label: 'Create Group', text: 'Define a group and assign members' },
          { label: 'Group Permissions', text: 'A group grants a set of permissions, every member receives them on top of their own role' },
          { label: 'Member Management', text: 'Add or remove users from groups' },
        ]
      },
    ],
    tips: [
      'Use groups to manage permissions for teams rather than individual users',
      'Disabled users cannot log in but their data is preserved',
    ],
    warnings: [
      'Deleting a user is permanent: consider disabling instead',
    ],
    related: ['RBAC', 'Audit Logs', 'Settings']
  },

  // ===== RBAC =====
  rbac: {
    title: 'Role-Based Access Control',
    subtitle: 'Fine-grained permission management',
    overview: 'Define custom roles with granular permissions. System roles (Admin, Operator, Auditor, Viewer) are built-in. Custom roles let you control exactly which operations each user can perform.',
    sections: [
      {
        title: 'System Roles',
        icon: ShieldCheck,
        definitions: [
          { term: 'Admin', description: 'Full access to all features and settings' },
          { term: 'Operator', description: 'Can manage certificates, CAs, CSRs, ACME, SSH and the settings an admin does not reserve; templates and groups read-only, no access to users or RBAC' },
          { term: 'Auditor', description: 'Read-only access to all operational data for compliance and audit' },
          { term: 'Viewer', description: 'Basic read-only access to certificates, CAs, and templates' },
        ]
      },
      {
        title: 'Custom Roles',
        icon: Key,
        items: [
          { label: 'Create Role', text: 'Define a new role with a name and description' },
          { label: 'Permission Matrix', text: 'Check/uncheck permissions by category (CAs, Certs, Private Keys, etc.)' },
          { label: 'Coverage', text: 'A bar and an n/N count of the permissions granted to the role' },
          { label: 'User Count', text: 'See how many users are assigned to each role' },
          { label: 'System role permissions', text: 'A system role shows the permissions UCM applies to it; Admin shows every permission of the matrix' },
          { label: 'SSH CA permissions (v2.248)', text: 'read:ssh_cas, write:ssh_cas and delete:ssh_cas govern SSH CAs, so write:ssh no longer creates or edits them. Roles, groups and API keys holding an SSH permission received the matching one on upgrade' },
        ]
      },
    ],
    tips: [
      'Follow the principle of least privilege: grant only necessary permissions',
      'System roles cannot be modified or deleted',
      'Toggle entire categories on/off for quick role setup',
    ],
    related: ['Users & Groups', 'Audit Logs']
  },

  // ===== AUDIT LOGS =====
  systemLogs: {
    title: 'System Logs',
    subtitle: 'The server\'s own application log',
    overview: 'Reads back what UCM itself wrote, without shell access to the host. This is the log that explains a protocol failure the request never reached a record for: a SCEP enrolment refused during validation is rejected before a request row exists, so it appears here and nowhere else.',
    sections: [
      {
        title: 'Sources',
        icon: Stack,
        items: [
          { label: 'Application', text: 'UCM\'s own log. Only this source carries components' },
          { label: 'Access', text: 'Gunicorn access log: HTTP requests and status codes, native installs only' },
          { label: 'Errors', text: 'Gunicorn error log: worker startup and unhandled tracebacks, native installs only' },
          { label: 'Journal', text: 'The systemd unit journal, where the service user can read it' },
        ]
      },
      {
        title: 'Filters',
        icon: ListChecks,
        items: [
          { label: 'Source', text: 'Which log to read. Only sources this deployment actually has are offered' },
          { label: 'Component', text: 'One subsystem of the application log, or all of them. Every subsystem is listed, not only those on screen' },
          { label: 'Log level', text: 'A floor, not an exact match: WARNING shows warnings, errors and critical' },
          { label: 'Search', text: 'Case-insensitive, across the message and the component name. Literal text, not a pattern' },
          { label: 'Exclude', text: 'Drops the lines that match: the quickest way to silence a heartbeat' },
          { label: 'Date', text: 'A From/To window, applied on the server' },
          { label: 'Lines', text: 'How many matching lines to return, newest first' },
        ]
      },
      {
        title: 'Live logs',
        icon: ArrowClockwise,
        items: [
          'Polls every five seconds; the newest line is the first row',
          'Clears the date window, which asks the opposite question',
        ]
      },
    ],
    tips: [
      'Timestamps are written in the server\'s local time with no offset in the line; the zone is named at the foot of the page',
      'A line that matches no known format is still shown, with no level, rather than hidden',
      'A traceback is one entry, not one line each: the message cell wraps to show it whole',
      'Secrets are redacted server-side before anything leaves the process',
    ],
    warnings: [
      'A component that has logged nothing recently is still listed, so picking one can come back empty',
      'Reading this log is admin-only, and is deliberately not audited: the audit trail echoes to this same log, so recording every read would bury the lines it exists to surface',
    ],
    related: ['auditLogs', 'settings'],
  },

  auditLogs: {
    title: 'Audit Logs',
    subtitle: 'Activity tracking and compliance',
    overview: 'Complete audit trail of all operations performed in UCM. Track who did what, when, and from where. Supports filtering, search, export, and integrity verification.',
    sections: [
      {
        title: 'Filters',
        icon: ListChecks,
        items: [
          { label: 'Action Type', text: 'Filter by operation type (create, update, delete, login, etc.)' },
          { label: 'User', text: 'Filter by the user who performed the action' },
          { label: 'Status', text: 'Show only successful or failed operations' },
          { label: 'Date Range', text: 'Set from/to dates to narrow the time window' },
          { label: 'Search', text: 'Free-text search across all log entries' },
        ]
      },
      {
        title: 'Actions',
        icon: Database,
        items: [
          { label: 'Export', text: 'Download logs in JSON or CSV format' },
          { label: 'Cleanup', text: 'Purge old logs with configurable retention (days)' },
          { label: 'Verify Integrity', text: 'Check log chain integrity to detect tampering' },
        ]
      },
    ],
    tips: [
      'Export logs regularly for compliance and archival purposes',
      'Failed login attempts are logged with source IP for security monitoring',
      'Log entries include User Agent for identifying client applications',
    ],
    warnings: [
      'Log cleanup is irreversible: exported data cannot be re-imported',
    ],
    related: ['Settings', 'Users & Groups', 'RBAC']
  },

  // ===== SETTINGS =====
  settings: {
    title: 'Settings',
    subtitle: 'System configuration',
    overview: 'Configure all aspects of the UCM system. Settings are organized by category: general, appearance, email, security, SSO, backup, audit, database, HTTPS, updates, and webhooks.',
    sections: [
      {
        title: "Prometheus metrics",
        content: "Opt-in /metrics endpoint exposing certificate, CA, scheduler, webhook and ACME counters in Prometheus format.",
        items: [
          { label: "Enable", text: "Set a metrics token in Settings › General; without a token the endpoint returns 404 (disabled)" },
          { label: "Auth", text: "Scrape with Authorization: Bearer <token>" },
          { label: "Counters", text: "ucm_certificates, ucm_certificate_authorities, ucm_scheduler_task_*, ucm_webhook_deliveries, ucm_acme_*" },
        ]
      },
      {
        title: "Public ACME vhost",
        content: "Settings › General: public hostname and port for ACME directory URLs behind a reverse proxy.",
        items: [
          { label: "Admin", text: "admin.ucm.example.com, GUI and API (mTLS per policy)" },
          { label: "ACME", text: "acme.ucm.example.com, /acme/* and /acme/proxy/* (no client mTLS)" },
          { label: "Wildcard TLS", text: "Use a concrete hostname here (e.g. acme.ucm.example.com). A *.ucm.example.com certificate SAN covers TLS for admin and ACME vhosts, do not enter *.ucm.example.com as the vhost" },
          { label: "Before saving", text: "Have DNS and TLS working for the ACME vhost first, clients that re-read the directory switch URLs immediately and renewals fail if the vhost is unreachable" },
          { label: "TLS certificate ID", text: "Metadata for the certificate deployed on the ACME vhost (e.g. wildcard)" },
        ]
      },
      {
        title: "Webhook delivery history",
        content: "Each webhook endpoint keeps a delivery log with status, attempts and a manual retry.",
        items: [
          { label: "Statuses", text: "pending / delivered / failed, with the last HTTP code and error" },
          { label: "Retry", text: "Manually re-queue a failed or already-delivered event" },
          { label: "Async", text: "Deliveries run from a durable queue with exponential backoff (up to 5 attempts)" },
        ]
      },
      {
        title: "Scheduler view",
        content: "Settings › Scheduler lists the background tasks with their status and last run.",
        items: [
          { label: "Tasks", text: "Expiry checks, CRL refresh, webhook delivery, scheduled backups, auto-renewal, etc." },
          { label: "Run now", text: "Trigger any task on demand" },
          { label: "Visibility", text: "Last run, last duration and failure count per task" },
          { label: 'Scheduler process (v2.251)', text: 'The tasks run in a scheduler process of their own, started with the service and restarted within seconds after a crash or a reload, so a long task delays neither requests nor workers. It takes about 150 MB of memory' },
          { label: 'Stale status (v2.251)', text: 'When the scheduler process has not reported for a while, the tab warns that the status shown may be out of date' },
          { label: 'Long tasks (v2.251)', text: 'Run now waits up to 30 seconds for the result. A task still running then is reported as started and still running, and its result shows on a later refresh' },
        ]
      },
      {
        title: "Scheduled backups",
        content: "Automatic, encrypted database backups on a configurable cadence with retention.",
        items: [
          { label: "Cadence", text: "Daily / weekly / monthly" },
          { label: "Retention", text: "Backups older than the set number of days (30 by default) are pruned" },
          { label: "Encryption", text: "Backups are encrypted with the configured backup password" },
          { label: "Key derivation", text: "Automatic (Argon2id when available, PBKDF2 in FIPS mode), PBKDF2-HMAC-SHA256 or Argon2id. Archives written with Argon2id cannot be restored on an instance in FIPS mode" },
        ]
      },
      {
        title: 'Restore (v2.251)',
        items: [
          { label: 'Replace or merge', text: 'Restore from Backup replaces the data here with the archive\'s and removes what the archive does not carry; the audit entry lists what was removed. The API also accepts mode=merge, which adds the archive to the data here' },
          { label: 'Shared lock', text: 'Backups and restores share one lock: a restore is refused (409) while a backup runs, and a manual backup waits for a running restore' },
          { label: 'Upload limit', text: 'An archive created since 3.0 is restored in chunks and has no size limit unless BACKUP_MAX_ARCHIVE_MB sets one. An older archive is accepted up to BACKUP_MAX_UPLOAD_MB (512 MB by default). Both are set in the server environment and a refusal names its setting. A reverse proxy in front of UCM keeps its own body limit' },
          { label: 'What an archive carries', text: 'Archives include ACME client orders, approval requests and key recovery requests. Restoring an archive written before this version leaves those rows here as they are' },
          { label: 'Same names', text: 'A DNS provider, ACME CA account or webhook whose name another row holds here is restored as "name (2)", and the restore result returned by the API lists it' },
          { label: 'Settings that name a row', text: 'The SCEP and ACME issuing CAs, OCSP responders and similar settings follow the archived rows. From an older archive restored on another installation, they are emptied and must be chosen again' },
        ]
      },
      {
        title: 'Automatic updates (v2.215)',
        content: 'Settings › Updates: a daily background check for new versions, and an optional unattended install.',
        items: [
          { label: 'Channel', text: 'Stable follows final releases only; Release candidates additionally accepts rcN versions only, alpha/beta never qualify' },
          { label: 'Notification', text: 'A newly available version fires the system.update_available webhook/email event, once per version' },
          { label: 'Auto-install', text: 'Off by default. When enabled, UCM downloads, verifies and installs the update at the chosen hour, then restarts, DEB/RPM installs only' },
          { label: 'Checksum', text: "An unattended install requires the release's published SHA256 to verify; a manual install also verifies whenever a checksum is published" },
          { label: 'Docker', text: 'Containers cannot update themselves, the check and notification still work; pull the new image to update' },
          { label: 'HA mode', text: 'In HA mode on DEB/RPM, Install Update and the auto-install update the nodes one at a time; the next node starts once the previous one is back on the new version. The screen shows the nodes done, the node in progress and the node where it stopped with the reason; Resume continues from it. Docker and Kubernetes leave it to the orchestrator' },
          { label: 'Post-update popup', text: 'Optional (v2.217): shows the release notes once after an update is installed, per user. Off by default' },
        ]
      },
      {
        title: 'HSTS (Strict Transport Security)',
        icon: Globe,
        content: 'Operator-configurable HSTS policy so instances serving self-signed certificates during setup can opt out entirely.',
        items: [
          { label: 'Default', text: 'HSTS on, includeSubDomains, max-age 1 year (backward compatible)' },
          { label: 'Disable', text: 'Turn off for instances with self-signed certs during initial setup (avoids browser lock-out)' },
          { label: 'Env override', text: 'UCM_HSTS_ENABLED, UCM_HSTS_INCLUDE_SUBDOMAINS, UCM_HSTS_MAX_AGE in /etc/ucm/ucm.env win over the DB setting' },
          { label: 'Subdomains', text: 'Drop includeSubDomains when subdomains host separate services with their own certs' },
        ]
      },
      {
        title: 'Categories',
        icon: Gear,
        items: [
          { label: 'General', text: 'Syslog hostname (sent as HOSTNAME in forwarded syslog messages), base URLs, and system-wide defaults' },
          { label: 'Appearance', text: 'Theme selection (light/dark/system), accent color, desktop mode' },
          { label: 'Email (SMTP)', text: 'SMTP server, credentials, email template editor, and expiry alert notifications. Supports OAuth2 (XOAUTH2) for Gmail, Outlook.com & Microsoft 365 in addition to legacy password auth' },
          { label: 'Security', text: 'Password policy, session duration, admin access allowlist, mTLS, private key encryption; the inactivity timeout and account lockout are under General' },
          { label: 'SSO', text: 'SAML 2.0, OAuth2/OIDC, and LDAP single sign-on integration' },
          { label: 'Backup', text: 'Manual and scheduled database backups' },
          { label: 'Audit', text: 'Log retention, syslog forwarding, integrity verification' },
          { label: 'Database', text: 'Active backend (SQLite or native PostgreSQL), size, table count, bidirectional migration UI with safety checks' },
          { label: 'PostgreSQL schema (v2.251)', text: 'A PostgreSQL URL whose search_path names a schema other than public is supported: the integrity check counts the tables of that schema, and a migration to it realigns its sequences' },
          { label: 'HTTPS', text: 'TLS certificate for the UCM web interface. The applied certificate is remembered and re-applied when it is renewed (v2.217); the bound certificate is shown with an unbind button to stop following renewals (v2.218). A protocol renewal whose key UCM does not hold leaves HTTPS on the previous certificate and says so, until the key of the renewed certificate is imported' },
          { label: 'Updates', text: 'Check for new versions, view changelog, scheduled daily check with opt-in unattended install (DEB/RPM)' },
          { label: 'Webhooks', text: 'HTTP webhooks for certificate events (issue, revoke, expire): internal LAN URLs allowed; cloud-metadata IPs blocked. Optional outbound auth: Bearer, Basic, API key, or custom header' },
          { label: 'Unique webhook names (v2.251)', text: 'A webhook name already in use is refused (409), on creation and on rename. The upgrade renamed earlier duplicates "name (2)", "name (3)", oldest first' },
          { label: 'Deployment', text: 'Deploy targets provide reusable SSH/SFTP connections, or an HTTP API request (v2.252); certificate and CRL deployments define their own paths and optional reload commands (admin-only, v2.215)' },
          { label: 'Active Directory', text: "UCM's own AD/LDAP connection for certificate-related lookups (Kerberos principal resolution, AD-derived subjects)" },
          { label: 'Windows Autoenrollment', text: 'MS-XCEP/MS-WSTEP native Windows enrollment: policy discovery, certificate issuance, and Kerberos/SPNEGO binding' },
          { label: 'About', text: 'System Information, Links & Resources and the Support UCM link to Ko-fi (administrators also see a dismissible Ko-fi card once per UCM version). With admin:system, Check FIPS readiness lists what FIPS mode would refuse on this instance, with a remedy for each, and changes nothing' },
          { label: 'Compliance profiles', text: 'In About, with admin:system: Check profile lists what ANSSI, BSI or EU ACM (rules aligned with a reference text) would refuse or advise against on this instance, changes nothing. With admin:settings, Default profile for new CAs sets the profile a CA receives when none is chosen; existing CAs are not changed' },
        ]
      },
      {
        title: 'Deploy hooks (v2.215)',
        icon: CloudArrowUp,
        content: 'Settings › Deployment (admin-only): reusable SSH/SFTP connections, or HTTP API requests, for certificate and CRL deployments. Paths and optional reload commands are configured on each SSH deployment.',
        items: [
          { label: 'Target', text: 'Host, port, SSH user. UCM generates an ed25519 key (install the shown public key on the target) or accepts an imported private key, stored encrypted' },
          { label: 'HTTP API target (v2.252)', text: 'URL, method (POST, PUT, PATCH), request headers stored encrypted and never shown again, and a body template with {{cert_pem}}, {{fullchain_pem}}, {{cn}}, {{serial}}... plus |json, |jsonstr, |b64 and |urlencode filters. A JSON body is checked at save time. The private key ({{key_pem}}) leaves only with the target\'s explicit opt-in and an https URL; the TLS certificate is always verified, against a pasted trust anchor if the appliance is self-signed. Redirects are refused, cloud-metadata and loopback addresses blocked. Certificates only: CRLs stay on SSH targets' },
          { label: 'Host key', text: 'Pinned on the first successful connection (trust-on-first-use); any later change fails closed. Changing the host re-pins' },
          { label: 'Reload command', text: 'An optional command configured per certificate or CRL binding and run after a successful push (e.g. systemctl reload nginx): exit 0 = success, no templating' },
          { label: 'Bindings', text: 'Certificates are attached from the certificate detail view; CRLs are attached under CRL & OCSP. Each binding owns its paths, file options and reload command' },
          { label: 'Delivery', text: 'Pushes run asynchronously through a durable queue with retries and backoff; per-delivery status, manual deploy-now and retry, full audit trail' },
          { label: 'Least privilege', text: 'Use a dedicated SSH account on each target: write access to the certificate paths and permission to reload the service, nothing more' },
        ]
      },
      {
        title: 'SMTP OAuth2 (XOAUTH2)',
        icon: Lock,
        content: 'Modern OAuth2 authentication for outbound mail, replacing legacy app-password flows that Microsoft and Google are deprecating:',
        items: [
          { label: 'Gmail', text: 'Configure a Google Cloud OAuth2 client with the https://mail.google.com/ scope' },
          { label: 'Microsoft 365 / Outlook.com', text: 'Register an Azure AD app with SMTP.Send delegated permission' },
          { label: 'Refresh tokens', text: 'UCM stores the refresh token and renews access tokens automatically before each send' },
          { label: 'Fallback', text: 'Password auth is still supported when OAuth2 is not configured' },
        ]
      },
      {
        title: 'Active Directory Connector',
        icon: UsersFour,
        content: "UCM's own LDAP connection to Active Directory, independent of any LDAP provider configured under SSO, that one is for logging into UCM, this one is for certificate-related AD lookups.",
        items: [
          { label: 'Purpose', text: 'Resolves a Kerberos machine or user principal to its AD object so UCM can derive a certificate subject/SAN, the same way a real Windows CA would' },
          { label: 'Connectors', text: 'One per directory (forest or domain), listed with its realm, the domain SID that was read and its health. A connector that Windows enrollment profiles use cannot be deleted, and the refusal lists them' },
          { label: 'Fields', text: 'Name, domain controllers (one per row, each by its own hostname, tried in order with failover), port, LDAPS with optional CA verification, Base DN, Bind DN and password (both required while the connector is enabled)' },
          { label: 'Disabled connector', text: 'A disabled connector looks nothing up, but its base DN still names the realm of the default profile as a last resort, when no enabled connector, SPN or keytab does' },
          { label: 'Test Connection', text: 'Verify connectivity and credentials before saving; the test also reads the domain SID' },
          { label: 'Health check', text: 'Each domain controller is probed with a real bind at the Health Check Interval; an unreachable one is skipped at enrollment time until it recovers. The verdict shows on the settings row and against each DC' },
        ]
      },
      {
        title: 'Windows Autoenrollment (XCEP/WSTEP)',
        icon: WindowsLogo,
        content: 'Native Windows certificate enrollment via MS-XCEP policy discovery and MS-WSTEP issuance, supports MMC/certreq manual enrollment and unattended GPO autoenrollment.',
        items: [
          { label: 'Profiles', text: 'One profile per Active Directory realm, routed by the realm of the client\'s Kerberos principal: its own issuing and policy CA, template subset, AD connector and keytab; the UsernamePassword accounts belong to the default profile. The list is paginated and filtered by the server (name or realm, CA, state: complete, keytab missing, connector failing, disabled)' },
          { label: 'Realm', text: 'In capital letters exactly as the KDC writes it (CORP.EXAMPLE): a KDC compares realms character by character. The default profile without a realm refuses Kerberos until one is set. A disabled profile refuses the machines of its realm; its keys stay in the served keytab so the refusal is audited by realm' },
          { label: 'XCEP', text: 'Lets Windows clients discover available certificate templates before enrolling' },
          { label: 'WSTEP', text: 'Handles certificate request and renewal once policy has been discovered' },
          { label: 'Kerberos/SPNEGO', text: 'Binds the Kerberos-authenticated endpoints used for silent GPO autoenrollment (an SPN shared by every profile, and a keytab per profile from the domain controller of its realm; the form lists the entries of a chosen file by realm and flags a realm that is not the profile\'s)' },
          { label: 'Setup checklist', text: 'The form of each profile lists what that profile still lacks: realm, issuing CA, keytab, a reachable connector, a template that allows autoenrollment, the profile enabled' },
          { label: 'Policy URLs', text: 'The same for every profile: routing is by realm, not by URL' },
          { label: 'AD-derived subjects', text: 'Templates can opt into deriving their subject/SAN from Active Directory (via the AD Connector) for unattended enrollment' },
          { label: 'ML-DSA templates (v2.248)', text: 'Announced by their key algorithm OID with the Microsoft Software Key Storage Provider, not yet tested with a real Windows client, and hidden in FIPS mode. Certificate-based renewal cannot use an ML-DSA certificate (XML-DSig has no ML-DSA signature): enroll a new one' },
          { label: 'ECDSA templates (v2.251)', text: 'Announced in policy schema 3 with their curve (ECDSA_P256, ECDSA_P384, ECDSA_P521) as a signature key and a request hash, the stronger of the template digest and the one matching the curve. RSA templates outside FIPS mode stay schema 2, where Windows signs its CMC request with SHA-1, which UCM accepts (a plain SHA-1 PKCS#10 is still refused)' },
          { label: 'Template named in the request (v2.252)', text: 'Each policy announces its template extension (szOID_CERTIFICATE_TEMPLATE), which Windows copies into its request, so a certificate is issued under the template chosen on the client even when another one has the same EKUs. A request naming no template is matched by its EKUs. A template whose EKUs are all never issued to an enrollee, such as OCSP Signing, is not announced, and a request for it is refused' },
          { label: 'Template and key (v2.251)', text: 'The request key must fit the template it is issued under: the same curve or ML-DSA set, or an RSA key at least as long, so a P-384 request is no longer issued under a P-256 template sharing its EKU. The request envelope Windows signs with an ECDSA key is accepted' },
          { label: 'Renewal from Windows (v2.248)', text: 'certreq ... Renew authenticates with the certificate being renewed as TLS client certificate: it needs mTLS enabled with the WSTEP CA, or one of its ancestors, trusted. Since 3.0 only a certificate issued through Windows enrollment renews this way: one signed in the interface is refused and must be reissued through Windows enrollment. A renewal keeps the template and EKUs of the certificate it renews, and its SubjectAltName when the CSR carries none (v2.252)' },
          { label: 'Renewal by certificate (3.0)', text: 'Served by the profile the certificate records (a 2.x WSTEP certificate: the default profile), under its issuing CA, and refused when that profile was deleted or is disabled; each refusal is audited with the profile and the reason. Only the SID is checked again, by the profile\'s connector: a computer removed from the group keeps renewing until its certificate is revoked. Over TLS it needs the profile\'s issuing CA to be the mTLS CA or under it; other profiles renew over Kerberos, where the realm\'s profile serves and the new certificate records it' },
          { label: 'Certificate type', text: 'Without Server Auth, a template with Email Protection or EFS issues an S/MIME certificate, one with Client Auth or Smartcard Logon a client one: a user request CN=jdoe without SAN gets no DNS name from its CN. A request without Key Usage gets the Key Usage the template configures, else the template kind\'s: Digital Signature, Key Encipherment and Non Repudiation for S/MIME or EFS, Digital Signature and Key Encipherment for Smartcard Logon, Digital Signature alone for Client Auth. Any other template, or none, issues a server one' },
          { label: 'Kerberos in Docker (v2.251)', text: 'The Docker images ship the Kerberos backend of pyspnego, so the Kerberos binding works in a container as it does in the DEB and RPM installs' },
        ]
      },
      {
        title: 'Auto-renewal',
        icon: ArrowClockwise,
        items: [
          { label: 'Sources', text: 'The scheduler renews certificates whose private key the server holds: by default those issued from the form or a signed request ("manual"), and SCEP, ACME and EST enrolments with a server-generated key. Devices holding their own key renew through their protocol' },
          { label: 'Awaiting approval', text: 'A certificate whose renewal is queued for approval is left to that decision, as long as it can come before the certificate expires' },
          { label: 'Renewed meanwhile', text: 'A certificate an operator renewed during the batch is not renewed a second time; one deleted during the batch is skipped' },
          { label: 'Short-lived certificates', text: 'Renewal never starts before the last third of a certificate\'s lifetime: a 27-day certificate is renewed with 9 days left, not from the day it is issued' },
          { label: 'Run now', text: 'Runs a renewal pass at once and reports the expiring certificates it left alone, counted by reason: not yet in the last third of their lifetime, private key not held by the server, source not selected' },
          { label: 'Signature digest (v2.251)', text: 'A renewal keeps the original certificate\'s digest while it is at least the one matching the CA key and the policies allow it, otherwise it follows the issuance rule: under a P-384 or P-521 CA, a SHA-256 original is renewed with SHA-384 or SHA-512' },
        ]
      },
    ],
    tips: [
      'Use the status bar at the bottom to check that the service answers',
      'Test SMTP settings before relying on email notifications',
      'Customize the email template with your branding using the built-in HTML/Text editor',
      'Schedule automatic backups for production environments',
      'Switching SQLite ↔ PostgreSQL is bidirectional: the UI runs safety checks (driver loaded, target reachable, target empty) before migrating',
    ],
    warnings: [
      'Changing the HTTPS certificate requires a service restart',
      'Modifying security settings may lock out users: verify access before saving',
    ],
    related: ['Users & Groups', 'Audit Logs', 'Account']
  },

  // ===== ACCOUNT =====
  account: {
    title: 'My Account',
    subtitle: 'Personal settings and security',
    overview: 'Manage your profile, security settings, and API keys. Enable two-factor authentication and register security keys for enhanced account protection.',
    sections: [
      {
        title: 'Profile',
        icon: Users,
        items: [
          { label: 'Full Name', text: 'Your display name shown across the application' },
          { label: 'Email', text: 'Used for notifications and account recovery' },
          { label: 'Account Info', text: 'Creation date, last login, total login count' },
        ]
      },
      {
        title: 'Security',
        icon: Lock,
        items: [
          { label: 'Password', text: 'Change your current password. Your other sessions are signed out; this one stays' },
          { label: '2FA (TOTP)', text: 'Enable time-based one-time passwords via authenticator app. Enabling it again while it is on is refused: disable it first. Each code works once: after using one, wait for the next to confirm another action' },
          { label: 'Security Keys', text: 'Register WebAuthn/FIDO2 keys (YubiKey, fingerprint, etc.)' },
          { label: 'mTLS', text: 'Manage client certificates for mutual TLS authentication' },
          { label: 'Forced password change (v2.245)', text: 'An account asked for a new password, such as the first administrator whose password UCM generated at first start, can do nothing else until it changes it, API and WebSocket included; the prompt offers Log out instead of Skip. That change removes the file holding the generated password. A password provided through INITIAL_ADMIN_PASSWORD or INITIAL_ADMIN_PASSWORD_FILE does not have to be changed, unless INITIAL_ADMIN_PASSWORD_FORCE_CHANGE is set (the Helm chart sets it for the password it generates)' },
        ]
      },
      {
        title: 'API Keys',
        icon: Key,
        items: [
          { label: 'Create Key', text: 'Generate a new API key, optionally expiring after a number of days' },
          { label: 'Permissions', text: 'A key carries the scope chosen at creation, never more than your own permissions. A key can create or regenerate only a key whose permissions it holds itself, expiring no later than itself. Regenerating keeps the key\'s lifetime; a revoked or expired key cannot be regenerated' },
          { label: 'Revoke', text: 'Immediately invalidate an API key' },
          { label: 'Deactivated users', text: 'API keys belonging to a deactivated user are rejected even if the key itself is still valid' },
          { label: 'Interactive session only', text: 'API keys, even Full Access ones, cannot change your profile, password, 2FA, security keys, mTLS certificates or sessions, nor reach your own account through the user administration actions: sign in interactively' },
        ]
      },
      {
        title: 'Preferences (synced server-side)',
        icon: Gear,
        content: 'Your language, theme family and theme mode are persisted in the database and follow you across browsers and devices:',
        items: [
          { label: 'Stored', text: 'In users.preferences (JSON). New endpoints GET/PUT /api/v2/account/preferences manage them' },
          { label: 'Auto-applied', text: '/api/v2/auth/verify returns your preferences and they\'re applied on every page load' },
          { label: 'Fresh browser', text: 'Logging in from a new device, or after clearing site data, restores your chosen language and theme, no fallback to browser locale' },
        ]
      },
    ],
    tips: [
      'Enable at least one second factor (TOTP or Security Key) for admin accounts',
      'API keys can expire after a set number of days for short-lived integrations',
      'API keys can also be created with no expiration for long-running automation',
      'Scan the QR code with any TOTP app: Google Authenticator, Authy, 1Password, etc.',
      'Filter selections on the main list pages (Certificates, CAs, Templates, Audit, Policies, Trust Store and others) are persisted across reloads; CSRs, Approvals, Key Recovery, Discovery and System Logs start unfiltered',
    ],
    related: ['Settings', 'Users & Groups']
  },

  // ===== IMPORT/EXPORT =====
  importExport: {
    title: 'Import & Export',
    subtitle: 'Data migration and backup',
    overview: 'Import certificates from external sources and export your PKI data. Smart Import auto-detects file types. The OPNsense integration imports the certificates and CAs of a firewall on demand.',
    sections: [
      {
        title: 'Import',
        icon: CloudArrowUp,
        items: [
          { label: 'Smart Import', text: 'Upload any certificate file, UCM auto-detects format (PEM, DER, P12, P7B)' },
          { label: 'OPNsense import', text: 'Connect to an OPNsense firewall and import its certificates and CAs, once per run (no ongoing sync)' },
        ]
      },
      {
        title: 'Export',
        icon: Database,
        items: [
          { label: 'Export Certificates', text: 'Bulk download certificates as PEM or PKCS#7 bundle' },
          { label: 'Export CAs', text: 'Bulk download CA certificates and chains' },
        ]
      },
      {
        title: 'OPNsense Integration',
        icon: Globe,
        items: [
          { label: 'Connection', text: 'Provide the OPNsense host and port, API key, and API secret' },
          { label: 'Test Connection', text: 'Verify connectivity before importing' },
          { label: 'Select Items', text: 'Choose which certificates and CAs to import' },
        ]
      },
    ],
    tips: [
      'Smart Import handles PEM bundles with multiple certificates in a single file',
      'Test the OPNsense connection before running a full import',
      'PKCS#12 files require the correct password to import private keys',
      'Post-quantum certificates (ML-DSA, SLH-DSA) and ML-DSA keys import as PEM or DER, and the certificates carry a Post-quantum badge; UCM cannot read an ML-DSA key from a PKCS#12 file yet',
    ],
    related: ['Certificates', 'CAs', 'Operations']
  },

  // ===== CERTIFICATE TOOLS =====
  certTools: {
    title: 'Certificate Tools',
    subtitle: 'Decode, convert, and verify certificates',
    overview: 'A suite of tools for working with certificates, CSRs, and keys. Decode certificates to inspect their contents, convert between formats, check remote SSL endpoints, and verify key matches.',
    sections: [
      {
        title: 'Available Tools',
        icon: Wrench,
        items: [
          { label: 'SSL Checker', text: 'Connect to a remote host and inspect the certificate it presents (the leaf only, not the chain)' },
          { label: 'CSR Decoder', text: 'Paste a CSR in PEM format to view its subject, SANs, and key info' },
          { label: 'Certificate Decoder', text: 'Paste a certificate in PEM format to inspect its subject, issuer, validity, key, SANs, key usages and fingerprints; CDP, AIA and policies are not shown' },
          { label: 'Key Matcher', text: 'Verify that a certificate, CSR, and private key belong together' },
          { label: 'Converter', text: 'Convert between PEM, DER, PKCS#12, and PKCS#7 formats' },
        ]
      },
      {
        title: 'Converter Details',
        icon: ArrowClockwise,
        items: [
          'PEM ↔ DER conversion',
          'PEM → PKCS#12 with password and full chain',
          'PKCS#12 → PEM extraction',
          'PEM → PKCS#7 (P7B) chain bundling',
        ]
      },
    ],
    tips: [
      'SSL Checker supports custom ports: use it to check any TLS service',
      'Key Matcher compares public keys, ML-DSA included: an ML-DSA private key must carry its seed, a key file holding only the expanded form is refused',
      'Converter preserves the full certificate chain when creating PKCS#12',
      'Decoders name a post-quantum key with its NIST security level, e.g. ML-DSA-65 (level 3), without a size in bits',
      'UCM cannot yet write an ML-DSA key into PKCS#12 or JKS: export it as PEM with the private key instead',
    ],
    related: ['Certificates', 'CSRs', 'Import/Export']
  },

  // ===== OPERATIONS =====
  operations: {
    title: 'Operations',
    subtitle: 'Import, export & bulk actions',
    overview: 'Centralized operations center. Import certificates from files or OPNsense, export bundles in PEM/P7B formats, and perform bulk actions across all resource types with inline search and filters.',
    sections: [
      {
        title: 'Sidebar Tabs',
        icon: Stack,
        items: [
          { label: 'Import', text: 'Smart Import with automatic format detection, plus OPNsense sync to pull certificates from firewalls' },
          { label: 'Export', text: 'Download certificate bundles per resource type in PEM or P7B format via action cards' },
          { label: 'Bulk Actions', text: 'Select a resource type and perform batch operations on multiple items' },
        ]
      },
      {
        title: 'Bulk Actions',
        icon: ListChecks,
        items: [
          { label: 'Certificates', text: 'Revoke, renew, delete, or export, filter by status and issuing CA' },
          { label: 'CAs', text: 'Delete or export certificate authorities' },
          { label: 'CSRs', text: 'Sign with a CA or delete pending requests' },
          { label: 'Templates', text: 'Delete certificate templates' },
          { label: 'Users', text: 'Delete user accounts' },
        ]
      },
    ],
    tips: [
      'Use the resource chips to quickly switch between resource types',
      'The inline search and filters (Status, CA) let you narrow down items without leaving the toolbar',
      'Switch between Table and Basket (transfer panel) view modes on desktop',
      'Revoke, renew, sign and delete ask for confirmation before they run; an export starts at once',
    ],
    warnings: [
      'Bulk delete is irreversible: always create a backup first',
      'Bulk revoke will publish updated CRLs for all affected CAs',
    ],
    related: ['Certificates', 'CAs', 'Import/Export']
  },

  // ===== HSM =====
  hsm: {
    title: 'Hardware Security Modules',
    subtitle: 'External key storage',
    overview: 'Integrate with Hardware Security Modules for secure private key storage. Support for PKCS#11, AWS CloudHSM, Azure Key Vault, Google Cloud KMS, and OpenBao/Vault Transit.',
    sections: [
      {
        title: 'Supported Providers',
        icon: HardDrive,
        definitions: [
          { term: 'PKCS#11', description: 'Industry standard HSM interface (Thales, Entrust, SoftHSM)' },
          { term: 'AWS CloudHSM', description: 'Amazon Web Services cloud-based HSM' },
          { term: 'Azure Key Vault', description: 'Microsoft Azure managed key storage' },
          { term: 'Google KMS', description: 'Google Cloud Key Management Service' },
          { term: 'OpenBao / Vault Transit', description: 'OpenBao or HashiCorp Vault Transit Secrets Engine for encryption-as-a-service key management' },
        ]
      },
      {
        title: 'Actions',
        icon: Key,
        items: [
          { label: 'Add Provider', text: 'Configure connection to an HSM (library path, credentials, slot)' },
          { label: 'Test Connection', text: 'Verify the HSM is reachable and credentials are valid; for a PKCS#11 module, also record what it reports (library, manufacturer, library and firmware versions), shown on the provider page' },
          { label: 'Generate Key', text: 'Create a new key pair directly on the HSM' },
          { label: 'Status', text: 'Monitor provider connection health' },
          { label: 'Certification', text: 'Declare the certification of the HSM: Common Criteria EAL 4+, EUCC high, FIPS 140-3 level 3, FIPS 140-2 level 3 or other. Left empty, it is not declared. The eu-acm compliance profile accepts only Common Criteria EAL 4+, EUCC high, and FIPS 140-3 level 3 (until 31 December 2030) for an HSM-backed CA' },
          { label: 'Name already held (v2.249)', text: 'Generating a key under a name OpenBao or Azure Key Vault already holds is refused (409): bring an existing key in with a key sync (POST /api/v2/hsm/providers/<id>/sync)' },
          { label: 'One generation at a time (v2.249)', text: 'Key generations take turns on each provider, and one still waiting after 60 seconds gets a 409. A key whose record could not be stored is removed from the HSM' },
          { label: 'PIN in backups (v2.249)', text: 'A backup holds the provider\'s PIN or token in clear inside the archive, protected by its password, so it restores on another installation. A value only another installation\'s key opens is dropped on restore, with a log entry asking to enter it again' },
          { label: 'SoftHSM in FIPS mode (v2.247)', text: 'FIPS mode refuses a new SoftHSM provider, SoftHSM not being a validated module; UCM_FIPS_ALLOW_SOFTHSM=1 allows one for tests' },
        ]
      },
      {
        title: 'HSM-backed CAs (v2.130+)',
        icon: ShieldCheck,
        content: 'Once a provider is configured, you can pin a CA\'s private key to that HSM at creation time:',
        items: [
          { label: 'Key Storage toggle', text: 'On the CA creation form, choose Local (encrypted in DB) or HSM. Pick the provider + key label' },
          { label: 'Signing path', text: 'Every issuance, CRL signing and OCSP signing for that CA uses the HSM, the key never leaves' },
          { label: 'Export restrictions', text: 'PKCS#12, JKS and key-only exports are disabled for HSM-backed CAs (only the public certificate / chain can be exported)' },
          { label: 'CRL & OCSP', text: 'Both work transparently with HSM-backed CAs (signed via HSM)' },
          { label: 'Migration', text: 'Existing local CAs cannot be moved to an HSM after creation, choose at creation time' },
        ]
      },
      {
        title: 'ML-DSA keys',
        icon: Key,
        content: 'ML-DSA-44, ML-DSA-65 and ML-DSA-87 (FIPS 204) keys are offered only on providers that sign with them. They sign the data itself, so no digest is chosen.',
        items: [
          { label: 'PKCS#11', text: 'A token implementing PKCS#11 3.2 with the ML-DSA mechanisms' },
          { label: 'OpenBao / Vault Transit', text: 'Transit key types mldsa-44, mldsa-65 and mldsa-87' },
          { label: 'Google Cloud KMS', text: 'PQ_SIGN_ML_DSA key versions, mapped from the KMS API but not yet tested against the service. KMS signs at most 64 KiB of data, so a CRL larger than that cannot be signed' },
          { label: 'Not available', text: 'Azure Key Vault and AWS CloudHSM providers hold no ML-DSA key, and FIPS mode refuses ML-DSA on every provider' },
        ]
      },
    ],
    tips: [
      'Use SoftHSM for testing before deploying with a physical HSM',
      'Keys generated on an HSM never leave the hardware: they cannot be exported',
      'Test connection before using an HSM provider for CA signing',
      'For long-lived root CAs in production, prefer HSM-backed key storage',
    ],
    warnings: [
      'The declared certification is the operator\'s statement about the HSM: UCM does not verify the hardware. Profiles aligned with eIDAS read it to check CA key protection',
      'HSM provider misconfiguration can prevent certificate signing',
      'Losing access to the HSM means losing access to the keys stored on it',
    ],
    related: ['CAs', 'Certificates', 'Settings']
  },

  // ===== SSO (sub-page of Settings, kept for reference) =====
  sso: {
    title: 'Single Sign-On',
    subtitle: 'SAML, OAuth2, and LDAP integration',
    overview: 'Configure Single Sign-On to allow users to authenticate via their organization identity provider. Supports SAML 2.0, OAuth2/OIDC, and LDAP protocols.',
    sections: [
      {
        title: 'SAML 2.0',
        icon: Lock,
        items: [
          { label: 'Identity Provider', text: 'Configure IDP metadata URL or upload XML' },
          { label: 'SP Metadata URL', text: 'Provide this URL to your IDP to auto-configure UCM as a service provider' },
          { label: 'SP Certificate', text: 'UCM HTTPS certificate included in metadata, must be trusted by the IDP or metadata will be rejected' },
          { label: 'Entity ID', text: 'UCM service provider entity identifier' },
          { label: 'ACS URL', text: 'Assertion Consumer Service callback URL' },
          { label: 'Attribute Mapping', text: 'Left column: the attribute name sent by the IdP. Right column: the UCM field it fills (username, email, fullname or groups). Example: user.userprincipalname → username.' },
          { label: 'Groups for role mapping', text: 'Read from the attributes mapped to groups, else from groups and the Microsoft Entra ID / AD FS group and role claims. When Entra ID sends groups.link instead of the groups (users in more than 150 groups), a warning is logged and, when role mapping rules exist, the user is refused: emit only the groups assigned to the application, or app roles.' },
          { label: 'IdP-initiated login', text: 'Accepts logins started from the IdP portal, checked like any other response. On for providers created before 2.243, off for new ones: turn it on only if users start from the IdP portal.' },
          { label: 'NameID format', text: 'Unspecified (IdP default), Persistent, Email address or Transient: sent in each login request and published in the SP metadata. Persistent gives a stable identifier; a transient NameID is never used to recognise the account.' },
          { label: 'Single Logout', text: 'A LogoutRequest signed by the IdP and sent to the SLO URL of the SP metadata (HTTP-Redirect) closes the UCM session of that NameID in this browser, unless its SessionIndex names another session. A LogoutResponse goes back to the IdP SLO URL, signed with the SP key (unsigned when the SP certificate is not RSA, which a strict IdP refuses); without an IdP SLO URL the browser returns to the login page. An unsigned, forged, stale or replayed request, or one without Destination, is refused.' },
        ]
      },
      {
        title: 'OAuth2 / OIDC',
        icon: Globe,
        items: [
          { label: 'Authorization URL', text: 'OAuth2 authorization endpoint' },
          { label: 'Token URL', text: 'OAuth2 token endpoint' },
          { label: 'Client ID/Secret', text: 'OAuth2 client credentials from your IDP' },
          { label: 'Scopes', text: 'OAuth2 scopes to request (openid, profile, email)' },
          { label: 'Auto-Create Users', text: 'Automatically create UCM accounts on first SSO login' },
        ]
      },
      {
        title: 'Role Provisioning (#81)',
        icon: UserPlus,
        items: [
          { label: 'Identity matching', text: 'A login opens the account bound to the IdP identifier (OIDC sub, SAML persistent NameID, LDAP entryUUID or objectGUID). A username or email only matches an account of the same provider not bound yet; a local account, or one bound to another identity, is refused at sign-in. To merge a local account, use Link to SSO in Users first: its next sign-in through that provider binds the identifier.' },
          { label: 'Default Role', text: 'Given to accounts created at first SSO login when the provider has no role mapping rule, and as the base role of a new account whose matching rule gives only a custom role (viewer when None). None: nobody signs in without a rule. Role changes made later in UCM are preserved.' },
          { label: 'Role Mapping', text: 'Map external groups (Azure AD, Okta, LDAP) → UCM roles (admin / operator / auditor / viewer) or custom roles. With at least one rule, a user no rule matches is refused at every SSO sign-in (OIDC, SAML, LDAP), new account or existing one; a passkey or certificate sign-in is not checked. Used at user creation, and at every login when role sync is enabled. When several groups match, the highest-privilege role wins (admin > operator > auditor > viewer): entry order does not matter (#221). Each group can also name a custom role (chosen from the existing custom roles): it is added to the base role, or used alone. If several matching groups give a custom role, the first one in the list wins. With role sync on, a custom role set by SSO is removed when no group gives one; a custom role assigned by hand in UCM is never touched. System roles cannot be used as the custom role.' },
          { label: 'Sync role on each login', text: 'OFF (default): SSO never overrides UCM-managed roles. ON: role is re-synced from role_mapping at every login; a matching rule that gives no base role keeps the stored one (default_role is never re-applied).' },
          { label: 'Enforce 2FA', text: 'Users of this provider must enrol a second factor. LDAP sign-ins ask for an enrolled TOTP code or security key, as local sign-ins do, with or without this option; OIDC and SAML sign-ins only require the enrolment and rely on the identity provider for MFA.' },
          { label: 'Auto-update users', text: 'Updates email and full name on each login. Does NOT touch the role.' },
        ]
      },
      {
        title: 'LDAP',
        icon: Database,
        items: [
          { label: 'Server', text: 'LDAP server hostname and port (389, or 636 for LDAPS)' },
          { label: 'StartTLS', text: 'On a plain LDAP port, upgrades the connection to TLS before any bind, with the same certificate verification as LDAPS. On by default for a new provider without SSL/TLS. Without SSL/TLS or StartTLS, the bind and user passwords cross the network in clear.' },
          { label: 'Bind DN', text: 'Distinguished name for LDAP bind authentication' },
          { label: 'Base DN', text: 'Search base for user lookups' },
          { label: 'User Filter', text: 'LDAP filter to match users (e.g., (uid={username}))' },
          { label: 'Attribute Mapping', text: 'Map LDAP attributes to username, email, full name' },
          { label: 'Unique ID attribute', text: 'Immutable id that recognises the account (entryUUID, objectGUID). An account bound by its DN moves to this id at its next sign-in; changing it from one id attribute to another refuses every bound user until Unlink then Link to SSO.' },
        ]
      },
    ],
    tips: [
      'Test SSO with a non-admin account first to avoid lockouts',
      'Keep local admin login available as a fallback',
      'Map the IDP email attribute to ensure unique user identification',
      'Use the SP Metadata URL to auto-configure your IDP (SAML)',
      'UCM HTTPS certificate must be trusted by the IDP for SAML metadata to be accepted',
    ],
    warnings: [
      'Misconfigured SSO can lock all users out: always keep a local admin',
    ],
    related: ['Settings', 'Users & Groups']
  },

  // ===== SECURITY (sub-page of Settings) =====
  security: {
    title: 'Security Settings',
    subtitle: 'Authentication and access policies',
    overview: 'Configure password policies, session management, rate limiting, and network security. These settings apply system-wide and affect all user accounts.',
    sections: [
      {
        title: 'Private Key Encryption',
        icon: Lock,
        items: [
          { label: 'Status & counters', text: 'Shows whether encryption is enabled and how many stored private keys are encrypted vs unencrypted' },
          { label: 'Enable / Disable', text: 'Encrypt all CA and certificate private keys with AES-128 (Fernet, with HMAC-SHA256) under a master key file. Enabling also removes plaintext key mirrors, while disabling recreates them. A disable stopped before every value was decrypted is shown as left half-way: run it again to finish it. After a disable, enabling again waits until every node has reloaded, then two minutes (ten at most, unless a live node never reloads). The data keys stay for reading only for seven days, so a value written late under them still opens; a daily sweep decrypts any such value, and each key is deleted after its date once a sweep finds nothing under it. Outside HA master.key is removed with the last of them' },
          { label: 'First start', text: 'Without a master key, UCM creates /etc/ucm/master.key (0600) at startup and encrypts the keys already stored. A container does so only when /etc/ucm is a named volume or a host directory. Skipped with KEY_ENCRYPTION_KEY set, with encrypted keys or a keyed audit chain already in the database, after encryption was disabled here, or with UCM_AUTO_MASTER_KEY=false. At each start a loaded key also encrypts the values still stored unencrypted, and a key that does not decrypt them puts UCM in safe mode. Back up the key file' },
          { label: 'Key files on disk', text: 'Shows how many plaintext key mirrors remain; use deploy hooks when another service needs a key file' },
          { label: 'UCM_REQUIRE_DB_ENCRYPTION_KEY', text: 'Opt-in environment variable: refuse to start without an explicit database encryption key' },
          { label: 'UCM_REQUIRE_KEY_ENCRYPTION', text: 'Opt-in environment variable: refuse to start unless private-key encryption is enabled' },
          { label: 'Encrypt remaining keys', text: 'Shown while encryption is enabled and some keys or secrets are still stored unencrypted: encrypts them, leaving those already encrypted as they are' },
          { label: 'Data key rotation', text: 'Keys are encrypted under a data key stored in the database and wrapped by the master key (master.key or KEY_ENCRYPTION_KEY), still the only file to back up. Rotate Data Key re-encrypts every stored key and secret under a new data key without changing the master key; an interrupted rotation keeps both data keys and is finished by running it again. The next rotation is possible once every node has loaded the new data key, then two minutes later (ten at most, unless a live node never loads it). The previous data keys stay for reading only for seven days, listed with their deletion date, so a value written late under one still opens; a daily sweep re-encrypts such values under the current key, and an old key is deleted after its date once a sweep finds nothing under it. The fingerprint shown names the master key without revealing it' },
          { label: 'Session key', text: 'The session key (SECRET_KEY) signs the CSRF tokens of the web interface; sessions themselves are stored on the server and do not depend on it. With encryption enabled (in HA, the KEK every node holds), Rotate Session Key stores a new key encrypted under the data key in the database: every node loads it without a restart, and the previous key stays accepted for 24 hours, the lifetime of a CSRF token, so nobody is logged out; another rotation waits for that period to end. SECRET_KEY in the environment is then only the fallback used when the stored key cannot be read at startup (another installation\'s database, a different master key), which is logged; a node already running keeps the key it has and tries again until it reads the stored one. Without encryption the key is never stored in the database: on a single node the rotation writes SECRET_KEY to the environment file and restarts the service; in HA it is refused until encryption is enabled. Once a disable of encryption succeeds, the stored key is removed and SECRET_KEY signs again: pages opened before must be reloaded. The stored key is never part of a backup' },
        ]
      },
      {
        title: 'Password Policy',
        icon: Lock,
        items: [
          { label: 'Minimum Length', text: 'Minimum number of characters required, 6 to 32' },
          { label: 'Complexity', text: 'Require uppercase letters, numbers and special characters, each switched on separately' },
        ]
      },
      {
        title: 'Session & Access',
        icon: Fingerprint,
        items: [
          { label: 'Session Timeout', text: 'Auto-logout after inactivity period (Settings › General)' },
          { label: 'Session Duration', text: 'Maximum session length in hours, whatever the activity' },
          { label: 'Account lockout', text: 'Max Login Attempts and Lockout Duration (Settings › General) lock an account after repeated failures. Request rate limits per IP are set by the RATE_LIMIT_* environment variables, not on this page' },
          { label: 'Admin access allowlist', text: 'Limit the web interface and the management API to listed IP addresses and networks' },
          { label: '2FA Enforcement', text: 'Require two-factor authentication for all users' },
        ]
      },
      {
        title: 'Admin Access Allowlist',
        icon: Globe,
        items: [
          { label: 'Networks', text: 'One IPv4 or IPv6 address or CIDR network per line, up to 100. Empty means no restriction. IPv4 and IPv6 are listed separately: 0.0.0.0/0 does not admit an IPv6 client, nor ::/0 an IPv4 client' },
          { label: 'What is blocked', text: 'From other addresses: the web interface, the login, the /api/v2 API (API keys included) and the WebSocket channel answer 403' },
          { label: 'Always reachable', text: 'ACME, SCEP, EST, OCSP, CRL/AIA, TSA, XCEP/WSTEP, the SSH setup script and the health endpoints' },
          { label: 'Your address', text: 'The section shows the address the server sees for you; a list that does not include it is refused' },
          { label: 'UCM_ADMIN_ALLOWED_NETWORKS', text: 'Environment variable (comma-separated) that wins over the setting and makes it read-only' },
          { label: 'UCM_ADMIN_ALLOWLIST_DISABLE', text: 'Set to 1 and restart to turn the check off after a lock-out' },
        ]
      },
      {
        title: 'mTLS Authentication',
        icon: ShieldCheck,
        items: [
          { label: 'Trusted CA', text: 'The CA whose client certificates are accepted at login, and the default issuer when a user generates one. Any CA whose certificate is not revoked can be chosen, keyless or offline included: such a CA issues nothing, so its users upload certificates issued elsewhere (v2.248). It is the only trust anchor of the HTTPS port: a client certificate from its parent or from a sibling CA is refused at the TLS handshake, so trust a root to accept its whole hierarchy (v2.252)' },
          { label: 'Require client certificate', text: 'Optionally make mTLS mandatory for the web UI, changing mTLS settings requires a service restart' },
          { label: 'Same serial, other CA (v2.251)', text: 'An enrolment is identified by its issuer and serial number, so a client certificate can be enrolled, imported or assigned when another CA\'s enrolled certificate has the same serial' },
          { label: 'Reverse proxy headers (v2.252)', text: 'Behind a proxy that forwards the client certificate as headers, send the issuer DN (X-SSL-Client-I-DN) with the serial, read as hexadecimal, or the certificate itself (X-SSL-Client-Cert). A serial without its issuer opens no enrolment that recorded one, and a presented certificate cannot be enrolled without it' },
          { label: 'Revoked issuer', text: 'A client certificate issued under a revoked CA, at any level of its chain, opens no session and can be neither enrolled nor imported (v2.252)' },
          { label: 'Generated keys (v2.251)', text: 'A user mTLS certificate generated by UCM gets a key at the issuing CA\'s strength, RSA or a NIST curve browsers accept, moved to the closest type the policies allow, instead of RSA-2048 always' },
        ]
      },
    ],
    tips: [
      'Enable rate limiting to protect against automated attack tools',
      'Use the admin access allowlist to limit the web interface to your management VLAN, bastion or VPN',
    ],
    warnings: [
      'Locking the password policy too tightly may frustrate users',
      'Behind a reverse proxy, set UCM_BEHIND_PROXY and UCM_TRUSTED_PROXIES before using the admin access allowlist, otherwise every request appears to come from the proxy',
      'Security-sensitive settings (session, lockout, HSTS, public URL, password policy) require admin:settings, the fields are locked for operators',
    ],
    related: ['Account', 'Users & Groups', 'Settings']
  },

  // ===== POLICIES =====
  policies: {
    title: 'Certificate Policies',
    subtitle: 'Issuance rules and compliance enforcement',
    overview: 'Define and manage certificate policies that control issuance rules, key requirements, validity limits, and approval workflows. Policies are evaluated in priority order when certificates are requested.',
    sections: [
      {
        title: 'Operations',
        icon: Gavel,
        items: [
          { label: 'Issuance', text: 'The issue form, CSR signing and bulk signing, and the renewals an operator performs' },
          { label: 'Renewal', text: 'Renewals by an operator, one or in bulk, and by the scheduler, which queues its renewal instead of performing it' },
          { label: 'Revocation', text: 'Revocations of certificates and intermediate CAs by an operator (a CA also under the policies scoped on it); an ACME client cannot wait for a decision, so its revocation is refused' },
          { label: 'Several at once', text: 'A policy can govern several operations; one with none (an old renewal or revocation type, never enforced) governs nothing until you choose' },
        ]
      },
      {
        title: 'Rules',
        icon: ShieldCheck,
        items: [
          { label: 'Max Validity', text: 'Maximum certificate lifetime in days' },
          { label: 'Allowed Key Types', text: 'Restrict which key algorithms and sizes can be used, ML-DSA-44, ML-DSA-65 and ML-DSA-87 included; FIPS mode removes ML-DSA' },
          { label: 'Allowed Signature Schemes', text: 'PKCS#1 v1.5, RSA-PSS, ECDSA, EdDSA, ML-DSA or SLH-DSA, matched against the signing CA\'s key. Allowed Signature Hashes do not bind an ML-DSA CA, which signs without a separate digest' },
          { label: 'SAN Restrictions', text: 'Limit the number of DNS names (other SAN types are not counted); one DNS pattern per policy (*.company.com, or company.com to include the domain itself) scopes the policy to the matching names' },
          { label: 'Allowed Signature Hashes', text: 'SHA-256, SHA-384 or SHA-512; none selected allows any. When nobody chose the hash, the default applies if allowed, else the weakest allowed one. The issue form offers only the allowed key types, Create CA only the allowed key types and hashes' },
        ]
      },
      {
        title: 'Approval Workflows',
        icon: Users,
        items: [
          { label: 'Approval Groups', text: 'Assign a user group responsible for approving requests' },
          { label: 'Min Approvers', text: 'Number of approvals required before issuance' },
          { label: 'Notifications', text: 'E-mail when the policy refuses an operation or holds one for approval; to the listed addresses, else to its approvers. A repeated refusal is reported once per hour' },
        ]
      },
    ],
    tips: [
      'Lower priority number = higher precedence for the approval. The rules of every policy in scope apply together, the strictest winning.',
      'Scope policies to specific CAs for granular control.',
      'Enable notifications to catch policy violations early.',
    ],
    related: ['Approvals', 'Certificates', 'CAs']
  },

  // ===== APPROVALS =====
  approvals: {
    title: 'Approval Requests',
    subtitle: 'Certificate approval workflow management',
    overview: 'Review and manage certificate approval requests. When a policy requires approval, certificate issuance is paused until the required number of approvers have reviewed and approved the request.',
    sections: [
      {
        title: 'Request Lifecycle',
        icon: ClockCounterClockwise,
        items: [
          { label: 'Pending', text: 'Awaiting review, certificate cannot be issued yet' },
          { label: 'Approved', text: 'All required approvals received, certificate can be issued' },
          { label: 'Rejected', text: 'Any rejection immediately stops the request' },
          { label: 'Expired', text: 'Not decided within seven days; closed as expired and never counted as pending' },
          { label: 'Cancelled', text: 'Its requester performed the action directly or approved a duplicate of it: nobody approves their own request' },
        ]
      },
      {
        title: 'Where requests come from',
        icon: ListChecks,
        items: [
          { label: 'Issue form', text: 'A certificate request matching a policy that requires approval' },
          { label: 'Sign CSR and bulk signing', text: 'Signing a stored request, alone or from Operations, is queued the same way; the approval performs the signing' },
          { label: 'Renewal', text: 'Renewing a certificate, alone or in bulk, is queued too; a renewal that could not be honoured (revoked, key not held by the server) is refused at once' },
          { label: 'Revocation', text: 'Revoking a certificate (alone, in bulk, from the user certificates) or an intermediate CA under a revocation policy is queued; the approval revokes with the reason asked for' },
          { label: 'Scheduler', text: 'Under a renewal policy the scheduler queues the renewal; the approval re-signs the key the server holds, as the scheduler would have' },
          { label: 'Enrolment protocols', text: 'An ACME finalize, an EST enrolment, re-enrolment or server key generation, a SCEP request (even on an auto-approving profile) or a WSTEP enrolment or renewal under a policy that requires approval is held: the client is told the request is pending and polls; the approval issues the certificate through that protocol, a rejection or expiry is reported to the client as a refusal' },
          { label: 'Administrators', text: 'Bypass the queue on every path, as on the issue form' },
        ]
      },
      {
        title: 'Requests closed for you',
        icon: ClockCounterClockwise,
        items: [
          { label: 'Signed or renewed directly', text: 'A queued request whose target an administrator signed or renewed meanwhile is closed as approved by that action and linked to the certificate' },
          { label: 'Deleted or revoked', text: 'A request whose target was deleted or revoked is closed as rejected; a certificate hold keeps the renewal request waiting for the unhold' },
          { label: 'Already satisfied', text: 'Approving a request already fulfilled closes it on the existing certificate; approving one of several requests for the same target closes the others as approved by you' },
          { label: 'Target gone', text: 'Approving a request whose stored request, certificate or CA no longer exists closes it as rejected' },
          { label: 'Revoked or renewed meanwhile', text: 'A queued revocation whose certificate was revoked directly is closed as approved; one whose certificate was renewed since is closed as rejected when approved' },
          { label: 'Deadline', text: 'A request waits seven days; past that it is closed as expired, never counted as pending, and the renewal scheduler resumes for its certificate' },
        ]
      },
    ],
    tips: [
      'Any single rejection immediately stops the approval: this is intentional for security.',
      'While a renewal awaits approval, the scheduler leaves the certificate to that decision, as long as it can come before the certificate expires; under a renewal policy it never renews without one.',
      'Each decision and its comment are kept in the request\'s approval timeline; the audit log records approvals, not the comment, a queued request or a rejection.',
    ],
    related: ['Policies', 'Certificates', 'Audit Logs']
  },

  // ===== KEY RECOVERY =====
  keyRecovery: {
    title: 'Key Recovery',
    subtitle: 'Recover archived private keys under dual control',
    overview: 'Key Recovery retrieves the archived private key of a previously issued certificate through an approval-gated, fully audited workflow. It exists for keys that were not exported at issuance time (the preset did not allow it, or export was skipped) and are needed later, with an approval trail attached to the retrieval.',
    sections: [
      {
        title: 'Workflow',
        icon: ClockCounterClockwise,
        items: [
          { label: 'Request', text: 'A user requests recovery of a specific certificate\'s archived key, with a reason' },
          { label: 'Approve (four-eyes)', text: 'An administrator reviews and approves; with dual control on (the default), the requester cannot approve their own request' },
          { label: 'Download', text: 'Once approved, the key is released as a password-protected PKCS#12 bundle' },
          { label: 'Certificate replaced (v2.251)', text: 'Approval and recovery answer 410 unless the request\'s certificate is still the one it was opened on. A replacing restore cancels the open requests on the certificates it removes' },
        ]
      },
      {
        title: 'Requirements',
        icon: Key,
        items: [
          { label: 'Archived key', text: 'The certificate\'s private key must be stored in the database, recovery cannot reconstruct a key that was never archived' },
          { label: 'Dual control', text: 'On by default: request and approval are separate actions by different people. Requests, approvals and downloads are written to the audit trail; a refused approval or download is not' },
        ]
      },
    ],
    tips: [
      'Key Recovery is for keys that were not exported when the certificate was issued; it is not a replacement for restricting key export at issuance time.',
      'Every request, approval and download is recorded in the audit trail; refusals are not.',
    ],
    warnings: [
      'A certificate whose private key was never archived cannot be recovered: there is nothing to release.',
    ],
    related: ['Certificates', 'Approvals', 'Audit Logs']
  },

  // ===== REPORTS =====
  reports: {
    title: 'Reports',
    subtitle: 'PKI compliance and inventory reports',
    overview: 'Generate, download, and schedule reports for compliance auditing. Reports cover certificate inventory, expiring certificates, CA hierarchy, audit activity, and policy compliance status. Download a PDF executive report for management review.',
    sections: [
      {
        title: 'Report Types',
        icon: FileText,
        items: [
          { label: 'Certificate Inventory', text: 'Complete list of all certificates with status' },
          { label: 'Expiring Certificates', text: 'Certificates expiring within a specified time window' },
          { label: 'CA Hierarchy', text: 'Certificate Authority structure and statistics' },
          { label: 'Audit Summary', text: 'The most frequent actions and the most active users over the period' },
          { label: 'Compliance Status', text: 'Three checks: active certificates, expired CAs, and certificates expiring within 30 days; certificate policies are not read' },
          { label: 'Revoked Certificates', text: 'Certificates revoked during the period, with date and reason' },
        ]
      },
      {
        title: 'Executive PDF Report',
        icon: FilePdf,
        items: [
          { label: 'Download PDF', text: 'One-click professional PDF report for management and auditors' },
          { label: 'Contents', text: 'Executive summary, risk assessment, certificate inventory, compliance scores, CA infrastructure, audit activity, and recommendations' },
          { label: 'Charts & Visuals', text: 'Includes risk gauge, status distribution, expiration timeline, and compliance breakdown' },
        ]
      },
      {
        title: 'Scheduling',
        icon: CalendarBlank,
        items: [
          { label: 'Schedule tab', text: 'Tick any data report or PDF template, then set its frequency (daily, weekly or monthly), time (UTC), format and recipients' },
          { label: 'Attachment', text: 'The report is attached to the email in its format: CSV or JSON for data reports, PDF for the PDF templates' },
        ]
      },
    ],
    tips: [
      'Use the PDF executive report for management reviews and compliance audits.',
      'Download reports as CSV for spreadsheet analysis or JSON for automation.',
      'Use the test send feature to verify email delivery before enabling schedules.',
    ],
    related: ['Policies', 'Certificates', 'Audit Logs', 'Settings']
  },

  // ===== DISCOVERY =====
  discovery: {
    title: 'Certificate Discovery',
    subtitle: 'Find TLS certificates on your network',
    overview: 'Scan your network to find TLS certificates deployed on servers and endpoints, and match them against your managed PKI inventory. Locate untracked certificates, detect changes, and watch for expiring certificates outside UCM\'s control.',
    sections: [
      {
        title: 'Tabs',
        icon: ListChecks,
        items: [
          { label: 'Discovered', text: 'All certificates found by scans, with status, expiry, and endpoint details' },
          { label: 'Profiles', text: 'Saved scan configurations, targets, ports, schedule, notifications' },
          { label: 'History', text: 'Past scan runs with duration, targets scanned, and certificates found' },
        ]
      },
      {
        title: 'Scanning',
        icon: Globe,
        items: [
          { label: 'Quick Scan', text: 'Ad-hoc scan without saving a profile, enter targets and ports, results stream live' },
          { label: 'Targets', text: 'Entered as tags, one per target: hostname, IP, CIDR subnet (192.168.1.0/24), or host:port (10.0.0.1:8443)' },
          { label: 'Ports', text: 'Comma-separated TCP ports (e.g. 443, 8443, 636), or the common-ports preset' },
          { label: 'Advanced options', text: 'Reverse DNS resolution (PTR records), timeout, and concurrency' },
          { label: 'Schedule', text: 'Profiles run manually or automatically every 1h / 6h / 12h / 24h / 7d' },
          { label: 'Notifications', text: 'Email alerts on new certificates, certificate changes, or upcoming expiry. A certificate found through SNI on an IP target is counted as new at every scan' },
        ]
      },
      {
        title: 'Result Statuses',
        icon: ShieldCheck,
        items: [
          { label: 'Managed', text: 'The certificate\'s SHA-256 fingerprint matches a certificate in UCM\'s inventory' },
          { label: 'Unmanaged', text: 'Found on the network but not in the inventory, a candidate for bringing under management' },
          { label: 'Error', text: 'The endpoint answered but its TLS handshake or certificate failed (SNI rejected, unreadable certificate). A refused connection, a timeout, a DNS or network failure leaves no row. Retry a row, or Retry all errors on the current page' },
          { label: 'Changed', text: 'An endpoint presenting a different certificate than the previous scan is flagged with a Last changed timestamp' },
        ]
      },
    ],
    tips: [
      'Filter results with the status pills: All, Managed, Unmanaged, Error',
      'Export downloads every discovered certificate as CSV, whatever the filters',
      'Schedule a daily scan of your server subnets with the new-certificate notification enabled',
    ],
    warnings: [
      'Running scans and managing profiles requires admin permissions; a profile subnet is capped at 1024 addresses (/22), a CIDR entered as a target at 65,536 hosts',
    ],
    related: ['Certificates', 'CAs', 'Reports']
  },

  // ===== MICROSOFT CA =====
  msca: {
    title: 'Microsoft AD CS Integration',
    subtitle: 'Sign certificates with Microsoft Certificate Authority',
    overview: 'Connect UCM to Microsoft Active Directory Certificate Services (AD CS) to sign CSRs using your Windows PKI infrastructure and manage the full certificate lifecycle. Supports certificate (mTLS), Kerberos, and Basic authentication, plus an optional WinRM admin channel for revocation, CRL, inventory and pending-request management.',
    sections: [
      {
        title: 'Authentication Methods',
        icon: Key,
        items: [
          { label: 'Client Certificate (mTLS)', text: 'Most secure. Generate a client cert on your MS CA, export as PFX, upload cert and key PEM.' },
          { label: 'Basic Auth', text: 'Username/password over HTTPS. Works without domain join. Enable basic auth in IIS certsrv.' },
          { label: 'Kerberos', text: 'Requires requests-kerberos package and domain-joined machine or keytab configured.' },
        ]
      },
      {
        title: 'Signing CSRs',
        icon: Certificate,
        items: [
          { label: 'Template Selection', text: 'Choose from available certificate templates on the MS CA' },
          { label: 'Auto-Approved', text: 'Templates with autoenroll return the certificate immediately' },
          { label: 'Manager Approval', text: 'Some templates require manager approval, UCM tracks the pending request' },
          { label: 'Pending requests', text: 'A request the CA holds for its manager stays Pending in UCM, and the page offers no status check: once it is issued on the CA, import the certificate, or let Inventory sync over the WinRM admin channel import the certificates UCM does not know yet' },
        ]
      },
      {
        title: 'Enroll on Behalf Of (EOBO)',
        icon: UserSwitch,
        items: [
          { label: 'Overview', text: 'Submit CSR on behalf of another user using enrollment agent certificates' },
          { label: 'Enrollee DN', text: 'Distinguished Name of the target user (auto-filled from CSR subject)' },
          { label: 'Enrollee UPN', text: 'User Principal Name of the target user (auto-filled from CSR SAN email)' },
          { label: 'Requirements', text: 'CA template must allow enrollment on behalf of others. UCM service account needs an enrollment agent certificate.' },
        ]
      },
      {
        title: 'Lifecycle: Renew & Revoke',
        icon: Certificate,
        items: [
          { label: 'Renew', text: 'Renewing an AD CS-issued certificate resubmits its original CSR to the same connection and template, the issuing CA signs it, UCM does not.' },
          { label: 'Revoke', text: 'Revoking an AD CS-issued certificate is local to UCM unless the WinRM admin channel is configured, in which case it is propagated to the Windows CA.' },
          { label: 'Pending renewal', text: 'If the CA holds the renewal for manager approval, UCM tracks it as a pending request like any other.' },
        ]
      },
      {
        title: 'WinRM Admin Channel (optional)',
        icon: Lock,
        items: [
          { label: 'Purpose', text: 'Runs management operations on the Windows CA (revoke, unrevoke, publish CRL, inventory, approve/deny) via PowerShell remoting + certutil, things AD CS Web Enrollment cannot do.' },
          { label: 'Transport', text: 'NTLM or Kerberos over HTTP/HTTPS. Kerberos + HTTPS recommended; Kerberos reuses the connection\'s keytab.' },
          { label: 'Credentials', text: 'Reuses the connection\'s own by default. mTLS-enrolled connections must set a dedicated WinRM account (least-privilege "Issue and Manage Certificates" officer).' },
          { label: 'Requirement', text: 'WinRM enabled on the CA and the optional pywinrm package installed. Management operations require admin:system; propagating a revocation or a hold release to the CA follows the certificate\'s write:certificates.' },
        ]
      },
      {
        title: 'CRL Revocation Sync',
        icon: ShieldCheck,
        items: [
          { label: 'One-way sync', text: 'Periodically fetches the CA\'s CRL and marks certificates revoked on the CA as revoked in UCM. Never un-revokes.' },
          { label: 'CRL source', text: 'An explicit CRL URL, or auto-detected from the CRL Distribution Point of issued certificates.' },
          { label: 'Verified', text: 'The CRL signature is checked against the CA certificate before anything is applied.' },
        ]
      },
      {
        title: 'CA Inventory & Control Panel',
        icon: HardDrive,
        items: [
          { label: 'Inventory sync', text: 'Imports certificates issued directly on the CA that UCM doesn\'t know yet (incremental by request id); reconciliation is available through the API.' },
          { label: 'Pending requests', text: 'List, approve (resubmit + auto-import) or deny requests awaiting CA manager approval.' },
          { label: 'CA health', text: 'CA service status, CA certificate expiry, CRL next-update and pending count at a glance.' },
        ]
      },
    ],
    tips: [
      'Test the connection first to verify authentication and discover available templates.',
      'Enable EOBO by checking the checkbox in the sign modal: fields auto-fill from CSR data.',
      'Client certificate authentication is recommended for production: it doesn\'t require domain join.',
      'Enable the WinRM admin channel to propagate revocations to the CA and manage pending requests from UCM.',
    ],
    warnings: [
      'Kerberos requires the machine to be domain-joined or a keytab configured, not available in Docker.',
      'EOBO requires an enrollment agent certificate configured on the AD CS server.',
      'Without the WinRM admin channel, revoking an AD CS certificate only marks it revoked in UCM: the Windows CA is not notified.',
    ],
    related: ['CSRs', 'Certificates', 'Settings']
  },

  // ===== SSH CAS =====
  sshCas: {
    title: 'SSH Certificate Authorities',
    subtitle: 'Manage SSH CAs for user and host authentication',
    overview: 'Create and manage SSH Certificate Authorities following OpenSSH standards. SSH CAs eliminate the need to distribute individual public keys, instead, servers and users trust the CA, and the CA signs certificates that grant access.',
    sections: [
      {
        title: 'CA Types',
        icon: Key,
        items: [
          { label: 'User CA', text: 'Signs user certificates for SSH login. Servers trust this CA and accept any certificate it signs.' },
          { label: 'Host CA', text: 'Signs host certificates to prove server identity. Clients trust this CA to verify they are connecting to the right server.' },
        ]
      },
      {
        title: 'Key Algorithms',
        icon: ShieldCheck,
        items: [
          { label: 'Ed25519', text: 'Modern, fast, small keys (256-bit). Recommended for new deployments.' },
          { label: 'ECDSA P-256 / P-384 / P-521', text: 'Elliptic curve keys, widely supported. Good balance of security and compatibility.' },
          { label: 'RSA 4096', text: 'Traditional algorithm, always 4096-bit. Broadest compatibility with older systems.' },
        ]
      },
      {
        title: 'Server Configuration',
        icon: HardDrive,
        items: [
          { label: 'Linux/macOS Setup Script', text: 'Download a POSIX shell script (.sh) that auto-configures sshd to trust this CA. Quick install: curl -sSL <url> | sudo bash' },
          { label: 'Windows Setup Script', text: 'Download a PowerShell script (.ps1) that configures Windows OpenSSH Server (writes the CA pubkey to %ProgramData%\\ssh, locks down ACLs, adds TrustedUserCAKeys / HostCertificate to sshd_config, validates with sshd -T, restarts sshd). Quick install: iwr <url> | iex' },
          { label: 'Diagnostic block', text: 'On Add-WindowsCapability failure (WSUS / domain-joined), the script prints a labelled block explaining the policy state and three remediation paths, it never modifies WSUS / WU policy itself' },
          { label: 'Dry-run', text: 'Both scripts support a -DryRun / --dry-run flag to preview changes without applying them' },
          { label: 'Manual Setup', text: 'Copy the CA public key and add TrustedUserCAKeys (user CA) or HostCertificate (host CA) to sshd_config' },
        ]
      },
      {
        title: 'Key Revocation',
        icon: Lock,
        items: [
          { label: 'KRL (Key Revocation List)', text: 'Compact binary format to revoke individual certificates. Configured via RevokedKeys in sshd_config.' },
          { label: 'Download KRL', text: 'Download the current KRL file from the CA detail panel.' },
        ]
      },
      {
        title: 'TTL Formats',
        icon: Clock,
        items: [
          { label: 'Suffixed durations', text: 'Default TTL and Max TTL accept 24h, 7d, 365d, suffixes s, m, h, d, w, y' },
          { label: 'Bare numbers', text: 'A plain number is interpreted as seconds (e.g. 3600 = 1 hour)' },
          { label: 'Validation', text: 'Malformed values are rejected with an error naming the accepted formats' },
        ]
      },
      {
        title: 'Allowed Principals',
        icon: Users,
        items: [
          { label: 'Allowed principals', text: 'Comma-separated patterns (e.g. deploy, team-*). Every principal in a request must match one of them.' },
          { label: 'Allow any principal', text: 'A CA with an empty list signs for any name, root included, only when this option is ticked. Otherwise it signs nothing.' },
          { label: 'Upgrade', text: 'CAs created before 2.245 without a list keep signing for any principal: the upgrade ticks the option for them.' },
        ]
      },
      {
        title: 'Key ID',
        icon: Key,
        items: [
          { label: 'Set by the CA', text: 'sshd logs the key ID as the holder\'s identity. By default the CA names every certificate principals@CA name, and a request that sets another key ID is refused.' },
          { label: 'Let requesters set the key ID', text: 'Tick it to let requesters choose their own, e.g. a ticket or employee number.' },
          { label: 'Upgrade', text: 'From 2.249, existing CAs start with the option off too.' },
        ]
      },
    ],
    tips: [
      'Use separate CAs for user and host certificates, never mix them.',
      'Ed25519 is recommended for new deployments due to speed and security.',
      'Download the setup script for easy server configuration: it handles backup and validation automatically.',
    ],
    warnings: [
      'A CA cannot be deleted while certificates it signed remain: delete them first, and update server trust.',
      'If the CA private key is compromised, all certificates signed by it must be considered untrusted.',
    ],
    related: ['SSH Certificates', 'Settings']
  },

  // ===== SSH CERTIFICATES =====
  sshCertificates: {
    title: 'SSH Certificates',
    subtitle: 'Issue and manage OpenSSH certificates',
    overview: 'Issue SSH certificates signed by your SSH CAs. Certificates replace manual authorized_keys management by providing time-limited, principal-scoped access with automatic expiry. Both user and host certificates are supported.',
    sections: [
      {
        title: 'Issuance Modes',
        icon: Certificate,
        items: [
          { label: 'Sign Mode', text: 'Paste an existing SSH public key to sign it. The private key stays on the user\'s machine, UCM never sees it.' },
          { label: 'Generate Mode', text: 'UCM generates a new key pair and signs the certificate. Download the private key immediately, it cannot be retrieved later.' },
        ]
      },
      {
        title: 'Certificate Fields',
        icon: FileText,
        items: [
          { label: 'Key ID', text: 'Identifier sshd logs for the holder. The CA sets it to principals@CA name, unless it lets requesters choose it.' },
          { label: 'Principals', text: 'Usernames (user cert) or hostnames (host cert) this certificate is valid for. Comma-separated.' },
          { label: 'Validity', text: 'Certificate lifetime. Choose a preset (1h, 8h, 24h, 7d, 30d, 90d, 365d) or set custom seconds. Valid from 5 minutes before issuance, for servers whose clock lags (v2.252).' },
          { label: 'Extensions', text: 'SSH extensions like permit-pty, permit-agent-forwarding. Only applicable to user certificates.' },
          { label: 'Critical Options', text: 'User certificates only: force-command, source-address (addresses or CIDR networks, comma-separated) and verify-required, plus vendor options named name@domain. Host certificates carry none, and any other option is refused (v2.252).' },
        ]
      },
      {
        title: 'Certificate Types',
        icon: Users,
        items: [
          { label: 'User Certificate', text: 'Authenticates a user to a server. The server must trust the signing CA via TrustedUserCAKeys.' },
          { label: 'Host Certificate', text: 'Authenticates a server to clients. Clients trust the CA via @cert-authority in known_hosts.' },
        ]
      },
      {
        title: 'Management',
        icon: ArrowClockwise,
        items: [
          { label: 'Revoke', text: 'Add a certificate to the CA\'s Key Revocation List (KRL). Servers must be configured to check the KRL. A revoked certificate stays in the KRL and cannot be deleted until it expires (v2.252).' },
          { label: 'Download', text: 'Download the certificate, public key, or private key (generate mode only).' },
        ]
      },
    ],
    tips: [
      'Use short-lived certificates (8h–24h) for user access to minimize the impact of key compromise.',
      'Sign mode is preferred: the user\'s private key never leaves their machine.',
      'Where a CA lets requesters set the key ID, keep it descriptive (e.g. "jdoe-prod-2025") for easy log auditing.',
      'For host certificates, the principal must match the hostname clients use to connect.',
    ],
    warnings: [
      'In generate mode, download the private key immediately: it is not stored and cannot be recovered.',
      'Revoking a certificate only works if servers are configured to check the CA\'s KRL file.',
    ],
    related: ['SSH CAs', 'Audit Logs']
  },
}

export default helpContent
