# API Wiring Audit - Frontend ↔ Backend

**Date:** 2026-01-27  
**Status:** 🔴 CRITICAL ISSUES FOUND

## Executive Summary

Multiple frontend-backend mismatches discovered during OpnSense import testing. Pages showing empty despite data in database due to incorrect response structure handling.

---

## Critical Issues Found

### 1. ✅ FIXED - CAs Page Empty
**Problem:** CAsPage expects `casData.cas` but API returns `data.data`  
**File:** `frontend-radix/src/pages/CAsPage.jsx` line 41  
**Fix Applied:** Changed `casData.cas` → `casData.data`

### 2. ✅ FIXED - Certificates Page Empty  
**Problem:** CertificatesPage expects `data.certificates` but API returns `data.data`  
**File:** `frontend-radix/src/pages/CertificatesPage.jsx`  
**Fix Applied:** Changed `data.certificates` → `data.data`, `data.total` → `data.meta.total`

### 3. ✅ FIXED - Session Not Persisting on Refresh
**Problem:** AuthContext never calls `checkSession()` on mount  
**File:** `frontend-radix/src/contexts/AuthContext.jsx` line 15-19  
**Fix Applied:** Changed from `setLoading(false)` to `checkSession()`

---

## API Response Structure Standards

### Backend Standard (Correct)
All list endpoints return:
```json
{
  "data": [...],
  "meta": {
    "total": 10,
    "page": 1,
    "per_page": 20,
    "total_pages": 1
  }
}
```

### Pages to Audit

| Page | Endpoint | Expected Structure | Status |
|------|----------|-------------------|--------|
| CAsPage | `/api/v2/cas` | `{data, meta}` | ✅ FIXED |
| CAsPage (tree) | `/api/v2/cas/tree` | `{tree}` | ⚠️ TO CHECK |
| CertificatesPage | `/api/v2/certificates` | `{data, meta}` | ✅ FIXED |
| CSRsPage | `/api/v2/csrs` | `{data, meta}` | ⚠️ TO CHECK |
| TemplatesPage | `/api/v2/templates` | `{data, meta}` | ⚠️ TO CHECK |
| UsersPage | `/api/v2/users` | `{data, meta}` | ⚠️ TO CHECK |
| ACMEPage | `/api/v2/acme/*` | Various | ⚠️ TO CHECK |
| DashboardPage | Multiple endpoints | Various | ⚠️ TO CHECK |
| SettingsPage | `/api/v2/settings/*` | Various | ⚠️ TO CHECK |

---

## Detailed Endpoint Mapping

### Certificate Authorities

#### `GET /api/v2/cas`
**Backend Response:**
```json
{
  "data": [
    {
      "id": 1,
      "refid": "xxx",
      "descr": "Root CA",
      "type": "Root CA",
      "status": "Active",
      "has_private_key": true,
      "certs": 42,
      ...
    }
  ],
  "meta": {
    "total": 4,
    "page": 1,
    "per_page": 20,
    "total_pages": 1
  }
}
```

**Frontend Usage:**
```javascript
// ✅ CORRECT (after fix)
const casData = await casService.getAll()
setCAs(casData.data || [])

// ❌ WRONG (before fix)
setCAs(casData.cas || [])
```

**Service:** `frontend-radix/src/services/cas.service.js`  
**Component:** `frontend-radix/src/pages/CAsPage.jsx`

---

#### `GET /api/v2/cas/tree`
**Backend Response:**
```json
{
  "tree": [
    {
      "id": 1,
      "name": "Root CA",
      "type": "root",
      "issued_count": 5,
      "children": [...]
    }
  ]
}
```

**Frontend Usage:**
```javascript
const treeDataRes = await casService.getTree()
setTreeData(buildTreeNodes(treeDataRes.tree || []))
```

**Status:** ⚠️ TO VERIFY - Check if backend actually returns `{tree: []}` or `{data: []}`

---

### Certificates

#### `GET /api/v2/certificates`
**Backend Response:**
```json
{
  "data": [
    {
      "id": 1,
      "common_name": "example.com",
      "status": "valid",
      "expires": "2026-12-31",
      ...
    }
  ],
  "meta": {
    "total": 54,
    "page": 1,
    "per_page": 20,
    "total_pages": 3
  }
}
```

**Frontend Usage:**
```javascript
// ✅ CORRECT (after fix)
const data = await certificatesService.getAll({...})
setCertificates(data.data || [])
setTotal(data.meta?.total || 0)

// ❌ WRONG (before fix)
setCertificates(data.certificates || [])
setTotal(data.total || 0)
```

**Service:** `frontend-radix/src/services/certificates.service.js`  
**Component:** `frontend-radix/src/pages/CertificatesPage.jsx`

---

### OpnSense Import

#### `POST /api/v2/import/opnsense/test`
**Backend Request:**
```json
{
  "host": "opnsense.example.com",
  "port": 443,
  "api_key": "xxx",
  "api_secret": "xxx",
  "verify_ssl": false
}
```

**Backend Response:**
```json
{
  "success": true,
  "items": [
    {
      "id": "uuid",
      "type": "CA" | "Certificate",
      "name": "...",
      "selected": true
    }
  ],
  "stats": {
    "cas": 3,
    "certificates": 28
  }
}
```

**Frontend Usage:**
```javascript
const result = await opnsenseService.test(config)
setTestResult(result.stats)
setTestItems(result.items || [])
```

**Status:** ✅ WORKING

---

#### `POST /api/v2/import/opnsense/import`
**Backend Request:**
```json
{
  "host": "...",
  "port": 443,
  "api_key": "...",
  "api_secret": "...",
  "verify_ssl": false,
  "items": ["uuid1", "uuid2", ...]
}
```

**Backend Response:**
```json
{
  "success": true,
  "imported": {
    "cas": 3,
    "certificates": 28
  },
  "skipped": 0,
  "errors": []
}
```

**Status:** ✅ WORKING (returns 0 when all items already exist)

---

## Authentication

### Session Management

#### `POST /api/v2/auth/login`
**Request:**
```json
{
  "username": "admin",
  "password": "changeme123"
}
```

**Response:**
```json
{
  "success": true,
  "user": {
    "id": 1,
    "username": "admin",
    "email": "..."
  },
  "message": "Login successful"
}
```

**Session Cookie:** `session` (HttpOnly, Secure, SameSite=Lax)  
**Lifetime:** 24 hours (changed from 30 min)  
**Storage:** Filesystem `/opt/ucm/data/sessions/`

**Status:** ✅ FIXED - Now calls `checkSession()` on mount

---

#### `GET /api/v2/auth/me`
**Response:**
```json
{
  "id": 1,
  "username": "admin",
  "email": "admin@localhost",
  "role": "admin"
}
```

**Frontend Usage:**
```javascript
const userData = await authService.getCurrentUser()
setUser(userData)
setIsAuthenticated(true)
```

**Status:** ✅ WORKING

---

## Dashboard

### System Overview
**Endpoint:** `/api/v2/dashboard/stats`  
**Status:** ⚠️ TO CHECK - Verify if using mock data or real backend

**Expected Response:**
```json
{
  "certificates": {
    "total": 54,
    "valid": 48,
    "expiring_soon": 3,
    "expired": 3
  },
  "cas": {
    "total": 4,
    "root": 2,
    "intermediate": 2
  }
}
```

---

## Settings Pages

### ACME Settings
**Endpoints:**
- `GET /api/v2/acme/settings`
- `PATCH /api/v2/acme/settings`
- `GET /api/v2/acme/stats`

**Status:** ⚠️ TO CHECK - Verify response structures

---

### SCEP Settings
**Endpoints:**
- `GET /api/v2/scep/config`
- `PATCH /api/v2/scep/config`

**Status:** ⚠️ TO CHECK

---

### Database Management
**Endpoints:**
- `GET /api/v2/system/database/stats`
- `POST /api/v2/system/database/optimize`
- `GET /api/v2/system/database/export`

**Status:** 🔴 NOT IMPLEMENTED (404)

---

### HTTPS Certificate
**Endpoints:**
- `GET /api/v2/system/https/cert`
- `POST /api/v2/system/https/cert/regenerate`
- `POST /api/v2/system/https/cert/apply`

**Status:** 🔴 NOT IMPLEMENTED (404)

---

## Recommendations

### Immediate Actions Required

1. **Create API Response Standard Document**
   - All list endpoints: `{data: [], meta: {}}`
   - All single item: `{data: {}, meta: {}}`
   - All mutations: `{success: bool, data: {}, message: string}`

2. **Audit Remaining Pages**
   - CSRsPage
   - TemplatesPage
   - UsersPage
   - DashboardPage
   - SettingsPage tabs

3. **Add Response Type Definitions**
   - Create TypeScript interfaces or JSDoc comments
   - Document in each service file

4. **Backend Consistency**
   - Verify all endpoints follow standard
   - Add response structure tests

5. **Error Handling**
   - Standardize error responses
   - Add error boundary components

### Long-term Improvements

1. **OpenAPI/Swagger Spec**
   - Generate from backend code
   - Use for frontend type generation

2. **API Client Generator**
   - Use openapi-generator or similar
   - Auto-generate TypeScript types

3. **Integration Tests**
   - Test frontend-backend contract
   - Mock server tests

4. **API Versioning**
   - Current: `/api/v2/*`
   - Plan for v3 migrations

---

## Files Modified (This Session)

### Frontend
- ✅ `frontend-radix/src/pages/CAsPage.jsx` - Fixed data structure
- ✅ `frontend-radix/src/pages/CertificatesPage.jsx` - Fixed data structure
- ✅ `frontend-radix/src/contexts/AuthContext.jsx` - Fixed session check
- ✅ `frontend-radix/src/pages/ImportExportPage.jsx` - Added OpnSense workflow
- ✅ `frontend-radix/src/services/opnsense.service.js` - API integration

### Backend
- ✅ `backend/api/v2/import_opnsense.py` - Added logging
- ✅ `backend/config/settings.py` - Extended session lifetime to 24h

---

## Testing Checklist

- [x] Login persists on refresh
- [x] CAs page shows data (4 CAs)
- [ ] Certificates page shows data (54 certs)
- [ ] CSRs page loads
- [ ] Templates page loads
- [ ] Users page loads
- [ ] Dashboard shows stats
- [ ] Settings tabs all functional
- [ ] OpnSense import works
- [ ] Export functions work

---

## Next Steps

1. Test Certificates page with real data
2. Audit CSRs, Templates, Users pages
3. Create comprehensive API spec document
4. Add TypeScript or JSDoc types
5. Implement missing backend endpoints (Database, HTTPS, OCSP)
