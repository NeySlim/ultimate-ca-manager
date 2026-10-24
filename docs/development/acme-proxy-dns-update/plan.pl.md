# Plan: nasłuch DNS UPDATE (RFC 2136) dla proxy ACME w UCM

Status: wersja robocza 2 (z raportem o klientach). Przed security review.

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
| `acme_client_account_id` | FK do `acme_client_accounts` (konto proxy, slug), `ON DELETE CASCADE` |
| `eab_credential_id` | FK do `acme_eab_credentials`, NULL = brak powiązania |
| `name` | Nazwa klucza jako nazwa DNS, absolutna, małe litery, unikalna (RFC 8945 §4.2) |
| `algorithm` | `hmac-sha256` (domyślnie), `hmac-sha384`, `hmac-sha512` |
| `secret` | Sekret szyfrowany kluczem master (wzorzec `AcmeClientAccount._eab_hmac_key`, kolumna dopisana do `MASTER_KEY_COLUMNS`) |
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

1. Klient pobiera authz (`get_authz`). Dla każdego wyzwania `dns-01` w stanie `pending` UCM zapisuje wiersz dla zamówienia klienta **i dla zamówień rodzeństwa** (te same upstream authz, #307). Zapis jest idempotentny i nie zależy od tego, czy automatyka DNS już ruszyła.
2. Wiersz jest „aktywny”, gdy: `status = pending`, `expires_at > teraz`, zamówienie ma `status = pending`.
3. `get_certificate` zamyka wiersze zamówienia (`status = closed`).
4. Wiersze starsze niż `expires_at + 7 dni` są usuwane przy kolejnym zapisie.

### 2.3 Strefy „autorytatywne” i zakres klucza

- **Domena D wiersza** = domena z „ACME → Domains”, którą wybiera istniejąca funkcja `find_provider_for_domain(identifier)` (najbardziej szczegółowe dopasowanie, bez `*.`). Tę samą domenę UCM używa dziś do wyboru dostawcy DNS. D jest apexem strefy, który UCM ogłasza w odpowiedziach SOA.
- **Strefa jest nasza** (RFC 2136 §3.1.1), gdy ZNAME jest domeną z „ACME → Domains” albo jej przodkiem (bez korzenia i bez nazw jednoetykietowych). Przodek jest potrzebny, bo cert-manager bierze apex z publicznego DNS, a win-acme zaczyna od domeny rejestrowalnej (sekcja 9). Prawdziwa strefa, do której pisze dostawca DNS UCM, to D albo przodek D. Ta reguła nie zależy od aktywnych zamówień. Dzięki temu usunięcie rekordu po zakończeniu zamówienia dostaje NOERROR, jak chce maintainer.
- **Zakres klucza** (RFC 3007 §3): wiersz pasuje do klucza, gdy `row.acme_client_account_id = key.acme_client_account_id`, a gdy klucz ma powiązane EAB, także `row.account_id = eab.used_by_account_id`.

## 3. Kolejność przetwarzania wiadomości

Każdy krok ma numer niezmiennika z sekcji 4.

```
1. Długość < 12 B → brak odpowiedzi (M2). QR=1 → brak odpowiedzi (M1).
2. UDP: datagram > MAX_MSG → brak odpowiedzi (N4).
3. Opcode ∉ {QUERY, UPDATE} → NOTIMP, sam nagłówek (M3).
4. Parsowanie dnspython (keyring=False, bez weryfikacji) → błąd → FORMERR (M4, S1, E2).
5. TSIG obecny → kolejność RFC 8945 §5.2:
   a. pole Error ≠ 0 albo TSIG nie na końcu / więcej niż jeden → FORMERR (S1, S9)
   b. klucz nieznany, odwołany, algorytm ≠ algorytm klucza lub spoza polityki → NOTAUTH/BADKEY, bez podpisu (S2, S3)
   c. rozmiar MAC > długość skrótu albo < max(10, połowa) → FORMERR (S8)
   d. MAC błędny → NOTAUTH/BADSIG, bez podpisu (S4)
   e. czas poza ±fudge albo starszy niż ostatni przyjęty dla klucza → NOTAUTH/BADTIME, podpisany (S6, S7)
   f. MAC skrócony (w dozwolonym zakresie) → NOTAUTH/BADTRUNC, podpisany (S8)
6. EDNS: wersja > 0 → BADVERS z OPT wersji 0 (E3).
7. QUERY → sekcja 3.1. UPDATE → sekcja 3.2.
8. Odpowiedź: ID i opcode skopiowane, QR=1, RD skopiowany, RA=0, Z=0 (M6–M8).
   Podpisana, gdy żądanie było podpisane i poprawne (S10). OPT, gdy żądanie miało OPT (E1).
9. UDP, żądanie bez poprawnego TSIG: odpowiedź dłuższa niż żądanie → odpowiedź minimalna z TC=1 (T1).
   UDP, żądanie z poprawnym TSIG: limit max(512, rozmiar EDNS); powyżej → TC=1 z TSIG (T2, S12).
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

Dlaczego tak (sekcja 9): certbot i lego idą od `_acme-challenge.<id>` w górę i potrzebują SOA w ANSWER na apexie. nsupdate pyta tylko o nazwę rekordu i przyjmuje SOA z AUTHORITY. Odpowiedź REFUSED na nazwę rekordu zatrzymałaby nsupdate.

### 3.2 UPDATE (kolejność RFC 2136 §3)

```
ZOCOUNT ≠ 1 albo ZTYPE ≠ SOA → FORMERR                (U1, §3.1.1)
ZCLASS ≠ IN → NOTAUTH                                 (U2, §3.1.1)
ZNAME nie jest naszą strefą → NOTAUTH                  (U3, §3.1.1)
brak podpisu TSIG → REFUSED                            (U4, RFC 3007 §3, RFC 2136 §3.3)
sekcja prerequisite niepusta → REFUSED                 (U5, polityka §3.3, wymaganie maintainera)
dla każdego RR (sprawdzenie uprawnień, §3.3):
    typ ≠ TXT albo nazwa nie zaczyna się od "_acme-challenge." → REFUSED (U9)
    dodanie: wartość ≠ aktywna wartość w zakresie klucza → REFUSED (U10)
    usunięcie klasy ANY typu ANY → REFUSED (U11)
prescan (§3.4.1): klasa ∉ {IN, ANY, NONE} → FORMERR; nazwa poza ZNAME → NOTZONE;
    reguły TTL/RDLENGTH/typów meta → FORMERR       (U6–U8)
zastosowanie: bez zmiany DNS (UCM publikuje rekord sam, jak dziś); zapis client_confirmed_at,
    last_used_at klucza, audyt                     (U12, U13, U15)
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
| S8 | Rozmiar MAC: > skrót → FORMERR; < max(10, skrót/2) → FORMERR; skrócony dozwolony → BADTRUNC (podpisany), bo polityka wymaga pełnego MAC | 8945 §5.2.2.1, §5.2.4, §7 | pełny MAC → przyjęty | 33 B dla sha256 → FORMERR; 9 B → FORMERR; 16 B → BADTRUNC |
| S9 | Pole Error w żądaniu ≠ 0 → FORMERR | 8945 §4.2, §5.2 | Error=0 → przyjęty | Error=16 → FORMERR |
| S10 | Podpisane żądanie → podpisana odpowiedź (klient ją weryfikuje); niepodpisane żądanie → odpowiedź bez TSIG | 8945 §5.3 | dnspython jako klient weryfikuje MAC odpowiedzi | żądanie bez TSIG → brak TSIG w odpowiedzi |
| S11 | MAC odpowiedzi nie krótszy niż MAC żądania | 8945 §7 | pełny MAC w odpowiedzi | — (test właściwości dla wszystkich algorytmów) |
| S12 | Ucięta odpowiedź podpisana: pytanie + TSIG, TC=1, NOERROR | 8945 §5.3 | SOA przez UDP z podpisem → TC=1 i poprawny TSIG | brak TSIG w uciętej odpowiedzi = błąd |
| S13 | Nazwy kluczy i algorytmów porównywane bez wielkości liter | 8945 §9; 1034 §3.1 | `KEY.Example.` = `key.example.` | inna nazwa → BADKEY |

### 4.3 UPDATE (U)

| ID | Niezmiennik | RFC | P | N |
|---|---|---|---|---|
| U1 | ZOCOUNT ≠ 1 albo ZTYPE ≠ SOA → FORMERR | 2136 §3.1.1 | 1 × SOA → dalej | 0, 2 rekordy; ZTYPE=A → FORMERR |
| U2 | ZCLASS ≠ IN → NOTAUTH | 2136 §3.1.1 | IN → dalej | CH, ANY → NOTAUTH |
| U3 | ZNAME poza naszymi strefami → NOTAUTH | 2136 §3.1.1 | domena z ACME Domains; jej przodek (apex publiczny, wzorzec cert-manager i win-acme) → dalej | obca strefa; potomek domeny; korzeń; TLD → NOTAUTH |
| U4 | UPDATE bez podpisu → REFUSED, tylko log aplikacji | 3007 §3; 2136 §3.3 | ten sam UPDATE podpisany → NOERROR | bez TSIG → REFUSED, brak audytu, brak zmian |
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
| R4 | Zamknięcie przy `get_certificate`; wygaśnięcie wg `expires_at` | 8555 §7.1.4 (`expires`) | po certyfikacie → `closed` | wiersz innego zamówienia bez zmian |
| R5 | Zakres klucza: konto proxy, opcjonalnie konto ACME z EAB | 3007 §3, §3.1 | pasuje → dozwolone | inne konto proxy; inne konto ACME → niedozwolone |
| K1 | Sekret z CSPRNG, długość = wyjście skrótu (32/48/64 B) | 8945 §8 | długości dla 3 algorytmów | dwa klucze nigdy nie mają tego samego sekretu (1000 prób) |
| K2 | Sekret zaszyfrowany w DB | maintainer | wartość w DB ≠ jawny tekst, odczyt przez model = jawny tekst | zły klucz master → brak odczytu |
| K3 | Sekret zwracany tylko przy utworzeniu | maintainer | POST zwraca sekret | GET listy i GET klucza nie zwracają sekretu |
| K4 | Algorytmy: tylko sha256/384/512, w trybie FIPS i poza nim | 8945 §6, §7; maintainer | 3 algorytmy → 201 | md5, sha1, sha224 → 400 |
| K5 | Nazwa klucza: poprawna nazwa DNS ≤ 255 B, unikalna bez wielkości liter | 8945 §4.2; 1035 §2.3.4 | poprawna → 201 | duplikat innej wielkości liter; etykieta > 63 B → 400 |
| K6 | Domyślnie brak uprawnień: nowy klucz bez wierszy nic nie zmienia | 3007 §3 | — | dodanie z nowym kluczem bez wierszy → REFUSED |

### 4.6 Serwer, logi, bezpieczeństwo (N)

| ID | Niezmiennik | Podstawa | P | N |
|---|---|---|---|---|
| N1 | Port: najpierw env `UCM_DNS_UPDATE_PORT`, potem ustawienie; 0 = wyłączony; domyślnie 0 | maintainer | env 8053 → nasłuch | brak env i ustawienia → brak nasłuchu; wartość błędna → 0 i ostrzeżenie |
| N2 | API: port 0 albo 1024–65535, inny niż HTTPS i port protokołów HTTP | maintainer (bez CAP_NET_BIND_SERVICE) | 8053 → 200 | 53, 70000, port HTTPS → 400 |
| N3 | Błąd bind nie zatrzymuje aplikacji | wzorzec serwera HTTP | wolny port → nasłuch | zajęty port → log błędu, aplikacja działa |
| N4 | Limity: UDP > MAX_MSG odrzucony; limit połączeń TCP (łącznie i na IP); limit wiadomości na IP | 7766 §6.2.2; bezpieczeństwo | ruch w limicie → odpowiedzi | ruch ponad limit → brak odpowiedzi, log |
| N5 | Brak rekursji i brak ruchu wychodzącego z handlera | maintainer; 8906 §3.1.3.1 | — | test z zablokowanym `socket.connect`: żadne wywołanie |
| N6 | Audyt: przyjęte i odrzucone żądania z TSIG; log aplikacji: bez podpisu i błędne | maintainer | żądanie z TSIG → wpis audytu | bez TSIG; błędne → brak wpisu audytu |
| N7 | Limit wpisów audytu na (IP, powód) | bezpieczeństwo (ochrona tabeli audytu) | pierwszy BADKEY → wpis | 100 BADKEY z tego samego IP w 60 s → 1 wpis + log |

## 5. Miejsca, w których uzgadniam wymagania maintainera z RFC

| # | Wymaganie maintainera | Problem | Decyzja i uzasadnienie |
|---|---|---|---|
| 1 | „answer unsigned SOA queries … refuse every other query” | nsupdate (acme.sh bez `NSUPDATE_ZONE`, Posh-ACME z `DDNSNameserver`) **podpisuje** zapytanie SOA, gdy ma klucz, a odpowiedź bez podpisu jest dla niego błędem krytycznym (sekcja 9). RFC 8945 §5.3 wymaga podpisanej odpowiedzi na podpisane żądanie | Odpowiadam na SOA bez podpisu i z podpisem. Zapytanie podpisane dostaje podpisaną odpowiedź i zakres klucza. Wyjaśnię to w PR |
| 2 | „No response larger than the request” | Odpowiedź SOA jest zawsze dłuższa niż zapytanie. lego i cert-manager powtarzają przez TCP po TC=1, certbot pyta najpierw przez TCP, ale **nsupdate nie obsługuje TC** i pyta przez UDP (sekcja 9) | Reguła obowiązuje dla UDP bez poprawnego TSIG (T1): tylko taki ruch można sfałszować (podrobiony adres źródłowy). Żądanie z poprawnym TSIG (MAC zweryfikowany, czas w oknie, S7 blokuje starsze) dostaje zwykły limit RFC: max(512, EDNS) (T2). Współczynnik dla podpisanego SOA ≈ 1,25. TCP bez limitu (handshake) |
| 3 | „Always answer NOERROR, even when the order is gone” | RFC 2136 §3.1.1 sprawdza strefę przed usunięciem. Strefa zależna od aktywnych zamówień dałaby NOTAUTH | Strefa zależy od ACME Domains, nie od zamówień (sekcja 2.3) |
| 4 | „A non-empty prerequisite section gets REFUSED” | RFC 2136 §3.2 ocenia prerequisite przed §3.3 | Nasza strefa nie ma stanu, względem którego można ocenić prerequisite. Odmowa jest polityką (§3.3.1 „implementation dependent”) |
| 5 | Algorytmy „nothing weaker than SHA-256” | RFC 8945 §6: implementacja MUSI mieć hmac-sha1 | §7 pozwala lokalnej polityce odrzucić algorytm. sha1 → BADKEY |
| 6 | Odpowiedzi BADTIME | dnspython podpisuje czasem serwera, a RFC 8945 §5.2.3 wymaga czasu klienta w Time Signed | Własna budowa TSIG dla BADTIME przez publiczne `dns.tsig.sign` |
| 7 | „Use dnspython … do not hand-roll HMAC” | `dns.tsig.validate` sprawdza czas przed MAC; RFC 8945 §5.2 wymaga: klucz, MAC, czas | Wywołuję `dns.tsig.validate` z `now = time_signed` (czas zawsze OK), potem sprawdzam czas sam. HMAC liczy dnspython. Sprawdzone prototypem na dnspython 2.8.0 (`spike/tsig_spike.py` w tym katalogu) |
| 8 | SOA „for names covered by a pending proxy order” | Który apex ogłaszać? Apex = nazwa rekordu psuje precheck lego (szuka NS dla fałszywej strefy). REFUSED dla nazwy rekordu zatrzymuje nsupdate | Apex = D (sekcja 2.3). SOA w ANSWER dla D, NODATA z SOA w AUTHORITY dla nazw od D do nazwy rekordu (Q1, Q7). Pasuje do certbot, lego i nsupdate (sekcja 9) |
| 9 | RFC 8945 §5.2.3 (SHOULD): odrzucać Time Signed starszy niż ostatni dla klucza | cert-manager wysyła kilka UPDATE równolegle (kilka nazw w certyfikacie). Pakiety UDP mogą przyjść w innej kolejności, więc jeden dostanie BADTIME | Implementuję zalecenie dosłownie (S7). cert-manager ponawia wyzwanie po błędzie. Sprawdzę to w E2E. Gdy ponawianie nie wystarczy, wrócę z danymi |

## 6. Bezpieczeństwo (do security review)

| Zagrożenie | Ochrona |
|---|---|
| Zapis dowolnego rekordu w DNS | Nasłuch nie zapisuje nic w DNS. Dodanie przechodzi tylko dla TXT `_acme-challenge` z wartością równą oczekiwanej |
| Podszycie się pod innego klienta | Wartość zależy od thumbprintu klienta (RFC 8555 §8.1). Zakres klucza = konto proxy, opcjonalnie konto ACME z EAB |
| Kradzież sekretu z DB | Szyfrowanie kluczem master, sekret pokazany raz |
| Powtórzenie żądania (replay) | Okno ±fudge, ostatni Time Signed na klucz (S7). Operacje są idempotentne |
| Amplifikacja UDP | Bez poprawnego TSIG: odpowiedź ≤ żądanie, inaczej TC=1 (T1). Z poprawnym TSIG: limit RFC (T2); sfałszować się nie da bez sekretu, powtórkę ogranicza okno fudge i S7 |
| Zalanie DB i audytu | Limity na IP (N4), limit wpisów audytu (N7), brak audytu dla żądań bez podpisu (N6) |
| Wyciek nazw aktywnych wyzwań | SOA bez podpisu ujawnia nazwy z aktywnymi wyzwaniami (wymaganie maintainera). Dokumentacja: nasłuch tylko w sieci wewnętrznej |
| Slow-read TCP | Limit bezczynności od pełnej wiadomości (T5), limit połączeń |
| Porównanie MAC w czasie stałym | `hmac.compare_digest` (dnspython) |
| Uprawnienia procesu | Port nieuprzywilejowany, bez CAP_NET_BIND_SERVICE |

## 7. Pozostałe części PR 2

- **Uruchomienie:** w `post_worker_init` (gunicorn, `workers = 1`), obok serwera HTTP protokołów; w trybie dev w `app.py main()`. Serwery gevent `DatagramServer` i `StreamServer`. Zmiana portu wymaga restartu (jak port HTTP protokołów).
- **API:**
  - `GET/POST /api/v2/acme/client/accounts/<id>/dns-update-keys` (`read:acme` / `write:acme`)
  - `DELETE /api/v2/acme/client/accounts/<id>/dns-update-keys/<key_id>` (`delete:acme`; aktywny → odwołanie, odwołany → usunięcie, jak EAB)
  - `dns_update_port` w `/api/v2/acme/client/settings` (GET/PATCH)
- **UI:** sekcja „Klucze DNS UPDATE (RFC 2136)” w karcie konta proxy (`CaAccountsManager.jsx`). Okno „pokaż raz” z sekretem i gotowymi fragmentami: plik klucza BIND (nsupdate, acme.sh, Posh-ACME), Secret i ClusterIssuer dla cert-manager, plik ini certbot. Pole portu w sekcji proxy (`LetsEncryptTab.jsx`). Pomoc kontekstowa. Teksty w 9 językach (`npm run check:i18n`).
- **Pakiety:** Dockerfile `EXPOSE 8053/udp 8053/tcp`; `docker/entrypoint.sh` sprawdza `UCM_DNS_UPDATE_PORT` (0 albo 1024–65535, inny niż inne porty). Helm: `dnsUpdate.enabled` (domyślnie false), `dnsUpdate.port` (8053), port usługi UDP i TCP (np. 53 → 8053), zmienna env. DEB i RPM: bez zmian w unitach.
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
