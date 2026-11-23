/**
 * The certificate active in the Certificates zone's dock and its section live in the URL (`item`,
 * `section`), with every open certificate (`open`) once there are several: a reload or a shared link
 * reopens them, Back closes the dock, the deep link /certificates/:id becomes the dock's item. The
 * tab titles travel with the open certificates. Real page, real inspector.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useLocation, useNavigate } from 'react-router-dom'

const stable = vi.hoisted(() => ({
  i18n: { t: (key) => key, i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} } },
  notify: {
    showSuccess: () => {}, showError: () => {}, showInfo: () => {}, showWarning: () => {},
    showConfirm: () => Promise.resolve(false), showPrompt: () => Promise.resolve(''),
  },
}))
const mocks = vi.hoisted(() => ({ getAll: vi.fn(), getById: vi.fn() }))

vi.mock('react-i18next', () => ({
  useTranslation: () => stable.i18n,
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../contexts/AuthContext', () => ({ useAuth: () => ({ isAuthenticated: true, permissions: ['*'] }) }))
vi.mock('../../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: false }) }))
vi.mock('../../../contexts', async () => {
  const inspector = await vi.importActual('../../../contexts/InspectorContext')
  return {
    useNotification: () => stable.notify,
    useMobile: () => ({ isMobile: false, isTablet: false }),
    useInspector: inspector.useInspector,
    InspectorProvider: inspector.InspectorProvider,
  }
})
vi.mock('../../../hooks', async () => {
  const actual = await vi.importActual('../../../hooks/usePersistedState')
  return {
    usePersistedState: actual.usePersistedState,
    usePermission: () => ({ canWrite: () => true, canDelete: () => true, hasPermission: () => true, canRead: () => true }),
    useRecentHistory: () => ({ addToHistory: vi.fn(), history: [] }),
    useFavorites: () => ({ favorites: [], toggleFavorite: vi.fn(), isFavorite: () => false }),
    useWebSocket: () => ({ muteToasts: vi.fn(), subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  }
})
vi.mock('../../../services', () => ({
  certificatesService: {
    getAll: (...a) => mocks.getAll(...a), getById: (...a) => mocks.getById(...a),
    getStats: vi.fn().mockResolvedValue({ data: { valid: 2, total: 2 } }),
  },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  auditService: { getLogs: vi.fn().mockResolvedValue({ data: [] }) },
  acmeService: {}, truststoreService: { addFromCA: vi.fn() },
}))
vi.mock('../../../services/account.service', () => ({ accountService: { updatePreferences: vi.fn() } }))
vi.mock('../../../components/deploy/CertDeploySection', () => ({ CertDeploySection: () => null }))

import { InspectorProvider } from '../../../contexts/InspectorContext'
import CertificatesPage from '../../CertificatesPage'

const cert = (id, cn) => ({ id, common_name: cn, cn, status: 'valid', valid_to: '2030-01-01T00:00:00Z', source: 'manual' })
const CERTS = [cert(7, 'web.example.com'), cert(8, 'mail.example.com')]

let nav
let where
function Where() { const l = useLocation(); nav = useNavigate(); where = l.pathname + l.search; return null }
const at = (url) => render(
  <MemoryRouter initialEntries={['/elsewhere', url]} initialIndex={1}>
    <InspectorProvider>
      <Routes>
        <Route path="/elsewhere" element={<p>elsewhere</p>} />
        <Route path="/certificates" element={<CertificatesPage />} />
        <Route path="/certificates/:id" element={<CertificatesPage />} />
      </Routes>
      <Where />
    </InspectorProvider>
  </MemoryRouter>,
)
const dock = () => document.getElementById('inspector')
// Every open tab, shown or under « +N », by its key (the certificate id), with its title
const tabTitles = () => {
  const out = {}
  for (const el of dock()?.querySelectorAll('[data-active]') || []) out[el.dataset.active] = el.getAttribute('title')
  return out
}

beforeEach(() => {
  window.localStorage.clear()
  mocks.getAll.mockResolvedValue({ data: CERTS, meta: { total: 2 } })
  mocks.getById.mockImplementation((id) => Promise.resolve({ data: CERTS.find((c) => c.id === id) || cert(id, `cert-${id}`) }))
})

describe('the certificate dock in the URL', () => {
  it('reopens the certificate and section a link names (a reload)', async () => {
    at('/certificates?item=8&section=chain')
    await waitFor(() => expect(dock()).not.toBeNull())
    expect(await within(dock()).findByRole('heading', { name: 'mail.example.com' })).toBeInTheDocument()
    expect(within(dock()).getByRole('tab', { name: 'inspector.sections.chain' })).toHaveAttribute('aria-selected', 'true')
    expect(mocks.getById).toHaveBeenCalledWith(8)
  })

  it('writes the certificate opened and its section, and Back closes the dock', async () => {
    at('/certificates')
    fireEvent.click(await screen.findByRole('button', { name: 'web.example.com' }))
    await waitFor(() => expect(where).toBe('/certificates?item=7'))
    await waitFor(() => expect(dock()).not.toBeNull())
    fireEvent.click(await within(dock()).findByRole('tab', { name: 'inspector.sections.extensions' }))
    expect(where).toBe('/certificates?item=7&section=extensions')
    act(() => nav(-1))
    await waitFor(() => expect(where).toBe('/certificates'))
    await waitFor(() => expect(dock()).toBeNull())
  })

  it('turns the deep link /certificates/:id into the dock\'s item', async () => {
    at('/certificates/8')
    await waitFor(() => expect(where).toBe('/certificates?item=8'))
    expect(await within(dock()).findByRole('heading', { name: 'mail.example.com' })).toBeInTheDocument()
  })

  it('opens the certificate of a former ?id= link', async () => {
    at('/certificates?id=8')
    await waitFor(() => expect(dock()).not.toBeNull())
    expect(await within(dock()).findByRole('heading', { name: 'mail.example.com' })).toBeInTheDocument()
  })

  it('a second certificate replaces the first in the URL, and closing drops it', async () => {
    at('/certificates?item=7')
    await waitFor(() => expect(dock()).not.toBeNull())
    fireEvent.click(await screen.findByRole('button', { name: 'mail.example.com' }))
    await waitFor(() => expect(where).toBe('/certificates?item=8&open=7%2C8'))
    fireEvent.click(dock().querySelector('[data-action="close-dock"]'))
    await waitFor(() => expect(where).toBe('/certificates'))
  })
})

describe('several open certificates (the mockup\'s open=…&active=…)', () => {
  it('writes every open certificate in the URL, the active one as item', async () => {
    at('/certificates')
    fireEvent.click(await screen.findByRole('button', { name: 'web.example.com' }))
    await waitFor(() => expect(where).toBe('/certificates?item=7'))
    fireEvent.click(await screen.findByRole('button', { name: 'mail.example.com' }))
    await waitFor(() => expect(where).toBe('/certificates?item=8&open=7%2C8'))
    // Back to the first tab: the list stays, the item follows
    fireEvent.click(dock().querySelector('.open-tab [data-active="7"], .tabs-menu-open[data-active="7"]'))
    await waitFor(() => expect(where).toBe('/certificates?item=7&open=7%2C8'))
  })

  it('reopens every certificate the URL lists on a reload, the item active, each tab named', async () => {
    at('/certificates?item=8&open=7,8,9')
    await waitFor(() => expect(dock()).not.toBeNull())
    expect(await within(dock()).findByRole('heading', { name: 'mail.example.com' })).toBeInTheDocument()
    await waitFor(() => expect(tabTitles()).toEqual({ 7: 'web.example.com', 8: 'mail.example.com', 9: 'cert-9' }))
    // The URL already says it all: nothing rewritten
    expect(where).toBe('/certificates?item=8&open=7,8,9')
  })

  it('closing a tab rewrites the list, and the last one left goes back to item alone', async () => {
    at('/certificates?item=8&open=7,8')
    await waitFor(() => expect(Object.keys(tabTitles())).toEqual(['7', '8']))
    fireEvent.click(dock().querySelector('[data-close-tab="7"]'))
    await waitFor(() => expect(where).toBe('/certificates?item=8'))
    expect(Object.keys(tabTitles())).toEqual(['8'])
  })
})

describe('the open tabs keep their titles (the entry carries them)', () => {
  it('after a visit to another page, and after Back', async () => {
    at('/certificates')
    fireEvent.click(await screen.findByRole('button', { name: 'web.example.com' }))
    expect(await within(dock()).findByRole('heading', { name: 'web.example.com' })).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: 'mail.example.com' }))
    await waitFor(() => expect(tabTitles()).toEqual({ 7: 'web.example.com', 8: 'mail.example.com' }))
    act(() => nav('/elsewhere'))
    await screen.findByText('elsewhere')
    expect(dock()).toBeNull()
    act(() => nav(-1))
    await waitFor(() => expect(dock()).not.toBeNull())
    expect(tabTitles()).toEqual({ 7: 'web.example.com', 8: 'mail.example.com' })
  })
})
