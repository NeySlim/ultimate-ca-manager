/** The whole interface switches to its phone layout at 800 px, as the Atelier mockup and the CSS do. */
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MobileProvider, useMobile } from '../MobileContext'

function Probe() {
  const { isMobile, isDesktop } = useMobile()
  return <output>{`${isMobile}/${isDesktop}`}</output>
}

const at = (width) => {
  window.innerWidth = width
  return render(<MobileProvider><Probe /></MobileProvider>)
}

afterEach(() => { window.innerWidth = 1024 })

describe('MobileContext threshold', () => {
  it.each([[800, 'true/false'], [801, 'false/true'], [880, 'false/true'], [390, 'true/false']])('at %i px reads %s', (width, expected) => {
    at(width)
    expect(screen.getByRole('status')).toHaveTextContent(expected)
  })
})
