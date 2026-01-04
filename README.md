<div align="center">

# Ultimate CA Manager

![Version](https://img.shields.io/badge/version-1.0.1-blue.svg)
![License](https://img.shields.io/badge/license-BSD--3--Clause-green.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![Platform](https://img.shields.io/badge/platform-Linux-lightgrey.svg)
![Docker](https://img.shields.io/docker/pulls/neyslim/ultimate-ca-manager.svg)
![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)

**Production-ready Certificate Authority management system with SCEP, OCSP, and modern web UI**

**📚 [Documentation Wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki) • 🚀 [Quick Start](https://github.com/NeySlim/ultimate-ca-manager/wiki/Quick-Start) • 🐳 [Docker Hub](https://hub.docker.com/r/neyslim/ultimate-ca-manager)**

</div>

---

## ✨ Key Features

- 🔐 **Certificate Authority Management** - Create Root/Intermediate CAs, multi-level hierarchy, flexible key types (RSA, ECDSA)
- 📜 **Certificate Lifecycle** - Issue, renew, revoke certificates with full CRL and OCSP support
- 🔄 **SCEP Server (RFC 8894)** - Auto-enrollment for iOS, Android, Windows, Cisco, network devices
- 🛡️ **Enterprise Security** - RBAC, audit logging, HTTPS-only, OWASP compliant (9.5/10)
- 🎨 **Modern Web UI** - Responsive design, dark/light themes, real-time dashboard
- 🌍 **Platform Agnostic** - Docker, any Linux distribution, SQLite or PostgreSQL
- 🔗 **REST API** - Complete programmatic access for automation and integration

**👉 [See all features in the Wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki/User-Manual)**

---

## 🚀 Quick Start

### Docker (Recommended)

```bash
# Download and start
curl -O https://raw.githubusercontent.com/NeySlim/ultimate-ca-manager/main/docker-compose.yml
docker-compose up -d

# Access: https://localhost:8443
# Login: admin / admin
```

### Linux Installation

```bash
# One-line install
curl -fsSL https://raw.githubusercontent.com/NeySlim/ultimate-ca-manager/main/install.sh | sudo bash

# Access: https://your-server-ip:8443
# Login: admin / admin
```

⚠️ **Change default password immediately after first login!**

**📖 Complete guide**: [Quick Start Tutorial](https://github.com/NeySlim/ultimate-ca-manager/wiki/Quick-Start) (10 minutes)

---

## 📚 Documentation

All documentation is available in the **[GitHub Wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki)**:

| Guide | Description |
|-------|-------------|
| **[Quick Start](https://github.com/NeySlim/ultimate-ca-manager/wiki/Quick-Start)** | Get started in 10 minutes |
| **[User Manual](https://github.com/NeySlim/ultimate-ca-manager/wiki/User-Manual)** | Complete user guide with examples |
| **[API Reference](https://github.com/NeySlim/ultimate-ca-manager/wiki/API-Reference)** | REST API documentation |
| **[FAQ](https://github.com/NeySlim/ultimate-ca-manager/wiki/FAQ)** | Frequently asked questions |
| **[Troubleshooting](https://github.com/NeySlim/ultimate-ca-manager/wiki/Troubleshooting)** | Problem solving guide |

**Additional resources**:
- [Docker Features & Configuration](DOCKER_FEATURES.md) - Advanced Docker deployment
- [Migration Guide](docs/MIGRATION_EXAMPLE.md) - Server-to-server migration
- [Architecture Diagrams](docs/diagrams/ARCHITECTURE.md) - System architecture

---

## 🐳 Docker Deployment

Pre-built multi-architecture images:

```bash
docker pull neyslim/ultimate-ca-manager:latest
```

**Available tags**: `latest`, `1.0.1`, `1.0`, `1`  
**Architectures**: `linux/amd64`, `linux/arm64`

[See Docker documentation →](DOCKER_FEATURES.md)

---

## 🔌 REST API

Complete REST API for automation:

```bash
# Login
curl -X POST https://localhost:8443/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' \
  -k

# List CAs
curl https://localhost:8443/api/v1/cas \
  -H "Authorization: Bearer <token>" \
  -k
```

[Full API documentation →](https://github.com/NeySlim/ultimate-ca-manager/wiki/API-Reference)

---

## 📋 System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **OS** | Any Linux | Ubuntu 22.04 LTS |
| **Python** | 3.10+ | 3.11+ |
| **RAM** | 512 MB | 2 GB |
| **Disk** | 100 MB + certificates | 1 GB SSD |
| **CPU** | 1 core | 2+ cores |

**Supported distributions**: Debian, Ubuntu, RHEL, Rocky, Alma, Fedora, Alpine, Arch, openSUSE

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the BSD-3-Clause License - see the [LICENSE](LICENSE) file for details.

---

## 🆘 Support

- **📚 Documentation**: [GitHub Wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki)
- **🐛 Bug Reports**: [GitHub Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)
- **💬 Discussions**: [GitHub Discussions](https://github.com/NeySlim/ultimate-ca-manager/discussions)
- **📦 Docker Hub**: [neyslim/ultimate-ca-manager](https://hub.docker.com/r/neyslim/ultimate-ca-manager)

---

## ⭐ Show Your Support

If you find UCM useful, please consider:
- ⭐ Starring this repository
- 🐛 Reporting bugs
- 💡 Suggesting features
- 📖 Improving documentation
- 🔀 Contributing code

---

<div align="center">

**Made with ❤️ for the PKI community**

[![GitHub stars](https://img.shields.io/github/stars/NeySlim/ultimate-ca-manager?style=social)](https://github.com/NeySlim/ultimate-ca-manager/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/NeySlim/ultimate-ca-manager?style=social)](https://github.com/NeySlim/ultimate-ca-manager/network/members)

</div>
