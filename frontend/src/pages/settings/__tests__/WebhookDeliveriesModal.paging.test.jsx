/**
 * The deliveries of a webhook are paged: the modal reads the page meta and asks for the next page.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

// Stable across renders: t and the notifiers are loader dependencies
const stable = vi.hoisted(() => ({
  t: (key) => key,
  notify: { showSuccess: () => {}, showError: () => {} },
}))
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: stable.t }) }))
vi.mock('../../../contexts', () => ({ useNotification: () => stable.notify }))
vi.mock('../../../components', () => ({
  Modal: ({ open, children }) => (open ? <div>{children}</div> : null),
  Button: ({ children, ...p }) => <button {...p}>{children}</button>,
  Badge: ({ children }) => <span>{children}</span>,
}))
const getWebhookDeliveries = vi.fn()
vi.mock('../../../services', () => ({
  settingsService: {
    getWebhookDeliveries: (...a) => getWebhookDeliveries(...a),
    retryWebhookDelivery: vi.fn(),
  },
}))

import WebhookDeliveriesModal from '../WebhookDeliveriesModal'

const delivery = (id) => ({ id, event_type: `evt.${id}`, status: 'failed', attempts: 1, max_attempts: 5, created_at: null })
const TOTAL = 60

beforeEach(() => {
  getWebhookDeliveries.mockReset().mockImplementation(async (_id, { page = 1, perPage = 25 }) => {
    const first = (page - 1) * perPage + 1
    const last = Math.min(page * perPage, TOTAL)
    return {
      data: Array.from({ length: Math.max(0, last - first + 1) }, (_, i) => delivery(first + i)),
      meta: { total: TOTAL, page, per_page: perPage, total_pages: Math.ceil(TOTAL / perPage) },
    }
  })
})

describe('WebhookDeliveriesModal paging', () => {
  it('reaches deliveries beyond the first page', async () => {
    render(<WebhookDeliveriesModal webhook={{ id: 7, name: 'hook' }} onClose={vi.fn()} canRetry />)
    await screen.findByText('evt.1')
    expect(screen.queryByText('evt.26')).toBeNull()
    fireEvent.click(screen.getByLabelText('common.next'))
    await screen.findByText('evt.26')
    expect(getWebhookDeliveries.mock.calls.at(-1)[1]).toMatchObject({ page: 2 })
    fireEvent.click(screen.getByLabelText('common.next'))
    await screen.findByText('evt.51')
    expect(screen.getByLabelText('common.next')).toBeDisabled()
  })

  it('goes back to the first page when the status filter changes', async () => {
    render(<WebhookDeliveriesModal webhook={{ id: 7, name: 'hook' }} onClose={vi.fn()} />)
    await screen.findByText('evt.1')
    fireEvent.click(screen.getByLabelText('common.next'))
    await screen.findByText('evt.26')
    fireEvent.click(screen.getByText('webhooks.deliveries.status.failed'))
    await waitFor(() => expect(getWebhookDeliveries.mock.calls.at(-1)[1]).toMatchObject({ page: 1, status: 'failed' }))
  })
})
