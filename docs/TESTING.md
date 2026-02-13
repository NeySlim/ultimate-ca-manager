# UCM Testing Guide

## Overview

UCM uses a comprehensive testing strategy with unit tests and E2E tests.

| Test Type | Framework | Status |
|-----------|-----------|--------|
| Unit Tests | Vitest + React Testing Library | Active |
| E2E Tests | Playwright | Active |

## Unit Tests

### Running Tests

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
├── core.spec.ts       # Users, Settings, Navigation
└── pro/               # Advanced features
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

| Metric | Target |
|--------|--------|
| Unit Test Coverage | 80% |
| E2E Pass Rate | 95% |
| Critical Paths | 100% |

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
