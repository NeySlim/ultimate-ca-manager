# Plan: DNS UPDATE (RFC 2136) listener for the UCM ACME proxy

Status: version 3. After the security review of the plan (findings F1–F15 in section 11). The PR 2 code is done (parts 2–9). The E2E tests are done (section 8). Changes against the plan during the work: section 2.2 point 5 (rows are closed only in error states).

## 0. Sources

| Source | Where |
|---|---|
| Maintainer requirements | NeySlim/ultimate-ca-manager#416, comment by NeySlim from 2026-10-24 |
| RFC texts (official) | `https://www.rfc-editor.org/rfc/rfcNNNN.txt` |
| UCM code | base branch: `upstream/dev` (NeySlim, 2.246-dev, `3ece475`); CONTRIBUTING.md: PRs go to `dev` |
| Client code | section 9 (client versions and commits) |
| dnspython 2.8.0 | `dns/tsig.py`, `dns/message.py` from the wheel `dnspython-2.8.0-py3-none-any.whl` |

RFCs used as invariants:

| RFC | Topic | Sections used |
|---|---|---|
| 1034, 1035 | DNS, message format, SOA, UDP/TCP | 1034 §3.1, §4.3.2; 1035 §3.3.13, §3.3.14, §4.1.1, §4.2.1, §4.2.2 |
| 2136 | DNS UPDATE | §2, §3.1–§3.8 |
| 3007 | Secure UPDATE, policy | §2, §3, §3.1 |
| 8945 | TSIG | §4.2, §5.1–§5.4, §6, §7, §8 |
| 6891 | EDNS(0) | §6.1.1, §6.1.3, §6.2.3, §7 |
| 7766 | DNS over TCP | §6.2.1–§6.2.4, §8 |
| 8906 | Answer instead of silence | §3.1.1–§3.1.5, §3.2.2–§3.2.5, §7 |
| 9619 | QDCOUNT = 1 | whole document |
| 2308 | Negative answers (NODATA) | §2.2, §3 |
| 8555, 7638, 4648 | dns-01 value, JWK thumbprint, base64url | 8555 §7.1.4, §8.1, §8.4; 7638 §3; 4648 §5 |

## 1. Scope and split into PRs

The maintainer wants two PRs:

1. **PR 1 – documentation (variant D).** Workarounds for each client. Resolver limits: cert-manager `--dns01-recursive-nameservers` and `--dns01-recursive-nameservers-only`, acme.sh `--dnssleep`, a conditional forwarder for `_acme-challenge`.
2. **PR 2 – listener.** Backend, migration, UI, translations (9 languages), Helm, packages, documentation, tests.

Both changes are based on `upstream/dev`. CONTRIBUTING.md says: a PR goes to `dev`. The fork `WMP` is behind upstream. Requirements of CONTRIBUTING.md: an entry in the CHANGELOG under `## [Unreleased]`, texts in 9 languages, a migration for SQLite and PostgreSQL, a commit subject `type(scope): summary` (< 72 characters). WMP has already signed the CLA v1.1 (2026-10-23).

## 2. Architecture

```
ACME client ──UDP/TCP──> [server.py] ─bytes─> [handler.py] ──> [tsig.py]   (RFC 8945)
                                                   │
                                                   ├──> [policy.py] ──> [records.py] (expected TXT, DB)
                                                   │                └──> [keys.py]    (TSIG keys, DB)
                                                   └──> audit / log
ACME proxy get_authz ──> records.py.persist()   (stores the expected value when authz is fetched)
ACME proxy get_certificate ──> records.py.close_order()
```

New package: `backend/services/acme/dns_update/`.

| Module | Responsibility | Dependencies |
|---|---|---|
| `constants.py` | Limits, algorithms, codes | none |
| `tsig.py` | Server-side TSIG verification in the order of RFC 8945 §5.2. Builds signed responses and TSIG errors | dnspython (public API only) |
| `keys.py` | Reads keys from the DB, algorithm policy, FIPS | model, `fips_mode` |
| `records.py` | Stores and reads expected TXT values, key scope | model, proxy |
| `policy.py` | Zones for which UCM "is authoritative"; the right to change a record | `records.py`, ACME Domains |
| `handler.py` | Pure function `handle(wire, transport, peer, now) -> bytes | None`. No sockets. All RFC logic | the modules above |
| `server.py` | UDP and TCP sockets (gevent), limits, start and stop | `handler.py` |

Rule: all protocol logic is in `handler.py` and `tsig.py`. These modules do not open sockets. Because of this, each RFC invariant has a unit test at the level of message bytes.

### 2.1 Data model (new tables, migration 111)

**`acme_dns_update_keys`** (TSIG keys):

| Field | Description |
|---|---|
| `id` | PK |
| `acme_client_account_id` | FK to `acme_client_accounts` (proxy account, slug), `ON DELETE CASCADE`. SQLite in UCM does not enforce FKs, so deleting an account also deletes the keys and rows in code (`_remove_account_row`) (F3) |
| `eab_credential_id` | FK to `acme_eab_credentials`, `ON DELETE CASCADE`, NULL = no link. Deleting an EAB credential also deletes the linked keys in code (EAB DELETE handler) (F2) |
| `name` | Key name as a DNS name, absolute, lowercase, unique (RFC 8945 §4.2) |
| `algorithm` | `hmac-sha256` (default), `hmac-sha384`, `hmac-sha512` |
| `secret` | Secret encrypted like the EAB HMAC: `utils.encryption.encrypt_if_needed` (Fernet, always on). A secret that cannot be decrypted, or an empty secret, is never used: key = unknown (BADKEY) (F4) |
| `status` | `active` / `revoked` |
| `created_at`, `created_by_user_id`, `last_used_at`, `revoked_at`, `notes` | |

**`acme_proxy_dns_challenges`** (expected TXT values):

| Field | Description |
|---|---|
| `id` | PK |
| `order_id` | FK to `acme_client_orders`, `ON DELETE CASCADE` |
| `acme_client_account_id` | proxy account (slug) of the order |
| `account_id` | local `AcmeAccount.account_id` of the client (used for the link to EAB) |
| `client_jwk_thumbprint` | client thumbprint (RFC 7638) |
| `identifier` | domain without `*.` |
| `record_name` | `_acme-challenge.<identifier>.`, lowercase |
| `zone_name` | D: the apex from "ACME → Domains" (`find_provider_for_domain(identifier)`, without `*.`), computed when the row is stored; because of this, the SOA response needs no DB query |
| `txt_value` | `base64url(SHA-256(token "." thumbprint))`, 43 characters |
| `upstream_challenge_url` | for diagnostics |
| `status` | `pending` / `closed` |
| `created_at`, `expires_at`, `client_confirmed_at` | |
| UNIQUE | (`order_id`, `record_name`, `txt_value`) |

Both tables are also added to: the SQLAlchemy models (`db.create_all()` for a new installation), the backup manifest (`services/backup/manifest.py`), the migration test (SQLite and PostgreSQL).

### 2.2 Life cycle of an expected value

1. The client fetches authz (`get_authz`). For each `dns-01` challenge in the `pending` state, UCM stores a row for the client order **and for the sibling orders** (the same upstream authz, #307). The row of a sibling has **its own** `client_jwk_thumbprint` and the `account_id` of the sibling. An order without a thumbprint gets no row. The write is idempotent and does not depend on whether the DNS automation has already started (F13b).
2. The write is "best effort": it runs in a savepoint (`db.session.begin_nested()`). A UNIQUE conflict and any other error are logged and **never** stop `get_authz` or roll back the state of `challenges_data` (F13a).
3. `expires_at` = `expires` from the upstream authz, but not later than `created_at + 24 h` (F13d).
4. A row is "active" when: `status = pending`, `expires_at > now`, the order has `status = pending`.
5. Closing (`status = closed`): `get_certificate`; reading an upstream authz or a challenge in a final error state (`invalid`, `expired`, `deactivated`, `revoked`, RFC 8555 §7.1.6) in `get_authz` and `respond_challenge` (F13d). The states `processing` and `valid` do **not** close the row: a client that fetched authz in the `pending` state can send UPDATE after the UCM automation has already validated the challenge, and it must not get REFUSED then (race). Success closes the row in `get_certificate`.
6. Rows with `expires_at` older than 7 days are deleted at the next write.

### 2.3 "Authoritative" zones and key scope

- **Domain D of a row** = the domain from "ACME → Domains" that the existing function `find_provider_for_domain(identifier)` selects (the most specific match, without `*.`). UCM already uses this same domain today to select the DNS provider. D is the zone apex that UCM announces in SOA responses.
- **The zone is ours** (RFC 2136 §3.1.1) when ZNAME is a domain from "ACME → Domains" or an ancestor of it (without the root and without single-label names). The ancestor is needed because cert-manager takes the apex from public DNS, and win-acme starts from the registrable domain (section 9). The real zone that the UCM DNS provider writes to is D or an ancestor of D. This rule does not depend on active orders. Because of this, deleting a record after the order ends gets NOERROR, as the maintainer wants.
- **The key is valid** (otherwise BADKEY) when: `status = active`, the secret is decrypted and not empty, the proxy account exists and has `proxy_enabled = true` (F3, F4).
- **Key scope** (RFC 3007 §3), the rule "no access by default": a row matches a key when `row.acme_client_account_id = key.acme_client_account_id`. When `key.eab_credential_id` is not NULL, these conditions also apply: the EAB credential exists, has `status = used`, has a non-empty `used_by_account_id`, and `row.account_id` is non-empty and equal to `used_by_account_id`. Every other case (EAB deleted, not used, NULL on either side) = no match (F2).
- **Value matching** always applies to the pair (`record_name`, `txt_value`), never to the value alone (F13c).

### 2.4 Resources, cache and resilience (F1, F8)

The listener runs in the only gevent worker (`workers = 1`). This worker also serves HTTPS, ACME, OCSP and CRL. DB calls (psycopg2 without psycogreen, sqlite3) block the gevent loop. Because of this:

| Mechanism | Default value | Purpose |
|---|---|---|
| `spawn=Pool(N)` for `DatagramServer` and `StreamServer` | N = 16 (UDP), 128 connections (TCP), max. 8 connections per source | limited number of greenlets; to occupy all TCP connections an attacker needs at least 16 sources (CR1-5) |
| Global token bucket of packets, checked before parsing | 200 packets/s, burst 400 | protection against flooding, also from spoofed addresses |
| Per-source limit, in a bounded LRU (for example 4096 entries) | 50 packets/s per source; source = IPv4 address or IPv6 /64 network | protection against a single source; a host with a /64 prefix does not get a new limit for each address (CR1-6); the LRU protects memory |
| Preliminary header check before `from_wire` | QDCOUNT ≤ 1, ANCOUNT = 0 for QUERY, NSCOUNT ≤ 16, ARCOUNT ≤ 4, length ≤ MAX_MSG = 4096 B | low cost of rejection |
| Cache of active rows (record_name, D, values, scope) | refresh after a write in `records.py` and every 5 s | unsigned SOA and BADKEY without DB queries |
| Cache of TSIG keys | invalidation at each key change (API in the same process, backup restore), TTL 30 s. Read error after invalidation → empty cache (each key = BADKEY); error after a normal expiry → old cache; retry after 2 s | revocation works at once, also when the DB fails (CR1-1) |
| Cache of ACME domains (zones) | TTL 10 s | zone check without the DB |
| TCP: idle limit, write time, max. connection lifetime | 10 s, 10 s, 120 s | protection against slow-read and connection exhaustion |
| Exception in the handler | SERVFAIL response (when the ID can be read), signed when the TSIG of the request was valid (RFC 8945 §5.3); otherwise no response; the server keeps running | resilience |
| Application logs for unsigned and invalid traffic | sampling: max. 1 line per (reason) per 10 s, plus counters | log protection |
| Listen address | `UCM_DNS_UPDATE_HOST`, default `HOST` | possibility to listen on the internal network only (F8) |

I reject a separate process for the listener: the pattern of the HTTP protocol server (maintainer requirement) and the shared cache invalidation in one process are simpler. The limits above reduce the cost of unsigned traffic to a few operations in memory.

## 3. Message processing order

Each step has the number of an invariant from section 4.

```
1. Global token bucket and per-IP limit (traffic not yet verified) → no response (N4, N8).
2. Length < 12 B → no response (M2). QR=1 → no response (M1).
3. Length > MAX_MSG or header counters over the limit → no response (N9).
4. Opcode ∉ {QUERY, UPDATE} → NOTIMP, header only, no TSIG (M3; decision 11).
5. dnspython parsing (keyring=False, no verification, no padding) → error → FORMERR, no TSIG (M4, S1, E2).
6. TSIG present → order of RFC 8945 §5.2:
   a. Error field ≠ 0 → FORMERR (S9)
   b. key unknown, not valid (section 2.3), algorithm ≠ key algorithm or outside the policy
      → NOTAUTH/BADKEY, no signature (S2, S3, K7–K9)
   c. MAC size > digest length or < max(10, half of the digest) → FORMERR (S8)
   d. MAC:
      full length → dns.tsig.validate(..., now=time_signed) (checks name, algorithm, HMAC);
      truncated → full MAC through the public dns.tsig.sign on the message without TSIG,
                  then hmac.compare_digest(full[:len], mac) (F5).
      Mismatch → NOTAUTH/BADSIG, no signature (S4, S8)
   e. replay: the same request MAC already accepted in the window → the same response from the replay cache,
      no side effects (S15)
   f. time: |now − Time Signed| > min(Fudge, 300) or Time Signed < the last accepted one for the key
      → NOTAUTH/BADTIME, signed, Time Signed = client time, Other Data = server time,
      Fudge = client fudge (S6, S7, S14)
   g. MAC truncated (matching) → NOTAUTH/BADTRUNC, signed; the signature contains the truncated request MAC (S8)
   h. the last accepted Time Signed for the key changes only here (after b–g) (S7)
7. EDNS: version > 0 → BADVERS with OPT of version 0 (E3).
8. QUERY → section 3.1. UPDATE → section 3.2.
9. Response: ID and opcode copied, QR=1, RD copied, RA=0, Z=0, no padding
   (make_response(pad=0)) (M6–M8, E5).
   Signed when the request was signed and passed 6b–6d (S10). OPT when the request had OPT (E1).
10. UDP, request without a valid TSIG (also each response to a TSIG error):
    response longer than the request → minimal response with TC=1 (T1).
    UDP, request with a valid TSIG: limit max(512, EDNS size); above it → TC=1 with TSIG (T2, S12).
11. Audit and log after the decision, in a separate transaction (N6, N12, N13).
```

### 3.1 QUERY

```
QDCOUNT ≠ 1 → FORMERR (M5)
QCLASS ≠ IN → REFUSED (Q4)
QTYPE ≠ SOA → REFUSED (Q3, Q5)
W = active rows (unsigned query: all; signed: within the key scope)
QNAME = D of a row from W
    → NOERROR, AA=1, SOA(D) in ANSWER (Q1)
QNAME is a descendant of D and an ancestor of or equal to record_name of a row from W
    → NOERROR, AA=1, ANSWER empty, SOA(D) in AUTHORITY (NODATA, RFC 2308 §2.2) (Q7)
every other query → REFUSED (Q3)
```

The SOA(D) record has fixed values (F12): owner D, TTL 0, MNAME = D, RNAME = `hostmaster.D`, SERIAL = 1, REFRESH 3600, RETRY 600, EXPIRE 86400, MINIMUM 0. It does not contain the UCM host name, an e-mail address or a timestamp.

Why this way (section 9): certbot and lego go up from `_acme-challenge.<id>` and need SOA in ANSWER at the apex. nsupdate asks only for the record name and accepts SOA from AUTHORITY. A REFUSED response for the record name would stop nsupdate.

Note for the PR (F14): the key scope for a signed SOA hides nothing, because the same client can send an unsigned query and get a response for all accounts. This is not a security control.

### 3.2 UPDATE (order of RFC 2136 §3)

```
no TSIG signature → REFUSED, at once, before the zone check (U4; RFC 3007 §2, RFC 2136 §3.3.1) (F6)
ZOCOUNT ≠ 1 or ZTYPE ≠ SOA → FORMERR                  (U1, §3.1.1)
ZCLASS ≠ IN → NOTAUTH                                 (U2, §3.1.1)
ZNAME is not our zone → NOTAUTH                       (U3, §3.1.1)
prerequisite section not empty → REFUSED              (U5, policy §3.3, maintainer requirement)
for each RR (permission check, §3.3):
    type ≠ TXT or name does not start with "_acme-challenge." → REFUSED (U9)
    add: pair (name, value) ≠ active row in the key scope → REFUSED (U10)
    delete of class ANY and type ANY → REFUSED (U11)
prescan (§3.4.1): class ∉ {IN, ANY, NONE} → FORMERR; name outside ZNAME → NOTZONE;
    rules for TTL/RDLENGTH/meta types → FORMERR       (U6–U8)
apply: no DNS change (UCM publishes the record itself, as it does today); write client_confirmed_at,
    last_used_at of the key (U12, U13, U15)
→ NOERROR, section counters = 0                       (U14, §3.8)
```

The whole message is checked before any write. One bad record rejects the whole message (RFC 2136 §3.3.2, §3.7).

## 4. RFC invariants and tests

Each invariant has a **positive test (P)** and a **negative test (N)**. The negative test uses the same data as the positive test and changes only one thing, the one that violates the invariant. The negative test also checks that there are no side effects: no DB write, no audit entry (when none should be created), no signature (when none should be created).

Test name: `test_<ID>_<description>_pos` / `test_<ID>_<description>_neg`.

### 4.1 Message (M), EDNS (E), transport (T)

| ID | Invariant | RFC | P | N |
|---|---|---|---|---|
| M1 | The server does not respond to a message with QR=1 | 1035 §4.1.1 | query QR=0 → response | the same with QR=1 → no response |
| M2 | A message shorter than the header (12 B) → no response | 1035 §4.1.1 | 12 B valid header → response | 11 B → no response |
| M3 | Opcode other than QUERY and UPDATE → NOTIMP, header only, opcode copied | 2136 §3; 8906 §3.1.4, §7 | opcode 0 and 5 → not NOTIMP | opcode 1, 2, 4, 6, 15 → NOTIMP, counters 0 |
| M4 | Format error for a known opcode → FORMERR | 8906 §7; 2136 §3.1.1 | valid message → not FORMERR | truncated RR, trailing garbage, bad label → FORMERR |
| M5 | QUERY with QDCOUNT ≠ 1 → FORMERR | 9619; 1035 §4.1.2 | QDCOUNT=1 → response | QDCOUNT=0 and 2 → FORMERR |
| M6 | Z=0 in the response, unknown flags are not copied | 1035 §4.1.1; 8906 §3.1.3 | request Z=0 → response Z=0 | request with Z=1 and AD=1 → response, Z=0, AD=0 |
| M7 | RD copied, RA=0 (no recursion) | 1035 §4.1.1; 8906 §3.1.3.1 | RD=0 → RD=0, RA=0 | RD=1 → RD=1, RA=0, no outgoing queries |
| M8 | ID and opcode copied | 1035 §4.1.1; 2136 §3.8 | random ID → the same ID | a response to another ID never matches (property test, 100 random IDs) |
| E1 | OPT in the response only when it was in the request | 6891 §6.1.1, §7 | with OPT → with OPT | without OPT → without OPT |
| E2 | Two OPT → FORMERR | 6891 §6.1.1 | one OPT → valid | two OPT → FORMERR |
| E3 | EDNS version > 0 → BADVERS, OPT of version 0 | 6891 §6.1.3; 8906 §3.2.2 | version 0 → valid | version 1 → BADVERS |
| E4 | Unknown EDNS options and flags are ignored and not copied | 6891 §6.1.2, §6.1.4; 8906 §3.2.3–§3.2.4 | no options → valid | unknown option and flag → valid, not present in the response |
| E5 | Response without EDNS padding (PADDING) | 6891 §7; maintainer (size) | query without PADDING → response without PADDING | small query with PADDING → response not longer than the query |
| T1 | UDP, request without a valid TSIG: the response is not longer than the request (maintainer). If longer → TC=1, header, question, OPT (when present) | 1035 §4.2.1; 6891 §7 | REFUSED fits → sent unchanged | unsigned SOA over UDP → TC=1, no ANSWER and AUTHORITY, length ≤ request |
| T2 | UDP, request with a valid TSIG: response ≤ max(512, EDNS size); if longer → TC=1 with TSIG | 1035 §4.2.1; 6891 §6.2.3; 8906 §3.2.5; 8945 §5.3 | signed SOA over UDP (nsupdate pattern, no EDNS) → full response ≤ 512 | response > 512 without EDNS → TC=1, question + TSIG |
| T3 | TCP: frame with a 2-byte length; several messages in one connection; data in several segments | 1035 §4.2.2; 7766 §6.2.1, §8 | 2 queries in one connection → 2 responses; length in a separate segment → response | length 0 or > MAX_MSG → close without a response |
| T4 | TCP: full response, no TC | 8906 §3.2.7 | SOA over TCP → full ANSWER, TC=0 | the same over UDP → TC=1 |
| T5 | TCP: idle limit counted from a full message | 7766 §6.2.3 | messages every < limit → connection stays open | half a message and silence > limit → close (protection against slow-read) |

### 4.2 TSIG (S)

| ID | Invariant | RFC | P | N |
|---|---|---|---|---|
| S1 | There is one TSIG and it is last in the additional section, otherwise FORMERR | 8945 §5.1, §5.2 | TSIG last → processed | TSIG before OPT; two TSIG → FORMERR without signature |
| S2 | Unknown or revoked key → NOTAUTH + BADKEY, response without signature (MAC Size 0) | 8945 §5.2.1, §5.3.2 | known key → accepted | unknown name; revoked key → BADKEY, MAC empty |
| S3 | Algorithm other than the key algorithm or outside the policy (sha1, md5, sha224, gss-tsig) → BADKEY | 8945 §5.2.1, §6, §7 | sha256/384/512 → accepted | the same name with sha1; md5 → BADKEY |
| S4 | Wrong MAC → NOTAUTH + BADSIG, no signature | 8945 §5.2.2, §5.3.2 | valid MAC → accepted | changed MAC byte; wrong secret; content changed after signing → BADSIG |
| S5 | Order: key → MAC → time → truncation | 8945 §5.2 | good MAC and bad time → BADTIME | bad MAC and bad time → BADSIG (not BADTIME); unknown key and bad time → BADKEY |
| S6 | Time outside ±fudge → BADTIME, signed with the same key; Time Signed = client time; Other Data = server time (6 B); Fudge = client fudge; request MAC in the signature | 8945 §5.2.3, §5.3.2 | difference = fudge → accepted | difference = fudge + 1 → BADTIME; the client verifies the response |
| S7 | Time Signed older than the last accepted one for the key → BADTIME | 8945 §5.2.3 (SHOULD) | the same and a later time → accepted | an earlier time → BADTIME |
| S8 | MAC size: > digest → FORMERR; < max(10, digest/2) → FORMERR; truncated allowed → BADTRUNC (signed), because the policy requires a full MAC | 8945 §5.2.2.1, §5.2.4, §7 | full MAC → accepted | 33 B for sha256 → FORMERR; 9 B → FORMERR; 16 B matching → BADTRUNC (signed); 16 B with wrong bytes → BADSIG without signature (F5) |
| S9 | Error field in the request ≠ 0 → FORMERR | 8945 §4.2, §5.2 | Error=0 → accepted | Error=16 → FORMERR |
| S10 | Signed request → signed response (the client verifies it); unsigned request → response without TSIG | 8945 §5.3 | dnspython as a client verifies the response MAC | request without TSIG → no TSIG in the response |
| S11 | The response MAC is not shorter than the request MAC | 8945 §7 | full MAC in the response | — (property test for all algorithms) |
| S12 | Truncated signed response: question + TSIG, TC=1, NOERROR | 8945 §5.3 | SOA over UDP with signature → TC=1 and valid TSIG | no TSIG in a truncated response = error |
| S13 | Key and algorithm names are compared case-insensitively | 8945 §9; 1034 §3.1 | `KEY.Example.` = `key.example.` | another name → BADKEY |
| S14 | Time window = min(request Fudge, 300 s); BADTIME returns the client fudge | 8945 §5.2.3, §10 | Fudge 300, difference 300 → accepted | Fudge 65535, difference 301 → BADTIME with Fudge 65535 in the response |
| S15 | Replay (the same pair: key name and request MAC, for 2 × 300 s, each transport, also with another header ID) → response without side effects; a copy during processing → no response | 8945 §10, §4.3.2 | UDP retransmission → identical response; UDP, then TCP → TCP response, effects once | the replay does not change `client_confirmed_at`, `last_used_at`, does not add an audit entry |

### 4.3 UPDATE (U)

| ID | Invariant | RFC | P | N |
|---|---|---|---|---|
| U1 | ZOCOUNT ≠ 1 or ZTYPE ≠ SOA → FORMERR | 2136 §3.1.1 | 1 × SOA → continue | 0, 2 records; ZTYPE=A → FORMERR |
| U2 | ZCLASS ≠ IN → NOTAUTH | 2136 §3.1.1 | IN → continue | CH, ANY → NOTAUTH |
| U3 | ZNAME outside our zones → NOTAUTH | 2136 §3.1.1 | domain from ACME Domains; its ancestor (public apex, cert-manager and win-acme pattern) → continue | foreign zone; descendant of a domain; root; TLD → NOTAUTH |
| U4 | UPDATE without a signature → REFUSED at once (before U1–U3), application log only | 3007 §2, §3; 2136 §3.3.1 | the same UPDATE signed → NOERROR | without TSIG → REFUSED, no audit entry, no changes; the response for a zone from ACME Domains and for a foreign zone is identical byte for byte (except the ID); 0 DB queries (F6) |
| U5 | Non-empty prerequisite section → REFUSED | 2136 §2.4, §3.3; maintainer | empty → continue | each of the 5 forms (§2.4.1–§2.4.5) → REFUSED |
| U6 | RR class ∉ {IN, ANY, NONE} → FORMERR | 2136 §3.4.1 | IN, ANY, NONE → continue | CH → FORMERR |
| U7 | RR name outside ZNAME → NOTZONE | 2136 §3.4.1 | name in the zone → continue | allowed name outside ZNAME → NOTZONE |
| U8 | Prescan: IN with type ANY/AXFR/MAILA/MAILB → FORMERR; ANY with TTL≠0 or RDLENGTH≠0 → FORMERR; NONE with TTL≠0 → FORMERR | 2136 §3.4.1.2 | valid forms → continue | each invalid form → FORMERR |
| U9 | Only TXT under `_acme-challenge.<identifier>` can be changed | 3007 §3, §3.1; 8555 §8.4 | TXT under the challenge name → continue | A under this name; TXT under `foo.<id>`; CNAME → REFUSED |
| U10 | Add needs an active value in the key scope; values are compared after joining the TXT strings, exact match | 3007 §3; 8555 §8.4; 1035 §3.3.14 | exact value; value in 2 strings → NOERROR | 1 character different; row of another proxy account; another ACME account with a key linked to EAB; expired row; closed row → REFUSED |
| U11 | Delete of TXT (class NONE and class ANY) → NOERROR, no changes, also after the order ends; ANY/ANY → REFUSED | 2136 §2.5.2, §2.5.4, §3.4.2.3–§3.4.2.4; 3007 §3.1; maintainer | NONE TXT, ANY TXT, order ended → NOERROR | ANY/ANY; delete of A → REFUSED |
| U12 | Atomicity: one bad RR rejects the whole message, no effects | 2136 §3.3.2, §3.7 | [delete ANY TXT, add valid] (lego/cert-manager pattern) → NOERROR | [delete, add bad] → REFUSED, no `client_confirmed_at`, audit "refused" |
| U13 | Adding the same value again → NOERROR | 2136 §2.5.1 | second identical UPDATE → NOERROR | — (pair with U10 N) |
| U14 | Response: ID and opcode copied, QR=1, section counters = 0 | 2136 §3.8 | header check | the response never contains the update section of the request |
| U15 | An accepted UPDATE does not change DNS through the listener; it sets `client_confirmed_at`, `last_used_at`, audit | maintainer; 2136 §3.5 (no state to persist) | accepted → fields set, DNS provider calls 0 | rejected → fields empty |

### 4.4 QUERY and SOA discovery (Q)

| ID | Invariant | RFC | P | N |
|---|---|---|---|---|
| Q1 | SOA for QNAME = D of an active row → NOERROR, AA=1, one SOA in ANSWER, owner = D, TTL 0, MINIMUM 0 | 8906 §3.1.1; 1034 §4.3.2; 1035 §3.3.13 | active row → SOA (TCP) | no row; closed row; expired row → REFUSED |
| Q2 | Signed SOA query: TSIG verification, signed response, key scope | 8945 §5.3; 3007 §3 | row in scope → signed SOA | row of another account → REFUSED (signed) |
| Q3 | Every other query → REFUSED (policy) | 1035 §4.1.1 (RCODE 5); maintainer | SOA → response | TXT, A, NS under the same name; SOA for an ancestor of D → REFUSED |
| Q4 | QCLASS ≠ IN → REFUSED | 1035 §4.1.1 | IN → response | CH → REFUSED |
| Q5 | Meta types (AXFR, IXFR, ANY) → REFUSED | 1035 §4.1.1; 8906 §3.1.2 | — | each meta type → REFUSED |
| Q6 | Names are compared case-insensitively | 1034 §3.1 | `_ACME-Challenge.Example.COM.` → response | another name → REFUSED |
| Q7 | SOA for a name between D and record_name (including record_name) → NOERROR, AA=1, ANSWER empty, SOA(D) in AUTHORITY | 2308 §2.2, §3 | nsupdate: SOA for `_acme-challenge.<id>` → zone D; certbot and lego: the walk up ends at D | a name under D without an active row → REFUSED |

### 4.5 Expected values (R) and keys (K)

| ID | Invariant | RFC | P | N |
|---|---|---|---|---|
| R1 | Value = base64url(SHA-256(token "." thumbprint)), without `=` | 8555 §8.1, §8.4; 4648 §5; 7638 §3 | vector from RFC 7638 §3.1 and a test token, result computed independently by `hashlib` | the result contains no `=`, `+`, `/` |
| R2 | Record name = `_acme-challenge.` + identifier without `*.` | 8555 §7.1.4, §8.4 | `*.example.com` → `_acme-challenge.example.com.` | never `_acme-challenge.*.example.com` |
| R3 | Write when authz is fetched, for the order and its siblings | 8555 §7.5; #307 | `pending` authz with dns-01 → rows for all orders | `valid` authz (#325); foreign client (403); no dns-01 → no rows |
| R4 | Closing at `get_certificate` and at a final error state of authz/challenge; `expires_at` ≤ creation + 24 h | 8555 §7.1.4 (`expires`), §7.1.6 | after the certificate → `closed`; authz or challenge `invalid` → `closed` | row of another order unchanged; `processing` and `valid` → the row stays `pending` (race with the UCM automation); authz `expires` in 7 days → `expires_at` = +24 h |
| R5 | Key scope: proxy account, optionally the ACME account with EAB | 3007 §3, §3.1 | match → allowed | another proxy account; another ACME account → not allowed |
| R6 | A row write error (for example a UNIQUE conflict with parallel `get_authz`) does not stop `get_authz` and does not roll back `challenges_data` | consistency | two parallel `get_authz` of siblings → both OK, rows without duplicates | forced IntegrityError → `get_authz` returns the authz, the state `initiated` stays |
| R7 | The row of a sibling has the thumbprint and `account_id` of the sibling; an order without a thumbprint has no row | 8555 §8.1; #307 | 2 accounts, shared authz → 2 rows with different values | order with `client_jwk_thumbprint` NULL → no row |
| K1 | Secret from a CSPRNG, length = digest output (32/48/64 B) | 8945 §8 | lengths for 3 algorithms | two keys never have the same secret (1000 trials) |
| K2 | Secret encrypted in the DB | maintainer | value in the DB ≠ plain text, read through the model = plain text | wrong master key → no read |
| K3 | Secret returned only at creation | maintainer | POST returns the secret | GET of the list and GET of the key do not return the secret |
| K4 | Algorithms: only sha256/384/512, in FIPS mode and outside it | 8945 §6, §7; maintainer | 3 algorithms → 201 | md5, sha1, sha224 → 400 |
| K5 | Key name: valid DNS name ≤ 255 B, unique case-insensitively | 8945 §4.2; 1035 §2.3.4 | valid → 201 | duplicate with other letter case; label > 63 B → 400 |
| K6 | No access by default: a new key without rows changes nothing | 3007 §3 | — | add with a new key without rows → REFUSED |
| K7 | Secret not decrypted or empty → key unknown (BADKEY), never an empty HMAC key | maintainer; 8945 §5.2.1 | valid secret → accepted | wrong DB encryption key; empty secret; HMAC with an empty key → BADKEY |
| K8 | Key with EAB: no match when EAB is deleted, not used, `used_by_account_id` is NULL, or the row has `account_id` NULL | 3007 §3 (no access by default) | EAB `used`, the same account → NOERROR | each of the 4 cases → REFUSED; revoking EAB revokes the key, deleting EAB deletes the key (SQLite); each change has a key audit entry |
| K9 | Key of a deleted proxy account or with `proxy_enabled = false` → BADKEY | 3007 §3 | active account → accepted | account deleted (SQLite, no FK); proxy disabled → BADKEY; a new account with the same ID does not inherit the key |

### 4.6 Server, logs, security (N)

| ID | Invariant | Basis | P | N |
|---|---|---|---|---|
| N1 | Port: first the env `UCM_DNS_UPDATE_PORT`, then the setting; 0 = disabled; default 0 | maintainer | env 8053 → listening | no env and no setting → no listener; invalid value → 0 and a warning |
| N2 | API: port 0 or 1024–65535, different from HTTPS and from the HTTP protocol port | maintainer (no CAP_NET_BIND_SERVICE) | 8053 → 200 | 53, 70000, HTTPS port → 400 |
| N3 | A bind error does not stop the application | HTTP server pattern | free port → listening | busy port → error log, the application runs |
| N4 | Limits: global token bucket, per-IP limit in the LRU, greenlet Pool, TCP connection limit, write time and connection lifetime | 7766 §6.2.2, §6.2.3; security (F1) | traffic within the limit → responses | traffic over the limit → no response; 10 000 IP addresses → LRU size ≤ limit; number of greenlets ≤ Pool |
| N5 | No recursion and no outgoing traffic from the handler | maintainer; 8906 §3.1.3.1 | — | test with `socket.connect` blocked: no call |
| N6 | Audit: accepted and rejected requests with TSIG; application log: unsigned and invalid. Accepted: max. 120 entries per key per minute, the excess in one summary entry (CR1-2) | maintainer | request with TSIG → audit entry | without TSIG; invalid → no audit entry; 200 accepted in a minute → 120 entries + summary |
| N7 | Limit of audit entries per (IP, reason) | security (protection of the audit table) | first BADKEY → entry | 100 BADKEY from the same IP in 60 s → 1 entry + log |
| N8 | Unsigned traffic (SOA, UPDATE) and BADKEY do not run DB queries | security (F1) | — | 1000 unsigned SOA queries and 1000 BADKEY → 0 SQL queries (SQLAlchemy event counter) |
| N9 | Header counters over the limit or length > MAX_MSG → no response, without full parsing | security (F1) | counters within the limit → processed | ARCOUNT=1000; QDCOUNT=2 for QUERY (FORMERR after the M5 check); 4097 B → no response |
| N10 | Exception (for example DB) → SERVFAIL or no response; the server keeps running. SERVFAIL for a request with a valid TSIG is signed | 1035 §4.1.1 (SERVFAIL); 2136 §3.4.2.1; 8945 §5.3 | request with TSIG → signed SERVFAIL | request without TSIG → SERVFAIL without TSIG; the next query → valid response |
| N11 | Secret and MAC never in logs and audit | security (F11) | — | the whole test suite with caplog at DEBUG: no secret (base64) and no MAC (hex, base64) in the logs |
| N12 | Global limit of audit entries per reason (independent of the IP) + one collective entry | security (F7) | first N entries → written | 1000 BADKEY from 1000 random IPs → ≤ N entries + 1 collective |
| N13 | The audit has the client address and the name `dns-update:<key name>` or `dns-update:unauthenticated`; names from the packet are shortened and sanitized | security (F7) | accepted UPDATE → IP and key name in the audit | name of 255 B with control characters → shortened, without control characters; never `system` |

## 5. Places where I reconcile the maintainer requirements with the RFCs

| # | Maintainer requirement | Problem | Decision and reason |
|---|---|---|---|
| 1 | "answer unsigned SOA queries … refuse every other query" | nsupdate (acme.sh without `NSUPDATE_ZONE`, Posh-ACME with `DDNSNameserver`) **signs** the SOA query when it has a key, and an unsigned response is a fatal error for it (section 9). RFC 8945 §5.3 requires a signed response to a signed request | I answer SOA queries both unsigned and signed. A signed query gets a signed response and the key scope. **Needs the agreement of the maintainer (F14), see section 11** |
| 2 | "No response larger than the request" | The SOA response is always longer than the query. lego and cert-manager repeat over TCP after TC=1, certbot asks over TCP first, but **nsupdate does not support TC** and asks over UDP (section 9) | The rule applies to UDP without a valid TSIG (T1): only this traffic can be forged (spoofed source address). A request with a valid TSIG (MAC verified, time in the window, S7 blocks older ones, S15 handles replays) gets the usual RFC limit: max(512, EDNS) (T2). The amplification factor for a signed SOA ≈ 1.25. TCP without a limit (handshake). **Needs the agreement of the maintainer (F14), see section 11** |
| 3 | "Always answer NOERROR, even when the order is gone" | RFC 2136 §3.1.1 checks the zone before the delete. A zone that depends on active orders would give NOTAUTH | The zone depends on ACME Domains, not on orders (section 2.3) |
| 4 | "A non-empty prerequisite section gets REFUSED" | RFC 2136 §3.2 evaluates prerequisites before §3.3 | Our zone has no state against which a prerequisite can be evaluated. The refusal is a policy (§3.3.1 "implementation dependent") |
| 5 | Algorithms "nothing weaker than SHA-256" | RFC 8945 §6: an implementation MUST have hmac-sha1 | §7 allows local policy to reject an algorithm. sha1 → BADKEY |
| 6 | BADTIME responses | dnspython signs with the server time, and RFC 8945 §5.2.3 requires the client time in Time Signed | Own TSIG construction for BADTIME through the public `dns.tsig.sign` |
| 7 | "Use dnspython … do not hand-roll HMAC" | `dns.tsig.validate` checks time before MAC; RFC 8945 §5.2 requires: key, MAC, time | I call `dns.tsig.validate` with `now = time_signed` (time is always OK), then I check the time myself. dnspython computes the HMAC. Verified with a prototype on dnspython 2.8.0 (`spike/tsig_spike.py` in this directory) |
| 8 | SOA "for names covered by a pending proxy order" | Which apex to announce? Apex = record name breaks the lego precheck (it looks for NS of a false zone). REFUSED for the record name stops nsupdate | Apex = D (section 2.3). SOA in ANSWER for D, NODATA with SOA in AUTHORITY for names from D down to the record name (Q1, Q7). This fits certbot, lego and nsupdate (section 9) |
| 9 | RFC 8945 §5.2.3 (SHOULD): reject Time Signed older than the last one for the key | cert-manager sends several UPDATEs in parallel (several names in a certificate). UDP packets can arrive in another order, so one of them gets BADTIME | I implement the recommendation literally (S7). The marker changes only after a positive check of MAC and time. Retransmissions are handled by the replay cache (S15). cert-manager retries the challenge after an error. I will check this in E2E |
| 10 | UPDATE without a signature | RFC 2136 §3 checks the zone (NOTAUTH) before permissions (§3.3). This lets anyone without a key check which domains are in ACME Domains (F6) | REFUSED at once after parsing. RFC 3007 §2: "TSIG or SIG(0) records MUST be included in all secure dynamic update messages"; RFC 2136 §3.3.1: permissions "in an implementation dependent fashion". No client sends UPDATE without a signature |
| 11 | NOTIMP and FORMERR for a message with TSIG | RFC 8945 §5.2: "the server is REQUIRED to return a TSIG RR in the response" | FORMERR: a message that cannot be interpreted (§5.2, "cannot be interpreted"). NOTIMP: we do not parse an unknown opcode beyond the header (RFC 8906 §7), so there is nothing to sign with. A deliberate deviation, with no effect on security (F15) |
| 12 | Fudge | RFC 8945 §5.2.3 uses the fudge from the request (up to 65535 s). §10: "A Fudge value that is too large may leave the server open to replay attacks" | Window = min(fudge, 300 s). BADTIME returns the client fudge (§5.2.3). All clients use 300 s (section 9) (F9) |
| 13 | SOA content | A host name, an e-mail address or a timestamp would reveal more than the maintainer agreed to (F12) | Fixed values (section 3.1) |

## 6. Security (for the security review)

| Threat | Protection |
|---|---|
| Writing any record in DNS | The listener writes nothing in DNS. An add passes only for a TXT `_acme-challenge` with a value equal to the expected one |
| Impersonating another client | The value depends on the client thumbprint (RFC 8555 §8.1). Key scope = proxy account, optionally the ACME account with EAB |
| Theft of the secret from the DB | Fernet encryption like the EAB HMAC (always on), the secret is shown once; a secret that is not decrypted = BADKEY (K7) |
| Widening of the key scope | The rule "no access by default" for EAB and proxy accounts, deleting keys in code because SQLite does not enforce FKs (K8, K9) |
| Signature oracle (BADTRUNC) | A truncated MAC is checked before a signed response (step 6d) |
| Secret in logs | Ban on logging `dns.tsig.Key`, the keyring and `Message.to_text()`; only the key name, the code, the address (N11) |
| Request replay | Window ±min(fudge, 300 s) (S14), last Time Signed per key (S7), replay cache by request MAC (S15). Operations are idempotent |
| UDP amplification | Without a valid TSIG: response ≤ request, otherwise TC=1 (T1). With a valid TSIG: RFC limit (T2); it cannot be forged without the secret, a replay is limited by the fudge window and S7 |
| Flooding the process, DB and audit | Section 2.4: Pool, global token bucket, per-IP LRU, header check, cache (0 DB queries for unsigned traffic and BADKEY, N8), audit limits per IP and global (N7, N12), audit after the decision in a separate transaction |
| Discovering domains without a key | UPDATE without a signature → REFUSED before the zone check (U4, F6) |
| Leak of names of active challenges | An unsigned SOA reveals D and the names with active challenges (maintainer requirement), nothing more (fixed SOA, F12). Active rows max. 24 h (R4). The listener on a separate address (`UCM_DNS_UPDATE_HOST`), a separate Service in Helm (ClusterIP), documentation: internal network only (F8) |
| TCP slow-read | Idle limit from a full message (T5), write time, max. lifetime, connection limit (2.4) |
| MAC comparison in constant time | `hmac.compare_digest` (dnspython) |
| Process privileges | Unprivileged port, no CAP_NET_BIND_SERVICE |

## 7. Remaining parts of PR 2

- **Start:** in `post_worker_init` (gunicorn, `workers = 1`), next to the HTTP protocol server; in dev mode in `app.py main()`. The gevent servers `DatagramServer` and `StreamServer` with `spawn=Pool(N)` (section 2.4). Address: `UCM_DNS_UPDATE_HOST` (default `HOST`). A port change needs a restart (like the HTTP protocol port).
- **Changes in existing code:** the DELETE handler of an EAB credential deletes the linked keys (K8); `_remove_account_row` deletes the keys and rows of the account (K9); `AuditService.log_action` gets an optional parameter `ip_address` (N13); `get_authz`, `respond_challenge`, `get_certificate` store and close rows (R3, R4).
- **API:**
  - `GET/POST /api/v2/acme/client/accounts/<id>/dns-update-keys` (`read:acme` / `write:acme`)
  - `DELETE /api/v2/acme/client/accounts/<id>/dns-update-keys/<key_id>` (`delete:acme`; active → revoke, revoked → delete, like EAB)
  - `dns_update_port` in `/api/v2/acme/client/settings` (GET/PATCH)
- **UI:** the section "DNS UPDATE keys (RFC 2136)" in the proxy account card (`CaAccountsManager.jsx`). A "show once" dialog with the secret and ready snippets: BIND key file (nsupdate, acme.sh, Posh-ACME), Secret and ClusterIssuer for cert-manager, certbot ini file. A port field in the proxy section (`LetsEncryptTab.jsx`). Context help. Texts in 9 languages (`npm run check:i18n`).
- **Packages:** Dockerfile `EXPOSE 8053/udp 8053/tcp`; `docker/entrypoint.sh` checks `UCM_DNS_UPDATE_PORT` (0 or 1024–65535, different from the other ports). Helm: `dnsUpdate.enabled` (default false), `dnsUpdate.port` (8053), a **separate Service** (`dnsUpdate.service.type`, default ClusterIP, port 53 → 8053, UDP and TCP), an optional NetworkPolicy, an env variable. Documentation: kube-proxy SNAT can merge the per-IP limits into one. DEB and RPM: no changes in the units.
- **Documentation:** `docs/ADMIN_GUIDE.md` (new section, note about the internal network, mapping of port 53), `examples/kubernetes/cert-manager/clusterissuer-ucm-proxy-rfc2136.yaml`, `docs/testing/ACME-PROXY-DNS-UPDATE.md` (manual tests and E2E), CHANGELOG.

## 8. End-to-end tests with real clients

Environment in a container (no internet access to a CA):

| Element | Role | Source |
|---|---|---|
| Pebble | Fake external CA (upstream of the proxy) | `go install github.com/letsencrypt/pebble/v2/cmd/pebble` |
| pebble-challtestsrv | Fake DNS for Pebble, HTTP API to set TXT | as above |
| DNS provider in UCM | `custom_command` → a script that calls the challtestsrv API | existing UCM provider |
| UCM | gunicorn with the real `post_worker_init` | repository |

Clients and scenarios (each with a negative test):

| Client | How it is run | P | N |
|---|---|---|---|
| acme.sh + `dns_nsupdate` | `nsupdate` from the package bind9-dnsutils | certificate issued; variant with `NSUPDATE_ZONE` and without | wrong secret → BADSIG, no certificate |
| certbot + `certbot-dns-rfc2136` | pip | certificate issued | key of another proxy account → REFUSED |
| lego `--dns rfc2136` | `go install` | certificate issued | revoked key → BADKEY |
| cert-manager v1.21.3 | Code `pkg/issuer/acme/dns/rfc2136` in a Go test program: Present/CleanUp with `ResolvedZone` = D (this is what the controller does after `FindZoneByFqdn`). A full kind cluster only when dockerd can be started | Present and CleanUp → NOERROR, UDP and TCP | value of another account → REFUSED; algorithm HMACMD5 (the default!) → BADKEY |
| Posh-ACME | `nsupdate` commands in the form from `RFC2136.ps1` (pwsh not available), with `DDNSZone` and without | NOERROR | wrong key → BADKEY |
| win-acme | Message recreated in dnspython according to the code (ZNAME from the registrable domain down, full MAC, UDP then TCP) | NOERROR at the first ZNAME | wrong ZNAME → NOTAUTH (win-acme goes on) |

Client settings in E2E: there is no access to public DNS, so: acme.sh `--dnssleep 1`, lego `--dns.propagation-wait 1s`, certbot `--dns-rfc2136-propagation-seconds 1`. The same settings go into the documentation (PR 1).

**Result (2026-10-24).** Procedure and result table: [`docs/testing/ACME-PROXY-DNS-UPDATE.md`](../../testing/ACME-PROXY-DNS-UPDATE.md). Differences against this section:

- acme.sh, certbot, lego and cert-manager issued certificates through the proxy. certbot, lego and cert-manager (through the lego ACME library) needed a proxy patch in the laboratory for the header `Link: rel="up"`, which Pebble does not send. This is a proxy bug outside the listener (the same bug exists without DNS UPDATE). The patch is not in PR 2.
- Negative tests in the full flow: acme.sh (key of another account → REFUSED, wrong secret → BADSIG), cert-manager (HMACMD5 → BADKEY, key of another account → REFUSED, zone outside ACME Domains → NOTAUTH). The negative cases of certbot and lego (wrong value, default algorithm, TC → TCP) are in the harness of the handler itself.
- Posh-ACME and win-acme were not run (no Windows and no pwsh). Their message shapes are covered by the handler tests and the `nsupdate` runs.

## 9. Client behavior (from source code)

Sources and versions: nsupdate from BIND 9.18.39, acme.sh @37d064f7, certbot-dns-rfc2136 5.8.0, lego v4.35.2, cert-manager v1.21.3, Posh-ACME @392c2e76, win-acme @c213e6dc with ARSoft.Tools.Net 3.6.0. I checked the key facts again in the sources (nsupdate `sendrequest`, certbot `_query_soa`).

| Client | SOA query: where to, signature, TC | Requirements for the SOA response | UPDATE add | UPDATE delete | Response signature required | Default algorithm |
|---|---|---|---|---|---|---|
| nsupdate (`server` set) | to UCM, **signed** when there is a key, UDP, **TC ignored** | NOERROR/NXDOMAIN; SOA in ANSWER, then AUTHORITY; any owner; AA not important | as in the script | ANY (no data) or NONE (with data) | **yes** (no signature = fatal error) | hmac-md5, when the key file does not give one |
| acme.sh `dns_nsupdate` | through nsupdate; none when `NSUPDATE_ZONE` is set | as nsupdate | IN, TTL 60, 1 string, UDP | **ANY TXT** (whole RRset) | yes | from the key file |
| certbot-dns-rfc2136 | to UCM, TCP then UDP, signature only with `sign_query` | NOERROR, SOA in ANSWER, owner = QNAME, **AA=1**; otherwise the next name up | IN, TTL 120, TCP only | NONE (one RR) | no (checks when present) | **HMAC-MD5** |
| lego | to UCM (unless `DNSUPDATE_ZONES`), unsigned, UDP → **TCP on TC** | NOERROR, SOA in ANSWER; NXDOMAIN/NODATA → go up; other code = error | **[ANY TXT, then IN]** in one message, TTL 120, UDP | NONE | no | **hmac-sha1** |
| cert-manager | **to recursive resolvers** (`--dns01-recursive-nameservers`), not to UCM | — | IN, TTL 60, UDP or TCP (field `protocol`) | NONE | no | **HMACMD5** |
| Posh-ACME | through nsupdate; none when `DDNSZone` is set | as nsupdate | TTL 60 | NONE | yes | from a parameter |
| win-acme | **no SOA**: trial UPDATEs from the registrable domain down, until NOERROR | — | IN, TTL 60, full MAC, UDP then TCP | NONE | no | md5, when the name is unknown |

Conclusions for the server (all are already in the plan):

1. A signed SOA must get a signed response (decision 1, Q2).
2. nsupdate does not support TC, so a signed SOA over UDP must fit in 512 B without truncation (decision 2, T2).
3. Apex = D: SOA in ANSWER for D (certbot, lego), NODATA with SOA in AUTHORITY for the record name (nsupdate) (decision 8, Q1, Q7).
4. Both forms of delete: ANY TXT (acme.sh, lego before the add) and NONE (the others) (U11, U12).
5. A wrong ZNAME → a code other than NOERROR, because win-acme looks for the zone on this basis (U3).
6. All responses to signed requests are signed (S10).

Conclusions for the documentation (PR 1 and PR 2):

- The default algorithms of the clients are md5 or sha1. UCM rejects them (BADKEY). Each configuration example sets **hmac-sha256**.
- win-acme: a bug in the code — `--serverport` becomes a timeout in ms, the target port is always 53. UCM must be reachable on port 53 (port mapping). ARSoft bug: hmac-sha384 is computed as sha256 — do not use sha384.
- Posh-ACME: `DDNSNameserver` is required (without it nsupdate sends UPDATE to MNAME, port 53).
- cert-manager and lego: zone detection (cert-manager) and precheck (lego, cert-manager, acme.sh) use public or recursive DNS. Without access to it: lego `DNSUPDATE_ZONES` and `--dns.propagation-wait`, acme.sh `--dnssleep`, cert-manager `--dns01-recursive-nameservers` that points to a resolver that sees the zone.

## 10. Work order and split into parts

| # | Part | Depends on | Executor |
|---|---|---|---|
| 0 | Branches based on `upstream/dev` | — | main session |
| 1 | PR 1: documentation | 0 | implementer |
| 2 | Models, migration 111, backup manifest, migration tests | 0 | implementer |
| 3 | `tsig.py` + tests S1–S13 | 0 | implementer, detailed review in the main session |
| 4 | `records.py`, hook in the proxy + tests R1–R5 | 2 | implementer |
| 5 | `keys.py`, `policy.py`, `handler.py` + tests M, E, U, Q, K6 | 2, 3, 4 | implementer |
| 6 | `server.py`, start, settings + tests T, N | 5 | implementer |
| 7 | API, audit + tests K1–K5, N2, N6, N7 | 2, 5 | implementer |
| 8 | UI, help, 9 languages | 7 | implementer |
| 9 | Packages, Helm, documentation, CHANGELOG | 6 | implementer |
| 10 | E2E with clients | 6, 7 | main session |
| 11 | 3 × `/code-review`, 3 × `/security-review`, fixes | 1–10 | main session |

Implementer: an agent on a smaller model, medium effort (user preference). The security code (parts 3, 5, 6) gets an exact specification from this plan. I read each result in the diff and I run the full test suite.

Validation commands:
- `cd backend && python -m pytest tests/ -q -n auto --dist loadfile`
- `cd frontend && npx vitest run && npm run check:i18n`
- PostgreSQL tests (`-m postgres`), when PostgreSQL can be started locally

## 11. Security review of the plan (2026-10-24)

An independent agent `reviewer` checked the plan in version 2. I accepted all findings. I checked two claims myself in the code (`eab.py`: permanent deletion of a used EAB; no `PRAGMA foreign_keys=ON` at run time).

| ID | Severity | Problem | Change in the plan |
|---|---|---|---|
| F1 | high | Unsigned UDP traffic (also from spoofed addresses) blocks the only gevent worker through DB queries | section 2.4; N4, N8–N10 |
| F2 | high | A key with EAB widens its scope after the EAB is deleted (SQLite without FK, `None == None`) | 2.1, 2.3; K8 |
| F3 | medium | Keys stay after the proxy account is deleted (SQLite without FK) | 2.1, 2.3, 7; K9 |
| F4 | medium | The secret can get into the DB in plain text; a decryption error can give an empty HMAC key | 2.1, 2.3; K7 |
| F5 | medium | BADTRUNC unreachable through `dns.tsig.validate`; the naive fix = signature oracle | step 6d and 6g; S8 |
| F6 | medium | UPDATE without a signature reveals the domains from ACME Domains (NOTAUTH vs REFUSED) | 3.2; U4; decision 10 |
| F7 | medium | Flooding the audit from random IPs; audit assigned to `system`; audit commit breaks atomicity | step 11; N12, N13 |
| F8 | medium | No own listen address; shared Service in Helm | 2.4, 7 |
| F9 | low | Replay window that depends on the client (fudge up to 65535 s) | step 6e–6f; S14, S15; decision 12 |
| F10 | low | `make_response` adds EDNS padding | step 9; E5 |
| F11 | low | `Key.__repr__` and `Message.to_text()` show the secret and MAC | section 6; N11 |
| F12 | low | SOA content not defined | 3.1; decision 13 |
| F13 | low | Race when a row is stored, sibling fields, pair (name, value), rows active for days | 2.2, 2.3; R4, R6, R7 |
| F14 | low | Deviations from the literal maintainer requirements (decisions 1, 2) without the agreement of the maintainer | comment on issue #416 ([`maintainer-comment-416.md`](maintainer-comment-416.md)), before PR 2 is merged |
| F15 | info | NOTIMP without TSIG; the zone accepts public suffixes | decision 11; zone rule unchanged (no effects) |

**F14 – agreement of the maintainer.** Decisions 1 and 2 change the literal wording of the requirements. I have no access to issues in upstream, so I prepare a comment for the user to send ([`maintainer-comment-416.md`](maintainer-comment-416.md)). Work on PR 2 goes on. If the maintainer does not agree, the change concerns only step 10 and section 3.1 (Q2).

## 12. Code review after completion (2026-10-24)

Round 1 of `/code-review` (19 findings). I checked each finding in the code and in the RFCs. Changes against the plan:

| ID | Problem | Change |
|---|---|---|
| CR1-1 | A key read error after invalidation left a revoked key in memory | empty cache after invalidation and an error (fail closed), retry after 2 s (2.4) |
| CR1-2 | A key holder could flood the audit (deletes are always accepted, a new ID bypasses the replay cache) | limit of 120 entries per key per minute with a summary (N6) |
| CR1-3 | Replay memory: TTL shorter than the time window, cache key included the transport, no protection of a copy during processing | TTL 2 × 300 s, key = message digest, copy during processing → no response (S15) |
| CR1-4 | An empty variable `UCM_DNS_UPDATE_PORT` disabled the listener and blocked the field in the UI | empty value = no variable |
| CR1-5 | 4 sources could occupy all TCP connections | 128 connections (2.4) |
| CR1-6 | Per-address limits for IPv6 bypassed by addresses from one /64 | IPv6 source = /64 network (2.4) |
| CR1-8 | Revoking EAB deleted keys without an audit entry | revoking EAB revokes the keys, deleting deletes them; an audit entry for each key (K8) |
| CR1-9 | One UNIQUE conflict deleted the rows of all orders of the call | a separate savepoint for each row (2.2) |
| CR1-10 | An unsigned SOA query parsed the names of all rows | a preliminary filter through the set of zones of the snapshot and a cache of parsed names |
| CR1-11, 14 | The audit summary omitted the rejections of the per-IP limit; a failed audit write returned success | counters and the write result corrected |
| CR1-12, 13 | Unneeded invalidations of the row cache, reading all EAB credentials | invalidation only after a write, reading only the linked EABs |
| CR1-15 | In developer mode with a reloader the listener could run in the parent process | start only in the process that serves the API |
| CR1-16 | The DNS UPDATE port could be equal to the TLS-ALPN-01 port; `restart_required` without a change | check of both ports; restart only after a change, when the environment variable does not win |
| — | Unsigned SERVFAIL for a request with a valid TSIG (RFC 8945 §5.3) | signed SERVFAIL (N10) |

Unchanged: CR1-7 (timestamp per key, decision 9: RFC 8945 §5.2.3 SHOULD, the client retries), `client_confirmed_at` (the confirmation write is for diagnostics), `tsig_start_offset` (a public function with tests), CR1-19 (the prompts in `docs/development/` are at the user's request; optional for upstream).

By the way, a backup test between installations showed that the restore skipped the keys table. Fix: a section in `restore_core.GENERIC_SECTIONS`, and after the restore a cleanup of the key, zone and row caches.

Round 2 of `/code-review` (17 findings):

| ID | Problem | Change |
|---|---|---|
| CR2-1 | A retransmission of an accepted request after a newer request of this key got BADTIME (timestamp S7) instead of the stored response | check of the replay cache after the MAC and before the time (order of step 6e before 6f); a replay does not change the timestamp (S15) |
| CR2-2 | `audit_logs.username` has 80 characters; a long key name lost the entry on PostgreSQL | trim fields to the column lengths |
| CR2-3 | A row read error repeated the DB query for each packet | retry after 2 s, also for zones |
| CR2-4 | A key with EAB after a backup restore without the EAB credential became a key of the whole proxy account | column `eab_bound` (migration 111): a key bound to EAB without a credential matches nothing (F2) |
| CR2-5 | The scope of a key with EAB in the cache did not see a newly used EAB for 30 s | `mark_eab_used` invalidates the key cache |
| CR2-6 | An invalidation in the retry window cleared the cache without a read attempt | invalidation clears the retry time |
| CR2-7, 8 | `restart_required` compared with the stored port; the check of the TLS-ALPN-01 port skipped the environment variable | comparison with the port on which the listener runs; effective port from the variable |
| CR2-9, 10 | A port from the variable outside the range disabled the listener without a warning; the UI showed an invalid port in the examples | warnings in the log; the API returns `dns_update_port_effective`, the UI uses this value |
| CR2-11 | The NetworkPolicy closes all other ports of the pod, and a comment said otherwise | `dnsUpdate.networkPolicy.extraPorts` and a correct description |
| CR2-12 | QUERY with ANCOUNT > 0 went to the parser | QUERY must have ANCOUNT = 0 (2.4) |
| CR2-13 | Each authz fetch made a zone query, DELETE and COMMIT | without new rows: no write |
| CR2-15 | Three reads of the TLS-ALPN-01 port | one function `get_stored_tls_alpn_port()` |

Unchanged: CR2-14 (a second function for the TXT value: it avoids an import cycle, test R1 checks that they agree), CR2-16 (two functions to truncate a response: a signed TC response has RCODE NOERROR per RFC 8945 §5.3, an unsigned one keeps the RCODE), CR2-17 (proxy hooks on the request session: the current call sites have no unsaved changes, and CR2-13 removes the unneeded commits).

Round 3 of `/code-review` (15 findings):

| ID | Problem | Change |
|---|---|---|
| CR3-1 | After a port save the UI showed the old port in the examples until the page was reloaded | the effective port is updated after the save, when there is no environment variable |
| CR3-2 | The entrypoint rejected values that the application accepts (spaces, empty value, `00`) | the same normalization in the entrypoint and in the application |
| CR3-3 | An IPv6 address in brackets in the examples of certbot, acme.sh, Posh-ACME, win-acme | the address without brackets; brackets only in the form `host:port` |
| CR3-4 | A signed TC response (RFC 8945 §5.3) that still exceeded the UDP limit was sent | no response; nothing in the replay cache |
| CR3-5 | The summary entry of skipped accepted requests was stored as `unauthenticated` and an error | key name and success |
| CR3-6 | Deleting a proxy account did not invalidate the row cache | invalidation after the commit |
| CR3-7 | The UI did not show a key with EAB that lost its credential | a warning at the key (9 languages) |
| CR3-8 | The BADTIME documentation omitted the timestamp of the key (S7) | description and recommendation: a separate key for each client |
| CR3-9 | A warning about the port from the variable at each settings read | one warning for a value |
| CR3-10 | The SOA query looked through all rows | row index by zone, once per snapshot; the deepest zone wins |
| CR3-12, 15 | Double read of the port; a local variable shadowed the module `zones` | one read; rename |

Unchanged: CR3-11 (three commits per accepted request: `last_used_at` at most once per 60 s, a separate audit entry by design, N12), CR3-13 (explicit cache invalidations, like in other UCM caches; the missing place was fixed in CR3-6), CR3-14 (the three caches have a different behavior on error on purpose: keys fail closed, zones and rows keep the previous state).

Round 1 of `/security-review`: no vulnerability with confidence ≥ 0.7. A note below the threshold, fixed: the replay cache used the digest of the whole message, and the MAC does not cover the header ID, so an intercepted request with another header ID repeated the effects (idempotent). The cache key is now (key name, request MAC); the stored response gets the header ID of the current request (TSIG keeps the original ID, RFC 8945 §4.3.2).

Round 2 of `/security-review`: no vulnerability with confidence ≥ 0.7. A hardening below the threshold, introduced: key name labels only with letters, digits, `_` and `-` (not at the start and not at the end). The name goes into shell and PowerShell commands in the ready configuration snippets of the clients; characters such as `` ` ``, `'`, `|`, `$` could take effect there. A non-ASCII name becomes punycode (ASCII). Notes unchanged: the difference between BADKEY/BADSIG shows that a key name exists (RFC 8945 requires this; generated names have a random suffix); a key without EAB confirms the values of all clients of its proxy account (design, section 2.3; `client_confirmed_at` does not affect any decision).

Round 3 of `/security-review`: no vulnerability with confidence ≥ 0.7. Hardenings below the threshold, introduced:
- TTL of the TSIG record other than 0 → FORMERR (RFC 8945 §4.2: "TTL: This MUST be 0"). dnspython always writes the TTL of the TSIG record as 0, and the MAC does not cover it, so the check reads the message bytes (S1).
- A message with TSIG whose header ID differs from Original ID is read a second time in the signed form (with Original ID, RFC 8945 §4.3.2). When the content differs (a name compressed with a pointer to the header, RFC 1035 §4.1.4 allows only a pointer to an earlier name) → FORMERR before the TSIG check (S1).
Notes unchanged: the zone accepts public suffixes as ancestors (F15; the scope of rows decides, the effect is only NOTAUTH/REFUSED); pushing an entry out of the replay cache by a key holder (idempotent effects); unsigned SOA queries show the names of pending challenges (F14, internal network only).

