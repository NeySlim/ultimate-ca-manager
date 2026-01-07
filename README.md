# Ultimate CA Manager

![Version](https://img.shields.io/badge/version-1.6.2-blue.svg)
![License](https://img.shields.io/badge/license-BSD--3--Clause-green.svg)
![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![Docker](https://img.shields.io/docker/pulls/neyslim/ultimate-ca-manager)
[![Complete Release Pipeline](https://github.com/NeySlim/ultimate-ca-manager/actions/workflows/release-complete.yml/badge.svg)](https://github.com/NeySlim/ultimate-ca-manager/actions/workflows/release-complete.yml)

**Ultimate CA Manager (UCM)** - Complete Certificate Authority management system with modern theming and RFC-compliant protocols.

## 📸 Dashboard Preview

![Dashboard](docs/screenshots/02-dashboard_amber-dark.png)
*Professional Dashboard - Amber Dark Theme*

## ✨ Features

### Core CA Management
- 🔐 **HTTPS Only** - Auto-generated self-signed certificates
- 🔑 **Full CA Management** - Create, import, manage Certificate Authorities
- 📜 **Certificate Operations** - Generate, sign, revoke, export (PEM, DER, PKCS#12)
- 🔄 **CRL Distribution** - RFC 5280 compliant CRL Distribution Points
- 🟢 **OCSP Responder** - Real-time certificate status validation
- 🔗 **SCEP Server** - RFC 8894 compliant auto-enrollment

### User Experience
- 🎨 **8 Beautiful Themes** - Sentinel, Amber, Blossom, Nebula (Light & Dark)
- 🖱️ **Custom Scrollbars** - Theme-aware styled scrollbars
- 🌓 **Full Dark Mode** - Complete dark theme support
- 📱 **Responsive UI** - Works on desktop and mobile
- ⚡ **HTMX Powered** - Fast, modern SPA experience
- 🔒 **Modal Body Lock** - Smooth modal interactions

### Integration & Import
- 🔗 **OPNsense Import** - Direct import from OPNsense
- 📥 **CA Import** - Import existing CAs (PEM, PKCS#12)
- 📤 **Flexible Export** - Multiple export formats
- 🔌 **REST API** - Full API access

### Security & Compliance
- 👥 **User Management** - Role-based access control
- 🔐 **JWT Authentication** - Secure session management
- 📋 **RFC Compliant** - Follows PKI standards
- 🔒 **Public Endpoints** - CDP/OCSP accessible without auth

## 📸 More Screenshots

### Certificate Authority Management
![CA Management](docs/screenshots/04-ca-detail_amber-dark.png)

### Certificate List
![Certificates](docs/screenshots/05-certificates-list_amber-dark.png)

### 8 Beautiful Themes Available
<table>
  <tr>
    <td><img src="docs/screenshots/08-theme-sentinel-light.png" alt="Sentinel Light" width="400"/><br/><i>Sentinel Light</i></td>
    <td><img src="docs/screenshots/09-theme-nebula-dark.png" alt="Nebula Dark" width="400"/><br/><i>Nebula Dark</i></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/10-theme-blossom-light.png" alt="Blossom Light" width="400"/><br/><i>Blossom Light</i></td>
    <td><img src="docs/screenshots/02-dashboard_amber-dark.png" alt="Amber Dark" width="400"/><br/><i>Amber Dark</i></td>
  </tr>
</table>

## 🚀 Quick Start

### Debian/Ubuntu Installation

```bash
# Download package
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.6.2/ultimate-ca-manager_1.6.2_amd64.deb

# Install
sudo dpkg -i ultimate-ca-manager_1.6.2_amd64.deb

# Service will start automatically
```

### Manual Installation

```bash
# Clone repository
git clone https://github.com/NeySlim/ultimate-ca-manager.git
cd ultimate-ca-manager

# Run installation script
sudo ./install.sh

# Start service
sudo systemctl start ucm
```

**Web Interface:** https://your-server-ip:8443  
**Default Credentials:** admin / changeme123 ⚠️ **CHANGE IMMEDIATELY!**

## 📡 API Endpoints

### Authentication
- `POST /api/v1/auth/login` - User login
- `POST /api/v1/auth/logout` - User logout
- `GET /api/v1/auth/me` - Get current user

### Certificate Authorities
- `GET /api/v1/ca/` - List all CAs
- `POST /api/v1/ca/` - Create new CA
- `GET /api/v1/ca/{id}` - Get CA details
- `POST /api/v1/ca/{id}/revoke` - Revoke CA
- `GET /api/v1/ca/{id}/export` - Export CA

### Certificates
- `GET /api/v1/certificates/` - List all certificates
- `POST /api/v1/certificates/` - Create certificate
- `GET /api/v1/certificates/{id}` - Get certificate details
- `POST /api/v1/certificates/{id}/revoke` - Revoke certificate
- `GET /api/v1/certificates/{id}/export` - Export certificate

### CRL & OCSP (Public Endpoints)
- `GET /cdp/{ca_refid}/crl.pem` - Download CRL (PEM)
- `GET /cdp/{ca_refid}/crl.der` - Download CRL (DER)
- `GET /cdp/{ca_refid}/info` - CRL information
- `POST /ocsp` - OCSP status request

### SCEP (Public Endpoints)
- `GET /scep/pkiclient.exe` - SCEP enrollment
- `POST /scep/pkiclient.exe` - SCEP operations

## 🎨 Themes

UCM includes 8 professionally designed themes:

**Light Themes:**
- **Sentinel Light** - Clean and professional
- **Amber Light** - Warm and inviting
- **Blossom Light** - Soft and elegant
- **Nebula Light** - Modern and vibrant

**Dark Themes:**
- **Sentinel Dark** - Professional dark mode
- **Amber Dark** - Warm dark palette
- **Blossom Dark** - Elegant dark theme
- **Nebula Dark** - Vibrant dark mode

All themes feature:
- Custom styled scrollbars
- Consistent color schemes
- Smooth transitions
- Optimized contrast ratios

## 📦 What's New in 1.6.2

### Latest Changes (v1.6.2) - Critical Bugfixes
- 🐛 **OPNsense Import Fixed** - Resolved critical JavaScript errors blocking configuration imports
- ✅ **Toast Notifications** - Added global showToast() function for reliable user feedback
- 🔧 **Simplified Import** - Streamlined to API Key authentication only (removed username/password)
- 📊 **Accurate Statistics** - Fixed import result display showing correct CA and certificate counts

### Previous Release (v1.6.1)
- 🐛 **Docker Files** - Fixed missing Dockerfile, entrypoint.sh, wsgi.py, gunicorn.conf.py
- ✅ **CI/CD** - All 4 GitHub Actions workflows passing
- 🐳 **Multi-arch** - Docker Hub builds for amd64/arm64
- 📦 **Packages** - Automated .deb and .rpm package builds

See [CHANGELOG.md](CHANGELOG.md) for complete details.

## 🛠️ Development

### Requirements
- Python 3.11+
- Flask 3.0+
- SQLite 3
- OpenSSL

### Setup Development Environment

```bash
# Clone repository
git clone https://github.com/NeySlim/ultimate-ca-manager.git
cd ultimate-ca-manager

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Initialize database
python backend/init_db.py

# Run development server
python backend/app.py
```

### Build Debian Package

```bash
# Build package
./build_deb.sh

# Package will be created as ultimate-ca-manager_1.6.2_amd64.deb
```

## 📚 Documentation

- [Installation Guide](INSTALLATION.md)
- [API Documentation](docs/API.md)
- [SCEP Setup Guide](docs/SCEP.md)
- [Changelog](CHANGELOG.md)

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

BSD 3-Clause License - See [LICENSE](LICENSE) file for details

## 🙏 Acknowledgments

- Flask framework
- HTMX for modern interactions
- Alpine.js for reactive components
- Font Awesome for icons
- All contributors and testers

---

**Made with ❤️ by the UCM Team**
