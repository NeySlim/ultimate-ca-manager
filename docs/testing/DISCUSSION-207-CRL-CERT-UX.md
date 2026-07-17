# Discussion #207 — CRL / cert UX + protocol URL flexibility — test plan

PR: [#208](https://github.com/NeySlim/ultimate-ca-manager/pull/208)  
Discussion: [#207](https://github.com/NeySlim/ultimate-ca-manager/discussions/207)

## Scope

### Batch 1
- CRL validity vs publish interval (`next_publish`), CRL digest, CDP filename, notBefore skew, template digest/`usage_count`, HTTP port 80

### Batch 2
- Cert description / friendly name, template column, CA validity ≤100y, HTTPS redirect port

### Protocol URL flexibility (complete)
| Layer | Control |
|-------|---------|
| Global | Settings → `protocol_base_url` (must be `http://`) + `http_protocol_port` |
| Per CA `protocol_mode` | `inherit` \| `http_protocol` \| `https_admin` \| `custom` |
| Per CA override | `protocol_base_url_override` (mode=`custom`) |
| Per endpoint | `cdp_base_url` / `ocsp_base_url` / `aia_base_url` |
| Legacy | `protocol_http` bool → maps to inherit / https_admin |

**TLS loop:** prefer HTTP protocol Settings URL. `https_admin` / `https://` custom bases are allowed but warned in UI.

## Automated tests

```bash
cd backend
pytest tests/test_discussion_207_crl_cert_ux.py \
       tests/test_discussion_207_batch2.py \
       tests/test_discussion_207_batch2_security.py \
       tests/test_protocol_url_flexibility.py \
       tests/test_protocol_url_flexibility_security.py \
       tests/test_crl.py \
       tests/test_crl_aki_rfc5280.py \
       tests/test_crl_rfc5280_profile.py -v

# Non-regression
pytest tests/test_certificates.py tests/test_cas.py tests/test_settings.py -q

cd ../frontend
npx vitest run src/i18n/__tests__/discussion207CrlI18n.test.js \
               src/i18n/__tests__/discussion207Batch2I18n.test.js
```

### Security (`test_protocol_url_flexibility_security.py`)

| Test | Expectation |
|------|-------------|
| PATCH mode without auth / as viewer | 401/403 |
| Unknown `protocol_mode` | 400 |
| Localhost / path / javascript: / oversized override | 400 |
| `file://` CDP base | 400 |
| `https://` custom | 200 (allowed, operator choice) |
| `custom` without any base | 400 |

## Lab smoke

```bash
python3 scripts/lab_discussion_207_crl_cert_ux.py
python3 scripts/lab_discussion_207_batch2.py
```

Live lab checklist (`https://admin.ucm.pfcorp.eu:8443`):

1. Settings → confirm `protocol_base_url=http://pki.ucm.pfcorp.eu`, port `8080`
2. CRL & OCSP → CA → mode **Inherit** → CDP starts with `http://pki…:8080`
3. Mode **HTTPS admin** → warning; CDP uses admin `:8443` (restore Inherit after)
4. Mode **Custom** → `http://pki-lab…:8080` → CDP regenerated
5. Advanced → set CDP-only base; OCSP stays on CA mode base
6. Cert friendly name / description PATCH still works

## Manual UI (9 locales)

`en` `fr` `de` `es` `it` `pt` `uk` `ja` `zh` — verify protocol mode labels, custom field, advanced endpoints, TLS warning.
