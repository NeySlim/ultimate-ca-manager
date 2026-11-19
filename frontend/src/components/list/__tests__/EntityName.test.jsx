/**
 * The name of a row: cut by an ellipsis when the column lacks room, shown whole in a tip
 * on hover and on keyboard focus, never when it already fits.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { EntityName } from '../StatusPill'

const LONG = 'a-very-long-common-name-that-does-not-fit.internal.example.com'
const sizes = (scroll, client) => {
  vi.spyOn(Element.prototype, 'scrollWidth', 'get').mockReturnValue(scroll)
  vi.spyOn(Element.prototype, 'clientWidth', 'get').mockReturnValue(client)
}

describe('EntityName', () => {
  afterEach(() => vi.restoreAllMocks())

  it('is a button whose text can shorten', () => {
    render(<EntityName>{LONG}</EntityName>)
    const name = screen.getByRole('button', { name: LONG })
    expect(name.querySelector('.lv-entity-text')).toHaveTextContent(LONG)
    expect(screen.queryByRole('tooltip')).toBeNull()
  })

  it('shows the whole of a cut name on keyboard focus and hides it on blur or Escape', () => {
    sizes(400, 180)
    render(<EntityName>{LONG}</EntityName>)
    const name = screen.getByRole('button')
    fireEvent.focus(name)
    expect(screen.getByRole('tooltip')).toHaveTextContent(LONG)
    fireEvent.keyDown(name, { key: 'Escape' })
    expect(screen.queryByRole('tooltip')).toBeNull()
    fireEvent.focus(name)
    fireEvent.blur(name)
    expect(screen.queryByRole('tooltip')).toBeNull()
  })

  it('shows it on hover too', () => {
    sizes(400, 180)
    render(<EntityName>{LONG}</EntityName>)
    fireEvent.mouseEnter(screen.getByRole('button'))
    expect(screen.getByRole('tooltip')).toHaveTextContent(LONG)
    fireEvent.mouseLeave(screen.getByRole('button'))
    expect(screen.queryByRole('tooltip')).toBeNull()
  })

  it('shows no tip for a name that fits', () => {
    sizes(180, 180)
    render(<EntityName>short.example.com</EntityName>)
    fireEvent.focus(screen.getByRole('button'))
    expect(screen.queryByRole('tooltip')).toBeNull()
  })

  it('leaves Escape to the page when no tip is shown', () => {
    const onKeyDown = vi.fn()
    render(<div onKeyDown={onKeyDown}><EntityName>short.example.com</EntityName></div>)
    fireEvent.keyDown(screen.getByRole('button'), { key: 'Escape' })
    expect(onKeyDown).toHaveBeenCalledTimes(1)
  })
})
