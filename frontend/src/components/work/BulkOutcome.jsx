/**
 * Outcome of a bulk action where one failed, line by line, in the mockup's record list: what
 * went through, what failed and why, then the dialog's single action.
 */
import { useTranslation } from 'react-i18next'
import { Btn, Pill, RecordList, RecordRow } from '../atelier'

/** @param {{ outcome: Array<{ item, ok, reason }>, nameOf: (item) => string, onClose: () => void }} p */
export function BulkOutcome({ outcome, nameOf, onClose }) {
  const { t } = useTranslation()
  const ok = outcome.filter((o) => o.ok).length
  const failed = outcome.length - ok
  return (
    <div data-testid="bulk-outcome">
      <p className="small muted" role="status">
        {t('work.bulk.done', { count: ok })}
        {failed > 0 && <>{', '}{t('work.bulk.failed', { count: failed })}</>}
      </p>
      <RecordList>
        {outcome.map((o, i) => (
          <RecordRow key={i} title={nameOf(o.item)} meta={!o.ok && o.reason ? o.reason : undefined}
            badge={<Pill label={t(o.ok ? 'work.bulk.ok' : 'work.bulk.ko')} tone={o.ok ? 'good' : 'bad'} />} />
        ))}
      </RecordList>
      <div className="modal-actions">
        <Btn tone="primary" write={false} onClick={onClose}>{t('common.close')}</Btn>
      </div>
    </div>
  )
}
