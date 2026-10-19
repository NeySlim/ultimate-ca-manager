/**
 * The ACME server offers the private-address switch its challenge validation
 * reads; it used to be settable only in the database.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../ProfilesEditor', () => ({ default: () => null }))

import ConfigTab from '../ConfigTab'

const toggle = () => screen.getByText('acme.allowPrivateIps').closest('div').parentElement.querySelector('[role="switch"]')

describe('ConfigTab private addresses', () => {
  it('shows the switch on by default and saves a change', () => {
    const updateSetting = vi.fn()
    render(<ConfigTab acmeSettings={{ enabled: true, profiles: {} }} cas={[]} updateSetting={updateSetting} canWrite />)
    expect(toggle().getAttribute('aria-checked')).toBe('true')
    fireEvent.click(toggle())
    expect(updateSetting).toHaveBeenCalledWith('allow_private_ips', false)
  })

  it('reflects a stored off', () => {
    render(<ConfigTab acmeSettings={{ enabled: true, profiles: {}, allow_private_ips: false }} cas={[]}
      updateSetting={vi.fn()} canWrite />)
    expect(toggle().getAttribute('aria-checked')).toBe('false')
  })
})
