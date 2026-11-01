/**
 * The link under an issuance picker that lists the CAs hidden from it (#430).
 * Renders nothing when no signing CA is hidden.
 */
import { useTranslation } from 'react-i18next'

export function HiddenCasToggle({ count, shown, onToggle }) {
  const { t } = useTranslation()
  if (!count) return null
  return (
    <button
      type="button"
      onClick={onToggle}
      className="mt-1 text-xs text-text-tertiary hover:text-text-secondary transition-colors"
    >
      {shown ? t('cas.hideHiddenCas') : t('cas.showHiddenCas', { count })}
    </button>
  )
}
