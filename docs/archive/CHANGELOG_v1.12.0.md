# Changelog - UCM v1.12.0

**Release Date:** TBD  
**Previous Version:** 1.11.0  
**Breaking Changes:** None  
**Status:** 🚧 IN DEVELOPMENT

**Summary:** This release focuses on advanced certificate management features including templates, S/MIME support, smart card (PIV/CAC) certificates, and bulk operations. UI improvements include submenu toggles and comprehensive icon system with complementary colors.

---

## 🚧 Work In Progress

### Certificate Templates (COMPLETE) ✅

**Database Model:** `CertificateTemplate`
- Template configuration (name, type, description)
- Key configuration (RSA-2048/4096, EC-P256/P384)
- DN template with variable substitution `{username}`, `{email}`, `{hostname}`
- Extensions template (key usage, extended key usage, SAN types)
- System vs custom templates (system templates can't be deleted)
- Audit trail (created_by, updated_by, timestamps)

**6 System Templates Pre-configured:**
1. **Web Server (TLS/SSL)** - serverAuth, TLS web server certificates
2. **Email Certificate (S/MIME)** - emailProtection, S/MIME signing/encryption
3. **VPN Server** - serverAuth, IPsec/SSL VPN servers
4. **VPN Client** - clientAuth, IPsec/SSL VPN clients
5. **Code Signing** - codeSigning, software signing certificates
6. **Client Authentication** - clientAuth, mutual TLS authentication

**Service Layer:** `template_service.py` (379 lines)
- `get_all_templates()` - List all templates
- `get_template(id)` - Get single template
- `create_template()` - Create custom template
- `update_template()` - Modify custom template
- `delete_template()` - Delete custom template (not system)
- `render_template()` - Apply template with variable substitution
- Template validation and DN/extension parsing

**REST API:** `/api/v1/templates` (154 lines)
- `GET /api/v1/templates` - List all templates
- `POST /api/v1/templates` - Create custom template
- `GET /api/v1/templates/<id>` - Get template details
- `PUT /api/v1/templates/<id>` - Update custom template (admin only)
- `DELETE /api/v1/templates/<id>` - Delete custom template (admin only)
- `POST /api/v1/templates/<id>/render` - Render template with variables

**Frontend UI:** `/config/templates` (13KB HTMX page)
- Template list with system/custom badges
- Template details modal
- Create/edit custom template form
- Variable substitution preview
- Delete confirmation (custom templates only)
- HTMX-powered, zero fetch() calls

**Seed Script:** `seed_templates.py`
- Populates 6 system templates on first run
- Idempotent (safe to run multiple times)
- DN and extension templates for each type

---

### Settings → Users Tab (COMPLETE) ✅

**Change Password Modal:**
- Real-time password strength meter (4 bars: weak/medium/strong)
- Requirements checklist (8+ chars, upper, lower, number, special)
- Password match confirmation indicator
- Toast notification on success
- Auto-close after submission

**Change Role Modal:**
- 3 roles with descriptions (Viewer, Operator, Administrator)
- Visual feedback on selection with color coding
- Table auto-refresh after role change (`hx-trigger="refreshUsers"`)
- Toast notification on success
- Auto-close after submission

**Bug Fixes:**
- Fixed `window.window.openModal()` typo → `window.openModal()`
- Fixed HTMX form swap destroying modal content (added `hx-swap="none"`)
- Fixed missing password validation in settings.html
- Fixed table auto-refresh with `hx-trigger="revealed, refreshUsers from:body"`

**Architecture:**
- 100% HTMX (zero fetch() calls)
- Global `window.openModal/closeModal` functions
- Modals in settings.html (single source of truth)
- `hx-swap="none"` prevents form content destruction

---

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

---

### S/MIME Certificate Support (COMPLETE) ✅

**Phase 1: Certificate Templates Integration**
- Backend: `template_id` parameter in `CertificateService.create_certificate()`
- Template defaults automatically applied (key_type, validity_days, digest_algorithm)
- Database: `certificates.template_id` stores audit trail
- API: POST `/api/v1/certificates` accepts `template_id` in request

**Phase 2: UI Template Integration**
- Create Certificate Modal: Template dropdown selector (`/api/ui/templates/options`)
- Auto-fill form fields from selected template
- `applyCertTemplate(templateId)` JavaScript function
- Template type mapping: email → client_cert, web_server → server_cert, etc.
- Globalized modal functions: `window.openCreateCertModal`, `window.closeCertModal`

**Phase 3: Email Validation**
- Frontend: RFC 5322 email regex validation in SAN email field
- Real-time validation on input/blur with visual feedback (green/red borders)
- Display count of valid/invalid emails with error list
- Backend: `CertificateService.validate_email()` prevents invalid emails
- Raises `ValueError` before certificate creation if invalid emails detected

**Phase 4: PKCS#12 Export Wizard**
- Enhanced password modal with 4-bar strength meter (Weak/Fair/Good/Strong)
- Password match confirmation indicator
- Password strength calculation: length (8+, 12+), upper+lower, numbers, special chars
- Color-coded strength bars: danger → warning → warning → success
- S/MIME installation quick reference (Outlook, Thunderbird, Apple Mail)
- Link to full documentation page

**Phase 5: S/MIME Documentation**
- New route: GET `/docs/smime-installation` (@login_required)
- Comprehensive installation guide (900px centered layout)
- Sections:
  - What is S/MIME? (signing, encryption, integrity)
  - Microsoft Outlook (Windows/Mac) step-by-step
  - Mozilla Thunderbird installation guide
  - Apple Mail (macOS/iOS) instructions
  - Troubleshooting common issues
  - Best practices (backup, passwords, expiration)
- Accessible from PKCS#12 modal via "📖 View detailed installation guide →" link
- Uses UCM design system (cards, icon system, color variables)

**Email Certificate Template (Pre-configured):**
- Key Usage: digitalSignature, keyEncipherment, dataEncipherment
- Extended Key Usage: emailProtection
- RSA-2048 default (upgradable to 4096)
- 365-day validity
- SHA-256 digest
- Subject DN template: CN={email}, emailAddress={email}, OU=Users, O={organization}
- SAN: email:{email} (RFC 822)

**Files Modified:**
- `/backend/services/cert_service.py` - Template integration + email validation
- `/backend/api/cert.py` - Added template_id to API docstring
- `/backend/api/ui_routes.py` - Template extraction, docs route
- `/frontend/templates/certs/list.html` - Template selector, email validation
- `/frontend/templates/base.html` - Enhanced PKCS#12 modal
- `/frontend/templates/docs/smime-installation.html` - **NEW** documentation page
- `/frontend/static/js/ucm-global.js` - Globalized modal functions

---

## 🎯 Planned Features

---

### 2. Smart Card Support (PIV/CAC) ⭐ Priority 2
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

### 3. Bulk Operations ⭐ Priority 1
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

### Database Schema

**New Table: `certificate_templates`** ✅ IMPLEMENTED
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

**Certificate Model Update:** ✅ IMPLEMENTED
- Added: `template_id` (nullable FK to certificate_templates)

---

## 📦 Commits (dev/v2.0.0)

### 2026-01-18 - Settings Users Tab & Modal Fixes (2 commits)

1. **fix(settings): Complete Settings→Users modal functionality** (a4199fd)
   - Fixed `window.window.openModal()` typo → `window.openModal()`
   - Fixed HTMX form swap destroying modal content (added `hx-swap="none"`)
   - Added password validation with real-time strength meter (4 bars)
   - Added password requirements checklist and match confirmation
   - Fixed table auto-refresh with `hx-trigger="revealed, refreshUsers from:body"`
   - Toast notifications on success, both modals work infinitely
   - 100% HTMX architecture (zero fetch() calls)
   - Files: 13 modified, +1614/-380 lines

2. **fix(settings): Remove duplicate route definitions causing 404s** (ea0762b)
   - Removed duplicate `/api/ui/settings/*` route definitions
   - Fixed settings endpoints returning 404

---

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
- ✅ Settings → Users tab (password/role modals)

**Phase 1: Certificate Templates** ✅ COMPLETE
- ✅ Database model (`CertificateTemplate`)
- ✅ Service layer (`template_service.py`)
- ✅ API endpoints (`/api/v1/templates/*`)
- ✅ UI page (`/config/templates`)
- ✅ 6 system templates seeded

**Phase 2: S/MIME Support** ⏳ Next
- [ ] Enhanced email validation
- [ ] P12/PFX export improvements
- [ ] Client installation guides

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
