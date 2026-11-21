import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { languages } from '../../i18n'
import { chooseLanguage } from '../../lib/chooseLanguage'

// The language as a field of a form: its label above, the 36 px list, names without flags
export default function LanguageSelector({ className = '' }) {
  const { t, i18n } = useTranslation()
  const id = useId()

  const handleChange = (e) => chooseLanguage(i18n, e.target.value)

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
