/**
 * The mockup's tableFooter() and pageJump(): the range in words, then the page size, previous,
 * the page (« 2 / 5 », or a field to jump to a page and « Aller » when the server pages a large
 * list), next. Without `pagination` the footer only says the range and a note. Under a list short of room, the
 * number of columns it folded follows the range, then Réinitialiser les colonnes while a width is set by hand.
 */
import { useContext, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from './Icon'
import { FoldedColumns, ColumnsReset } from './foldedColumns'

/**
 * @param {string} range  « 1–25 sur 276 certificats »
 * @param {{page, pages, perPage, sizes, onPage, onPerPage, perPageLabel, jump}} [pagination]
 */
export function TableFooter({ range, note, pagination }) {
  return (
    <footer className="table-footer">
      <span id={pagination?.jump ? 'page-range' : undefined}>{range}</span>
      <FoldedNote />
      <ResetColumns />
      {pagination ? <PageControls {...pagination} /> : note !== undefined && <span>{note}</span>}
    </footer>
  )
}

/** The columns the list folded for want of room: their number, their whole names in its title (R3, E6). */
export function FoldedNote() {
  const { t } = useTranslation()
  const folded = useContext(FoldedColumns)
  if (!folded) return null
  return <span className="folded-note" title={folded.join(', ')}>{t('table.foldedColumns', { count: folded.length })}</span>
}

/** The widths set by hand back to automatic, offered by the list while one is set (DataTable, C2). */
export function ResetColumns() {
  const { t } = useTranslation()
  const reset = useContext(ColumnsReset)
  if (!reset) return null
  return <button type="button" className="btn quiet reset-columns" data-action="reset-columns" onClick={reset}>{t('table.resetColumns')}</button>
}

function PageControls({ page, pages, perPage, sizes = [10, 25, 50, 100], onPage, onPerPage, perPageLabel, jump = false }) {
  const { t, i18n } = useTranslation()
  const locale = i18n?.language || undefined
  const goTo = (n) => onPage?.(Math.min(pages, Math.max(1, n)))
  return (
    <div className="controls">
      {onPerPage && (
        <select id="page-size" aria-label={perPageLabel || t('table.perPageLabel')} value={perPage} onChange={(e) => onPerPage(Number(e.target.value))}>
          {sizes.map((n) => <option key={n} value={n}>{t('table.perPage', { size: n })}</option>)}
        </select>
      )}
      <button type="button" className="icon-btn" data-page="prev" aria-label={t('table.previousPage')} disabled={page <= 1} onClick={() => goTo(page - 1)}>
        <Icon name="left" />
      </button>
      {jump ? <PageJump page={page} pages={pages} onGo={goTo} locale={locale} /> : <span>{page} / {pages}</span>}
      <button type="button" className="icon-btn" data-page="next" aria-label={t('table.nextPage')} disabled={page >= pages} onClick={() => goTo(page + 1)}>
        <Icon name="right" />
      </button>
    </div>
  )
}

/** A page number to type: Enter or Aller goes there, bounded to the pages; the field keeps the focus. */
export function PageJump({ page, pages, onGo, locale }) {
  const { t } = useTranslation()
  const [value, setValue] = useState(String(page))
  useEffect(() => { setValue(String(page)) }, [page])
  const go = () => onGo(parseInt(value, 10) || 1)
  return (
    <>
      <label className="page-jump"><span>{t('table.page')}</span>
        <input id="page-jump" type="number" min="1" max={pages} value={value} inputMode="numeric" aria-describedby="page-total"
          onChange={(e) => setValue(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); go() } }} />
      </label>
      <span id="page-total">{t('table.pageOf', { total: pages.toLocaleString(locale) })}</span>
      <button type="button" className="btn" id="page-go" data-action="page-go" onClick={go}>{t('table.goToPage')}</button>
    </>
  )
}

export default TableFooter
