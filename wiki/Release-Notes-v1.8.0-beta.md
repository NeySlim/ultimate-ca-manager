# Release Notes - v1.8.3-beta

**Release Date:** January 10, 2026  
**Release Type:** Beta Feature Release  
**Previous Version:** v1.7.0

---

## 🎯 Overview

Version 1.8.3-beta enhances certificate and CA export functionality, improves HTTPS certificate management display, and introduces visual theme preview cards. This beta release focuses on improving security, user experience, and cross-platform compatibility.

---

## ✨ What's New

### Enhanced Certificate & CA Export

**Fixed Authentication Issues:**
- ✅ Certificate exports now properly authenticated with JWT tokens
- ✅ CA exports now include Bearer token in Authorization header
- ✅ Eliminated 401 Unauthorized and 500 Internal Server errors

**Improved Download Experience:**
- 📄 Files now download with **descriptive names** instead of numeric IDs
- 🎯 Filename extracted from `Content-Disposition` header
- 🔄 Download spinner with toast notifications
- ✅ "Preparing download..." → "Download started: filename.pem" flow

**Technical Details:**
- Added JWT bearer token injection to `exportWithToken()` functions
- Created `window.exportWithTokenCert()` for certificate exports
- Implemented filename parsing from response headers
- Fixed HTMX redeclaration errors with proper scope management

### HTTPS Certificate Type Detection

**Accurate Certificate Classification:**
- ✅ Correctly identifies **Self-Signed** certificates (subject == issuer)
- ✅ Distinguishes **CA-Signed (Auto-generated)** certificates
- ✅ Shows **UCM Managed** for user-selected certificates

**Before:** All auto-generated certs showed as "Self-Signed" ❌  
**After:** Proper detection based on issuer comparison ✅

**API Endpoint:** `/api/ui/system/https-cert-info`

### Certificate Source Selection Synchronization

**Fixed Race Condition:**
- Radio button selection now properly syncs with current certificate
- Eliminated unreliable 800ms `setTimeout` approach
- Implemented Promise-based synchronization

**Technical Implementation:**
```javascript
// loadCertificateCandidates() now returns Promise
// loadHTTPSCertInfo() awaits candidates before selecting
await loadCertificateCandidates();
// Then fetch and select current cert
```

### Visual Theme Previews

**Replaced:** Simple theme buttons  
**With:** Interactive preview cards showing actual theme appearance

**Features:**
- 🎨 Miniature UI preview with theme colors
- 🖼️ Shows backgrounds, buttons, cards, and text
- ✨ Hover effects with color-matched borders and shadows
- 📐 2 rows × 4 columns layout (8 themes total)
- 📱 Responsive with 200px minimum width per card

**Grid Layout:**
```css
grid-template-columns: repeat(4, minmax(200px, 1fr));
min-width: 0; /* prevents grid blowout */
```

### Sidebar Improvements

**Renamed:** "Settings" → "System Settings"
- Clearer distinction between system and user settings
- Consistent with sidebar organization from v1.7.0

---

## 🔧 Technical Improvements

### Docker & Native Installation Compatibility

**Dynamic Path Resolution:**
- Replaced hardcoded `/opt/ucm` paths with `current_app.config[]`
- Uses `HTTPS_CERT_PATH`, `HTTPS_KEY_PATH`, `CERT_DIR`, `PRIVATE_DIR`
- Paths dynamically calculated from `BASE_DIR` in `settings.py`

**Result:**
- ✅ Native installation: `/opt/ucm/backend/data/`
- ✅ Docker installation: `/app/backend/data/`
- ✅ No code changes needed between environments

### JavaScript Architecture

**Export Functions:**
- `window.exportWithToken(url)` - CA exports with JWT
- `window.exportWithTokenCert(url)` - Certificate exports with JWT
- Proper scope management to prevent HTMX redeclaration errors

**HTMX Integration:**
```javascript
if (typeof window.exportWithToken === 'undefined') {
    window.exportWithToken = function(url) { ... }
}
```

### CSS Enhancements

**Theme Preview Cards:**
- ~120 lines of inline styles per theme
- Interactive hover transitions (0.2s ease)
- Theme-specific color variables
- Responsive grid layout

---

## 🐛 Bug Fixes

### Certificate Export Issues
- ❌ **Before:** 500 errors due to missing `Certificate` import
- ✅ **After:** Added import in `backend/api/cert.py`

### CA Export Authentication
- ❌ **Before:** 401 Unauthorized errors
- ✅ **After:** JWT token properly injected in requests

### Download Filenames
- ❌ **Before:** Files downloaded as `cert_123.pem`
- ✅ **After:** `Certificate_Name.pem` from Content-Disposition

### HTMX Function Redeclaration
- ❌ **Before:** "Identifier 'exportWithToken' has already been declared"
- ✅ **After:** Proper scope management with `window` and existence checks

### HTTPS Certificate Display
- ❌ **Before:** CA-signed certs showed as "Self-Signed"
- ✅ **After:** Correct type based on subject/issuer comparison

### Theme Preview Layout
- ❌ **Before:** Simple buttons, themes wrapped on small screens
- ✅ **After:** Visual cards with 2×4 grid and 200px minimum width

---

## 📝 Files Modified

### Backend
- `backend/api/cert.py` - Added `Certificate` import
- `backend/api/ui_routes.py` - Enhanced exports, HTTPS detection, dynamic paths
- `backend/config/settings.py` - No changes (already had dynamic paths)

### Frontend
- `frontend/templates/my_account.html` - Visual theme preview cards
- `frontend/templates/settings.html` - Certificate synchronization fixes
- `frontend/templates/base.html` - Sidebar "System Settings" rename

---

## 📊 Git Commits (v1.8.3-beta)

```
77d2f42 - fix: replace hardcoded /opt/ucm paths with dynamic config paths
6688944 - fix: prevent theme preview cards from being crushed on small screens
1835c24 - fix: force theme previews to display in 2 rows of 4
1f62191 - fix: remove duplicate theme preview buttons
93cf047 - feat: compact theme previews and rename sidebar Settings
94dd4ee - feat: add visual theme previews instead of simple buttons
da1dfbf - fix: simplify and globalize export functions
5cf670b - fix: HTTPS certificate display and export improvements
34d4eb2 - fix: certificate/CA export with proper authentication and filenames
```

---

## 🚀 Deployment

### Native Installation (/opt/ucm)
```bash
# Already deployed and tested on netsuit:8443
systemctl restart ucm
```

### Docker Installation
```bash
# Pull latest beta image
docker pull neyslim/ultimate-ca-manager:1.8.3-beta

# Or update from source
cd /path/to/ucm-src
docker build -t neyslim/ultimate-ca-manager:1.8.3-beta .
docker restart ucm
```

### Upgrade Notes
- ✅ No database migrations required
- ✅ No configuration changes needed
- ✅ Backward compatible with existing data
- ✅ Works with all 8 themes

---

## 🎨 Theme Compatibility

All changes fully compatible with UCM's 8 themes:

- ✅ Sentinel Light/Dark
- ✅ Amber Light/Dark
- ✅ Blossom Light/Dark
- ✅ Nebula Light/Dark

Theme preview cards showcase:
- Background colors
- Card backgrounds
- Primary/secondary button styles
- Text colors
- Interactive hover effects

---

## 🔒 Security Improvements

### JWT Authentication
- All export endpoints now properly secured
- Token validation on both certificate and CA exports
- No more unauthenticated download attempts

### Certificate Validation
- Accurate certificate type detection
- Proper subject/issuer comparison
- Clear visibility of certificate sources

---

## 🐛 Known Issues

### Beta Limitations
- Theme preview cards require minimum 800px viewport width
- Mobile responsive design for previews not optimized yet
- Some theme hover effects may vary slightly by browser

### Future Improvements
- Mobile-optimized theme selector
- Keyboard navigation for theme selection
- Accessibility improvements (ARIA labels)

---

## 🔮 Planned for v1.8.3 Stable

- [ ] Mobile theme selector optimization
- [ ] Additional export format options (DER, PKCS12)
- [ ] Bulk certificate export
- [ ] Enhanced certificate search/filtering
- [ ] Accessibility audit and improvements

---

## 📖 Documentation Updates

- Created Release-Notes-v1.8.3-beta.md
- Updated README.md version references
- Added deployment notes
- Documented dynamic path architecture

---

## 🙏 Acknowledgments

This release addresses real-world deployment challenges with Docker compatibility and improves the overall user experience with better visual feedback and accurate certificate information.

---

## 📦 Download

- **GitHub Tag:** [v1.8.3-beta](https://github.com/NeySlim/ultimate-ca-manager/releases/tag/v1.8.3-beta)
- **Docker Image:** `docker pull neyslim/ultimate-ca-manager:1.8.3-beta`
- **Source Code:** [GitHub Repository](https://github.com/NeySlim/ultimate-ca-manager)

---

## 📞 Support

- **GitHub Issues:** [Report bugs or request features](https://github.com/NeySlim/ultimate-ca-manager/issues)
- **Wiki:** [Comprehensive documentation](https://github.com/NeySlim/ultimate-ca-manager/wiki)
- **Discussions:** [Community support](https://github.com/NeySlim/ultimate-ca-manager/discussions)

---

**Previous Release:** [v1.7.0 Release Notes](Release-Notes-v1.7.0)
