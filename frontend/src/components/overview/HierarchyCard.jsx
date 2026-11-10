import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { casService, overviewService } from '../../services'
import { CardFrame, num, settle, useCardData } from './shared'

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

/** Without the authorities, the issuances per CA are all the card still has: no link to a page that may be forbidden. */
function IssuedOnly({ entries, t }) {
  return (
    <ul>
      {entries.map((e) => (
        <li key={e.caref ?? e.ca_id} className="flex items-center justify-between gap-3 py-1">
          <span className="text-sm text-text-primary truncate">{e.ca_name || e.caref || '–'}</span>
          <span className="text-xs text-text-secondary tabular-nums whitespace-nowrap">
            {t('overview.hierarchy.issued7d')} {num(e.issued)}
          </span>
        </li>
      ))}
    </ul>
  )
}

export function HierarchyCard() {
  const { t } = useTranslation()
  const state = useCardData(async () => {
    const { got, missing } = await settle(
      { cas: () => casService.getAll(), issuance: () => overviewService.getIssuance(DAYS) },
      (g) => Boolean(g.cas) || g.issuance?.data?.by_ca?.length > 0)
    return { data: { cas: got.cas?.data, issuance: got.issuance?.data, missing }, meta: got.cas?.meta }
  })
  const casLoaded = Array.isArray(state.data?.cas)
  const cas = casLoaded ? state.data.cas : []
  const byCa = state.data?.issuance?.by_ca
  // Issuances per CA in the window; null when the response carries no per-CA series at all
  const issued = Array.isArray(byCa) ? new Map(byCa.map((e) => [e.caref, e.issued])) : null
  const { roots, kids } = buildTree(cas)

  return (
    <CardFrame id="hierarchy" title={t('overview.cards.hierarchy')} state={state} onRetry={state.reload}
      missing={state.data?.missing}
      empty={state.status === 'ready' && casLoaded && cas.length === 0}
      action={casLoaded && <Link to="/cas" className="text-sm font-semibold tabular-nums">{num(state.meta?.total)}</Link>}>
      {casLoaded
        ? <ul>{roots.map((ca) => <Node key={ca.id} ca={ca} kids={kids} issued={issued} t={t} />)}</ul>
        : <IssuedOnly entries={Array.isArray(byCa) ? byCa : []} t={t} />}
    </CardFrame>
  )
}
