# Changelog

All notable changes to Ultimate CA Manager will be documented in this file.

## [1.6.0] - 2026-01-05

### Added
- Custom styled scrollbars for all themes (light and dark variants)
- Modal body scroll lock when modals are open
- CRL information page with public and integrated versions
- Global modal utilities (modal-utils.js)
- HTMX trigger support for opening modals from sidebar

### Changed
- **BREAKING**: Complete removal of Tailwind CSS
- Migrated all components to custom CSS with CSS variables
- Improved theme consistency across all pages
- Updated all 8 templates to use theme variables
- Enhanced modal z-index (1000) to appear above sidebar (999)

### Fixed
- Modal positioning issues (no longer appearing under sidebar)
- JavaScript variable conflicts (pkcs12ExportId, pkcs12ExportType, pkcs12Params)
- Sidebar modal triggers not working with HTMX
- Theme flash on page load
- Scrollbar visibility when no modal is open
- IconSystem and SessionManager redeclaration errors

### Technical Changes
- Replaced ~827 Tailwind classes with CSS variables
- Added HX-Trigger-After-Swap for modal opening
- Implemented openModal/closeModal helpers
- Scrollbar theming for 8 themes (Sentinel, Amber, Blossom, Nebula - light & dark)

## [1.5.0] - 2026-01-04

### Added
- CRL Phase 1 & 2 implementation
- OCSP responder
- SCEP server

### Changed
- Improved CA management
- Enhanced certificate workflow

## [1.0.0] - 2025-12-15

### Added
- Initial release
- CA creation and management
- Certificate issuance
- Web-based interface
- Basic CRL support
