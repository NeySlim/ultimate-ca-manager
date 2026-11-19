/**
 * Labels of the list template in real locales: totals and ranges take the plural
 * of the language and group their thousands as it does.
 */
import { describe, it, expect } from 'vitest'
import i18next from 'i18next'
import en from '../locales/en.json'
import fr from '../locales/fr.json'
import ru from '../locales/ru.json'

const say = async (lng, resources) => {
  const i18n = i18next.createInstance()
  await i18n.init({ lng, resources: { [lng]: { translation: resources } } })
  return i18n.t.bind(i18n)
}

describe('list template labels', () => {
  it('reads in English', async () => {
    const t = await say('en', en)
    expect(t('certificates.total', { count: 1 })).toBe('1 certificate')
    expect(t('certificates.total', { count: 1234 })).toBe('1,234 certificates')
    expect(t('certificates.range', { start: 1, end: 25, count: 1276 })).toBe('1–25 of 1,276 certificates')
    expect(t('table.range', { start: 26, end: 50, total: 1276 })).toBe('26–50 of 1,276')
    expect(t('table.selectedCount', { count: 2 })).toBe('2 selected')
    expect(t('table.perPage', { size: 25 })).toBe('25 / page')
    expect(t('table.rowAction', { action: 'Export', name: 'web.example.com' })).toBe('Export: web.example.com')
  })

  it('reads in French, with its plurals and its thousands separator', async () => {
    const t = await say('fr', fr)
    expect(t('certificates.total', { count: 1 })).toBe('1 certificat')
    expect(t('certificates.total', { count: 1234 })).toMatch(/^1\s234 certificats$/)
    expect(t('certificates.range', { start: 1, end: 25, count: 276 })).toBe('1–25 sur 276 certificats')
    expect(t('table.selectedCount', { count: 1 })).toBe('1 sélectionné')
    expect(t('table.selectedCount', { count: 3 })).toBe('3 sélectionnés')
    expect(t('certificates.bulkExported', { count: 2 })).toBe('2 certificats exportés')
  })

  it('names the state of a certificate, not the State or Province of a subject', async () => {
    // common.state is the subject field (ST): the list needs its own word
    const de = (await import('../locales/de.json')).default
    expect(de.common.state).toBe('Bundesland')
    expect(de.certificates.state).toBe('Zustand')
    expect(ru.certificates.state).not.toBe(ru.common.state)
    expect(en.certificates.state).toBe('State')
  })

  it('takes the Russian forms', async () => {
    const t = await say('ru', ru)
    expect([1, 2, 5, 21].map((count) => t('certificates.total', { count }))).toEqual([
      '1 сертификат', '2 сертификата', '5 сертификатов', '21 сертификат',
    ])
    expect(t('certificates.range', { start: 1, end: 25, count: 276 })).toBe('1–25 из 276 сертификатов')
  })
})
