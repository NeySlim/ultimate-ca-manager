import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { CaretRight, CheckCircle, GitBranch, LinkSimple, Lock, Prohibit, ShieldCheck } from '@phosphor-icons/react'
import { casService, overviewService } from '../../services'
import { HIERARCHY_LIMIT, boundedTree, nameOf } from '../../lib/overviewHierarchy'
import { stateLabel } from '../../lib/stateLabel'
import { CardFrame, Pill, num, settle, useCardData } from './shared'

const DAYS = 7

function Node({ ca, tree, issued, t }) {
  const children = tree.shown.get(ca.id) || []
  const hidden = (tree.kids.get(ca.id) || []).length - children.length
  const sevenDays = issued === null ? '–' : (issued.get(ca.refid) ?? 0)
  const inactive = ca.status && ca.status !== 'Active'
  const Icon = ca.parent_id ? GitBranch : ShieldCheck
  return (
    <li>
      <Link to={`/cas/${ca.id}`} className="ov-hier-node" data-state={String(ca.status || 'active').toLowerCase()}>
        <span className="ov-hier-head">
          <Icon size={15} aria-hidden="true" />
          <strong>{nameOf(ca)}</strong>
          {inactive && <Pill tone={ca.status === 'Pending' ? 'warn' : 'bad'}>{stateLabel(t, ca.status)}</Pill>}
        </span>
        <span className="ov-hier-meta">
          {ca.offline && <Pill icon={Lock}>{t('overview.hierarchy.offline')}</Pill>}
          {ca.cross_certificate_count > 0 && <Pill icon={LinkSimple}>{t('overview.hierarchy.crossSigned')}</Pill>}
          <Pill tone={ca.cdp_enabled ? undefined : 'plain'} icon={ca.cdp_enabled ? CheckCircle : Prohibit}>
            {t(ca.cdp_enabled ? 'overview.hierarchy.crlOn' : 'overview.hierarchy.crlOff')}
          </Pill>
          <Pill tone={ca.ocsp_enabled ? undefined : 'plain'} icon={ca.ocsp_enabled ? CheckCircle : Prohibit}>
            {t(ca.ocsp_enabled ? 'overview.hierarchy.ocspOn' : 'overview.hierarchy.ocspOff')}
          </Pill>
          {hidden > 0 && <Pill tone="plain" data-testid="hierarchy-hidden">{t('overview.hierarchy.below', { count: hidden })}</Pill>}
          {sevenDays !== 0 && <span className="ov-hier-issued ov-num">{t('overview.hierarchy.issued7d')} {sevenDays}</span>}
        </span>
      </Link>
      {children.length > 0 && (
        <ul>{children.map((k) => <Node key={k.id} ca={k} tree={tree} issued={issued} t={t} />)}</ul>
      )}
    </li>
  )
}

/** Without the authorities, the issuances per CA are all the card still has: no link to a page that may be forbidden. */
function IssuedOnly({ entries, t }) {
  return (
    <ul className="ov-plain-rows">
      {entries.slice(0, HIERARCHY_LIMIT).map((e) => (
        <li key={e.caref ?? e.ca_id}>
          <span>{e.ca_name || e.caref || '–'}</span>
          <span className="ov-muted ov-num">{t('overview.hierarchy.issued7d')} {num(e.issued)}</span>
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
  }, ['ca', 'certificate'])
  const casLoaded = Array.isArray(state.data?.cas)
  const cas = casLoaded ? state.data.cas : []
  const byCa = state.data?.issuance?.by_ca
  // Issuances per CA in the window; null when the response carries no per-CA series at all
  const issued = Array.isArray(byCa) ? new Map(byCa.map((e) => [e.caref, e.issued])) : null
  const tree = boundedTree(cas, issued)
  const total = typeof state.meta?.total === 'number' ? state.meta.total : cas.length

  return (
    <CardFrame id="hierarchy" title={t('overview.cards.hierarchy')} state={state} onRetry={state.reload}
      missing={state.data?.missing}
      empty={state.status === 'ready' && casLoaded && cas.length === 0}
      count={casLoaded ? num(state.meta?.total) : undefined}
      sub={casLoaded ? t('overview.hierarchy.sub', { total, roots: tree.rootCount }) : undefined}
      tools={casLoaded && (
        <Link to="/cas" className="ov-link">{t('overview.hierarchy.explore')}<CaretRight size={13} aria-hidden="true" /></Link>
      )}>
      <div className="ov-body">
        {casLoaded ? (
          <div className="ov-hier-columns">
            {tree.roots.map((ca) => (
              <ul key={ca.id} className="ov-hier-tree" aria-label={t('overview.hierarchy.branch', { name: nameOf(ca) })}>
                <Node ca={ca} tree={tree} issued={issued} t={t} />
              </ul>
            ))}
          </div>
        ) : <IssuedOnly entries={Array.isArray(byCa) ? byCa : []} t={t} />}
        {casLoaded && tree.listed < cas.length && (
          <p className="ov-hier-more">
            <span>{t('overview.hierarchy.bounded', { shown: tree.listed, total })}</span>
            <Link to="/cas" className="ov-link">{t('overview.hierarchy.all', { total })}<CaretRight size={13} aria-hidden="true" /></Link>
          </p>
        )}
      </div>
    </CardFrame>
  )
}
