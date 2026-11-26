/** The XCEP URLs are long: their group keeps the whole card where the groups of fields go two abreast. */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en' } }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../contexts', () => ({ useNotification: () => ({ showWarning: vi.fn(), showError: vi.fn() }) }))
vi.mock('../../../hooks/useSaveParts', () => ({ useSavePart: () => {}, keptPartDraft: () => ({}) }))
vi.mock('../../../services', () => ({
  windowsProfilesService: { getSettings: () => Promise.resolve({ data: { xcep_enabled: true } }) },
}))

import WindowsSettingsPanel from '../WindowsSettingsPanel'

describe('Windows settings layout', () => {
  it('lays the XCEP URLs on the whole card', async () => {
    render(<WindowsSettingsPanel hasPermission={() => true} />)
    const legend = await screen.findByText('xcepWstep.urlsTitle', { selector: 'legend' })
    expect(legend.closest('fieldset')).toHaveClass('settings-group', 'wide')
  })
})
