/**
 * The mockup's tableView(): the list section of a page (`section.table-workspace`) with its toolbar,
 * the active filters, the selection bar, the table and its footer, and the caption under it
 * (what stays available, the row height and the column count). The shown columns are the user's,
 * kept in the browser when the page names a storage key; the density is one for every list (density.js).
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { usePersistedState } from '../../hooks/usePersistedState'
import { useComfortable, setComfortable } from './density'
import { DataTable } from './DataTable'
import { Toolbar, ToolsDivider, ColumnsButton, DensityButton } from './Toolbar'
import { IconBtn } from './Btn'
import { AtelierDialog } from './AtelierDialog'

/**
 * @param {object} p  every prop of DataTable, plus:
 * @param {string} p.label  accessible name of the section
 * @param {string} [p.tableLabel]  accessible name of the table's scrolling region
 * @param {import('react').ReactNode} p.search  the toolbar's search field and selects (SearchField, FilterSelect)
 * @param {import('react').ReactNode} [p.tools]  more tools after the divider (a page's own)
 * @param {import('react').ReactNode} [p.applied]  AppliedFilters
 * @param {import('react').ReactNode} [p.batch]  BatchBar, while rows are ticked
 * @param {string} [p.storageKey]  keeps the hidden columns and their widths
 * @param {{ note: string }} [p.columnsDialog]  offers the Colonnes dialog; columns with `always` stay shown
 * @param {boolean} [p.density]  offers the density toggle, which sets every list's
 * @param {{ label: string, onClick }} [p.exporter]  the export icon of the toolbar
 * @param {string} [p.captionNote]  first half of the caption under the table
 */
export function TableView({
  label, tableLabel, search, tools, applied, batch, storageKey, columnsDialog, density = false, exporter, captionNote, busy, columns, ...table
}) {
  const { t } = useTranslation()
  const comfortable = useComfortable()
  // Kept as { hidden } so that showing every column is remembered too (an empty list would read as « no choice »)
  const [prefs, setPrefs] = usePersistedState(storageKey ? `${storageKey}-columns` : null, { hidden: columns.filter((c) => c.defaultHidden).map((c) => c.id) })
  const [widths, setWidths] = usePersistedState(storageKey ? `${storageKey}-widths` : null, {})
  const [dialog, setDialog] = useState(false)
  const hiddenSet = new Set(Array.isArray(prefs?.hidden) ? prefs.hidden : [])
  const shown = columns.filter((c) => c.always || !hiddenSet.has(c.id))
  const toggleColumn = (id) => setPrefs((prev) => {
    const list = Array.isArray(prev?.hidden) ? prev.hidden : []
    return { hidden: list.includes(id) ? list.filter((x) => x !== id) : [...list, id] }
  })
  const setWidth = (id, w) => setWidths((prev) => {
    const next = { ...(prev || {}) }
    if (w === null) delete next[id]; else next[id] = w
    return next
  })
  // The mockup counts the data columns, not the checkbox and the actions
  const count = shown.length

  return (
    <section className="table-workspace" aria-label={label} aria-busy={busy || undefined}>
      <Toolbar>
        {search}
        {(columnsDialog || density || exporter || tools) && <ToolsDivider />}
        {columnsDialog && <ColumnsButton label={t('table.columns')} onClick={() => setDialog(true)} />}
        {density && (
          <DensityButton label={t('table.densityComfortable')} title={t('table.changeDensity')} pressed={!!comfortable}
            onClick={() => setComfortable(!comfortable)} />
        )}
        {exporter && <IconBtn icon="download" label={exporter.label} data-action="export-list" onClick={exporter.onClick} />}
        {tools}
      </Toolbar>
      {applied}
      {batch}
      <DataTable label={tableLabel} columns={shown} columnWidths={widths || {}} onColumnWidth={storageKey ? setWidth : undefined} {...table} />
      <div className="table-caption">
        <span>{captionNote}</span>
        <span>{t('table.rowsNote', { px: comfortable ? 44 : 36, count })}</span>
      </div>
      {dialog && (
        <AtelierDialog title={t('table.columnsDialogTitle')} size="narrow" onClose={() => setDialog(false)}>
          {columnsDialog.note && <p className="small muted" style={{ marginBottom: 17 }}>{columnsDialog.note}</p>}
          <div className="columns-list">
            {columns.filter((c) => !c.always).map((c) => (
              <label key={c.id} className="checkbox-line">
                <input type="checkbox" data-column={c.id} checked={!hiddenSet.has(c.id)} onChange={() => toggleColumn(c.id)} />{c.label}
              </label>
            ))}
          </div>
          <div className="modal-actions">
            <button type="button" className="btn primary" data-write="false" data-action="close-modal" onClick={() => setDialog(false)}>{t('table.done')}</button>
          </div>
        </AtelierDialog>
      )}
    </section>
  )
}

export default TableView
