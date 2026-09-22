import { describe, it, expect, vi } from 'vitest'
import { render, waitFor } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../components', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: () => <input />,
  Select: ({ options = [] }) => (
    <select>{options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
  ),
  Badge: ({ children }) => <span>{children}</span>,
  DetailHeader: ({ title }) => <header>{title}</header>,
  DetailSection: ({ children }) => <section>{children}</section>,
  DetailGrid: ({ children }) => <div>{children}</div>,
  DetailContent: ({ children }) => <div>{children}</div>,
}))
vi.mock('../../../components/ui/ToggleSwitch', () => ({ ToggleSwitch: () => <input type="checkbox" /> }))
vi.mock('../../../contexts', () => ({ useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn() }) }))
vi.mock('../ServiceStatusWidget', () => ({ default: () => null }))
vi.mock('../PublicEndpointsPanel', () => ({ default: () => null }))

const getAll = vi.fn()
vi.mock('../../../services', () => ({
  certificatesService: { getAll: (...a) => getAll(...a) },
  settingsService: { updateBulk: vi.fn() },
}))

import GeneralSection from '../GeneralSection'

describe('ACME public vhost TLS certificate selector (#365)', () => {
  it('names a certificate by its CN with the description alongside', async () => {
    getAll.mockResolvedValue({ data: [
      { id: 7, refid: 'r7', common_name: 'acme.example.com', descr: 'Renamed', has_private_key: true },
    ] })
    render(
      <GeneralSection settings={{}} updateSetting={vi.fn()} handleSave={vi.fn()} saving={false}
        canWrite={() => true} hasPermission={() => true} />
    )
    await waitFor(() => {
      const labels = Array.from(document.querySelectorAll('option')).map((o) => o.textContent)
      expect(labels).toContain('acme.example.com · Renamed (#7)')
    })
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
    await waitFor(() => {
      const labels = Array.from(document.querySelectorAll('option')).map((o) => o.textContent)
      expect(labels).toContain('last.example.com (#101)')
    })
  })
})
