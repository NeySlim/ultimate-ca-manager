# Ultimate CA Manager - Wiki

![Version](https://img.shields.io/badge/version-1.6.1-blue.svg)
![License](https://img.shields.io/badge/license-BSD--3--Clause-green.svg)

Welcome to the **Ultimate CA Manager (UCM)** documentation! This wiki provides comprehensive guides for all features.

---

## 📚 Table of Contents

### Getting Started
- [Installation Guide](Installation-Guide)
- [Quick Start](Quick-Start)
- [First Steps](First-Steps)
- [Configuration](Configuration)

### Core Features
- [Certificate Authority Management](CA-Management)
- [Certificate Operations](Certificate-Operations)
- [CRL & CDP Distribution](CRL-CDP)
- [SCEP Server](SCEP-Server)
- [OCSP Responder](OCSP-Responder)

### User Interface
- [Dashboard Overview](Dashboard)
- [Theme Customization](Themes)
- [User Settings](User-Settings)
- [API Access](API-Documentation)

### Advanced Topics
- [Import from OPNsense](Import-OPNsense)
- [Certificate Export](Certificate-Export)
- [Troubleshooting](Troubleshooting)
- [Security Best Practices](Security)

### Administration
- [User Management](User-Management)
- [System Configuration](System-Config)
- [Backup & Restore](Backup-Restore)
- [Monitoring](Monitoring)

### Development
- [Building from Source](Building)
- [Contributing](Contributing)
- [API Reference](API-Reference)
- [Architecture](Architecture)

---

## 🚀 Quick Links

- **Installation**: `sudo dpkg -i ucm_1.6.1_all.deb`
- **Web UI**: `https://your-server:8443`
- **Default Credentials**: `admin` / `changeme123` ⚠️ Change immediately!
- **GitHub**: [NeySlim/ultimate-ca-manager](https://github.com/NeySlim/ultimate-ca-manager)

---

## 📖 What's New

### v1.6.1 (Latest)
- 🐛 Fixed missing Docker files (Dockerfile, entrypoint.sh, wsgi.py, gunicorn.conf.py)
- ✅ All 4 GitHub Actions workflows now passing
- 🐳 Docker Hub multi-arch builds (amd64/arm64)
- 📦 Automated .deb and .rpm package builds

### v1.6.0
- ✨ Complete Tailwind CSS removal (~827 classes)
- 🎨 Custom themed scrollbars
- 🔐 CRL Information pages (public & integrated)
- 🎭 Modal system improvements
- 📱 Full responsive design
- 🌈 8 beautiful themes

[See Full Changelog](https://github.com/NeySlim/ultimate-ca-manager/blob/main/CHANGELOG.md)

---

## 💡 Need Help?

- **Issues**: [GitHub Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)
- **Discussions**: [GitHub Discussions](https://github.com/NeySlim/ultimate-ca-manager/discussions)
- **Documentation**: This wiki

---

**Last Updated**: 2026-01-07  
**Maintained By**: NeySlim
