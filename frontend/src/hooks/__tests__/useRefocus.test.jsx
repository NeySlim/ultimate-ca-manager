/** A test button disabled while it runs gets the focus back when the run ends. */
import { describe, it, expect } from 'vitest'
import { useRef } from 'react'
import { render, screen } from '@testing-library/react'
import { useRefocusAfter } from '../useRefocus'

function Zone({ busy }) {
  const ref = useRef(null)
  useRefocusAfter(busy, ref)
  return (
    <>
      <button type="button" ref={ref} disabled={busy}>Test</button>
      <input aria-label="other" />
    </>
  )
}

describe('useRefocusAfter', () => {
  it('gives the focus back to the button the browser took it from', () => {
    const { rerender } = render(<Zone busy={false} />)
    const button = screen.getByRole('button', { name: 'Test' })
    button.focus()
    rerender(<Zone busy />)
    // A browser drops the focus of a button that becomes disabled: the page keeps it
    const gone = document.createElement('input')
    document.body.appendChild(gone)
    gone.focus()
    gone.remove()
    expect(document.activeElement).toBe(document.body)
    rerender(<Zone busy={false} />)
    expect(document.activeElement).toBe(button)
  })

  it('leaves the focus where the user put it meanwhile', () => {
    const { rerender } = render(<Zone busy={false} />)
    const button = screen.getByRole('button', { name: 'Test' })
    button.focus()
    rerender(<Zone busy />)
    screen.getByLabelText('other').focus()
    rerender(<Zone busy={false} />)
    expect(document.activeElement).toBe(screen.getByLabelText('other'))
  })
})
