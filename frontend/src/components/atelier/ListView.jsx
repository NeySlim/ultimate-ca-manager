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
import { cardFacts } from './cardFacts'

/**
 * @param {object} p
 * @param {{views, active, onChange, label, aside}} [p.filters]  StateFilters
 * @param {string} p.label  the module, naming the section and the table
 * @param {string} p.icon  the module's icon, before each name
 * @param {(row) => string} p.title
 * @param {(row) => import('react').ReactNode} p.status
 * @param {Array<{id, label, cell(row), kind?, priority?, grow?, sort?, labelled?, labelFull?, muted?} | {status: true}>} p.columns  the column
 *   contract of DataTable (or its old flags fit, fold); the state is priority 1
 * @param {{range, note?, pagination?}} p.footer
 * @param {import('react').ReactNode} [p.error]  a LoadError in place of the table
 * @param {{key, asc}} [p.sort]  with onSort, the columns naming a `sort` key sort the list (the server's order); nameSort for the name
 * @param {ReturnType<import('./useClientList').useClientList>} [p.list]  a list sorted and paged in memory: its rows, sort and
 *   pagination take the place of rows, sort, onSort and footer.pagination
 * @param {string} [p.storageKey]  where the widths set by hand are kept; by default a key of the page and its columns
 * @param {string} [p.scrollId]  the region's id, its own where several lists share a page (the settings)
 */
export function ListView({ filters, label, caption, icon, rows: allRows, rowKey, title, status, columns, openedId, onOpen, footer, toolbar, loading, empty, error, selection, rowActions, sort: serverSort, onSort: serverOnSort, nameSort, nameExtra, list, storageKey, scrollId = 'module-scroll' }) {
  const { t } = useTranslation()
  const rows = list ? list.rows : allRows
  const sort = list ? list.sort : serverSort
  const onSort = list ? list.onSort : serverOnSort
  const foot = footer && (list?.pagination && !footer.pagination ? { ...footer, pagination: list.pagination } : footer)
  // A list that declares the column contract (priority) gives the state priority 1; otherwise the old flag keeps it
  const migrated = columns.some((c) => c.priority !== undefined)
  const cols = [
    { id: 'name', label: t('atelier.name'), entity: true, icon: () => icon, cell: title, sort: nameSort, extra: nameExtra, skeleton: { base: 55, spread: 35 } },
    ...columns.map((c, i) => (c.status
      ? { id: 'status', label: t('atelier.state'), cell: status, sort: c.sort, ...(migrated ? { kind: 'fit', priority: 1 } : { fold: c.fold ?? false }), skeleton: { width: '74px', kind: 'pill' } }
      : {
        id: c.id || `col-${i}`, label: c.label, labelFull: c.labelFull, cell: c.cell, grow: !!c.grow, tone: c.muted ? 'muted' : undefined, fit: c.fit, title: c.title,
        sort: c.sort, fold: c.fold, kind: c.kind, priority: c.priority, labelled: c.labelled,
      })),
  ]
  const card = (row) => ({ meta: cardFacts(cols, row), status: columns.some((c) => c.status) ? status(row) : undefined })
  return (
    <>
      {filters && <StateFilters {...filters} busy={loading && !rows?.length} />}
      <section className="table-workspace module-workspace" aria-label={label}>
        {toolbar}
        {error || (
          <DataTable kind="module" scrollId={scrollId} label={t('atelier.tableOf', { name: label })} caption={caption}
            columns={cols} rows={rows} rowKey={rowKey} rowLabel={title} sort={sort} onSort={onSort} onOpen={onOpen} openedId={openedId} loading={loading} empty={empty}
            openLabel={(row) => t('atelier.openDetail', { name: title(row) })} card={card} selection={selection} rowActions={rowActions}
            footer={foot && <TableFooter {...foot} />} widthsKey={storageKey} />
        )}
      </section>
    </>
  )
}

export default ListView
