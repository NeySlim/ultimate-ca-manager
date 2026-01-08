# 🎉 Ultimate CA Manager v1.7.0 - Major Feature Release

**Release Date:** January 8, 2026  
**Git Tag:** v1.7.0  

---

## 📦 Overview

Ultimate CA Manager v1.7.0 is a **major feature release** introducing three powerful authentication methods, comprehensive email notification system, enhanced UI navigation, and significant user experience improvements.

This release transforms UCM into a complete enterprise-grade PKI management platform with modern authentication options and proactive certificate monitoring.

---

## ✨ What's New in v1.7.0

### 🔐 **1. WebAuthn/FIDO2 Passwordless Authentication**

Modern passwordless authentication using security keys and biometrics.

**Features:**
- **Passwordless Login**: Authenticate with YubiKey, Windows Hello, Touch ID, Face ID
- **Multi-Credential Support**: Register and manage multiple security keys per user
- **Credential Management UI** (`/config/webauthn`):
  - View all registered keys with metadata
  - Registration date, last used, sign counter
  - Enable/disable individual credentials
  - Delete unused credentials
- **Login Integration**: "Sign in with Security Key" button on login page
- **Security Features**:
  - Challenge-response protocol (no credential storage in browser)
  - Replay protection via sign counter
  - Domain-scoped credentials (RP ID)
  - User verification support (PIN/biometrics)

**Supported Hardware:**
- YubiKey (all FIDO2 models)
- Google Titan Key
- Nitrokey FIDO2
- SoloKeys
- All FIDO2-compliant tokens

**Platform Biometrics:**
- Windows Hello (fingerprint/face/PIN)
- macOS Touch ID
- iOS Face ID / Touch ID
- Android biometric unlock

**New Components:**
- Backend: `backend/api/webauthn_api.py` (9.2KB, 7 endpoints)
- Frontend: `frontend/templates/config/webauthn.html` (28.7KB)
- Model: `backend/models/webauthn.py` with `webauthn_credentials` table
- Service: `backend/services/webauthn_service.py`
- Migration: `backend/migrate_webauthn.py`

---

### 🛡️ **2. mTLS Client Certificate Authentication**

Enterprise-grade certificate-based authentication with auto-login support.

**Features:**
- **Certificate-Based Login**: Authenticate using X.509 client certificates
- **Auto-Login**: Automatic authentication when valid certificate detected
- **Hybrid Mode**: Simultaneous support for mTLS + password authentication
- **Certificate Management UI** (`/config/mtls`):
  - Associate certificates with user accounts
  - Auto-detect current client certificate
  - View certificate details (issuer, subject, serial, expiration)
  - Enable/disable individual certificates
  - Delete certificates
- **Reverse Proxy Integration**:
  - Nginx configuration generator with copy-to-clipboard
  - Apache configuration generator with copy-to-clipboard
  - Automatic header parsing (`X-SSL-Client-*`)
- **Security Features**:
  - Certificate chain validation
  - CRL/OCSP revocation checking
  - Subject DN validation
  - Serial number tracking

**Use Cases:**
- Hardware security keys with PIV slots (YubiKey PIV)
- Corporate PKI integration
- Zero-trust network architecture
- API authentication

**New Components:**
- Backend: `backend/api/mtls_api.py` (10.8KB, 5 endpoints)
- Frontend: `frontend/templates/config/mtls.html` (26.2KB)
- Model: `backend/models/auth_certificate.py` with `auth_certificates` table
- Service: `backend/services/mtls_auth_service.py`
- Middleware: `backend/middleware/mtls_middleware.py`
- Migration: `backend/migrate_mtls.py`

---

### 📧 **3. Email Notification System**

Proactive monitoring with automated alerts for certificate and CRL expiration.

**Features:**
- **SMTP Configuration** (`/config/notifications`):
  - Full SMTP server setup (host, port, credentials)
  - TLS/SSL security options
  - Enable/disable toggle
  - Test email function
- **Alert Rules**:
  - Certificate expiration notifications (customizable threshold)
  - CRL expiration notifications (customizable threshold)
  - Per-rule recipient email lists
  - Enable/disable individual rules
- **Notification History**:
  - Complete log of sent notifications
  - Success/failure tracking
  - Error messages for failed deliveries
- **Statistics Dashboard**:
  - Sent/failed counts (last 30 days)
  - Breakdown by notification type
- **Manual Triggers**: Run immediate expiration checks on-demand

**Supported SMTP Providers:**
- Gmail (with app password)
- Office 365 / Outlook
- SendGrid
- Mailgun
- Amazon SES
- Local mail servers

**New Components:**
- Backend: `backend/api/notification_api.py` (11.3KB, 7 endpoints)
- Frontend: `frontend/templates/config/notifications.html` (22.5KB)
- Models: `backend/models/email_notification.py`
  - `smtp_config` table
  - `notification_config` table
  - `notification_log` table
- Services:
  - `backend/services/email_service.py` - SMTP sending
  - `backend/services/notification_service.py` - Alert logic

**Automation:**
Schedule notifications with cron:
```bash
# Daily at 8 AM
0 8 * * * cd /opt/ucm && source venv/bin/activate && python -c 'from services.notification_service import NotificationService; NotificationService.run_notification_check()'
```

---

### 🎨 **4. Enhanced UI Navigation**

Complete sidebar navigation redesign with better organization and user experience.

**Features:**

#### Collapsible Sidebar Submenus
- **Certificate Authorities**, **Certificates**, **SCEP** sections with expand/collapse
- Smooth chevron rotation animations (0° → 180°)
- State persisted in localStorage
- Auto-expand when child page is active
- HTMX-aware (reinitialize after content swaps)

#### Submenu Icons
- 14×14px SVG icons for all submenu items
- Hover effects (opacity 0.7 → 1.0)
- Visual hierarchy (smaller than main menu 20×20px icons)

#### My Account Section
User-specific settings grouped at bottom of sidebar:
- 📧 Email Notifications
- 🛡️ mTLS Authentication
- 🔑 Security Keys (WebAuthn/FIDO2)
- Visual separator with border-top

#### Optimized Sidebar Width
- **Before**: 240-260px (varied by theme)
- **After**: 220px (uniform)
- **Benefit**: 20-40px more space for main content

**New Components:**
- JavaScript: `frontend/static/js/sidebar-toggle.js` (165 lines)
- CSS: ~650 lines added to `frontend/static/css/components.css`
- Theme updates: All 8 themes (Sentinel, Amber, Blossom, Nebula)

---

### 🎭 **5. Themed Modal System**

Custom modal dialogs that integrate seamlessly with UCM's theme system.

**Features:**
- **Replace Native Dialogs**: Modern alternatives to `alert()`, `confirm()`, `prompt()`
- **Theme Integration**: Automatic adaptation to all 8 UCM themes
- **Promise-Based API**: Modern async/await support
- **Customizable Options**:
  - Custom button text and colors
  - Danger mode for destructive actions
  - Icons for visual context
  - Multi-step confirmations
- **UX Enhancements**:
  - Smooth fade-in/slide-in animations
  - Keyboard support (Escape to close, Enter to confirm)
  - Click outside to close
  - Focus management

**New Component:**
- `frontend/static/js/modal-system.js`

---

### 🎯 **6. UI/UX Improvements**

#### Button System Fixes
Fixed 33 buttons across 5 pages with missing base `btn` class:
- Corrected colors (was pink/salmon, now theme colors)
- Added missing padding and borders
- Fixed invisible icons
- Unified button styling across all themes

#### Icon System Standardization
Complete migration to native UCM SVG icons:
- Replaced FontAwesome classes with `<use href="#icon-name"/>`
- Better performance (no JavaScript replacement)
- Theme-aware gradient support
- New icon classes: `.btn-icon`, `.btn-icon-primary/danger/success/warning`

#### Form Style Unification
Standardized form inputs across all pages:
- Consistent padding, spacing, borders, backgrounds
- Theme-aware hover and focus states
- Unified label positioning and typography

#### Certificate Display Improvements
- Better certificate selection highlighting
- Improved visual hierarchy in lists
- Enhanced metadata display
- Icon filtering for operations

---

## 📊 Technical Details

### Database Schema Changes

**New Tables:**
```sql
-- WebAuthn credentials
webauthn_credentials (id, user_id, credential_id, public_key, sign_count, name, ...)

-- mTLS certificates
auth_certificates (id, user_id, certificate_pem, subject_dn, serial, fingerprint, ...)

-- Email notifications
smtp_config (id, smtp_host, smtp_port, smtp_user, smtp_password, enabled, ...)
notification_config (id, type, enabled, days_before, recipients, ...)
notification_log (id, type, recipient, subject, status, sent_at, ...)
```

### API Endpoints Added

**WebAuthn (7 endpoints):**
- `POST /api/v1/webauthn/register/options`
- `POST /api/v1/webauthn/register/verify`
- `POST /api/v1/webauthn/authenticate/options`
- `POST /api/v1/webauthn/authenticate/verify`
- `GET /api/v1/webauthn/credentials`
- `POST /api/v1/webauthn/credentials/<id>/toggle`
- `DELETE /api/v1/webauthn/credentials/<id>`

**mTLS (5 endpoints):**
- `GET /api/v1/mtls/certificates`
- `POST /api/v1/mtls/certificates`
- `DELETE /api/v1/mtls/certificates/<id>`
- `POST /api/v1/mtls/certificates/<id>/toggle`
- `GET /api/v1/mtls/current-certificate`

**Email Notifications (7 endpoints):**
- `GET /api/v1/notifications/smtp/config`
- `POST /api/v1/notifications/smtp/config`
- `POST /api/v1/notifications/smtp/test`
- `GET /api/v1/notifications/config`
- `POST /api/v1/notifications/config/<type>`
- `GET /api/v1/notifications/history`
- `GET /api/v1/notifications/stats`
- `POST /api/v1/notifications/check`

### Files Modified/Created

**Created (31 files):**
- 3 API blueprints (notification, webauthn, mtls)
- 3 UI templates (notifications.html, webauthn.html, mtls.html)
- 3 database models (email_notification, webauthn, auth_certificate)
- 5 services (email, notification, webauthn, mtls_auth, certificate_parser)
- 2 middleware (mtls_middleware)
- 3 migration scripts
- 1 JavaScript module (sidebar-toggle.js)
- Documentation files

**Modified (20+ files):**
- `backend/app.py` - Register new blueprints
- `backend/api/ui_routes.py` - Add new UI routes
- `backend/api/auth.py` - Integrate mTLS/WebAuthn auth
- `frontend/templates/base.html` - Sidebar redesign
- `frontend/templates/auth/login.html` - Add WebAuthn login
- `frontend/static/css/components.css` - Submenu styles
- All 8 theme CSS files - Width optimization
- Icon system files

**Total Changes:**
- +7,000 lines of code
- +150KB total size increase
- 3 new database tables
- 19 new API endpoints
- 3 new UI pages

---

## 🚀 Installation & Upgrade

### From v1.6.2 to v1.7.0

#### 1. Backup Database
```bash
sudo systemctl stop ucm
sudo cp /opt/ucm/backend/data/ucm.db /opt/ucm/backend/data/ucm.db.backup-1.6.2
```

#### 2. Update Code
```bash
cd /opt/ucm
sudo git fetch origin
sudo git checkout v1.7.0
```

#### 3. Run Migrations
```bash
cd /opt/ucm/backend
source /opt/ucm/venv/bin/activate
python migrate_webauthn.py
python migrate_mtls.py
python migrate_email_notifications.py
```

#### 4. Restart Service
```bash
sudo systemctl restart ucm
sudo systemctl status ucm
```

#### 5. Verify Installation
Visit: `https://your-server:8443`
- Check version in footer (should show "v1.7.0")
- Navigate to new pages: Notifications, mTLS Auth, WebAuthn

---

### Fresh Installation

#### Debian/Ubuntu (.deb)
```bash
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.7.0/ucm_1.7.0_all.deb
sudo dpkg -i ucm_1.7.0_all.deb
sudo systemctl start ucm
sudo systemctl enable ucm
```

#### RHEL/CentOS/Fedora (.rpm)
```bash
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.7.0/ucm-1.7.0-1.noarch.rpm
sudo rpm -ivh ucm-1.7.0-1.noarch.rpm
sudo systemctl start ucm
sudo systemctl enable ucm
```

#### Docker
```bash
docker pull neyslim/ultimate-ca-manager:1.7.0
docker run -d -p 8443:8443 \
  -v ucm-data:/app/data \
  --name ucm \
  neyslim/ultimate-ca-manager:1.7.0
```

#### From Source
```bash
git clone https://github.com/NeySlim/ultimate-ca-manager.git
cd ultimate-ca-manager
git checkout v1.7.0
# Follow installation instructions in README.md
```

---

## 📚 Configuration Guides

### Setup Email Notifications

1. Navigate to **Config** → **Notifications**
2. **SMTP Configuration**:
   - Host: `smtp.gmail.com`
   - Port: `587`
   - Username: `your-email@gmail.com`
   - Password: Your app password
   - Enable TLS: ✓
   - Click "Save SMTP Configuration"
3. **Test SMTP**: Click "Send Test Email"
4. **Configure Rules**:
   - Certificate Expiring: Enable, set threshold (e.g., 30 days)
   - Add recipient emails (comma-separated)
   - Click "Save Rule"
5. **Test Manually**: Click "Run Manual Check"

### Setup WebAuthn/FIDO2

1. Navigate to **My Account** → **Security Keys**
2. Click "Register New Key"
3. Enter a descriptive name (e.g., "YubiKey 5 NFC")
4. Follow browser prompt to touch security key
5. Verify credential appears in list
6. **Test Login**:
   - Logout
   - Click "Sign in with Security Key"
   - Touch your security key

### Setup mTLS Authentication

1. **Generate Client Certificate** (using UCM):
   - Navigate to **Certificates** → **Create Certificate**
   - Certificate Type: Client Certificate
   - Common Name: Your username
   - Subject Alternative Names: email:you@domain.com
   - Click "Create"
   - Download certificate (.p12)

2. **Install in Browser**:
   - Import .p12 into browser certificate store
   - Chrome/Edge: Settings → Privacy → Manage certificates
   - Firefox: Settings → Privacy → Certificates → View Certificates

3. **Configure Reverse Proxy**:
   - Navigate to **My Account** → **mTLS Authentication**
   - Copy Nginx or Apache configuration
   - Apply to your reverse proxy
   - Restart proxy

4. **Associate Certificate**:
   - Navigate to **My Account** → **mTLS Authentication**
   - Click "Add Certificate"
   - Current certificate should auto-populate
   - Click "Save"

5. **Test Auto-Login**:
   - Logout
   - Browser should prompt for certificate
   - Select your certificate
   - Should auto-login

---

## 🔐 Security Considerations

### WebAuthn
- ⚠️ **HTTPS Required**: WebAuthn only works over HTTPS
- 🔒 Private keys never leave the authenticator
- 🛡️ Replay protection via sign counter
- 🌐 Credentials scoped to domain (RP ID)

### mTLS
- ⚠️ **Reverse Proxy Required**: Nginx/Apache must verify certificates
- 🔒 Certificate chain validation essential
- 🛡️ Use CRL/OCSP for revocation checking
- 🔐 Protect private keys with encryption

### Email Notifications
- ⚠️ **Secure SMTP Credentials**: Use app passwords, not main passwords
- 🔒 SMTP password encrypted in database
- 🛡️ TLS/SSL strongly recommended
- 📧 Test with non-critical recipients first

---

## 🎨 Theme Compatibility

All v1.7.0 features fully compatible with UCM's 8 themes:

- ✅ **Sentinel** (Light/Dark)
- ✅ **Amber** (Light/Dark)
- ✅ **Blossom** (Light/Dark)
- ✅ **Nebula** (Light/Dark)

Theme-aware components:
- Modals
- Forms
- Buttons
- Icons with gradients
- Sidebar submenus

---

## 🧪 Testing Performed

### Functional Testing
- ✅ WebAuthn registration with YubiKey 5 NFC
- ✅ WebAuthn login with platform authenticator (Windows Hello)
- ✅ mTLS auto-login with client certificate
- ✅ Email notifications with Gmail SMTP
- ✅ Sidebar collapse/expand persistence
- ✅ All 8 themes tested
- ✅ HTMX navigation across all new pages

### Browser Compatibility
- ✅ Chrome 131+
- ✅ Firefox 133+
- ✅ Edge 131+
- ✅ Safari 18+ (macOS)

### Platform Testing
- ✅ Windows 11 (Windows Hello)
- ✅ macOS (Touch ID)
- ✅ Linux (YubiKey)

---

## 📝 Known Issues & Limitations

### WebAuthn
1. **HTTPS Requirement**: Localhost works, but production requires valid SSL
2. **Browser Support**: IE 11 and older browsers not supported
3. **Sign Counter**: Some software authenticators don't increment (handled gracefully)

### mTLS
1. **Reverse Proxy Required**: Cannot use standalone Flask server
2. **Certificate Import**: Browser certificate import varies by platform
3. **Auto-Detection**: Requires proper proxy header configuration

### Email Notifications
1. **Gmail App Passwords**: Gmail requires app-specific passwords (not main password)
2. **Rate Limiting**: Some SMTP providers have sending limits
3. **Manual Scheduling**: Cron job required for automated checks

### UI Navigation
1. **Mobile Responsiveness**: Sidebar not yet optimized for mobile devices
2. **Tooltip System**: Tooltip attributes added but not yet functional

---

## 🚀 Future Enhancements

Potential improvements for v1.8.0:
- [ ] Mobile-responsive sidebar with hamburger menu
- [ ] Active tooltip system for collapsed sidebar
- [ ] TOTP/OTP 2FA support
- [ ] SSO integration (SAML, OAuth)
- [ ] Advanced notification templates
- [ ] Webhook notifications
- [ ] Slack/Teams integration

---

## 📖 Documentation Links

- **GitHub Repository**: https://github.com/NeySlim/ultimate-ca-manager
- **Wiki**: https://github.com/NeySlim/ultimate-ca-manager/wiki
- **Release Notes**: https://github.com/NeySlim/ultimate-ca-manager/wiki/Release-Notes-v1.7.0
- **Changelog**: https://github.com/NeySlim/ultimate-ca-manager/blob/main/CHANGELOG.md
- **User Manual**: https://github.com/NeySlim/ultimate-ca-manager/wiki/User-Manual

---

## 🙏 Acknowledgments

This release represents a significant milestone in UCM's evolution. Special thanks to:
- The WebAuthn community for FIDO2 standards
- Users who requested mTLS and notification features
- Beta testers who provided valuable feedback

---

## 📞 Support

- **Issues**: https://github.com/NeySlim/ultimate-ca-manager/issues
- **Discussions**: https://github.com/NeySlim/ultimate-ca-manager/discussions
- **Security**: Report vulnerabilities via GitHub Security Advisories

---

## 📊 Release Statistics

- **Development Time**: 3 weeks
- **Commits**: 45+ commits
- **Lines of Code**: +7,000 lines
- **New Features**: 5 major features
- **Bug Fixes**: 15+ bug fixes
- **Files Changed**: 50+ files
- **Contributors**: 1 (NeySlim)

---

## 🎯 Upgrade Recommendation

**Recommended for:**
- ✅ All production users (major features + stability improvements)
- ✅ Users needing multi-factor authentication
- ✅ Organizations with PKI compliance requirements
- ✅ Teams wanting proactive certificate monitoring

**Migration Effort:**
- **Low**: Simple database migration scripts provided
- **Downtime**: < 5 minutes for migration
- **Rollback**: Full database backup recommended

---

**Previous Release:** [v1.6.2](https://github.com/NeySlim/ultimate-ca-manager/releases/tag/v1.6.2) - Bugfix Release (January 7, 2026)  
**Next Release:** v1.8.0 (TBD)

---

**Release Prepared By:** UCM Development Team  
**Release Date:** January 8, 2026  
**Status:** ✅ Production Ready

**Full Changelog**: https://github.com/NeySlim/ultimate-ca-manager/compare/v1.6.2...v1.7.0
