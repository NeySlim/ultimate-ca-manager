/**
 * The discovery docks: an analysis is the mockup's simplePage() dock (Aperçu: Propriétés, Résumé)
 * with the product's runs of it; a found certificate and a run are the product's further views,
 * drawn in the same dock and sections.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, Dock, DockBody, Icon, Pill, Props, RecordList, RecordRow, Section } from '../../components/atelier'
import { useOpenEntity } from '../../hooks/useOpenEntity'
import { discoveryService } from '../../services'
import { formatDate } from '../../lib/utils'
import { extensionRows } from '../../lib/certificateDetail'
import { keyAlgorithmLabel } from '../../lib/keyAlgorithms'
import { FOUND_TONES, RUN_TONES, SCAN_TONES, dnParts, durationLabel, errorHint, foundState, portsOf, runState, targetsOf, runTitle, foundTitle, useScanFacts } from './discoveryModel'

const when = (d) => (d ? formatDate(d, { time: true }) : '—')
const mono = (v) => <span className="mono">{v}</span>

export function ScanPill({ state }) {
  const { t } = useTranslation()
  return <Pill label={t(`discovery.scans.state.${state}`)} tone={SCAN_TONES[state]} />
}
export function RunPill({ run }) {
  const { t } = useTranslation()
  const s = runState(run)
  return <Pill label={t(`discovery.runs.state.${s}`)} tone={RUN_TONES[s]} />
}
export function FoundPill({ cert }) {
  const { t } = useTranslation()
  const s = foundState(cert)
  return <Pill label={t(`discovery.found.state.${s}`)} tone={FOUND_TONES[s]} />
}

export function ScanDock({ profile, run, runs, state, section, onSection, onClose, actions }) {
  const { t } = useTranslation()
  const facts = useScanFacts()
  const own = runs.filter((r) => r.scan_profile_id === profile.id)
  return (
    <Dock label={t('atelier.detailOf', { name: t('discovery.scans.title') })} tabsLabel={t('atelier.openItem')} activeKey={profile.id}
      tabs={[{ key: profile.id, title: profile.name, icon: 'radar' }]} onClose={onClose}>
      <DockBody icon="radar" title={profile.name} badge={<ScanPill state={state} />} actions={actions}
        sections={[['overview', t('atelier.overview')], ['runs', t('discovery.scans.runsTab')]]}
        section={section} onSection={onSection} sectionsLabel={t('atelier.sectionsOf', { name: profile.name })}>
        {section === 'runs' ? (
          <RecordList empty={t('discovery.noHistory')}>
            {own.map((r) => (
              <RecordRow key={r.id} title={when(r.started_at)}
                meta={t('discovery.runs.summary', { count: r.certs_found ?? 0, targets: r.targets_scanned ?? 0 })} badge={<RunPill run={r} />} />
            ))}
          </RecordList>
        ) : (
          <div className="module-detail">
            <Section title={t('atelier.properties')}>
              <Props items={[
                [t('discovery.form.range'), mono(targetsOf(profile).join(', ') || '—')],
                [t('discovery.ports'), mono(portsOf(profile).join(', '))],
                [t('discovery.scans.found'), facts.found(profile, run)],
                [t('discovery.scans.last'), facts.last(profile, run)],
                [t('discovery.schedule'), facts.schedule(profile)],
                profile.schedule_enabled && profile.next_scan_at && [t('discovery.scans.next'), when(profile.next_scan_at)],
                profile.notify_email && [t('discovery.notifyEmail'), profile.notify_email],
                [t('atelier.state'), <ScanPill state={state} />],
              ]} />
            </Section>
            <Section title={t('atelier.summary')}>
              <p className="summary">{profile.description || <span className="muted">{t('discovery.scans.noDescription')}</span>}</p>
            </Section>
          </div>
        )}
      </DockBody>
    </Dock>
  )
}

export function RunDock({ run, onClose }) {
  const { t } = useTranslation()
  const title = runTitle(run, t)
  return (
    <Dock label={t('atelier.detailOf', { name: t('discovery.runs.title') })} tabsLabel={t('atelier.openItem')} activeKey={run.id}
      tabs={[{ key: run.id, title, icon: 'clock' }]} onClose={onClose}>
      <DockBody icon="clock" title={title} badge={<RunPill run={run} />}
        sections={[['overview', t('atelier.overview')]]} section="overview" onSection={() => {}} sectionsLabel={t('atelier.sectionsOf', { name: title })}>
        <div className="module-detail">
          <Section title={t('atelier.properties')}>
            <Props items={[
              [t('discovery.profile'), title],
              [t('discovery.certsFound'), run.certs_found ?? 0],
              run.new_certs > 0 && [t('discovery.runs.new'), run.new_certs],
              run.changed_certs > 0 && [t('discovery.runs.changed'), run.changed_certs],
              [t('discovery.targetsScanned'), `${run.targets_scanned ?? 0} / ${run.total_targets ?? '—'}`],
              [t('discovery.startedAt'), when(run.started_at)],
              [t('discovery.completedAt'), when(run.completed_at)],
              [t('discovery.duration'), durationLabel(run.duration_seconds) || '—'],
              run.triggered_by && [t('discovery.runs.trigger'), [t(`discovery.runs.by.${run.triggered_by}`, { defaultValue: run.triggered_by }), run.triggered_by_user].filter(Boolean).join(' · ')],
              [t('atelier.state'), <RunPill run={run} />],
            ]} />
          </Section>
        </div>
      </DockBody>
    </Dock>
  )
}

export function FoundDock({ cert, onClose, actions }) {
  const { t } = useTranslation()
  const openEntity = useOpenEntity()
  const [detail, setDetail] = useState(null)
  const failed = cert.status === 'error'
  useEffect(() => {
    if (!cert?.id || failed) return undefined
    let live = true
    discoveryService.getById(cert.id).then((res) => { if (live) setDetail(res?.data || res) }).catch(() => {})
    return () => { live = false }
  }, [cert?.id, failed])
  const c = { ...cert, ...(detail || {}) }
  const title = foundTitle(cert, t)
  const hint = errorHint(cert.scan_error)
  const days = cert.days_until_expiry
  const dn = (v) => {
    const parts = dnParts(v)
    return parts.length ? <Props items={parts.map(([k, val], i) => [`${k}${parts.slice(0, i).some(([x]) => x === k) ? ` (${i})` : ''}`, val])} /> : <p className="muted small">—</p>
  }
  const exts = extensionRows(c.extensions)
  return (
    <Dock label={t('atelier.detailOf', { name: t('discovery.found.title') })} tabsLabel={t('atelier.openItem')} activeKey={cert.id}
      tabs={[{ key: cert.id, title, icon: 'cert' }]} onClose={onClose}>
      <DockBody icon="cert" title={title} badge={<FoundPill cert={cert} />} actions={actions}
        sections={[['overview', t('atelier.overview')]]} section="overview" onSection={() => {}} sectionsLabel={t('atelier.sectionsOf', { name: title })}>
        <div className="module-detail">
          {failed && (
            <div className="notice bad" role="note"><Icon name="warning" /><span><span className="mono">{cert.scan_error}</span>{hint && <><br />{t(hint)}</>}</span></div>
          )}
          <Section title={t('atelier.properties')}>
            <Props items={[
              [t('discovery.host'), mono(`${cert.target}:${cert.port || 443}`)],
              cert.sni_hostname && ['SNI', mono(cert.sni_hostname)],
              cert.dns_hostname && [t('discovery.dnsHostname'), cert.dns_hostname],
              [t('atelier.state'), <FoundPill cert={cert} />],
              cert.ucm_certificate_id && [t('discovery.found.inInventory'),
                <button type="button" className="text-link" onClick={() => openEntity('certificate', cert.ucm_certificate_id)}>#{cert.ucm_certificate_id}</button>],
              !failed && [t('common.serialNumber'), mono(cert.serial_number || '—')],
              !failed && [t('common.notBefore'), when(cert.not_before)],
              !failed && [t('common.notAfter'), <>{when(cert.not_after)}{cert.is_expired ? <> · <span className="bad">{t('common.expired')}</span></>
                : days != null && days <= 30 ? <> · <span className="warn">{t('discovery.found.inDays', { count: days })}</span></> : null}</>],
              c.key_algorithm && [t('common.keyAlgorithm'), `${keyAlgorithmLabel(c.key_algorithm, t, c.security_level)}${c.key_size ? ` ${c.key_size}` : ''}${c.curve ? ` (${c.curve})` : ''}`],
              c.signature_algorithm && [t('common.issuerSignatureAlgorithm'), c.signature_algorithm],
              [t('discovery.firstSeen'), when(cert.first_seen)],
              [t('discovery.lastSeen'), when(cert.last_seen)],
              cert.last_changed_at && [t('discovery.lastChanged'), when(cert.last_changed_at)],
            ]} />
          </Section>
          {!failed && <Section title={t('common.subject')}>{dn(cert.subject)}</Section>}
          {!failed && <Section title={t('common.issuer')}>{dn(cert.issuer)}</Section>}
          {!failed && (exts.length > 0 || cert.san_dns_names?.length > 0 || cert.san_ip_addresses?.length > 0) && (
            <Section title={t('discovery.found.extensions')}>
              <Props items={exts.length ? exts.map((r) => [r.label, <>{r.values.map((v, i) => <span key={i}>{i > 0 && <br />}{v}</span>)}<br /><small className="mono muted">{r.oid}{r.critical ? ` · ${t('inspector.cert.critical')}` : ''}</small></>])
                : [[t('discovery.subjectAltNames'), [...(cert.san_dns_names || []), ...(cert.san_ip_addresses || [])].join(', ')]]} />
            </Section>
          )}
          {!failed && (c.fingerprint_sha256 || c.fingerprint_sha1) && (
            <Section title={t('common.fingerprint')}>
              <Props items={[
                c.fingerprint_sha256 && ['SHA-256', mono(c.fingerprint_sha256)],
                c.fingerprint_sha1 && ['SHA-1', mono(c.fingerprint_sha1)],
              ]} />
            </Section>
          )}
        </div>
      </DockBody>
    </Dock>
  )
}

/** The dock heading's actions on a found certificate. */
export function FoundActions({ cert, canScan, canRemove, busy, onRetry, onRemove }) {
  const { t } = useTranslation()
  return (
    <>
      {cert.status === 'error' && canScan && (
        <Btn icon="refresh" id="found-retry" write disabled={busy || undefined} onClick={() => onRetry(cert)}>{t('discovery.retry')}</Btn>
      )}
      {canRemove && <Btn tone="danger" icon="block" id="found-remove" onClick={() => onRemove(cert)}>{t('common.delete')}…</Btn>}
    </>
  )
}
