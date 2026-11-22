/**
 * The detached windows: several at once, cascaded, the touched one in front, moved by the title
 * bar and the keyboard, closed by the cross or Escape (which the dock under them does not see),
 * kept for the session and inside the viewport; none on a phone.
 */
import { useEffect } from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act, within } from '@testing-library/react'

const size = vi.hoisted(() => ({ isMobile: false, signedIn: true }))
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k, p) => (p?.name ? `${k} ${p.name}` : k) }) }))
vi.mock('../../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: size.isMobile }) }))
vi.mock('../../../contexts/AuthContext', () => ({ useAuth: () => ({ isAuthenticated: size.signedIn }) }))
vi.mock('../../../pages/certificates/CertificateFloat', () => ({
  default: function Body({ ids, onTitle }) {
    useEffect(() => { onTitle(`cert ${ids[0]}`) }, []) // eslint-disable-line react-hooks/exhaustive-deps
    return <p>{`body ${ids[0]}`}</p>
  },
}))

import { DetachedProvider } from '../DetachedContext'
import { DetachedLayer } from '../DetachedLayer'
import { useDetached } from '../useDetached'
import { STEP } from '../geometry'

if (!window.PointerEvent) {
  window.PointerEvent = class extends MouseEvent {
    constructor(type, init = {}) { super(type, init); this.pointerId = init.pointerId ?? 1 }
  }
}

let api
function Grab() { api = useDetached(); return null }
const setup = () => render(<DetachedProvider><Grab /><DetachedLayer /></DetachedProvider>)
const win = (name) => screen.getByRole('dialog', { name })
const box = (el) => ({ x: parseInt(el.style.left, 10), y: parseInt(el.style.top, 10), w: parseInt(el.style.width, 10), h: parseInt(el.style.height, 10), z: Number(el.style.zIndex) })

beforeEach(() => {
  size.isMobile = false
  size.signedIn = true
  sessionStorage.clear()
  window.innerWidth = 1600
  window.innerHeight = 1000
})
afterEach(() => { vi.restoreAllMocks() })

describe('detached windows', () => {
  it('opens several non-modal windows, cascaded, named by their object, the last in front', async () => {
    setup()
    act(() => { api.open('certificate', [7]) })
    act(() => { api.open('certificate', [8]) })
    const a = await screen.findByRole('dialog', { name: 'cert 7' })
    const b = await screen.findByRole('dialog', { name: 'cert 8' })
    expect(a).toHaveAttribute('aria-modal', 'false')
    expect(within(a).getByText('body 7')).toBeInTheDocument()
    expect(box(b).x).toBeGreaterThan(box(a).x)
    expect(box(b).y).toBeGreaterThan(box(a).y)
    expect(box(b).z).toBeGreaterThan(box(a).z)
  })

  it('brings the window touched in front of the others', async () => {
    setup()
    act(() => { api.open('certificate', [7]); api.open('certificate', [8]) })
    const a = await screen.findByRole('dialog', { name: 'cert 7' })
    fireEvent.pointerDown(within(a).getByText('body 7'))
    expect(box(win('cert 7')).z).toBeGreaterThan(box(win('cert 8')).z)
    // Its node stays where it is: moved under a press, the browser would drop the click that follows
    expect([...document.querySelectorAll('[data-detached]')].map((el) => el.dataset.detached)).toEqual(['certificate:7', 'certificate:8'])
  })

  it('closes the window that has the focus on Escape, the event marked handled for the dock', async () => {
    setup()
    act(() => { api.open('certificate', [7]); api.open('certificate', [8]) })
    const a = await screen.findByRole('dialog', { name: 'cert 7' })
    const seen = vi.fn()
    window.addEventListener('keydown', seen)
    fireEvent.keyDown(within(a).getByText('body 7'), { key: 'Escape' })
    window.removeEventListener('keydown', seen)
    expect(screen.queryByRole('dialog', { name: 'cert 7' })).toBeNull()
    expect(screen.getByRole('dialog', { name: 'cert 8' })).toBeInTheDocument()
    expect(seen.mock.calls[0][0].defaultPrevented).toBe(true)
  })

  it('closes by its cross', async () => {
    setup()
    act(() => { api.open('certificate', [7]) })
    const a = await screen.findByRole('dialog', { name: 'cert 7' })
    fireEvent.click(within(a).getByRole('button', { name: 'detached.close cert 7' }))
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('moves by its title bar and by the keyboard of its handle, resizes with Shift', async () => {
    setup()
    act(() => { api.open('certificate', [7]) })
    const a = await screen.findByRole('dialog', { name: 'cert 7' })
    const start = box(a)
    fireEvent.pointerDown(a.querySelector('.float-title'), { clientX: 300, clientY: 200, button: 0 })
    fireEvent.pointerMove(window, { clientX: 350, clientY: 230 })
    fireEvent.pointerUp(window, { clientX: 350, clientY: 230 })
    expect(box(win('cert 7'))).toMatchObject({ x: start.x + 50, y: start.y + 30, w: start.w, h: start.h })
    const handle = within(win('cert 7')).getByRole('button', { name: 'detached.moveHandle' })
    fireEvent.keyDown(handle, { key: 'ArrowLeft' })
    expect(box(win('cert 7')).x).toBe(start.x + 50 - STEP)
    fireEvent.keyDown(handle, { key: 'ArrowDown', shiftKey: true })
    expect(box(win('cert 7'))).toMatchObject({ y: start.y + 30, h: start.h + STEP })
  })

  it('resizes by an edge', async () => {
    setup()
    act(() => { api.open('certificate', [7]) })
    const a = await screen.findByRole('dialog', { name: 'cert 7' })
    const start = box(a)
    fireEvent.pointerDown(a.querySelector('[data-edge="se"]'), { clientX: 500, clientY: 500, button: 0 })
    fireEvent.pointerMove(window, { clientX: 540, clientY: 560 })
    fireEvent.pointerUp(window)
    expect(box(win('cert 7'))).toMatchObject({ x: start.x, y: start.y, w: start.w + 40, h: start.h + 60 })
  })

  it('keeps its place for the session and comes back inside a narrower browser window', async () => {
    const first = setup()
    act(() => { api.open('certificate', [7]) })
    const a = await screen.findByRole('dialog', { name: 'cert 7' })
    fireEvent.keyDown(within(a).getByRole('button', { name: 'detached.moveHandle' }), { key: 'ArrowRight' })
    const placed = box(win('cert 7'))
    first.unmount()
    setup()
    expect(box(await screen.findByRole('dialog', { name: 'cert 7' }))).toMatchObject({ x: placed.x, y: placed.y })
    act(() => { window.innerWidth = 700; window.dispatchEvent(new Event('resize')) })
    const now = box(win('cert 7'))
    expect(now.x + now.w).toBeLessThanOrEqual(700)
    expect(now.x).toBeGreaterThanOrEqual(0)
  })

  it('keeps the windows while the session is checked at load, and drops them at a sign-out', async () => {
    const first = setup()
    act(() => { api.open('certificate', [7]) })
    await screen.findByRole('dialog', { name: 'cert 7' })
    first.unmount()
    // A reload: the session is not known yet when the shell mounts
    size.signedIn = false
    const second = setup()
    size.signedIn = true
    second.rerender(<DetachedProvider><Grab /><DetachedLayer /></DetachedProvider>)
    expect(await screen.findByRole('dialog', { name: 'cert 7' })).toBeInTheDocument()
    size.signedIn = false
    second.rerender(<DetachedProvider><Grab /><DetachedLayer /></DetachedProvider>)
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(api.windows).toEqual([])
  })

  it('draws no window on a phone', () => {
    size.isMobile = true
    setup()
    act(() => { api.open('certificate', [7]) })
    expect(api.available).toBe(false)
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})
