import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { languages } from '../../i18n'
import { persistPreference } from '../../stores/userPreferencesStore'

// The language as a field of a form: its label above, the 36 px list, names without flags
export default function LanguageSelector({ className = '' }) {
  const { t, i18n } = useTranslation()
  const id = useId()

  const handleChange = (e) => {
    const newLang = e.target.value
    i18n.changeLanguage(newLang)
    try {
      localStorage.setItem('i18nextLng', newLang)
    } catch {
      // Safari private mode
    }
    // Persist server-side when authenticated (issue #73). No-op on login page.
    persistPreference('language', newLang)
  }

  return (
    <div className={`ui-field ${className}`.trim()}>
      <label htmlFor={id} className="ui-label">{t('settings.language')}</label>
      <select
        id={id}
        value={i18n.language?.split('-')[0] || 'en'}
        onChange={handleChange}
        className="ui-control"
      >
        {languages.map((lang) => (
          <option key={lang.code} value={lang.code}>{lang.name}</option>
        ))}
      </select>
    </div>
  )
}
