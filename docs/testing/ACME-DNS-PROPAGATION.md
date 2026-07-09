# ACME DNS-01 propagation checks

UCM waits for the DNS-01 TXT record to be visible before telling the external
ACME CA to validate, instead of submitting immediately and burning the challenge
token on a validation failure. This document describes the resolver order, the
tunable settings, and what to do when a public resolver misbehaves.

Related: GitHub issue #171, #140.

## Resolver order

For each `_acme-challenge.<domain>` name, UCM queries in order:

1. **`acme.dns01_nameservers`** — comma-separated IPs in SystemConfig (optional)
2. **Authoritative nameservers** for the zone
3. **Public resolvers** — `9.9.9.9`, `8.8.8.8`, `1.1.1.1`
4. **System resolver** as last resort

A domain is **ready** when **any** of these paths returns the expected TXT value.
You do **not** need all three public resolvers to answer OK — the public-resolver
lines in the logs are informational only.

## TXT matching

Some public resolvers (notably Quad9) split long TXT character-strings across
multiple `<character-string>` elements in a single TXT RR (RFC 1035 §3.3.14).
UCM joins these chunks before comparing against the expected ACME token, so a
correctly published record is not misclassified as `pending` / `value_mismatch`
on such a resolver.

## Settings

| Key | Purpose |
|-----|---------|
| `acme.client.dns_propagation_timeout` | Seconds to poll before auto DNS submits to the CA. `0` = skip the propagation wait entirely. Default `120`. |
| `acme.client.debug_logging` | When `true`, DNS poll diagnostics (pending TXT, poll ticks, resolver lookup source, per-resolver failures) log at **INFO** instead of DEBUG. Implemented in `utils/acme_debug.py`, memoized per app context. |
| `acme.dns01_nameservers` | Optional comma-separated resolver IPs used **first** for propagation checks (and DNS-01 challenge cleanup). |

### `dns_propagation_timeout` behavior

| Value | Auto DNS (background poll) | Manual Verify |
|-------|---------------------------|--------------|
| `0`   | Skip polling; submit to CA immediately | Skip DNS gate; submit to CA immediately |
| `> 0` | Poll up to N seconds, then submit anyway if still missing | Block Verify until TXT visible or timeout; use **Force Verify** to override |

The UI helper text on **ACME → Let's Encrypt** reflects this split.

## Proxy and Renewal (LOT A)

Proxy and renewal no longer use a blind fixed 30s sleep:

- `services/acme/acme_proxy_service.py::_bg_respond_challenge`
- `services/acme_renewal_service.py::renew_certificate`

Both now use the shared active DNS self-check (`services/acme/dns_selfcheck.py`)
with `acme.client.dns_propagation_timeout`:

- `timeout=0` -> skip wait, submit immediately (legacy behavior)
- `timeout>0` -> poll for TXT visibility before submit

If proxy DNS never becomes visible before timeout, upstream challenge submission
is skipped and challenge state is marked `dns_not_ready`. Renewal deletes
created TXT records on propagation or finalization failure (same as the success
path cleanup).

### LOT A pytest plan

```bash
cd backend
python -m pytest tests/test_acme_dns_selfcheck.py tests/test_acme_proxy_ca_account.py -q
python -m pytest tests/test_acme.py::TestAcmeClientSettings -q
python -m pytest tests/test_acme_public_url.py tests/test_acme_security_paths.py::TestKeyChangeConflict::test_key_change_to_existing_account_key_rejected -q
```

### Excluding a problematic resolver

There is no per-resolver disable switch for the public-recursor diagnostic
(`9.9.9.9` / `8.8.8.8` / `1.1.1.1`), because those queries are informational
only and never block issuance. If you want to change which resolvers are
queried for the actual readiness decision, set
`acme.dns01_nameservers` to a custom comma-separated list of IPs; that list
replaces the public resolvers entirely for both the readiness check and the
DNS-01 challenge cleanup.

## Log interpretation

```
INFO  DNS TXT confirmed for _acme-challenge.example.com via authoritative resolver
INFO  DNS public propagation for _acme-challenge.example.com (diagnostic, does not block issuance): 9.9.9.9=pending, 8.8.8.8=OK, 1.1.1.1=OK
DEBUG DNS public resolver 9.9.9.9 returned no matching TXT for _acme-challenge.example.com: NXDOMAIN: ...
```

- The first `INFO` line means the self-check **succeeded**; challenges are
  then submitted to the CA.
- The `diagnostic, does not block issuance` line is emitted even on success to
  aid debugging. A `pending` entry there does **not** stop issuance.
- A `DEBUG` line per failing resolver shows the exception type
  (`NXDOMAIN` / `Timeout` / `NoAnswer` / `ConnectionError` / …) so a flaky
  resolver is distinguishable from a genuine propagation gap. Enable DEBUG on
  the `utils.dns_txt_lookup` logger to see them, or turn on **Verbose ACME/DNS
  logs** in **ACME → Let's Encrypt** to promote poll diagnostics to INFO.
