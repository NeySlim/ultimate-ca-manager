# ACME proxy DNS UPDATE listener (RFC 2136) — Test plan

Feature: the ACME proxy accepts TSIG-signed DNS UPDATE messages (RFC 2136, RFC 8945) for DNS-01 challenges (#416). The listener checks the TXT value against the pending proxy order and writes nothing to DNS. Design and RFC mapping: [`docs/development/acme-proxy-dns-update/plan.pl.md`](../development/acme-proxy-dns-update/plan.pl.md).

## Automated tests (regression)

```bash
cd backend
python -m pytest tests/test_dns_update_tsig.py \
  tests/test_dns_update_handler.py \
  tests/test_dns_update_records.py \
  tests/test_dns_update_keys_zones_audit.py \
  tests/test_dns_update_models.py \
  tests/test_dns_update_api.py \
  tests/test_dns_update_server.py \
  tests/test_migration_111_acme_dns_update.py \
  tests/test_entrypoint_dns_update_port.py -q
# Reference 2026-10-24: 497 passed, 1 skipped (the PostgreSQL case)

# Migration 111 on PostgreSQL too:
UCM_TEST_PG_URL=postgresql://ucm@127.0.0.1:55432/ucmtest \
  python -m pytest tests/test_migration_111_acme_dns_update.py -q
# Reference: 6 passed (PostgreSQL 16)
```

The test names start with the identifier of the plan invariant (`T…` TSIG, `U…` UPDATE, `Q…` query, `N…` other) and end with `_pos` or `_neg`. Every invariant has a positive and a negative test.

| File | Scenarios |
|------|-----------|
| `test_dns_update_tsig.py` | RFC 8945 §5.2 order (key, MAC, time, truncation), BADKEY/BADSIG unsigned with MAC size 0, BADTIME with the server time, BADTRUNC, MAC size rules, fudge limit, time watermark, algorithms |
| `test_dns_update_handler.py` | RFC 2136 §3 order (zone, prerequisites, permission, prescan), add and delete forms, NOTAUTH/NOTZONE/REFUSED/FORMERR/NOTIMP, SOA answers (RFC 1034, RFC 2308), EDNS (RFC 6891), UDP size rules, replay cache, audit |
| `test_dns_update_records.py` | Expected TXT values (RFC 8555 §8.4), rows per order, closing on failed states, cache |
| `test_dns_update_keys_zones_audit.py` | Key scope (proxy account, EAB link), zone index, audit rate limits and the `reason` field |
| `test_dns_update_api.py` | Key API (secret shown once, algorithms, EAB link, 409), port setting validation |
| `test_dns_update_server.py` | UDP and TCP server (RFC 7766 framing, pipelining, idle timeout), rate limits, start and stop |
| `test_migration_111_acme_dns_update.py` | Tables and constraints on SQLite and PostgreSQL |
| `test_entrypoint_dns_update_port.py` | Docker entrypoint check of `UCM_DNS_UPDATE_PORT` |

Frontend:

```bash
cd frontend
npx vitest run src/pages/acme/__tests__/DnsUpdateKeysPanel.test.jsx \
  src/pages/acme/__tests__/DnsUpdatePortField.test.jsx \
  src/pages/acme/__tests__/dnsUpdateSnippets.test.js \
  src/i18n/__tests__/dnsUpdateI18n.test.js
npm run check:i18n
```

## End-to-end lab

The lab runs on one host, without internet access for the clients.

| Part | Version | Role |
|------|---------|------|
| Pebble | v2.10.1 | Upstream ACME CA |
| pebble-challtestsrv | v2.10.1 | Authoritative DNS for Pebble (port 8053) and for the UCM propagation check |
| UCM | this branch, gunicorn (`gunicorn_config.py`) | ACME proxy, DNS UPDATE listener on `127.0.0.1:18054` |
| UCM DNS provider | `custom_command` | A shell script that sends the TXT record to challtestsrv (`/set-txt`, `/clear-txt`) |
| acme.sh | 3.1.7 (`dns_nsupdate`), BIND `nsupdate` 9.18.39 | Client |
| certbot | 5.8.0 with `certbot-dns-rfc2136` 5.8.0 | Client |
| lego | v4.35.2 (`--dns rfc2136`) | Client |
| cert-manager | v1.21.3 `pkg/issuer/acme/dns/rfc2136` | DNS-01 solver, driven by a small Go program with the lego ACME library (no cluster) |

### Setup

1. Start Pebble and challtestsrv:

   ```bash
   PEBBLE_VA_NOSLEEP=1 PEBBLE_WFE_NONCEREJECT=0 PEBBLE_AUTHZREUSE=0 \
     pebble -config pebble-config.json -dnsserver 127.0.0.1:8053 &
   pebble-challtestsrv -dnsserver :8053 -management :8055 \
     -http01 "" -https01 "" -tlsalpn01 "" -doh "" -defaultIPv4 127.0.0.1 &
   ```

   `pebble-config.json` is the Pebble test configuration with `listenAddress` `127.0.0.1:14000`.

2. The DNS provider script for UCM (`challtest-dns.sh`):

   ```sh
   #!/bin/sh
   name="$RECORD_NAME"; case "$name" in *.) ;; *) name="$name.";; esac
   if [ "$ACTION" = "create" ]; then
     curl -s -X POST -d "{\"host\":\"$name\",\"value\":\"$RECORD_VALUE\"}" http://127.0.0.1:8055/set-txt
   else
     curl -s -X POST -d "{\"host\":\"$name\"}" http://127.0.0.1:8055/clear-txt
   fi
   ```

3. Start UCM with its own data directory. The CA bundle must contain the Pebble root (`test/certs/pebble.minica.pem`), so that UCM can register with Pebble:

   ```bash
   DATA_DIR=/srv/ucm-e2e HTTPS_PORT=18443 HTTP_PROTOCOL_PORT=0 HOST=127.0.0.1 \
   UCM_DNS_UPDATE_PORT=18054 UCM_DNS_UPDATE_HOST=127.0.0.1 \
   REQUESTS_CA_BUNDLE=/srv/ca-bundle-with-pebble.pem SSL_CERT_FILE=/srv/ca-bundle-with-pebble.pem \
     gunicorn -c gunicorn_config.py wsgi:app
   ```

   Set `SECRET_KEY`, `UCM_DB_ENCRYPTION_KEY` and `INITIAL_ADMIN_PASSWORD` too.

4. Configure UCM (web interface or API):
   - Settings: `acme.client.allow_loopback_upstream=true`, `acme.dns01_resolver_mode=custom`, `acme.dns01_nameservers=127.0.0.1:8053`.
   - DNS provider `custom_command` with the script of step 2 as create and delete command.
   - ACME Domains: `example.com` with that provider, wildcards allowed.
   - Two External CA accounts on `https://127.0.0.1:14000/dir`, both exposed via the proxy: slugs `pebble` and `pebble2`.
   - One DNS UPDATE key per account (`hmac-sha256`): `e2e-a.` for `pebble`, `e2e-b.` for `pebble2`. Save each secret in a BIND key file.

### Client commands

acme.sh:

```bash
export NSUPDATE_SERVER=127.0.0.1 NSUPDATE_SERVER_PORT=18054 NSUPDATE_KEY=keys/e2e-a.key
./acme.sh --issue --server https://127.0.0.1:18443/acme/proxy/pebble/directory --insecure \
  --dns dns_nsupdate --dnssleep 3 -d app.example.com --keylength ec-256
```

certbot (`rfc2136.ini` with `dns_rfc2136_server = 127.0.0.1`, `dns_rfc2136_port = 18054`, `dns_rfc2136_name = e2e-a.`, the secret, `dns_rfc2136_algorithm = HMAC-SHA256`):

```bash
certbot certonly --non-interactive --agree-tos --register-unsafely-without-email --no-verify-ssl \
  --server https://127.0.0.1:18443/acme/proxy/pebble/directory \
  --authenticator dns-rfc2136 --dns-rfc2136-credentials rfc2136.ini \
  --dns-rfc2136-propagation-seconds 3 -d certbot.example.com
```

lego:

```bash
DNSUPDATE_NAMESERVER=127.0.0.1:18054 DNSUPDATE_TSIG_KEY=e2e-a. DNSUPDATE_TSIG_SECRET="$S" \
DNSUPDATE_TSIG_ALGORITHM=hmac-sha256. LEGO_CA_CERTIFICATES=ucm-https.pem LEGO_DISABLE_CNAME_SUPPORT=true \
  lego --server https://127.0.0.1:18443/acme/proxy/pebble/directory --email lego@example.org \
  --accept-tos --dns rfc2136 --dns.propagation-wait 3s --domains lego.example.com run
```

cert-manager: a Go program calls `rfc2136.NewDNSProviderCredentials` of cert-manager v1.21.3 and uses its `Present` and `CleanUp` as the DNS-01 step of a lego ACME client. Arguments: directory, domain, key name, secret, algorithm (`HMACSHA256`), zone (`example.com.`). cert-manager in a cluster finds the zone with its recursive resolvers. The program gives the zone directly.

### Results (2026-10-24)

| Client | Case | Expected | Result |
|--------|------|----------|--------|
| acme.sh + nsupdate | Issue `app.example.com`, key `e2e-a.` | Certificate from Pebble, audit `acme.dns_update.accepted` | Pass |
| acme.sh + nsupdate | Key `e2e-b.` (other proxy account) | Signed SOA query `REFUSED`, no certificate | Pass |
| acme.sh + nsupdate | Right key name, wrong secret | `BADSIG`, no certificate; `nsupdate` repeats unsigned and ends with `REFUSED` | Pass |
| certbot + dns-rfc2136 | Issue `certbot.example.com` (SOA over TCP, UPDATE over TCP) | Certificate | Pass with the lab patch below |
| lego rfc2136 | Issue `lego.example.com` (delete ANY + add in one message) | Certificate | Pass with the lab patch below |
| cert-manager rfc2136 | Issue `cm.example.com` and `*.wild.example.com` | Certificates | Pass with the lab patch below |
| cert-manager rfc2136 | `HMACMD5` (its default) | `BADKEY` (shown as `bad authentication`), no certificate | Pass |
| cert-manager rfc2136 | Key `e2e-b.` (other proxy account) | `REFUSED`, no certificate | Pass |
| cert-manager rfc2136 | Zone `example.net.` (not in ACME Domains) | `NOTAUTH` (shown as `bad authentication`), no certificate | Pass |

### Handler interop harness

`DnsUpdateHandler` behind a plain UDP/TCP socket server, with in-memory keys, zones and one expected value. This checks the wire format with the real client libraries, without an ACME flow.

| Client | Cases | Result |
|--------|-------|--------|
| BIND `nsupdate` 9.18 | Signed SOA discovery, add, delete (class ANY and NONE), TCP (`-v`), `REFUSED` (wrong value, unsigned, prerequisite), `NOTAUTH`, `BADSIG`, `BADKEY` (unknown key, `hmac-md5`), `BADTIME` (client clock moved with `faketime`: "clocks are unsynchronized") | Pass |
| certbot-dns-rfc2136 5.8.0 | SOA walk up from `_acme-challenge.<name>`, `sign_query` false and true, add and delete; wrong value (`REFUSED`), `HMAC-MD5` (`BADKEY`), name outside the zones (no SOA found) | Pass |
| lego v4.35.2 | `hmac-sha256` add and delete, UDP answer with TC then retry over TCP, `hmac-sha1` (default) `BADKEY`, wrong value `REFUSED` | Pass |
| cert-manager v1.21.3 | `HMACSHA256` add and delete; `HMACMD5` and an algorithm that does not match the key (`BADKEY`), wrong value (`REFUSED`), zone not served (`NOTAUTH`). `miekg/dns` shows every `NOTAUTH` header code as `bad authentication` | Pass |

win-acme and Posh-ACME were not run (Windows). Their message forms (trial updates from the registrable domain, TTL 60, delete class NONE, `nsupdate` for Posh-ACME) are covered by the handler tests and by the `nsupdate` runs.

### miekg/dns (cert-manager, lego)

cert-manager v1.21.3 and lego v4.35.2 use `github.com/miekg/dns` v1.1.72. Facts from its source:

- `tsig.go`, `stripTsig`: a response with the header code `NOTAUTH` (9) gives `ErrAuth` ("bad authentication") before any MAC check. RFC 8945 puts every TSIG error under this header code, and RFC 2136 uses the same code for "not authoritative for the zone". So the client message is the same for `BADKEY`, `BADSIG`, `BADTIME` and a zone that is not in ACME Domains. The audit log of UCM tells them apart.
- `client.go`, `Exchange`: one new connection per message, closed after the answer.
- PR [miekg/dns#1316](https://github.com/miekg/dns/pull/1316) (merged 2021): the server side of the library does not sign `BADKEY` and `BADSIG` answers (RFC 8945 §5.3.2), the same rule as the UCM listener.
- PR [miekg/dns#1654](https://github.com/miekg/dns/pull/1654) (closed without merge, 2026-01): a client that requires a TSIG record on every non-FORMERR answer to a signed request. UCM signs the answers it builds for a request with a valid TSIG, and its `BADKEY`/`BADSIG` answers carry a TSIG record with an empty MAC, so this change would not break normal use of UCM.

The README of the GitHub repository says that it gets only specific fixes and that version 2 is at `codeberg.org/miekg/dns`. In v2 (checked: v0.6.121), `TSIGVerify` returns `ErrKey` for `BADKEY` and `ErrSig` for `BADSIG` and has no `NOTAUTH` shortcut, and `Client.Exchange` does not sign or verify TSIG by itself. A client that moves to v2 can show other messages.

### TSIG on one TCP connection (miekg/dns#1733)

The issue [miekg/dns#1733](https://github.com/miekg/dns/issues/1733) (open on 2026-10-24) is about a client that sends several signed messages on one TCP connection. RFC 8945 §5.3.1 chains the prior MAC only for the messages of one multi-message response (for example a zone transfer). Each independent request is signed as a first message (§4.3.1: the request MAC is used only for the response). The listener verifies each request on its own and keeps no TSIG state per connection.

- `test_T3_independent_signed_updates_on_one_connection_pos`: three signed UPDATEs on one TCP connection, each response verifies with the MAC of its own request.
- `test_T3_request_signed_with_the_prior_response_mac_is_badsig_neg`: a request signed with the MAC of the previous response gets an unsigned `BADSIG` and no confirmation; the next independent request on the same connection gets `NOERROR`.

cert-manager v1.21.3 and lego v4.35.2 use `miekg/dns` v1.1.72. They send each UPDATE with `Client.Exchange`, which opens a new connection and closes it after the answer (`client.go`, `Exchange`). The issue does not apply to them.

### Known issue in the lab: no `Link: rel="up"` from Pebble

certbot and lego need the `Link: <authz>;rel="up"` header in the answer to the challenge POST (`"up" Link header missing`, `authorization[get]: empty URL`). Pebble does not send it there. The ACME proxy of UCM only rewrites the header of the upstream CA, so the header is missing. This is not part of the listener: the same error occurs with `--manual` and no DNS UPDATE.

For the lab, a small change in `AcmeProxyService._get_authz_link` uses the authorization URL that the proxy already knows when the upstream header is missing. With it, certbot, lego and cert-manager pass. The change is not in this branch. It is a candidate for a separate fix.

### Cleanup

Stop gunicorn, Pebble and challtestsrv, and remove the lab data directory.
