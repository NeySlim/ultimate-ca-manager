# CA details polish — test plan

Follow-up fixes for [PR #164 review](https://github.com/NeySlim/ultimate-ca-manager/pull/164#issuecomment-4882185221) (plaimbock).

## Scope

| Issue | Fix |
|-------|-----|
| Duplicate "Validity Period" in Create CA modal | Remove redundant section heading |
| Serial shows `0`/`1` in Technical Details | `GET /api/v2/cas/:id` exposes X.509 `serial_number` (colon hex) |
| Empty fingerprints | Fix `DefaultBackend` in fingerprint mixin + API maps `thumbprint_sha256` / `thumbprint_sha1` |
| Intermediate `notAfter` after parent | Clamp child validity to parent `not_valid_after` |

## Automated tests

```bash
cd backend
pytest tests/test_cas.py::TestGetCA::test_get_ca_includes_x509_serial_and_fingerprints -v
pytest tests/test_cas.py::TestCreateCA::test_intermediate_valid_to_clamped_to_parent -v
pytest tests/test_cas.py::TestGetCA -v
pytest tests/test_cas.py::TestCreateCA -v
```

## Manual validation (UI)

1. **Create CA modal** — open *Create CA*; confirm a single "Validity Period" label (no duplicate heading).
2. **Root CA details** — create root (e.g. ECDSA P-384, 10 years); open Technical Details:
   - Serial is colon-separated hex (not `0` or `1`).
   - Fingerprints section shows SHA-256 and SHA-1.
3. **Intermediate validity** — create root with 5 years, then intermediate with 20 years under that root:
   - Intermediate *Valid until* equals root *Valid until* (not 20 years later).
4. **Cross-check** — compare displayed serial with:
   ```bash
   openssl x509 -in /opt/ucm/data/cas/<refid>.crt -noout -serial
   ```

## Lab deploy (`172.31.10.8`)

Backend paths under `/opt/ucm/backend`, service `ucm`, frontend `/opt/ucm/frontend/dist`.

```bash
# From dev machine (workspace root)
cd ultimate-ca-manager
tar czf /tmp/ucm-ca-polish.tgz -C backend \
  api/v2/cas/crud.py \
  services/ca/ca_creation.py \
  services/trust_store/ca_certificate_creation_mixin.py \
  services/trust_store/fingerprint_mixin.py \
  utils/serial_format.py \
  utils/datetime_utils.py

scp /tmp/ucm-ca-polish.tgz root@172.31.10.8:/tmp/

ssh root@172.31.10.8 '
  cd /opt/ucm/backend && tar xzf /tmp/ucm-ca-polish.tgz
  systemctl restart ucm && systemctl is-active ucm
'

# Frontend (build locally, deploy dist)
cd frontend && npm run build
tar czf /tmp/ucm-fe-ca-polish.tgz -C dist .
scp /tmp/ucm-fe-ca-polish.tgz root@172.31.10.8:/tmp/
ssh root@172.31.10.8 'rm -rf /opt/ucm/frontend/dist/* && tar xzf /tmp/ucm-fe-ca-polish.tgz -C /opt/ucm/frontend/dist'
```

## API smoke (authenticated)

```bash
TOKEN=<api_token>
curl -s -H "Authorization: Bearer $TOKEN" https://<host>/api/v2/cas/1 | jq '.data | {serial_number, thumbprint_sha256, thumbprint_sha1, valid_to}'
```

Expected: non-empty `serial_number` with colons; both thumbprints populated.
