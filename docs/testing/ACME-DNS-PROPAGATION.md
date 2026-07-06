# ACME DNS-01 propagation checks

This document describes how Ultimate CA Manager (UCM) waits for DNS-01 TXT
records before submitting challenges to an external ACME CA, and how to tune
behavior when propagation is slow or a public resolver misbehaves.

Related: GitHub issue #171, #140.

## Resolver order

For each `_acme-challenge.<domain>` name, UCM queries in order:

1. **`acme.dns01_nameservers`** — comma-separated IPs in SystemConfig (optional)
2. **Authoritative nameservers** for the zone
3. **Public resolvers** — `9.9.9.9`, `8.8.8.8`, `1.1.1.1`
4. **System resolver** as last resort

A domain is **ready** when **any** of these paths returns the expected TXT value.
You do **not** need all three public resolvers to answer OK.

## Settings

| Key | Purpose |
|-----|---------|
| `acme.client.dns_propagation_timeout` | Seconds to poll before auto DNS submits to the CA. `0` = skip propagation wait entirely. Default `120`. |
| `acme.dns01_nameservers` | Optional comma-separated resolver IPs used **first** for propagation checks (and DNS-01 challenge cleanup). |

### `dns_propagation_timeout` behavior

| Value | Auto DNS (background poll) | Manual Verify |
|-------|---------------------------|---------------|
| `0` | Skip polling; submit to CA immediately | Skip DNS gate; submit to CA immediately |
| `> 0` | Poll up to N seconds, then submit anyway if still missing | Block Verify until TXT visible or timeout; use **Force Verify** to override |

The UI helper text on **ACME → Let's Encrypt** reflects this split.

### Excluding a problematic resolver

If one public resolver (e.g. Quad9) returns stale `NXDOMAIN` while authoritative
DNS is correct, UCM still proceeds when authoritative or another resolver
confirms the TXT. Logs show per-resolver status, e.g.:

```
DNS public propagation for _acme-challenge.example.com: 9.9.9.9=pending (nxdomain), 8.8.8.8=OK, 1.1.1.1=pending (timeout)
DNS public propagation summary for _acme-challenge.example.com: 1/3 resolvers OK (informational only; UCM proceeds when authoritative or any resolver confirms)
```

To avoid querying a bad resolver during checks, set `acme.dns01_nameservers` to
the resolvers you trust (e.g. `8.8.8.8,1.1.1.1`) until the upstream issue is
resolved. Leave empty to use the default chain above.

## Logs

When a resolver does not see the expected TXT, the pending reason is logged:

- `nxdomain` — name does not exist from that resolver
- `no_answer` — name exists but no TXT RR
- `value_mismatch` — TXT present but wrong value
- `timeout` — query timed out

Authoritative confirmation is logged separately:

```
DNS TXT confirmed for _acme-challenge.example.com via authoritative resolver
```

## Manual Verify and Force Verify

- **Verify** (manual DNS): respects `dns_propagation_timeout` unless it is `0`.
- **Force Verify**: bypasses the DNS gate even when timeout is positive (use when
  you know the record is published but UCM cannot see it yet).

## Code references

- `backend/utils/dns_txt_lookup.py` — resolver chain and logging
- `backend/api/v2/acme_client/orders.py` — `_dns_selfcheck`, `verify_challenges`, `_auto_poll_and_finalize`
- `backend/tests/test_acme_dns_selfcheck.py` — unit tests
