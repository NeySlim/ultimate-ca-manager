/**
 * The inspector dock of the Atelier mockup: its frame (grip, size, fold, close, Escape, the right
 * anchoring read by the zone), its open tabs (closable, keyboard) and its body (section tabs), on
 * a phone a modal dialog; the focus comes back to the row button of the object on close.
 */
import { useState } from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const size = vi.hoisted(() => ({ isMobile: false }))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, p) => (p ? `${k} ${JSON.stringify(p)}` : k), i18n: { language: 'fr' } }),
}))
vi.mock('../../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: size.isMobile }) }))

import { Dock, DockBody } from '../Dock'
import { Zone } from '../Zone'
import { DOCK_RIGHT_MIN } from '../dockSide'

const frame = () => new Promise((r) => requestAnimationFrame(r))
const sections = [['overview', 'Aperçu'], ['chain', 'Chaîne'], ['history', 'Historique']]

function Page({ multi = false, onCloseSpy = () => {} }) {
  const [open, setOpen] = useState(true)
  const [tabs, setTabs] = useState([{ key: 1, title: 'vpn', icon: 'cert' }, { key: 2, title: 'api', icon: 'cert' }])
  const [active, setActive] = useState(1)
  const [section, setSection] = useState('overview')
  const dock = open && (
    <Dock label="Inspecteur" tabsLabel="Ouverts" tabs={multi ? tabs : tabs.slice(0, 1)} activeKey={active} onSelectTab={setActive}
      onCloseTab={multi ? (k) => setTabs((all) => all.filter((x) => x.key !== k)) : undefined} onClose={() => { onCloseSpy(); setOpen(false) }}>
      <DockBody icon="cert" title={`Objet ${active}`} badge={<span>Valide</span>} actions={<button type="button">Exporter</button>}
        sections={sections} section={section} onSection={setSection} sectionsLabel="Sections">
        <p>{`panneau ${section}`}</p>
      </DockBody>
    </Dock>
  )
  return (
    <Zone dock={dock}>
      <button type="button" data-open="1">vpn</button>
      <button type="button" onClick={() => setOpen(true)}>rouvrir</button>
    </Zone>
  )
}

beforeEach(() => {
  size.isMobile = false
  localStorage.clear()
  window.innerWidth = 1600
  window.innerHeight = 1000
})

describe('the dock frame', () => {
  it('resizes from its grip with the arrows, Home and End, within its bounds', () => {
    render(<Page />)
    const grip = screen.getByRole('separator', { name: 'inspector.resizeHeight' })
    expect(grip).toHaveAttribute('aria-valuenow', '278')
    fireEvent.keyDown(grip, { key: 'ArrowUp' })
    expect(grip).toHaveAttribute('aria-valuenow', '298')
    fireEvent.keyDown(grip, { key: 'End' })
    expect(grip).toHaveAttribute('aria-valuenow', '450')
    fireEvent.keyDown(grip, { key: 'ArrowUp' })
    expect(grip).toHaveAttribute('aria-valuenow', '450')
    fireEvent.keyDown(grip, { key: 'Home' })
    expect(grip).toHaveAttribute('aria-valuenow', '210')
    expect(document.getElementById('inspector').style.getPropertyValue('--dock')).toBe('210px')
  })
  it('grows and shrinks by its size button, folds and unfolds its body', () => {
    render(<Page />)
    fireEvent.click(screen.getByRole('button', { name: 'inspector.grow' }))
    expect(screen.getByRole('separator')).toHaveAttribute('aria-valuenow', '420')
    fireEvent.click(screen.getByRole('button', { name: 'inspector.shrink' }))
    expect(screen.getByRole('separator')).toHaveAttribute('aria-valuenow', '278')
    fireEvent.click(screen.getByRole('button', { name: 'inspector.collapse' }))
    expect(document.getElementById('inspector')).toHaveClass('collapsed')
    expect(screen.queryByText('panneau overview')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'inspector.expand' }))
    expect(screen.getByText('panneau overview')).toBeInTheDocument()
  })
  it('closes on its button and on Escape from anywhere, the focus back on the row button', async () => {
    const spy = vi.fn()
    render(<Page onCloseSpy={spy} />)
    // jsdom draws no box: the row button is said to be on screen
    const row = screen.getByRole('button', { name: 'vpn' })
    row.getClientRects = () => [{ width: 10, height: 10 }]
    fireEvent.keyDown(document.body, { key: 'Escape' })
    expect(spy).toHaveBeenCalledTimes(1)
    expect(document.getElementById('inspector')).toBeNull()
    await act(frame)
    expect(document.activeElement).toBe(row)
    fireEvent.click(screen.getByRole('button', { name: 'rouvrir' }))
    fireEvent.click(screen.getByRole('button', { name: 'inspector.close' }))
    expect(spy).toHaveBeenCalledTimes(2)
    await act(frame)
    expect(document.activeElement).toBe(row)
  })
  it('leaves Escape to an open dialog or menu', () => {
    const spy = vi.fn()
    render(<><Page onCloseSpy={spy} /><div role="menu">menu</div></>)
    fireEvent.keyDown(document.body, { key: 'Escape' })
    expect(spy).not.toHaveBeenCalled()
  })
  it('anchors at the right on a wide window: the zone reads it, the grip sets the width', () => {
    const { container } = render(<Page />)
    fireEvent.click(screen.getByRole('button', { name: 'inspector.dockRight' }))
    expect(container.querySelector('#app')).toHaveClass('dock-right')
    const grip = screen.getByRole('separator', { name: 'inspector.resizeWidth' })
    expect(grip).toHaveAttribute('aria-valuenow', '460')
    fireEvent.keyDown(grip, { key: 'ArrowLeft' })
    expect(grip).toHaveAttribute('aria-valuenow', '480')
    expect(screen.queryByRole('button', { name: 'inspector.collapse' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'inspector.dockBottom' }))
    expect(container.querySelector('#app')).not.toHaveClass('dock-right')
  })
  it('offers no right anchoring on a narrower window', () => {
    window.innerWidth = 1100
    render(<Page />)
    expect(screen.queryByRole('button', { name: 'inspector.dockRight' })).toBeNull()
  })
  it('offers the right from the one named threshold, 1200 px', () => {
    expect(DOCK_RIGHT_MIN).toBe(1200)
    window.innerWidth = DOCK_RIGHT_MIN - 1
    const { unmount } = render(<Page />)
    expect(screen.queryByRole('button', { name: 'inspector.dockRight' })).toBeNull()
    unmount()
    window.innerWidth = DOCK_RIGHT_MIN
    render(<Page />)
    expect(screen.getByRole('button', { name: 'inspector.dockRight' })).toBeInTheDocument()
  })
  it('covers the screen as a modal dialog on a phone, its close button focused', () => {
    size.isMobile = true
    render(<Page />)
    const dock = screen.getByRole('dialog', { name: 'Inspecteur' })
    expect(dock).toHaveAttribute('aria-modal', 'true')
    expect(document.activeElement).toBe(within(dock).getByRole('button', { name: 'inspector.close' }))
  })
})

describe('the dock on a phone', () => {
  // jsdom draws no box: every element is said to be on screen
  let rects
  beforeEach(() => {
    size.isMobile = true
    rects = vi.spyOn(Element.prototype, 'getClientRects').mockReturnValue([{ width: 10, height: 10 }])
    return () => rects.mockRestore()
  })
  const Shell = (props) => (
    <>
      <a className="skip" href="#main">skip</a>
      <header className="masthead"><button type="button">menu</button></header>
      <Page {...props} />
      <footer className="statusbar"><button type="button">nodes</button></footer>
    </>
  )

  it('keeps the focus in the dock: 40 Tab presses, then Shift Tab, never leave it', async () => {
    const user = userEvent.setup()
    render(<Shell />)
    const dock = screen.getByRole('dialog', { name: 'Inspecteur' })
    for (let i = 0; i < 40; i += 1) {
      await user.tab()
      expect(dock.contains(document.activeElement)).toBe(true)
    }
    for (let i = 0; i < 12; i += 1) {
      await user.tab({ shift: true })
      expect(dock.contains(document.activeElement)).toBe(true)
    }
  })

  it('makes the page, the bars and the skip link inert behind it, until it closes', () => {
    const { container } = render(<Shell />)
    const behind = [container.querySelector('.page-content'), container.querySelector('.masthead'),
      container.querySelector('.statusbar'), container.querySelector('.skip')]
    for (const el of behind) expect(el).toHaveAttribute('inert')
    expect(document.getElementById('inspector').closest('[inert]')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'inspector.close' }))
    for (const el of behind) expect(el).not.toHaveAttribute('inert')
  })

  it('lifts the inertness of the part of the page that holds a dialog opened over the dock', async () => {
    function WithDialog() {
      const [asking, setAsking] = useState(false)
      return (
        <Zone dock={(
          <Dock label="Inspecteur" tabsLabel="Ouverts" tabs={[{ key: 1, title: 'vpn', icon: 'cert' }]} activeKey={1} onClose={() => {}}>
            <button type="button" onClick={() => setAsking(true)}>Révoquer</button>
          </Dock>
        )}>
          {asking && <dialog open aria-modal="true"><button type="button" onClick={() => setAsking(false)}>Confirmer</button></dialog>}
        </Zone>
      )
    }
    const { container } = render(<WithDialog />)
    const content = container.querySelector('.page-content')
    expect(content).toHaveAttribute('inert')
    fireEvent.click(screen.getByRole('button', { name: 'Révoquer' }))
    await vi.waitFor(() => expect(content).not.toHaveAttribute('inert'))
    expect(screen.getByRole('button', { name: 'Confirmer' }).closest('[inert]')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmer' }))
    await vi.waitFor(() => expect(content).toHaveAttribute('inert'))
  })

  it('leaves the page alone on a wider screen', () => {
    size.isMobile = false
    const { container } = render(<Shell />)
    expect(container.querySelector('[inert]')).toBeNull()
  })

  it('gives the focus back to the button of the mobile record, not to the record', async () => {
    function Records() {
      const [open, setOpen] = useState(true)
      return (
        <Zone dock={open && (
          <Dock label="Inspecteur" tabsLabel="Ouverts" tabs={[{ key: 'x1', title: 'vpn', icon: 'cert' }]} activeKey="x1" onClose={() => setOpen(false)}>
            <p>panneau</p>
          </Dock>
        )}>
          <article className="mobile-record" data-open="x1"><button type="button" data-open="x1">vpn</button></article>
        </Zone>
      )
    }
    render(<Records />)
    fireEvent.click(screen.getByRole('button', { name: 'inspector.close' }))
    await act(frame)
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'vpn' }))
  })
})

describe('the open tabs and the body', () => {
  it('shows the one open object as a label when tabs do not close', () => {
    const { container } = render(<Page />)
    expect(container.querySelector('.open-tabs > .open-tab.active > .open-tab-label')).toHaveTextContent('vpn')
  })
  it('selects and closes the open objects, by click, the arrows and Delete', () => {
    const { container } = render(<Page multi />)
    const strip = container.querySelector('.open-tabs')
    const [vpn, api] = within(strip).getAllByRole('button', { pressed: undefined }).filter((b) => b.dataset.active)
    expect(vpn).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(api)
    expect(screen.getByRole('heading', { name: 'Objet 2' })).toBeInTheDocument()
    fireEvent.keyDown(api, { key: 'ArrowLeft' })
    expect(screen.getByRole('heading', { name: 'Objet 1' })).toBeInTheDocument()
    fireEvent.keyDown(api, { key: 'Delete' })
    expect(within(strip).queryByTitle('api')).toBeNull()
    fireEvent.click(within(strip).getByRole('button', { name: 'inspector.closeTab {"name":"vpn"}' }))
    expect(strip.querySelectorAll('.open-tab')).toHaveLength(0)
  })
  it('moves between the sections with the arrows, Home and End', () => {
    render(<Page />)
    const tabs = screen.getByRole('tablist', { name: 'Sections' })
    const [first] = within(tabs).getAllByRole('tab')
    expect(first).toHaveAttribute('aria-selected', 'true')
    expect(first).toHaveAttribute('tabindex', '0')
    fireEvent.keyDown(first, { key: 'ArrowLeft' })
    expect(screen.getByText('panneau history')).toBeInTheDocument()
    fireEvent.keyDown(first, { key: 'Home' })
    expect(screen.getByText('panneau overview')).toBeInTheDocument()
    fireEvent.click(within(tabs).getByRole('tab', { name: 'Chaîne' }))
    expect(screen.getByRole('tabpanel')).toHaveAttribute('aria-labelledby', 'tab-chain')
  })
  it('puts the objects beyond the width in the « +N » menu, the active one shown, the menu closing on a click elsewhere', () => {
    // jsdom measures nothing: the strip is said to hold room for one tab at 120 px
    const width = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(180)
    const { container } = render(<Page multi />)
    width.mockRestore()
    const more = screen.getByRole('button', { name: /\+1/ })
    expect(container.querySelectorAll('.open-tabs .open-tab')).toHaveLength(1)
    expect(container.querySelector('.open-tabs .open-tab.active')).toHaveTextContent('vpn')
    fireEvent.click(more)
    const menu = screen.getByRole('menu')
    expect(menu).not.toHaveAttribute('hidden')
    expect(document.activeElement).toBe(within(menu).getAllByRole('menuitem')[0])
    fireEvent.pointerDown(document.body)
    expect(document.getElementById('tabs-menu')).toHaveAttribute('hidden')
    fireEvent.click(more)
    fireEvent.click(within(screen.getByRole('menu')).getAllByRole('menuitem')[0])
    expect(screen.getByRole('heading', { name: 'Objet 2' })).toBeInTheDocument()
    expect(container.querySelector('.open-tabs .open-tab.active')).toHaveTextContent('api')
  })
})
