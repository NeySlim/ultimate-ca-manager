# Changelog - UCM v1.12.0

**Release Date:** TBD  
**Previous Version:** 1.11.0  
**Breaking Changes:** None  
**Status:** 🚧 IN DEVELOPMENT

**Summary:** This release focuses on advanced certificate management features including templates, S/MIME support, smart card (PIV/CAC) certificates, and bulk operations. UI improvements include submenu toggles and comprehensive icon system with complementary colors.

---

## 🚧 Work In Progress

### UI & Icon System Improvements (COMPLETE) ✅

**Submenu Toggle Buttons**
- Collapsible submenus for CA, Certificates, SCEP
- Chevron indicators (down = expanded, right = collapsed)
- State persists in localStorage per submenu
- Visible even in collapsed sidebar mode (10px icons)
- Smooth transitions and animations

**Icon System Finalization (v6.2)**
- **50/74 icons (68%)** now have complementary colors
- Complementary color pairs:
  - Blue themes → Blue ↔ Orange
  - Orange themes → Orange ↔ Blue
  - Purple themes → Purple ↔ Yellow/Green
- **35 icons updated** with complement gradients:
  - System: database, server, shield-check, save, clock, eye
  - Actions: edit, copy, clipboard, lock, user-check, user-plus
  - Feedback: check-circle, info-circle, exclamation-circle, alert-triangle
  - Navigation: external-link, link, logout, inbox
  - Content: book-open, envelope, globe, file-text
  - Special: chart-bar, plug, eye-slash, ban, list-check, ocsp, crown, award
- Fixed ACME icon cutoff (corrected viewBox bounds)
- Eliminated all remnants of old icon system
- Higher stroke width on complement paths (2.0-2.5px) for better visibility

**Sidebar Improvements**
- My Account section pushed to bottom of sidebar
- Better visual separation between system nav and user account
- Uses flexbox with `margin-top: auto` for bottom alignment
- Works with both expanded and collapsed states

**Settings Page Icons**
- Database Management: icon-database (with complement)
- mTLS Authentication: icon-shield-check (with complement)
- HTTPS Certificate: shield → lock (more semantic)

---

## 🎯 Planned Features

### 1. Certificate Templates ⭐ Priority 1
**Status:** Not started  
**Estimated:** 12-15 hours

Pre-configured certificate profiles for common use cases:
- Web Server (TLS/SSL)
- Email (S/MIME)
- VPN Client/Server
- Code Signing
- Client Authentication

**Features:**
- Database model: `CertificateTemplate`
- CRUD API endpoints
- Template selector in cert creation
- Pre-filled DN fields and extensions
- Custom user-defined templates
- Template export/import (JSON)

---

### 2. S/MIME Certificate Generation ⭐ Priority 1
**Status:** Not started  
**Estimated:** 8-10 hours

Full support for email encryption/signing certificates:
- Extended Key Usage: emailProtection
- Key Usage: digitalSignature, keyEncipherment, dataEncipherment
- RFC 822 email addresses in SAN (mandatory)
- PKCS#12 export with password protection
- Compatible with Outlook, Thunderbird, Apple Mail
- Email address validation
- Installation guides for popular clients

---

### 3. Smart Card Support (PIV/CAC) ⭐ Priority 2
**Status:** Not started  
**Estimated:** 15-20 hours

PIV-compliant certificates (NIST SP 800-73-4):
- 4 PIV slots: Authentication (9A), Digital Signature (9C), Key Management (9D), Card Auth (9E)
- PIV certificate extensions (FASC-N, Card UUID, PIV Interim)
- Certificate Policy OID: 2.16.840.1.101.3.2.1.3.7
- CHUID support
- Compatible with YubiKey, Gemalto, etc.
- Smart card setup middleware instructions

---

### 4. Bulk Operations ⭐ Priority 1
**Status:** Not started  
**Estimated:** 12-15 hours

Manage multiple certificates simultaneously:
- **Bulk Revocation** - Single reason code, CRL update, notifications
- **Bulk Export** - ZIP archive, multiple formats (PEM/DER/P12)
- **Bulk Renewal** - Keep DN/extensions, new serial numbers
- **Bulk Delete** - Remove expired certs with safety checks

**UI Components:**
- Multi-select checkboxes in certificate list
- Bulk action toolbar (appears on selection)
- Progress indicators for long operations
- Results summary modal

---

## 🔧 Technical Changes

### Database Schema (Planned)

**New Table: `certificate_templates`**
```sql
CREATE TABLE certificate_templates (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    template_type VARCHAR(50),
    key_type VARCHAR(20) DEFAULT 'RSA-2048',
    validity_days INTEGER DEFAULT 397,
    digest VARCHAR(20) DEFAULT 'sha256',
    dn_template TEXT,
    extensions_template TEXT,
    is_system BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME,
    created_by VARCHAR(80)
);
```

**Certificate Model Update:**
- Add: `template_id` (nullable FK to certificate_templates)

---

## 📦 Commits (dev/v1.12.0)

### 2026-01-17 - UI Improvements (6 commits)

1. **feat(sidebar): Add submenu toggle buttons with chevrons**
   - Chevron toggle for CA, Certificates, SCEP submenus
   - localStorage persistence per submenu
   - Smooth collapse/expand animations

2. **fix(sidebar): Keep submenu chevrons visible when collapsed + fix ACME icon cutoff**
   - Chevrons stay visible (10px, opacity 0.3) in collapsed mode
   - ACME icon: fixed viewBox overflow (2.5,6 instead of 2,7)

3. **feat(icons): Add complementary colors to 35 more icons (v6.2)**
   - 50/74 icons now with complement gradient (68% coverage)
   - Blue↔Orange, Purple↔Yellow complementary color system
   - Higher stroke width on complement paths for visibility

4. **fix(settings): Replace old icon system with UCM SVG icons**
   - Database Management & mTLS icons migrated
   - Eliminated `<i data-ucm-icon>` remnants

5. **fix(settings): Replace HTTPS Certificate icon shield → lock**
   - More semantic lock icon with complement colors
   - Removed hardcoded color styles

6. **feat(sidebar): Push My Account section to bottom of sidebar**
   - Flexbox layout with `margin-top: auto`
   - Better UX separation between system nav and user account

---

## 📊 Development Progress

**Phase 0: UI Polish** ✅ COMPLETE
- ✅ Submenu toggles
- ✅ Icon system finalization (68% with complement colors)
- ✅ Sidebar UX improvements
- ✅ Settings page icons

**Phase 1: Certificate Templates** 🔄 Ready to start
- [ ] Database model
- [ ] Service layer
- [ ] API endpoints
- [ ] UI pages
- [ ] Tests

**Phase 2: S/MIME Support** ⏳ Planned
**Phase 3: PIV/CAC Support** ⏳ Planned
**Phase 4: Bulk Operations** ⏳ Planned
**Phase 5: Integration & Testing** ⏳ Planned

---

## 🚀 Installation

**From Source:**
```bash
git clone https://github.com/NeySlim/ultimate-ca-manager.git
cd ultimate-ca-manager
git checkout dev/v1.12.0
pip install -r requirements.txt
python app.py
```

**Testing (when ready):**
```bash
pytest tests/
```

---

## 📝 Notes

This version is currently in active development. Features are being implemented incrementally and may not be stable until official release.

**Documentation:**
- Development plan: `/root/ucm-context/PLAN_V1.12.0_CERT_FEATURES.md`
- Session notes: `/root/ucm-context/SESSION_2026-01-17_UI_IMPROVEMENTS.md`
- Icon system: `/root/ucm-context/docs/UCM_ICON_SYSTEM_RULES.md`

**Testing:**
- UI improvements tested manually
- Awaiting feature implementation for automated tests

---

**See Also:**
- [v1.11.0 Changelog](CHANGELOG_v1.11.0.md)
- [Main Changelog](CHANGELOG.md)
