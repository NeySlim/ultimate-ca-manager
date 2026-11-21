/**
 * The Aperçu panel of a certificate: the mockup's overviewDetail() (validity, identity and key, the
 * chain of trust as a small tree), then what the product shows in more, folded under « Plus de
 * détails » (the issue form's advanced toggle).
 */
import { Fragment, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from '../../../components/atelier'
import { formatDate, extractCN } from '../../../lib/utils'
import { validityFacts, chainNodes, lastAcmeFailure, certificateKeyLabel, serialHex, certTypeLabel, originLabel, complianceReasonLabel } from '../../../lib/certificateDetail'
import { compactAgo } from '../../../lib/relativeTime'
import { signatureHashName } from '../../../lib/signatureName'
import { sourceLabel, sourceOf, SOURCE_LABEL_KEYS } from '../certificateSources'
import { usePermission } from '../../../hooks'
import { acmeService } from '../../../services/acme.service'
import { CertDeploySection } from '../../../components/deploy/CertDeploySection'

const GRADE_TONES = { 'A+': 'good', A: 'good', B: 'good', C: 'warn', D: 'warn', F: 'bad' }
const ACME_CLIENT_SOURCES = ['acme_client', 'letsencrypt']
const OVERRIDE_LABELS = { key_type: 'common.keyType', validity_days: 'common.validityPeriod', digest: 'common.digest' }
const SOURCES = { keys: SOURCE_LABEL_KEYS, label: sourceLabel }

/** Subject alternative names, one per line: the parsed entries, else the stored list. */
function sanLines(cert) {
  const entries = cert?.extensions?.subject_alt_names?.entries
  if (entries?.length) return entries.map((e) => (e.type === 'DNS' ? e.value : `${e.type}: ${e.value}`))
  return cert?.san_combined ? cert.san_combined.split(',').map((s) => s.trim()).filter(Boolean) : []
}

// The open failure of UCM's own ACME client for this certificate, when the user may read it
function useAcmeFailure(cert) {
  const { hasPermission } = usePermission()
  const [failure, setFailure] = useState(null)
  const wanted = ACME_CLIENT_SOURCES.includes(cert?.source) && hasPermission('read:acme')
  useEffect(() => {
    if (!wanted) return undefined
    let cancelled = false
    acmeService.getClientOrders(undefined, undefined, { per_page: 100 })
      .then((res) => { if (!cancelled) setFailure(lastAcmeFailure(cert, res?.data || [])) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [wanted, cert?.id, cert?.renewed_at]) // eslint-disable-line react-hooks/exhaustive-deps
  return wanted ? failure : null
}

const Props = ({ items }) => (
  <dl className="props">{items.filter(Boolean).map(([k, v, cls]) => [<dt key={`${k}-t`}>{k}</dt>, <dd key={`${k}-d`} className={cls}>{v}</dd>])}</dl>
)

/** The chain as a small tree, anchor first, the certificate last (the mockup's miniChain()). */
function MiniChain({ cert, title, openCa }) {
  const { t } = useTranslation()
  const nodes = chainNodes(cert)
  const issuer = cert.issuer_name || extractCN(cert.issuer)
  const shown = nodes.length ? nodes : (issuer ? [{ name: issuer, role: 'intermediate', issuing: true }] : [])
  return (
    <ol className="chain-mini">
      {shown.map((n, i) => (
        <li key={`${n.name}-${i}`}>
          <Icon name={n.role === 'intermediate' ? 'branch' : 'shield'} />
          {openCa && n.type !== 'trust_store' && n.role === 'intermediate'
            ? <button type="button" className="text-link" data-ca-go={n.name} onClick={() => openCa(n.name, { issuing: n.issuing })}>{n.name}</button>
            : <>{n.name}{n.role === 'anchor' && <> <span className="muted small">{t('inspector.cert.trustStore')}</span></>}</>}
        </li>
      ))}
      <li className="leaf"><Icon name="cert" /><span>{title}</span></li>
    </ol>
  )
}

function Validity({ cert }) {
  const { t } = useTranslation()
  const f = validityFacts(cert)
  const failure = useAcmeFailure(cert)
  const revoked = f.state === 'revoked'
  const expired = !revoked && f.days !== null && f.days < 0
  const big = revoked ? t('common.revoked') : f.days === null ? '—' : expired ? t('common.expired') : t('inspector.cert.days', { count: f.days })
  // Amber under 30 days, as the mockup draws it
  const warn = f.days !== null && f.days < 30
  return (
    <section>
      <h3 className="section-title">{t('inspector.cert.validity')}</h3>
      <div className="validity-head">
        <strong className={warn ? 'warn' : undefined}>{big}</strong>
        <span>{!revoked && !expired && f.days !== null ? t('inspector.cert.remaining') : ''}</span>
      </div>
      <div className={warn ? 'progress warn' : 'progress'} role="img" aria-label={t('inspector.cert.validityLeft', { percent: Math.round(f.ratio) })}>
        <span style={{ width: `${f.ratio}%` }} />
      </div>
      <div className="validity-dates">
        <span>{formatDate(f.from, { time: false })}</span>
        <span>{formatDate(f.to, { time: false })}</span>
      </div>
      {revoked ? <p className="mini-notice">{t('inspector.cert.revokedNotice')}</p>
        : f.short ? <p className="mini-notice"><Icon name="clock" />{t('inspector.cert.renewSoon', { count: f.days })}</p> : null}
      {failure && (
        <dl className="props last-failure" data-testid="acme-last-failure">
          <dt>{t('inspector.cert.lastFailure')}</dt>
          <dd>
            <strong>{failure.error_message}</strong>
            <br />
            <span className="muted">
              {[t('inspector.cert.order', { id: failure.id }), failure.primary_domain, failure.challenge_type?.toUpperCase(),
                failure.last_error_at && compactAgo(failure.last_error_at, t)].filter(Boolean).join(' · ')}
            </span>
          </dd>
        </dl>
      )}
    </section>
  )
}

function Identity({ cert, onOpenRelated }) {
  const { t } = useTranslation()
  const sans = sanLines(cert)
  const sig = cert.signature_algorithm ? signatureHashName(cert.signature_algorithm) : null
  const weakSig = /sha-?1|md5/i.test(cert.signature_algorithm || '')
  const template = cert.template_name
    ? (cert.template_overrides?.length
      ? `${cert.template_name} (${t('certificates.modifiedFromTemplate')}: ${cert.template_overrides.map((f) => (OVERRIDE_LABELS[f] ? t(OVERRIDE_LABELS[f]) : f)).join(', ')})`
      : cert.template_name)
    : null
  const relatedId = cert.related_certificate_id ?? null
  const otherRole = { classical: 'certificates.hybrid.rolePq', pq: 'certificates.hybrid.roleClassical' }[cert.hybrid_role]
  const grade = cert.compliance?.grade
  const none = <span className="muted">{t('inspector.cert.none')}</span>
  return (
    <section>
      <h3 className="section-title">{t('inspector.cert.identity')}</h3>
      <Props items={[
        [t('common.description'), cert.descr && cert.descr !== cert.common_name ? cert.descr : none],
        [t('inspector.cert.altName'), sans.length ? sans.map((s, i) => <Fragment key={i}>{i > 0 && <br />}{s}</Fragment>) : none],
        [t('common.keyAlgorithm'), certificateKeyLabel(cert, t) || '—'],
        [t('inspector.cert.signature'), <>{sig || '—'}{weakSig && <> <span className="warn"><Icon name="warning" />{t('inspector.cert.obsolete')}</span></>}</>],
        [t('inspector.cert.origin'), [sourceLabel(sourceOf(cert), t), template].filter(Boolean).join(' / ')],
        [t('inspector.cert.serial'), serialHex(cert.serial_number) || '—', 'mono'],
        // The product's own facts, after the mockup's
        [t('common.privateKey'), cert.has_private_key ? t('inspector.cert.keyHeld') : <span className="muted">{t('inspector.cert.keyNotHeld')}</span>],
        relatedId != null && [t('certificates.hybrid.relatedCertificate'), (
          <a className="text-link" href={`/certificates/${relatedId}`} aria-label={t('certificates.hybrid.openRelated', { id: relatedId })}
            onClick={onOpenRelated ? (e) => { e.preventDefault(); onOpenRelated(relatedId) } : undefined}>
            #{relatedId}{otherRole ? ` (${t(otherRole)})` : ''}
          </a>
        )],
        grade && [t('inspector.cert.compliance'), <><span className={`grade ${GRADE_TONES[grade] || 'bad'}`}>{grade}</span> <span className="muted">· {cert.compliance.score}/100</span></>],
      ]} />
    </section>
  )
}

function MoreDetails({ cert }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const row = (label, value, mono) => (value ? [label, value, mono ? 'mono' : undefined] : null)
  const breakdown = Object.entries(cert.compliance?.breakdown || {}).filter(([, v]) => v && v.score !== undefined)
  const scts = cert.ct_scts || []
  const id = `more-details-${cert.id}`
  return (
    <div className="advanced">
      <button type="button" className="advanced-toggle" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
        <Icon name={open ? 'down' : 'right'} /><span>{t('inspector.cert.moreDetails')}</span><small>{t('inspector.cert.moreDetailsHint')}</small>
      </button>
      <div className="advanced-panel" id={id} hidden={!open}>
        <section>
          <h3 className="section-title">{t('common.subject')}</h3>
          <Props items={[
            row(t('details.subjectDN'), cert.subject),
            row(t('details.issuerDN'), cert.issuer),
            row(t('details.certType'), certTypeLabel(cert.cert_type, t)),
            row(t('certificates.windowsProfile'), cert.windows_profile_id != null ? (cert.windows_profile_name || `#${cert.windows_profile_id}`) : null),
            row(t('common.validFrom'), cert.valid_from && formatDate(cert.valid_from, { time: true })),
            row(t('common.validUntil'), cert.valid_to && formatDate(cert.valid_to, { time: true })),
            row(t('details.revokedAt'), cert.revoked && cert.revoked_at && formatDate(cert.revoked_at, { time: true })),
            row(t('revocation.reasonLabel'), cert.revoked && (cert.revoke_reason ? t(`revocation.reasons.${cert.revoke_reason}`, cert.revoke_reason) : t('details.unspecified'))),
          ]} />
        </section>
        <section>
          <h3 className="section-title">{t('common.fingerprints')}</h3>
          <Props items={[
            row('SHA-1', cert.thumbprint_sha1, true),
            row('SHA-256', cert.thumbprint_sha256, true),
            row(t('certificates.ctScts'), scts.length ? scts.map((s) => s.log_url || '?').join(', ') : t('certificates.ctNoScts')),
          ]} />
        </section>
        {breakdown.length > 0 && (
          <section>
            <h3 className="section-title">{t('compliance.title')}</h3>
            <Props items={breakdown.map(([key, item]) => [t(`compliance.criteria.${key}`), `${item.score}/${item.max} · ${complianceReasonLabel(item.reason, t)}`])} />
          </section>
        )}
        <section>
          <h3 className="section-title">{t('details.metadata')}</h3>
          <Props items={[
            row(t('common.created'), cert.created_at && formatDate(cert.created_at)),
            row(t('details.createdBy'), originLabel(cert.created_by, SOURCES, t)),
            row(t('details.importedFrom'), originLabel(cert.imported_from, SOURCES, t)),
            row(t('details.referenceId'), cert.refid, true),
            row(t('details.caReference'), cert.caref, true),
          ]} />
        </section>
        {/* Deployment targets: the product's own panel, kept with its styles */}
        <div className="atl-out"><CertDeploySection certificate={cert} /></div>
      </div>
    </div>
  )
}

export function OverviewPanel({ cert, title, openCa, onOpenRelated }) {
  const { t } = useTranslation()
  return (
    <>
      <div className="detail-overview" data-testid="certificate-overview">
        <Validity cert={cert} />
        <Identity cert={cert} onOpenRelated={onOpenRelated} />
        <section className="overview-chain">
          <h3 className="section-title">{t('inspector.cert.chainOfTrust')}</h3>
          <MiniChain cert={cert} title={title} openCa={openCa} />
          {cert.chain_status?.status === 'incomplete' && (
            <p className="chain-cross warn"><Icon name="warning" /><span>{t('details.chainIncomplete')}</span></p>
          )}
        </section>
      </div>
      <MoreDetails cert={cert} />
    </>
  )
}
