/** The shell counters pluralise in every locale instead of printing "1 certificates". */
import { describe, it, expect } from 'vitest'
import i18next from 'i18next'
import en from '../../../i18n/locales/en.json'
import fr from '../../../i18n/locales/fr.json'
import uk from '../../../i18n/locales/uk.json'

const make = async (lng, shell) => {
  const i = i18next.createInstance()
  await i.init({ lng, fallbackLng: false, resources: { [lng]: { translation: { shell } } }, interpolation: { escapeValue: false } })
  return i.t
}

describe('shell counters', () => {
  it('english uses the singular for one', async () => {
    const t = await make('en', en.shell)
    expect(t('shell.expiringBadge', { count: 1 })).toMatch(/^1 certificate expiring/)
    expect(t('shell.expiringBadge', { count: 2 })).toMatch(/^2 certificates expiring/)
    expect(t('shell.haNodes', { count: 1 })).toBe('1 node')
    expect(t('shell.haNodes', { count: 3 })).toBe('3 nodes')
    expect(t('shell.haLate', { count: 2 })).toBe('2 late')
  })

  it('french is translated and agrees in number', async () => {
    const t = await make('fr', fr.shell)
    expect(t('shell.haNodes', { count: 1 })).toBe('1 nœud')
    expect(t('shell.haNodes', { count: 3 })).toBe('3 nœuds')
    expect(t('shell.expiringBadge', { count: 1 })).toMatch(/^1 certificat expire/)
  })

  it('ukrainian carries the few and many forms for every counter', () => {
    for (const k of ['expiringBadge', 'haNodes', 'haLate']) {
      for (const f of ['one', 'few', 'many', 'other']) expect(uk.shell[`${k}_${f}`]).toBeTruthy()
    }
  })
})
