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

import { ModulesMenu } from '../ModulesMenu'
import { togglePinList } from '../pins'
import { MODULES, groupsFor, sidebarGroups, isVisible } from '../../../navigation/registry'

// Stateful host so a toggle re-renders the menu like the shell does
function Host({ permissions, initialPins = [], activeId = 'dashboard', onHelp }) {
  const [pins, setPins] = useState(initialPins)
  const toggle = (id) => {
    const next = togglePinList(pins, id)
    if (!next) return false
    setPins(next)
    return true
  }
  return <ModulesMenu can={canFor(permissions)} pins={pins} onTogglePin={toggle} activeId={activeId} onOpenHelp={onHelp} />
}

function setup(props = {}, path = '/') {
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={[path]}><Host permissions={ROLES.admin} {...props} /></MemoryRouter>)
  return user
}

const button = () => screen.getByRole('button', { name: /shell\.modules$/ })
const menu = () => screen.queryByRole('navigation', { name: 'shell.modulesMenuLabel' })
const linkIds = (root) => within(root).getAllByRole('link').map(a => a.getAttribute('data-module'))

// Entries the old sidebar listed, plus the ones it reached from elsewhere
// (settings from its bottom link, user certificates from no entry at all)
function oldNavigationIds(can) {
  const listed = sidebarGroups(can).flatMap(g => g.children.map(c => c.id))
  const elsewhere = MODULES.filter(m => m.group && !m.navGroup && isVisible(m, can)).map(m => m.id)
  return [...new Set([...listed, ...elsewhere])].sort()
}

describe('Modules menu: what each role sees', () => {
  it.each(Object.keys(ROLES))('lists exactly the modules the old navigation gave %s', async (role) => {
    const user = setup({ permissions: ROLES[role] })
    await user.click(button())
    const ids = linkIds(menu()).sort()
    expect(ids).toEqual(oldNavigationIds(canFor(ROLES[role])))
    expect(ids).toEqual(groupsFor(canFor(ROLES[role])).flatMap(g => g.modules.map(m => m.id)).sort())
  })

  it('shows a viewer the five signed-in modules and nothing guarded', async () => {
    const user = setup({ permissions: ROLES.viewer })
    await user.click(button())
    expect(linkIds(menu()).sort()).toEqual(['cas', 'certificates', 'csrs', 'templates', 'tools'])
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
    const user = setup({ activeId: 'cas' })
    await user.click(button())
    const current = within(menu()).getAllByRole('link').filter(a => a.getAttribute('aria-current') === 'page')
    expect(current.map(a => a.getAttribute('data-module'))).toEqual(['cas'])
  })

  it('highlights the Modules button for a module view, not for a fixed link or a pinned module', () => {
    setup({ activeId: 'audit' })
    expect(button().className).toContain('is-active')
    cleanup()
    setup({ activeId: 'cas' })
    expect(button().className).not.toContain('is-active')
    cleanup()
    setup({ activeId: 'audit', initialPins: ['audit'] })
    expect(button().className).not.toContain('is-active')
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
    await user.click(pinButton('common.audit'))
    expect(pinButton('common.audit')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('shell.pinCount')).toBeInTheDocument()
  })

  it('refuses a fourth pin with an explanation, and pins nothing', async () => {
    const user = setup({ initialPins: ['audit', 'users', 'hsm'] })
    await user.click(button())
    const fourth = pinButton('common.rbac')
    expect(fourth).toHaveAttribute('aria-disabled', 'true')
    await user.click(fourth)
    expect(fourth).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('status')).toHaveTextContent('shell.pinFull')
  })

  it('unpins to make room, then accepts the new pin', async () => {
    const user = setup({ initialPins: ['audit', 'users', 'hsm'] })
    await user.click(button())
    await user.click(pinButton('common.audit'))
    await user.click(pinButton('common.rbac'))
    expect(pinButton('common.rbac')).toHaveAttribute('aria-pressed', 'true')
    expect(pinButton('common.audit')).toHaveAttribute('aria-pressed', 'false')
  })

  it('offers no pin on the pages the bar always shows', async () => {
    const user = setup()
    await user.click(button())
    expect(screen.queryByRole('button', { name: 'shell.pinModule|common.certificates' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'shell.pinModule|common.cas' })).toBeNull()
  })
})
