/** Last saves of the settings, as the audit log records them (who, when, what). */
import { useTranslation } from 'react-i18next'
import { formatDate } from '../../lib/utils'

export default function SettingsHistory({ entries }) {
  const { t } = useTranslation()
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
                <strong>{entry.resource_name || entry.action}</strong>
                {entry.details && <span className="sf-history-detail">{entry.details}</span>}
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
