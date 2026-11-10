import { describe, it, expect, vi } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import { MemoryRouter, createRoutesFromChildren, useLocation } from 'react-router-dom'

const auth = vi.hoisted(() => ({ value: {} }))
vi.mock('../../contexts', () => ({
  useAuth: () => auth.value,
  AuthProvider: ({ children }) => children,
  ThemeProvider: ({ children }) => children,
  NotificationProvider: ({ children }) => children,
  MobileProvider: ({ children }) => children,
  WindowManagerProvider: ({ children }) => children,
}))
vi.mock('../../hooks/useWebSocket', () => ({ WebSocketProvider: ({ children }) => children }))
vi.mock('../../components', async () => {
  const { Outlet } = await vi.importActual('react-router-dom')
  return {
    AppShell: () => <Outlet />,
    ErrorBoundary: ({ children }) => children,
    LoadingSpinner: () => null,
    SessionWarning: () => null,
    ForcePasswordChange: () => null,
    ForceEnroll2FA: () => null,
    SafeModeOverlay: () => null,
    DetailWindowLayer: () => null,
  }
})

vi.mock('../../pages/DashboardPage', () => ({ default: () => <div>dashboard-page</div> }))
// Same keys as the real binding, each page a stub naming its module
vi.mock('../pages', async () => {
  const actual = await vi.importActual('../pages')
  const stubs = Object.fromEntries(Object.keys(actual.pages)
    .map(id => [id, () => <div data-testid="module-page">{id}</div>]))
  return { ...actual, pages: stubs }
})

import { AppRoutes, moduleRoutes, guarded } from '../../App'
import { Routes, Route } from 'react-router-dom'
import { pages } from '../pages'
import {
  MODULES, GROUPS, SIDEBAR_GROUPS, REDIRECTS, visibleModules, groupsFor, sidebarGroups,
  moduleForPath, paletteCommands, isVisible,
} from '../registry'
import { PERMISSION_RESOURCES } from '../../lib/rbacPermissions'

const here = dirname(fileURLToPath(import.meta.url))
const localesDir = join(here, '../../i18n/locales')
const locales = Object.fromEntries(
  readdirSync(localesDir).filter(f => f.endsWith('.json'))
    .map(f => [f, JSON.parse(readFileSync(join(localesDir, f), 'utf8'))]))
const lookup = (obj, key) => key.split('.').reduce((o, k) => (o == null ? o : o[k]), obj)

const allPaths = MODULES.flatMap(m => [m.path, ...m.paths])
const adminCan = { isAdmin: () => true, hasPermission: () => true }
const makeCan = (permissions) => ({
  isAdmin: () => permissions.includes('*'),
  hasPermission: (p) => permissions.includes('*') || permissions.includes(p),
})
const flatPaths = (routes) => routes.flatMap(r => [r.path, ...flatPaths(r.children || [])]).filter(Boolean)

describe('registry and router agree (a)', () => {
  it('the routes the router builds are exactly the registry paths and redirects', () => {
    const built = flatPaths(createRoutesFromChildren(moduleRoutes()))
    expect([...built].sort()).toEqual([...allPaths, ...REDIRECTS.map(r => r.from)].sort())
  })

  it('every module has a page and every page a module', () => {
    expect(Object.keys(pages).sort()).toEqual(MODULES.map(m => m.id).sort())
  })

  it('a module route denies what its guard denies, in the rendered tree', async () => {
    const Where = () => <div data-testid="where">{useLocation().pathname}</div>
    for (const m of MODULES.filter(x => x.guard === 'admin' || x.guard.permission)) {
      auth.value = { isAuthenticated: true, loading: false, sessionChecked: true, permissions: ['read:other'] }
      const { unmount } = render(<MemoryRouter initialEntries={[m.path]}><AppRoutes /><Where /></MemoryRouter>)
      await waitFor(() => expect(screen.getByTestId('where').textContent, m.id).toBe('/'))
      unmount()
    }
  })

  it('an auth module route admits a signed-in user without permissions, in the rendered tree', async () => {
    const Where = () => <div data-testid="where">{useLocation().pathname}</div>
    const authModules = MODULES.filter(x => x.guard === 'auth')
    expect(authModules.length).toBeGreaterThan(0)
    for (const m of authModules) {
      for (const p of [m.path, ...m.paths]) {
        const path = p.replace(/:[^/]+/g, '7')
        auth.value = { isAuthenticated: true, loading: false, sessionChecked: true, permissions: ['read:other'] }
        const { unmount } = render(<MemoryRouter initialEntries={[path]}><AppRoutes /><Where /></MemoryRouter>)
        expect((await screen.findByTestId('module-page')).textContent, path).toBe(m.id)
        expect(screen.getByTestId('where').textContent, path).toBe(path)
        unmount()
      }
    }
  })
})

// Guards of every route as the router declared them before the registry: 'auth', 'admin' or a permission
const BASE_GUARDS = {
  '/': 'auth', '/dashboard': 'auth', '/certificates': 'auth', '/certificates/:id': 'auth',
  '/user-certificates': 'read:user_certificates', '/cas': 'auth', '/cas/:id': 'auth', '/csrs': 'auth',
  '/templates': 'auth', '/users': 'admin', '/acme': 'read:acme', '/scep-config': 'read:scep',
  '/est-config': 'read:est', '/tsa-config': 'read:settings', '/settings': 'admin', '/audit': 'read:audit',
  '/logs': 'admin', '/operations': 'admin', '/tools': 'auth', '/account': 'auth', '/crl-ocsp': 'read:crl',
  '/truststore': 'read:truststore', '/truststore/:id': 'read:truststore', '/rbac': 'admin',
  '/hsm': 'read:hsm', '/policies': 'read:policies', '/approvals': 'read:approvals',
  '/key-recovery': 'read:key_recovery', '/reports': 'read:audit', '/discovery': 'read:certificates',
  '/ssh/cas': 'read:ssh_cas', '/ssh/certificates': 'read:ssh',
}
const BASE_REDIRECTS = {
  '/import': '/operations', '/groups': '/users?tab=groups', '/sso': '/settings?tab=sso',
  '/security': '/settings?tab=security',
}
const guardOf = (g) => (typeof g === 'string' ? g : g.permission)

describe('guards are those of the router before the registry', () => {
  it('every path carries the same guard', () => {
    const now = {}
    for (const m of MODULES) for (const p of [m.path, ...m.paths]) now[p] = guardOf(m.guard)
    expect(now).toEqual(BASE_GUARDS)
  })

  it('the legacy redirects lead to the same targets', () => {
    expect(Object.fromEntries(REDIRECTS.map(r => [r.from, r.to]))).toEqual(BASE_REDIRECTS)
  })

  const Where = () => <div data-testid="where">{useLocation().pathname}</div>
  const at = (guard, perms, signedIn = true) => {
    auth.value = { isAuthenticated: signedIn, loading: false, sessionChecked: true, permissions: perms }
    return render(
      <MemoryRouter initialEntries={['/p']}>
        <Routes>
          <Route path="/p" element={guarded(guard, <div data-testid="page">page</div>)} />
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>)
  }

  it.each([['auth'], ['admin'], [{ permission: 'read:cas' }]])('guarded(%j) sends a signed-out user to /login', (g) => {
    at(g, [], false)
    expect(screen.getByTestId('where').textContent).toBe('/login')
  })

  it('auth admits any signed-in user', () => {
    at('auth', [])
    expect(screen.getByTestId('page')).toBeTruthy()
  })

  it('admin admits the wildcard only', () => {
    at('admin', ['read:settings'])
    expect(screen.getByTestId('where').textContent).toBe('/')
    cleanup()
    at('admin', ['*'])
    expect(screen.getByTestId('page')).toBeTruthy()
  })

  it('a permission module admits that permission, the wildcard, and no other', () => {
    at({ permission: 'read:hsm' }, ['read:audit'])
    expect(screen.getByTestId('where').textContent).toBe('/')
    cleanup()
    at({ permission: 'read:hsm' }, ['read:hsm'])
    expect(screen.getByTestId('page')).toBeTruthy()
    cleanup()
    at({ permission: 'read:hsm' }, ['*'])
    expect(screen.getByTestId('page')).toBeTruthy()
  })
})

describe('registry shape (b)', () => {
  it('ids and paths are unique', () => {
    const ids = MODULES.map(m => m.id)
    expect(new Set(ids).size).toBe(ids.length)
    expect(new Set(allPaths).size).toBe(allPaths.length)
    const all = [...allPaths, ...REDIRECTS.map(r => r.from)]
    expect(new Set(all).size).toBe(all.length)
  })

  it('imports no page', () => {
    const src = readFileSync(join(here, '../registry.js'), 'utf8')
    // static, side-effect and dynamic imports, either quote
    const specifiers = [...src.matchAll(/(?:^|[\s;}])(?:from\s*|import\s*\(?\s*)['"]([^'"]+)['"]/gm)].map(m => m[1])
    expect(specifiers).toEqual(['@phosphor-icons/react'])
  })

  it('every guard is auth, admin or a permission; any other is refused, not opened', () => {
    for (const m of MODULES) {
      const ok = m.guard === 'auth' || m.guard === 'admin' || typeof m.guard?.permission === 'string'
      expect(ok, m.id).toBe(true)
    }
    expect(() => guarded('admn', null)).toThrow(/unknown guard/)
    expect(() => guarded({ permisson: 'read:x' }, null)).toThrow(/unknown guard/)
    const can = { isAdmin: () => false, hasPermission: () => true }
    expect(isVisible({ guard: 'admn' }, can)).toBe(false)
  })

  it('every group reference names a declared group', () => {
    for (const m of MODULES) {
      if (m.group) expect(GROUPS.map(g => g.id), m.id).toContain(m.group)
      if (m.navGroup) expect(SIDEBAR_GROUPS.map(g => g.id), m.id).toContain(m.navGroup)
    }
  })
})

describe('labels (c)', () => {
  const keys = [
    ...MODULES.flatMap(m => [m.labelKey, m.shortKey, m.palette?.labelKey]),
    ...GROUPS.map(g => g.labelKey), ...SIDEBAR_GROUPS.map(g => g.labelKey),
    ...REDIRECTS.map(r => r.palette?.labelKey),
    ...paletteCommands().flatMap(c => [c.labelKey, c.categoryKey]),
  ].filter(Boolean)

  it('every key exists in the nine locales', () => {
    expect(Object.keys(locales)).toHaveLength(9)
    for (const [file, json] of Object.entries(locales)) {
      for (const key of keys) expect(typeof lookup(json, key), `${file}: ${key}`).toBe('string')
    }
  })
})

describe('permissions (d)', () => {
  it('every permission cited is a known resource with a known action', () => {
    for (const m of MODULES) {
      if (!m.guard.permission) continue
      const [action, resource] = m.guard.permission.split(':')
      expect(['read', 'write', 'delete'], m.id).toContain(action)
      expect(PERMISSION_RESOURCES, m.id).toContain(resource)
    }
  })
})

describe('visibility (e)', () => {
  it('hides admin modules and permission modules the user lacks', () => {
    const ids = visibleModules(makeCan(['read:cas'])).map(m => m.id)
    expect(ids).not.toContain('users')
    expect(ids).not.toContain('settings')
    expect(ids).not.toContain('acme')
    expect(ids).toContain('cas')
    expect(ids).toContain('dashboard')
  })

  it('shows a permission module once granted, an admin sees all', () => {
    expect(visibleModules(makeCan(['read:acme'])).map(m => m.id)).toContain('acme')
    expect(visibleModules(adminCan)).toHaveLength(MODULES.length)
  })

  it('groupsFor drops empty groups', () => {
    const groups = groupsFor(makeCan([])).map(g => g.id)
    expect(groups).toContain('pki')
    expect(groups).not.toContain('governance')
  })

  const sidebarIds = (perms) => sidebarGroups(makeCan(perms)).flatMap(g => g.children.map(c => c.id))
  const operator = ['read:certificates', 'read:user_certificates', 'read:cas', 'read:csrs', 'read:templates',
    'read:truststore', 'read:crl', 'read:acme', 'read:scep', 'read:est', 'read:hsm', 'read:ssh', 'read:ssh_cas',
    'read:policies', 'read:approvals', 'read:key_recovery', 'read:audit', 'read:settings', 'read:groups']
  const auditor = ['read:certificates', 'read:cas', 'read:csrs', 'read:templates', 'read:truststore', 'read:crl',
    'read:acme', 'read:scep', 'read:est', 'read:hsm', 'read:ssh', 'read:ssh_cas', 'read:policies', 'read:approvals', 'read:audit']
  const viewer = ['read:certificates', 'read:cas', 'read:csrs', 'read:templates', 'read:truststore', 'read:ssh', 'read:ssh_cas']

  // Lists captured from the sidebar before the registry replaced its local table
  it.each([
    ['admin', ['*'], ['certificates', 'cas', 'csrs', 'templates', 'ssh-cas', 'ssh-certificates', 'acme', 'scep', 'est', 'tsa', 'crl-ocsp', 'truststore', 'operations', 'tools', 'policies', 'approvals', 'keyRecovery', 'reports', 'discovery', 'users', 'rbac', 'hsm', 'audit', 'logs']],
    ['operator', operator, ['certificates', 'cas', 'csrs', 'templates', 'ssh-cas', 'ssh-certificates', 'acme', 'scep', 'est', 'tsa', 'crl-ocsp', 'truststore', 'tools', 'policies', 'approvals', 'keyRecovery', 'reports', 'discovery', 'hsm', 'audit']],
    ['auditor', auditor, ['certificates', 'cas', 'csrs', 'templates', 'ssh-cas', 'ssh-certificates', 'acme', 'scep', 'est', 'crl-ocsp', 'truststore', 'tools', 'policies', 'approvals', 'reports', 'discovery', 'hsm', 'audit']],
    ['viewer', viewer, ['certificates', 'cas', 'csrs', 'templates', 'ssh-cas', 'ssh-certificates', 'truststore', 'tools', 'discovery']],
  ])('the sidebar lists the same ids in the same order for %s', (_role, perms, expected) => {
    expect(sidebarIds(perms)).toEqual(expected)
  })
})

describe('redirects (f)', () => {
  it('every legacy redirect leads to an existing module route', () => {
    for (const r of REDIRECTS) {
      const target = r.to.split('?')[0]
      expect(moduleForPath(target)?.path, r.from).toBe(target)
    }
  })
})

describe('moduleForPath', () => {
  it('resolves exact, detail and alias routes', () => {
    expect(moduleForPath('/')?.id).toBe('dashboard')
    expect(moduleForPath('/dashboard')?.id).toBe('dashboard')
    expect(moduleForPath('/cas/42')?.id).toBe('cas')
    expect(moduleForPath('/ssh/cas/9')?.id).toBe('ssh-cas')
    expect(moduleForPath('/cas/')?.id).toBe('cas')
    expect(moduleForPath('/nowhere')).toBeNull()
  })
})

describe('palette', () => {
  it('offers the same commands, in the same order, as before the registry', () => {
    expect(paletteCommands().map(c => `${c.id} ${c.path}`)).toEqual([
      'dashboard /', 'certificates /certificates', 'cas /cas', 'csrs /csrs', 'templates /templates',
      'users /users', 'acme /acme', 'scep /scep-config', 'est /est-config', 'import /operations',
      'tools /tools', 'audit /audit', 'settings /settings', 'account /account', 'groups /users?tab=groups',
      'rbac /rbac', 'sso /sso', 'hsm /hsm', 'policies /policies', 'approvals /approvals', 'reports /reports',
      'ssh-cas /ssh/cas', 'ssh-certificates /ssh/certificates',
      'new-cert /certificates', 'new-ca /cas', 'upload-csr /csrs',
    ])
    expect(paletteCommands().filter(c => c.pro).map(c => c.id)).toEqual(['rbac', 'sso', 'hsm'])
  })
})
