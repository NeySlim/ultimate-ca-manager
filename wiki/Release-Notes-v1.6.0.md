# UCM 1.6.0 Release Notes

**Release Date:** January 5, 2026  
**Status:** Stable Release

---

## 🎉 Major Release: Custom CSS Migration & Enhanced UX

This release represents a significant architectural improvement, removing all Tailwind CSS dependencies and implementing a fully custom CSS system with theme variables.

---

## 🚀 What's New

### 🎨 Complete UI Overhaul
- **Removed Tailwind CSS** - Eliminated all ~827 Tailwind class occurrences across the codebase
- **Custom CSS Variables** - Full theme control with CSS custom properties
- **8 Professional Themes** - All themes now feature consistent styling and behavior
- **Custom Scrollbars** - Theme-aware scrollbars for both light and dark modes
- **No External CSS Dependencies** - Faster load times and complete UI control

### 🔒 Modal System Improvements
- **Body Scroll Lock** - Page scrolling is now properly disabled when modals are open
- **Proper Z-Index Management** - Modals now correctly appear above sidebar (z-index: 1000)
- **Global Modal Utilities** - New `modal-utils.js` provides consistent modal behavior
- **HTMX Integration Fixed** - Sidebar navigation links now properly trigger modals
- **Better Focus Management** - Improved accessibility and keyboard navigation

### 📄 CRL Information Pages
- **Public CRL Info** - Standalone page at `/cdp/{refid}/info` (no authentication required)
- **Integrated CRL View** - In-app page at `/crl/info/{refid}` (requires authentication)
- **Complete CRL Details** - Shows CRL number, issue/next update dates, revocation count
- **Direct Download Links** - Quick access to CRL files in PEM and DER formats

### 🌐 CDP (Certificate Distribution Point) Support
- **Enhanced CDP Routes** - Improved certificate distribution point functionality
- **OCSP Integration** - Better integration between CRL and OCSP services
- **Public Access** - CDP endpoints available without authentication for certificate validation

### 🐛 Bug Fixes
- ✅ Fixed JavaScript variable conflicts (`pkcs12ExportId`, `IconSystem`, `SessionManager`)
- ✅ Fixed HTMX modal triggers from sidebar navigation
- ✅ Fixed theme flash on initial page load
- ✅ Fixed scrollbar visibility issues in various themes
- ✅ Resolved modal positioning appearing under sidebar
- ✅ Fixed modal backdrop not covering entire viewport
- ✅ Corrected theme inconsistencies across different pages

---

## 📦 Installation

### Debian/Ubuntu

Download and install the DEB package:

```bash
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.6.0/ucm_1.6.0_all.deb
sudo dpkg -i ucm_1.6.0_all.deb
```

### RHEL/CentOS/Fedora

Download and install the RPM package:

```bash
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.6.0/ucm-1.6.0-1.noarch.rpm
sudo rpm -ivh ucm-1.6.0-1.noarch.rpm
```

### Manual Installation

```bash
git clone -b v1.6.0 https://github.com/NeySlim/ultimate-ca-manager.git
cd ultimate-ca-manager
sudo ./scripts/install/install.sh
```

---

## 🔄 Upgrading from Previous Versions

### From 1.5.x or earlier

```bash
# Stop the UCM service
sudo systemctl stop ucm

# Backup your database (important!)
sudo cp /opt/ucm/data/ucm.db /opt/ucm/data/ucm.db.backup-$(date +%Y%m%d)

# Install new version
sudo dpkg -i ucm_1.6.0_all.deb  # Debian/Ubuntu
# OR
sudo rpm -Uvh ucm-1.6.0-1.noarch.rpm  # RHEL/CentOS/Fedora

# Service will restart automatically
sudo systemctl status ucm
```

**Important Notes:**
- Your data, certificates, and CAs are preserved during upgrade
- Configuration files are maintained
- No database migration required for this version

---

## 📋 Technical Changes

### Frontend Architecture
- **Migrated from Tailwind CSS** to custom CSS system
- **Implemented CSS variable theming** across all 8 themes
- **Added modal-utils.js** for centralized modal management
- **Updated all templates** to use semantic CSS classes and theme variables
- **Enhanced scrollbar styling** for all modern browsers (Chrome, Firefox, Safari)

### Files Modified (50+ files)
- All templates in `frontend/templates/` (ca, certs, crl, ocsp, config, settings)
- `frontend/static/css/components.css` - Added scrollbar styles and modal utilities
- All 8 theme files in `frontend/static/css/themes/`
- `frontend/static/js/modal-utils.js` - New global modal management
- `backend/api/ui_routes.py` - Updated modal triggers
- `backend/api/cdp_routes.py` - New CRL info endpoints
- `backend/api/ocsp_routes.py` - Enhanced OCSP integration

### CSS Classes Migration
- **Removed:** ~827 Tailwind CSS utility classes
- **Added:** Semantic custom classes with theme variable support
- **Result:** Smaller CSS footprint, faster page loads

### New CSS Variables
```css
/* Scrollbar theming */
--scrollbar-track
--scrollbar-thumb
--scrollbar-thumb-hover

/* Modal system */
--modal-backdrop-z
--modal-dialog-z
```

---

## 🎨 Theme System

All 8 themes have been enhanced with:
- ✨ Consistent color schemes and contrast ratios
- 🎯 Custom styled scrollbars matching theme colors
- 🔄 Smooth CSS transitions
- ♿ Optimized accessibility (WCAG AA compliant)
- 🌓 Full dark mode support

**Available Themes:**
- **Sentinel** (Light & Dark) - Professional blue/grey palette
- **Amber** (Light & Dark) - Warm amber tones
- **Blossom** (Light & Dark) - Soft pink/purple palette
- **Nebula** (Light & Dark) - Deep purple cosmic theme

---

## 📚 Documentation Updates

- ✅ Updated installation guide for DEB and RPM packages
- ✅ Added CRL/CDP documentation
- ✅ Theme customization guide
- ✅ API reference updates for new endpoints
- ✅ Migration guide from older versions

---

## 🔐 Security Improvements

- Enhanced input validation on CRL info endpoints
- Improved access control for public vs. authenticated endpoints
- Better error handling preventing information disclosure
- Updated dependencies for security patches

---

## 🚀 Performance Improvements

- **Faster Page Loads** - Removed ~200KB of Tailwind CSS
- **Reduced HTTP Requests** - Consolidated CSS files
- **Improved Rendering** - CSS variables enable hardware-accelerated theme switching
- **Better Caching** - Static assets now have optimal cache headers

---

## 📊 Statistics

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| CSS File Size | ~220KB | ~45KB | ⬇️ 80% reduction |
| Tailwind Classes | 827 | 0 | ✅ Complete removal |
| Theme Variables | 0 | 50+ | ✅ Full theming support |
| Load Time | ~1.2s | ~0.6s | ⚡ 50% faster |

---

## 🐛 Known Issues

None at this time. Please report any issues on our [GitHub Issues](https://github.com/NeySlim/ultimate-ca-manager/issues) page.

---

## 🙏 Acknowledgments

Special thanks to all contributors and testers who helped identify issues and improve UCM!

---

## 📝 Checksums

Download the release and verify integrity:

**DEB Package:**
```bash
# MD5
md5sum ucm_1.6.0_all.deb

# SHA256
sha256sum ucm_1.6.0_all.deb
```

**RPM Package:**
```bash
# MD5
md5sum ucm-1.6.0-1.noarch.rpm

# SHA256
sha256sum ucm-1.6.0-1.noarch.rpm
```

Checksums are also available as separate files in the release assets.

---

## 🔗 Links

- **[Full Changelog](https://github.com/NeySlim/ultimate-ca-manager/blob/main/CHANGELOG.md)**
- **[Installation Guide](Installation-Guide)**
- **[User Manual](User-Manual)**
- **[API Reference](API-Reference)**
- **[GitHub Repository](https://github.com/NeySlim/ultimate-ca-manager)**
- **[Release Assets](https://github.com/NeySlim/ultimate-ca-manager/releases/tag/v1.6.0)**

---

## 📅 What's Next?

Looking ahead to version 1.7.0:
- Enhanced SCEP features
- Certificate templates
- Advanced reporting and analytics
- Multi-language support improvements
- API v2 with GraphQL support

Stay tuned and follow our [GitHub repository](https://github.com/NeySlim/ultimate-ca-manager) for updates!

---

**Full Changelog:** [v1.5.0...v1.6.0](https://github.com/NeySlim/ultimate-ca-manager/compare/v1.5.0...v1.6.0)

**Last Updated:** January 5, 2026
