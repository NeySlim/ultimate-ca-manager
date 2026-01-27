# UCM API Specification v2 - Complete Contract

**Generated:** 2026-01-27  
**Status:** 🔴 CRITICAL - All frontend/backend contracts broken

---

## Problem Statement

**100% of tested endpoints have frontend/backend mismatches.**

The backend consistently returns `{data: ...}` wrapper, but frontend expects various structures:
- Some expect `data.certificates`, `data.users`, etc. (nested)
- Some expect direct `settings`, `config` (no wrapper)
- Some were recently fixed to use `data.data` but analyzer shows old expectations

---

## Standard Response Structure (Backend Reality)

### List Endpoints
```json
{
  "data": [...],  // Array of items
  "meta": {
    "total": 54,
    "page": 1,
    "per_page": 20,
    "total_pages": 3
  }
}
```

### Single Item / Config Endpoints
```json
{
  "data": {
    // Single object or config
  }
}
```

### Mutations (Create/Update/Delete)
```json
{
  "success": true,
  "data": {...},
  "message": "Operation successful"
}
```

---

## Endpoint-by-Endpoint Analysis

### CAs List

**Endpoint:** `GET /api/v2/cas`  
**Status:** `200`  
**Backend Returns:** `['data', 'meta']`  
**Compatible:** ❌ False  

**Backend Structure:**
```json
{
  "data": [...],
  "meta": {...}
}
```

---

### CAs Tree

**Endpoint:** `GET /api/v2/cas/tree`  
**Status:** `200`  
**Backend Returns:** `['data']`  
**Compatible:** ❌ False  

**Backend Structure:**
```json
{
  "data": {...} or [...]
}
```

---

### Certificates

**Endpoint:** `GET /api/v2/certificates`  
**Status:** `200`  
**Backend Returns:** `['data', 'meta']`  
**Compatible:** ❌ False  

**Backend Structure:**
```json
{
  "data": [...],
  "meta": {...}
}
```

---

### CSRs

**Endpoint:** `GET /api/v2/csrs`  
**Status:** `200`  
**Backend Returns:** `['data', 'meta']`  
**Compatible:** ❌ False  

**Backend Structure:**
```json
{
  "data": [...],
  "meta": {...}
}
```

---

### Templates

**Endpoint:** `GET /api/v2/templates`  
**Status:** `200`  
**Backend Returns:** `['data']`  
**Compatible:** ❌ False  

**Backend Structure:**
```json
{
  "data": {...} or [...]
}
```

---

### Users

**Endpoint:** `GET /api/v2/users`  
**Status:** `200`  
**Backend Returns:** `['data']`  
**Compatible:** ❌ False  

**Backend Structure:**
```json
{
  "data": {...} or [...]
}
```

---

### Dashboard Stats

**Endpoint:** `GET /api/v2/dashboard/stats`  
**Status:** `200`  
**Backend Returns:** `['data']`  
**Compatible:** ❌ False  

**Backend Structure:**
```json
{
  "data": {...} or [...]
}
```

---

### ACME Settings

**Endpoint:** `GET /api/v2/acme/settings`  
**Status:** `200`  
**Backend Returns:** `['data']`  
**Compatible:** ❌ False  

**Backend Structure:**
```json
{
  "data": {...} or [...]
}
```

---

### SCEP Config

**Endpoint:** `GET /api/v2/scep/config`  
**Status:** `200`  
**Backend Returns:** `['data']`  
**Compatible:** ❌ False  

**Backend Structure:**
```json
{
  "data": {...} or [...]
}
```

---


## Required Frontend Changes

All pages must be updated to use `data` wrapper:

### Pattern 1: List with Pagination
```javascript
// ❌ WRONG
const response = await service.getAll()
setItems(response.items || [])
setTotal(response.total || 0)

// ✅ CORRECT
const response = await service.getAll()
setItems(response.data || [])
setTotal(response.meta?.total || 0)
```

### Pattern 2: Single Config/Settings
```javascript
// ❌ WRONG  
const settings = await service.getSettings()
setConfig(settings)

// ✅ CORRECT
const response = await service.getSettings()
setConfig(response.data)
```

### Pattern 3: Tree/Hierarchical Data
```javascript
// ❌ WRONG
const tree = await service.getTree()
setTree(tree.tree || [])

// ✅ CORRECT
const response = await service.getTree()
// Check actual backend structure - might be response.data.roots, response.data.orphans
setTree(response.data || [])
```

---

## Files Requiring Updates

### Priority 1 - CRITICAL (Empty Pages)
1. ✅ `CAsPage.jsx` - FIXED (partially)
2. ✅ `CertificatesPage.jsx` - FIXED  
3. ❌ `CSRsPage.jsx` - Change `data.csrs` → `data.data`
4. ❌ `TemplatesPage.jsx` - Change `data.templates` → `data.data`
5. ❌ `UsersPage.jsx` - Change `data.users` → `data.data`
6. ❌ `DashboardPage.jsx` - Change `stats.*` → `stats.data.*`

### Priority 2 - Settings Tabs
7. ❌ `SettingsPage.jsx` (ACME tab) - Change `settings` → `response.data`
8. ❌ `SettingsPage.jsx` (SCEP tab) - Change `config` → `response.data`
9. ❌ `SettingsPage.jsx` (Other tabs) - Verify all use `response.data`

---

## Testing Checklist

After fixes, verify:

- [ ] CAs page shows 4 CAs
- [ ] CAs tree view works
- [ ] Certificates page shows 54 certs
- [ ] CSRs page loads (currently empty OK)
- [ ] Templates page loads
- [ ] Users page shows users
- [ ] Dashboard shows correct stats
- [ ] ACME settings load
- [ ] SCEP settings load
- [ ] All dates display correctly (not "Invalid Date")

---

## Date Field Mapping

Backend uses different field names than frontend expects:

| Backend Field | Frontend Expects | Fix |
|--------------|------------------|-----|
| `valid_from` | `not_before` | Map in service or fix frontend |
| `valid_to` | `not_after` | Map in service or fix frontend |
| `expires` | `expires` | ✅ OK (string "YYYY-MM-DD") |
| `expiry` | N/A | Duplicate of expires |

**Recommendation:** Update frontend to use backend field names (`valid_from`, `valid_to`)

---

## Implementation Plan

### Phase 1: Fix Critical Empty Pages (30 min)
1. Update CSRsPage.jsx
2. Update TemplatesPage.jsx  
3. Update UsersPage.jsx
4. Update DashboardPage.jsx
5. Deploy and test

### Phase 2: Fix Settings Tabs (15 min)
1. Update all SettingsPage.jsx tabs
2. Verify each tab loads correctly

### Phase 3: Fix Date Display (15 min)
1. Change all `not_before` → `valid_from`
2. Change all `not_after` → `valid_to`
3. Test date formatting

### Phase 4: Comprehensive Testing (30 min)
1. Manual test all pages
2. Check browser console for errors
3. Verify all data displays correctly

**Total Time: ~90 minutes**

---

## Long-term Solution

1. **TypeScript Interfaces**: Generate from OpenAPI spec
2. **API Service Layer**: Single source of truth for transformations
3. **Automated Testing**: Contract tests between frontend/backend
4. **Documentation**: Keep this spec updated with all changes

