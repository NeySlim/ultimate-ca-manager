# Release v1.8.1 - Nginx Optional Fix

**Release Date:** January 10, 2026  
**Tag:** v1.8.1  
**Commit:** 3ab944a  
**Status:** ✅ STABLE - Production ready

---

## 🐛 Bug Fix

### Nginx Dependency Made Truly Optional
**Problem:** v1.8.0 Debian package had nginx in `Recommends:`, causing it to be installed by default even though UCM can run standalone.

**Solution:** Moved nginx to `Suggests:` only - now completely optional!

```bash
# v1.8.0 behavior
apt install ucm  # ← Would install nginx

# v1.8.1 behavior  
apt install ucm  # ← Does NOT install nginx ✅
apt install ucm nginx  # ← Install with nginx if you want it
```

---

## 📦 Deployment Options

UCM is **flexible** - choose what works for you:

### 1. Standalone (No Reverse Proxy) ✅
```bash
apt install ucm
# UCM runs on its own built-in HTTPS server (port 8443)
# Perfect for: Testing, small deployments, homelab
```

### 2. With Reverse Proxy (Recommended for Production) 🚀
```bash
apt install ucm nginx
# Configure nginx as reverse proxy
# Perfect for: Production, multiple services, load balancing
```

### 3. Docker 🐳
```bash
docker pull ghcr.io/neyslim/ultimate-ca-manager:1.8.1
# No nginx needed - use docker networking
# Perfect for: Containers, orchestration, microservices
```

---

## 📝 Package Description Updates

Both Debian and RPM packages now include complete feature lists:
- ✅ ACME protocol (Let's Encrypt compatible)
- ✅ SCEP enrollment (device automation)
- ✅ WebAuthn/FIDO2 passwordless login
- ✅ mTLS client authentication
- ✅ CRL distribution
- ✅ Email notifications
- ✅ JWT-authenticated REST API
- ✅ 8 beautiful themes

---

## 🔄 Upgrade from v1.8.0

### Debian/Ubuntu
```bash
# Remove v1.8.0
apt remove ucm

# Install v1.8.1 (no nginx!)
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.8.1/ucm_1.8.1_all.deb
sudo dpkg -i ucm_1.8.1_all.deb
```

### Docker
```bash
docker pull ghcr.io/neyslim/ultimate-ca-manager:1.8.1
docker pull ghcr.io/neyslim/ultimate-ca-manager:latest
```

**No data migration needed** - Just swap the package!

---

## 📊 Changes from v1.8.0

- **Debian control:** nginx moved from `Recommends:` to `Suggests:`
- **RPM spec:** Enhanced description with all features
- **Documentation:** Clarified deployment options

**All v1.8.0 features remain unchanged** - This is purely a packaging fix.

---

## 📦 Available Packages

- ✅ **Debian** (.deb) - nginx is optional
- ✅ **Docker** (multi-arch) - amd64 + arm64
- ⚠️ **RPM** (.rpm) - UNTESTED, use at own risk

---

**Previous Release:** [v1.8.0](https://github.com/NeySlim/ultimate-ca-manager/releases/tag/v1.8.0)  
**Next Release:** v1.9.0 - TBD

**Status:** ✅ STABLE - Nginx dependency fix applied
