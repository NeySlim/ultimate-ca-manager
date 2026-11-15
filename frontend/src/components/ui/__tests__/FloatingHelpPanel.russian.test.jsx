/**
 * Russian is an interface language without translated help: on the real i18n
 * instance the panel shows the English page and the notice from ru.json.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup, act } from '@testing-library/react'
import { I18nextProvider } from 'react-i18next'
import i18n from '../../../i18n'
import ru from '../../../i18n/locales/ru.json'

const h = vi.hoisted(() => ({ load: vi.fn() }))

vi.mock('../../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: false }) }))
vi.mock('../FloatingWindow', () => ({
  FloatingWindow: ({ title, children }) => <div><h1>{title}</h1>{children}</div>,
}))
vi.mock('../../../data/helpLoader', () => ({ loadHelpPage: (...a) => h.load(...a) }))

import { FloatingHelpPanel } from '../FloatingHelpPanel'
import { helpContent } from '../../../data/helpContent'

describe('FloatingHelpPanel in Russian', () => {
  afterEach(async () => { cleanup(); await i18n.changeLanguage('en') })

  it('shows the English page with the Russian notice and imports nothing', async () => {
    await act(async () => { await i18n.changeLanguage('ru') })
    render(<I18nextProvider i18n={i18n}><FloatingHelpPanel isOpen onClose={() => {}} pageKey="acme" /></I18nextProvider>)
    expect(i18n.resolvedLanguage).toBe('ru')
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(helpContent.acme.title)
    expect(screen.getByText(ru.help.englishOnlyNotice)).toBeTruthy()
    expect(h.load).not.toHaveBeenCalled()
  })
})
