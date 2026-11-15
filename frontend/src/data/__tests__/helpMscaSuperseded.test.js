/**
 * A request closed because its CSR was signed elsewhere shows only the Check status
 * message: each help language quotes that message in its own locale, word for word,
 * and names the full sync that brings in a certificate the CA still issues.
 */
import { describe, it, expect } from 'vitest'
import { helpContent } from '../helpContent'
import { helpGuides } from '../helpGuides'
import fr from '../help/fr/msca'
import zh from '../help/zh/msca'

const locales = import.meta.glob('../../i18n/locales/*.json', { eager: true })
const msca = (lang) => locales[`../../i18n/locales/${lang}.json`].default.msca
const LANGS = ['de', 'en', 'es', 'fr', 'it', 'ja', 'pt', 'ru', 'uk', 'zh']

const pending = (content) => content.sections.flatMap((s) => s.items || [])
  .find((i) => /checkStatus|Check status|Vérifier le statut|检查状态/.test(i.text) && i.text.includes('CSR')).text

describe('the closed request is described by what the screen shows', () => {
  it('has no status label no screen displays', () => {
    for (const lang of LANGS) expect(msca(lang).superseded, lang).toBeUndefined()
  })

  it('translates the Check status message in every language', () => {
    for (const lang of LANGS.filter((l) => l !== 'en')) {
      expect(msca(lang).checkSuperseded, lang).toBeTruthy()
      expect(msca(lang).checkSuperseded, lang).not.toBe(msca('en').checkSuperseded)
    }
  })

  it.each([
    ['en', helpContent.msca, helpGuides.msca.content],
    ['fr', fr.helpContent, fr.helpGuides.content],
    ['zh', zh.helpContent, zh.helpGuides.content],
  ])('%s help quotes the message its screen shows', (lang, content, guide) => {
    const shown = msca(lang).checkSuperseded
    expect(pending(content)).toContain(shown)
    expect(guide).toContain(shown)
    // Only a full sync reaches a request below the high-water mark
    expect(pending(content)).toContain('full: true')
    expect(guide).toContain('full: true')
  })
})
