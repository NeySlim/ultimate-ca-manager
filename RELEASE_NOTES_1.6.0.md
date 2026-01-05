# UCM 1.6.0 Release Notes

## 🎉 Major Release: Custom CSS Migration & Enhanced UX

This release represents a significant architectural improvement, removing all Tailwind CSS dependencies and implementing a fully custom CSS system with theme variables.

---

## 🚀 What's New

### 🎨 Complete UI Overhaul
- **Removed Tailwind CSS** - Eliminated all ~827 Tailwind class occurrences
- **Custom CSS Variables** - Full theme control with CSS custom properties
- **8 Professional Themes** - All themes now feature consistent styling
- **Custom Scrollbars** - Theme-aware scrollbars for light and dark modes

### 🔒 Modal Improvements
- **Body Scroll Lock** - Page scrolling disabled when modal is open
- **Proper Z-Index** - Modals now appear above sidebar (z-index: 1000)
- **Global Modal Utils** - New `modal-utils.js` for consistent behavior
- **HTMX Integration** - Sidebar links properly trigger modals

### 📄 CRL Information Pages
- **Public CRL Info** - Standalone page at `/cdp/{refid}/info` (no auth required)
- **Integrated View** - In-app page at `/crl/info/{refid}` (authenticated)
- **Complete Details** - CRL number, dates, revocation count, download links

### 🐛 Bug Fixes
- Fixed JavaScript variable conflicts (pkcs12ExportId, IconSystem, SessionManager)
- Fixed HTMX modal triggers from sidebar navigation
- Fixed theme flash on page load
- Fixed scrollbar visibility issues
- Resolved modal positioning under sidebar

---

## 📦 Installation

### Debian/Ubuntu (Recommended)

```bash
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.6.0/ucm_1.6.0_all.deb
sudo dpkg -i ucm_1.6.0_all.deb
```

### Manual Installation

```bash
git clone -b v1.6.0 https://github.com/NeySlim/ultimate-ca-manager.git
cd ultimate-ca-manager
sudo ./install.sh
```

---

## 🔄 Upgrading from 1.5.x

```bash
# Stop service
sudo systemctl stop ucm

# Backup database
sudo cp /opt/ucm/data/ucm.db /opt/ucm/data/ucm.db.backup

# Install new version
sudo dpkg -i ucm_1.6.0_all.deb

# Service will restart automatically
```

**Note:** Your data, certificates, and CAs are preserved during upgrade.

---

## 📋 Technical Changes

### Frontend
- Migrated from Tailwind CSS to custom CSS system
- Implemented CSS variable theming across 8 themes
- Added `modal-utils.js` for global modal management
- Updated all templates to use theme variables
- Enhanced scrollbar styling for all browsers

### Files Changed (50+)
- All templates in `frontend/templates/` (ca, certs, crl, ocsp, config)
- `frontend/static/css/components.css` (scrollbar styles, modal lock)
- All 8 theme files in `frontend/static/css/themes/`
- `frontend/static/js/modal-utils.js` (new)
- `backend/api/ui_routes.py` (modal triggers)
- `backend/api/cdp_routes.py` (CRL info endpoint)

### Classes Removed
- ~827 Tailwind CSS classes across 8 template files
- Replaced with CSS variables and custom classes

### New CSS Variables
```css
--scrollbar-track
--scrollbar-thumb
--scrollbar-thumb-hover
```

---

## 🎨 Theme Examples

All themes now feature:
- Consistent color schemes
- Custom styled scrollbars
- Smooth transitions
- Optimized contrast ratios
- Full dark mode support

**Available Themes:**
- Sentinel (Light & Dark)
- Amber (Light & Dark)
- Blossom (Light & Dark)
- Nebula (Light & Dark)

---

## 📚 Documentation

- [Full Changelog](CHANGELOG.md)
- [Installation Guide](INSTALLATION.md)
- [API Documentation](docs/API.md)
- [Theme Guide](docs/THEMES.md) *(new)*

---

## 🙏 Acknowledgments

Special thanks to all contributors and testers who helped identify issues and improve UCM!

---

## 📝 Checksums

**MD5:**
```
[will be generated during build]
```

**SHA256:**
```
[will be generated during build]
```

---

**Full Changelog:** https://github.com/NeySlim/ultimate-ca-manager/compare/v1.5.0...v1.6.0
