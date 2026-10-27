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

### Index of test IDs

Every ID in a test name, in the module docstring of `handler.py` and in its comments is listed here. The Rule column says what must hold. The RFC column gives the section, or "—" for a rule of UCM. The Tests column names the files with a test of that ID.

| Group | Meaning |
|-------|---------|
| `M` | message |
| `E` | EDNS |
| `S` | TSIG |
| `T` | transport |
| `U` | UPDATE |
| `Q` | query and SOA discovery |
| `R` | expected values |
| `K` | keys |
| `N` | server, logs and security |
| `A` | hardening of the listener: replay cache, SERVFAIL, cost of SOA queries, row cache, IPv6 limits |
| `B` | key cache that fails closed, audit limits, port setting, EAB link of keys |
| `D` | keys bound to EAB, cache retry, port checks, length of audit fields |
| `F` | regression test of a fixed defect |

#### M: message

| ID | Rule | RFC | Tests |
|----|------|-----|-------|
| M1 | A message with QR=1 gets no response. | RFC 1035 §4.1.1 | `test_dns_update_handler.py` |
| M2 | A message shorter than the 12 byte header gets no response. | RFC 1035 §4.1.1 | `test_dns_update_handler.py` |
| M3 | Opcodes QUERY and UPDATE are served. Other opcodes get NOTIMP with a header only. | RFC 8906 §3.1.4, §7; RFC 2136 §3 | `test_dns_update_handler.py` |
| M4 | A malformed message gets FORMERR with a header only. | RFC 8906 §7; RFC 2136 §3.1 | `test_dns_update_handler.py` |
| M5 | A QUERY with QDCOUNT other than 1 gets FORMERR. | RFC 9619 §3; RFC 1035 §4.1.2 | `test_dns_update_handler.py` |
| M6 | The Z bit is 0 in the response. The Z, AD and CD flags of the request are not echoed. | RFC 1035 §4.1.1; RFC 8906 §3.1.3 | `test_dns_update_handler.py` |
| M7 | RD is copied from the request. RA is always 0. | RFC 1035 §4.1.1; RFC 8906 §3.1.3.1 | `test_dns_update_handler.py` |
| M8 | The ID and the opcode are copied. A response for another ID does not match. | RFC 1035 §4.1.1; RFC 2136 §3.8 | `test_dns_update_handler.py` |

#### E: EDNS

| ID | Rule | RFC | Tests |
|----|------|-----|-------|
| E1 | The response has an OPT record only when the request had one. The advertised payload size is the limit of the listener. | RFC 6891 §6.1.1, §7 | `test_dns_update_handler.py` |
| E2 | One OPT record is valid. Two OPT records give FORMERR. | RFC 6891 §6.1.1 | `test_dns_update_handler.py` |
| E3 | EDNS version 0 is served. Version 1 gives BADVERS with an OPT record of version 0. | RFC 6891 §6.1.3; RFC 8906 §7 | `test_dns_update_handler.py` |
| E4 | Unknown EDNS options and flags are ignored and not echoed. | RFC 6891 §6.1.2, §6.1.4; RFC 8906 §3.2.3, §3.2.4 | `test_dns_update_handler.py` |
| E5 | The response has no padding. A request with a padding option gets no padding back. | RFC 6891 §7 | `test_dns_update_handler.py` |

#### S: TSIG

| ID | Rule | RFC | Tests |
|----|------|-----|-------|
| S1 | There is one TSIG record and it is last, else FORMERR. The TTL of the TSIG record is 0, else FORMERR. A message whose header ID changed is read as it was signed. If the names differ, the answer is FORMERR before the TSIG check. | RFC 8945 §4.2, §4.3.2, §5.1 | `test_dns_update_handler.py`, `test_dns_update_tsig.py` |
| S2 | An unknown or empty-secret key gives BADKEY without a signature (MAC size 0). | RFC 8945 §5.2.1, §5.3.2 | `test_dns_update_handler.py`, `test_dns_update_tsig.py` |
| S3 | The algorithm must be the algorithm of the key and one of sha256, sha384 or sha512. Else BADKEY. | RFC 8945 §5.2.1, §6, §7 | `test_dns_update_tsig.py` |
| S4 | A wrong MAC (flipped byte, wrong secret, changed body) gives BADSIG without a signature. | RFC 8945 §5.2.2, §5.3.2 | `test_dns_update_handler.py`, `test_dns_update_tsig.py` |
| S5 | The checks run in this order: key, MAC, time. A bad time with a good MAC gives BADTIME. A bad MAC gives BADSIG, an unknown key BADKEY. | RFC 8945 §5.2 | `test_dns_update_tsig.py` |
| S6 | A time outside the fudge gives BADTIME, signed with the key. It has the server time in Other Data and the client fudge. A small request fudge is used as given. | RFC 8945 §5.2.3, §5.3.2 | `test_dns_update_handler.py`, `test_dns_update_tsig.py` |
| S7 | A Time Signed older than the last accepted time of the key gives BADTIME. The time is kept for each key, is updated only by a valid request, and the table is bounded. | RFC 8945 §5.2.3 | `test_dns_update_tsig.py` |
| S8 | The MAC size must be the digest size, or at least max(10, digest/2) bytes. Else FORMERR. A correct truncated MAC gives a signed BADTRUNC, because the policy needs a full MAC. A wrong truncated MAC gives BADSIG. | RFC 8945 §5.2.2.1, §5.2.4, §7 | `test_dns_update_handler.py`, `test_dns_update_tsig.py` |
| S9 | The Error field of a request must be 0, else FORMERR. | RFC 8945 §4.2, §5.2 | `test_dns_update_tsig.py` |
| S10 | A response to a signed request is signed and verifies. A response to an unsigned request has no TSIG. A response needs a validated key. | RFC 8945 §5.3 | `test_dns_update_handler.py`, `test_dns_update_tsig.py` |
| S11 | The response MAC has the full length, also when the request MAC was truncated. | RFC 8945 §7 | `test_dns_update_tsig.py` |
| S12 | A truncated signed response keeps the TSIG and sets TC. A response above the limit is truncated, also without OPT. | RFC 8945 §5.3 | `test_dns_update_handler.py`, `test_dns_update_tsig.py` |
| S13 | Key names are compared without case. | RFC 8945 §4.2; RFC 1035 §2.3.3 | `test_dns_update_keys_zones_audit.py`, `test_dns_update_tsig.py` |
| S14 | The time window is the smaller of the request fudge and 300 s. BADTIME returns the fudge of the client. | RFC 8945 §5.2.3, §10 | `test_dns_update_tsig.py` |
| S15 | A replay (same key name and request MAC, any header ID, any transport) gets the stored response with no new side effects. A replay is checked after the MAC and before the time. A new request older than the watermark gets BADTIME. A replay with a wrong MAC gets BADSIG. A replay after the 600 s entry life is outside the window and gets BADTIME. Unsigned requests are not cached. The cache is bounded and thread safe. | RFC 8945 §10, §4.3.2 | `test_dns_update_handler.py`, `test_dns_update_tsig.py` |

#### T: transport

| ID | Rule | RFC | Tests |
|----|------|-----|-------|
| T1 | Over UDP, an unsigned response is not longer than the request. If it is, it is truncated (TC=1). | RFC 1035 §4.2.1; RFC 6891 §7 | `test_dns_update_handler.py` |
| T2 | Over UDP, a signed response may be up to 512 bytes (or the EDNS size). A longer one is truncated with TC and a TSIG. | RFC 1035 §4.2.1; RFC 6891 §6.2.3; RFC 8945 §5.3 | `test_dns_update_handler.py` |
| T3 | Over TCP, messages have a 2 byte length. The listener handles pipelined messages in order and a length in a separate segment. A length of 0 or above the maximum closes the connection. Each signed request is verified on its own. | RFC 1035 §4.2.2; RFC 7766 §6.2.1, §8 | `test_dns_update_server.py` |
| T4 | Over TCP, the response is full and not truncated. | RFC 8906 §3.2.7 | `test_dns_update_handler.py` |
| T5 | The idle timer counts from a full message. A half message and silence close the connection. A slow drip does not reset the timer. A connection ends after its lifetime. | RFC 7766 §6.2.3 | `test_dns_update_server.py` |

#### U: UPDATE

| ID | Rule | RFC | Tests |
|----|------|-----|-------|
| U1 | The zone section has exactly one record, of type SOA. Else FORMERR. | RFC 2136 §3.1.1 | `test_dns_update_handler.py` |
| U2 | The zone class is IN, else NOTAUTH. (A meta class is rejected by the parser with FORMERR first.) | RFC 2136 §3.1.1 | `test_dns_update_handler.py` |
| U3 | The zone must be a domain from ACME Domains or an ancestor of one. Else NOTAUTH. A zone below an entry is U16. | RFC 2136 §3.1.1 | `test_dns_update_handler.py`, `test_dns_update_keys_zones_audit.py` |
| U4 | An UPDATE without TSIG is REFUSED at once, before the zone check, with no audit row and no database access. | RFC 3007 §2, §3; RFC 2136 §3.3.1 | `test_dns_update_handler.py` |
| U5 | A non-empty prerequisite section is REFUSED (all five forms). | RFC 2136 §2.4, §3.2 | `test_dns_update_handler.py` |
| U6 | The class of an update record is IN, ANY or NONE. Class CH gives FORMERR. | RFC 2136 §3.4.1 | `test_dns_update_handler.py` |
| U7 | An update record name must be inside the zone, else NOTZONE. | RFC 2136 §3.4.1 | `test_dns_update_handler.py` |
| U8 | Prescan: a delete of class ANY has TTL 0 and no RDATA. A delete of class NONE has TTL 0. Else FORMERR. | RFC 2136 §3.4.1.2 | `test_dns_update_handler.py` |
| U9 | Only TXT at `_acme-challenge.<name>` can be changed. The first label is compared without case. Other types and names are REFUSED. | RFC 3007 §3.1; RFC 8555 §8.4 | `test_dns_update_handler.py` |
| U10 | An add needs an active row in the key scope with the same value. Two strings of one TXT are joined. One different character, another proxy account, another row, a non-ASCII value, or no active row is REFUSED. | RFC 3007 §3; RFC 8555 §8.4; RFC 1035 §3.3.14 | `test_dns_update_handler.py` |
| U11 | A delete of TXT (class NONE or ANY) is NOERROR and changes nothing, without a row. A delete of another type is REFUSED. A delete of all RRsets is U17. | RFC 2136 §2.5.2, §2.5.4, §3.4.2.3, §3.4.2.4 | `test_dns_update_handler.py` |
| U12 | One bad record rejects the whole message. A delete followed by a valid add is accepted (the lego pattern). A good add after a bad add is not applied. | RFC 2136 §3.3.2, §3.7 | `test_dns_update_handler.py` |
| U13 | Adding a value that was already added is NOERROR, also twice in one message. | RFC 2136 §2.5.1 | `test_dns_update_handler.py` |
| U14 | The response has the ID and opcode of the request, QR=1 and no sections. The update section is never echoed. | RFC 2136 §3.8 | `test_dns_update_handler.py` |
| U15 | An accepted update sets `client_confirmed_at` and `last_used_at` and writes an audit row. Nothing is written to DNS. A refused update changes nothing. | RFC 2136 §3.5 | `test_dns_update_handler.py` |
| U16 | A zone below an ACME Domains entry is accepted. A record outside that zone gets NOTZONE. A zone below another domain gets NOTAUTH. | RFC 2136 §3.1.1, §3.4.1 | `test_dns_update_handler.py`, `test_dns_update_keys_zones_audit.py` |
| U17 | A delete of all RRsets (class ANY, type ANY) at `_acme-challenge.<name>` is NOERROR and changes nothing. Type ANY with class IN or NONE, and the same delete at another name, are REFUSED. With RDATA it is FORMERR. | RFC 2136 §2.5.3, §3.4.1.2, §3.4.2.3 | `test_dns_update_handler.py` |

#### Q: query and SOA discovery

| ID | Rule | RFC | Tests |
|----|------|-----|-------|
| Q1 | An SOA query for the zone of an active row gets NOERROR, AA and one SOA with fixed values (TTL 0, MINIMUM 0). Without a row the answer is REFUSED. | RFC 8906 §3.1.1; RFC 1035 §3.3.13 | `test_dns_update_handler.py` |
| Q2 | A signed SOA query is answered with a signed response, for the rows of the key scope only. | RFC 8945 §5.3; RFC 3007 §3 | `test_dns_update_handler.py` |
| Q3 | Every other type is REFUSED. The SOA of an ancestor of the zone is REFUSED. | RFC 1035 §4.1.1 | `test_dns_update_handler.py` |
| Q4 | Class IN is served. Other classes are REFUSED. | RFC 1035 §4.1.1 | `test_dns_update_handler.py` |
| Q5 | Meta types (AXFR, IXFR, ANY and others) are REFUSED. | RFC 1035 §4.1.1; RFC 8906 §3.1.2 | `test_dns_update_handler.py` |
| Q6 | Names are compared without case. | RFC 1035 §2.3.3 | `test_dns_update_handler.py` |
| Q7 | An SOA query for a name between the zone and the record name gets NOERROR with no answer and the SOA in AUTHORITY. This covers the nsupdate, certbot and lego patterns, also over TCP after a truncated UDP answer. A name without a row is REFUSED. | RFC 2308 §2.2 | `test_dns_update_handler.py` |
| Q8 | Q1 and Q7 also work for a row for 24 h after `expires_at`, whatever its status. A signed query sees rows of the key scope only. An add with the value of a closed row is REFUSED. After the grace period the SOA is REFUSED. | RFC 2136 §3.1.1 | `test_dns_update_handler.py` |

#### R: expected values

| ID | Rule | RFC | Tests |
|----|------|-----|-------|
| R1 | The value is base64url(SHA-256(token "." thumbprint)) without padding, in the RFC alphabet. | RFC 8555 §8.1, §8.4; RFC 4648 §5; RFC 7638 §3 | `test_dns_update_records.py` |
| R2 | The record name is `_acme-challenge.` and the identifier without `*.`, in lower case. | RFC 8555 §8.4 | `test_dns_update_records.py` |
| R3 | A row is stored when a client fetches the authorization: one for each order, also for sibling orders. Nothing is stored for a valid authorization, a foreign client, an order without a dns-01 challenge, a name without a zone, or when nothing is new. | RFC 8555 §7.5 | `test_dns_update_records.py` |
| R4 | Rows close at the certificate download and at a failed state of the authorization or the challenge. Processing and valid keep them. `expires_at` is at most 24 h after creation. Old rows are purged. | RFC 8555 §7.1.4, §7.1.6 | `test_dns_update_records.py` |
| R5 | The key scope is the proxy account, and the ACME account when the key is linked to EAB. Another proxy account or ACME account is REFUSED. | RFC 3007 §3 | `test_dns_update_handler.py` |
| R6 | An error while a row is written (a duplicate, a flush error, a hook error) does not stop the authorization. | — | `test_dns_update_records.py` |
| R7 | The row of a sibling order has its own thumbprint. An order without a thumbprint gets no row. | RFC 8555 §8.1 | `test_dns_update_records.py` |
| R8 | The snapshot has two views: active rows (for adds) and rows up to 24 h after `expires_at` (for SOA discovery). A row older than that is in neither view. | RFC 2136 §3.1.1 | `test_dns_update_records.py` |
| R9 | A row is also stored while the challenge is processing. A final authorization or challenge stores none. A processing challenge starts no automation. | RFC 8555 §7.1.6 | `test_dns_update_records.py` |

#### K: keys

| ID | Rule | RFC | Tests |
|----|------|-----|-------|
| K1 | The secret comes from a random source. Its length is the digest size of the algorithm (32, 48, 64 bytes). Two keys never share a secret. | RFC 8945 §8 | `test_dns_update_api.py` |
| K2 | The secret is encrypted at rest. A corrupt ciphertext reads as none. | — | `test_dns_update_models.py` |
| K3 | The secret is returned only when the key is created. The list and `to_dict` never contain it. | — | `test_dns_update_api.py`, `test_dns_update_models.py` |
| K4 | Only hmac-sha256, hmac-sha384 and hmac-sha512 are accepted. Other algorithms give 400. | RFC 8945 §6, §7 | `test_dns_update_api.py` |
| K5 | A key name is a valid DNS name, normalized to lower case with a final dot. Each label has at most 63 bytes and only letters, digits, `_` and `-` (not at the start or end). The name is unique, also across accounts and ignoring case. A generated name uses the slug. Notes have at most 1000 characters. | RFC 8945 §4.2; RFC 1035 §2.3.1, §2.3.4 | `test_dns_update_api.py`, `test_dns_update_models.py` |
| K6 | A key without rows changes nothing. An add gets REFUSED. | RFC 3007 §3 | `test_dns_update_handler.py` |
| K7 | A secret that is empty, corrupt, not base64 or with a disallowed algorithm gives no key material. The key is then unknown (BADKEY), never an empty HMAC key. | RFC 8945 §5.2.1 | `test_dns_update_keys_zones_audit.py`, `test_dns_update_models.py` |
| K8 | A key with an EAB credential matches nothing when the credential is deleted, not used, or has no account, or when the row has no account. A used credential allows its own account only. Revoking or deleting the credential revokes or deletes the key. | RFC 3007 §3 | `test_dns_update_keys_zones_audit.py`, `test_dns_update_models.py` |
| K9 | Only an active key of an account with the proxy on is valid. A deleted account, a disabled proxy or a revoked key gives BADKEY. Deleting an account deletes its keys and rows. A new account does not inherit a key. | RFC 3007 §3 | `test_dns_update_keys_zones_audit.py`, `test_dns_update_models.py` |

#### N: server, logs and security

| ID | Rule | RFC | Tests |
|----|------|-----|-------|
| N1 | The port comes from `UCM_DNS_UPDATE_PORT`, then from the setting. 0 disables the listener. An invalid variable gives 0 and a warning. The `dns_update_listening` flag follows the listener. | — | `test_dns_update_api.py`, `test_dns_update_server.py` |
| N2 | The API accepts the port 0 or 1024 to 65535. It refuses other values, the HTTPS port and the HTTP protocol port. It shows the variable. A viewer gets 403. | — | `test_dns_update_api.py` |
| N3 | A busy UDP or TCP port makes the start return false. The application runs on. A free port listens and stop clears it. | — | `test_dns_update_server.py` |
| N4 | Limits: a global rate limit, a per-IP rate limit, a bounded per-IP table, a handler pool, and a TCP cap per source. Over the rate limit, a UDP packet or a TCP message gets no response. Over the TCP cap, the extra connection is closed. Traffic inside the limits is answered. | RFC 7766 §6.2.2, §6.2.3 | `test_dns_update_server.py` |
| N5 | The handler makes no outgoing connection and does no recursion. | RFC 8906 §3.1.3.1 | `test_dns_update_handler.py` |
| N6 | Unsigned and malformed requests are not audited. An accepted signed update is audited once with peer, key and transport. A signed refusal is audited with its reason. No row holds a TXT value. | — | `test_dns_update_handler.py` |
| N7 | One IP address writes one audit row for each reason in a window. The IP table is bounded. | — | `test_dns_update_keys_zones_audit.py` |
| N8 | Unsigned and BADKEY traffic runs no SQL. A signed accepted update uses the database. | — | `test_dns_update_handler.py` |
| N9 | The header counts and the size are checked before the parse. A QUERY with ANCOUNT above 0, QDCOUNT or ANCOUNT or NSCOUNT above 16, ARCOUNT above 4, or a message above 4096 bytes gets no response. | — | `test_dns_update_handler.py` |
| N10 | An exception gives SERVFAIL, signed when the TSIG was verified. The server goes on serving, also after an error in a side effect. | RFC 1035 §4.1.1; RFC 8945 §5.3 | `test_dns_update_handler.py`, `test_dns_update_server.py` |
| N11 | No log line of the module holds a secret, a MAC or a TXT value. | — | `test_dns_update_handler.py`, `test_dns_update_keys_zones_audit.py` |
| N12 | Audit rows for rejections have a global limit for each reason, for all IP addresses. A flood gives a bounded number of rows. | — | `test_dns_update_keys_zones_audit.py` |
| N13 | An audit row has the peer address, the user name `dns-update:<key>` or `dns-update:unauthenticated`, and the reason in the details. Names from the packet are shortened and cleaned. Writing never raises. | — | `test_dns_update_keys_zones_audit.py` |

#### A: hardening of the listener (replay, errors, cost, limits)

| ID | Rule | RFC | Tests |
|----|------|-----|-------|
| A1 | A replay is found by key name and request MAC. The entry lives 600 s (2 x 300 s fudge). A copy of a request that is still in work gets no response. A replay over the other transport has no new side effects. A different request is processed. | RFC 8945 §10, §4.3.2 | `test_dns_update_handler.py` |
| A2 | An error while a signed request is processed gives a signed SERVFAIL. An unsigned request, or a failed signing, gives a SERVFAIL with a header only. A failure is not stored in the replay cache. | RFC 8945 §5.3 | `test_dns_update_handler.py` |
| A3 | An SOA query for a name outside every zone of the snapshot parses no row names. Parsed names are cached (4096 entries). | — | `test_dns_update_handler.py` |
| A4 | A conflict on one row does not drop the other rows. One conflicting row gives 0 new rows and the authorization is still returned. The row cache is cleared only when a row was inserted. | — | `test_dns_update_records.py` |
| A5 | Per-address limits use the /64 network for IPv6 and the address for IPv4. The rate limit and the TCP cap per source use the same key. The TCP pool (128) needs 16 sources of 8 connections. | RFC 7766 §6.2.2 | `test_dns_update_server.py` |

#### B: fixes of the key cache, audit, port setting and EAB link

| ID | Rule | RFC | Tests |
|----|------|-----|-------|
| B1 | The key cache fails closed. After an invalidation and a failed reload, no key is found. After an expiry and a failed reload, the old cache stays. A retry comes after 2 s at the earliest, with one warning for each failed attempt. Only the EAB credentials that a key refers to are read. | — | `test_dns_update_keys_zones_audit.py` |
| B2 | An accepted update writes at most 120 audit rows for each key in a minute. The excess goes into one summary row. A per-IP drop is counted for its own reason. The key table is bounded. A failed audit write returns false. | — | `test_dns_update_keys_zones_audit.py` |
| B3 | An empty `UCM_DNS_UPDATE_PORT` is the same as no variable, and the stored setting is used. A set variable wins over the setting. An invalid stored value is 0. | — | `test_dns_update_api.py` |
| B4 | The DNS UPDATE port and the TLS-ALPN-01 port must differ. The check works in both directions and within one request. A disabled DNS UPDATE port (0) conflicts with nothing. `restart_required` is true only after a change, and not when the variable decides the port. | — | `test_dns_update_api.py` |
| B5 | Revoking an ACME EAB credential revokes the linked key. Deleting the credential deletes the linked key. Each change has an audit row. Other keys stay. | — | `test_dns_update_api.py` |

#### D: fixes of keys bound to EAB, cache retry, port checks and audit text

| ID | Rule | RFC | Tests |
|----|------|-----|-------|
| D1 | A key created with an EAB credential is marked `eab_bound`. A bound key whose credential is missing matches nothing. An unbound key matches the whole proxy account. | RFC 3007 §3 | `test_dns_update_api.py`, `test_dns_update_keys_zones_audit.py`, `test_dns_update_models.py` |
| D2 | `mark_eab_used` clears the key cache, so the scope allows the account at once. A failed mark keeps its return value and an invalidation error never changes the result. | — | `test_dns_update_keys_zones_audit.py` |
| D3a | `invalidate` inside the retry window reloads at once. With a failing database it empties the cache. | — | `test_dns_update_keys_zones_audit.py` |
| D3b | The zone index retries a failed load after the retry interval (2 s), not on every call. `invalidate` clears the retry time. | — | `test_dns_update_keys_zones_audit.py` |
| D4a | `restart_required` compares the new port with the port on which the listener runs. A listener that is not running counts as 0. | — | `test_dns_update_api.py` |
| D4b | The TLS-ALPN-01 port is checked against the port from the environment variable. Without the variable, a disabled DNS UPDATE port is ignored. | — | `test_dns_update_api.py` |
| D4c | A port in the variable outside 0 to 65535 is 0, with a warning. A port below 1024 is kept, with a warning. A valid port gives no warning. | — | `test_dns_update_api.py` |
| D4d | The effective port follows the variable. An invalid variable gives 0. Without a variable the stored port is used. | — | `test_dns_update_api.py` |
| D5 | The audit row fits the column limits: user name 80, resource name 255, address 45. A short key name is not changed. | — | `test_dns_update_keys_zones_audit.py` |

#### F: regression tests of fixed defects

| ID | Rule | RFC | Tests |
|----|------|-----|-------|
| F1 | A signed UDP answer that does not fit even in its truncated form is dropped and not cached. One that fits is sent with TC and cached. Key and zone lookups on a warm cache run no SQL. A cold cache does. | RFC 8945 §5.3; RFC 1035 §4.2.1 | `test_dns_update_handler.py`, `test_dns_update_keys_zones_audit.py`, `test_dns_update_tsig.py` |
| F2 | A key change is visible after `invalidate` and after the cache age (30 s). A restore clears the key and zone caches. The audit summary row of an accepted update belongs to the key and succeeds. The summary row of a refusal stays unauthenticated and failed. | — | `test_dns_update_keys_zones_audit.py` |
| F3 | A database error keeps the previous cache. On the first load it finds nothing. Deleting an account drops its rows from the warm row cache, and deleting another account does not. | — | `test_dns_update_api.py`, `test_dns_update_keys_zones_audit.py` |
| F4 | `touch` sets `last_used_at`, at most once per 60 s, and never raises. The same invalid port variable gives one warning. Another invalid value warns again. | — | `test_dns_update_api.py`, `test_dns_update_keys_zones_audit.py` |
| F5 | The settings GET reads the stored port once. A stored value that the caller gives is used without a database read. | — | `test_dns_update_api.py` |
| F6 | An SOA query looks only at the rows of its own zone. With nested zones the deepest zone wins. The row index is built again only for a new snapshot. | — | `test_dns_update_handler.py` |
| F8 | The listener binds `UCM_DNS_UPDATE_HOST`. Without it, it binds the HTTP host. | — | `test_dns_update_server.py` |
| F11 | `repr` of a key and of a TSIG result hides the secret and the MAC. | — | `test_dns_update_tsig.py` |

### Scenarios of the review round

| Scenario | Expected | Check |
|----------|----------|-------|
| Auditor permissions (`read:acme` only) | `GET` of keys and settings `200`. `POST` of a key, `DELETE` of a key and `PATCH` of `dns_update_port` give `403` and change nothing. A role with `write:acme` but not `delete:acme` gets `403` on `DELETE` | `test_dns_update_api.py`, `test_permissions_*` |
| Bind retry after reload | After `systemctl reload`, the new worker retries the bind while the old worker holds the port, first after 0.25 s, then after 0.5 s, then every second, without a time limit. After `graceful_timeout` + 5 s (35 s by default) it logs one error and goes on. Another bind error stops the retries and is logged with its message. Then `dns_update_listening` is `true` | `test_dns_update_server.py`, `test_retry_*`. Lab: `kill -HUP` on the gunicorn master |
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
