/**
 * EmailSection: the SMTP target (where reset links go) is locked without admin:settings,
 * as the API refuses to move it; the other fields stay editable.
 */
import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import './pageRenderingSetup.jsx'

import EmailSection from '../settings/EmailSection'

const SAVED = { smtp_host: 'smtp.example.com', smtp_port: 587, smtp_username: 'mailer',
  smtp_security: 'starttls', smtp_auth_method: 'oauth2', smtp_oauth_provider: 'custom',
  smtp_oauth_client_id: 'ucm-client' }
const TARGET = ['set-smtp_host', 'set-smtp_port', 'set-smtp_from_email', 'set-smtp_username',
  'set-smtp_oauth_client_id', 'set-smtp_oauth_authorize_url', 'set-smtp_oauth_token_url',
  'set-smtp_oauth_redirect_uri']
const BY_PASSWORD = { ...SAVED, smtp_auth_method: 'password', smtp_password: '********' }

const renderSection = (perms, settings = SAVED) => render(
  <EmailSection hasPermission={(p) => perms.includes(p)} settings={settings} savedEmail={settings}
                updateSetting={vi.fn()} handleSave={vi.fn()} canWrite={() => true} isMobile={false}
                setOauthDirty={vi.fn()} expiryAlerts={{ alert_days: [], recipients: [] }} setExpiryAlerts={vi.fn()} />
)

describe('EmailSection: the SMTP target needs admin:settings', () => {
  it('locks the target for write:settings alone', () => {
    const { container } = renderSection(['read:settings', 'write:settings'])
    for (const id of TARGET) expect(container.querySelector(`#${id}`)).toBeDisabled()
    expect(container.querySelectorAll('[data-testid="admin-lock"]').length).toBeGreaterThan(0)
    expect(container.querySelector('#set-smtp_content_type, [id^="set-smtp_content_type"]')).not.toBeNull()
    // A new consent picks the sending mailbox: the API refuses it as well
    const authorize = [...container.querySelectorAll('button')].find((b) => b.textContent.includes('settings.smtpOauthAuthorize'))
    expect(authorize).toBeDisabled()
  })

  it('keeps the password of the same account editable', () => {
    const { container } = renderSection(['read:settings', 'write:settings'], BY_PASSWORD)
    expect(container.querySelector('#set-smtp_username')).toBeDisabled()
    expect(container.querySelector('#set-smtp_password')).not.toBeDisabled()
  })

  it('leaves it editable with admin:settings', () => {
    const { container } = renderSection(['read:settings', 'write:settings', 'admin:settings'])
    for (const id of TARGET) expect(container.querySelector(`#${id}`)).not.toBeDisabled()
    expect(container.querySelector('[data-testid="admin-lock"]')).toBeNull()
  })
})
