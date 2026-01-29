# API Endpoint Audit - Backend Integration

**Date**: 2026-01-22 00:44 UTC

## Directive
- ✅ **API a fonction** → Corriger frontend (transformation données)
- ⚙️ **API manque fonction** → Corriger backend API

---

## Status par Endpoint

### ✅ WORKING - Frontend OK
1. **Dashboard** - 4 endpoints OK
   - `/api/v2/stats/overview` ✅
   - `/api/v2/dashboard/stats` ✅
   - `/api/v2/dashboard/activity` ✅
   - `/api/v2/dashboard/expiring-certs` ✅

2. **CAs** - Endpoint OK, transformation ajoutée ✅
   - `/api/v2/cas` ✅
   - Transform: `common_name` → `name`, `is_root` → `type`, calculate `status`

3. **Profile** - Endpoint OK ✅
   - `/api/v2/account/profile` ✅
   - `/api/v2/account/sessions` ✅

### 🔧 TO FIX - Need Data Transformation
4. **Certificates** - Endpoint exists
   - `/api/v2/certificates` - Returns empty but structure OK
   - Action: Add transformation like CAs

5. **CSRs** - Endpoint exists
   - `/api/v2/csrs` - Returns empty but structure OK
   - Action: Add transformation

6. **Activity** - Endpoint exists
   - `/api/v2/account/activity` - Returns empty array
   - Action: Test with data

### ⚙️ TO CREATE - Missing Backend Functions
7. **ACME Settings** - NEED ENDPOINT
   - `/api/v2/acme/settings` - Returns nothing
   - Action: Create backend endpoint

8. **ACME Stats** - NEED ENDPOINT
   - `/api/v2/acme/stats` - Returns nothing
   - Action: Create backend endpoint

9. **SCEP** - NEED ENDPOINT
   - `/api/v2/scep/settings` - Returns nothing
   - Action: Create backend endpoint

10. **CRL** - NEED ENDPOINT
    - `/api/v2/crl` - Returns nothing
    - Action: Create backend endpoint

11. **Settings** - NEED ENDPOINT
    - `/api/v2/settings` - Returns nothing
    - Action: Create backend endpoint

12. **Templates** - NEED TO CHECK
    - No endpoint tested yet
    - Action: Check if exists

13. **Users** - NEED TO CHECK
    - No endpoint tested yet
    - Action: Check if exists

14. **Import** - NEED TO CHECK
    - `/api/v2/certificates/import` ?
    - Action: Check if exists

15. **TrustStore** - NEED TO CHECK
    - No endpoint found
    - Action: Check backend

---

## Action Plan

### Phase 1: Fix Working Endpoints (Frontend)
- [ ] Certificates - Add data transformation
- [ ] CSRs - Add data transformation
- [ ] Activity - Verify with data

### Phase 2: Create Missing Endpoints (Backend)
- [ ] ACME Settings
- [ ] ACME Stats  
- [ ] SCEP Settings
- [ ] CRL
- [ ] Settings
- [ ] Templates (if needed)
- [ ] Users (if needed)
- [ ] Import (if needed)
- [ ] TrustStore (if needed)

---

**Priority**: Phase 1 first (quick wins), then Phase 2
