/**
 * Overview of a certificate: validity (days left, band between the two dates,
 * what to do next), identity and key, the chain of trust as a small tree; three
 * columns under the list, one in a narrow dock. Rarer facts fold under More details.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Clock, Warning, ShieldCheck, TreeStructure, Certificate, CaretRight, Prohibit } from '@phosphor-icons/react'
import { formatDate, extractCN, cn } from '../../../lib/utils'
import { validityFacts, chainNodes, lastAcmeFailure, certificateKeyLabel, serialHex } from '../../../lib/certificateDetail'
import { relativeAgo } from '../../../lib/relativeTime'
import { signatureHashName } from '../../../lib/signatureName'
import { sourceLabel, sourceOf } from '../../../pages/certificates/certificateSources'
import { usePermission } from '../../../hooks'
import { acmeService } from '../../../services/acme.service'
import { CertDeploySection } from '../../deploy/CertDeploySection'

const GRADE_TONES = { 'A+': 'good', A: 'good', B: 'good', C: 'warn', D: 'warn', F: 'bad' }
const ACME_CLIENT_SOURCES = ['acme_client', 'letsencrypt']
const OVERRIDE_LABELS = { key_type: 'common.keyType', validity_days: 'common.validityPeriod', digest: 'common.digest' }

/** Subject alternative names, one per line: the parsed entries, else the stored list. */
export function sanLines(cert) {
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

function Validity({ cert }) {
  const { t } = useTranslation()
  const f = validityFacts(cert)
  const failure = useAcmeFailure(cert)
  const revoked = f.state === 'revoked'
  const expired = !revoked && f.days !== null && f.days < 0
  const big = revoked ? t('common.revoked') : f.days === null ? '—' : expired ? t('common.expired') : t('inspector.cert.days', { count: f.days })
  const tone = revoked || expired ? 'bad' : f.short ? 'warn' : ''
  return (
    <section aria-labelledby="ins-validity-title">
      <h3 id="ins-validity-title" className="ins-section-title">{t('inspector.cert.validity')}</h3>
      <div className="ins-validity-head">
        <strong className={cn(tone && `is-${tone}`)}>{big}</strong>
        <span>{!revoked && !expired && f.days !== null ? t('inspector.cert.remaining') : ''}</span>
      </div>
      <div className={cn('ins-progress', f.short && 'is-warn')} role="img"
        aria-label={t('inspector.cert.validityLeft', { percent: Math.round(f.ratio) })}>
        <span style={{ width: `${f.ratio}%` }} />
      </div>
      <div className="ins-dates">
        <span>{formatDate(f.from, { time: false })}</span>
        <span>{formatDate(f.to, { time: false })}</span>
      </div>
      {revoked ? (
        <p className="ins-notice is-bad">
          <Prohibit size={13} aria-hidden="true" />
          <span>
            {t('inspector.cert.revokedNotice')}
            {cert.revoked_at && <> {t('inspector.cert.revokedOn', {
              date: formatDate(cert.revoked_at, { time: false }),
              reason: cert.revoke_reason ? t(`revocation.reasons.${cert.revoke_reason}`, cert.revoke_reason) : t('details.unspecified'),
            })}</>}
          </span>
        </p>
      ) : f.short ? (
        <p className="ins-notice"><Clock size={13} aria-hidden="true" />{t('inspector.cert.renewSoon', { count: f.days })}</p>
      ) : expired ? (
        <p className="ins-notice is-bad"><Warning size={13} aria-hidden="true" />{t('inspector.cert.expiredNotice', { count: -f.days })}</p>
      ) : null}
      {failure && (
        <dl className="ins-props ins-failure" data-testid="acme-last-failure">
          <dt>{t('inspector.cert.lastFailure')}</dt>
          <dd>
            <strong>{failure.error_message}</strong>
            <br />
            <span className="ins-muted">
              {[t('inspector.cert.order', { id: failure.id }), failure.primary_domain, failure.challenge_type,
                failure.last_error_at && relativeAgo(failure.last_error_at, t)].filter(Boolean).join(' · ')}
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
  const keyName = certificateKeyLabel(cert, t)
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
  return (
    <section aria-labelledby="ins-identity-title">
      <h3 id="ins-identity-title" className="ins-section-title">{t('inspector.cert.identity')}</h3>
      <dl className="ins-props">
        <dt>{t('common.description')}</dt>
        <dd>{cert.descr && cert.descr !== cert.common_name ? cert.descr : <span className="ins-muted">{t('inspector.cert.none')}</span>}</dd>
        <dt>{t('inspector.cert.altName')}</dt>
        <dd>{sans.length ? sans.map((s, i) => <span key={i}>{i > 0 && <br />}{s}</span>) : <span className="ins-muted">{t('inspector.cert.none')}</span>}</dd>
        <dt>{t('common.keyAlgorithm')}</dt>
        <dd>{keyName || '—'}</dd>
        <dt>{t('inspector.cert.signature')}</dt>
        <dd>
          {sig || '—'}
          {weakSig && <span className="ins-grade is-warn"> <Warning size={12} aria-hidden="true" /> {t('inspector.cert.obsolete')}</span>}
        </dd>
        <dt>{t('inspector.cert.origin')}</dt>
        <dd>{[sourceLabel(sourceOf(cert), t), template].filter(Boolean).join(' / ')}</dd>
        <dt>{t('inspector.cert.serial')}</dt>
        <dd className="ins-mono" title={cert.serial_number || undefined}>{serialHex(cert.serial_number) || '—'}</dd>
        <dt>{t('common.privateKey')}</dt>
        <dd>{cert.has_private_key ? t('inspector.cert.keyHeld') : <span className="ins-muted">{t('inspector.cert.keyNotHeld')}</span>}</dd>
        {relatedId != null && (
          <>
            <dt>{t('certificates.hybrid.relatedCertificate')}</dt>
            <dd>
              <a className="ins-link" href={`/certificates/${relatedId}`} aria-label={t('certificates.hybrid.openRelated', { id: relatedId })}
                onClick={onOpenRelated ? (e) => { e.preventDefault(); onOpenRelated(relatedId) } : undefined}>
                #{relatedId}{otherRole ? ` (${t(otherRole)})` : ''}
              </a>
            </dd>
          </>
        )}
        {grade && (
          <>
            <dt>{t('inspector.cert.compliance')}</dt>
            <dd>
              <span className={cn('ins-grade', `is-${GRADE_TONES[grade] || 'bad'}`)}>{grade}</span>
              <span className="ins-muted"> · {cert.compliance.score}/100</span>
            </dd>
          </>
        )}
      </dl>
    </section>
  )
}

/** The chain as a small tree, anchor first, the certificate last. */
export function MiniChain({ cert, title, openCa }) {
  const { t } = useTranslation()
  const nodes = chainNodes(cert)
  const issuer = cert.issuer_name || extractCN(cert.issuer)
  const shown = nodes.length ? nodes : (issuer ? [{ name: issuer, role: 'intermediate', issuing: true }] : [])
  return (
    <ol className="ins-chain-mini">
      {shown.map((n, i) => (
        <li key={`${n.name}-${i}`}>
          {n.role === 'intermediate' ? <TreeStructure aria-hidden="true" /> : <ShieldCheck aria-hidden="true" />}
          {openCa && n.type !== 'trust_store' && n.role === 'intermediate'
            ? <button type="button" className="ins-link" onClick={() => openCa(n.name, { issuing: n.issuing })}>{n.name}</button>
            : <span>{n.name}</span>}
          {n.role === 'anchor' && <span className="ins-muted">{t('inspector.cert.trustStore')}</span>}
        </li>
      ))}
      <li className="is-leaf"><Certificate aria-hidden="true" /><span>{title}</span></li>
    </ol>
  )
}

function MoreDetails({ cert }) {
  const { t } = useTranslation()
  const row = (label, value, mono) => (value ? [<dt key={`${label}-t`}>{label}</dt>, <dd key={`${label}-d`} className={mono ? 'ins-mono' : undefined}>{value}</dd>] : null)
  const breakdown = Object.entries(cert.compliance?.breakdown || {}).filter(([, v]) => v && v.score !== undefined)
  const scts = cert.ct_scts || []
  return (
    <details className="ins-more">
      <summary><CaretRight size={12} aria-hidden="true" />{t('inspector.cert.moreDetails')}</summary>
      <div className="ins-more-grid">
        <section>
          <h3 className="ins-section-title">{t('common.subject')}</h3>
          <dl className="ins-props">
            {row(t('details.subjectDN'), cert.subject)}
            {row(t('details.issuerDN'), cert.issuer)}
            {row(t('details.certType'), cert.cert_type)}
            {row(t('certificates.windowsProfile'), cert.windows_profile_id != null ? (cert.windows_profile_name || `#${cert.windows_profile_id}`) : null)}
            {row(t('common.validFrom'), cert.valid_from && formatDate(cert.valid_from, { time: true }))}
            {row(t('common.validUntil'), cert.valid_to && formatDate(cert.valid_to, { time: true }))}
          </dl>
        </section>
        <section>
          <h3 className="ins-section-title">{t('common.fingerprints')}</h3>
          <dl className="ins-props">
            {row('SHA-1', cert.thumbprint_sha1, true)}
            {row('SHA-256', cert.thumbprint_sha256, true)}
            {row(t('certificates.ctScts'), scts.length ? scts.map((s) => s.log_url || '?').join(', ') : t('certificates.ctNoScts'))}
          </dl>
        </section>
        {breakdown.length > 0 && (
          <section>
            <h3 className="ins-section-title">{t('compliance.title')}</h3>
            <div className="ins-breakdown">
              {breakdown.map(([key, item]) => (
                <div key={key}>
                  <span className="ins-muted">{t(`compliance.criteria.${key}`)}</span>
                  <span>{item.score}/{item.max} · {t(`compliance.reasons.${item.reason}`, item.reason)}</span>
                </div>
              ))}
            </div>
          </section>
        )}
        <section>
          <h3 className="ins-section-title">{t('details.metadata')}</h3>
          <dl className="ins-props">
            {row(t('common.created'), cert.created_at && formatDate(cert.created_at))}
            {row(t('details.createdBy'), cert.created_by)}
            {row(t('details.importedFrom'), cert.imported_from)}
            {row(t('details.referenceId'), cert.refid, true)}
            {row(t('details.caReference'), cert.caref, true)}
          </dl>
        </section>
      </div>
      <CertDeploySection certificate={cert} />
    </details>
  )
}

export function CertificateOverview({ cert, title, columns, openCa, onOpenRelated }) {
  const { t } = useTranslation()
  return (
    <>
      <div className="ins-overview" data-columns={columns} data-testid="certificate-overview">
        <Validity cert={cert} />
        <Identity cert={cert} onOpenRelated={onOpenRelated} />
        <section aria-labelledby="ins-chain-title">
          <h3 id="ins-chain-title" className="ins-section-title">{t('inspector.cert.chainOfTrust')}</h3>
          <MiniChain cert={cert} title={title} openCa={openCa} />
          {cert.chain_status?.status === 'incomplete' && (
            <p className="ins-note is-warn"><Warning size={13} aria-hidden="true" />{t('details.chainIncomplete')}</p>
          )}
        </section>
      </div>
      <MoreDetails cert={cert} />
    </>
  )
}
