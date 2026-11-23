/**
 * The section of a page on the mockup's sectioned form lives in ?tab=: a link opens on it, a
 * choice writes it (the first section leaves the address bare), stacked frames scroll to it,
 * and a page of one frame at a time gives the new frame's title the focus.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { act, render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'

import { useSectionParam } from '../useSectionParam'
import { SettingsFrame } from '../SettingsView'

afterEach(() => { delete Element.prototype.scrollIntoView })

function Page({ stacked, ready = true }) {
  const [current, select] = useSectionParam(['a', 'b', 'c'], 'a', { stacked, ready })
  const location = useLocation()
  const ids = stacked ? ['a', 'b', 'c'] : [current]
  return (
    <>
      <output data-testid="current">{current}</output>
      <output data-testid="search">{location.search}</output>
      <button type="button" onClick={() => select('c')}>to-c</button>
      <button type="button" onClick={() => select('a')}>to-a</button>
      {ids.map((id) => <SettingsFrame key={id} id={id} label={`Title ${id}`}>{id}</SettingsFrame>)}
    </>
  )
}

const mount = (entry, props) => render(<MemoryRouter initialEntries={[entry]}><Page {...props} /></MemoryRouter>)

describe('useSectionParam', () => {
  it('opens on the section the link names, and on the first one otherwise', () => {
    mount('/x?tab=b', {})
    expect(screen.getByTestId('current')).toHaveTextContent('b')
  })

  it('ignores a section that does not exist', () => {
    mount('/x?tab=zzz', {})
    expect(screen.getByTestId('current')).toHaveTextContent('a')
  })

  it('writes the choice in the address, bare for the first section', () => {
    mount('/x?tab=b&keep=1', {})
    act(() => screen.getByText('to-c').click())
    expect(screen.getByTestId('search')).toHaveTextContent('?tab=c&keep=1')
    act(() => screen.getByText('to-a').click())
    expect(screen.getByTestId('search')).toHaveTextContent('?keep=1')
  })

  it('another section drops the sort of the list it leaves; the same one keeps it', () => {
    mount('/x?tab=b&sort=name&order=desc&keep=1', {})
    act(() => screen.getByText('to-c').click())
    expect(screen.getByTestId('search')).toHaveTextContent('?tab=c&keep=1')
    const again = mount('/x?tab=c&sort=name&order=desc', {})
    act(() => again.getAllByText('to-c').pop().click())
    expect(again.getAllByTestId('search').pop()).toHaveTextContent('?tab=c&sort=name&order=desc')
  })

  it('stacked sections are all on the page: their sorts stay', () => {
    mount('/x?tab=b&sort=name', { stacked: true })
    act(() => screen.getByText('to-c').click())
    expect(screen.getByTestId('search')).toHaveTextContent('?tab=c&sort=name')
  })

  it('gives the title of the newly shown frame the focus', () => {
    mount('/x', {})
    act(() => screen.getByText('to-c').click())
    expect(document.activeElement).toBe(screen.getByRole('heading', { name: 'Title c' }))
  })

  it('scrolls stacked frames to the linked one once the page is ready', () => {
    const scrolled = []
    Element.prototype.scrollIntoView = vi.fn(function scroll() { scrolled.push(this.id) })
    const { rerender } = mount('/x?tab=c', { stacked: true, ready: false })
    expect(scrolled).toEqual([])
    rerender(<MemoryRouter initialEntries={['/x?tab=c']}><Page stacked ready /></MemoryRouter>)
    expect(scrolled).toContain('set-sec-c')
    expect(document.activeElement).toBe(screen.getByRole('heading', { name: 'Title c' }))
  })

  it('lands a link without the keyboard outline, which a later jump keeps', () => {
    Element.prototype.scrollIntoView = vi.fn()
    mount('/x?tab=b', { stacked: true })
    const landed = screen.getByRole('heading', { name: 'Title b' })
    expect(document.activeElement).toBe(landed)
    expect(landed).toHaveAttribute('data-quiet-focus')
    act(() => screen.getByText('to-c').click())
    expect(landed).not.toHaveAttribute('data-quiet-focus')
    const jumped = screen.getByRole('heading', { name: 'Title c' })
    expect(document.activeElement).toBe(jumped)
    expect(jumped).not.toHaveAttribute('data-quiet-focus')
  })
})
