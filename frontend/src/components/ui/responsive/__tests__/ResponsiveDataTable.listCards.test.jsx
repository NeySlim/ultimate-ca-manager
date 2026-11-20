/**
 * ResponsiveDataTable variant="list" on a phone: the Atelier records, one per row,
 * with a checkbox, the name that opens, the description, a line of facts, the state
 * and an end value; the footer stays under them with the page size and « page / pages ».
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { useState } from 'react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts ? `${key}:${JSON.stringify(opts)}` : key),
    i18n: { language: 'en', changeLanguage: () => {} },
  }),
}))
vi.mock('../../../../contexts', () => ({
  useMobile: () => ({ isMobile: true, isTablet: false, isDesktop: false }),
}))

import { ResponsiveDataTable } from '../ResponsiveDataTable'

const ROWS = [
  { id: 1, name: 'web.example.com', note: 'Front door', issuer: 'Issuing CA 1', state: 'Valid', due: '12 Mar 2027' },
  { id: 2, name: 'api.example.com', note: '', issuer: 'Issuing CA 2', state: 'Expired', due: '2 Jan 2026' },
]
const COLUMNS = [
  { key: 'name', header: 'Name', priority: 1 },
  { key: 'issuer', header: 'Issuer', priority: 2 },
]
const card = (row) => ({
  description: row.note,
  meta: [row.issuer, 'Manual'],
  status: <span className="lv-pill">{row.state}</span>,
  end: row.due,
})

function Harness({ onRowClick = () => {}, ...props }) {
  const [ids, setIds] = useState(() => new Set())
  return (
    <ResponsiveDataTable
      variant="list"
      data={ROWS}
      columns={COLUMNS}
      card={card}
      rowLabel={(row) => row.name}
      tableLabel="List of things"
      multiSelect
      selectedIds={ids}
      onSelectionChange={setIds}
      onRowClick={onRowClick}
      openFromName
      lockRowsOnSelect
      bulkActions={<button type="button">Compare</button>}
      pagination={{ page: 1, total: 276, perPage: 12, pageSizes: [12, 25, 50, 100], onChange: () => {}, onPerPageChange: () => {} }}
      {...props}
    />
  )
}

const record = (name) => screen.getAllByRole('listitem').find((li) => within(li).queryByRole('button', { name }))

beforeEach(() => { window.localStorage.clear() })

describe('ResponsiveDataTable variant="list" on a phone', () => {
  it('draws one record per row, no table', () => {
    render(<Harness />)
    expect(screen.queryByRole('table')).toBeNull()
    const list = screen.getByRole('list', { name: 'List of things' })
    expect(within(list).getAllByRole('listitem')).toHaveLength(2)
    const web = record('web.example.com')
    expect(web.querySelector('.lv-mrecord-desc')).toHaveTextContent('Front door')
    expect([...web.querySelectorAll('.lv-mrecord-meta > span')].map((s) => s.textContent)).toEqual(['Issuing CA 1', 'Manual'])
    expect(web.querySelector('.lv-mrecord-status')).toHaveTextContent('Valid12 Mar 2027')
    // No description: no empty paragraph
    expect(record('api.example.com').querySelector('.lv-mrecord-desc')).toBeNull()
  })

  it('opens from the name only, and ticks without opening', () => {
    const onRowClick = vi.fn()
    render(<Harness onRowClick={onRowClick} />)
    fireEvent.click(record('web.example.com'))
    expect(onRowClick).not.toHaveBeenCalled()
    fireEvent.click(within(record('web.example.com')).getByRole('button', { name: 'web.example.com' }))
    expect(onRowClick).toHaveBeenCalledWith(ROWS[0])
    onRowClick.mockClear()
    const box = within(record('api.example.com')).getByRole('checkbox', { name: 'table.selectRow:{"name":"api.example.com"}' })
    fireEvent.click(box)
    expect(box).toBeChecked()
    expect(record('api.example.com')).toHaveClass('is-checked')
    expect(onRowClick).not.toHaveBeenCalled()
    // While a selection is on, the names do not open
    expect(within(record('web.example.com')).getByRole('button', { name: 'web.example.com' })).toBeDisabled()
    expect(screen.getByRole('group', { name: 'table.selection' })).toHaveTextContent('table.selectedCount:{"count":1}')
  })

  it('keeps the footer: page size and page out of pages, without a page number field', () => {
    render(<Harness />)
    const footer = document.querySelector('footer.lv-footer')
    expect(within(footer).getByRole('combobox', { name: 'table.perPageLabel' })).toHaveValue('12')
    expect(footer).toHaveTextContent('1 / 23')
    expect(within(footer).queryByRole('spinbutton')).toBeNull()
  })

  it('shows the empty content inside the list', () => {
    render(<Harness data={[]} emptyTitle="Nothing yet" emptyDescription="Issue one." pagination={{ page: 1, total: 0, perPage: 12, onChange: () => {} }} />)
    expect(screen.getByTestId('list-empty')).toHaveTextContent('Nothing yet')
  })
})
