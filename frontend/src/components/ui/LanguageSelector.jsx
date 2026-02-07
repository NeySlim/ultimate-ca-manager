import { useTranslation } from 'react-i18next'
import { languages } from '../../i18n'
import { Globe } from '@phosphor-icons/react'

export default function LanguageSelector({ className = '' }) {
  const { i18n } = useTranslation()

  const handleChange = (e) => {
    const newLang = e.target.value
    i18n.changeLanguage(newLang)
    try {
      localStorage.setItem('i18nextLng', newLang)
    } catch {
      // Safari private mode
    }
  }

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <Globe className="w-4 h-4 text-text-secondary" />
      <select
        value={i18n.language?.split('-')[0] || 'en'}
        onChange={handleChange}
        className="bg-bg-secondary border border-border rounded-md px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-primary"
      >
        {languages.map((lang) => (
          <option key={lang.code} value={lang.code}>
            {lang.flag} {lang.name}
          </option>
        ))}
      </select>
    </div>
  )
}
