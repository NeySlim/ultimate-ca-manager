/**
 * EmailSection: the SMTP target (where reset links go) is locked without admin:settings,
 * as the API refuses to move it; the other fields stay editable.
 */
import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import './pageRenderingSetup.jsx'

import EmailSection from '../settings/EmailSection'

const SAVED = { smtp_host: 'smtp.example.com', smtp_port: 587, smtp_username: 'mailer',
  smtp_security: 'starttls', smtp_auth_method: 'oauth2', smtp_oauth_provider: 'custom' }
const TARGET = ['set-smtp_host', 'set-smtp_port', 'set-smtp_from_email', 'set-smtp_oauth_authorize_url',
  'set-smtp_oauth_token_url', 'set-smtp_oauth_redirect_uri']

const renderSection = (perms) => render(
  <EmailSection hasPermission={(p) => perms.includes(p)} settings={SAVED} savedEmail={SAVED}
                updateSetting={vi.fn()} handleSave={vi.fn()} canWrite={() => true} isMobile={false}
                setOauthDirty={vi.fn()} expiryAlerts={{ alert_days: [], recipients: [] }} setExpiryAlerts={vi.fn()} />
)

describe('EmailSection: the SMTP target needs admin:settings', () => {
  it('locks the target for write:settings alone', () => {
    const { container } = renderSection(['read:settings', 'write:settings'])
    for (const id of TARGET) expect(container.querySelector(`#${id}`)).toBeDisabled()
    expect(container.querySelectorAll('[data-testid="admin-lock"]').length).toBeGreaterThan(0)
    expect(container.querySelector('#set-smtp_username')).not.toBeDisabled()
    expect(container.querySelector('#set-smtp_content_type, [id^="set-smtp_content_type"]')).not.toBeNull()
  })

  it('leaves it editable with admin:settings', () => {
    const { container } = renderSection(['read:settings', 'write:settings', 'admin:settings'])
    for (const id of TARGET) expect(container.querySelector(`#${id}`)).not.toBeDisabled()
    expect(container.querySelector('[data-testid="admin-lock"]')).toBeNull()
  })
})
