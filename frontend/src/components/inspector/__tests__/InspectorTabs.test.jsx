/**
 * The strip of open objects: every tab keeps a minimum width, the active one is always
 * drawn, the others wait in a "+N" menu that the keyboard opens, walks and closes.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, opts) => (opts?.count !== undefined ? `${key}:${opts.count}` : opts?.name ? `${key}:${opts.name}` : key) }),
}))

import { ObjectTabs, splitTabs } from '../InspectorTabs'

const objects = (n) => Array.from({ length: n }, (_, i) => ({ key: `certificate:${i + 1}`, type: 'certificate', entityId: i + 1 }))
const titles = Object.fromEntries(objects(6).map((o) => [o.key, `host${o.entityId}.example.com`]))

describe('splitTabs', () => {
  it('draws every object while they fit', () => {
    expect(splitTabs(objects(3), 'certificate:1', Infinity)).toEqual({ shown: objects(3), hidden: [] })
    expect(splitTabs(objects(3), 'certificate:1', 3).hidden).toEqual([])
  })

  it('leaves the others to the menu, the active one taking the last place', () => {
    const { shown, hidden } = splitTabs(objects(5), 'certificate:5', 2)
    expect(shown.map((o) => o.entityId)).toEqual([1, 5])
    expect(hidden.map((o) => o.entityId)).toEqual([2, 3, 4])
  })

  it('keeps the first ones when the active one is among them, and one tab at least', () => {
    expect(splitTabs(objects(5), 'certificate:2', 2).shown.map((o) => o.entityId)).toEqual([1, 2])
    expect(splitTabs(objects(5), 'certificate:4', 0).shown.map((o) => o.entityId)).toEqual([4])
  })
})

describe('ObjectTabs', () => {
  let width
  const clientWidth = Object.getOwnPropertyDescriptor(Element.prototype, 'clientWidth')
  beforeEach(() => {
    width = 0
    Object.defineProperty(Element.prototype, 'clientWidth', { configurable: true, get() { return this.getAttribute('role') === 'tablist' ? width : 0 } })
  })
  afterEach(() => { Object.defineProperty(Element.prototype, 'clientWidth', clientWidth) })

  const mount = (n, activeKey, props = {}) => {
    const onSelect = vi.fn()
    const onClose = vi.fn()
    render(<ObjectTabs opened={objects(n)} activeKey={activeKey} titles={titles} onSelect={onSelect} onClose={onClose} {...props} />)
    return { onSelect, onClose }
  }

  it('draws every tab and no menu while the strip has room, each with its whole name as a tip', () => {
    width = 600
    mount(5, 'certificate:1')
    expect(screen.getAllByRole('tab')).toHaveLength(5)
    expect(screen.queryByTestId('inspector-more')).toBeNull()
    expect(screen.getByRole('tab', { name: 'host2.example.com' })).toHaveAttribute('title', 'host2.example.com')
  })

  it('keeps the minimum width of a tab: what does not fit goes to "+N", the active one stays', () => {
    // 300 px: two tabs of 120 px beside the 52 px of the button
    width = 300
    mount(6, 'certificate:6')
    expect(screen.getAllByRole('tab').map((tab) => tab.textContent)).toEqual(['host1.example.com', 'host6.example.com'])
    expect(screen.getByRole('tab', { name: 'host6.example.com' })).toHaveAttribute('aria-selected', 'true')
    const more = screen.getByTestId('inspector-more')
    expect(more).toHaveTextContent('+4')
    expect(more).toHaveTextContent('inspector.moreCount:4')
    expect(more).toHaveAttribute('aria-haspopup', 'menu')
    expect(more).toHaveAttribute('aria-expanded', 'false')
  })

  it('opens the menu, activates an object from it and closes one from it', () => {
    width = 300
    const { onSelect, onClose } = mount(4, 'certificate:1', { badge: (o) => <em>{`state-${o.entityId}`}</em> })
    fireEvent.click(screen.getByTestId('inspector-more'))
    const menu = screen.getByRole('menu', { name: 'inspector.notShown' })
    expect(screen.getByTestId('inspector-more')).toHaveAttribute('aria-expanded', 'true')
    const rows = within(menu).getAllByRole('menuitem').filter((i) => i.classList.contains('insp-menu-open'))
    expect(rows.map((r) => r.textContent)).toEqual(['host3.example.comstate-3', 'host4.example.comstate-4'])
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'inspector.closeTab:host4.example.com' }))
    expect(onClose).toHaveBeenCalledWith('certificate:4')
    fireEvent.click(rows[0])
    expect(onSelect).toHaveBeenCalledWith('certificate:3')
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('walks the menu with the arrows and closes it with Escape, the focus back on the button', () => {
    width = 300
    mount(5, 'certificate:1')
    const more = screen.getByTestId('inspector-more')
    fireEvent.keyDown(more, { key: 'ArrowDown' })
    const menu = screen.getByRole('menu')
    const rows = [...menu.querySelectorAll('.insp-menu-open')]
    rows[0].focus()
    fireEvent.keyDown(rows[0], { key: 'ArrowDown' })
    expect(rows[1]).toHaveFocus()
    fireEvent.keyDown(rows[1], { key: 'End' })
    expect(rows[2]).toHaveFocus()
    fireEvent.keyDown(rows[2], { key: 'ArrowRight' })
    expect(menu.querySelectorAll('.insp-x')[2]).toHaveFocus()
    fireEvent.keyDown(menu.querySelectorAll('.insp-x')[2], { key: 'Escape' })
    expect(screen.queryByRole('menu')).toBeNull()
    expect(more).toHaveFocus()
  })

  it('closes the menu on a press outside it', () => {
    width = 300
    mount(5, 'certificate:1')
    fireEvent.click(screen.getByTestId('inspector-more'))
    fireEvent.pointerDown(document.body)
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('moves between the drawn tabs with the arrows and closes one with Delete', () => {
    width = 600
    const { onSelect, onClose } = mount(3, 'certificate:2')
    fireEvent.keyDown(screen.getByRole('tab', { name: 'host2.example.com' }), { key: 'ArrowRight' })
    expect(onSelect).toHaveBeenCalledWith('certificate:3')
    fireEvent.keyDown(screen.getByRole('tab', { name: 'host2.example.com' }), { key: 'Home' })
    expect(onSelect).toHaveBeenCalledWith('certificate:1')
    fireEvent.keyDown(screen.getByRole('tab', { name: 'host2.example.com' }), { key: 'Delete' })
    expect(onClose).toHaveBeenCalledWith('certificate:2')
  })
})
