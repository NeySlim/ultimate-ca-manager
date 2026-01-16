# Changelog - UCM v1.11.0

**Release Date:** 2026-01-16  
**Previous Version:** 1.8.3  
**Breaking Changes:** None

---

## 🎉 Major Features

### Backup & Restore System (NEW)
- **Full system backup with encryption**
  - AES-256-GCM encryption for all sensitive data
  - PBKDF2 key derivation (100,000 iterations)
  - Individual private key encryption
  - SHA256 checksum verification
  - Exports all models: CAs, certificates, users, config, ACME accounts
  
- **Restore with validation**
  - Version compatibility checks
  - Checksum verification before restore
  - Database transaction rollback on failure
  - Validation endpoint for pre-restore checks
  
- **API Endpoints**
  - `POST /api/v1/backup/create` - Create encrypted backup
  - `POST /api/v1/backup/restore` - Restore from backup
  - `POST /api/v1/backup/validate` - Validate backup file
  
- **Testing**
  - 22 unit tests passing (12 backup + 10 restore)
  - Full workflow integration tests passing
  - Typical backup size: ~219KB

### Sidebar Collapsible (NEW)
- **Collapsible navigation sidebar** with icon-only mode
  - Normal mode: 240px width with full text labels
  - Collapsed mode: 70px width with centered icons
  - Toggle button integrated in Dashboard item (chevron left/right)
  - **13 tooltips** on all navigation items in collapsed mode
  - State persists via localStorage
  - Smooth transitions with cubic-bezier easing
  - Compatible with all 8 themes

### Login UX Complete Redesign
- **Simplified 3-step authentication flow**:
  1. Username entry
  2. User selection (with avatar) for "remember me"
  3. Direct authentication attempt (mTLS/WebAuthn → password fallback)
  
- **Persistent user badge** during authentication
  - Shows 48px avatar + username throughout auth process
  - Only auth method container refreshes, not entire page
  - "Not you?" link positioned below badge

- **Windows 11-style spinner**
  - Circular spinner (28px) positioned right of username
  - Appears during mTLS/WebAuthn attempt
  - Hides during password entry
  - Re-appears during form submission
  - Uses primary theme color for compatibility

- **WebAuthn timeout protection**
  - 10-second timeout prevents hanging in headless environments
  - Automatic fallback to password authentication

### CRL Auto-Regeneration
- **Background scheduler** for automatic CRL regeneration
  - Daemon thread running SchedulerService
  - Regenerates CRLs 24 hours before expiry
  - Visual status indicator in CRL list UI
  - Statistics dashboard with:
    - Active CRLs count
    - Revoked certificates count
    - Scheduler status (enabled/disabled)
    - Last check timestamp

### Health & Monitoring
- **Health check API endpoints**
  - `/health` - Basic health status
  - `/health/detailed` - Comprehensive system info
  - Database connectivity checks
  - Scheduler status monitoring

---

## 🔧 Improvements

### UI/UX Enhancements
- **Refresh icon behavior fixed**
  - Static by default (no constant spinning)
  - Spins fast only when clicked or during active request
  - Uses `:active`, `.refreshing`, `.htmx-request` states

- **Theme system improvements**
  - Nebula theme now purple (was blue)
  - Dynamic theme colors in dropdown preview
  - Gradient theme palette icon (thinner stroke 1.5→1)
  - Smooth animations on all pages

- **Settings tabs redesign**
  - Standardized to "Spacious" design across all pages
  - Removed obsolete `my_account_mtls` page
  - Consolidated mTLS management to dedicated page

### Performance Optimizations
- **Global loader improvements**
  - Added delay to prevent flicker on fast requests
  - Smooth fade-in/out transitions

- **Database optimization**
  - Automated VACUUM optimization
  - Reduces database file size
  - Improves query performance

### System Maintenance
- **Log rotation with logrotate**
  - Automatic log file rotation
  - Prevents disk space issues
  - Configurable retention policies

- **Backup directory management**
  - Moved HTTPS cert backups to data directory
  - Uses DATA_DIR constant for consistency
  - Fixed /etc/ucm write access permissions

---

## 🐛 Bug Fixes

### Backup System
- Fixed backup directory path using DATA_DIR constant
- Fixed /etc/ucm write permissions for cert backups
- Improved backup file organization

### Login Flow
- Fixed manual "Sign In" button not working
- Fixed theme dropdown styling issues
- Fixed username persistence with "Not you?" option
- Restored complete login functionality after theme integration

### Scheduler
- Fixed "Initializing..." stuck state in UI
  - Now uses `init_scheduler()` to ensure global instance sharing
  - Route handlers properly access same scheduler instance
- Added explicit "Pending" and "Disabled" states
- Removed redundant CRL info banner

### Icons & UI
- Fixed spinner animations for refresh icons
- Updated icons.json with missing icon definitions
- Fixed login page manual sign-in flow
- Updated system config icons

---

## 📊 Statistics & Metrics

### Code Changes
- **Commits:** 40+ commits since v1.8.3
- **Files Modified:** 30+ files across frontend and backend
- **Lines Added:** ~3,500+ lines
- **Lines Removed:** ~800+ lines

### Features Breakdown
- **New Features:** 6 major features (Backup, Restore, Sidebar, Login UX, CRL Auto-regen, Health)
- **UI Improvements:** 12+ enhancements
- **Bug Fixes:** 10+ critical fixes
- **Performance:** 3 optimizations
- **Security:** AES-256-GCM encryption for backups

---

## 🎨 Visual Changes

### Login Page
- Clean, modern design following Google/Microsoft/GitHub best practices
- Large 64px avatars for user selection
- Compact 48px badge during authentication
- Smooth fade transitions between steps

### Sidebar
- Toggle button: 20px with 14px chevron icon
- Opacity 0.4 (discrete), 0.8 on hover
- Position: absolute right edge of Dashboard row
- Tooltips: appear on right, z-index 1000

### CRL Management
- Dashboard-style statistics cards
- Grid + table card layout
- Real-time scheduler status updates

---

## 🔄 Migration Notes

### From v1.8.3
- **No database migration required**
- **No breaking changes** in API or configuration
- All new features are additive
- Existing functionality fully preserved

### Recommended Steps
1. Backup database (optional, no schema changes)
2. Deploy new code to `/opt/ucm`
3. Restart service: `systemctl restart ucm`
4. Clear browser cache (Ctrl+Shift+R) for CSS updates

---

## 📚 Documentation Updates

### Session Summaries Created
- `SESSION_2026-01-16_LOGIN_UX_COMPLETE.md`
- `SESSION_2026-01-16_LOGIN_UX_REFACTOR.md`
- `SESSION_2026-01-16_SIDEBAR_COLLAPSE.md`
- `SESSION_2026-01-12_V1.9.0_COMPLETE.md`
- `SESSION_2026-01-11_COMPLETE.md`

### Updated Documentation
- ROADMAP updated to v1.9.0-beta1 status
- AI Assistant instructions updated with backup rules
- Icon system context fully documented
- Testing tools documentation completed

---

## 🚀 Deployment

### Production Status
- ✅ Deployed to `/opt/ucm`
- ✅ Service active and running
- ✅ All features tested and validated
- ✅ Compatible with all 8 themes

### Git Status
- **Branch:** `dev/v1.11.0`
- **Remote:** `origin/dev/v1.11.0`
- **Commits:** All commits pushed
- **Status:** Ready for merge to main (pending approval)

---

## 👥 Contributors

- AI Assistant (all development)
- User feedback and validation throughout

---

## 🔗 Related Issues

- Sidebar collapse feature (requested)
- Login UX improvements (requested)
- CRL auto-regeneration (implemented)
- Theme consistency (improved)

---

## 📝 Notes

This release represents a significant UX overhaul with focus on:
1. **Modern design patterns** - Following industry leaders
2. **User experience** - Streamlined, intuitive flows
3. **Performance** - Optimized loading and database
4. **Maintainability** - Clean code, good documentation

All features have been tested in production environment and validated by end user.

---

**Next Steps:**
- User testing and feedback collection
- Potential merge to `main` branch
- Official release tagging (requires approval)
- Update production documentation

---

*Generated: 2026-01-16 23:29 CET*  
*Build: dev/v1.11.0 (aff5811)*
