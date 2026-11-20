/**
 * French sentences under the settings frames, as the mockup writes them: a full stop at the
 * end, the typographic apostrophe, and a space before the colon of a label.
 */
import { describe, it, expect } from 'vitest'
import fr from '../../../i18n/locales/fr.json'

const KEYS = [
  'settings.generalSubtitle', 'settings.appearanceSubtitle', 'settings.emailSubtitle', 'settings.securitySubtitle',
  'sso.subtitle', 'settings.backupSubtitle', 'settings.auditSubtitle', 'settings.databaseSubtitle',
  'settings.httpsSubtitle', 'settings.updatesSubtitle', 'scheduler.subtitle', 'webhooks.subtitle',
  'settings.ctDescription', 'settings.autoRenewalDescription', 'deploy.subtitle', 'msca.subtitle',
  'adConnector.subtitle', 'xcepWstep.subtitle', 'settings.about.subtitle',
]
const read = (key) => key.split('.').reduce((node, part) => node?.[part], fr)

describe('French settings sentences', () => {
  it.each(KEYS)('%s ends with a full stop and uses the typographic apostrophe', (key) => {
    const text = read(key)
    expect(text).toMatch(/\.$/)
    expect(text).not.toContain("'")
  })

  it('separates a label from its value with a space before the colon', () => {
    expect(fr.work.sep).toBe(' : ')
  })
})
