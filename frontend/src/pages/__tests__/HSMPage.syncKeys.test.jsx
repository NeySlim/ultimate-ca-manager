/**
 * HSM provider details: the key synchronization runs once at a time and its
 * message reports everything the route returns.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts ? `${key} ${JSON.stringify(opts)}` : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

const notify = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
  showConfirm: vi.fn().mockResolvedValue(false),
}))
vi.mock('../../contexts', () => ({
  useNotification: () => notify,
  useMobile: () => ({ isMobile: false }),
}))
vi.mock('../../hooks', async () => {
  const persisted = await vi.importActual('../../hooks/usePersistedState')
  return {
    usePersistedState: persisted.usePersistedState,
    usePermission: () => ({
      canWrite: () => true, canDelete: () => true, hasPermission: () => true, canRead: () => true,
    }),
    useClipboard: () => ({ copy: vi.fn(), isCopied: () => false }),
  }
})
vi.mock('../../lib/policyAlgorithms', () => ({
  useFipsMode: () => false,
  useKeyPlatform: () => ({ fips: false, fipsKeys: null }),
}))

const getProviders = vi.fn()
const syncKeys = vi.fn()
vi.mock('../../services', () => ({
  hsmService: {
    getProviders: (...a) => getProviders(...a),
    getStatus: vi.fn().mockResolvedValue({ data: null }),
    getKeys: vi.fn().mockResolvedValue({ data: [] }),
    syncKeys: (...a) => syncKeys(...a),
  },
}))

import HSMPage, { syncKeysMessage } from '../HSMPage'

const PROVIDER = { id: 5, name: 'Token', provider_type: 'pkcs11', enabled: true, key_count: 2 }

async function openProvider() {
  render(<MemoryRouter><HSMPage /></MemoryRouter>)
  fireEvent.click(await screen.findByText('Token'))
  return screen.findByRole('button', { name: /common\.syncKeys/ })
}

describe('HSM key synchronization', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getProviders.mockResolvedValue({ data: [PROVIDER] })
  })

  it('disables the button while the call runs, so a second click sends nothing', async () => {
    let finish
    syncKeys.mockReturnValue(new Promise(resolve => { finish = resolve }))
    const button = await openProvider()
    fireEvent.click(button)
    const busy = await screen.findByRole('button', { name: /hsm\.syncingKeys/ })
    expect(busy.disabled).toBe(true)
    fireEvent.click(busy)
    expect(syncKeys).toHaveBeenCalledTimes(1)

    await act(async () => { finish({ data: { added: 1, removed: 0, unchanged: 1 } }) })
    await waitFor(() => expect(screen.getByRole('button', { name: /common\.syncKeys/ }).disabled).toBe(false))
    expect(notify.showSuccess).toHaveBeenCalledTimes(1)
  })

  it('frees the button after a refusal and shows the server message', async () => {
    syncKeys.mockRejectedValue(new Error('HSM synchronization error'))
    fireEvent.click(await openProvider())
    await waitFor(() => expect(notify.showError).toHaveBeenCalledWith('HSM synchronization error'))
    expect(screen.getByRole('button', { name: /common\.syncKeys/ }).disabled).toBe(false)
  })
})

describe('syncKeysMessage', () => {
  const t = (key, opts) => `${key} ${JSON.stringify(opts)}`

  it('is the plain counts when nothing was kept or changed', () => {
    const m = syncKeysMessage(t, { added: 2, removed: 1, unchanged: 3, missing_kept: 0, listing_errors: 0,
      changed_referenced_key_ids: [] })
    expect(m.notable).toBe(false)
    expect(m.text).toBe('messages.success.hsm.keysSynced {"added":2,"removed":1,"unchanged":3}')
  })

  it('says which keys an authority kept', () => {
    const m = syncKeysMessage(t, { added: 0, removed: 0, unchanged: 1, missing_kept: 2, listing_errors: 0 })
    expect(m.notable).toBe(true)
    expect(m.text).toContain('messages.success.hsm.keysSyncedKept {"count":2}')
  })

  it('gives both counts when the token listing failed', () => {
    const m = syncKeysMessage(t, { added: 0, removed: 0, unchanged: 1, missing_kept: 3, listing_errors: 1 })
    expect(m.notable).toBe(true)
    expect(m.text).toContain('messages.success.hsm.keysSyncedUnreadable {"count":1}')
    // Without a full listing every missing key is kept, not only those an authority holds
    expect(m.text).toContain('messages.success.hsm.keysSyncedMissingKept {"count":3}')
    expect(m.text).not.toContain('keysSyncedKept ')
  })

  it('names no kept key when the listing failed but nothing is missing', () => {
    const m = syncKeysMessage(t, { added: 0, removed: 0, unchanged: 1, missing_kept: 0, listing_errors: 2 })
    expect(m.text).not.toContain('Kept')
  })

  it('reports the authority keys whose material changed', () => {
    const m = syncKeysMessage(t, { added: 0, removed: 0, unchanged: 1, changed_referenced_key_ids: [4, 9] })
    expect(m.text).toContain('messages.success.hsm.keysSyncedChanged {"count":2}')
  })
})
