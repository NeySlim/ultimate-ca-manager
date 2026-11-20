/**
 * ResponsiveDataTable variant="list": rows of one fixed height, a column that
 * absorbs the width so a name is not cut, one action and a chevron per row, a
 * checkbox that selects without opening, a footer that says the range in words.
 * A table that does not ask for the variant keeps its structure.
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
const device = vi.hoisted(() => ({ mobile: false }))
vi.mock('../../../../contexts', () => ({
  useMobile: () => ({ isMobile: device.mobile, isTablet: false, isDesktop: !device.mobile }),
}))

import { ResponsiveDataTable } from '../ResponsiveDataTable'
import { blockedWhileSuspended } from '../../../../components/shell/__tests__/writeGuardProbe'

const LONG = 'a-very-long-common-name-that-used-to-be-cut.internal.example.com'
const ROWS = [
  { id: 1, name: LONG, note: 'Front door of the shop, renamed by an operator', issuer: 'Issuing CA 1', grade: 'A' },
  { id: 2, name: 'api.example.com', note: '', issuer: 'Issuing CA 2', grade: 'B' },
]
const COLUMNS = [
  { key: 'name', header: 'Name', priority: 1, render: (val) => <button type="button">{val}</button> },
  { key: 'note', header: 'Note', grow: true, muted: true, hideOnMobile: true },
  { key: 'issuer', header: 'Issuer', priority: 2, maxWidth: 200, sortable: false },
  { key: 'grade', header: 'Grade', defaultHidden: true, hideOnMobile: true },
]

function Harness({ onSelection, ...props }) {
  const [ids, setIds] = useState(() => new Set())
  return (
    <ResponsiveDataTable
      variant="list"
      data={ROWS}
      columns={COLUMNS}
      rowLabel={(row) => row.name}
      tableLabel="List of things"
      multiSelect
      selectedIds={ids}
      onSelectionChange={(next) => { setIds(next); onSelection?.(next) }}
      bulkActions={<button type="button">Compare</button>}
      {...props}
    />
  )
}

const row = (name) => screen.getByRole('row', { name: new RegExp(name.replace(/\./g, '\\.')) })
const cells = (r) => within(r).getAllByRole('cell')

beforeEach(() => {
  window.localStorage.clear()
  device.mobile = false
})

describe('ResponsiveDataTable variant="list": rows', () => {
  it('keeps every row to one line: each cell holds a single fixed-height box', () => {
    render(<Harness onRowClick={() => {}} rowActions={() => [{ label: 'Export', onClick: () => {} }]} />)
    for (const name of [LONG, 'api.example.com']) {
      const data = cells(row(name)).filter((td) => !td.matches('.lv-col-check, .lv-col-actions'))
      expect(data).toHaveLength(3)
      data.forEach((td) => {
        expect(td.children).toHaveLength(1)
        expect(td.firstElementChild.matches('div.lv-cell, div.lv-clip')).toBe(true)
      })
    }
  })

  it('never cuts the name: the column flagged grow absorbs the width instead', () => {
    render(<Harness />)
    const [, name, note, issuer] = cells(row(LONG))
    expect(name).toHaveTextContent(LONG)
    expect(name).not.toHaveClass('is-clipped')
    expect(name.querySelector('.truncate, .lv-clip')).toBeNull()
    expect(name.style.maxWidth).toBe('')
    expect(note).toHaveClass('lv-grow', 'is-clipped')
    expect(issuer).not.toHaveClass('lv-grow')
    expect(screen.getAllByRole('columnheader').filter((th) => th.matches('.lv-grow')).map((th) => th.textContent)).toEqual(['Note'])
  })

  it('lets a fill column shorten its own content, with a floor, and caps go through variables', () => {
    const columns = [
      { key: 'name', header: 'Name', grow: true, fill: true, minWidth: 160, render: (val) => <button type="button">{val}</button> },
      { key: 'note', header: 'Note', maxWidth: 320, narrowMaxWidth: 150 },
      { key: 'issuer', header: 'Issuer', maxWidth: 200 },
    ]
    render(<Harness columns={columns} />)
    const [, name, note] = cells(row(LONG))
    expect(name).toHaveClass('lv-grow')
    expect(name.firstElementChild.matches('div.lv-cell.lv-fill')).toBe(true)
    expect(name.style.getPropertyValue('--lv-min')).toBe('160px')
    expect(note).toHaveClass('lv-capped', 'is-clipped')
    expect(note.style.getPropertyValue('--lv-max')).toBe('320px')
    expect(note.style.getPropertyValue('--lv-max-narrow')).toBe('150px')
    // The header of the grow column is the name, never the note
    expect(screen.getAllByRole('columnheader').filter((th) => th.matches('.lv-grow')).map((th) => th.textContent)).toEqual(['Name'])
  })

  it('gives a clipped cell its whole text on hover', () => {
    render(<Harness />)
    const [, , note, issuer] = cells(row(LONG))
    expect(note.firstElementChild).toHaveAttribute('title', 'Front door of the shop, renamed by an operator')
    expect(issuer).toHaveClass('lv-capped')
    expect(issuer.style.getPropertyValue('--lv-max')).toBe('200px')
    expect(issuer.firstElementChild).toHaveAttribute('title', 'Issuing CA 1')
    // Nothing to tell for an empty cell
    expect(cells(row('api.example.com'))[2].firstElementChild).not.toHaveAttribute('title')
  })

  it('shows the actions of the row as buttons, then the chevron that opens it', () => {
    const onRowClick = vi.fn()
    const onExport = vi.fn()
    render(<Harness onRowClick={onRowClick} rowActions={(r) => [{ label: 'Export', onClick: () => onExport(r.id) }]} />)
    const buttons = within(row('api.example.com')).getAllByRole('button').filter((b) => b.matches('.lv-icon-btn'))
    expect(buttons.map((b) => b.title)).toEqual(['Export', 'table.open'])
    expect(buttons[0]).toHaveAttribute('aria-label', 'table.rowAction:{"action":"Export","name":"api.example.com"}')
    expect(buttons[1]).toHaveAttribute('aria-label', 'table.openRow:{"name":"api.example.com"}')
    fireEvent.click(buttons[0])
    expect(onExport).toHaveBeenCalledWith(2)
    expect(onRowClick).not.toHaveBeenCalled()
    fireEvent.click(buttons[1])
    expect(onRowClick).toHaveBeenCalledTimes(1)
    expect(onRowClick).toHaveBeenCalledWith(ROWS[1])
  })

  it('opens from the row and from the name inside it', () => {
    const onRowClick = vi.fn()
    render(<Harness onRowClick={onRowClick} />)
    fireEvent.click(cells(row('api.example.com'))[3])
    fireEvent.click(within(row('api.example.com')).getByRole('button', { name: 'api.example.com' }))
    expect(onRowClick.mock.calls.map(([r]) => r.id)).toEqual([2, 2])
  })

  it('has no chevron and no action column on a table that opens nothing', () => {
    render(<Harness />)
    expect(screen.queryByTitle('table.open')).toBeNull()
    expect(document.querySelector('.lv-col-actions')).toBeNull()
  })

  it('marks the row whose detail is open', () => {
    render(<Harness onRowClick={() => {}} selectedId={2} />)
    expect(row('api.example.com')).toHaveClass('is-opened')
    expect(row(LONG)).not.toHaveClass('is-opened')
  })

  it('names the table and its scrolling region', () => {
    render(<Harness />)
    expect(screen.getByRole('table', { name: 'List of things' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'List of things' })).toHaveAttribute('tabindex', '0')
  })
})

describe('ResponsiveDataTable variant="list": selection', () => {
  it('ticks a row without opening it and shows the batch bar', () => {
    const onRowClick = vi.fn()
    const onSelection = vi.fn()
    render(<Harness onRowClick={onRowClick} onSelection={onSelection} />)
    expect(screen.queryByRole('group', { name: 'table.selection' })).toBeNull()
    const box = within(row('api.example.com')).getByRole('checkbox')
    expect(box).toHaveAttribute('aria-label', 'table.selectRow:{"name":"api.example.com"}')
    fireEvent.click(box)
    expect([...onSelection.mock.calls[0][0]]).toEqual([2])
    expect(onRowClick).not.toHaveBeenCalled()
    expect(row('api.example.com')).toHaveClass('is-checked')
    const bar = screen.getByRole('group', { name: 'table.selection' })
    expect(bar).toHaveTextContent('table.selectedCount:{"count":1}')
    expect(within(bar).getByText('Compare')).toBeInTheDocument()
  })

  it('does not open the row from the cell around the checkbox', () => {
    const onRowClick = vi.fn()
    render(<Harness onRowClick={onRowClick} />)
    fireEvent.click(cells(row('api.example.com'))[0])
    expect(onRowClick).not.toHaveBeenCalled()
  })

  it('ticks and clears the page from the header, and clears from the bar', () => {
    const onSelection = vi.fn()
    render(<Harness onSelection={onSelection} />)
    const all = screen.getByRole('checkbox', { name: 'table.selectPage' })
    fireEvent.click(all)
    expect([...onSelection.mock.lastCall[0]]).toEqual([1, 2])
    expect(all).toBeChecked()
    fireEvent.click(within(screen.getByRole('group', { name: 'table.selection' })).getByText('table.clearSelection'))
    expect([...onSelection.mock.lastCall[0]]).toEqual([])
    expect(screen.queryByRole('group', { name: 'table.selection' })).toBeNull()
  })

  it('has no checkbox on a page without bulk actions', () => {
    render(<ResponsiveDataTable variant="list" data={ROWS} columns={COLUMNS} />)
    expect(screen.queryByRole('checkbox')).toBeNull()
  })
})

describe('ResponsiveDataTable variant="list": header, toolbar and footer', () => {
  it('announces the sort of a column and leaves a fixed one without a button', () => {
    const onSortChange = vi.fn()
    render(<Harness sortable onSortChange={onSortChange} />)
    const [, name, , issuer] = screen.getAllByRole('columnheader')
    expect(name).toHaveAttribute('aria-sort', 'none')
    expect(issuer).not.toHaveAttribute('aria-sort')
    expect(within(issuer).queryByRole('button')).toBeNull()
    fireEvent.click(within(name).getByRole('button', { name: 'Name' }))
    expect(onSortChange).toHaveBeenLastCalledWith({ key: 'name', direction: 'asc' })
    expect(screen.getAllByRole('columnheader')[1]).toHaveAttribute('aria-sort', 'ascending')
  })

  it('searches from a field whose placeholder names what is searched', () => {
    const onSearchChange = vi.fn()
    render(<Harness searchable searchPlaceholder="Name, note, issuer…" externalSearch="" onSearchChange={onSearchChange} />)
    const field = screen.getByRole('searchbox', { name: 'common.search' })
    expect(field).toHaveAttribute('placeholder', 'Name, note, issuer…')
    fireEvent.change(field, { target: { value: 'api' } })
    expect(onSearchChange).toHaveBeenCalledWith('api')
  })

  it('offers the columns under a visible label and keeps the choice', () => {
    render(<Harness searchable columnStorageKey="test-columns" />)
    // The modal dialog hides the page from the accessibility tree while it is open
    const headers = () => screen.getAllByRole('columnheader', { hidden: true }).map((th) => th.textContent).filter(Boolean)
    // A column flagged defaultHidden waits in the menu
    expect(headers()).toEqual(['Name', 'Note', 'Issuer'])
    const button = screen.getByRole('button', { name: 'table.columns' })
    expect(button).toHaveAttribute('aria-haspopup', 'dialog')
    fireEvent.click(button)
    const dialog = screen.getByRole('dialog', { name: 'table.columnsDialogTitle' })
    fireEvent.click(within(dialog).getByRole('checkbox', { name: 'Grade' }))
    expect(headers()).toEqual(['Name', 'Note', 'Issuer', 'Grade'])
    expect(JSON.parse(window.localStorage.getItem('test-columns'))).toEqual([])
    fireEvent.click(within(dialog).getByRole('button', { name: 'table.done' }))
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('does not offer a column that always shows', () => {
    render(<Harness searchable columnStorageKey="test-columns-2" columns={[{ ...COLUMNS[0], alwaysVisible: true }, ...COLUMNS.slice(1)]} />)
    fireEvent.click(screen.getByRole('button', { name: 'table.columns' }))
    const dialog = screen.getByRole('dialog', { name: 'table.columnsDialogTitle' })
    expect(within(dialog).getAllByRole('checkbox').map((c) => c.closest('label').textContent)).toEqual(['Note', 'Issuer', 'Grade'])
  })

  it('lets a saved choice of columns win over the default', () => {
    window.localStorage.setItem('test-columns', JSON.stringify(['issuer']))
    render(<Harness columnStorageKey="test-columns" />)
    expect(screen.getAllByRole('columnheader').map((th) => th.textContent).filter(Boolean)).toEqual(['Name', 'Note', 'Grade'])
  })

  it('keeps a filter without control out of the toolbar and in the chips', () => {
    const onChange = vi.fn()
    render(
      <Harness
        searchable
        toolbarFilters={[
          { key: 'state', label: 'State', type: 'multiSelect', hideControl: true, value: ['a', 'b'], onChange,
            options: [{ value: 'a', label: 'Alpha' }, { value: 'b', label: 'Beta' }] },
          { key: 'issuer', label: 'Issuer', type: 'multiSelect', value: [], onChange: () => {}, placeholder: 'All issuers', options: [] },
        ]}
      />,
    )
    const toolbar = document.querySelector('.lv-toolbar')
    expect(within(toolbar).getByRole('button', { name: 'All issuers' })).toBeInTheDocument()
    expect(within(toolbar).queryByText(/State|common\.all\b/)).toBeNull()
    const chip = screen.getAllByText('State:')[0].parentElement
    expect(chip).toHaveTextContent('State:Alpha')
    fireEvent.click(within(chip).getByRole('button'))
    expect(onChange).toHaveBeenCalledWith(['b'])
  })

  it('says the range in the words of the page, with the page size and the pages', () => {
    const onChange = vi.fn()
    render(
      <Harness
        rangeLabel={({ start, end, total }) => `${start}–${end} of ${total} things`}
        pagination={{ page: 2, total: 276, perPage: 12, pageSizes: [12, 25, 50, 100], onChange, onPerPageChange: () => {} }}
      />,
    )
    const footer = document.querySelector('footer.lv-footer')
    expect(footer).toHaveTextContent('13–24 of 276 things')
    // Beyond twenty pages, a page number to jump to
    const jump = within(footer).getByRole('spinbutton', { name: 'table.pageNumber' })
    expect(jump).toHaveValue(2)
    expect(footer).toHaveTextContent('table.pageOf:{"total":23}')
    const size = within(footer).getByRole('combobox', { name: 'table.perPageLabel' })
    expect([...size.options].map((o) => o.value)).toEqual(['12', '25', '50', '100'])
    expect(size).toHaveValue('12')
    fireEvent.click(within(footer).getByRole('button', { name: 'table.nextPage' }))
    fireEvent.click(within(footer).getByRole('button', { name: 'table.previousPage' }))
    expect(onChange.mock.calls).toEqual([[3], [1]])
    fireEvent.change(jump, { target: { value: '40' } })
    fireEvent.click(within(footer).getByRole('button', { name: 'table.goToPage' }))
    expect(onChange).toHaveBeenLastCalledWith(23)
  })

  it('counts the pages without a jump up to twenty pages', () => {
    render(<Harness pagination={{ page: 2, total: 240, perPage: 12, onChange: () => {} }} />)
    const footer = document.querySelector('footer.lv-footer')
    expect(footer).toHaveTextContent('2 / 20')
    expect(within(footer).queryByRole('spinbutton')).toBeNull()
  })

  it('says under the table what stays open, the row height and the columns on screen', () => {
    render(<Harness footNote="Open things stay in the inspector." />)
    const caption = screen.getByTestId('list-caption')
    expect(caption).toHaveTextContent('Open things stay in the inspector.')
    expect(caption).toHaveTextContent('table.rowsNote:{"px":36,"count":')
  })

  it('falls back to the plain range and stops at the ends', () => {
    render(<Harness pagination={{ page: 1, total: 2, perPage: 25, onChange: () => {} }} />)
    const footer = document.querySelector('footer.lv-footer')
    expect(footer).toHaveTextContent('table.range:{"start":1,"end":2,"total":2}')
    expect(within(footer).getByRole('button', { name: 'table.previousPage' })).toBeDisabled()
    expect(within(footer).getByRole('button', { name: 'table.nextPage' })).toBeDisabled()
  })

  it('draws skeleton rows while loading, and says so', () => {
    render(<Harness loading />)
    expect(screen.getByRole('status')).toHaveTextContent('table.loadingRows')
    expect(document.querySelector('.lv-scroll')).toHaveAttribute('aria-busy', 'true')
    const rows = document.querySelectorAll('tbody tr.lv-sk-row')
    expect(rows.length).toBe(12)
    expect(rows[0].querySelectorAll('.lv-sk').length).toBeGreaterThan(2)
    expect(screen.queryByText('api.example.com')).toBeNull()
  })
})

describe('ResponsiveDataTable variant="list" on a phone', () => {
  beforeEach(() => { device.mobile = true })

  it('keeps the cards: a tap opens, the checkbox selects', () => {
    const onRowClick = vi.fn()
    const onSelection = vi.fn()
    render(<Harness onRowClick={onRowClick} onSelection={onSelection} />)
    expect(screen.queryByRole('table')).toBeNull()
    fireEvent.click(screen.getByText('api.example.com'))
    expect(onRowClick).toHaveBeenCalledWith(ROWS[1])
    expect(onSelection).not.toHaveBeenCalled()
    fireEvent.click(screen.getAllByRole('checkbox')[2])
    expect([...onSelection.mock.lastCall[0]]).toEqual([2])
    expect(onRowClick).toHaveBeenCalledTimes(1)
  })
})

describe('ResponsiveDataTable without the variant', () => {
  const mount = (props) => render(
    <ResponsiveDataTable
      data={ROWS} columns={COLUMNS} searchable columnStorageKey="test-columns"
      onRowClick={() => {}} rowActions={() => [{ label: 'Export', onClick: () => {} }]}
      pagination={{ page: 1, total: 276, perPage: 25, onChange: () => {}, onPerPageChange: () => {} }}
      {...props}
    />,
  )

  it('keeps its structure: none of the list template reaches it', () => {
    const { container } = mount()
    expect(container.querySelector('[class*="lv-"]')).toBeNull()
    expect(screen.queryByTitle('table.open')).toBeNull()
    expect(screen.queryByRole('checkbox')).toBeNull()
    expect(screen.queryByRole('searchbox')).toBeNull()
    expect(screen.getByRole('textbox')).toBeInTheDocument()
    // The columns button stays the icon alone
    expect(screen.getByTitle('table.customizeColumns')).toHaveTextContent('')
  })

  it('keeps the row click on its own behaviour with a selection: the row ticks', () => {
    const onRowClick = vi.fn()
    const onSelectionChange = vi.fn()
    device.mobile = true
    mount({ onRowClick, multiSelect: true, selectedIds: new Set(), onSelectionChange })
    device.mobile = false
    fireEvent.click(screen.getByText('api.example.com'))
    expect(onRowClick).not.toHaveBeenCalled()
    expect([...onSelectionChange.mock.lastCall[0]]).toEqual([2])
    expect(screen.getByText('common.selectAll')).toBeInTheDocument()
  })

  it('says its range through the translations', () => {
    mount()
    expect(screen.getByText('table.range:{"start":1,"end":25,"total":276}')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'table.nextPage' })).toBeEnabled()
  })

  it('honours defaultHidden too', () => {
    mount()
    expect(screen.getAllByRole('columnheader').map((th) => th.textContent).filter(Boolean)).not.toContain('Grade')
  })
})

describe('ResponsiveDataTable page jump and the write guard', () => {
  it('leaves Go enabled while writes are suspended: going to a page only reads', () => {
    render(<Harness pagination={{ page: 2, total: 276, perPage: 12, onChange: () => {}, onPerPageChange: () => {} }} />)
    expect(blockedWhileSuspended(screen.getByRole('button', { name: 'table.goToPage' }))).toBe(false)
  })
})

describe('ResponsiveDataTable phone filter strip', () => {
  const FILTERS = ['All CAs', 'All sources', 'All templates'].map((placeholder, i) => ({
    key: `f${i}`, type: 'multiSelect', value: [], onChange: () => {}, placeholder, options: [{ value: 'a', label: 'A' }],
  }))
  const phone = (props) => render(<Harness searchable searchLabel="Search" toolbarFilters={FILTERS}
    card={(r) => ({ description: r.note })} exportEnabled {...props} />)
  beforeEach(() => { device.mobile = true })

  it('on a phone, an opted-in toolbar lines its filters in a strip that keeps every one of them', () => {
    phone({ mobileFilterStrip: true })
    const tools = document.querySelector('.lv-toolbar .lv-tools')
    expect(tools).toHaveClass('is-strip')
    expect(within(tools).getAllByRole('button').map((b) => b.textContent)).toEqual(['All CAs', 'All sources', 'All templates'])
    // The export button stays outside the strip, after it: the mockup's place
    const exportButton = screen.getByRole('button', { name: 'table.exportData' })
    expect(tools.contains(exportButton)).toBe(false)
    expect(tools.compareDocumentPosition(exportButton) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('keeps the shared behaviour elsewhere: no strip without the option, nor on a wide screen', () => {
    const { unmount } = phone()
    expect(document.querySelector('.lv-toolbar .lv-tools')).not.toHaveClass('is-strip')
    unmount()
    device.mobile = false
    phone({ mobileFilterStrip: true })
    expect(document.querySelector('.lv-toolbar .lv-tools')).not.toHaveClass('is-strip')
  })
})
