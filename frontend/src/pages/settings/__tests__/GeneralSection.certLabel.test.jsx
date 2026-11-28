import { describe, it, expect, vi } from 'vitest'
import { render, waitFor, fireEvent } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../components', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: () => <input />,
  Select: ({ options = [], onFocus, id }) => (
    <select id={id} onFocus={onFocus}>{options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
  ),
  Badge: ({ children }) => <span>{children}</span>,
  DetailHeader: ({ title }) => <header>{title}</header>,
  DetailSection: ({ children }) => <section>{children}</section>,
  DetailGrid: ({ children }) => <div>{children}</div>,
  DetailContent: ({ children }) => <div>{children}</div>,
}))
vi.mock('../../../contexts', () => ({ useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn() }) }))
vi.mock('../ServiceStatusWidget', () => ({ default: () => null }))
vi.mock('../PublicEndpointsPanel', () => ({ default: () => null }))

const getAll = vi.fn()
const getById = vi.fn()
vi.mock('../../../services', () => ({
  certificatesService: { getAll: (...a) => getAll(...a), getById: (...a) => getById(...a) },
  settingsService: { updateBulk: vi.fn() },
}))

import GeneralSection from '../GeneralSection'

const openSelector = () => fireEvent.focus(document.getElementById('set-acme_public_tls_cert_id'))

describe('ACME public vhost TLS certificate selector (#365)', () => {
  it('names a certificate by its CN with the description alongside', async () => {
    getAll.mockResolvedValue({ data: [
      { id: 7, refid: 'r7', common_name: 'acme.example.com', descr: 'Renamed', has_private_key: true },
    ] })
    render(
      <GeneralSection settings={{}} updateSetting={vi.fn()} handleSave={vi.fn()} saving={false}
        canWrite={() => true} hasPermission={() => true} />
    )
    openSelector()
    await waitFor(() => {
      const labels = Array.from(document.querySelectorAll('option')).map((o) => o.textContent)
      expect(labels).toContain('acme.example.com · Renamed (#7)')
    })
  })

  it('asks the server for certificates holding a private key', async () => {
    getAll.mockReset()
    getAll.mockResolvedValue({ data: [] })
    render(
      <GeneralSection settings={{}} updateSetting={vi.fn()} handleSave={vi.fn()} saving={false}
        canWrite={() => true} hasPermission={() => true} />
    )
    openSelector()
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    expect(getAll.mock.calls[0][0].has_private_key).toBe(true)
  })

  it('offers certificates beyond the first page', async () => {
    const page1 = Array.from({ length: 100 }, (_, i) => ({ id: i + 1, common_name: `c${i + 1}.example.com`, has_private_key: true }))
    getAll.mockImplementation(({ page }) => Promise.resolve(page === 1
      ? { data: page1, meta: { total: 101 } }
      : { data: [{ id: 101, common_name: 'last.example.com', has_private_key: true }], meta: { total: 101 } }))
    render(
      <GeneralSection settings={{}} updateSetting={vi.fn()} handleSave={vi.fn()} saving={false}
        canWrite={() => true} hasPermission={() => true} />
    )
    openSelector()
    await waitFor(() => {
      const labels = Array.from(document.querySelectorAll('option')).map((o) => o.textContent)
      expect(labels).toContain('last.example.com (#101)')
    })
  })

  it('lists no certificates until the selector is used, then once', async () => {
    getAll.mockReset()
    getAll.mockResolvedValue({ data: [] })
    render(
      <GeneralSection settings={{}} updateSetting={vi.fn()} handleSave={vi.fn()} saving={false}
        canWrite={() => true} hasPermission={() => true} />
    )
    await new Promise((r) => setTimeout(r, 20))
    expect(getAll).not.toHaveBeenCalled()
    openSelector()
    openSelector()
    await waitFor(() => expect(getAll).toHaveBeenCalledTimes(1))
  })

  it('names the saved certificate with one read and no listing', async () => {
    getAll.mockReset()
    getById.mockReset()
    getById.mockResolvedValue({ data: { id: 9, common_name: 'saved.example.com', has_private_key: true } })
    render(
      <GeneralSection settings={{ acme_public_tls_cert_id: 9 }} updateSetting={vi.fn()} handleSave={vi.fn()} saving={false}
        canWrite={() => true} hasPermission={() => true} />
    )
    await waitFor(() => {
      const labels = Array.from(document.querySelectorAll('option')).map((o) => o.textContent)
      expect(labels).toContain('saved.example.com (#9)')
    })
    expect(getById).toHaveBeenCalledWith('9')
    expect(getAll).not.toHaveBeenCalled()
  })

  it('does not read again a saved certificate the opened list already holds', async () => {
    getAll.mockReset()
    getById.mockReset()
    getAll.mockResolvedValue({ data: [{ id: 5, common_name: 'listed.example.com', has_private_key: true }] })
    const props = { updateSetting: vi.fn(), handleSave: vi.fn(), saving: false, canWrite: () => true, hasPermission: () => true }
    const { rerender } = render(<GeneralSection settings={{}} {...props} />)
    openSelector()
    await waitFor(() => {
      const labels = Array.from(document.querySelectorAll('option')).map((o) => o.textContent)
      expect(labels).toContain('listed.example.com (#5)')
    })
    rerender(<GeneralSection settings={{ acme_public_tls_cert_id: 5 }} {...props} />)
    await new Promise((r) => setTimeout(r, 20))
    expect(getById).not.toHaveBeenCalled()
  })
})
