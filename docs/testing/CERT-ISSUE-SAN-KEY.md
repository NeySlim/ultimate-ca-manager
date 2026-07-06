# Issue Certificate — SAN types & EC curves — test plan

Extends [#167](https://github.com/NeySlim/ultimate-ca-manager/issues/167) / [#168](https://github.com/NeySlim/ultimate-ca-manager/pull/168) to **Émettre un certificat** (`POST /api/v2/certificates`).

PR: [#169](https://github.com/NeySlim/ultimate-ca-manager/pull/169)

## Fixes

- **Typed SAN enforcement**: FQDN in IP field → HTTP 400 (no silent DNS reclassification)
- **EC curves**: `ecdsa` + `256` / `NIST P-384` / UI labels → `prime256v1` / `secp384r1` / `secp521r1`
- **CN auto-SAN**: email CN (`fred@fred.fr`) is **not** auto-added as DNS on server certs; use **Email** or **Combined** cert type for email SAN
- **i18n**: validation messages under `certificates.san*` (9 locales); CSR key labels under `csrs.key*`
- **UI clarity**: certificate details label **Issuer signature algorithm** (`common.issuerSignatureAlgorithm`) — distinct from **Key type** (EE public key). An EC P-521 cert issued by an RSA CA correctly shows `SHA256-RSA` as issuer signature.

## Automated tests

```bash
cd backend
pytest tests/test_san_parse.py::TestParseCertSanPayload -v
pytest tests/test_san_parse.py::TestAutoSanFromCn -v
pytest tests/test_key_type.py::TestParseIssueKeyType -v
pytest tests/test_certificates.py::TestCreateCertificate -v
pytest tests/test_cert_issuer_signature.py -v

cd ../frontend
npm test -- --run src/lib/__tests__/sanValidate.test.js
npm test -- --run src/i18n/__tests__/issuerSignatureI18n.test.js
```

### Regression (`test_cert_issuer_signature.py`)

| Test | Expectation |
|------|-------------|
| EC P-521 EE + RSA CA | X.509 pubkey `secp521r1`, signature OID RSA (SHA256-RSA in API) |
| RSA EE + RSA CA | RSA pubkey, SHA256-RSA issuer signature |
| EC EE + ECDSA CA | EC pubkey, ECDSA issuer signature OID |
| Legacy `san` string | Still parses DNS + IP buckets |

### Security (`test_cert_issuer_signature.py`)

| Test | Expectation |
|------|-------------|
| Email in `san_dns` | HTTP 400 |
| Invalid EC curve `999` | HTTP 400 |
| FQDN in `san_ip` | HTTP 400 (see `test_certificates.py`) |

## Manual (UI)

1. **Certificates** → **Issue Certificate**
2. Type **Serveur**, CN `fred@fred.fr` → no auto DNS SAN row (empty auto-SAN block)
3. Type **Email**, same CN → auto **email** SAN `fred@fred.fr`
4. Add SAN type **IP** with `www.example.com` → client error (translated)
5. Key type **ECDSA** + **NIST P-521** → certificate issued
6. Open certificate details → **Key type** = `EC secp521r1`, **Issuer signature algorithm** = `SHA256-RSA` when CA is RSA (tooltip explains independence)
7. Hover issuer signature label → hint visible in all 9 languages

## Lab API smoke (optional)

```bash
# Login + CSRF, then POST /api/v2/certificates with ecdsa/521
# GET /api/v2/certificates/:id/export?format=pem → openssl x509 -text
# Verify: Public Key Algorithm id-ecPublicKey, Signature Algorithm sha256WithRSAEncryption (RSA CA)
```
