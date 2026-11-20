/**
 * Outcome of a bulk action where one failed, line by line: what went through, what failed and why.
 */
import { useTranslation } from 'react-i18next'
import { Warning } from '@phosphor-icons/react'
import { CheckIcon } from './workIcons'
import { cn } from '../../lib/utils'
import { WorkButton } from './WorkQueue'

/** @param {{ outcome: Array<{ item, ok, reason }>, nameOf: (item) => string, onClose: () => void }} p */
export function BulkOutcome({ outcome, nameOf, onClose }) {
  const { t } = useTranslation()
  const ok = outcome.filter((o) => o.ok).length
  const failed = outcome.length - ok
  return (
    <div className="wk-dialog" data-testid="bulk-outcome">
      <p role="status">
        {t('work.bulk.done', { count: ok })}
        {failed > 0 && <>{', '}{t('work.bulk.failed', { count: failed })}</>}
      </p>
      <ul className="wk-outcome">
        {outcome.map((o, i) => (
          <li key={i} className={cn(o.ok ? 'is-ok' : 'is-failed')}>
            {o.ok ? <CheckIcon aria-hidden="true" /> : <Warning aria-hidden="true" />}
            <span>
              <strong>{nameOf(o.item)}</strong>
              {' '}<span className="wk-muted">{o.ok ? t('work.bulk.ok') : t('work.bulk.ko')}</span>
              {!o.ok && o.reason && <span className="wk-reason">{o.reason}</span>}
            </span>
          </li>
        ))}
      </ul>
      <div className="lv-dialog-actions">
        <WorkButton primary data-write="false" onClick={onClose}>{t('common.close')}</WorkButton>
      </div>
    </div>
  )
}
