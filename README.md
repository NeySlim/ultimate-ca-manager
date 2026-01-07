# Ultimate CA Manager

![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)

**Ultimate CA Manager (UCM)** - Complete Certificate Authority management with SCEP support.

## ✨ Features

- 🔐 **HTTPS Only** - Auto-generated self-signed certificates
- 🔑 **Full CA Management** - Create, import, manage Certificate Authorities
- 📜 **Certificate Operations** - Generate, sign, revoke, export
- 🔄 **SCEP Server** - RFC 8894 compliant auto-enrollment
- 🔗 **OPNsense Import** - Direct import from OPNsense
- 🎨 **Themable UI** - Multiple themes
- 👥 **User Management** - Role-based access control
- ⚙️ **Web Configuration** - All settings via web UI
- 📦 **Portable** - SQLite database

## 🚀 Quick Start

```bash
./scripts/setup.sh
./scripts/start.sh
```

**Server:** https://localhost:8443  
**Credentials:** admin / changeme123 ⚠️ CHANGE IMMEDIATELY!

## 📡 API

- `/api/v1/auth/*` - Authentication
- `/api/v1/ca/*` - Certificate Authorities
- `/api/v1/certificates/*` - Certificates
- `/api/v1/system/*` - Configuration
- `/scep/pkiclient.exe` - SCEP enrollment

## 📄 License

BSD 3-Clause License
