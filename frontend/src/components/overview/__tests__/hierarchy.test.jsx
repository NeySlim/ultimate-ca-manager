/** Hierarchy card: a CA's status reads in the user's language. */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, configure } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import fr from '../../../i18n/locales/fr.json'

const api = vi.hoisted(() => ({ getAll: vi.fn(), getIssuance: vi.fn() }))
const lookup = (key) => key.split('.').reduce((node, part) => (node == null ? node : node[part]), fr)
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, arg) => (typeof lookup(key) === 'string' ? lookup(key) : (typeof arg === 'string' ? arg : key)) }),
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
