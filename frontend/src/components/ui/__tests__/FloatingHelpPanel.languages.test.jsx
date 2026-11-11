/**
 * Help is translated for the languages in HELP_TRANSLATED_LANGUAGES only; any
 * other interface language shows English, attempts no import and says so.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'

const h = vi.hoisted(() => ({ lang: 'en', resolved: null, load: vi.fn() }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, fallback) => (key === 'help.englishOnlyNotice' ? 'NOTICE' : (fallback ?? key)),
    i18n: { language: h.lang, resolvedLanguage: h.resolved || h.lang },
  }),
}))
vi.mock('../../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: false }) }))
vi.mock('../FloatingWindow', () => ({
  FloatingWindow: ({ title, children }) => <div><h1>{title}</h1>{children}</div>,
}))
vi.mock('../../../data/helpLoader', () => ({ loadHelpPage: (...a) => h.load(...a) }))

import { FloatingHelpPanel } from '../FloatingHelpPanel'
import { helpContent } from '../../../data/helpContent'
import { HELP_TRANSLATED_LANGUAGES } from '../../../data/helpLanguages'

const en = helpContent.acme.title
const open = (pageKey = 'acme') => render(<FloatingHelpPanel isOpen onClose={() => {}} pageKey={pageKey} />)

describe('FloatingHelpPanel help languages', () => {
  beforeEach(() => {
    h.load.mockReset()
    h.resolved = null
    h.load.mockResolvedValue({ default: { helpContent: { title: 'TRADUIT' } } })
  })

  it('lists exactly fr and zh', () => {
    expect([...HELP_TRANSLATED_LANGUAGES].sort()).toEqual(['fr', 'zh'])
  })

  it.each(['fr', 'zh-CN'])('merges the translation for %s', async (lang) => {
    h.lang = lang
    open()
    await waitFor(() => expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('TRADUIT'))
    expect(h.load).toHaveBeenCalledWith(lang.slice(0, 2), 'acme')
    expect(screen.queryByText('NOTICE')).toBeNull()
  })

  it.each(['de', 'ja', 'uk'])('shows English with no import for %s, with the notice', async (lang) => {
    h.lang = lang
    open()
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(en)
    expect(screen.getByText('NOTICE')).toBeTruthy()
    await Promise.resolve()
    expect(h.load).not.toHaveBeenCalled()
  })

  it('shows English without notice for en', () => {
    h.lang = 'en'
    open()
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(en)
    expect(screen.queryByText('NOTICE')).toBeNull()
    expect(h.load).not.toHaveBeenCalled()
  })

  it('shows no notice when the browser language is unsupported and the interface resolves to English', () => {
    h.lang = 'nl-NL'
    h.resolved = 'en'
    open()
    expect(screen.queryByText('NOTICE')).toBeNull()
    expect(h.load).not.toHaveBeenCalled()
  })

  it('ignores a French load that resolves after switching to German', async () => {
    let resolveFr
    h.load.mockReturnValueOnce(new Promise((r) => { resolveFr = r }))
    h.lang = 'fr'
    // A page not cached by the earlier tests, so the fr load really is in flight.
    const { rerender } = open('dashboard')
    h.lang = 'de'
    rerender(<FloatingHelpPanel isOpen onClose={() => {}} pageKey="dashboard" />)
    await act(async () => { resolveFr({ default: { helpContent: { title: 'TRADUIT' } } }) })
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(helpContent.dashboard.title)
    expect(screen.getByText('NOTICE')).toBeTruthy()
  })
})
