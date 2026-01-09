# Ultimate CA Manager v1.7.5 Release Notes

**Release Date:** 2026-01-08  
**Type:** Maintenance & Dependency Update

---

## 🎯 Overview

This release focuses on dependency updates, bug fixes, and improvements to the HTTPS certificate management interface.

---

## ✨ What's New

### **Dependency Updates (Python 3.13 Compatible)**
All Python dependencies have been updated to their latest stable versions:

- **Flask**: 3.0.0 → 3.1.2
- **cryptography**: 41.0.7 → 46.0.3 (critical security updates)
- **pyOpenSSL**: 23.3.0 → 25.3.0
- **Flask-CORS**: 4.0.0 → 6.0.2
- **Flask-JWT-Extended**: 4.5.3 → 4.7.1
- **Flask-Limiter**: 3.5.0 → 4.1.1
- **Flask-Migrate**: 4.0.5 → 4.1.0
- **webauthn**: 2.2.0 → 2.7.0 (FIDO2 improvements)
- **requests**: 2.31.0 → 2.32.5
- **python-dotenv**: 1.0.0 → 1.2.1
- **bcrypt**: 4.1.1 → 5.0.0
- **gunicorn**: 21.2.0 → 23.0.0
- **pytest**: 7.4.3 → 9.0.2
- **black**: 23.11.0 → 25.12.0
- **flake8**: 6.1.0 → 7.3.0

**New Dependencies:**
- **email-validator**: 2.3.0 (added for improved email validation)
- **cbor2**: 5.8.0 (explicit dependency for WebAuthn)

---

## 🐛 Bug Fixes

### **HTTPS Certificate Management**
- ✅ Fixed certificate source selector not maintaining state after applying managed certificate
- ✅ Added visual badge showing certificate source (Managed/Imported/Auto-generated)
- ✅ Certificate selector now correctly pre-selects currently active managed certificate
- ✅ Added success notification when applying managed certificates
- ✅ Fixed radio button state restoration on page reload

### **System Configuration**
- ✅ Certificate source is now properly tracked in database with separate `https_cert_id` config key
- ✅ System Configuration page displays correct certificate source badge

### **Docker**
- ✅ Fixed Dockerfile mkdir command to use bash for brace expansion compatibility

---

## 🔧 Technical Improvements

### **Database Schema**
- New `https_cert_id` system config key for tracking managed certificate ID
- Improved certificate source tracking (`managed`, `auto-generated`, `imported`)

### **API Enhancements**
- `/api/ui/system/https-cert-info` now returns `cert_id` for managed certificates
- Better error handling and logging for certificate operations

### **Frontend Improvements**
- Enhanced certificate selector UX with automatic state restoration
- Clearer visual feedback for certificate source type
- Improved certificate dropdown population timing

---

## 📦 Installation & Upgrade

### **Fresh Installation**
```bash
git clone https://github.com/NeySlim/ultimate-ca-manager.git
cd ultimate-ca-manager
./scripts/setup.sh
```

### **Upgrade from Previous Version**
```bash
cd /path/to/ucm-src
git pull origin main
source venv/bin/activate
pip install --upgrade -r backend/requirements.txt
sudo systemctl restart ucm
```

### **Docker**
```bash
docker pull neyslim/ultimate-ca-manager:1.7.5
docker pull neyslim/ultimate-ca-manager:latest
```

---

## ⚠️ Breaking Changes

**None** - This release is fully backward compatible.

---

## 🔐 Security Notes

- **cryptography 46.0.3** includes important security fixes
- **pyOpenSSL 25.3.0** resolves multiple CVEs
- All dependencies audited for known vulnerabilities

---

## 📊 Testing

All features have been tested on:
- ✅ Python 3.13.5
- ✅ Debian 12 (Bookworm)
- ✅ Docker environment
- ✅ WebAuthn/FIDO2 authentication
- ✅ Certificate management operations
- ✅ HTTPS certificate selection and application

---

## 🙏 Contributors

- **NeySlim** - Lead Developer

---

## 📝 Full Changelog

```
b9fc7bb fix: Use bash for brace expansion in Dockerfile mkdir command
d71e880 fix: Certificate source selector now correctly shows managed certificate state
a175cd0 debug: Add console logging to certificate selector
072d112 fix: Use separate https_cert_id config key for managed certificate tracking
d723f07 fix: Restore certificate source radio selection based on SystemConfig state
4f7e299 feat: Track HTTPS certificate source (managed/imported/auto-generated) and display badge
fd25d8d fix: Add success notification when applying managed certificate to HTTPS
1a9d3f5 chore: Update dependencies to latest versions (Python 3.13 compatible)
```

---

## 🔗 Links

- **GitHub Repository:** https://github.com/NeySlim/ultimate-ca-manager
- **Documentation:** https://github.com/NeySlim/ultimate-ca-manager/wiki
- **Issues:** https://github.com/NeySlim/ultimate-ca-manager/issues
- **Docker Hub:** https://hub.docker.com/r/neyslim/ultimate-ca-manager

---

**Thank you for using Ultimate CA Manager!** 🎉
