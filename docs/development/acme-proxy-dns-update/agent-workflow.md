# How we work with AI agents (issue #416)

This document describes how the change "DNS UPDATE (RFC 2136) listener for the ACME proxy" is made: who does what, what the rules are, and what prompts the agents get. The plan for the change is in [`plan.md`](plan.md). The maintainer requirements are in [`maintainer-requirements.md`](maintainer-requirements.md).

The prompts are kept verbatim: they still name the plan `plan.pl.md`, its file name at the time (now `plan.md`).

## 1. Rules

1. **RFCs are invariants.** Each protocol function is based on a specific RFC section. We download the RFC texts from rfc-editor.org and quote them verbatim. The maintainer requirements have the same status. When a maintainer requirement and an RFC differ, the plan records the difference and the decision (plan, section 5).
2. **Each invariant has a positive test and a negative test.** The negative test changes one thing that breaks the invariant. It also checks that there are no side effects (DB write, audit entry, signature).
3. **Facts about clients come only from the source code.** Each claim about the behavior of an ACME client has a file and a line number in the client code. We mark what we cannot confirm as unconfirmed.
4. **Prototype before decision.** When the plan assumes a behavior of a library (dnspython), we check it with a short prototype (`spike/`).
5. **Independent review.** The reviewer gets the source materials, but not the conclusions of the author. This way the review does not repeat the assumptions of the author.
6. **A human decides.** The results of the agents are supporting material. The main session reads each diff, runs the tests, and decides if the work is done. The user makes the decisions that have an effect outside the session (branches, commit author, PR).

## 2. Roles

| Role | Agent | Task | Tools |
|---|---|---|---|
| Main session | main model | Scope, architecture, RFC decisions, review of each result, tests, decision that the work is done | all |
| Code mapping | `Explore` | Facts about the existing UCM code: files, lines, patterns. No design | read only |
| Client research | `general-purpose` | Download the code of the ACME clients and answer questions with a quote from the code | read, git, pip, go |
| Implementation | `implementer` (a smaller model, medium effort) | Code, tests and documentation from an exact specification. No commits | file edit, tests |
| Review | `reviewer` | Independent security review of the plan and the code | read only |
| Code review | `/code-review`, `/security-review` | 3 rounds of each after the code is done, fixes between rounds | — |

## 3. Order of work

```
1. Maintainer requirements (issue #416)      ──┐
2. Download the RFCs and read the sections     ├─> plan with the invariant table (P/N)
3. Map the UCM code (Explore)                  │
4. Code of the ACME clients (general-purpose) ─┘
5. dnspython prototype (spike)               ──> plan fixes
6. Security review of the plan (reviewer)    ──> plan fixes
7. PR 1: documentation (implementer)         ──> diff review, validation
8. PR 2: parts 2–9 of the plan (implementer, in order of dependencies)
                                             ──> review of each part, full tests
9. E2E with real clients (main session)
10. 3 × /code-review, 3 × /security-review, fixes
```

## 4. How we write a prompt for an agent

The agent starts with no context. The prompt must contain:

| Element | Example |
|---|---|
| Goal and reason | "We will add an optional DNS UPDATE (RFC 2136) listener…" |
| Scope and limits | "Do not propose a design; just report facts", "Do NOT commit or push" |
| Inputs (paths, versions) | paths to the RFCs, to the client code, the base branch |
| List of questions or products | numbered, so that the report has the same structure |
| Evidence requirement | "every claim must cite a file path + line numbers… If something cannot be confirmed from source, say UNCONFIRMED" |
| Validation | commands to run and the expected result |
| Report format | sections, summary table, list of unconfirmed items |

For the reviewer: we give source materials and questions. We do not give our conclusions or "what we already checked". We ask for: severity level, attack scenario, evidence (file:line or RFC quote), and a specific fix.

For the implementer: we give the specification from the plan (invariants with IDs, processing order, decisions), the files to change, the constraints, and the test commands. The security code (TSIG, handler, server) gets a detailed specification and a thorough review in the main session.

## 5. Prompts used so far

The paths `/tmp/...` in the prompts are working directories in the session container. The prompts are recorded verbatim.

### 5.1 Map of the UCM code (`Explore`)

```text
Repository: /home/user/ultimate-ca-manager (Flask backend in backend/, React frontend in frontend/, packaging in Dockerfile, docker/, charts/ucm, debian/, packaging/). We will add an optional DNS UPDATE (RFC 2136) listener (UDP+TCP) to UCM, with TSIG keys that belong to an ACME proxy CA account (slug) and can optionally link to an EAB credential. I need a precise map of existing code to reuse/extend. Thoroughness: very thorough. Report file paths with line numbers and short code excerpts (not whole files). Answer each item:

1. HTTP protocol server startup: backend/protocol_http_server.py (start_http_protocol_server, get_http_protocol_port) and backend/gunicorn_config.py post_worker_init. How does it avoid binding the port in every gunicorn worker (lock, SO_REUSEPORT, worker id)? How many workers, worker class (gevent)? Env var vs DB setting precedence; how 0 disables. Any non-gunicorn startup path (app.py dev server, start-ucm.sh, systemd units in debian/ or packaging/) that also starts it.
2. Models: AcmeClientAccount (proxy_enabled, proxy_slug), EAB credential model (name, kid, encrypted hmac, restrictions, bound account), AcmeAccount (jwk_thumbprint, eab link), AcmeClientOrder (fields incl. client_jwk_thumbprint, upstream_authz_urls, dns_records_created, status, is_proxy_order). Give file paths + field lists.
3. Encryption at rest helpers used for EAB HMAC keys (master key encrypt/decrypt functions, how a model field is encrypted transparently). Also how EAB HMAC is "shown once" at creation (API response).
4. Migrations: how a new migration is written (numbering, file naming in backend/migrations/, SQLite+PostgreSQL support, the latest migration number, an example migration that creates a table).
5. Audit log: the service/function to write an audit entry (signature, example call from ACME code), and the app logger conventions.
6. FIPS mode: backend/fips_mode.py and how backend/services/acme/dns_providers/rfc2136.py refuses hmac-md5 / which TSIG algorithms are allowed in FIPS and non-FIPS mode.
7. ACME proxy: in backend/services/acme/acme_proxy_service.py, where get_authz handles a pending dns-01 challenge (token, key authorization, client thumbprint, sibling orders via _orders_by_authz_url / _client_txt_values). Where would we persist "expected TXT value" at authz fetch time? Where are proxy orders marked finished/invalid (status transitions), and where DNS cleanup happens.
8. API for proxy CA accounts and EAB credentials: blueprint files, route patterns, permission decorators (e.g. write:acme), response schema conventions.
9. Frontend: the component(s) that render external CA accounts with "Expose via ACME proxy" + slug, and the EAB credentials page (create dialog showing secret once). Paths of locale files for the 9 languages and how strings are keyed (i18n library). Contextual help files (frontend/src/data/help/*/acme.js, helpContent.js) structure.
10. Packaging: Dockerfile EXPOSE lines, container entrypoint script and any "port check" logic there, Helm chart service template and values for ports, debian/packaging systemd units (any CAP_NET_BIND_SERVICE).
11. Tests: backend/tests layout, how ACME proxy tests are written (fixtures, app context, db), how to run tests (command, pytest config), and any existing tests that run a UDP/TCP socket server.
12. Settings storage: SystemConfig get/set helpers and the ACME settings API (backend/api/v2/acme/settings.py, client settings) where a new setting like a DNS update port would live.
Do not propose a design; just report facts with paths and line numbers.
```

### 5.2 Code of the ACME clients (`general-purpose`)

```text
We are implementing an RFC 2136 (DNS UPDATE) + TSIG (RFC 8945) server endpoint inside a Python app (dnspython 2.8.0). Before designing it, I need exact, source-verified facts about how these ACME clients send their DNS UPDATE and related queries. Do NOT guess: every claim must cite a file path + line numbers (or function name) in the client source and a short verbatim code excerpt. If something cannot be confirmed from source, say "UNCONFIRMED".

Work in /tmp/claude-0/clientsrc (create it). Get sources this way (public GitHub reads work via `git clone --depth 1 --filter=blob:none --sparse`; PyPI via `pip download --no-deps`; Go modules via `GOFLAGS=-mod=mod go mod download -json <module>@latest` which prints the Dir):
- BIND 9.18 nsupdate: `git clone --depth 1 --branch v9.18.39 https://github.com/isc-projects/bind9` (sparse: bin/nsupdate, lib/dns/request.c if needed). If the tag doesn't exist, use the closest v9_18 tag/branch and say which.
- acme.sh: https://github.com/acmesh-official/acme.sh (dnsapi/dns_nsupdate.sh, and acme.sh main script parts that do the DNS propagation check / --dnssleep).
- certbot-dns-rfc2136: `pip download --no-deps certbot-dns-rfc2136` (unzip the wheel) and also certbot's dns_common.base_domain_name_guesses (`pip download --no-deps certbot`).
- lego: module github.com/go-acme/lego/v4 (providers/dns/rfc2136, challenge/dns01 FindZoneByFqdn and precheck).
- cert-manager: module github.com/cert-manager/cert-manager (pkg/issuer/acme/dns/rfc2136, pkg/issuer/acme/dns/util FindZoneByFqdn, how nameservers for zone lookup are chosen).
- Posh-ACME: https://github.com/rmbolger/Posh-ACME (Posh-ACME/Plugins/RFC2136.ps1).
- win-acme: https://github.com/win-acme/win-acme (find the RFC2136 validation plugin source, e.g. under src/plugin.validation.dns.rfc2136 or similar).

For EACH client answer:
1. Zone discovery: how does it decide the Zone Section ZNAME? Does it send an SOA query, and to which server (the configured update server, or recursive/system resolvers)? Over UDP or TCP? Is the SOA query TSIG-signed? What exactly must the SOA response contain for the client to accept it (AA flag? SOA in ANSWER vs AUTHORITY? owner name rules? rcode NOERROR/NXDOMAIN?). Which names does it query, in which order (e.g. certbot base_domain_name_guesses on the record name)? What does it do if the response has TC=1 (retry over TCP or not)?
2. The UPDATE message it sends for "present"/"add": exact sections (prerequisites? delete-RRset (class ANY) before add, as lego does?), record name, TTL, class, TXT rdata format (one string?), UDP or TCP, TSIG algorithm names supported/default, fudge value, whether MAC is truncated.
3. The UPDATE for cleanup/remove: class NONE single-RR delete or class ANY RRset delete? Zone discovery again?
4. How it treats the UPDATE response: which rcodes count as success; does it verify the TSIG on the response (and fail if response unsigned)? Does it retry over TCP on TC=1 or on timeout? Does it fall back UDP<->TCP?
5. Any port configuration (custom port support) and how it is specified.
6. Propagation/self-check after the update: which resolvers does it query (public DoH, recursive, authoritative NS from SOA/NS lookup)? Can it be disabled or pointed at a specific resolver, and with which flag/env var?
7. For nsupdate specifically: when a `server` command is given and no `zone`, how does it find the zone (function recvsoa / sendrequest): does it sign the SOA query with the TSIG key when a key is configured (look for something like `default_servers ? NULL : tsigkey`)? How does it handle answer vs authority SOA, NXDOMAIN, and walking up labels? What does it do with the SOA MNAME when `server` is set? Does it use UDP by default and TCP when -v? Does it retry over TCP when the SOA reply is truncated?
8. For acme.sh dns_nsupdate: the exact nsupdate input it writes (heredoc), whether `zone` is sent only when NSUPDATE_ZONE is set, the -k key file format expected (BIND key file vs. TSIG "key name secret"), and what acme.sh does to check DNS propagation by default (DoH servers used) and how --dnssleep changes it.

Report as one section per client with the numbered answers, then a short cross-client table: SOA query target / signed? / TCP-on-TC?, UPDATE sections for add and delete, response TSIG verification, zone section value used. Keep it factual and compact (excerpts max ~10 lines each).
```

### 5.3 Security review of the plan (`reviewer`)

```text
Security review of a DESIGN PLAN (not code). Be adversarial and independent: assume the plan is wrong until you have checked it.

Context: UCM (Ultimate CA Manager, Flask + gevent, repository at /home/user/ultimate-ca-manager; the target base is git ref `upstream/dev`, read files with `git show upstream/dev:<path>`) is an ACME proxy: internal ACME clients (cert-manager, acme.sh, certbot, lego, win-acme, Posh-ACME) talk to UCM, and UCM obtains certificates from an upstream public CA, publishing the dns-01 TXT records itself through its own DNS provider. The plan adds an optional DNS UPDATE (RFC 2136) + TSIG (RFC 8945) listener (UDP+TCP) so that clients can use their standard rfc2136 solver pointed at UCM. The listener never writes DNS itself; it only accepts updates whose TXT value matches the value UCM expects for a pending proxy order, and answers NOERROR.

Inputs (read them yourself):
- The plan (Polish, with RFC section references): .../scratchpad/plan-rfc2136-listener.md
- Maintainer requirements: .../scratchpad/maintainer-requirements-416.md
- Official RFC texts (use the .clean.txt files): .../scratchpad/rfc/ (1034, 1035, 2136, 2181, 2308, 3007, 4648, 6891, 6895, 7638, 7766, 8555, 8906, 8945, 9619)
- dnspython 2.8.0 source (the library the plan relies on): .../scratchpad/dnspy/src/dns/
- Client sources (for checking client-behaviour claims): /tmp/claude-0/clientsrc/
- Existing UCM proxy code: backend/services/acme/acme_proxy_service.py, backend/api/acme/acme_proxy_api.py, backend/services/acme/mixins/eab.py, backend/models/acme_models.py, backend/models/acme_client_account.py, backend/gunicorn_config.py, backend/protocol_http_server.py (read from upstream/dev).

What to check (report anything else you find too):
1. Authentication and authorization: can anyone without a valid TSIG key cause any state change, audit write, DB load, or information disclosure beyond what the maintainer explicitly accepted? Can a key holder of proxy account A affect or learn about account B? Is the EAB-link scoping sound given how EAB credentials bind to accounts in UCM (check mixins/eab.py and the models)? Is the "zone authority" rule (section 2.3) exploitable?
2. TSIG handling: is the planned verification order and error signing correct per RFC 8945 §5.2–§5.3.2? Any oracle (timing, error-code differences) that leaks key existence or secrets? Replay handling (S7) — correct and sufficient? Is calling dns.tsig.validate with now=time_signed safe (check what else validate() does)? Truncation handling. Key name/algorithm comparison.
3. DoS / amplification: UDP size rules (sections 3, T1/T2, decision 2) — is relaxing the size limit for TSIG-verified requests safe? TCP slow-read/connection exhaustion, gevent single worker (workers=1) — can the listener starve the main HTTPS app? DB query cost per packet for unsigned SOA queries. Audit flooding (N6/N7).
4. Expected-value store: race conditions, stale rows, sibling-order logic (#307), cross-account leakage, what happens if the order owner differs from the requester, wildcard handling.
5. Information disclosure via unsigned SOA discovery (Q1/Q7): what exactly leaks to an unauthenticated network peer? Is it within the maintainer's acceptance?
6. Parser robustness: malformed packets, name compression loops, oversized RDATA, multiple OPT/TSIG, exceptions escaping to the server loop.
7. Secrets management: generation, storage (encryption at rest), display-once, logging (make sure secrets and MACs never reach logs/audit), FIPS.
8. Deployment: port defaults, binding address, Helm/Docker exposure, running unprivileged.
9. Any place where the plan contradicts an RFC MUST/MUST NOT, or the maintainer requirements, in a security-relevant way.
10. Missing negative tests for security properties.

Output: a list of findings, each with: severity (critical/high/medium/low/info), the plan section or invariant ID, the concrete attack or failure scenario, evidence (file:line or RFC section quote), and a concrete fix to the plan. Then a short list of things you checked and found sound. Do not edit any files.
```

### 5.4 PR 1: documentation (`implementer`)

The prompt in short (the full text has more than 100 lines): the goal and context of issue #416, the basis in RFC 8555 §8.4 and §7.5.1 (quotes), the list of products (new file `docs/integrations/acme-proxy-clients.md`, an example cert-manager manifest with a dummy acme-dns, links in ADMIN_GUIDE and in the examples README, an entry in CHANGELOG), and the configuration for certbot, acme.sh, lego, cert-manager, win-acme and Posh-ACME. The most important requirement:

```text
Every CLI flag, env var, file name and config key you write must be verified in the client source under /tmp/claude-0/clientsrc/ (or already present in this repo). In your final report, list each one with the source file and line where you verified it. If something cannot be verified, do not write it as fact.
```

### 5.5 Prompts for PR 2

The prompts for parts 2–9 of the plan are made from sections 2–7 and 11 of the plan. Each prompt contains: the invariant IDs from the table (with the columns P and N), the processing order from section 3, the decisions from section 5, the findings of the security review from section 11, the files to change, the files that the agent must not change (parallel work), and the test commands.

Parts 2 and 3 do not depend on each other. They run in parallel in the same worktree, on separate files.

The full prompts of all parts of PR 2 are in [`prompts-pr2.md`](prompts-pr2.md). Below are the most important elements of each prompt.

#### Part 3: TSIG module (`implementer`)

The most important elements of the prompt:

- the exact public API of the module (`TsigKeyMaterial`, `TsigOutcome`, `TsigResult`, `TimeWatermark`, `verify_request`, the `render_*` functions), so that the handler in part 5 can use them without guessing;
- the verification order step by step, with the RFC 8945 section numbers (§5.2: key, MAC size, MAC, time, truncation) and with the findings F5, F9, F11;
- a ban on relying on the automatic signing of dnspython (it sometimes signs with the server time and with the wrong request MAC for an error response);
- a requirement for **independent** MAC verification in the tests: the test computes the HMAC with the `hmac` module from the elements of RFC 8945 §4.3, not with the dnspython function that it tests;
- for each ID of the S table: a `_pos` test and a `_neg` test, with a description of what the negative test changes.

The part about the order (verbatim):

```text
## verify_request — exact order (RFC 8945 §5.2), no shortcuts
0. No TSIG in msg → `UNSIGNED`.
1. rdata.error != 0 → `FORMERR` (§4.2: "In requests, this MUST be zero"; §5.2: cannot be interpreted).
2. Key check (§5.2.1): `key = lookup_key(owner)`; `None` → `BADKEY`. `rdata.algorithm != key.algorithm` or `key.algorithm not in ALLOWED_TSIG_ALGORITHMS` → `BADKEY`. (Also BADKEY if key.secret is empty — defense in depth, F4.)
3. MAC size (§5.2.2.1), with `full = dns.tsig.mac_sizes[key.algorithm]`, `m = len(rdata.mac)`: `m > full` → `FORMERR`; `m < max(10, full // 2)` → `FORMERR` (this includes m == 0 in a request).
4. MAC check (§5.2.2):
   - `m == full`: call public `dns.tsig.validate(wire, dnspython_key, owner, rdata, rdata.time_signed, b"", tsig_start_offset(wire))`. Passing `now=rdata.time_signed` neutralises its time check (dnspython checks time BEFORE the MAC, which contradicts §5.2 order; the spike proves this works).
   - `m < full` (truncated, allowed range): build the request wire without the TSIG RR, compute the full MAC with public `dns.tsig.sign(...)` and compare with `hmac.compare_digest(full_mac[:m], rdata.mac)`. Mismatch → `BADSIG` (F5: never reach a signed response without a validated MAC).
5. Time check (§5.2.3, §10): `window = min(rdata.fudge, MAX_FUDGE)`; `abs(now - rdata.time_signed) > window` → `BADTIME`; `watermark.is_older(key.key_id, rdata.time_signed)` → `BADTIME`.
6. Truncation policy (§5.2.4): `m < full` → `BADTRUNC` (local policy requires the full MAC).
7. `watermark.record(key.key_id, rdata.time_signed)`; return `OK`.
```

#### Part 2: models, migration 111, key cleanup (`implementer`)

The most important elements of the prompt:

- the columns, constraints and indexes of both tables from the plan (2.1);
- encryption of the secret with the same layer as the EAB HMAC, but the getter returns `None` on a decryption error, **never** the ciphertext (F4, K7);
- the migration for SQLite and PostgreSQL, following the existing patterns (027, 078, 110) and the rules of `migration_runner.py`;
- deleting the keys in code when an EAB or a proxy account is deleted, because SQLite in UCM does not enforce foreign keys (F2, F3, K8, K9). The agent must check this, not assume it;
- `_pos`/`_neg` tests for K2, K3, K5, K8, K9 and for the UNIQUE constraint, also through the API (deleting an EAB and an account).

#### Part 4: expected values and hooks in the proxy (`implementer`)

- the exact API of the `records.py` module (`record_name_for`, `expected_value`, `zone_for`, `persist_expected_values`, `close_*`, `mark_confirmed`, the cache of active rows);
- a row for each sibling order with **its own** thumbprint and account (F13b, #307), written in a savepoint that never changes the result of `get_authz` (F13a, R6);
- independent computation of the value in the test (`hashlib` + `base64`) on the examples from RFC 8555 §8.3 and RFC 7638 §3.1;
- a "0 SQL queries" test for a warm cache (a `before_cursor_execute` counter).

Fix after the review in the main session: the specification closed the rows also in the states `processing` and `valid`. This caused a race with the UPDATE of the client. The rows now close only in the error states (plan 2.2, point 5).

#### Part 5a: key store, zone index, audit (`implementer`)

- `KeyScope.allows` fails closed: each `None` gives a denial (plan 2.3, K8);
- the key of an account with the proxy disabled, a revoked key, a secret that cannot be decrypted, an algorithm outside the list: the key does not exist for the listener (K7, K9);
- audit with a limit per pair (IP, reason) and a global limit per reason, with a summary row (F7, N7, N12);
- cleaning of the text from the attacker before it is written to the audit (N13), no secrets in the logs (N11).

#### Part 5b: protocol handler (`implementer`)

- the processing order step by step from the plan (section 3), with the RFC section numbers; each step has tests;
- the test client is an independent library (dnspython as a client), and the signed responses are verified on the client side;
- the message shapes of each client from the plan (section 9): nsupdate, certbot, lego, cert-manager, win-acme, acme.sh;
- no side effects in the negative tests (no `mark_confirmed`, no audit, no `touch`, no TSIG in the response);
- an integration test with a real database: 1000 unsigned SOA queries and 1000 UPDATEs with BADKEY, with no SQL queries (N8).

Fixes after the review in the main session: the EDNS size in the response (it was 8192, it is now `MAX_MESSAGE_SIZE`), the reason for a denial in the `reason` field of the audit row.

#### Part 6: UDP/TCP server (`implementer`)

- the table of resource limits from plan 2.4 as the specification (`ServerLimits`);
- RFC 7766: many messages in one connection, the idle limit counted from the last **complete** message, one write per response;
- a `bind` error does not stop UCM (N3), port 0 disables the listener (N1);
- start in `post_worker_init` (gunicorn, `workers = 1`) and in the development path of `app.py`.

#### Part 7: key API and port setting (`implementer`)

- the routes, permissions and responses follow the pattern of the EAB API (secret shown once);
- only `hmac-sha256`, `hmac-sha384`, `hmac-sha512`, also in FIPS mode (K4);
- port 0 or 1024–65535, with no conflict with the HTTPS and HTTP ports (N2);
- immediate invalidation of the key and zone cache after changes in the API (integration test).

#### Part 8: UI, help, translations (`implementer`)

- a key panel for the proxy account, a dialog with the secret shown once, ready configuration snippets for 7 clients;
- each client option name verified in the client source code;
- 9 languages, `check:i18n`, vitest tests.

Fixes after the review in the main session: `--validationmode dns-01` in the win-acme snippet, a note about port 53 for the port redirect.

#### Part 9: packages, Helm, documentation (`implementer`)

- `EXPOSE 8053/udp` and `8053/tcp`, a port check in the entrypoint (the container runs without the right to ports < 1024);
- a separate Helm Service for the listener (exposing the UI does not expose the listener), an optional NetworkPolicy;
- administrator and client documentation with facts from the client source code.

Fixes after the E2E in the main session: a troubleshooting section (the `bad authentication` messages in `miekg/dns`, the behavior of `nsupdate` after BADSIG, the `reason` field in the audit).

## 6. End-to-end tests

The main session does the E2E tests, with no agent. The procedure and the results are in [`docs/testing/ACME-PROXY-DNS-UPDATE.md`](../../testing/ACME-PROXY-DNS-UPDATE.md).

1. First the harness: only `DnsUpdateHandler` behind a simple UDP/TCP server, with keys and zones in memory. It checks the message format with the real client libraries, without the ACME flow.
2. Then the full flow: Pebble as the external CA, pebble-challtestsrv as DNS, UCM with the `custom_command` provider, real clients.
3. Each client has a positive test (certificate) and a negative test (key of another account, wrong secret, wrong algorithm, zone outside ACME Domains).

The E2E found a defect outside the scope of PR 2: the proxy does not add the header `Link: rel="up"` when the external CA does not send it (Pebble). This is a candidate for a separate fix.

## 7. Code review after the work is done

After the code is done: 3 rounds of `/code-review` and 3 rounds of `/security-review` on the whole PR 2 change, with fixes between the rounds. The main session checks each finding in the code and in the RFCs before it fixes it. The `implementer` agents prepare the fixes (separate files for each agent, parallel work). The main session reads the diff and runs the full tests before the commit. All findings, decisions (also "no change" with a reason) and commits are in section 12 of the plan.

After the review rounds, the main session repeats the E2E on the final code, on a new database.
