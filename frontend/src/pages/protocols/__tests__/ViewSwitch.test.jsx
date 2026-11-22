/**
 * The views of a protocol page as a row of tabs under its head: one tab per view (its counter when it
 * has one), the groups apart, the arrow keys, the panel the tabs control, and the edge shadows of a
 * row wider than the page.
 */
import { useState } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'

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

  it('marks the edge the row hides behind with a shadow when the tabs overflow it', () => {
    const { container } = render(<Page />)
    const row = container.querySelector('[role="tablist"]')
    const frame = container.querySelector('.page-views')
    expect(frame).not.toHaveAttribute('data-more-start')
    expect(frame).not.toHaveAttribute('data-more-end')
    Object.defineProperty(row, 'scrollWidth', { configurable: true, value: 900 })
    Object.defineProperty(row, 'clientWidth', { configurable: true, value: 400 })
    act(() => { row.scrollLeft = 0; fireEvent.scroll(row) })
    expect(frame).not.toHaveAttribute('data-more-start')
    expect(frame).toHaveAttribute('data-more-end')
    act(() => { row.scrollLeft = 200; fireEvent.scroll(row) })
    expect(frame).toHaveAttribute('data-more-start')
    expect(frame).toHaveAttribute('data-more-end')
    act(() => { row.scrollLeft = 500; fireEvent.scroll(row) })
    expect(frame).toHaveAttribute('data-more-start')
    expect(frame).not.toHaveAttribute('data-more-end')
  })

  it('turns a mouse wheel into a scroll of a row that overflows, until its end', () => {
    const { container } = render(<Page />)
    const row = container.querySelector('[role="tablist"]')
    const wheel = (deltaY) => {
      const e = new WheelEvent('wheel', { deltaY, bubbles: true, cancelable: true })
      row.dispatchEvent(e)
      return e.defaultPrevented
    }
    expect(wheel(100)).toBe(false)
    Object.defineProperty(row, 'scrollWidth', { configurable: true, value: 900 })
    Object.defineProperty(row, 'clientWidth', { configurable: true, value: 400 })
    expect(wheel(100)).toBe(true)
    expect(row.scrollLeft).toBe(100)
    row.scrollLeft = 500
    expect(wheel(100)).toBe(false)
    expect(wheel(-100)).toBe(true)
    expect(row.scrollLeft).toBe(400)
  })

  it('measures its edges again when the tabs widen without the row changing size', () => {
    const { container, rerender } = render(<Page />)
    const row = container.querySelector('[role="tablist"]')
    Object.defineProperty(row, 'clientWidth', { configurable: true, value: 400 })
    Object.defineProperty(row, 'scrollWidth', { configurable: true, value: 900 })
    rerender(<Page groups={GROUPS.map((g) => ({ ...g, options: g.options.map((o) => ({ ...o, count: 7 })) }))} />)
    expect(container.querySelector('.page-views')).toHaveAttribute('data-more-end')
  })

  it('brings the shown tab into the row when it lies beyond its edge', () => {
    const { container, rerender } = render(<Page />)
    const row = container.querySelector('[role="tablist"]')
    Object.defineProperty(row, 'clientWidth', { configurable: true, value: 300 })
    Object.defineProperty(row, 'scrollWidth', { configurable: true, value: 900 })
    const history = tab('Issued certificates')
    Object.defineProperty(history, 'offsetLeft', { configurable: true, value: 600 })
    Object.defineProperty(history, 'offsetWidth', { configurable: true, value: 140 })
    row.scrollTo = vi.fn()
    fireEvent.click(history)
    rerender(<Page />)
    expect(row.scrollTo).toHaveBeenCalledWith(expect.objectContaining({ left: 600 + 140 - 300 + 24 }))
  })
})
