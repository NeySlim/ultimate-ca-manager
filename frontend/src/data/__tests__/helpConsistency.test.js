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

describe('French wording of the certification authority', () => {
  const fr = import.meta.glob('../../i18n/locales/fr.json', { eager: true })['../../i18n/locales/fr.json'].default
  const frStrings = [
    ...strings(fr),
    ...strings(entries.filter((e) => e.lang === 'fr').map((e) => e.page)),
  ]
  // The French acronym is "AC"; "CA" stays only in these English technical terms, in code
  // and in the example CA name of the import placeholder, kept as the English one.
  const ENGLISH_TERMS = /CA\/Browser Forum|CA:(?:TRUE|FALSE)|CA Issuers|Global Root CA|Corp-Root-CA/g
  // In a fenced block only the translated comments and the "(note)" after an address are French.
  const prose = (block) => block.split('\n').map((l) => (l.match(/#.*$|\s{2,}\(.*\)$/) || [''])[0]).join('\n')
  const uncoded = (s) => s.replace(/```[\s\S]*?```/g, prose).replace(/`[^`]*`/g, ' ').replace(ENGLISH_TERMS, ' ')
  it('has no isolated "CA" in the interface and the help', () => {
    const found = frStrings.flatMap((s) => uncoded(s).match(/(?<![\p{L}\p{N}_])CAs?(?![\p{L}\p{N}_]).{0,20}/gu) || [])
    expect(found).toEqual([])
  })
  // Where English spells out "Certificate Authority", the French label spells out "autorité de certification".
  it('spells out the long form wherever English does', () => {
    const en = import.meta.glob('../../i18n/locales/en.json', { eager: true })['../../i18n/locales/en.json'].default
    const flat = (o, p = '') => Object.entries(o).flatMap(([k, v]) => (v && typeof v === 'object' ? flat(v, `${p}${k}.`) : [[p + k, v]]))
    const frFlat = Object.fromEntries(flat(fr))
    const found = flat(en)
      .filter(([k, v]) => /certificate authorit/i.test(v) && !/autorité/i.test(frFlat[k] || ''))
      .map(([k]) => k)
    expect(found).toEqual([])
  })
  // The key ID template and the SSH CA types are written as the French screens show them.
  it('has no English fragments around the AC in the SSH help', () => {
    const found = frStrings.flatMap((s) => s.match(/AC name|User AC|Host AC|Production User/g) || [])
    expect(found).toEqual([])
  })
  // "AC" is feminine and starts with a vowel: "l'AC", "d'AC", "cette AC", "toute AC", never "la AC", "tout AC", "l'CA".
  it('elides and agrees the article before AC', () => {
    const found = frStrings.flatMap((s) => uncoded(s).match(/(?<![\p{L}\p{N}_])(?:la|le|de|du|ce|cet|au|un|sa|ma|ta|que|si|tout|nouveau|quel)\s+AC(?![\p{L}\p{N}_]).{0,20}|[\p{L}\p{N}_]+\\?['’]CA(?![\p{L}\p{N}_]).{0,20}/giu) || [])
    expect(found).toEqual([])
  })
})

describe('SSO setup steps', () => {
  const locales = import.meta.glob('../../i18n/locales/{en,fr,ru,zh}.json', { eager: true })
  const guide = (lang) => (lang === 'en' ? helpGuides.sso : pages[`../help/${lang}/sso.js`].default.helpGuides).content
  // Settings > SSO shows one card per type with a Configure button; there is no "Add SSO Provider" button.
  const oldLabel = { en: 'Add SSO Provider', fr: 'Ajouter un fournisseur SSO', ru: 'Добавить провайдера SSO', zh: '添加 SSO 提供者' }
  it.each(['en', 'fr', 'ru', 'zh'])('%s names the Configure button of each provider card', (lang) => {
    const { sso } = locales[`../../i18n/locales/${lang}.json`].default
    const text = guide(lang)
    expect(text).not.toContain(oldLabel[lang])
    expect(text).toContain(`**${sso.configure}**`)
    for (const type of ['saml', 'oauth2', 'ldap']) expect(text).toContain(`**${sso[type]}**`)
  })
})

describe('dead locale keys', () => {
  const all = import.meta.glob('../../i18n/locales/*.json', { eager: true })
  // The SSO page has one Configure button per provider card; no screen renders sso.addProvider.
  it.each(Object.keys(all))('%s has no sso.addProvider', (path) => {
    expect(all[path].default.sso).not.toHaveProperty('addProvider')
  })
})

describe('values and buttons quoted by the translated pages', () => {
  const locales = import.meta.glob('../../i18n/locales/{en,fr,ru,zh}.json', { eager: true })
  const page = (lang, key) => (lang === 'en' ? helpContent[key] : pages[`../help/${lang}/${key}.js`].default.helpContent)
  it.each(['fr', 'ru', 'zh'])('%s keeps the renamed duplicates "name (N)" in English', (lang) => {
    const found = strings(entries.filter((e) => e.lang === lang).map((e) => e.page))
      .filter((s) => s.includes('name (2)') && !s.includes('name (3)') && /\(3\)/.test(s))
    expect(found).toEqual([])
  })
  // The provider details have a Sync keys button; the SSH CA guide names the key storage and provider fields.
  it.each(['en', 'fr', 'ru', 'zh'])('%s names the HSM Sync keys button and the SSH CA key fields', (lang) => {
    const t = locales[`../../i18n/locales/${lang}.json`].default
    const guide = (key) => (lang === 'en' ? helpGuides[key].content : pages[`../help/${lang}/${key}.js`].default.helpGuides.content)
    expect(guide('hsm')).toContain(`**${t.common.syncKeys}**`)
    for (const label of [t.cas.create.keyStorage, t.cas.create.hsmProvider, t.cas.create.hsmExistingKey, t.sshCas.createCA]) {
      expect(guide('sshCas')).toContain(`**${label}**`)
    }
    const items = strings(page(lang, 'hsm').sections.flatMap((sec) => sec.items || []))
    expect(items.join('\n')).toContain(t.common.syncKeys)
  })
  // The HSM page creates a provider with its "New Provider" button.
  it.each(['en', 'fr', 'ru', 'zh'])('%s names the HSM New Provider button', (lang) => {
    const { hsm } = locales[`../../i18n/locales/${lang}.json`].default
    const actions = helpContent.hsm.sections.findIndex((s) => s.title === 'Actions')
    expect(page(lang, 'hsm').sections[actions].items[0].label).toBe(hsm.newProvider)
  })
})

describe('buttons named by the English help', () => {
  // Every "Click **X**" must be a label en.json holds.
  const norm = (s) => s.replace(/\{\{\w+\}\}/g, 'N').replace(/^▶\s*/, '').trim().toLowerCase()
  it('cites only labels the interface shows', async () => {
    const en = (await import('../../i18n/locales/en.json')).default
    const labels = new Set(strings(en).map(norm))
    const cited = strings([helpContent, helpGuides])
      .flatMap((s) => [...s.matchAll(/\b[Cc]lick(?: on)? \*\*([^*]+)\*\*/g)].map((m) => m[1]))
    expect([...new Set(cited)].filter((c) => !labels.has(norm(c)))).toEqual([])
  })
})

describe('buttons of the HSM, certificate and template guides in every language', () => {
  const locales = import.meta.glob('../../i18n/locales/{en,fr,ru,zh}.json', { eager: true })
  const guide = (lang, key) => (lang === 'en' ? helpGuides[key].content : pages[`../help/${lang}/${key}.js`].default.helpGuides.content)
  it.each(['en', 'fr', 'ru', 'zh'])('%s quotes the Generate, Issue Certificate and Copy buttons as the screen shows them', (lang) => {
    const t = locales[`../../i18n/locales/${lang}.json`].default
    expect(guide(lang, 'hsm')).toContain(`**${t.common.generate}**`)
    expect(guide(lang, 'certificates')).toContain(`**${t.certificates.issueCertificate}**`)
    expect(guide(lang, 'templates')).toContain(`**${t.common.copy}**`)
    // The key generation modal opens with Generate; the former labels are gone from the steps.
    const oldLabel = { en: 'Generate Key', fr: 'Générer une clé', ru: 'Сформировать ключ HSM', zh: '生成密钥' }[lang]
    expect(guide(lang, 'hsm')).not.toContain(`**${oldLabel}**`)
    if (lang === 'en') expect(guide(lang, 'certificates')).not.toMatch(/Click \*\*Issue\*\*/)
  })
  it.each(['en', 'fr', 'ru', 'zh'])('%s says the forced password prompt has Logout as its only other button', (lang) => {
    const t = locales[`../../i18n/locales/${lang}.json`].default
    const text = (lang === 'en' ? helpContent.account : pages[`../help/${lang}/account.js`].default.helpContent)
    const forced = strings(text.sections).find((s) => s.includes('INITIAL_ADMIN_PASSWORD_FORCE_CHANGE'))
    expect(forced).toContain(t.common.logout)
    expect(forced).toMatch({ en: /only other button is Logout/, fr: /seul autre bouton est Déconnexion/, ru: /единственная другая кнопка/, zh: /唯一的另一个按钮/ }[lang])
  })
})

describe('screen labels quoted by every help language', () => {
  const locales = import.meta.glob('../../i18n/locales/{en,fr,ru,zh}.json', { eager: true })
  const help = (lang, key) => (lang === 'en'
    ? { guide: helpGuides[key].content, page: helpContent[key] }
    : { guide: pages[`../help/${lang}/${key}.js`].default.helpGuides.content, page: pages[`../help/${lang}/${key}.js`].default.helpContent })
  it.each(['en', 'fr', 'ru', 'zh'])('%s quotes the labels and API routes users actually have', (lang) => {
    const t = locales[`../../i18n/locales/${lang}.json`].default
    const bold = (s) => `**${s.replace(/\{\{\w+\}\}/g, 'N')}**`
    const mtls = help(lang, 'user-certificates').guide
    for (const s of [t.account.addCertificate, t.account.mtlsGenerate, t.account.generateCertificate, t.account.clientCertificates]) expect(mtls).toContain(bold(s))
    const audit = help(lang, 'auditLogs').guide
    for (const s of [t.audit.cleanupLogs, t.common.deleteOldLogs]) expect(audit).toContain(bold(s))
    expect(help(lang, 'importExport').guide).toContain(bold(t.importExport.opnsense.importSelected))
    expect(strings(help(lang, 'account').page).join('\n')).toContain(t.common.logout)
    // Key regeneration and signature schemes have no control on screen: the help names the API.
    expect(help(lang, 'account').guide).toContain('/api/v2/account/apikeys/<id>/regenerate')
    expect(help(lang, 'policies').guide).toContain('`allowed_signature_schemes`')
  })
})

describe('system template advice', () => {
  const locales = import.meta.glob('../../i18n/locales/*.json', { eager: true })
  // The Templates page offers a Copy button, never "duplicate"; per language: the former verb and the stem of the button label.
  const verbs = {
    en: [/duplicate/i, /copy/i], fr: [/dupliqu/i, /copi/i], ru: [/дублиру|продублиру/i, /копир/i], zh: [/复制/, /复制/],
    de: [/duplizier/i, /kopier/i], es: [/dupliqu/i, /copi/i], it: [/duplic/i, /copi/i], pt: [/dupliqu/i, /copi/i],
    uk: [/дублікат/i, /копі/i], ja: [/複製/, /コピー/],
  }
  const tip = (lang) => locales[`../../i18n/locales/${lang}.json`].default.templates.deactivateTooltip
  const help = (lang) => {
    const page = lang === 'en' ? helpContent.templates : pages[`../help/${lang}/templates.js`].default.helpContent
    return page.sections.flatMap((sec) => sec.items || []).filter((i) => /^(Deactivate|Désactiver|Деактивировать|停用)$/.test(i.label)).map((i) => i.text)
  }
  it.each(Object.keys(verbs))('%s tooltip advises the Copy button', (lang) => {
    const [old, copy] = verbs[lang]
    if (lang !== 'zh') expect(tip(lang)).not.toMatch(old)
    expect(tip(lang)).toMatch(copy)
  })
  it.each(['en', 'fr', 'ru', 'zh'])('%s help advises the Copy button', (lang) => {
    const [old, copy] = verbs[lang]
    const text = help(lang).join('\n')
    if (lang !== 'zh') expect(text).not.toMatch(old)
    expect(text).toMatch(copy)
  })
})
