/**
 * Compliance (maquette-1): the average score as a ring (one ratio), its grades A+ to F, then one gauge
 * per rule of GET /dashboard/compliance with its conforming share and count. A rule the server gives
 * a list filter for opens that list, filtered on its gap. The score comes from /certificates/compliance
 * until /dashboard/compliance carries it; its base is written under the ring when the two differ.
 */
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Icon } from '../atelier'
import { certificatesService, overviewService } from '../../services'
import { listHref } from '../../lib/overviewFilters'
import { GRADE_ORDER, gradeOfScore, rulePercent, ruleTone } from '../../lib/overviewViz'
import { OverviewCard, num, settle, useCardData, useLang } from './shared'
import { Ring, useChartTip } from './viz'

const COUNTERS = ['rsa_below_3072', 'server_lifetime_over_398_days', 'weak_signature_hash',
  'incomplete_chain', 'no_private_key']
const TONE_COLOR = { good: 'var(--good)', warn: 'var(--warn-fill)', bad: 'var(--bad)', info: 'var(--s0)', '': 'var(--s0)' }
const TONE_ICON = { good: 'check', warn: 'warning', bad: 'warning', info: 'block' }
// One hue of the accent, from the strongest grade to the palest
const GRADE_STEPS = [100, 78, 58, 42, 30, 20]
const gradeColor = (i) => `color-mix(in srgb, var(--accent) ${GRADE_STEPS[i]}%, var(--panel))`
const isNum = (v) => typeof v === 'number' && Number.isFinite(v)

/** The population the route names (`population`, a count or {count}), else its total. */
function populationOf(summary) {
  const p = summary?.population
  if (isNum(p)) return p
  if (isNum(p?.count)) return p.count
  return isNum(summary?.total) ? summary.total : null
}

export function ComplianceCard() {
  const { t } = useTranslation()
  const lang = useLang()
  const tip = useChartTip()
  const state = useCardData(async () => {
    const { got, missing } = await settle(
      { summary: () => overviewService.getCompliance(), scores: () => certificatesService.getComplianceStats() },
      (g) => Boolean(g.summary))
    return { data: { summary: got.summary?.data || {}, scores: got.scores?.data || null, missing } }
  }, ['certificate', 'ca'])
  const summary = state.data?.summary || {}
  const scores = state.data?.scores
  const counters = summary.counters || {}
  const total = populationOf(summary)
  // The dashboard's own score once it has one (same population as the rules), else the certificates' route
  const own = isNum(summary.score)
  const score = own ? summary.score : (isNum(scores?.average_score) ? scores.average_score : null)
  const grades = (own ? summary.distribution || summary.grades : null) || scores?.distribution || null
  const graded = grades ? GRADE_ORDER.reduce((s, g) => s + (Number(grades[g]) || 0), 0) : 0
  const scoreBase = own ? total : scores?.total
  const grade = gradeOfScore(score)
  const algos = Array.isArray(summary.by_key_algorithm) ? summary.by_key_algorithm : []
  const link = (entry) => (entry?.filter_available ? listHref(entry.filter_hint) : null)

  const rule = (name) => {
    const n = counters[name]?.count
    const pct = rulePercent(n, total)
    const tone = ruleTone(name, n, total)
    const ok = pct === null ? null : total - n
    const label = t(`overview.compliance.rule.${name}`)
    const stateWord = tone ? t(`overview.compliance.state.${tone}`) : null
    const inner = (
      <>
        <span className="name">{label}<small>{isNum(n) ? t(`overview.compliance.gap.${name}`, { count: n }) : t(`overview.compliance.sub_${name}`)}</small></span>
        <span className="track" role="img" aria-label={pct === null ? '–' : t('overview.compliance.conformPct', { pct })}>
          {pct !== null && <i style={{ width: `${Math.max(2, pct)}%` }} />}
        </span>
        <span className="val">{pct === null ? <b>–</b> : <><b>{t('overview.compliance.pct', { pct })}</b> {`${ok}/${total}`}</>}</span>
        {tone ? <span className={`rule-state ${tone}`} role="img" aria-label={stateWord}><Icon name={TONE_ICON[tone]} /></span> : <span />}
      </>
    )
    const to = link(counters[name])
    const props = {
      className: 'meter', 'data-check': name, 'data-tone': tone || undefined, style: { '--tone': TONE_COLOR[tone] },
      ...(pct === null ? {} : tip.bind({
        title: label,
        rows: [{ label: t('overview.compliance.conform'), value: ok }, { label: t('overview.compliance.inGap'), value: n }],
        hint: to ? t('overview.compliance.openGap') : null,
      })),
    }
    return <li key={name}>{to ? <Link to={to} {...props}>{inner}</Link> : <div {...props}>{inner}</div>}</li>
  }

  const gradeParts = GRADE_ORDER.map((g, i) => ({ key: g, value: Number(grades?.[g]) || 0, color: gradeColor(i) }))
  const table = () => [
    {
      caption: t('overview.compliance.tableRules', { count: num(total) }),
      columns: [t('overview.compliance.ruleCol'), t('overview.compliance.conform'), t('overview.compliance.inGap'), '%'],
      rows: COUNTERS.map((name) => {
        const n = counters[name]?.count
        const pct = rulePercent(n, total)
        return [t(`overview.compliance.rule.${name}`), pct === null ? '–' : total - n, isNum(n) ? n : '–', pct ?? '–']
      }),
    },
    ...(grades ? [{
      caption: t('overview.compliance.tableGrades', { count: num(scoreBase) }),
      columns: [t('overview.compliance.gradeCol'), t('overview.compliance.certificates')],
      rows: gradeParts.map((p) => [p.key, p.value]),
    }] : []),
    ...(algos.length ? [{
      caption: t('overview.compliance.byAlgorithm'),
      columns: [t('overview.compliance.algoCol'), t('overview.compliance.certificates')],
      rows: algos.map((a) => [a.key_algo ?? t('overview.compliance.unknownAlgo'), num(a.count)]),
    }] : []),
  ]

  return (
    <OverviewCard id="compliance" state={state} route="GET /api/v2/dashboard/compliance" missing={state.data?.missing}
      empty={state.status === 'ready' && summary.total === 0} table={table}
      sub={t('overview.compliance.subRules', { count: num(total) })}>
      <div className="panel-content comp">
        {score !== null && (
          <div className="comp-score">
            <Ring value={score} label={t('overview.compliance.ringAlt', { score, grade })}>
              <span className="value">{score}</span>
              <small>{t('overview.compliance.ringSub', { grade })}</small>
            </Ring>
            {grades && graded > 0 && (
              <div className="grades">
                <span className="grade-bar">
                  {gradeParts.filter((p) => p.value > 0).map((p) => (
                    <i key={p.key} tabIndex={0} data-grade={p.key} style={{ flexGrow: p.value, background: p.color }}
                      aria-label={t('overview.compliance.gradeAlt', { grade: p.key, count: p.value })}
                      {...tip.bind({
                        title: t('overview.compliance.grade', { grade: p.key }),
                        rows: [{ label: t('overview.compliance.certificates'), value: p.value },
                          { label: t('overview.compliance.share'), value: t('overview.compliance.pct', { pct: Math.round((p.value / graded) * 100) }) }],
                      })} />
                  ))}
                </span>
                <ul className="legend">
                  {gradeParts.map((p) => <li key={p.key}><i className="swatch" style={{ background: p.color }} />{p.key}<b>{p.value.toLocaleString(lang)}</b></li>)}
                </ul>
              </div>
            )}
            {!own && isNum(scoreBase) && scoreBase !== total && (
              <p className="score-base">{t('overview.compliance.scoreBase', { count: scoreBase })}</p>
            )}
          </div>
        )}
        <ul className="meters">{COUNTERS.map(rule)}</ul>
      </div>
      {tip.node}
    </OverviewCard>
  )
}
