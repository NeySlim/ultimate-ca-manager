# UCM Upgrade Guide

This guide covers upgrading UCM to newer versions across different installation methods.

## Table of Contents

- [Docker Upgrade](#docker-upgrade)
- [DEB Package Upgrade](#deb-package-upgrade)
- [RPM Package Upgrade](#rpm-package-upgrade)
- [Source Installation Upgrade](#source-installation-upgrade)
- [Version-Specific Notes](#version-specific-notes)

---

## Docker Upgrade

### Using Docker Compose

```bash
# 1. Backup current data
docker-compose exec ucm cp /opt/ucm/data/ucm.db /opt/ucm/data/backups/manual-backup-$(date +%Y%m%d).db

# 2. Pull new image
docker-compose pull

# 3. Restart containers
docker-compose down
docker-compose up -d

# 4. Check logs
docker-compose logs -f ucm
```

### Manual Docker Commands

```bash
# 1. Stop container
docker stop ucm

# 2. Backup data
docker cp ucm:/opt/ucm/data/ucm.db ./backup-$(date +%Y%m%d).db

# 3. Remove old container
docker rm ucm

# 4. Pull new image
docker pull neyslim/ultimate-ca-manager:latest

# 5. Start new container
docker run -d \
  --name ucm \
  -p 8443:8443 \
  -v ucm-data:/opt/ucm/data \
  -v ucm-config:/etc/ucm \
  -e UCM_FQDN=ucm.example.com \
  neyslim/ultimate-ca-manager:latest
```

`/etc/ucm` holds `master.key`. If the old container ran without a volume there, copy the key out before `docker rm` (`docker cp ucm:/etc/ucm/master.key ./master.key`) and into the new container afterwards.

---

## DEB Package Upgrade

### Automatic Upgrade

```bash
# Download new version (replace VERSION, e.g. 2.48)
wget https://github.com/NeySlim/ultimate-ca-manager/releases/latest/download/ucm_VERSION_all.deb

# Install (automatically backs up database)
sudo dpkg -i ucm_VERSION_all.deb

# Fix dependencies if needed
sudo apt-get install -f
```

**What happens during upgrade:**
1. Pre-upgrade backup created automatically
2. Service stopped gracefully
3. Files updated
4. Database migrated (if schema changed)
5. Configuration preserved
6. Service restarted

### Manual Backup Before Upgrade

```bash
sudo systemctl stop ucm
sudo cp /opt/ucm/data/ucm.db ~/ucm-backup-$(date +%Y%m%d).db
sudo cp /etc/ucm/ucm.env ~/ucm-config-backup.env
sudo systemctl start ucm
```

### Rollback

```bash
sudo systemctl stop ucm

# Restore database
sudo cp /opt/ucm/data/backups/ucm-pre-upgrade-*.db /opt/ucm/data/ucm.db

# Reinstall previous version
sudo dpkg -i ucm_<previous-version>_all.deb

sudo systemctl start ucm
```

---

## RPM Package Upgrade

### Using DNF/YUM

```bash
# Download new version (replace VERSION, e.g. 2.48)
wget https://github.com/NeySlim/ultimate-ca-manager/releases/latest/download/ucm-VERSION-1.noarch.rpm

# Upgrade
sudo dnf upgrade ./ucm-VERSION-1.noarch.rpm
```

### Manual Backup

```bash
sudo systemctl stop ucm
sudo cp /opt/ucm/data/ucm.db ~/ucm-backup-$(date +%Y%m%d).db
sudo systemctl start ucm
```

---

## Source Installation Upgrade

### Git-based Installation

```bash
# 1. Stop service
sudo systemctl stop ucm

# 2. Backup database
sudo cp /opt/ucm/data/ucm.db ~/ucm-backup-$(date +%Y%m%d).db

# 3. Pull updates
cd /opt/ucm
git fetch --tags
git checkout <version-tag>

# 4. Update dependencies
cd backend
pip install -r requirements.txt --upgrade

# 5. Restart service
sudo systemctl start ucm
```

Database migrations run automatically at startup.

---

## Version-Specific Notes

### Custom Command DNS providers are written by administrators only

Creating a DNS provider of type `custom_command`, or changing one (`PATCH /api/v2/dns-providers/{id}`), now requires the `write:deploy` permission, which only administrators hold. An operator, a custom role or an API key holding `write:acme` without it receives `403`; such keys must be replaced by an administrator's key that carries `write:deploy`. Existing providers keep working for domain tests, provider tests, orders and renewals, and every other provider type keeps its permissions. Review the Custom Command providers already in place, and the `dns_provider_create` and `dns_provider_update` audit entries made by non-administrators: one created before the upgrade by an operator or an API key still runs.

### Package updates are checked again by root

The `ucm-watcher` unit that installs an update from Settings > Updates now accepts only a release package of `/opt/ucm/data/updates/` matching the `.sha256` of its release, fetched by root directly from GitHub over HTTPS, without the proxy configured for UCM, declaring the package `ucm` at the target version, above the installed one; it no longer forces an RPM install (`rpm -U --force`). A refused update installs nothing, leaves UCM running and is reported as failed at step `precheck` at the next hourly update check. A host whose root cannot reach github.com sees every update refused: install the package by hand there. The watcher's output, the package manager's included, is now in `journalctl -u ucm-watcher` only, no longer in `/var/log/ucm/ucm.log`; it also appears in the Journal source of the system logs page and in the diagnostic bundle.

### An SSH CA description is one line of text

`POST /api/v2/ssh/cas`, `PUT /api/v2/ssh/cas/{ca_id}` and `POST /api/v2/ssh/cas/import` now answer `400` for a `descr` holding a control character or a line break inside it (one at either end is trimmed, as before). A description stored before keeps working: the setup scripts print it on one line, and saving it again from the CA's panel needs those characters removed.

### Export requests with a password in the wrong place are refused

The routes that can return a private key (certificate, CA, CSR, user-certificate and mTLS exports, key recovery) now answer `400` instead of a key in clear for a request whose password they would not read: a form or plain-text body, a `GET` or `HEAD` carrying a body, a JSON body that is not an object, a `password` that is neither a string nor `null`, a name given twice in the JSON body, or a name containing `password` or `passphrase` placed anywhere but the top-level `password` string of the JSON body (including the query string, whatever the method, and a `password` nested inside another value). A script that sent `curl -d '{"password":"..."}'` without `Content-Type: application/json`, or `password=...` as a form, must send a `POST` with a JSON object body and that content type. Requests that were well formed, and unrelated extra parameters, are answered as before.

### A password given with a PEM export encrypts the private key

A PEM export that carries the private key (`format: pem` with `include_key`, and a user certificate's PEM, which includes its key by default) ignored a `password` and returned the key in clear; with a password it now returns the key as an encrypted PKCS#8 block (`BEGIN ENCRYPTED PRIVATE KEY`), and without one nothing changes. The CA export now reads `include_key` as a JSON boolean (`true` or `false`, or `true`/`false` in the query string): a string such as `"false"` answered with the CA key and now answers 400. In the query string of a `GET`, any value other than `true` or `false` (`0`, `1`, `no`, an empty value) answers 400 as well. A user certificate's PEM export now applies the export password rule: a password outside 8 to 256 characters answers 400. The key of an offline CA kept under its offline password is exported as stored: a password given with its `pem` or `key` export answers 409 (the `key` export answered 500), so export it without one.

### ACME: a DNS name in the CN alone counts against a policy

A policy's maximum number of DNS names now counts, over ACME, a DNS name the CSR carries in its CN but not in its SAN. An ACME client whose CSR carried in its CN a DNS name absent from its SAN, beyond a policy's limit, was issued and is now refused at finalize (`badCSR`, the order becomes `invalid`): raise the policy's limit, or have the client request fewer names per order.

### A restore keeps SSO accounts with their IdP

An archived SSO provider is matched to the provider of the same name here. When the two sign in through different IdPs (another OIDC issuer, SAML entity ID, or LDAP server and base DN; a trailing slash of an OIDC issuer and the case of its scheme and host do not count), the provider here is no longer rewritten in place with its accounts still bound to it. A replacing restore removes it and creates the archive's provider: the accounts it opened here that the archive does not bind itself are left without provider, as orphans of its IdP, and its SSO sessions are closed. A merge keeps the provider here unchanged and does not restore the archive's: the accounts the archive binds to it come back as orphans of the archive's IdP. Each case adds a warning starting with `sso_providers:` and naming the provider to the restore report and the log, and a sign-in refused on such an account describes it in the audit log as having `no provider (orphan of '<IdP>')`. A provider created later for that same IdP takes these accounts back at their next sign-in; otherwise use **Link to SSO** on each account, with a provider of the IdP the person signs in through. A provider of the same IdP written otherwise is updated in place, as before.

### Trust store: private keys removed, certificates only

An entry of the trust store whose file held a private key next to its certificate kept that key in the database, and every account allowed to read the trust store could read it through the API, the exports and the backups. At the first start after the upgrade, the key is removed from each such entry; the entry keeps its identifier and its certificates, and the log and the audit log name every entry cleaned (identifier and name, never the key). Treat each key named there as compromised: revoke the certificate it belongs to and replace it. Backup archives made before the upgrade are not rewritten and may still carry such a key: restoring one removes it again, but protect or delete the old archives. A trust store import or `POST /api/v2/truststore` that carries a private key is now refused with `400`, and `certificate_pem` in the API, the exports and the backups holds certificates only. Two answers change with it: an entry whose first certificate reads but which also holds a block that is not a certificate, or one left open, is refused with `400` instead of being stored with its first certificate; and the PEM export answers `400` (`No valid certificates to export`) instead of `200` when no selected entry holds a certificate.

### Deleting a CA a setting names

As for the default SCEP CA, deleting a CA chosen as the default ACME issuing, EST, TSA, WSTEP, XCEP or trusted mTLS CA, or reached through an EST label, is now refused with `409` and a message naming the setting, in a single and a bulk deletion: choose another CA in that setting, or clear it, then delete. An ACME issuing CA setting that already names a deleted CA refuses the orders it would sign (`serverInternal`, the order stays `ready`) instead of signing them with the first CA: choose the CA again in the ACME settings.

### An ACME issuing CA that cannot sign refuses its orders

An order for an ACME domain whose chosen issuing CA has no private key or is offline was signed by the default ACME issuing CA, and an order for a default CA without a private key by the first CA able to sign. Such an order is now refused (`serverInternal`, the order stays `ready` and the client may retry), and the log and the audit name the CA: choose a CA able to sign for the domain in the ACME domain settings, or as the default in the ACME settings, or bring the CA back online. Only when no CA is chosen at all does the first CA able to sign issue the certificate, as before.

### SSO role mapping reads more groups

OIDC role mapping rules now also match the `groups` and `roles` of the ID token validated for the login, and a `roles` claim no longer hides `groups`; SAML matching is unchanged, except that an assertion repeating an attribute name is now accepted with all its values, and the LDAP changes are in the next note. A user no rule matched before may now be admitted, or, with *Sync role on each login*, get a higher role at the next sign-in: review the mapping rules of OIDC providers before upgrading.

### LDAP role mapping compares group names as the directory does

Rule keys and required groups now compare with the directory's group names ignoring case, edge spaces and the length of inner space runs, and groups are read whenever a provider has rules or required groups, even without a group filter: a rule can match a group it missed before, so review the rules of an LDAP provider and check a few users with *Test Mapping*. A provider saved with two keys equal in that sense keeps signing in (both rules apply, the highest-privilege role wins), and saving it with that mapping is refused until one key is removed.

### SSO: Link to SSO moves accounts, a shared email is refused

`POST /api/v2/users/{id}/link-sso` now accepts an account already linked to a provider or left without one (it answered `400` before): it moves the account, or clears its SSO identity when the provider is the same, and closes the account's sessions. A sign-in whose email belongs to an account of another provider or left without provider by another or an unknown IdP (after a restore, for instance), or to an account an administrator linked to this provider while the OIDC IdP marks that email unverified, is now refused (`sso_email_conflict`) instead of receiving a second account with the default role: use Link to SSO on that account if it is the same person, or create an account under the name the provider sends and link it with its local password removed. An email shared with a local account still gives the SSO identity an account of its own. A provider with no role mapping rule and no default role now refuses with `sso_no_default_role` (it was `sso_unmapped`). Forgot password no longer sends a reset link to an account linked to an SSO provider that has no local password (the answer is unchanged), and a reset link such an account holds is refused: its provider alone opens it. An SSO account that kept a local password keeps the reset.

### A restore signs out every session, the restoring one included

After a successful restore, every session opened before it is refused, whatever the session store, including the session of the operator who ran the restore: sign in again once the restore has completed. A script that restores through the API with a session cookie needs a new sign-in before its next call; an API key is not a session and is kept or replaced as the archive says. A failed restore, or an archive that carried no data, signs nobody out.

### `-fips` Docker image: the FIPS module is checked against the build

With `UCM_FIPS=1`, the `-fips` image now refuses to start when its `fips.so` differs from the one installed when the image was built, or when the record of that build (`/usr/share/ucm/fips-module.mac`) is missing or malformed. An image derived from the `-fips` image that replaces or modifies `fips.so` no longer starts in FIPS mode: build it from the UCM sources instead, or use the published `-fips` image unchanged. FIPS mode also refuses to start when `OPENSSL_MODULES` is set to anything but the absolute path of the directory of the checked module. The standard image is not affected.

### Upgrading to v2.243

Several fixes change what an existing installation does once upgraded. The CHANGELOG lists them under **Upgrade notes**; before upgrading:

- Back up `audit-chain.keys` with `master.key` from now on (same directory), and on Docker Compose follow the `ucm-config` volume steps below.
- Review custom roles and their assignments, and the members of the default Certificate Operators and Auditors groups: they now grant their permissions.
- SAML: set the admin Base URL and check that the IdP matches `/api/v2/sso/saml/metadata` and that its clock is within five minutes.
- Check policies (notification e-mails, 50-name maximum now applied to ACME and the other protocols), ACME "Allow wildcard" per domain, discovery profile notifications and Reports > Schedule.
- Integrations whose server or account changes ask for their secret again; SMTP OAuth needs a new consent after such a change.
- API clients: a failing key is refused even with a session, and `Authorization: Bearer` is read as a key only for `ucm_ak_` tokens; exporting a CA private key needs `read:private_keys`.

### Docker Compose: `/etc/ucm` is now a named volume

The bundled compose files now mount `ucm-config` at `/etc/ucm`, which holds `master.key`. Before, it lived in an anonymous volume that `docker compose down` left behind. If your compose file had no `/etc/ucm` volume, copy the key out before switching, then into the new volume:

```bash
docker compose cp ucm:/etc/ucm/master.key ./master.key   # old file, container running
docker compose down && docker compose up -d                # new file
docker compose cp ./master.key ucm:/etc/ucm/master.key
docker compose exec -u root ucm chown 1000:1000 /etc/ucm/master.key
docker compose exec -u root ucm chmod 600 /etc/ucm/master.key
docker compose restart ucm
```

With `docker-compose.simple.yml` the service is `ultimate-ca-manager` rather than `ucm`. Without the key UCM starts in safe mode and says so; the key stays in the old anonymous volume (`docker volume ls`) until you prune it.

### Upgrading past v2.200 (protocol conformance sweep)

v2.200 tightened many protocol paths in ways that broke existing deployments; later releases restore compatible defaults. If you upgraded to 2.200–2.202 and saw any of the following, upgrading to the latest release fixes them without manual action: TSA answering 503 on every request, ACME finalize failing with `CAA check failed` on networks without public DNS, renewals rejected by `name constraints`, SCEP devices failing with `badMessageCheck`/`badTime`, EST scripts getting 415, syslog TCP+TLS streams corrupted after upgrade.

Notes:

- **Strictness is now opt-in.** The 2.200 fail-closed behaviours remain available as explicit settings: CAA enforcement (ACME settings), SCEP signingTime enforcement + clock skew (SCEP settings), SCEP GetCACert full chain, EST chain-in-response, CT require-SCTs. Review them if you operate a public-facing CA.
- **OIDC SSO**: ID-token verification (introduced in 2.200, fail-closed) is now configurable in Settings → SSO, including the issuer and JWKS URI it requires. Existing OIDC providers need their issuer set there for logins to work with verification enabled.
- **EST `/serverkeygen` response format changed in 2.200** and stays RFC 7030-conformant: the private key is delivered as CMS EnvelopedData (`smime-type=server-generated-key`) and the multipart part order follows the RFC. Clients written against the pre-2.200 proprietary format must be updated; mTLS clients using non-RSA certificates are not supported for key transport.
- **OCSP cache** is purged once at upgrade (migration 066) so responses cached before the revocation-invalidation fix cannot outlive it; the cache repopulates on demand.
- **Wildcard ACME authorizations** stored before 2.200 are normalized at upgrade (migration 067) so authorization reuse works again.

### Upgrading to v2.193

**No breaking changes for typical deployments** — safe to upgrade directly.

**ACME proxy — loopback upstreams now rejected.** The ACME proxy's upstream calls (directory, nonce, signed POST) now go through the same SSRF-hardened HTTP path as the ACME client: cloud-metadata and **loopback** targets are rejected. If your proxy upstream directory URL points at `localhost` / `127.0.0.1` (e.g. a self-referencing test setup), the proxy directory endpoint will return an error after upgrade. Point it at a routable address instead (a LAN IP or hostname — RFC1918 and `.lan`/`.local` remain fully supported). Regular upstreams (Let's Encrypt, internal CAs on LAN addresses) are unaffected.

**SoftHSM provider config normalized automatically.** Migration 057 rewrites legacy `library_path`/`pin` config keys to `module_path`/`user_pin` on all PKCS#11 providers; the `SoftHSM-Default` provider's *Test connection* works again after upgrade with no manual action.

### Upgrading to v2.56 from v2.5x

**No breaking changes** — safe to upgrade directly.

**Fixed in v2.55–v2.56:**
- Certificate subject/issuer fields now use standard RFC 4514 format (CN=, C=, O= instead of verbose names)
- Existing certificates with wrong format are auto-corrected by migration on startup
- ACME/CSR-signed certificates now include Extended Key Usage (`serverAuth`) — fixes Edge/Chrome rejecting certs
- CSRs with empty subject (common from ACME clients) now get CN populated from SAN

**Note:** Existing ACME certificates need to be re-issued to benefit from the EKU fix.

### Upgrading to v2.52 from v2.48–v2.51

**No breaking changes** — safe to upgrade directly.

**New in v2.49–v2.52:**
- Certificate Discovery with network scanning (scan profiles, scheduling, results management)
- EST protocol (RFC 7030) for device enrollment
- Certificate Templates (server, client, VPN, code signing, email)
- Certificate Toolbox (SSL checker, CSR decoder, key matcher, format converter)
- SSO integration (LDAP/Active Directory, OAuth2, SAML 2.0) with role mapping
- HSM support (SoftHSM, PKCS#11, Azure Key Vault, Google Cloud KMS)
- ACME client for Let's Encrypt integration
- Intermediate CA signing from CSRs
- Email notifications with customizable templates
- Certificate policies and approval workflows

### Upgrading to v2.48 from v2.1.x

**No breaking changes** — safe to upgrade directly.

> **Note:** UCM switched from Semantic Versioning (2.1.x) to Major.Build versioning (2.48) starting with this release. The version jump from 2.1.x to 2.48 is intentional and expected.

**New in v2.48:**
- Comprehensive backend test suite (1364 tests, ~95% route coverage)
- ucm-watcher system for safe service restarts and auto-updates
- Experimental badges for untested features (mTLS, HSM, SSO)
- TOTP 2FA login flow with QR code setup
- Auto-update mechanism via GitHub releases

**Auto-update (DEB/RPM):**
UCM can now check for and install updates automatically. The ucm-watcher systemd service monitors signal files:
- `/opt/ucm/data/.restart_requested` — triggers a service restart
- `/opt/ucm/data/.update_pending` — triggers package installation + restart

No manual action required — updates are triggered from the Settings > System page.

### Upgrading to v2.1.0 from v2.0.x

**No breaking changes** — safe to upgrade directly.

**New features:**
- AKI/SKI-based certificate chain matching (automatic migration at startup)
- Chain repair scheduler (hourly background task)
- Chain repair widget on CAs page
- Smart import deduplication (prevents duplicate CAs)
- Webhook management UI
- 9-language i18n

**Automatic migration:**
- On first startup, UCM populates SKI/AKI fields for all existing CAs and certificates
- Orphan CAs and certificates are automatically re-chained if their parent CA exists
- Duplicate CAs (same Subject Key Identifier) are merged

No action required — all migration happens automatically.

### Upgrading from v1.8.x to v2.0.x

**Major version upgrade** -- data is automatically migrated.

- Database path moved from `/var/lib/ucm/` to `/opt/ucm/data/`
- Frontend replaced: HTMX -> React 18
- Authentication: JWT -> session cookies
- A backup is created automatically during upgrade

Steps:
1. Standard upgrade procedure (install new package)
2. No configuration changes required
3. Check logs: `journalctl -u ucm -n 50`

---

## Troubleshooting

### Upgrade Failed - Service Won't Start

```bash
# Check logs
sudo journalctl -u ucm -n 100 --no-pager

# Common fixes:

# 1. Permission issues
sudo chown -R ucm:ucm /opt/ucm/data
sudo chown -R ucm:ucm /var/log/ucm

# 2. Missing dependencies
sudo apt-get install -f     # Debian/Ubuntu
sudo dnf install -y ucm     # RHEL

# 3. Database corruption
sudo systemctl stop ucm
sudo cp /opt/ucm/data/backups/ucm-pre-upgrade-*.db /opt/ucm/data/ucm.db
sudo systemctl start ucm
```

### Configuration Lost

```bash
sudo cp ~/ucm-config-backup.env /etc/ucm/ucm.env
sudo systemctl restart ucm
```

### Port Conflict After Upgrade

```bash
sudo netstat -tlnp | grep 8443
# Change port in /etc/ucm/ucm.env: HTTPS_PORT=8444
sudo systemctl restart ucm
```

---

## Best Practices

### Before Upgrading

1. Read release notes for breaking changes
2. Backup database manually
3. Test in staging environment first
4. Ensure enough disk space for backup

### After Upgrading

1. Check service status: `systemctl status ucm`
2. Review logs for errors
3. Test login and basic operations
4. Verify existing CAs and certificates

---

## Support

- **Logs:** `journalctl -u ucm -f` or `docker logs -f ucm`
- **Issues:** https://github.com/NeySlim/ultimate-ca-manager/issues
- **Wiki:** https://github.com/NeySlim/ultimate-ca-manager/wiki
