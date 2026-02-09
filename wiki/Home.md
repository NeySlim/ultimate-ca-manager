# Ultimate CA Manager - Wiki

![Version](https://img.shields.io/badge/version-1.8.3-blue.svg)
![License](https://img.shields.io/badge/license-BSD--3--Clause-green.svg)
![Docker](https://img.shields.io/badge/docker-multi--arch-blue.svg)
![CI/CD](https://img.shields.io/badge/CI%2FCD-automated-success.svg)

Welcome to the **Ultimate CA Manager (UCM)** documentation! This wiki provides comprehensive guides for installation, configuration, and usage.

---

## 📚 Table of Contents

### Getting Started
- **[Installation Guide](Installation-Guide)** - Complete installation instructions
- **[First Steps](First-Steps)** - Initial setup and configuration
- **[Quick Start](Quick-Start)** - Get running in 5 minutes

### Core Features
- **[CA Management](CA-Management)** - Certificate Authority operations
- **[Certificate Operations](Certificate-Operations)** - Issue, revoke, renew certificates
- **[CRL & CDP](CRL-CDP)** - Certificate Revocation Lists

### Protocols & Services
- **[ACME Server](ACME-Support)** - Let's Encrypt compatible
- **[SCEP Server](SCEP-Server)** - Device enrollment (iOS/Android/Windows)
- **[OCSP Responder](OCSP-Responder)** - Real-time certificate validation

### Security Features
- **[mTLS Authentication](MTLS-Authentication)** - Client certificate authentication
- **[WebAuthn Support](WebAuthn-Support)** - FIDO2/Hardware keys
- **[API Documentation](API-Documentation)** - REST API with JWT

### User Interface
- **[Dashboard](Dashboard)** - Overview and statistics
- **[Themes](Themes)** - 8 beautiful themes (light/dark)
- **[User Management](User-Management)** - Role-based access control

### Administration
- **[System Configuration](System-Config)** - HTTPS, database, settings
- **[Backup & Restore](Backup-Restore)** - Data protection
- **[Monitoring](Monitoring)** - Health checks and logs

### Advanced
- **[Building from Source](Building)** - Development setup
- **[Architecture](Architecture)** - Technical details
- **[Contributing](Contributing)** - How to contribute

### Reference
- **[FAQ](FAQ)** - Frequently asked questions
- **[Troubleshooting](Troubleshooting)** - Common issues and solutions

---

## 🚀 Quick Links

### Installation
- **Universal Installer**: `curl -fsSL https://raw.githubusercontent.com/NeySlim/ultimate-ca-manager/main/packaging/scripts/install-ucm.sh | sudo bash`
- **Docker**: `docker pull ghcr.io/neyslim/ultimate-ca-manager:1.8.3`
- **DEB**: Download from [releases](https://github.com/NeySlim/ultimate-ca-manager/releases/latest)
- **RPM**: Download from [releases](https://github.com/NeySlim/ultimate-ca-manager/releases/latest)

### Default Credentials
- **Username:** `admin`
- **Password:** `changeme123`
- ⚠️ **CHANGE IMMEDIATELY AFTER FIRST LOGIN!**

---

## 📖 What's New

### v1.8.3 (Latest) ✅ STABLE

**Release Date:** 2026-01-10

#### 🚀 Installation & Deployment
- **Universal Installer** - One-line install for all Linux distributions
  - Auto-detects OS and uses best method (DEB/RPM/source)
  - Supports Debian, Ubuntu, RHEL, Rocky, Alma, Fedora, openSUSE, Arch, Alpine
  - Zero dependencies required (only bash)
- **CI/CD Improvements**
  - Simplified GitHub Actions workflows
  - Source tarballs included in releases
  - SHA256 and MD5 checksums for all packages

#### 🎨 UI & UX Improvements
- **Navigation Fix** - mTLS settings now use `/my-account/mtls` route
- **Theme Indicator** - Active theme visible on all pages
- **Button Consistency** - Improved visibility across all themes
- **Full English Translation** - All French text translated

#### 📸 Documentation
- **Screenshots Gallery** - 16 high-quality screenshots
- **Updated Guides** - All docs reflect v1.8.3 features accurately
- **Roadmap Published** - Clear development plan through v2.0.0

#### 🔧 Technical
- **Auto-Restart** - Service automatically restarts after HTTPS cert changes
- **Service Management** - Centralized utils module for restart/reload
- **Packaging Fixes** - macOS-compatible HTTPS certificates in packages

[Read Full Release Notes](https://github.com/NeySlim/ultimate-ca-manager/releases/tag/v1.8.3)

---

### v1.8.2 - Service Management

- **Auto-restart utilities** - No sudo required for service restart
- **Certificate selection fix** - HTTPS cert dropdown now works correctly
- **Service management module** - Centralized restart/reload functions

[v1.8.2 Release Notes](Release-Notes-v1.8.2)

---

### v1.8.0 - mTLS & API Complete

- **mTLS Authentication** - Client certificate browser authentication
- **REST API Complete** - Full JWT API coverage
- **OPNsense Import** - Direct CA/certificate import
- **8 Beautiful Themes** - Sentinel, Amber, Nebula, Blossom (light/dark)

[v1.8.0 Release Notes](Release-Notes-v1.8.0-beta)

---

### v1.7.0 - ACME & WebAuthn

- **ACME Server** - RFC 8555 compliant (Let's Encrypt compatible)
- **Email Notifications** - Certificate expiration alerts
- **WebAuthn/FIDO2** - Hardware key passwordless authentication
- **CRL Enhancements** - Auto-generation, improved UI

[v1.7.0 Release Notes](Release-Notes-v1.7.0)

---

## 🗺️ Roadmap

### v2.1.0 - Current Development
- ✅ HSM Support (PKCS#11, Azure Key Vault, Google Cloud KMS)
- ✅ Let's Encrypt Proxy with DNS-01
- ✅ RBAC with custom roles
- ✅ Security Dashboard
- 🔄 Multi-tenancy (in progress)

### v2.2.0 - Planned
- GraphQL API
- Enhanced monitoring
- Bulk operations

[View Full Roadmap](https://github.com/NeySlim/ultimate-ca-manager/blob/main/ROADMAP.md)

---

## 💡 Key Features

### Complete PKI Infrastructure
- Full CA management (create, import, manage)
- Certificate lifecycle (generate, sign, revoke, renew, export)
- CRL & CDP (Certificate Revocation Lists with distribution)
- OCSP Responder (real-time certificate validation)

### Industry Standard Protocols
- **SCEP Server** - RFC 8894 compliant auto-enrollment
- **ACME Support** - Let's Encrypt compatible (certbot, acme.sh)
- **OCSP** - Online Certificate Status Protocol
- **CRL/CDP** - Certificate Revocation List distribution

### Advanced Security
- mTLS Authentication (mutual TLS certificate-based auth)
- WebAuthn/FIDO2 (hardware security key support)
- Multi-Factor Auth (multiple authentication methods)
- JWT Sessions (secure token-based authentication)
- HTTPS Only (all traffic encrypted by default)

### Modern Interface
- 8 Beautiful Themes (4 colors × light/dark variants)
- Responsive Design (works on desktop, tablet, mobile)
- Real-time Updates (HTMX-powered dynamic interface)
- Intuitive UI (clean, professional design)

### Deployment Flexibility
- Docker (multi-arch: amd64, arm64)
- Debian/Ubuntu (native .deb packages)
- RHEL/Rocky/Alma (native .rpm packages)
- Universal Installer (all Linux distributions)
- From Source (Python 3.11+ with virtual environment)

---

## 📊 Quick Reference

| Property | Value |
|----------|-------|
| Version | 1.8.3 |
| License | BSD-3-Clause |
| Language | Python 3.11+ |
| Framework | Flask |
| Database | SQLite (PostgreSQL supported) |
| Frontend | HTMX + Alpine.js |
| Default Port | 8443 (HTTPS) |

---

## 🔗 External Links

- **GitHub Repository**: https://github.com/NeySlim/ultimate-ca-manager
- **Docker Registry**: https://ghcr.io/neyslim/ultimate-ca-manager
- **Latest Release**: https://github.com/NeySlim/ultimate-ca-manager/releases/latest
- **Issue Tracker**: https://github.com/NeySlim/ultimate-ca-manager/issues
- **Discussions**: https://github.com/NeySlim/ultimate-ca-manager/discussions

---

## 📜 Release History

- **[v1.8.3 Release](https://github.com/NeySlim/ultimate-ca-manager/releases/tag/v1.8.3)** - Latest stable
- **[v1.8.2 Release](Release-Notes-v1.8.2)** - Service management
- **[v1.8.0 Release](Release-Notes-v1.8.0-beta)** - mTLS & API
- **[v1.7.0 Release](Release-Notes-v1.7.0)** - ACME & WebAuthn
- **[v1.6.2 Release](Release-Notes-v1.6.2)** - CRL improvements
- **[v1.6.0 Release](Release-Notes-v1.6.0)** - SCEP support

---

**Need help?** Check the [FAQ](FAQ) or [Troubleshooting](Troubleshooting) guide.

**Want to contribute?** See [Contributing](Contributing) guide.
