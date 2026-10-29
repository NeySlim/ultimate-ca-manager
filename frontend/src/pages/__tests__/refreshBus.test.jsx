/**
 * The `ucm:data-changed` refresh bus (DUP-FE-017).
 *
 * (a) SSHCertificatesPage listened for `detail.type === 'ssh-certificate'`.
 *     That string exists nowhere else in the repo: the only types dispatched
 *     are `certificate`, `ca`, `truststore` and `user_certificate`, all from
 *     the floating detail window and the CA modals — and SSH certificates are
 *     never opened in a floating window (no openWindow('ssh-certificate', ...),
 *     no entry in FloatingDetailWindow's DetailContent). The listener could
 *     never fire, and repointing it at `certificate` would reload the SSH list
 *     on unrelated X.509 events.
 *
 * (b) #345: a bus listener registered with `[]` keeps the loader captured at
 *     mount. CertificatesPage, UserCertificatesPage and SSHCertificatesPage
 *     depend on their loader; CAsPage and TrustStorePage did not. Their loaders
 *     read no filter state today, so the defect is latent rather than visible —
 *     the check below is therefore STRUCTURAL (the effect's dependency array
 *     and the memoisation of the loader), plus a behavioural check that the
 *     listener still reloads and that memoising did not create a re-subscribe
 *     or reload loop.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { readFileSync } from 'fs'
import { join } from 'path'

// `t` must keep its identity across renders, like the real hook: every page's
// loader lists it in its dependencies.
vi.mock('react-i18next', () => {
  const translation = {
    t: (key, opts) => (opts && typeof opts.count === 'number' ? `${key}:${opts.count}` : key),
    i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} },
  }
  return {
    useTranslation: () => translation,
    Trans: ({ children }) => children,
    initReactI18next: { type: '3rdParty', init: () => {} },
  }
})

// The real notification context memoises these; a mock that returns a fresh
// object per render would make every page's loader unstable and re-fire its
// effects, which is a test artefact, not a page defect.
const notification = {
  showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
  showConfirm: vi.fn().mockResolvedValue(false), showPrompt: vi.fn().mockResolvedValue(null),
}
const mobile = {
  isMobile: false, isTablet: false, isDesktop: true, isTouch: false, isLargeScreen: true,
  screenWidth: 1280, sidebarOpen: true, setSidebarOpen: vi.fn(),
}
const windowManager = {
  openWindow: vi.fn(), closeWindow: vi.fn(), windows: [],
  prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: vi.fn(),
}

vi.mock('../../contexts', () => ({
  useNotification: () => notification,
  useMobile: () => mobile,
  useWindowManager: () => windowManager,
}))
vi.mock('../../contexts/MobileContext', () => ({ useMobile: () => mobile }))
vi.mock('../../contexts/WindowManagerContext', () => ({ useWindowManager: () => windowManager }))

const permission = {
  canWrite: () => true, canDelete: () => true, hasPermission: () => true, canRead: () => true,
}
const recentHistory = { addToHistory: vi.fn(), history: [] }
const favorites = { favorites: [], toggleFavorite: vi.fn(), isFavorite: () => false }
const websocket = { muteToasts: vi.fn(), subscribe: vi.fn(() => vi.fn()), isConnected: false }
const clipboard = { copy: vi.fn(), copied: false }

vi.mock('../../hooks', async () => {
  const persisted = await vi.importActual('../../hooks/usePersistedState')
  const common = await vi.importActual('../../hooks/useCommon')
  return {
    usePersistedState: persisted.usePersistedState,
    useModals: common.useModals,
    usePermission: () => permission,
    useRecentHistory: () => recentHistory,
    useFavorites: () => favorites,
    useWebSocket: () => websocket,
    useClipboard: () => clipboard,
  }
})

const casGetAll = vi.fn()
const trustGetAll = vi.fn()
const sshGetAll = vi.fn()
vi.mock('../../services', () => ({
  casService: {
    getAll: (...a) => casGetAll(...a),
    getChainRepairStatus: vi.fn().mockResolvedValue({ data: null }),
    getCrossFindings: vi.fn().mockResolvedValue({ data: { findings: [] } }),
    getById: vi.fn().mockResolvedValue({ data: {} }),
    export: vi.fn(),
  },
  truststoreService: {
    getAll: (...a) => trustGetAll(...a),
    getStats: vi.fn().mockResolvedValue({ data: { total: 0, root_ca: 0, intermediate_ca: 0, expired: 0, valid: 0 } }),
    getById: vi.fn().mockResolvedValue({ data: {} }),
  },
  sshCertificatesService: {
    getAll: (...a) => sshGetAll(...a),
    getStats: vi.fn().mockResolvedValue({ data: { certificates: { valid: 0, expired: 0, revoked: 0, total: 0 } } }),
  },
  sshCasService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
}))

import SSHCertificatesPage from '../SSHCertificatesPage'
import CAsPage from '../CAsPage'
import TrustStorePage from '../TrustStorePage'

const dispatch = async (type) => {
  await act(async () => {
    window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type } }))
  })
}

const src = (file) => readFileSync(join(__dirname, '..', file), 'utf8')

/** Dependency array of the effect that registers the `ucm:data-changed` listener. */
const busEffectDeps = (source) => {
  const m = source.match(/removeEventListener\('ucm:data-changed', handler\)\s*\n\s*\},\s*\[([^\]]*)\]/)
  return m ? m[1].trim() : null
}

describe('DUP-FE-017a — no listener for an event nobody emits', () => {
  beforeEach(() => {
    window.localStorage.clear()
    sshGetAll.mockReset()
    sshGetAll.mockResolvedValue({ data: [], meta: { total: 0 } })
  })

  it('SSHCertificatesPage does not reload on a phantom `ssh-certificate` event', async () => {
    render(<MemoryRouter><SSHCertificatesPage /></MemoryRouter>)
    await waitFor(() => expect(sshGetAll).toHaveBeenCalled())
    const before = sshGetAll.mock.calls.length
    await dispatch('ssh-certificate')
    expect(sshGetAll.mock.calls.length).toBe(before)
  })

  it('SSHCertificatesPage does not reload on X.509 certificate events either', async () => {
    render(<MemoryRouter><SSHCertificatesPage /></MemoryRouter>)
    await waitFor(() => expect(sshGetAll).toHaveBeenCalled())
    const before = sshGetAll.mock.calls.length
    await dispatch('certificate')
    await dispatch('ca')
    expect(sshGetAll.mock.calls.length).toBe(before)
  })
})

describe('DUP-FE-017b — the #345 dependency, structural', () => {
  it('CAsPage registers its listener against the loader', () => {
    const source = src('CAsPage.jsx')
    expect(busEffectDeps(source)).toBe('loadCAs')
    expect(source).toMatch(/const loadCAs = useCallback\(/)
  })

  it('TrustStorePage registers its listener against the loader', () => {
    const source = src('TrustStorePage.jsx')
    expect(busEffectDeps(source)).toBe('loadCertificates')
    expect(source).toMatch(/const loadCertificates = useCallback\(/)
  })

  it('the three pages already fixed keep the dependency', () => {
    expect(busEffectDeps(src('CertificatesPage.jsx'))).toBe('loadData')
    expect(busEffectDeps(src('UserCertificatesPage.jsx'))).toBe('loadData')
  })
})

describe('DUP-FE-017b — the listener still works, and only once', () => {
  beforeEach(() => {
    window.localStorage.clear()
    casGetAll.mockReset()
    casGetAll.mockResolvedValue({ data: [] })
    trustGetAll.mockReset()
    trustGetAll.mockResolvedValue({ data: [] })
  })

  it('CAsPage loads once at mount and reloads on a `ca` event', async () => {
    render(<MemoryRouter><CAsPage /></MemoryRouter>)
    await waitFor(() => expect(casGetAll).toHaveBeenCalled())
    await waitFor(() => expect(casGetAll.mock.calls.length).toBe(1))
    await dispatch('ca')
    await waitFor(() => expect(casGetAll.mock.calls.length).toBe(2))
    await dispatch('certificate')
    expect(casGetAll.mock.calls.length).toBe(2)
  })

  it('TrustStorePage loads once at mount and reloads on a `truststore` event', async () => {
    render(<MemoryRouter><TrustStorePage /></MemoryRouter>)
    await waitFor(() => expect(trustGetAll).toHaveBeenCalled())
    await waitFor(() => expect(trustGetAll.mock.calls.length).toBe(1))
    await dispatch('truststore')
    await waitFor(() => expect(trustGetAll.mock.calls.length).toBe(2))
    await dispatch('ca')
    expect(trustGetAll.mock.calls.length).toBe(2)
  })
})
