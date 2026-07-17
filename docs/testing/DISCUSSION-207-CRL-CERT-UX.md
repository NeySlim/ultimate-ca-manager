# Discussion #207 — CRL / cert UX — test plan

PR: [#208](https://github.com/NeySlim/ultimate-ca-manager/pull/208)  
Discussion: [#207](https://github.com/NeySlim/ultimate-ca-manager/discussions/207)

## Scope

### Batch 1
- CRL validity vs publish interval (`next_publish`)
- Configurable CRL digest
- CDP download filename `{slug}-{refid8}.crl`
- Certificate `notBefore` skew (~15 minutes)
- Template digest + `usage_count`
- HTTP protocol port may be `80`

### Batch 2
- Editable certificate **description** / **friendly name** (`PATCH /api/v2/certificates/<id>`)
- List column **template used**
- CA validity presets up to **100 years** / custom end date
- Per-CA **protocol_http** (HTTP `:8080` vs HTTPS admin for CDP/OCSP/AIA)
- HTTPS redirect uses `HTTPS_PORT` (not `:8080`)

## Automated tests

```bash
cd backend
pytest tests/test_discussion_207_crl_cert_ux.py \
       tests/test_discussion_207_batch2.py \
       tests/test_discussion_207_batch2_security.py \
       tests/test_crl.py \
       tests/test_crl_aki_rfc5280.py \
       tests/test_crl_rfc5280_profile.py -v

cd ../frontend
npx vitest run src/i18n/__tests__/discussion207CrlI18n.test.js \
               src/i18n/__tests__/discussion207Batch2I18n.test.js
```

### Non-regression (recommended)

```bash
cd backend
pytest tests/test_certificates.py tests/test_cas.py tests/test_settings.py -q
```

### Security (`test_discussion_207_batch2_security.py`)

| Test | Expectation |
|------|-------------|
| PATCH cert without auth | 401/403 |
| Empty / oversized description or friendly_name | 400 |
| Non-string friendly_name | 400 |
| PATCH `protocol_http` without auth / as viewer | 401/403 |
| `validityYears` > 100 | 400 |
| Invalid `validityEndDate` | 400 |

## Lab smoke

```bash
python3 scripts/lab_discussion_207_crl_cert_ux.py
python3 scripts/lab_discussion_207_batch2.py
python3 scripts/lab_crl_openssl_verify.py
```

Against a live lab (example `https://admin.ucm.pfcorp.eu:8443`):

1. **CRL & OCSP** → CA detail → Full CRL schedule + **CDP / OCSP URL transport** toggle HTTP ↔ HTTPS; confirm CDP URL scheme/port.
2. **Certificates** → issue with template → list shows template; detail → edit friendly name / description → save.
3. **CAs** → create with 50y or custom end date → certificate `notBefore`/`notAfter` match.
4. Issue cert → confirm `notBefore` ~15 minutes in the past (openssl).
5. Download CDP → Content-Disposition filename is slug-based.

## Manual UI (9 locales)

Switch language to each of: `en`, `fr`, `de`, `es`, `it`, `pt`, `uk`, `ja`, `zh`.

- [ ] CRL schedule labels
- [ ] Protocol transport title / options
- [ ] Certificate friendly name / template used / metadata section
- [ ] CA custom validity years / date messages
