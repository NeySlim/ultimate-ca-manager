/**
 * The link under an issuance picker that lists the CAs hidden from it (#430).
 * Renders nothing when no signing CA is hidden. Under a zone it is the mockup's `.text-link`.
 */
import { useContext } from 'react'
import { useTranslation } from 'react-i18next'
import { AtlScopeContext } from '../atelier/scope'

export function HiddenCasToggle({ count, shown, onToggle }) {
  const { t } = useTranslation()
  const inZone = useContext(AtlScopeContext)
  if (!count) return null
  return (
    <button
      type="button"
      onClick={onToggle}
      className={inZone ? 'text-link' : 'mt-1 text-xs text-text-tertiary hover:text-text-secondary transition-colors'}
    >
      {shown ? t('cas.hideHiddenCas') : t('cas.showHiddenCas', { count })}
    </button>
  )
}
