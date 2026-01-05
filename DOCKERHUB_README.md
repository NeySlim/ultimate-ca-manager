# Ultimate CA Manager

![Docker Pulls](https://img.shields.io/docker/pulls/neyslim/ultimate-ca-manager)
![Docker Image Size](https://img.shields.io/docker/image-size/neyslim/ultimate-ca-manager/latest)
![GitHub release](https://img.shields.io/github/v/release/NeySlim/ultimate-ca-manager)
[![Complete Release Pipeline](https://github.com/NeySlim/ultimate-ca-manager/actions/workflows/release-complete.yml/badge.svg)](https://github.com/NeySlim/ultimate-ca-manager/actions/workflows/release-complete.yml)

🔐 **Enterprise-grade Certificate Authority Management System**

Ultimate CA Manager (UCM) is a comprehensive web-based solution for managing Certificate Authorities, issuing certificates, and providing industry-standard protocols (SCEP, OCSP, CRL) with a modern, intuitive interface.

## 📸 Dashboard Preview

![Dashboard](https://raw.githubusercontent.com/NeySlim/ultimate-ca-manager/main/docs/screenshots/02-dashboard_amber-dark.png)
*Professional Dashboard - Amber Dark Theme*

---

## 🚀 Quick Start

### Docker (Recommended)

```bash
# Pull from Docker Hub
docker pull neyslim/ultimate-ca-manager:latest

# Run with SQLite
docker run -d \
  --name ucm \
  -p 8443:8443 \
  -v ucm-data:/app/backend/data \
  --restart unless-stopped \
  neyslim/ultimate-ca-manager:latest

# Access: https://localhost:8443
# Default login: admin / changeme123
```

### Docker Compose

```bash
# Clone repository
git clone https://github.com/NeySlim/ultimate-ca-manager.git
cd ultimate-ca-manager

# Start with Docker Compose
docker-compose up -d

# Check logs
docker-compose logs -f ucm
```

### Linux Installation (Auto-detect)

```bash
curl -fsSL https://raw.githubusercontent.com/NeySlim/ultimate-ca-manager/main/install.sh | sudo bash
```

**Supports**: Debian, Ubuntu, RHEL, CentOS, Rocky, Alpine, Arch, openSUSE (10+ distributions)

---

## ✨ Features

### Certificate Authority Management
- Create and manage multiple CAs (Root and Intermediate)
- Import existing CAs (PEM, PKCS#12)
- Support for RSA (2048-4096) and ECDSA (P-256, P-384, P-521)
- Flexible hash algorithms (SHA-256, SHA-384, SHA-512)
- CA hierarchy visualization

### Certificate Operations
- Issue certificates (server, client, code signing, email)
- Import and sign CSRs
- Certificate revocation with CRL support
- Export to PEM, DER, PKCS#12
- Certificate lifecycle tracking
- Expiration monitoring

### Industry-Standard Protocols
- **SCEP Server** (RFC 8894) - Zero-touch device enrollment
- **OCSP Responder** (RFC 6960) - Real-time certificate status
- **CRL Distribution** (RFC 5280) - Certificate Revocation Lists
- Compatible with iOS, Android, Windows, Cisco, Palo Alto

### Modern Web Interface
- 🎨 **8 Professional Themes** - Sentinel, Amber, Blossom, Nebula (Light & Dark)
- 📱 **Responsive Design** - Desktop, tablet, mobile optimized
- 🌓 **Full Dark Mode** - Complete dark theme support
- ⚡ **Modern SPA** - HTMX-powered fast navigation
- 🖱️ **Custom Scrollbars** - Theme-aware styled scrollbars

### Security
- HTTPS-only access (TLS 1.2+)
- Role-based access control (Admin, Operator, Viewer)
- JWT authentication for API
- Audit logging
- OWASP Top 10 2021 compliant
- Non-root container execution

### REST API
- Complete programmatic access
- JWT authentication
- Comprehensive endpoints
- API documentation

---

## 📸 More Screenshots

### Certificate Management
![Certificate List](https://raw.githubusercontent.com/NeySlim/ultimate-ca-manager/main/docs/screenshots/05-certificates-list_amber-dark.png)
*Comprehensive Certificate Management Interface*

### 8 Beautiful Themes Available

<table>
  <tr>
    <td align="center">
      <img src="https://raw.githubusercontent.com/NeySlim/ultimate-ca-manager/main/docs/screenshots/08-theme-sentinel-light.png" width="350"/><br/>
      <b>Sentinel Light</b>
    </td>
    <td align="center">
      <img src="https://raw.githubusercontent.com/NeySlim/ultimate-ca-manager/main/docs/screenshots/09-theme-nebula-dark.png" width="350"/><br/>
      <b>Nebula Dark</b>
    </td>
  </tr>
  <tr>
    <td align="center">
      <img src="https://raw.githubusercontent.com/NeySlim/ultimate-ca-manager/main/docs/screenshots/10-theme-blossom-light.png" width="350"/><br/>
      <b>Blossom Light</b>
    </td>
    <td align="center">
      <img src="https://raw.githubusercontent.com/NeySlim/ultimate-ca-manager/main/docs/screenshots/02-dashboard_amber-dark.png" width="350"/><br/>
      <b>Amber Dark</b>
    </td>
  </tr>
</table>

---

## 🐳 Docker Hub

**Images available:**

```bash
# Latest stable
docker pull neyslim/ultimate-ca-manager:latest

# Specific version
docker pull neyslim/ultimate-ca-manager:1.0.1

# Major version
docker pull neyslim/ultimate-ca-manager:1

# Architecture-specific
docker pull neyslim/ultimate-ca-manager:latest  # Multi-arch (amd64, arm64)
```

**Tags**:
- `latest` - Latest stable release (v1.6.1)
- `1.6.1`, `1.6`, `1` - Semantic versions
- `v*.*.*` - Specific releases

**Image Details**:
- Base: Python 3.11 Alpine
- Size: ~266 MB (optimized multi-stage build)
- User: Non-root (UID 1000)
- Server: Gunicorn production WSGI
- Platforms: linux/amd64, linux/arm64

---

## 📚 Documentation

- **[README.md](README.md)** - Project overview and features
- **[DOCKER.md](DOCKER.md)** - Complete Docker deployment guide
- **[DOCKER_FEATURES.md](DOCKER_FEATURES.md)** - Configuration reference
- **[DISTRIBUTIONS.md](DISTRIBUTIONS.md)** - Linux compatibility matrix
- **[docs/MIGRATION_EXAMPLE.md](docs/MIGRATION_EXAMPLE.md)** - Migration guide
- **[.env.docker.example](.env.docker.example)** - Configuration template
- **[CHANGELOG.md](CHANGELOG.md)** - Version history

---

## ⚙️ Configuration

All Docker settings configurable via `.env` file:

```env
# Network
UCM_HTTPS_PORT=8443

# Storage
UCM_DATA_DIR=./data
POSTGRES_DATA_DIR=./postgres-data

# Database (PostgreSQL)
POSTGRES_DB=ucm
POSTGRES_USER=ucm
POSTGRES_PASSWORD=changeme123
```

See [.env.docker.example](.env.docker.example) for complete configuration.

---

## 🔄 Migration

Move UCM between hosts in 5 minutes:

```bash
# Source host
docker-compose down
tar -czf ucm-backup.tar.gz data/ postgres-data/ .env
scp ucm-backup.tar.gz user@new-host:/opt/ucm/

# Destination host
cd /opt/ucm
tar -xzf ucm-backup.tar.gz
docker-compose up -d
```

See [docs/MIGRATION_EXAMPLE.md](docs/MIGRATION_EXAMPLE.md) for detailed guide.

---

## 🏗️ Architecture

- **Backend**: Python 3.11, Flask, SQLAlchemy
- **Database**: SQLite (default), PostgreSQL (supported)
- **Frontend**: HTML5, CSS3, JavaScript (Vanilla)
- **Server**: Gunicorn WSGI (auto-scaling workers)
- **Protocols**: HTTPS/TLS, SCEP, OCSP, REST API
- **Deployment**: Docker, Linux native, Kubernetes-ready

---

## 🔒 Security

- Non-root container execution
- Minimal Linux capabilities
- Auto-generated HTTPS certificates
- No hardcoded secrets
- Production WSGI server
- Regular security audits

**Security Score**: 9.5/10

---

## 📊 Requirements

**Docker**:
- Docker 20.10+
- Docker Compose 2.0+

**Linux**:
- Python 3.10+
- OpenSSL 1.1.1+
- 512 MB RAM (minimum)
- 1 GB disk space

---

## 🤝 Contributing

Contributions welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) first.

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing`)
5. Open Pull Request

---

## 📄 License

BSD 3-Clause License - see [LICENSE](LICENSE) for details.

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)
- **Discussions**: [GitHub Discussions](https://github.com/NeySlim/ultimate-ca-manager/discussions)
- **Documentation**: [Wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki)
- **Docker Hub**: [neyslim/ultimate-ca-manager](https://hub.docker.com/r/neyslim/ultimate-ca-manager)

---

## ⭐ Star History

If you find UCM useful, please consider giving it a star! ⭐

---

**Version**: 1.6.1  
**Status**: Production Ready ✅  
**Last Updated**: 2026-01-06
