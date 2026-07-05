# Test plan — ACME key source (#161)

RFC 8555 §7.4: ACME finalize accepts a client-supplied CSR. This feature exposes
`generate`, `reuse` (renewal), and `csr` modes on the ACME client request path.

## Prerequisites

- Migration `049_acme_key_source_preflight` applied
- Service restarted after deploy

## Tests

### Generate (regression)

| # | Action | Expected |
|---|--------|----------|
| 1 | Key source = Generate, staging | Cert issued with private key in UCM |
| 2 | Renewal | New key (default behaviour) |

### Reuse on renewal

| # | Action | Expected |
|---|--------|----------|
| 1 | Request with Reuse key on renewal | First issue OK, key stored |
| 2 | Manual/auto renew | Same public key fingerprint |

```bash
openssl x509 -in cert1.pem -pubkey -noout > k1.pub
openssl x509 -in cert2.pem -pubkey -noout > k2.pub
diff k1.pub k2.pub   # empty = same key
```

### External CSR

| # | Action | Expected |
|---|--------|----------|
| 1 | Paste PEM CSR, matching domains | Order created |
| 2 | Finalize after challenge | Cert without private key in UCM |

```bash
openssl req -new -newkey rsa:2048 -nodes \
  -keyout t.key -out t.csr \
  -subj "/CN=test.example.com" \
  -addext "subjectAltName=DNS:test.example.com"
```

## Automated tests

```bash
cd backend && python -m pytest tests/test_acme_key_source.py -v
```

## API

`POST /api/v2/acme/client/request` body fields:

- `key_source`: `generate` | `reuse` | `csr`
- `csr_pem`: required when `key_source=csr`
- `source_certificate_id`: optional for immediate reuse from an existing cert
