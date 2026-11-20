/** Last saves of the settings, as the audit log records them (who, when, what). */
import { useTranslation } from 'react-i18next'
import { formatDate } from '../../lib/utils'

// The audit log names a save in English: the known names and fixed details in the reader's
// language, as the mockup writes them (« SMTP modifié »); any other text is shown as recorded
const TITLES = {
  'General Settings': 'settings.history.general',
  'Email/SMTP Settings': 'settings.history.smtp',
  'Email Template': 'settings.history.template',
  'Notification Settings': 'settings.history.notifications',
  'Auto-Renewal Settings': 'settings.history.autoRenewal',
  'UCM Update Settings': 'settings.history.autoUpdate',
  'UCM Update': 'settings.history.update',
  syslog: 'settings.history.syslog',
  mTLS: 'settings.history.mtls',
}
const ACTIONS = { ct_settings_updated: 'settings.history.ct' }
const DETAILS = {
  'Updated general settings': 'settings.history.generalDetail',
  'Updated email/SMTP settings': 'settings.history.smtpDetail',
  'Updated email template': 'settings.history.templateDetail',
  'Reset email template to default': 'settings.history.templateResetDetail',
  'Updated notification settings': 'settings.history.notificationsDetail',
  'Updated certificate auto-renewal configuration': 'settings.history.autoRenewalDetail',
  'Certificate Transparency settings updated': 'settings.history.ctDetail',
}

export default function SettingsHistory({ entries }) {
  const { t } = useTranslation()
  const title = (entry) => {
    const key = TITLES[entry.resource_name] || ACTIONS[entry.action]
    return key ? t(key) : (entry.resource_name || entry.action)
  }
  const detail = (text) => (DETAILS[text] ? t(DETAILS[text]) : text)
  return (
    <section className="sf-history" aria-labelledby="sf-history-title">
      <header className="sf-heading">
        <div>
          <h2 id="sf-history-title">{t('settings.historyTitle')}</h2>
          <p>{t('settings.historyIntent')}</p>
        </div>
      </header>
      {entries.length ? (
        <ul className="sf-history-list">
          {entries.map((entry) => (
            <li key={entry.id}>
              <span className="sf-history-main">
                <strong>{title(entry)}</strong>
                {entry.details && <span className="sf-history-detail">{detail(entry.details)}</span>}
              </span>
              <span className="sf-history-meta">{entry.username} · {formatDate(entry.timestamp, { time: true })}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="sf-history-empty">{t('settings.historyEmpty')}</p>
      )}
    </section>
  )
}
