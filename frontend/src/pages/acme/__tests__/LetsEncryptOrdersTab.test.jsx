import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../components', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Badge: ({ children }) => <span>{children}</span>,
  FilterSelect: ({ value, onChange, allLabel, options }) => (
    <select aria-label="status-filter" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{allLabel}</option>
      {options.map((option) => (
        <option key={option.value} value={option.value}>{option.label}</option>
      ))}
    </select>
  ),
}))

import LetsEncryptOrdersTab from '../LetsEncryptOrdersTab'

const orders = [
  { id: 1, primary_domain: 'a.example.com', status: 'valid', environment: 'production' },
  { id: 2, primary_domain: 'b.example.com', status: 'pending', environment: 'production' },
]

const noop = vi.fn()
const renderTab = (props = {}) => render(
  <LetsEncryptOrdersTab
    clientOrders={orders}
    selectedClientOrder={null}
    onSelectOrder={noop}
    onRefresh={noop}
    {...props}
  />
)

describe('LetsEncryptOrdersTab', () => {
  beforeEach(() => vi.clearAllMocks())

  it('is a dedicated orders view with a visible/total count', () => {
    renderTab()
    expect(screen.getByText('acme.letsEncryptOrders')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('a.example.com')).toBeInTheDocument()
    expect(screen.getByText('b.example.com')).toBeInTheDocument()
  })

  it('filters orders by status', () => {
    renderTab()
    fireEvent.change(screen.getByLabelText('status-filter'), { target: { value: 'valid' } })
    expect(screen.getByText('a.example.com')).toBeInTheDocument()
    expect(screen.queryByText('b.example.com')).not.toBeInTheDocument()
  })

  it.each([
    [{ status: 'issued' }, 1],
    [{ status: 'valid', certificate_id: 7 }, 1],
    [{ status: 'valid', error_message: 'refused' }, 1],
    // Still being imported: a second order here would replace a certificate about to arrive
    [{ status: 'valid' }, 0],
    [{ status: 'valid', certificate_id: 7, is_proxy_order: true }, 0],
    [{ status: 'pending' }, 0],
  ])('offers Renew on %j: %i', (fields, count) => {
    const order = { id: 1, primary_domain: 'a.example.com', environment: 'production', ...fields }
    renderTab({ clientOrders: [order], selectedClientOrder: order, onRenewCertificate: noop })
    expect(screen.queryAllByText('acme.renew')).toHaveLength(count)
  })

  it('refreshes from the dedicated view', () => {
    const onRefresh = vi.fn()
    renderTab({ onRefresh })
    fireEvent.click(screen.getByRole('button', { name: 'common.refresh' }))
    expect(onRefresh).toHaveBeenCalledOnce()
  })
})
