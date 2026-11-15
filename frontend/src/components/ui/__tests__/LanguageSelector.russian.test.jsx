import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { I18nextProvider, useTranslation } from 'react-i18next'
import i18n from '../../../i18n'
import LanguageSelector from '../LanguageSelector'

vi.mock('../../../stores/userPreferencesStore', () => ({ persistPreference: vi.fn() }))

function Witness() {
  const { t } = useTranslation()
  return <p data-testid="witness">{t('common.cancel')}</p>
}

describe('language selector offers Russian', () => {
  afterEach(async () => { cleanup(); await i18n.changeLanguage('en') })

  it('lists Русский, and choosing it translates the screen and sets lang="ru"', async () => {
    render(<I18nextProvider i18n={i18n}><LanguageSelector /><Witness /></I18nextProvider>)
    const option = screen.getByRole('option', { name: /Русский/ })
    expect(option.value).toBe('ru')
    expect(screen.getByTestId('witness').textContent).toBe('Cancel')
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'ru' } })
    await vi.waitFor(() => expect(screen.getByTestId('witness').textContent).toBe('Отмена'))
    expect(document.documentElement.lang).toBe('ru')
  })
})
