# ACME proxy DNS UPDATE listener (RFC 2136) — Test plan

Feature: the ACME proxy accepts TSIG-signed DNS UPDATE messages (RFC 2136, RFC 8945) for DNS-01 challenges (#416). The listener checks the TXT value against the pending proxy order and writes nothing to DNS.

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

The test names start with the identifier of the scenario (`M…` message, `E…` EDNS, `T…` transport, `S…` TSIG, `U…` UPDATE, `Q…` query, `R…` expected values, `K…` keys, `N…` server, logs and security, `F…` regression test of a fixed defect) and end with `_pos` or `_neg`. Every scenario has a positive and a negative test.

| File | Scenarios |
|------|-----------|
| `test_dns_update_tsig.py` | RFC 8945 §5.2 order (key, MAC, time, truncation), BADKEY/BADSIG unsigned with MAC size 0, BADTIME with the server time, BADTRUNC, MAC size rules, fudge limit, time watermark, algorithms |
| `test_dns_update_handler.py` | RFC 2136 §3 order (zone, prerequisites, permission, prescan), add and delete forms, NOTAUTH/NOTZONE/REFUSED/FORMERR/NOTIMP, SOA answers (RFC 1034, RFC 2308), EDNS (RFC 6891), UDP size rules, replay cache, audit |
| `test_dns_update_records.py` | Expected TXT values (RFC 8555 §8.4), rows per order, closing on failed states, cache |
| `test_dns_update_keys_zones_audit.py` | Key scope (proxy account, EAB link), zone index, audit rate limits and the `reason` field |
| `test_dns_update_api.py` | Key API (secret shown once, algorithms, EAB link, 409), port setting validation, permissions with the auditor role and a custom role with `write:acme` only, `dns_update_key_count` of the account list |
| `test_dns_update_server.py` | UDP and TCP server (RFC 7766 framing, pipelining, idle timeout), rate limits, start and stop |
| `test_migration_111_acme_dns_update.py` | Tables and constraints on SQLite and PostgreSQL |
| `test_entrypoint_dns_update_port.py` | Docker entrypoint check of `UCM_DNS_UPDATE_PORT` |

Frontend:

```bash
cd frontend
npx vitest run src/pages/acme/__tests__/DnsUpdateKeysPanel.test.jsx \
  src/pages/acme/__tests__/DnsUpdatePortField.test.jsx \
  src/pages/acme/__tests__/dnsUpdateSnippets.test.js \
  src/pages/acme/__tests__/CaAccountsManager.dnsUpdate.test.jsx \
  src/i18n/__tests__/dnsUpdateI18n.test.js
npm run check:i18n
```

### Scenarios of the review round

| Scenario | Expected | Check |
|----------|----------|-------|
| Auditor permissions (`read:acme` only) | `GET` of keys and settings `200`. `POST` of a key, `DELETE` of a key and `PATCH` of `dns_update_port` give `403` and change nothing. A role with `write:acme` but not `delete:acme` gets `403` on `DELETE` | `test_dns_update_api.py`, `test_permissions_*` |
| Bind retry after reload | After `systemctl reload`, the new worker retries the bind for up to `graceful_timeout` + 5 s (35 s by default) while the old worker holds the port. Then `dns_update_listening` is `true` | `test_dns_update_server.py`. Lab: `systemctl reload`, then read `dns_update_listening` |
| SOA after the rows close | The SOA query is answered for 24 hours after the expected value expires, also after a failed validation or a downloaded certificate. An add still gets `REFUSED` without a pending order | `test_dns_update_handler.py`, `test_dns_update_records.py` |
| Zone below an entry | An UPDATE for a zone below an ACME Domains entry is accepted. A record outside that zone gets `NOTZONE` | `test_dns_update_handler.py`, `test_dns_update_keys_zones_audit.py` |
| Delete of type ANY | `update delete <name>` without a type for an `_acme-challenge` name gets `NOERROR` and changes nothing | `test_dns_update_handler.py`. Lab: `nsupdate` with `update delete _acme-challenge.<name>` |
| Sibling order while processing | UCM stores the expected value when a client fetches the authorization while the challenge is pending or processing (#307) | `test_dns_update_records.py` |
| `dns_update_key_count` | The account list gives the number of keys of any status for each account, `0` without keys, computed in one query | `test_dns_update_api.py`, `test_account_list_key_count_*` |
| UI warning for an account whose proxy is off | The button **DNS UPDATE keys** shows for an account with keys. The warning shows, **New key** is disabled, revoke and delete work. No keys and no proxy: no button | `DnsUpdateKeysPanel.test.jsx`, `CaAccountsManager.dnsUpdate.test.jsx` |

Lab results of the review round (Pebble upstream; the DNS provider publishes a wrong value for names that contain `fail`, so that the validation fails):

| Client | Before the change | After the change |
|--------|-------------------|------------------|
| certbot + dns-rfc2136, failed validation | Cleanup fails: `Unable to determine base domain` (SOA `REFUSED` after the rows closed) | Cleanup works: the delete is `NOERROR` |
| acme.sh `dns_nsupdate` without `NSUPDATE_ZONE`, failed validation | `Communication with 127.0.0.1#18054 failed: REFUSED`, `Error removing txt` | `Successfully removed` |
| lego rfc2136, failed validation | Cleanup works: lego keeps the SOA for its Refresh value and does not ask again | Same |
| cert-manager rfc2136 provider, failed validation | Cleanup works: cert-manager finds the zone through its recursive resolvers, not through UCM | Same |
| gunicorn `HUP` (reload) | — | The new worker gets `EADDRINUSE`, retries, and the listener is up after 4 attempts (2 s) |
| acme.sh, certbot, lego, cert-manager provider, valid order | — | Certificates, without the local patch |
| `nsupdate` with `zone host.example.com` (entry `example.com`) | — | `update delete _acme-challenge.host.example.com` gives `NOERROR`; an add with a wrong value gives `REFUSED` (not `NOTAUTH`) |

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
| certbot + dns-rfc2136 | Issue `certbot.example.com` (SOA over TCP, UPDATE over TCP) | Certificate | Pass with the lab patch (not needed since #420) |
| lego rfc2136 | Issue `lego.example.com` (delete ANY + add in one message) | Certificate | Pass with the lab patch (not needed since #420) |
| cert-manager rfc2136 | Issue `cm.example.com` and `*.wild.example.com` | Certificates | Pass with the lab patch (not needed since #420) |
| cert-manager rfc2136 | `HMACMD5` (its default) | `BADKEY` (shown as `bad authentication`), no certificate | Pass |
| cert-manager rfc2136 | Key `e2e-b.` (other proxy account) | `REFUSED`, no certificate | Pass |
| cert-manager rfc2136 | Zone `example.net.` (not in ACME Domains) | `NOTAUTH` (shown as `bad authentication`), no certificate | Pass |

**Final run after the review rounds** (commit `e056060`, fresh database, 2026-10-24): every case of the table was repeated with the same result. acme.sh issued `final.example.com` without any patch; the key of the other proxy account and the wrong secret were refused. certbot (`certbot-final.example.com`), lego (`lego-final.example.com`) and cert-manager (`cm-final.example.com`, `*.wildf.example.com`) issued with the lab patch for the "up" link. cert-manager negatives: `HMACMD5` → `bad authentication` (audit `rejected`, reason `badkey`), key of the other account → `REFUSED` (audit `refused`, `no_pending_order`), zone `example.net.` → `bad authentication` (audit `refused`, `not_authoritative`). The wrong secret of acme.sh is in the audit as `rejected`, `badsig`. The client CleanUp after a refused Present sends deletes, which are always accepted and change nothing (audit `accepted`).

### Handler interop harness

`DnsUpdateHandler` behind a plain UDP/TCP socket server, with in-memory keys, zones and one expected value. This checks the wire format with the real client libraries, without an ACME flow.

| Client | Cases | Result |
|--------|-------|--------|
| BIND `nsupdate` 9.18 | Signed SOA discovery, add, delete (class ANY and NONE), TCP (`-v`), `REFUSED` (wrong value, unsigned, prerequisite), `NOTAUTH`, `BADSIG`, `BADKEY` (unknown key, `hmac-md5`), `BADTIME` (client clock moved with `faketime`: "clocks are unsynchronized") | Pass |
| certbot-dns-rfc2136 5.8.0 | SOA walk up from `_acme-challenge.<name>`, `sign_query` false and true, add and delete; wrong value (`REFUSED`), `HMAC-MD5` (`BADKEY`), name outside the zones (no SOA found) | Pass |
| lego v4.35.2 | `hmac-sha256` add and delete, UDP answer with TC then retry over TCP, `hmac-sha1` (default) `BADKEY`, wrong value `REFUSED` | Pass |
| miekg/dns v2 (`codeberg.org/miekg/dns` v0.6.121, the library version that Go clients can move to) | Signed SOA query and UPDATE add and delete (class NONE), UDP and TCP, with and without EDNS: each answer verifies with `TSIGVerify`; wrong value `REFUSED` (signed); wrong secret `ErrSig`, unknown key `ErrKey` (header code `NOTAUTH`); three signed UPDATEs on one TCP connection with `ExchangeWithConn` (miekg/dns#1733 case) | Pass (27 checks, also on the final commit `e056060`) |
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

### Fixed: no `Link: rel="up"` from Pebble

**Status: fixed on `dev` by #420.** The proxy now uses the authorization URL that it knows when the upstream header is missing. The lab no longer needs the local patch. The text below describes the old problem.

certbot and lego need the `Link: <authz>;rel="up"` header in the answer to the challenge POST (`"up" Link header missing`, `authorization[get]: empty URL`). Pebble does not send it there. The ACME proxy of UCM only rewrites the header of the upstream CA, so the header is missing. This is not part of the listener: the same error occurs with `--manual` and no DNS UPDATE.

Before #420, the lab used a small change in `AcmeProxyService._get_authz_link`. It used the authorization URL that the proxy already knows when the upstream header is missing. #420 contains this fix, so certbot, lego and cert-manager pass without a patch.

### Cleanup

Stop gunicorn, Pebble and challtestsrv, and remove the lab data directory.
