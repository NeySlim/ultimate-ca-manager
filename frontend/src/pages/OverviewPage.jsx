/**
 * Overview: the mockup's dashboard(), a strip of figures and self-contained cards over the
 * aggregates of /dashboard/*. The layout (order, hidden cards) is a per-user server preference,
 * key `dashboard`; cards are shown, hidden and reordered from the Cards dialog.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { Btn, Icon, IconBtn, PageHead, Zone } from '../components/atelier'
import {
  ActivityCard, CardsDialog, ComplianceCard, HealthCard, HierarchyCard, HorizonCard, MetricStrip, QueueCard, TrendCard,
} from '../components/overview'
import { OverviewContext } from '../components/overview/shared'
import { KeyEncryptionBanner } from '../components/overview/KeyEncryptionBanner'
import { SetupWizard } from '../components/overview/SetupWizard'
import { KofiSupportCard } from '../components/KofiSupportCard'
import { useNotification } from '../contexts/NotificationContext'
import { usePermission } from '../hooks/usePermission'
import { REFRESH_EVENT } from '../lib/overviewRefresh'
import { getPreferences, persistPreference, subscribePreferences } from '../stores/userPreferencesStore'
import { normalizeLayout, presetActive, presetLayout, setCardHidden, visibleCards } from '../lib/overviewLayout'

const CARDS = {
  queue: QueueCard, health: HealthCard, hierarchy: HierarchyCard, horizon: HorizonCard,
  compliance: ComplianceCard, activity: ActivityCard, trend: TrendCard,
}
const HEAD_PRESETS = ['operator', 'manager']

export default function OverviewPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { isAdmin, canWrite } = usePermission()
  const notify = useNotification()
  const [layout, setLayout] = useState(() => normalizeLayout(getPreferences().dashboard))
  useEffect(() => subscribePreferences((prefs) => setLayout(normalizeLayout(prefs.dashboard))), [])
  // The Cards dialog, and where the focus returns when its opener is gone
  const [dialog, setDialog] = useState(null)
  const inflight = useRef(new Map())
  const current = useRef(layout)
  current.current = layout

  const save = useCallback((next) => { setLayout(next); persistPreference('dashboard', next) }, [])
  const shown = visibleCards(layout)
  const title = useCallback((id) => t(`overview.cards.${id}`), [t])

  const page = useMemo(() => ({
    // Two readers of one route (a card and the figures strip) share the request in flight
    share: (key, run) => {
      const map = inflight.current
      if (!map.has(key)) map.set(key, Promise.resolve().then(run).finally(() => map.delete(key)))
      return map.get(key)
    },
    hide: (id) => {
      save(setCardHidden(current.current, id, true))
      requestAnimationFrame(() => document.getElementById('dash-cards-button')?.focus())
      notify.showInfo(t('overview.layout.hidden', { name: title(id) }))
    },
    customize: (id) => setDialog({ returnTo: id ? `card-menu-btn-${id}` : 'dash-cards-button' }),
    // The mockup's showQueue(): a hidden queue card is shown again first, then filtered and focused
    showQueue: (group) => {
      if (current.current.hidden.includes('queue')) {
        save(setCardHidden(current.current, 'queue', false))
        notify.showInfo(t('overview.layout.queueShown'))
      }
      requestAnimationFrame(() => window.dispatchEvent(new CustomEvent('ucm:overview-queue', { detail: { group } })))
    },
  }), [save, t, title, notify])
  const context = useMemo(() => ({ ...page, notify }), [page, notify])

  // A figure of the strip leads to its card when that card is on screen
  const go = (id) => {
    if (!shown.includes(id)) return null
    return () => {
      const card = document.getElementById(`card-${id}`)
      card?.scrollIntoView?.({ block: 'start' })
      document.getElementById(`card-${id}-title`)?.focus({ preventScroll: true })
    }
  }

  return (
    <OverviewContext.Provider value={context}>
      <Zone testId="overview-page" after={dialog && (
        <CardsDialog layout={layout} onChange={save} returnTo={dialog.returnTo} onClose={() => setDialog(null)} />
      )}>
        <KeyEncryptionBanner />
        <PageHead title={t('overview.title')} total={window.location.host} intent={t('overview.intent')}
          actions={(
            <>
              <span className="preset-label" aria-hidden="true">{t('overview.presets.short')}</span>
              <div className="segmented preset-switch" role="group" aria-label={t('overview.presets.label')}>
                {HEAD_PRESETS.map((name) => (
                  <button key={name} type="button" id={`head-preset-${name}`} data-dash-preset={name}
                    aria-pressed={presetActive(name, layout)} onClick={() => save(presetLayout(name, layout))}>
                    {t(`overview.presets.${name}`)}
                  </button>
                ))}
              </div>
              <IconBtn quiet icon="refresh" data-action="refresh" label={t('overview.refresh')}
                onClick={() => window.dispatchEvent(new Event(REFRESH_EVENT))} />
              <button type="button" className="btn cards-button" id="dash-cards-button" data-action="dash-cards"
                aria-label={t('overview.layout.cardsLabel')} onClick={() => page.customize()}>
                <Icon name="cards" /><span className="btn-label">{t('overview.layout.cards')}</span>
              </button>
              {canWrite('certificates') && (
                <Btn tone="primary" icon="plus" data-action="issue" onClick={() => navigate('/certificates?action=create')}>{t('overview.actions.issue')}</Btn>
              )}
            </>
          )} />
        <div className="scroll-view" id="view-scroll">
          <SetupWizard admin={isAdmin()} share={page.share} />
          <MetricStrip showQueue={page.showQueue} go={go} />
          {shown.length > 0 ? (
            <div className="dash-cards">
              {shown.map((id) => {
                const Card = CARDS[id]
                return id === 'queue'
                  ? <Card key={id} defaultOpen={layout.queueShowAll} onToggle={(open) => save({ ...current.current, queueShowAll: open })} />
                  : <Card key={id} />
              })}
            </div>
          ) : (
            <div className="queue-empty dash-empty">
              <Icon name="cards" />
              <h3>{t('overview.allHiddenTitle')}</h3>
              <p>{t('overview.allHidden')}</p>
              <Btn icon="cards" data-action="dash-cards" onClick={() => page.customize()}>{t('overview.layout.cards')}</Btn>
            </div>
          )}
          <KofiSupportCard inline />
        </div>
      </Zone>
    </OverviewContext.Provider>
  )
}
