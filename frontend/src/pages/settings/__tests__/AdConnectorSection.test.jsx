/**
 * The connector list: health, the domain SID read, and a deletion refused with the profiles that use it.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render as rtlRender, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
// The lists keep their sort in the address
const render = (ui, options) => rtlRender(ui, { wrapper: MemoryRouter, ...options })

const mocks = vi.hoisted(() => ({
  t: (key, opts) => (opts ? `${key}|${Object.entries(opts).map(([k, v]) => `${k}=${v}`).join('|')}` : key),
  notify: { showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showConfirm: vi.fn() },
  list: vi.fn(),
  remove: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: mocks.t,
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../contexts', () => ({
  useNotification: () => mocks.notify,
  useMobile: () => ({
    isMobile: false, isTablet: false, isDesktop: true, isTouch: false, isLargeScreen: true,
    screenWidth: 1440, sidebarOpen: true, setSidebarOpen: vi.fn(),
  }),
}))
vi.mock('../../../services', () => ({
  adConnectorsService: { list: mocks.list, remove: mocks.remove, update: vi.fn(), create: vi.fn(), testSaved: vi.fn(), test: vi.fn() },
}))

import AdConnectorSection from '../AdConnectorSection'

const CONNECTORS = [
  {
    id: 1, name: 'forest-a', realm: 'A.EXAMPLE', domain_sid: 'S-1-5-21-1-2-3', servers: ['dc1.a.example'],
    port: 389, enabled: true, health: { state: 'down' }, health_fresh: true, last_test_at: null,
  },
  {
    id: 2, name: 'forest-b', realm: 'B.EXAMPLE', domain_sid: null, servers: ['dc1.b.example'],
    port: 389, enabled: true, health: { state: 'up' }, health_fresh: true, last_test_at: null,
  },
]

beforeEach(() => {
  mocks.list.mockReset().mockResolvedValue({ data: CONNECTORS })
  mocks.remove.mockReset()
  for (const m of Object.values(mocks.notify)) m.mockReset()
  mocks.notify.showConfirm.mockResolvedValue(true)
})

describe('AdConnectorSection', () => {
  it('shows each connector with its health and the domain SID that was read', async () => {
    render(<AdConnectorSection hasPermission={() => true} />)
    await screen.findByText('forest-a')
    expect(screen.getByText('S-1-5-21-1-2-3')).toBeInTheDocument()
    expect(screen.getByText('adConnector.domainSidUnknown')).toBeInTheDocument()
    expect(screen.getByText('adConnector.healthStateDown')).toBeInTheDocument()
    expect(screen.getByText('adConnector.healthStateUp')).toBeInTheDocument()
    // Its own region among the settings' lists
    expect(screen.getByText('forest-a').closest('.table-scroll')).toHaveAttribute('id', 'ad-connectors-scroll')
  })

  it('names the profiles that use a connector whose deletion is refused', async () => {
    const error = Object.assign(new Error('Cannot delete the connector: 2 Windows enrollment profile(s) use it.'), {
      status: 409, data: { details: { profiles: [{ id: 4, name: 'corp' }, { id: 5, name: 'branch' }] } },
    })
    mocks.remove.mockRejectedValue(error)
    render(<AdConnectorSection hasPermission={() => true} />)
    await screen.findByText('forest-a')
    fireEvent.click(screen.getAllByTitle('common.delete')[0])
    await waitFor(() => expect(mocks.remove).toHaveBeenCalledWith(1))
    const list = await screen.findByTestId('refusal-profiles')
    expect(within(list).getByText('corp')).toBeInTheDocument()
    expect(within(list).getByText('branch')).toBeInTheDocument()
    expect(mocks.notify.showError).not.toHaveBeenCalled()
  })

  it('counts every profile that uses the connector, not only the ones listed', async () => {
    const listed = Array.from({ length: 50 }, (_, i) => ({ id: i + 1, name: `p${i}` }))
    mocks.remove.mockRejectedValue(Object.assign(new Error('in use'), {
      status: 409, data: { details: { profiles: listed, total: 150 } },
    }))
    render(<AdConnectorSection hasPermission={() => true} />)
    await screen.findByText('forest-a')
    fireEvent.click(screen.getAllByTitle('common.delete')[0])
    await screen.findByTestId('refusal-profiles')
    expect(screen.getByText('adConnector.deleteRefused|count=150')).toBeInTheDocument()
    expect(screen.getByText('adConnector.deleteRefusedMore|count=100')).toBeInTheDocument()
  })

  it('says nothing more when every profile is listed', async () => {
    mocks.remove.mockRejectedValue(Object.assign(new Error('in use'), {
      status: 409, data: { details: { profiles: [{ id: 4, name: 'corp' }], total: 1 } },
    }))
    render(<AdConnectorSection hasPermission={() => true} />)
    await screen.findByText('forest-a')
    fireEvent.click(screen.getAllByTitle('common.delete')[0])
    await screen.findByTestId('refusal-profiles')
    expect(screen.queryByText(/deleteRefusedMore/)).not.toBeInTheDocument()
  })

  it('opens by name, sorts every data column from its header, the order in the address under its own scope', async () => {
    mocks.list.mockResolvedValue({ data: [{ ...CONNECTORS[1], last_test_at: '2026-11-20T10:00:00Z' }, CONNECTORS[0]] })
    const at = { search: '' }
    function Where() { at.search = useLocation().search; return null }
    render(<><AdConnectorSection hasPermission={() => true} /><Where /></>)
    await screen.findByText('forest-a')
    const names = () => [...document.querySelectorAll('tbody tr .entity-label')].map((n) => n.textContent)
    expect(screen.getByRole('columnheader', { name: 'atelier.name' })).toHaveAttribute('aria-sort', 'ascending')
    expect(names()).toEqual(['forest-a', 'forest-b'])
    const sortable = screen.getAllByRole('columnheader').filter((h) => h.querySelector('button[data-sort]')).map((h) => h.textContent)
    expect(sortable).toEqual(['atelier.name', 'adConnector.realm', 'adConnector.servers', 'adConnector.domainSid', 'adConnector.lastTest', 'atelier.state'])
    // A connector never tested sorts last whichever the direction
    fireEvent.click(screen.getByRole('button', { name: 'adConnector.lastTest' }))
    expect(names()).toEqual(['forest-b', 'forest-a'])
    fireEvent.click(screen.getByRole('button', { name: 'adConnector.lastTest' }))
    expect(names()).toEqual(['forest-b', 'forest-a'])
    fireEvent.click(screen.getByRole('button', { name: 'adConnector.realm' }))
    fireEvent.click(screen.getByRole('button', { name: 'adConnector.realm' }))
    expect(names()).toEqual(['forest-b', 'forest-a'])
    expect(at.search).toBe('?ad-sort=realm&ad-order=desc')
  })

  it('offers no writing to a user who cannot write connectors', async () => {
    render(<AdConnectorSection hasPermission={() => false} />)
    await screen.findByText('forest-a')
    expect(screen.queryByText('adConnector.add')).not.toBeInTheDocument()
  })
})
