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
    expect(value('common.twoFactorAuth')).toBe('common.yes')
    expect(value('common.totp')).toBe('common.yes')
    expect(value('users.exempt2faLabel')).toBe('common.no')
  })

  it('ignores the former fields', () => {
    render(<UserSecuritySection user={{ mfa_enabled: true, totp_confirmed: true }} />)
    expect(value('common.twoFactorAuth')).toBe('common.no')
    expect(value('common.totp')).toBe('common.no')
    expect(screen.queryByText('common.enable2FA')).toBeNull()
  })
})
