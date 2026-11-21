/**
 * The Modules mega-menu: what each role sees, keyboard and focus, pins.
 * Ported from the sidebar tests: rights per entry, active entry, SSH split.
 */
import { describe, it, expect, vi } from 'vitest'
import { cleanup, render, screen, within, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { useState } from 'react'
import { ROLES, canFor, tStub } from './shellTestUtils'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: tStub, i18n: { language: 'en' } }),
}))
const showInfo = vi.hoisted(() => vi.fn())

import { ModulesButton, ModulesMenu } from '../ModulesMenu'
import { useDisclosure } from '../useDisclosure'
import { togglePinList } from '../pins'
import { groupsFor, menuGroupsFor, MAIN_IDS } from '../../../navigation/registry'

// Stateful host so a toggle re-renders the menu like the shell does
function Host({ permissions, initialPins = [], activeId = 'dashboard', onHelp }) {
  const [pins, setPins] = useState(initialPins)
  const toggle = (id) => {
    const next = togglePinList(pins, id)
    if (!next) return false
    setPins(next)
    return true
  }
  // The bar holds the button among its links and the menu after them, sharing one disclosure
  const menu = useDisclosure()
  return (
    <>
      <nav aria-label="bar"><ModulesButton menu={menu} can={canFor(permissions)} pins={pins} activeId={activeId} /></nav>
      <ModulesMenu menu={menu} can={canFor(permissions)} pins={pins} onTogglePin={toggle} activeId={activeId} onOpenHelp={onHelp} onNotice={showInfo} />
    </>
  )
}

function setup(props = {}, path = '/') {
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={[path]}><Host permissions={ROLES.admin} {...props} /></MemoryRouter>)
  return user
}

const button = () => screen.getByRole('button', { name: /shell\.modules$/ })
const menu = () => screen.queryByRole('navigation', { name: 'shell.modulesMenuLabel' })
const linkIds = (root) => within(root).getAllByRole('link').map(a => a.getAttribute('data-module'))

describe('Modules menu: what each role sees', () => {
  it.each(Object.keys(ROLES))('lists exactly the grouped modules %s may see', async (role) => {
    const user = setup({ permissions: ROLES[role] })
    await user.click(button())
    const ids = linkIds(menu()).sort()
    const expected = groupsFor(canFor(ROLES[role])).flatMap(g => g.modules.map(m => m.id)).filter(id => !MAIN_IDS.includes(id))
    expect(ids).toEqual(expected.sort())
  })

  it('leaves out the pages of the main bar, Activity included', async () => {
    const user = setup({ permissions: ROLES.admin })
    await user.click(button())
    for (const id of MAIN_IDS) expect(linkIds(menu())).not.toContain(id)
  })

  it('shows a viewer the three signed-in modules and nothing guarded', async () => {
    const user = setup({ permissions: ROLES.viewer })
    await user.click(button())
    expect(linkIds(menu()).sort()).toEqual(['csrs', 'templates', 'tools'])
  })

  it('counts the modules of each group and of the menu', async () => {
    const user = setup({ permissions: ROLES.admin })
    await user.click(button())
    const groups = menuGroupsFor(canFor(ROLES.admin))
    const counters = within(menu()).getAllByRole('heading', { level: 2 }).map(h => h.querySelector('.counter').textContent)
    expect(counters).toEqual(groups.map(g => String(g.modules.length)))
    const pages = groups.reduce((n, g) => n + g.modules.length, 0)
    expect(within(menu()).getByText(new RegExp(`shell\\.modulePages`)).textContent).toContain('shell.pinCount')
    expect(pages).toBe(linkIds(menu()).length)
  })

  it('puts one line of description under every module', async () => {
    const user = setup({ permissions: ROLES.admin })
    await user.click(button())
    for (const link of within(menu()).getAllByRole('link')) {
      const small = link.querySelector('small')
      expect(small?.textContent).toMatch(/^shell\.moduleDesc\./)
    }
  })

  it('gives an administrator the four groups', async () => {
    const user = setup({ permissions: ROLES.admin })
    await user.click(button())
    const titles = within(menu()).getAllByRole('heading', { level: 2 }).map(h => h.textContent)
    expect(titles.map(t => t.replace(/\d+$/, ''))).toEqual([
      'common.navPki', 'common.navProtocols', 'common.navGovernance', 'common.navAdmin',
    ])
  })

  it('shows SSH certificates but not SSH CAs with read:ssh alone', async () => {
    const user = setup({ permissions: ['read:ssh'] })
    await user.click(button())
    expect(linkIds(menu())).toContain('ssh-certificates')
    expect(linkIds(menu())).not.toContain('ssh-cas')
  })

  it('shows SSH CAs with read:ssh_cas alone', async () => {
    const user = setup({ permissions: ['read:ssh_cas'] })
    await user.click(button())
    expect(linkIds(menu())).toContain('ssh-cas')
    expect(linkIds(menu())).not.toContain('ssh-certificates')
  })

  it('marks the current module with aria-current and leaves the others unmarked', async () => {
    const user = setup({ activeId: 'acme' })
    await user.click(button())
    const current = within(menu()).getAllByRole('link').filter(a => a.getAttribute('aria-current') === 'page')
    expect(current.map(a => a.getAttribute('data-module'))).toEqual(['acme'])
  })

  it('highlights the Modules button for a module view, not for a fixed link or a pinned module', () => {
    setup({ activeId: 'reports' })
    expect(button().className).toContain('active')
    cleanup()
    setup({ activeId: 'audit' })
    expect(button().className).not.toContain('active')
    cleanup()
    setup({ activeId: 'reports', initialPins: ['reports'] })
    expect(button().className).not.toContain('active')
  })
})

describe('Modules menu: keyboard and focus', () => {
  it('starts closed with aria-expanded=false and the panel hidden', () => {
    setup()
    expect(button()).toHaveAttribute('aria-expanded', 'false')
    expect(menu()).toBeNull()
  })

  it('opens on click and focuses the first page', async () => {
    const user = setup()
    await user.click(button())
    expect(button()).toHaveAttribute('aria-expanded', 'true')
    expect(document.activeElement).toBe(within(menu()).getAllByRole('link')[0])
  })

  it('opens on ArrowDown from the button', async () => {
    const user = setup()
    button().focus()
    await user.keyboard('{ArrowDown}')
    expect(button()).toHaveAttribute('aria-expanded', 'true')
    expect(document.activeElement.getAttribute('data-module')).toBeTruthy()
  })

  it('moves with the arrows, wraps, and jumps with Home and End', async () => {
    const user = setup()
    await user.click(button())
    const links = within(menu()).getAllByRole('link')
    await user.keyboard('{ArrowDown}')
    expect(document.activeElement).toBe(links[1])
    await user.keyboard('{End}')
    expect(document.activeElement).toBe(links.at(-1))
    await user.keyboard('{ArrowDown}')
    expect(document.activeElement).toBe(links[0])
    await user.keyboard('{ArrowUp}')
    expect(document.activeElement).toBe(links.at(-1))
    await user.keyboard('{Home}')
    expect(document.activeElement).toBe(links[0])
  })

  it('closes on Escape and gives the focus back to the button', async () => {
    const user = setup()
    await user.click(button())
    await user.keyboard('{Escape}')
    expect(menu()).toBeNull()
    expect(button()).toHaveAttribute('aria-expanded', 'false')
    expect(document.activeElement).toBe(button())
  })

  it('closes on a click outside', async () => {
    const user = setup()
    await user.click(button())
    await user.click(document.body)
    expect(menu()).toBeNull()
  })

  it('closes when focus leaves the menu', async () => {
    const user = setup()
    await user.click(button())
    const outside = document.createElement('button')
    document.body.appendChild(outside)
    act(() => outside.focus())
    expect(menu()).toBeNull()
    outside.remove()
  })

  it('closes on a route change', async () => {
    const user = setup()
    await user.click(button())
    await user.click(within(menu()).getAllByRole('link')[0])
    expect(menu()).toBeNull()
  })

  it('opens the navigation help from its foot', async () => {
    const onHelp = vi.fn()
    const user = setup({ onHelp })
    await user.click(button())
    await user.click(screen.getByRole('button', { name: /shell\.navHelp/ }))
    expect(onHelp).toHaveBeenCalledWith('navigation')
    expect(menu()).toBeNull()
  })
})

describe('Modules menu: pins', () => {
  const pinButton = (id) => screen.getByRole('button', { name: `shell.pinModule|${id}` })

  it('pins a module, reflects it with aria-pressed, and counts it', async () => {
    const user = setup()
    await user.click(button())
    await user.click(pinButton('common.reports'))
    expect(pinButton('common.reports')).toHaveAttribute('aria-pressed', 'true')
    expect(within(menu()).getByText(/shell\.pinCount/)).toBeInTheDocument()
  })

  it('refuses a fourth pin with a message, as the mockup, keeps the foot hint, and pins nothing', async () => {
    showInfo.mockClear()
    const user = setup({ initialPins: ['reports', 'users', 'hsm'] })
    await user.click(button())
    const fourth = pinButton('common.rbac')
    expect(fourth).toHaveAttribute('aria-disabled', 'true')
    await user.click(fourth)
    expect(fourth).toHaveAttribute('aria-pressed', 'false')
    expect(showInfo).toHaveBeenCalledWith('shell.pinFull')
    expect(within(menu()).getByText('shell.pinHint')).toBeInTheDocument()
    expect(fourth).toHaveAttribute('title', 'shell.pinFullTitle')
  })

  it('unpins to make room, then accepts the new pin', async () => {
    const user = setup({ initialPins: ['reports', 'users', 'hsm'] })
    await user.click(button())
    await user.click(pinButton('common.reports'))
    await user.click(pinButton('common.rbac'))
    expect(pinButton('common.rbac')).toHaveAttribute('aria-pressed', 'true')
    expect(pinButton('common.reports')).toHaveAttribute('aria-pressed', 'false')
  })

  it('offers no pin on the pages the bar always shows', async () => {
    const user = setup()
    await user.click(button())
    expect(screen.queryByRole('button', { name: 'shell.pinModule|common.certificates' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'shell.pinModule|common.cas' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'shell.pinModule|common.audit' })).toBeNull()
  })
})

describe('Modules menu: its place under the button', () => {
  it('follows its button when the bar gains a link while the menu is open', async () => {
    const user = userEvent.setup()
    const host = (permissions) => <MemoryRouter><Host permissions={permissions} /></MemoryRouter>
    const { rerender } = render(host(ROLES.viewer))
    let left = 300
    vi.spyOn(button(), 'getBoundingClientRect').mockImplementation(() => ({ left, top: 0, width: 119, height: 61 }))
    await user.click(button())
    expect(menu().style.left).toBe('300px')
    // The rights arrive: the bar grows a link and pushes the button to the right
    left = 393
    rerender(host(ROLES.admin))
    expect(menu().style.left).toBe('393px')
  })
})
