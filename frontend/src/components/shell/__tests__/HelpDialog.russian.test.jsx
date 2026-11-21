/**
 * Russian has its own help: on the real i18n instance and the real loader the
 * dialog shows the Russian page without the notice; German still gets English plus the notice.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup, act, waitFor } from '@testing-library/react'
import { I18nextProvider } from 'react-i18next'
import i18n from '../../../i18n'
import de from '../../../i18n/locales/de.json'
import ru from '../../../i18n/locales/ru.json'
import ruHsm from '../../../data/help/ru/hsm'


import { HelpDialog } from '../HelpDialog'
import { helpContent } from '../../../data/helpContent'

const open = async (lang) => {
  await act(async () => { await i18n.changeLanguage(lang) })
  render(<I18nextProvider i18n={i18n}><HelpDialog open onClose={() => {}} pageKey="hsm" /></I18nextProvider>)
}

describe('HelpDialog in Russian', () => {
  afterEach(async () => { cleanup(); await i18n.changeLanguage('en') })

  it('shows the Russian page and no English-only notice', async () => {
    await open('ru')
    expect(i18n.resolvedLanguage).toBe('ru')
    await waitFor(() => expect(screen.getByRole('heading', { level: 2 }).textContent).toBe(ruHsm.helpContent.title))
    expect(ruHsm.helpContent.title).not.toBe(helpContent.hsm.title)
    expect(screen.queryByText(ru.help.englishOnlyNotice)).toBeNull()
  })

  it('keeps English and the notice for a language without help', async () => {
    await open('de')
    expect(screen.getByRole('heading', { level: 2 }).textContent).toBe(helpContent.hsm.title)
    expect(screen.getByText(de.help.englishOnlyNotice)).toBeTruthy()
  })
})
