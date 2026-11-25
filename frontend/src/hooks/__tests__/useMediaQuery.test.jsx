/** The phone width the CSS switches at, read from matchMedia and read again when the window crosses it. */
import { afterEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { usePhoneWidth } from '../useMediaQuery'
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
})
