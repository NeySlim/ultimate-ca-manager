/**
 * The headers and the sort of the lists (DataTable, useSortParam): a separator between data headers,
 * the sign of every sortable column, two states kept in the address with a default sort, the sort said to a screen
 * reader, the journal's static header, and on a phone the sort from the toolbar and the facts named by their column.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within, renderHook } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'

const size = vi.hoisted(() => ({ isMobile: false }))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, p) => (p ? `${k} ${JSON.stringify(p)}` : k), i18n: { language: 'en' } }),
}))
vi.mock('../../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: size.isMobile }) }))

import { DataTable } from '../DataTable'
import { ListView } from '../ListView'
import { cardFacts } from '../cardFacts'
import { useSortParam } from '../useSortParam'
import { useClientList } from '../useClientList'

beforeEach(() => { size.isMobile = false })

const rows = [{ id: 1, name: 'b-vpn', ca: 'Root', certs: 3 }, { id: 2, name: 'a-api', ca: 'Issuing', certs: 12 }]
const columns = [
  { id: 'name', label: 'Nom', kind: 'entity', priority: 1, sort: 'name', cell: (r) => r.name },
  { id: 'ca', label: 'Émetteur', kind: 'text', priority: 2, sort: 'ca', cell: (r) => r.ca },
  { id: 'note', label: 'Note', kind: 'text', priority: 4, grow: true, cell: () => 'n' },
  { id: 'certs', label: 'Certificats', kind: 'number', priority: 3, sort: 'certs', cell: (r) => r.certs },
]
const DEFAULT = { key: 'name', asc: true }

function Loc() {
  const location = useLocation()
  return <output data-testid="loc">{location.search}</output>
}
function List({ initial = DEFAULT, ...props }) {
  const { sort, onSort } = useSortParam(initial, ['name', 'ca', 'certs'])
  return <DataTable columns={columns} rows={rows} rowLabel={(r) => r.name} onOpen={() => {}} sort={sort} onSort={onSort} caption="Liste" {...props} />
}
const at = (url, ui = <List />) => render(<MemoryRouter initialEntries={[url]}>{ui}<Loc /></MemoryRouter>)
const sortOf = (name) => screen.getByRole('columnheader', { name }).getAttribute('aria-sort')
const loc = () => screen.getByTestId('loc').textContent

describe('the headers', () => {
  it('a separator closes each data header but the last, the column\'s handle on every list; none in the body', () => {
    const { container } = render(<DataTable columns={columns} rows={rows} onOpen={() => {}} />)
    expect([...container.querySelectorAll('thead th')].map((th) => th.querySelectorAll(':scope > .col-sep').length)).toEqual([1, 1, 1, 0, 0])
    expect(container.querySelector('thead .col-sep')).toHaveAttribute('role', 'separator')
    expect(container.querySelector('tbody .col-sep')).toBeNull()
    // A column labelled for screen readers only is an action: a plain separator, no handle
    const action = { id: 'run', label: <span className="sr-only">Actions</span>, kind: 'fit', priority: 1, cell: () => 'x' }
    const { container: other } = render(<DataTable columns={[...columns.slice(0, 1), action, ...columns.slice(1)]} rows={rows} />)
    const sep = other.querySelectorAll('thead th')[1].querySelector(':scope > .col-sep')
    expect(sep).toHaveAttribute('aria-hidden', 'true')
    expect(sep).not.toHaveAttribute('role')
  })

  it('no separator before a column of buttons at the end: the last labelled column closes the row', () => {
    const run = { id: 'run', label: <span className="sr-only">Actions</span>, kind: 'fit', priority: 1, cell: () => 'x' }
    const { container } = render(<DataTable columns={[...columns, run]} rows={rows} columnWidths={{}} onColumnWidth={() => {}} />)
    expect([...container.querySelectorAll('thead th')].map((th) => th.querySelectorAll(':scope > .col-sep').length)).toEqual([1, 1, 1, 0, 0])
    expect(container.querySelectorAll('thead th')[4].querySelector('[role=separator]')).toBeNull()
  })

  it('in a list whose widths are set by hand, the grip is the separator', () => {
    const { container } = render(<DataTable columns={columns} rows={rows} columnWidths={{}} onColumnWidth={() => {}} />)
    const grips = [...container.querySelectorAll('thead th > .col-resize')]
    expect(grips.map((g) => g.classList.contains('col-sep'))).toEqual([true, true, true, false])
    expect(container.querySelectorAll('thead th > .col-sep:not(.col-resize)')).toHaveLength(0)
  })

  it('a sortable column shows its solid sign, the sorted one an arrow with its shaft, a column that does not sort neither', () => {
    render(<DataTable columns={columns} rows={rows} sort={{ key: 'certs', asc: false }} onSort={() => {}} />)
    const head = (name) => screen.getByRole('columnheader', { name })
    const idle = head('Émetteur').querySelector('button[data-sort=ca] svg.sort-idle')
    expect(idle).toHaveAttribute('aria-hidden', 'true')
    // A glyph painted solid, not a stroke of 0.8 px
    expect([idle.getAttribute('fill'), idle.getAttribute('stroke')]).toEqual(['currentColor', 'none'])
    const arrow = head('Certificats').querySelector('button svg')
    expect(arrow).toHaveClass('sort-arrow')
    expect(arrow).not.toHaveClass('sort-idle')
    // Descending: a shaft down and its head, not a chevron
    expect(arrow.querySelector('path').getAttribute('d')).toBe('M12 5v14m-6-6 6 6 6-6')
    expect(head('Note').querySelector('button, svg')).toBeNull()
    expect(head('Note')).not.toHaveAttribute('aria-sort')
  })

  it('without onSort, the sorted column of a journal shows its arrow and aria-sort, with no button', () => {
    render(<DataTable kind="audit" columns={[{ id: 'time', label: 'Heure', sort: 'time', cell: () => '10:00' }, { id: 'msg', label: 'Message', cell: () => 'm' }]}
      rows={rows} sort={{ key: 'time', asc: false }} />)
    const time = screen.getByRole('columnheader', { name: 'Heure' })
    expect(time).toHaveAttribute('aria-sort', 'descending')
    expect(within(time).queryByRole('button')).toBeNull()
    expect(time.querySelector('svg')).not.toBeNull()
    expect(screen.getByRole('columnheader', { name: 'Message' })).not.toHaveAttribute('aria-sort')
  })

  it('a short label names the whole one in its accessible name and in the title that says the click', () => {
    render(<DataTable columns={[columns[0], { id: 'next', label: 'Proch. MàJ', labelFull: 'Prochaine mise à jour', kind: 'fit', priority: 2, sort: 'next', cell: () => 'x' }]}
      rows={rows} sort={DEFAULT} onSort={() => {}} />)
    const button = screen.getByRole('button', { name: 'Prochaine mise à jour' })
    expect(button).toHaveAttribute('title', 'table.sortByColumn {"column":"Prochaine mise à jour"}')
    expect(button).toHaveTextContent('Proch. MàJ')
  })

  it('each sort button says what a click does: sort by its column, or reverse the sort it shows', () => {
    render(<DataTable columns={columns} rows={rows} sort={{ key: 'name', asc: true }} onSort={() => {}} />)
    expect(screen.getByRole('button', { name: 'Émetteur' })).toHaveAttribute('title', 'table.sortByColumn {"column":"Émetteur"}')
    expect(screen.getByRole('button', { name: 'Nom' }))
      .toHaveAttribute('title', 'table.sortedByReverse {"column":"Nom","order":"table.sortAscending"}')
  })
})

describe('the sort kept in the address', () => {
  it('opens on the default sort, writes nothing for it, and says in the caption that the headers sort', () => {
    const { container } = at('/list')
    expect(sortOf('Nom')).toBe('ascending')
    expect(container.querySelectorAll('th[aria-sort=ascending], th[aria-sort=descending]')).toHaveLength(1)
    expect(loc()).toBe('')
    expect(container.querySelector('caption')).toHaveTextContent('Liste table.sortHint')
  })

  it('three clicks on a header: ascending, descending, ascending; back to page one, the focus kept on the button', () => {
    at('/list?page=3&q=vpn')
    const button = screen.getByRole('button', { name: 'Émetteur' })
    button.focus()
    fireEvent.click(button)
    expect(sortOf('Émetteur')).toBe('ascending')
    expect(sortOf('Nom')).toBe('none')
    expect(loc()).toBe('?q=vpn&sort=ca&order=asc')
    fireEvent.click(screen.getByRole('button', { name: 'Émetteur' }))
    expect(sortOf('Émetteur')).toBe('descending')
    expect(loc()).toBe('?q=vpn&sort=ca&order=desc')
    fireEvent.click(screen.getByRole('button', { name: 'Émetteur' }))
    expect(sortOf('Émetteur')).toBe('ascending')
    expect(document.activeElement).toBe(button)
    // Back on the default: nothing in the address
    fireEvent.click(screen.getByRole('button', { name: 'Nom' }))
    expect(loc()).toBe('?q=vpn')
  })

  it('says each change of sort in a polite live region', () => {
    const { container } = at('/list')
    const live = container.querySelector('[aria-live=polite]')
    expect(live).toHaveTextContent('')
    fireEvent.click(screen.getByRole('button', { name: 'Certificats' }))
    expect(live).toHaveTextContent('table.sortedBy {"column":"Certificats","order":"table.sortAscending"}')
    fireEvent.click(screen.getByRole('button', { name: 'Certificats' }))
    expect(live).toHaveTextContent('"order":"table.sortDescending"')
  })

  it('an address with a sort opens the list sorted; an unknown key falls back on the default', () => {
    const { unmount } = at('/list?sort=certs&order=desc')
    expect(sortOf('Certificats')).toBe('descending')
    unmount()
    at('/list?sort=nope&order=desc')
    expect(sortOf('Nom')).toBe('ascending')
  })

  it('two lists on one page keep their sorts apart under their own scope, and leave the page number alone', () => {
    function Two() {
      const a = useSortParam(DEFAULT, ['name', 'ca', 'certs'], { scope: 'tasks' })
      const b = useSortParam({ key: 'certs', asc: false }, ['name', 'certs'], { scope: 'backup' })
      return (
        <>
          <DataTable columns={columns} rows={rows} sort={a.sort} onSort={a.onSort} />
          <output data-testid="b">{`${b.sort.key}:${b.sort.asc}`}</output>
          <button type="button" onClick={() => b.onSort('name')}>b-name</button>
        </>
      )
    }
    at('/settings?tab=x&page=2&backup-sort=name&backup-order=desc', <Two />)
    expect(sortOf('Nom')).toBe('ascending')
    expect(screen.getByTestId('b')).toHaveTextContent('name:false')
    fireEvent.click(screen.getByRole('button', { name: 'Émetteur' }))
    expect(loc()).toBe('?tab=x&page=2&backup-sort=name&backup-order=desc&tasks-sort=ca&tasks-order=asc')
    fireEvent.click(screen.getByText('b-name'))
    expect(loc()).toBe('?tab=x&page=2&tasks-sort=ca&tasks-order=asc&backup-sort=name&backup-order=asc')
    expect(screen.getByTestId('b')).toHaveTextContent('name:true')
    expect(sortOf('Émetteur')).toBe('ascending')
  })

  it('a default sort descending is read and written as such', () => {
    at('/list', <List initial={{ key: 'certs', asc: false }} />)
    expect(sortOf('Certificats')).toBe('descending')
    fireEvent.click(screen.getByRole('button', { name: 'Certificats' }))
    expect(loc()).toBe('?sort=certs&order=asc')
    fireEvent.click(screen.getByRole('button', { name: 'Certificats' }))
    expect(loc()).toBe('')
  })

  it('a list that sorts declares its default', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => at('/list', <List initial={null} />)).toThrow(/default sort/)
    console.error.mockRestore()
  })

  it('a list sorted in memory follows the address and goes back to page one', () => {
    const items = Array.from({ length: 30 }, (_, i) => ({ id: i + 1, n: i + 1 }))
    const wrapper = ({ children }) => <MemoryRouter initialEntries={['/x?sort=n&order=desc']}>{children}</MemoryRouter>
    const { result } = renderHook(() => {
      const sortParam = useSortParam({ key: 'n', asc: true }, ['n'])
      return useClientList(items, { sorts: { n: (r) => r.n }, sortParam, perPage: 10, sizes: [10] })
    }, { wrapper })
    expect(result.current.sort).toEqual({ key: 'n', asc: false })
    expect(result.current.rows[0].n).toBe(30)
  })
})

describe('on a phone', () => {
  beforeEach(() => { size.isMobile = true })
  const card = () => ({ meta: [] })

  it('the toolbar sorts by the same state as the headers: a select of the sortable columns and a button that reverses', () => {
    at('/list', <List card={card} scrollId="x" />)
    const select = screen.getByRole('combobox', { name: 'table.sortBy' })
    expect(select).toHaveClass('filter-select')
    expect([...select.options].map((o) => o.value)).toEqual(['name', 'ca', 'certs'])
    expect(select.closest('.toolbar')).toHaveClass('mobile-sort')
    fireEvent.change(select, { target: { value: 'certs' } })
    expect(loc()).toBe('?sort=certs&order=asc')
    // The button shows the direction with an arrow and says it, and that a click reverses it
    const reverse = screen.getByRole('button', { name: 'table.ascendingReverse' })
    expect(reverse).toHaveAttribute('title', 'table.ascendingReverse')
    expect(reverse.querySelector('svg.sort-arrow path').getAttribute('d')).toBe('M12 19V5m-6 6 6-6 6 6')
    fireEvent.click(reverse)
    expect(loc()).toBe('?sort=certs&order=desc')
    expect(screen.getByRole('button', { name: 'table.descendingReverse' }).querySelector('svg.sort-arrow')).not.toBeNull()
    // The records follow the rows given, sorted by the list
    expect(document.querySelectorAll('article.mobile-record')).toHaveLength(2)
  })

  it('the toolbar names the columns by their whole label, the headers\' short one aside', () => {
    const cols = columns.map((c) => (c.id === 'certs' ? { ...c, label: 'Certs', labelFull: 'Certificats émis' } : c))
    render(<DataTable columns={cols} rows={rows} card={card} sort={DEFAULT} onSort={() => {}} />)
    expect([...screen.getByRole('combobox', { name: 'table.sortBy' }).options].map((o) => o.textContent)).toEqual([
      'table.sortByColumn {"column":"Nom"}', 'table.sortByColumn {"column":"Émetteur"}', 'table.sortByColumn {"column":"Certificats émis"}'])
  })

  it('a list that does not sort has no such toolbar', () => {
    render(<DataTable columns={columns.map(({ sort: _sort, ...c }) => c)} rows={rows} card={card} />)
    expect(screen.queryByRole('combobox')).toBeNull()
  })

  it('a record shows the facts of priority 2 then 3, a date or a number after its label, nothing absent', () => {
    const cols = [
      { id: 'name', entity: true, label: 'Nom', cell: (r) => r.name },
      { id: 'number', label: 'CRL', kind: 'text', priority: 3, cell: () => 'n° 9' },
      { id: 'published', label: 'Publiée', kind: 'fit', priority: 3, labelled: true, cell: () => '19 nov. 2026' },
      { id: 'next', label: 'Prochaine mise à jour', kind: 'fit', priority: 2, labelled: true, cell: () => '26 nov. 2026' },
      { id: 'ocsp', label: 'OCSP', kind: 'fit', priority: 4, cell: () => 'Actif' },
      { id: 'certs', label: 'Certificats', kind: 'number', priority: 2, cell: () => '—' },
    ]
    const facts = cardFacts(cols, {})
    const { container } = render(<div>{facts.map((f, i) => <span key={i}>{f}</span>)}</div>)
    expect([...container.querySelectorAll('div > span')].map((s) => s.textContent)).toEqual(['Prochaine mise à jour 26 nov. 2026', 'n° 9', 'Publiée 19 nov. 2026'])
    // A short header's whole label names the fact
    const short = cardFacts(cols.map((c) => (c.id === 'next' ? { ...c, label: 'Échéance' , labelFull: 'Prochaine mise à jour' } : c)), {})
    const { container: other } = render(<div>{short.map((f, i) => <span key={i}>{f}</span>)}</div>)
    expect(other.querySelector('.fact-label')).toHaveTextContent('Prochaine mise à jour')
    // The column's name in its own span, muted beside its value
    expect([...container.querySelectorAll('.fact-label')].map((s) => s.textContent)).toEqual(['Prochaine mise à jour', 'Publiée'])
  })

  it('a module list draws those facts in its records', () => {
    render(
      <MemoryRouter>
        <ListView label="CRL" icon="crl" rows={rows} title={(r) => r.name} status={() => 'ok'} onOpen={() => {}}
          columns={[{ id: 'certs', label: 'Certificats', kind: 'number', priority: 3, cell: (r) => r.certs }, { status: true }]} />
      </MemoryRouter>,
    )
    expect(document.querySelector('article .row-meta > span')).toHaveTextContent('Certificats 3')
  })
})
