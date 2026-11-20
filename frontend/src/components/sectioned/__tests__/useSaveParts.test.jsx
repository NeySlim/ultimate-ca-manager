/**
 * Save parts and the drafts: changes counted key by key, parts a section keeps registered
 * with the page and their draft kept for the tab, no question when a link leaves the page,
 * the browser's own question before a reload or a close of the tab.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, Link } from 'react-router-dom'
import { useState } from 'react'

import { changedKeys, keptPartDraft, useUnloadGuard, useSavePart, useSavePartsRegistry, SavePartsContext } from '..'
import { dropAllDrafts, keepDraft, readDraft, setDraftOwner, signOutDrafts } from '../draftMemory'

afterEach(() => { vi.restoreAllMocks(); dropAllDrafts() })

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

function DraftPart({ count, draft }) {
  useSavePart('d', { section: 's', count, draft, save: vi.fn(), reset: vi.fn() })
  return null
}

describe('useSavePart drafts', () => {
  it('keeps the draft of a part with changes, and forgets it once nothing is pending', () => {
    const { rerender } = render(<Host><DraftPart count={1} draft={{ host: 'a' }} /></Host>)
    expect(keptPartDraft('d')).toEqual({ host: 'a' })
    rerender(<Host><DraftPart count={0} draft={{ host: 'b' }} /></Host>)
    expect(keptPartDraft('d')).toBeUndefined()
  })

  it('leaves a kept draft alone while the part has not loaded', () => {
    keepDraft('part:d', { host: 'a' })
    render(<Host><DraftPart count={0} draft={undefined} /></Host>)
    expect(keptPartDraft('d')).toEqual({ host: 'a' })
  })
})

describe('draftMemory', () => {
  it('drops the drafts on sign-out and when another account signs in', () => {
    setDraftOwner('alice')
    keepDraft('k', 1)
    setDraftOwner('alice')
    expect(readDraft('k')).toBe(1)
    setDraftOwner('bob')
    expect(readDraft('k')).toBeUndefined()
    keepDraft('k', 2)
    signOutDrafts()
    expect(readDraft('k')).toBeUndefined()
  })
})

function Guarded({ active }) {
  useUnloadGuard(active)
  return <Link to="/elsewhere">away</Link>
}

const mount = (active) => render(
  <MemoryRouter initialEntries={['/form']}>
    <Routes>
      <Route path="/form" element={<Guarded active={active} />} />
      <Route path="/elsewhere" element={<p>arrived</p>} />
    </Routes>
  </MemoryRouter>,
)

describe('useUnloadGuard', () => {
  it('lets a link leave the page without a question while changes are pending', async () => {
    mount(true)
    await act(async () => { fireEvent.click(screen.getByText('away')) })
    expect(screen.getByText('arrived')).toBeInTheDocument()
  })

  it('asks the browser before a reload or a close of the tab', () => {
    mount(true)
    const event = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
  })

  it('asks the browser nothing when nothing is pending', () => {
    mount(false)
    const event = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(false)
  })
})
