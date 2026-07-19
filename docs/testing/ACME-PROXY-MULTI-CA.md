# ACME Proxy Multi-CA — Test plan

Feature: the ACME proxy reuses `AcmeClientAccount` records (the same registry as the ACME client). Each account can expose a dedicated endpoint `/acme/proxy/<slug>/directory` in addition to the legacy path `/acme/proxy/directory`.

## Prerequisites

- UCM deployed with migrations `050_acme_proxy_ca_account_link` and `051_acme_proxy_slug`
- At least one external CA account registered (e.g. Actalis, Let's Encrypt Staging)
- A domain configured in **ACME Domains** with a DNS provider (e.g. Gandi)
- `read:acme` / `write:acme` permissions

## Automated tests (regression)

```bash
cd backend
python -m pytest tests/test_acme_proxy_ca_account.py \
  tests/test_acme_proxy_key_encrypted.py \
  tests/test_acme.py::TestAcmeClientProxy \
  tests/test_acme.py::TestAcmeClientSettings \
  -q
```

Targeted coverage:

| File | Scenarios |
|------|-----------|
| `test_acme_proxy_ca_account.py` | Account resolution, settings API, service binding, **multi-path** (`TestProxyMultiPath`) |
| `test_acme_proxy_key_encrypted.py` | Key encryption on `AcmeClientAccount` |
| `test_acme.py` | Proxy register/unregister by `acme_account_id`, settings fields |

Full suite (reference 2026-07-06):

```bash
cd /opt/ucm/backend && runuser -u ucm -- /opt/ucm/venv/bin/python -m pytest tests/ -q
# Expected: 2115 passed, 6 skipped
```

## Manual tests — UI

### 1. CA account selection (global proxy)

1. ACME → Let's Encrypt → **ACME Proxy** section
2. Enable the proxy
3. Check that the **Upstream CA account** selector lists the accounts from **External CA accounts**
4. Pick an account → the directory URL is shown under the selector
5. Reload the page → selection persists

### 2. Dedicated endpoint per account (slug)

1. **External CA accounts** → edit an account (e.g. Actalis Production)
2. Enable **Expose via ACME proxy**
3. Set a unique slug (e.g. `actalis-production`) — no reserved slug (`directory`, `challenge`, …)
4. Save → a `/acme/proxy/actalis-production/directory` badge appears on the account card
5. Proxy section → **Dedicated proxy URL** + **All enabled proxy endpoints** list
6. Copy the URL → `curl -sk …/acme/proxy/actalis-production/directory` returns the upstream directory

### 3. Connection test

1. With an account selected, click **Test connection**
2. Expected: ✓ connected + CA name
3. With no account selected: button disabled

### 4. Upstream registration

1. Select an unregistered account (`is_registered: false`)
2. Enter a public email (e.g. `you@gmail.com`)
3. **Register account** → success, "Account registered" badge
4. Check in **External CA accounts** that the same account shows as registered

### 5. Switching between CAs

1. Create 2 accounts with distinct slugs (Staging + Production)
2. Register both
3. Certbot / curl against each slug → directory and issuer consistent with the linked account

### 6. Account reset

1. Registered account → reset icon (↻)
2. Confirm → `account_url` / key cleared on the linked account
3. Re-registration possible

### 7. `preferred_chain` (alternate chains) — optional

1. In **External CA accounts**, edit the CA account you use for the proxy (e.g. Let's Encrypt).
2. In the **Preferred chain** field, enter the **trust anchor CN** (e.g. `ISRG Root X1`).
   - UCM matches **case-insensitively** against the **CN of the last certificate** provided in the PEM: **subject CN** *or* **issuer CN** (supports "short" chains where the root is omitted).
3. Issue a certificate via Certbot against `/acme/proxy/<slug>/directory`.
4. Check the returned chain: verify that the **subject CN** *or* **issuer CN** of the **last certificate** equals `ISRG Root X1`.
   - For example (if you have a chain file like `chain.pem`):
     `openssl storeutl -noout -text -certs chain.pem | grep -A1 'Subject:' | tail -2`

## Manual tests — API

```bash
# Settings
curl -sk -H "Authorization: Bearer $TOKEN" \
  https://ucm.example:8443/api/v2/acme/client/settings | jq '.data | {proxy_acme_account_id, proxy_upstream_url, proxy_account_registered}'

# Enable proxy + slug on account id=4
curl -sk -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"proxy_enabled":true,"proxy_slug":"actalis-production"}' \
  https://ucm.example:8443/api/v2/acme/client/accounts/4

# Directory by slug (no auth)
curl -sk https://ucm.example:8443/acme/proxy/actalis-production/directory | jq .

# Legacy directory (account selected in settings)
curl -sk https://ucm.example:8443/acme/proxy/directory | jq .

# Connection test
curl -sk -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"acme_account_id":4}' \
  https://ucm.example:8443/api/v2/acme/client/proxy/test-connection
```

## Manual tests — ACME proxy E2E (Certbot)

Example validated in a lab environment (UCM + external CA + DNS provider):

```bash
TEST_DOMAIN="cert-proxy-test.example.com"   # fresh subdomain per run
CFG="/tmp/certbot-proxy-path"
rm -rf "$CFG" && mkdir -p "$CFG"/{config,work,logs}

certbot certonly \
  --config-dir "$CFG/config" \
  --work-dir "$CFG/work" \
  --logs-dir "$CFG/logs" \
  --server https://<ucm-host>:8443/acme/proxy/<slug>/directory \
  --no-verify-ssl \
  --preferred-challenges dns-01 \
  --authenticator manual \
  --manual-auth-hook /bin/true \
  --manual-cleanup-hook /bin/true \
  --non-interactive --agree-tos \
  -m you@example.com \
  -d "$TEST_DOMAIN"

openssl x509 -in "$CFG/config/live/$TEST_DOMAIN/cert.pem" -noout -issuer -subject
```

E2E notes:

- UCM creates/deletes TXT records via the configured DNS provider; Certbot hooks can stay `/bin/true`
- Intermittent `unauthorized` failure: Actalis DNS propagation (~30 s) — retry with a fresh FQDN
- Logs: `/var/log/ucm/ucm.log` (lines starting with `[ACME Proxy BG]`)

## Legacy migration (upgrade)

1. Migration **050**: links `acme.proxy.acme_account_id` to the `AcmeClientAccount` registry
2. Migration **051**: `proxy_slug`, `proxy_enabled` columns; backfills the slug for the configured proxy account
3. Verify in DB: `SELECT id,label,proxy_slug,proxy_enabled FROM acme_client_accounts`
4. `/acme/proxy/directory` stays compatible; new clients can target `/acme/proxy/<slug>/directory`

## Acceptance criteria

- [x] Multi-CA selection in the proxy UI
- [x] A single account registry (no duplicate proxy EAB)
- [x] Dedicated endpoint per account (`proxy_slug` + `proxy_enabled`)
- [x] Backward-compatible `/acme/proxy/directory`
- [x] Targeted pytest tests + green suite
- [x] Certbot E2E via slug (external CA + DNS provider)
- [x] i18n 9 languages + help guides + contextual GUI help
