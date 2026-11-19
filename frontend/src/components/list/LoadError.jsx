/**
 * A list that could not be read: what failed, why, and a button to try again. It takes
 * the place of the list; the rest of the page stays usable.
 */
import { useTranslation } from 'react-i18next'
import { Warning, ArrowClockwise } from '@phosphor-icons/react'
import './list.css'

export function LoadError({ title, cause, onRetry, children }) {
  const { t } = useTranslation()
  return (
    <div className="lv-error" role="alert">
      <Warning aria-hidden="true" />
      <div>
        <h2>{title}</h2>
        {cause && <p>{cause}</p>}
        <div className="lv-error-actions">
          <button type="button" className="lv-btn is-primary" onClick={onRetry}>
            <ArrowClockwise size={16} aria-hidden="true" />{t('common.retry')}
          </button>
          {children}
        </div>
      </div>
    </div>
  )
}

export default LoadError
