/**
 * HierarchyTree: folded beyond the first level, counters on each node, state as a pill and
 * marks, keyboard, search, a large installation without one card per authority, cross links.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'

import { HierarchyTree } from '../HierarchyTree'
import { buildForest } from '../caTree'
import { ca, smallHierarchy, largeInstallation } from './caFixtures'

const t = (key, opts) => (opts && typeof opts.count === 'number' ? `${opts.count} ${key}`
  : opts?.name ? `${key} ${opts.name}` : opts?.level ? `${key} ${opts.level}` : key)

function renderTree(cas, props = {}) {
  const onSelect = vi.fn()
  const forest = buildForest(cas, { query: props.query })
  const utils = render(<HierarchyTree forest={forest} onSelect={onSelect} t={t} {...props} />)
  return { onSelect, ...utils }
}
const item = (name) => screen.getByRole('treeitem', { name })
const names = () => screen.getAllByRole('treeitem').map((el) => el.getAttribute('aria-labelledby'))
  .map((id) => document.getElementById(id).textContent)
const press = (el, key) => fireEvent.keyDown(el, { key })

describe('HierarchyTree: the mockup caView()', () => {
  it('draws the panel, its heading and the nodes as the mockup', () => {
    const { container } = renderTree(smallHierarchy(), { selectedId: 2, total: 6 })
    const panel = container.querySelector('section.panel.ca-tree-panel')
    expect(panel.querySelector('header.panel-heading h2#ca-tree-title')).toHaveTextContent('cas.tree.title')
    expect(panel.querySelector('.panel-heading .actions .chip')).toHaveTextContent('6 cas.total')
    expect(panel.querySelector('#ca-tree-scroll > .ca-forest > ul#ca-tree.ca-tree[role=tree]')).not.toBeNull()
    const node = item('Services')
    expect(node).toHaveAttribute('id', 'ca-node-2')
    expect(node.querySelector(':scope > .ca-card.active > .ca-card-head > strong#ca-name-2')).toHaveTextContent('Services')
    expect(node.querySelector('.ca-card-head > button.icon-btn.tree-toggle')).toHaveAttribute('tabindex', '-1')
    expect(node.querySelector('.ca-count')).toHaveAttribute('aria-hidden', 'true')
    expect(node.querySelector('.ca-count strong')).toHaveTextContent('12')
    expect(panel.querySelector('p.ca-guidance')).toHaveTextContent('cas.guidance.lead')
  })

  it('makes the selected node the tab stop', () => {
    renderTree(smallHierarchy(), { selectedId: 5 })
    expect(item('Identities')).toHaveAttribute('tabindex', '0')
    expect(item('Example Root')).toHaveAttribute('tabindex', '-1')
  })

  it('draws a revoked authority dashed, as the mockup', () => {
    const { container } = renderTree([ca(1, { name: 'Gone', status: 'Revoked', revoked: true, certs: 1 }), ca(2, { name: 'Sub', type: 'intermediate', parent_id: 1 })])
    expect(container.querySelector('[data-ca="1"]')).toHaveClass('state-revoked')
  })
})

describe('HierarchyTree: structure', () => {
  it('is one tree whose roots are open and whose deeper nodes are folded', () => {
    renderTree(smallHierarchy())
    expect(screen.getByRole('tree', { name: 'cas.tree.title' })).toBeInTheDocument()
    expect(names()).toEqual(['Example Root', 'Identities', 'Services', 'Second Root'])
    expect(item('Example Root')).toHaveAttribute('aria-expanded', 'true')
    expect(item('Services')).toHaveAttribute('aria-expanded', 'false')
    expect(item('Identities')).not.toHaveAttribute('aria-expanded')
    expect(item('Example Root')).toHaveAttribute('aria-level', '1')
    expect(item('Services')).toHaveAttribute('aria-level', '2')
  })

  it('counts the certificates and the sub-authorities of each node', () => {
    renderTree(smallHierarchy())
    const services = item('Services')
    expect(services).toHaveAccessibleDescription(/12 cas\.certificateCount/)
    expect(services).toHaveAccessibleDescription(/2 cas\.tree\.subCaCount/)
    expect(item('Identities')).toHaveAccessibleDescription(/8 cas\.certificateCount/)
    expect(item('Identities')).not.toHaveAccessibleDescription(/subCaCount/)
    expect(within(services).getByText('cas.tree.level 2', { exact: false })).toBeInTheDocument()
  })

  it('unfolds and folds a node from its button, without opening its detail', () => {
    const { onSelect } = renderTree(smallHierarchy())
    fireEvent.click(screen.getByRole('button', { name: 'cas.tree.expand Services', hidden: true }))
    expect(names()).toEqual(['Example Root', 'Identities', 'Services', 'Internal', 'Legacy', 'Second Root'])
    fireEvent.click(screen.getByRole('button', { name: 'cas.tree.collapse Services', hidden: true }))
    expect(names()).not.toContain('Internal')
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('folds and unfolds everything', () => {
    renderTree(smallHierarchy())
    fireEvent.click(screen.getByRole('button', { name: 'cas.tree.collapseAll' }))
    expect(names()).toEqual(['Example Root', 'Second Root'])
    fireEvent.click(screen.getByRole('button', { name: 'cas.tree.expandAll' }))
    expect(names()).toEqual(['Example Root', 'Identities', 'Services', 'Internal', 'Legacy', 'Second Root'])
  })

  it('opens the detail on a click of the node', () => {
    const { onSelect } = renderTree(smallHierarchy())
    fireEvent.click(screen.getByText('Identities'))
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 5 }))
  })

  it('shows the sub-authority of a root that appears after the first load', () => {
    const { rerender } = renderTree([ca(1, { name: 'Old root' })])
    const later = [ca(1, { name: 'Old root' }), ca(2, { name: 'New root' }), ca(3, { name: 'New sub', type: 'intermediate', parent_id: 2 })]
    rerender(<HierarchyTree forest={buildForest(later)} onSelect={() => {}} t={t} />)
    expect(names()).toEqual(['New root', 'New sub', 'Old root'])
  })

  it('marks the authority open in the detail and unfolds the way to it', () => {
    renderTree(smallHierarchy(), { selectedId: 3 })
    expect(item('Internal')).toHaveAttribute('aria-selected', 'true')
    expect(item('Services')).toHaveAttribute('aria-expanded', 'true')
  })
})

describe('HierarchyTree: state', () => {
  it('says the state in words, with a sign of its own, and offline with its mark', () => {
    renderTree([
      ...smallHierarchy(),
      ca(7, { name: 'Soon', valid_to: new Date(Date.now() + 5 * 86400000).toISOString(), certs: 1 }),
      ca(8, { name: 'Waiting', status: 'Pending', certs: 1 }),
    ])
    fireEvent.click(screen.getByRole('button', { name: 'cas.tree.expand Services', hidden: true }))
    const stateOf = (name) => item(name).querySelector('[data-state]')
    expect(stateOf('Example Root')).toHaveTextContent('cas.state.active')
    expect(stateOf('Example Root')).toHaveClass('badge', 'good')
    expect(stateOf('Example Root').dataset.state).toBe('active')
    expect(stateOf('Legacy')).toHaveTextContent('cas.state.expired')
    expect(stateOf('Legacy')).toHaveClass('badge', 'bad')
    expect(stateOf('Soon')).toHaveTextContent('cas.state.expiring')
    expect(stateOf('Waiting')).toHaveTextContent('cas.awaitingCertificate')
    for (const name of ['Example Root', 'Legacy', 'Soon', 'Waiting']) expect(stateOf(name).querySelector('svg')).not.toBeNull()
    expect(item('Second Root').querySelector('.chip[data-mark="offline"]')).toHaveTextContent('cas.offline')
  })

  it('writes the marks of a card in words', () => {
    renderTree([
      ca(1, { name: 'Root', offline: true, uses_hsm: true, cross_certificate_count: 1 }),
      ca(2, { name: 'Sub', type: 'intermediate', parent_id: 1, revoked_in_chain: true }),
      ca(3, { name: 'Lost', type: 'intermediate', parent_id: 99 }),
      ca(4, { name: 'Under lost', type: 'intermediate', parent_id: 3 }),
    ])
    const root = item('Root')
    expect(root.querySelector('[data-mark="offline"]')).toHaveTextContent('cas.offline')
    expect(root.querySelector('[data-mark="hsm"]')).toHaveTextContent('HSM')
    expect(root.querySelector('[data-mark="cross"]')).toHaveTextContent('crossCerts.badge')
    expect(item('Sub').querySelector('[data-mark="chain"]')).toHaveTextContent('cas.chainRevoked')
    expect(item('Lost').querySelector('[data-mark="orphan"]')).toHaveTextContent('cas.tree.orphan')
  })
})

describe('HierarchyTree: keyboard', () => {
  it('has one tab stop, moved by the arrows', () => {
    renderTree(smallHierarchy())
    const stops = () => screen.getAllByRole('treeitem').filter((el) => el.tabIndex === 0)
    expect(stops()).toEqual([item('Example Root')])
    item('Example Root').focus()
    press(item('Example Root'), 'ArrowDown')
    expect(document.activeElement).toBe(item('Identities'))
    expect(stops()).toEqual([item('Identities')])
    press(item('Identities'), 'ArrowDown')
    press(item('Services'), 'ArrowUp')
    expect(document.activeElement).toBe(item('Identities'))
    press(item('Identities'), 'End')
    expect(document.activeElement).toBe(item('Second Root'))
    press(item('Second Root'), 'Home')
    expect(document.activeElement).toBe(item('Example Root'))
  })

  it('unfolds with right then enters, folds with left then returns to the parent', () => {
    renderTree(smallHierarchy())
    const services = item('Services')
    services.focus()
    press(services, 'ArrowRight')
    expect(services).toHaveAttribute('aria-expanded', 'true')
    press(services, 'ArrowRight')
    expect(document.activeElement).toBe(item('Internal'))
    press(item('Internal'), 'ArrowLeft')
    expect(document.activeElement).toBe(services)
    press(services, 'ArrowLeft')
    expect(services).toHaveAttribute('aria-expanded', 'false')
    press(services, 'ArrowLeft')
    expect(document.activeElement).toBe(item('Example Root'))
  })

  it('opens the detail with Enter and with Space', () => {
    const { onSelect } = renderTree(smallHierarchy())
    press(item('Services'), 'Enter')
    expect(onSelect).toHaveBeenLastCalledWith(expect.objectContaining({ id: 2 }), { keyboard: true })
    press(item('Second Root'), ' ')
    expect(onSelect).toHaveBeenLastCalledWith(expect.objectContaining({ id: 6 }), { keyboard: true })
  })
})

describe('HierarchyTree: search', () => {
  it('shows what the search found with the branch that leads to it', () => {
    renderTree(smallHierarchy(), { query: 'legacy' })
    expect(names()).toEqual(['Example Root', 'Services', 'Legacy'])
  })

  it('says so when nothing matches, with the reset of the page', () => {
    const onReset = vi.fn()
    renderTree(smallHierarchy(), { query: 'nothing like it', onReset })
    expect(screen.queryByRole('tree')).toBeNull()
    expect(screen.getByRole('status')).toHaveTextContent('cas.tree.noMatch')
    fireEvent.click(screen.getByRole('button', { name: 'cas.tree.reset' }))
    expect(onReset).toHaveBeenCalled()
  })
})

describe('HierarchyTree: 139 authorities', () => {
  it('draws cards for the hierarchies only and folds the idle roots into one group', () => {
    const { container } = renderTree(largeInstallation())
    // Two roots with their eight intermediates: ten cards, never one per authority
    expect(container.querySelectorAll('.ca-card')).toHaveLength(10)
    expect(container.querySelectorAll('.ca-line')).toHaveLength(9)
    const group = item('120 cas.tree.idleRoots')
    expect(group).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getAllByRole('treeitem')).toHaveLength(10 + 9 + 1)
    expect(screen.queryByText('smoke test ca')).toBeNull()
  })

  it('opens the group from the keyboard and lists its roots as lines', () => {
    const { container } = renderTree(largeInstallation())
    const group = item('120 cas.tree.idleRoots')
    press(group, 'Enter')
    expect(group).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getAllByText('smoke test ca')).toHaveLength(120)
    expect(container.querySelectorAll('.ca-card')).toHaveLength(10)
    press(group, 'ArrowLeft')
    expect(group).toHaveAttribute('aria-expanded', 'false')
  })

  it('opens the group for the authority shown in the detail', () => {
    renderTree(largeInstallation(), { selectedId: 77 })
    expect(item('120 cas.tree.idleRoots')).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getAllByRole('treeitem', { selected: true })).toHaveLength(1)
  })

  it('lists every root a search finds, none folded', () => {
    const { container } = renderTree(largeInstallation(), { query: 'smoke' })
    expect(container.querySelectorAll('.ca-line')).toHaveLength(120)
    expect(container.querySelectorAll('.ca-card')).toHaveLength(0)
    expect(screen.queryByRole('treeitem', { name: /idleRoots/ })).toBeNull()
  })

  it('draws a bounded number of lines and gives the rest on demand', () => {
    const many = Array.from({ length: 300 }, (_, i) => ca(i + 1, { name: `Busy ${i + 1}`, certs: 1 }))
    const { container } = renderTree(many)
    expect(container.querySelectorAll('.ca-line')).toHaveLength(120)
    fireEvent.click(screen.getByRole('button', { name: '120 cas.tree.showMore' }))
    expect(container.querySelectorAll('.ca-line')).toHaveLength(240)
  })
})

describe('HierarchyTree: cross-certificates', () => {
  const cas = () => [
    ca(1, { name: 'Old root' }),
    ca(2, { name: 'Sub', type: 'intermediate', parent_id: 1 }),
    ca(3, { name: 'Between' }),
    ca(4, { name: 'Sub between', type: 'intermediate', parent_id: 3 }),
    ca(5, { name: 'New root', cross_certificate_count: 1 }),
  ]

  it('links the issuer to the root it cross-certified, drawn as cards one under the other', () => {
    const { container } = renderTree(cas(), { crossLinks: [{ from: 1, to: 5 }] })
    expect(container.querySelector('[data-cross-link="1-5"]')).not.toBeNull()
    expect(container.querySelector('[data-cross-link="1-5"]')).toHaveAttribute('aria-hidden', 'true')
    expect(container.querySelector('[data-cross-link="1-5"]')).toHaveClass('cross-link')
    // The cross-certified root has no subtree: it is a card all the same, right after its issuer
    expect(names().filter((n) => ['Old root', 'Between', 'New root'].includes(n))).toEqual(['Between', 'Old root', 'New root'])
    expect(item('New root').querySelector('.ca-card')).not.toBeNull()
  })

  it('draws no link without a cross-certificate', () => {
    const { container } = renderTree(cas())
    expect(container.querySelector('[data-cross-link]')).toBeNull()
    expect(item('New root').querySelector('.ca-line')).not.toBeNull()
  })
})
