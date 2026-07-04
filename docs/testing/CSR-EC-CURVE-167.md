# CSR EC curve parsing — test plan

Fixes [#167](https://github.com/NeySlim/ultimate-ca-manager/issues/167): *Generate CSR* failed with `EC P-256` because the API stripped `EC` and validated `P-256` against OpenSSL curve names.

## Root cause

`POST /api/v2/csrs` did `key_type.replace('EC', '').strip()` → `"EC P-256"` became `"P-256"`, which is not a valid `KEY_TYPES` identifier.

## Fix

- `utils/key_type.py`: normalize UI labels (`EC P-256`, `NIST P-384`, `secp256r1`, …) → `prime256v1` / `secp384r1` / `secp521r1`
- UI: add **NIST P-521** option; labels aligned with [RFC 8422](https://www.rfc-editor.org/rfc/rfc8422.html#appendix-A) naming
- **secp256k1** intentionally not supported (non-NIST Koblitz curve; rare in enterprise TLS/PKI)

## Automated tests

```bash
cd backend
pytest tests/test_key_type.py -v
pytest tests/test_csrs.py::TestCreateCSR::test_create_csr_ec_key -v
pytest tests/test_csrs.py::TestCreateCSR::test_create_csr_ec_p521 -v
pytest tests/test_csrs.py::TestCreateCSR::test_create_csr_ec_invalid_curve -v
```

## Manual (UI)

1. **CSRs** → **Generate CSR**
2. CN: `example.org`, Key Type: **NIST P-256 (ECDSA)**, DNS SAN: `www.example.org`
3. Submit → CSR created, no curve error
4. Repeat with **NIST P-521 (ECDSA)**

## Lab deploy files

```bash
tar czf /tmp/ucm-csr167.tgz -C backend \
  api/v2/csrs.py \
  utils/key_type.py \
  services/trust_store/constants.py
```
