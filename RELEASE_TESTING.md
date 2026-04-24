# Release Testing Workflow

UCM uses a 3-branch promotion model to gate releases behind real-environment smoke tests.

## Branches

| Branch | Purpose | Who pushes | What runs |
|--------|---------|------------|-----------|
| `dev`  | Active development. All daily commits land here. | Maintainers / agents | `tests.yml` (unit + frontend tests) |
| `test` | Release candidate channel. Merged from `dev` when a release is being prepared. | Maintainers (manual merge from `dev`) | `tests.yml` + `test-channel.yml` (full build sanity, no publish) |
| `main` | Production. Merged from `test` after RC validation passes. | Maintainers (manual fast-forward from `test`) | Nothing on push — releases are tag-driven |

Tags:
- `vX.Y-rcN` (e.g. `v2.137-rc1`) → published as **GitHub pre-release**, NOT tagged `latest` on Docker Hub
- `vX.Y` (e.g. `v2.137`) → published as **GitHub release**, tagged `latest` on Docker Hub

## Release flow

```
dev  ──merge──▶  test  ──tag v2.137-rc1──▶  Pre-release artifacts on GitHub
                  │     ◀─── fixes if needed ───▶
                  │
                  └──fast-forward──▶  main  ──tag v2.137──▶  Stable release
```

### 1. Prepare RC
On `dev`:
```bash
# Make sure dev is green
cd /root/ucm-src
git checkout dev && git pull
cd backend && python3 -m pytest tests/ -x -q
cd ../frontend && npm test
```

Merge to `test`:
```bash
git checkout test && git pull
git merge --ff-only dev      # If diverged, resolve on dev first
```

Bump VERSION to RC:
```bash
echo -n "2.137-rc1" > VERSION
sed -i 's/"version": ".*"/"version": "2.137-rc1"/' frontend/package.json frontend/package-lock.json
git add VERSION frontend/package.json frontend/package-lock.json
git commit -m "chore: 2.137-rc1"
git tag v2.137-rc1
git push origin test v2.137-rc1
```

`build-release.yml` runs on the tag → publishes pre-release with DEB/RPM/Docker artifacts.

### 2. Smoke-test the RC

Use the **mock DB seed script** to set up a known-state test DB before each smoke test:
```bash
# On the test target (pve / fedor / docker)
sudo cp /opt/ucm/data/ucm.db /opt/ucm/data/ucm.db.before-rc
sudo systemctl stop ucm
sudo python3 /opt/ucm/scripts/seed_test_db.py /opt/ucm/data/ucm.db
sudo systemctl start ucm
```

Run through the **smoke-test matrix** (see `Smoke-test checklist` below).
- ✅ All pass → promote to stable (step 3)
- ❌ Any fail → fix on `dev`, merge to `test`, bump `-rc2`, repeat

### 3. Promote to stable

```bash
# On test branch, finalize version
git checkout test
echo -n "2.137" > VERSION
sed -i 's/"version": "2.137-rc[0-9]*"/"version": "2.137"/' frontend/package.json frontend/package-lock.json
# Move CHANGELOG [Unreleased] under [2.137] - YYYY-MM-DD
git add -A && git commit -m "release(v2.137): summary"

# Fast-forward main
git checkout main && git pull
git merge --ff-only test
git tag v2.137
git push origin main v2.137

# Bump dev to next -dev cycle
git checkout dev && git pull
git merge --ff-only main      # bring release commit + tag back into dev
echo -n "2.138-dev" > VERSION
sed -i 's/"version": "2.137"/"version": "2.138-dev"/' frontend/package.json frontend/package-lock.json
git add -A && git commit -m "chore: bump to 2.138-dev"
git push origin dev
```

## Smoke-test checklist

Run on each of the 3 distros: **DEB**, **RPM**, **Docker**.

### Core
- [ ] Service starts: `systemctl status ucm` (or `docker ps`)
- [ ] Login works (admin / changeme123 from seeded DB)
- [ ] Version banner shows the RC number
- [ ] `/api/v2/ping` returns 200
- [ ] No tracebacks in `/var/log/ucm/error.log` after 60s of activity

### Database backends
- [ ] **SQLite** (default): Settings → Database shows real size, Optimize works
- [ ] **PostgreSQL**: Settings → Database Backend → enter `postgresql://...` → Test Connection succeeds (validates psycopg2 is bundled)

### Authentication
- [ ] Password login (admin)
- [ ] mTLS enrollment (Account → Add cert)
- [ ] WebAuthn enrollment (Account → Add hardware token)
- [ ] SSO — at least one of: OIDC, SAML, LDAP (from seed config, with role mapping if possible)

### PKI
- [ ] Issue cert from CA (manual)
- [ ] Sign CSR
- [ ] Revoke cert (CRL regenerated)
- [ ] Renew cert
- [ ] Auto-renewal job runs (set short threshold + wait, or trigger manually)
- [ ] Smart Import: import a PFX/P12, verify duplicate detection works (try re-importing — must say "already exists")

### Protocols (public, no auth)
- [ ] `curl -k https://host/cdp/<ca-id>.crl` returns CRL bytes
- [ ] `curl -k -I https://host/ocsp` returns 405/200 (HEAD)
- [ ] `curl -k https://host/.well-known/est/cacerts` returns CA certs
- [ ] ACME issuance to a `*.lan` or `*.local` domain (HTTP-01) succeeds

### HSM
- [ ] HSM detection page loads
- [ ] If SoftHSM/PKCS#11 configured: Test button succeeds
- [ ] If OpenBao configured: Test button succeeds

### Networking
- [ ] Webhook to `http://192.168.x.x/...` succeeds (LAN allowed)
- [ ] Webhook to `http://169.254.169.254/...` blocked (cloud metadata)
- [ ] Discovery scan of `127.0.0.1` works
- [ ] Discovery scan of `192.168.x.x/24` works

### UI
- [ ] Dashboard loads, charts render
- [ ] Certificates list paginates
- [ ] Floating detail window opens on row click
- [ ] Settings → Restart from UI works (frontend reconnects)
- [ ] Dark + light theme both render correctly
- [ ] At least 3 languages load (en, fr, de)

### Logs / observability
- [ ] `/var/log/ucm/ucm.log` populated, no errors
- [ ] `/var/log/ucm/error.log` empty (or only known warnings)
- [ ] Audit log records key actions (login, cert issue, cert revoke)

## Mock DB seeding

`scripts/seed_test_db.py` creates a known-state DB with:
- 1 root CA + 1 intermediate CA
- 5 leaf certificates (mix of valid, expiring soon, expired)
- 3 users (admin, operator, viewer)
- 1 disabled SSO config (OIDC) for path testing
- 1 ACME account (disabled)
- 2 webhook endpoints (one LAN, one cloud-metadata for SSRF test)
- 5 audit log entries

This gives RC testers a consistent baseline to verify against, instead of relying on production data.

## Hotfix exception

For **critical security fixes** that can't wait for RC cycle, hotfix directly on `main`:
```bash
git checkout main && git pull
# fix
git commit -m "fix: critical CVE-XXXX"
git tag v2.137.1
git push origin main v2.137.1

# back-merge to dev and test
git checkout test && git merge --ff-only main
git checkout dev && git merge --no-ff main
git push origin test dev
```

Document the bypass in CHANGELOG and the fix's commit body.
