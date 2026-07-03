# Test plan — ACME preflight / dry-run (#162)

Validates ACME certificate requests against Let's Encrypt **staging** (or
connectivity-only for custom CAs) without consuming production rate limits or
changing global ACME settings.

Depends on #161 (key_source fields used during CSR validation in preflight).

## Prerequisites

- PR #161 merged or deployed (migration 049)
- LE staging account registered (for `full` mode)

## Tests

### Validate only

| # | Action | Expected |
|---|--------|----------|
| 1 | Run preflight, mode Validate only | Steps: domains, email, ca_connectivity, account_eab |
| 2 | Production CA selected | Directory URL in report = staging LE |
| 3 | Settings → Default Environment | Unchanged after preflight |

### Full (staging order + TXT)

| # | Action | Expected |
|---|--------|----------|
| 1 | DNS-01 manual, mode Full | TXT records shown in modal |
| 2 | Verify DNS unchecked | No dns_propagation step failure blocking report |
| 3 | Verify DNS checked after adding TXT | dns_propagation = pass |
| 4 | GET /acme/client/orders | No leftover preflight order rows |

### Webhook & audit

| # | Action | Expected |
|---|--------|----------|
| 1 | Webhook subscribed to `acme.preflight` | Event received |
| 2 | Audit log | `acme_preflight` entry |

## Automated tests

```bash
cd backend && python -m pytest tests/test_acme_preflight.py -v
```

## API

`POST /api/v2/acme/client/preflight`

```json
{
  "domains": ["test.example.com"],
  "email": "admin@example.com",
  "challenge_type": "dns-01",
  "mode": "full",
  "verify_dns": false
}
```

Response: `{ "ok": bool, "steps": [...], "txt_records": [...] }`
