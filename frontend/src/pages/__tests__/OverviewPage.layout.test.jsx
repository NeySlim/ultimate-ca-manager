/**
 * Overview page: which cards show and in which order, saved under the `dashboard` preference
 * whatever moved them (preset, drag and drop, arrow keys, card menu, Cards dialog).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, o) => (o && Object.keys(o).length > 0 ? `${k}:${Object.values(o).join(',')}` : k) }),
}))
vi.mock('../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ connectionState: 'connected' }),
  ConnectionState: { CONNECTED: 'connected', DISCONNECTED: 'disconnected', CONNECTING: 'connecting', ERROR: 'error' },
}))
// The real frame (grip, menu) around an empty body; the real Cards dialog
vi.mock('../../components/overview', async () => {
  const { CardFrame } = await vi.importActual('../../components/overview/shared')
  const { CardsDialog } = await vi.importActual('../../components/overview/CardsDialog')
  const card = (id) => function Stub({ defaultOpen, onToggle }) {
    return (
      <CardFrame id={id} title={`overview.cards.${id}`} state={{ status: 'ready' }}>
        <button type="button" data-testid={`fold-${id}`} data-open={String(defaultOpen)} onClick={() => onToggle?.(!defaultOpen)}>fold</button>
      </CardFrame>
    )
  }
  return {
    QueueCard: card('queue'), HealthCard: card('health'), ComplianceCard: card('compliance'), HierarchyCard: card('hierarchy'),
    HorizonCard: card('horizon'), ActivityCard: card('activity'), TrendCard: card('trend'), StatesCard: card('states'),
    MetricStrip: () => <div data-testid="strip" />, CardsDialog,
  }
})
vi.mock('../../components/overview/KeyEncryptionBanner', () => ({ KeyEncryptionBanner: () => <div data-testid="key-banner" /> }))
vi.mock('../../components/KofiSupportCard', () => ({ KofiSupportCard: ({ inline }) => <div data-testid="kofi" data-inline={String(inline)} /> }))
vi.mock('../../contexts/NotificationContext', () => ({ useNotification: () => ({}) }))
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

const ALL = ['queue', 'health', 'hierarchy', 'horizon', 'trend', 'states', 'compliance', 'activity']
function Where() {
  const { pathname, search } = useLocation()
  return <p data-testid="where">{pathname + search}</p>
}
const show = () => render(<MemoryRouter><OverviewPage /><Where /></MemoryRouter>)
const cards = () => screen.getAllByTestId(/^card-/).map((e) => e.dataset.testid.slice(5))
const saved = () => store.persist.mock.calls.at(-1)
const grip = (id) => screen.getByTestId(`card-${id}`).querySelector('.ov-grip')
const slot = (id) => screen.getByTestId(`card-${id}`).closest('.ov-slot')
const transfer = () => ({ setData: vi.fn(), setDragImage: vi.fn(), effectAllowed: '', dropEffect: '' })

beforeEach(() => { store.prefs = {}; store.persist.mockClear(); perms.list = ['*'] })

describe('cards shown', () => {
  it('shows the eight cards by default, under the banner and the figures strip', () => {
    show()
    expect(cards()).toEqual(ALL)
    expect(screen.getByTestId('key-banner')).toBeTruthy()
    expect(screen.getByTestId('strip')).toBeTruthy()
  })

  it('a layout saved when the overview had six cards keeps its order; the two new cards come after', () => {
    store.prefs = { dashboard: { order: ['activity', 'queue', 'horizon', 'health', 'hierarchy', 'compliance'], hidden: ['health'] } }
    show()
    expect(cards()).toEqual(['activity', 'queue', 'horizon', 'hierarchy', 'compliance', 'trend', 'states'])
  })

  it('a preset hides the other cards, is saved under the dashboard key and reads as pressed', () => {
    show()
    const manager = screen.getByText('overview.presets.manager')
    expect(manager.getAttribute('aria-pressed')).toBe('false')
    fireEvent.click(manager)
    expect(cards()).toEqual(['compliance', 'states', 'trend', 'horizon', 'hierarchy', 'activity'])
    const [key, value] = saved()
    expect(key).toBe('dashboard')
    expect(value.hidden.sort()).toEqual(['health', 'queue'])
    expect(Object.keys(value).sort()).toEqual(['hidden', 'order', 'queueShowAll'])
    expect(screen.getByText('overview.presets.manager').getAttribute('aria-pressed')).toBe('true')
  })

  it('with every card hidden, says so and offers the Cards dialog', () => {
    store.prefs = { dashboard: { hidden: ALL } }
    show()
    expect(screen.queryAllByTestId(/^card-/)).toHaveLength(0)
    const empty = screen.getByText('overview.allHidden').parentElement
    fireEvent.click(within(empty).getByRole('button'))
    expect(screen.getByRole('dialog')).toBeTruthy()
  })

  it('the queue spans the grid and the wide cards two columns', () => {
    show()
    expect(ALL.map((id) => slot(id).getAttribute('data-span'))).toEqual(['full', null, null, null, 'wide', null, 'wide', null])
  })

  it('packs the cards by column from their own heights, in the saved order', () => {
    const heights = { queue: 400, health: 300, hierarchy: 900, horizon: 480 }
    const rect = vi.spyOn(Element.prototype, 'getBoundingClientRect')
      .mockImplementation(function measured() { return { height: heights[this.id?.slice(5)] ?? 200 } })
    show()
    rect.mockRestore()
    expect(screen.getByTestId('overview-grid').hasAttribute('data-masonry')).toBe(true)
    expect(ALL.slice(0, 5).map((id) => slot(id).style.gridRowEnd)).toEqual(['span 400', 'span 300', 'span 900', 'span 480', 'span 200'])
    expect(cards()).toEqual(ALL)
  })

  it('a card shown again is packed with the others', () => {
    store.prefs = { dashboard: { hidden: ['states'] } }
    show()
    fireEvent.click(screen.getByRole('button', { name: 'overview.layout.cardsLabel' }))
    fireEvent.click(within(screen.getByRole('dialog')).getByLabelText('overview.cards.states'))
    expect(slot('states').style.gridRowEnd).toMatch(/^span \d+$/)
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

describe('reordering', () => {
  it('dropping a card on another gives it that place and saves the order', () => {
    show()
    const data = transfer()
    fireEvent.dragStart(grip('horizon'), { dataTransfer: data })
    expect(data.setData).toHaveBeenCalledWith('text/plain', 'horizon')
    expect(slot('horizon').className).toContain('is-dragged')
    fireEvent.dragOver(slot('health'), { dataTransfer: data })
    expect(slot('health').className).toContain('is-target')
    fireEvent.drop(slot('health'), { dataTransfer: data })
    expect(cards()).toEqual(['queue', 'horizon', 'health', 'hierarchy', 'trend', 'states', 'compliance', 'activity'])
    expect(saved()).toEqual(['dashboard', { order: cards(), hidden: [], queueShowAll: false }])
    expect(document.querySelector('.is-dragged, .is-target')).toBeNull()
    expect(screen.getByTestId('overview-said').textContent).toBe('overview.layout.moved:overview.cards.horizon,2,8')
  })

  it('a drop on itself, or without a card being dragged, saves nothing', () => {
    show()
    const data = transfer()
    fireEvent.dragStart(grip('queue'), { dataTransfer: data })
    fireEvent.drop(slot('queue'), { dataTransfer: data })
    fireEvent.drop(slot('health'), { dataTransfer: data })
    expect(store.persist).not.toHaveBeenCalled()
    expect(cards()).toEqual(ALL)
  })

  it('a drag given up leaves the order and the marks as they were', () => {
    show()
    const data = transfer()
    fireEvent.dragStart(grip('queue'), { dataTransfer: data })
    fireEvent.dragOver(slot('health'), { dataTransfer: data })
    fireEvent.dragEnd(grip('queue'), { dataTransfer: data })
    expect(document.querySelector('.is-dragged, .is-target')).toBeNull()
    fireEvent.drop(slot('health'), { dataTransfer: data })
    expect(store.persist).not.toHaveBeenCalled()
  })

  it('the arrow keys on the grip move the card one place, keep the focus on it and say where it went', () => {
    show()
    expect(grip('health').getAttribute('tabindex')).toBe('0')
    expect(grip('health').getAttribute('role')).toBe('button')
    grip('health').focus()
    fireEvent.keyDown(grip('health'), { key: 'ArrowRight' })
    expect(cards().slice(0, 3)).toEqual(['queue', 'hierarchy', 'health'])
    expect(saved()[1].order.slice(0, 3)).toEqual(['queue', 'hierarchy', 'health'])
    expect(document.activeElement).toBe(grip('health'))
    expect(screen.getByTestId('overview-said').textContent).toBe('overview.layout.moved:overview.cards.health,3,8')
    fireEvent.keyDown(grip('health'), { key: 'ArrowUp' })
    fireEvent.keyDown(grip('health'), { key: 'ArrowLeft' })
    expect(cards().slice(0, 3)).toEqual(['health', 'queue', 'hierarchy'])
  })

  it('at either end the arrow keys change nothing, and another key is left alone', () => {
    show()
    fireEvent.keyDown(grip('queue'), { key: 'ArrowUp' })
    fireEvent.keyDown(grip('activity'), { key: 'ArrowDown' })
    fireEvent.keyDown(grip('health'), { key: 'Enter' })
    expect(store.persist).not.toHaveBeenCalled()
  })

  it('the card menu moves the card, or hides it and hands the focus to the Cards button', () => {
    show()
    const menu = () => within(screen.getByTestId('card-queue')).getByRole('button', { name: 'overview.layout.menu:overview.cards.queue' })
    fireEvent.click(menu())
    expect(menu().getAttribute('aria-expanded')).toBe('true')
    expect(screen.getByText('overview.layout.earlier').disabled).toBe(true)
    fireEvent.click(screen.getByText('overview.layout.later'))
    expect(cards().slice(0, 2)).toEqual(['health', 'queue'])
    fireEvent.click(menu())
    fireEvent.click(screen.getByText('overview.layout.hide'))
    expect(cards()).not.toContain('queue')
    expect(saved()[1].hidden).toEqual(['queue'])
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'overview.layout.cardsLabel' }))
    expect(screen.getByTestId('overview-said').textContent).toBe('overview.layout.hidden:overview.cards.queue')
  })
})

describe('Cards dialog', () => {
  const open = () => { fireEvent.click(screen.getByRole('button', { name: 'overview.layout.cardsLabel' })); return within(screen.getByRole('dialog')) }

  it('lists every card with its checkbox, hides and shows one', () => {
    store.prefs = { dashboard: { hidden: ['trend'] } }
    show()
    const dialog = open()
    const boxes = dialog.getAllByRole('checkbox')
    expect(boxes.map((b) => b.checked)).toEqual([true, true, true, true, false, true, true, true])
    fireEvent.click(dialog.getByLabelText('overview.cards.health'))
    expect(saved()[1].hidden.sort()).toEqual(['health', 'trend'])
    expect(cards()).not.toContain('health')
    fireEvent.click(dialog.getByLabelText('overview.cards.trend'))
    expect(saved()[1].hidden).toEqual(['health'])
    expect(cards()).toContain('trend')
  })

  it('moves a card up or down, hidden ones included, and stops at the ends', () => {
    show()
    const dialog = open()
    expect(dialog.getByRole('button', { name: 'overview.layout.up:overview.cards.queue' }).disabled).toBe(true)
    expect(dialog.getByRole('button', { name: 'overview.layout.down:overview.cards.activity' }).disabled).toBe(true)
    fireEvent.click(dialog.getByRole('button', { name: 'overview.layout.down:overview.cards.queue' }))
    expect(saved()[1].order.slice(0, 2)).toEqual(['health', 'queue'])
    fireEvent.click(dialog.getByRole('button', { name: 'overview.layout.up:overview.cards.activity' }))
    expect(saved()[1].order.slice(-2)).toEqual(['activity', 'compliance'])
  })

  it('offers the three presets and closes on Done', () => {
    show()
    const dialog = open()
    fireEvent.click(dialog.getByText('overview.presets.operator'))
    expect(cards()).toEqual(['queue', 'health', 'hierarchy', 'horizon'])
    expect(dialog.getByText('overview.presets.operator').closest('button').getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(dialog.getByText('overview.presets.all'))
    expect(cards()).toEqual(ALL)
    fireEvent.click(dialog.getByText('common.done'))
    expect(screen.queryByRole('dialog')).toBeNull()
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

  it.each([
    ['overview.actions.issue', '/certificates?action=create'],
    ['overview.actions.newCa', '/cas?action=create'],
    ['overview.actions.discovery', '/discovery'],
  ])('%s opens %s', (label, target) => {
    show()
    fireEvent.click(screen.getByText(label))
    expect(screen.getByTestId('where').textContent).toBe(target)
  })

  it('shows a quick action only to who may use it', () => {
    perms.list = ['read:dashboard', 'read:certificates']
    const view = show()
    expect(screen.queryByText('overview.actions.issue')).toBeNull()
    expect(screen.queryByText('overview.actions.newCa')).toBeNull()
    expect(screen.getByText('overview.actions.discovery')).toBeTruthy()
    view.unmount()
    perms.list = ['read:dashboard', 'write:certificates']
    show()
    expect(screen.getByText('overview.actions.issue')).toBeTruthy()
    expect(screen.queryByText('overview.actions.discovery')).toBeNull()
  })

  it('keeps the support message in the page flow, where it covers no card', () => {
    show()
    expect(screen.getByTestId('kofi').dataset.inline).toBe('true')
    expect(screen.getByTestId('kofi').closest('.ov-page')).not.toBeNull()
  })
})
