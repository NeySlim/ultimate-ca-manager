/** Hierarchy card: a CA's status reads in the user's language. */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, configure } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import fr from '../../../i18n/locales/fr.json'

const api = vi.hoisted(() => ({ getAll: vi.fn(), getIssuance: vi.fn() }))
const lookup = (key) => key.split('.').reduce((node, part) => (node == null ? node : node[part]), fr)
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, arg) => {
      const text = typeof lookup(key) === 'string' ? lookup(key) : (typeof arg === 'string' ? arg : key)
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

  it('139 authorities give ten lines and a link to all of them', async () => {
    const cas = []
    for (let i = 1; i <= 45; i += 1) cas.push(ca(i), ca(100 + i, i))
    for (let i = 1; i <= 49; i += 1) cas.push(ca(200 + i, 101))
    api.getIssuance.mockResolvedValue({ data: { by_ca: [] } })
    api.getAll.mockResolvedValue({ data: cas, meta: { total: 139 } })
    render(<MemoryRouter><HierarchyCard /></MemoryRouter>)
    await screen.findByTestId('hierarchy-total')
    expect(document.querySelectorAll('a[href^="/cas/"]')).toHaveLength(10)
    expect(screen.getByTestId('hierarchy-total').textContent).toBe('139')
    const all = [...document.querySelectorAll('a[href="/cas"]')]
    expect(all.map((a) => a.textContent)).toEqual(['Explorer', 'Tout voir (139)'])
    expect(document.body.textContent).toContain('10 autorités affichées sur 139')
    // A node whose children were cut says how many are below
    expect(screen.getAllByTestId('hierarchy-hidden').length).toBeGreaterThan(0)
  })

  it('a small hierarchy shows whole, without the link to the rest', async () => {
    api.getIssuance.mockResolvedValue({ data: { by_ca: [{ caref: 'r2', issued: 3 }] } })
    api.getAll.mockResolvedValue({ data: [ca(1), ca(2, 1), ca(3, 1)], meta: { total: 3 } })
    render(<MemoryRouter><HierarchyCard /></MemoryRouter>)
    await screen.findByText('Authority 1')
    expect(document.querySelectorAll('a[href^="/cas/"]')).toHaveLength(3)
    expect(document.body.textContent).not.toContain('Tout voir')
    expect(screen.queryByTestId('hierarchy-hidden')).toBeNull()
  })

  it('shows the issuances of a CA that issued, and no line for a zero', async () => {
    api.getIssuance.mockResolvedValue({ data: { by_ca: [{ caref: 'r2', issued: 3 }] } })
    api.getAll.mockResolvedValue({ data: [ca(1), ca(2, 1), ca(3, 1)], meta: { total: 3 } })
    render(<MemoryRouter><HierarchyCard /></MemoryRouter>)
    const busy = (await screen.findByText('Authority 2')).closest('a')
    expect(busy.textContent).toContain('Émis, 7 jours : 3')
    for (const name of ['Authority 1', 'Authority 3']) expect(screen.getByText(name).closest('a').textContent).not.toContain('Émis, 7 jours')
  })

  it('CRL and OCSP read as pills, with an icon each', async () => {
    api.getIssuance.mockResolvedValue({ data: { by_ca: [] } })
    api.getAll.mockResolvedValue({ data: [ca(2)], meta: { total: 1 } })
    render(<MemoryRouter><HierarchyCard /></MemoryRouter>)
    const pills = [...(await screen.findByText('Authority 2')).closest('a').querySelectorAll('.ov-pill')]
    expect(pills.map((p) => p.textContent)).toEqual(['CRL activée', 'OCSP désactivé'])
    for (const pill of pills) expect(pill.querySelector('svg')).not.toBeNull()
  })
})
