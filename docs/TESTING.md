# UCM Testing Guide

## Overview

UCM uses a comprehensive testing strategy with unit tests and E2E tests.

| Test Type | Framework | Tests | Status |
|-----------|-----------|-------|--------|
| Unit Tests (Frontend) | Vitest + React Testing Library | 450 | Active |
| Unit Tests (Backend) | pytest | 1364 | Active |
| E2E Tests | Playwright | — | Active |
| Linting (Frontend) | ESLint v9 | — | Active |
| Linting (Backend) | Ruff | — | Active |

**Total: 1814 tests** (450 frontend + 1364 backend)

## Linting

### Frontend (ESLint)

```bash
cd frontend
npm run lint          # Check for issues
npm run lint:fix      # Auto-fix issues
```

Configured with `react-hooks` plugin to catch stale closures, conditional hooks, and undefined variables.

### Backend (Ruff)

```bash
cd backend
ruff check .          # Check for issues
ruff check --fix .    # Auto-fix issues
```

Configured for bug-catching rules only (E/F/B/S categories).

## Unit Tests

### Backend Tests

```bash
cd backend

# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_certificates.py

# Run with coverage
pytest --cov=. --cov-report=term-missing
```

#### Test Files

| File | Tests | Coverage |
|------|-------|----------|
| test_auth_methods.py | 43 | Login, logout, 2FA, method detection |
| test_account.py | 66 | Profile, password, API keys, 2FA, sessions |
| test_users.py | 74 | CRUD, bulk operations, roles |
| test_rbac.py | 38 | Permissions, custom roles |
| test_cas.py | 68 | CA CRUD, import, export, hierarchy |
| test_certificates.py | 73 | Cert lifecycle, export, revoke, renew |
| test_csrs.py | 60 | CSR create, sign, export |
| test_templates.py | 62 | Template CRUD, duplicate, import/export |
| test_settings.py | 93 | All settings categories |
| test_system.py | 89 | Database, HTTPS, backup, updates |
| test_dashboard.py | 27 | Stats, charts, activity |
| test_audit.py | 33 | Logs, export, cleanup |
| test_acme.py | 150 | ACME server, client, domains |
| test_crl.py | 21 | CRL generation, OCSP |
| test_hsm.py | 52 | HSM providers, keys |
| test_sso_routes.py | 37 | SSO providers, sessions |
| test_mtls.py | 25 | mTLS settings, certificates |
| test_webauthn.py | 14 | WebAuthn credentials |
| test_truststore.py | 20 | Trust store CRUD |
| test_webhooks.py | 24 | Webhook CRUD, test |
| test_misc_routes.py | 108 | Search, reports, policies, groups, DNS |

#### Test Pattern

Each test file covers 3 levels per endpoint:
1. **Authentication** — 401 without auth
2. **Authorization** — 403 with wrong role (viewer testing admin endpoints)
3. **Happy path** — 200/201 with valid data

#### Test Infrastructure

- Session-scoped fixtures in `conftest.py` (shared SQLite temp DB)
- Factory helpers: `create_ca()`, `create_cert()`, `create_user()`
- CSRF disabled via `CSRF_DISABLED=true` environment variable
- No external dependencies (no Docker, no network)

### Frontend Tests

```bash
cd frontend

# Run all tests
npm test

# Run with coverage
npm run test:coverage

# Run in watch mode
npm run test:watch
```

### Test Structure

```
frontend/src/
├── components/__tests__/
│   ├── Button.test.jsx
│   ├── Card.test.jsx
│   ├── Table.test.jsx
│   ├── Modal.test.jsx
│   ├── Select.test.jsx
│   └── Pagination.test.jsx
├── pages/__tests__/
│   └── ...
└── services/__tests__/
    └── ...
```

### Writing Tests

```jsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { Button } from '../Button'

describe('Button', () => {
  it('renders with text', () => {
    render(<Button>Click me</Button>)
    expect(screen.getByText('Click me')).toBeInTheDocument()
  })

  it('calls onClick when clicked', () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Click</Button>)
    fireEvent.click(screen.getByText('Click'))
    expect(onClick).toHaveBeenCalled()
  })
})
```

## E2E Tests

### Setup

```bash
cd frontend

# Install Playwright browsers
npx playwright install

# Run E2E tests
npm run test:e2e

# Run with UI
npm run test:e2e:headed
```

### Test Structure

```
frontend/e2e/
├── auth.setup.ts      # Authentication setup
├── config.ts          # Test configuration
├── dashboard.spec.ts  # Dashboard tests
├── certificates.spec.ts
├── cas.spec.ts
├── csrs.spec.ts
├── templates.spec.ts
├── truststore.spec.ts
├── acme.spec.ts
├── scep.spec.ts
├── crlocsp.spec.ts
├── hsm.spec.ts
├── rbac.spec.ts
├── operations.spec.ts
├── audit.spec.ts
├── tools.spec.ts
├── account.spec.ts
├── core.spec.ts       # Users, Settings, Navigation
└── pro/               # SSO & advanced features
    ├── groups.spec.ts
    ├── rbac.spec.ts
    ├── sso.spec.ts
    ├── hsm.spec.ts
    └── ldap.spec.ts
```

### Configuration

E2E tests are configured in `playwright.config.ts`:

```typescript
export default defineConfig({
  testDir: './e2e',
  baseURL: 'https://localhost:8443',
  use: {
    ignoreHTTPSErrors: true,
    storageState: 'e2e/.auth/user.json',
  },
  projects: [
    { name: 'setup', testMatch: /auth\.setup\.ts/ },
    { name: 'chromium', dependencies: ['setup'] },
    { name: 'pro-features', dependencies: ['setup'] },
  ],
})
```

### Writing E2E Tests

```typescript
import { test, expect } from '@playwright/test'

test.describe('Dashboard', () => {
  test('displays stats widgets', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page.locator('text=Certificates')).toBeVisible()
    await expect(page.locator('text=Active CAs')).toBeVisible()
  })
})
```

## Advanced Features Test Infrastructure

For testing advanced features (SSO, LDAP, HSM), a Docker Compose stack is available:

```bash
# Start test infrastructure
cd docker
docker-compose -f docker-compose.test.yml up -d
```

### Services

| Service | Port | Description |
|---------|------|-------------|
| Keycloak | 8180 | SSO (OIDC/SAML) |
| OpenLDAP | 389 | Directory |
| phpLDAPadmin | 8181 | LDAP admin UI |
| SoftHSM | - | HSM simulation |

### Test Credentials

**Keycloak:**
- Admin: `admin` / `admin123`
- Realm: `ucm`
- Client: `ucm-app`

**LDAP:**
- Admin: `cn=admin,dc=ucm,dc=test` / `admin123`
- Users: `alice`, `bob`, `charlie`, `david`, `eve` (password: `{username}123`)

**SoftHSM:**
- Token: `UCM-Test`
- PIN: `87654321`
- Keys: `ucm-ca-key` (RSA 2048), `ucm-root-key` (RSA 4096)

## CI/CD Integration

### GitHub Actions (recommended)

```yaml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      
      - name: Install dependencies
        run: cd frontend && npm ci
      
      - name: Run unit tests
        run: cd frontend && npm test
      
      - name: Install Playwright
        run: cd frontend && npx playwright install --with-deps
      
      - name: Run E2E tests
        run: cd frontend && npm run test:e2e
```

## Coverage Goals

| Metric | Target | Current |
|--------|--------|---------|
| Backend Route Coverage | 80% | ~95% (347 routes) |
| Frontend Unit Tests | — | 450 tests passing |
| Backend Unit Tests | — | 1364 tests passing |
| E2E Pass Rate | 95% | Active |
| Critical Paths | 100% | Covered |

## Troubleshooting

### Auth Setup Fails

UCM has a complex login flow (username → auth method detection → password). If auth fails:

1. Check if WebAuthn is registered for admin user
2. The test waits for "Use password instead" link
3. Increase timeout if WebAuthn detection is slow

### E2E Tests Timeout

```typescript
// Increase timeout for slow operations
test.setTimeout(60000)

// Or per-assertion
await expect(locator).toBeVisible({ timeout: 10000 })
```

### SSL Certificate Errors

Tests ignore HTTPS errors by default. If issues persist:

```typescript
use: {
  ignoreHTTPSErrors: true,
}
```
