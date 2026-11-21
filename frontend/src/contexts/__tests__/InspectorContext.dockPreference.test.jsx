/**
 * One dock preference for every page (the mockup's state.dock, height, width, collapsed): the
 * account's `inspector` preference, read by the Certificates dock and by every module dock alike.
 * The old per-browser keys of the module docks are carried over once when the account has none.
 */
import { useState } from 'react'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }))
vi.mock('../AuthContext', () => ({ useAuth: () => ({ isAuthenticated: true }) }))
vi.mock('../MobileContext', () => ({ useMobile: () => ({ isMobile: false }) }))
const saved = vi.hoisted(() => ({ calls: [] }))
vi.mock('../../services/account.service', () => ({
  accountService: { updatePreferences: (p) => { saved.calls.push(p); return Promise.resolve() } },
}))

import { InspectorProvider, useInspector } from '../InspectorContext'
import { Dock } from '../../components/atelier/Dock'
import { Zone } from '../../components/atelier/Zone'
import { applyServerPreferences, setAuthenticated } from '../../stores/userPreferencesStore'

/** A page with one open object in its dock; `closable` draws it as the Certificates dock (closable tabs). */
function ModulePage({ id = 'a', closable = false }) {
  const [open, setOpen] = useState(true)
  const tabs = [{ key: id, title: id, icon: 'cert' }]
  return (
    <Zone dock={open && (
      <Dock label={`dock ${id}`} tabsLabel="open" tabs={tabs} activeKey={id} onClose={() => setOpen(false)}
        onCloseTab={closable ? () => setOpen(false) : undefined}>
        <p>{`body ${id}`}</p>
      </Dock>
    )} />
  )
}

function App({ page }) {
  return <InspectorProvider>{page}</InspectorProvider>
}

const LEGACY = ['ucm-atelier-dock-side', 'ucm-atelier-dock-height', 'ucm-atelier-dock-width']
const app = () => document.getElementById('app')
const grip = () => screen.getByRole('separator')

beforeEach(() => {
  localStorage.clear()
  saved.calls = []
  setAuthenticated(false)
  window.innerWidth = 1600
  window.innerHeight = 1000
})

describe('one dock preference for every page', () => {
  it('opens a module dock at the right after the Certificates dock was put there, and back', () => {
    const { rerender } = render(<App page={<ModulePage id="cert" closable />} />)
    fireEvent.click(screen.getByRole('button', { name: 'inspector.dockRight' }))
    expect(app()).toHaveClass('dock-right')
    rerender(<App page={<ModulePage id="templates" key="templates" />} />)
    expect(screen.getByText('body templates')).toBeInTheDocument()
    expect(app()).toHaveClass('dock-right')
    fireEvent.click(screen.getByRole('button', { name: 'inspector.dockBottom' }))
    rerender(<App page={<ModulePage id="cert" key="cert" closable />} />)
    expect(app()).not.toHaveClass('dock-right')
  })

  it('shares the height and the width between pages, and keeps no key of its own in the browser', () => {
    const { rerender } = render(<App page={<ModulePage id="users" />} />)
    fireEvent.keyDown(grip(), { key: 'ArrowUp' })
    expect(grip()).toHaveAttribute('aria-valuenow', '298')
    rerender(<App page={<ModulePage id="hsm" key="hsm" />} />)
    expect(grip()).toHaveAttribute('aria-valuenow', '298')
    fireEvent.click(screen.getByRole('button', { name: 'inspector.dockRight' }))
    fireEvent.keyDown(grip(), { key: 'ArrowLeft' })
    rerender(<App page={<ModulePage id="cert" key="cert" closable />} />)
    expect(grip()).toHaveAttribute('aria-valuenow', '480')
    for (const k of LEGACY) expect(localStorage.getItem(k)).toBeNull()
  })

  it('writes the choice to the account preference', async () => {
    setAuthenticated(true)
    applyServerPreferences({ inspector: { position: 'bottom', height: 278, width: 460 } })
    render(<App page={<ModulePage id="rbac" />} />)
    fireEvent.click(screen.getByRole('button', { name: 'inspector.dockRight' }))
    await act(async () => { await Promise.resolve() })
    expect(saved.calls.at(-1).inspector).toEqual({ position: 'right', height: 278, width: 460 })
  })

  it('keeps the fold from page to page; opening another object unfolds it', () => {
    const { rerender } = render(<App page={<ModulePage id="policies" />} />)
    fireEvent.click(screen.getByRole('button', { name: 'inspector.collapse' }))
    expect(document.getElementById('inspector')).toHaveClass('collapsed')
    // The Certificates dock shown again (its objects stayed open) keeps the fold, as the mockup's state.collapsed
    rerender(<App page={<ModulePage id="cert" key="cert" closable />} />)
    expect(document.getElementById('inspector')).toHaveClass('collapsed')
    // A module object opened unfolds it, as the mockup's openItem()
    rerender(<App page={<ModulePage id="tsa" key="tsa" />} />)
    expect(document.getElementById('inspector')).not.toHaveClass('collapsed')
  })
})

describe('close on navigate', () => {
  let api
  function Probe() {
    api = useInspector()
    return null
  }
  const PREFS = 'ucm-inspector-prefs'

  it('is off by default: the open objects stay across pages, as the mockup', () => {
    render(<App page={<Probe />} />)
    expect(api.closeOnNav).toBe(false)
  })

  it.each([[true], [false]])('keeps the value %s a browser already set', (value) => {
    localStorage.setItem(PREFS, JSON.stringify({ closeOnNav: value, position: 'right' }))
    render(<App page={<Probe />} />)
    expect(api.closeOnNav).toBe(value)
  })

  it('is still set from the account page', () => {
    render(<App page={<Probe />} />)
    act(() => api.toggleCloseOnNav())
    expect(api.closeOnNav).toBe(true)
    expect(JSON.parse(localStorage.getItem(PREFS)).closeOnNav).toBe(true)
  })
})

describe('the old per-browser dock keys', () => {
  const legacy = () => {
    localStorage.setItem('ucm-atelier-dock-side', JSON.stringify('right'))
    localStorage.setItem('ucm-atelier-dock-width', JSON.stringify(520))
    localStorage.setItem('ucm-atelier-dock-height', JSON.stringify(300))
  }

  it('become the account preference once when the account has none', async () => {
    legacy()
    setAuthenticated(true)
    render(<App page={<ModulePage id="csrs" />} />)
    act(() => applyServerPreferences({ theme: 'dark' }))
    await act(async () => { await Promise.resolve() })
    expect(app()).toHaveClass('dock-right')
    expect(grip()).toHaveAttribute('aria-valuenow', '520')
    expect(saved.calls.at(-1)).toEqual({ theme: 'dark', inspector: { position: 'right', height: 300, width: 520 } })
    for (const k of LEGACY) expect(localStorage.getItem(k)).toBeNull()
  })

  it('give way to the preference the account already has', async () => {
    legacy()
    setAuthenticated(true)
    render(<App page={<ModulePage id="csrs" />} />)
    act(() => applyServerPreferences({ inspector: { position: 'bottom', height: 260, width: 400 } }))
    await act(async () => { await Promise.resolve() })
    expect(app()).not.toHaveClass('dock-right')
    expect(grip()).toHaveAttribute('aria-valuenow', '260')
    expect(saved.calls).toEqual([])
    for (const k of LEGACY) expect(localStorage.getItem(k)).toBeNull()
  })

  it('are carried over when the preferences were loaded before the inspector', async () => {
    legacy()
    setAuthenticated(true)
    applyServerPreferences({})
    render(<App page={<ModulePage id="csrs" />} />)
    await act(async () => { await Promise.resolve() })
    expect(app()).toHaveClass('dock-right')
    expect(saved.calls.at(-1).inspector).toEqual({ position: 'right', height: 300, width: 520 })
  })
})
