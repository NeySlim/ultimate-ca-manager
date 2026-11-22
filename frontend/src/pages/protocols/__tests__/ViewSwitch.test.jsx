/**
 * The views of a protocol page as a row of tabs under its head: one tab per view (its counter when it
 * has one), the groups apart, the arrow keys, the panel the tabs control, and the « More » menu that
 * takes the tabs past the room.
 */
import { useState } from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k) => k, i18n: { language: 'en' } }),
}))
vi.mock('../../../contexts', () => ({ useNotification: () => ({ showSuccess: vi.fn() }) }))
vi.mock('../../../hooks', () => ({ useClipboard: () => ({ copy: vi.fn() }) }))

import { ViewSwitch } from '../atelierParts'

const GROUPS = [
  { label: 'Local ACME', options: [{ value: 'accounts', label: 'Accounts', count: 43 }, { value: 'config', label: 'Server settings' }] },
  { label: 'ACME client', options: [{ value: 'dns', label: 'DNS providers', count: null }] },
  { label: 'History', options: [{ value: 'history', label: 'Issued certificates', count: 1234 }] },
]

function Page({ initial = 'accounts', onChange = () => {}, groups = GROUPS, options }) {
  const [value, setValue] = useState(initial)
  return (
    <ViewSwitch id="acme-view" label="View" value={value} groups={options ? [] : groups} options={options}
      onChange={(v) => { onChange(v); setValue(v) }}>
      <p>panel of {value}</p>
    </ViewSwitch>
  )
}

const tab = (name) => screen.getByRole('tab', { name: new RegExp(`^${name}`) })

describe('the views of a protocol page', () => {
  it('draws one tab per view in a named tablist, the shown one selected and controlling the panel', () => {
    render(<Page initial="config" />)
    const list = screen.getByRole('tablist', { name: 'View' })
    expect(screen.getAllByRole('tab').map((b) => b.id)).toEqual(['acme-view-tab-accounts', 'acme-view-tab-config', 'acme-view-tab-dns', 'acme-view-tab-history'])
    expect(list.querySelectorAll('[role="tab"]')).toHaveLength(4)
    expect(tab('Server settings')).toHaveAttribute('aria-selected', 'true')
    expect(tab('Server settings')).toHaveClass('view-btn', 'active')
    expect(tab('Accounts')).toHaveAttribute('aria-selected', 'false')
    // The roving focus: only the shown tab is in the Tab order
    expect(tab('Server settings')).toHaveAttribute('tabindex', '0')
    expect(tab('Accounts')).toHaveAttribute('tabindex', '-1')
    const panel = screen.getByRole('tabpanel')
    expect(panel).toHaveAttribute('id', 'acme-view-panel')
    expect(panel).toHaveAttribute('aria-labelledby', 'acme-view-tab-config')
    expect(panel).toHaveTextContent('panel of config')
    for (const t of screen.getAllByRole('tab')) expect(t).toHaveAttribute('aria-controls', 'acme-view-panel')
    // No select is left in the page head
    expect(screen.queryByRole('combobox')).toBeNull()
  })

  it('counts the views that have a counter, a bar while it is read, nothing for the others', () => {
    render(<Page />)
    expect(tab('Accounts').querySelector('.counter')).toHaveTextContent('43')
    expect(tab('Issued certificates').querySelector('.counter')).toHaveTextContent('1,234')
    expect(tab('DNS providers').querySelector('.counter .sk')).not.toBeNull()
    expect(tab('Server settings').querySelector('.counter')).toBeNull()
  })

  it('keeps the groups apart: a divider between them, each tab described by its group', () => {
    const { container } = render(<Page />)
    expect(container.querySelectorAll('[role="tablist"] .tools-divider[aria-hidden="true"]')).toHaveLength(2)
    expect(tab('Accounts')).toHaveAccessibleDescription('Local ACME')
    expect(tab('Server settings')).toHaveAccessibleDescription('Local ACME')
    expect(tab('DNS providers')).toHaveAccessibleDescription('ACME client')
    expect(tab('Issued certificates')).toHaveAccessibleDescription('History')
  })

  it('a flat list of views has no divider and no description', () => {
    const { container } = render(<Page initial="list" options={[{ value: 'list', label: 'Services', count: 1 }, { value: 'config', label: 'Configuration' }]} />)
    expect(container.querySelector('.tools-divider')).toBeNull()
    expect(tab('Services')).not.toHaveAttribute('aria-describedby')
    expect(tab('Services')).toHaveAttribute('aria-selected', 'true')
  })

  it('a click shows the view', () => {
    const onChange = vi.fn()
    render(<Page onChange={onChange} />)
    fireEvent.click(tab('DNS providers'))
    expect(onChange).toHaveBeenCalledWith('dns')
    expect(tab('DNS providers')).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tabpanel')).toHaveTextContent('panel of dns')
  })

  it('the arrows, Home and End move the view and the focus, wrapping at the ends', async () => {
    const onChange = vi.fn()
    render(<Page onChange={onChange} />)
    const raf = vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb) => { cb(0); return 0 })
    tab('Accounts').focus()
    fireEvent.keyDown(tab('Accounts'), { key: 'ArrowRight' })
    expect(onChange).toHaveBeenLastCalledWith('config')
    expect(tab('Server settings')).toHaveFocus()
    fireEvent.keyDown(tab('Server settings'), { key: 'End' })
    expect(onChange).toHaveBeenLastCalledWith('history')
    expect(tab('Issued certificates')).toHaveFocus()
    fireEvent.keyDown(tab('Issued certificates'), { key: 'ArrowRight' })
    expect(onChange).toHaveBeenLastCalledWith('accounts')
    fireEvent.keyDown(tab('Accounts'), { key: 'ArrowLeft' })
    expect(onChange).toHaveBeenLastCalledWith('history')
    fireEvent.keyDown(tab('Issued certificates'), { key: 'Home' })
    expect(onChange).toHaveBeenLastCalledWith('accounts')
    expect(tab('Accounts')).toHaveFocus()
    // Another key is left to the page
    onChange.mockClear()
    fireEvent.keyDown(tab('Accounts'), { key: 'a' })
    expect(onChange).not.toHaveBeenCalled()
    raf.mockRestore()
  })

})

// jsdom lays nothing out: a tab is 100 px, a divider 7 px, the « More » block 60 px, the row's frame W.frame px
const W = { frame: 300 }
const widthOf = (el) => (el.dataset?.view ? 100 : el.classList?.contains('tools-divider') ? 7 : el.classList?.contains('views-more') ? 60 : 0)
const saved = {}

describe('the views past the room', () => {
  beforeEach(() => {
    W.frame = 300
    for (const k of ['offsetWidth', 'clientWidth']) saved[k] = Object.getOwnPropertyDescriptor(HTMLElement.prototype, k)
    Object.defineProperty(HTMLElement.prototype, 'offsetWidth', { configurable: true, get() { return widthOf(this) } })
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, get() { return this.classList?.contains('page-views') ? W.frame : 0 } })
  })
  afterEach(() => {
    for (const k of ['offsetWidth', 'clientWidth']) {
      if (saved[k]) Object.defineProperty(HTMLElement.prototype, k, saved[k])
      else delete HTMLElement.prototype[k]
    }
  })
  const more = () => screen.queryByRole('button', { name: 'common.more' })

  it('shows every tab and no « More » when they fit, and the row never scrolls', () => {
    W.frame = 1000
    const { container } = render(<Page />)
    expect(screen.getAllByRole('tab')).toHaveLength(4)
    expect(more()).toBeNull()
    expect(container.querySelector('[data-overflow]')).toBeNull()
  })

  it('moves the tabs past the room into a « More » menu at the end of the row, their counters with them', async () => {
    const user = userEvent.setup()
    const { container } = render(<Page />)
    expect(screen.getAllByRole('tab').map((b) => b.id)).toEqual(['acme-view-tab-accounts', 'acme-view-tab-config'])
    // Out of the row, the reading and the tab order, still drawn for their width
    const dns = container.querySelector('#acme-view-tab-dns')
    expect(dns).toHaveAttribute('data-overflow')
    expect(dns).toHaveAttribute('aria-hidden', 'true')
    expect(dns).toHaveAttribute('tabindex', '-1')
    // The « More » button follows the row, a menu button
    const button = more()
    expect(button.closest('.views-more').previousElementSibling).toHaveAttribute('role', 'tablist')
    expect(button).toHaveAttribute('aria-haspopup', 'menu')
    expect(button).toHaveAttribute('aria-expanded', 'false')
    await user.click(button)
    expect(button).toHaveAttribute('aria-expanded', 'true')
    const menu = screen.getByRole('menu', { name: 'common.otherViews' })
    expect(button).toHaveAttribute('aria-controls', menu.id)
    const items = within(menu).getAllByRole('menuitem')
    expect(items.map((b) => b.querySelector('.pop-label').textContent)).toEqual(['DNS providers', 'Issued certificates'])
    expect(items[0]).toHaveFocus()
    expect(items[0].querySelector('.counter .sk')).not.toBeNull()
    expect(items[1].querySelector('.counter')).toHaveTextContent('1,234')
    // Two groups apart, each item described by its group
    expect(within(menu).getAllByRole('separator')).toHaveLength(1)
    expect(items[1]).toHaveAccessibleDescription('History')
  })

  it('a view chosen in the menu takes the place of the last tab shown, and the focus', async () => {
    const onChange = vi.fn()
    const raf = vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb) => { cb(0); return 0 })
    const user = userEvent.setup()
    render(<Page onChange={onChange} />)
    await user.click(more())
    await user.click(screen.getByRole('menuitem', { name: /^Issued certificates/ }))
    expect(onChange).toHaveBeenCalledWith('history')
    expect(screen.queryByRole('menu')).toBeNull()
    expect(screen.getAllByRole('tab').map((b) => b.id)).toEqual(['acme-view-tab-accounts', 'acme-view-tab-history'])
    expect(tab('Issued certificates')).toHaveAttribute('aria-selected', 'true')
    expect(tab('Issued certificates')).toHaveFocus()
    raf.mockRestore()
  })

  it('follows the room: a wider frame brings the tabs back and drops the button', () => {
    const { rerender } = render(<Page />)
    expect(more()).not.toBeNull()
    W.frame = 1000
    rerender(<Page />)
    expect(screen.getAllByRole('tab')).toHaveLength(4)
    expect(more()).toBeNull()
  })

  it('the arrows still reach a view in the menu, which comes into the row', () => {
    const onChange = vi.fn()
    const raf = vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb) => { cb(0); return 0 })
    render(<Page initial="config" onChange={onChange} />)
    fireEvent.keyDown(tab('Server settings'), { key: 'ArrowRight' })
    expect(onChange).toHaveBeenLastCalledWith('dns')
    expect(tab('DNS providers')).toHaveFocus()
    expect(tab('DNS providers')).not.toHaveAttribute('data-overflow')
    raf.mockRestore()
  })

  it('the menu answers its keys: down arrow on the button opens it, Escape closes it on the button', async () => {
    const user = userEvent.setup()
    render(<Page />)
    more().focus()
    await user.keyboard('{ArrowDown}')
    const items = within(screen.getByRole('menu')).getAllByRole('menuitem')
    expect(items[0]).toHaveFocus()
    await user.keyboard('{ArrowDown}')
    expect(items[1]).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('menu')).toBeNull()
    expect(more()).toHaveFocus()
  })
})
