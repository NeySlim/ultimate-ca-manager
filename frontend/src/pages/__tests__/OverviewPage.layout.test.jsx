/**
 * Overview page, the mockup's dashboard(): which cards show and in which order, saved under the
 * `dashboard` preference whatever changed them (head presets, card menu, Cards dialog).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within, act, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  Trans: ({ i18nKey }) => i18nKey,
  useTranslation: () => ({ t: (k, o) => (o && Object.keys(o).length > 0 ? `${k}:${Object.values(o).join(',')}` : k) }),
}))
vi.mock('../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ connectionState: 'connected' }),
  ConnectionState: { CONNECTED: 'connected', DISCONNECTED: 'disconnected', CONNECTING: 'connecting', ERROR: 'error' },
}))
// The real card frame (its menu) around a body that reports the page context; the real Cards dialog
const seen = vi.hoisted(() => ({ page: null }))
vi.mock('../../components/overview', async () => {
  const { useContext } = await vi.importActual('react')
  const { OverviewCard, OverviewContext } = await vi.importActual('../../components/overview/shared')
  const { CardsDialog } = await vi.importActual('../../components/overview/CardsDialog')
  const card = (id) => function Stub({ defaultOpen, onToggle }) {
    seen.page = useContext(OverviewContext)
    return (
      <OverviewCard id={id} state={{ status: 'ready' }}>
        <button type="button" data-testid={`fold-${id}`} data-open={String(defaultOpen)} onClick={() => onToggle?.(!defaultOpen)}>fold</button>
      </OverviewCard>
    )
  }
  return {
    QueueCard: card('queue'), HealthCard: card('health'), ComplianceCard: card('compliance'), HierarchyCard: card('hierarchy'),
    HorizonCard: card('horizon'), ActivityCard: card('activity'), TrendCard: card('trend'),
    MetricStrip: () => <div data-testid="strip" />, CardsDialog,
  }
})
vi.mock('../../components/overview/SetupWizard', () => ({ SetupWizard: () => <div data-testid="setup" /> }))
vi.mock('../../components/overview/KeyEncryptionBanner', () => ({ KeyEncryptionBanner: () => <div data-testid="key-banner" /> }))
vi.mock('../../components/KofiSupportCard', () => ({ KofiSupportCard: ({ inline }) => <div data-testid="kofi" data-inline={String(inline)} /> }))
const notify = vi.hoisted(() => ({ showInfo: vi.fn(), showError: vi.fn(), showSuccess: vi.fn() }))
vi.mock('../../contexts/NotificationContext', () => ({ useNotification: () => notify }))
const perms = vi.hoisted(() => ({ list: ['*'] }))
vi.mock('../../hooks/usePermission', () => ({
  usePermission: () => {
    const hasPermission = (p) => perms.list.includes('*') || perms.list.includes(p)
    return { isAdmin: () => perms.list.includes('*'), hasPermission, canWrite: (r) => hasPermission(`write:${r}`) }
  },
}))
const store = vi.hoisted(() => ({ prefs: {}, persist: vi.fn(), listeners: new Set() }))
vi.mock('../../stores/userPreferencesStore', () => ({
  getPreferences: () => store.prefs,
  persistPreference: (...a) => store.persist(...a),
  subscribePreferences: (cb) => { store.listeners.add(cb); return () => store.listeners.delete(cb) },
}))

import OverviewPage from '../OverviewPage'
import { REFRESH_EVENT } from '../../lib/overviewRefresh'

const ALL = ['queue', 'health', 'hierarchy', 'horizon', 'compliance', 'activity', 'trend']
function Where() {
  const { pathname, search } = useLocation()
  return <p data-testid="where">{pathname + search}</p>
}
const show = () => render(<MemoryRouter><OverviewPage /><Where /></MemoryRouter>)
const cards = () => [...document.querySelectorAll('.dash-cards > .dash-card')].map((e) => e.dataset.card)
const saved = () => store.persist.mock.calls.at(-1)
const frame = () => new Promise((done) => requestAnimationFrame(() => done()))

beforeEach(() => { store.prefs = {}; store.persist.mockClear(); perms.list = ['*']; vi.clearAllMocks() })

describe('cards shown', () => {
  it('shows the seven cards by default in the mockup order, under the banner, the assistant and the figures strip', () => {
    show()
    expect(cards()).toEqual(ALL)
    const view = document.getElementById('view-scroll')
    expect([...view.children].map((c) => c.dataset.testid || c.className)).toEqual(['setup', 'strip', 'dash-cards', 'kofi'])
    expect(screen.getByTestId('key-banner').compareDocumentPosition(view) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('a layout saved before keeps its order and hidden cards; the trend comes after', () => {
    store.prefs = { dashboard: { order: ['activity', 'queue', 'states', 'horizon', 'health', 'hierarchy', 'compliance'], hidden: ['health'] } }
    show()
    expect(cards()).toEqual(['activity', 'queue', 'horizon', 'hierarchy', 'compliance', 'trend'])
  })

  it('a head preset shows its cards, is saved under the dashboard key and reads as pressed', () => {
    show()
    const manager = screen.getByText('overview.presets.manager')
    expect(manager.id).toBe('head-preset-manager')
    expect(manager.getAttribute('aria-pressed')).toBe('false')
    fireEvent.click(manager)
    expect(cards()).toEqual(['compliance', 'horizon', 'hierarchy', 'activity'])
    const [key, value] = saved()
    expect(key).toBe('dashboard')
    expect(value.hidden.sort()).toEqual(['health', 'queue', 'trend'])
    expect(Object.keys(value).sort()).toEqual(['hidden', 'order', 'queueShowAll'])
    expect(screen.getByText('overview.presets.manager').getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByText('overview.presets.operator').getAttribute('aria-pressed')).toBe('false')
  })

  it('with every card hidden, says so and offers the Cards dialog', () => {
    store.prefs = { dashboard: { hidden: ALL } }
    show()
    expect(cards()).toHaveLength(0)
    const empty = document.querySelector('.queue-empty.dash-empty')
    expect(empty.textContent).toContain('overview.allHidden')
    fireEvent.click(within(empty).getByRole('button'))
    expect(screen.getByRole('dialog')).toBeTruthy()
  })

  it('the queue fold follows the preference and is saved with the layout', () => {
    store.prefs = { dashboard: { queueShowAll: true } }
    show()
    expect(screen.getByTestId('fold-queue').dataset.open).toBe('true')
    fireEvent.click(screen.getByTestId('fold-queue'))
    expect(saved()[1].queueShowAll).toBe(false)
    expect(saved()[1].order).toEqual(ALL)
  })
})

describe('card menu', () => {
  it('hides the card, says so and hands the focus to the Cards button', async () => {
    show()
    fireEvent.click(document.getElementById('card-menu-btn-health'))
    fireEvent.click(document.getElementById('card-hide-health'))
    expect(cards()).not.toContain('health')
    expect(saved()[1].hidden).toEqual(['health'])
    expect(notify.showInfo).toHaveBeenCalledWith('overview.layout.hidden:overview.cards.health')
    await act(frame)
    expect(document.activeElement.id).toBe('dash-cards-button')
  })

  it('opens the Cards dialog, and the focus comes back to that card menu on closing', async () => {
    // As a browser: an element inside a hidden menu takes no focus
    const real = HTMLElement.prototype.focus
    const focus = vi.spyOn(HTMLElement.prototype, 'focus').mockImplementation(function browserFocus(...args) {
      return this.closest('[hidden]') ? undefined : real.apply(this, args)
    })
    show()
    fireEvent.click(document.getElementById('card-menu-btn-horizon'))
    fireEvent.click(within(document.getElementById('card-menu-horizon')).getByText('atelier.customizeCards'))
    const dialog = within(screen.getByRole('dialog'))
    fireEvent.click(dialog.getByText('common.done'))
    expect(screen.queryByRole('dialog')).toBeNull()
    try {
      await waitFor(() => expect(document.activeElement.id).toBe('card-menu-btn-horizon'))
    } finally { focus.mockRestore() }
  })
})

describe('the queue asked for by another card or figure', () => {
  it('a hidden queue is shown again first, said, then asked for the type', async () => {
    store.prefs = { dashboard: { hidden: ['queue'] } }
    const heard = vi.fn()
    window.addEventListener('ucm:overview-queue', heard)
    show()
    expect(cards()).not.toContain('queue')
    act(() => { seen.page.showQueue('acme') })
    expect(cards()).toContain('queue')
    expect(saved()[1].hidden).toEqual([])
    expect(notify.showInfo).toHaveBeenCalledWith('overview.layout.queueShown')
    await act(frame)
    window.removeEventListener('ucm:overview-queue', heard)
    expect(heard).toHaveBeenCalledTimes(1)
    expect(heard.mock.calls[0][0].detail).toEqual({ group: 'acme' })
  })

  it('a queue on screen is only asked for the type, nothing is saved', async () => {
    const heard = vi.fn()
    window.addEventListener('ucm:overview-queue', heard)
    show()
    act(() => { seen.page.showQueue('') })
    await act(frame)
    window.removeEventListener('ucm:overview-queue', heard)
    expect(heard).toHaveBeenCalledTimes(1)
    expect(store.persist).not.toHaveBeenCalled()
    expect(notify.showInfo).not.toHaveBeenCalled()
  })
})

describe('Cards dialog', () => {
  const open = () => { fireEvent.click(screen.getByRole('button', { name: 'overview.layout.cardsLabel' })); return within(screen.getByRole('dialog')) }

  it('lists every card with its checkbox, hides and shows one', () => {
    store.prefs = { dashboard: { hidden: ['trend'] } }
    show()
    const dialog = open()
    const boxes = dialog.getAllByRole('checkbox')
    expect(boxes.map((b) => b.id)).toEqual(ALL.map((id) => `card-toggle-${id}`))
    expect(boxes.map((b) => b.checked)).toEqual([true, true, true, true, true, true, false])
    fireEvent.click(dialog.getByLabelText('overview.cards.health'))
    expect(saved()[1].hidden.sort()).toEqual(['health', 'trend'])
    expect(cards()).not.toContain('health')
    fireEvent.click(dialog.getByLabelText('overview.cards.trend'))
    expect(saved()[1].hidden).toEqual(['health'])
    expect(cards()).toContain('trend')
  })

  it('moves a card up or down, hidden ones included, stops at the ends and keeps the focus on the move', async () => {
    store.prefs = { dashboard: { hidden: ['health'] } }
    show()
    const dialog = open()
    expect(dialog.getByRole('button', { name: 'overview.layout.up:overview.cards.queue' }).disabled).toBe(true)
    expect(dialog.getByRole('button', { name: 'overview.layout.down:overview.cards.trend' }).disabled).toBe(true)
    fireEvent.click(dialog.getByRole('button', { name: 'overview.layout.down:overview.cards.queue' }))
    expect(saved()[1].order.slice(0, 2)).toEqual(['health', 'queue'])
    await act(frame)
    expect(document.activeElement.id).toBe('card-down-queue')
    document.activeElement.blur()
    fireEvent.click(dialog.getByRole('button', { name: 'overview.layout.up:overview.cards.queue' }))
    expect(saved()[1].order.slice(0, 2)).toEqual(['queue', 'health'])
    // At the top its up button is disabled: the focus goes to the other move button of that card
    await act(frame)
    expect(document.activeElement.id).toBe('card-down-queue')
  })

  it('offers the three presets, says the choice is saved, and closes on Done to the Cards button', async () => {
    show()
    const dialog = open()
    expect(dialog.getAllByRole('button', { pressed: false }).concat(dialog.getAllByRole('button', { pressed: true }))
      .filter((b) => b.classList.contains('preset-btn'))).toHaveLength(3)
    fireEvent.click(dialog.getByText('overview.presets.operator'))
    expect(cards()).toEqual(['queue', 'health', 'hierarchy', 'horizon'])
    expect(dialog.getByText('overview.presets.operator').closest('button').getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(dialog.getByText('overview.presets.all'))
    expect(cards()).toEqual(ALL)
    expect(dialog.getByText('overview.layout.saved')).toBeTruthy()
    fireEvent.click(dialog.getByText('common.done'))
    expect(screen.queryByRole('dialog')).toBeNull()
    await waitFor(() => expect(document.activeElement.id).toBe('dash-cards-button'))
  })
})

describe('header', () => {
  it('the refresh button asks every card to reload', () => {
    const heard = vi.fn()
    window.addEventListener(REFRESH_EVENT, heard)
    show()
    fireEvent.click(screen.getByRole('button', { name: 'overview.refresh' }))
    window.removeEventListener(REFRESH_EVENT, heard)
    expect(heard).toHaveBeenCalledTimes(1)
  })

  it('Issue opens the certificate form, and is offered only to who may issue', () => {
    const view = show()
    fireEvent.click(screen.getByRole('button', { name: /overview.actions.issue/ }))
    expect(screen.getByTestId('where').textContent).toBe('/certificates?action=create')
    view.unmount()
    perms.list = ['read:dashboard', 'read:certificates']
    show()
    expect(screen.queryByText('overview.actions.issue')).toBeNull()
  })

  it('keeps the support message in the page flow, after the cards', () => {
    show()
    expect(screen.getByTestId('kofi').dataset.inline).toBe('true')
    expect(document.getElementById('view-scroll').lastElementChild).toBe(screen.getByTestId('kofi'))
  })
})
