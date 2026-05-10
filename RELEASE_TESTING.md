# UCM Release Testing

Cross-distro validation matrix for every release candidate (`-rcN`) and stable
tag. **6/6 mandatory** — 3 distros × 2 backends.

| Target            | Host:Port           | SQLite | PostgreSQL |
|-------------------|---------------------|--------|------------|
| DEB package       | pve:8445            | smoke + UC | smoke + UC + 33-migration from-scratch |
| RPM package       | fedor:8443          | smoke + UC | smoke + UC |
| Docker container  | pve:8444 (test)     | smoke + UC | smoke + UC |

> The production Docker container on pve uses 8089/8449. RC test containers
> always go on **8444** under a separate name (e.g. `ucm-rc-test`). Never
> restart the prod container with an RC image.

## Smoke + UC scripts

| Script                              | Scope                          |
|-------------------------------------|--------------------------------|
| `/tmp/opencode/smoke.py`            | API smoke (urllib + cookie + CSRF) |
| `/tmp/opencode/playwright_uc.py`    | 11 real-UI workflows (Chromium headless) |

Bump the version assertion line in `smoke.py` for every release. Currently
matches `2.X-dev`, `2.X-rcN`, and `2.X` — see `/tmp/opencode/smoke.py:40`.

## Per-target recipe

```bash
# 1. Install / pull the RC artefact
ssh <host> "dpkg -i ucm_<X.Y-rcN>_all.deb && apt-get install -f -y"        # DEB
ssh fedor "dnf install -y ./ucm-<X.Y-rcN>-1.noarch.rpm"                    # RPM
ssh pve   "docker rm -f ucm-rc-test 2>/dev/null; \
           docker run -d --name ucm-rc-test -p 8444:8443 \
             -e UCM_DOCKER=1 \
             -v /mnt/disk2/appdata/ucm-rc-test/etc:/etc/ucm \
             -v /mnt/disk2/appdata/ucm-rc-test/data:/opt/ucm/data \
             neyslim/ultimate-ca-manager:<X.Y-rcN>"                        # Docker

# 2. Verify boot
ssh <host> "journalctl -u ucm -n 80 --no-pager | grep -E 'Database|migration|listening'"
curl -k https://<host>:<port>/api/v2/health   # → {"status":"ok"}

# 3. Run smoke + UC
UCM_BASE=https://<host>:<port> python3 /tmp/opencode/smoke.py
UCM_BASE=https://<host>:<port> python3 /tmp/opencode/playwright_uc.py
```

## PostgreSQL sub-test (DEB / RPM)

```bash
# Throwaway PG on pve
ssh pve "docker run -d --name ucm-rc-pg -p 0.0.0.0:5444:5432 \
    -e POSTGRES_USER=ucm -e POSTGRES_PASSWORD=ucmtest -e POSTGRES_DB=ucm \
    postgres:16-alpine"

# Switch backend (env file is sourced by systemd)
ssh <host> "cp /etc/ucm/ucm.env /etc/ucm/ucm.env.pre-pg && \
    echo 'DATABASE_URL=postgresql://ucm:ucmtest@<pve-ip>:5444/ucm' >> /etc/ucm/ucm.env && \
    systemctl restart ucm"

# Boot log MUST show: ✓ Database: POSTGRESQL + applied migration count
ssh <host> "journalctl -u ucm -n 100 --no-pager | grep -E 'Database|migration'"

# Re-run smoke + UC
UCM_BASE=https://<host>:<port> python3 /tmp/opencode/smoke.py
UCM_BASE=https://<host>:<port> python3 /tmp/opencode/playwright_uc.py

# Restore + cleanup
ssh <host> "mv /etc/ucm/ucm.env.pre-pg /etc/ucm/ucm.env && systemctl restart ucm"
ssh pve "docker rm -f ucm-rc-pg"
```

Docker → PG: add `--add-host=host.docker.internal:host-gateway` and use
`host.docker.internal:5444`. IPv6 docker-proxy is unreliable on pve — use the
FQDN or `127.0.0.1`, never `localhost`.

## Mandatory functional smoke tests

After login on every target, exercise these features. They fail at runtime,
not boot, so a clean `journalctl` is **not** sufficient.

| Feature              | What to do                                                     | Catches |
|----------------------|----------------------------------------------------------------|---------|
| PostgreSQL backend   | Settings → Database Backend → Test Connection                  | Missing `psycopg2` (#78) |
| HSM detect/test      | Settings → HSM → Detect / Test                                 | Provider mismatch |
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
ssh pve "docker rm -f ucm-rc-test 2>/dev/null; \
         docker run -d --name ucm-rc-test -p 8444:8443 \
           -v /mnt/disk2/appdata/ucm-rc-test/etc:/etc/ucm \
           -v /mnt/disk2/appdata/ucm-rc-test/data:/opt/ucm/data \
           neyslim/ultimate-ca-manager:<X.Y-rcN>"

# 2. Login → Settings → Security → Enable Encryption
#    → Backup modal MUST appear, MUST require download + checkbox before close

# 3. Confirm master.key was created on the host
ssh pve "ls -la /mnt/disk2/appdata/ucm-rc-test/etc/master.key"
#    → -rw------- ucm ucm

# 4. Recreate container (simulates upgrade / image change)
ssh pve "docker rm -f ucm-rc-test && \
         docker run -d --name ucm-rc-test -p 8444:8443 \
           -v /mnt/disk2/appdata/ucm-rc-test/etc:/etc/ucm \
           -v /mnt/disk2/appdata/ucm-rc-test/data:/opt/ucm/data \
           neyslim/ultimate-ca-manager:<X.Y-rcN>"

# 5. Verify NO safe-mode banner, encryption still enabled
curl -k https://pve:8444/api/v2/system/security/encryption-status
#    → {"data": {"enabled": true, "key_source": "file", ...}}

# 6. Test the existing-key download endpoint
#    Settings → Security → Back Up Master Key → file downloaded
#    AND check audit log for master_key_downloaded entry
```

## Pass criteria

A release is **not** stable until **6/6** targets pass:

- [ ] DEB / SQLite — smoke + UC + functional smoke tests
- [ ] DEB / PostgreSQL — smoke + UC + 33-migration-from-scratch
- [ ] RPM / SQLite — smoke + UC + functional smoke tests
- [ ] RPM / PostgreSQL — smoke + UC
- [ ] Docker / SQLite — smoke + UC + master-key persistence
- [ ] Docker / PostgreSQL — smoke + UC

Skipping a target is how distro-specific regressions ship.
