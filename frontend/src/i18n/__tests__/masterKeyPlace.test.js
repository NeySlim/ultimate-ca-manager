/**
 * Where the master key lives depends on the installation (UCM_CONFIG_DIR, KEY_ENCRYPTION_KEY): the
 * Security settings text and the help name its sources, never one fixed path as a fact.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { helpContent } from '../../data/helpContent'
import { helpGuides } from '../../data/helpGuides'
import es from '../../data/help/es/security'
import fr from '../../data/help/fr/security'
import ru from '../../data/help/ru/security'
import zh from '../../data/help/zh/security'

const dir = dirname(fileURLToPath(import.meta.url))
const LOCALE_CODES = ['de', 'en', 'es', 'fr', 'it', 'ja', 'pt', 'ru', 'uk', 'zh']
const load = (code) => JSON.parse(readFileSync(join(dir, '..', 'locales', `${code}.json`), 'utf8'))

describe('the master key text of Settings > Security (10 locales)', () => {
  it.each(LOCALE_CODES)('%s: names the file and the variable, and the Key source row, no fixed path', (code) => {
    const { settings } = load(code)
    const text = settings.encryptionDesc
    expect(text).not.toContain('/etc/ucm')
    expect(text).toContain('master.key')
    expect(text).toContain('KEY_ENCRYPTION_KEY')
    expect(text).toContain(settings.keySource)
  })
})

describe('the help on the first start creating the master key (5 languages)', () => {
  it.each([
    ['en', helpContent.security, helpGuides.security.content],
    ['es', es.helpContent, es.helpGuides.content],
    ['fr', fr.helpContent, fr.helpGuides.content],
    ['ru', ru.helpContent, ru.helpGuides.content],
    ['zh', zh.helpContent, zh.helpGuides.content],
  ])('%s: the key file is in the configuration directory, which UCM_CONFIG_DIR moves', (lang, content, guide) => {
    const items = content.sections.flatMap((s) => s.items || [])
    const first = items.find((i) => /master\.key \(0600\)|master\.key（0600）/.test(i.text))
    expect(first, lang).toBeTruthy()
    for (const text of [first.text, guide]) {
      expect(text, lang).not.toContain('/etc/ucm/master.key')
      expect(text, lang).toContain('UCM_CONFIG_DIR')
    }
  })
})
