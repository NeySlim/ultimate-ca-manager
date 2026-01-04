# Screenshot Guide for UCM Documentation

This guide lists all the screenshots needed for comprehensive UCM documentation.

## 📸 Screenshot Requirements

### General Guidelines

- **Resolution**: 1920x1080 or higher
- **Format**: PNG (for clarity)
- **Browser**: Chrome/Firefox (latest)
- **Zoom**: 100% (no zoom)
- **Theme**: Light theme (better for documentation)
- **Language**: English
- **Data**: Use sample/demo data (no production data)

### Capture Method

**Option 1 - Browser DevTools:**
1. Press F12 to open DevTools
2. Press Ctrl+Shift+P (Cmd+Shift+P on Mac)
3. Type "screenshot"
4. Select "Capture full size screenshot" or "Capture node screenshot"

**Option 2 - Browser Extension:**
- Use "Awesome Screenshot" or "Nimbus Screenshot"
- Capture full page or visible area

---

## 📋 Screenshots to Capture

### 1. Login & Dashboard (Priority: HIGH)

#### 1.1 Login Page
**File**: `docs/images/01-login-page.png`  
**URL**: `https://pve-ip:8444/`  
**Description**: Login screen showing username/password fields  
**Notes**: 
- Show the UCM logo
- Default credentials visible in placeholder
- Clean, no errors

#### 1.2 Dashboard Overview
**File**: `docs/images/02-dashboard.png`  
**URL**: `https://pve-ip:8444/dashboard`  
**Description**: Main dashboard with statistics  
**Notes**:
- Show CA count, certificate count
- Recent activity
- Quick actions buttons
- Navigation sidebar visible

---

### 2. Certificate Authority Management (Priority: HIGH)

#### 2.1 CA List
**File**: `docs/images/03-ca-list.png`  
**URL**: `https://pve-ip:8444/cas`  
**Description**: List of Certificate Authorities  
**Notes**:
- Show 2-3 CAs (Root and Intermediate)
- Status indicators (Active/Inactive)
- Actions menu visible

#### 2.2 Create CA - Form
**File**: `docs/images/04-create-ca-form.png`  
**URL**: `https://pve-ip:8444/cas` (click "Create CA")  
**Description**: CA creation form  
**Notes**:
- All fields visible
- Show different key types (RSA, ECDSA)
- DN fields (CN, O, OU, C, ST, L)
- Validity period selector

#### 2.3 CA Details
**File**: `docs/images/05-ca-details.png`  
**URL**: `https://pve-ip:8444/cas/{ca_id}`  
**Description**: CA detail page  
**Notes**:
- Certificate information
- DN fields displayed correctly
- Valid from/to dates
- Serial number
- Export options visible

#### 2.4 CA Hierarchy
**File**: `docs/images/06-ca-hierarchy.png`  
**URL**: `https://pve-ip:8444/cas` (if hierarchy view exists)  
**Description**: Visual CA hierarchy  
**Notes**:
- Root → Intermediate relationship
- Tree/graph visualization

---

### 3. Certificate Management (Priority: HIGH)

#### 3.1 Certificate List
**File**: `docs/images/07-certificate-list.png`  
**URL**: `https://pve-ip:8444/certificates`  
**Description**: List of issued certificates  
**Notes**:
- Show 5-10 certificates
- Different types (server, client, code signing)
- Status (valid, revoked, expired)
- Search/filter visible

#### 3.2 Issue Certificate - Form
**File**: `docs/images/08-issue-certificate-form.png`  
**URL**: `https://pve-ip:8444/certificates` (click "Issue Certificate")  
**Description**: Certificate issuance form  
**Notes**:
- Certificate type selector
- Common Name field
- SANs (Subject Alternative Names)
- Key usage options
- Validity period

#### 3.3 Certificate Details
**File**: `docs/images/09-certificate-details.png`  
**URL**: `https://pve-ip:8444/certificates/{cert_id}`  
**Description**: Certificate detail page  
**Notes**:
- Full certificate information
- Issuer information
- Subject information
- Extensions
- Download/Export buttons

#### 3.4 Certificate Export Options
**File**: `docs/images/10-certificate-export.png`  
**URL**: Certificate details → Export menu  
**Description**: Export format options  
**Notes**:
- PEM, DER, PKCS#12 options
- Download certificate
- Download private key
- Download full chain

---

### 4. SCEP Configuration (Priority: MEDIUM)

#### 4.1 SCEP Server Settings
**File**: `docs/images/11-scep-settings.png`  
**URL**: `https://pve-ip:8444/scep` or Settings → SCEP  
**Description**: SCEP server configuration  
**Notes**:
- Enable/Disable toggle
- Challenge password setting
- CA selection
- SCEP URL display

#### 4.2 SCEP Enrollment Example
**File**: `docs/images/12-scep-enrollment.png`  
**URL**: SCEP documentation page (if exists)  
**Description**: SCEP enrollment instructions/code  
**Notes**:
- Example commands
- Configuration snippets
- Platform-specific instructions

---

### 5. User Management (Priority: MEDIUM)

#### 5.1 User List
**File**: `docs/images/13-user-list.png`  
**URL**: `https://pve-ip:8444/users` or Settings → Users  
**Description**: List of users  
**Notes**:
- Username, role, status
- Last login
- Actions (edit, delete)

#### 5.2 Create/Edit User
**File**: `docs/images/14-user-form.png`  
**URL**: User management → Add User  
**Description**: User creation form  
**Notes**:
- Username, password fields
- Role selector (Admin, Operator, Viewer)
- Active/Inactive toggle

---

### 6. System Settings (Priority: LOW)

#### 6.1 General Settings
**File**: `docs/images/15-settings-general.png`  
**URL**: `https://pve-ip:8444/settings`  
**Description**: System settings page  
**Notes**:
- Configuration options
- HTTPS port
- Session timeout
- Other general settings

#### 6.2 System Information
**File**: `docs/images/16-system-info.png`  
**URL**: Settings → System Info  
**Description**: System information display  
**Notes**:
- Version number
- Python version
- Database info
- System paths

---

### 7. Additional Nice-to-Have Screenshots (Priority: LOW)

#### 7.1 Import CA
**File**: `docs/images/17-import-ca.png`  
**Description**: CA import interface

#### 7.2 Certificate Revocation
**File**: `docs/images/18-revoke-certificate.png`  
**Description**: Certificate revocation dialog/confirmation

#### 7.3 Theme Toggle
**File**: `docs/images/19-dark-theme.png`  
**Description**: Interface in dark theme (if available)

#### 7.4 Mobile View
**File**: `docs/images/20-mobile-responsive.png`  
**Description**: Mobile/tablet responsive view
**Notes**: Resize browser to 768px width or use DevTools device mode

---

## 📁 Directory Structure

After capturing, organize as follows:

```
docs/
├── images/
│   ├── 01-login-page.png
│   ├── 02-dashboard.png
│   ├── 03-ca-list.png
│   ├── 04-create-ca-form.png
│   ├── 05-ca-details.png
│   ├── 06-ca-hierarchy.png
│   ├── 07-certificate-list.png
│   ├── 08-issue-certificate-form.png
│   ├── 09-certificate-details.png
│   ├── 10-certificate-export.png
│   ├── 11-scep-settings.png
│   ├── 12-scep-enrollment.png
│   ├── 13-user-list.png
│   ├── 14-user-form.png
│   ├── 15-settings-general.png
│   ├── 16-system-info.png
│   ├── 17-import-ca.png
│   ├── 18-revoke-certificate.png
│   ├── 19-dark-theme.png
│   └── 20-mobile-responsive.png
└── diagrams/
    └── ARCHITECTURE.md (already created with Mermaid diagrams)
```

---

## 🚀 Quick Capture Checklist

**Minimum Essential Screenshots (8):**
- [ ] Login page
- [ ] Dashboard
- [ ] CA list
- [ ] Create CA form
- [ ] Certificate list
- [ ] Issue certificate form
- [ ] Certificate details
- [ ] User management

**Full Documentation (16):**
- [ ] All essential screenshots above
- [ ] CA details
- [ ] Certificate export
- [ ] SCEP settings
- [ ] System settings
- [ ] Import CA
- [ ] Revoke certificate
- [ ] Dark theme (optional)
- [ ] Mobile view (optional)

---

## 📝 After Capturing

1. **Optimize images:**
   ```bash
   # Install optipng (optional)
   sudo apt install optipng
   
   # Optimize all PNGs
   optipng -o7 docs/images/*.png
   ```

2. **Add to git:**
   ```bash
   git add docs/images/
   git commit -m "docs: Add UI screenshots for documentation"
   git push origin main
   ```

3. **Update documentation to reference images:**
   - README.md
   - DOCKER.md
   - New file: docs/USER_GUIDE.md (I can create this with image references)

---

## 🎯 Priority Order

1. **HIGH Priority** (capture first):
   - Login, Dashboard, CA List, CA Form, Certificate List, Certificate Form
   - These are essential for basic documentation

2. **MEDIUM Priority**:
   - CA Details, Certificate Details, SCEP Settings, User Management
   - Important for complete documentation

3. **LOW Priority**:
   - System Settings, Import/Export, Theme variants
   - Nice to have for comprehensive docs

---

**Estimated Time**: 15-20 minutes for all screenshots

**Next Steps**: After you capture these, I'll create a USER_GUIDE.md that incorporates all the screenshots with detailed explanations!
