# Release Notes - v1.7.0

**Release Date:** January 8, 2026  
**Release Type:** Feature Release  
**Previous Version:** v1.6.2

---

## 🎯 Overview

Version 1.7.0 enhances the user interface with collapsible sidebar submenus, optimized navigation, and improved organization of user account settings. This release focuses on improving the user experience with smoother navigation and better space utilization.

---

## ✨ What's New

### Collapsible Sidebar Submenus

The sidebar navigation now features expandable/collapsible submenus for better organization:

- **Certificate Authorities Section**
  - List CAs
  - Create CA
  - Import CA

- **Certificates Section**
  - List Certificates
  - Create Certificate
  - Import Certificate

- **SCEP Section**
  - SCEP Configuration

**Features:**
- 🔽 Smooth chevron rotation animations
- 💾 State persisted in browser localStorage
- 🎯 Auto-expand when navigating to child pages
- ⚡ HTMX-aware: works seamlessly with dynamic content loading

### Submenu Icons

All submenu items now have dedicated icons for better visual hierarchy:

- **Icon Size:** 14×14px (smaller than main menu 20×20px)
- **Hover Effect:** Opacity transitions from 0.7 to 1.0
- **Theme Integration:** Works across all 8 color schemes

### My Account Section at Bottom

User-specific settings are now grouped together at the bottom of the sidebar:

- 📧 **Email Notifications** - Configure email alerts
- 🛡️ **mTLS Authentication** - Manage client certificates
- 🔑 **Security Keys** - WebAuthn/FIDO2 configuration

**Benefits:**
- Visual separation with border-top separator
- Always accessible regardless of scroll position
- Clear distinction between system and user settings

### Optimized Sidebar Width

**Before:** 240-260px (varied by theme)  
**After:** 220px (uniform across all themes)

**Benefits:**
- 20-40px more space for main content
- Consistent layout across all themes
- Better space utilization on smaller screens

---

## 🔧 Technical Improvements

### JavaScript Architecture

- **New Module:** `sidebar-toggle.js` (165 lines)
  - Submenu state management
  - localStorage persistence
  - HTMX integration
  - Auto-expand logic

### CSS Enhancements

- **~150 lines** added to `components.css`
- Smooth transition animations (0.3s ease)
- Flexbox-based sidebar layout
- Theme-aware submenu styling

### State Management

```javascript
// localStorage keys for submenu persistence
'sidebar-ca-expanded'           // Certificate Authorities
'sidebar-certificates-expanded' // Certificates
'sidebar-scep-expanded'        // SCEP
```

---

## 🎨 Theme Compatibility

All changes fully compatible with UCM's 8 themes:

- ✅ Sentinel Light/Dark
- ✅ Amber Light/Dark
- ✅ Blossom Light/Dark
- ✅ Nebula Light/Dark

---

## 📊 Performance Impact

- **Bundle Size:** +6.5KB (sidebar-toggle.js)
- **CSS Size:** +150 lines in components.css
- **Performance:** No noticeable impact, animations remain smooth
- **Compatibility:** All modern browsers supported

---

## 🚫 Known Limitations

### Sidebar Collapse Feature (Disabled)

During development, we explored a full sidebar collapse feature (icon-only mode with flyout menus). However, this was disabled in the final release due to:

- Layout stability issues
- Complexity in maintaining responsive behavior
- Tooltip positioning challenges

**Status:** Code preserved in comments for potential future implementation

---

## 📝 Migration Notes

### For Existing Users

No action required. The update is seamless:

1. Submenus will be collapsed by default on first load
2. User preferences auto-saved as you navigate
3. All existing functionality preserved

### For Developers

If you've customized the sidebar:

1. Review changes in `frontend/templates/base.html`
2. Check CSS in `frontend/static/css/components.css`
3. Test submenu behavior with your customizations

---

## 🐛 Bug Fixes

- Fixed submenu icon opacity transitions
- Improved sidebar flexbox layout
- Corrected theme-specific width inconsistencies

---

## 📖 Documentation Updates

- Updated README.md to v1.7.0
- Added comprehensive CHANGELOG entry
- Created this release notes page

---

## 🔮 Future Considerations

### Potential Future Features

1. **Sidebar Collapse** - Revisit with improved architecture
2. **Mobile Responsive Sidebar** - Hamburger menu for mobile devices
3. **Keyboard Navigation** - Arrow key support for submenus
4. **Accessibility** - Enhanced ARIA attributes
5. **Active Tooltips** - Utilize existing data-tooltip attributes

---

## 🙏 Acknowledgments

This release represents continuous improvement in user experience design. Special thanks to all users who provided feedback on navigation and layout.

---

## 📦 Download

- **GitHub Release:** [v1.7.0](https://github.com/NeySlim/ultimate-ca-manager/releases/tag/v1.7.0)
- **Docker Image:** `docker pull neyslim/ultimate-ca-manager:1.7.0`
- **Source Code:** Available on [GitHub](https://github.com/NeySlim/ultimate-ca-manager)

---

## 📞 Support

- **GitHub Issues:** [Report bugs or request features](https://github.com/NeySlim/ultimate-ca-manager/issues)
- **Wiki:** [Comprehensive documentation](https://github.com/NeySlim/ultimate-ca-manager/wiki)
- **Discussions:** [Community support](https://github.com/NeySlim/ultimate-ca-manager/discussions)

---

**Previous Release:** [v1.6.2 Release Notes](Release-Notes-v1.6.2)
