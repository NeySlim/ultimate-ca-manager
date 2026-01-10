# UCM v1.8.3 - Package Deployment & UI Polish

**Release Date**: 2026-01-10  
**Type**: Patch Release (Bug Fixes + Deployment Improvements)

---

## 🎯 Highlights

This release focuses on **deployment infrastructure modernization** and UI polish:

- ✅ **Modern HTTPS Certificates** - Compatible with macOS/Safari/Chrome (digitalSignature)
- ✅ **Clean Package System** - DEB/RPM use proper packaging structure
- ✅ **Systemd Wrapper** - Proper environment variable handling
- ✅ **UI Translation** - Complete French → English for all orphaned strings
- ✅ **Theme Persistence** - Active theme indicator on all pages

---

## 📦 Deployment Improvements

### DEB Package (Debian/Ubuntu)
- ✨ **Modern HTTPS Certificate Generation**
  - Includes `digitalSignature` extension (required by Safari/macOS)
  - `keyUsage = critical, digitalSignature, keyEncipherment, keyAgreement`
  - Subject Alternative Names (SAN) with DNS + IP + wildcard
  - SHA-256 signature algorithm
  
- ✨ **Systemd Service Improvements**
  - Wrapper script `/opt/ucm/start-ucm.sh` for proper ENV loading
  - Type=simple instead of Type=notify (more reliable)
  - Proper ReadWritePaths for database access
  
- ✨ **Clean Package Structure**
  - Uses files from `packaging/debian/` instead of inline generation
  - Non-interactive postinst for GitHub Actions builds
  - Creates `/var/log/ucm`, `/var/lib/ucm`, `/etc/ucm` with correct permissions

### RPM Package (RHEL/CentOS/Fedora)
- ✨ **Modern HTTPS Certificate** - Same improvements as DEB
- ✅ Certificate auto-generated in `%post` section
- ✅ Compatible with all modern browsers

### Docker
- ✅ Already generates modern certificates in entrypoint (unchanged)

---

## 🐛 Bug Fixes

### UI/UX Fixes
- 🔧 **Theme Indicator** - Now visible on all pages, not just dashboard
- 🔧 **Button Visibility** - Fixed missing `btn-success` and `btn-warning` classes
- 🔧 **Translation Complete** - All French strings translated to English:
  - Table headers (Nom, Date de création, etc.)
  - Search placeholders
  - Orphaned CAs backend text
  
### Backend Fixes
- 🔧 **Certificate Source Bug** - Fixed selection in Settings page
- 🔧 **Auto-Restart** - Server restarts automatically after HTTPS certificate changes
- 🔧 **Gunicorn Config** - Added missing `gunicorn_config.py` for native installations
- 🔧 **Service Update** - Force systemd service file update during package upgrade

---

## 🔧 Technical Changes

### New Files
```
packaging/debian/
├── start-ucm.sh           # Systemd wrapper script
└── postinst-simple.sh     # Modern certificate generation

packaging/rpm/
└── ucm.spec               # Updated with modern cert generation
```

### Modified Files
- `.github/workflows/build-deb.yml` - Uses packaging files instead of inline
- `packaging/debian/ucm.service` - Type=simple with wrapper
- `packaging/rpm/ucm.spec` - Modern certificate in %post
- `backend/gunicorn_config.py` - Added for native installations

### Certificate Configuration
```ini
[v3_req]
keyUsage = critical, digitalSignature, keyEncipherment, keyAgreement
extendedKeyUsage = serverAuth
subjectAltName = @alt_names
basicConstraints = critical, CA:FALSE
subjectKeyIdentifier = hash

[alt_names]
DNS.1 = hostname.domain.com
DNS.2 = localhost
DNS.3 = *.domain.com        # Wildcard
IP.1 = 192.168.1.X
IP.2 = 127.0.0.1
```

---

## 📊 Changes Since v1.8.2

### Added
- Modern HTTPS certificate generation for DEB/RPM
- Systemd wrapper script for environment loading
- Complete English translation
- Active theme indicator on all pages
- `btn-success` and `btn-warning` button classes
- Centralized service management utility

### Fixed
- ERR_SSL_KEY_USAGE_INCOMPATIBLE on macOS/Safari
- Theme indicator only showing on dashboard
- French strings in tables and search fields
- Certificate source selection bug in Settings
- Missing gunicorn_config.py file
- Systemd service not updating on upgrade

### Changed
- Package structure to use `packaging/` files
- Service type from notify to simple
- Docker restart messages for clarity

### Removed
- Backup and obsolete template files
- Inline package generation in GitHub workflows

---

## 🚀 Upgrade Instructions

### From v1.8.2 to v1.8.3

#### DEB (Debian/Ubuntu)
```bash
# Download package
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.8.3/ucm_1.8.3_all.deb

# Install/Upgrade
sudo dpkg -i ucm_1.8.3_all.deb

# Service will restart automatically
systemctl status ucm
```

#### RPM (RHEL/CentOS/Fedora)
```bash
# Download package
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.8.3/ucm-1.8.3.x86_64.rpm

# Install/Upgrade
sudo rpm -Uvh ucm-1.8.3.x86_64.rpm

# Start service if needed
sudo systemctl start ucm
```

#### Docker
```bash
# Pull latest image
docker pull ghcr.io/neyslim/ultimate-ca-manager:1.8.3
docker pull ghcr.io/neyslim/ultimate-ca-manager:latest

# Restart container
docker-compose down
docker-compose up -d
```

### ⚠️ Breaking Changes
**None** - This is a drop-in replacement for v1.8.2

### 🔐 Security Notes
- New HTTPS certificates are automatically generated with modern security standards
- Old certificates remain valid but should be regenerated for macOS compatibility:
  ```bash
  # Regenerate certificate
  sudo rm /var/lib/ucm/https_*.pem  # DEB
  sudo rm /etc/ucm/https_*.pem      # RPM
  sudo systemctl restart ucm
  ```

---

## 📝 Installation

### Fresh Install - DEB
```bash
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.8.3/ucm_1.8.3_all.deb
sudo dpkg -i ucm_1.8.3_all.deb
```

### Fresh Install - RPM
```bash
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.8.3/ucm-1.8.3.x86_64.rpm
sudo rpm -i ucm-1.8.3.x86_64.rpm
```

### Fresh Install - Docker
```bash
docker run -d \
  -p 8443:8443 \
  -v ucm-data:/var/lib/ucm \
  --name ucm \
  ghcr.io/neyslim/ultimate-ca-manager:1.8.3
```

---

## 🐛 Known Issues

None currently identified.

---

## 📚 Documentation

- **GitHub Wiki**: https://github.com/NeySlim/ultimate-ca-manager/wiki
- **Installation Guide**: See `docs/INSTALLATION.md`
- **Docker Guide**: See `DOCKER_QUICKSTART.md`
- **API Documentation**: https://your-ucm:8443/api/docs

---

## 🙏 Contributors

Special thanks to all contributors who helped with testing and feedback!

---

## 📄 Full Changelog

**Commits since v1.8.2**: 22 commits
- 8 bug fixes
- 6 deployment improvements  
- 5 UI/UX enhancements
- 3 documentation updates

See the [full commit log](https://github.com/NeySlim/ultimate-ca-manager/compare/v1.8.2...v1.8.3) for details.

---

**SHA256 Checksums**:
- `ucm_1.8.3_all.deb`: (to be added)
- `ucm-1.8.3.x86_64.rpm`: (to be added)
- Docker image: `ghcr.io/neyslim/ultimate-ca-manager:1.8.3`
