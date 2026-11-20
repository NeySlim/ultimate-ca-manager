/** The language is a field of the form: a label above a list whose options are plain names, no emoji flags. */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'fr', changeLanguage: vi.fn() } }),
}))
vi.mock('../../../stores/userPreferencesStore', () => ({ persistPreference: vi.fn() }))
vi.mock('../../../i18n', () => ({
  languages: [{ code: 'en', name: 'English', flag: '🇬🇧' }, { code: 'fr', name: 'Français', flag: '🇫🇷' }],
}))

import LanguageSelector from '../LanguageSelector'

describe('LanguageSelector as a form field', () => {
  it('is named by its label and lists the names without flags', () => {
    render(<LanguageSelector />)
    const list = screen.getByRole('combobox', { name: 'settings.language' })
    expect(list).toHaveValue('fr')
    expect(list).toHaveClass('ui-control')
    expect(screen.getAllByRole('option').map((o) => o.textContent)).toEqual(['English', 'Français'])
  })
})
