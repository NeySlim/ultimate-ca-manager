/**
 * Overview: six self-contained cards over the aggregates of /dashboard/*.
 * The layout (order, hidden cards) is a per-user server preference, key `dashboard`.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '../components'
import {
  ActivityCard, ComplianceCard, HealthCard, HierarchyCard, HorizonCard, QueueCard,
} from '../components/overview'
import { getPreferences, persistPreference, subscribePreferences } from '../stores/userPreferencesStore'
import { PRESETS, normalizeLayout, presetLayout, visibleCards } from '../lib/overviewLayout'

const CARDS = {
  queue: QueueCard, health: HealthCard, hierarchy: HierarchyCard,
  horizon: HorizonCard, compliance: ComplianceCard, activity: ActivityCard,
}

export default function OverviewPage() {
  const { t } = useTranslation()
  const [layout, setLayout] = useState(() => normalizeLayout(getPreferences().dashboard))
  useEffect(() => subscribePreferences((prefs) => setLayout(normalizeLayout(prefs.dashboard))), [])

  const save = (next) => { setLayout(next); persistPreference('dashboard', next) }
  const shown = visibleCards(layout)

  return (
    <div className="p-4 flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold text-text-primary">{t('overview.title')}</h1>
        <div role="group" aria-label={t('overview.presets.label')} className="flex gap-2">
          {Object.keys(PRESETS).map((name) => (
            <Button key={name} type="button" size="sm" variant="secondary"
              onClick={() => save(presetLayout(name, layout))}>
              {t(`overview.presets.${name}`)}
            </Button>
          ))}
        </div>
      </header>
      {shown.length === 0 && <p className="text-sm text-text-secondary">{t('overview.allHidden')}</p>}
      <div className="grid gap-4 grid-cols-1 lg:grid-cols-2">
        {shown.map((id) => {
          const Card = CARDS[id]
          return id === 'queue'
            ? <Card key={id} defaultOpen={layout.queueShowAll}
                onToggle={(open) => save({ ...layout, queueShowAll: open })} />
            : <Card key={id} />
        })}
      </div>
    </div>
  )
}
