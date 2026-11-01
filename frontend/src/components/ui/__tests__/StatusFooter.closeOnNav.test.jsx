/**
 * "Close on navigate" closes the floating windows when the operator changes page.
 * A detail link (/certificates/12) that settles on its list page is the same page.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, act } from '@testing-library/react'
import { MemoryRouter, useNavigate } from 'react-router-dom'

const wm = vi.hoisted(() => ({ closeAll: vi.fn(), windowCount: 1 }))

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key, fallback) => fallback ?? key }) }))
vi.mock('../../../contexts/WindowManagerContext', () => ({
  useWindowManager: () => ({
    windowCount: wm.windowCount, closeAll: wm.closeAll, tileWindows: vi.fn(), stackWindows: vi.fn(),
    sameWindow: true, closeOnNav: true, toggleSameWindow: vi.fn(), toggleCloseOnNav: vi.fn(),
  }),
}))

import { StatusFooter } from '../StatusFooter'

let navigate
function Navigator() {
  navigate = useNavigate()
  return null
}

function renderAt(path) {
  render(<MemoryRouter initialEntries={[path]}><Navigator /><StatusFooter /></MemoryRouter>)
}

describe('StatusFooter close on navigate', () => {
  beforeEach(() => { wm.closeAll.mockReset(); wm.windowCount = 1 })

  it('keeps the window a direct link opened when the URL settles on the list', () => {
    renderAt('/certificates/12')
    act(() => navigate('/certificates', { replace: true }))
    expect(wm.closeAll).not.toHaveBeenCalled()
  })

  it('keeps the window a link to another certificate opened', () => {
    renderAt('/certificates')
    act(() => navigate('/certificates/13'))
    act(() => navigate('/certificates', { replace: true }))
    expect(wm.closeAll).not.toHaveBeenCalled()
  })

  it.each([['/certificates', '/cas'], ['/certificates/12', '/cas'], ['/ssh/cas', '/ssh/certificates']])(
    'closes the windows from %s to %s', (from, to) => {
      renderAt(from)
      act(() => navigate(to))
      expect(wm.closeAll).toHaveBeenCalledTimes(1)
    })
})
