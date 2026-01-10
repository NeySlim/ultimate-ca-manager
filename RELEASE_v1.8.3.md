# Release v1.8.3 - UI Improvements

**Date:** 2026-01-10  
**Tag:** v1.8.3  
**Type:** Enhancement Release

## 🎨 UI Improvements

### Button Visibility Fixes
- ✅ Fixed `btn-success` buttons invisible on light themes (Sentinel Light, Amber Light)
- ✅ Added missing `btn-warning` button class
- ✅ Added `--status-success`, `--status-warning`, `--status-danger`, `--status-info` CSS variables to all themes
- ✅ Buttons now properly colored across all 8 themes:
  - **btn-success**: Green (#10b981) - visible on all themes
  - **btn-warning**: Orange (#f59e0b) - visible on all themes
  - **btn-primary**: Blue (unchanged)
  - **btn-danger**: Red (unchanged)
  - **btn-secondary**: Gray (unchanged)

### Theme Selector Enhancement
- ✅ Added visual checkmark (✓) indicator for currently active theme
- ✅ Indicator persists across theme changes
- ✅ Works with HTMX SPA navigation (appears on all pages)
- ✅ Uses CSS classes instead of inline styles for better performance

### Docker Messages
- ✅ Updated restart messages to reflect automatic restart mechanism
- ✅ Removed outdated "manual restart required" messages for Docker users
- ✅ Consistent messaging across Docker and native installations

### Translation to English
- ✅ Translated all French UI text to English
- ✅ CA table headers (Émetteur→Issuer, Nom→Name, etc.)
- ✅ Certificate table headers
- ✅ Orphaned CAs section
- ✅ Pagination controls (Affichage→Showing, par page→per page)
- ✅ Search field placeholders (Recherche→Search)

## 📦 Installation

### Upgrade from v1.8.2

**Native Installation:**
```bash
# Download v1.8.3 package
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.8.3/ucm_1.8.3_all.deb

# Install (automatic upgrade)
sudo dpkg -i ucm_1.8.3_all.deb
```

**Docker:**
```bash
# Pull new image
docker pull ghcr.io/neyslim/ultimate-ca-manager:1.8.3

# Restart container
docker-compose down && docker-compose up -d
```

## 🔄 Migration Notes

This is a **UI-only update** with no database or configuration changes.

- No database migration needed
- No configuration changes required
- No breaking changes
- Data and settings preserved

## 📋 Changes from v1.8.2

**Files Modified:**
- `frontend/static/css/components.css` - Added btn-success, btn-warning, active-theme classes
- `frontend/static/css/themes/sentinel-light.css` - Added status-* variables
- `frontend/static/css/themes/amber-light.css` - Added status-* variables  
- `frontend/static/js/theme-switcher.js` - Theme indicator logic
- `frontend/templates/base.html` - Cache busting for JS
- `backend/config/settings.py` - Updated Docker restart messages
- `frontend/templates/config/system.html` - Updated restart confirmation messages

**Commits:**
- d9476cb - Docker restart message updates
- 01749a7 - Button classes and theme indicator (initial)
- 1b0d00e - Theme variables for light themes
- 4b641eb - HTMX navigation support
- 684b06e - Final clean implementation (v1.8.3)

## 🧪 Testing

**Test Cases:**
1. ✅ Button visibility on all 8 themes (light and dark variants)
2. ✅ Theme indicator persistence across page navigation
3. ✅ Theme indicator updates when changing themes
4. ✅ HTTPS certificate buttons visible and functional
5. ✅ Docker auto-restart messages accurate

**Tested Themes:**
- Sentinel Light / Dark
- Amber Light / Dark
- Blossom Light / Dark
- Nebula Light / Dark

## 🐛 Known Issues

None reported.

## 📖 Documentation

All documentation updated to reflect v1.8.3:
- README.md
- UPGRADE.md
- Wiki pages
- Docker Compose files

## 🙏 Credits

Thanks to users who reported button visibility issues during testing.

---

**Previous Release:** [v1.8.2](RELEASE_v1.8.2.md) - Nginx Truly Optional  
**Next Release:** TBD
