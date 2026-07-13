# SoftHSM auto-register — test plan (PR #194)

## Problem

`auto_register_softhsm` wrote `library_path` / `pin` in `hsm_providers.config`, but
`PKCS11Provider` reads `module_path` / `user_pin`. The built-in **SoftHSM-Default**
provider failed **Test connection** with `module_path is required`.

## Fix summary

| Layer | Behaviour |
|-------|-----------|
| **New installs** | `auto_register_softhsm` stores canonical keys |
| **Migration 057** | Rewrites legacy JSON in all `pkcs11` rows |
| **Startup** | `auto_register_softhsm` repairs existing SoftHSM-Default |
| **Runtime** | `PKCS11Provider` normalizes legacy aliases before validation |

## Automated regression tests

```bash
cd backend
pytest tests/test_pkcs11_config.py -v
pytest tests/test_hsm.py -q
```

Covers: normalization helper, provider legacy acceptance, auto-register keys,
startup repair, migration 057 SQLite rewrite.

## Manual test plan

### A. Fresh Docker deploy (SoftHSM enabled)

1. Deploy UCM image with `HSM_DEFAULT_PIN` set and SoftHSM token initialized.
2. Start application — logs should contain `Auto-registered SoftHSM provider 'SoftHSM-Default'`.
3. **Admin → HSM** → provider **SoftHSM-Default** shows library path and token label.
4. Click **Test connection** → expect success (not `module_path is required`).
5. DB check: `config` JSON contains `module_path` and `user_pin`, not `library_path` / `pin`.

### B. Upgrade from broken install (migration)

1. On a copy of production DB, insert or keep a row with legacy keys:
   ```json
   {"library_path": "/usr/lib/softhsm/libsofthsm2.so", "pin": "…", "token_label": "UCM-Default"}
   ```
2. Restart UCM — migration **057** runs at boot.
3. Re-read `hsm_providers.config` → canonical keys only.
4. **Test connection** in UI succeeds.

### C. Runtime fallback (no migration yet)

1. Temporarily skip migration (dry-run only) but deploy new code.
2. Legacy row still has `library_path` / `pin`.
3. **Test connection** should still work (`PKCS11Provider` normalizes at read time).
4. After restart with migration, DB row is persisted in canonical form.

## Playwright (lab / staging)

```bash
cd frontend
UCM_BASE_URL=https://admin.ucm.pfcorp.eu:8443 \
UCM_PASSWORD='…' \
npx playwright test e2e/hsm.spec.ts
```

Smoke: page load, table/empty state, provider detail panel. Full connection test
requires SoftHSM on the target host.

## Lab validation (native Debian — 2026-07-13)

Host `172.31.10.8` (`admin.ucm.pfcorp.eu`):

- SoftHSM2 installed; token **UCM-Default** in `/opt/ucm/data/softhsm/tokens/`
- `HSM_DEFAULT_PIN` in `/etc/ucm/ucm.env` → auto-register **SoftHSM-Default**
- `POST /api/v2/hsm/providers/1/test` → **Connection successful**
- Playwright `e2e/hsm.spec.ts`: 9/10 smoke tests pass

Full install procedure: [HSM-LAB-SOFTHSM-NATIVE.md](./HSM-LAB-SOFTHSM-NATIVE.md)  
Ops runbook: `90-docs-and-runbooks/ucm/SOFTHSM-LAB.md` + `setup-softhsm-lab.sh`

## Non-regression scope

- All existing `tests/test_hsm.py` (auth, CRUD, validation, OpenBao mappings).
- PKCS#11 providers created via API with `module_path` / `user_pin` unchanged.
- Non-PKCS#11 providers (Azure, GCP, OpenBao) unaffected.
