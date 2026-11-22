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
    expect(t('shell.expiringCount', { count: 1 })).toBe('1 certificate expiring or expired')
    expect(t('shell.expiringCount', { count: 2 })).toBe('2 certificates expiring or expired')
    expect(t('shell.approvalsPending', { count: 1 })).toBe('1 approval pending')
    expect(t('shell.approvalsPending', { count: 2 })).toBe('2 approvals pending')
    expect(t('shell.haNodes', { count: 1 })).toBe('1 node · up to date')
    expect(t('shell.haNodes', { count: 3 })).toBe('3 nodes · all up to date')
    expect(t('shell.haLate', { count: 1 })).toBe('1 node late')
    expect(t('shell.haLate', { count: 2 })).toBe('2 nodes late')
  })

  it('french is translated and agrees in number', async () => {
    const t = await make('fr', fr.shell)
    expect(t('shell.haNodes', { count: 1 })).toBe('1 nœud · à jour')
    expect(t('shell.haNodes', { count: 3 })).toBe('3 nœuds · tous à jour')
    expect(t('shell.haLate', { count: 2 })).toBe('2 nœuds en retard')
    expect(t('shell.expiringCount', { count: 1 })).toBe('1 certificat expire ou a expiré')
    expect(t('shell.approvalsPending', { count: 2 })).toBe('2 approbations en attente')
  })

  it('ukrainian carries the few and many forms for every counter', () => {
    for (const k of ['expiringCount', 'approvalsPending', 'haNodes', 'haLate']) {
      for (const f of ['one', 'few', 'many', 'other']) expect(uk.shell[`${k}_${f}`]).toBeTruthy()
    }
  })
})
