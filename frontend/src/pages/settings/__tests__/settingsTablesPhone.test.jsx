/**
 * On a phone the settings tables become cards: a card keeps the row actions, which the edit
 * form a record opens does not hold (deliveries, test, enable, delete).
 */
import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import WebhooksSection from '../WebhooksSection'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() } }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../contexts/MobileContext', () => ({
  useMobile: () => ({ isMobile: true, isTablet: false, isDesktop: false, isTouch: true, screenWidth: 390 }),
  MobileProvider: ({ children }) => children,
}))
vi.mock('../WebhookDeliveriesModal', () => ({ default: () => null }))

const HOOK = { id: 7, name: 'ops', url: 'https://hook.example.com', enabled: true, events: ['certificate.issued'] }

describe('webhooks on a phone', () => {
  it('keeps the row actions on the card', () => {
    const handleWebhookToggle = vi.fn()
    render(
      <WebhooksSection webhooks={[HOOK]} webhooksLoading={false} handleWebhookCreate={vi.fn()} handleWebhookEdit={vi.fn()}
        handleWebhookToggle={handleWebhookToggle} handleWebhookTest={vi.fn()} setWebhookConfirmDelete={vi.fn()}
        hasPermission={(p) => ['read:settings', 'write:settings', 'delete:settings'].includes(p)} />,
      { wrapper: MemoryRouter },
    )
    const card = document.querySelector('.mobile-record')
    for (const label of ['webhooks.deliveries.title', 'webhooks.test', 'common.edit', 'common.delete']) {
      expect(within(card).getByTitle(label)).toBeInTheDocument()
    }
    fireEvent.click(within(card).getByTitle('common.disable'))
    expect(handleWebhookToggle).toHaveBeenCalledWith(HOOK)
  })
})
