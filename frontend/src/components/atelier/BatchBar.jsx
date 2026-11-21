/**
 * The mockup's batchbar: the count of selected items, the bulk actions, then « Annuler la
 * sélection » at the far right. Clearing gives the focus to the page title, as the mockup does
 * once the bar leaves.
 */
import { useTranslation } from 'react-i18next'
import { focusMainTitle } from './helpers'

/** `count` words the selection (a node); `extra` sits after them (select every result, keep the page). */
export function BatchBar({ count, extra, children, onClear, work = false }) {
  const { t } = useTranslation()
  return (
    <div className={work ? 'batchbar work-bar' : 'batchbar'} role="group" aria-label={t(work ? 'work.bulkLabel' : 'table.selection')}>
      <strong id={work ? undefined : 'selection-count'}>{count}</strong>
      {extra}
      {children}
      <span className="spacer" />
      <button type="button" className="btn quiet" data-action="deselect" onClick={() => { onClear?.(); focusMainTitle() }}>
        {t('table.clearSelection')}
      </button>
    </div>
  )
}

export default BatchBar
