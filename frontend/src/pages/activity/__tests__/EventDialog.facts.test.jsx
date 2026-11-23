/**
 * The detail of a journal entry as typed facts: its result as a state, its IP address in a chip that
 * copies it, no button beside a value, the client's long signature on a long row.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, p) => (p ? `${k} ${JSON.stringify(p)}` : k), i18n: { language: 'en' } }),
}))
vi.mock('../../../contexts/NotificationContext', () => ({ useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn() }) }))

import { EventDialog } from '../EventDialog'

const LOG = {
  action: 'certificate.revoke', resource_type: 'certificate', resource_id: '12', username: 'alice', timestamp: '2026-11-20T10:00:00Z',
  success: false, ip_address: '2001:db8::10', user_agent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0 Safari/537.36',
  details: 'Revoked',
}
const row = (term) => [...document.querySelectorAll('dl.kv > div.row')].find((r) => r.querySelector('dt')?.textContent === term)
let writeText

beforeEach(() => {
  writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
  Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true })
})

describe('the event dialog', () => {
  it('reads the entry as typed facts, its IP address copied from its chip', async () => {
    render(<EventDialog log={LOG} locale="en" resource="web.example.com" onClose={vi.fn()} onInspect={vi.fn()} canInspect={() => true} />)
    expect(document.querySelector('dl.props')).toBeNull()
    expect(row('audit.colResult').querySelector('dd.v .badge.bad')).toHaveTextContent('audit.badgeFailed')
    expect(row('audit.action').querySelector('dd.v .mono')).toHaveTextContent('certificate.revoke')
    const ip = row('audit.ipAddress')
    expect(ip.querySelector('dd.v .code-value')).toHaveTextContent('2001:db8::10')
    const buttons = [...document.querySelectorAll('dl.kv dd button')]
    expect(buttons.every((b) => b.closest('.code-value'))).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: /protocols\.copyValue/ }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('2001:db8::10'))
    expect(row('audit.client')).toHaveClass('long')
    // Its margin comes from the stylesheet (.event-detail .kv), not from a style of its own
    expect(document.querySelector('.event-detail > dl.kv')).not.toHaveAttribute('style')
  })

  it('names the system when no user did it, and shows no address it does not have', () => {
    render(<EventDialog log={{ ...LOG, username: null, ip_address: null, user_agent: null, success: true }} locale="en" resource="—"
      onClose={vi.fn()} onInspect={vi.fn()} canInspect={() => false} />)
    expect(row('audit.colUser').querySelector('dd.v')).toHaveTextContent('common.system')
    expect(row('audit.colResult').querySelector('dd.v .badge.good')).toHaveTextContent('audit.badgeOk')
    expect(row('audit.ipAddress')).toBeUndefined()
    expect(row('audit.client')).toBeUndefined()
  })
})
