/**
 * A list toolbar beside the dock anchored at the right: short of room (its search field at its floor, or
 * its tools overflowing), it folds as the mockup's phone toolbar, the search on its own line and the
 * filters and tools on the next; it unfolds when the room comes back, and never folds with the dock below.
 * jsdom has no layout: the field takes what the other tools (600 px) leave of the room, at least 170 px.
 */
import { describe, it, expect, beforeAll, afterAll, beforeEach } from 'vitest'
import { render, act } from '@testing-library/react'

import { Toolbar, SearchField, FilterSelect } from '../Toolbar'

const room = { width: 676 }
const observers = new Set()
const saved = {}
const toolbarOf = (el) => el.closest?.('.toolbar')
beforeAll(() => {
  saved.client = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'clientWidth')
  saved.scroll = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollWidth')
  saved.offset = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetWidth')
  saved.RO = global.ResizeObserver
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, get() { return this.classList?.contains('toolbar') ? room.width : 0 } })
  Object.defineProperty(HTMLElement.prototype, 'scrollWidth', { configurable: true, get() { return this.classList?.contains('toolbar') ? room.width : 0 } })
  Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {
    configurable: true,
    get() {
      if (!this.classList?.contains('search')) return 0
      return toolbarOf(this).classList.contains('folded') ? room.width : Math.max(170, room.width - 600)
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
  for (const [k, prop] of [['client', 'clientWidth'], ['scroll', 'scrollWidth'], ['offset', 'offsetWidth']]) {
    if (saved[k]) Object.defineProperty(HTMLElement.prototype, prop, saved[k])
  }
  global.ResizeObserver = saved.RO
})
beforeEach(() => { room.width = 676; observers.clear() })

const resize = (w) => act(() => { room.width = w; for (const o of [...observers]) o.cb([]) })
// The copied rule's floor, as the page's stylesheet gives it
const bar = () => (
  <Toolbar>
    <SearchField label="Rechercher" placeholder="Nom, description" value="" onChange={() => {}} />
    <FilterSelect label="AC" value="" options={[{ value: '', label: 'Toutes les AC' }]} />
  </Toolbar>
)
const styled = (ui) => <><style>{'.search{min-width:170px}'}</style>{ui}</>

describe('the toolbar beside the right dock', () => {
  it('folds when its search field is at its floor, and unfolds when the room comes back', () => {
    const { container } = render(styled(<div id="app" className="dock-right">{bar()}</div>))
    const toolbar = container.querySelector('.toolbar')
    expect(toolbar).toHaveClass('folded')
    resize(1076)
    expect(toolbar).not.toHaveClass('folded')
    resize(700)
    expect(toolbar).toHaveClass('folded')
  })

  it('folds when its tools overflow', () => {
    room.width = 1076
    Object.defineProperty(HTMLElement.prototype, 'scrollWidth', { configurable: true, get() { return this.classList?.contains('toolbar') ? room.width + 40 : 0 } })
    try {
      const { container } = render(styled(<div id="app" className="dock-right">{bar()}</div>))
      expect(container.querySelector('.toolbar')).toHaveClass('folded')
    } finally {
      Object.defineProperty(HTMLElement.prototype, 'scrollWidth', { configurable: true, get() { return this.classList?.contains('toolbar') ? room.width : 0 } })
    }
  })

  it('never folds with the dock below', () => {
    const { container } = render(styled(<div id="app">{bar()}</div>))
    expect(container.querySelector('.toolbar')).toHaveClass('toolbar')
    expect(container.querySelector('.toolbar')).not.toHaveClass('folded')
  })
})
