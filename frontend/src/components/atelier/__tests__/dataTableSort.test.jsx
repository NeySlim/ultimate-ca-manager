/**
 * The headers and the sort of the lists (DataTable, useSortParam, COLONNES-SPEC G2): a separator between data headers,
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
  it('a separator closes each data header but the last; none in the body', () => {
    const { container } = render(<DataTable columns={columns} rows={rows} onOpen={() => {}} />)
    expect([...container.querySelectorAll('thead th')].map((th) => th.querySelectorAll(':scope > .col-sep').length)).toEqual([1, 1, 1, 0, 0])
    expect(container.querySelector('thead .col-sep')).toHaveAttribute('aria-hidden', 'true')
    expect(container.querySelector('tbody .col-sep')).toBeNull()
  })

  it('in a list whose widths are set by hand, the grip is the separator', () => {
    const { container } = render(<DataTable columns={columns} rows={rows} columnWidths={{}} onColumnWidth={() => {}} />)
    const grips = [...container.querySelectorAll('thead th > .col-resize')]
    expect(grips.map((g) => g.classList.contains('col-sep'))).toEqual([true, true, true, false])
    expect(container.querySelectorAll('thead th > .col-sep:not(.col-resize)')).toHaveLength(0)
  })

  it('a sortable column shows both arrows, the sorted one its direction, a column that does not sort neither', () => {
    render(<DataTable columns={columns} rows={rows} sort={{ key: 'certs', asc: false }} onSort={() => {}} />)
    const head = (name) => screen.getByRole('columnheader', { name })
    expect(head('Émetteur').querySelector('button[data-sort=ca] svg.sort-idle')).toHaveAttribute('aria-hidden', 'true')
    expect(head('Certificats').querySelector('button svg')).not.toHaveClass('sort-idle')
    expect(head('Note').querySelector('button, svg')).toBeNull()
    expect(head('Note')).not.toHaveAttribute('aria-sort')
  })

  it('without onSort, the sorted column of a journal shows its arrow and aria-sort, with no button (T7)', () => {
    render(<DataTable kind="audit" columns={[{ id: 'time', label: 'Heure', sort: 'time', cell: () => '10:00' }, { id: 'msg', label: 'Message', cell: () => 'm' }]}
      rows={rows} sort={{ key: 'time', asc: false }} />)
    const time = screen.getByRole('columnheader', { name: 'Heure' })
    expect(time).toHaveAttribute('aria-sort', 'descending')
    expect(within(time).queryByRole('button')).toBeNull()
    expect(time.querySelector('svg')).not.toBeNull()
    expect(screen.getByRole('columnheader', { name: 'Message' })).not.toHaveAttribute('aria-sort')
  })

  it('a short label names the whole one in its title and its accessible name', () => {
    render(<DataTable columns={[columns[0], { id: 'next', label: 'Proch. MàJ', labelFull: 'Prochaine mise à jour', kind: 'fit', priority: 2, sort: 'next', cell: () => 'x' }]}
      rows={rows} sort={DEFAULT} onSort={() => {}} />)
    const button = screen.getByRole('button', { name: 'Prochaine mise à jour' })
    expect(button).toHaveAttribute('title', 'Prochaine mise à jour')
    expect(button).toHaveTextContent('Proch. MàJ')
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
    fireEvent.click(screen.getByRole('button', { name: 'table.reverseSort' }))
    expect(loc()).toBe('?sort=certs&order=desc')
    // The records follow the rows given, sorted by the list
    expect(document.querySelectorAll('article.mobile-record')).toHaveLength(2)
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
      { id: 'certs', label: 'Certificats', kind: 'number', priority: 3, cell: () => '—' },
    ]
    const facts = cardFacts(cols, {})
    const { container } = render(<div>{facts.map((f, i) => <span key={i}>{f}</span>)}</div>)
    expect([...container.querySelectorAll('span')].map((s) => s.textContent)).toEqual(['Prochaine mise à jour 26 nov. 2026', 'n° 9', 'Publiée 19 nov. 2026'])
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
