/**
 * The layout of a list in its region (DataTable, COLONNES-SPEC G1): one column takes the room left, the others are
 * fitted within their bounds, the columns fold by priority at any desktop width and the footer says how many, the
 * sorted column never folds, numbers read at the right, the checkbox column is 40 px, the open row is marked and kept
 * in view, the chevron and row actions are never hidden but the Certificates' Export.
 * jsdom has no layout: while the table measures (table.measuring) a header is as wide as its column's natural width,
 * 40 px for the checkbox and the actions; the region's client width is the room the test gives it.
 */
import { describe, it, expect, vi, beforeAll, afterAll, beforeEach } from 'vitest'
import { render, act, screen, fireEvent, within } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, p) => (p ? `${k} ${JSON.stringify(p)}` : k), i18n: { language: 'fr' } }),
}))
vi.mock('../../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: false }) }))

import { DataTable } from '../DataTable'
import { TableFooter } from '../TableFooter'
import { TableView } from '../TableView'
import { ListView } from '../ListView'
import { foldOrder, columnErrors } from '../columnShare'
import { certificateColumns } from '../../../pages/certificates/certificateRows'

const room = { width: 1400 }
const NATURAL = { name: 300, description: 400, status: 80, ca: 240, source: 70, expiry: 130, key: 90, certs: 50, a: 100, b: 100, c: 100 }
const observers = new Set()
const saved = {}
const narrow = (th) => !!th.querySelector('.sr-only, input')
const idOf = (th) => th.className.match(/col-(\w+)/)?.[1]
beforeAll(() => {
  saved.client = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'clientWidth')
  saved.rect = HTMLElement.prototype.getBoundingClientRect
  saved.RO = global.ResizeObserver
  saved.scroll = HTMLElement.prototype.scrollIntoView
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
    configurable: true,
    get() { return this.classList?.contains('table-scroll') ? room.width : 0 },
  })
  HTMLElement.prototype.getBoundingClientRect = function rect() {
    let width = 0
    if (this.tagName === 'TH') width = narrow(this) ? 40 : NATURAL[idOf(this)] ?? 100
    return { width, height: 0, top: 0, left: 0, right: width, bottom: 0, x: 0, y: 0 }
  }
  global.ResizeObserver = class {
    constructor(cb) { this.cb = cb }
    observe() { observers.add(this) }
    unobserve() {}
    disconnect() { observers.delete(this) }
  }
})
afterAll(() => {
  if (saved.client) Object.defineProperty(HTMLElement.prototype, 'clientWidth', saved.client); else delete HTMLElement.prototype.clientWidth
  HTMLElement.prototype.getBoundingClientRect = saved.rect
  HTMLElement.prototype.scrollIntoView = saved.scroll
  global.ResizeObserver = saved.RO
})
beforeEach(() => { room.width = 1400; observers.clear() })

const resize = (w) => act(() => { room.width = w; for (const o of [...observers]) o.cb([]) })
const heads = (c) => [...c.querySelectorAll('thead th')].map((th) => idOf(th) || '·')
const cellOf = (c, id) => c.querySelector('tbody tr').children[heads(c).indexOf(id)]
const headOf = (c, id) => c.querySelectorAll('thead th')[heads(c).indexOf(id)]
const rows = [{ id: 1, name: 'vpn.example.com', ca: 'UCM Production Intermediate CA' }, { id: 2, name: 'api.example.com', ca: 'UCM Root' }]
const columns = [
  { id: 'name', label: 'Nom', kind: 'entity', priority: 1, sort: 'name', cell: (r) => r.name },
  { id: 'description', label: 'Description', kind: 'text', priority: 4, grow: true, cell: () => 'desc' },
  { id: 'status', label: 'État', kind: 'fit', priority: 1, cell: () => <span className="pill">ok</span> },
  { id: 'ca', label: 'Émetteur', kind: 'text', priority: 2, sort: 'ca', cell: (r) => r.ca },
  { id: 'source', label: 'Source', kind: 'fit', priority: 3, cell: () => 'UCM' },
  { id: 'expiry', label: 'Expiration', kind: 'fit', priority: 2, sort: 'days', cell: () => '2027' },
  { id: 'key', label: 'Clé', kind: 'fit', priority: 3, sort: 'key', cell: () => 'RSA' },
]
const table = (props = {}) => (
  <DataTable kind="certificates" columns={columns} rows={rows} rowLabel={(r) => r.name} onOpen={() => {}}
    footer={<TableFooter range="1–2 sur 2" />} {...props} />
)

describe('one column takes the room left', () => {
  it('the growing description; every other column is fitted to its content', () => {
    const { container } = render(table())
    expect(heads(container)).toEqual(['name', 'description', 'status', 'ca', 'source', 'expiry', 'key', '·'])
    const fit = [...container.querySelectorAll('thead th')].map((th) => th.classList.contains('fit'))
    expect(fit).toEqual([true, false, true, true, true, true, true, true])
    expect(container.querySelector('table')).not.toHaveClass('measuring')
  })

  it('bounds no name nor text while the sum fits (R1); short of room, an ellipsis and its title after them', () => {
    const before = { ...NATURAL }
    Object.assign(NATURAL, { name: 520, ca: 410 })
    try {
      room.width = 2000
      const { container } = render(table())
      expect(cellOf(container, 'name').style.maxWidth).toBe('')
      expect(cellOf(container, 'ca').style.maxWidth).toBe('')
      expect(cellOf(container, 'ca')).toHaveClass('text-cell')
      expect(cellOf(container, 'ca')).toHaveAttribute('title', 'UCM Production Intermediate CA')
      // 1360 of room: the description at 64, the name and the issuer share the last 4 px above their comfort
      resize(1400)
      expect(parseFloat(cellOf(container, 'name').style.maxWidth)).toBeCloseTo(518.04, 1)
      expect(parseFloat(cellOf(container, 'ca').style.maxWidth)).toBeCloseTo(407.96, 1)
      expect(cellOf(container, 'expiry').style.maxWidth).toBe('')
    } finally { Object.assign(NATURAL, before) }
  })

  it('a text cell names its whole text in a title without the page asking; a fitted one does not', () => {
    const { container } = render(table())
    expect(cellOf(container, 'description')).toHaveAttribute('title', 'desc')
    expect(cellOf(container, 'source')).not.toHaveAttribute('title')
    expect(container.querySelector('tbody td.entity-cell .entity-label')).toHaveAttribute('title', 'vpn.example.com')
  })
})

describe('short of room, at any desktop width', () => {
  it('folds by priority, the description first, then the priority 3 columns from the right, and says how many', () => {
    // 560 of room (600 less the actions): at their comfort (280, 160) the columns still ask too much until the
    // description and the priority 3 columns are gone; then the name and the issuer share the shortfall
    room.width = 600
    const { container } = render(table())
    expect(heads(container)).toEqual(['name', 'status', 'ca', 'expiry', '·'])
    expect(headOf(container, 'name')).not.toHaveClass('fit')
    expect(cellOf(container, 'ca').style.maxWidth).toBe('120px')
    expect(cellOf(container, 'name').style.maxWidth).toBe('230px')
    const note = container.querySelector('.table-footer .folded-note')
    expect(note).toHaveTextContent('table.foldedColumns {"count":3}')
    expect(note).toHaveAttribute('title', 'Description, Source, Clé')
    // The chevron stays
    expect(container.querySelector('tbody tr button[aria-label^="table.openRow"]')).not.toBeNull()
  })

  it('unfolds as the region widens and folds again as it narrows; the mention goes with the folds', () => {
    room.width = 600
    const { container } = render(table())
    resize(1400)
    expect(heads(container)).toEqual(['name', 'description', 'status', 'ca', 'source', 'expiry', 'key', '·'])
    expect(container.querySelector('.folded-note')).toBeNull()
    // 810 of room: at comfort the columns ask 910 with the description, 810 without: it folds alone
    resize(850)
    expect(heads(container)).toEqual(['name', 'status', 'ca', 'source', 'expiry', 'key', '·'])
    expect(container.querySelector('.folded-note')).toHaveTextContent('{"count":1}')
  })

  it('never folds the sorted column: the next one goes in its place', () => {
    room.width = 600
    const { container } = render(table({ sort: { key: 'key', asc: true }, onSort: () => {} }))
    expect(heads(container)).toEqual(['name', 'status', 'ca', 'key', '·'])
  })

  it('a page not yet migrated folds by its fold rank, else from the right, never the name nor fold: false', () => {
    room.width = 520
    const plain = [
      { id: 'name', label: 'Nom', entity: true, cell: (r) => r.name },
      { id: 'a', label: 'A', cell: () => 'a' },
      { id: 'b', label: 'B', cell: () => 'b' },
      { id: 'status', label: 'État', cell: () => 's', fold: false },
      { id: 'c', label: 'C', cell: () => 'c' },
    ]
    // 300 + 100 + 100 + 80 + 100 in 480, the name at its comfort 280 at most: c then b fold
    const { container } = render(table({ columns: plain }))
    expect(heads(container)).toEqual(['name', 'a', 'status', '·'])
  })

  it('a module list (ListView) keeps its state and folds its other columns', () => {
    // A name of 200 and four columns of 100 in 400: c then b fold
    room.width = 440
    const { container } = render(
      <ListView label="Modèles" icon="template" rows={rows} title={(r) => r.name} status={() => 'ok'} onOpen={() => {}}
        columns={[{ id: 'a', label: 'A', cell: () => 'a' }, { id: 'b', label: 'B', cell: () => 'b' }, { status: true }, { id: 'c', label: 'C', cell: () => 'c' }]} />,
    )
    expect([...container.querySelectorAll('thead th')].map((th) => (narrow(th) ? '·' : th.textContent))).toEqual(['atelier.name', 'A', 'atelier.state', '·'])
  })

  it('the Colonnes dialog does not change with the folds: a folded column stays ticked', () => {
    room.width = 600
    render(<TableView label="Liste" storageKey="t-fold" columns={columns.map((c) => ({ ...c, always: c.priority === 1 }))} rows={rows}
      rowLabel={(r) => r.name} onOpen={() => {}} search={null} columnsDialog={{ note: '' }} />)
    expect(screen.queryByRole('columnheader', { name: 'Description' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'table.columns' }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByRole('checkbox', { name: 'Description' })).toBeChecked()
    expect(within(dialog).getByRole('checkbox', { name: 'Clé' })).toBeChecked()
  })
})

describe('a width set by hand beside the folds (C2)', () => {
  const widened = (props = {}) => table({ columnWidths: { ca: 400 }, onColumnWidth: () => {}, ...props })

  it('holds while it fits: the header and the cells at 400 px, the description takes the rest', () => {
    const { container } = render(widened())
    expect(heads(container)).toEqual(['name', 'description', 'status', 'ca', 'source', 'expiry', 'key', '·'])
    expect(headOf(container, 'ca').style.width).toBe('400px')
    expect(cellOf(container, 'ca').style.maxWidth).toBe('400px')
    expect(cellOf(container, 'ca').style.minWidth).toBe('400px')
    expect(headOf(container, 'description')).not.toHaveClass('fit')
  })

  it('the columns still fold beside it, in their order, and the footer says so; out of room it is ignored', () => {
    room.width = 900
    const { container } = render(widened())
    // 860 of room: the description, the key and the source fold before the name gives way to its hard floor
    expect(heads(container)).toEqual(['name', 'status', 'ca', 'expiry', '·'])
    expect(headOf(container, 'ca').style.width).toBe('400px')
    expect(container.querySelector('.folded-note')).toHaveTextContent('{"count":3}')
    // Only folding the issuer itself would make room: its width is ignored for this render, the layout is the plain one
    resize(560)
    expect(heads(container)).toEqual(['name', 'status', 'ca', 'expiry', '·'])
    expect(headOf(container, 'ca').style.width).toBe('')
    resize(1400)
    expect(headOf(container, 'ca').style.width).toBe('400px')
  })

  it('a handle is bounded by its column: a name at 200, a fitted column at its content, 640 at most', () => {
    const { container } = render(widened())
    const bounds = (id) => ['aria-valuemin', 'aria-valuemax', 'aria-valuenow'].map((a) => headOf(container, id).querySelector('[role=separator]').getAttribute(a))
    expect(bounds('name')).toEqual(['200', '640', '300'])
    expect(bounds('source')).toEqual(['70', '640', '70'])
    expect(bounds('ca')).toEqual(['96', '640', '400'])
  })
})

describe('a name with badges under it (the authorities, G5)', () => {
  // A group of badges spans the cell (adjust.css): its box is the cell's, 535 px; its badges are 90 and 70 px
  const WIDTH = { 'ca-badges': 535, chip: 0, 'entity-name': 262 }
  beforeAll(() => {
    saved.offset = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetWidth')
    Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {
      configurable: true,
      get() { return Number(this.dataset?.w) || WIDTH[[...this.classList].find((c) => c in WIDTH)] || 0 },
    })
  })
  afterAll(() => {
    if (saved.offset) Object.defineProperty(HTMLElement.prototype, 'offsetWidth', saved.offset); else delete HTMLElement.prototype.offsetWidth
  })

  it('counts the widest badge, not the group\'s box, and nothing for an empty group: the name gives way to 200 before a column folds', () => {
    const before = { ...NATURAL }
    Object.assign(NATURAL, { name: 560, status: 300, expiry: 340 })
    try {
      room.width = 880
      const badges = (r) => <span className="ca-badges">{r.id === 1 && <><span className="chip" data-w="90">Racine</span><span className="chip" data-w="70">PQ</span></>}</span>
      const cas = [
        { id: 'name', label: 'Nom', kind: 'entity', priority: 1, grow: true, cell: (r) => r.name, extra: badges },
        { id: 'status', label: 'État', kind: 'fit', priority: 1, cell: () => 'Active' },
        { id: 'expiry', label: 'Expire', kind: 'fit', priority: 2, cell: () => '2036' },
      ]
      const { container } = render(table({ columns: cas }))
      // 1200 asked in 840: the name gives 280 down to its comfort, then 80 down to 200; the expiry stays
      expect(heads(container)).toEqual(['name', 'status', 'expiry', '·'])
      expect(cellOf(container, 'name').style.maxWidth).toBe('200px')
    } finally { Object.assign(NATURAL, before) }
  })
})

describe('the fixed columns and the rows', () => {
  it('a number column reads at the right: its header and cells say so, its arrow before its label', () => {
    const cols = [columns[0], { id: 'certs', label: 'Certificats', kind: 'number', priority: 3, sort: 'certs', cell: () => 12 }]
    const { container } = render(table({ columns: cols, sort: { key: 'name', asc: true }, onSort: () => {} }))
    expect(headOf(container, 'certs')).toHaveClass('num')
    expect(cellOf(container, 'certs')).toHaveClass('num')
    expect(headOf(container, 'certs').querySelector('button').firstChild.tagName.toLowerCase()).toBe('svg')
    expect(headOf(container, 'name').querySelector('button').firstChild.nodeType).toBe(Node.TEXT_NODE)
  })

  it('the checkbox column is marked as such in its header and its cells (40 px, adjust.css)', () => {
    const { container } = render(table({ selection: { selected: new Set(), onToggle: () => {}, onTogglePage: () => {} } }))
    expect(container.querySelector('thead th:first-child')).toHaveClass('check-col')
    expect(container.querySelector('tbody td:first-child')).toHaveClass('check-col')
  })

  it('the open row is the current one for a screen reader, a ticked one is not', () => {
    const { container } = render(table({ openedId: 2, selection: { selected: new Set([1]), onToggle: () => {}, onTogglePage: () => {} } }))
    const [first, second] = container.querySelectorAll('tbody tr')
    expect(second).toHaveAttribute('aria-current', 'true')
    expect(second).toHaveClass('opened')
    expect(first).toHaveClass('checked')
    expect(first).not.toHaveAttribute('aria-current')
  })

  it('brings the open row into view after a sort', () => {
    const into = vi.fn()
    HTMLElement.prototype.scrollIntoView = into
    const { rerender } = render(table({ openedId: 2, sort: { key: 'name', asc: true }, onSort: () => {} }))
    into.mockClear()
    rerender(table({ openedId: 2, sort: { key: 'name', asc: false }, onSort: () => {} }))
    expect(into).toHaveBeenCalledWith({ block: 'nearest', inline: 'nearest' })
    expect(into.mock.contexts[0]).toHaveClass('opened')
  })

  it('marks an action that gives way short of room (the Certificates\' Export); the chevron is never one', () => {
    const { container } = render(table({ rowActions: () => [{ icon: 'download', label: 'Exporter', spare: true }, { icon: 'refresh', label: 'Renouveler' }] }))
    const buttons = container.querySelectorAll('tbody tr:first-child .table-actions > button')
    expect([...buttons].map((b) => b.hasAttribute('data-spare'))).toEqual([true, false, false])
  })

  it('refuses a column declared by halves', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(table({ columns: [columns[0], { id: 'x', label: 'X', kind: 'fit', cell: () => 'x' }] }))).toThrow(/x: no priority/)
    console.error.mockRestore()
  })
})

describe('the certificates declare the contract', () => {
  it('fold the description first, then the qualifiers from the right, the expiry and the issuer last', () => {
    const cols = certificateColumns((k) => k)
    expect(columnErrors(cols)).toEqual([])
    expect(foldOrder(cols)).toEqual(['description', 'created', 'pair', 'grade', 'key', 'source', 'expiry', 'ca'])
    expect(foldOrder(cols, 'days')).not.toContain('expiry')
  })
})
