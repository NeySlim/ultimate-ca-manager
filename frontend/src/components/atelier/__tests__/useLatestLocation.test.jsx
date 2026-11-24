/**
 * Two writes to the URL in one handler, before the router draws: the second builds on the first.
 * The history's own address carries it (react-router's UNSAFE_NavigationContext); without it, the
 * last write noted by useLatestNavigate does.
 */
import { useContext, useMemo } from 'react'
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { BrowserRouter, MemoryRouter, Routes, Route, UNSAFE_NavigationContext, useLocation, useNavigate } from 'react-router-dom'
import { useDockParam } from '../useDockParam'
import { useSortParam } from '../useSortParam'

function Where() {
  const loc = useLocation()
  return <output data-testid="url">{loc.pathname + loc.search}</output>
}
const url = () => screen.getByTestId('url').textContent

function SortAndOpen() {
  const d = useDockParam({})
  const { onSort } = useSortParam({ key: 'created', asc: false }, ['created', 'name'])
  return (
    <>
      <button type="button" onClick={() => { d.open(7); onSort('name') }}>openAndSort</button>
      <button type="button" onClick={() => { onSort('name'); d.open(7) }}>sortAndOpen</button>
    </>
  )
}

// The router's history seen through a navigator without `location`, as a react-router that dropped it would give
function WithoutLocation({ children }) {
  const ctx = useContext(UNSAFE_NavigationContext)
  const value = useMemo(() => {
    const h = ctx.navigator
    const navigator = {
      push: (...a) => h.push(...a), replace: (...a) => h.replace(...a), go: (n) => h.go(n),
      createHref: (to) => h.createHref(to), encodeLocation: h.encodeLocation && ((to) => h.encodeLocation(to)),
    }
    return { ...ctx, navigator }
  }, [ctx])
  return <UNSAFE_NavigationContext.Provider value={value}>{children}</UNSAFE_NavigationContext.Provider>
}

const page = (ui) => (
  <Routes>
    <Route path="*" element={<>{ui}<Where /></>} />
  </Routes>
)

describe('useLatestLocation', () => {
  afterEach(() => window.history.replaceState(null, '', '/'))

  // Sentinel: the history's own address, written at once while the drawing waits, is what the hook reads first
  it('reads the browser history\'s address through the navigation context, a write included before it is drawn', () => {
    window.history.replaceState(null, '', '/x?q=a')
    let seen
    function Probe() {
      const { navigator } = useContext(UNSAFE_NavigationContext)
      const navigate = useNavigate()
      return <button type="button" onClick={() => { navigate('/x?q=b', { replace: true }); seen = navigator.location }}>write</button>
    }
    render(<BrowserRouter>{page(<Probe />)}</BrowserRouter>)
    fireEvent.click(screen.getByText('write'))
    expect(typeof seen?.search).toBe('string')
    expect(`${seen.pathname}${seen.search}`).toBe('/x?q=b')
  })

  it('under the browser router, a dock and a sort written in one moment keep each other', () => {
    window.history.replaceState(null, '', '/x?q=a')
    render(<BrowserRouter>{page(<SortAndOpen />)}</BrowserRouter>)
    fireEvent.click(screen.getByText('openAndSort'))
    expect(url()).toBe('/x?q=a&item=7&sort=name&order=asc')
  })

  for (const [button, expected] of [['openAndSort', '/x?q=a&item=7&sort=name&order=asc'], ['sortAndOpen', '/x?q=a&sort=name&order=asc&item=7']]) {
    it(`without the history's address, the last write noted stands for it (${button})`, () => {
      render(<MemoryRouter initialEntries={['/x?q=a']}><WithoutLocation>{page(<SortAndOpen />)}</WithoutLocation></MemoryRouter>)
      fireEvent.click(screen.getByText(button))
      expect(url()).toBe(expected)
    })
  }

  it('strips a base name as the router does, whatever its case', () => {
    render(<MemoryRouter basename="/App" initialEntries={['/app/x?q=a']}>{page(<SortAndOpen />)}</MemoryRouter>)
    expect(url()).toBe('/x?q=a')
    fireEvent.click(screen.getByText('openAndSort'))
    expect(url()).toBe('/x?q=a&item=7&sort=name&order=asc')
  })
})
