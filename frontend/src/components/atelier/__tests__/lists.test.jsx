/**
 * The lists of the mockup beyond Certificats: one density for every list (the class `comfortable`
 * on #app, M:1108), and the sort and the pages a module list keeps in memory when its API sends it whole.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within, act } from '@testing-library/react'
import { renderHook } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, p) => (p ? `${k} ${JSON.stringify(p)}` : k), i18n: { language: 'en' } }),
}))
vi.mock('../../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: false }) }))
vi.mock('../../shell/bannersSlot', () => ({ useShellBanners: () => null }))

import { Zone } from '../Zone'
import { TableView } from '../TableView'
import { ListView } from '../ListView'
import { useClientList } from '../useClientList'

beforeEach(() => { localStorage.clear() })

const columns = [{ id: 'name', label: 'Nom', entity: true, cell: (r) => r.name }]
const rows = [{ id: 1, name: 'a' }]
const moduleCols = [{ id: 'n', label: 'N', cell: (r) => r.n, sort: 'n' }]

describe('one density for every list', () => {
  it('turns every zone comfortable from the Certificats toggle, and keeps it', () => {
    const certs = render(
      <Zone><TableView label="Liste" storageKey="ucm-certs-table" density columns={columns} rows={rows} search={null} /></Zone>,
    )
    const app = () => document.querySelector('#app')
    expect(app()).not.toHaveClass('comfortable')
    fireEvent.click(screen.getByRole('button', { name: 'table.densityComfortable' }))
    expect(app()).toHaveClass('comfortable')
    expect(certs.container.querySelector('.table-caption')).toHaveTextContent('"px":44')
    certs.unmount()
    // Another page, a module list without the toggle: the same rows
    const users = render(
      <Zone><ListView label="Users" icon="users" rows={[{ id: 1, n: 'x' }]} title={(r) => r.n} status={() => null} columns={moduleCols} footer={{ range: '1' }} /></Zone>,
    )
    expect(users.container.querySelector('#app')).toHaveClass('comfortable')
    users.unmount()
    render(<Zone><TableView label="Liste" storageKey="ucm-operations" density columns={columns} rows={rows} search={null} /></Zone>)
    const toggle = screen.getByRole('button', { name: 'table.densityComfortable' })
    expect(toggle).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(toggle)
    expect(app()).not.toHaveClass('comfortable')
  })
  it('follows a change made while two lists are on screen', () => {
    render(<>
      <Zone><TableView label="Liste" density columns={columns} rows={rows} search={null} /></Zone>
      <Zone testId="other"><p>other</p></Zone>
    </>)
    fireEvent.click(screen.getByRole('button', { name: 'table.densityComfortable' }))
    expect(screen.getByTestId('other').querySelector('.zone-app')).toHaveClass('comfortable')
  })
})

const items = Array.from({ length: 30 }, (_, i) => ({ id: i + 1, n: `item ${i + 1}`, size: (i * 7) % 30, when: i % 5 ? `2026-01-${String(i + 1).padStart(2, '0')}` : null }))

describe('a module list sorted and paged in memory', () => {
  const sorts = { n: (r) => r.n, size: (r) => r.size, when: (r) => r.when }
  it('shows the first page of 25, then the next, and sorts from page one again', () => {
    const { result } = renderHook(({ list }) => useClientList(list, { sorts }), { initialProps: { list: items } })
    expect(result.current.rows).toHaveLength(25)
    expect(result.current.paged).toBe(true)
    expect(result.current.pagination).toMatchObject({ page: 1, pages: 2, perPage: 25 })
    act(() => result.current.pagination.onPage(2))
    expect(result.current.rows.map((r) => r.id)).toEqual([26, 27, 28, 29, 30])
    expect([result.current.start, result.current.end, result.current.total]).toEqual([26, 30, 30])
    act(() => result.current.onSort('size'))
    expect(result.current.sort).toEqual({ key: 'size', asc: true })
    expect(result.current.pagination.page).toBe(1)
    expect(result.current.rows[0].size).toBe(0)
    act(() => result.current.onSort('size'))
    expect(result.current.sort).toEqual({ key: 'size', asc: false })
    expect(result.current.rows[0].size).toBe(29)
  })
  it('compares names as words with numbers, and leaves the empty values last both ways', () => {
    const { result } = renderHook(() => useClientList(items, { sorts, perPage: 100 }))
    act(() => result.current.onSort('n'))
    expect(result.current.rows.slice(0, 3).map((r) => r.n)).toEqual(['item 1', 'item 2', 'item 3'])
    act(() => result.current.onSort('when'))
    expect(result.current.rows.slice(-7).map((r) => r.when)).toEqual(['2026-01-30', null, null, null, null, null, null])
    act(() => result.current.onSort('when'))
    expect(result.current.rows[0].when).toBe('2026-01-30')
    expect(result.current.rows.at(-1).when).toBeNull()
  })
  it('keeps the order of the API until a header is clicked, and starts from an initial sort when given', () => {
    const plain = renderHook(() => useClientList(items, { sorts }))
    expect(plain.result.current.sort).toBeNull()
    expect(plain.result.current.rows[0].id).toBe(1)
    const sorted = renderHook(() => useClientList(items, { sorts, initial: { key: 'size', asc: false } }))
    expect(sorted.result.current.rows[0].size).toBe(29)
  })
  it('changes the page size from page one, has no controls under the smallest page, and goes back to page one on a new filter', () => {
    const { result, rerender } = renderHook(({ list, k }) => useClientList(list, { sorts, resetKey: k }), { initialProps: { list: items, k: '' } })
    act(() => result.current.pagination.onPage(2))
    act(() => result.current.pagination.onPerPage(10))
    expect(result.current.pagination).toMatchObject({ page: 1, pages: 3, perPage: 10 })
    act(() => result.current.pagination.onPage(3))
    rerender({ list: items.slice(0, 22), k: 'q' })
    expect(result.current.pagination.page).toBe(1)
    rerender({ list: items.slice(0, 8), k: 'q2' })
    expect(result.current.paged).toBe(false)
    expect(result.current.pagination).toBeUndefined()
    expect(result.current.rows).toHaveLength(8)
  })
  it('stays on the last page when rows leave it', () => {
    const { result, rerender } = renderHook(({ list }) => useClientList(list, { sorts, perPage: 10 }), { initialProps: { list: items } })
    act(() => result.current.pagination.onPage(3))
    rerender({ list: items.slice(0, 15) })
    expect(result.current.pagination.page).toBe(2)
    expect(result.current.rows.map((r) => r.id)).toEqual([11, 12, 13, 14, 15])
  })
})

describe('the list template with a list kept in memory', () => {
  function Page({ list: rowsIn }) {
    const list = useClientList(rowsIn, { sorts: { name: (r) => r.n, size: (r) => r.size } })
    return (
      <ListView label="Mod" icon="crl" list={list} title={(r) => r.n} status={() => null} nameSort="name"
        columns={[{ id: 'size', label: 'Size', cell: (r) => r.size, sort: 'size' }]}
        footer={{ range: `${list.start}-${list.end} / ${list.total}` }} />
    )
  }
  it('sorts from its headers and pages from its footer', () => {
    const { container } = render(<Page list={items} />)
    expect(container.querySelectorAll('tbody tr')).toHaveLength(25)
    const footer = container.querySelector('footer.table-footer')
    expect(footer).toHaveTextContent('1-25 / 30')
    fireEvent.click(within(footer).getByRole('button', { name: 'table.nextPage' }))
    expect(container.querySelectorAll('tbody tr')).toHaveLength(5)
    expect(footer).toHaveTextContent('26-30 / 30')
    fireEvent.click(screen.getByRole('button', { name: 'Size' }))
    expect(screen.getByRole('columnheader', { name: 'Size' })).toHaveAttribute('aria-sort', 'ascending')
    expect(footer).toHaveTextContent('1-25 / 30')
    expect(container.querySelector('tbody tr td:nth-child(2)')).toHaveTextContent('0')
    fireEvent.click(screen.getByRole('button', { name: 'atelier.name' }))
    expect(screen.getByRole('columnheader', { name: 'atelier.name' })).toHaveAttribute('aria-sort', 'ascending')
    expect(container.querySelector('tbody tr .entity-name')).toHaveTextContent('item 1')
    expect(within(footer).getByRole('combobox', { name: 'table.perPageLabel' })).toHaveValue('25')
  })
})
