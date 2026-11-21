/**
 * The connector list: health, the domain SID read, and a deletion refused with the profiles that use it.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'

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

  it('offers no writing to a user who cannot write connectors', async () => {
    render(<AdConnectorSection hasPermission={() => false} />)
    await screen.findByText('forest-a')
    expect(screen.queryByText('adConnector.add')).not.toBeInTheDocument()
  })
})
