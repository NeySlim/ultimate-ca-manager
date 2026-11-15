import { describe, it, expect, afterEach } from 'vitest'
import i18n from '../index'

// The page's lang attribute follows the interface language (WCAG 3.1.1)
describe('document language', () => {
  afterEach(async () => { await i18n.changeLanguage('en') })

  it('follows a language change', async () => {
    await i18n.changeLanguage('fr')
    expect(document.documentElement.lang).toBe('fr')
    await i18n.changeLanguage('de')
    expect(document.documentElement.lang).toBe('de')
  })
})
