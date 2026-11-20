/**
 * French sentences under the settings frames, as the mockup writes them: a full stop at the
 * end, the typographic apostrophe, and a space before the colon of a label.
 */
import { describe, it, expect } from 'vitest'
import fr from '../../../i18n/locales/fr.json'
import en from '../../../i18n/locales/en.json'
import ru from '../../../i18n/locales/ru.json'
import zh from '../../../i18n/locales/zh.json'

const KEYS = [
  'settings.generalSubtitle', 'settings.appearanceSubtitle', 'settings.emailSubtitle', 'settings.securitySubtitle',
  'sso.subtitle', 'settings.backupSubtitle', 'settings.auditSubtitle', 'settings.databaseSubtitle',
  'settings.httpsSubtitle', 'settings.updatesSubtitle', 'scheduler.subtitle', 'webhooks.subtitle',
  'settings.ctDescription', 'settings.autoRenewalDescription', 'deploy.subtitle', 'msca.subtitle',
  'adConnector.subtitle', 'xcepWstep.subtitle', 'settings.about.subtitle',
]
// The frames of Mon compte, Outils and Opérations follow the same rule
const OTHER_PAGES = [
  'account.personalDetails', 'account.manageAccountSecurity', 'tools.sslCheckerDesc', 'tools.csrDecoderDesc',
  'tools.certDecoderDesc', 'tools.keyMatcherDesc', 'tools.converterDesc', 'operations.importHeaderDesc',
  'operations.exportHeaderDesc', 'operations.bulkHeaderDesc',
]
// Legends and labels of the same frames: typographic apostrophe, « et » rather than « & »
const LEGENDS = [
  'settings.auditLogging', 'settings.emailTemplate', 'settings.expiryAlerts', 'settings.anomalyDetection',
  'settings.adminAllowlistTitle', 'settings.smtpAuthMethod', 'settings.about.links', 'settings.syslogCatUsers',
  'settings.syslogCatSystem',
]
const readIn = (locale, key) => key.split('.').reduce((node, part) => node?.[part], locale)
const read = (key) => readIn(fr, key)

describe('French settings sentences', () => {
  it.each(KEYS)('%s ends with a full stop and uses the typographic apostrophe', (key) => {
    const text = read(key)
    expect(text).toMatch(/\.$/)
    expect(text).not.toContain("'")
  })

  it.each(OTHER_PAGES)('%s, a frame sentence of the other pages, ends the same way', (key) => {
    expect(read(key)).toMatch(/\.$/)
    expect(read(key)).not.toContain("'")
  })

  it.each(LEGENDS)('%s keeps the typographic apostrophe and no ampersand', (key) => {
    expect(read(key)).not.toContain("'")
    expect(read(key)).not.toContain('&')
  })

  it.each([...KEYS, ...OTHER_PAGES])('%s ends with a full stop in English, Russian and Chinese too', (key) => {
    expect(readIn(en, key)).toMatch(/\.$/)
    expect(readIn(ru, key)).toMatch(/\.$/)
    expect(readIn(zh, key)).toMatch(/。$/)
  })

  it('says the same as the French in the three general sentences rewritten from the mockup', () => {
    expect(readIn(en, 'settings.generalSubtitle')).toBe('Identity of the instance and its public address.')
    expect(readIn(en, 'settings.emailSubtitle')).toBe('Relay of the notifications and reports.')
    expect(readIn(en, 'settings.securitySubtitle')).toBe('Sessions, authentication and cryptography.')
  })

  it('separates a label from its value with a space before the colon', () => {
    expect(fr.work.sep).toBe(' : ')
  })
})
