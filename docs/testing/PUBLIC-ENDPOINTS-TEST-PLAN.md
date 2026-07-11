# Test plan — Public endpoints (admin / protocol / ACME vhost)

Reference topology (lab example — adapt hostnames):

| Role | Example |
|------|---------|
| Admin GUI/API | `https://admin.ucm.example.com:8443` |
| PKI protocol HTTP | `http://admin.ucm.example.com:8080` |
| ACME public vhost | `https://acme.ucm.example.com:8443` |

## 1. Automated (pytest)

From `backend/`:

```bash
python3 -m pytest tests/test_public_endpoints.py tests/test_acme_public_url.py -v
```

| ID | Test | Expected |
|----|------|----------|
| P-01 | URL validation HTTPS admin / HTTP protocol | 400 on invalid scheme or path |
| P-02 | Reject `metadata.google.internal` on save | 400 |
| P-03 | Split topology ACME vhost blocks admin `/` | 404 on ACME host |
| P-04 | ACME `/acme/directory` on ACME vhost | 200 |
| P-05 | Spoofed `Host: localhost` from public IP | 302 → canonical admin |
| P-06 | Loopback peer + `Host: localhost` | No erroneous redirect |
| P-07 | Untrusted `X-Forwarded-Host` with ProxyFix hops | 403 on admin API |
| P-08 | Preflight POST | 200 admin, 403 viewer |
| P-09 | GET `/api/v2/settings/public-endpoints` | Effective URLs JSON |
| P-10 | Preflight with `UCM_CORPORATE_DNS_SERVERS` | `dns_internal` warn/ok, `corporate_dns_servers` in JSON |
| P-11 | Preflight A-only zone (no AAAA) | Internal DNS ok (AAAA NXDOMAIN must not wipe A) |
| P-12 | Preflight metadata IP resolution | TLS skip, no socket to 169.254.169.254 |
| P-13 | LAN peer + X-Forwarded-Host + ProxyFix | 403 (not trusted unless in UCM_TRUSTED_PROXIES) |

### Preflight DNS — three perspectives

| Badge | Source | Purpose |
|-------|--------|---------|
| **DNS (local)** | `getaddrinfo` → `/etc/hosts` + `resolv.conf` | What the UCM process uses at runtime |
| **DNS (interne)** | `UCM_CORPORATE_DNS_SERVERS` or `acme.dns01_nameservers` | Split-horizon / corporate resolver (e.g. `172.31.10.190`) |
| **DNS (public)** | 9.9.9.9, 8.8.8.8, 1.1.1.1 | Internet clients without VPN |

Configure corporate DNS in `/etc/ucm/ucm.env` (independent of `resolv.conf`):

```bash
# Comma-separated IPs — used for preflight « DNS (interne) » only
UCM_CORPORATE_DNS_SERVERS=172.31.10.190
```

Fallback: SystemConfig `acme.dns01_nameservers` (same comma-separated format).

When `resolv.conf` already uses the internal nameserver, **local** and **interne** should agree; **public** may still fail until records are published on the Internet.

## 2. Lab manual — connectivity

Replace `LAB` with lab IP or admin FQDN.

```bash
LAB=admin.ucm.example.com
PORT=8443
```

| ID | Command | Expected |
|----|---------|----------|
| L-01 | `curl -sk https://${LAB}:${PORT}/api/health` | `"status":"ok"` |
| L-02 | `curl -skI https://ucm.example.com:${PORT}/` | 302 → admin URL |
| L-03 | `curl -skI https://172.31.10.8:${PORT}/` | 302 → admin URL |
| L-04 | `curl -skI -H "Host: localhost" https://172.31.10.8:${PORT}/` | 302 → admin (not 200) |
| L-05 | `curl -sk -o /dev/null -w "%{http_code}" -H "Host: acme.ucm.example.com" https://127.0.0.1:${PORT}/` | 404 |
| L-06 | `curl -sk -o /dev/null -w "%{http_code}" -H "Host: acme.ucm.example.com" https://127.0.0.1:${PORT}/acme/directory` | 200 |

## 3. Lab manual — authenticated API

Login (use operator password; do not commit). Mutating requests require CSRF:

```bash
COOKIE=/tmp/ucm-lab-cookies.txt
curl -sk -c "$COOKIE" -b "$COOKIE" \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<ADMIN_PASSWORD>"}' \
  "https://${LAB}:${PORT}/api/v2/auth/login"
CSRF=$(curl -sk -b "$COOKIE" "https://${LAB}:${PORT}/api/v2/auth/verify" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['csrf_token'])")
```

| ID | Command | Expected |
|----|---------|----------|
| A-01 | Login | 200, session cookie set |
| A-02 | `GET /api/v2/settings/public-endpoints` | 200, `admin.host` matches config |
| A-03 | `POST /api/v2/settings/public-endpoints/preflight` | 200, DNS/TLS checks array |
| A-04 | PATCH `base_url` invalid (`http://…`) | 400 |
| A-05 | PATCH `base_url` metadata host | 400 |
| A-06 | PATCH valid trio + GET effective | URLs updated |

Example PATCH (after login):

```bash
curl -sk -b "$COOKIE" -X PATCH -H 'Content-Type: application/json' -H "X-CSRF-Token: $CSRF" \
  -d '{"base_url":"https://admin.ucm.example.com:8443","protocol_base_url":"http://admin.ucm.example.com:8080","acme_public_vhost":"acme.ucm.example.com"}' \
  "https://${LAB}:${PORT}/api/v2/settings/general"
```

## 4. GUI (browser)

1. Open `https://admin.ucm.example.com:8443` — login admin.
2. **Paramètres → Général** — verify three URL fields.
3. **Endpoints publics** — canonical URLs, preflight badges.
4. **Utiliser l'URL du navigateur** → save → refresh effective block.
5. Open `https://ucm.example.com:8443` in browser → must land on admin URL.

## 5. Regression

- ACME directory URLs still advertise `acme_public_vhost` when set (#173).
- CORS from browser on admin origin still works (WebSocket + API).
- CDP/OCSP still served on protocol paths without admin redirect.

## 6. Security sign-off

- [ ] P-05 / L-04: no admin on IP + spoofed localhost Host
- [ ] P-02 / A-05: metadata hostname rejected
- [ ] P-08: preflight requires `write:settings`
- [ ] P-07 / P-13: proxy header spoof blocked when `TRUSTED_PROXY_HOPS>0` (public and RFC1918 LAN peers)
- [ ] P-12: preflight does not TCP-probe metadata/loopback IPs

Details: [PUBLIC-ENDPOINTS.md](./PUBLIC-ENDPOINTS.md#host-middleware-behaviour).
