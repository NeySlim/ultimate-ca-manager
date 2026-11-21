/**
 * The object open in a dock and its section live in the URL (`?item=`, `?section=`): a reload or a
 * shared link reopens them, the browser's Back closes the dock, a section change adds no step.
 */
import { useState } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useLocation, useNavigate } from 'react-router-dom'
import { useDockParam, useDockSelection, useDockId } from '../useDockParam'

let nav
function Where() {
  const loc = useLocation()
  nav = useNavigate()
  return <output data-testid="url">{loc.pathname + loc.search}</output>
}

function Probe({ opts }) {
  const d = useDockParam(opts)
  return (
    <div>
      <span data-testid="item">{String(d.item)}</span>
      <span data-testid="section">{d.section}</span>
      <button type="button" onClick={() => d.open(7)}>open7</button>
      <button type="button" onClick={() => d.open('8', { section: 'chain' })}>open8</button>
      <button type="button" onClick={() => d.setSection('chain')}>chain</button>
      <button type="button" onClick={() => d.setSection('overview')}>overview</button>
      <button type="button" onClick={d.close}>close</button>
    </div>
  )
}

const at = (url, ui) => render(
  <MemoryRouter initialEntries={['/elsewhere', url]} initialIndex={1}>
    <Routes>
      <Route path="*" element={<>{ui}<Where /></>} />
    </Routes>
  </MemoryRouter>,
)
const url = () => screen.getByTestId('url').textContent

describe('useDockParam', () => {
  it('reads the object and its section from the URL', () => {
    at('/templates?item=3&section=subject', <Probe opts={{ sections: ['overview', 'subject'] }} />)
    expect(screen.getByTestId('item')).toHaveTextContent('3')
    expect(screen.getByTestId('section')).toHaveTextContent('subject')
  })

  it('falls back to the first section for an unknown one', () => {
    at('/templates?item=3&section=nope', <Probe opts={{ sections: ['overview', 'subject'] }} />)
    expect(screen.getByTestId('section')).toHaveTextContent('overview')
  })

  it('opens into the URL, keeps the other parameters, and Back closes', async () => {
    at('/users?tab=groups', <Probe opts={{ sections: ['overview', 'chain'] }} />)
    fireEvent.click(screen.getByText('open7'))
    expect(url()).toBe('/users?tab=groups&item=7')
    act(() => nav(-1))
    await waitFor(() => expect(url()).toBe('/users?tab=groups'))
    expect(screen.getByTestId('item')).toHaveTextContent('null')
  })

  it('changes section without a history step: one Back still closes', async () => {
    at('/x', <Probe opts={{ sections: ['overview', 'chain'] }} />)
    fireEvent.click(screen.getByText('open7'))
    fireEvent.click(screen.getByText('chain'))
    expect(url()).toBe('/x?item=7&section=chain')
    fireEvent.click(screen.getByText('overview'))
    expect(url()).toBe('/x?item=7')
    fireEvent.click(screen.getByText('chain'))
    act(() => nav(-1))
    await waitFor(() => expect(url()).toBe('/x'))
  })

  it('switching to another object starts on its asked section and adds no step', async () => {
    at('/x', <Probe opts={{ sections: ['overview', 'chain'] }} />)
    fireEvent.click(screen.getByText('open7'))
    fireEvent.click(screen.getByText('chain'))
    fireEvent.click(screen.getByText('open7'))
    expect(url()).toBe('/x?item=7&section=chain')
    fireEvent.click(screen.getByText('open8'))
    expect(url()).toBe('/x?item=8&section=chain')
    act(() => nav(-1))
    await waitFor(() => expect(url()).toBe('/x'))
  })

  it('closing a dock it opened steps back, so Back then leaves the page', async () => {
    at('/x?q=a', <Probe opts={{}} />)
    fireEvent.click(screen.getByText('open7'))
    fireEvent.click(screen.getByText('close'))
    await waitFor(() => expect(url()).toBe('/x?q=a'))
    act(() => nav(-1))
    await waitFor(() => expect(url()).toBe('/elsewhere'))
  })

  it('closing a dock that came with the link only drops the object', () => {
    at('/x?q=a&item=4&section=chain', <Probe opts={{}} />)
    fireEvent.click(screen.getByText('close'))
    expect(url()).toBe('/x?q=a')
  })

  it('reads a former name (the palette\'s ?selected=) and writes the convention', () => {
    at('/templates?selected=6', <Probe opts={{ aliases: ['selected'] }} />)
    expect(screen.getByTestId('item')).toHaveTextContent('6')
    fireEvent.click(screen.getByText('chain'))
    expect(url()).toBe('/templates?item=6&section=chain')
  })
})

function List({ rows, ready = true, load }) {
  const [, rerender] = useState(0)
  const { selected, select, section, setSection } = useDockSelection(rows, { ready, load, sections: ['overview', 'subject'] })
  return (
    <div>
      <span data-testid="sel">{selected ? selected.name : 'none'}</span>
      <span data-testid="section">{section}</span>
      {rows.map((r) => <button key={r.id} type="button" onClick={() => select(r)}>{r.name}</button>)}
      <button type="button" onClick={() => select({ id: 9, name: 'fresh' })}>created</button>
      <button type="button" onClick={() => { select({ id: 9, name: 'fresh' }); setSection('subject') }}>created on subject</button>
      <button type="button" onClick={() => setSection('subject')}>subject</button>
      <button type="button" onClick={() => select(null)}>close</button>
      <button type="button" onClick={() => rerender((n) => n + 1)}>again</button>
    </div>
  )
}
const rows = [{ id: 1, name: 'one' }, { id: 2, name: 'two' }]

function ListProbe({ list }) {
  const d = useDockParam({ list })
  return (
    <div>
      <span data-testid="list">{d.list.join('|')}</span>
      <button type="button" onClick={() => d.open(8, { list: [7, 8] })}>open8of2</button>
      <button type="button" onClick={() => d.setList([8])}>only8</button>
      <button type="button" onClick={() => d.setSection('chain')}>chain</button>
      <button type="button" onClick={d.close}>close</button>
    </div>
  )
}

describe('useDockParam with several open objects (list)', () => {
  it('keeps them in `open` once there are two, the shown one as `item`, a section change keeping them', () => {
    at('/certificates?item=7&q=web', <ListProbe list />)
    fireEvent.click(screen.getByText('open8of2'))
    expect(url()).toBe('/certificates?q=web&item=8&open=7%2C8')
    expect(screen.getByTestId('list')).toHaveTextContent('7|8')
    fireEvent.click(screen.getByText('chain'))
    expect(url()).toBe('/certificates?q=web&item=8&section=chain&open=7%2C8')
    fireEvent.click(screen.getByText('only8'))
    expect(url()).toBe('/certificates?q=web&item=8&section=chain')
  })

  it('drops the list with the last object', () => {
    at('/certificates?item=8&open=7,8', <ListProbe list />)
    fireEvent.click(screen.getByText('close'))
    expect(url()).toBe('/certificates')
  })

  it('leaves an `open` parameter alone on a dock without a list', () => {
    at('/elsewhere?open=x&item=3', <ListProbe list={false} />)
    expect(screen.getByTestId('list')).toHaveTextContent('')
    fireEvent.click(screen.getByText('close'))
    expect(url()).toBe('/elsewhere?open=x')
  })
})

describe('useDockSelection', () => {
  it('reopens the object of the URL once the list is there', () => {
    at('/t?item=2&section=subject', <List rows={rows} />)
    expect(screen.getByTestId('sel')).toHaveTextContent('two')
    expect(screen.getByTestId('section')).toHaveTextContent('subject')
  })

  it('holds an object not yet in the list (just created)', () => {
    at('/t', <List rows={rows} />)
    fireEvent.click(screen.getByText('created'))
    expect(screen.getByTestId('sel')).toHaveTextContent('fresh')
    expect(url()).toBe('/t?item=9')
  })

  it('a section set in the same handler as an open applies to the object just opened', () => {
    at('/t?item=1', <List rows={rows} />)
    fireEvent.click(screen.getByText('created on subject'))
    expect(url()).toBe('/t?item=9&section=subject')
  })

  it('a row starts on the first section', () => {
    at('/t?item=1&section=subject', <List rows={rows} />)
    fireEvent.click(screen.getByText('two'))
    expect(url()).toBe('/t?item=2')
    expect(screen.getByTestId('section')).toHaveTextContent('overview')
  })

  it('reads an object off the list by id', async () => {
    const load = vi.fn(async (id) => ({ id: Number(id), name: `loaded ${id}` }))
    at('/t?item=38', <List rows={rows} load={load} />)
    await waitFor(() => expect(screen.getByTestId('sel')).toHaveTextContent('loaded 38'))
    expect(load).toHaveBeenCalledWith('38')
  })

  it('drops an object that no longer exists, without waiting for a list still loading', async () => {
    const { rerender } = at('/t?item=77', <List rows={[]} ready={false} />)
    expect(url()).toBe('/t?item=77')
    rerender(
      <MemoryRouter initialEntries={['/t?item=77']}>
        <Routes><Route path="*" element={<><List rows={rows} /><Where /></>} /></Routes>
      </MemoryRouter>,
    )
    await waitFor(() => expect(url()).toBe('/t'))
    expect(screen.getByTestId('sel')).toHaveTextContent('none')
  })
})

function Ids() {
  const { openId, setOpenId } = useDockId()
  return (
    <div>
      <span data-testid="id">{JSON.stringify(openId)}</span>
      <button type="button" onClick={() => setOpenId(12)}>twelve</button>
      <button type="button" onClick={() => setOpenId('iot')}>iot</button>
      <button type="button" onClick={() => setOpenId(null)}>none</button>
    </div>
  )
}

describe('useDockId', () => {
  it('reads a number back as a number, a name as a name, and null closes', async () => {
    at('/x', <Ids />)
    fireEvent.click(screen.getByText('twelve'))
    expect(screen.getByTestId('id')).toHaveTextContent('12')
    expect(screen.getByTestId('id').textContent).toBe('12')
    fireEvent.click(screen.getByText('iot'))
    expect(screen.getByTestId('id').textContent).toBe('"iot"')
    fireEvent.click(screen.getByText('none'))
    await waitFor(() => expect(url()).toBe('/x'))
    expect(screen.getByTestId('id').textContent).toBe('null')
  })
})
