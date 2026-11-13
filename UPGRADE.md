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

### Upgrading to v3.0

- In-app help is available in English, French and Chinese only; with the interface in German, Spanish, Italian, Japanese, Portuguese or Ukrainian the help panel shows the English text. The interface itself keeps its nine languages.
- Private-key encryption becomes an envelope: the key in `master.key` or `KEY_ENCRYPTION_KEY` (the KEK) wraps a data key stored in the database. Nothing is re-encrypted at the upgrade and the KEK stays the only secret to back up. A KEK is now changed by hand with the previous one in `master.key.previous` or `KEY_ENCRYPTION_KEY_PREVIOUS` (see the Admin Guide); swapping the key without it puts UCM in safe mode while encryption is enabled, and in HA also once it was disabled. Disabling encryption with `KEY_ENCRYPTION_KEY` set no longer answers 409: the variable stays configured and unused.
- No default administrator password: a new installation no longer creates `admin` / `changeme123`. Automation that logged in with `changeme123` after a fresh install must provide the password (`INITIAL_ADMIN_PASSWORD_FILE` or `INITIAL_ADMIN_PASSWORD`) or read the generated one from `DATA_DIR/initial-admin-password` and change it, as the first login requires for a generated password. An existing installation is not touched: its administrator, its password and its sessions stay as they are, and no file is generated.
- The line `INITIAL_ADMIN_PASSWORD=changeme123` that 2.x packages wrote into `/etc/ucm/ucm.env` is removed by the DEB and RPM upgrade; any other value stays, and none is read while an account exists. Without the removal, a later database reset would have recreated the administrator with that public password. A Docker or Compose setup that still passes `INITIAL_ADMIN_PASSWORD=changeme123` keeps it: remove it, it is unused once the administrator exists.
- Windows enrollment (XCEP, WSTEP, Kerberos): the upgrade turns the configuration into the profile `default`, whose Kerberos realm is now explicit: the base DN of the enabled AD connector, else the `@REALM` of the SPN, else the single realm of the keytab, else the base DN of a disabled connector when the keytab holds that realm, or, with no keytab at all, once the first start finds none (a keytab the upgrade could not read leaves the realm to the start or the upload that takes it). When none of them names it, Kerberos is refused while the UsernamePassword and certificate bindings answer as before; the profile screen (or `GET /api/v2/windows-profiles/{id}`, `kerberos_refusal`) gives the reason, and `PUT /api/v2/windows-profiles/{id}` with `{"realm": "CORP.EXAMPLE"}` sets it (in capitals, a realm of the keytab). Kerberos clients of any other realm, such as a trusted forest served while the connector was disabled, are refused until a profile serves their realm. A 2.x backup restored on 3.0 is converted the same way.
- API clients of the single-row routes: `/api/v2/xcep/config`, `/api/v2/wstep/config`, `/api/v2/kerberos/config`, `/api/v2/kerberos/keytab` and `/api/v2/ad-connector` (with `/test` and `/test-saved`) are removed. Use `/api/v2/windows-profiles` (the profile fields, `POST /{id}/keytab`, and `/settings` for the XCEP, WSTEP and Kerberos switches and the SPN) and `/api/v2/ad-connectors`. An API key of 2.x that only had `write:kerberos` must also carry `write:xcep` to call `POST /api/v2/windows-profiles/{id}/keytab`, which replaces `POST /api/v2/kerberos/keytab` and needs both.
- Windows enrollment, XCEP without its own CA: 2.x answered GetPolicies with 503 when only the WSTEP CA was set. The upgrade, like the restore of a 2.x backup, switches XCEP off in that case, so clients still get no policy; switch it on to serve the policy of the WSTEP CA.
- Windows enrollment, renewal by certificate: 2.x renewed over the Certificate binding any certificate of the WSTEP CA, including one signed in the interface and then renewed with `certreq -Renew`. 3.0 renews there only a certificate issued through Windows enrollment and refuses the others (`The certificate was not issued through Windows enrollment`, audited); reissue such a certificate through Windows enrollment (autoenrollment or `certreq` against the policy), whose renewals then work.
- SCEP: a PKCSReq signed by a certificate issued through the same endpoint is now a renewal. Its CSR must keep that certificate's subject and SANs, and the signer must not be revoked, expired or superseded: 2.x issued such a request as a new certificate when its challenge was valid, 3.0 refuses it with `badMessageCheck`. A device that changes its subject must sign its request with a self-signed key.
- Windows enrollment, renewal limits: renewal with the TLS client certificate works only for a profile whose issuing CA is the mTLS CA of the server (or a CA under it), since the TLS trust is not widened; other profiles renew over Kerberos. A renewal by certificate re-checks the SID of the account against the connector of the profile but not the AD group (a renewal over Kerberos checks the group as an enrollment does), so a computer or user removed from the group keeps renewing until its certificate is revoked. EST `/simplereenroll` and SCEP RenewalReq now refuse to renew a certificate of a Windows profile (403, `badMessageCheck`, audited as `windows_enrollment.refused`); renew it over WSTEP. An administrator's manual renewal is not blocked, and the scheduled automatic renewal leaves these certificates alone.
- Windows enrollment, keytab: the keytab of 2.x becomes that of the default profile at the first start, and UCM composes the file the acceptor reads from the keytabs of all profiles. A forest added later gets its own profile and keytab; nothing is merged by hand.
- Windows enrollment, requests without template: on the Kerberos binding, 2.x issued a request that names no template (no certificate template extension, by OID or name) and whose Extended Key Usages match none of the templates offered as a server certificate (`serverAuth`), with its subject built from Active Directory. 3.0 refuses it with `The request names no certificate template and its Extended Key Usages match none this profile offers`, audited as `windows_enrollment.refused`, as AD CS does. A request that names its template (the extension XCEP announces with each template, for CertEnroll to copy into its request) or carries the EKUs of an offered template, as the Windows CertEnroll requests captured for the tests do, is served as before; a script that sends its own PKCS#10 must add the template extension (1.3.6.1.4.1.311.21.7 with the OID the policy announces, or 1.3.6.1.4.1.311.20.2 with the template name) or the EKUs of the template. The UsernamePassword binding keeps the 2.x behavior, and so does a Kerberos renewal signed by a certificate issued without template, provided that certificate is valid (not revoked, expired or superseded), was issued by Windows enrollment under the same profile, and belongs to the requester (its SID, else its subject or the computer's `dNSHostName` in the directory); any other is refused as an initial request. A renewal held for approval keeps that decision, and is refused once the renewed certificate is revoked.
- CA import: a CA whose RSA key is under 2048 bits is refused when imported with its private key; import its certificate without the key to keep it for chain building. Existing CAs are not touched.
- CA import: an imported CA is attached to a parent only when the parent's key verifies its signature, on every import path. Smart import used to attach by identifier or name without checking, so a CA under a parent whose key type the server cannot verify (SLH-DSA, GOST) is now imported without a parent, and the hourly chain repair leaves it so.
- CA import: a new CA or certificate whose issuer is stored as a root and as a cross or link certificate of the same key is chained under the root, a pending CA's installed certificate included. What is already chained is not moved: the hourly chain repair applies the rule only to a CA or certificate with no parent recorded. A CA with no recorded parent and no authority key identifier now resolves its issuer to the root for its chain status, and an export that completes a missing chain adds the root, where either could pick the cross or link certificate before.
- Audit and syslog consumers (SIEM): a restore refused before its archive was read is now audited as a failed `system_restore` whose text starts with `Restore request refused: ` followed by the reason; match on that prefix. Version 2.x wrote no audit line for these refusals.

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
