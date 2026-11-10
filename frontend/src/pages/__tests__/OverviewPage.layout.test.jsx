import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k) => k }) }))
vi.mock('../../components', () => ({ Button: ({ children, ...p }) => <button {...p}>{children}</button> }))
vi.mock('../../components/overview', () => {
  const card = (id) => () => <div data-testid={`card-${id}`} />
  return { QueueCard: card('queue'), HealthCard: card('health'), ComplianceCard: card('compliance'),
    HierarchyCard: card('hierarchy'), HorizonCard: card('horizon'), ActivityCard: card('activity') }
})
const store = vi.hoisted(() => ({ prefs: {}, persist: vi.fn(), listeners: new Set() }))
vi.mock('../../stores/userPreferencesStore', () => ({
  getPreferences: () => store.prefs,
  persistPreference: (...a) => store.persist(...a),
  subscribePreferences: (cb) => { store.listeners.add(cb); return () => store.listeners.delete(cb) },
}))

import OverviewPage from '../OverviewPage'

beforeEach(() => { store.prefs = {}; store.persist.mockClear() })

describe('OverviewPage', () => {
  it('shows the six cards by default', () => {
    render(<OverviewPage />)
    expect(screen.getAllByTestId(/^card-/)).toHaveLength(6)
  })

  it('a preset hides the other cards and is saved under the dashboard key', () => {
    render(<OverviewPage />)
    fireEvent.click(screen.getByText('overview.presets.manager'))
    expect(screen.queryByTestId('card-queue')).toBeNull()
    expect(screen.getByTestId('card-compliance')).toBeTruthy()
    const [key, value] = store.persist.mock.calls[0]
    expect(key).toBe('dashboard')
    expect(value.hidden.sort()).toEqual(['health', 'queue'])
  })

  it('starts from the stored layout', () => {
    store.prefs = { dashboard: { order: ['horizon'], hidden: ['queue', 'health', 'compliance', 'hierarchy', 'activity'] } }
    render(<OverviewPage />)
    expect(screen.getAllByTestId(/^card-/).map((e) => e.dataset.testid)).toEqual(['card-horizon'])
  })
})
