# Public endpoints — admin, protocol HTTP, ACME vhost

UCM can split **three public roles** behind distinct hostnames: admin GUI/API,
PKI protocol HTTP (CDP/OCSP/AIA), and ACME directory. This document covers
architecture, configuration, DNS preflight, and security constraints.

**Related:** [ACME-PUBLIC-VHOST.md](./ACME-PUBLIC-VHOST.md) (ACME-specific),
[PUBLIC-ENDPOINTS-TEST-PLAN.md](./PUBLIC-ENDPOINTS-TEST-PLAN.md) (pytest + lab checklist).

## Architecture

| Role | Typical URL | Runtime effect |
|------|-------------|----------------|
| **Admin** | `https://admin.ucm.example.com:8443` | GUI, `/api/*`, WebSocket, CORS, redirect target for IP/alias |
| **Protocol** | `http://pki.ucm.example.com:8080` | CDP/OCSP/AIA base URL embedded in certificates (HTTP avoids TLS loops) |
| **ACME** | `https://acme.ucm.example.com:8443` | Directory URLs when split from admin (`acme_public_vhost`) |

Single gunicorn listener; production uses a reverse proxy for SNI/TLS per vhost.

### Code map

| Layer | Path |
|-------|------|
| URL logic, CORS, preflight | `backend/utils/public_endpoints.py` |
| Host redirect + split topology | `backend/middleware/public_host_middleware.py` |
| REST | `GET/POST/PATCH /api/v2/settings/public-endpoints` → `api/v2/settings/public_endpoints.py` |
| Save validation | `api/v2/settings/general.py` (`base_url`, `protocol_base_url`, `acme_public_vhost`) |
| GUI | `frontend/src/pages/settings/PublicEndpointsPanel.jsx` |

### Effective ports

When the stored URL **omits** an explicit `:port`:

- Admin / CORS / redirects → `HTTPS_PORT` from `/etc/ucm/ucm.env` (lab: `8443`)
- Protocol → `HTTP_PROTOCOL_PORT` / `http_protocol_port` (lab default: `8080`; **`80` is allowed** in Settings when the process can bind privileged ports or a reverse proxy forwards 80→8080)
- ACME directory → `acme_public_port` or `HTTPS_PORT` if unset

Explicit ports in DB are preserved as-is. Binding port 80 on Linux typically needs `CAP_NET_BIND_SERVICE` (or root); otherwise use a reverse proxy.

## SystemConfig keys

| Key | Scheme | Purpose |
|-----|--------|---------|
| `base_url` | HTTPS | Canonical admin origin |
| `protocol_base_url` | HTTP | Protocol base (empty → admin host + protocol port) |
| `acme_public_vhost` | host only | ACME hostname in directory URLs |
| `acme_public_port` | 1–65535 | Port in ACME URLs |

Save rules: valid FQDN, no path/query; `metadata.google.internal` and similar blocked;
wildcard rejected for `acme_public_vhost` (TLS SAN only).

## Environment variables

| Variable | Effect |
|----------|--------|
| `FQDN` / `UCM_FQDN` | Fallback admin host when `base_url` empty; GUI hint when env-locked |
| `HTTPS_PORT` | Default admin/ACME port when URL has no `:port` |
| `HTTP_PROTOCOL_PORT` | Default protocol HTTP port |
| `CORS_EXTRA_ORIGINS` | Comma-separated extra CORS origins |
| `UCM_CORPORATE_DNS_SERVERS` | Internal resolvers for preflight **DNS (interne)** (comma-separated IPs) |
| `UCM_BEHIND_PROXY` / `UCM_TRUSTED_PROXY_HOPS` | Enable ProxyFix for `X-Forwarded-*` |
| `UCM_TRUSTED_PROXIES` | Immediate peers allowed to set forwarded headers (default: `127.0.0.1`, `::1`) |

Fallback for corporate DNS preflight: SystemConfig `acme.dns01_nameservers` (same format).

Example `/etc/ucm/ucm.env` snippet:

```bash
FQDN=admin.ucm.example.com
HTTPS_PORT=8443
HTTP_PROTOCOL_PORT=8080
UCM_CORPORATE_DNS_SERVERS=10.0.0.53
```

Behind nginx/traefik:

```bash
UCM_BEHIND_PROXY=1
UCM_TRUSTED_PROXIES=10.0.0.5    # reverse-proxy IP only — not entire RFC1918
```

## GUI — Paramètres → Général → Endpoints publics

- **URLs effectives** after save (canonical admin, protocol, ACME directory/proxy).
- **Vérifier DNS et TLS** runs preflight (requires `write:settings`).
- **Utiliser l'URL du navigateur** fills `base_url` from current tab.

### Preflight DNS badges

| Badge | Resolver | Meaning |
|-------|----------|---------|
| **DNS (local)** | `getaddrinfo` → `/etc/hosts` + `resolv.conf` | What the UCM process uses at runtime |
| **DNS (interne)** | `UCM_CORPORATE_DNS_SERVERS` or `acme.dns01_nameservers` | Corporate/split-horizon view |
| **DNS (public)** | 9.9.9.9, 8.8.8.8, 1.1.1.1 | Internet clients without VPN |

Interpretation:

- **Local + interne OK, public fail** — normal internal lab; publish public DNS for external clients.
- **All fail** — check `resolv.conf`, corporate DNS, and that hostnames exist in zone.
- **Avertissement (private IP)** — expected for internal `172.x` addresses.

TLS/HTTP probes connect only to **non-forbidden** resolved IPs (metadata/loopback blocked).

## API

```http
GET  /api/v2/settings/public-endpoints     # read:settings — effective snapshot
POST /api/v2/settings/public-endpoints/preflight  # write:settings — DNS/TLS checks
PATCH /api/v2/settings/public-endpoints    # write:settings — delegates to general PATCH
```

Preflight response includes `corporate_dns_servers` when internal DNS is configured.

## Host middleware behaviour

- IP or alias admin host → **302** to canonical `base_url`.
- Split topology: ACME vhost serves `/acme/*` only; admin UI on ACME host → **404**.
- `Host: localhost` bypass redirect **only** if `REMOTE_ADDR` is loopback (blocks remote spoof).
- With ProxyFix enabled: untrusted peers sending `X-Forwarded-Host` on admin paths → **403**
  (trusted peers = `UCM_TRUSTED_PROXIES`, not all RFC1918).

Protocol paths (`/ocsp`, `/cdp/`, …) skip admin redirect.

## Common pitfalls

| Symptom | Cause | Fix |
|---------|-------|-----|
| Preflight local fail, interne OK | `resolv.conf` points to public DNS (9.9.9.9) | Point to internal DNS **or** rely on `UCM_CORPORATE_DNS_SERVERS` |
| Public DNS always fail | No Internet A/AAAA records | Publish DNS or accept warn for internal-only |
| GUI works, preflight public fail | Browser uses local `/etc/hosts`; server does not | Align server DNS or hosts |
| CORS errors after URL change | Origin not in allowlist | Save correct `base_url`; check `CORS_EXTRA_ORIGINS` |
| Certbot timeout on ACME vhost | DNS/TLS for `acme_public_vhost` missing | Fix DNS + cert on reverse proxy before saving vhost |
| 403 after enabling reverse proxy | ProxyFix on but proxy IP not trusted | Set `UCM_TRUSTED_PROXIES` to proxy IP |

## Tests

```bash
cd backend && python3 -m pytest tests/test_public_endpoints.py -v
```

Security-related cases: metadata hostname rejected, preflight `write:settings` only,
metadata IP not probed, private LAN `X-Forwarded-Host` blocked when ProxyFix enabled.

See [PUBLIC-ENDPOINTS-TEST-PLAN.md](./PUBLIC-ENDPOINTS-TEST-PLAN.md) for full matrix.
