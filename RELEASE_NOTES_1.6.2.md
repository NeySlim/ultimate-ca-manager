# Ultimate CA Manager v1.6.2 - Critical Import Bugfixes

**Release Date:** January 7, 2026

## 🐛 Critical Bugfixes

This hotfix release addresses critical issues with the OPNsense configuration import functionality that prevented users from importing certificates and CAs.

### Fixed Issues

#### OPNsense Import Page Errors
- **Fixed critical JavaScript error**: Resolved "showToast is not defined" error that completely blocked import functionality
- **Enhanced notification system**: Added global `showToast()` function to base template ensuring reliable toast notifications across all pages
- **Improved HTMX compatibility**: Fixed toast function availability in dynamically loaded content
- **Better error handling**: Enhanced user feedback during import operations with proper error messages

#### Import Statistics Display
- **Fixed misleading success messages**: Corrected toast displaying "0 CA 0 Cert" after successful imports
- **Accurate result reporting**: Import completion now shows correct counts of imported CAs and certificates
- **Response data parsing**: Fixed data extraction from import API responses

### Changed

#### UI/UX Improvements
- **Simplified authentication**: Removed username/password authentication method from OPNsense import
- **API Key only**: Streamlined import process to use API Key authentication exclusively
- **Cleaner interface**: Removed unnecessary authentication method toggle for better user experience
- **Consistent styling**: Toast notifications now maintain theme consistency across all 8 color schemes

### Technical Details

**Files Modified:**
- `frontend/templates/base.html` - Added global toast notification system
- `backend/api/ui_routes.py` - Simplified import form, improved response handling
- Enhanced error propagation for better debugging

**Compatibility:**
- ✅ All 8 themes supported
- ✅ HTMX dynamic content loading
- ✅ Session-based authentication maintained
- ✅ Backward compatible with existing configurations

## Upgrade Instructions

### For Existing Installations

**Debian/Ubuntu:**
```bash
wget https://github.com/fabriziosalmi/ultimate-ca-manager/releases/download/v1.6.2/ultimate-ca-manager_1.6.2_amd64.deb
sudo dpkg -i ultimate-ca-manager_1.6.2_amd64.deb
sudo systemctl restart ucm
```

**RHEL/CentOS/Fedora:**
```bash
wget https://github.com/fabriziosalmi/ultimate-ca-manager/releases/download/v1.6.2/ultimate-ca-manager-1.6.2-1.x86_64.rpm
sudo rpm -Uvh ultimate-ca-manager-1.6.2-1.x86_64.rpm
sudo systemctl restart ucm
```

**Docker:**
```bash
docker pull fabriziosalmi/ultimate-ca-manager:1.6.2
docker pull fabriziosalmi/ultimate-ca-manager:latest
```

### For New Installations

See [INSTALLATION.md](INSTALLATION.md) for complete installation instructions.

## Important Notes

- **No database migration required** - This is a pure bugfix release
- **No configuration changes needed** - Existing settings are preserved
- **Import functionality fully restored** - OPNsense imports now work reliably
- **No breaking changes** - All existing features continue to work

## What's Next?

**v1.7.0** (In Development) - Advanced Authentication
- mTLS certificate-based authentication
- WebAuthn/FIDO2 hardware key support
- Enhanced security features
- PKI database reset functionality

## Support

- **Documentation**: [GitHub Wiki](https://github.com/fabriziosalmi/ultimate-ca-manager/wiki)
- **Issues**: [GitHub Issues](https://github.com/fabriziosalmi/ultimate-ca-manager/issues)
- **Discussions**: [GitHub Discussions](https://github.com/fabriziosalmi/ultimate-ca-manager/discussions)

---

**Full Changelog**: [v1.6.0...v1.6.2](https://github.com/fabriziosalmi/ultimate-ca-manager/compare/v1.6.0...v1.6.2)
