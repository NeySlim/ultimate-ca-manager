/**
 * Russian is a full interface language: the picker offers it, the page lang follows it, its
 * plural forms (one, few, many, other) render, and its file keeps the shape and guards of the others.
 */
import { describe, it, expect, afterEach } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import i18next from 'i18next'
import i18n, { languages } from '../index'

const require = createRequire(import.meta.url)
const { flattenKeys, missingPluralForms, isLocalePluralForm } = require('../../../../scripts/check-i18n-sync.js')

const localesDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'locales')
const load = (code) => JSON.parse(readFileSync(join(localesDir, `${code}.json`), 'utf8'))
const codes = readdirSync(localesDir).filter(f => f.endsWith('.json')).map(f => f.slice(0, -5))
const flat = (o) => Object.fromEntries(flattenKeys(o).map(k => [k, k.split('.').reduce((a, p) => a[p], o)]))
const vars = (s) => [...String(s).matchAll(/\{\{\s*([^}]+?)\s*\}\}/g)].map(m => m[1]).sort()

describe('Russian declaration', () => {
  afterEach(async () => { await i18n.changeLanguage('en') })

  it('is offered by the language list', () => {
    expect(languages.find(l => l.code === 'ru')).toMatchObject({ name: 'Русский', flag: '🇷🇺' })
  })

  it('sets the page language and translates a witness screen', async () => {
    await i18n.changeLanguage('ru')
    expect(document.documentElement.lang).toBe('ru')
    expect(i18n.t('common.cancel')).toBe(load('ru').common.cancel)
    expect(i18n.t('common.cancel')).not.toBe(load('en').common.cancel)
  })

  it('serves a browser asking for ru-RU in Russian', async () => {
    await i18n.changeLanguage('ru-RU')
    expect(i18n.resolvedLanguage).toBe('ru')
    expect(document.documentElement.lang).toBe('ru')
  })
})

describe('Russian plural forms', () => {
  async function inst() {
    const t = i18next.createInstance()
    await t.init({ lng: 'ru', resources: { ru: { translation: load('ru') } } })
    return t
  }
  const pluralKeys = flattenKeys(load('en')).filter(k => k.endsWith('_one')).map(k => k.slice(0, -4))

  it('agrees the noun with the count', async () => {
    const t = await inst()
    const forms = [1, 2, 5, 21, 11].map(count => t.t('common.subtitle', { count }))
    expect(forms[0]).toBe('1 сертификат')
    expect(forms[1]).toBe('2 сертификата')
    expect(forms[2]).toBe('5 сертификатов')
    expect(forms[3]).toBe('21 сертификат')
    expect(forms[4]).toBe('11 сертификатов')
  })

  it.each([1, 2, 5, 11, 21, 22])('every plural key renders a sentence for %i', async (count) => {
    const t = await inst()
    expect(pluralKeys.length).toBeGreaterThan(20)
    for (const key of pluralKeys) {
      const out = t.t(key, { count })
      expect(out, key).not.toBe(key)
      expect(out, key).toContain(String(count))
    }
  })
})

describe('check-i18n-sync plural rules', () => {
  const ref = new Set(['a.n_one', 'a.n_other', 'b'])
  const full = new Set(['a.n_one', 'a.n_few', 'a.n_many', 'a.n_other', 'b'])
  const cats = new Intl.PluralRules('ru').resolvedOptions().pluralCategories

  it.each(['ru', 'uk'])('accepts complete forms and rejects a missing few or many for %s', (code) => {
    const c = new Intl.PluralRules(code).resolvedOptions().pluralCategories
    expect(missingPluralForms(full, ref, c)).toEqual([])
    expect(missingPluralForms(new Set([...full].filter(k => k !== 'a.n_few')), ref, c)).toEqual(['a.n_few'])
    expect(missingPluralForms(new Set([...full].filter(k => k !== 'a.n_many')), ref, c)).toEqual(['a.n_many'])
    expect(isLocalePluralForm('a.n_few', ref, c)).toBe(true)
  })

  it('does not demand few for English', () => {
    expect(missingPluralForms(ref, ref, new Intl.PluralRules('en').resolvedOptions().pluralCategories)).toEqual([])
    expect(cats).toContain('many')
  })
})

describe('locale file guards', () => {
  const en = flat(load('en'))

  // Plural forms the language adds beyond English one/other carry the base variables
  it.each(codes.filter(c => c !== 'en'))('%s keeps the {{variables}} of the English text', (code) => {
    const other = flat(load(code))
    const bad = []
    for (const [k, v] of Object.entries(other)) {
      const base = en[k] !== undefined ? en[k] : en[k.replace(/_(zero|two|few|many)$/, '_other')]
      if (base === undefined) continue
      const a = vars(base), b = vars(v)
      if (a.join() !== b.join()) bad.push(`${k}: ${a} != ${b}`)
    }
    expect(bad).toEqual([])
  })

  it('ru has no em dash and no empty value', () => {
    const ru = flat(load('ru'))
    expect(Object.entries(ru).filter(([, v]) => String(v).includes('—')).map(([k]) => k)).toEqual([])
    // An empty value is allowed only where the English reference is empty too
    expect(Object.entries(ru).filter(([k, v]) => String(v).trim() === '' && en[k] !== '').map(([k]) => k)).toEqual([])
  })
  // Identical to English only where the text is a protocol, product or token name (measured: 3.5%
  // of the keys, ukrainian 3.8%). Placeholders carry examples and commands and are left alone.
  const SAME_AS_ENGLISH = new Set([
  "ACL", "ACME", "AD", "AES", "API", "AWS CloudHSM", "Active Directory", "Active Directory, OpenLDAP",
  "Atelier", "Aurore", "Azure AD, Google, GitHub, OIDC", "Azure Key Vault", "Base DN", "Bind DN",
  "Brainpool (RFC 5639)", "CA/Browser Forum", "CRL/OCSP", "CSR", "CSR PEM", "CT", "Common Criteria EAL 4+",
  "DNS", "ECDSA P-256", "ECDSA P-384", "ECDSA P-521", "EST", "ETSI (EN 319 412)", "Ed25519", "Ed448",
  "EdDSA", "Entity ID", "GitHub", "Gmail", "Google Cloud KMS", "Google Workspace", "HSM",
  "HSTS (Strict Transport Security)", "HTML", "HTTP API", "HTTPS", "ID", "ISO 8601", "Intune",
  "JKS (Java KeyStore)", "Kerberos", "Kerberos / SPNEGO", "Keytab", "LDAP", "LDAP / Active Directory",
  "LET'S ENCRYPT", "Let's Encrypt", "ML-DSA (FIPS 204)", "Microsoft AD CS", "Microsoft CA",
  "Microsoft Entra ID (Azure AD)", "NIST P-256 (ECDSA)", "NIST P-384 (ECDSA)", "NIST P-521 (ECDSA)",
  "OAuth2", "OAuth2 (XOAUTH2)", "OAuth2 / OIDC", "OCSP Must-Staple (RFC 6066)", "OID", "OPNsense",
  "Okta, ADFS, Keycloak", "OpenLDAP", "PEM", "PKCS#1 v1.5", "PKCS#12 (.p12)", "PKCS12 (.p12/.pfx)",
  "PKCS7 (.p7b)", "PKI", "Posh-ACME", "Python", "QcCClegislation", "QcCompliance", "QcLimitValue", "QcPDS",
  "QcRetentionPeriod", "QcSSCD", "QcType", "RBAC", "RFC 5280", "RSA", "RSA 2048", "RSA 3072", "RSA 4096",
  "RSA-PSS", "SAML", "SAML 2.0", "SAN DNS", "SCEP", "SHA-1", "SHA-256", "SSH", "SSH / SFTP", "SSL/TLS",
  "SSO", "STARTTLS", "TOTP", "TSA", "UCM {{version}}", "UPN", "URI", "URL", "WebSocket", "X-API-Key",
  "acme.sh", "cert-manager", "certbot", "lego", "member (OpenLDAP / RFC 2307)",
  "memberOf (Active Directory)", "permit-X11-forwarding", "permit-agent-forwarding",
  "permit-port-forwarding", "permit-pty", "permit-user-rc", "ssh-certificate",
  "uniqueMember (OpenLDAP groupOfUniqueNames)", "win-acme", "{{action}}: {{name}}", "{{action}} {{name}}", "{{label}}: {{value}}", "Esc", "⚫ GitHub", "🔵 Google",
  "🟦 Microsoft Entra"
  ])

  it('ru translates the text: identical values are named protocols and products, under 4%', () => {
    const ru = flat(load('ru'))
    const same = Object.keys(en).filter(k => en[k] !== '' && en[k] === ru[k])
    expect(same.length / Object.keys(en).length).toBeLessThan(0.04)
    const untranslated = same.filter(k => !k.endsWith('Placeholder') && !SAME_AS_ENGLISH.has(en[k]))
    expect(untranslated).toEqual([])
  })
})
