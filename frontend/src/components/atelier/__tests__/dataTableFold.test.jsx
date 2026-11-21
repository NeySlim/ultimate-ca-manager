/**
 * A list beside the dock anchored at the right: the secondary columns fold by their priority until the
 * table fits its region (no horizontal scroll, the chevron in view); nothing folds with the dock below.
 * jsdom has no layout: the region's scroll width is the sum of its header cells (100 px each, 40 for
 * the checkbox and the actions), its client width the room the test gives it.
 */
import { describe, it, expect, vi, beforeAll, afterAll, beforeEach } from 'vitest'
import { render, act } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k) => k, i18n: { language: 'fr' } }),
}))
vi.mock('../../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: false }) }))

import { DataTable, foldOrder } from '../DataTable'
import { certificateColumns } from '../../../pages/certificates/certificateRows'
import { ListView } from '../ListView'

const room = { width: 1000 }
// The checkbox and the actions header (its name for screen readers only) are the narrow cells
const narrow = (th) => !!th.querySelector('.sr-only, input')
const observers = new Set()
const saved = {}
beforeAll(() => {
  saved.client = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'clientWidth')
  saved.scroll = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollWidth')
  saved.RO = global.ResizeObserver
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
    configurable: true,
    get() { return this.classList?.contains('table-scroll') ? room.width : 0 },
  })
  Object.defineProperty(HTMLElement.prototype, 'scrollWidth', {
    configurable: true,
    get() {
      if (!this.classList?.contains('table-scroll')) return 0
      const cells = [...this.querySelectorAll('thead th')]
      const need = cells.reduce((sum, th) => sum + (narrow(th) ? 40 : 100), 0)
      return Math.max(need, room.width)
    },
  })
  global.ResizeObserver = class {
    constructor(cb) { this.cb = cb }
    observe() { observers.add(this) }
    unobserve() {}
    disconnect() { observers.delete(this) }
  }
})
afterAll(() => {
  if (saved.client) Object.defineProperty(HTMLElement.prototype, 'clientWidth', saved.client)
  if (saved.scroll) Object.defineProperty(HTMLElement.prototype, 'scrollWidth', saved.scroll)
  global.ResizeObserver = saved.RO
})
beforeEach(() => { room.width = 1000; observers.clear() })

const resize = (w) => act(() => { room.width = w; for (const o of [...observers]) o.cb([]) })
const heads = (c) => [...c.querySelectorAll('thead th')].map((th) => (narrow(th) ? '·' : th.textContent))
const rows = [{ id: 1, name: 'vpn.example.com' }, { id: 2, name: 'api.example.com' }]
const columns = [
  { id: 'name', label: 'Nom', entity: true, cell: (r) => r.name },
  { id: 'description', label: 'Description', grow: true, cell: () => 'd', fold: 5 },
  { id: 'status', label: 'État', cell: () => 'ok' },
  { id: 'ca', label: 'Émetteur', cell: () => 'CA', fold: 4 },
  { id: 'source', label: 'Source', cell: () => 'UCM', fold: 6 },
  { id: 'expiry', label: 'Expiration', cell: () => '2027', fold: 3 },
  { id: 'key', label: 'Clé', cell: () => 'RSA', fold: 7 },
]
const table = (props = {}) => (
  <DataTable kind="certificates" columns={columns} rows={rows} rowLabel={(r) => r.name} onOpen={() => {}} {...props} />
)

describe('columns folded beside the right dock', () => {
  it('folds the columns of highest priority first until the table fits, keeping the name and the chevron', () => {
    // 7 columns of 100 + the actions (40): 740 px; 480 px of room leaves the name, the state and two more
    room.width = 480
    const { container } = render(<div id="app" className="dock-right">{table()}</div>)
    expect(heads(container)).toEqual(['Nom', 'État', 'Émetteur', 'Expiration', '·'])
    expect(container.querySelectorAll('tbody tr:first-child td')).toHaveLength(5)
    expect(container.querySelector('tbody tr button[aria-label="table.openRow"]')).not.toBeNull()
  })

  it('folds nothing while the dock is below the list', () => {
    room.width = 480
    const { container } = render(<div id="app">{table()}</div>)
    expect(heads(container)).toEqual(['Nom', 'Description', 'État', 'Émetteur', 'Source', 'Expiration', 'Clé', '·'])
  })

  it('unfolds as the region widens and folds again as it narrows', () => {
    room.width = 480
    const { container } = render(<div id="app" className="dock-right">{table()}</div>)
    expect(heads(container)).toHaveLength(5)
    resize(740)
    expect(heads(container)).toEqual(['Nom', 'Description', 'État', 'Émetteur', 'Source', 'Expiration', 'Clé', '·'])
    resize(600)
    expect(heads(container)).toEqual(['Nom', 'Description', 'État', 'Émetteur', 'Expiration', '·'])
  })

  it('without priorities, folds from the last column, never the name nor a column marked fold: false', () => {
    room.width = 340
    const plain = [
      { id: 'name', label: 'Nom', entity: true, cell: (r) => r.name },
      { id: 'a', label: 'A', cell: () => 'a' },
      { id: 'b', label: 'B', cell: () => 'b' },
      { id: 'state', label: 'État', cell: () => 's', fold: false },
      { id: 'c', label: 'C', cell: () => 'c' },
    ]
    const { container } = render(<div className="dock-right">{table({ columns: plain })}</div>)
    expect(heads(container)).toEqual(['Nom', 'A', 'État', '·'])
  })

  it('keeps the state of a module list (ListView) and folds its other columns', () => {
    room.width = 340
    const { container } = render(
      <div className="dock-right">
        <ListView label="Modèles" icon="template" rows={rows} title={(r) => r.name} status={() => 'ok'} onOpen={() => {}}
          columns={[{ id: 'a', label: 'A', cell: () => 'a' }, { id: 'b', label: 'B', cell: () => 'b' }, { status: true }, { id: 'c', label: 'C', cell: () => 'c' }]} />
      </div>,
    )
    expect(heads(container)).toEqual(['atelier.name', 'A', 'atelier.state', '·'])
  })

  it('the certificates fold the optional columns first, then the key, the source, the description, the issuer, the expiry', () => {
    expect(foldOrder(certificateColumns((k) => k))).toEqual(['created', 'pair', 'grade', 'key', 'source', 'description', 'ca', 'expiry'])
  })
})
