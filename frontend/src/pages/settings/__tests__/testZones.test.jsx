/**
 * Test zones of the sections, as the mockup's: the button stays shown (syslog off included),
 * its result on the same line in the tone of the outcome, a hint at rest.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import '../../__tests__/pageRenderingSetup.jsx'
import AuditSection from '../AuditSection'
import AutoRenewalSection from '../AutoRenewalSection'

const syslog = { enabled: false, host: '', port: 514, protocol: 'udp', categories: [] }
const audit = (props) => render(
  <AuditSection settings={{}} updateSetting={vi.fn()} hasPermission={() => true} syslogConfig={syslog}
    updateSyslogConfig={vi.fn()} handleTestSyslog={vi.fn()} {...props} />,
)
const ar = { enabled: true, days_before_expiry: 30, renewal_sources: ['acme'], notify_on_renewal: true, notify_on_failure: true, notify_emails: [] }

describe('section test zones', () => {
  it('keeps the syslog test button while syslog is off, with the hint at rest', () => {
    audit()
    expect(screen.getByRole('button', { name: /settings.syslogTest/ })).toBeEnabled()
    expect(screen.getByText('settings.syslogTestSavedHint').closest('.sf-test-result')).not.toHaveClass('is-bad')
  })

  it('shows the syslog test result beside the button in its tone', () => {
    audit({ syslogTestResult: { ok: false, text: 'refused' } })
    const result = screen.getByRole('status')
    expect(result).toHaveTextContent('refused')
    expect(result).toHaveClass('is-bad')
    expect(result.closest('.sf-test')).toContainElement(screen.getByRole('button', { name: /settings.syslogTest/ }))
  })

  it('shows the auto-renewal run result beside Run now', () => {
    render(<AutoRenewalSection arSettings={ar} setArSettings={vi.fn()} arRunResult={{ ok: true, text: '2 renewed' }} handleArRunNow={vi.fn()} />)
    const result = screen.getByRole('status')
    expect(result).toHaveTextContent('2 renewed')
    expect(result).toHaveClass('is-good')
    expect(screen.getByRole('button', { name: /settings.autoRenewalSource_acme/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: /settings.autoRenewalSource_est/ })).toHaveAttribute('aria-pressed', 'false')
  })
})
