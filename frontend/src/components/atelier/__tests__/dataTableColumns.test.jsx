/**
 * The width of the list columns (DataTable): a short fixed-format column takes its content's width and never
 * gives way; a free-text column (the name, a column naming its whole text in a title) shortens by an ellipsis,
 * the widest first, before any column folds; a width set by hand never clips a fixed-format cell.
 * jsdom has no layout: a header is as wide as its column's natural width, or the ceiling its cells carry; a growing
 * description takes what is left, 64 px at least, its text 200 px wide; the region's scroll width is the sum of its headers.
 */
import { describe, it, expect, vi, beforeAll, afterAll, beforeEach } from 'vitest'
import { render } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k) => k, i18n: { language: 'fr' } }),
}))
vi.mock('../../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: false }) }))

import { DataTable } from '../DataTable'
import { cedeWidths, CEDE_FLOOR } from '../columnShare'

const room = { width: 1000 }
const NATURAL = { name: 300, ca: 240, status: 80, expiry: 130, key: 90, short: 110 }
const ACTIONS = 40
const GROW_TEXT = 200
// A column's width: its natural one, down to the ceiling set on its first cell
const widthOf = (th) => {
  const id = th.className.match(/col-(\w+)/)?.[1]
  if (!id) return ACTIONS
  if (id === 'description') {
    const others = [...th.parentElement.children].filter((h) => h !== th).reduce((sum, h) => sum + widthOf(h), 0)
    return Math.max(64, room.width - others)
  }
  const index = [...th.parentElement.children].indexOf(th)
  const cell = th.closest('table').querySelector('tbody tr')?.children[index]
  const cap = parseFloat(cell?.style.maxWidth)
  return Number.isNaN(cap) ? NATURAL[id] : Math.min(NATURAL[id], cap)
}
const saved = {}
// The name's line (its button and its marks) and its button alone
const marks = { line: 0, button: 0 }
beforeAll(() => {
  // No padding in the cells: jsdom's own 1 px would add to the name's floor
  saved.style = document.head.appendChild(Object.assign(document.createElement('style'), { textContent: 'td, th { padding: 0 }' }))
  saved.offset = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetWidth')
  Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {
    configurable: true,
    get() { return this.classList?.contains('entity-name') ? marks.button : 0 },
  })
  saved.client = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'clientWidth')
  saved.scroll = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollWidth')
  saved.rect = HTMLElement.prototype.getBoundingClientRect
  saved.RO = global.ResizeObserver
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
    configurable: true,
    get() { return this.classList?.contains('table-scroll') ? room.width : 0 },
  })
  Object.defineProperty(HTMLElement.prototype, 'scrollWidth', {
    configurable: true,
    get() {
      if (this.classList?.contains('description-cell')) return GROW_TEXT
      if (this.classList?.contains('entity-line')) return marks.line
      if (!this.classList?.contains('table-scroll')) return 0
      return Math.max(room.width, [...this.querySelectorAll('thead th')].reduce((sum, th) => sum + widthOf(th), 0))
    },
  })
  HTMLElement.prototype.getBoundingClientRect = function rect() {
    const width = this.tagName === 'TH' ? widthOf(this) : 0
    return { width, height: 0, top: 0, left: 0, right: width, bottom: 0, x: 0, y: 0 }
  }
  global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
})
afterAll(() => {
  for (const [name, d] of [['clientWidth', saved.client], ['scrollWidth', saved.scroll], ['offsetWidth', saved.offset]]) {
    if (d) Object.defineProperty(HTMLElement.prototype, name, d); else delete HTMLElement.prototype[name]
  }
  HTMLElement.prototype.getBoundingClientRect = saved.rect
  saved.style.remove()
  global.ResizeObserver = saved.RO
})
beforeEach(() => { room.width = 1000; marks.line = 0; marks.button = 0 })

const rows = [{ id: 1, name: 'a-long-name.example.com', ca: 'UCM Production Intermediate CA' }, { id: 2, name: 'b.example.com', ca: 'UCM Root' }]
const columns = [
  { id: 'name', label: 'Nom', entity: true, cell: (r) => r.name },
  { id: 'status', label: 'État', fold: false, cell: () => <span className="pill">ok</span> },
  { id: 'ca', label: 'Émetteur', fold: 4, cell: (r) => r.ca, title: (r) => r.ca },
  { id: 'expiry', label: 'Expiration', fold: 3, cell: () => <span className="expiry-cell">14 déc. 2026<span className="remaining">22 j</span></span> },
  { id: 'key', label: 'Clé', fold: 7, cell: () => 'RSA 2048' },
]
const table = (props = {}) => (
  <DataTable kind="certificates" columns={columns} rows={rows} rowLabel={(r) => r.name} onOpen={() => {}} {...props} />
)
const heads = (c) => [...c.querySelectorAll('thead th')].map((th) => th.className.match(/col-(\w+)/)?.[1] || '·')
const cap = (c, id) => {
  const index = heads(c).indexOf(id)
  return c.querySelector('tbody tr').children[index].style.maxWidth
}

describe('the share of the columns', () => {
  it('fits a fixed-format column and the actions to their content; a free-text column shares the rest', () => {
    const { container } = render(table())
    const fit = Object.fromEntries([...container.querySelectorAll('thead th')].map((th, i) => [heads(container)[i], th.classList.contains('fit')]))
    expect(fit).toEqual({ name: false, status: true, ca: false, expiry: true, key: true, '·': true })
  })

  it('shortens a free-text cell by an ellipsis, its whole text in a title; the name keeps its marks beside it', () => {
    const { container } = render(table({ columns: columns.map((c) => (c.entity ? { ...c, extra: () => <span className="key-presence" /> } : c)) }))
    const ca = container.querySelector('tbody tr').children[heads(container).indexOf('ca')]
    expect(ca).toHaveClass('text-cell')
    expect(ca).toHaveAttribute('title', 'UCM Production Intermediate CA')
    const line = container.querySelector('tbody td.entity-cell > .entity-line')
    expect(line.querySelector('button.entity-name > .entity-label')).toHaveAttribute('title', 'a-long-name.example.com')
    expect(line.lastElementChild).toHaveClass('key-presence')
    expect(container.querySelector('tbody td:not(.text-cell):not(.entity-cell)')).not.toHaveAttribute('title')
  })

  it('a module description without a title of its own names its text in one', () => {
    const { container } = render(
      <DataTable kind="module" rows={rows} rowLabel={(r) => r.name} onOpen={() => {}}
        columns={[columns[0], { id: 'note', label: 'Description', grow: true, cell: (r) => `Issued by ${r.ca}` }]} />,
    )
    expect(container.querySelector('tbody td.description-cell')).toHaveAttribute('title', 'Issued by UCM Production Intermediate CA')
  })

  it('a width set by hand narrows a free-text column, never a fixed-format one', () => {
    const { container } = render(table({ columnWidths: { ca: 160, expiry: 60 }, onColumnWidth: () => {} }))
    expect(cap(container, 'ca')).toBe('160px')
    expect(cap(container, 'expiry')).toBe('')
    const th = container.querySelectorAll('thead th')[heads(container).indexOf('expiry')]
    expect(th.style.width).toBe('60px')
    // The header holds its label: no ceiling under it
    expect(th.style.maxWidth).toBe('')
  })
})

describe('a list short of room', () => {
  it('the widest free-text column gives way first, then both, and nothing folds while that is enough', () => {
    // 300 + 80 + 240 + 130 + 90 + 40 = 880 px; 800 px of room: the name comes down to the issuer, then both share
    room.width = 800
    const { container } = render(<div id="app" className="dock-right">{table()}</div>)
    expect(heads(container)).toEqual(['name', 'status', 'ca', 'expiry', 'key', '·'])
    expect(cap(container, 'name')).toBe('230px')
    expect(cap(container, 'ca')).toBe('230px')
    expect(cap(container, 'expiry')).toBe('')
  })

  it('a name that also takes the room left (the Authorities list) gives way as well', () => {
    room.width = 800
    const { container } = render(<div id="app" className="dock-right">{table({ columns: [{ ...columns[0], grow: true }, ...columns.slice(1)] })}</div>)
    expect(cap(container, 'name')).toBe('230px')
    expect(cap(container, 'ca')).toBe('230px')
  })

  it('beside the right dock, folds a column only once the free text is at its floor, then gives the room back', () => {
    // At the floor: 2 × 120 + 80 + 130 + 90 + 40 = 580 > 500: the key folds, and the free text gives way again from its natural width
    room.width = 500
    const { container } = render(<div id="app" className="dock-right">{table()}</div>)
    expect(heads(container)).toEqual(['name', 'status', 'ca', 'expiry', '·'])
    expect(cap(container, 'name')).toBe('125px')
    expect(cap(container, 'ca')).toBe('125px')
  })

  it('with the dock below, gives way down to the floor and folds nothing', () => {
    room.width = 500
    const { container } = render(<div id="app">{table()}</div>)
    expect(heads(container)).toEqual(['name', 'status', 'ca', 'expiry', 'key', '·'])
    expect(cap(container, 'name')).toBe(`${CEDE_FLOOR}px`)
    expect(cap(container, 'ca')).toBe(`${CEDE_FLOOR}px`)
  })

  it('the name keeps room for its marks besides the floor of its text', () => {
    // Its marks take 150 px of its 300: it stops at 270 while the issuer goes down to the floor
    room.width = 500
    marks.line = 300
    marks.button = 150
    const { container } = render(<div id="app">{table()}</div>)
    expect(cap(container, 'name')).toBe('270px')
    expect(cap(container, 'ca')).toBe(`${CEDE_FLOOR}px`)
  })

  it('with room to spare, leaves every column whole', () => {
    const { container } = render(<div id="app" className="dock-right">{table()}</div>)
    expect(cap(container, 'name')).toBe('')
    expect(cap(container, 'ca')).toBe('')
  })
})

describe('a description squeezed under its floor', () => {
  const described = (cols) => cols.flatMap((c) => (c.id === 'status'
    ? [{ id: 'description', label: 'Description', grow: true, fold: 5, cell: () => 'A description of two hundred pixels' }, c] : [c]))

  it('makes the free text give way although the table fits', () => {
    // 880 px of other columns in 950: the description would keep 70 px; the name gives 50 to bring it to 120
    room.width = 950
    const { container } = render(<div id="app" className="dock-right">{table({ columns: described(columns) })}</div>)
    expect(heads(container)).toEqual(['name', 'description', 'status', 'ca', 'expiry', 'key', '·'])
    expect(cap(container, 'name')).toBe('250px')
  })

  it('beside the right dock, folds a column when no free text can give way', () => {
    // A short name (110 px) cannot give way: the key folds and the description has its 120 px
    room.width = 520
    const cols = described([{ ...columns[0], id: 'short' }, columns[1], columns[3], columns[4]])
    const { container } = render(<div id="app" className="dock-right">{table({ columns: cols })}</div>)
    expect(heads(container)).toEqual(['short', 'description', 'status', 'expiry', '·'])
  })
})

describe('cedeWidths', () => {
  it('lowers one ceiling from the widest column down, to the floor at most', () => {
    expect(cedeWidths({ name: 300, ca: 240, key: 90 }, 40)).toEqual({ name: 260 })
    expect(cedeWidths({ name: 300, ca: 240, key: 90 }, 80)).toEqual({ name: 230, ca: 230 })
    expect(cedeWidths({ name: 300, ca: 240 }, 1000)).toEqual({ name: CEDE_FLOOR, ca: CEDE_FLOOR })
    expect(cedeWidths({ key: 90 }, 50)).toBeNull()
  })
})
