/**
 * The table of the Atelier lists (tableView, listView, activity): its kinds, sorting, selection
 * (page box, mixed state, names and actions waiting while rows are ticked), opening by the name,
 * the chevron or the row, row actions, skeleton rows, the empty block, the phone records and the
 * width of a column set by hand. Then the list section around it (TableView): columns, density.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'

const size = vi.hoisted(() => ({ isMobile: false }))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, p) => (p ? `${k} ${JSON.stringify(p)}` : k), i18n: { language: 'fr' } }),
}))
vi.mock('../../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: size.isMobile }) }))

import { DataTable } from '../DataTable'
import { TableView } from '../TableView'

const rows = [{ id: 1, name: 'vpn.example.com', ca: 'Services CA' }, { id: 2, name: 'api.example.com', ca: 'Services CA' }]
const columns = [
  { id: 'name', label: 'Nom commun', sort: 'name', entity: true, icon: () => 'cert', cell: (r) => r.name },
  { id: 'description', label: 'Description', grow: true, tone: 'muted', cell: () => 'desc', title: () => 'desc' },
  { id: 'ca', label: 'Émetteur', sort: 'ca', tone: 'muted', cell: (r) => r.ca },
]
const sel = (selected, extra = {}) => ({ selected: new Set(selected), onToggle: vi.fn(), onTogglePage: vi.fn(), ...extra })

beforeEach(() => { size.isMobile = false; localStorage.clear() })

describe('the table', () => {
  it('draws the mockup table of its kind', () => {
    const { container, rerender } = render(<DataTable kind="certificates" scrollId="cert-scroll" label="Tableau" caption="Cap" columns={columns} rows={rows} rowLabel={(r) => r.name} />)
    expect(container.querySelector('.table-container > #cert-scroll.table-scroll[role=region][tabindex="0"]')).toHaveAttribute('aria-label', 'Tableau')
    expect(container.querySelector('table.cert-table caption.sr-only')).toHaveTextContent('Cap')
    expect([...container.querySelectorAll('thead th')].map((th) => th.className)).toEqual(['col-name', 'col-description', 'col-ca fit'])
    expect(container.querySelector('tbody td.entity-cell > .entity-line > button.entity-name')).toHaveTextContent('vpn.example.com')
    expect(container.querySelector('tbody td.description-cell.muted')).toHaveAttribute('title', 'desc')
    rerender(<DataTable kind="module" columns={columns} rows={rows} rowLabel={(r) => r.name} onOpen={() => {}} />)
    expect(container.querySelector('table')).toHaveClass('cert-table', 'module-table')
    expect([...container.querySelectorAll('thead th')].map((th) => th.className)).toEqual(['', 'col-description', 'fit', 'fit'])
    expect(container.querySelector('tbody td .table-actions > button.icon-btn:not(.quiet)')).not.toBeNull()
    rerender(<DataTable kind="audit" columns={columns.map((c) => (c.entity ? { ...c, entity: false, resource: true } : c))} rows={rows} rowLabel={(r) => r.name} onOpen={() => {}} />)
    expect(container.querySelector('.table-container')).toHaveClass('audit-container')
    expect(container.querySelector('.table-container').style.marginBottom).toBe('20px')
    expect(container.querySelector('tbody td > button.resource')).toHaveTextContent('vpn.example.com')
    expect(container.querySelector('tbody td > button.icon-btn.quiet')).not.toBeNull()
  })
  it('sorts by a column: aria-sort on every sortable header, the arrow on the sorted one', () => {
    const onSort = vi.fn()
    render(<DataTable columns={columns} rows={rows} sort={{ key: 'name', asc: false }} onSort={onSort} />)
    const headers = screen.getAllByRole('columnheader')
    expect(headers.map((h) => h.getAttribute('aria-sort'))).toEqual(['descending', null, 'none'])
    expect(within(headers[0]).getByRole('button').querySelector('svg')).not.toBeNull()
    expect(within(headers[2]).getByRole('button').querySelector('svg')).toBeNull()
    fireEvent.click(within(headers[2]).getByRole('button', { name: 'Émetteur' }))
    expect(onSort).toHaveBeenCalledWith('ca')
  })
  it('ticks rows and the page, the page box mixed while some are ticked', () => {
    const s = sel([2])
    const { container } = render(<DataTable columns={columns} rows={rows} rowLabel={(r) => r.name} selection={s} onOpen={() => {}} />)
    const page = screen.getByRole('checkbox', { name: 'table.selectPage' })
    expect(page.indeterminate).toBe(true)
    expect(page).not.toBeChecked()
    fireEvent.click(page)
    expect(s.onTogglePage).toHaveBeenCalledWith(true)
    fireEvent.click(screen.getByRole('checkbox', { name: 'table.selectRow {"name":"vpn.example.com"}' }))
    expect(s.onToggle).toHaveBeenCalledWith(1)
    expect(container.querySelectorAll('tbody tr')[1]).toHaveClass('checked')
  })
  it('holds the names, row actions and chevrons while rows are ticked', () => {
    const onOpen = vi.fn(); const act = vi.fn()
    const { rerender } = render(<DataTable columns={columns} rows={rows} rowLabel={(r) => r.name} selection={sel([1])} onOpen={onOpen}
      rowActions={() => [{ icon: 'download', label: 'Exporter', onClick: act }]} />)
    expect(screen.getByRole('button', { name: 'api.example.com' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'table.rowAction {"action":"Exporter","name":"api.example.com"}' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'table.openRow {"name":"api.example.com"}' })).toBeDisabled()
    rerender(<DataTable columns={columns} rows={rows} rowLabel={(r) => r.name} selection={sel([])} onOpen={onOpen}
      rowActions={() => [{ icon: 'download', label: 'Exporter', onClick: act }]} />)
    fireEvent.click(screen.getByRole('button', { name: 'api.example.com' }))
    fireEvent.click(screen.getByRole('button', { name: 'table.openRow {"name":"vpn.example.com"}' }))
    fireEvent.click(screen.getByRole('button', { name: 'table.rowAction {"action":"Exporter","name":"api.example.com"}' }))
    expect(onOpen.mock.calls.map(([r]) => r.id)).toEqual([2, 1])
    expect(act).toHaveBeenCalledWith(rows[1])
  })
  it('opens from anywhere on the row only when asked, never from its controls twice', () => {
    const onOpen = vi.fn()
    const { container, rerender } = render(<DataTable columns={columns} rows={rows} rowLabel={(r) => r.name} onOpen={onOpen} />)
    fireEvent.click(container.querySelector('tbody td.description-cell'))
    expect(onOpen).not.toHaveBeenCalled()
    rerender(<DataTable columns={columns} rows={rows} rowLabel={(r) => r.name} onOpen={onOpen} rowOpens />)
    fireEvent.click(container.querySelector('tbody td.description-cell'))
    fireEvent.click(screen.getByRole('button', { name: 'api.example.com' }))
    expect(onOpen.mock.calls.map(([r]) => r.id)).toEqual([1, 2])
  })
  it('marks the open row', () => {
    const { container } = render(<DataTable columns={columns} rows={rows} openedId={2} />)
    expect(container.querySelectorAll('tbody tr')[1]).toHaveClass('opened')
    expect(container.querySelectorAll('tbody tr')[0]).not.toHaveClass('opened')
  })
  it('draws at most twelve skeleton rows, the first announcing the read, then the empty block', () => {
    const { container, rerender } = render(<DataTable columns={[...columns.slice(0, 2), { id: 's', label: 'État', cell: () => '', skeleton: { width: '74px', kind: 'pill' } }]}
      rows={[]} loading skeletonRows={50} selection={sel([])} onOpen={() => {}} empty={<p>vide</p>} />)
    const sk = container.querySelectorAll('tbody tr.sk-row')
    expect(sk).toHaveLength(12)
    expect(sk[0]).not.toHaveAttribute('aria-hidden')
    expect(within(sk[0]).getByRole('status')).toHaveTextContent('table.loadingRows')
    expect(sk[1]).toHaveAttribute('aria-hidden', 'true')
    expect(sk[0].querySelector('.sk.sk-box')).not.toBeNull()
    expect(sk[0].querySelector('.sk.sk-pill').style.width).toBe('74px')
    expect(container.querySelector('.table-container')).toHaveAttribute('aria-busy', 'true')
    expect(screen.queryByText('vide')).toBeNull()
    rerender(<DataTable columns={columns} rows={[]} selection={sel([])} onOpen={() => {}} empty={<p>vide</p>} />)
    expect(screen.getByText('vide').closest('td')).toHaveAttribute('colspan', '5')
  })
  it('sets a column width by hand and puts it back on a double click', () => {
    const onWidth = vi.fn()
    const { container } = render(<DataTable columns={columns} rows={rows} columnWidths={{ ca: 180 }} onColumnWidth={onWidth} />)
    const th = container.querySelectorAll('thead th')[2]
    expect(th.style.width).toBe('180px')
    fireEvent.doubleClick(th.querySelector('.col-resize'))
    expect(onWidth).toHaveBeenCalledWith('ca', null)
  })
})

describe('the records on a phone', () => {
  beforeEach(() => { size.isMobile = true })
  const card = (r) => ({ description: 'Desc', meta: [r.ca, null, 'ACME'], status: <span>Valide</span>, end: '11 nov.' })
  it('draws one record per row with its facts, and a chevron when the record opens', () => {
    const { container } = render(<DataTable columns={columns} rows={rows} rowLabel={(r) => r.name} card={card} onOpen={() => {}} recordsId="recs" />)
    expect(container.querySelector('table')).toBeNull()
    const rec = container.querySelectorAll('#recs.mobile-list > article.mobile-record.opens')
    expect(rec).toHaveLength(2)
    expect(within(rec[0]).getByText('Desc')).toHaveClass('row-description')
    expect([...rec[0].querySelectorAll('.row-meta > span')].map((s) => s.textContent)).toEqual(['Services CA', 'ACME'])
    expect(rec[0].querySelector('.row-status .remaining')).toHaveTextContent('11 nov.')
    expect(rec[0].querySelector('.row-top > .icon-btn:last-child')).toHaveAttribute('aria-label', 'table.openRow {"name":"vpn.example.com"}')
  })
  it('opens from anywhere on the record, the checkbox only ticks, nothing opens while rows are ticked', () => {
    const onOpen = vi.fn(); const s = sel([])
    const { container, rerender } = render(<DataTable columns={columns} rows={rows} rowLabel={(r) => r.name} card={card} onOpen={onOpen} selection={s} />)
    fireEvent.click(container.querySelector('article .row-description'))
    expect(onOpen).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: 'vpn.example.com' }))
    expect(onOpen).toHaveBeenCalledTimes(2)
    fireEvent.click(screen.getAllByRole('checkbox')[0])
    expect(onOpen).toHaveBeenCalledTimes(2)
    expect(s.onToggle).toHaveBeenCalledWith(1)
    rerender(<DataTable columns={columns} rows={rows} rowLabel={(r) => r.name} card={card} onOpen={onOpen} selection={sel([1])} />)
    fireEvent.click(container.querySelectorAll('article .row-description')[1])
    expect(onOpen).toHaveBeenCalledTimes(2)
    expect(container.querySelector('article')).toHaveClass('checked')
  })
  it('marks a module\'s open item as the mockup does, not a certificate\'s', () => {
    const { container, rerender } = render(<DataTable kind="module" columns={columns} rows={rows} card={card} openedId={2} />)
    expect(container.querySelectorAll('article')[1]).toHaveClass('checked')
    rerender(<DataTable kind="certificates" columns={columns} rows={rows} card={card} openedId={2} />)
    expect(container.querySelectorAll('article')[1]).not.toHaveClass('checked')
  })
  it('draws six skeleton records while the first read runs', () => {
    const { container } = render(<DataTable columns={columns} rows={[]} loading card={card} />)
    expect(container.querySelectorAll('article.mobile-record.sk-record')).toHaveLength(6)
  })
})

describe('the list section', () => {
  const cols = [...columns.map((c, i) => (i === 0 ? { ...c, always: true } : c)), { id: 'grade', label: 'Conformité', defaultHidden: true, cell: () => 'A' }]
  const view = (extra = {}) => render(<TableView label="Liste" tableLabel="Tableau" storageKey="t-list" columns={cols} rows={rows} rowLabel={(r) => r.name}
    search={<input aria-label="q" />} columnsDialog={{ note: 'Note' }} density exporter={{ label: 'Exporter la liste', onClick: extra.onExport }} captionNote="Ouverts" {...extra} />)
  it('hides and shows columns from the Colonnes dialog, keeps the choice, never lists those always shown', async () => {
    const { container, unmount } = view()
    expect(screen.queryByRole('columnheader', { name: 'Conformité' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'table.columns' }))
    const dialog = screen.getByRole('dialog', { name: 'table.columnsDialogTitle' })
    expect(within(dialog).queryByRole('checkbox', { name: 'Nom commun' })).toBeNull()
    fireEvent.click(within(dialog).getByRole('checkbox', { name: 'Conformité' }))
    fireEvent.click(within(dialog).getByRole('checkbox', { name: 'Émetteur' }))
    expect(screen.getByRole('columnheader', { name: 'Conformité' })).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'Émetteur' })).toBeNull()
    expect(container.querySelector('.table-caption')).toHaveTextContent('table.rowsNote {"px":36,"count":3}')
    await new Promise((r) => setTimeout(r, 250))
    unmount()
    view()
    expect(screen.getByRole('columnheader', { name: 'Conformité' })).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'Émetteur' })).toBeNull()
  })
  it('remembers that every column is shown, a default-hidden one included', async () => {
    const { unmount } = view()
    fireEvent.click(screen.getByRole('button', { name: 'table.columns' }))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('checkbox', { name: 'Conformité' }))
    await new Promise((r) => setTimeout(r, 250))
    unmount()
    view()
    expect(screen.getByRole('columnheader', { name: 'Conformité' })).toBeInTheDocument()
  })
  it('toggles the comfortable density, says the row height, and exports from the toolbar', () => {
    const onExport = vi.fn()
    const { container } = view({ onExport })
    const density = screen.getByRole('button', { name: 'table.densityComfortable' })
    expect(density).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(density)
    expect(density).toHaveAttribute('aria-pressed', 'true')
    // The class goes on the zone's #app, for every list (lists.test.jsx)
    expect(container.querySelector('section.table-workspace')).not.toHaveClass('comfortable')
    expect(container.querySelector('.table-caption')).toHaveTextContent('"px":44')
    fireEvent.click(screen.getByRole('button', { name: 'Exporter la liste' }))
    expect(onExport).toHaveBeenCalled()
    expect(screen.getByRole('region', { name: 'Liste' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Tableau' })).toBeInTheDocument()
  })
})
