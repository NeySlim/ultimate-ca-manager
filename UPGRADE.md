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

# Install
sudo dpkg -i ucm_VERSION_all.deb

# Fix dependencies if needed
sudo apt-get install -f
```

**What happens during upgrade:**
1. No backup is taken by the package: make one first (below). From 2.254 to 3.0, UCM copies a SQLite database itself at its first start (see Upgrading to v3.0)
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

# Restore the database from the manual backup taken above
sudo cp ~/ucm-backup-YYYYMMDD.db /opt/ucm/data/ucm.db

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

- **Start from 2.254.** 3.0 upgrades a database last started by UCM 2.254, nothing older. From an earlier 2.x, install 2.254 first (package or image), start it once so it completes its own migrations, then install 3.0. The same applies to every node of a shared PostgreSQL database and to a database copied from SQLite to PostgreSQL: it is the database that must have been started by 2.254. A 2.x backup archive of any version still restores on 3.0.
- **What a refused start looks like.** On a database that 2.254 has not started, 3.0 stops before writing anything: `This database was last started by a release older than 2.254 (N migration(s) of 2.254 are missing from its registry, first ...). Install 2.254, start it once, then upgrade. Nothing was changed: 2.254 still starts on this database.` A database without a migration registry gives the same message with `it has no migration registry`. A package installation shows it in the service journal (`journalctl -u ucm`) and the service does not come up; a container shows it in its log (`docker logs <container>`) and exits. Since nothing was written, put 2.254 back (the 2.254 package, or the 2.254 image on the same volume), start it once, then upgrade to 3.0 again. The 2.254.x security updates add no migration, so a database they started upgrades like a 2.254 one; a database whose registry names a migration that neither 2.254 nor this release knows (started by a later release, or edited by hand) is refused the same way, without writing, by `This database names N migration(s) this release does not know, first ...`.
- **A refused start or a failed upgrade is not restarted.** The DEB and RPM packages now install the same systemd unit. When 3.0 refuses the database (one 2.254 has not started, on SQLite or PostgreSQL, a PostgreSQL database not in UTF8, or a copy before the upgrade it could not take), or when a step of the upgrade fails, the server exits with code 78 and the unit stays `failed`, without restarting, until you act (`systemctl status ucm` shows the code). Once the cause is fixed, start it again: `sudo systemctl start ucm`. A failure while the service runs restarts it after 10 seconds, at most 5 times in 5 minutes; past that, run `sudo systemctl reset-failed ucm` before starting it.
- **A longer first start on a large database.** The first start of 3.0 reads every stored certificate once, in batches, to index its subject: measured at 2 to 5 seconds per 100,000 certificates on SQLite and about 6 on PostgreSQL, so around a minute for a million, longer on a slow disk or a busy host, during which the service is not yet ready. Let it finish: stopped, the step starts over at the next start.
- **Several nodes on one PostgreSQL.** The move to 3.0 is a full stop: stop every node, upgrade each one, then start them. Later upgrades go one node at a time unless the release notes say otherwise; see [High availability](docs/HA.md#upgrading).
- **FIPS image on a new module.** The `-fips` Docker image now carries the OpenSSL FIPS Provider 3.5.9 (CMVP certificate #5586) instead of 3.1.2 (#4985): pulling the new tag changes the module and the certificate number with nothing to do, and an instance created on 3.1.2 starts on 3.5.9 with its keys, CAs and backups. In FIPS mode the module now approves ML-DSA, Ed25519 and Ed448, which UCM then allows; the DEB and RPM packages on RHEL 9 and Ubuntu 24.04 keep refusing them, their modules do not approve them. A key of these types made on 3.5.9 does not load if the image is rebuilt on 3.1.2.
- **FIPS image: TLS 1.2 without Extended Master Secret is refused.** The 3.5.9 module enforces EMS (RFC 7627) for TLS 1.2, in both directions: a client that does not send it cannot connect, and an outgoing connection (ACME server, LDAP, SMTP, webhook, DNS API, PostgreSQL) to a TLS 1.2 server without it fails with a TLS internal error. TLS 1.3 is not affected; there is no setting to lift it in the approved mode, update the peer instead.
- **FIPS mode: RSA sizes.** In FIPS mode a request whose RSA key has an even length other than 2048, 3072 and 4096 bits, up to 16384 (RSA-8192 among them), refused by 2.254, is now signed; an odd length or one over 16384 bits stays refused at issuance and is now also refused for an OCSP responder or a TSA signer key.
- **FIPS mode: HMAC secrets of 14 bytes or more.** Saving a webhook secret or an RFC 2136 TSIG key shorter than 14 bytes (112 bits) is refused in FIPS mode, on every module. A TSIG key already saved keeps working; a webhook secret, Constellix, DNS Made Easy, INWX or Tencent Cloud secret or external EAB key already saved that short now fails when used in FIPS mode, with the FIPS reason, and a `SECRET_KEY` that short makes every sign-in fail. The FIPS readiness check lists them under `hmac.short_secret`, and the `SECRET_KEY` as the blocker `session.short_secret_key`: replace them before the switch.
- **The DEB and RPM packages check the installed version first.** Installing 3.0 over an installed UCM package older than 2.254 (1.x included) stops in the pre-installation script, before any file is written: `UCM 2.253 is installed, and this package upgrades UCM 2.254 or later only: its database must have been started by 2.254 first. Install 2.254, start it once, then install this package. Nothing was changed: UCM 2.253 is still installed.` The installed version stays installed, and the 3.0 package stops nothing. Release candidates of 2.254 (`2.254~rc1`) and the 2.254.x security updates are accepted. The 3.0 packages no longer carry the 1.x to 2.0 upgrade: a 1.x installation goes through 2.254 too.
- **An older UCM removed with its data left in place is archived, not upgraded.** After an RPM removal, or a DEB removed or purged, no UCM package is installed and the 3.0 package installs as new. Before it writes its configuration, it asks the 3.0 migration runner whether it starts on the SQLite database left there. When it does not, the package moves everything that installation left, unchanged, into `/opt/ucm-archive/<UTC date and time>/` (readable by root only, outside every path UCM serves, writes or backs up): the contents of `/opt/ucm/data` and `/etc/ucm`, and the database file with its `-wal` when `DATABASE_PATH` placed it elsewhere. It then sets up a new, empty UCM and starts it; `UCM_FIPS_BUILD=1`, when the archived `ucm.env` set it, is written into the new one, and the output says so; when a retry had built the Python environment while that `ucm.env` was still in the archive, the environment is built again against the system OpenSSL. The installation output and `/var/log/ucm/leftover-archive.log` say what was found and where it went. Every item is renamed, never copied or removed: one that cannot be renamed out of its filesystem (another filesystem, a bind mount, overlayfs) goes into a `.ucm-archive-<UTC date and time>/` directory beside it, readable by root only, and a directory that cannot be renamed at all stays where it is while its contents move the same way. The output lists each such directory, and the archive's `README.txt` lists each one with what it holds; UCM never uses or removes them, and `apt purge ucm` leaves them in place: it removes the rest of `/etc/ucm`, `/var/lib/ucm` and `/var/log/ucm` and names what it kept. `README.txt` in the archive gives the way back: install 2.254 in place of 3.0, stop it, put the archived data and configuration back, start it once, then install 3.0 again. Data that 3.0 starts on (left by 2.254 or later) is kept and used as before. A database whose registry names migrations 3.0 does not know (written by a later release) is not archived either: that is a downgrade, the service refuses to start, and the output says to reinstall the release that wrote it. A database it cannot read, or a PostgreSQL database it refuses, is left where it is, the output says so (the SQLite file, or `postgresql` without its address), and the service then refuses to start as described above. In these cases where nothing is archived, the installation does not end on its `UCM INSTALLED` banner. If a move fails, the installation stops there: what was moved is put back (the output says whether all of it could be), nothing else is written, and the service is not started. Once the cause is fixed, `dpkg --configure -a` or `dnf reinstall ucm` retries, first putting back whatever could not be. On EL9, dnf reports that failure as a warning (`%post(...) scriptlet failed`) and still ends with `Complete!` and exit code 0: `systemctl is-active ucm` then answers `inactive`, and `/var/log/ucm/leftover-archive.log` holds the reason.
- **Docker has no package step.** The 3.0 image starts and refuses a database older than 2.254 as described above; it never archives a volume, since starting a newer image on it is an upgrade. A container that still mounts its volume at a path used by images before 2.70 (`/opt/ucm/backend/data` or `/app/backend/data`) has those files copied into `/opt/ucm/data` at startup, as before; a database carried over that way is checked the same way.
- **A copy of the SQLite database before the upgrade.** At its first start on a 2.254 SQLite database, before changing anything, 3.0 copies it next to itself as `ucm.db.2.254-before-3.0` (`/opt/ucm/data/` for the packages and the image, so the Docker data volume keeps it), mode 0600 and with the owner of the database. The copy goes through SQLite's online backup, so it includes what the WAL holds, and is checked (integrity, the 2.254 migration registry, the row count of every table). It takes about the size of the database: the start checks that this size plus 8 MB is free. When the copy cannot be taken or checked, the start stops, the database is left as it was and the log says why, how much space is needed and where. UCM never deletes the copy and it is not listed among the backup archives: remove it yourself once 3.0 suits you.
- **When an upgrade stops partway.** Once the copy is checked, and before the first upgrade step, 3.0 records in the database that the upgrade has started (a table named `_upgrade_from_2_254_started`, which the copy does not hold and which a completed upgrade removes). A start that finds this record does not copy the database again, since it is no longer the 2.254 one: it keeps the existing copy and says `kept the copy taken by an earlier start` in the log, or, when that copy is missing or fails its check, says that no copy of the 2.254 database exists, makes none, and resumes the upgrade. A start on a database without the record (the copy put back, or a 2.254 database that was never upgraded) takes a fresh copy that replaces the previous one. The `dry-run` and `status` commands of `migration_runner.py` say which of these applies, and where the copy is, without writing anything.
- **Going back to 2.254 with that copy.** Stop UCM, put the copy back in place of the database, remove the `-wal` and `-shm` files left by 3.0, then reinstall the 2.254 package or start the 2.254 image on the same volume. Everything written by 3.0 since the upgrade is lost. Do the same after an upgrade that failed: put the copy back before starting 2.254, never start 2.254 on the half-upgraded database, because the steps already applied have changed tables that 2.254 reads and writes. If 2.254 was started on it anyway, the next 3.0 start keeps the original copy, and what 2.254 wrote in between is not in that copy. On a package installation:

  ```bash
  sudo systemctl stop ucm
  sudo cp -p /opt/ucm/data/ucm.db.2.254-before-3.0 /opt/ucm/data/ucm.db
  sudo rm -f /opt/ucm/data/ucm.db-wal /opt/ucm/data/ucm.db-shm
  ```
- **PostgreSQL: UTF8 only.** A database whose `server_encoding` is not `UTF8` (`SQL_ASCII`, the default of a cluster created under the C locale) is refused at startup and by the package's check, with its encoding named; 2.254 failed on it too, without naming it. Create a UTF8 database as the Admin Guide shows (PostgreSQL Backend) and point `DATABASE_URL` at it.
- **PostgreSQL: back the database up yourself.** No copy is taken on PostgreSQL, single node or HA; the upgrade log says so. Run `pg_dump` on the database before installing 3.0, and stop every node first in a cluster.
- In-app help is available in English, French and Chinese only; with the interface in German, Spanish, Italian, Japanese, Portuguese or Ukrainian the help panel shows the English text. The interface itself keeps its nine languages.
- Private-key encryption becomes an envelope: the key in `master.key` or `KEY_ENCRYPTION_KEY` (the KEK) wraps a data key stored in the database. Nothing is re-encrypted at the upgrade and the KEK stays the only secret to back up. A KEK is now changed by hand with the previous one in `master.key.previous` or `KEY_ENCRYPTION_KEY_PREVIOUS` (see the Admin Guide); swapping the key without it puts UCM in safe mode while encryption is enabled, and in HA also once it was disabled. Disabling encryption with `KEY_ENCRYPTION_KEY` set no longer answers 409: the variable stays configured and unused.
- No default administrator password: a new installation no longer creates `admin` / `changeme123`. Automation that logged in with `changeme123` after a fresh install must provide the password (`INITIAL_ADMIN_PASSWORD_FILE` or `INITIAL_ADMIN_PASSWORD`) or read the generated one from `DATA_DIR/initial-admin-password` and change it, as the first login requires for a generated password. An existing installation is not touched: its administrator, its password and its sessions stay as they are, and no file is generated.
- The line `INITIAL_ADMIN_PASSWORD=changeme123` that 2.x packages wrote into `/etc/ucm/ucm.env` is removed by the DEB and RPM upgrade; any other value stays, and none is read while an account exists. Without the removal, a later database reset would have recreated the administrator with that public password. A Docker or Compose setup that still passes `INITIAL_ADMIN_PASSWORD=changeme123` keeps it: remove it, it is unused once the administrator exists.
- CA hierarchy: a CA whose recorded parent provably did not issue its certificate (a certificate replaced by one from another issuer kept the former parent in 2.x) is moved by the first chain repair, at start, under the stored CA that did, or left without a parent, and each change is audited as `ca_parent_unlinked`; the chain exported and served for that CA changes with it. The proof is a parent whose subject is not the issuer name of the certificate, or a parent holding the key the certificate's authority key identifier names whose signature check fails, a signature algorithm of another key type (an Ed25519 signature under an RSA or EC parent) included. A parent of another name that an earlier version linked by its key alone is thus dropped too, at the first chain repair or the next change of the CA's certificate. On both paths, a revoked CA (while its certificate keeps its serial number), a parent re-keyed since the link (the certificate names its former key) and a link whose signature this build or its FIPS module cannot check are left as they are; the chain repair also leaves a parent confirmed by hand.
- Windows enrollment (XCEP, WSTEP, Kerberos): the upgrade turns the configuration into the profile `default`, whose Kerberos realm is now explicit: the base DN of the enabled AD connector, else the `@REALM` of the SPN, else the single realm of the keytab, else the base DN of a disabled connector when the keytab holds that realm, or, with no keytab at all, once the first start finds none (a keytab the upgrade could not read leaves the realm to the start or the upload that takes it). When none of them names it, Kerberos is refused while the UsernamePassword and certificate bindings answer as before; the profile screen (or `GET /api/v2/windows-profiles/{id}`, `kerberos_refusal`) gives the reason, and `PUT /api/v2/windows-profiles/{id}` with `{"realm": "CORP.EXAMPLE"}` sets it (in capitals, a realm of the keytab). Kerberos clients of any other realm, such as a trusted forest served while the connector was disabled, are refused until a profile serves their realm. A 2.x backup restored on 3.0 is converted the same way.
- API clients of the single-row routes: `/api/v2/xcep/config`, `/api/v2/wstep/config`, `/api/v2/kerberos/config`, `/api/v2/kerberos/keytab` and `/api/v2/ad-connector` (with `/test` and `/test-saved`) are removed. Use `/api/v2/windows-profiles` (the profile fields, `POST /{id}/keytab`, and `/settings` for the XCEP, WSTEP and Kerberos switches and the SPN) and `/api/v2/ad-connectors`. An API key of 2.x that only had `write:kerberos` must also carry `write:xcep` to call `POST /api/v2/windows-profiles/{id}/keytab`, which replaces `POST /api/v2/kerberos/keytab` and needs both.
- API clients of `POST /api/v2/database/switch`: a switch stopped by a transient failure (lost connection, deadlock, locked database) once the target answered its connection test, before or during the copy, answers 503 instead of 409 or 500, and a target whose copied accounts did not pass their verification is copied again on retry instead of being taken as it is.
- Windows enrollment, XCEP without its own CA: 2.x answered GetPolicies with 503 when only the WSTEP CA was set. The upgrade, like the restore of a 2.x backup, switches XCEP off in that case, so clients still get no policy; switch it on to serve the policy of the WSTEP CA.
- Windows enrollment, renewal by certificate: 2.x renewed over the Certificate binding any certificate of the WSTEP CA, including one signed in the interface and then renewed with `certreq -Renew`. 3.0 renews there only a certificate issued through Windows enrollment and refuses the others (`The certificate was not issued through Windows enrollment`, audited); reissue such a certificate through Windows enrollment (autoenrollment or `certreq` against the policy), whose renewals then work.
- SCEP: a PKCSReq signed by a certificate issued through the same endpoint is now a renewal. Its CSR must keep that certificate's subject and SANs, and the signer must not be revoked, expired or superseded: 2.x issued such a request as a new certificate when its challenge was valid, 3.0 refuses it with `badMessageCheck`. A device that changes its subject must sign its request with a self-signed key.
- Windows enrollment, renewal limits: renewal with the TLS client certificate works only for a profile whose issuing CA is the mTLS CA of the server (or a CA under it), since the TLS trust is not widened; other profiles renew over Kerberos. A renewal by certificate re-checks the SID of the account against the connector of the profile but not the AD group (a renewal over Kerberos checks the group as an enrollment does), so a computer or user removed from the group keeps renewing until its certificate is revoked. EST `/simplereenroll` and SCEP RenewalReq now refuse to renew a certificate of a Windows profile (403, `badMessageCheck`, audited as `windows_enrollment.refused`); renew it over WSTEP. An administrator's manual renewal is not blocked, and the scheduled automatic renewal leaves these certificates alone.
- Windows enrollment, template OIDs: with an XCEP CA apart from the WSTEP CA, 2.x also issued a request naming the template OID derived from the WSTEP CA, which its policy never announced. 3.0 issues only the template OIDs the policy of the profile announces (for the profile `default` of an upgrade, those 2.x announced, derived from its XCEP CA) and refuses any other with `Certificate template <OID> is not offered by this CA`; the renewal of a certificate carrying such an OID is accepted as before.
- Windows enrollment, keytab: the keytab of 2.x becomes that of the default profile at the first start, and UCM composes the file the acceptor reads from the keytabs of all profiles. A forest added later gets its own profile and keytab; nothing is merged by hand.
- Windows enrollment, requests without template: on the Kerberos binding, 2.x issued a request that names no template (no certificate template extension, by OID or name) and whose Extended Key Usages match none of the templates offered as a server certificate (`serverAuth`), with its subject built from Active Directory. 3.0 refuses it with `The request names no certificate template and its Extended Key Usages match none this profile offers`, audited as `windows_enrollment.refused`, as AD CS does. A request that names its template (the extension XCEP announces with each template, for CertEnroll to copy into its request) or carries the EKUs of an offered template, as the Windows CertEnroll requests captured for the tests do, is served as before; a script that sends its own PKCS#10 must add the template extension (1.3.6.1.4.1.311.21.7 with the OID the policy announces, or 1.3.6.1.4.1.311.20.2 with the template name) or the EKUs of the template. The UsernamePassword binding keeps the 2.x behavior, and so does a Kerberos renewal signed by a certificate issued without template, provided that certificate is valid (not revoked, expired or superseded), was issued by Windows enrollment under the same profile, and belongs to the requester (its SID, else its subject or the computer's `dNSHostName` in the directory); any other is refused as an initial request. A renewal held for approval is checked again when it is approved, as AD CS processes an approved request as a new one: it is refused once the renewed certificate is revoked, renewed or expired meanwhile, and the client must then send a new request (with a template, or signed by a valid certificate).
- CA import: a CA whose RSA key is under 2048 bits is refused when imported with its private key; import its certificate without the key to keep it for chain building. Existing CAs are not touched.
- CA import: an imported CA is attached to a parent only when the parent's key verifies its signature, on every import path. Smart import used to attach by identifier or name without checking, so a CA under a parent whose key type the server cannot verify (SLH-DSA, GOST) is now imported without a parent, and the hourly chain repair leaves it so. Such a CA names its probable parent (import response and CA details), and an administrator with `write:cas` links it on an explicit confirmation (CA details, or `POST /api/v2/cas/{id}/parent-confirmation`); the hourly chain repair keeps that link, and so does a re-import or an installed renewal certificate while that parent is still the one proposed.
- CA import: a new CA or certificate whose issuer is stored as a root and as a cross or link certificate of the same key is chained under the root, a pending CA's installed certificate included. What is already chained is not moved: the hourly chain repair applies the rule only to a CA or certificate with no parent recorded. A CA with no recorded parent and no authority key identifier now resolves its issuer to the root for its chain status, and an export that completes a missing chain adds the root, where either could pick the cross or link certificate before.
- Account API clients: a password checked again in a session (`POST /api/v2/account/password`, `current_password` on one's own `PUT /api/v2/users/{id}` or `reset-password`, `PUT /api/v2/account/2fa/webauthn`) answers 429 after `max_login_attempts` wrong tries, even for the right one, until `lockout_duration` has passed. A change of second factor (TOTP, recovery codes, security keys) now closes the account's other sessions, as a password change already did: a script holding a second session of that account gets 401 and signs in again.
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

### Upgrading from v1.8.x

Bring the installation to 2.254 first: 3.0 starts only on a database 2.254 has started, and its packages no longer handle a 1.x installation. Then follow [Upgrading to v3.0](#upgrading-to-v30).

---

## Troubleshooting

### Upgrade Failed - Service Won't Start

```bash
# Check logs
sudo journalctl -u ucm -n 100 --no-pager

# Common fixes:

# 1. Permission issues
# A local archive (.ucm-archive-*) holds an earlier installation's keys: it stays root's
sudo find /opt/ucm/data/ -name '.ucm-archive-*' -prune -o -exec chown -h ucm:ucm {} +
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
