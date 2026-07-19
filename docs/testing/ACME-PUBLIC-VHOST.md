# ACME — public vhost, directory URLs and wildcard certificates

UCM can advertise public ACME URLs distinct from the administration URL.
This document describes the recommended topology (using `example.com` names only),
the wildcard certificate rules, the test plan and the pytest commands.

See also: [ACME-PROXY-MULTI-CA.md](./ACME-PROXY-MULTI-CA.md), [ACME-DNS-PROPAGATION.md](./ACME-DNS-PROPAGATION.md), [PUBLIC-ENDPOINTS.md](./PUBLIC-ENDPOINTS.md).

## Functional scope (PR)

| Area | Files / behavior |
|------|------------------|
| **Backend** | `backend/utils/acme_public_url.py`, `get_acme_public_origin()` |
| **ACME API** | `acme_api.py`, `acme_proxy_api.py` — directory links (`newOrder`, …) |
| **Settings API** | `api/v2/settings/general.py` — GET/PATCH `acme_public_*` |
| **ACME settings** | `api/v2/acme/settings.py`, `api/v2/acme_client/settings.py` — `acme_public_base_url`, `acme_proxy_public_base_url` |
| **Frontend** | `GeneralSection.jsx`, `ConfigTab.jsx`, `LetsEncryptTab.jsx` |
| **i18n (9 languages)** | `frontend/src/i18n/locales/{en,fr,de,es,it,ja,pt,uk,zh}.json` — labels + wildcard helpers |
| **Contextual help** | `helpContent.js` / `helpGuides.js` (en) + `help/{de,es,fr,it,ja,pt,uk,zh}/settings.js` |
| **Tests** | `backend/tests/test_acme_public_url.py`, `test_acme.py` extensions |

### `SystemConfig` keys

| Key | Validation | Runtime effect |
|-----|------------|----------------|
| `acme_public_vhost` | Concrete hostname only (no `*.` prefix) | ACME directory URLs (local server **and** proxy) |
| `acme_public_port` | 1–65535 | Port in URLs (omitted if 443) |
| `acme_public_tls_cert_id` | UCM certificate ID with a private key | Ops metadata (no automatic TLS push) |

## Reference topology

In the common case, admin and ACME are **subdomains of `ucm.example.com`**:

| Role | FQDN | Usage |
|------|------|-------|
| **UCM admin** | `https://admin.ucm.example.com:8443` | GUI, session API, optional/required mTLS client |
| **Public ACME** | `https://acme.ucm.example.com:8443` | `/acme/*` (local CA) and `/acme/proxy/*` (proxy to external CA) |
| **UCM base URL** (Settings → General) | `https://admin.ucm.example.com` | Absolute links, notifications, SAML |

The UCM listener (gunicorn) is single; in production a **reverse proxy** (F5, nginx, Traefik) terminates TLS per **vhost** and routes to the UCM backend.

### UCM settings (Settings → General)

| `SystemConfig` key | Example | Effect |
|--------------------|---------|--------|
| `acme_public_vhost` | `acme.ucm.example.com` | Hostname in the ACME directory URLs (`newOrder`, `newNonce`, …) |
| `acme_public_port` | `8443` | Port in those URLs (omitted if `443`) |
| `acme_public_tls_cert_id` | UCM certificate ID | **Metadata**: TLS cert to deploy on the ACME vhost on the proxy side (not applied to the gunicorn runtime) |

Without `acme_public_vhost`, UCM falls back to the `scheme://Host` of the incoming request.

> **Important**: configure DNS and TLS for the ACME vhost **before** saving this field.
> As soon as it is set, ACME clients that re-read the directory (Certbot, renewals)
> immediately switch to the new URLs — an unreachable vhost breaks renewals.

> The `*.ucm.example.com` wildcard is a **TLS SAN** concept, not an advertizable hostname.
> The API validation **rejects** `*.ucm.example.com` as a value for `acme_public_vhost`.

## Wildcard certificates — key rules

A wildcard SAN `*.ucm.example.com` covers **a single** label to the left of `ucm.example.com`:

| Hostname accessed | `*.ucm.example.com` cert | `*.example.com` cert |
|-------------------|--------------------------|----------------------|
| `admin.ucm.example.com` | ✅ | ❌ |
| `acme.ucm.example.com` | ✅ | ❌ |
| `api.ucm.example.com` | ✅ | ❌ |
| `ucm.example.com` (apex) | ❌ | ❌ |
| `acme.example.com` | ❌ | ✅ |

**Typical UCM case**: a `*.ucm.example.com` wildcard certificate is enough for **both** vhosts
`admin.ucm.example.com` and `acme.ucm.example.com`, provided the reverse proxy presents
the same certificate (or copies) on each SNI vhost.

This wildcard **does not** cover the apex `ucm.example.com` — an explicit SAN is required if that name is used.

### Common mistakes

1. **Applying `*.ucm.example.com` then accessing via `ucm.example.com`**
   The apex is not covered by the wildcard → **hostname mismatch**.

2. **Configuring `acme_public_vhost=acme.ucm.example.com` but DNS/TLS on another name**
   (e.g. `acme.example.com` outside the `ucm` zone) → timeout or TLS error on the Certbot side.

3. **A single gunicorn listener with an admin cert, directory URLs pointing to `acme.ucm.example.com`**
   ACME clients verify the certificate of the hostname advertised in the directory, not the admin one.

4. **Confusing directory URL and server certificate**
   The URLs in the directory follow `acme_public_vhost`; the ACME client validates TLS **of each advertised URL**.

5. **Entering `*.ucm.example.com` as the vhost**
   Rejected by the API — it would produce invalid URLs (`https://*.ucm.example.com/...`).

### Recommended TLS strategies

**Option A — `*.ucm.example.com` wildcard (recommended if both vhosts are under `ucm.example.com`)**

```
admin.ucm.example.com:8443  → cert *.ucm.example.com (mTLS per admin policy)
acme.ucm.example.com:8443   → same cert *.ucm.example.com, no client mTLS
```

**Option B — explicit SANs**

```
SAN: admin.ucm.example.com, acme.ucm.example.com
```

**Option C — Lab / single-node (temporary)**

Same FQDN for admin and ACME while validating the flow, then split the vhosts.

> `*.example.com` does not replace `*.ucm.example.com` for `admin.ucm.example.com` /
> `acme.ucm.example.com`: these names have **two** labels before `example.com`.

### Reverse proxy — `Host` header

RFC 8555 JWS checks compare the URL signed by the client with the configured public origin
(`get_acme_public_origin`). The local ACME server and the proxy use the same origin
for both directory links **and** JWS validation.

If the reverse proxy does not forward the public `Host` to gunicorn, the ACME proxy also accepts
the URL as seen by UCM (fallback) — but **nginx / Traefik / F5** should ideally
preserve the client hostname:

```nginx
# nginx — ACME vhost
proxy_set_header Host $host;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
```

Without `proxy_set_header Host`, some proxy flows may fail with "URL mismatch"
when the public vhost is configured and the client signs the directory URLs.

## Example configuration

### UCM (GUI or API)

```http
PATCH /api/v2/settings/general
{
  "base_url": "https://admin.ucm.example.com",
  "acme_public_vhost": "acme.ucm.example.com",
  "acme_public_port": 8443,
  "acme_public_tls_cert_id": 42
}
```

`acme_public_tls_cert_id` references the wildcard (or dedicated) certificate managed in UCM to install on the `acme.ucm.example.com` vhost of the reverse proxy.

### DNS

```
admin.ucm.example.com.  A     203.0.113.10
acme.ucm.example.com.   A     203.0.113.10
```

Same IP possible; the proxy distinguishes by **SNI / Host**.

### Certbot (multi-CA proxy)

```bash
certbot certonly \
  --server https://acme.ucm.example.com:8443/acme/proxy/actalis-production/directory \
  --preferred-challenges dns-01 \
  --authenticator manual \
  --manual-auth-hook /path/to/auth.sh \
  --manual-cleanup-hook /path/to/cleanup.sh \
  --non-interactive --agree-tos \
  -m operator@example.com \
  -d app.example.com
```

Prerequisites: `acme.ucm.example.com` resolves to the proxy, valid TLS cert for that name (`*.ucm.example.com` wildcard or explicit SAN), no client mTLS required on this vhost.

## Automated tests (pytest)

### Minimal suite (public vhost)

```bash
cd backend
python -m pytest tests/test_acme_public_url.py -q
# Expected: 21 passed

python -m pytest \
  tests/test_acme.py::TestAcmeServerSettings::test_get_settings_exposes_configured_public_acme_base_url \
  tests/test_acme.py::TestAcmeClientSettings::test_get_client_settings_exposes_configured_public_acme_urls \
  -q
# Expected: 2 passed
```

### `test_acme_public_url.py` detail

| Class | Scenarios |
|-------|-----------|
| `TestGetAcmePublicOrigin` | vhost+port configured, port 443 omitted, `Host` fallback, admin Host does not override the ACME vhost |
| `TestWildcardSanHostnameCompatibility` | SAN table: `*.ucm.example.com` covers `admin.ucm.example.com` **and** `acme.ucm.example.com`; apex `ucm.example.com` not covered; `*.example.com` insufficient for `ucm` subdomains |
| `TestAcmePublicVhostSettingsApi` | PATCH rejects `*.ucm.example.com`, accepts a concrete hostname |
| `TestProxyJwsExpectedUrls` | proxy JWS: configured public origin takes precedence over the incoming `Host` |
| `TestAcmeDirectoryPublicUrls` | `/acme/directory` and `/acme/proxy/directory` return `newOrder` with the configured origin |

### Settings API coverage

| File | Scenarios |
|------|-----------|
| `test_acme.py` | `acme_public_base_url`, `acme_proxy_public_base_url` after PATCH general settings |

### Extended ACME suite (proxy regression)

```bash
cd backend
python -m pytest tests/test_acme_public_url.py \
  tests/test_acme_proxy_ca_account.py \
  tests/test_acme_dns_selfcheck.py \
  tests/test_acme.py::TestAcmeServerSettings \
  tests/test_acme.py::TestAcmeClientSettings \
  tests/test_acme.py::TestAcmeClientProxy \
  -q
# Local reference: 90 passed
```

### Frontend (i18n)

```bash
cd frontend
npm run check:i18n
# Expected: 4036 keys, 9/9 locales in sync (acmePublic* keys)
```

## Manual test plan

### 1. General settings (GUI)

1. **Settings → General**: set
   - `acme_public_vhost` = `acme.ucm.example.com`
   - `acme_public_port` = `8443`
   - `acme_public_tls_cert_id` = ID of a `*.ucm.example.com` cert (optional)
2. Save → reload (`Ctrl+Shift+R`) → values persisted
3. Check the **helpers** (concrete hostname, DNS/TLS warning) in at least **fr** and **en**
4. **ACME → Configuration**: directory `https://acme.ucm.example.com:8443/acme/directory`
5. **ACME → Let's Encrypt**: proxy base `https://acme.ucm.example.com:8443/acme/proxy/...`

### 2. REST API

```bash
# Read
curl -sk -b cookies.txt https://admin.ucm.example.com:8443/api/v2/settings/general \
  | jq '.data.acme_public_vhost, .data.acme_public_port'

curl -sk -b cookies.txt https://admin.ucm.example.com:8443/api/v2/acme/client/settings \
  | jq '.data.acme_public_base_url, .data.acme_proxy_public_base_url'

# Write (admin session)
curl -sk -b cookies.txt -X PATCH https://admin.ucm.example.com:8443/api/v2/settings/general \
  -H 'Content-Type: application/json' \
  -d '{"acme_public_vhost":"acme.ucm.example.com","acme_public_port":8443}'
```

Expected after PATCH: the URLs above reflect `acme.ucm.example.com:8443`.

### 3. Contextual help (9 UI languages / 8+1 help)

| UI language | Panel help file | i18n helpers |
|-------------|-----------------|--------------|
| en | `helpContent.js` + `helpGuides.js` | `en.json` |
| fr, de, es, it, ja, pt, uk, zh | `help/<lang>/settings.js` | `<lang>.json` |

1. Open **Settings** → floating help panel
2. **"Public ACME vhost"** section (or translated equivalent) visible
3. Content: `admin.ucm.example.com`, `acme.ucm.example.com`, `*.ucm.example.com` wildcard, apex not covered

### 4. DNS and TLS (`*.ucm.example.com` wildcard)

1. `dig +short acme.ucm.example.com` → expected proxy IP
2. `openssl s_client -connect acme.ucm.example.com:8443 -servername acme.ucm.example.com`
   → SAN `*.ucm.example.com` or `acme.ucm.example.com`
3. Repeat for `admin.ucm.example.com` with the **same** wildcard certificate
4. `curl -sk https://acme.ucm.example.com:8443/acme/proxy/directory` → JSON; each URL uses `acme.ucm.example.com`

### 5. Admin / ACME separation (reverse proxy)

1. **admin** vhost: mTLS per policy (`mtls_required` if applicable)
2. **ACME** vhost: no mandatory client mTLS (Certbot / Actalis)
3. Same wildcard cert presented on both SNI vhosts

### 6. Certbot E2E

```bash
certbot certonly \
  --server https://acme.ucm.example.com:8443/acme/proxy/<slug>/directory \
  --preferred-challenges dns-01 \
  ...
```

Expected: account registration OK; failure only if DNS hook missing or TXT not published.

### 7. Known wildcard regressions

| Action | Expected result |
|--------|-----------------|
| `*.ucm.example.com` cert on admin vhost | `https://admin.ucm.example.com` OK |
| Same cert on ACME vhost | `https://acme.ucm.example.com` OK |
| Access apex `https://ucm.example.com` with wildcard SAN only | **TLS failure** (apex not covered) |
| Apply wildcard as the single gunicorn HTTPS cert + directory pointing to `acme.ucm...` | Certbot **hostname mismatch** if cert does not match the directory URL |
| `acme_public_vhost` points to an unreachable DNS | Certbot `ConnectTimeout` |

## Acceptance criteria

- [ ] `acme_public_base_url` and `acme_proxy_public_base_url` use the configured `acme.ucm.example.com`
- [ ] A `*.ucm.example.com` cert covers **admin** and **ACME** (not the apex)
- [ ] Certbot reaches the directory without timeout or hostname mismatch
- [ ] `pytest tests/test_acme_public_url.py` — 21 passed
- [ ] `npm run check:i18n` — 9 locales synchronized
- [ ] Help panel + helpers mention the wildcard topology in all UI languages
- [ ] Doc and examples: `example.com` only (no lab FQDN)

## Troubleshooting

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| `ConnectTimeout` to `acme.ucm.example.com` | DNS / firewall | Fix A/AAAA, open :8443 |
| `Hostname mismatch` on admin | Apex or wrong wildcard | Check SAN; apex requires a dedicated SAN |
| Certbot OK locally, KO remotely | `acme.ucm.example.com` DNS incorrect | Align public DNS |
| GUI OK after HTTPS cert change | Cert applied to single listener | Split proxy vhost or restore admin cert |
