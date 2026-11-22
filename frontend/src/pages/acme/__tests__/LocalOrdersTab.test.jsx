import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  delete: vi.fn(),
  post: vi.fn(),
  showConfirm: vi.fn(),
  showSuccess: vi.fn(),
  showError: vi.fn(),
  canWrite: vi.fn(),
  canDelete: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, values) => values?.domain ? `${key}:${values.domain}` : key,
    i18n: { language: 'en' },
  }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../../services', () => ({
  apiClient: {
    get: mocks.get,
    delete: mocks.delete,
    post: mocks.post,
  },
}))

vi.mock('../../../services/apiClient', () => ({
  buildQueryString: (params) => {
    const query = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined) query.set(key, String(value))
    })
    return `?${query.toString()}`
  },
}))

vi.mock('../../../contexts', () => ({
  useMobile: () => ({ isMobile: false }),
  useNotification: () => ({
    showConfirm: mocks.showConfirm,
    showSuccess: mocks.showSuccess,
    showError: mocks.showError,
  }),
}))

vi.mock('../../../hooks', async () => ({
  usePersistedState: (await vi.importActual('../../../hooks/usePersistedState')).usePersistedState,
  useClipboard: () => ({ copy: vi.fn() }),
  usePermission: () => ({
    canWrite: mocks.canWrite,
    canDelete: mocks.canDelete,
  }),
}))
vi.mock('../../../stores/timezoneStore', () => ({ getAppTimezone: () => 'UTC' }))

import { MemoryRouter } from 'react-router-dom'
import LocalOrdersTab from '../LocalOrdersTab'
import { WithDockSlot } from '../../protocols/__tests__/withDockSlot'

const order = {
  id: 7,
  domain: 'example.com',
  account: 'acct',
  status: 'Pending',
  method: 'DNS-01',
  expires: '2026-09-01',
  created_at: '2026-08-31T00:00:00Z',
}

const response = (items, page, total) => ({
  data: { items, meta: { page, per_page: 50, total } },
})

describe('LocalOrdersTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.canWrite.mockReturnValue(true)
    mocks.canDelete.mockReturnValue(true)
    mocks.showConfirm.mockResolvedValue(true)
    mocks.delete.mockResolvedValue({})
    mocks.post.mockResolvedValue({ data: { orders: 1 } })
    mocks.get.mockResolvedValue(response([order], 1, 1))
  })

  it('hides purge without delete:acme even when write:acme is granted', async () => {
    mocks.canDelete.mockReturnValue(false)
    render(<WithDockSlot><LocalOrdersTab /></WithDockSlot>)
    await screen.findAllByText('example.com')
    expect(screen.queryByText('acme.purgeLocalOrders')).not.toBeInTheDocument()
  })

  it('passes translated scope and danger options to delete confirmation', async () => {
    render(<WithDockSlot><LocalOrdersTab /></WithDockSlot>)
    await screen.findAllByText('example.com')
    fireEvent.click(screen.getByTitle('common.delete'))

    await waitFor(() => expect(mocks.showConfirm).toHaveBeenCalledWith(
      'acme.deleteLocalOrderConfirmDesc:example.com',
      {
        title: 'acme.deleteLocalOrderConfirm',
        confirmText: 'common.delete',
        cancelText: 'common.cancel',
        variant: 'danger',
      }
    ))
  })

  it('passes translated scope and danger options to purge confirmation', async () => {
    render(<WithDockSlot><LocalOrdersTab /></WithDockSlot>)
    await screen.findAllByText('example.com')
    fireEvent.click(screen.getByText('acme.purgeLocalOrders'))

    await waitFor(() => expect(mocks.showConfirm).toHaveBeenCalledWith(
      'acme.purgeLocalOrdersConfirmDesc',
      {
        title: 'acme.purgeLocalOrdersConfirm',
        confirmText: 'acme.purgeLocalOrders',
        cancelText: 'common.cancel',
        variant: 'danger',
      }
    ))
  })

  it('returns to the last valid page after deleting its final row', async () => {
    mocks.get
      .mockResolvedValueOnce(response([order], 1, 51))
      .mockResolvedValueOnce(response([order], 2, 51))
      .mockResolvedValueOnce(response([], 2, 50))
      .mockResolvedValueOnce(response([order], 1, 50))

    render(<WithDockSlot><LocalOrdersTab /></WithDockSlot>)
    await screen.findByText('1 / 2')
    fireEvent.click(screen.getByRole('button', { name: 'table.nextPage' }))
    await screen.findByText('2 / 2')
    fireEvent.click(screen.getByTitle('common.delete'))

    await waitFor(() => {
      const urls = mocks.get.mock.calls.map(([url]) => url)
      expect(urls.filter((url) => url.includes('page=1')).length).toBeGreaterThan(1)
    })
  })
})

describe('LocalOrdersTab in the URL', () => {
  it('reopens the order of the URL, read by id when the page does not hold it', async () => {
    mocks.get.mockImplementation(async (url) => (url.startsWith('/acme/orders?') ? response([], 1, 80) : { data: { ...order, id: 99, domain: 'far.example.com' } }))
    render(<MemoryRouter initialEntries={['/acme?tab=localorders&item=99']}><WithDockSlot><LocalOrdersTab /></WithDockSlot></MemoryRouter>)
    expect(await screen.findByRole('heading', { level: 2, name: 'far.example.com' })).toBeInTheDocument()
    expect(mocks.get).toHaveBeenCalledWith('/acme/orders/99')
  })
})

describe('LocalOrdersTab dock', () => {
  it('shows the order id in a chip that copies it whole', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true })
    mocks.get.mockResolvedValue(response([{ ...order, order_id: 'ord-0123456789' }], 1, 1))
    render(<MemoryRouter initialEntries={['/acme?tab=localorders&item=7']}><WithDockSlot><LocalOrdersTab /></WithDockSlot></MemoryRouter>)
    await screen.findByRole('heading', { level: 2, name: 'example.com' })
    const id = [...document.querySelectorAll('dl.kv > div.row')].find((r) => r.querySelector('dt').textContent === 'acme.orderId')
    fireEvent.click(id.querySelector('dd.v').querySelector('.code-value .cp'))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('ord-0123456789'))
  })
})
