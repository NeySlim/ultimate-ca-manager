# Plan: nasłuch DNS UPDATE (RFC 2136) dla proxy ACME w UCM

Status: wersja 3. Po security review planu (ustalenia F1–F15 w sekcji 11).

## 0. Źródła

| Źródło | Gdzie |
|---|---|
| Wymagania maintainera | NeySlim/ultimate-ca-manager#416, komentarz NeySlim z 2026-10-24 |
| Teksty RFC (oficjalne) | `https://www.rfc-editor.org/rfc/rfcNNNN.txt` |
| Kod UCM | gałąź bazowa: `upstream/dev` (NeySlim, 2.246-dev, `3ece475`); CONTRIBUTING.md: PR do `dev` |
| Kod klientów | sekcja 9 (wersje i commity klientów) |
| dnspython 2.8.0 | `dns/tsig.py`, `dns/message.py` z wheel `dnspython-2.8.0-py3-none-any.whl` |

RFC użyte jako niezmienniki:

| RFC | Temat | Sekcje używane |
|---|---|---|
| 1034, 1035 | DNS, format wiadomości, SOA, UDP/TCP | 1034 §3.1, §4.3.2; 1035 §3.3.13, §3.3.14, §4.1.1, §4.2.1, §4.2.2 |
| 2136 | DNS UPDATE | §2, §3.1–§3.8 |
| 3007 | Bezpieczny UPDATE, polityka | §2, §3, §3.1 |
| 8945 | TSIG | §4.2, §5.1–§5.4, §6, §7, §8 |
| 6891 | EDNS(0) | §6.1.1, §6.1.3, §6.2.3, §7 |
| 7766 | DNS przez TCP | §6.2.1–§6.2.4, §8 |
| 8906 | Odpowiadanie zamiast milczenia | §3.1.1–§3.1.5, §3.2.2–§3.2.5, §7 |
| 9619 | QDCOUNT = 1 | całość |
| 2308 | Odpowiedzi negatywne (NODATA) | §2.2, §3 |
| 8555, 7638, 4648 | Wartość dns-01, thumbprint JWK, base64url | 8555 §7.1.4, §8.1, §8.4; 7638 §3; 4648 §5 |

## 1. Zakres i podział na PR

Maintainer chce dwóch PR:

1. **PR 1 – dokumentacja (wariant D).** Obejścia dla każdego klienta. Ograniczenia resolverów: cert-manager `--dns01-recursive-nameservers` i `--dns01-recursive-nameservers-only`, acme.sh `--dnssleep`, conditional forwarder dla `_acme-challenge`.
2. **PR 2 – nasłuch.** Backend, migracja, UI, tłumaczenia (9 języków), Helm, pakiety, dokumentacja, testy.

Obie zmiany powstają na bazie `upstream/dev`. CONTRIBUTING.md mówi: PR trafia do `dev`. Fork `WMP` jest za upstream. Wymagania CONTRIBUTING.md: wpis w CHANGELOG pod `## [Unreleased]`, teksty w 9 językach, migracja dla SQLite i PostgreSQL, temat commitu `type(scope): summary` (< 72 znaki). WMP ma już podpis CLA v1.1 (2026-10-23).

## 2. Architektura

```
klient ACME ──UDP/TCP──> [server.py] ─bytes─> [handler.py] ──> [tsig.py]   (RFC 8945)
                                                   │
                                                   ├──> [policy.py] ──> [records.py] (oczekiwane TXT, DB)
                                                   │                └──> [keys.py]    (klucze TSIG, DB)
                                                   └──> audit / log
proxy ACME get_authz ──> records.py.persist()   (zapis oczekiwanej wartości przy pobraniu authz)
proxy ACME get_certificate ──> records.py.close_order()
```

Nowy pakiet: `backend/services/acme/dns_update/`.

| Moduł | Odpowiedzialność | Zależności |
|---|---|---|
| `constants.py` | Limity, algorytmy, kody | brak |
| `tsig.py` | Weryfikacja TSIG po stronie serwera w kolejności z RFC 8945 §5.2. Budowa odpowiedzi podpisanych i błędów TSIG | dnspython (tylko publiczne API) |
| `keys.py` | Odczyt kluczy z DB, polityka algorytmów, FIPS | model, `fips_mode` |
| `records.py` | Zapis i odczyt oczekiwanych wartości TXT, zakres klucza | model, proxy |
| `policy.py` | Strefy, w których UCM „jest autorytatywny”; prawo do zmiany rekordu | `records.py`, ACME Domains |
| `handler.py` | Czysta funkcja `handle(wire, transport, peer, now) -> bytes | None`. Bez gniazd. Cała logika RFC | powyższe |
| `server.py` | Gniazda UDP i TCP (gevent), limity, start i stop | `handler.py` |

Zasada: cała logika protokołu jest w `handler.py` i `tsig.py`. Te moduły nie otwierają gniazd. Dzięki temu każdy niezmiennik RFC ma test jednostkowy na poziomie bajtów wiadomości.

### 2.1 Model danych (nowe tabele, migracja 111)

**`acme_dns_update_keys`** (klucze TSIG):

| Pole | Opis |
|---|---|
| `id` | PK |
| `acme_client_account_id` | FK do `acme_client_accounts` (konto proxy, slug), `ON DELETE CASCADE`. SQLite w UCM nie wymusza FK, dlatego usunięcie konta usuwa też klucze i wiersze w kodzie (`_remove_account_row`) (F3) |
| `eab_credential_id` | FK do `acme_eab_credentials`, `ON DELETE CASCADE`, NULL = brak powiązania. Usunięcie poświadczenia EAB usuwa powiązane klucze także w kodzie (handler DELETE EAB) (F2) |
| `name` | Nazwa klucza jako nazwa DNS, absolutna, małe litery, unikalna (RFC 8945 §4.2) |
| `algorithm` | `hmac-sha256` (domyślnie), `hmac-sha384`, `hmac-sha512` |
| `secret` | Sekret szyfrowany jak HMAC EAB: `utils.encryption.encrypt_if_needed` (Fernet, zawsze włączone). Sekretu, którego nie da się odszyfrować, albo pustego, nie używa się nigdy: klucz = nieznany (BADKEY) (F4) |
| `status` | `active` / `revoked` |
| `created_at`, `created_by_user_id`, `last_used_at`, `revoked_at`, `notes` | |

**`acme_proxy_dns_challenges`** (oczekiwane wartości TXT):

| Pole | Opis |
|---|---|
| `id` | PK |
| `order_id` | FK do `acme_client_orders`, `ON DELETE CASCADE` |
| `acme_client_account_id` | konto proxy (slug) zamówienia |
| `account_id` | lokalne `AcmeAccount.account_id` klienta (do powiązania z EAB) |
| `client_jwk_thumbprint` | thumbprint klienta (RFC 7638) |
| `identifier` | domena bez `*.` |
| `record_name` | `_acme-challenge.<identifier>.`, małe litery |
| `txt_value` | `base64url(SHA-256(token "." thumbprint))`, 43 znaki |
| `upstream_challenge_url` | do diagnostyki |
| `status` | `pending` / `closed` |
| `created_at`, `expires_at`, `client_confirmed_at` | |
| UNIQUE | (`order_id`, `record_name`, `txt_value`) |

Obie tabele trafiają też do: modeli SQLAlchemy (`db.create_all()` przy nowej instalacji), manifestu kopii zapasowej (`services/backup/manifest.py`), testu migracji (SQLite i PostgreSQL).

### 2.2 Cykl życia oczekiwanej wartości

1. Klient pobiera authz (`get_authz`). Dla każdego wyzwania `dns-01` w stanie `pending` UCM zapisuje wiersz dla zamówienia klienta **i dla zamówień rodzeństwa** (te same upstream authz, #307). Wiersz rodzeństwa ma **własny** `client_jwk_thumbprint` i `account_id` rodzeństwa. Zamówienie bez thumbprintu nie dostaje wiersza. Zapis jest idempotentny i nie zależy od tego, czy automatyka DNS już ruszyła (F13b).
2. Zapis jest „best effort”: w savepoincie (`db.session.begin_nested()`), konflikt UNIQUE i każdy inny błąd jest logowany i **nigdy** nie przerywa `get_authz` ani nie cofa stanu `challenges_data` (F13a).
3. `expires_at` = `expires` z upstream authz, ale nie później niż `created_at + 24 h` (F13d).
4. Wiersz jest „aktywny”, gdy: `status = pending`, `expires_at > teraz`, zamówienie ma `status = pending`.
5. Zamknięcie (`status = closed`): `get_certificate`; każdy odczyt upstream authz albo challenge w stanie innym niż `pending` (`get_authz`, `respond_challenge`) (F13d).
6. Wiersze z `expires_at` starszym niż 7 dni są usuwane przy kolejnym zapisie.

### 2.3 Strefy „autorytatywne” i zakres klucza

- **Domena D wiersza** = domena z „ACME → Domains”, którą wybiera istniejąca funkcja `find_provider_for_domain(identifier)` (najbardziej szczegółowe dopasowanie, bez `*.`). Tę samą domenę UCM używa dziś do wyboru dostawcy DNS. D jest apexem strefy, który UCM ogłasza w odpowiedziach SOA.
- **Strefa jest nasza** (RFC 2136 §3.1.1), gdy ZNAME jest domeną z „ACME → Domains” albo jej przodkiem (bez korzenia i bez nazw jednoetykietowych). Przodek jest potrzebny, bo cert-manager bierze apex z publicznego DNS, a win-acme zaczyna od domeny rejestrowalnej (sekcja 9). Prawdziwa strefa, do której pisze dostawca DNS UCM, to D albo przodek D. Ta reguła nie zależy od aktywnych zamówień. Dzięki temu usunięcie rekordu po zakończeniu zamówienia dostaje NOERROR, jak chce maintainer.
- **Klucz jest ważny** (inaczej BADKEY), gdy: `status = active`, sekret odszyfrowany i niepusty, konto proxy istnieje i ma `proxy_enabled = true` (F3, F4).
- **Zakres klucza** (RFC 3007 §3), zasada „domyślnie brak”: wiersz pasuje do klucza, gdy `row.acme_client_account_id = key.acme_client_account_id`. Gdy `key.eab_credential_id` nie jest NULL, dodatkowo: poświadczenie EAB istnieje, ma `status = used`, ma niepuste `used_by_account_id`, a `row.account_id` jest niepuste i równe `used_by_account_id`. Każdy inny przypadek (EAB usunięte, nieużyte, NULL po którejkolwiek stronie) = brak dopasowania (F2).
- **Dopasowanie wartości** zawsze dotyczy pary (`record_name`, `txt_value`), nigdy samej wartości (F13c).

### 2.4 Zasoby, pamięć podręczna i odporność (F1, F8)

Nasłuch działa w jedynym workerze gevent (`workers = 1`), który obsługuje też HTTPS, ACME, OCSP i CRL. Wywołania DB (psycopg2 bez psycogreen, sqlite3) blokują pętlę gevent. Dlatego:

| Mechanizm | Wartość domyślna | Cel |
|---|---|---|
| `spawn=Pool(N)` dla `DatagramServer` i `StreamServer` | N = 16 (UDP), 32 połączenia (TCP) | ograniczona liczba greenletów |
| Globalny token bucket pakietów, sprawdzany przed parsowaniem | 200 pakietów/s, zryw 400 | ochrona przed zalaniem także z podrobionych adresów |
| Limit na IP, w ograniczonym LRU (np. 4096 wpisów) | 50 pakietów/s na IP dla ruchu bez poprawnego TSIG | ochrona przed jednym źródłem; LRU chroni pamięć |
| Wstępna kontrola nagłówka przed `from_wire` | QDCOUNT ≤ 1, ANCOUNT = 0 dla QUERY, NSCOUNT ≤ 16, ARCOUNT ≤ 4, długość ≤ MAX_MSG = 4096 B | mały koszt odrzucenia |
| Pamięć podręczna aktywnych wierszy (record_name, D, wartości, zakres) | odświeżanie po zapisie w `records.py` i co 5 s | SOA bez podpisu i BADKEY bez zapytań do DB |
| Pamięć podręczna kluczy TSIG | unieważnienie przy każdej zmianie klucza (API w tym samym procesie), TTL 30 s | odwołanie działa od razu |
| Pamięć podręczna domen ACME (strefy) | TTL 10 s | sprawdzanie strefy bez DB |
| TCP: limit bezczynności, czas zapisu, maks. czas życia połączenia | 10 s, 10 s, 120 s | ochrona przed slow-read i wyczerpaniem połączeń |
| Wyjątek w handlerze | odpowiedź SERVFAIL (gdy da się odczytać ID), inaczej brak odpowiedzi; serwer działa dalej | odporność |
| Logi aplikacji dla ruchu bez podpisu i błędnego | próbkowanie: maks. 1 wiersz na (powód) na 10 s, plus liczniki | ochrona logów |
| Adres nasłuchu | `UCM_DNS_UPDATE_HOST`, domyślnie `HOST` | możliwość nasłuchu tylko w sieci wewnętrznej (F8) |

Osobny proces dla nasłuchu odrzucam: wzorzec serwera HTTP protokołów (wymaganie maintainera) i wspólne unieważnianie pamięci podręcznej w jednym procesie są prostsze. Powyższe limity ograniczają koszt ruchu bez podpisu do kilku operacji w pamięci.

## 3. Kolejność przetwarzania wiadomości

Każdy krok ma numer niezmiennika z sekcji 4.

```
1. Globalny token bucket i limit na IP (ruch jeszcze niezweryfikowany) → brak odpowiedzi (N4, N8).
2. Długość < 12 B → brak odpowiedzi (M2). QR=1 → brak odpowiedzi (M1).
3. Długość > MAX_MSG albo liczniki nagłówka poza limitem → brak odpowiedzi (N9).
4. Opcode ∉ {QUERY, UPDATE} → NOTIMP, sam nagłówek, bez TSIG (M3; decyzja 11).
5. Parsowanie dnspython (keyring=False, bez weryfikacji, bez dopełnienia) → błąd → FORMERR, bez TSIG (M4, S1, E2).
6. TSIG obecny → kolejność RFC 8945 §5.2:
   a. pole Error ≠ 0 → FORMERR (S9)
   b. klucz nieznany, nieważny (sekcja 2.3), algorytm ≠ algorytm klucza lub spoza polityki
      → NOTAUTH/BADKEY, bez podpisu (S2, S3, K7–K9)
   c. rozmiar MAC > długość skrótu albo < max(10, połowa skrótu) → FORMERR (S8)
   d. MAC:
      pełna długość → dns.tsig.validate(..., now=time_signed) (sprawdza nazwę, algorytm, HMAC);
      skrócony → pełny MAC przez publiczne dns.tsig.sign na wiadomości bez TSIG,
                 potem hmac.compare_digest(pełny[:len], mac) (F5).
      Niezgodność → NOTAUTH/BADSIG, bez podpisu (S4, S8)
   e. powtórka: ten sam MAC żądania już przyjęty w oknie → ta sama odpowiedź z pamięci,
      bez skutków ubocznych (S15)
   f. czas: |teraz − Time Signed| > min(Fudge, 300) albo Time Signed < ostatni przyjęty dla klucza
      → NOTAUTH/BADTIME, podpisany, Time Signed = czas klienta, Other Data = czas serwera,
      Fudge = fudge klienta (S6, S7, S14)
   g. MAC skrócony (zgodny) → NOTAUTH/BADTRUNC, podpisany; w podpisie skrócony MAC żądania (S8)
   h. ostatni przyjęty Time Signed dla klucza zmienia się dopiero tutaj (po b–g) (S7)
7. EDNS: wersja > 0 → BADVERS z OPT wersji 0 (E3).
8. QUERY → sekcja 3.1. UPDATE → sekcja 3.2.
9. Odpowiedź: ID i opcode skopiowane, QR=1, RD skopiowany, RA=0, Z=0, bez dopełnienia
   (make_response(pad=0)) (M6–M8, E5).
   Podpisana, gdy żądanie było podpisane i przeszło 6b–6d (S10). OPT, gdy żądanie miało OPT (E1).
10. UDP, żądanie bez poprawnego TSIG (także każda odpowiedź na błąd TSIG):
    odpowiedź dłuższa niż żądanie → odpowiedź minimalna z TC=1 (T1).
    UDP, żądanie z poprawnym TSIG: limit max(512, rozmiar EDNS); powyżej → TC=1 z TSIG (T2, S12).
11. Audyt i log po decyzji, w osobnej transakcji (N6, N12, N13).
```

### 3.1 QUERY

```
QDCOUNT ≠ 1 → FORMERR (M5)
QCLASS ≠ IN → REFUSED (Q4)
QTYPE ≠ SOA → REFUSED (Q3, Q5)
W = aktywne wiersze (zapytanie bez podpisu: wszystkie; z podpisem: w zakresie klucza)
QNAME = D wiersza z W
    → NOERROR, AA=1, SOA(D) w ANSWER (Q1)
QNAME jest potomkiem D i przodkiem lub równa record_name wiersza z W
    → NOERROR, AA=1, ANSWER pusty, SOA(D) w AUTHORITY (NODATA, RFC 2308 §2.2) (Q7)
każde inne zapytanie → REFUSED (Q3)
```

Rekord SOA(D) ma stałe wartości (F12): właściciel D, TTL 0, MNAME = D, RNAME = `hostmaster.D`, SERIAL = 1, REFRESH 3600, RETRY 600, EXPIRE 86400, MINIMUM 0. Nie zawiera nazwy hosta UCM, adresu e-mail ani znacznika czasu.

Dlaczego tak (sekcja 9): certbot i lego idą od `_acme-challenge.<id>` w górę i potrzebują SOA w ANSWER na apexie. nsupdate pyta tylko o nazwę rekordu i przyjmuje SOA z AUTHORITY. Odpowiedź REFUSED na nazwę rekordu zatrzymałaby nsupdate.

Uwaga do PR (F14): zakres klucza dla podpisanego SOA niczego nie ukrywa, bo ten sam klient może wysłać zapytanie bez podpisu i dostać odpowiedź dla wszystkich kont. To nie jest zabezpieczenie.

### 3.2 UPDATE (kolejność RFC 2136 §3)

```
brak podpisu TSIG → REFUSED, od razu, przed sprawdzeniem strefy (U4; RFC 3007 §2, RFC 2136 §3.3.1) (F6)
ZOCOUNT ≠ 1 albo ZTYPE ≠ SOA → FORMERR                (U1, §3.1.1)
ZCLASS ≠ IN → NOTAUTH                                 (U2, §3.1.1)
ZNAME nie jest naszą strefą → NOTAUTH                  (U3, §3.1.1)
sekcja prerequisite niepusta → REFUSED                 (U5, polityka §3.3, wymaganie maintainera)
dla każdego RR (sprawdzenie uprawnień, §3.3):
    typ ≠ TXT albo nazwa nie zaczyna się od "_acme-challenge." → REFUSED (U9)
    dodanie: para (nazwa, wartość) ≠ aktywny wiersz w zakresie klucza → REFUSED (U10)
    usunięcie klasy ANY typu ANY → REFUSED (U11)
prescan (§3.4.1): klasa ∉ {IN, ANY, NONE} → FORMERR; nazwa poza ZNAME → NOTZONE;
    reguły TTL/RDLENGTH/typów meta → FORMERR       (U6–U8)
zastosowanie: bez zmiany DNS (UCM publikuje rekord sam, jak dziś); zapis client_confirmed_at,
    last_used_at klucza (U12, U13, U15)
→ NOERROR, liczniki sekcji = 0                     (U14, §3.8)
```

Cała wiadomość jest sprawdzana przed jakimkolwiek zapisem. Jeden zły rekord odrzuca całą wiadomość (RFC 2136 §3.3.2, §3.7).

## 4. Niezmienniki RFC i testy

Każdy niezmiennik ma **test pozytywny (P)** i **test negatywny (N)**. Test negatywny używa tych samych danych co pozytywny i zmienia tylko jedną rzecz, która narusza niezmiennik. Test negatywny sprawdza też, że nie ma skutków ubocznych: brak zapisu w DB, brak wpisu audytu (gdy nie powinien powstać), brak podpisu (gdy nie powinien powstać).

Nazwa testu: `test_<ID>_<opis>_pos` / `test_<ID>_<opis>_neg`.

### 4.1 Wiadomość (M), EDNS (E), transport (T)

| ID | Niezmiennik | RFC | P | N |
|---|---|---|---|---|
| M1 | Na wiadomość z QR=1 serwer nie odpowiada | 1035 §4.1.1 | zapytanie QR=0 → odpowiedź | to samo z QR=1 → brak odpowiedzi |
| M2 | Wiadomość krótsza niż nagłówek (12 B) → brak odpowiedzi | 1035 §4.1.1 | 12 B poprawny nagłówek → odpowiedź | 11 B → brak odpowiedzi |
| M3 | Opcode inny niż QUERY i UPDATE → NOTIMP, sam nagłówek, opcode skopiowany | 2136 §3; 8906 §3.1.4, §7 | opcode 0 i 5 → nie NOTIMP | opcode 1, 2, 4, 6, 15 → NOTIMP, liczniki 0 |
| M4 | Błąd formatu dla znanego opcode → FORMERR | 8906 §7; 2136 §3.1.1 | poprawna wiadomość → nie FORMERR | ucięty RR, śmieci na końcu, zła etykieta → FORMERR |
| M5 | QUERY z QDCOUNT ≠ 1 → FORMERR | 9619; 1035 §4.1.2 | QDCOUNT=1 → odpowiedź | QDCOUNT=0 i 2 → FORMERR |
| M6 | Z=0 w odpowiedzi, nieznane flagi nie są kopiowane | 1035 §4.1.1; 8906 §3.1.3 | żądanie Z=0 → odpowiedź Z=0 | żądanie z Z=1 i AD=1 → odpowiedź, Z=0, AD=0 |
| M7 | RD skopiowany, RA=0 (brak rekursji) | 1035 §4.1.1; 8906 §3.1.3.1 | RD=0 → RD=0, RA=0 | RD=1 → RD=1, RA=0, brak zapytań wychodzących |
| M8 | ID i opcode skopiowane | 1035 §4.1.1; 2136 §3.8 | ID losowe → to samo ID | odpowiedź na inne ID nigdy nie pasuje (test właściwości, 100 losowych ID) |
| E1 | OPT w odpowiedzi tylko, gdy było w żądaniu | 6891 §6.1.1, §7 | z OPT → z OPT | bez OPT → bez OPT |
| E2 | Dwa OPT → FORMERR | 6891 §6.1.1 | jeden OPT → poprawnie | dwa OPT → FORMERR |
| E3 | Wersja EDNS > 0 → BADVERS, OPT wersji 0 | 6891 §6.1.3; 8906 §3.2.2 | wersja 0 → poprawnie | wersja 1 → BADVERS |
| E4 | Nieznane opcje i flagi EDNS są ignorowane i niekopiowane | 6891 §6.1.2, §6.1.4; 8906 §3.2.3–§3.2.4 | bez opcji → poprawnie | nieznana opcja i flaga → poprawnie, brak ich w odpowiedzi |
| E5 | Odpowiedź bez dopełnienia EDNS (PADDING) | 6891 §7; maintainer (rozmiar) | zapytanie bez PADDING → odpowiedź bez PADDING | małe zapytanie z PADDING → odpowiedź nie dłuższa niż zapytanie |
| T1 | UDP, żądanie bez poprawnego TSIG: odpowiedź nie dłuższa niż żądanie (maintainer). Dłuższa → TC=1, nagłówek, pytanie, OPT (gdy był) | 1035 §4.2.1; 6891 §7 | REFUSED mieści się → wysłany bez zmian | SOA bez podpisu przez UDP → TC=1, brak ANSWER i AUTHORITY, długość ≤ żądanie |
| T2 | UDP, żądanie z poprawnym TSIG: odpowiedź ≤ max(512, rozmiar EDNS); dłuższa → TC=1 z TSIG | 1035 §4.2.1; 6891 §6.2.3; 8906 §3.2.5; 8945 §5.3 | SOA podpisane przez UDP (wzorzec nsupdate, bez EDNS) → pełna odpowiedź ≤ 512 | odpowiedź > 512 bez EDNS → TC=1, pytanie + TSIG |
| T3 | TCP: ramka z 2 bajtami długości; kilka wiadomości w jednym połączeniu; dane w kilku segmentach | 1035 §4.2.2; 7766 §6.2.1, §8 | 2 zapytania w jednym połączeniu → 2 odpowiedzi; długość w osobnym segmencie → odpowiedź | długość 0 albo > MAX_MSG → zamknięcie bez odpowiedzi |
| T4 | TCP: pełna odpowiedź, bez TC | 8906 §3.2.7 | SOA przez TCP → pełny ANSWER, TC=0 | to samo przez UDP → TC=1 |
| T5 | TCP: limit bezczynności liczony od pełnej wiadomości | 7766 §6.2.3 | wiadomości co < limit → połączenie trwa | połowa wiadomości i cisza > limit → zamknięcie (ochrona przed slow-read) |

### 4.2 TSIG (S)

| ID | Niezmiennik | RFC | P | N |
|---|---|---|---|---|
| S1 | TSIG jest jeden i ostatni w sekcji additional, inaczej FORMERR | 8945 §5.1, §5.2 | TSIG ostatni → przetworzony | TSIG przed OPT; dwa TSIG → FORMERR bez podpisu |
| S2 | Nieznany albo odwołany klucz → NOTAUTH + BADKEY, odpowiedź bez podpisu (MAC Size 0) | 8945 §5.2.1, §5.3.2 | znany klucz → przyjęty | nieznana nazwa; klucz odwołany → BADKEY, MAC pusty |
| S3 | Algorytm inny niż algorytm klucza albo spoza polityki (sha1, md5, sha224, gss-tsig) → BADKEY | 8945 §5.2.1, §6, §7 | sha256/384/512 → przyjęty | ta sama nazwa z sha1; md5 → BADKEY |
| S4 | Błędny MAC → NOTAUTH + BADSIG, bez podpisu | 8945 §5.2.2, §5.3.2 | poprawny MAC → przyjęty | zmieniony bajt MAC; zły sekret; zmieniona treść po podpisie → BADSIG |
| S5 | Kolejność: klucz → MAC → czas → skrócenie | 8945 §5.2 | dobry MAC i zły czas → BADTIME | zły MAC i zły czas → BADSIG (nie BADTIME); nieznany klucz i zły czas → BADKEY |
| S6 | Czas poza ±fudge → BADTIME, podpisany tym samym kluczem; Time Signed = czas klienta; Other Data = czas serwera (6 B); Fudge = fudge klienta; MAC żądania w podpisie | 8945 §5.2.3, §5.3.2 | różnica = fudge → przyjęty | różnica = fudge + 1 → BADTIME; klient weryfikuje odpowiedź |
| S7 | Time Signed starszy niż ostatni przyjęty dla klucza → BADTIME | 8945 §5.2.3 (SHOULD) | ten sam i późniejszy czas → przyjęty | czas wcześniejszy → BADTIME |
| S8 | Rozmiar MAC: > skrót → FORMERR; < max(10, skrót/2) → FORMERR; skrócony dozwolony → BADTRUNC (podpisany), bo polityka wymaga pełnego MAC | 8945 §5.2.2.1, §5.2.4, §7 | pełny MAC → przyjęty | 33 B dla sha256 → FORMERR; 9 B → FORMERR; 16 B zgodne → BADTRUNC (podpisany); 16 B z błędnymi bajtami → BADSIG bez podpisu (F5) |
| S9 | Pole Error w żądaniu ≠ 0 → FORMERR | 8945 §4.2, §5.2 | Error=0 → przyjęty | Error=16 → FORMERR |
| S10 | Podpisane żądanie → podpisana odpowiedź (klient ją weryfikuje); niepodpisane żądanie → odpowiedź bez TSIG | 8945 §5.3 | dnspython jako klient weryfikuje MAC odpowiedzi | żądanie bez TSIG → brak TSIG w odpowiedzi |
| S11 | MAC odpowiedzi nie krótszy niż MAC żądania | 8945 §7 | pełny MAC w odpowiedzi | — (test właściwości dla wszystkich algorytmów) |
| S12 | Ucięta odpowiedź podpisana: pytanie + TSIG, TC=1, NOERROR | 8945 §5.3 | SOA przez UDP z podpisem → TC=1 i poprawny TSIG | brak TSIG w uciętej odpowiedzi = błąd |
| S13 | Nazwy kluczy i algorytmów porównywane bez wielkości liter | 8945 §9; 1034 §3.1 | `KEY.Example.` = `key.example.` | inna nazwa → BADKEY |
| S14 | Okno czasu = min(Fudge żądania, 300 s); BADTIME podaje fudge klienta | 8945 §5.2.3, §10 | Fudge 300, różnica 300 → przyjęty | Fudge 65535, różnica 301 → BADTIME z Fudge 65535 w odpowiedzi |
| S15 | Powtórka (ten sam MAC żądania w oknie) → ta sama odpowiedź, bez skutków ubocznych | 8945 §10 | retransmisja UDP → identyczna odpowiedź | powtórka nie zmienia `client_confirmed_at`, `last_used_at`, nie dodaje audytu |

### 4.3 UPDATE (U)

| ID | Niezmiennik | RFC | P | N |
|---|---|---|---|---|
| U1 | ZOCOUNT ≠ 1 albo ZTYPE ≠ SOA → FORMERR | 2136 §3.1.1 | 1 × SOA → dalej | 0, 2 rekordy; ZTYPE=A → FORMERR |
| U2 | ZCLASS ≠ IN → NOTAUTH | 2136 §3.1.1 | IN → dalej | CH, ANY → NOTAUTH |
| U3 | ZNAME poza naszymi strefami → NOTAUTH | 2136 §3.1.1 | domena z ACME Domains; jej przodek (apex publiczny, wzorzec cert-manager i win-acme) → dalej | obca strefa; potomek domeny; korzeń; TLD → NOTAUTH |
| U4 | UPDATE bez podpisu → REFUSED od razu (przed U1–U3), tylko log aplikacji | 3007 §2, §3; 2136 §3.3.1 | ten sam UPDATE podpisany → NOERROR | bez TSIG → REFUSED, brak audytu, brak zmian; odpowiedź dla strefy z ACME Domains i dla obcej strefy identyczna bajt w bajt (poza ID); 0 zapytań do DB (F6) |
| U5 | Niepusta sekcja prerequisite → REFUSED | 2136 §2.4, §3.3; maintainer | pusta → dalej | każda z 5 form (§2.4.1–§2.4.5) → REFUSED |
| U6 | Klasa RR ∉ {IN, ANY, NONE} → FORMERR | 2136 §3.4.1 | IN, ANY, NONE → dalej | CH → FORMERR |
| U7 | Nazwa RR poza ZNAME → NOTZONE | 2136 §3.4.1 | nazwa w strefie → dalej | dozwolona nazwa poza ZNAME → NOTZONE |
| U8 | Prescan: IN z typem ANY/AXFR/MAILA/MAILB → FORMERR; ANY z TTL≠0 lub RDLENGTH≠0 → FORMERR; NONE z TTL≠0 → FORMERR | 2136 §3.4.1.2 | poprawne formy → dalej | każda forma błędna → FORMERR |
| U9 | Zmieniać można tylko TXT pod `_acme-challenge.<identyfikator>` | 3007 §3, §3.1; 8555 §8.4 | TXT pod nazwą wyzwania → dalej | A pod tą nazwą; TXT pod `foo.<id>`; CNAME → REFUSED |
| U10 | Dodanie wymaga aktywnej wartości w zakresie klucza; porównanie wartości po złączeniu ciągów TXT, dokładne | 3007 §3; 8555 §8.4; 1035 §3.3.14 | dokładna wartość; wartość w 2 ciągach → NOERROR | 1 znak inny; wiersz innego konta proxy; inne konto ACME przy kluczu z EAB; wiersz wygasły; wiersz zamknięty → REFUSED |
| U11 | Usunięcie TXT (klasa NONE i klasa ANY) → NOERROR, bez zmian, także po zakończeniu zamówienia; ANY/ANY → REFUSED | 2136 §2.5.2, §2.5.4, §3.4.2.3–§3.4.2.4; 3007 §3.1; maintainer | NONE TXT, ANY TXT, zamówienie zakończone → NOERROR | ANY/ANY; usunięcie A → REFUSED |
| U12 | Atomowość: jeden zły RR odrzuca całość, bez skutków | 2136 §3.3.2, §3.7 | [usuń ANY TXT, dodaj poprawną] (wzorzec lego/cert-manager) → NOERROR | [usuń, dodaj złą] → REFUSED, brak `client_confirmed_at`, audyt „refused” |
| U13 | Powtórne dodanie tej samej wartości → NOERROR | 2136 §2.5.1 | drugi identyczny UPDATE → NOERROR | — (para z U10 N) |
| U14 | Odpowiedź: ID i opcode skopiowane, QR=1, liczniki sekcji = 0 | 2136 §3.8 | sprawdzenie nagłówka | odpowiedź nigdy nie zawiera sekcji update żądania |
| U15 | Przyjęty UPDATE nie zmienia DNS przez nasłuch; ustawia `client_confirmed_at`, `last_used_at`, audyt | maintainer; 2136 §3.5 (brak stanu do utrwalenia) | przyjęty → pola ustawione, wywołań dostawcy DNS 0 | odrzucony → pola puste |

### 4.4 QUERY i SOA discovery (Q)

| ID | Niezmiennik | RFC | P | N |
|---|---|---|---|---|
| Q1 | SOA dla QNAME = D aktywnego wiersza → NOERROR, AA=1, jeden SOA w ANSWER, właściciel = D, TTL 0, MINIMUM 0 | 8906 §3.1.1; 1034 §4.3.2; 1035 §3.3.13 | aktywny wiersz → SOA (TCP) | brak wiersza; wiersz zamknięty; wiersz wygasły → REFUSED |
| Q2 | Zapytanie SOA podpisane: weryfikacja TSIG, odpowiedź podpisana, zakres klucza | 8945 §5.3; 3007 §3 | wiersz w zakresie → SOA podpisane | wiersz innego konta → REFUSED (podpisane) |
| Q3 | Każde inne zapytanie → REFUSED (polityka) | 1035 §4.1.1 (RCODE 5); maintainer | SOA → odpowiedź | TXT, A, NS pod tą samą nazwą; SOA dla przodka D → REFUSED |
| Q4 | QCLASS ≠ IN → REFUSED | 1035 §4.1.1 | IN → odpowiedź | CH → REFUSED |
| Q5 | Typy meta (AXFR, IXFR, ANY) → REFUSED | 1035 §4.1.1; 8906 §3.1.2 | — | każdy typ meta → REFUSED |
| Q6 | Porównanie nazw bez wielkości liter | 1034 §3.1 | `_ACME-Challenge.Example.COM.` → odpowiedź | inna nazwa → REFUSED |
| Q7 | SOA dla nazwy między D a record_name (włącznie z record_name) → NOERROR, AA=1, ANSWER pusty, SOA(D) w AUTHORITY | 2308 §2.2, §3 | nsupdate: SOA dla `_acme-challenge.<id>` → strefa D; certbot i lego: przejście w górę kończy się na D | nazwa pod D bez aktywnego wiersza → REFUSED |

### 4.5 Wartości oczekiwane (R) i klucze (K)

| ID | Niezmiennik | RFC | P | N |
|---|---|---|---|---|
| R1 | Wartość = base64url(SHA-256(token "." thumbprint)), bez `=` | 8555 §8.1, §8.4; 4648 §5; 7638 §3 | wektor z RFC 7638 §3.1 i tokenem testowym, wynik liczony niezależnie przez `hashlib` | wynik nie zawiera `=`, `+`, `/` |
| R2 | Nazwa rekordu = `_acme-challenge.` + identyfikator bez `*.` | 8555 §7.1.4, §8.4 | `*.example.com` → `_acme-challenge.example.com.` | nigdy `_acme-challenge.*.example.com` |
| R3 | Zapis przy pobraniu authz dla zamówienia i rodzeństwa | 8555 §7.5; #307 | authz `pending` z dns-01 → wiersze dla wszystkich zamówień | authz `valid` (#325); obcy klient (403); brak dns-01 → brak wierszy |
| R4 | Zamknięcie przy `get_certificate` i gdy upstream authz/challenge nie jest `pending`; `expires_at` ≤ utworzenie + 24 h | 8555 §7.1.4 (`expires`), §7.1.6 | po certyfikacie → `closed`; authz `valid` → `closed` | wiersz innego zamówienia bez zmian; authz `expires` za 7 dni → `expires_at` = +24 h |
| R5 | Zakres klucza: konto proxy, opcjonalnie konto ACME z EAB | 3007 §3, §3.1 | pasuje → dozwolone | inne konto proxy; inne konto ACME → niedozwolone |
| R6 | Błąd zapisu wiersza (np. konflikt UNIQUE przy równoległym `get_authz`) nie przerywa `get_authz` i nie cofa `challenges_data` | spójność | dwa równoległe `get_authz` rodzeństwa → oba OK, wiersze bez duplikatów | wymuszony IntegrityError → `get_authz` zwraca authz, stan `initiated` zostaje |
| R7 | Wiersz rodzeństwa ma thumbprint i `account_id` rodzeństwa; zamówienie bez thumbprintu nie ma wiersza | 8555 §8.1; #307 | 2 konta, wspólny authz → 2 wiersze z różnymi wartościami | zamówienie z `client_jwk_thumbprint` NULL → brak wiersza |
| K1 | Sekret z CSPRNG, długość = wyjście skrótu (32/48/64 B) | 8945 §8 | długości dla 3 algorytmów | dwa klucze nigdy nie mają tego samego sekretu (1000 prób) |
| K2 | Sekret zaszyfrowany w DB | maintainer | wartość w DB ≠ jawny tekst, odczyt przez model = jawny tekst | zły klucz master → brak odczytu |
| K3 | Sekret zwracany tylko przy utworzeniu | maintainer | POST zwraca sekret | GET listy i GET klucza nie zwracają sekretu |
| K4 | Algorytmy: tylko sha256/384/512, w trybie FIPS i poza nim | 8945 §6, §7; maintainer | 3 algorytmy → 201 | md5, sha1, sha224 → 400 |
| K5 | Nazwa klucza: poprawna nazwa DNS ≤ 255 B, unikalna bez wielkości liter | 8945 §4.2; 1035 §2.3.4 | poprawna → 201 | duplikat innej wielkości liter; etykieta > 63 B → 400 |
| K6 | Domyślnie brak uprawnień: nowy klucz bez wierszy nic nie zmienia | 3007 §3 | — | dodanie z nowym kluczem bez wierszy → REFUSED |
| K7 | Sekret nieodszyfrowany albo pusty → klucz nieznany (BADKEY), nigdy pusty klucz HMAC | maintainer; 8945 §5.2.1 | poprawny sekret → przyjęty | zły klucz szyfrowania DB; pusty sekret; HMAC z pustym kluczem → BADKEY |
| K8 | Klucz z EAB: brak dopasowania, gdy EAB usunięte, nieużyte, `used_by_account_id` NULL albo wiersz z `account_id` NULL | 3007 §3 (domyślnie brak) | EAB `used`, to samo konto → NOERROR | każdy z 4 przypadków → REFUSED; usunięcie EAB usuwa klucz (SQLite) |
| K9 | Klucz konta proxy usuniętego albo z `proxy_enabled = false` → BADKEY | 3007 §3 | konto aktywne → przyjęty | konto usunięte (SQLite, bez FK); proxy wyłączone → BADKEY; nowe konto z tym samym ID nie dziedziczy klucza |

### 4.6 Serwer, logi, bezpieczeństwo (N)

| ID | Niezmiennik | Podstawa | P | N |
|---|---|---|---|---|
| N1 | Port: najpierw env `UCM_DNS_UPDATE_PORT`, potem ustawienie; 0 = wyłączony; domyślnie 0 | maintainer | env 8053 → nasłuch | brak env i ustawienia → brak nasłuchu; wartość błędna → 0 i ostrzeżenie |
| N2 | API: port 0 albo 1024–65535, inny niż HTTPS i port protokołów HTTP | maintainer (bez CAP_NET_BIND_SERVICE) | 8053 → 200 | 53, 70000, port HTTPS → 400 |
| N3 | Błąd bind nie zatrzymuje aplikacji | wzorzec serwera HTTP | wolny port → nasłuch | zajęty port → log błędu, aplikacja działa |
| N4 | Limity: globalny token bucket, limit na IP w LRU, Pool greenletów, limit połączeń TCP, czas zapisu i życia połączenia | 7766 §6.2.2, §6.2.3; bezpieczeństwo (F1) | ruch w limicie → odpowiedzi | ruch ponad limit → brak odpowiedzi; 10 000 adresów IP → rozmiar LRU ≤ limit; liczba greenletów ≤ Pool |
| N5 | Brak rekursji i brak ruchu wychodzącego z handlera | maintainer; 8906 §3.1.3.1 | — | test z zablokowanym `socket.connect`: żadne wywołanie |
| N6 | Audyt: przyjęte i odrzucone żądania z TSIG; log aplikacji: bez podpisu i błędne | maintainer | żądanie z TSIG → wpis audytu | bez TSIG; błędne → brak wpisu audytu |
| N7 | Limit wpisów audytu na (IP, powód) | bezpieczeństwo (ochrona tabeli audytu) | pierwszy BADKEY → wpis | 100 BADKEY z tego samego IP w 60 s → 1 wpis + log |
| N8 | Ruch bez podpisu (SOA, UPDATE) i BADKEY nie wykonuje zapytań do DB | bezpieczeństwo (F1) | — | 1000 zapytań SOA bez podpisu i 1000 BADKEY → 0 zapytań SQL (licznik zdarzeń SQLAlchemy) |
| N9 | Liczniki nagłówka poza limitem albo długość > MAX_MSG → brak odpowiedzi, bez pełnego parsowania | bezpieczeństwo (F1) | liczniki w limicie → przetworzone | ARCOUNT=1000; QDCOUNT=2 dla QUERY (FORMERR po kontroli M5); 4097 B → brak odpowiedzi |
| N10 | Wyjątek (np. DB) → SERVFAIL albo brak odpowiedzi; serwer działa dalej | 1035 §4.1.1 (SERVFAIL); 2136 §3.4.2.1 | — | wymuszony wyjątek DB → SERVFAIL; następne zapytanie → poprawna odpowiedź |
| N11 | Sekret i MAC nigdy w logach i audycie | bezpieczeństwo (F11) | — | cały zestaw testów z caplog na DEBUG: brak sekretu (base64) i MAC (hex, base64) w logach |
| N12 | Globalny limit wpisów audytu na powód (niezależnie od IP) + jeden wpis zbiorczy | bezpieczeństwo (F7) | pierwsze N wpisów → zapisane | 1000 BADKEY z 1000 losowych IP → ≤ N wpisów + 1 zbiorczy |
| N13 | Audyt ma adres klienta i nazwę `dns-update:<nazwa klucza>` albo `dns-update:unauthenticated`; nazwy z pakietu są skracane i oczyszczane | bezpieczeństwo (F7) | przyjęty UPDATE → IP i nazwa klucza w audycie | nazwa 255 B ze znakami sterującymi → skrócona, bez znaków sterujących; nigdy `system` |

## 5. Miejsca, w których uzgadniam wymagania maintainera z RFC

| # | Wymaganie maintainera | Problem | Decyzja i uzasadnienie |
|---|---|---|---|
| 1 | „answer unsigned SOA queries … refuse every other query” | nsupdate (acme.sh bez `NSUPDATE_ZONE`, Posh-ACME z `DDNSNameserver`) **podpisuje** zapytanie SOA, gdy ma klucz, a odpowiedź bez podpisu jest dla niego błędem krytycznym (sekcja 9). RFC 8945 §5.3 wymaga podpisanej odpowiedzi na podpisane żądanie | Odpowiadam na SOA bez podpisu i z podpisem. Zapytanie podpisane dostaje podpisaną odpowiedź i zakres klucza. **Wymaga zgody maintainera (F14), patrz sekcja 11** |
| 2 | „No response larger than the request” | Odpowiedź SOA jest zawsze dłuższa niż zapytanie. lego i cert-manager powtarzają przez TCP po TC=1, certbot pyta najpierw przez TCP, ale **nsupdate nie obsługuje TC** i pyta przez UDP (sekcja 9) | Reguła obowiązuje dla UDP bez poprawnego TSIG (T1): tylko taki ruch można sfałszować (podrobiony adres źródłowy). Żądanie z poprawnym TSIG (MAC zweryfikowany, czas w oknie, S7 blokuje starsze, S15 obsługuje powtórki) dostaje zwykły limit RFC: max(512, EDNS) (T2). Współczynnik dla podpisanego SOA ≈ 1,25. TCP bez limitu (handshake). **Wymaga zgody maintainera (F14), patrz sekcja 11** |
| 3 | „Always answer NOERROR, even when the order is gone” | RFC 2136 §3.1.1 sprawdza strefę przed usunięciem. Strefa zależna od aktywnych zamówień dałaby NOTAUTH | Strefa zależy od ACME Domains, nie od zamówień (sekcja 2.3) |
| 4 | „A non-empty prerequisite section gets REFUSED” | RFC 2136 §3.2 ocenia prerequisite przed §3.3 | Nasza strefa nie ma stanu, względem którego można ocenić prerequisite. Odmowa jest polityką (§3.3.1 „implementation dependent”) |
| 5 | Algorytmy „nothing weaker than SHA-256” | RFC 8945 §6: implementacja MUSI mieć hmac-sha1 | §7 pozwala lokalnej polityce odrzucić algorytm. sha1 → BADKEY |
| 6 | Odpowiedzi BADTIME | dnspython podpisuje czasem serwera, a RFC 8945 §5.2.3 wymaga czasu klienta w Time Signed | Własna budowa TSIG dla BADTIME przez publiczne `dns.tsig.sign` |
| 7 | „Use dnspython … do not hand-roll HMAC” | `dns.tsig.validate` sprawdza czas przed MAC; RFC 8945 §5.2 wymaga: klucz, MAC, czas | Wywołuję `dns.tsig.validate` z `now = time_signed` (czas zawsze OK), potem sprawdzam czas sam. HMAC liczy dnspython. Sprawdzone prototypem na dnspython 2.8.0 (`spike/tsig_spike.py` w tym katalogu) |
| 8 | SOA „for names covered by a pending proxy order” | Który apex ogłaszać? Apex = nazwa rekordu psuje precheck lego (szuka NS dla fałszywej strefy). REFUSED dla nazwy rekordu zatrzymuje nsupdate | Apex = D (sekcja 2.3). SOA w ANSWER dla D, NODATA z SOA w AUTHORITY dla nazw od D do nazwy rekordu (Q1, Q7). Pasuje do certbot, lego i nsupdate (sekcja 9) |
| 9 | RFC 8945 §5.2.3 (SHOULD): odrzucać Time Signed starszy niż ostatni dla klucza | cert-manager wysyła kilka UPDATE równolegle (kilka nazw w certyfikacie). Pakiety UDP mogą przyjść w innej kolejności, więc jeden dostanie BADTIME | Implementuję zalecenie dosłownie (S7). Znacznik zmienia się dopiero po pozytywnym sprawdzeniu MAC i czasu. Retransmisje obsługuje pamięć powtórek (S15). cert-manager ponawia wyzwanie po błędzie. Sprawdzę to w E2E |
| 10 | UPDATE bez podpisu | RFC 2136 §3 sprawdza strefę (NOTAUTH) przed uprawnieniami (§3.3), co pozwala bez klucza sprawdzić, które domeny są w ACME Domains (F6) | REFUSED od razu po parsowaniu. RFC 3007 §2: „TSIG or SIG(0) records MUST be included in all secure dynamic update messages”; RFC 2136 §3.3.1: uprawnienia „in an implementation dependent fashion”. Żaden klient nie wysyła UPDATE bez podpisu |
| 11 | NOTIMP i FORMERR dla wiadomości z TSIG | RFC 8945 §5.2: „the server is REQUIRED to return a TSIG RR in the response” | FORMERR: wiadomość, której nie da się zinterpretować (§5.2, „cannot be interpreted”). NOTIMP: nieznanego opcode nie parsujemy dalej niż nagłówek (RFC 8906 §7), więc nie ma czym podpisać. Świadome odstępstwo, bez wpływu na bezpieczeństwo (F15) |
| 12 | Fudge | RFC 8945 §5.2.3 używa fudge z żądania (do 65535 s). §10: „A Fudge value that is too large may leave the server open to replay attacks” | Okno = min(fudge, 300 s). BADTIME podaje fudge klienta (§5.2.3). Wszyscy klienci używają 300 s (sekcja 9) (F9) |
| 13 | Treść SOA | Nazwa hosta, e-mail albo znacznik czasu ujawniałyby więcej niż zgodził się maintainer (F12) | Stałe wartości (sekcja 3.1) |

## 6. Bezpieczeństwo (do security review)

| Zagrożenie | Ochrona |
|---|---|
| Zapis dowolnego rekordu w DNS | Nasłuch nie zapisuje nic w DNS. Dodanie przechodzi tylko dla TXT `_acme-challenge` z wartością równą oczekiwanej |
| Podszycie się pod innego klienta | Wartość zależy od thumbprintu klienta (RFC 8555 §8.1). Zakres klucza = konto proxy, opcjonalnie konto ACME z EAB |
| Kradzież sekretu z DB | Szyfrowanie Fernet jak HMAC EAB (zawsze włączone), sekret pokazany raz; sekret nieodszyfrowany = BADKEY (K7) |
| Rozszerzenie zakresu klucza | Zasada „domyślnie brak” dla EAB i kont proxy, usuwanie kluczy w kodzie, bo SQLite nie wymusza FK (K8, K9) |
| Wyrocznia podpisu (BADTRUNC) | MAC skrócony jest sprawdzany przed odpowiedzią podpisaną (krok 6d) |
| Sekret w logach | Zakaz logowania `dns.tsig.Key`, keyring i `Message.to_text()`; tylko nazwa klucza, kod, adres (N11) |
| Powtórzenie żądania (replay) | Okno ±min(fudge, 300 s) (S14), ostatni Time Signed na klucz (S7), pamięć powtórek wg MAC żądania (S15). Operacje są idempotentne |
| Amplifikacja UDP | Bez poprawnego TSIG: odpowiedź ≤ żądanie, inaczej TC=1 (T1). Z poprawnym TSIG: limit RFC (T2); sfałszować się nie da bez sekretu, powtórkę ogranicza okno fudge i S7 |
| Zalanie procesu, DB i audytu | Sekcja 2.4: Pool, globalny token bucket, LRU na IP, kontrola nagłówka, pamięć podręczna (0 zapytań DB dla ruchu bez podpisu i BADKEY, N8), limity audytu na IP i globalne (N7, N12), audyt po decyzji w osobnej transakcji |
| Rozpoznanie domen bez klucza | UPDATE bez podpisu → REFUSED przed sprawdzeniem strefy (U4, F6) |
| Wyciek nazw aktywnych wyzwań | SOA bez podpisu ujawnia D i nazwy z aktywnymi wyzwaniami (wymaganie maintainera), nic więcej (stałe SOA, F12). Wiersze aktywne maks. 24 h (R4). Nasłuch na osobnym adresie (`UCM_DNS_UPDATE_HOST`), osobny Service w Helm (ClusterIP), dokumentacja: tylko sieć wewnętrzna (F8) |
| Slow-read TCP | Limit bezczynności od pełnej wiadomości (T5), czas zapisu, maks. czas życia, limit połączeń (2.4) |
| Porównanie MAC w czasie stałym | `hmac.compare_digest` (dnspython) |
| Uprawnienia procesu | Port nieuprzywilejowany, bez CAP_NET_BIND_SERVICE |

## 7. Pozostałe części PR 2

- **Uruchomienie:** w `post_worker_init` (gunicorn, `workers = 1`), obok serwera HTTP protokołów; w trybie dev w `app.py main()`. Serwery gevent `DatagramServer` i `StreamServer` z `spawn=Pool(N)` (sekcja 2.4). Adres: `UCM_DNS_UPDATE_HOST` (domyślnie `HOST`). Zmiana portu wymaga restartu (jak port HTTP protokołów).
- **Zmiany w istniejącym kodzie:** handler DELETE poświadczenia EAB usuwa powiązane klucze (K8); `_remove_account_row` usuwa klucze i wiersze konta (K9); `AuditService.log_action` dostaje opcjonalny parametr `ip_address` (N13); `get_authz`, `respond_challenge`, `get_certificate` zapisują i zamykają wiersze (R3, R4).
- **API:**
  - `GET/POST /api/v2/acme/client/accounts/<id>/dns-update-keys` (`read:acme` / `write:acme`)
  - `DELETE /api/v2/acme/client/accounts/<id>/dns-update-keys/<key_id>` (`delete:acme`; aktywny → odwołanie, odwołany → usunięcie, jak EAB)
  - `dns_update_port` w `/api/v2/acme/client/settings` (GET/PATCH)
- **UI:** sekcja „Klucze DNS UPDATE (RFC 2136)” w karcie konta proxy (`CaAccountsManager.jsx`). Okno „pokaż raz” z sekretem i gotowymi fragmentami: plik klucza BIND (nsupdate, acme.sh, Posh-ACME), Secret i ClusterIssuer dla cert-manager, plik ini certbot. Pole portu w sekcji proxy (`LetsEncryptTab.jsx`). Pomoc kontekstowa. Teksty w 9 językach (`npm run check:i18n`).
- **Pakiety:** Dockerfile `EXPOSE 8053/udp 8053/tcp`; `docker/entrypoint.sh` sprawdza `UCM_DNS_UPDATE_PORT` (0 albo 1024–65535, inny niż inne porty). Helm: `dnsUpdate.enabled` (domyślnie false), `dnsUpdate.port` (8053), **osobny Service** (`dnsUpdate.service.type`, domyślnie ClusterIP, port 53 → 8053, UDP i TCP), opcjonalna NetworkPolicy, zmienna env. Dokumentacja: SNAT kube-proxy może połączyć limity na IP w jeden. DEB i RPM: bez zmian w unitach.
- **Dokumentacja:** `docs/ADMIN_GUIDE.md` (nowa sekcja, uwaga o sieci wewnętrznej, mapowanie portu 53), `examples/kubernetes/cert-manager/clusterissuer-ucm-proxy-rfc2136.yaml`, `docs/testing/ACME-PROXY-DNS-UPDATE.md` (testy ręczne i E2E), CHANGELOG.

## 8. Testy end-to-end z prawdziwymi klientami

Środowisko w kontenerze (bez internetu do CA):

| Element | Rola | Skąd |
|---|---|---|
| Pebble | Fałszywy zewnętrzny CA (upstream proxy) | `go install github.com/letsencrypt/pebble/v2/cmd/pebble` |
| pebble-challtestsrv | Fałszywy DNS dla Pebble, API HTTP do ustawiania TXT | jw. |
| Dostawca DNS w UCM | `custom_command` → skrypt, który woła API challtestsrv | istniejący dostawca UCM |
| UCM | gunicorn z prawdziwym `post_worker_init` | repozytorium |

Klienci i scenariusze (każdy z testem negatywnym):

| Klient | Jak uruchomiony | P | N |
|---|---|---|---|
| acme.sh + `dns_nsupdate` | `nsupdate` z pakietu bind9-dnsutils | certyfikat wydany; wariant z `NSUPDATE_ZONE` i bez | zły sekret → BADSIG, brak certyfikatu |
| certbot + `certbot-dns-rfc2136` | pip | certyfikat wydany | klucz innego konta proxy → REFUSED |
| lego `--dns rfc2136` | `go install` | certyfikat wydany | klucz odwołany → BADKEY |
| cert-manager v1.21.3 | Kod `pkg/issuer/acme/dns/rfc2136` w programie testowym Go: Present/CleanUp z `ResolvedZone` = D (tak robi kontroler po `FindZoneByFqdn`). Pełny klaster kind tylko, gdy uda się uruchomić dockerd | Present i CleanUp → NOERROR, UDP i TCP | wartość innego konta → REFUSED; algorytm HMACMD5 (domyślny!) → BADKEY |
| Posh-ACME | Polecenia `nsupdate` w formie z `RFC2136.ps1` (pwsh niedostępny), z `DDNSZone` i bez | NOERROR | zły klucz → BADKEY |
| win-acme | Odtworzenie wiadomości w dnspython wg kodu (ZNAME od domeny rejestrowalnej w dół, pełny MAC, UDP potem TCP) | NOERROR przy pierwszym ZNAME | zły ZNAME → NOTAUTH (win-acme idzie dalej) |

Ustawienia klientów w E2E: brak dostępu do publicznego DNS, dlatego: acme.sh `--dnssleep 1`, lego `--dns.propagation-wait 1s`, certbot `--dns-rfc2136-propagation-seconds 1`. Te same ustawienia trafią do dokumentacji (PR 1).

## 9. Zachowanie klientów (z kodu źródłowego)

Źródła i wersje: nsupdate z BIND 9.18.39, acme.sh @37d064f7, certbot-dns-rfc2136 5.8.0, lego v4.35.2, cert-manager v1.21.3, Posh-ACME @392c2e76, win-acme @c213e6dc z ARSoft.Tools.Net 3.6.0. Kluczowe fakty sprawdziłem ponownie w źródłach (nsupdate `sendrequest`, certbot `_query_soa`).

| Klient | Zapytanie SOA: dokąd, podpis, TC | Wymagania wobec odpowiedzi SOA | UPDATE dodanie | UPDATE usunięcie | Podpis odpowiedzi wymagany | Domyślny algorytm |
|---|---|---|---|---|---|---|
| nsupdate (`server` ustawiony) | do UCM, **podpisane** gdy jest klucz, UDP, **TC ignorowane** | NOERROR/NXDOMAIN; SOA w ANSWER, potem AUTHORITY; dowolny właściciel; AA nieważne | jak w skrypcie | ANY (bez danych) albo NONE (z danymi) | **tak** (brak podpisu = błąd krytyczny) | hmac-md5, gdy plik klucza nie podaje |
| acme.sh `dns_nsupdate` | przez nsupdate; brak, gdy `NSUPDATE_ZONE` | jak nsupdate | IN, TTL 60, 1 ciąg, UDP | **ANY TXT** (cały RRset) | tak | z pliku klucza |
| certbot-dns-rfc2136 | do UCM, TCP potem UDP, podpis tylko z `sign_query` | NOERROR, SOA w ANSWER, właściciel = QNAME, **AA=1**; inaczej następna nazwa w górę | IN, TTL 120, tylko TCP | NONE (jeden RR) | nie (sprawdza, gdy jest) | **HMAC-MD5** |
| lego | do UCM (chyba że `DNSUPDATE_ZONES`), bez podpisu, UDP → **TCP przy TC** | NOERROR, SOA w ANSWER; NXDOMAIN/NODATA → wyżej; inny kod = błąd | **[ANY TXT, potem IN]** w jednej wiadomości, TTL 120, UDP | NONE | nie | **hmac-sha1** |
| cert-manager | **do resolverów rekurencyjnych** (`--dns01-recursive-nameservers`), nie do UCM | — | IN, TTL 60, UDP albo TCP (pole `protocol`) | NONE | nie | **HMACMD5** |
| Posh-ACME | przez nsupdate; brak, gdy `DDNSZone` | jak nsupdate | TTL 60 | NONE | tak | z parametru |
| win-acme | **brak SOA**: próbne UPDATE od domeny rejestrowalnej w dół, aż NOERROR | — | IN, TTL 60, pełny MAC, UDP potem TCP | NONE | nie | md5, gdy nazwa nieznana |

Wnioski dla serwera (wszystkie są już w planie):

1. Podpisane SOA musi dostać podpisaną odpowiedź (decyzja 1, Q2).
2. nsupdate nie obsługuje TC, więc podpisane SOA przez UDP musi zmieścić się w 512 B bez ucięcia (decyzja 2, T2).
3. Apex = D: SOA w ANSWER dla D (certbot, lego), NODATA z SOA w AUTHORITY dla nazwy rekordu (nsupdate) (decyzja 8, Q1, Q7).
4. Obie formy usunięcia: ANY TXT (acme.sh, lego przed dodaniem) i NONE (pozostali) (U11, U12).
5. Zły ZNAME → kod inny niż NOERROR, bo win-acme na tej podstawie szuka strefy (U3).
6. Wszystkie odpowiedzi na podpisane żądania są podpisane (S10).

Wnioski dla dokumentacji (PR 1 i PR 2):

- Domyślne algorytmy klientów to md5 albo sha1. UCM je odrzuca (BADKEY). Każdy przykład konfiguracji ustawia **hmac-sha256**.
- win-acme: błąd w kodzie — `--serverport` staje się limitem czasu w ms, port docelowy jest zawsze 53. UCM musi być dostępny na porcie 53 (mapowanie portu). Błąd ARSoft: hmac-sha384 liczy się jak sha256 — nie używać sha384.
- Posh-ACME: wymagany `DDNSNameserver` (bez niego nsupdate wysyła UPDATE na MNAME, port 53).
- cert-manager i lego: wykrywanie strefy (cert-manager) i precheck (lego, cert-manager, acme.sh) używają publicznego albo rekurencyjnego DNS. Bez dostępu do niego: lego `DNSUPDATE_ZONES` i `--dns.propagation-wait`, acme.sh `--dnssleep`, cert-manager `--dns01-recursive-nameservers` wskazujący resolver, który widzi strefę.

## 10. Kolejność pracy i podział na części

| # | Część | Zależy od | Wykonawca |
|---|---|---|---|
| 0 | Gałęzie na bazie `upstream/dev` | — | główna sesja |
| 1 | PR 1: dokumentacja | 0 | implementer |
| 2 | Modele, migracja 111, manifest kopii, testy migracji | 0 | implementer |
| 3 | `tsig.py` + testy S1–S13 | 0 | implementer, przegląd szczegółowy w głównej sesji |
| 4 | `records.py`, hak w proxy + testy R1–R5 | 2 | implementer |
| 5 | `keys.py`, `policy.py`, `handler.py` + testy M, E, U, Q, K6 | 2, 3, 4 | implementer |
| 6 | `server.py`, start, ustawienia + testy T, N | 5 | implementer |
| 7 | API, audyt + testy K1–K5, N2, N6, N7 | 2, 5 | implementer |
| 8 | UI, pomoc, 9 języków | 7 | implementer |
| 9 | Pakiety, Helm, dokumentacja, CHANGELOG | 6 | implementer |
| 10 | E2E z klientami | 6, 7 | główna sesja |
| 11 | 3 × `/code-review`, 3 × `/security-review`, poprawki | 1–10 | główna sesja |

Implementer: agent Sonnet 5.5, wysiłek medium (preferencja użytkownika). Kod bezpieczeństwa (części 3, 5, 6) dostaje dokładną specyfikację z tego planu. Każdy wynik czytam w diffie i uruchamiam pełny zestaw testów.

Polecenia walidacji:
- `cd backend && python -m pytest tests/ -q -n auto --dist loadfile`
- `cd frontend && npx vitest run && npm run check:i18n`
- testy PostgreSQL (`-m postgres`), gdy uda się uruchomić PostgreSQL lokalnie

## 11. Security review planu (2026-10-24)

Niezależny agent `reviewer` sprawdził plan w wersji 2. Wszystkie ustalenia przyjąłem. Dwa twierdzenia sprawdziłem sam w kodzie (`eab.py`: trwałe usunięcie używanego EAB; brak `PRAGMA foreign_keys=ON` w czasie działania).

| ID | Waga | Problem | Zmiana w planie |
|---|---|---|---|
| F1 | wysoka | Ruch UDP bez podpisu (także z podrobionych adresów) blokuje jedyny worker gevent przez zapytania DB | sekcja 2.4; N4, N8–N10 |
| F2 | wysoka | Klucz z EAB rozszerza zakres po usunięciu EAB (SQLite bez FK, `None == None`) | 2.1, 2.3; K8 |
| F3 | średnia | Klucze zostają po usunięciu konta proxy (SQLite bez FK) | 2.1, 2.3, 7; K9 |
| F4 | średnia | Sekret może trafić do DB jawnie; błąd odszyfrowania może dać pusty klucz HMAC | 2.1, 2.3; K7 |
| F5 | średnia | BADTRUNC nieosiągalne przez `dns.tsig.validate`; naiwna poprawka = wyrocznia podpisu | krok 6d i 6g; S8 |
| F6 | średnia | UPDATE bez podpisu ujawnia domeny z ACME Domains (NOTAUTH vs REFUSED) | 3.2; U4; decyzja 10 |
| F7 | średnia | Zalanie audytu z losowych IP; audyt przypisany do `system`; commit audytu łamie atomowość | krok 11; N12, N13 |
| F8 | średnia | Brak własnego adresu nasłuchu; wspólny Service w Helm | 2.4, 7 |
| F9 | niska | Okno powtórki zależne od klienta (fudge do 65535 s) | krok 6e–6f; S14, S15; decyzja 12 |
| F10 | niska | `make_response` dodaje dopełnienie EDNS | krok 9; E5 |
| F11 | niska | `Key.__repr__` i `Message.to_text()` pokazują sekret i MAC | sekcja 6; N11 |
| F12 | niska | Treść SOA nieokreślona | 3.1; decyzja 13 |
| F13 | niska | Wyścig przy zapisie wiersza, pola rodzeństwa, para (nazwa, wartość), wiersze aktywne przez dni | 2.2, 2.3; R4, R6, R7 |
| F14 | niska | Odstępstwa od dosłownych wymagań maintainera (decyzje 1, 2) bez jego zgody | komentarz do issue #416 (poniżej), przed scaleniem PR 2 |
| F15 | info | NOTIMP bez TSIG; strefa przyjmuje sufiksy publiczne | decyzja 11; reguła strefy bez zmian (brak skutków) |

**F14 – zgoda maintainera.** Decyzje 1 i 2 zmieniają dosłowne brzmienie wymagań. Nie mam dostępu do issue w upstream, więc przygotowuję komentarz do wysłania przez użytkownika ([`maintainer-comment-416.md`](maintainer-comment-416.md)). Praca nad PR 2 idzie dalej. Gdy maintainer się nie zgodzi, zmiana dotyczy tylko kroku 10 i sekcji 3.1 (Q2).
