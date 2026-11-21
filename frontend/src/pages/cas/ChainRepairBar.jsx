/**
 * CAs page: the chain repair strip, under the page head when something needs repairing (or on
 * demand), in the mockup's notice grammar: the share of linked authorities as the setup progress
 * bar, the counts, the next automatic pass, Run now, and the findings with their explicit repairs.
 */
import { useState, useEffect } from 'react'
import { Icon } from '../../components/atelier'

function FindingRow({ finding, canConvert, canRestore, onConvert, onRestore, caName, t }) {
  const label = finding.kind === 'shadowed_root'
    ? t('crossCerts.findingShadowed', { name: finding.ca_name, root: finding.root_name })
    : t('crossCerts.findingSameKey', { subject: finding.subject })
  const restores = finding.actions?.includes('restore_primary') && canRestore ? finding.ca_ids || [] : []
  const converts = finding.actions?.includes('convert_to_cross') && canConvert
  return (
    <li data-testid="cross-finding">
      <div className="rl-main"><strong title={finding.subject}>{label}</strong></div>
      {(converts || restores.length > 0) && (
        <div className="rl-action">
          {converts && <button type="button" className="btn" data-write="" onClick={() => onConvert?.(finding)}>{t('crossCerts.convertToCross')}</button>}
          {restores.map((id) => (
            <button type="button" key={id} className="btn" data-write="" onClick={() => onRestore?.(finding, id)}>
              {t('crossCerts.restorePrimaryOn', { name: caName ? caName(id) : `#${id}` })}
            </button>
          ))}
        </div>
      )}
    </li>
  )
}

export function ChainRepairBar({ data, running, onRun, canRunRepair, t, findings = [], canConvert = false, canRestore = false, onConvert, onRestore, caName }) {
  const task = data?.task || {}
  const crStats = data?.stats || {}
  const [countdown, setCountdown] = useState('')
  const [showFindings, setShowFindings] = useState(false)

  useEffect(() => {
    if (!task.next_run) return undefined
    const update = () => {
      const diff = Math.max(0, Math.floor((new Date(task.next_run).getTime() - Date.now()) / 1000))
      setCountdown(`${Math.floor(diff / 60)}:${String(diff % 60).padStart(2, '0')}`)
    }
    update()
    const id = setInterval(update, 1000)
    return () => clearInterval(id)
  }, [task.next_run])

  if (!data) return null
  const total = crStats.total_cas || 0
  const orphans = crStats.orphan_cas || 0
  const sameKey = crStats.same_key_distinct_certs || 0
  const pct = total > 0 ? Math.round(((total - orphans) / total) * 100) : 100
  const attention = orphans > 0 || sameKey > 0 || findings.length > 0

  return (
    <section className={attention ? 'notice warn ca-repair' : 'notice ca-repair'} aria-labelledby="ca-repair-title" data-testid="chain-repair">
      <Icon name="link" />
      <div className="ca-repair-body">
        <div className="ca-repair-head">
          <strong id="ca-repair-title">{t('dashboard.chainRepair')}</strong>
          <div className="setup-progress">
            <div className="setup-bar" role="progressbar" aria-labelledby="ca-repair-title" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
              <span style={{ width: `${pct}%` }} />
            </div>
            <p className="mono">{pct} %</p>
          </div>
          <span>{t('cas.repair.counts', { cas: total, certs: crStats.total_certs || 0 })}</span>
          {orphans > 0 && <span>{orphans} {t('dashboard.chainRepairOrphans')}</span>}
          {sameKey > 0 && <span>{sameKey} {t('dashboard.chainRepairSameKey')}</span>}
          {running ? <span role="status">{t('cas.repair.running')}</span>
            : countdown ? <span className="mono" title={t('cas.repair.nextRun')}><Icon name="clock" />{countdown}</span> : null}
          {findings.length > 0 && (
            <button type="button" className="text-link" aria-expanded={showFindings} onClick={() => setShowFindings((v) => !v)}>
              {t('crossCerts.findings', { count: findings.length })}<Icon name={showFindings ? 'up' : 'down'} />
            </button>
          )}
          {canRunRepair && (
            <button type="button" className="btn" data-write="" onClick={onRun} disabled={running}>
              <Icon name="refresh" />{t('dashboard.chainRepairRun')}
            </button>
          )}
        </div>
        {showFindings && findings.length > 0 && (
          <>
            <p className="small">{t('crossCerts.findingsNote')}</p>
            <ul className="record-list">
              {findings.map((f, i) => (
                <FindingRow key={`${f.kind}-${f.ca_id ?? f.ski}-${i}`} finding={f} t={t}
                  canConvert={canConvert} canRestore={canRestore} onConvert={onConvert} onRestore={onRestore} caName={caName} />
              ))}
            </ul>
          </>
        )}
      </div>
    </section>
  )
}
