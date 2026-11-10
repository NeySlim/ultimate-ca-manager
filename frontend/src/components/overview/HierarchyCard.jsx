import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { casService, overviewService } from '../../services'
import { CardFrame, num, useCardData } from './shared'

const DAYS = 7

/** Roots first: a CA whose parent is absent from the list is a root of its own subtree. */
export function buildTree(cas) {
  const ids = new Set(cas.map((c) => c.id))
  const kids = new Map()
  const roots = []
  for (const ca of cas) {
    if (ca.parent_id && ids.has(ca.parent_id)) {
      kids.set(ca.parent_id, [...(kids.get(ca.parent_id) || []), ca])
    } else roots.push(ca)
  }
  return { roots, kids }
}

function Node({ ca, kids, issued, t }) {
  const children = kids.get(ca.id) || []
  const sevenDays = issued === null ? '–' : (issued.get(ca.refid) ?? 0)
  return (
    <li>
      <Link to={`/cas/${ca.id}`} className="flex items-center justify-between gap-3 py-1 hover:text-accent-primary">
        <span className="min-w-0">
          <span className="block text-sm text-text-primary truncate">{ca.descr || ca.common_name || '–'}</span>
          <span className="block text-xs text-text-secondary">
            {ca.status && ca.status !== 'Active' ? `${ca.status} · ` : ''}
            {ca.offline ? `${t('overview.hierarchy.offline')} · ` : ''}
            {ca.cross_certificate_count > 0 ? `${t('overview.hierarchy.crossSigned')} · ` : ''}
            {t(ca.cdp_enabled ? 'overview.hierarchy.crlOn' : 'overview.hierarchy.crlOff')}
            {' · '}
            {t(ca.ocsp_enabled ? 'overview.hierarchy.ocspOn' : 'overview.hierarchy.ocspOff')}
          </span>
        </span>
        <span className="text-xs text-text-secondary tabular-nums whitespace-nowrap">
          {t('overview.hierarchy.issued7d')} {sevenDays}
        </span>
      </Link>
      {children.length > 0 && (
        <ul className="ml-4 border-l border-border-op30 pl-3">
          {children.map((k) => <Node key={k.id} ca={k} kids={kids} issued={issued} t={t} />)}
        </ul>
      )}
    </li>
  )
}

export function HierarchyCard() {
  const { t } = useTranslation()
  const state = useCardData(async () => {
    const [cas, issuance] = await Promise.all([casService.getAll(), overviewService.getIssuance(DAYS)])
    return { data: { cas: cas?.data, issuance: issuance?.data }, meta: cas?.meta }
  })
  const cas = Array.isArray(state.data?.cas) ? state.data.cas : []
  const byCa = state.data?.issuance?.by_ca
  // Issuances per CA in the window; null when the response carries no per-CA series at all
  const issued = Array.isArray(byCa) ? new Map(byCa.map((e) => [e.caref, e.issued])) : null
  const { roots, kids } = buildTree(cas)

  return (
    <CardFrame id="hierarchy" title={t('overview.cards.hierarchy')} state={state} onRetry={state.reload}
      empty={state.status === 'ready' && cas.length === 0}
      action={<Link to="/cas" className="text-sm font-semibold tabular-nums">{num(state.meta?.total)}</Link>}>
      <ul>{roots.map((ca) => <Node key={ca.id} ca={ca} kids={kids} issued={issued} t={t} />)}</ul>
    </CardFrame>
  )
}
