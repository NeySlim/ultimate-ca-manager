/**
 * Authorities and HSM as live tiles (maquette-3): for the authorities in alert first, then the most
 * active, their state in a word, algorithm, key guard, validity spent, CRL, OCSP and issuances over
 * 7 days; for the HSM modules, their state, last test, keys held and authorities served.
 */
import { useContext, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Icon } from '../atelier'
import { casService, crlService, hsmService, overviewService } from '../../services'
import { usePermission } from '../../hooks/usePermission'
import { compactDue, shortParts } from '../../lib/relativeTime'
import { clockOf } from '../../lib/overviewTime'
import { ISSUANCE_DAYS } from '../../lib/overviewViz'
import { chooseTiles, daysSince } from '../../lib/overviewTiles'
import { CardEmpty, OverviewCard, OverviewContext, settle, useCardData, useLang } from './shared'
import { Spark } from './viz'

const STATE_ICON = { good: 'check', warn: 'warning', bad: 'warning', muted: 'block' }

/** What is left of a validity, short (« 2 a 11 mois », « 48 j »). */
function leftOf(date, t) {
  const p = shortParts(date)
  return p ? t(p.key, { count: p.count, months: p.months }) : '–'
}


function Badge({ tile, t }) {
  return (
    <span className={tile.tone === 'muted' ? 'chip' : `chip ${tile.tone}`} data-tone={tile.tone}>
      <Icon name={STATE_ICON[tile.tone]} />{t(`overview.tiles.state.${tile.key}`, { count: tile.count })}
    </span>
  )
}

function CaTile({ tile, t }) {
  const left = tile.validTo ? leftOf(tile.validTo, t) : '–'
  const expired = tile.elapsed !== null && tile.elapsed >= 100
  const crl = {
    current: tile.crl.next_update ? t('overview.tiles.crlWhen', { when: compactDue(tile.crl.next_update, t) }) : t('overview.tiles.crlCurrent'),
    stale: tile.crl.next_update ? t('overview.tiles.crlStaleSince', { count: daysSince(tile.crl.next_update) }) : t('overview.tiles.crlStale'),
    missing: t('overview.tiles.crlMissing'), off: t('overview.tiles.crlOff'), unknown: '–',
  }[tile.crl.state]
  return (
    <Link className="atile" to={`/cas/${tile.id}`} data-tile="ca" data-tile-id={tile.id} data-tone={tile.tone}>
      <span className="atile-top"><Icon name="shield" /><b>{tile.name}</b><Badge tile={tile} t={t} /></span>
      <span className="atile-meta">
        {tile.algo && <span className="chip">{tile.algo}</span>}
        <span className="chip"><Icon name="key" />
          {tile.guard.hsm !== undefined ? t('overview.tiles.hsmKey', { name: tile.guard.hsm }) : t(tile.guard.software ? 'overview.tiles.softwareKey' : 'overview.tiles.noKey')}
        </span>
      </span>
      {tile.elapsed !== null && (
        // An expired CA reads red as its pill; amber is for one late in its life
        <span className="life" style={{ '--tone': expired ? 'var(--bad)' : tile.late ? 'var(--warn-fill)' : 'var(--accent)' }}>
          <span>{t('overview.tiles.elapsed')}</span>
          <span><b className={expired ? 'bad' : tile.late ? 'warn' : undefined}>{t('overview.compliance.pct', { pct: tile.elapsed })}</b>{tile.elapsed < 100 ? ` · ${t('overview.tiles.left', { when: left })}` : ''}</span>
          <span className={expired ? 'track expired' : tile.late ? 'track late' : 'track'} role="img" aria-label={t('overview.tiles.elapsedAlt', { pct: tile.elapsed, when: left })}>
            <i style={{ width: `${Math.max(2, tile.elapsed)}%` }} />
          </span>
        </span>
      )}
      <span className="atile-foot">
        <span className={tile.crl.state === 'stale' || tile.crl.state === 'missing' ? 'bad' : undefined}>
          <Icon name={tile.crl.state === 'stale' || tile.crl.state === 'missing' ? 'warning' : 'clock'} />{crl}
        </span>
        <span>{t(tile.ocsp ? 'overview.hierarchy.ocspOn' : 'overview.hierarchy.ocspOff')}</span>
        {tile.activity && tile.issued > 0
          ? <Spark values={tile.activity} w={72} h={24} label={t('overview.tiles.activityAlt', { count: tile.issued })} />
          : <span>{t('overview.tiles.noActivity')}</span>}
      </span>
    </Link>
  )
}

function HsmTile({ tile, t, lang, onTest, busy }) {
  return (
    <div className="atile" data-tile="hsm" data-tile-id={tile.id} data-tone={tile.tone}>
      <span className="atile-top"><Icon name="chip" /><b><Link to="/hsm">{tile.name}</Link></b><Badge tile={tile} t={t} /></span>
      <span className="atile-meta">
        {tile.type && <span className="chip">{tile.type}</span>}
        {tile.certification && <span className="chip"><Icon name="shield" />{tile.certification}</span>}
      </span>
      <span className="life">
        <span>{t('overview.tiles.keys')}</span><b>{tile.keys}</b>
        <span>{t('overview.tiles.served')}</span><b>{tile.cas}</b>
      </span>
      <span className="atile-foot">
        <span><Icon name="clock" />{tile.tested ? t('overview.tiles.tested', { when: clockOf(tile.tested, t, lang) }) : t('overview.tiles.neverTested')}</span>
        {onTest && (
          <button type="button" className="text-link" data-action="test-hsm" disabled={busy} onClick={onTest}>
            {t('overview.tiles.test')}
          </button>
        )}
      </span>
    </div>
  )
}

export function AuthoritiesCard() {
  const { t } = useTranslation()
  const lang = useLang()
  const page = useContext(OverviewContext)
  const { hasPermission } = usePermission()
  const shared = (key, run) => (page?.share ? page.share(key, run) : run())
  const state = useCardData(async () => {
    const { got, missing } = await settle({
      cas: () => shared('cas', () => casService.getAll()),
      crls: () => crlService.getAll(),
      providers: () => (hasPermission('read:hsm') ? hsmService.getProviders() : Promise.resolve({ data: [] })),
      issuance: () => shared('issuance', () => overviewService.getIssuance(ISSUANCE_DAYS)),
    }, (g) => Boolean(g.cas) || g.providers?.data?.length > 0)
    return { data: { cas: got.cas?.data, crls: got.crls?.data, providers: got.providers?.data, issuance: got.issuance?.data, missing } }
  }, ['ca', 'certificate'])
  const [busy, setBusy] = useState(null)
  const data = state.data || {}
  const { tiles, authorities, modules } = chooseTiles(data)
  const canTest = hasPermission('write:hsm') && page?.notify
  const test = (tile) => async () => {
    setBusy(tile.id)
    try {
      await hsmService.testProvider(tile.id)
      page.notify.showSuccess(t('overview.tiles.testDone', { name: tile.name }))
    } catch (error) {
      page.notify.showError(error?.message || t('overview.queue.actionFailed'))
    } finally {
      setBusy(null)
      state.refresh()
    }
  }

  return (
    <OverviewCard id="authorities" state={state} route="GET /api/v2/cas" missing={data.missing}
      sub={t('overview.tiles.sub', { authorities: t('overview.hierarchy.authorities', { count: authorities }), modules: t('overview.tiles.modules', { count: modules }) })}
      // No authority: the hierarchy's empty block, not the green tick of a card with nothing to report
      empty={state.status === 'ready' && tiles.length === 0 && <div className="panel-content"><CardEmpty id="tiles-empty" icon="shield" title={t('overview.hierarchy.emptyTitle')} /></div>}
      tools={<Link to="/cas" className="text-link" data-nav="cas">{t('overview.tiles.explore')} <Icon name="right" /></Link>}>
      <div className="panel-content">
        <div className="atiles">
          {tiles.map((tile) => (tile.kind === 'ca'
            ? <CaTile key={`ca-${tile.id}`} tile={tile} t={t} />
            : <HsmTile key={`hsm-${tile.id}`} tile={tile} t={t} lang={lang} busy={busy === tile.id} onTest={canTest ? test(tile) : null} />))}
        </div>
      </div>
    </OverviewCard>
  )
}
