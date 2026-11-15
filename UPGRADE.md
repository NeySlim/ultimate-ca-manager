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

- **Start from 2.254.** 3.0 upgrades a database last started by UCM 2.254, nothing older. From an earlier 2.x, install 2.254 first (package or image), start it once so it completes its own migrations, then install 3.0. The same applies to every node of a shared PostgreSQL database and to a database copied from SQLite to PostgreSQL: it is the database that must have been started by 2.254. 3.0 reads the backup archives of every 2.x version; what a restore refuses is under *Backup archives* below.
- **What a refused start looks like.** On a database that 2.254 has not started, 3.0 stops before writing anything: `This database was last started by a release older than 2.254 (N migration(s) of 2.254 are missing from its registry, first ...). Install 2.254, start it once, then upgrade. Nothing was changed: 2.254 still starts on this database.` A database without a migration registry gives the same message with `it has no migration registry`. A package installation shows it in the service journal (`journalctl -u ucm`) and the service does not come up; a container shows it in its log (`docker logs <container>`) and exits. Since nothing was written, put 2.254 back (the 2.254 package, or the 2.254 image on the same volume), start it once, then upgrade to 3.0 again. The 2.254.x security updates add no migration, so a database they started upgrades like a 2.254 one; a database whose registry names a migration that neither 2.254 nor this release knows (started by a later release, or edited by hand) is refused the same way, without writing, by `This database names N migration(s) this release does not know, first ...`.
- **A longer first start on a large database.** The first start of 3.0 reads every stored certificate once, in batches (subject index, key size, serial spelling): on 255,000 certificates and a million audit lines it was measured at about 31 seconds on SQLite and 50 on PostgreSQL until the service answers, growing in proportion to the number of certificates and of audit lines (step 150 reads the audit log: under a second of the 27 seconds of upgrade measured on SQLite, 44 on PostgreSQL), longer on a slow disk or a busy host. The service answers nothing until it ends. The log shows each step of the upgrade with its start, its end and its duration, and a progress line at most every 30 seconds while a step reads certificates. Let it finish: stopped, the upgrade starts over at the next start.
- **Start limits during that first start.** The DEB and RPM services and the Docker image never stop a start that takes long: its container is only reported unhealthy after one to two minutes (its health check), and `docker-compose.prod.yml` then leaves nginx unstarted until `docker compose up -d` is run again once UCM answers. On Kubernetes the chart's startup probe allows 360 seconds before the liveness probe begins, with or without HA (before 3.0 the chart had none without HA, and the liveness probe restarted the pod after about 100 seconds): for a database several times larger than the one above, raise `startupProbe.failureThreshold` for the upgrade.
- **Disk space for the upgrade on SQLite.** At its peak the upgrade holds the database, its rollback journal and the copy the Docker image takes before each start (`UCM_BACKUP_ENABLED`, on by default): about 2.7 times the database (4.5 GB for a 1.65 GB database). Before that copy the image checks each part on its own filesystem and refuses to start, with the space needed and available, when one is short: the copy needs the database's size free in `/opt/ucm/data/backups` (unless `UCM_BACKUP_ENABLED=false`), and a start that will upgrade the database (one whose migration registry lacks a migration of the image) needs its size again beside the database; both are summed when they share a filesystem. A DEB upgrade copies the database first as well.
- **Several nodes on one PostgreSQL.** The move to 3.0 is a full stop: stop every node, upgrade each one, then start them. Later upgrades go one node at a time unless the release notes say otherwise; see [High availability](docs/HA.md#upgrading).
- **FIPS image on a new module.** The `-fips` Docker image now carries the OpenSSL FIPS Provider 3.5.9 (CMVP certificate #5586) instead of 3.1.2 (#4985): pulling the new tag changes the module and the certificate number with nothing to do, and an instance created on 3.1.2 starts on 3.5.9 with its keys, CAs and backups. In FIPS mode the module now approves ML-DSA, Ed25519 and Ed448, which UCM then allows; the DEB and RPM packages on RHEL 9 and Ubuntu 24.04 keep refusing them, their modules do not approve them. A key of these types made on 3.5.9 does not load if the image is rebuilt on 3.1.2.
- **FIPS image: TLS 1.2 without Extended Master Secret is refused.** The 3.5.9 module enforces EMS (RFC 7627) for TLS 1.2, in both directions: a client that does not send it cannot connect, and an outgoing connection (ACME server, LDAP, SMTP, webhook, DNS API, PostgreSQL) to a TLS 1.2 server without it fails with a TLS internal error. TLS 1.3 is not affected; there is no setting to lift it in the approved mode, update the peer instead.
- **FIPS mode: RSA sizes.** In FIPS mode a request whose RSA key has an even length other than 2048, 3072 and 4096 bits, up to 16384 (RSA-8192 among them), refused by 2.254, is now signed; an odd length or one over 16384 bits stays refused at issuance and is now also refused for an OCSP responder or a TSA signer key.
- **FIPS mode: HMAC secrets of 14 bytes or more.** Saving a webhook secret or an RFC 2136 TSIG key shorter than 14 bytes (112 bits) is refused in FIPS mode, on every module. A TSIG key already saved keeps working; a webhook secret, Constellix, DNS Made Easy, INWX or Tencent Cloud secret or external EAB key already saved that short now fails when used in FIPS mode, with the FIPS reason, and a `SECRET_KEY` that short makes every sign-in fail. The FIPS readiness check lists them under `hmac.short_secret`, and the `SECRET_KEY` as the blocker `session.short_secret_key`: replace them before the switch.
- **FIPS mode: HSM keys.** 2.x checked an HSM key against FIPS mode only when it was generated, so a CA bound to a key that FIPS mode refuses (RSA under 2048 bits, of an odd length or over 16384 bits, an elliptic curve other than P-256, P-384 and P-521, or Ed25519, Ed448 and ML-DSA, which not every FIPS module approves) kept signing. In FIPS mode 3.0 refuses to sign with such a key, whatever the module: its CA issues no certificate and no CRL, and its OCSP answers `unauthorized`, unless a valid delegated responder answers for it (until that responder expires). The FIPS readiness check lists these keys under `hsm.unapproved_keys`: replace them before the switch, or keep their CAs on an instance without FIPS mode.
- In-app help is available in English, French and Chinese only; with the interface in German, Spanish, Italian, Japanese, Portuguese or Ukrainian the help panel shows the English text. The interface itself keeps its nine languages.
- Private-key encryption becomes an envelope: the key in `master.key` or `KEY_ENCRYPTION_KEY` (the KEK) wraps a data key stored in the database. Nothing is re-encrypted at the upgrade and the KEK stays the only secret to back up. A KEK is now changed by hand with the previous one in `master.key.previous` or `KEY_ENCRYPTION_KEY_PREVIOUS` (see the Admin Guide); swapping the key without it puts UCM in safe mode while encryption is enabled, and in HA also once it was disabled. Disabling encryption with `KEY_ENCRYPTION_KEY` set no longer answers 409: the variable stays configured and unused.
- No default administrator password: a new installation no longer creates `admin` / `changeme123`. Automation that logged in with `changeme123` after a fresh install must provide the password (`INITIAL_ADMIN_PASSWORD_FILE` or `INITIAL_ADMIN_PASSWORD`) or read the generated one from `DATA_DIR/initial-admin-password` and change it, as the first login requires for a generated password. An existing installation is not touched: its administrator and its password stay as they are, and no file is generated (for its sessions, see *Sessions* below).
- The line `INITIAL_ADMIN_PASSWORD=changeme123` that 2.x packages wrote into `/etc/ucm/ucm.env` is removed by the DEB and RPM upgrade; any other value stays, and none is read while an account exists. Without the removal, a later database reset would have recreated the administrator with that public password. A Docker or Compose setup that still passes `INITIAL_ADMIN_PASSWORD=changeme123` keeps it: remove it, it is unused once the administrator exists.

#### Before you upgrade

- Backup archives: 3.0 writes every archive in format 4, which 2.254 refuses (`Unsupported backup format version: 4`), and it has no setting to write an older format. Keep an archive taken by 2.254, with its password, out of the retention: going back to 2.254 needs it or a copy of the database taken before the upgrade, and loses what 3.0 changed since. A restore of a 2.x archive on 3.0 is refused for the same reasons as on 2.254 (wrong password, an archive over `BACKUP_MAX_UPLOAD_MB`, an Argon2id archive in FIPS mode) and for one more, before anything is written: two certificates of one CA sharing a serial number, once the database carries the unique serial index (every 3.0 database except an upgraded one in which two certificates of one CA still store the same serial, see *Duplicate serial numbers* below).
- Approval policies: 2.x applied a policy that requires approval to the requests made in the interface and the API, while ACME, EST, SCEP and WSTEP requests were issued without waiting for approval (the rules of the policy still applied). 3.0 holds the protocol requests such a policy covers too, a SCEP profile that approves automatically included, until an approver decides: the ACME order stays `processing`, EST answers 202 with `Retry-After`, SCEP answers PENDING and WSTEP returns a pending response. Before upgrading, review the scope of these policies, name the approvers, and check that the clients wait and retry.
- Windows enrollment (XCEP, WSTEP, Kerberos): the upgrade turns the configuration into the profile `default`, whose Kerberos realm is now explicit: the base DN of the enabled AD connector, else the `@REALM` of the SPN, else the single realm of the keytab, else the base DN of a disabled connector when the keytab holds that realm, or, with no keytab at all, once the first start finds none (a keytab the upgrade could not read leaves the realm to the start or the upload that takes it). When none of them names it, Kerberos is refused while the UsernamePassword and certificate bindings answer as before; the profile screen (or `GET /api/v2/windows-profiles/{id}`, `kerberos_refusal`) gives the reason, and `PUT /api/v2/windows-profiles/{id}` with `{"realm": "CORP.EXAMPLE"}` sets it (in capitals, a realm of the keytab). Kerberos clients of any other realm, such as a trusted forest served while the connector was disabled, are refused until a profile serves their realm. A 2.x backup restored on 3.0 is converted the same way.
- Helm chart: no value is renamed or removed. The liveness and readiness probes now call `/health/live` and `/health/ready` instead of `/health`, on a single pod too. With `initialAdminPassword` empty the chart now generates a password into its Secret (`UCM_INITIAL_ADMIN_PASSWORD`), which UCM reads only on a database that holds no account.
- Environment and settings: no environment variable of 2.254 is renamed or removed. `BACKUP_MAX_UPLOAD_MB` now bounds only the archives written by 2.x; a 3.0 archive is bounded by `BACKUP_MAX_ARCHIVE_MB`, unlimited by default. The new variables `UCM_CONFIG_DIR` (default `/etc/ucm`), `UCM_HA`, `UCM_NODE_ID`, `INITIAL_ADMIN_PASSWORD_FILE`, `INITIAL_ADMIN_PASSWORD_FORCE_CHANGE` and `KEY_ENCRYPTION_KEY_PREVIOUS` change nothing while unset. The settings `xcep_ca_refid`, `xcep_username`, `xcep_password`, `wstep_ca_refid`, `wstep_username`, `wstep_password` and `wstep_validity_days` move into the profile `default` and are removed; the XCEP, WSTEP and Kerberos switches and the SPN stay settings.

#### What changes for clients and scripts

- Sessions: 2.x kept sessions in files unless Redis was configured. 3.0 keeps them in files on SQLite and in Redis when `REDIS_URL` is set, as before, but on PostgreSQL without Redis it keeps them in the database (table `flask_sessions`), single node included, and does not take up the files: after the upgrade everyone signs in again once, browsers and scripts that reuse a session cookie alike. Accounts, passwords and API keys are not affected.
- Windows administration API: the single-row routes `/api/v2/xcep/config`, `/api/v2/wstep/config`, `/api/v2/kerberos/config`, `/api/v2/kerberos/keytab` and `/api/v2/ad-connector` (with `/test` and `/test-saved`) are removed. The profiles are a paginated list (`data`, `meta.total`); take the profile marked `is_default`, not the first one. Every profile and settings route needs the XCEP scope first, so a key that only held the WSTEP or Kerberos scope of 2.x now gets 403; in `/settings`, the WSTEP and Kerberos fields are then left out of a read, and refused with 403 on a write, without that service's own scope:

  | 2.x call (scope) | 3.0 call | Scopes in 3.0 |
  |---|---|---|
  | `GET /xcep/config` (`read:xcep`) | `GET /windows-profiles/{id}` (`policy_ca_refid`, `xcep_username`), `GET /windows-profiles/settings` (`xcep_enabled`) | `read:xcep` |
  | `PATCH /xcep/config` (`write:xcep`) | `PUT /windows-profiles/{id}`, `PATCH /windows-profiles/settings` (`xcep_enabled`) | `write:xcep` |
  | `GET /wstep/config` (`read:wstep`) | `GET /windows-profiles/{id}` (`issuing_ca_refid`, `wstep_username`, `validity_days`), `GET /windows-profiles/settings` (`wstep_enabled`) | `read:xcep`; `wstep_enabled` also needs `read:wstep` |
  | `PATCH /wstep/config` (`write:wstep`) | `PUT /windows-profiles/{id}` (CA, account, validity), `PATCH /windows-profiles/settings` (`wstep_enabled`) | `write:xcep`; `wstep_enabled` also needs `write:wstep` |
  | `GET /kerberos/config` (`read:kerberos`) | `GET /windows-profiles/settings` (`kerberos_enabled`, `kerberos_spn`, keytab state) | `read:xcep` and `read:kerberos` |
  | `PATCH /kerberos/config` (`write:kerberos`) | `PATCH /windows-profiles/settings` (`kerberos_enabled`, `kerberos_spn`) | `write:xcep` and `write:kerberos` |
  | `POST /kerberos/keytab` (`write:kerberos`) | `POST /windows-profiles/{id}/keytab` | `write:xcep` and `write:kerberos` |
  | `/ad-connector`, `/test`, `/test-saved` | `/ad-connectors`, `/ad-connectors/{id}`, `/ad-connectors/test`, `/ad-connectors/{id}/test` | `read:ad_connector`, `write:ad_connector`, unchanged |

  All paths are under `/api/v2`. `write:xcep` alone now changes the WSTEP CA, account and validity of a profile: review who holds it, and add the scopes your scripts need to their roles and API keys, nothing is widened automatically.
- Session key rotation: with private-key encryption enabled, `POST /api/v2/system/security/rotate-secrets` stores the new key in the database without a restart, and the previous key stays accepted for 24 hours (`previous_accepted_until` in the answer); another rotation is refused until then. `auto_apply: false`, which returned the manual steps in 2.x, now answers 400 in this mode. A rotation signs nobody out: to close sessions, reset the account's password (`POST /api/v2/users/{id}/reset-password`), or let the user close the others (`POST /api/v2/account/sessions/revoke-all`). With encryption disabled the rotation rewrites `ucm.env` and restarts the service, as in 2.x, and is refused in HA.
- New permission `read:dashboard`: the overview routes `/api/v2/dashboard/compliance`, `/api/v2/dashboard/health`, `/api/v2/dashboard/issuance` and `/api/v2/dashboard/queue` require it. Every built-in role grants it, so accounts keep the overview; an API key whose scopes are listed one by one needs it added to call them. The other dashboard routes of 2.x keep their checks.
- Certificate serial numbers: `serial_number` is stored and returned as a decimal string, where 2.x stored the hexadecimal one; the upgrade rewrites the stored serials of certificates and revocation records (duplicates aside, below), and the serial inside each signed certificate does not change. Update scripts that compare or parse it as hexadecimal, and keep it a string (it can exceed the integer range of JavaScript).
- API clients of `POST /api/v2/database/switch`: a switch stopped by a transient failure (lost connection, deadlock, locked database) once the target answered its connection test, before or during the copy, answers 503 instead of 409 or 500, and a target whose copied accounts did not pass their verification is copied again on retry instead of being taken as it is. A target that a failed attempt wrote no longer has to be reset: once the cause is corrected, retrying on it resumes the switch. A switch to a target, or back to SQLite, whose database 3.0 would refuse to start (see *Start from 2.254*) answers 409 before anything is written.
- Account API clients: a password checked again in a session (`POST /api/v2/account/password`, `current_password` on one's own `PUT /api/v2/users/{id}` or `reset-password`, `PUT /api/v2/account/2fa/webauthn`) answers 429 after `max_login_attempts` wrong tries, even for the right one, until `lockout_duration` has passed. A change of second factor (TOTP, recovery codes, security keys) now closes the account's other sessions, as a password change already did: a script holding a second session of that account gets 401 and signs in again.
- Login lockout: `max_login_attempts` below 3 is refused with 400 when saved (`PATCH /api/v2/settings/general`).
- Dashboard activity: `GET /api/v2/dashboard/activity` answers 500 (`Activity log unavailable`) when the audit log cannot be read, where 2.x answered 200 with an empty list; treat it as an error, not as an empty feed.
- Certificate hold of a related pair: `POST /api/v2/certificates/{id}/unhold` now lifts the hold of the other member of the pair too, as a revocation already takes both; send `{"unhold_related": false}` to lift one alone. The answer names the other one in `related_unheld`, and the webhook event `certificate.unheld` is now sent for each certificate lifted.
- Audit and syslog consumers (SIEM): a restore refused before its archive was read is now audited as a failed `system_restore` whose text starts with `Restore request refused: ` followed by the reason; match on that prefix. Version 2.x wrote no audit line for these refusals.
- SCEP: a PKCSReq signed by a certificate issued through the same endpoint is now a renewal. Its CSR must keep that certificate's subject and SANs, and the signer must not be revoked, expired or superseded: 2.x issued such a request as a new certificate when its challenge was valid, 3.0 refuses it with `badMessageCheck`. A device that changes its subject must sign its request with a self-signed key.
- Windows enrollment, renewal by certificate: 2.x renewed over the Certificate binding any certificate of the WSTEP CA, including one signed in the interface and then renewed with `certreq -Renew`. 3.0 renews there only a certificate issued through Windows enrollment and refuses the others (`The certificate was not issued through Windows enrollment`, audited); reissue such a certificate through Windows enrollment (autoenrollment or `certreq` against the policy), whose renewals then work.
- Windows enrollment, renewal limits: renewal with the TLS client certificate works only for a profile whose issuing CA is the mTLS CA of the server (or a CA under it), since the TLS trust is not widened; other profiles renew over Kerberos. A renewal by certificate re-checks the SID of the account against the connector of the profile but not the AD group (a renewal over Kerberos checks the group as an enrollment does), so a computer or user removed from the group keeps renewing until its certificate is revoked. EST `/simplereenroll` and SCEP RenewalReq now refuse to renew a certificate of a Windows profile (403, `badMessageCheck`, audited as `windows_enrollment.refused`); renew it over WSTEP. An administrator's manual renewal is not blocked, and the scheduled automatic renewal leaves these certificates alone.
- Windows enrollment, template OIDs: with an XCEP CA apart from the WSTEP CA, 2.x also issued a request naming the template OID derived from the WSTEP CA, which its policy never announced. 3.0 issues only the template OIDs the policy of the profile announces (for the profile `default` of an upgrade, those 2.x announced, derived from its XCEP CA) and refuses any other with `Certificate template <OID> is not offered by this CA`; the renewal of a certificate carrying such an OID is accepted as before.
- Windows enrollment, requests without template: on the Kerberos binding, 2.x issued a request that names no template (no certificate template extension, by OID or name) and whose Extended Key Usages match none of the templates offered as a server certificate (`serverAuth`), with its subject built from Active Directory. 3.0 refuses it with `The request names no certificate template and its Extended Key Usages match none this profile offers`, audited as `windows_enrollment.refused`, as AD CS does. A request that names its template (the extension XCEP announces with each template, for CertEnroll to copy into its request) or carries the EKUs of an offered template, as the Windows CertEnroll requests captured for the tests do, is served as before; a script that sends its own PKCS#10 must add the template extension (1.3.6.1.4.1.311.21.7 with the OID the policy announces, or 1.3.6.1.4.1.311.20.2 with the template name) or the EKUs of the template. The UsernamePassword binding keeps the 2.x behavior, and so does a Kerberos renewal signed by a certificate issued without template, provided that certificate is valid (not revoked, expired or superseded), was issued by Windows enrollment under the same profile, and belongs to the requester (its SID, else its subject or the computer's `dNSHostName` in the directory); any other is refused as an initial request. A renewal held for approval is checked again when it is approved, as AD CS processes an approved request as a new one: it is refused once the renewed certificate is revoked, renewed or expired meanwhile, and the client must then send a new request (with a template, or signed by a valid certificate).
- CA import: a CA whose RSA key is under 2048 bits is refused when imported with its private key; import its certificate without the key to keep it for chain building. Existing CAs are not touched.
- API clients of `GET /api/v2/dashboard/system-status`: 2.x returned `smtp` (its message naming the mail host), `webhooks` and `auto_renewal` to any authenticated caller. 3.0 returns them only to a caller holding `read:settings`; an API key that reads them must carry that scope, the other entries are unchanged.

#### What changes without an error

- CA hierarchy: a CA whose recorded parent provably did not issue its certificate (a certificate replaced by one from another issuer kept the former parent in 2.x) is moved by the first chain repair, at start, under the stored CA that did, or left without a parent, and each change is audited as `ca_parent_unlinked`; the chain exported and served for that CA changes with it. The proof is a parent whose subject is not the issuer name of the certificate, or a parent holding the key the certificate's authority key identifier names whose signature check fails, a signature algorithm of another key type (an Ed25519 signature under an RSA or EC parent) included. A parent of another name that an earlier version linked by its key alone is thus dropped too, at the first chain repair or the next change of the CA's certificate. On both paths, a revoked CA (while its certificate keeps its serial number), a parent re-keyed since the link (the certificate names its former key) and a link whose signature this build or its FIPS module cannot check are left as they are; the chain repair also leaves a parent confirmed by hand.
- CA import: an imported CA is attached to a parent only when the parent's key verifies its signature, on every import path. Smart import used to attach by identifier or name without checking, so a CA under a parent whose key type the server cannot verify (SLH-DSA, GOST) is now imported without a parent, and the hourly chain repair leaves it so. Such a CA names its probable parent (import response and CA details), and an administrator with `write:cas` links it on an explicit confirmation (CA details, or `POST /api/v2/cas/{id}/parent-confirmation`); the hourly chain repair keeps that link, and so does a re-import or an installed renewal certificate while that parent is still the one proposed.
- CA import: a new CA or certificate whose issuer is stored as a root and as a cross or link certificate of the same key is chained under the root, a pending CA's installed certificate included. A CA or certificate already chained under the cross or link certificate stays there: the hourly chain repair applies this preference only to one with no parent recorded. It does not protect a CA whose parent is proven wrong, which the chain repair removes as described under *CA hierarchy* above. A CA with no recorded parent and no authority key identifier now resolves its issuer to the root for its chain status, and an export that completes a missing chain adds the root, where either could pick the cross or link certificate before.
- Windows enrollment, XCEP without its own CA: 2.x answered GetPolicies with 503 when only the WSTEP CA was set. The upgrade, like the restore of a 2.x backup, switches XCEP off in that case, so clients still get no policy; switch it on to serve the policy of the WSTEP CA.
- Windows enrollment, keytab: the keytab of 2.x becomes that of the default profile at the first start, and UCM composes the file the acceptor reads from the keytabs of all profiles. A forest added later gets its own profile and keytab; nothing is merged by hand.
- Duplicate serial numbers: the upgrade adds a unique index on the serial number within each CA. Where certificates of one CA share a serial, it changes none of them, logs their identifiers and reports `serial_unique_index_pending` in `/health`; delete all but one of each (revoke it first if it is in use), then restart UCM, which creates the index at the next start. Until then a full backend switch is refused, and so is the restore of an archive holding them onto a database with the index.
- Subject uniqueness per CA is new and off on every CA the upgrade carries over: no request is refused for a subject already issued until you switch it on in the CA settings.
- Key defaults: a request that names no key, and whose template names none, was RSA-2048 in 2.x and refused when a policy forbade it. 3.0 takes the first of RSA-2048, RSA-3072, EC-P256 and EC-P384 that the policies and the CA's compliance profile allow; name the key in the request to keep a fixed result.
- CA digest: an intermediate CA created without a digest (`auto`) is now signed with a hash at least as strong as the parent key's own (SHA-384 under a P-384 parent, where 2.x could choose SHA-256 for an RSA child). Existing certificates are not reissued.
- SCEP replies: 2.x signed every CertRep with SHA-256. 3.0 signs it with the digest of the request when it is SHA-256, SHA-384 or SHA-512; test devices that accept only a SHA-256 reply.
- Login lockout: a `max_login_attempts` below 3 saved by 2.x is applied as 3.
- PostgreSQL connections: each pooled connection is checked before use and carries TCP keepalives, and a server that does not accept a connection within 10 seconds fails the attempt, where 2.x set no timeout; `connect_timeout` or a `keepalives` setting in `DATABASE_URL` takes precedence. Without Redis, each UCM process also opens for the sessions a second pool sized like the first (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`), and each web worker keeps one more connection open to receive events: check the server's `max_connections` against the number of processes.
- HTTP protocol port: saving a new `http_protocol_port` (`PATCH /api/v2/settings/general`) now restarts the service of a package installation at once, a rolling restart in HA, and asks for a restart of a container (`needs_restart`, `restart_message`); 2.x saved it and bound it at the next restart. With `HTTP_PROTOCOL_PORT` set, the setting reads that port, and another value saved stays unused, which the answer says.
- Webhooks and notifications: `certificate.issued` (`certificate.renewed` for a renewal) is now also sent for a certificate issued after an approval, through an AD CS connection or through the ACME proxy, and for a first certificate, or a renewal into a new row, obtained by the ACME client (2.x already sent `certificate.renewed` for an ACME client renewal in place); `certificate.imported` for a certificate imported by the import route, an mTLS import or an OPNsense import; `ca.created` (then `ca.updated`) for a CA brought in by the certificate import. 2.x did not send the other events on these paths: review the webhooks subscribed to them.
- Expiry webhooks: `certificate.expired` now covers every certificate expired since the previous pass, up to 30 days back, so a stop of UCM no longer loses the expiries in between and a second pass does not announce them again. 2.x announced those of the last 24 hours at each pass; the first pass of 3.0 does the same.
- Revoking a certificate obtained by the ACME client (in the interface or the API, one by one, in bulk or after an approval) now also revokes it at the ACME CA that issued it, and a revocation that CA does not confirm is sent again by the scheduler until it does; a hold stays in UCM. 2.x revoked it in UCM only. Keep the network access and the ACME account the certificate was ordered with.
- Renewal over EST, SCEP or WSTEP: the deploy bindings and the HTTPS listener binding of the renewed certificate now move to the new one, where 2.x left them on the archived certificate. A binding that sends the private key, and the HTTPS binding, move only when UCM holds the new key; otherwise they stay on the previous certificate and are flagged (event `certificate.binding_left_behind`) until the key is imported or the binding is set again.
- CRL signing key: a CA whose stored key is not the key of its certificate (a certificate or key replaced alone) no longer signs a CRL that nobody can verify: the scheduled CRL is skipped with an error in the log, and `POST /api/v2/crl/{id}/regenerate` and `/delta/regenerate` answer 409.
- After a restore, UCM signs a new CRL (and delta CRL) for each CA that publishes one with its own key, so the distribution point no longer serves the CRL of the replaced instance until the next scheduled one; the restore summary names the CAs whose CRL could not be signed.
- Common names with a comma: `common_name` of certificates and CAs, and `cn` and `issuer_name` of certificates, now return the whole name, unescaped (`Doe, John` for `CN=Doe\, John`, where 2.x returned `Doe\`); the signed subject does not change. Update scripts that match on the shortened name.
- Discovery on a PostgreSQL server whose time zone is not UTC: the validity dates of discovered certificates are now stored in UTC like every other date; those a 2.x scan stored stay shifted by the server's offset until the next scan of their target rewrites them.
- Rate limiting: both limiters now read `RATE_LIMIT_ENABLED` the same way. `1`, `yes` and `on` (any case) turn the route limits on, where 2.254 put them on for `true` only, and an empty value keeps the default, on, where 2.254 read it as off. An installation that ran without these limits through one of those spellings gets them back: write `false` to keep them off.

#### Interface

- The side bar is replaced by a top bar with the Modules menu and pinned modules, and the floating detail windows by one docked inspector with a tab per object. Page addresses are kept, `/dashboard` included.
- The overview replaces the dashboard: its choice of cards is saved with the account, and the widget layout 2.x kept in the browser is not carried over. The Gray theme is now called Atelier and is applied in its place.

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

**No breaking changes for typical deployments**: safe to upgrade directly.

**ACME proxy: loopback upstreams now rejected.** The ACME proxy's upstream calls (directory, nonce, signed POST) now go through the same SSRF-hardened HTTP path as the ACME client: cloud-metadata and **loopback** targets are rejected. If your proxy upstream directory URL points at `localhost` / `127.0.0.1` (e.g. a self-referencing test setup), the proxy directory endpoint will return an error after upgrade. Point it at a routable address instead (a LAN IP or hostname; RFC1918 and `.lan`/`.local` remain fully supported). Regular upstreams (Let's Encrypt, internal CAs on LAN addresses) are unaffected.

**SoftHSM provider config normalized automatically.** Migration 057 rewrites legacy `library_path`/`pin` config keys to `module_path`/`user_pin` on all PKCS#11 providers; the `SoftHSM-Default` provider's *Test connection* works again after upgrade with no manual action.

### Upgrading to v2.56 from v2.5x

**No breaking changes**: safe to upgrade directly.

**Fixed in v2.55–v2.56:**
- Certificate subject/issuer fields now use standard RFC 4514 format (CN=, C=, O= instead of verbose names)
- Existing certificates with wrong format are auto-corrected by migration on startup
- ACME/CSR-signed certificates now include Extended Key Usage (`serverAuth`), which fixes Edge/Chrome rejecting certs
- CSRs with empty subject (common from ACME clients) now get CN populated from SAN

**Note:** Existing ACME certificates need to be re-issued to benefit from the EKU fix.

### Upgrading to v2.52 from v2.48–v2.51

**No breaking changes**: safe to upgrade directly.

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

**No breaking changes**: safe to upgrade directly.

> **Note:** UCM switched from Semantic Versioning (2.1.x) to Major.Build versioning (2.48) starting with this release. The version jump from 2.1.x to 2.48 is intentional and expected.

**New in v2.48:**
- Comprehensive backend test suite (1364 tests, ~95% route coverage)
- ucm-watcher system for safe service restarts and auto-updates
- Experimental badges for untested features (mTLS, HSM, SSO)
- TOTP 2FA login flow with QR code setup
- Auto-update mechanism via GitHub releases

**Auto-update (DEB/RPM):**
UCM can now check for and install updates automatically. The ucm-watcher systemd service monitors signal files:
- `/opt/ucm/data/.restart_requested`: triggers a service restart
- `/opt/ucm/data/.update_pending`: triggers package installation + restart

No manual action required: updates are triggered from Settings > Updates.

### Upgrading to v2.1.0 from v2.0.x

**No breaking changes**: safe to upgrade directly.

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

No action required: all migration happens automatically.

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
4. Ensure enough disk space: on SQLite, the database's size free beside it for the upgrade's journal, and its size again where its copy goes

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
