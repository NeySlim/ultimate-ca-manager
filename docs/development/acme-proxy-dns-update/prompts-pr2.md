# Prompty dla PR 2 (issue #416)

Ten plik zawiera pełne prompty, które dostali agenci `implementer` (mniejszy model, wysiłek medium) dla części 2–9 planu. Zasady pisania promptów i role są w [`agent-workflow.md`](agent-workflow.md). Prompty są zapisane bez zmian.

Ścieżki `/tmp/...` i `/home/user/...` w promptach to katalogi robocze w kontenerze sesji. Części 6 i 7 oraz 8 i 9 działały równolegle w osobnych worktree (`tmp/dns-update-*`). Główna sesja przeglądała każdy diff i przenosiła commity na gałąź PR 2 (cherry-pick).

## Część 2: modele, migracja 111, sprzątanie kluczy

Narzędzie: Agent, agent: `implementer`.

````text
Implement the data layer for a new DNS UPDATE (RFC 2136) listener in UCM. Work ONLY in the git worktree /home/user/ucm-dns-update (branch `claude/relaxed-planck-c6xvuc-dns-update`, based on upstream `dev`). Do NOT commit or push. Python venv: /home/user/ultimate-ca-manager/.venv. Run tests from /home/user/ucm-dns-update/backend with `/home/user/ultimate-ca-manager/.venv/bin/python -m pytest <files> -q -p no:cacheprovider`. Another agent works in parallel in the same worktree on `backend/services/acme/dns_update/` and `backend/tests/test_dns_update_tsig.py`: do not touch those.

Read first: the plan `docs/development/acme-proxy-dns-update/plan.pl.md` (Polish) sections 2.1, 2.2, 2.3, 4.5 (R and K tables), 7 ("Zmiany w istniejącym kodzie"), 11 (F2, F3, F4, F13). Then the existing code you extend: `backend/models/acme_models.py` (AcmeEabCredential ~L592-758, especially the `hmac_key_b64` property using `utils.encryption`; AcmeClientOrder ~L343-516; AcmeAccount), `backend/models/acme_client_account.py`, `backend/models/__init__.py`, `backend/utils/encryption.py`, `backend/migration_runner.py` (docstring rules: migrations ≥ 020 need `pg_compatible = True` and `upgrade(conn)` that handles both a `sqlite3.Connection` and a SQLAlchemy connection), example migrations `backend/migrations/027_acme_eab_credentials.py`, `078_revoked_serials.py`, `110_ssh_ca_allow_any_principal.py`, migration tests like `backend/tests/test_migration_101_acme_eab_keys.py`, `backend/services/backup/manifest.py` (every new table/column must be declared; `backend/tests/test_backup_manifest.py` enforces it), `backend/api/v2/acme/eab.py` (DELETE handler ~L189-230), `backend/api/v2/acme_client/accounts.py` (`_remove_account_row`).

## 1. Models: new file `backend/models/acme_dns_update.py`, exported from `backend/models/__init__.py`
### AcmeDnsUpdateKey (table `acme_dns_update_keys`)
Columns: `id` PK; `acme_client_account_id` Integer FK `acme_client_accounts.id` ondelete CASCADE, not null, indexed; `eab_credential_id` Integer FK `acme_eab_credentials.id` ondelete CASCADE, nullable, indexed; `name` String(255) unique not null (absolute DNS name, lowercase, trailing dot); `algorithm` String(32) not null default `hmac-sha256` (allowed: hmac-sha256, hmac-sha384, hmac-sha512); `_secret` column `secret` Text not null (encrypted); `status` String(16) not null default `active` (active|revoked), indexed; `created_at` DateTime default utcnow; `created_by_user_id` Integer nullable; `last_used_at` DateTime nullable; `revoked_at` DateTime nullable; `notes` Text nullable.
- Secret storage (F4): use the SAME layer as the EAB HMAC (`utils.encryption.encrypt_if_needed` on write). Property `secret` returns the decrypted base64 text or **None** when decryption fails or the value is empty — NEVER fall back to the stored ciphertext or to the raw value (unlike the EAB getter). Store the secret as standard base64 text (BIND key file format).
- Static helper `normalize_name(name: str) -> str`: strip, lowercase, ensure trailing dot, validate with `dns.name.from_text` (each label ≤ 63 bytes, whole name ≤ 255 bytes in wire format), reject the root name, reject empty labels; raise ValueError with a clear message. (K5)
- `to_dict()` never includes the secret (K3). Include id, acme_client_account_id, eab_credential_id, name, algorithm, status, created_at, created_by_user_id, last_used_at, revoked_at, notes.
### AcmeProxyDnsChallenge (table `acme_proxy_dns_challenges`)
Columns: `id` PK; `order_id` Integer FK `acme_client_orders.id` ondelete CASCADE not null, indexed; `acme_client_account_id` Integer nullable, indexed (proxy account of the order); `account_id` String(64) nullable (local AcmeAccount.account_id of the client); `client_jwk_thumbprint` String(128) not null; `identifier` String(255) not null (no `*.`); `record_name` String(255) not null, indexed (`_acme-challenge.<identifier>.`, lowercase, trailing dot); `txt_value` String(64) not null; `upstream_challenge_url` Text nullable; `status` String(16) not null default `pending` (pending|closed); `created_at` DateTime default utcnow; `expires_at` DateTime not null; `client_confirmed_at` DateTime nullable. UniqueConstraint(order_id, record_name, txt_value). Index on (status, expires_at).
Look at how other models in acme_models.py declare FKs, indexes and datetime defaults and follow that style exactly.

## 2. Migration `backend/migrations/111_acme_dns_update.py`
`pg_compatible = True`, `upgrade(conn)` and `downgrade(conn)` for SQLite and PostgreSQL, creating both tables with the same columns, constraints and indexes as the models (CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS, follow 027/078). Then `backend/tests/test_migration_111_acme_dns_update.py` following test_migration_101: SQLite upgrade creates tables/indexes/unique constraint; idempotent second run; downgrade drops them; a PostgreSQL variant marked `postgres` like the existing PG migration tests (it will be skipped without UCM_TEST_PG_URL — that is fine).

## 3. Backup manifest
Declare both tables in `backend/services/backup/manifest.py` the way EAB credentials and CA accounts are declared (look at how encrypted/secret columns such as the EAB HMAC are classified and do the same for `acme_dns_update_keys.secret`). Make `backend/tests/test_backup_manifest.py` pass.

## 4. Fail-closed cleanup in existing code (SQLite in UCM does not enforce foreign keys at runtime — verify: no `PRAGMA foreign_keys=ON` on connect)
- `backend/api/v2/acme/eab.py` DELETE handler: in every branch that deletes or revokes a credential, also delete the `AcmeDnsUpdateKey` rows with that `eab_credential_id`, in the same transaction, before the commit. (F2, K8)
- `backend/api/v2/acme_client/accounts.py` `_remove_account_row` (and any other path that deletes an AcmeClientAccount row): delete that account's `AcmeDnsUpdateKey` rows and `AcmeProxyDnsChallenge` rows (by acme_client_account_id) in the same transaction. (F3, K9)
Keep these changes minimal and in the style of the surrounding code.

## 5. Tests: `backend/tests/test_dns_update_models.py`
Each invariant has a POSITIVE and a NEGATIVE test named `test_<ID>_<what>_pos|_neg` (IDs from plan §4.5). Use the existing fixtures from `backend/tests/conftest.py` (`app`, `auth_client`, etc.) and the seeding style of `backend/tests/test_acme_proxy_ca_account.py` / `test_acme_proxy_issue_fixes.py`. Required:
- K2: the raw DB value of `secret` (query with `db.session.execute(text("SELECT secret FROM acme_dns_update_keys ..."))`) is not the plaintext and is a Fernet token; reading through the model returns the plaintext (pos). Neg: corrupt the stored ciphertext (or patch decrypt to fail) → model property returns None (K7), never the ciphertext.
- K5: normalize_name accepts `Key1.Example.COM` → `key1.example.com.`; neg: label of 64 bytes, name > 255 bytes, empty label `a..b`, root `.` → ValueError; uniqueness: inserting `KEY.example.` after `key.example.` (both normalized) violates the unique constraint.
- K3: to_dict has no secret key and no secret value (pos/neg on content).
- K8: create EAB credential + linked key; DELETE the EAB through the API (`auth_client`, route `/api/v2/acme/eab-credentials/<id>`) for an active, a used and a revoked credential → key rows gone (pos); a key linked to another credential stays (neg).
- K9: delete a proxy CA account through its API delete route → its keys and challenge rows are gone (pos); keys/rows of another account stay (neg). Then create a new account and check that no old key references its id.
- R-model: unique constraint (order_id, record_name, txt_value) rejects a duplicate (neg) and accepts a different value for the same name (pos).

## Validation
- Run: the new tests, `tests/test_backup_manifest.py`, `tests/test_migration_runner*.py`, every existing `tests/test_acme_proxy*.py`, `tests/test_acme*eab*.py` and the existing tests for the accounts API (find them with grep for `acme/client/accounts`). All green.
- Ruff/pyflakes on the changed files if available.
- Report: files changed, model/migration summary, test names mapped to IDs, anything you could not do and why.
````

## Część 2: uzupełnienie (kolumna zone_name, SendMessage)

Narzędzie: SendMessage, agent: `SendMessage` do agenta części 2.

````text
Spec addition for AcmeProxyDnsChallenge (model + migration 111 + manifest + tests): add column `zone_name` String(255) NOT NULL — the absolute, lowercase, trailing-dot apex D of the ACME → Domains entry that covers the identifier (the `matched_domain` returned by `api.v2.acme_domains.find_provider_for_domain(identifier)`, with any leading `*.` removed). It is computed when the row is written (in a later part), so the DNS listener never needs to query ACME Domains to answer SOA. Add an index on `zone_name`. Everything else in the spec is unchanged.
````

## Część 3: moduł TSIG

Narzędzie: Agent, agent: `implementer`.

````text
Implement the server-side TSIG (RFC 8945) module for a new DNS UPDATE listener in UCM. Work ONLY in the git worktree /home/user/ucm-dns-update (branch `claude/relaxed-planck-c6xvuc-dns-update`, based on upstream `dev`). Do NOT commit or push. Python venv: /home/user/ultimate-ca-manager/.venv (dnspython 2.8.0). Run tests with: `cd /home/user/ucm-dns-update/backend && /home/user/ultimate-ca-manager/.venv/bin/python -m pytest tests/test_dns_update_tsig.py -q -p no:cacheprovider`. Another agent works in parallel in the same worktree on models/migrations (backend/models, backend/migrations, backend/api/v2/acme/eab.py, backend/api/v2/acme_client/accounts.py): do not touch those files.

Read first: the design plan `docs/development/acme-proxy-dns-update/plan.pl.md` (Polish; sections 3 step 6, 4.2 table S1–S15, 5 decisions 6, 7, 11, 12, 11 "Security review" F5/F9/F11), the RFC text https://www.rfc-editor.org/rfc/rfc8945.txt (local clean copy: /tmp/claude-0/-home-user-ultimate-ca-manager/5d252c34-87db-550d-aac1-9cb612323145/scratchpad/rfc/rfc8945.clean.txt, sections 4.2, 4.3, 5.1–5.4, 6, 7, 10), the spike `docs/development/acme-proxy-dns-update/spike/tsig_spike.py` (proves the approach), and dnspython 2.8.0 `dns/tsig.py` and `dns/message.py` in the venv.

## Files to create
- `backend/services/acme/dns_update/__init__.py` (empty docstring module)
- `backend/services/acme/dns_update/constants.py`
- `backend/services/acme/dns_update/tsig.py`
- `backend/tests/test_dns_update_tsig.py`
Match the style of existing modules in backend/services/acme/ (module docstring, logging.getLogger(__name__), type hints where the codebase uses them).

## constants.py
- `ALLOWED_TSIG_ALGORITHMS`: dns.name.Name for hmac-sha256, hmac-sha384, hmac-sha512 (dns.tsig.HMAC_SHA256 etc.). Nothing else (no md5, sha1, sha224, truncated variants, gss-tsig) — RFC 8945 §7 local policy, maintainer: "nothing weaker than SHA-256".
- `SECRET_LENGTHS = {sha256: 32, sha384: 48, sha512: 64}` (RFC 8945 §8: secret at least as long as the hash output).
- `MAX_FUDGE = 300`, `RESPONSE_FUDGE = 300`.

## tsig.py — public API (exact)
```python
@dataclass(frozen=True)
class TsigKeyMaterial:
    key_id: int
    name: dns.name.Name        # absolute, compared case-insensitively by dnspython
    algorithm: dns.name.Name   # one of ALLOWED_TSIG_ALGORITHMS
    secret: bytes              # non-empty raw bytes
    def __repr__(self) -> str: ...   # MUST NOT include the secret (F11)

class TsigOutcome(enum.Enum):
    UNSIGNED, OK, FORMERR, BADKEY, BADSIG, BADTIME, BADTRUNC

@dataclass
class TsigResult:
    outcome: TsigOutcome
    key: Optional[TsigKeyMaterial] = None      # set for OK, BADTIME, BADTRUNC only
    keyname: Optional[dns.name.Name] = None    # owner of the request TSIG RR, if any
    rdata: Optional[...] = None                # request TSIG rdata (dns.rdtypes.ANY.TSIG.TSIG), if any
    request_mac: bytes = b""                   # MAC exactly as received
    # __repr__ must not include MACs.

class TimeWatermark:   # RFC 8945 §5.2.3 SHOULD: most recent Time Signed per key
    def __init__(self, max_keys: int = 4096): ...   # bounded (LRU eviction), thread-safe (threading.Lock)
    def is_older(self, key_id: int, time_signed: int) -> bool    # strictly earlier than the stored value
    def record(self, key_id: int, time_signed: int) -> None      # stores max(old, new)

def tsig_start_offset(wire: bytes) -> int
    # offset of the LAST RR of the additional section, walked with public dns.wire.Parser (see spike)

def verify_request(wire: bytes, msg: dns.message.Message,
                   lookup_key: Callable[[dns.name.Name], Optional[TsigKeyMaterial]],
                   now: int, watermark: TimeWatermark) -> TsigResult
    # msg was parsed by the caller with dns.message.from_wire(wire, keyring=False) — dnspython then
    # does NOT validate anything (verify this in message.py) and keeps the TSIG in msg.tsig.

def generate_secret(algorithm: dns.name.Name) -> bytes      # secrets.token_bytes(SECRET_LENGTHS[alg]); ValueError for others

def render_signed(response: dns.message.Message, result: TsigResult, now: int,
                  max_size: Optional[int] = None) -> bytes
def render_unsigned_tsig_error(response: dns.message.Message, result: TsigResult,
                               error: int) -> bytes          # BADKEY or BADSIG
def render_badtime(response: dns.message.Message, result: TsigResult, now: int) -> bytes
def render_badtrunc(response: dns.message.Message, result: TsigResult, now: int) -> bytes
```
`response` is always a response skeleton built by the caller with `dns.message.make_response(query, pad=0)` from a query parsed with keyring=False, so `response.tsig` is None and dnspython will not sign it. Your render functions must never rely on dnspython's automatic signing (it signs with the server time and the wrong request MAC for our error cases).

## verify_request — exact order (RFC 8945 §5.2), no shortcuts
0. No TSIG in msg → `UNSIGNED`.
1. rdata.error != 0 → `FORMERR` (§4.2: "In requests, this MUST be zero"; §5.2: cannot be interpreted).
2. Key check (§5.2.1): `key = lookup_key(owner)`; `None` → `BADKEY`. `rdata.algorithm != key.algorithm` or `key.algorithm not in ALLOWED_TSIG_ALGORITHMS` → `BADKEY`. (Also BADKEY if key.secret is empty — defense in depth, F4.) The lookup function decides revoked/disabled keys; just treat None as unknown.
3. MAC size (§5.2.2.1), with `full = dns.tsig.mac_sizes[key.algorithm]`, `m = len(rdata.mac)`: `m > full` → `FORMERR`; `m < max(10, full // 2)` → `FORMERR` (this includes m == 0 in a request).
4. MAC check (§5.2.2):
   - `m == full`: call public `dns.tsig.validate(wire, dnspython_key, owner, rdata, rdata.time_signed, b"", tsig_start_offset(wire))`. Passing `now=rdata.time_signed` neutralises its time check (dnspython checks time BEFORE the MAC, which contradicts §5.2 order; the spike proves this works). Catch `dns.tsig.BadSignature`, `dns.tsig.BadKey`, `dns.tsig.BadAlgorithm` → `BADSIG` (BadKey/BadAlgorithm cannot normally happen after step 2, map them to BADSIG anyway? NO: map BadKey/BadAlgorithm to BADKEY to stay truthful). Any other exception from validate → `FORMERR`.
   - `m < full` (truncated, allowed range): build the request wire without the TSIG RR (header ARCOUNT-1, bytes up to tsig_start), compute the full MAC with public `dns.tsig.sign(new_wire, dnspython_key, rdata, time=rdata.time_signed, request_mac=b"")` and compare with `hmac.compare_digest(full_mac[:m], rdata.mac)`. Mismatch → `BADSIG` (F5: never reach a signed response without a validated MAC).
5. Time check (§5.2.3, §10): `window = min(rdata.fudge, MAX_FUDGE)`; `abs(now - rdata.time_signed) > window` → `BADTIME`; `watermark.is_older(key.key_id, rdata.time_signed)` → `BADTIME`.
6. Truncation policy (§5.2.4): `m < full` → `BADTRUNC` (local policy requires the full MAC).
7. `watermark.record(key.key_id, rdata.time_signed)`; return `OK`.
For OK/BADTIME/BADTRUNC set `result.key`. Always set keyname, rdata, request_mac when a TSIG is present.

## render functions
- `render_signed`: render `response.to_wire()` (no TSIG), then append ONE TSIG RR (owner = key.name, class ANY, TTL 0) whose rdata = `TSIG(algorithm=key.algorithm, time_signed=now, fudge=RESPONSE_FUDGE, mac=<computed>, original_id=<request message id>, error=0, other=b"")`, signed with `dns.tsig.sign(body_wire, key, rdata, time=now, request_mac=result.request_mac)` (request MAC as received — for a truncated request this is the truncated MAC, §5.2.2.1). Increment ARCOUNT in the header. The TSIG must be the last RR (after OPT). Response MAC is full length (§7: never shorter than the request MAC). If `max_size` is given and the signed wire is larger: build the truncated form required by §5.3 — header + question section (copy) + OPT if the response had one + TSIG, TC bit set, RCODE NOERROR (RFC 8945 §5.3: "This response contains only the question and a TSIG record, has the TC bit set, and has an RCODE of 0 (NOERROR)"; RFC 6891 §7: OPT stays in a truncated response) and sign THAT.
- `render_unsigned_tsig_error`: response RCODE NOTAUTH; append a TSIG RR with owner = request key name, algorithm = request algorithm, time_signed = request time_signed, fudge = request fudge, mac = b"" (MAC Size 0), original_id = request id, error = BADKEY (17) or BADSIG (16), other = b"". Not signed (§5.2.1, §5.2.2, §5.3.2: "MUST NOT send back a signed error message").
- `render_badtime`: RCODE NOTAUTH; signed with the key; TSIG rdata: time_signed = REQUEST time_signed (client's time), fudge = REQUEST fudge, other = 6-byte big-endian server time (48-bit unsigned) and Other Len 6, error = BADTIME (18), original_id = request id; MAC computed over request MAC (validated) + response + TSIG variables (§5.3.2) — i.e. `dns.tsig.sign(body, key, rdata, time=request_time_signed, request_mac=result.request_mac)`.
- `render_badtrunc`: RCODE NOTAUTH; signed with the key; time_signed = now; fudge = RESPONSE_FUDGE; error = BADTRUNC (22); request_mac = the truncated request MAC.
Use only public dnspython API (dns.tsig.sign, dns.tsig.validate, dns.tsig.Key, dns.rdtypes.ANY.TSIG.TSIG, dns.rrset, dns.wire.Parser, Message.to_wire). Do not hand-roll HMAC except `hmac.compare_digest` on the truncated prefix. Never log keys, secrets, MACs, keyrings or `Message.to_text()` (F11); logging is not needed in this module at all.

## Tests: backend/tests/test_dns_update_tsig.py
Every invariant gets a POSITIVE and a NEGATIVE test named `test_<ID>_<what>_pos` / `test_<ID>_<what>_neg`. The negative test changes exactly one thing that violates the invariant. Build client requests with dnspython as an independent client (`dns.update.UpdateMessage(..., keyring=..., keyname=..., keyalgorithm=...)`, `dns.message.make_query(...).use_tsig(...)`), parse with `dns.message.from_wire(wire, keyring=False)`, call verify_request with a dict-backed lookup. Use a fixed `now` and set the request time with `msg.use_tsig(..., fudge=...)` + rendering at a controlled time (you can monkeypatch `time.time` in dnspython.message during client rendering, or build the TSIG rdata yourself with dns.tsig.sign). Required tests (IDs from plan §4.2):
- S2 unknown key → BADKEY (pos: known key OK).
- S3 algorithm mismatch / disallowed: key sha256, request signed with same name but hmac-sha1 → BADKEY; key stored with hmac-md5 or hmac-sha224 → BADKEY. Pos: sha256, sha384, sha512 each OK.
- S4 bad MAC: flip one MAC byte; wrong secret; message body changed after signing (e.g. change one TXT byte) → BADSIG. Pos: untouched → OK.
- S5 order: bad MAC AND bad time → BADSIG (not BADTIME); unknown key AND bad time → BADKEY; good MAC and bad time → BADTIME.
- S6 time: |now − t| == window → OK; window + 1 → BADTIME. render_badtime output: parse with keyring=False, check RCODE NOTAUTH, TSIG error 18, time_signed == request time, fudge == request fudge, len(other) == 6 and value == now, and verify its MAC INDEPENDENTLY: recompute HMAC-SHA256 with Python's `hmac` module over the RFC 8945 §4.3 digest components (request MAC length + request MAC, response wire without TSIG and with ARCOUNT-1, key name canonical wire, class ANY, TTL 0, algorithm name canonical wire, 48-bit time signed, fudge, error, other len, other data) and compare. This independent check is mandatory for render_signed (success) and render_badtime.
- S7 watermark: same and later time OK; earlier than last recorded → BADTIME; and the watermark is NOT updated by a request that fails MAC (BADSIG) or time (BADTIME) checks (pos/neg).
- S8 MAC size for sha256: 33 B → FORMERR; 9 B → FORMERR; 0 B → FORMERR; 16 B correct truncated prefix → BADTRUNC (and render_badtrunc is signed and verifiable); 16 B with wrong bytes → BADSIG (neg, F5). Pos: 32 B → OK. (Build truncated requests by signing with dnspython full MAC then replacing rdata.mac with mac[:16] and re-rendering the TSIG RR, or by assembling the TSIG RR yourself.)
- S9 request TSIG error field 16 → FORMERR; 0 → OK.
- S10 render_signed output verifies with dnspython as a client: `dns.message.from_wire(resp, keyring={name: key}, request_mac=<request mac>)` succeeds; neg: same response bytes with one MAC byte flipped fails.
- S11 response MAC length == full hash length for all three algorithms (and ≥ request MAC length).
- S12 render_signed with max_size smaller than the full response → TC=1, RCODE NOERROR, only question (+OPT if present) + TSIG, verifies with dnspython client; neg: max_size large → no TC, full answer.
- S13 key name case: request key name `K1.Example.` matches stored `k1.example.`; a different name → BADKEY.
- S14 fudge cap: request fudge 65535 and skew 301 → BADTIME, and render_badtime echoes fudge 65535; fudge 300 skew 300 → OK.
- BADKEY/BADSIG rendering: render_unsigned_tsig_error → RCODE NOTAUTH, TSIG present, MAC size 0, error 17 / 16; neg: never contains a non-empty MAC.
- F11: `repr(TsigKeyMaterial)` and `repr(TsigResult)` do not contain the secret (base64 or raw) or the MAC.
- generate_secret: lengths 32/48/64; ValueError for hmac-sha1; 1000 secrets unique.
- tsig_start_offset: equals the offset dnspython would use (compare with a message whose TSIG you appended yourself at a known offset), also with name compression in earlier sections.

## Validation
- `python -m pytest tests/test_dns_update_tsig.py -q` all green.
- `cd /home/user/ucm-dns-update/backend && /home/user/ultimate-ca-manager/.venv/bin/python -m ruff check services/acme/dns_update tests/test_dns_update_tsig.py` if ruff is installed (else `python -m pyflakes`); fix findings.
- Report: files, public API as implemented, each test name mapped to its invariant ID, any deviation from this spec and why, and anything in dnspython that behaved differently than described here.
````

## Część 4: wartości oczekiwane i haki w proxy

Narzędzie: Agent, agent: `implementer`.

````text
Implement the "expected TXT value" store for the DNS UPDATE (RFC 2136) listener in UCM, and hook it into the ACME proxy. Work ONLY in the git worktree /home/user/ucm-dns-update (branch `claude/relaxed-planck-c6xvuc-dns-update`). Do NOT commit or push. Venv: /home/user/ultimate-ca-manager/.venv. Run tests from /home/user/ucm-dns-update/backend with `/home/user/ultimate-ca-manager/.venv/bin/python -m pytest <files> -q -p no:cacheprovider`. Another agent is working in parallel on `backend/services/acme/dns_update/tsig.py`, `constants.py` and `backend/tests/test_dns_update_tsig.py`: do not touch those (you may add a new module in the same package).

Read first: plan `docs/development/acme-proxy-dns-update/plan.pl.md` (Polish) sections 2.1 (table `acme_proxy_dns_challenges`, incl. `zone_name`), 2.2 (lifecycle), 2.3, 2.4 (caches), 4.5 (R1–R7), 11 (F13). The models already exist: `backend/models/acme_dns_update.py` (`AcmeProxyDnsChallenge`). Proxy code: `backend/services/acme/acme_proxy_service.py` — `_dns01_txt_value` (~L61), `_client_txt_values` (~L906), `_orders_by_authz_url`, `get_authz` (~L1104-1225), `respond_challenge` (~L1227-1340), `get_certificate` (~L1868-1906). Domain lookup: `backend/api/v2/acme_domains.py` `find_provider_for_domain` (returns `matched_domain`). Existing proxy test helpers: `backend/tests/acme_proxy_upstream_stub.py`, `backend/tests/test_acme_proxy_issue_fixes.py` (`_make_service`, `_seed_proxy_order`, how `threading.Thread` and `_post_with_account` are patched), `backend/tests/test_acme_proxy_ca_account.py`. Find an existing test that seeds `AcmeDomain` + `DnsProvider` and copy its seeding.

## New module: backend/services/acme/dns_update/records.py
- Constants: `ACTIVE_MAX_AGE = timedelta(hours=24)`, `PURGE_AFTER = timedelta(days=7)`, `CACHE_MAX_AGE_S = 5`.
- `record_name_for(identifier: str) -> str`: lowercase, strip a leading `*.`, return `_acme-challenge.<identifier>.` (RFC 8555 §8.4, §7.1.4).
- `expected_value(token: str, thumbprint: str) -> str`: base64url(SHA-256(f"{token}.{thumbprint}")) without padding (RFC 8555 §8.1, §8.4; RFC 4648 §5). Must equal `acme_proxy_service._dns01_txt_value`. Do not import acme_proxy_service from records.py (avoid an import cycle; acme_proxy_service will import records).
- `zone_for(identifier) -> Optional[str]`: `find_provider_for_domain(identifier)`; None if no match; else `matched_domain` lowercased, leading `*.` removed, trailing dot added.
- `persist_expected_values(orders, identifier, token, challenge_url, authz_expires, now) -> int`: one row per order in `orders` (dedupe by order id). Each row uses THAT order's own `client_jwk_thumbprint`, `account_id` and `acme_client_account_id` (F13b, #307). Skip an order whose `client_jwk_thumbprint` is empty (R7). `zone_name = zone_for(identifier)`; if None, write nothing. `expires_at = min(parsed authz_expires (RFC 3339 string, may be None or unparsable → ignore), now + ACTIVE_MAX_AGE)`. Do it inside `db.session.begin_nested()`; an `IntegrityError` (duplicate of the UNIQUE (order_id, record_name, txt_value)) or any other exception rolls back the SAVEPOINT only, is logged at warning level without values, and never propagates (F13a, R6). Insert only rows that do not exist yet (query first; the UNIQUE constraint is the backstop for races). In the same savepoint delete rows with `expires_at < now - PURGE_AFTER`. Then `db.session.commit()` (if the commit fails: rollback, log, return 0 — never raise). Call `invalidate_cache()` after a successful commit. Return the number of inserted rows.
- `close_for_order(order_id)` and `close_for_challenge_urls(urls)`: set `status='closed'` for matching pending rows, commit (errors → rollback + log, never raise), `invalidate_cache()`.
- `mark_confirmed(row_ids, now)`: set `client_confirmed_at = now` (used later by the listener), commit, never raise.
- Active-row cache (plan 2.4): a module-level `ActiveRecordCache` with an `ActiveRecord` NamedTuple(row_id, order_id, record_name, txt_value, zone_name, acme_client_account_id, account_id). `snapshot(now)` returns an immutable view with: `by_name: dict[record_name -> tuple[ActiveRecord]]`, `zones: frozenset[zone_name]`. It reloads from the DB only when `invalidate_cache()` was called since the last load or the snapshot is older than CACHE_MAX_AGE_S. A row is active when `status == 'pending'`, `expires_at > now`, and its order (`AcmeClientOrder`) has `status == 'pending'` (one query with a join). Reload under a `threading.Lock` (gevent patches it); a DB error during reload keeps the previous snapshot and logs a warning (never raises). Provide `get_active_snapshot(now)` and `invalidate_cache()` at module level. Must work inside a Flask app context; document that the caller provides it.

## Hooks in backend/services/acme/acme_proxy_service.py (minimal, in the style of the file)
- `get_authz`: for each `dns-01` challenge whose status is `pending` while the authz is not `already_valid`, call `persist_expected_values(candidates, domain, chall['token'], chall_url, authz.get('expires'), now)` where `candidates` is the list already returned by `_orders_by_authz_url(authz_url)` (it includes the requester's order and its siblings). Call it BEFORE the existing "automation started" block and independent of it (the row must exist even when a sibling already started the automation). It must never change the outcome of `get_authz` (R6).
- `get_authz`: when the authz is `already_valid`, or a challenge status is not `pending`, call `close_for_challenge_urls([...those challenge urls...])`.
- `respond_challenge`: in the `status != 'pending'` branch, `close_for_challenge_urls([chall_url])`.
- `get_certificate`: after the order is set to `valid` and committed, `close_for_order(order.id)`.
Wrap every hook so that an exception is logged and swallowed.

## Tests: backend/tests/test_dns_update_records.py
Every invariant: `test_<ID>_<what>_pos` and `_neg`; the negative test changes one thing that violates the invariant.
- R1: `expected_value` with the RFC 8555 §8.3 example token `evaGxfADs6pSRb2LAv9IZf17Dt3juxGJ-PCt92wr-oA` and the RFC 7638 §3.1 thumbprint `NzbLsXh8uDCcd-6MNwXF4W_7noWXFZAfHkxZsRGC9Xs`: equals a value you compute independently in the test with `hashlib.sha256` + `base64.urlsafe_b64encode(...).rstrip(b'=')`, and equals `acme_proxy_service._dns01_txt_value`. Neg: output never contains `=`, `+`, `/` (property test over 200 random tokens/thumbprints) and has length 43.
- R2: `*.Example.COM` → `_acme-challenge.example.com.`; neg: never contains `*`.
- R3 (integration through `AcmeProxyService.get_authz`, upstream stubbed like the existing proxy tests): two proxy orders (different `client_jwk_thumbprint` and `account_id`, same upstream authz URL, same proxy account) and an `AcmeDomain` for `example.com` → after get_authz by one owner, two rows exist, each with its own order's thumbprint-derived value, `zone_name == 'example.com.'`, `record_name == '_acme-challenge.app.example.com.'`. Neg cases (each a separate test): upstream authz `valid` → no rows; requester not the owner → existing ownership error and no rows; authz without a dns-01 challenge → no rows; no ACME Domains entry → no rows.
- R4: after `get_certificate` (stubbed) rows of that order are `closed`, other order's rows untouched (neg). get_authz seeing the authz `valid` closes the rows of its challenge URLs. `expires_at` with authz `expires` = now + 7 days is capped to now + 24 h (pos); authz `expires` = now + 1 h is kept (neg of the cap).
- R6: with a pre-existing duplicate row and with `db.session.flush` patched to raise once inside the savepoint, `get_authz` still returns the authz and the `challenges_data` "initiated" entry is committed (when the automation thread is triggered — patch Thread like the existing tests).
- R7: a sibling order with `client_jwk_thumbprint = None` gets no row; the other order does.
- Cache: snapshot contains a new row only after `invalidate_cache()` or after CACHE_MAX_AGE_S (patch time); closed rows, expired rows and rows of non-pending orders are not in the snapshot (neg); a warm snapshot runs 0 SQL statements (count with `sqlalchemy.event.listen(db.engine, "before_cursor_execute", ...)`); a DB error during reload keeps the previous snapshot.
- Run also all existing `tests/test_acme_proxy*.py` to make sure the hooks change nothing else.

## Report
Files changed, functions added, test names mapped to IDs, full test results (new + existing proxy tests), and any deviation from this spec with the reason.
````

## Część 5a: magazyn kluczy, indeks stref, audyt

Narzędzie: Agent, agent: `implementer`.

````text
Implement three support modules for the DNS UPDATE (RFC 2136) listener in UCM. Work ONLY in the git worktree /home/user/ucm-dns-update (branch `claude/relaxed-planck-c6xvuc-dns-update`). Do NOT commit or push. Venv: /home/user/ultimate-ca-manager/.venv. Run tests from /home/user/ucm-dns-update/backend with `/home/user/ultimate-ca-manager/.venv/bin/python -m pytest <files> -q -p no:cacheprovider`. Another agent works in parallel on `backend/services/acme/dns_update/records.py`, `backend/services/acme/acme_proxy_service.py` and `backend/tests/test_dns_update_records.py`: do not touch those. Do not change `tsig.py` or `constants.py` (already reviewed and committed); import from them.

Read first: plan `docs/development/acme-proxy-dns-update/plan.pl.md` (Polish) sections 2.3, 2.4, 3 (step 6b, 11), 4.5 (K-table), 4.6 (N6, N7, N8, N11, N12, N13), 11 (F1, F2, F3, F4, F7, F11). Existing code: `backend/services/acme/dns_update/tsig.py` (`TsigKeyMaterial`), `backend/models/acme_dns_update.py` (`AcmeDnsUpdateKey`, secret property returns None when it cannot be decrypted), `backend/models/acme_client_account.py` (`proxy_enabled`), `backend/models/acme_models.py` (`AcmeEabCredential`: `status`, `used_by_account_id`; `AcmeDomain.domain`), `backend/services/audit/core.py` (`AuditService.log_action`), `backend/api/v2/acme_domains.py` (how AcmeDomain entries are stored, wildcard spelling).

## 1. backend/services/acme/dns_update/keys.py — key store with cache (F1, F2, F3, F4)
```python
@dataclass(frozen=True)
class KeyScope:
    acme_client_account_id: int
    eab_bound: bool                    # True if the key has an eab_credential_id
    eab_account_id: Optional[str]      # AcmeAccount.account_id bound to that EAB, or None
    def allows(self, row_acme_client_account_id, row_account_id) -> bool
        # fail closed (plan 2.3): proxy account must match; if eab_bound: eab_account_id must be
        # non-empty AND row_account_id non-empty AND equal. Any None → False.

class KeyStore:
    def __init__(self, max_age_s: float = 30.0, clock=time.monotonic): ...
    def lookup(self, name: dns.name.Name) -> Optional[TsigKeyMaterial]   # cached, case-insensitive
    def scope(self, key_id: int) -> Optional[KeyScope]                   # cached
    def invalidate(self) -> None                                          # next call reloads
    def touch(self, key_id: int, now: datetime) -> None   # sets last_used_at, at most once per 60 s per key; never raises
```
Loading (one pass, inside the caller's Flask app context): every `AcmeDnsUpdateKey` with `status == 'active'` whose proxy account (`AcmeClientAccount`) exists AND has `proxy_enabled == True` (K9), whose algorithm is one of `constants.ALLOWED_TSIG_ALGORITHMS`, and whose `secret` property returns a non-empty value that base64-decodes to non-empty bytes (K7; otherwise skip the key and log ONE warning with the key name only, never the value). For a key with `eab_credential_id`: load the credential; `eab_account_id = cred.used_by_account_id` only if the credential exists, `status == 'used'` and `used_by_account_id` is non-empty; otherwise `eab_account_id=None` (the key stays valid for TSIG but its scope matches nothing — K8). Build `TsigKeyMaterial(key_id, dns.name.from_text(name), dns.name.from_text(algorithm), secret_bytes)`. The cache is a dict keyed by the canonical lowercase name; reload when invalidated or older than `max_age_s`; protect with a `threading.Lock`; a DB error during reload keeps the previous cache and logs a warning (no secret). Never log keys, secrets or `TsigKeyMaterial` objects with secrets (its repr is already safe). Module-level singleton `key_store = KeyStore()` and `invalidate_keys()` helper.

## 2. backend/services/acme/dns_update/zones.py — our authority zones (plan 2.3, U3)
```python
class ZoneIndex:
    def __init__(self, max_age_s: float = 10.0, clock=time.monotonic): ...
    def zones(self) -> frozenset[dns.name.Name]       # apex names of ACME Domains entries (lowercase, absolute, '*.' removed)
    def is_authoritative(self, zname: dns.name.Name) -> bool
        # True if zname is one of zones(), or a proper ANCESTOR of one of them, and zname is
        # neither the root nor a single-label name (a TLD). Descendants of a zone → False.
    def invalidate(self) -> None
```
Load from `AcmeDomain` (all entries; normalize the stored spelling exactly as find_provider_for_domain matching treats it: lowercase, strip a leading `*.`). Cache like KeyStore (lock, TTL, keep previous on DB error). Module singleton `zone_index`.

## 3. backend/services/acme/dns_update/audit.py — bounded audit sink (F7, N6, N7, N12, N13)
```python
class AuditSink:
    def __init__(self, per_ip_per_minute: int = 1, global_per_reason_per_minute: int = 20,
                 max_ips: int = 4096, clock=time.monotonic): ...
    def record(self, *, action: str, reason: str, peer_ip: str, keyname: Optional[str],
               success: bool, details: dict) -> bool   # True if an audit row was written
```
Rules: a per-(peer_ip, reason) limit (default 1 row per 60 s) kept in a bounded LRU (max_ips entries) AND a global per-reason limit (default 20 rows per 60 s regardless of IP). When the global limit drops events, count them and, when the next minute window opens, write ONE summary row (`action='acme.dns_update.suppressed'`, details with reason and dropped count). Writes go through `AuditService.log_action(action=..., resource_type='acme_dns_update', resource_name=<keyname or 'unauthenticated'>, details=json.dumps(details), success=success, username=f"dns-update:{keyname}" if keyname else "dns-update:unauthenticated", ip_address=peer_ip)`. Sanitize every attacker-controlled string before it goes into details/username/resource_name: `keyname` and DNS names are passed as text, truncated to 255 chars, and every character that is not printable ASCII (codes < 0x20, 0x7f, non-ASCII) replaced by `?`. Never put secrets, MACs or raw packets in details. `record` never raises (catch everything, log a warning). Module singleton `audit_sink`.
Also extend `AuditService.log_action` in `backend/services/audit/core.py` with an optional keyword parameter `ip_address=None`: when given, it is stored instead of the IP derived from the request context (no request context exists in the listener). Keep the default behaviour identical for all existing callers. Check `backend/services/audit/helpers.py` / `__init__.py` wrappers and keep them working.

## Tests: backend/tests/test_dns_update_keys_zones_audit.py
Every invariant: `test_<ID>_<what>_pos` and `_neg`, the negative test changes one thing.
- K7: key with a corrupt stored secret (write an invalid Fernet token directly) → `lookup` returns None (neg); valid key → material with the right bytes (pos).
- K8: EAB-bound key: credential `used` with account `acct-1` → scope allows (account X, 'acct-1') (pos); credential `active` (unused), credential with `used_by_account_id` NULL, credential row deleted directly in the DB (simulating SQLite without FK) → scope allows nothing; row with `account_id` None never allowed (neg, one test per case).
- K9: key of an account with `proxy_enabled=False` → lookup None; key whose account row is deleted directly in the DB → lookup None; revoked key → None (neg); active key of an enabled account → found (pos).
- S13-style: lookup is case-insensitive (`KEY1.Example.` finds `key1.example.`).
- Cache (F1/N8): after a warm load, 1000 `lookup()` calls (known and unknown names) and 1000 `zone_index.is_authoritative()` calls run 0 SQL statements (count with `sqlalchemy.event.listen(db.engine, "before_cursor_execute", ...)`); after `invalidate()` the next call reloads (pos); revocation is visible right after `invalidate_keys()` (pos) and, without invalidate, after max_age (patch the clock).
- touch: sets last_used_at; a second touch within 60 s writes nothing (count SQL).
- U3 zones: ACME Domains `example.com` and `*.corp.example.net` → authoritative: `example.com.`, `corp.example.net.`, `example.net.` (ancestor) (pos); not authoritative: `foo.example.com.` (descendant), `other.org.`, `net.` (TLD), `.` (root) (neg).
- N12/N7: 1000 `record()` calls with reason `badkey` from 1000 random IPs within one minute → at most 20 audit rows + 1 summary row after the window moves (patch the clock) (neg on flooding); 100 calls from one IP → 1 row (N7); first call → 1 row (pos).
- N13: the written audit row has `ip_address` = the peer IP and username `dns-update:<keyname>` / `dns-update:unauthenticated`; a 300-char keyname with control characters and non-ASCII is stored truncated to 255 with `?` replacements (neg); `log_action` without `ip_address` keeps the old behaviour (run the existing audit tests).
- N11: run the tests of this file with `caplog` at DEBUG and assert that no test secret (raw/base64) appears in the captured logs.
Run also the existing audit tests (`grep -l log_action backend/tests/*.py` and `tests/test_audit*.py`) to prove the `ip_address` change breaks nothing.

## Report
Files, public API as implemented, test names mapped to IDs, full test results, deviations with reasons.
````

## Część 5b: handler protokołu

Narzędzie: Agent, agent: `implementer`.

````text
Implement the protocol handler of the DNS UPDATE (RFC 2136) + TSIG (RFC 8945) listener in UCM: a pure function from request bytes to response bytes, no sockets. Work ONLY in the git worktree /home/user/ucm-dns-update (branch `claude/relaxed-planck-c6xvuc-dns-update`). Do NOT commit or push. Venv: /home/user/ultimate-ca-manager/.venv. Run tests from /home/user/ucm-dns-update/backend with `/home/user/ultimate-ca-manager/.venv/bin/python -m pytest <files> -q -p no:cacheprovider`. Nobody else edits the worktree now. Do not change the behaviour of the already reviewed modules `tsig.py`, `records.py`, `keys.py`, `zones.py` (you may add to `constants.py`, and add ONE method to `audit.py` as described below).

Read first, carefully: the plan `docs/development/acme-proxy-dns-update/plan.pl.md` (Polish) sections 2.3, 2.4, 3 (the whole processing order, steps 1–11), 3.1, 3.2, 4.1, 4.3, 4.4, 4.6, 5 (decisions), 9 (client behaviour), 11. RFC texts (clean copies) in /tmp/claude-0/-home-user-ultimate-ca-manager/5d252c34-87db-550d-aac1-9cb612323145/scratchpad/rfc/: rfc2136 §2–§3, rfc1035 §4.1.1/§4.2, rfc6891 §6.1.1/§6.1.3/§7, rfc9619, rfc8906 §3, §7, rfc2308 §2.2/§3, rfc3007 §2–§3. Existing modules in `backend/services/acme/dns_update/`: `tsig.py` (verify_request, render_*), `records.py` (get_active_snapshot → ActiveSnapshot(by_name, zones), ActiveRecord fields, mark_confirmed), `keys.py` (key_store.lookup/scope/touch, KeyScope.allows), `zones.py` (zone_index.is_authoritative), `audit.py` (audit_sink.record, sanitize_text), `constants.py`. Read them before you write code. dnspython 2.8.0 source is in the venv (`dns/message.py`, `dns/update.py`): check how an UpdateMessage exposes the zone, prerequisite and update sections and how a delete is represented (`rrset.deleting`).

## Module: backend/services/acme/dns_update/handler.py
```python
class DnsUpdateHandler:
    def __init__(self, *, key_store=keys.key_store, zone_index=zones.zone_index,
                 audit=audit.audit_sink, snapshot_fn=records.get_active_snapshot,
                 mark_confirmed_fn=records.mark_confirmed, clock=time.time,
                 watermark: Optional[TimeWatermark] = None, replay_cache=None, log_sampler=None): ...
    def handle(self, wire: bytes, peer_ip: str, transport: str) -> Optional[bytes]:
        # transport is 'udp' or 'tcp'. Returns the response bytes, or None for "no response".
        # Must be called inside a Flask app context (the server provides it). Never raises.
```
Add to `constants.py`: `MAX_MESSAGE_SIZE = 4096`, `MAX_QDCOUNT = 16`, `MAX_ANCOUNT = 16`, `MAX_NSCOUNT = 16`, `MAX_ARCOUNT = 4`, `REPLAY_CACHE_SIZE = 4096`, `REPLAY_TTL_S = 300`, `SOA_TIMERS = (1, 3600, 600, 86400, 0)` (serial, refresh, retry, expire, minimum), `CHALLENGE_LABEL = b'_acme-challenge'`.

### Exact processing order (plan §3). Every number below has tests.
1. `len(wire) < 12` → None (M2). QR bit set → None (M1).
2. `len(wire) > MAX_MESSAGE_SIZE` or QDCOUNT > MAX_QDCOUNT or ANCOUNT > MAX_ANCOUNT or NSCOUNT > MAX_NSCOUNT or ARCOUNT > MAX_ARCOUNT → None (N9). Read the counts from the raw header with struct, before parsing.
3. Opcode not QUERY (0) and not UPDATE (5) → NOTIMP: header only (ID copied, QR=1, opcode copied, RD copied, RCODE NOTIMP, all counts 0). No parsing beyond the header, no TSIG (decision 11) (M3).
4. Parse `dns.message.from_wire(wire, keyring=False)`. Any exception (dns.exception.DNSException and subclasses, ValueError, TypeError, IndexError, struct.error, UnicodeError) → FORMERR: header only (ID, opcode, RD copied, QR=1, RCODE FORMERR, counts 0), no TSIG (M4, S1, E2). Do not use the parsed message after a failure.
5. TSIG: `result = tsig.verify_request(wire, msg, self._key_store.lookup, now_int, self._watermark)`:
   - FORMERR → FORMERR header-only as in step 4.
   - BADKEY / BADSIG → `tsig.render_unsigned_tsig_error(skeleton, result, dns.rcode.BADKEY/BADSIG)`.
   - BADTIME → `tsig.render_badtime(skeleton, result, now_int)`. BADTRUNC → `tsig.render_badtrunc(...)`.
   - These 4 are audited through `audit.record(...)` with reason `badkey|badsig|badtime|badtrunc`, keyname = request key name text.
   - OK or UNSIGNED → continue.
   The skeleton is `dns.message.make_response(msg, pad=0)`; for UPDATE clear the zone section so all section counts are 0 (RFC 2136 §3.8 allows zeros; never echo the update/prereq sections). For QUERY keep the question.
6. Replay (S15): for OK requests, key = (transport, sha256(wire)). If the replay cache has a non-expired entry → return the cached response bytes with NO side effects (no DB write, no audit, no touch). The cache is a bounded LRU (REPLAY_CACHE_SIZE) with TTL REPLAY_TTL_S, thread-safe. Store the final bytes of every OK request after rendering.
7. EDNS version > 0 → BADVERS: skeleton (make_response gives an OPT of version 0) with `set_rcode(dns.rcode.BADVERS)`; signed if OK (E3).
8. QUERY → section "QUERY" below; UPDATE → section "UPDATE" below. Both produce a response Message plus an "event" (for side effects/audit).
9. Flags: QR=1, ID and opcode copied, RD copied, RA never set, Z=0, no PADDING (`make_response(..., pad=0)`), AD/CD not set (M6–M8, E4, E5). OPT only if the request had one (E1; make_response does this — test it).
10. Rendering and size (T1/T2, S12):
    - OK requests: `tsig.render_signed(resp, result, now_int, max_size=limit)` where for UDP `limit = max(512, msg.payload if msg.edns >= 0 else 512)` and for TCP `limit = None`.
    - Everything else (UNSIGNED, and the step-3/4/5 error responses): render `resp.to_wire(max_size=65535)`. For UDP the limit is `min(len(wire), max(512, payload))`: if the response is longer, replace it by the truncated form (copy of the response, answer/authority/additional cleared, TC set, same RCODE, OPT kept) and if that is still longer than the limit → None. Also apply this UDP limit to the TSIG-error responses of step 5 (BADKEY/BADSIG are unverified; BADTIME/BADTRUNC are signed — for those use the signed limit of the OK case).
    - TCP: no size limit.
11. Side effects and audit AFTER the response is decided (plan step 11): `mark_confirmed_fn`, `key_store.touch`, audit, sampled app log.
12. Any unexpected exception anywhere → SERVFAIL header-only if ID/opcode can be read, else None; log the exception TYPE only (sampled); `db.session.rollback()` in a try (N10).

### QUERY (plan §3.1)
- `len(msg.question) != 1` → FORMERR (RFC 9619; keep the response header-only).
- QCLASS ≠ IN → REFUSED (Q4); QTYPE ≠ SOA → REFUSED (Q3, Q5 — includes AXFR, IXFR, ANY, TXT, A, NS).
- Candidate rows W: from `snapshot_fn()` (`by_name` values). Unsigned: all rows. OK (signed): only rows where `key_store.scope(result.key.key_id).allows(row.acme_client_account_id, row.account_id)` (scope None → no rows).
- QNAME (case-insensitive, absolute) equal to `row.zone_name` of some row in W → NOERROR, AA=1, ANSWER = one SOA RR owned by that zone (Q1).
- else QNAME is a proper subdomain of some row's `zone_name` AND that row's `record_name` is a subdomain of (or equal to) QNAME → NOERROR, AA=1, empty ANSWER, AUTHORITY = SOA of that zone (NODATA, RFC 2308 §2.2, §3) (Q7).
- else REFUSED (Q3).
- SOA RR: owner = zone, TTL 0, class IN, RDATA `MNAME=zone, RNAME=hostmaster.<zone>, SERIAL/REFRESH/RETRY/EXPIRE/MINIMUM = SOA_TIMERS` (decision 13; no hostname, no time).
- No audit for queries. Sampled app log at DEBUG only.

### UPDATE (plan §3.2, RFC 2136 §3 order)
1. UNSIGNED → REFUSED immediately, before any zone check (U4, decision 10). App log only (sampled), no audit, no DB access at all.
2. Zone section: count ≠ 1 or ZTYPE ≠ SOA → FORMERR (U1). ZCLASS ≠ IN → NOTAUTH (U2). `not zone_index.is_authoritative(zname)` → NOTAUTH (U3).
3. Prerequisite section non-empty → REFUSED (U5).
4. Permission, for every RR of the update section, before applying anything (RFC 2136 §3.3, RFC 3007 §3):
   - type must be TXT and the first label of the owner name must equal `_acme-challenge` (case-insensitive), else REFUSED (U9). A delete of class ANY with type ANY ("delete all RRsets") → REFUSED (U11). Meta types (ANY, AXFR, IXFR, MAILA, MAILB, OPT, TSIG, TKEY) are refused here (REFUSED, permission comes before prescan in RFC 2136 order).
   - add (class IN): every rdata value = `b''.join(rdata.strings)` decoded as ASCII (non-ASCII → REFUSED) must match a row in `snapshot.by_name[canonical owner text]` with the same `txt_value` AND `scope.allows(row.acme_client_account_id, row.account_id)`; collect the matching row ids. No row at that name in scope → REFUSED with reason `no_pending_order`; rows exist in scope but no value matches → REFUSED with reason `value_mismatch` (U10, K6, R5).
   - delete (class ANY with type TXT, or class NONE with type TXT): permitted without a row (U11; "Always answer NOERROR, even when the order is gone").
5. Prescan (RFC 2136 §3.4.1): owner name not a subdomain of ZNAME (or equal) → NOTZONE (U7); class not in {IN, ANY, NONE} → FORMERR (U6, probably already rejected by the parser — test it anyway); deletes (ANY/NONE) with TTL ≠ 0 → FORMERR (U8).
6. Apply: nothing in DNS. `mark_confirmed_fn(row_ids, now)`; `key_store.touch(key_id, now)` (U15). Duplicate adds are fine (U13).
7. Response: NOERROR, all counts 0 (U14).
8. Audit (N6, N13): accepted UPDATE → write through a NEW method you add to `audit.py`: `AuditSink.record_authenticated(*, action, peer_ip, keyname, success, details)` — same sanitizing and `AuditService.log_action(..., ip_address=peer_ip)` call as `_write`, but NO rate limit (the request carries a verified TSIG; replays are absorbed by the replay cache). Use `action='acme.dns_update.accepted'`, details: zone, record names, number of adds/deletes, transport. Refusals of OK (signed) requests (REFUSED/NOTAUTH/NOTZONE/FORMERR after step 5) → `audit.record(action='acme.dns_update.refused', reason=<value_mismatch|no_pending_order|not_authoritative|not_in_zone|prerequisite|type_not_allowed|format>, ...)` (rate-limited). Never put TXT values, MACs or secrets in audit details or logs (only names, counts and reason codes).

### Sampled application log
A small `LogSampler` in handler.py: at most one line per reason per 10 s, plus counters (`counts()` returns a dict). Reasons include `short`, `qr`, `oversize`, `counts`, `notimp`, `formerr`, `unsigned_update`, `badkey`, `badsig`, `badtime`, `badtrunc`, `servfail`, `udp_drop`. Never log packet bytes, MACs, TXT values or keys.

## Tests: backend/tests/test_dns_update_handler.py
Every invariant: `test_<ID>_<what>_pos` and `_neg`; the negative test changes exactly one thing that violates the invariant, and also checks the absence of side effects where relevant (no `mark_confirmed` call, no audit row, no `touch`, no TSIG in the response). Use fakes for unit tests: a dict-backed key store (`lookup`, `scope`, `touch` recording calls), a zone index fake, a snapshot function returning a fixed `ActiveSnapshot`, a fake audit sink recording calls, a fixed clock. Build requests with dnspython as an independent client (`dns.update.UpdateMessage`, `dns.message.make_query`, `use_tsig`, `use_edns`). Parse responses with dnspython; verify signed responses with dnspython as a client (keyring + request_mac). Required coverage (IDs from plan §4):
- M1–M8 (incl. opcodes 1,2,4,6,15 → NOTIMP header-only; truncated RR, trailing junk, bad label → FORMERR; QDCOUNT 0 and 2 → FORMERR; Z bit and AD set → not echoed; RD copied, RA 0; ID echoed for 100 random IDs).
- E1–E5 (OPT echo / no OPT; two OPT → FORMERR; version 1 → BADVERS with OPT version 0; unknown option and flag ignored and not echoed; PADDING request → no padding, response not longer than request).
- T1/T2 at handler level: unsigned SOA answer over UDP longer than the request → TC=1, no answer/authority, length ≤ request; same over TCP → full answer; signed SOA query over UDP without EDNS (nsupdate pattern) → full signed answer ≤ 512; signed response larger than 512 without EDNS → TC with TSIG, verifiable.
- Q1–Q7 incl. the client patterns from plan §9: nsupdate (signed SOA query for `_acme-challenge.app.example.com.` over UDP, no EDNS → NODATA with SOA(example.com.) in AUTHORITY, signed); certbot (unsigned queries walking `_acme-challenge.app.example.com.`, `app.example.com.`, `example.com.` over TCP → NODATA, NODATA, then SOA in ANSWER with AA=1 and owner == QNAME); lego (unsigned UDP, EDNS 4096 → TC → TCP retry works); signed SOA for a row of another proxy account → REFUSED (signed); unsigned SOA for a name without rows → REFUSED; SOA RDATA has exactly the fixed values.
- U1–U15 incl. client shapes: cert-manager (zone = example.com. while the record is `_acme-challenge.app.example.com.`, add TTL 60, delete class NONE), lego ([class ANY TXT delete, add] in ONE message → NOERROR; [delete, add wrong value] → REFUSED and no mark_confirmed), acme.sh/nsupdate (add TTL 60; delete `update delete name TXT` → class ANY TXT), certbot (zone == the zone from SOA discovery, add TTL 120, delete class NONE), win-acme (ZNAME = registrable domain ancestor → NOERROR; ZNAME `other.org.` → NOTAUTH). Unsigned UPDATE for a zone in ACME Domains and for a foreign zone → byte-identical responses except the ID, and the fakes record zero calls (U4/F6). Each of the 5 prerequisite forms (RFC 2136 §2.4.1–§2.4.5) → REFUSED. Delete of a record whose order is gone (no rows) → NOERROR. TXT value split into two character-strings that join to the expected value → NOERROR.
- S1 (TSIG not last / two TSIG → FORMERR unsigned), S10 (every response to an OK request verifies with dnspython; every response to an unsigned request has no TSIG), S15 (identical UDP retransmit → identical bytes, side effects once; different transport → separate entry).
- K6, R5: a new key with no rows → REFUSED; EAB-scoped key against a row of another ACME account → REFUSED.
- N5: patch `socket.socket.connect` and `socket.create_connection` to raise; run a full UPDATE + SOA flow → no call.
- N6: unsigned/malformed → no audit call; OK accepted → `record_authenticated` called once with the peer IP and keyname; signed refusal → `record` called with the reason.
- N8 (integration, real DB): seed a proxy account, a key, an AcmeDomain and an active challenge row (use the real models; see `tests/test_dns_update_records.py` and `tests/test_dns_update_keys_zones_audit.py` for seeding), warm the real caches, then run 1000 unsigned SOA queries and 1000 BADKEY UPDATEs through a handler with the REAL key_store/zone_index/snapshot (fresh instances) → 0 SQL statements (sqlalchemy before_cursor_execute counter). One end-to-end integration test with the real modules: signed add for the real row → NOERROR and `client_confirmed_at` set in the DB.
- N10: snapshot_fn raising → SERVFAIL; the next request → normal answer.
- N11: caplog at DEBUG over the whole handler test module contains no test secret (base64/raw), no MAC (hex/base64) and no TXT value.

## Validation
- New tests green; also rerun `tests/test_dns_update_*.py` and `tests/test_acme_proxy*.py`.
- pyflakes clean on the new/changed files.
- Report: files, how each processing step maps to code, test names mapped to IDs, deviations from this spec with reasons, and any dnspython behaviour that differed from what the spec assumes.
````

## Część 7: API kluczy i ustawienie portu

Narzędzie: Agent, agent: `implementer`.

````text
Implement the REST API for the TSIG keys of the DNS UPDATE (RFC 2136) listener in UCM, the port setting, and cache invalidation hooks. Work ONLY in the git worktree /home/user/ucm-dns-update-api (local branch `tmp/dns-update-api`). Do NOT push. When done and green, COMMIT once in that worktree with `git -c user.name=WMP -c user.email=45381+WMP@users.noreply.github.com commit -m "feat(acme): add API for DNS UPDATE keys and listener port" -m "<2-4 line body>"` (no Co-authored-by trailer). Venv: /home/user/ultimate-ca-manager/.venv. Run tests from /home/user/ucm-dns-update-api/backend with `/home/user/ultimate-ca-manager/.venv/bin/python -m pytest <files> -q -p no:cacheprovider`. Do not touch `backend/services/acme/dns_update/` except creating the new file `status.py` described below.

Read first: plan `docs/development/acme-proxy-dns-update/plan.pl.md` (Polish) sections 2.1, 2.3, 4.5 (K1–K9), 4.6 (N1, N2), 7 (API). Existing code to follow: `backend/api/v2/acme/eab.py` (create with secret shown once, list/get without secret, DELETE = revoke active / delete revoked, audit calls, `require_auth`, `success_response`/`error_response`/`no_content_response`, `safe_commit`), `backend/api/v2/acme_client/accounts.py` and `backend/api/v2/acme_client/__init__.py` (blueprint `acme_client`, how route modules are imported), `backend/api/v2/acme_client/settings.py` (GET/PATCH `/api/v2/acme/client/settings`, `acme.client.tls_alpn_port` validation and `_set_config`), `backend/api/v2/settings/general.py` (~L250-270: `http_protocol_port` validation 0 or 1024..65535, conflict with `Config.HTTPS_PORT`; check whether it triggers a restart or just says a restart is needed, and do the same), `backend/protocol_http_server.py` `get_http_protocol_port()` (env var first, then DB, invalid → 0 + warning), models `backend/models/acme_dns_update.py` (`AcmeDnsUpdateKey.normalize_name`, `secret` setter, `to_dict`), `backend/services/acme/dns_update/tsig.py` (`generate_secret`), `keys.py` (`invalidate_keys`), `zones.py` (`zone_index.invalidate()`), `backend/api/v2/acme_domains.py` (AcmeDomain create/update/delete routes), `backend/services/acme/acme_proxy_account.py` (slug helpers).

## 1. Routes: new module `backend/api/v2/acme_client/dns_update_keys.py` (register like the other acme_client route modules)
- `GET /api/v2/acme/client/accounts/<int:account_id>/dns-update-keys` — `read:acme`. 404 if the account does not exist. Returns `[key.to_dict() ...]` (never the secret) (K3).
- `POST /api/v2/acme/client/accounts/<int:account_id>/dns-update-keys` — `write:acme`. JSON body: `name` (optional), `algorithm` (optional, default `hmac-sha256`; allowed exactly `hmac-sha256`, `hmac-sha384`, `hmac-sha512`, case-insensitive; anything else, incl. hmac-md5, hmac-sha1, hmac-sha224, truncated variants → 400 (K4); the same set applies in FIPS mode, md5 is never allowed), `eab_credential_id` (optional int: must exist and not be `revoked` → else 400), `notes` (optional, ≤ 1000 chars).
  - Name: if given → `AcmeDnsUpdateKey.normalize_name` (ValueError → 400). If absent → generate `f"{base}-{secrets.token_hex(4)}."` where `base` is the account's `proxy_slug` or `f"proxy{account_id}"`, then normalize. Case-insensitive duplicate → 409 (K5).
  - Secret: `raw = tsig.generate_secret(dns.name.from_text(algorithm))`; store `base64.b64encode(raw)` through the model setter (K1, K2).
  - 201 response: `to_dict()` plus `secret` (standard base64) — the ONLY time the secret is returned (K3). Message like the EAB create.
  - Audit `acme.dns_update.key.create` with resource_type `acme_dns_update_key`, resource_name = key name, details without the secret.
  - After commit: `invalidate_keys()`.
- `DELETE /api/v2/acme/client/accounts/<int:account_id>/dns-update-keys/<int:key_id>` — `delete:acme`. 404 if the key does not belong to that account. Active → `status='revoked'`, `revoked_at=now` (200 with to_dict); revoked → hard delete (204). Audit `acme.dns_update.key.revoke` / `.delete`. After commit: `invalidate_keys()`.
- Never log or audit the secret.

## 2. Port setting
- SystemConfig key `acme.proxy.dns_update_port` (int, default 0 = disabled). Env var `UCM_DNS_UPDATE_PORT` overrides it. Add `backend/services/acme/dns_update/status.py` with:
  - `get_dns_update_port() -> int`: env var first (invalid → 0 + one warning), then the DB setting (invalid or out of 0..65535 → 0), then 0. Same structure as `get_http_protocol_port()`.
  - `get_dns_update_host() -> str`: env `UCM_DNS_UPDATE_HOST`, else the same bind host as the HTTP protocol server (`listen_address.get_bind_host()` or whatever `protocol_http_server` uses).
  - `set_listening(bool)` / `is_listening() -> bool` (module-level flag, set later by the server).
- `GET /api/v2/acme/client/settings`: add `dns_update_port` (stored value), `dns_update_port_env` (env value or null), `dns_update_listening` (`is_listening()`).
- `PATCH /api/v2/acme/client/settings`: accept `dns_update_port`: int 0 or 1024..65535 (N2: below 1024 → 400 because UCM runs without CAP_NET_BIND_SERVICE), not equal to `Config.HTTPS_PORT` nor to the effective HTTP protocol port → 400. Save with the existing `_set_config` helper. Response says that a restart is needed for the change, the same way the HTTP protocol port does (follow that code exactly). Audit as the other client-settings changes.

## 3. Cache invalidation hooks (minimal edits)
- `backend/api/v2/acme/eab.py` DELETE handler: after a successful commit call `invalidate_keys()` (keys linked to the credential were deleted in the same transaction already).
- `backend/api/v2/acme_client/accounts.py`: after any successful commit that deletes an account, or changes `proxy_enabled`/`proxy_slug`, call `invalidate_keys()`.
- `backend/api/v2/acme_domains.py`: after any successful commit that creates/updates/deletes an `AcmeDomain`, call `zone_index.invalidate()`.
Import lazily inside the functions to avoid import cycles if needed.

## 4. Tests: `backend/tests/test_dns_update_api.py`
`test_<ID>_<what>_pos` / `_neg` pairs, the negative test changes one thing. Use the `auth_client` (admin) and `viewer_client` fixtures from conftest; seed a proxy CA account like `tests/test_acme_proxy_ca_account.py`.
- K1: POST for each algorithm → base64 secret decodes to 32/48/64 bytes (pos); 20 created keys have 20 different secrets (neg on reuse).
- K3: POST returns `secret`; GET list never contains a `secret` key or the secret value (neg).
- K4: 3 allowed algorithms → 201; `hmac-md5`, `hmac-sha1`, `hmac-sha224`, `hmac-sha256-128`, `gss-tsig` → 400 (each).
- K5: invalid names (64-byte label, `a..b`, `.`) → 400; `Key.Example.` after `key.example.` → 409; no name → generated name starting with the slug.
- EAB link: nonexistent id → 400; revoked credential → 400; active/used credential → 201 with `eab_credential_id`.
- Permissions: viewer POST/DELETE → 403; viewer GET → 200 (if viewers have read:acme; otherwise assert what the existing EAB tests assert for viewers).
- DELETE: active → revoked (200), then → deleted (204); key of another account → 404.
- Invalidation (integration): after DELETE (revoke), `keys.key_store.lookup(name)` returns None at once (no wait for the cache age); after POST, lookup finds the key; after changing `proxy_enabled` to false through the accounts API, lookup returns None; after deleting an AcmeDomain through its API, `zones.zone_index.is_authoritative` turns False at once.
- N1: `get_dns_update_port()` with env `8053` → 8053; env `abc` → 0 (+warning); no env, DB `8053` → 8053; nothing → 0.
- N2: PATCH 8053 → 200; 0 → 200; 53, 1023, 70000, the HTTPS port, the HTTP protocol port, `"abc"` → 400.
- No secret in logs: caplog at DEBUG during a POST does not contain the returned secret.
Also run the existing tests for EAB, accounts, acme_domains and client settings (find them with grep) and `tests/test_dns_update_*.py`.

## Report
Files, routes, test names mapped to IDs, results, deviations with reasons, and the commit hash.
````

## Część 6: serwer UDP/TCP

Narzędzie: Agent, agent: `implementer`.

````text
Implement the network server of the DNS UPDATE (RFC 2136) listener in UCM and wire it into startup. Work ONLY in the git worktree /home/user/ucm-dns-update-server (local branch `tmp/dns-update-server`). When done and green, COMMIT once there with `git -c user.name=WMP -c user.email=45381+WMP@users.noreply.github.com commit -m "feat(acme): add the UDP/TCP server of the DNS UPDATE listener" -m "<2-4 line body>"` (no Co-authored-by trailer). Do NOT push. Venv: /home/user/ultimate-ca-manager/.venv. Run tests from /home/user/ucm-dns-update-server/backend with `/home/user/ultimate-ca-manager/.venv/bin/python -m pytest <files> -q -p no:cacheprovider`.

Read first: plan `docs/development/acme-proxy-dns-update/plan.pl.md` (Polish) sections 2.4 (resource limits — the table is the spec), 3 step 1, 4.1 (T3, T4, T5), 4.6 (N1, N3, N4, N9, N10), 7 (startup), 11 (F1, F8). RFC 1035 §4.2.1/§4.2.2 and RFC 7766 §6.2.1–§6.2.4, §8 (clean copies in /tmp/claude-0/-home-user-ultimate-ca-manager/5d252c34-87db-550d-aac1-9cb612323145/scratchpad/rfc/). Existing code: `backend/services/acme/dns_update/handler.py` (`DnsUpdateHandler.handle(wire, peer_ip, transport)` → bytes or None, never raises, needs a Flask app context), `status.py` (`get_dns_update_port`, `get_dns_update_host`, `set_listening`), `constants.py` (`MAX_MESSAGE_SIZE`), `backend/protocol_http_server.py` (`start_http_protocol_server` pattern: port ≤ 0 → None, OSError on bind → log error, return None, never raise), `backend/gunicorn_config.py` (`post_worker_init`, gevent worker, `workers = 1`, `monkey.patch_all()`), `backend/app.py` `main()` (~L1874-1886 dev path starting the protocol server), `backend/listen_address.py` (bind host helpers, IPv4-mapped IPv6 normalization — reuse the existing normalization helper for peer IPs), tests `backend/tests/test_listen_address.py` (how a gevent server runs in a thread in tests; the test process is NOT monkey-patched) and `backend/tests/test_gunicorn_control_socket.py` (gunicorn_config is checked with `ast`, never imported).

## Module backend/services/acme/dns_update/server.py
```python
@dataclass(frozen=True)
class ServerLimits:
    udp_pool: int = 16
    tcp_pool: int = 32
    tcp_per_ip: int = 8
    global_rate: float = 200.0      # packets per second, all sources
    global_burst: int = 400
    per_ip_rate: float = 50.0       # packets per second per source IP
    per_ip_burst: int = 100
    per_ip_table: int = 4096        # bounded LRU of per-IP buckets
    tcp_idle_s: float = 10.0        # RFC 7766 §6.2.3, reset only on a FULL message
    tcp_write_s: float = 10.0
    tcp_lifetime_s: float = 120.0

class DnsUpdateServer:
    def __init__(self, app, host: str, port: int, handler=None, limits=ServerLimits(), clock=time.monotonic): ...
    def start(self) -> bool       # binds UDP and TCP on (host, port); OSError → log error, stop what started, return False (N3). Sets status.set_listening(True) on success.
    def stop(self) -> None        # stops both, set_listening(False)
    @property
    def port(self) -> int         # the bound port (useful with port 0 in tests)
def start_dns_update_server(app) -> Optional[DnsUpdateServer]
    # reads get_dns_update_port()/get_dns_update_host() inside app.app_context(); port ≤ 0 → None (disabled, N1);
    # creates DnsUpdateHandler() and the server; returns it or None; never raises; keeps a module-level reference.
```
- Use gevent: `gevent.server.DatagramServer` (UDP) and `gevent.server.StreamServer` (TCP), each with `spawn=gevent.pool.Pool(n)`. Bind UDP and TCP to the SAME port; with port 0 (tests) bind TCP first, then UDP to the port TCP got.
- Rate limiting (before any parsing, plan 2.4, F1): a global token bucket and a per-IP token bucket table (bounded LRU `per_ip_table`), applied to every UDP datagram and every TCP message. Over the limit → drop silently (no response) and count it (a sampled log line, at most one per 10 s; never log packet bytes).
- UDP handler: normalize the peer IP; rate limit; `with app.app_context(): out = handler.handle(data, ip, 'udp')`; `sendto` if out is not None. Any exception → log type only, continue.
- TCP handler (RFC 1035 §4.2.2, RFC 7766): per-IP concurrent connection cap `tcp_per_ip` (over the cap → close at once); loop: read the 2-byte length and then exactly that many bytes, allowing the data to arrive in several segments (RFC 7766 §8: never close just because one read is short); the idle timeout `tcp_idle_s` counts from the last COMPLETE message (a slow partial message is cut when the idle time since the last full message is exceeded — slow-read protection); length 0 or > MAX_MESSAGE_SIZE → close without a response; rate limit per message; handle with transport 'tcp'; if the handler returns None → close the connection; else send `len(out).to_bytes(2,'big') + out` in ONE `sendall` with a `tcp_write_s` timeout (RFC 7766 §8); several messages per connection are processed in order (pipelining, RFC 7766 §6.2.1); the connection is closed after `tcp_lifetime_s` at the latest; the peer closing is normal; always close the socket and release the per-IP slot in `finally`.
- Logging: module logger, sampled, no packet bytes, no secrets.

## Startup wiring
- `backend/gunicorn_config.py` `post_worker_init`: after the HTTP protocol server, in its own try/except (same pattern, logger 'ucm.protocol'), `from services.acme.dns_update.server import start_dns_update_server; with flask_app.app_context(): start_dns_update_server(flask_app)`.
- `backend/app.py` dev `main()`: start the listener the same way as the dev HTTP protocol server, if a port is configured (gevent servers can run `serve_forever()` in a daemon thread; check that this works without monkey patching, as the existing tests do with WSGIServer).
- No other startup path exists (systemd units and start-ucm.sh exec gunicorn).

## Tests: backend/tests/test_dns_update_server.py
Run the real server on 127.0.0.1 port 0 in a thread (see test_listen_address.py), with a FAKE handler (records calls, returns configurable bytes) for most tests and the REAL handler in one smoke test (inside the test app; seed a key/AcmeDomain/row like tests/test_dns_update_handler.py's integration tests, or just check that an unsigned SOA query for an unknown name gets REFUSED over UDP and TCP). Use small limits/timeouts via ServerLimits in tests. Every invariant has `_pos`/`_neg`:
- T3: two pipelined messages in one TCP connection → two responses in order (pos); length prefix and body sent in separate segments with a pause shorter than idle → answered (pos); length 0 → connection closed, no response (neg); length MAX_MESSAGE_SIZE+1 → closed, no response, the body is never read in full (neg).
- T5: messages every 0.2 s with tcp_idle_s=0.5 for 2 s → connection stays open (pos); half a message then silence > tcp_idle_s → closed (neg); a connection is closed after tcp_lifetime_s even if active (neg).
- UDP: a datagram is answered (pos); handler returning None → no datagram back (neg); MAX_MESSAGE_SIZE+1 datagram → the handler still decides (it is the handler's job; assert it was called with the full datagram or document the gevent buffer size — make sure the UDP receive buffer is at least MAX_MESSAGE_SIZE+1 so oversize datagrams are seen and dropped by the handler, not silently truncated into a valid-looking message).
- N3: binding a port already in use → start() returns False, no exception, status.is_listening() False (neg); free port → True and is_listening() True (pos); stop() → is_listening() False.
- N1: start_dns_update_server with port 0 configured → None, nothing bound (neg); with env UCM_DNS_UPDATE_PORT set to a free port → server running (pos).
- N4: with global_rate=5, burst=5: 50 fast UDP queries → between 5 and 10 answered (neg); slow traffic under the limit → all answered (pos); per-IP table never grows beyond per_ip_table (simulate many IPs by calling the limiter directly); TCP per-IP cap: cap+1 concurrent connections from 127.0.0.1 → the extra one is closed at once (neg), cap connections all work (pos).
- N10: a handler that raises → the server logs and keeps serving the next datagram/connection (neg on crash).
- F8: the server binds the host given by get_dns_update_host (test with UCM_DNS_UPDATE_HOST=127.0.0.1 vs default).
- Startup wiring: parse gunicorn_config.py with `ast` and assert that post_worker_init calls start_dns_update_server inside a try (pos); and that the HTTP protocol server call is still there (neg on regression).
Also run `tests/test_dns_update_*.py`, `tests/test_listen_address.py`, `tests/test_gunicorn_*.py`.

## Report
Files, design notes (how backpressure works with the pools), test names mapped to IDs, results, deviations with reasons, commit hash.
````

## Część 8: interfejs, pomoc, tłumaczenia

Narzędzie: Agent, agent: `implementer`.

````text
Implement the web UI, contextual help and translations for the DNS UPDATE (RFC 2136) listener of UCM's ACME proxy. Work ONLY in the git worktree /home/user/ucm-dns-update-ui (local branch `tmp/dns-update-ui`). When done and green, COMMIT once there with `git -c user.name=WMP -c user.email=45381+WMP@users.noreply.github.com commit -m "feat(acme): add UI for DNS UPDATE keys and listener port" -m "<2-4 line body>"` (no Co-authored-by trailer). Do NOT push. Frontend: `cd /home/user/ucm-dns-update-ui/frontend && npm ci` first (the npm registry is reachable), then `npx vitest run <files>`, `npm run check:i18n`, `npm run lint` (on changed files if the full lint is slow) and `npx vite build` at the end. Do not change backend code.

Read first: plan `docs/development/acme-proxy-dns-update/plan.pl.md` (Polish) sections 7 (UI), 9 (client behaviour and "Wnioski dla dokumentacji": default algorithms md5/sha1 that UCM rejects, win-acme port bug, Posh-ACME needs DDNSNameserver, cert-manager zone discovery). Backend API (already implemented, read the code): `backend/api/v2/acme_client/dns_update_keys.py` (GET/POST `/api/v2/acme/client/accounts/<id>/dns-update-keys`, DELETE `/.../<key_id>`; POST returns `secret` once; algorithms hmac-sha256/384/512; optional `name`, `eab_credential_id`, `notes`) and `backend/api/v2/acme_client/settings.py` (`dns_update_port`, `dns_update_port_env`, `dns_update_listening`; PATCH `dns_update_port` 0 or 1024–65535; response `data.restart_required`). Existing UI to follow closely (same components, styles, patterns, i18n usage): `frontend/src/pages/acme/CaAccountsManager.jsx` (proxy toggle + slug per CA account), `frontend/src/pages/acme/EabTab.jsx` (create modal; "secret shown once" modal with warning and copy buttons, L419-504), `frontend/src/pages/acme/LetsEncryptTab.jsx` (proxy section, `tls_alpn_port` field ~L214-221), `frontend/src/services/acme.service.js` (EAB calls L56-90, CA account calls L131-162), `frontend/src/i18n/locales/{en,fr,de,es,it,pt,uk,zh,ja}.json` (`acme.*` namespace; key parity checked by `scripts/check-i18n-sync.js`), `frontend/src/data/helpContent.js` (acme section ~L573, structure {title, subtitle, overview, sections[{title, items[{label,text}]}], tips, warnings}), `frontend/src/data/helpGuides.js` (acme guide ~L876, Markdown, "ACME Proxy Mode" section ~L995-1077), `frontend/src/data/help/{de,es,fr,it,ja,pt,uk,zh}/acme.js` (translated helpContent + helpGuides). Existing frontend tests to imitate: `frontend/src/i18n/__tests__/systemLogsI18n.test.js` and any `*.test.jsx` near the ACME pages (grep).

## 1. Service calls (acme.service.js)
`listDnsUpdateKeys(accountId)`, `createDnsUpdateKey(accountId, body)`, `deleteDnsUpdateKey(accountId, keyId)`. The settings calls already exist; just send/read `dns_update_port`.

## 2. CA accounts: DNS UPDATE keys (CaAccountsManager.jsx)
For an account with "Expose via ACME proxy" on: a "DNS UPDATE keys (RFC 2136)" action that opens a panel/modal with the key list (name, algorithm, EAB credential link if any, created, last used, status) and actions Create, Revoke (active) / Delete (revoked), with the same confirmation style as EAB. Create dialog: name (optional, placeholder explains a name is generated), algorithm select (hmac-sha256 default, hmac-sha384, hmac-sha512 — with a hint that some clients do not support sha384: cert-manager supports HMACSHA256/HMACSHA512 only, win-acme computes sha384 wrongly), optional EAB credential select (list non-revoked EAB credentials through the existing service; explain: "limits the key to orders of the ACME account registered with this credential"), notes.
"Shown once" modal after create (same look as the EAB one, with the same kind of warning): key name, algorithm, secret, each with a copy button, plus ready-to-copy configuration snippets in tabs. Generate them from the response and the proxy directory URL the page already knows. VERIFY every option/variable name in the client sources under /tmp/claude-0/clientsrc/ before using it (do not invent names; report the file and line for each):
 - BIND key file for nsupdate / acme.sh (`NSUPDATE_KEY` points to it) / Posh-ACME: `key "<name>" {\n  algorithm <alg>;\n  secret "<secret>";\n};` — check the format nsupdate `-k` accepts in /tmp/claude-0/clientsrc/bind9/bin/nsupdate/nsupdate.c (`read_sessionkey`).
 - acme.sh: `NSUPDATE_SERVER`, `NSUPDATE_SERVER_PORT`, `NSUPDATE_KEY`, `NSUPDATE_ZONE` (acmesh/acme.sh/dnsapi/dns_nsupdate.sh) and `acme.sh --issue --dns dns_nsupdate --server <proxy directory> -d <domain> --dnssleep 30`.
 - cert-manager: a Secret with the TSIG secret and the `rfc2136` solver (`nameserver`, `tsigKeyName`, `tsigAlgorithm`, `tsigSecretSecretRef`) — check names and allowed algorithm values in the cert-manager v1.21.3 module under /tmp/claude-0/clientsrc/gomod/ (types_issuer.go, pkg/issuer/acme/dns/rfc2136). If the key algorithm is hmac-sha384 show a note that cert-manager cannot use it.
 - certbot-dns-rfc2136 credentials ini (pypi/rfc2136/certbot_dns_rfc2136/_internal/dns_rfc2136.py): server must be an IP address; algorithm in upper case (e.g. HMAC-SHA256); default algorithm is HMAC-MD5, so the snippet always sets it.
 - lego (`--dns rfc2136` and its env vars, gomod/.../go-acme/lego/v4@v4.35.2/providers/dns/rfc2136): default algorithm is hmac-sha1, so the snippet always sets it.
 - win-acme: `--validation rfc2136 --serverhost ... --tsigkeyname ... --tsigkeysecret ... --tsigkeyalgorithm ...` plus a note that win-acme always sends to port 53 (its `--serverport` is used as a timeout by its DNS library), so UCM must be reachable on port 53.
 - Posh-ACME: `-Plugin RFC2136 -PluginArgs @{DDNSNameserver=...; DDNSPort=...; DDNSKeyName=...; DDNSKeyType=...; DDNSKeyValue=(SecureString)...}` (Posh-ACME/Plugins/RFC2136.ps1) and a note that DDNSNameserver is required.
 Host in snippets: the UCM host from the page context (or a placeholder `ucm.example.com`), port: the configured `dns_update_port`, or 53 with a note "if you map port 53 to the listener".

## 3. Listener port (LetsEncryptTab.jsx, proxy section)
Field "DNS UPDATE listener port" (0 = disabled; 1024–65535), showing `dns_update_port_env` when the env var overrides it (field read-only then), a status badge from `dns_update_listening`, and a notice "restart UCM to apply" after saving when `restart_required`. Contextual helper text: the listener is for the internal network only; to use port 53 map it in Docker/Kubernetes or with a firewall redirect.

## 4. Help
- `helpContent.js` acme section: a new section "DNS UPDATE (RFC 2136) for the ACME proxy" with items: what it is (clients use their standard rfc2136 solver pointed at UCM; UCM still creates the TXT record through its DNS provider), keys per proxy account and optional EAB link, accepted changes (only TXT under `_acme-challenge` with the value UCM expects; deletes always answered NOERROR), port and internal network, algorithms (hmac-sha256/384/512; md5/sha1 refused, set the algorithm in every client), SOA discovery, client-side DNS checks still need a resolver that sees the public zone.
- `helpGuides.js` acme guide: a Markdown subsection after "ACME Proxy Mode" with step-by-step setup and the same client notes.
- Translate both into the 8 languages in `frontend/src/data/help/*/acme.js`, following how those files structure helpContent and helpGuides.

## 5. Translations
All new UI strings under `acme.dnsUpdate.*` in all 9 locale files (`npm run check:i18n` must pass). Write real translations (not English copies). Follow the existing style of each locale file (no em dashes if the existing locale test forbids them — check `systemLogsI18n.test.js`).

## 6. Tests (vitest)
- Key panel: renders the list from a mocked service; create flow calls the service with the selected algorithm/EAB and shows the secret once; after closing the modal the secret is no longer in the DOM (neg); revoke/delete call the right service function.
- Snippets: for a sha256 key the cert-manager snippet contains `HMACSHA256`, the certbot snippet `HMAC-SHA256` and the lego snippet the algorithm variable; for a sha384 key the cert-manager tab shows the "not supported" note (neg).
- Port field: rejects 53 and 70000 client-side (neg), accepts 0 and 8053 (pos); read-only when the env override is set.
- i18n: every new `acme.dnsUpdate.*` key exists in all 9 locales and is non-empty (pos), no em dash if the project forbids it (neg).

## Report
Files, screens added, the verification list (snippet option names with source file:line), test results (vitest, check:i18n, lint, build), deviations with reasons, commit hash.
````

## Część 9: pakiety, Helm, dokumentacja

Narzędzie: Agent, agent: `implementer`.

````text
Implement packaging, Helm chart and documentation for the DNS UPDATE (RFC 2136) listener of UCM's ACME proxy. Work ONLY in the git worktree /home/user/ucm-dns-update-pkg (local branch `tmp/dns-update-pkg`). When done and green, COMMIT once there with `git -c user.name=WMP -c user.email=45381+WMP@users.noreply.github.com commit -m "feat(acme): package and document the DNS UPDATE listener" -m "<2-4 line body>"` (no Co-authored-by trailer). Do NOT push. Do not change backend Python code or the frontend (other agents do that in parallel).

Read first: plan `docs/development/acme-proxy-dns-update/plan.pl.md` (Polish) sections 2.4, 5 (decisions), 6, 7 ("Pakiety", "Dokumentacja"), 9 (client behaviour, "Wnioski dla dokumentacji"), 11 (F8), and `docs/development/acme-proxy-dns-update/maintainer-requirements.md`. Backend facts (read the code, do not guess): settings and env vars in `backend/services/acme/dns_update/status.py` (`UCM_DNS_UPDATE_PORT`, `UCM_DNS_UPDATE_HOST`, setting `acme.proxy.dns_update_port`, 0 = disabled), API in `backend/api/v2/acme_client/dns_update_keys.py` and `backend/api/v2/acme_client/settings.py`, protocol behaviour in `backend/services/acme/dns_update/handler.py` (what is accepted, rcodes, SOA discovery, size limits), limits in `constants.py`. Packaging to extend: `Dockerfile` (EXPOSE L188-189, USER ucm), `docker/entrypoint.sh` (`validate_port()` L36-42, port defaults L161-162 and checks L196-205), `docker-compose.yml`, `charts/ucm/` (values.yaml service L90-94, securityContext L144-155, templates/service.yaml, templates/deployment.yaml containerPorts L46-52, README.md values table), `packaging/` and `debian/` (DO NOT change service units — the maintainer requires them unchanged), docs `docs/ADMIN_GUIDE.md` (ACME sections ~L506-560), `docs/API_REFERENCE.md`, `examples/kubernetes/cert-manager/` (README.md and existing ClusterIssuers), `CHANGELOG.md` (`## [Unreleased]`, CONTRIBUTING.md asks for one or two sentences).

## 1. Docker
- `Dockerfile`: `EXPOSE 8053/udp` and `EXPOSE 8053/tcp` next to the other EXPOSE lines, with a comment that the listener is off unless `UCM_DNS_UPDATE_PORT` (or the setting) is set.
- `docker/entrypoint.sh`: if `UCM_DNS_UPDATE_PORT` is set and not 0: it must be an integer in 1024..65535 (the image runs as the unprivileged user `ucm` without CAP_NET_BIND_SERVICE; give a clear error that says to map port 53 with `-p 53:8053/udp -p 53:8053/tcp` instead) and must differ from the HTTPS and HTTP ports already validated there; exit with an error otherwise, like the existing port checks. Keep the style of the script. Add a shell test if the repo has tests for entrypoint.sh (grep tests for entrypoint); otherwise test it manually with `bash -n` and a small ad-hoc run of the validation function, and say so in the report.
- `docker-compose.yml`: a commented example of the two port mappings and the env var (do not enable it).

## 2. Helm chart (charts/ucm)
- values.yaml: `dnsUpdate: { enabled: false, port: 8053, host: "", service: { type: ClusterIP, port: 53, annotations: {}, loadBalancerIP: "" }, networkPolicy: { enabled: false, from: [] } }` with comments: internal network only; separate Service so that exposing the HTTPS UI never exposes the listener.
- deployment.yaml: when enabled, env `UCM_DNS_UPDATE_PORT` (and `UCM_DNS_UPDATE_HOST` if set) and containerPorts `dns-udp`/`dns-tcp` (UDP and TCP) on `dnsUpdate.port`.
- New `templates/service-dns-update.yaml` (only when enabled): its own Service with UDP and TCP ports `dnsUpdate.service.port` → targetPort `dnsUpdate.port`, type from values (default ClusterIP), same selector labels as the main Service.
- New `templates/networkpolicy-dns-update.yaml` (only when both enabled): allows ingress to the listener ports only from `networkPolicy.from` (list of NetworkPolicy peers), as an additional policy (do not block other ports).
- README.md values table rows and a short "DNS UPDATE listener" section (mixed-protocol LoadBalancer support depends on the cloud; kube-proxy SNAT can hide client IPs).
- Validate: if `helm` is not installed, download a pinned helm release binary into /tmp/claude-0/helm (e.g. `curl -sSL https://get.helm.sh/helm-v3.16.3-linux-amd64.tar.gz`) and run `helm lint charts/ucm` and `helm template charts/ucm --set dnsUpdate.enabled=true --set dnsUpdate.networkPolicy.enabled=true` and the default `helm template charts/ucm` (no DNS objects). If the download is blocked, render with any existing chart test in the repo (grep `charts/` in tests) and say so.
- Check whether the repo bumps `Chart.yaml` version on chart changes (git log on charts/ucm/Chart.yaml); follow that convention.

## 3. Documentation
- `docs/ADMIN_GUIDE.md`: new section "ACME proxy: DNS UPDATE listener (RFC 2136)" after the ACME proxy/DNS-01 sections: purpose; enabling (setting or env, restart needed, 0 = off, default off); ports (unprivileged default suggestion 8053; mapping to 53 with Docker, Kubernetes Service, or a firewall redirect such as `iptables -t nat -A PREROUTING -p udp --dport 53 -j REDIRECT --to-port 8053` plus the TCP rule); `UCM_DNS_UPDATE_HOST` to bind only an internal address; **internal network only** warning; keys per proxy account (shown once, encrypted at rest, revoke/delete), optional EAB link and what it limits; what the listener accepts and answers (only TXT at `_acme-challenge.<name>` with the value UCM expects for a pending proxy order, signed; unsigned UPDATE refused; deletes always NOERROR; nothing is written to DNS by the listener — UCM still publishes through its DNS provider; SOA discovery answers; every other query refused; UDP answers to unsigned requests never larger than the request); algorithms (hmac-sha256/384/512 only; client defaults md5/sha1 are refused with BADKEY, so set the algorithm); time: client clock within 300 s (BADTIME); troubleshooting table: BADKEY, BADSIG, BADTIME, REFUSED (unsigned / value mismatch / no pending order / not `_acme-challenge` / prerequisites), NOTAUTH (zone not in ACME Domains), NOTZONE.
- New `docs/integrations/acme-proxy-dns-update.md`: per-client configuration for cert-manager, acme.sh (dns_nsupdate), certbot (certbot-dns-rfc2136), lego, win-acme, Posh-ACME, with complete examples. VERIFY every option/env var/flag in the client sources under /tmp/claude-0/clientsrc/ (bind9, acmesh, pypi/rfc2136, gomod lego v4.35.2 and cert-manager v1.21.3, Posh-ACME, win-acme) and list file:line for each in your report; do not invent names. Include the client facts from plan §9: nsupdate signs SOA discovery and needs no TC; certbot needs `sign_query` only optionally and sends over TCP; lego default algorithm hmac-sha1 → set hmac-sha256, `DNSUPDATE_ZONES`/propagation flags when hosts cannot reach public DNS; cert-manager finds the zone apex through its recursive resolvers (they must see the public zone), supports HMACSHA256/HMACSHA512 (not sha384), default HMACMD5 must be changed; win-acme always sends to port 53 (its `--serverport` becomes a timeout in its DNS library) and computes hmac-sha384 wrongly → use sha256 and map port 53; Posh-ACME needs `DDNSNameserver` (otherwise nsupdate sends to the SOA MNAME on port 53). Link it from docs/README.md and from ADMIN_GUIDE.
- `examples/kubernetes/cert-manager/clusterissuer-ucm-proxy-rfc2136.yaml`: Secret with the TSIG secret placeholder + ClusterIssuer with the `rfc2136` solver pointing at the UCM DNS UPDATE Service (`<release>-ucm-dns-update.<ns>.svc:53`), `tsigAlgorithm: HMACSHA256`, `server: https://ucm.example.com:8443/acme/proxy/<slug>/directory`; comment that it replaces the acme-dns stub approach. Add it to the examples README table. YAML must parse (`/home/user/ultimate-ca-manager/.venv/bin/python -c "import yaml,sys; list(yaml.safe_load_all(open(sys.argv[1])))" <file>`).
- `docs/API_REFERENCE.md`: the 3 key routes and the 3 settings fields, in the style of the EAB entries.
- `CHANGELOG.md` under `## [Unreleased]`, `### Added` (create the subsection if missing, follow the file's pattern): one or two sentences, reference #416.
Use example.com / ucm.example.com only; no real hosts.

## Report
Files, validation results (helm lint/template outputs summarized, entrypoint checks, YAML parse), the verification list (client option names with file:line), anything you could not verify, deviations with reasons, commit hash.
````
