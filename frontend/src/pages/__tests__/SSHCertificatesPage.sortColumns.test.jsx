/**
 * SSHCertificatesPage: the columns the server sorts offer a sort, the nearest expiry first by default,
 * the sort kept in the address; a phone record says its dates.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { renderAtUrl } from '../../test/dockUrl'
import { sortKeys, sortedHeaders, absorbing, recordFacts } from '../../test/listColumns'

// Stable across renders: t and showError are loader dependencies, a fresh one reloads in a loop
const stable = vi.hoisted(() => ({
  mobile: false,
  i18n: {
    t: (key, opts) => (opts?.keyId ? `${key}:${opts.keyId}` : key),
    i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} },
  },
  notify: {
    showSuccess: () => {}, showError: () => {}, showInfo: () => {}, showWarning: () => {},
    showConfirm: () => Promise.resolve(false),
  },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => stable.i18n,
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => stable.notify,
  useMobile: () => ({ isMobile: stable.mobile, isTablet: false, isDesktop: !stable.mobile, sidebarOpen: true, setSidebarOpen: vi.fn() }),
}))
vi.mock('../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: stable.mobile }) }))

vi.mock('../../hooks', async () => {
  const actual = await vi.importActual('../../hooks')
  return {
    ...actual,
    usePermission: () => ({
      canWrite: () => true, canDelete: () => true, hasPermission: () => true, canRead: () => true,
    }),
    useWebSocket: () => ({ muteToasts: vi.fn(), subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  }
})

const getAll = vi.fn()
const getStats = vi.fn()
const generate = vi.fn()
const casGetAll = vi.fn()
vi.mock('../../services', () => ({
  sshCertificatesService: {
    getAll: (...a) => getAll(...a),
    getStats: (...a) => getStats(...a),
    generate: (...a) => generate(...a),
    getById: vi.fn(),
    sign: vi.fn(),
    importCertificate: vi.fn(),
  },
  sshCasService: { getAll: (...a) => casGetAll(...a) },
}))


import SSHCertificatesPage from '../SSHCertificatesPage'

const lastParams = () => getAll.mock.calls.at(-1)[0]

describe('SSHCertificatesPage: sortable columns', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.clearAllMocks()
    stable.mobile = false
    getAll.mockResolvedValue({ data: [{ id: 1, key_id: 'c', cert_type: 'user', principals: ['a'], ca_name: 'CA',
      valid_to: '2030-01-01T00:00:00Z' }], meta: { total: 1 } })
    getStats.mockResolvedValue({ data: {} })
    casGetAll.mockResolvedValue({ data: [] })
  })

  it('opens on the nearest expiry; every column the server sorts offers it, the principals do not', async () => {
    const { container } = render(<MemoryRouter><SSHCertificatesPage /></MemoryRouter>)
    await screen.findByText('c')
    expect(lastParams()).toMatchObject({ sort_by: 'valid_to', sort_order: 'asc', page: 1 })
    expect(sortedHeaders(container)).toEqual([['certificates.expiry', 'ascending']])
    expect(sortKeys(container)).toEqual(['key_id', 'cert_type', 'valid_to', 'ca', 'status'])
    expect(absorbing(container)).toEqual(['sshCertificates.principals'])
  })

  it('keeps every principal in the cell and its title, an ellipsis shortening it', async () => {
    getAll.mockResolvedValue({ data: [{ id: 1, key_id: 'c', cert_type: 'user', principals: ['alice', 'bob', 'carol', 'deploy'], ca_name: 'CA',
      valid_to: '2030-01-01T00:00:00Z' }], meta: { total: 1 } })
    render(<MemoryRouter><SSHCertificatesPage /></MemoryRouter>)
    const cell = await screen.findByText('alice, bob, carol, deploy')
    expect(cell.closest('td')).toHaveAttribute('title', 'alice, bob, carol, deploy')
  })

  it('sorts by the authority and the state on the server, back to page one, kept in the address', async () => {
    getAll.mockResolvedValue({ data: [{ id: 1, key_id: 'c', cert_type: 'user', principals: ['a'], ca_name: 'CA', valid_to: '2030-01-01T00:00:00Z' }], meta: { total: 60 } })
    const at = renderAtUrl(<SSHCertificatesPage />, '/ssh/certificates')
    await screen.findByText('c')
    fireEvent.click(screen.getByRole('button', { name: 'table.nextPage' }))
    await waitFor(() => expect(lastParams()).toMatchObject({ page: 2 }))
    fireEvent.click(at.container.querySelector('[data-sort="ca"]'))
    await waitFor(() => expect(lastParams()).toMatchObject({ sort_by: 'ca', sort_order: 'asc', page: 1 }))
    expect(at.where()).toBe('/ssh/certificates?sort=ca&order=asc')
    fireEvent.click(at.container.querySelector('[data-sort="status"]'))
    await waitFor(() => expect(lastParams()).toMatchObject({ sort_by: 'status', sort_order: 'asc' }))
    at.unmount()
    renderAtUrl(<SSHCertificatesPage />, '/ssh/certificates?sort=key_id&order=desc')
    await screen.findByText('c')
    expect(lastParams()).toMatchObject({ sort_by: 'key_id', sort_order: 'desc' })
  })

  it('draws a phone record by priority: the expiry after its label', async () => {
    stable.mobile = true
    render(<MemoryRouter><SSHCertificatesPage /></MemoryRouter>)
    await screen.findByText('c')
    const record = document.querySelector('article.mobile-record')
    expect(recordFacts(record)[0]).toMatch(/^certificates\.expiry \S/)
  })
})
