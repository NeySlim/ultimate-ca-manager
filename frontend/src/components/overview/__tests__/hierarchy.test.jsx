/** Hierarchy card: a CA's status reads in the user's language. */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, configure } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import fr from '../../../i18n/locales/fr.json'

const api = vi.hoisted(() => ({ getAll: vi.fn(), getIssuance: vi.fn() }))
const lookup = (key) => key.split('.').reduce((node, part) => (node == null ? node : node[part]), fr)
vi.mock('react-i18next', () => ({
  Trans: ({ i18nKey }) => i18nKey,
  useTranslation: () => ({
    t: (key, arg) => {
      const word = lookup(key) ?? lookup(`${key}_${arg?.count === 1 || arg?.count === 0 ? 'one' : 'other'}`)
      const text = typeof word === 'string' ? word : (typeof arg === 'string' ? arg : key)
      return text.replace(/\{\{(\w+)\}\}/g, (_, name) => arg?.[name])
    },
  }),
}))
vi.mock('../../../services', () => ({
  casService: { getAll: api.getAll },
  overviewService: { getIssuance: api.getIssuance },
}))
vi.mock('../../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ connectionState: 'connected' }),
  ConnectionState: { CONNECTED: 'connected', DISCONNECTED: 'disconnected', CONNECTING: 'connecting', ERROR: 'error' },
}))
vi.mock('../../../hooks/usePermission', () => ({ usePermission: () => ({ hasPermission: () => true }) }))

import { HierarchyCard } from '..'

// A loaded machine slows the first render past the default second
configure({ asyncUtilTimeout: 5000 })

describe('hierarchy card states', () => {
  it('reads a CA that is not active in French', async () => {
    api.getIssuance.mockResolvedValue({ data: { by_ca: [] } })
    api.getAll.mockResolvedValue({ data: [
      { id: 1, refid: 'a', descr: 'Old Root', status: 'Expired' },
      { id: 2, refid: 'b', descr: 'Bad Root', status: 'Revoked' },
      { id: 3, refid: 'c', descr: 'New Root', status: 'Pending' },
    ], meta: { total: 3 } })
    render(<MemoryRouter><HierarchyCard /></MemoryRouter>)
    await screen.findByText('Old Root')
    const text = document.body.textContent
    expect(text).toContain('Expiré')
    expect(text).toContain('Révoqué')
    expect(text).toContain('En attente')
    expect(text).not.toMatch(/\b(Expired|Revoked|Pending)\b/)
  })
})

describe('hierarchy card bounds', () => {
  const ca = (id, parent) => ({ id, refid: `r${id}`, descr: `Authority ${id}`, parent_id: parent ?? null, cdp_enabled: id % 2 === 0, ocsp_enabled: false })

  it('139 authorities give ten lines, the sentence says how many are shown, Explorer leads to all of them', async () => {
    const cas = []
    for (let i = 1; i <= 45; i += 1) cas.push(ca(i), ca(100 + i, i))
    for (let i = 1; i <= 49; i += 1) cas.push(ca(200 + i, 101))
    api.getIssuance.mockResolvedValue({ data: { by_ca: [] } })
    api.getAll.mockResolvedValue({ data: cas, meta: { total: 139 } })
    render(<MemoryRouter><HierarchyCard /></MemoryRouter>)
    await screen.findByText('Authority 1')
    expect(document.querySelectorAll('a[href^="/cas/"]')).toHaveLength(10)
    expect([...document.querySelectorAll('a[href="/cas"]')].map((a) => a.textContent.trim())).toEqual(['Explorer'])
    const sub = document.querySelector('#card-hierarchy .panel-heading p').textContent
    expect(sub).toContain('139 autorités sous 45 racines.')
    expect(sub).toContain('10 autorités affichées sur 139')
    // A node whose children were cut says how many are below
    expect(document.querySelectorAll('[data-hidden-below]').length).toBeGreaterThan(0)
  })

  it('a small hierarchy shows whole, nested under its root', async () => {
    api.getIssuance.mockResolvedValue({ data: { by_ca: [{ caref: 'r2', issued: 3, total: 4 }] } })
    api.getAll.mockResolvedValue({ data: [ca(1), ca(2, 1), ca(3, 1)], meta: { total: 3 } })
    render(<MemoryRouter><HierarchyCard /></MemoryRouter>)
    await screen.findByText('Authority 1')
    expect(document.querySelectorAll('a[href^="/cas/"]')).toHaveLength(3)
    expect(document.querySelector('#card-hierarchy .panel-heading p').textContent).not.toContain('affichées')
    expect(document.querySelector('[data-hidden-below]')).toBeNull()
    const tree = document.querySelector('.hier-tree')
    expect(tree.getAttribute('aria-label')).toBe('Branche Authority 1')
    expect([...tree.querySelectorAll(':scope > li > ul > li.hier-node')]).toHaveLength(2)
  })

  it('gives each authority under a root its issuances and renewals on 7 days, a zero included', async () => {
    api.getIssuance.mockResolvedValue({ data: { by_ca: [{ caref: 'r2', issued: 3, total: 4 }] } })
    api.getAll.mockResolvedValue({ data: [ca(1), ca(2, 1), ca(3, 1)], meta: { total: 3 } })
    render(<MemoryRouter><HierarchyCard /></MemoryRouter>)
    expect((await screen.findByText('Authority 2')).closest('a').textContent).toContain('4 émissions sur 7 j')
    expect(screen.getByText('Authority 3').closest('a').textContent).toContain('0 émission sur 7 j')
    // A root says its CRL, not issuances
    expect(screen.getByText('Authority 1').closest('a').textContent).not.toContain('émission')
  })

  it('CRL and OCSP are the mockup\'s meta lines, with an icon each', async () => {
    api.getIssuance.mockResolvedValue({ data: { by_ca: [] } })
    api.getAll.mockResolvedValue({ data: [ca(1), ca(2, 1)], meta: { total: 2 } })
    render(<MemoryRouter><HierarchyCard /></MemoryRouter>)
    const meta = [...(await screen.findByText('Authority 2')).closest('a').querySelectorAll('.hier-meta > span')]
    expect(meta.map((p) => p.textContent)).toEqual(['CRL activée', 'OCSP inactif', '0 émission sur 7 j'])
    for (const span of meta) expect(span.querySelector('svg')).not.toBeNull()
    expect(screen.getByText('Authority 2').closest('a').className).toBe('hier-card state-active')
  })
})
