/**
 * Overview: a strip of figures and self-contained cards over the aggregates of /dashboard/*.
 * The layout (order, hidden cards) is a per-user server preference, key `dashboard`;
 * the cards are reordered by dragging their grip, with the arrow keys or from the Cards dialog.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { ArrowsClockwise, MagnifyingGlass, Plus, ShieldPlus, SquaresFour } from '@phosphor-icons/react'
import {
  ActivityCard, CardsDialog, ComplianceCard, HealthCard, HierarchyCard, HorizonCard, MetricStrip, QueueCard,
  StatesCard, TrendCard,
} from '../components/overview'
import { OverviewContext } from '../components/overview/shared'
import { KeyEncryptionBanner } from '../components/overview/KeyEncryptionBanner'
import { KofiSupportCard } from '../components/KofiSupportCard'
import { useNotification } from '../contexts/NotificationContext'
import { usePermission } from '../hooks/usePermission'
import { REFRESH_EVENT } from '../lib/overviewRefresh'
import { isVisible, moduleById } from '../navigation/registry'
import { getPreferences, persistPreference, subscribePreferences } from '../stores/userPreferencesStore'
import {
  moveCard, normalizeLayout, presetActive, presetLayout, setCardHidden, stepCard, visibleCards,
} from '../lib/overviewLayout'

const CARDS = {
  queue: QueueCard, health: HealthCard, hierarchy: HierarchyCard, horizon: HorizonCard,
  trend: TrendCard, states: StatesCard, compliance: ComplianceCard, activity: ActivityCard,
}
// Columns a card takes when the grid has several: the queue all of them, the wide ones two of three
const SPAN = { queue: 'full', trend: 'wide', compliance: 'wide' }
const HEAD_PRESETS = ['operator', 'manager']
const STEP_KEYS = { ArrowUp: -1, ArrowLeft: -1, ArrowDown: 1, ArrowRight: 1 }

export default function OverviewPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { isAdmin, hasPermission, canWrite } = usePermission()
  const notify = useNotification()
  const [layout, setLayout] = useState(() => normalizeLayout(getPreferences().dashboard))
  useEffect(() => subscribePreferences((prefs) => setLayout(normalizeLayout(prefs.dashboard))), [])
  const [dialog, setDialog] = useState(false)
  const [drag, setDrag] = useState(null)
  const [said, setSaid] = useState('')
  const cardsButton = useRef(null)
  const refocus = useRef(null)
  const inflight = useRef(new Map())
  const current = useRef(layout)
  current.current = layout
  const dragged = useRef(null)

  const save = useCallback((next) => { setLayout(next); persistPreference('dashboard', next) }, [])
  const shown = visibleCards(layout)
  const title = useCallback((id) => t(`overview.cards.${id}`), [t])

  // Keyboard moves keep the focus on the grip of the card that moved
  useEffect(() => {
    if (!refocus.current) return
    document.querySelector(`#card-${refocus.current} .ov-grip`)?.focus()
    refocus.current = null
  }, [layout])

  const page = useMemo(() => {
    const place = (id, next) => {
      const cards = visibleCards(next)
      setSaid(t('overview.layout.moved', { name: title(id), position: cards.indexOf(id) + 1, total: cards.length }))
      save(next)
    }
    const step = (id, delta) => {
      const next = stepCard(current.current, id, delta)
      if (next === current.current) return
      refocus.current = id
      place(id, next)
    }
    return {
      // Two readers of one route (a card and the figures strip) share the request in flight
      share: (key, run) => {
        const map = inflight.current
        if (!map.has(key)) map.set(key, Promise.resolve().then(run).finally(() => map.delete(key)))
        return map.get(key)
      },
      grip: (id) => ({
        draggable: true,
        onDragStart: (e) => {
          e.dataTransfer.effectAllowed = 'move'
          e.dataTransfer.setData('text/plain', id)
          const card = e.currentTarget.closest('section')
          if (card && e.dataTransfer.setDragImage) e.dataTransfer.setDragImage(card, 20, 20)
          dragged.current = id
          setDrag({ id, over: null })
        },
        onDragEnd: () => { dragged.current = null; setDrag(null) },
        onKeyDown: (e) => {
          if (!(e.key in STEP_KEYS)) return
          e.preventDefault()
          step(id, STEP_KEYS[e.key])
        },
      }),
      slot: (id) => ({
        onDragOver: (e) => {
          if (!dragged.current) return
          e.preventDefault()
          e.dataTransfer.dropEffect = 'move'
          setDrag((d) => (d && d.over !== id ? { ...d, over: id } : d))
        },
        onDrop: (e) => {
          const from = dragged.current
          if (!from) return
          e.preventDefault()
          dragged.current = null
          setDrag(null)
          if (from !== id) place(from, moveCard(current.current, from, id))
        },
      }),
      step,
      canStep: (id, delta) => stepCard(current.current, id, delta) !== current.current,
      hide: (id) => {
        setSaid(t('overview.layout.hidden', { name: title(id) }))
        save(setCardHidden(current.current, id, true))
        cardsButton.current?.focus()
      },
      customize: () => setDialog(true),
      showQueue: (group) => window.dispatchEvent(new CustomEvent('ucm:overview-queue', { detail: { group } })),
    }
  }, [save, t, title])
  const context = useMemo(
    () => ({ ...page, notify, showQueue: visibleCards(layout).includes('queue') ? page.showQueue : null }),
    [page, layout, notify])

  // A figure of the strip leads to its card when that card is on screen
  const go = (id) => {
    if (!shown.includes(id)) return null
    return () => {
      const card = document.getElementById(`card-${id}`)
      card?.scrollIntoView?.({ block: 'start' })
      card?.querySelector('h2')?.focus()
    }
  }

  const discovery = moduleById('discovery')
  const canScan = Boolean(discovery) && isVisible(discovery, { isAdmin, hasPermission })

  return (
    <OverviewContext.Provider value={context}>
      <div className="ov-page">
        <header className="ov-head">
          <div className="ov-head-text">
            <div className="ov-title-line">
              <h1>{t('overview.title')}</h1>
              <span className="ov-total">{window.location.host}</span>
            </div>
            <p>{t('overview.intent')}</p>
          </div>
          <div className="ov-actions">
            <span className="ov-preset-label" aria-hidden="true">{t('overview.presets.short')}</span>
            <div className="ov-segmented" role="group" aria-label={t('overview.presets.label')}>
              {HEAD_PRESETS.map((name) => (
                <button key={name} type="button" aria-pressed={presetActive(name, layout)}
                  onClick={() => save(presetLayout(name, layout))}>
                  {t(`overview.presets.${name}`)}
                </button>
              ))}
            </div>
            <button type="button" className="ov-btn is-quiet is-icon" aria-label={t('overview.refresh')} title={t('overview.refresh')}
              onClick={() => window.dispatchEvent(new Event(REFRESH_EVENT))}>
              <ArrowsClockwise size={16} aria-hidden="true" />
            </button>
            <button type="button" ref={cardsButton} className="ov-btn is-collapsible" aria-label={t('overview.layout.cardsLabel')}
              onClick={() => setDialog(true)}>
              <SquaresFour size={16} aria-hidden="true" /><span>{t('overview.layout.cards')}</span>
            </button>
            {canWrite('cas') && (
              <button type="button" className="ov-btn is-secondary" onClick={() => navigate('/cas?action=create')}>
                <ShieldPlus size={16} aria-hidden="true" /><span>{t('overview.actions.newCa')}</span>
              </button>
            )}
            {canScan && (
              <button type="button" className="ov-btn is-secondary" onClick={() => navigate('/discovery')}>
                <MagnifyingGlass size={16} aria-hidden="true" /><span>{t('overview.actions.discovery')}</span>
              </button>
            )}
            {canWrite('certificates') && (
              <button type="button" className="ov-btn is-primary" onClick={() => navigate('/certificates?action=create')}>
                <Plus size={16} weight="bold" aria-hidden="true" /><span>{t('overview.actions.issue')}</span>
              </button>
            )}
          </div>
        </header>
        <KeyEncryptionBanner />
        <MetricStrip go={go} />
        {shown.length === 0 && (
          <div className="ov-all-hidden">
            <p>{t('overview.allHidden')}</p>
            <button type="button" className="ov-btn" onClick={() => setDialog(true)}>
              <SquaresFour size={16} aria-hidden="true" />{t('overview.layout.cards')}
            </button>
          </div>
        )}
        <div className="ov-grid" data-testid="overview-grid">
          {shown.map((id) => {
            const Card = CARDS[id]
            const marks = `${drag?.id === id ? ' is-dragged' : ''}${drag?.over === id && drag.id !== id ? ' is-target' : ''}`
            return (
              <div key={id} className={`ov-slot${marks}`} data-card={id} data-span={SPAN[id]} {...page.slot(id)}>
                {id === 'queue'
                  ? <Card defaultOpen={layout.queueShowAll} onToggle={(open) => save({ ...current.current, queueShowAll: open })} />
                  : <Card />}
              </div>
            )
          })}
        </div>
        <p className="sr-only" aria-live="polite" data-testid="overview-said">{said}</p>
        <KofiSupportCard inline />
        <CardsDialog open={dialog} onClose={() => setDialog(false)} layout={layout} onChange={save} />
      </div>
    </OverviewContext.Provider>
  )
}
