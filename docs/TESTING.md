# UCM Testing Guide

## Overview

UCM uses a comprehensive testing strategy with unit tests and E2E tests.

| Test Type | Framework | Status |
|-----------|-----------|--------|
| Unit Tests (Frontend) | Vitest + React Testing Library | Active |
| Unit Tests (Backend) | pytest | Active |
| E2E Tests | Playwright, against a real instance | Active (CI job "End-to-end (browser)") |
| Linting (Frontend) | ESLint v9 | Active |
| Linting (Backend) | Ruff | Active |

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
pip install -r requirements-dev.txt   # runtime and test dependencies

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
| test_crl_aki_rfc5280.py | 7 | RFC 5280 §5.2.1. CRL AKI = issuing CA SKI (#202/#203) |
| test_crl_rfc5280_profile.py | 13 | IDP/FreshestCRL/reasonCode profile (#204) |
| test_rfc5280_cert_crl_profile_gaps.py | 8 | CSR SKI/AKI, CA AIA, invalidityDate, unhold removeFromCRL |
| test_hsm.py | 52 | HSM providers, keys |
| test_sso_routes.py | 37 | SSO providers, sessions |
| test_mtls.py | 25 | mTLS settings, certificates |
| test_webauthn.py | 14 | WebAuthn credentials |
| test_truststore.py | 20 | Trust store CRUD |
| test_webhooks.py | 24 | Webhook CRUD, test |
| test_misc_routes.py | 108 | Search, reports, policies, groups, DNS |

#### Test Pattern

Each test file covers 3 levels per endpoint:
1. **Authentication**: 401 without auth
2. **Authorization**: 403 with wrong role (viewer testing admin endpoints)
3. **Happy path**: 200/201 with valid data

#### Test Infrastructure

- Session-scoped fixtures in `conftest.py` (shared SQLite temp DB)
- Factory helpers: `create_ca()`, `create_cert()`, `create_user()`
- CSRF disabled via `CSRF_DISABLED=true` environment variable
- No external dependencies (no Docker, no network)
- PostgreSQL mode: `UCM_TEST_APP_PG_URL` runs the same fixtures on PostgreSQL, see [testing/postgres-harness.md](testing/postgres-harness.md)

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

## Release Smoke

The release smoke (`release-smoke.yml`, with `scripts/ci/package-smoke.sh` for the packages) is called by "Build & Release" on a tag before anything is published, so its definition and scripts are those of the tag, and every checkout names the tag `v<version>`. It boots the images that run pushed without a tag, pulled by their amd64 digest (standard and FIPS), and installs the packages from that run's artifacts. Only a green smoke lets the run tag the standard and FIPS images (both registries) and update the Docker Hub page, then create the GitHub release. The smoke boots the amd64 images only: the arm64 images are tagged without it. The standard and FIPS images are tagged by two jobs side by side, so if one of them fails after a green smoke, the other's tags are public while no release is created. A failed smoke, standard or FIPS, fails the run with none of these done; its "Nothing Published" job lists the untagged digests left on the registries, which the workflow does not delete, and the git tag stays. It can also be started by hand (workflow dispatch with the version), which checks out the same tag and runs that tag's scripts (`scripts/ci/release_version.py`, `scripts/ci/wait-health.sh`): a manual smoke only checks tags that carry them, and an earlier version is checked from its own release line. A "Build & Release" run started manually on a branch builds the packages and the images to check them, but pushes no image, publishes no release and calls no smoke.

The `latest` and `latest-fips` image tags, and the "Latest" mark of the GitHub release, go to a stable version that no published stable tag exceeds: never to a release candidate, never to a maintenance release of an older line, never to a branch run (`scripts/ci/release_version.py latest`).

## E2E Tests

The end-to-end suite drives Chromium against a real instance: the backend of the checkout, a fresh SQLite database in a temporary directory, and the interface built by `npm run build`. One script sets it up, the same in the CI and on a workstation.

### Running

```bash
# From the repository root: builds the interface, starts UCM on a free loopback port,
# runs Playwright, stops UCM. The exit code is Playwright's.
bash scripts/ci/e2e.sh

# Arguments go to `playwright test`: one file, one test, a headed browser
bash scripts/ci/e2e.sh e2e/certificates.spec.ts
bash scripts/ci/e2e.sh -g "revoked" --headed
```

The script needs `python` (or `UCM_PYTHON`) with `backend/requirements.txt` installed, `npm`, and the system libraries of Chromium (`npx playwright install-deps chromium`, as root). It downloads Chromium with `npx playwright install chromium`, into `PLAYWRIGHT_BROWSERS_PATH` when set. It writes only under a temporary directory and under `frontend/` (`dist/`, `playwright-report/`, `test-results/`). The administrator password is generated for each run and handed to the tests. It refuses to run while a `.env` file sits at the root of the checkout: the backend loads it, so its database, Redis and keys would become those of the test instance.

### What it covers

One file per domain under `frontend/e2e/`; every test creates its own objects through the API and checks what the screen shows and what the API returns afterwards.

| File | Covers |
|------|--------|
| `auth.spec.ts` | Password sign-in, refused password, sign-out, a session ended by the server, French and dark mode kept across a reload |
| `navigation.spec.ts` | Every route of `src/navigation/registry.js` (detail routes with a created object) opens with a heading, no error screen and no console error; the legacy URLs; the Modules menu |
| `overview.spec.ts` | The overview cards load; a queue entry opens the object it names |
| `cas.spec.ts` | A root then an intermediate created on screen, seen in the hierarchy |
| `certificates.spec.ts` | Issue, inspector detail, renew, revoke (the next CRL lists the serial), PEM export |
| `csrs.spec.ts`, `templates.spec.ts`, `crl-ocsp.spec.ts` | CSR import and signing, template creation, CRL generation and OCSP switch |
| `protocols.spec.ts` | ACME, SCEP and EST settings saved and read back |
| `truststore.spec.ts` | A managed CA added to the trust store, the certificate decoder |
| `users.spec.ts` | An operator neither sees nor opens the administration pages (sent back to the overview); users, groups and custom roles created on screen |
| `settings.spec.ts`, `audit.spec.ts` | A general setting saved and read back; an action of the test found in the audit log |
| `key-recovery.spec.ts`, `account.spec.ts` | Key recovery with dual control; password change and TOTP enrolment |
| `backup-restore.spec.ts` | A backup created then restored on screen, with its report; runs alone, after the others, since a restore replaces the database |

The configuration is `frontend/playwright.config.ts`: Chromium only, no retry (a flaky test is fixed, not replayed), traces and screenshots kept on failure, English forced. A test marked `test.fail()` documents a known product defect, with its reason on the same line; it turns red once the defect is fixed, so the mark is removed then.

### Lab tests

`frontend/e2e/lab/` holds the tests that need external services (an ACME CA reachable on the Internet and a DNS provider). The configuration leaves them out unless `UCM_LAB=1` is set; they run against an instance prepared for them, never in the CI:

```bash
cd frontend
UCM_LAB=1 UCM_E2E_BASE_URL=https://ucm.example.test:8443 UCM_E2E_ADMIN_PASSWORD='...' \
  npx playwright test e2e/lab/acme-dns-preferred-chain.spec.ts
```

Without `UCM_E2E_MANAGED=1`, which only `scripts/ci/e2e.sh` sets, and always with `UCM_LAB=1`, the global setup changes no setting and the backup restore test does not run. The other tests still create objects and save settings: on a shared instance, name the lab files to run, as above.

## CI/CD Integration

The "End-to-end (browser)" job of `tests.yml` runs on pull requests, on each push of the 3.0 integration branch and on a manual run. It installs the backend and frontend dependencies and the browser libraries, then calls `scripts/ci/e2e.sh`; on failure the Playwright report and the traces are kept as the `e2e-report` artifact. `backend/tests/test_workflow_e2e.py` pins when the job runs and what it runs.

## Troubleshooting

### The instance does not start

`scripts/ci/e2e.sh` prints the last lines of the server console, application log and access log when the instance is not healthy within 180 seconds or when a test fails.

### A test fails in the CI only

Download the `e2e-report` artifact and open a trace with `npx playwright show-trace <trace.zip>`; the console log of the job also holds the accessibility tree of the page at the failure.
