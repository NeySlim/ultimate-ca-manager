/** A bounded field of General carries its bounds and shows the error the save found on it. */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'fr' } }),
  initReactI18next: { type: '3rdParty', init: () => {} },
}))
vi.mock('../../../contexts', () => ({ useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn() }) }))
vi.mock('../ServiceStatusWidget', () => ({ default: () => null }))
vi.mock('../PublicEndpointsPanel', () => ({ default: () => null }))
vi.mock('../../../services', () => ({
  certificatesService: { getAll: () => Promise.resolve({ data: [] }) },
  settingsService: { updateBulk: vi.fn() },
}))

import GeneralSection from '../GeneralSection'

describe('GeneralSection bounded fields', () => {
  it('gives the inactivity field its bounds and marks it out of range', () => {
    render(
      <GeneralSection settings={{ session_timeout: 99999 * 60 }} updateSetting={vi.fn()} canWrite={() => true}
        hasPermission={() => true} fieldErrors={{ session_timeout: 'Durée hors plage : un entier de 5 à 1440 minutes.' }} />,
    )
    const field = screen.getByRole('spinbutton', { name: /settings\.sessionTimeout/ })
    expect(field).toHaveAttribute('min', '5')
    expect(field).toHaveAttribute('max', '1440')
    expect(field).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText('Durée hors plage : un entier de 5 à 1440 minutes.')).toBeInTheDocument()
    expect(screen.getByRole('spinbutton', { name: /settings\.maxLoginAttempts/ })).not.toHaveAttribute('aria-invalid')
  })
})
