# Sposób pracy z agentami AI (issue #416)

Ten dokument opisuje, jak powstaje zmiana „nasłuch DNS UPDATE (RFC 2136) dla proxy ACME”: kto co robi, jakie są zasady i jakie prompty dostają agenci. Plan zmiany jest w [`plan.pl.md`](plan.pl.md). Wymagania maintainera są w [`maintainer-requirements.md`](maintainer-requirements.md).

## 1. Zasady

1. **RFC to niezmienniki.** Każda funkcja protokołu ma podstawę w konkretnej sekcji RFC. Teksty RFC pobieramy z rfc-editor.org i cytujemy dosłownie. Wymagania maintainera mają ten sam status. Gdy wymaganie maintainera i RFC się różnią, plan opisuje różnicę i decyzję (plan, sekcja 5).
2. **Każdy niezmiennik ma test pozytywny i negatywny.** Test negatywny zmienia jedną rzecz, która narusza niezmiennik, i sprawdza też brak skutków ubocznych (zapis w DB, audyt, podpis).
3. **Fakty o klientach tylko z kodu źródłowego.** Każde twierdzenie o zachowaniu klienta ACME ma plik i numer wiersza w kodzie klienta. Czego nie da się potwierdzić, oznaczamy jako niepotwierdzone.
4. **Prototyp przed decyzją.** Gdy plan zakłada zachowanie biblioteki (dnspython), sprawdzamy je krótkim prototypem (`spike/`).
5. **Niezależny przegląd.** Recenzent dostaje materiały źródłowe, ale nie wnioski autora. Dzięki temu jego ocena nie powtarza założeń autora.
6. **Człowiek decyduje.** Wyniki agentów to materiał pomocniczy. Główna sesja czyta każdy diff, uruchamia testy i decyduje, czy praca jest skończona. Decyzje z wpływem na zewnątrz (gałęzie, autor commitów, PR) podejmuje użytkownik.

## 2. Role

| Rola | Agent | Zadanie | Narzędzia |
|---|---|---|---|
| Główna sesja | model główny | Zakres, architektura, decyzje RFC, przegląd każdego wyniku, testy, decyzja o końcu pracy | wszystkie |
| Mapowanie kodu | `Explore` | Fakty o istniejącym kodzie UCM: pliki, wiersze, wzorce. Bez projektu | tylko odczyt |
| Badanie klientów | `general-purpose` | Pobranie kodu klientów ACME i odpowiedź na pytania z cytatem z kodu | odczyt, git, pip, go |
| Implementacja | `implementer` (mniejszy model, wysiłek medium) | Kod, testy i dokumentacja według dokładnej specyfikacji. Bez commitów | edycja plików, testy |
| Przegląd | `reviewer` | Niezależny przegląd bezpieczeństwa planu i kodu | tylko odczyt |
| Przegląd kodu | `/code-review`, `/security-review` | 3 rundy każdego po zakończeniu kodu, poprawki między rundami | — |

## 3. Kolejność pracy

```
1. Wymagania maintainera (issue #416)       ──┐
2. Pobranie RFC i odczyt sekcji               ├─> plan z tabelą niezmienników (P/N)
3. Mapowanie kodu UCM (Explore)               │
4. Kod klientów ACME (general-purpose)       ──┘
5. Prototyp dnspython (spike)               ──> poprawki planu
6. Security review planu (reviewer)         ──> poprawki planu
7. PR 1: dokumentacja (implementer)         ──> przegląd diffu, walidacja
8. PR 2: części 2–9 planu (implementer, po kolei według zależności)
                                             ──> przegląd każdej części, pełne testy
9. E2E z prawdziwymi klientami (główna sesja)
10. 3 × /code-review, 3 × /security-review, poprawki
```

## 4. Jak piszemy prompt dla agenta

Agent zaczyna bez kontekstu. Prompt musi zawierać:

| Element | Przykład |
|---|---|
| Cel i powód | „We will add an optional DNS UPDATE (RFC 2136) listener…” |
| Zakres i granice | „Do not propose a design; just report facts”, „Do NOT commit or push” |
| Wejścia (ścieżki, wersje) | ścieżki do RFC, do kodu klientów, gałąź bazowa |
| Lista pytań lub produktów | numerowana, żeby raport miał tę samą strukturę |
| Wymóg dowodu | „every claim must cite a file path + line numbers… If something cannot be confirmed from source, say UNCONFIRMED” |
| Walidacja | polecenia do uruchomienia i oczekiwany wynik |
| Format raportu | sekcje, tabela zbiorcza, lista niepotwierdzonych rzeczy |

Dla recenzenta: dajemy materiały źródłowe i pytania, nie dajemy naszych wniosków ani „co już sprawdziliśmy”. Prosimy o: poziom ważności, scenariusz ataku, dowód (plik:wiersz albo cytat z RFC) i konkretną poprawkę.

Dla implementera: dajemy specyfikację z planu (niezmienniki z ID, kolejność przetwarzania, decyzje), pliki do zmiany, ograniczenia i polecenia testów. Kod bezpieczeństwa (TSIG, handler, serwer) dostaje szczegółową specyfikację i przechodzi dokładny przegląd w głównej sesji.

## 5. Prompty użyte do tej pory

Ścieżki `/tmp/...` w promptach to katalogi robocze w kontenerze sesji. Prompty są zapisane bez zmian.

### 5.1 Mapowanie kodu UCM (`Explore`)

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

### 5.2 Kod klientów ACME (`general-purpose`)

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

### 5.3 Security review planu (`reviewer`)

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

### 5.4 PR 1: dokumentacja (`implementer`)

Prompt w skrócie (pełna treść ma ponad 100 wierszy): cel i kontekst issue #416, podstawa w RFC 8555 §8.4 i §7.5.1 (cytaty), lista produktów (nowy plik `docs/integrations/acme-proxy-clients.md`, przykład manifestu cert-manager z atrapą acme-dns, odnośniki w ADMIN_GUIDE i README przykładów, wpis w CHANGELOG), konfiguracja dla certbot, acme.sh, lego, cert-manager, win-acme i Posh-ACME. Najważniejszy wymóg:

```text
Every CLI flag, env var, file name and config key you write must be verified in the client source under /tmp/claude-0/clientsrc/ (or already present in this repo). In your final report, list each one with the source file and line where you verified it. If something cannot be verified, do not write it as fact.
```

### 5.5 Prompty dla PR 2

Prompty dla części 2–9 planu powstają z sekcji 2–7 i 11 planu. Każdy prompt zawiera: ID niezmienników z tabeli (z kolumnami P i N), kolejność przetwarzania z sekcji 3, decyzje z sekcji 5, ustalenia security review z sekcji 11, pliki do zmiany, pliki, których agent nie może zmieniać (praca równoległa), i polecenia testów.

Części 2 i 3 nie zależą od siebie, więc działają równolegle w tym samym worktree, na rozłącznych plikach.

Pełne prompty wszystkich części PR 2 są w [`prompts-pr2.md`](prompts-pr2.md). Poniżej są najważniejsze elementy każdego promptu.

#### Część 3: moduł TSIG (`implementer`)

Najważniejsze elementy promptu:

- dokładne publiczne API modułu (`TsigKeyMaterial`, `TsigOutcome`, `TsigResult`, `TimeWatermark`, `verify_request`, funkcje `render_*`), żeby handler w części 5 mógł z nich korzystać bez zgadywania;
- kolejność weryfikacji krok po kroku z numerami sekcji RFC 8945 (§5.2: klucz, rozmiar MAC, MAC, czas, skrócenie) i z ustaleniami F5, F9, F11;
- zakaz polegania na automatycznym podpisie dnspython (podpisuje czasem serwera i złym MAC żądania dla odpowiedzi z błędem);
- wymóg **niezależnej** weryfikacji MAC w testach: test liczy HMAC modułem `hmac` z elementów z RFC 8945 §4.3, a nie funkcją dnspython, którą testuje;
- dla każdego ID z tabeli S: test `_pos` i `_neg`, z opisem, co test negatywny zmienia.

Fragment o kolejności (dosłownie):

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

#### Część 2: modele, migracja 111, sprzątanie kluczy (`implementer`)

Najważniejsze elementy promptu:

- kolumny, ograniczenia i indeksy obu tabel z planu (2.1);
- szyfrowanie sekretu tą samą warstwą co HMAC EAB, ale getter zwraca `None` przy błędzie odszyfrowania, **nigdy** szyfrogram (F4, K7);
- migracja dla SQLite i PostgreSQL według istniejących wzorców (027, 078, 110) i reguł `migration_runner.py`;
- usuwanie kluczy w kodzie przy usunięciu EAB i konta proxy, bo SQLite w UCM nie wymusza kluczy obcych (F2, F3, K8, K9) — agent ma to sprawdzić, a nie przyjąć;
- testy `_pos`/`_neg` dla K2, K3, K5, K8, K9 i ograniczenia UNIQUE, także przez API (usunięcie EAB i konta).

#### Część 4: wartości oczekiwane i haki w proxy (`implementer`)

- dokładne API modułu `records.py` (`record_name_for`, `expected_value`, `zone_for`, `persist_expected_values`, `close_*`, `mark_confirmed`, pamięć podręczna aktywnych wierszy);
- wiersz dla każdego zamówienia rodzeństwa z **jego własnym** thumbprintem i kontem (F13b, #307), zapis w savepoincie, który nigdy nie zmienia wyniku `get_authz` (F13a, R6);
- niezależne obliczenie wartości w teście (`hashlib` + `base64`) na przykładach z RFC 8555 §8.3 i RFC 7638 §3.1;
- test „0 zapytań SQL” dla ciepłej pamięci podręcznej (licznik `before_cursor_execute`).

Poprawka po przeglądzie w głównej sesji: specyfikacja zamykała wiersze także w stanach `processing` i `valid`. To dawało wyścig z UPDATE klienta. Wiersze zamykają się teraz tylko w stanach błędu (plan 2.2, punkt 5).

#### Część 5a: magazyn kluczy, indeks stref, audyt (`implementer`)

- `KeyScope.allows` „fail closed”: każde `None` daje odmowę (plan 2.3, K8);
- klucz konta z wyłączonym proxy, klucz odwołany, sekret, którego nie da się odszyfrować, algorytm spoza listy: klucz nie istnieje dla nasłuchu (K7, K9);
- audyt z limitem na parę (IP, przyczyna) i z limitem globalnym na przyczynę, z wierszem podsumowania (F7, N7, N12);
- czyszczenie tekstu od atakującego przed zapisem do audytu (N13), brak sekretów w logach (N11).

#### Część 5b: handler protokołu (`implementer`)

- kolejność przetwarzania krok po kroku z planu (sekcja 3) z numerami sekcji RFC; każdy krok ma testy;
- klient testów to niezależna biblioteka (dnspython jako klient), odpowiedzi podpisane są weryfikowane po stronie klienta;
- kształty wiadomości każdego klienta z planu (sekcja 9): nsupdate, certbot, lego, cert-manager, win-acme, acme.sh;
- brak skutków ubocznych w testach negatywnych (brak `mark_confirmed`, audytu, `touch`, TSIG w odpowiedzi);
- test integracyjny z prawdziwą bazą: 1000 zapytań SOA bez podpisu i 1000 UPDATE z BADKEY bez zapytań SQL (N8).

Poprawki po przeglądzie w głównej sesji: rozmiar EDNS w odpowiedzi (było 8192, jest `MAX_MESSAGE_SIZE`), przyczyna odmowy w polu `reason` wiersza audytu.

#### Część 6: serwer UDP/TCP (`implementer`)

- tabela limitów zasobów z planu 2.4 jako specyfikacja (`ServerLimits`);
- RFC 7766: wiele wiadomości w jednym połączeniu, limit bezczynności liczony od ostatniej **pełnej** wiadomości, jeden zapis na odpowiedź;
- błąd `bind` nie zatrzymuje UCM (N3), port 0 wyłącza nasłuch (N1);
- start w `post_worker_init` (gunicorn, `workers = 1`) i w ścieżce deweloperskiej `app.py`.

#### Część 7: API kluczy i ustawienie portu (`implementer`)

- trasy, uprawnienia i odpowiedzi według wzoru API EAB (sekret pokazany raz);
- tylko `hmac-sha256`, `hmac-sha384`, `hmac-sha512`, także w trybie FIPS (K4);
- port 0 albo 1024–65535, bez konfliktu z portami HTTPS i HTTP (N2);
- natychmiastowe unieważnienie pamięci podręcznej kluczy i stref po zmianach w API (test integracyjny).

#### Część 8: interfejs, pomoc, tłumaczenia (`implementer`)

- panel kluczy przy koncie proxy, okno z sekretem pokazanym raz, gotowe fragmenty konfiguracji dla 7 klientów;
- każda nazwa opcji klienta zweryfikowana w kodzie źródłowym klienta;
- 9 języków, `check:i18n`, testy vitest.

Poprawki po przeglądzie w głównej sesji: `--validationmode dns-01` w fragmencie win-acme, informacja o porcie 53 przy przekierowaniu portu.

#### Część 9: pakiety, Helm, dokumentacja (`implementer`)

- `EXPOSE 8053/udp` i `8053/tcp`, kontrola portu w entrypoint (kontener działa bez prawa do portów < 1024);
- osobny Service Helm dla nasłuchu (wystawienie UI nie wystawia nasłuchu), opcjonalna NetworkPolicy;
- dokumentacja administratora i klientów z faktami z kodu źródłowego klientów.

Poprawki po E2E w głównej sesji: sekcja rozwiązywania problemów (komunikaty `bad authentication` w `miekg/dns`, zachowanie `nsupdate` po BADSIG, pole `reason` w audycie).

## 6. Testy end-to-end

Testy E2E wykonuje główna sesja, bez agenta. Procedura i wyniki są w [`docs/testing/ACME-PROXY-DNS-UPDATE.md`](../../testing/ACME-PROXY-DNS-UPDATE.md).

1. Najpierw harness: sam `DnsUpdateHandler` za prostym serwerem UDP/TCP, z kluczami i strefami w pamięci. Sprawdza format wiadomości z prawdziwymi bibliotekami klientów, bez przepływu ACME.
2. Potem pełny przepływ: Pebble jako zewnętrzny CA, pebble-challtestsrv jako DNS, UCM z dostawcą `custom_command`, prawdziwi klienci.
3. Każdy klient ma test pozytywny (certyfikat) i negatywny (klucz innego konta, zły sekret, zły algorytm, strefa spoza ACME Domains).

E2E znalazło błąd poza zakresem PR 2: proxy nie dodaje nagłówka `Link: rel="up"`, gdy zewnętrzny CA go nie wysyła (Pebble). To kandydat na osobną poprawkę.

## 7. Przegląd kodu po zakończeniu

Po zakończeniu kodu: 3 rundy `/code-review` i 3 rundy `/security-review` na całej zmianie PR 2, z poprawkami między rundami. Każde ustalenie główna sesja sprawdza w kodzie i w RFC, zanim je poprawi. Poprawki przygotowują agenci `implementer` (osobne pliki dla każdego agenta, praca równoległa), a główna sesja czyta diff i uruchamia pełne testy przed commitem. Wszystkie ustalenia, decyzje (także „bez zmian” z uzasadnieniem) i commity są w sekcji 12 planu.

Po rundach przeglądu główna sesja powtarza E2E na końcowym kodzie, na nowej bazie danych.

