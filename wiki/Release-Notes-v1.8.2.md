# Release Notes - v1.8.2

**Release Date:** January 10, 2026  
**Status:** ✅ STABLE - Production Ready  
**Download:** [GitHub Releases](https://github.com/NeySlim/ultimate-ca-manager/releases/tag/v1.8.2)

---

## 🐛 Critical Bug Fix

### Nginx Dependency Made Optional

**Problem:** Previous versions (v1.8.3 and v1.8.1) forced nginx installation due to a bug in the GitHub Actions workflow, even though UCM includes a built-in HTTPS server.

**Root Cause:** The build workflow generated its own package `control` file with nginx hardcoded in `Depends:`, ignoring the repository's correct configuration.

**Solution:**
- Fixed `.github/workflows/build-deb.yml` to match repository configuration
- **Depends:** python3, python3-pip, python3-venv, systemd (essentials only)
- **Recommends:** python3-flask-caching, python3-redis (performance)
- **Suggests:** nginx, apache2, certbot, python3-gunicorn (optional)

---

## 📦 Installation

### Debian/Ubuntu

```bash
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.8.2/ucm_1.8.2_all.deb
sudo dpkg -i ucm_1.8.2_all.deb
# ✅ No nginx installation required!
```

### Docker

```bash
docker pull ghcr.io/neyslim/ultimate-ca-manager:1.8.2
# or
docker pull ghcr.io/neyslim/ultimate-ca-manager:latest
```

### RPM (⚠️ UNTESTED)

```bash
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.8.2/ucm-1.8.2-1.el9.noarch.rpm
sudo dnf install ucm-1.8.2-1.el9.noarch.rpm
```

---

## 🚀 Deployment Options

UCM is flexible - choose what works for you:

### 1. Standalone (No Reverse Proxy)
Perfect for testing, homelab, small deployments.

```bash
# UCM runs on built-in HTTPS server (port 8443)
sudo systemctl start ucm
```

**Access:** https://your-server:8443

### 2. With Reverse Proxy (Production)
Recommended for production environments.

```bash
# Install UCM
sudo dpkg -i ucm_1.8.2_all.deb

# Install nginx (optional)
sudo apt install nginx

# Configure nginx as reverse proxy
# See: Nginx Configuration Guide
```

**Benefits:**
- Load balancing
- SSL/TLS termination
- Serve multiple applications
- Caching and compression

### 3. Docker
Perfect for containers and orchestration.

```bash
docker run -d \
  --name ucm \
  -p 8443:8443 \
  -v ucm-data:/app/backend/data \
  ghcr.io/neyslim/ultimate-ca-manager:1.8.2
```

---

## 🔄 Migration from v1.8.3 / v1.8.1

### Remove Old Version

```bash
sudo apt remove ucm
sudo apt autoremove  # Remove nginx if it was auto-installed
```

### Install v1.8.2

```bash
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.8.2/ucm_1.8.2_all.deb
sudo dpkg -i ucm_1.8.2_all.deb
sudo systemctl restart ucm
```

**Data Migration:** Not required - all data preserved!

---

## 📋 Features (Unchanged from v1.8.3-beta)

All features from v1.8.3-beta are preserved:

### 🔐 Complete PKI Infrastructure
- Full CA management (Root, Intermediate, Sub-CA)
- Certificate lifecycle (create, sign, revoke, renew, export)
- CRL & CDP (Certificate Revocation Lists)
- OCSP Responder (RFC 6960)

### 📡 Industry Protocols
- **ACME** (RFC 8555) - Let's Encrypt compatible
- **SCEP** (RFC 8894) - Device auto-enrollment
- **OCSP** - Real-time certificate status
- **CRL/CDP** - Revocation list distribution

### 🔒 Advanced Security
- **mTLS Authentication** - Client certificate auth
- **WebAuthn/FIDO2** - Hardware security keys (YubiKey, etc.)
- **JWT Sessions** - Secure token-based auth
- **Export Authentication** - All exports require JWT tokens

### 🎨 Modern Interface
- **8 Themes** - Light & dark variants (Sentinel, Amber, Blossom, Nebula)
- **Visual Theme Previews** - 2×4 grid with live previews
- **HTMX-Powered** - No page reloads
- **Responsive Design** - Desktop, tablet, mobile

### 🔌 REST API
- Complete JWT-authenticated API
- Certificate operations
- CA management
- OCSP/SCEP/ACME endpoints

---

## 📊 Changes from v1.8.1

### Fixed
- `.github/workflows/build-deb.yml` - Removed nginx from hard dependencies
- Package description enhanced with complete feature list

### Improved
- Documentation clarity on deployment options
- Package metadata with all protocols listed

### No Breaking Changes
All v1.8.3-beta features preserved and working.

---

## 🧪 Verification

Test that nginx is NOT required:

```bash
# Download package
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.8.2/ucm_1.8.2_all.deb

# Inspect dependencies
dpkg-deb -I ucm_1.8.2_all.deb | grep Depends:
# Should show: python3, pip, venv, systemd (NO nginx!)

# Install
sudo dpkg -i ucm_1.8.2_all.deb
# ✅ SUCCESS - No nginx dependency error!
```

---

## 📝 Documentation Updates

- README.md - Updated to v1.8.2
- UPGRADE.md - Updated upgrade instructions
- DOCKER_QUICKSTART.md - Updated Docker examples
- CHANGELOG.md - Added v1.8.2 and v1.8.3-beta entries

---

## 🔗 Links

- **GitHub Release:** https://github.com/NeySlim/ultimate-ca-manager/releases/tag/v1.8.2
- **Docker Image:** ghcr.io/neyslim/ultimate-ca-manager:1.8.2
- **Installation Guide:** [Installation-Guide](Installation-Guide)
- **Quick Start:** [Quick-Start](Quick-Start)
- **Previous Release:** [v1.8.3-beta](Release-Notes-v1.8.3-beta)

---

## 💡 Support

- **Issues:** https://github.com/NeySlim/ultimate-ca-manager/issues
- **Wiki:** https://github.com/NeySlim/ultimate-ca-manager/wiki
- **Discussions:** https://github.com/NeySlim/ultimate-ca-manager/discussions

---

**Previous:** [v1.8.3-beta](Release-Notes-v1.8.3-beta)  
**Next:** v1.9.0 (TBD)
