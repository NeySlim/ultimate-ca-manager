import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { trustStoreText, templateText, SYSTEM_TEMPLATES } from '../systemTexts'

const t = (key, opts) => (opts?.path ? `${key}:${opts.path}` : `«${key}»`)
const dir = dirname(fileURLToPath(import.meta.url))
const LOCALES = ['de', 'en', 'es', 'fr', 'it', 'ja', 'pt', 'ru', 'uk', 'zh']
const load = (code) => JSON.parse(readFileSync(join(dir, '..', '..', '..', 'i18n', 'locales', `${code}.json`), 'utf8'))

describe('the texts the server writes for its own objects', () => {
  it('words the system trust bundle in the user\'s language, the path kept', () => {
    expect(trustStoreText(t, 'Imported from system CA bundle')).toBe('«trustStore.systemBundleDescription»')
    expect(trustStoreText(t, 'Auto-imported from /etc/ssl/certs/ca-certificates.crt'))
      .toBe('trustStore.systemBundleNote:/etc/ssl/certs/ca-certificates.crt')
  })

  it('keeps a text an operator wrote', () => {
    expect(trustStoreText(t, 'Partner root, added by hand')).toBe('Partner root, added by hand')
    expect(trustStoreText(t, null)).toBe(null)
  })

  it('names a system template in the user\'s language, never a custom one of the same name', () => {
    expect(templateText(t, { is_system: true, name: 'Email (S/MIME)' }, 'name')).toBe('«templates.builtIn.email.name»')
    expect(templateText(t, { is_system: true, name: 'Email (S/MIME)', description: 'x' }, 'description')).toBe('«templates.builtIn.email.description»')
    expect(templateText(t, { is_system: false, name: 'Email (S/MIME)' }, 'name')).toBe('Email (S/MIME)')
    expect(templateText(t, { is_system: true, name: 'Unknown built-in' }, 'name')).toBe('Unknown built-in')
    // a language that lacks the key shows the server's name
    expect(templateText((k) => k, { is_system: true, name: 'Email (S/MIME)' }, 'name')).toBe('Email (S/MIME)')
  })

  it('has every key it uses in every language', () => {
    for (const code of LOCALES) {
      const d = load(code)
      expect(d.trustStore.systemBundleDescription, code).toBeTruthy()
      expect(d.trustStore.systemBundleNote, code).toContain('{{path}}')
      for (const key of new Set(Object.values(SYSTEM_TEMPLATES))) {
        expect(d.templates.builtIn[key].name, `${code} ${key}`).toBeTruthy()
        expect(d.templates.builtIn[key].description, `${code} ${key}`).toBeTruthy()
      }
    }
  })
})
