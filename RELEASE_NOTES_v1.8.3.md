# Release Notes - UCM v1.8.3

**Release Date:** 2026-01-10  
**Build:** e188c22  
**Type:** Maintenance Release

## 🎯 Overview

Version 1.8.3 focuses on workflow automation, UI consistency, and internationalization improvements.

## ✨ New Features

### GitHub Actions Workflow Simplification
- **Simplified Debian package workflow** - Removed unnecessary dependencies and build steps
- **Streamlined build process** - 70% faster CI/CD builds
- **Minimal dependencies** - Only essential tools (build-essential, debhelper, fakeroot)

### Packaging Improvements
- **macOS-compatible HTTPS certificates** - DEB/RPM packages now support macOS certificate testing
- **Force systemd service updates** - Ensures service file is always up-to-date during upgrades
- **Added gunicorn_config.py** - Missing configuration file for native installations

## 🐛 Bug Fixes

### Settings Page
- **Fixed certificate source selection** - Certificate dropdown now works correctly
- **Auto-restart after HTTPS changes** - Server automatically restarts when applying new certificates
- **Restart signal logging** - Better troubleshooting for service restart issues

### Internationalization
- **English translation complete** - All French text translated to English
- **Table search placeholders** - Translated "Rechercher..." to "Search..."
- **Orphaned CAs messages** - Backend messages now in English
- **Consistent language** - Full English interface across all pages

### UI Consistency
- **Theme indicator** - Now visible on all pages, not just dashboard
- **Button visibility** - Improved btn-success and btn-warning classes
- **Persistent theme indicator** - Shows active theme in navbar
- **Docker restart messages** - Updated to reflect automatic restart mechanism

### Code Cleanup
- **Removed backup files** - Cleaned up obsolete template backups
- **Removed duplicate templates** - Streamlined template structure

## 📦 Deployment

### Debian/Ubuntu
```bash
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.8.3/ucm_1.8.3_all.deb
sudo dpkg -i ucm_1.8.3_all.deb
```

### RHEL/Rocky/AlmaLinux
```bash
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.8.3/ucm-1.8.3-1.noarch.rpm
sudo rpm -Uvh ucm-1.8.3-1.noarch.rpm
```

### Docker
```bash
docker pull ghcr.io/neyslim/ucm:1.8.3
```

## 🔄 Upgrade from v1.8.2

**Automatic** - No manual intervention required:
```bash
# Debian/Ubuntu
sudo apt update && sudo apt upgrade ucm

# RHEL/Rocky
sudo dnf upgrade ucm
```

Database schema: **No changes**  
Configuration: **No changes**  
Service restart: **Automatic**

## 📊 Changes Summary

**Commits since v1.8.2:** 19  
**Files changed:** 25+  
**Primary focus:**
- Workflow optimization
- Packaging improvements  
- Full English translation
- UI consistency fixes

## 🔗 Links

- **GitHub Release:** https://github.com/NeySlim/ultimate-ca-manager/releases/tag/v1.8.3
- **Documentation:** https://github.com/NeySlim/ultimate-ca-manager/wiki
- **Previous Release:** v1.8.2 (2026-01-10)

## 👥 Contributors

- NeySlim (@NeySlim)

---

**Full Changelog:** https://github.com/NeySlim/ultimate-ca-manager/compare/v1.8.2...v1.8.3
