# Ultimate CA Manager

![Version](https://img.shields.io/github/v/release/NeySlim/ultimate-ca-manager?label=version&color=brightgreen)
![License](https://img.shields.io/badge/license-BSD--3--Clause-green.svg)
![Docker](https://img.shields.io/docker/v/neyslim/ultimate-ca-manager?label=docker&color=blue)
![CI/CD](https://img.shields.io/github/actions/workflow/status/NeySlim/ultimate-ca-manager/tests.yml?label=tests)

**Ultimate CA Manager (UCM)** is a comprehensive Certificate Authority management platform with full PKI protocol support (SCEP, OCSP, ACME, CRL/CDP), multi-factor authentication, and complete certificate lifecycle management.

![Dashboard](docs/screenshots/dashboard-dark.png)

---

## Features

- **Full CA & Certificate Lifecycle** — Create, sign, revoke, renew, export certificates and CAs with hierarchy support
- **Industry Protocols** — SCEP (RFC 8894), ACME (Let's Encrypt compatible), OCSP (RFC 6960), CRL/CDP
- **Certificate Toolbox** — SSL checker, CSR/cert decoder, key matcher, format converter (PEM, DER, PKCS#12, PKCS#7)
- **Advanced Security** — WebAuthn/FIDO2, mTLS, TOTP 2FA, audit logs with hash chain integrity, rate limiting
- **Modern UI** — React 18 + Radix UI, 12 themes (6 colors × light/dark), responsive mobile-first design, command palette (Ctrl+K)
- **User Management** — Groups, API keys, session tracking, force password change
- **Import/Export** — Smart parser (drag & drop), OPNsense import, bulk export, backup & restore
- **Multi-platform** — Docker (amd64/arm64), Debian/Ubuntu (.deb), RHEL/Rocky/Fedora (.rpm)

---

## Screenshots

<table>
<tr>
<td width="50%"><img src="docs/screenshots/dashboard.png" alt="Dashboard"><br><b>Dashboard</b></td>
<td width="50%"><img src="docs/screenshots/cas.png" alt="CAs"><br><b>CA Management</b></td>
</tr>
<tr>
<td width="50%"><img src="docs/screenshots/certificates.png" alt="Certificates"><br><b>Certificates</b></td>
<td width="50%"><img src="docs/screenshots/theme-panel.png" alt="Themes"><br><b>12 Theme Variants</b></td>
</tr>
</table>

See more: **[Full Gallery](docs/SCREENSHOTS.md)**

---

## Quick Start

### Docker (Recommended)

```bash
docker run -d --restart=unless-stopped \
  --name ucm -p 8443:8443 \
  -v ucm-data:/opt/ucm/data \
  neyslim/ultimate-ca-manager:latest
```

### Docker Compose

```yaml
services:
  ucm:
    image: neyslim/ultimate-ca-manager:latest
    ports: ["8443:8443"]
    volumes: ["./data:/opt/ucm/data"]
    restart: unless-stopped
```

### Debian/Ubuntu

```bash
wget https://github.com/NeySlim/ultimate-ca-manager/releases/latest/download/ucm_all.deb
sudo apt install -y python3-venv python3-pip && sudo dpkg -i ucm_*.deb
```

### RHEL/Rocky/Fedora

```bash
wget https://github.com/NeySlim/ultimate-ca-manager/releases/latest/download/ucm.noarch.rpm
sudo dnf install ./ucm-*.rpm
```

### Universal Installer

```bash
curl -fsSL https://raw.githubusercontent.com/NeySlim/ultimate-ca-manager/main/packaging/scripts/install-ucm.sh | sudo bash
```

**Access:** https://localhost:8443 — **Credentials:** admin / (shown during install or in `/etc/ucm/ucm.env`)

---

## API

RESTful JSON API under `/api/v2/`. See [OpenAPI spec](docs/openapi.yaml) and [Wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki/API-Documentation).

| Resource | Endpoints |
|----------|-----------|
| **Auth** | `POST /auth/login`, `/logout`, `/verify` |
| **CAs** | `GET/POST /cas`, `GET/PUT/DELETE /cas/{id}` |
| **Certificates** | `GET/POST /certificates`, `.../revoke`, `.../renew` |
| **CSRs** | `GET/POST /csrs`, `POST /csrs/{id}/sign` |
| **SCEP** | `GET /scep/pkiclient.exe` |
| **OCSP** | `POST /ocsp` |
| **CRL** | `GET /crl/{ca_id}` |

---

## Tech Stack

**Frontend:** React 18, Vite, Radix UI · **Backend:** Python 3.11+, Flask, SQLAlchemy · **Database:** SQLite · **Server:** Gunicorn + gevent WebSocket · **Auth:** JWT, WebAuthn/FIDO2, TOTP

---

## Documentation

Full docs on the **[Wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki)**: [Installation](https://github.com/NeySlim/ultimate-ca-manager/wiki/Installation-Guide) · [Quick Start](https://github.com/NeySlim/ultimate-ca-manager/wiki/Quick-Start) · [SCEP](https://github.com/NeySlim/ultimate-ca-manager/wiki/SCEP-Server) · [ACME](https://github.com/NeySlim/ultimate-ca-manager/wiki/ACME-Support) · [Troubleshooting](https://github.com/NeySlim/ultimate-ca-manager/wiki/Troubleshooting)

---

## Contributing

See [CONTRIBUTING.md](docs/development/contributing.md). Fork → branch → commit → PR.

## License

BSD 3-Clause — See [LICENSE](LICENSE).

## Support

[Issues](https://github.com/NeySlim/ultimate-ca-manager/issues) · [Wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki) · [Discussions](https://github.com/NeySlim/ultimate-ca-manager/discussions)

