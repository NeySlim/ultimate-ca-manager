/**
 * The Aperçu panel of a certificate: the mockup's overviewDetail() (validity, identity and key, the
 * chain of trust as a small tree), then what the product shows in more, folded under « Plus de
 * détails » (the issue form's advanced toggle).
 */
import { Fragment, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon, Facts, CodeValue, RowAction } from '../../../components/atelier'
import { Breakable } from '../../../components/atelier/Breakable'
import { formatDate, extractCN } from '../../../lib/utils'
import { validityFacts, chainNodes, lastAcmeFailure, certificateKeyLabel, serialHex, certTypeLabel, originLabel, complianceReasonLabel } from '../../../lib/certificateDetail'
import { compactAgo } from '../../../lib/relativeTime'
import { signatureHashName } from '../../../lib/signatureName'
import { sourceLabel, sourceOf, SOURCE_LABEL_KEYS } from '../certificateSources'
import { usePermission } from '../../../hooks'
import { acmeService } from '../../../services/acme.service'
import { CertDeploySection } from '../../../components/deploy/CertDeploySection'
import { CertBadge } from '../CertBadge'
import { stateOf } from '../certState'
import { CommentDialog } from './CommentDialog'

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

// The role of a node in small under its name; the anchor of a trust store says where it is held
const ROLE_KEYS = { root: 'inspector.cert.chainRoleRoot', anchor: 'inspector.cert.chainRoleRoot', intermediate: 'inspector.cert.chainRoleIntermediate' }
const LAPSED = ['expired', 'revoked']

/**
 * The chain as a vertical tree, anchor first, the certificate last as the current node (the mockup's
 * miniChain()): each node its role in small, the product's authorities clickable, a lapsed certificate its state.
 */
function MiniChain({ cert, title, openCa }) {
  const { t } = useTranslation()
  const nodes = chainNodes(cert)
  const issuer = cert.issuer_name || extractCN(cert.issuer)
  const shown = nodes.length ? nodes : (issuer ? [{ name: issuer, role: 'intermediate', issuing: true }] : [])
  const role = (n) => [t(ROLE_KEYS[n.role]), n.role === 'anchor' && t('inspector.cert.trustStore')].filter(Boolean).join(' · ')
  return (
    <ol className="chain-mini">
      {shown.map((n, i) => (
        <li key={`${n.name}-${i}`} className="chain-node" data-role={n.role}>
          <span className="chain-mark"><Icon name={n.role === 'intermediate' ? 'branch' : 'shield'} /></span>
          <span className="chain-label">
            {openCa && n.type !== 'trust_store' && n.role === 'intermediate'
              ? <button type="button" className="text-link chain-name" data-ca-go={n.name} onClick={() => openCa(n.name, { issuing: n.issuing })}>{n.name}</button>
              : <span className="chain-name">{n.name}</span>}
            <span className="chain-meta"><small className="chain-role">{role(n)}</small></span>
          </span>
        </li>
      ))}
      <li className="chain-node leaf current" aria-current="true">
        <span className="chain-mark"><Icon name="cert" /></span>
        <span className="chain-label">
          <span className="chain-name">{title}</span>
          <span className="chain-meta">
            <small className="chain-role">{t('inspector.cert.chainRoleCurrent')}</small>
            {LAPSED.includes(stateOf(cert)) && <CertBadge cert={cert} t={t} />}
          </span>
        </span>
      </li>
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
        {/* Expired or revoked in the colour of its pill beside it; amber only for a near end */}
        <strong className={revoked || expired ? 'bad' : warn ? 'warn' : undefined}>{big}</strong>
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
        // The error is a sentence: a long row, the order, its domain and its age under it
        <Facts className="last-failure" data-testid="acme-last-failure" items={[{
          label: t('inspector.cert.lastFailure'), long: true, value: failure.error_message,
          sub: [t('inspector.cert.order', { id: failure.id }), failure.primary_domain, failure.challenge_type?.toUpperCase(),
            failure.last_error_at && compactAgo(failure.last_error_at, t)].filter(Boolean).join(' · '),
        }]} />
      )}
    </section>
  )
}

function Identity({ cert, onOpenRelated, onChanged, idPrefix = '' }) {
  const { t } = useTranslation()
  const { hasPermission } = usePermission()
  const [editing, setEditing] = useState(false)
  const canComment = hasPermission('write:certificates')
  // A detached window shows the same certificate as the dock: its ids carry the window's prefix
  const editId = `${idPrefix}cert-comment-edit-${cert.id}`
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
  const none = t('inspector.cert.none')
  const serial = serialHex(cert.serial_number)
  return (
    <section>
      <h3 className="section-title">{t('inspector.cert.identity')}</h3>
      <Facts items={[
        cert.descr && cert.descr !== cert.common_name ? [t('common.description'), cert.descr] : { label: t('common.description'), absent: none },
        // The product's comment (#454): plain text, its line breaks kept; a writer edits it in a dialog
        {
          label: t('certificates.comment'), product: true, long: !!cert.comment,
          ...(cert.comment ? { value: <span className="cert-comment">{cert.comment}</span> } : { absent: none }),
          action: canComment && (
            <RowAction id={editId} onClick={() => setEditing(true)}>{t(cert.comment ? 'certificates.editComment' : 'certificates.addComment')}</RowAction>
          ),
        },
        sans.length
          ? { label: t('inspector.cert.altName'), value: sans.map((s, i) => <Fragment key={i}>{i > 0 && <br />}<Breakable text={s} /></Fragment>) }
          : { label: t('inspector.cert.altName'), absent: none },
        [t('common.keyAlgorithm'), certificateKeyLabel(cert, t) || '—'],
        [t('inspector.cert.signature'), <>{sig || '—'}{weakSig && <> <span className="warn"><Icon name="warning" />{t('inspector.cert.obsolete')}</span></>}</>],
        [t('inspector.cert.origin'), [sourceLabel(sourceOf(cert), t), template].filter(Boolean).join(' / ')],
        // A serial longer than a short value goes under its term in a narrow panel
        serial ? { label: t('inspector.cert.serial'), value: serial, kind: 'hex', long: serial.length > 23 } : [t('inspector.cert.serial'), '—'],
        // The product's own facts, after the mockup's
        cert.has_private_key ? [t('common.privateKey'), t('inspector.cert.keyHeld')] : { label: t('common.privateKey'), absent: t('inspector.cert.keyNotHeld') },
        relatedId != null && [t('certificates.hybrid.relatedCertificate'), (
          <a className="text-link" href={`/certificates/${relatedId}`} aria-label={t('certificates.hybrid.openRelated', { id: relatedId })}
            onClick={onOpenRelated ? (e) => { e.preventDefault(); onOpenRelated(relatedId) } : undefined}>
            #{relatedId}{otherRole ? ` (${t(otherRole)})` : ''}
          </a>
        )],
        grade && [t('inspector.cert.compliance'), <><span className={`grade ${GRADE_TONES[grade] || 'bad'}`}>{grade}</span> <span className="muted">· {cert.compliance.score}/100</span></>],
      ]} />
      {editing && (
        <CommentDialog cert={cert} returnTo={editId} idPrefix={idPrefix} onClose={() => setEditing(false)} onSaved={(updated) => {
          setEditing(false)
          onChanged?.({ ...cert, ...updated })
          window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'certificate', id: cert.id } }))
        }} />
      )}
    </section>
  )
}

function MoreDetails({ cert }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  // A fact the certificate has, else no row; a DN wraps after its separators on a long row
  const row = (label, value) => (value ? [label, value] : null)
  const dn = (label, value) => (value ? { label, value: <Breakable text={value} />, long: true } : null)
  const ref = (label, value) => (value ? { label, value, kind: 'hex' } : null)
  const breakdown = Object.entries(cert.compliance?.breakdown || {}).filter(([, v]) => v && v.score !== undefined)
  const scts = cert.ct_scts || []
  const id = `more-details-${cert.id}`
  return (
    <div className={open ? 'advanced open' : 'advanced'}>
      <button type="button" className="advanced-toggle" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
        <Icon name={open ? 'down' : 'right'} /><span>{t('inspector.cert.moreDetails')}</span><small>{t('inspector.cert.moreDetailsHint')}</small>
      </button>
      <div className="advanced-panel" id={id} hidden={!open}>
        <section>
          <h3 className="section-title">{t('common.subject')}</h3>
          <Facts items={[
            dn(t('details.subjectDN'), cert.subject),
            dn(t('details.issuerDN'), cert.issuer),
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
          <Facts items={[
            cert.thumbprint_sha1 && { label: 'SHA-1', value: cert.thumbprint_sha1, kind: 'hex', long: true },
            cert.thumbprint_sha256 && { label: 'SHA-256', value: cert.thumbprint_sha256, kind: 'hex', long: true },
            // Each CT log a URL copied whole; none submitted, a grey sentence
            scts.length
              ? { label: t('certificates.ctScts'), long: true, value: scts.map((s, i) => (
                <Fragment key={i}>{i > 0 && <br />}{s.log_url ? <CodeValue value={s.log_url} kind="url" label={t('certificates.ctScts')} /> : '?'}</Fragment>
              )) }
              : { label: t('certificates.ctScts'), absent: t('certificates.ctNoScts') },
          ]} />
        </section>
        {breakdown.length > 0 && (
          <section>
            <h3 className="section-title">{t('compliance.title')}</h3>
            <Facts items={breakdown.map(([key, item]) => ({ label: t(`compliance.criteria.${key}`), value: `${item.score}/${item.max}`, sub: complianceReasonLabel(item.reason, t) }))} />
          </section>
        )}
        <section>
          <h3 className="section-title">{t('details.metadata')}</h3>
          <Facts items={[
            row(t('common.created'), cert.created_at && formatDate(cert.created_at)),
            row(t('details.createdBy'), originLabel(cert.created_by, SOURCES, t)),
            row(t('details.importedFrom'), originLabel(cert.imported_from, SOURCES, t)),
            ref(t('details.referenceId'), cert.refid),
            ref(t('details.caReference'), cert.caref),
          ]} />
        </section>
        {/* Deployment targets: the product's own section, drawn as the others */}
        <CertDeploySection certificate={cert} />
      </div>
    </div>
  )
}

export function OverviewPanel({ cert, title, openCa, onOpenRelated, onChanged, idPrefix }) {
  const { t } = useTranslation()
  return (
    <>
      <div className="detail-overview" data-testid="certificate-overview">
        <Validity cert={cert} />
        <Identity cert={cert} onOpenRelated={onOpenRelated} onChanged={onChanged} idPrefix={idPrefix} />
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
