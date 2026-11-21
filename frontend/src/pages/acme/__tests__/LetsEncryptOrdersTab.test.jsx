/**
 * Orders of the ACME client as the mockup's module list: state chips, the renewal failures on the
 * row, the order's dock with the actions its state allows, the automatic renewal, a partial list.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, vars) => (vars?.total !== undefined ? `${key} ${JSON.stringify(vars)}` : key), i18n: { language: 'en' } }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../contexts', () => ({ useNotification: () => ({ showSuccess: vi.fn() }), useMobile: () => ({ isMobile: false }) }))
vi.mock('../../../stores/timezoneStore', () => ({ getAppTimezone: () => 'UTC' }))

import LetsEncryptOrdersTab from '../LetsEncryptOrdersTab'
import { WithDockSlot } from '../../protocols/__tests__/withDockSlot'

const orders = [
  { id: 1, primary_domain: 'a.example.com', status: 'valid', environment: 'production' },
  { id: 2, primary_domain: 'b.example.com', status: 'pending', environment: 'production' },
]
const noop = vi.fn()
const renderTab = (props = {}) => render(
  <WithDockSlot>
    <LetsEncryptOrdersTab clientOrders={orders} selectedClientOrder={null} onSelectOrder={noop} onRefresh={noop} {...props} />
  </WithDockSlot>,
)
const dock = () => screen.getByRole('complementary')

describe('LetsEncryptOrdersTab', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lists the orders with chips by state and a range', () => {
    renderTab()
    expect(screen.getByRole('button', { name: 'a.example.com' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'b.example.com' })).toBeInTheDocument()
    expect(document.querySelector('footer.table-footer')).toHaveTextContent('acme.clientOrdersRange')
  })

  it('filters orders by state', () => {
    renderTab()
    fireEvent.click(within(screen.getByRole('group', { name: 'acme.filterByState' })).getByRole('button', { name: /valid/i }))
    expect(screen.getByRole('button', { name: 'a.example.com' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'b.example.com' })).not.toBeInTheDocument()
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
    renderTab({ clientOrders: [order], selectedClientOrder: order, onRenewCertificate: noop, canWrite: true })
    expect(within(dock()).queryAllByRole('button', { name: 'acme.renewNow' })).toHaveLength(count)
  })

  it('shows failed renewals on the row with the last error in the tooltip', () => {
    const order = { id: 1, primary_domain: 'a.example.com', status: 'issued', environment: 'production', renewal_failures: 2, error_message: 'CA unreachable' }
    renderTab({ clientOrders: [order] })
    expect(screen.getByText('acme.renewalFailures')).toHaveAttribute('title', 'CA unreachable')
  })

  it('says when renewal is down to once a day', () => {
    const order = { id: 1, primary_domain: 'a.example.com', status: 'issued', environment: 'production', renewal_failures: 5, renewal_retry_daily: true }
    renderTab({ clientOrders: [order], selectedClientOrder: order })
    expect(within(dock()).getByText('acme.renewalRetryDaily')).toBeInTheDocument()
  })

  it('shows no failure on an order that has not failed', () => {
    renderTab()
    expect(screen.queryByText('acme.renewalFailures')).not.toBeInTheDocument()
  })

  it("turns an order's automatic renewal off", () => {
    const onToggleRenewal = vi.fn()
    const order = { id: 1, primary_domain: 'a.example.com', status: 'issued', environment: 'production', renewal_enabled: true }
    renderTab({ clientOrders: [order], selectedClientOrder: order, onToggleRenewal, canWrite: true })
    const toggle = within(dock()).getByRole('checkbox', { name: 'acme.orderAutoRenew' })
    expect(toggle).toBeChecked()
    fireEvent.click(toggle)
    expect(onToggleRenewal).toHaveBeenCalledWith(order, false)
  })

  it('keeps the switch read-only without write permission', () => {
    const order = { id: 1, primary_domain: 'a.example.com', status: 'issued', environment: 'production', renewal_enabled: false }
    renderTab({ clientOrders: [order], selectedClientOrder: order, onToggleRenewal: vi.fn() })
    expect(within(dock()).getByRole('checkbox')).toBeDisabled()
    expect(within(dock()).getByRole('checkbox')).not.toBeChecked()
  })

  it.each([[{ opened_by_renewal: true }], [{ is_proxy_order: true }]])('offers no switch on %j', (fields) => {
    const order = { id: 1, primary_domain: 'a.example.com', status: 'issued', environment: 'production', ...fields }
    renderTab({ clientOrders: [order], selectedClientOrder: order, onToggleRenewal: vi.fn(), canWrite: true })
    expect(within(dock()).queryByRole('checkbox')).not.toBeInTheDocument()
  })

  it('refreshes from the toolbar', () => {
    const onRefresh = vi.fn()
    renderTab({ onRefresh })
    fireEvent.click(screen.getByRole('button', { name: 'common.refresh' }))
    expect(onRefresh).toHaveBeenCalledOnce()
  })

  it('says when the list is partial', () => {
    renderTab({ partial: { loaded: 2, total: 300 } })
    expect(screen.getByRole('status')).toHaveTextContent('acme.ordersListPartial {"loaded":2,"total":300}')
  })

  it('shows no notice for a complete list', () => {
    renderTab()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
