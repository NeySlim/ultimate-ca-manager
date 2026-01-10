# Release Notes - v1.6.2

**Release Date:** January 7, 2026  
**Release Type:** Bugfix Release  
**Previous Version:** v1.6.0

---

## 🎯 Overview

Version 1.6.2 is a critical bugfix release addressing JavaScript errors in the OPNsense import functionality and improving the import statistics display.

---

## 🐛 Critical Bugfixes

### Fixed

#### OPNsense Import Page
Fixed critical JavaScript errors preventing configuration imports:

- **Added global `showToast()` function** to base template for reliable toast notifications
- **Fixed "showToast is not defined" error** in HTMX-loaded content
- **Removed authentication method toggle**, now uses API Key only (simplified UX)
- **Improved error handling** and user feedback during import process

#### Import Statistics Display
Fixed toast message showing "0 CA 0 Cert" after successful import:

- **Corrected response data parsing** in import completion handler
- **Enhanced import result feedback** with proper counts

---

## 🔧 Changed

- Simplified OPNsense import authentication to API Key only (removed username/password option)
- Improved toast notification system with consistent styling across all themes

---

## 📦 Download

- **GitHub Release:** [v1.6.2](https://github.com/NeySlim/ultimate-ca-manager/releases/tag/v1.6.2)
- **Docker Image:** `docker pull neyslim/ultimate-ca-manager:1.6.2`

---

**Next Release:** [v1.7.0 Release Notes](Release-Notes-v1.7.0)  
**Previous Release:** [v1.6.0 Release Notes](Release-Notes-v1.6.0)
