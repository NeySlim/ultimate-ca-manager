# Release v1.8.2 - Nginx Truly Optional (Fixed!)

**Release Date:** January 10, 2026  
**Tag:** v1.8.2  
**Status:** ✅ STABLE - Production ready, nginx is NOW optional

---

## 🐛 Critical Fix

### Nginx Dependency FINALLY Optional
**Problem:** v1.8.0 and v1.8.1 both had nginx hardcoded in the GitHub Actions workflow, making it a required dependency despite documentation saying otherwise.

**Root Cause:** Workflow file `.github/workflows/build-deb.yml` generated its own `control` file with `nginx` in `Depends:`, overriding the repository's correct `control` file.

**Solution:** Fixed workflow to match repository configuration:
- **Depends:** python3, pip, venv, systemd (essentials only)
- **Recommends:** flask-caching, redis (performance)  
- **Suggests:** nginx, apache2, certbot, gunicorn (optional)

```bash
# NOW THIS WORKS WITHOUT NGINX! ✅
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.8.2/ucm_1.8.2_all.deb
sudo dpkg -i ucm_1.8.2_all.deb
# ✅ No nginx installation!
# ✅ UCM runs standalone on port 8443
```

---

## 🚀 Major Features (Unchanged from v1.8.0)

UCM is a **production-ready Certificate Authority** with:

### **1. ACME Protocol (RFC 8555)** ⭐
- Full Let's Encrypt-compatible ACME v2 server
- HTTP-01 and DNS-01 challenge validation
- Works with certbot, acme.sh, all standard clients
- **Run your own internal Let's Encrypt!**

### **2. WebAuthn/FIDO2 Authentication** 🔐
- Passwordless login with YubiKey, Touch ID, Windows Hello
- Biometric support (fingerprint, face recognition)
- Multi-device credential management

### **3. SCEP Enrollment** 📱
- Device automation for iOS, Android, Windows, macOS
- Auto-approval workflows for MDM
- PKCS#7 encryption/signing

### **4. mTLS Client Authentication** 🔒
- Mutual TLS with client certificates
- Works with Gunicorn native or reverse proxy
- Auto-detection (peercert vs headers)

### **5. Certificate Revocation Lists (CRL)** ⛔
- RFC 5280 compliant CRL generation
- Public CDP endpoints
- Automatic updates on revocation

### **6. Email Notifications** 📧
- Automated expiration alerts
- SMTP with TLS support
- Scheduled checks

### **7. REST API** 🔌
- Complete JWT-authenticated API
- Certificate lifecycle management
- OpenAPI docs (coming soon)

### **8. Modern Web UI** 🎨
- 8 beautiful themes (light/dark)
- HTMX-powered (no page reloads)
- Responsive dashboard

---

## 📦 Deployment Options

### 1. Standalone (No Reverse Proxy) ✅ **RECOMMENDED FOR TESTING**
```bash
apt install ucm_1.8.2_all.deb
# UCM runs on built-in HTTPS server (port 8443)
# Perfect for: Homelab, testing, small deployments
```

### 2. With Reverse Proxy 🚀 **RECOMMENDED FOR PRODUCTION**
```bash
apt install ucm_1.8.2_all.deb nginx
# Configure nginx as reverse proxy
# Perfect for: Production, load balancing, multiple services
```

### 3. Docker 🐳
```bash
docker pull ghcr.io/neyslim/ultimate-ca-manager:1.8.2
docker pull ghcr.io/neyslim/ultimate-ca-manager:latest
```

---

## 🔄 Migration from v1.8.0 / v1.8.1

### Remove old version:
```bash
apt remove ucm
apt autoremove  # Remove nginx if it was auto-installed
```

### Install v1.8.2:
```bash
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.8.2/ucm_1.8.2_all.deb
sudo dpkg -i ucm_1.8.2_all.deb
```

**No data migration needed** - Config and certificates preserved!

---

## 📊 Changes from v1.8.1

### Fixed Files:
- `.github/workflows/build-deb.yml` - Removed nginx from Depends, added proper Recommends/Suggests
- Package description updated with complete feature list

### Features:
- ✅ All v1.8.0 features preserved
- ✅ Nginx now truly optional
- ✅ Deployment flexibility restored

---

## 📦 Available Packages

- ✅ **Debian** (.deb) - nginx optional, TESTED ✅
- ✅ **Docker** (multi-arch) - amd64 + arm64
- ⚠️ **RPM** (.rpm) - UNTESTED, use at own risk

---

## 🧪 Verification

Test that nginx is NOT required:
```bash
# Download package
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.8.2/ucm_1.8.2_all.deb

# Inspect dependencies
dpkg-deb -I ucm_1.8.2_all.deb | grep Depends:
# Should show: python3, pip, venv, systemd (NO nginx!)

# Install without nginx
sudo dpkg -i ucm_1.8.2_all.deb
# ✅ SUCCESS - No nginx dependency error!
```

---

**Previous Release:** [v1.8.0-beta](https://github.com/NeySlim/ultimate-ca-manager/releases/tag/v1.8.0-beta)  
**Next Release:** v1.9.0 - TBD

**Status:** ✅ STABLE - Nginx dependency bug FIXED, ready for production
