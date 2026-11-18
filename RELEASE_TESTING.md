# UCM Release Testing

Validation matrix for every release candidate (`-rcN`) and stable tag. Each
deliverable is tested on its own, on each database it supports, and the result
of every cell is recorded separately.

| Deliverable                      | Architecture | SQLite | PostgreSQL |
|----------------------------------|--------------|--------|------------|
| DEB package                      | all          | cell   | cell       |
| RPM, Fedora                      | noarch       | cell   | cell       |
| RPM, EL9 (RHEL, Rocky, Alma)     | noarch       | cell   | cell       |
| RPM, EL10 (RHEL, Rocky, Alma)    | noarch       | cell   | cell       |
| Docker image, standard           | amd64, arm64 | cell per architecture | cell per architecture |
| Docker image, `-fips`            | amd64, arm64 | cell per architecture | cell per architecture |
| Helm chart                       | n/a          | cell   | cell       |

Every cell is "smoke + UI checks" (below); add the fresh-database check on
PostgreSQL, the master-key persistence recipe on the images, and the HA checks
of `docs/HA.md` on the chart and on a shared PostgreSQL. `release-smoke.yml`
and `test-channel.yml` automate part of this (see "Package install smoke"); a
cell they do not cover is run by hand. Packages need Python 3.12 or
later: the system `python3` where it is recent enough, the `python3.12` package
on EL9.

Run each target on a host of your own (`<host>`, `<port>` below). An RC container
runs under a separate name and port (e.g. `ucm-rc-test`): never restart a
production container with an RC image.

"Fresh database" means an empty PostgreSQL database. The boot log must show
`Database: POSTGRESQL`, `migration baseline marked` and no line starting with `✗`.

On a release candidate, the Helm chart cell installs the chart from the
`helm-chart` artifact of the release run: only a stable release pushes it to the
registry.

## Rehearsal before a release candidate

Before the bump commit of a candidate or of a stable release, dispatch
`build-release.yml` on the branch that will carry it, with `version` set to the
version to simulate and `dry_run` on (its default). A rehearsal plays the whole
chain and publishes nothing: no tag, no release, no registry push, no Docker Hub
page, no chart. Its images go to a registry started inside each build job and
gone with it; the smoke boots the amd64 images the run saved. A dispatch with
`dry_run` off is refused unless it runs on the tag of its own version.
A stable rehearsed before its bump commit has no `## [X.Y]` section yet: its
notes take `[Unreleased]` with a warning, where the tag run stops.

What the run keeps, to read before tagging:

| Artifact | Holds |
|----------|-------|
| `deb-package`, `rpm-package`, `rpm-el9-package`, `rpm-el10-package` | the packages, their `.sha256` and their SBOMs |
| `std-sbom-*`, `fips-sbom-*`, `std-digest-*`, `fips-digest-*` | one SBOM and one digest per image platform (amd64, arm64) |
| `std-image-amd64`, `fips-image-amd64` | the images the smoke booted |
| `helm-chart` | `ucm-<chart version>.tgz` and its checksum |
| `release-rehearsal` | `notes.md`, `release.txt` (tag, prerelease, make_latest), `full-stop-migrations.json`, `sbom-index.json` |

The manifest jobs print the image tags a release would create: `X.Y-rcN` and
`X.Y-rcN-fips` for a candidate; `X.Y`, `X.Y-fips`, `latest` and `latest-fips`
for a stable release that no published stable tag exceeds (a `2.254.N` released
after 3.0 takes neither).

A release run, from the tag, then publishes: the GitHub release (a prerelease for
a candidate) with the DEB, the Fedora, EL9 and EL10 RPMs, their checksums and
SBOMs, `full-stop-migrations.json` and `sbom-index.json`; the images of both
variants and both architectures on both registries; the Docker Hub page when the
image takes `latest`; for a stable release only,
the chart at `oci://ghcr.io/neyslim/charts/ucm`, versioned as the release in
semver form. `scripts/bump-version.sh X.Y-rcN` writes the version into
`VERSION`, both npm files and the chart before the tag. A tag run refuses a tag whose commit carries another version in `VERSION`.

## Smoke and UI checks

`scripts/smoke_release.py` checks `/api/v2/health` (the version it reports must
equal `--version` exactly), the login, the permissions and the CSRF token:

```bash
UCM_SMOKE_ADMIN_PASSWORD=<password> python3 scripts/smoke_release.py \
    --base-url https://<host>:<port> --version <X.Y-rcN> --allow-rc
```

UCM has no default password: on a fresh install, read the generated one in
`/opt/ucm/data/initial-admin-password` (Docker: `docker exec <container> cat
/opt/ucm/data/initial-admin-password`) and change it at first login, or set
`INITIAL_ADMIN_PASSWORD_FILE` before the first start.

The UI checks are the workflows of "Mandatory functional smoke tests" below,
run in a browser on every target.

## Package install smoke

`scripts/ci/package-smoke.sh` installs one DEB or RPM in a bare distribution container (no sudo, no systemd) and checks the venv imports, the application start and `/api/v2/health`. The `smoke-packages` job of `release-smoke.yml` runs it (checksum verified first) for Debian 13, Ubuntu 24.04 and 26.04, AlmaLinux 9 and 10, and Fedora 43: on the packages of the release run before the release is created, or on the published assets by `workflow_dispatch` on a version. Debian 12 is out: the packages need python3 >= 3.12. `test-channel.yml` runs it on the sanity DEB (Debian 13, Ubuntu 24.04).

## Per-target recipe

```bash
# 1. Install / pull the RC artefact
# Asset names carry dots: 3.0-rc1 ships as ucm_3.0.rc1_all.deb
ssh <host> "apt-get install -y ./ucm_<X.Y.rcN>_all.deb"                        # DEB
ssh <host> "dnf install -y ./ucm-<X.Y.rcN>-1.fc43.noarch.rpm"                 # RPM, Fedora
ssh <host> "dnf install -y ./ucm-el9-<X.Y.rcN>-1.el9.noarch.rpm"              # RPM, EL9 (el10: ucm-el10-...el10)
ssh <host> "docker rm -f ucm-rc-test 2>/dev/null; \
           docker run -d --name ucm-rc-test -p <port>:8443 \
             -v <state-dir>/etc:/etc/ucm \
             -v <state-dir>/data:/opt/ucm/data \
             neyslim/ultimate-ca-manager:<X.Y-rcN>"                        # Docker

# 2. Verify boot
ssh <host> "journalctl -u ucm -n 80 --no-pager | grep -E 'Database|migration|listening'"
curl -k https://<host>:<port>/api/v2/health   # → {"status":"ok"}

# 3. Run the smoke, then the UI checks
UCM_SMOKE_ADMIN_PASSWORD=<password> python3 scripts/smoke_release.py \
    --base-url https://<host>:<port> --version <X.Y-rcN> --allow-rc
```

## PostgreSQL sub-test (DEB / RPM)

```bash
# Throwaway PostgreSQL on a host with Docker
ssh <pg-host> "docker run -d --name ucm-rc-pg -p <pg-port>:5432 \
    -e POSTGRES_USER=ucm -e POSTGRES_PASSWORD=<password> -e POSTGRES_DB=ucm \
    postgres:<major>-alpine"

# Switch backend (env file is sourced by systemd)
ssh <host> "cp /etc/ucm/ucm.env /etc/ucm/ucm.env.pre-pg && \
    echo 'DATABASE_URL=postgresql://ucm:<password>@<pg-host>:<pg-port>/ucm' >> /etc/ucm/ucm.env && \
    systemctl restart ucm"

# Boot log MUST show: ✓ Database: POSTGRESQL
ssh <host> "journalctl -u ucm -n 100 --no-pager | grep -E 'Database|migration'"

# Re-run the smoke and the UI checks
UCM_SMOKE_ADMIN_PASSWORD=<password> python3 scripts/smoke_release.py \
    --base-url https://<host>:<port> --version <X.Y-rcN> --allow-rc

# Restore + cleanup
ssh <host> "mv /etc/ucm/ucm.env.pre-pg /etc/ucm/ucm.env && systemctl restart ucm"
ssh <pg-host> "docker rm -f ucm-rc-pg"
```

Docker → PG: add `--add-host=host.docker.internal:host-gateway` and use
`host.docker.internal:<pg-port>`. IPv6 docker-proxy can be unreliable: use the
FQDN or `127.0.0.1`, never `localhost`.

## Mandatory functional smoke tests

After login on every target, exercise these features. They fail at runtime,
not boot, so a clean `journalctl` is **not** sufficient.

| Feature              | What to do                                                     | Catches |
|----------------------|----------------------------------------------------------------|---------|
| PostgreSQL backend   | Settings → Database → Test                  | Missing `psycopg` (#78) |
| HSM detect/test      | Modules → Administration → HSM Management → Test                                 | Provider mismatch |
| SSO role mapping     | OIDC/SAML login that mutates a user's role                     | Audit signature drift (#79) |
| ACME internal domain | Issue cert for `*.lan` / RFC1918                               | SSRF over-block (v2.124) |
| Webhook to LAN       | Webhook → `http://192.168.x.x/...`                             | SSRF over-block |
| Cloud metadata IP    | Webhook → `http://169.254.169.254` → MUST be rejected          | SSRF under-block |
| Discovery loopback   | Discovery scan of `127.0.0.1`                                  | Loopback over-block |
| Public protocols     | `curl -k <host>:<port>/cdp/<ca>.crl`, `/ocsp`, `/.well-known/est/cacerts` | SPA catch-all hijack |
| Service restart      | Settings → General → Restart UCM (UI button)                          | Regression to `subprocess.run` |

Tail logs while running: `ssh <host> "tail -f /var/log/ucm/ucm.log /var/log/ucm/error.log"` (packages).
Tracebacks land in **error.log**, not `ucm.log`.

## Master key persistence (Docker)

Since v2.155 the Docker image declares `VOLUME ["/etc/ucm", "/opt/ucm/data"]`.
Without bind-mounting `/etc/ucm`, recreating the container destroys the
master key and renders all encrypted private keys (CAs, certs, ACME accounts,
SSH CA, webhook secrets) unrecoverable.

**Test recipe (run on every Docker RC):**

```bash
# 1. Bind-mount both volumes
ssh <host> "docker rm -f ucm-rc-test 2>/dev/null; \
         docker run -d --name ucm-rc-test -p <port>:8443 \
           -v <state-dir>/etc:/etc/ucm \
           -v <state-dir>/data:/opt/ucm/data \
           neyslim/ultimate-ca-manager:<X.Y-rcN>"

# 2. Login → Settings → Security → Enable Encryption
#    → Backup modal MUST appear, MUST require download + checkbox before close

# 3. Confirm master.key was created on the host
ssh <host> "ls -la <state-dir>/etc/master.key"
#    → -rw------- ucm ucm

# 4. Recreate container (simulates upgrade / image change)
ssh <host> "docker rm -f ucm-rc-test && \
         docker run -d --name ucm-rc-test -p <port>:8443 \
           -v <state-dir>/etc:/etc/ucm \
           -v <state-dir>/data:/opt/ucm/data \
           neyslim/ultimate-ca-manager:<X.Y-rcN>"

# 5. Verify NO safe-mode banner, encryption still enabled
curl -k https://<host>:<port>/api/v2/system/security/encryption-status
#    → {"data": {"enabled": true, "key_source": "file", ...}}

# 6. Test the existing-key download endpoint
#    Settings → Security → Back Up Master Key → file downloaded
#    AND check audit log for master_key_downloaded entry
```

## Upgrade from 2.254 and rollback

3.0 upgrades only a database last started by 2.254 (see "Upgrading to v3.0" in
`UPGRADE.md`). On every package and image cell, also run:

1. Install 2.254 (the latest 2.254.N), start it once, create a certificate and
   take a backup archive and a copy of the database.
2. Install the release under test and start it. It must come up on the same
   data with the certificate intact and the smoke passing. On a database 2.254
   never started, it must refuse to start and write nothing, with the message
   `UPGRADE.md` quotes.
3. Roll back following the *Rollback* section of `UPGRADE.md` (written for the
   DEB; the other deliverables use their own package or image), the *Upgrading
   to v3.0* notes saying what it requires and what it loses: stop the service,
   restore the database copy taken in step 1, reinstall 2.254, start it. Do not
   restore a 3.0 backup archive on 2.254: it refuses the archive format.

## Pass criteria

A release is **not** stable until every cell of the matrix is recorded as
passed, the upgrade and rollback run is done for each deliverable, and the
functional smoke tests above pass on at least one cell per deliverable.
Skipping a cell is how distro-specific regressions ship. The numbers a check
depends on (migrations, versions, asset names) are read from the code and its
tests, never copied here: `scripts/ci/release_version.py` for asset names and
version forms, `UPGRADE.md` for the upgrade requirements.
