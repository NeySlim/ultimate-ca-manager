# SoftHSM on a native UCM install (lab / DEB)

Guide for enabling **SoftHSM2** on a **non-Docker** UCM deployment (systemd + `/opt/ucm`).
Validated on lab `10.42.0.8` (Debian 13, UCM native) — 2026-07-13.

Docker deployments: see [HSM_DOCKER.md](../HSM_DOCKER.md) (auto-init via entrypoint).

## Overview

```
┌─────────────────────────────────────────────────────────────┐
│  systemd ucm.service (user: ucm)                            │
│    SOFTHSM2_CONF=/etc/ucm/softhsm2.conf                     │
│    HSM_DEFAULT_PIN → auto_register_softhsm() at boot        │
│         ↓                                                   │
│  PKCS#11 libsofthsm2.so  →  token UCM-Default                │
│         ↓                                                   │
│  /opt/ucm/data/softhsm/tokens/  (persistent, ucm-owned)     │
└─────────────────────────────────────────────────────────────┘
```

## Prerequisites

- UCM installed under `/opt/ucm` with venv containing `python-pkcs11`
- Service runs as user `ucm` (`ReadWritePaths` includes `/opt/ucm/data`)
- PR **#198** / migration **057** applied (canonical `module_path` / `user_pin`)

## 1. Install SoftHSM

```bash
sudo apt-get update
sudo apt-get install -y softhsm2
```

Library path (Debian 13 amd64):

```text
/usr/lib/softhsm/libsofthsm2.so
→ /usr/lib/x86_64-linux-gnu/softhsm/libsofthsm2.so
```

## 2. Token directory (writable by `ucm`)

Default `/var/lib/softhsm/tokens` is root:softhsm — the `ucm` service cannot write there
under `ProtectSystem=strict`. Store tokens under `DATA_DIR` instead:

```bash
sudo mkdir -p /opt/ucm/data/softhsm/tokens
sudo chown -R ucm:ucm /opt/ucm/data/softhsm
```

## 3. SoftHSM configuration

`/etc/ucm/softhsm2.conf`:

```ini
directories.tokendir = /opt/ucm/data/softhsm/tokens/
objectstore.backend = file
log.level = ERROR
slots.removable = false
slots.mechanisms = ALL
library.reset_on_fork = false
```

```bash
sudo chmod 640 /etc/ucm/softhsm2.conf
sudo chown root:ucm /etc/ucm/softhsm2.conf
```

## 4. UCM environment (`/etc/ucm/ucm.env`)

Append:

```ini
# SoftHSM — lab defaults (change PINs in production)
SOFTHSM2_CONF=/etc/ucm/softhsm2.conf
HSM_PIN=87654321
HSM_SO_PIN=12345678
HSM_DEFAULT_PIN=87654321
```

`HSM_DEFAULT_PIN` triggers `auto_register_softhsm()` at startup: creates
**SoftHSM-Default** in the HSM page with canonical PKCS#11 keys.

## 5. Initialize token

As user `ucm` (first time only):

```bash
export SOFTHSM2_CONF=/etc/ucm/softhsm2.conf
runuser -u ucm -- env SOFTHSM2_CONF="$SOFTHSM2_CONF" softhsm2-util --init-token --free \
  --label "UCM-Default" --pin "$HSM_PIN" --so-pin "$HSM_SO_PIN"
runuser -u ucm -- env SOFTHSM2_CONF="$SOFTHSM2_CONF" softhsm2-util --show-slots
```

If a broken **SoftHSM-Default** provider row exists from earlier tests, delete it
before restart so auto-register runs cleanly:

```bash
sqlite3 /opt/ucm/data/ucm.db "DELETE FROM hsm_providers WHERE name='SoftHSM-Default';"
```

## 6. Restart and verify

```bash
sudo systemctl restart ucm
sudo systemctl status ucm
```

### API

```bash
# Login (session cookie + CSRF)
curl -sk -c /tmp/ucm.jar -b /tmp/ucm.jar -X POST https://admin.ucm.example.com:8443/api/v2/auth/login \
  -H 'Content-Type: application/json' -d '{"username":"admin","password":"…"}'

CSRF=$(curl -sk -b /tmp/ucm.jar -X POST …/auth/login … | jq -r '.data.csrf_token')

curl -sk -b /tmp/ucm.jar -X POST https://admin.ucm.example.com:8443/api/v2/hsm/providers/1/test \
  -H "X-CSRF-Token: $CSRF"
```

Expected:

```json
{"data": {"success": true, "message": "Connection successful", "details": {"token_label": "UCM-Default", …}}}
```

### Web UI

**Administration → Gestion HSM** → **SoftHSM-Default** → **Tester la connexion** → succès.

### Playwright smoke

```bash
cd frontend
UCM_BASE_URL=https://admin.ucm.example.com:8443 UCM_PASSWORD='…' \
  npx playwright test e2e/hsm.spec.ts --project=chromium
```

## Automated setup script (lab)

See runbook repo: `90-docs-and-runbooks/ucm/setup-softhsm-lab.sh`

## Troubleshooting

| Symptom | Cause | Fix |
|---------|--------|-----|
| `module_path is required` | Legacy config keys | Migration 057 + PR #198 |
| `PKCS#11 module not found` | softhsm2 not installed | `apt install softhsm2` |
| `CKR_PIN_INCORRECT` | PIN mismatch | Align `HSM_DEFAULT_PIN` with token PIN |
| Token init permission denied | Wrong tokendir owner | Use `/opt/ucm/data/softhsm/tokens`, `chown ucm:ucm` |
| Provider missing after boot | Row exists, no `HSM_DEFAULT_PIN` | Set env var or create provider in UI |
| `python-pkcs11 not installed` | Missing venv package | `/opt/ucm/venv/bin/pip install python-pkcs11` |

## Backup

```bash
sudo tar czf softhsm-tokens-$(date +%F).tar.gz -C /opt/ucm/data/softhsm tokens
```

Restore: stop UCM, extract to `/opt/ucm/data/softhsm/tokens`, `chown -R ucm:ucm`, start UCM.

## Related

- [HSM-SOFTHSM-AUTO-REGISTER.md](./HSM-SOFTHSM-AUTO-REGISTER.md) — config key fix + test plan
- [HSM_DOCKER.md](../HSM_DOCKER.md) — container entrypoint auto-init
