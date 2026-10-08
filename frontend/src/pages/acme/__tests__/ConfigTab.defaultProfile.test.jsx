/**
 * The default ACME profile (#378) can only name a profile that exists: one
 * removed in the editor stops being the default before the settings are saved.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../ProfilesEditor', () => ({
  default: ({ onChange }) => (
    <>
      <button onClick={() => onChange({ default: { validity_days: 90 } })}>drop-short</button>
      <button onClick={() => onChange({ default: { validity_days: 90 }, shorter: { validity_days: 27 } })}>
        rename-short
      </button>
    </>
  ),
}))

import ConfigTab from '../ConfigTab'

const settings = (extra) => ({
  enabled: true,
  profiles: { default: { validity_days: 90 }, short: { validity_days: 27 } },
  ...extra,
})

describe('ConfigTab default profile', () => {
  it('clears the default when its profile is removed', () => {
    const updateSetting = vi.fn()
    render(<ConfigTab acmeSettings={settings({ default_profile: 'short' })} cas={[]}
      updateSetting={updateSetting} canWrite />)
    fireEvent.click(screen.getByText('drop-short'))
    expect(updateSetting).toHaveBeenCalledWith('profiles', { default: { validity_days: 90 } })
    expect(updateSetting).toHaveBeenCalledWith('default_profile', '')
  })

  it('follows a renamed default profile', () => {
    const updateSetting = vi.fn()
    render(<ConfigTab acmeSettings={settings({ default_profile: 'short' })} cas={[]}
      updateSetting={updateSetting} canWrite />)
    fireEvent.click(screen.getByText('rename-short'))
    expect(updateSetting).toHaveBeenCalledWith('default_profile', 'shorter')
  })

  it('keeps a default whose profile survives', () => {
    const updateSetting = vi.fn()
    render(<ConfigTab acmeSettings={settings({ default_profile: 'default' })} cas={[]}
      updateSetting={updateSetting} canWrite />)
    fireEvent.click(screen.getByText('drop-short'))
    expect(updateSetting).not.toHaveBeenCalledWith('default_profile', '')
  })

  it('offers each profile and a none option', () => {
    render(<ConfigTab acmeSettings={settings({ default_profile: '' })} cas={[]}
      updateSetting={vi.fn()} canWrite />)
    expect(screen.getByText('acme.defaultProfile')).toBeInTheDocument()
    expect(screen.getByText('acme.defaultProfileDesc')).toBeInTheDocument()
  })
})
