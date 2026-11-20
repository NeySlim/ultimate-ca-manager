/**
 * Save parts and the leave guard: changes counted key by key, parts a section keeps
 * registered with the page, and leaving with pending changes asked first, by a link,
 * by the palette (`whenLeaving`) or by closing the tab.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, Link } from 'react-router-dom'
import { useState } from 'react'

import { changedKeys, useLeaveGuard, useSavePart, useSavePartsRegistry, SavePartsContext } from '..'
import { whenLeaving } from '../../../navigation/leaveGuard'

afterEach(() => vi.restoreAllMocks())

describe('changedKeys', () => {
  it('counts what differs, empty and missing alike, objects by value', () => {
    expect(changedKeys({ a: '1', b: '', c: [1, 2], d: 3 }, { a: 1, c: [1, 2], d: 4 }, ['a', 'b', 'c', 'd'])).toEqual(['d'])
    expect(changedKeys({ a: 'x' }, {}, ['a'])).toEqual(['a'])
  })
})

function Part({ id, count }) {
  useSavePart(id, { section: 's', count, save: vi.fn(), reset: vi.fn() })
  return null
}

function Host({ children }) {
  const registry = useSavePartsRegistry()
  return (
    <SavePartsContext.Provider value={registry.api}>
      {children}
      <output data-testid="total">{registry.list.reduce((n, p) => n + p.count, 0)}</output>
    </SavePartsContext.Provider>
  )
}

describe('useSavePart', () => {
  it('reports the count of a part to the page, and drops it on unmount', () => {
    function Toggle() {
      const [count, setCount] = useState(0)
      const [shown, setShown] = useState(true)
      return (
        <>
          <button type="button" onClick={() => setCount(2)}>edit</button>
          <button type="button" onClick={() => setShown(false)}>hide</button>
          {shown && <Part id="p" count={count} />}
          <Part id="q" count={1} />
        </>
      )
    }
    render(<Host><Toggle /></Host>)
    expect(screen.getByTestId('total')).toHaveTextContent('1')
    fireEvent.click(screen.getByText('edit'))
    expect(screen.getByTestId('total')).toHaveTextContent('3')
    fireEvent.click(screen.getByText('hide'))
    expect(screen.getByTestId('total')).toHaveTextContent('1')
  })
})

function Guarded({ active, ask }) {
  useLeaveGuard(active, ask)
  return (
    <>
      <Link to="/elsewhere">away</Link>
      <Link to="/form?tab=b">same page</Link>
    </>
  )
}

const mount = (active, ask) => render(
  <MemoryRouter initialEntries={['/form']}>
    <Routes>
      <Route path="/form" element={<Guarded active={active} ask={ask} />} />
      <Route path="/elsewhere" element={<p>arrived</p>} />
    </Routes>
  </MemoryRouter>,
)

describe('useLeaveGuard', () => {
  it('asks before a link leaves the page, and stays when refused', async () => {
    window.history.replaceState(null, '', '/form')
    const ask = vi.fn().mockResolvedValue(false)
    mount(true, ask)
    await act(async () => { fireEvent.click(screen.getByText('away')) })
    expect(ask).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('arrived')).toBeNull()
  })

  it('leaves once agreed', async () => {
    window.history.replaceState(null, '', '/form')
    const ask = vi.fn().mockResolvedValue(true)
    mount(true, ask)
    await act(async () => { fireEvent.click(screen.getByText('away')) })
    expect(await screen.findByText('arrived')).toBeInTheDocument()
  })

  it('lets a link to the same page through without asking', async () => {
    window.history.replaceState(null, '', '/form')
    const ask = vi.fn().mockResolvedValue(false)
    mount(true, ask)
    await act(async () => { fireEvent.click(screen.getByText('same page')) })
    expect(ask).not.toHaveBeenCalled()
  })

  it('asks nothing when nothing is pending', async () => {
    const ask = vi.fn()
    mount(false, ask)
    await act(async () => { fireEvent.click(screen.getByText('away')) })
    expect(ask).not.toHaveBeenCalled()
    expect(screen.getByText('arrived')).toBeInTheDocument()
  })

  it('holds the palette navigation until agreed, and lets it go at once when inactive', async () => {
    const ask = vi.fn().mockResolvedValue(false)
    const { unmount } = mount(true, ask)
    const go = vi.fn()
    await act(async () => { whenLeaving(go) })
    expect(ask).toHaveBeenCalled()
    expect(go).not.toHaveBeenCalled()
    unmount()
    whenLeaving(go)
    expect(go).toHaveBeenCalledTimes(1)
  })

  it('asks the browser before a reload or a close of the tab', () => {
    mount(true, vi.fn())
    const event = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
  })
})
