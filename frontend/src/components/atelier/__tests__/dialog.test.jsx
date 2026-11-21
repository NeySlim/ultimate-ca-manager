/**
 * The mockup's modal(): the focus goes back to the opener, to the element that replaced it, to
 * the declared fallback, else to the page title.
 */
import { useState } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k) => k }) }))

import { AtelierDialog } from '../AtelierDialog'

const frame = () => new Promise((r) => requestAnimationFrame(r))

function Page() {
  const [open, setOpen] = useState(false)
  const [menu, setMenu] = useState(true)
  return (
    <>
      <h1 id="main-title" tabIndex={-1}>T</h1>
      <button type="button" id="fallback">Repli</button>
      {menu && <button type="button" onClick={() => { setOpen(true); setMenu(false) }}>Item de menu</button>}
      {open && <AtelierDialog title="D" returnTo="fallback" onClose={() => setOpen(false)}><button type="button">Dedans</button></AtelierDialog>}
    </>
  )
}

describe('the dialog', () => {
  it('gives the focus to the declared fallback when its opener left the page', async () => {
    render(<Page />)
    const item = screen.getByRole('button', { name: 'Item de menu' })
    item.focus()
    fireEvent.click(item)
    fireEvent.click(screen.getByRole('button', { name: 'common.closeWindow' }))
    await act(frame)
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Repli' }))
  })
  it('gives the first focus to the field the dialog names', () => {
    render(<AtelierDialog title="D" onClose={() => {}}><input aria-label="a" /><input aria-label="b" data-autofocus="" /></AtelierDialog>)
    expect(document.activeElement).toBe(screen.getByRole('textbox', { name: 'b' }))
  })
})
