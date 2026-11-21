/**
 * The mockup's listView(), the list and detail template of the module pages: state chips with
 * their counters, then the full-width table (the name opens the detail, as does the chevron),
 * the phone records, and the footer. A toolbar, skeleton rows, a read error and the empty block
 * take the places the mockup gives them in its other lists.
 */
import { useTranslation } from 'react-i18next'
import { StateFilters } from './StateFilters'
import { DataTable } from './DataTable'
import { TableFooter } from './TableFooter'

/**
 * @param {object} p
 * @param {{views, active, onChange, label, aside}} [p.filters]  StateFilters
 * @param {string} p.label  the module, naming the section and the table
 * @param {string} p.icon  the module's icon, before each name
 * @param {(row) => string} p.title
 * @param {(row) => import('react').ReactNode} p.status
 * @param {Array<{id, label, cell(row), grow?, muted?} | {status: true}>} p.columns
 * @param {{range, note?, pagination?}} p.footer
 * @param {import('react').ReactNode} [p.error]  a LoadError in place of the table
 * @param {{key, asc}} [p.sort]  with onSort and a column's `sort` (nameSort for the name): the server's sort, as tableView() draws it
 */
export function ListView({ filters, label, caption, icon, rows, title, status, columns, openedId, onOpen, footer, toolbar, loading, empty, error, selection, rowActions, sort, onSort, nameSort, nameExtra }) {
  const { t } = useTranslation()
  const cols = [
    { id: 'name', label: t('atelier.name'), entity: true, icon: () => icon, cell: title, sort: nameSort, extra: nameExtra, skeleton: { base: 55, spread: 35 } },
    ...columns.map((c, i) => (c.status
      ? { id: 'status', label: t('atelier.state'), cell: status, skeleton: { width: '74px', kind: 'pill' } }
      : { id: c.id || `col-${i}`, label: c.label, cell: c.cell, grow: !!c.grow, tone: c.muted ? 'muted' : undefined, fit: c.fit, title: c.title, sort: c.sort })),
  ]
  const card = (row) => ({
    meta: columns.filter((c) => !c.status).slice(0, 3).map((c) => c.cell(row)),
    status: columns.some((c) => c.status) ? status(row) : undefined,
  })
  return (
    <>
      {filters && <StateFilters {...filters} busy={loading && !rows.length} />}
      <section className="table-workspace module-workspace" aria-label={label}>
        {toolbar}
        {error || (
          <DataTable kind="module" scrollId="module-scroll" label={t('atelier.tableOf', { name: label })} caption={caption}
            columns={cols} rows={rows} rowLabel={title} onOpen={onOpen} openedId={openedId} loading={loading} empty={empty}
            openLabel={(row) => t('atelier.openDetail', { name: title(row) })} card={card} selection={selection} rowActions={rowActions} sort={sort} onSort={onSort}
            footer={footer && <TableFooter {...footer} />} />
        )}
      </section>
    </>
  )
}

export default ListView
