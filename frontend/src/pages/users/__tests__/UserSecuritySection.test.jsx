/**
 * The user detail shows the 2FA state the API reports. It used to read
 * `mfa_enabled`, which nothing ever set, and `totp_confirmed`, which the API
 * does not return, so every user showed 2FA off.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }))

import UserSecuritySection from '../UserSecuritySection'

const value = (label) => screen.getByText(label).nextElementSibling.textContent

describe('UserSecuritySection', () => {
  it('reports a confirmed TOTP as 2FA on', () => {
    render(<UserSecuritySection user={{ two_factor_enabled: true, totp_enabled: true }} />)
    expect(value('common.twoFactorAuth')).toBe('common.enabled')
    expect(value('common.totp')).toBe('common.enabled')
    expect(value('users.exempt2faLabel')).toBe('common.no')
  })

  it('ignores the former fields', () => {
    render(<UserSecuritySection user={{ mfa_enabled: true, totp_confirmed: true }} />)
    expect(value('common.twoFactorAuth')).toBe('common.disabled')
    expect(value('common.totp')).toBe('common.disabled')
    expect(screen.queryByText('common.enable2FA')).toBeNull()
  })
})

describe('UserSecuritySection facts', () => {
  const badge = (label) => screen.getByText(label, { selector: 'dt' }).closest('div.row').querySelector('dd.v .badge')

  it('writes each factor as a state, neutral when off, in a dl.kv', () => {
    const { container } = render(<UserSecuritySection user={{ two_factor_enabled: true, totp_enabled: false, totp_exempt: false }} />)
    expect(container.querySelector('dl.kv')).not.toBeNull()
    expect(container.querySelector('dl.props')).toBeNull()
    expect(badge('common.twoFactorAuth')).toHaveClass('good')
    expect(badge('common.twoFactorAuth')).toHaveTextContent('common.enabled')
    expect(badge('common.totp')).toHaveClass('muted')
    expect(badge('common.totp')).toHaveTextContent('common.disabled')
    expect(badge('users.exempt2faLabel')).toHaveClass('muted')
  })

  it('marks an exemption from the second factor as a warning', () => {
    render(<UserSecuritySection user={{ totp_exempt: true }} />)
    expect(badge('users.exempt2faLabel')).toHaveClass('warn')
    expect(badge('users.exempt2faLabel')).toHaveTextContent('common.yes')
  })
})
