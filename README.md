# Ultimate Certificate Manager

![Version](https://img.shields.io/github/v/release/NeySlim/ultimate-ca-manager?label=version&color=brightgreen)
![License](https://img.shields.io/badge/license-AGPL--3.0--only-blue.svg)
![Docker Hub](https://img.shields.io/docker/v/neyslim/ultimate-ca-manager?label=docker%20hub&color=blue)
![GHCR](https://img.shields.io/badge/ghcr.io-available-blue)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support%20UCM-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/neyslim)

**Ultimate Certificate Manager (UCM)** is a web-based Certificate Authority management platform with PKI protocol support (ACME, SCEP, EST, OCSP, CRL/CDP), Microsoft ADCS integration, multi-factor authentication, and certificate lifecycle management.

> **UCM is a young and actively developed project.** Feedback, bug reports, and feature requests are very welcome! Feel free to [open an issue](https://github.com/NeySlim/ultimate-ca-manager/issues): every report helps make UCM better.

> See the [latest release notes](https://github.com/NeySlim/ultimate-ca-manager/releases/latest) and the full [CHANGELOG](CHANGELOG.md) for what's new.

![Dashboard](docs/screenshots/dashboard-dark.png)

---

## Features

### PKI Core
- **CA Management** -- Root and intermediate CAs, hierarchy view, import/export, **intermediate CA revocation** (parent's CRL and OCSP, revoked-upstream status below it), **certificate-only CAs** (a CA signed from an external request, its private key imported later), **HSM-backed signing keys** (private key never leaves the HSM), **configurable RFC 5280 profile** (signature digest, Key Usage, EKU), a CA can be **hidden from the issuance forms** (a root that only signs intermediates) with Let's Encrypt-style defaults and an optional **RSA-PSS** signature scheme, **compliance profiles** aligned with ANSSI, BSI and the EU agreed mechanisms, **externally-signed CAs** (UCM generates the key pair and a CA-type CSR, an offline/external root signs it: the private key never leaves UCM, with same-key CSR renewal), **cross-signed CA certificates** (attach or cross-sign one beside the CA's own certificate, serve it in the default chain during a root rollover, pick the chain per export or deployment, see what still chains to the old root), **RFC 5280 name constraints** set at creation (permitted and excluded DNS, IP-range and e-mail subtrees, enforced on every issuance path), validity from 1 year or any number of days up to 50 years, and an optional **unique subject** rule (a certificate whose subject another entity already carries under that CA is refused on every issuance path, RFC 5280 §4.1.2.6)
- **Certificate Lifecycle** -- Issue, sign, revoke (with the RFC 5280 reason, from every revoke dialog and in bulk), renew (**in-place**: stable IDs across renewals, superseded serials stay on CRL/OCSP until their original expiry, with a chosen validity still capped by policy), rename (mutable display name, covers CN-less certificates), export (PEM, DER, PKCS#12 with a 3DES/SHA-1 compatibility mode for Android 15 and earlier, macOS 14 and earlier, older Windows and Java, JKS; the chain omits the self-signed root by default, with an **Include Root CA** option where a packaging or import target needs it), bulk operations, filter by status / issuer / source (ACME, SCEP, EST, AD CS, import…), including the records **archived** by a renewal or a re-enrolment and kept for history
- **Conformance Linting** -- per-certificate checks against RFC 5280, CA/Browser Forum Baseline Requirements and ETSI EN 319 412 via pkilint (and zlint when available), informative-only
- **CSR Management** -- Create, import, sign Certificate Signing Requests with **custom Extra EKU OIDs** (RFC 5280 §4.2.1.12), **typed SAN validation** (DNS / IP / Email / URI / UPN), NIST P-256 / P-384 / P-521 and Brainpool P256r1 / P384r1 / P512r1 curves, and an **external CA return path**: a certificate issued elsewhere for a CSR generated in UCM completes that CSR on import and keeps its private key; **names added at signing** (the email address of an S/MIME request from a smart card that carries only a CN, under the same name constraints, policies and approval) and **sign again** from the history, for devices that cannot produce their request twice
- **Certificate Templates** -- Predefined profiles for server, client, code signing, email, Windows smartcard logon; key types RSA-2048/3072/4096, EC P-256/P-384/P-521, Brainpool and **post-quantum ML-DSA-44/65/87** (Ed25519/Ed448 for CAs), **custom X.509 extensions by OID**, **qcStatements (ETSI EN 319 412-5) and certificate policy OIDs**, and subject defaults (email included) prefilled into the issue form; JSON export and import that keep every setting, one template or several per file
- **Certificate Discovery** -- Network scanning, scan profiles, scheduled scans, certificate import
- **Trust Store** -- Manage trusted root CA certificates with expiry alerts and bulk removal
- **Chain Repair** -- AKI/SKI-based chain validation with automatic repair scheduler
- **SSH Certificates** -- SSH Certificate Authority management, sign host/user certificates, import CAs and certs, curl-friendly setup scripts; key IDs named by the CA (`principals@CA name`) or left to the requester

### Protocols
- **ACME** -- RFC 8555, auto-enrollment, auto-renewal, DNS-01/HTTP-01/TLS-ALPN-01 challenges, wildcard support, **IP identifiers (RFC 8738)**, **CAA checking with account/method binding (RFC 8657/8659)**, **External Account Binding (EAB, RFC 8555 §7.3.4)**, **Renewal Information (ARI, RFC 9773)**, **HTTP-01 challenge files served by UCM** (forward `/.well-known/acme-challenge/` from port 80, checked before submitting, renewed automatically), **DNS-01 resolver choice** (automatic, system only, or listed resolvers only, for networks without access to public resolvers) for split-horizon, ACME on internal/private IPs (incl. opt-in loopback upstream for a colocated CA), **multi-CA management** (per-request CA selection, pinned on order so renewals reuse the same CA: Let's Encrypt, Actalis, ZeroSSL, Google Trust Services, HARICA…), **external CSR and renewal key reuse**, **staging preflight dry-run**, **multi-CA proxy** (pre-validated upstream domains pass straight through, per-CA endpoints at `/acme/proxy/<slug>/directory`, incl. upstream revocation), **preferred certificate chain** (RFC 8555 §7.4.2 alternates, per CA account), **certificate profiles** (draft-ietf-acme-profiles: named issuance policies advertised in the directory and selectable per order, each optionally bound to a certificate template whose key usage and EKU then govern the issued certificate, plus a **default profile** and a default signing digest for orders that name none), **local server order management** (orders view with cleanup and a scheduled purge of expired orders); the proxy also publishes the client-side dns-01 TXT values so client propagation pre-checks (lego, Traefik, Caddy) pass as-is, and reuses an account's still-pending order on retries, and an optional **DNS UPDATE (RFC 2136) listener** lets standard rfc2136 solvers such as cert-manager's answer DNS-01 through the proxy with per-account TSIG keys
- **SCEP** -- RFC 8894 device auto-enrollment with approval workflows, GetCert/GetCRL, signed GetNextCACert, optionally on the plain HTTP port for clients such as sscep, renewals authenticated by the device's certificate, AES-128 encryption with password-based (PBKDF2) fallback for non-RSA clients; a request approved by hand issues with the template of the profile it came through, exactly as auto-approval does; named profiles validate **Microsoft Intune** challenges against the tenant's Intune API, and Windows (RSAES-OAEP key transport) and Apple devices enroll through them, see [docs/integrations/intune-scep.md](docs/integrations/intune-scep.md)
- **EST** -- RFC 7030 Enrollment over Secure Transport, incl. server-side key generation (CMS §4.4) and **CA labels** (§3.2.2: serve several CAs from one endpoint)
- **OCSP** -- RFC 6960 real-time certificate status, multi-certificate requests, nonce support, delegated responder validation with automatic renewal of the responder certificate, configurable response validity
- **TSA (RFC 3161)** -- timestamp authority with configurable policy OID; signs with the CA certificate (refused by strict verifiers such as `openssl ts -verify` and jarsigner) or a **dedicated end-entity signing certificate**, required by those verifiers, picked from issued certificates or generated in one click (critical, exclusive timeStamping EKU); renewals followed automatically, issuer chain embedded in tokens, strict dedicated-signer mode, signer health and expiry surfaced on the dashboard
- **CRL/CDP** -- Certificate Revocation List distribution with Delta CRL support (RFC 5280 §5.2.4), per-CA schedule (validity decoupled from publish cadence) and configurable signature digest, optional named URLs (CA-name slug in CDP/AIA paths, can be enabled on existing CAs), **externally-signed CRL upload for offline / key-less CAs** (validated against the CA certificate with CRL-number monotonicity, served at the existing CDP endpoint and consulted by OCSP)
- **AIA CA Issuers** -- Authority Information Access CA certificate download (RFC 5280 §4.2.2.1)

### Integrations
- **Microsoft ADCS** -- Full lifecycle over AD CS: CSR signing, template discovery, EOBO (Enroll On Behalf Of), renew/revoke through the connector, and an optional WinRM admin channel for CRL revocation sync, CA inventory import, and pending-request approve/deny with a CA health panel
- **Windows autoenrollment & Active Directory Connector** -- MS-XCEP/WSTEP policy and enrollment for domain-joined machines and users under the template the request names; on the Kerberos binding, machine and AD-derived templates take the subject from Active Directory (the computer's DNS host name, or the user's DN and UPN), across several domain controllers with failover and a scheduled health check per DC, never with an anonymous bind; enrollment is configured in **profiles per realm** (`/api/v2/windows-profiles`), each with its own CA, templates, Kerberos keytab, AD group and connector, and a Kerberos request is served by the enabled profile of its principal's realm (the UsernamePassword binding by the default profile), across **several Active Directory connectors** (one per forest or domain)
- **Microsoft Intune** -- SCEP challenge validation for Intune-managed devices, Entra app registrations defined once under SCEP › Intune app registrations and picked per profile, with a step-by-step guide in `docs/integrations/intune-scep.md`
- **HSM** -- SoftHSM included, PKCS#11, Azure Key Vault, Google Cloud KMS, OpenBao/Vault Transit; **HSM-backed CAs** with non-exportable signing keys, RSA-PSS and Brainpool on PKCS#11, and a declared device certification (Common Criteria, EUCC, FIPS 140-3) checked by the EU compliance profile; a connection test shows what a PKCS#11 module reports (library, manufacturer, firmware)
- **Kubernetes / cert-manager** -- Reference manifests for ClusterIssuer (HTTP-01 + DNS-01 with EAB), sample Certificate, Secret template under `examples/kubernetes/cert-manager/`
- **DNS Providers** -- Cloudflare, Route53, Azure DNS, Plesk and more for ACME DNS-01 challenges
- **Webhooks** -- Event-driven notifications for certificate lifecycle events (15+ event types), **per-endpoint delivery history with manual retry**, durable async delivery queue with exponential backoff, and a retention window on the history so it does not grow without end

### Security & Access
- **Authentication** -- Password, WebAuthn/FIDO2 (also as the second factor, next to or instead of TOTP), TOTP 2FA, mTLS, API keys (`X-API-Key` or `Authorization: Bearer`)
- **SSO** -- LDAP (LDAPS or StartTLS), OAuth2 (Azure/Google/GitHub), SAML single sign-on with Single Logout, role mapping to built-in and **custom roles** (SAML groups read from the assertion, Entra ID and AD FS claims included) and a configurable NameID format; **per-user `auth_source` tracking** and opt-in role sync on login
- **RBAC** -- 4 built-in roles (Admin, Operator, Auditor, Viewer) plus custom roles with granular permissions; **groups grant additional permissions** on top of a user's role (never administrator)
- **Policies & Approvals** -- Certificate issuance policies with approval workflows and enforced rules (allowed key types and signature hashes, DNS SAN cap, validity cap, scoped by CA, template or DNS pattern), binding **every operator path** (the issue form, signing a stored request alone or in bulk, and renewal) and, for key types and hashes, ACME, SCEP, EST, WSTEP and CA creation too; a policy that requires approval holds **ACME, EST, SCEP and WSTEP requests** in the approval queue, and each client is told so in its protocol's terms (ACME `processing`, EST 202 with Retry-After, SCEP PENDING, WSTEP pending); a policy can also put **revocations and renewals** under approval; a queued request is closed on its own when its target is signed, renewed, deleted or revoked meanwhile
- **Key and hash defaults** -- A request that names no key or hash follows one default on every issuance path (RSA-2048 with SHA-256 unless a profile or policy refuses it, then the first accepted type), the hash follows the signing key, and a new intermediate CA never takes a hash below its parent's
- **Audit Logs** -- Action logging with integrity verification, remote syslog forwarding and an opt-in retention period
- **Private Key Encryption** -- AES-128 (Fernet, HMAC-SHA256) at rest under a master key created at first start (in a container, when `/etc/ucm` is a volume) or given as `KEY_ENCRYPTION_KEY`, covering CA and certificate keys, SSH CA and deployment target keys, ACME account and EAB keys, SCEP challenges and LDAP bind passwords, with **Encrypt remaining keys** for secrets stored before it was enabled; with encryption enabled no plaintext key file is kept on disk (existing mirrors are removed at enable time and at startup, public certificate files stay), and key files are recreated when it is disabled
- **High availability** -- Run two or more nodes on one PostgreSQL database with `UCM_HA=1` (Docker, Docker Compose, DEB/RPM or the Helm chart's `ha.enabled`): one elected node runs the scheduled tasks, settings, encryption, backups and rolling updates reach every node, and sessions are shared, so only the Kerberos enrollment endpoints need source-address affinity (see [docs/HA.md](docs/HA.md))
- **FIPS mode** -- the `-fips` Docker image runs UCM's cryptography in the OpenSSL FIPS Provider 3.5.9 (CMVP certificate #5586), which approves ML-DSA, Ed25519 and Ed448, so post-quantum and EdDSA signatures are available in FIPS mode with the image; the DEB and RPM packages built with `UCM_FIPS_BUILD=1` run on the FIPS module of RHEL 9 (#5573) or Ubuntu 24.04 Pro (#5115), which do not provide them. With `UCM_FIPS=1` UCM starts only on an active, self-tested module, generates keys through it, allows an algorithm only when the loaded module approves it and refuses the rest (MD5, 3DES, scrypt, Argon2id, legacy PKCS#12, NTLM), and a readiness check lists beforehand what an instance would lose. UCM itself is not a validated module, and Debian 13 and arm64 are not among the tested configurations of certificate #5586
- **Compliance profiles** -- per-CA policies aligned with ANSSI PG-083, BSI TR-02102-1 and the ECCG agreed cryptographic mechanisms (key types, hashes, signature schemes, validity horizons, HSM-held CA keys, EC timestamp signer), refusals where the text imposes and notices where it recommends, with a read-only preflight before a profile is attached to an existing CA; UCM is not certified or qualified by any of these bodies
- **Hardening** -- Operator-configurable HSTS (Settings → Security or env override), trusted-proxy gating of client-cert headers, API key permissions capped to the creator's own; trusted proxies can be given as CIDR networks and, once proxy support is on, `X-Forwarded-*` headers are honoured only from them, so a client reaching the backend directly cannot spoof its address; the web interface and management API can be **restricted to listed IP addresses and networks** while PKI protocol endpoints stay reachable

### Operations & Monitoring
- **Overview** -- Six independent cards (work queue, automation health, hierarchy, expiry horizon, compliance, latest operations) with layout presets saved per user, reloaded on their own when the data changes
- **Reports** -- Scheduled PDF reports, executive summaries, revoked certificates, custom templates
- **Certificate Toolbox** -- SSL checker, CSR/cert decoder, key matcher, format converter
- **Email Notifications** -- SMTP with STARTTLS or implicit TLS (port 465), **OAuth2 (XOAUTH2)** for Gmail, Outlook.com & Microsoft 365, customizable HTML/text templates, certificate expiry alerts with several day thresholds (one e-mail per threshold and validity period, escalating 30/14/7/1 style), optionally leaving out the certificates ACME clients renew themselves
- **Deploy Hooks** -- Push issued and renewed certificates, and regenerated CRLs (DER or a PEM bundle with the parent CRLs), to remote hosts over SSH/SFTP, with destination paths and an optional reload command per binding: key-based auth (generated ed25519 or imported key, encrypted at rest), host-key pinning on first connect, per-binding destination paths (cert / key / full chain, the chain without the self-signed root unless the binding asks for it, written atomically), durable delivery queue with retries and per-delivery history, a **same-host preset** for services running next to UCM, and **HTTP API targets** that push a certificate to a firewall, load balancer or cloud API in one request built from a body template (URL, method, encrypted headers, `{{cert_pem|json}}`-style variables, private key only with an explicit opt-in over verified HTTPS)
- **Backup & Restore** -- Manual and scheduled encrypted backups with retention policies and an optional ceiling on the space the stored archives take; archives are streams of independently authenticated chunks, so creating one and checking it before a restore do not hold it whole in memory; archives carry ACME client orders and pending requests, restore in merge or replace mode, match rows by name across installations and replay the repair migrations
- **Diagnostic Log Bundle** -- One-click download (Settings → About → Diagnostic) of application logs, error log, systemd journal and a secret-free system diagnostic as a ZIP, with sensitive tokens redacted
- **System Log Viewer** -- Browse the application, access, error and systemd journal logs from the UI, filtered by level, time window and text, with secrets redacted
- **Prometheus Metrics** -- opt-in, bearer-gated `/metrics` endpoint exposing certificate, CA, scheduler, webhook and ACME counters
- **Scheduler** -- admin view of background tasks (expiry checks, CRL refresh, webhook delivery, backups, auto-renewal) with status and run-now, run in a process of their own under gunicorn
- **Self-serving HTTPS** -- apply any issued certificate to the web UI; the binding follows renewals automatically (files re-materialized, service restarted)
- **Safe networking defaults** -- dual-stack listening (`HOST=::` serves IPv6 and IPv4 on one socket), and admin Base URL guardrails (reachability check before applying, canonical redirect steps aside when the host stops resolving, `UCM_DISABLE_CANONICAL_REDIRECT=1` recovery switch)
- **Software Updates** -- In-app update checker with one-click install, scheduled daily check on a stable or release-candidate channel, and opt-in unattended install (DEB/RPM) with mandatory SHA256 verification and truthful outcome events (installed only after the actual install is version-verified), plus an optional one-time per-user release-notes window after an update
- **Global Search** -- Cross-resource search and command palette (Ctrl+K)

### Platform
- **6 Themes** -- 3 color schemes (Gray, Purple Night, Orange Sunset) × Light/Dark; **per-user preferences persisted server-side** (language, theme, mode)
- **i18n** -- 9 languages (EN, FR, DE, ES, IT, PT, UK, ZH, JA)
- **Persisted UI state** -- Filter selections persist across reloads on the main list pages (certificates, CAs, templates, policies, audit logs, trust store, users, SSH)
- **Database** -- SQLite (default) or **native PostgreSQL backend** with bidirectional migration UI
- **Responsive UI** -- React 18 + Radix UI, mobile-friendly
- **Real-time** -- WebSocket live updates: a change made by another operator refreshes the lists that show it, and a reconnection after an outage reloads them rather than leaving stale rows on screen
- **Multi-platform** -- Docker, Debian/Ubuntu (.deb), RHEL/Rocky/Fedora (.rpm); the packages install log rotation for the access and error logs
- **Reverse proxy ready** -- Public ports independent of the listen ports (an explicit `:80` or `:443` in the base URLs is advertised as typed), trusted proxies by IP or CIDR network, and Helm chart `proxy.*` values for an Ingress in front of UCM

---

## Quick Start

### Docker

```bash
docker run -d --restart=unless-stopped \
  --name ucm \
  -p 8443:8443 \
  -p 8080:8080 \
  -v ucm-data:/opt/ucm/data \
  -v ucm-config:/etc/ucm \
  neyslim/ultimate-ca-manager:latest
```

Also available from GitHub Container Registry: `ghcr.io/neyslim/ultimate-ca-manager`. The FIPS variant is tagged `<version>-fips` (run it with `UCM_FIPS=1`).

### Debian/Ubuntu

Download the `.deb` package from the [latest release](https://github.com/NeySlim/ultimate-ca-manager/releases/latest):

```bash
sudo dpkg -i ucm_<version>_all.deb
sudo systemctl enable --now ucm
```

### RHEL/Rocky/Fedora

Download the `.rpm` package from the [latest release](https://github.com/NeySlim/ultimate-ca-manager/releases/latest): `ucm-VERSION-1.fc43.noarch.rpm` for Fedora, `ucm-el9-VERSION-1.el9.noarch.rpm` for RHEL, Rocky Linux and AlmaLinux 9, `ucm-el10-VERSION-1.el10.noarch.rpm` for the same distributions at 10.

```bash
sudo dnf install ./ucm-VERSION-1.fc43.noarch.rpm
sudo systemctl enable --now ucm
```

**Access:** `https://localhost:8443` or `https://your-server-fqdn:8443`
**First login:** `admin`, with the password generated at first start: `sudo cat /opt/ucm/data/initial-admin-password` (Docker: `docker exec <container> cat /opt/ucm/data/initial-admin-password`). It must be changed at first login. See [First access](docs/installation/README.md#first-access) to provide your own.

See [Installation Guide](docs/installation/README.md) for all methods including Docker Compose and source install.

---

## Documentation

| Resource | Link |
|----------|------|
| Wiki (full docs) | [github.com/NeySlim/ultimate-ca-manager/wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki) |
| Installation | [docs/installation/](docs/installation/README.md) |
| User Guide | [docs/USER_GUIDE.md](docs/USER_GUIDE.md) |
| Admin Guide | [docs/ADMIN_GUIDE.md](docs/ADMIN_GUIDE.md) |
| Microsoft Intune SCEP | [docs/integrations/intune-scep.md](docs/integrations/intune-scep.md) |
| ACME proxy clients | [docs/integrations/acme-proxy-clients.md](docs/integrations/acme-proxy-clients.md) |
| API Reference | [docs/API_REFERENCE.md](docs/API_REFERENCE.md) |
| Security | [docs/SECURITY.md](docs/SECURITY.md) |
| Upgrade Guide | [UPGRADE.md](UPGRADE.md) |
| Changelog | [CHANGELOG.md](CHANGELOG.md) |

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| Frontend | React 18, Vite, Radix UI, Recharts |
| Backend | Python 3.11+, Flask, SQLAlchemy |
| Database | SQLite or PostgreSQL |
| Server | Gunicorn + gevent WebSocket |
| Crypto | pyOpenSSL, cryptography |
| Auth | Session cookies, WebAuthn/FIDO2, TOTP, mTLS |

---

## File Locations

| Item | Path |
|------|------|
| Application | `/opt/ucm/` |
| Data & DB | `/opt/ucm/data/` |
| Config (DEB/RPM) | `/etc/ucm/ucm.env` |
| Logs (DEB/RPM) | `/var/log/ucm/` |
| Service | `systemctl status ucm` |

Docker: data at `/opt/ucm/data/` (mount as volume), config via environment variables, logs to stdout.

---

## Contributing

Pull requests target `dev`, and the first one asks you to sign the
[CLA](CLA.md) once. See [CONTRIBUTING.md](CONTRIBUTING.md) for the rest: how to
report a bug usefully, what a reviewable pull request looks like, and the rules on
tests, translations and migrations.

---

## License

UCM is free software under the [GNU AGPL v3.0 only](LICENSE). Running it, at any scale and commercially, costs nothing; a [commercial licence](COMMERCIAL-LICENSE.md) is available for those who modify it and cannot publish their changes.

Versions before 2.243 remain under their original licence, BSD 3-Clause with the Commons Clause.

---

## Support

- [GitHub Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)
- [GitHub Wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki)

If you find UCM useful, consider supporting its development:

<a href="https://ko-fi.com/neyslim"><img src="https://ko-fi.com/img/githubbutton_sm.svg" alt="Support on Ko-fi" /></a>

