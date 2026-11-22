/**
 * The mockup's hierarchyCard() and hierNode() over the CA list and GET /dashboard/issuance:
 * one tree per root, each authority a card with its state, CRL, OCSP and issuances on 7 days,
 * bounded to a few lines on a large installation.
 */
import { useContext } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { EmptyBlock, Icon } from '../atelier'
import { casService, overviewService } from '../../services'
import { HIERARCHY_LIMIT, boundedTree, nameOf } from '../../lib/overviewHierarchy'
import { stateLabel } from '../../lib/stateLabel'
import { ISSUANCE_DAYS, recentTotal } from '../../lib/overviewViz'
import { OverviewCard, OverviewContext, num, settle, useCardData } from './shared'

const DAYS = 7
// A CA state that is not active: its badge tone and icon (the mockup's caStates)
const STATE_BADGE = { pending: ['warn', 'clock'], revoked: ['bad', 'block'], expired: ['bad', 'warning'] }

function Node({ ca, tree, issued, t }) {
  const children = tree.shown.get(ca.id) || []
  const hidden = (tree.kids.get(ca.id) || []).length - children.length
  const count = issued === null ? '–' : (issued.get(ca.refid) ?? 0)
  const state = String(ca.status || 'active').toLowerCase()
  const [tone, icon] = STATE_BADGE[state] || ['warn', 'warning']
  const crl = <span><Icon name={ca.cdp_enabled ? 'check' : 'block'} />{t(ca.cdp_enabled ? 'overview.hierarchy.crlOn' : 'overview.hierarchy.crlOff')}</span>
  return (
    <li className="hier-node">
      <Link className={`hier-card state-${state}`} to={`/cas/${ca.id}`} data-ca-link={ca.id}>
        <span className="hier-head">
          <Icon name={ca.parent_id ? 'branch' : 'shield'} />
          <strong>{nameOf(ca)}</strong>
          {state === 'active'
            ? <span className="sr-only">{t('overview.hierarchy.active')}</span>
            : <span className={`badge ${tone}`}><Icon name={icon} />{stateLabel(t, ca.status)}</span>}
        </span>
        <span className="hier-meta">
          {ca.parent_id ? (
            <>
              {crl}
              <span><Icon name={ca.ocsp_enabled ? 'check' : 'block'} />{t(ca.ocsp_enabled ? 'overview.hierarchy.ocspOn' : 'overview.hierarchy.ocspOff')}</span>
              <span><Icon name="cert" />{t('overview.hierarchy.issued', { count })}</span>
            </>
          ) : (
            <>
              {ca.offline && <span><Icon name="lock" />{t('overview.hierarchy.offline')}</span>}
              {crl}
              {ca.cross_certificate_count > 0 && <span><Icon name="link" />{t('overview.hierarchy.crossSigned')}</span>}
            </>
          )}
          {hidden > 0 && <span data-hidden-below=""><Icon name="branch" />{t('overview.hierarchy.below', { count: hidden })}</span>}
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
    <div className="panel-content hier-columns">
      <ul className="hier-tree">
        {entries.slice(0, HIERARCHY_LIMIT).map((e) => (
          <li key={e.caref ?? e.ca_id} className="hier-node">
            <span className="hier-card">
              <span className="hier-head"><Icon name="branch" /><strong>{e.ca_name || e.caref || '–'}</strong></span>
              <span className="hier-meta"><span><Icon name="cert" />{t('overview.hierarchy.issued', { count: num(e.total) })}</span></span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function HierarchyCard() {
  const { t } = useTranslation()
  const page = useContext(OverviewContext)
  // The strip's 30 days, one request for both; the card counts the last 7
  const issuance = () => (page?.share
    ? page.share('issuance', () => overviewService.getIssuance(ISSUANCE_DAYS)) : overviewService.getIssuance(ISSUANCE_DAYS))
  const state = useCardData(async () => {
    const { got, missing } = await settle(
      { cas: () => casService.getAll(), issuance },
      (g) => Boolean(g.cas) || g.issuance?.data?.by_ca?.length > 0)
    return { data: { cas: got.cas?.data, issuance: got.issuance?.data, missing }, meta: got.cas?.meta }
  }, ['ca', 'certificate'])
  const casLoaded = Array.isArray(state.data?.cas)
  const cas = casLoaded ? state.data.cas : []
  const byCa = state.data?.issuance?.by_ca
  // Issuances and renewals per CA in the window; null when the response carries no per-CA series at all
  const issued = Array.isArray(byCa) ? new Map(byCa.map((e) => [e.caref, recentTotal(e, DAYS)])) : null
  const tree = boundedTree(cas, issued)
  const total = typeof state.meta?.total === 'number' ? state.meta.total : cas.length
  const sub = casLoaded && [
    t('overview.hierarchy.sub', {
      authorities: t('overview.hierarchy.authorities', { count: total }), roots: t('overview.hierarchy.roots', { count: tree.rootCount }),
    }),
    tree.listed < cas.length ? t('overview.hierarchy.bounded', { shown: tree.listed, total }) : null,
  ].filter(Boolean).join(' ')

  return (
    <OverviewCard id="hierarchy" state={state} route="GET /api/v2/cas" missing={state.data?.missing}
      empty={state.status === 'ready' && casLoaded && cas.length === 0 && (
        <div className="panel-content hier-columns">
          <EmptyBlock id="cas" icon="shield" title={t('overview.hierarchy.emptyTitle')} text={t('overview.hierarchy.emptyText')} />
        </div>
      )}
      sub={sub || undefined}
      tools={casLoaded && <Link to="/cas" className="text-link" data-nav="cas">{t('overview.hierarchy.explore')} <Icon name="right" /></Link>}>
      {casLoaded ? (
        <div className="panel-content hier-columns">
          {tree.roots.map((ca) => (
            <ul key={ca.id} className="hier-tree" aria-label={t('overview.hierarchy.branch', { name: nameOf(ca) })}>
              <Node ca={ca} tree={tree} issued={issued} t={t} />
            </ul>
          ))}
        </div>
      ) : <IssuedOnly entries={Array.isArray(byCa) ? byCa : []} t={t} />}
    </OverviewCard>
  )
}
