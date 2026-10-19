/**
 * EmailSection: a moved SMTP server marks the saved password as required, with the reason.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import './pageRenderingSetup.jsx'

import EmailSection from '../settings/EmailSection'

const SAVED = { smtp_host: 'smtp.example.com', smtp_port: 587, smtp_username: 'mailer',
  smtp_password: '********', smtp_security: 'starttls', smtp_auth_method: 'password' }

const renderSection = (settings) => render(
  <EmailSection settings={settings} savedEmail={SAVED} updateSetting={vi.fn()} handleSave={vi.fn()}
                canWrite={() => true} isMobile={false} oauthPresets={{}} setOauthDirty={vi.fn()}
                expiryAlerts={{ alert_days: [], recipients: [] }} setExpiryAlerts={vi.fn()} />
)

describe('EmailSection: saved password and target', () => {
  it('asks for the password once the server moves', () => {
    renderSection({ ...SAVED, smtp_host: 'smtp.attacker.example' })
    expect(screen.getByText('common.secretRequiredForTarget')).toBeInTheDocument()
  })

  it('says nothing while the server stays', () => {
    renderSection(SAVED)
    expect(screen.queryByText('common.secretRequiredForTarget')).not.toBeInTheDocument()
  })
})
