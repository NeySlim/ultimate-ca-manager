# UCM Release Testing

Cross-distro validation matrix for every release candidate (`-rcN`) and stable
tag. **6/6 mandatory**: 3 distros × 2 backends.

| Target            | SQLite | PostgreSQL |
|-------------------|--------|------------|
| DEB package       | smoke + UI | smoke + UI + fresh database |
| RPM package       | smoke + UI | smoke + UI |
| Docker container  | smoke + UI | smoke + UI |

Each target is a host of its own (`<host>`, `<port>` below). An RC container
runs under a separate name and port (e.g. `ucm-rc-test`): never restart a
production container with an RC image.

"Fresh database" means an empty PostgreSQL database: its schema is built in one
pass, not migration by migration. The boot log must show `Database: POSTGRESQL`,
`Fresh PostgreSQL database` and `migration baseline marked`, and no line starting with `✗`.

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
             -v /srv/ucm-rc-test/etc:/etc/ucm \
             -v /srv/ucm-rc-test/data:/opt/ucm/data \
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
    -e POSTGRES_USER=ucm -e POSTGRES_PASSWORD=ucmtest -e POSTGRES_DB=ucm \
    postgres:16-alpine"

# Switch backend (env file is sourced by systemd)
ssh <host> "cp /etc/ucm/ucm.env /etc/ucm/ucm.env.pre-pg && \
    echo 'DATABASE_URL=postgresql://ucm:ucmtest@<pg-host>:<pg-port>/ucm' >> /etc/ucm/ucm.env && \
    systemctl restart ucm"

# Boot log MUST show: ✓ Database: POSTGRESQL and, on a fresh database, the migration baseline marked
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
| Service restart      | Settings → Restart Service (UI button)                          | Regression to `subprocess.run` |

Tail logs while running: `ssh <host> "tail -f /var/log/ucm/ucm.log /var/log/ucm/error.log"`.
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
           -v /srv/ucm-rc-test/etc:/etc/ucm \
           -v /srv/ucm-rc-test/data:/opt/ucm/data \
           neyslim/ultimate-ca-manager:<X.Y-rcN>"

# 2. Login → Settings → Security → Enable Encryption
#    → Backup modal MUST appear, MUST require download + checkbox before close

# 3. Confirm master.key was created on the host
ssh <host> "ls -la /srv/ucm-rc-test/etc/master.key"
#    → -rw------- ucm ucm

# 4. Recreate container (simulates upgrade / image change)
ssh <host> "docker rm -f ucm-rc-test && \
         docker run -d --name ucm-rc-test -p <port>:8443 \
           -v /srv/ucm-rc-test/etc:/etc/ucm \
           -v /srv/ucm-rc-test/data:/opt/ucm/data \
           neyslim/ultimate-ca-manager:<X.Y-rcN>"

# 5. Verify NO safe-mode banner, encryption still enabled
curl -k https://<host>:<port>/api/v2/system/security/encryption-status
#    → {"data": {"enabled": true, "key_source": "file", ...}}

# 6. Test the existing-key download endpoint
#    Settings → Security → Back Up Master Key → file downloaded
#    AND check audit log for master_key_downloaded entry
```

## Pass criteria

A release is **not** stable until **6/6** targets pass:

- [ ] DEB / SQLite: smoke + UI + functional smoke tests
- [ ] DEB / PostgreSQL: smoke + UI + fresh database
- [ ] RPM / SQLite: smoke + UI + functional smoke tests
- [ ] RPM / PostgreSQL: smoke + UI
- [ ] Docker / SQLite: smoke + UI + master-key persistence
- [ ] Docker / PostgreSQL: smoke + UI

Skipping a target is how distro-specific regressions ship.
