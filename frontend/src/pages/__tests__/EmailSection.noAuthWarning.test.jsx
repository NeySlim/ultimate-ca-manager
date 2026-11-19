/**
 * EmailSection: switching to no authentication warns that the stored OAuth2 secrets go.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import './pageRenderingSetup.jsx'

import EmailSection from '../settings/EmailSection'

const SAVED = { smtp_host: 'smtp.example.com', smtp_port: 587, smtp_username: 'mailer',
  smtp_security: 'starttls', smtp_auth_method: 'oauth2', smtp_oauth_provider: 'google' }

const renderSection = (settings) => render(
  <EmailSection settings={settings} savedEmail={SAVED} updateSetting={vi.fn()} handleSave={vi.fn()}
                canWrite={() => true} isMobile={false} oauthPresets={{}} setOauthDirty={vi.fn()}
                expiryAlerts={{ alert_days: [], recipients: [] }} setExpiryAlerts={vi.fn()} />
)

const WARNING = 'settings.smtpNoAuthClearsOauth'

describe('EmailSection: no authentication over stored OAuth2 secrets', () => {
  it.each([
    ['client secret', { has_oauth_client_secret: true }],
    ['refresh token', { has_oauth_refresh_token: true }],
  ])('warns when a %s is stored', (_label, stored) => {
    renderSection({ ...SAVED, ...stored, smtp_auth_method: 'none' })
    expect(screen.getByText(WARNING)).toBeInTheDocument()
  })

  it('says nothing when no OAuth2 secret is stored', () => {
    renderSection({ ...SAVED, smtp_auth_method: 'none' })
    expect(screen.queryByText(WARNING)).not.toBeInTheDocument()
  })

  it('says nothing while OAuth2 stays selected', () => {
    renderSection({ ...SAVED, has_oauth_client_secret: true, has_oauth_refresh_token: true })
    expect(screen.queryByText(WARNING)).not.toBeInTheDocument()
  })
})
