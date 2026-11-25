/** The phone width the CSS switches at, read from matchMedia and read again when the window crosses it. */
import { afterEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { useMediaQuery, usePhoneWidth } from '../useMediaQuery'
import { phoneScreen } from '../../test/phoneScreen'

function Probe() {
  return <p data-testid="probe">{usePhoneWidth() ? 'phone' : 'wide'}</p>
}

let screenSize
afterEach(() => screenSize?.restore())

describe('usePhoneWidth', () => {
  it('follows (max-width: 800px) as the window is resized', () => {
    screenSize = phoneScreen(false)
    const { unmount } = render(<Probe />)
    expect(screen.getByTestId('probe')).toHaveTextContent('wide')
    screenSize.resize(true)
    expect(screen.getByTestId('probe')).toHaveTextContent('phone')
    screenSize.resize(false)
    expect(screen.getByTestId('probe')).toHaveTextContent('wide')
    unmount()
  })

  it('starts as a phone on a narrow screen', () => {
    screenSize = phoneScreen(true)
    render(<Probe />)
    expect(screen.getByTestId('probe')).toHaveTextContent('phone')
  })

  it('keeps one subscription from one render to the next while the query is the same', () => {
    screenSize = phoneScreen(false)
    const media = window.matchMedia
    let added = 0
    window.matchMedia = (query) => {
      const list = media(query)
      return { ...list, matches: list.matches, addEventListener: (type, fn) => { added += 1; list.addEventListener(type, fn) } }
    }
    function Counter({ n }) {
      return <p data-testid="probe">{`${n}:${useMediaQuery('(max-width: 800px)') ? 'phone' : 'wide'}`}</p>
    }
    const { rerender } = render(<Counter n={1} />)
    rerender(<Counter n={2} />)
    rerender(<Counter n={3} />)
    expect(screen.getByTestId('probe')).toHaveTextContent('3:wide')
    expect(added).toBe(1)
  })
})
