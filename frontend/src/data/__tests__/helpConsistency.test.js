/**
 * Every help language shows the same code and the same punctuation rules as the
 * English page: no en or em dash, and the same commands, URLs and values in code blocks
 * (only the comment lines and the "(note)" after an address may be translated).
 */
import { describe, it, expect } from 'vitest'
import { helpContent } from '../helpContent'
import { helpGuides } from '../helpGuides'

const pages = import.meta.glob('../help/*/*.js', { eager: true })
const entries = Object.entries(pages).map(([path, mod]) => {
  const [, lang, file] = path.match(/help\/([^/]+)\/([^/]+)\.js$/)
  return { path, lang, key: file, page: mod.default }
})

const strings = (node, out = []) => {
  if (typeof node === 'string') out.push(node)
  else if (Array.isArray(node)) node.forEach((n) => strings(n, out))
  else if (node && typeof node === 'object') Object.values(node).forEach((n) => strings(n, out))
  return out
}
const codeLines = (text) => (text.match(/```[\s\S]*?```/g) || []).flatMap((block) => block.split('\n'))
  .filter((l) => !l.trim().startsWith('#'))
  .map((l) => l.replace(/\s{2,}\(.*\)$/, ''))

describe('help text punctuation', () => {
  it.each(['en', ...new Set(entries.map((e) => e.lang))])('%s has no en dash or em dash', (lang) => {
    const found = lang === 'en'
      ? strings([helpContent, helpGuides])
      : strings(entries.filter((e) => e.lang === lang).map((e) => e.page))
    expect(found.filter((s) => /[–—]/.test(s))).toEqual([])
  })
})

describe('code blocks of the translated guides', () => {
  it.each(entries.filter((e) => e.page.helpGuides?.content))('$lang/$key keeps the English commands and values', ({ key, page }) => {
    expect(codeLines(page.helpGuides.content)).toEqual(codeLines(helpGuides[key].content))
  })
})

describe('French help wording', () => {
  // "CA" is read "cé-a" and never elided: "la CA", "de la CA", not "l'CA" or "d'CA".
  it('never elides an article before CA', () => {
    const found = strings(entries.filter((e) => e.lang === 'fr').map((e) => e.page))
      .flatMap((s) => s.match(/\b\w+\\?['’]CA\b.{0,20}/g) || [])
    expect(found).toEqual([])
  })
})

describe('SSO setup steps', () => {
  const locales = import.meta.glob('../../i18n/locales/{en,fr,ru,zh}.json', { eager: true })
  const guide = (lang) => (lang === 'en' ? helpGuides.sso : pages[`../help/${lang}/sso.js`].default.helpGuides).content
  // Settings > SSO shows one card per type with a Configure button; there is no "Add SSO Provider" button.
  it.each(['en', 'fr', 'ru', 'zh'])('%s names the Configure button of each provider card', (lang) => {
    const { sso } = locales[`../../i18n/locales/${lang}.json`].default
    const text = guide(lang)
    expect(text).not.toContain(sso.addProvider)
    expect(text).toContain(`**${sso.configure}**`)
    for (const type of ['saml', 'oauth2', 'ldap']) expect(text).toContain(`**${sso[type]}**`)
  })
})
