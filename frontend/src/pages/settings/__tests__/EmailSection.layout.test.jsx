/**
 * The e-mail section: the template group names the template once (its legend), its sentence and button under it;
 * the expiry alerts switched off grey their thresholds, recipients and options.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k) => k, i18n: { language: 'en' } }) }))
vi.mock('../../../contexts', () => ({ useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn() }) }))
vi.mock('../../../hooks/useClipboard', () => ({ useClipboard: () => ({ copy: vi.fn() }) }))
vi.mock('../EmailTemplateDialog', () => ({ default: () => null }))

import EmailSection from '../EmailSection'

const draw = (enabled) => render(
  <EmailSection settings={{ smtp_host: 'mail.example', smtp_auth_method: 'none' }} savedEmail={{}} updateSetting={vi.fn()} canWrite={() => true}
    isMobile={false} expiryAlerts={{ enabled, alert_days: [30], recipients: [], include_revoked: false, exclude_acme: false }}
    setExpiryAlerts={vi.fn()} triggerExpiryCheck={vi.fn()} showTemplateEditor={false} setShowTemplateEditor={vi.fn()}
    handleTestEmail={vi.fn()} applyOAuthProviderPreset={vi.fn()} handleSmtpOAuthAuthorize={vi.fn()} handleSmtpOAuthRevoke={vi.fn()} />,
)

describe('EmailSection', () => {
  it('names the template once, its sentence and its button under the legend', () => {
    draw(true)
    expect(screen.getAllByText('settings.emailTemplate')).toHaveLength(1)
    expect(screen.getByText('settings.emailTemplate').tagName).toBe('LEGEND')
    expect(screen.getByRole('button', { name: 'settings.editTemplate' })).toBeEnabled()
  })

  it('greys the alerts\' settings while the alerts are off, and gives them back when on', () => {
    const { unmount } = draw(false)
    expect(document.getElementById('set-expiry_recipients')).toBeDisabled()
    expect(document.getElementById('set-expiry_include_revoked')).toBeDisabled()
    expect(screen.getByRole('group', { name: 'settings.alertDays' }).querySelector('button')).toBeDisabled()
    unmount()
    draw(true)
    expect(document.getElementById('set-expiry_recipients')).toBeEnabled()
    expect(document.getElementById('set-expiry_include_revoked')).toBeEnabled()
  })
})
