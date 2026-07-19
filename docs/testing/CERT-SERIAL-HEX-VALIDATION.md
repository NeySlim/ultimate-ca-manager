# Test plan — hex serial display (certificate details)

**Branch**: `feat/cert-serial-hex-display`
**Scope**: Certificates UI — **Technical details** section + `formatSerialNumberHex` utility

---

## 1. Automated tests (mandatory)

### Frontend (Vitest)

```bash
cd frontend
npm run test -- src/lib/__tests__/utils.test.js --run
```

| ID | Case | Expected |
|----|------|----------|
| T1 | UCM decimal serial (`4065849396…`) | `47:37:E6:35:…:D3:0B` |
| T2 | Compact hex (`4737E635…`) | Same colon-separated uppercase output |
| T3 | Hex already with `:` (lowercase) | Normalized to uppercase |
| T4 | Empty / invalid input | `null` |

Criterion: **39/39 passed** (`utils.test.js` suite including the 4 cases above).

### Backend (pytest — regression)

No backend change; run the full suite before merge:

```bash
cd backend
pytest -q --tb=no
```

Criterion: **0 failed** (warnings acceptable).

---

## 2. Manual UI test

1. Open **Certificates** → select a certificate issued by UCM.
2. **Technical details** panel:
   - **Serial**: decimal value (e.g. `406584939640065587371689749107479415526363616011`)
   - **Serial (hex)**: browser format (e.g. `47:37:E6:35:30:D7:EA:91:39:2B:51:4E:34:55:DB:E2:2E:A1:D3:0B`)
3. Copy the hex value (copy button) → paste into `openssl x509 -serial` or compare to the PEM certificate.
4. FR locale: label **Série (hex)**; EN: **Serial (hex)**.

---

## 3. Serial / OCSP correspondence

| Decimal (UCM) | Hex (UI / browser) |
|---------------|--------------------|
| `406584939640065587371689749107479415526363616011` | `47:37:E6:35:30:D7:EA:91:39:2B:51:4E:34:55:DB:E2:2E:A1:D3:0B` |
| `316154770811771731777519343495635219991455236293` | `37:60:DE:C7:AF:D7:7B:9A:B8:9D:86:BF:BD:08:D1:05:BA:A6:80:C5` |

OpenSSL verification:

```bash
openssl x509 -in cert.pem -noout -serial
# serial=4737E63530D7EA91392B514E3455DBE22EA1D30B  → same value without the ':'
```

---

## 4. Validation results (2026-07-03)

| Check | Result |
|-------|--------|
| Vitest `utils.test.js` | **39 passed** |
| backend pytest | see CI / local run |
| Deployment | build + dist deployed, field visible after hard refresh |

---

## Modified files

- `frontend/src/lib/utils.js` — `formatSerialNumberHex()`
- `frontend/src/components/CertificateDetails.jsx` — **Serial (hex)** field
- `frontend/src/lib/__tests__/utils.test.js` — tests T1–T4
- `frontend/src/i18n/locales/*.json` — `common.serialHex` key (9 languages)
