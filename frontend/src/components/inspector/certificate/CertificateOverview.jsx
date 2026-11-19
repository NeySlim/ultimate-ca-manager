/**
 * Overview of a certificate: validity, identity and key, chain of trust, in three columns
 * (one when the inspector is narrow), then what the record holds beyond them.
 */
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Clock, Warning, Certificate, ShieldCheck, TreeStructure, Vault, Copy, Check, LinkSimple, Prohibit, CheckCircle } from '@phosphor-icons/react'
import { cn, formatDate, formatSerialNumberHex, certificateNames, extractCN, isOnHold } from '../../../lib/utils'
import { keyAlgorithmLabel } from '../../../lib/keyAlgorithms'
import { relativeAgo } from '../../../lib/relativeTime'
import { useClipboard } from '../../../hooks/useClipboard'
import { PostQuantumBadge } from '../../PostQuantumBadge'
import { CertDeploySection } from '../../deploy/CertDeploySection'
import { sourceOf, sourceLabel } from '../../../pages/certificates/certificateSources'
import { chainPath, chainSentence } from './chainPath'
import { useLastFailure } from './useLastFailure'
import { alternativeNames, validityFacts } from './certificateFacts'

const SHOWN_NAMES = 6
const WEAK_HASH = /(^|[^a-z0-9])(sha-?1|md5|md2)([^0-9]|$)/i
const HYBRID_ROLE_KEYS = { classical: 'certificates.hybrid.roleClassical', pq: 'certificates.hybrid.rolePq' }
const OVERRIDE_LABEL_KEYS = { key_type: 'common.keyType', validity_days: 'common.validityPeriod', digest: 'common.digest' }
const CERT_TYPE_KEYS = {
  server_cert: 'server', client_cert: 'client', code_signing: 'codeSigning', email_cert: 'emailSmime', ca_cert: 'ca',
  intermediate_ca: 'intermediateCA', root_ca: 'rootCA', self_signed: 'selfSigned', timestamping: 'timestamping',
}

function CopyButton({ value, name }) {
  const { t } = useTranslation()
  const { copy, isCopied } = useClipboard()
  if (!value) return null
  return (
    <button type="button" className="insp-copy" onClick={() => copy(value, name)}
      aria-label={t('inspector.copyOf', { name })} title={isCopied(name) ? t('common.copied') : t('common.copy')}>
      {isCopied(name) ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
    </button>
  )
}

function LastFailure({ certificate }) {
  const { t } = useTranslation()
  const failure = useLastFailure(certificate)
  if (!failure) return null
  return (
    <dl className="insp-props insp-failure" data-testid="last-failure">
      <dt>{t('inspector.failure.title')}</dt>
      <dd>
        <strong>{t(`overview.kind.${failure.kind}`)}</strong>
        <br />
        {t(`overview.cause.${failure.kind}`)}
        <br />
        <span className="insp-muted">
          {[failure.label, relativeAgo(failure.at, t)].filter(Boolean).join(' · ')}
        </span>
        {failure.href && <>{' '}<Link className="insp-link" to={failure.href}>{t('inspector.failure.open')}</Link></>}
      </dd>
    </dl>
  )
}

export function CertificateOverview({ certificate, layout = 'columns', onShowExtensions, onOpenIssuer, onOpenRelated }) {
  const { t } = useTranslation()
  const cert = certificate
  const name = cert.cn || cert.common_name || extractCN(cert.subject) || ''
  const { days, share, state, tone } = validityFacts(cert)
  const onHold = isOnHold(cert)
  const names = alternativeNames(cert)
  const chain = chainPath(cert)
  const sentence = chainSentence(chain, t)
  const { subtitle } = certificateNames(cert)
  const keyName = keyAlgorithmLabel(cert.key_algorithm || cert.key_type, t, cert.security_level)
  const serialHex = formatSerialNumberHex(cert.serial_number)
  const relatedId = cert.related_certificate_id ?? null
  const otherRole = HYBRID_ROLE_KEYS[{ classical: 'pq', pq: 'classical' }[cert.hybrid_role]]
  const overrides = (cert.template_overrides || []).map((f) => (OVERRIDE_LABEL_KEYS[f] ? t(OVERRIDE_LABEL_KEYS[f]) : f))
  const template = cert.template_name
    ? (overrides.length ? t('inspector.cert.templateModified', { name: cert.template_name, fields: overrides.join(', ') }) : cert.template_name)
    : t('inspector.cert.noTemplate')
  const reason = cert.revoke_reason ? t(`revocation.reasons.${cert.revoke_reason}`, cert.revoke_reason) : t('details.unspecified')
  const grade = cert.compliance
  const subject = [
    [t('common.organization'), cert.organization], [t('common.orgUnit'), cert.organizational_unit],
    [t('common.country'), cert.country], [t('common.state'), cert.state], [t('common.locality'), cert.locality],
    [t('common.email'), cert.email],
  ].filter(([, v]) => v)
  const certType = cert.cert_type
    ? (CERT_TYPE_KEYS[cert.cert_type] ? t(`certificates.sourceTypes.${CERT_TYPE_KEYS[cert.cert_type]}`) : cert.cert_type.replace(/_/g, ' '))
    : null

  return (
    <>
      <div className="insp-overview" data-testid="cert-overview" data-layout={layout}>
        <section>
          <h3 className="insp-h3">{t('inspector.cert.validity')}</h3>
          <div className="insp-validity">
            <strong className={cn(tone && `is-${tone}`)}>
              {state === 'revoked' ? t('common.revoked')
                : state === 'expired' ? t('common.expired')
                  : days === null ? t('inspector.cert.noExpiry')
                    : t('inspector.cert.days', { count: days })}
            </strong>
            <span>{state !== 'revoked' && state !== 'expired' && days !== null ? t('inspector.cert.remaining') : ''}</span>
          </div>
          <div className={cn('insp-progress', tone && `is-${tone}`)} role="img"
            aria-label={t('inspector.cert.validityShare', { percent: Math.round(share ?? 0) })}>
            <span style={{ width: `${state === 'revoked' ? 0 : share ?? 0}%` }} />
          </div>
          <div className="insp-dates">
            <span>{formatDate(cert.valid_from, { time: false })}</span>
            <span>{formatDate(cert.valid_to, { time: false })}</span>
          </div>
          {state === 'expiring' && days !== null && (
            <p className="insp-mini"><Clock aria-hidden="true" />{t('inspector.cert.renewSoon', { count: days })}</p>
          )}
          {state === 'revoked' && (
            <>
              <p className="insp-mini is-muted">
                <Prohibit aria-hidden="true" />{t(onHold ? 'inspector.cert.onHoldNotice' : 'inspector.cert.revokedNotice')}
              </p>
              <p className="insp-mini is-muted">
                {t('inspector.cert.revokedOn', { date: formatDate(cert.revoked_at), reason })}
              </p>
            </>
          )}
          <LastFailure certificate={cert} />
        </section>

        <section>
          <h3 className="insp-h3">{t('inspector.cert.identity')}</h3>
          <dl className="insp-props">
            <dt>{t('common.description')}</dt>
            <dd>{subtitle || <span className="insp-muted">{t('inspector.cert.noDescription')}</span>}</dd>
            <dt>{t('inspector.cert.altNames')}</dt>
            <dd className="insp-lines">
              {names.length === 0 && <span className="insp-muted">{t('inspector.cert.none')}</span>}
              {names.slice(0, SHOWN_NAMES).map((n, i) => <span key={i} title={n.type || undefined}>{n.value}</span>)}
              {names.length > SHOWN_NAMES && (
                <span>
                  <button type="button" className="insp-link" onClick={onShowExtensions}>
                    {t('inspector.cert.moreNames', { count: names.length - SHOWN_NAMES })}
                  </button>
                </span>
              )}
            </dd>
            <dt>{t('common.keyAlgorithm')}</dt>
            <dd className="insp-inline">
              {keyName || '—'}
              <PostQuantumBadge postQuantum={cert.post_quantum} algorithm={cert.key_algorithm || cert.key_type} />
            </dd>
            <dt>{t('common.signature')}</dt>
            <dd>
              {cert.signature_algorithm || '—'}
              {WEAK_HASH.test(cert.signature_algorithm || '') && (
                <>{' '}<span className="insp-inline insp-warn"><Warning aria-hidden="true" />{t('inspector.cert.weakHash')}</span></>
              )}
            </dd>
            <dt>{t('inspector.cert.sourceTemplate')}</dt>
            <dd>{sourceLabel(sourceOf(cert), t)} / {template}</dd>
            <dt>{t('inspector.cert.serial')}</dt>
            <dd className="insp-mono">
              {serialHex || cert.serial_number || '—'}
              <CopyButton value={serialHex || cert.serial_number} name={t('inspector.cert.serial')} />
            </dd>
            <dt>{t('common.privateKey')}</dt>
            <dd className="insp-inline">
              {cert.has_private_key
                ? <><Vault aria-hidden="true" />{cert.private_key_location ? t('inspector.cert.keyHeldIn', { location: cert.private_key_location }) : t('inspector.cert.keyHeld')}</>
                : <span className="insp-muted">{t('inspector.cert.keyNotHeld')}</span>}
            </dd>
            {relatedId != null && (
              <>
                <dt>{t('certificates.hybrid.relatedCertificate')}</dt>
                <dd>
                  <a className="insp-link" href={`/certificates/${relatedId}`} data-testid="hybrid-related-link"
                    aria-label={t('certificates.hybrid.openRelated', { id: relatedId })}
                    onClick={onOpenRelated ? (e) => { e.preventDefault(); onOpenRelated(relatedId) } : undefined}>
                    <span className="insp-inline"><LinkSimple aria-hidden="true" />#{relatedId}{otherRole ? ` (${t(otherRole)})` : ''}</span>
                  </a>
                </dd>
              </>
            )}
            {cert.windows_profile_id != null && (
              <>
                <dt>{t('certificates.windowsProfile')}</dt>
                <dd>{cert.windows_profile_name || `#${cert.windows_profile_id}`}</dd>
              </>
            )}
            {grade && (
              <>
                <dt>{t('compliance.grade')}</dt>
                <dd>{grade.grade} · {grade.score}/100</dd>
              </>
            )}
          </dl>
        </section>

        <section>
          <h3 className="insp-h3">{t('inspector.cert.trustChain')}</h3>
          <ol className="insp-chain-mini" data-testid="chain-mini">
            {chain.path.map((node, i) => (
              <li key={i}>
                {node.root || node.kind === 'store' ? <ShieldCheck aria-hidden="true" /> : <TreeStructure aria-hidden="true" />}
                {node.issuing && onOpenIssuer
                  ? <button type="button" className="insp-link" onClick={onOpenIssuer}>{node.name}</button>
                  : <span>{node.name}</span>}
                {node.kind === 'store' && <span className="insp-muted">{t('inspector.cert.inTrustStore')}</span>}
                {node.kind === 'unknown' && <span className="insp-muted">{t('inspector.cert.notHeld')}</span>}
              </li>
            ))}
            <li className="is-leaf"><Certificate aria-hidden="true" /><span>{name}</span></li>
          </ol>
          {sentence && (
            <p className={cn('insp-chain-note', `is-${sentence.tone}`)}>
              {sentence.tone === 'warn' ? <Warning aria-hidden="true" /> : sentence.tone === 'good' ? <CheckCircle aria-hidden="true" /> : <LinkSimple aria-hidden="true" />}
              <span>{sentence.text}</span>
            </p>
          )}
        </section>
      </div>

      <div className="insp-more-zone" data-testid="cert-more">
        <section>
          <h3 className="insp-h3">{t('common.subject')}</h3>
          <dl className="insp-props">
            <dt>{t('common.commonName')}</dt>
            <dd>{name || '—'}</dd>
            {subject.map(([label, value]) => [<dt key={`${label}-t`}>{label}</dt>, <dd key={`${label}-d`}>{value}</dd>])}
            <dt>{t('inspector.cert.subjectDn')}</dt>
            <dd className="insp-mono">{cert.subject || '—'}</dd>
            {certType && <><dt>{t('details.certType')}</dt><dd>{certType}</dd></>}
          </dl>
        </section>
        <section>
          <h3 className="insp-h3">{t('inspector.cert.record')}</h3>
          <dl className="insp-props">
            <dt>SHA-256</dt>
            <dd className="insp-mono">{cert.thumbprint_sha256 || '—'}<CopyButton value={cert.thumbprint_sha256} name="SHA-256" /></dd>
            <dt>SHA-1</dt>
            <dd className="insp-mono">{cert.thumbprint_sha1 || '—'}<CopyButton value={cert.thumbprint_sha1} name="SHA-1" /></dd>
            <dt>{t('inspector.cert.serialDecimal')}</dt>
            <dd className="insp-mono">{cert.serial_number || '—'}</dd>
            <dt>{t('common.created')}</dt>
            <dd>{formatDate(cert.created_at)}{cert.created_by ? ` · ${cert.created_by}` : ''}</dd>
            {cert.imported_from && <><dt>{t('details.importedFrom')}</dt><dd>{cert.imported_from}</dd></>}
            <dt>{t('details.referenceId')}</dt>
            <dd className="insp-mono">{cert.refid || '—'}<CopyButton value={cert.refid} name={t('details.referenceId')} /></dd>
          </dl>
        </section>
        {(grade || cert.ct_scts?.length > 0) && (
          <section>
            {grade && (
              <>
                <h3 className="insp-h3">{t('compliance.title')}</h3>
                <div className="insp-grade"><strong>{grade.grade}</strong><span className="insp-muted">{grade.score}/100</span></div>
                {grade.breakdown && (
                  <dl className="insp-props" data-testid="compliance-breakdown">
                    {Object.entries(grade.breakdown).filter(([, item]) => item && item.score !== undefined).map(([key, item]) => [
                      <dt key={`${key}-t`}>{t(`compliance.criteria.${key}`)}</dt>,
                      <dd key={`${key}-d`}>
                        {item.score}/{item.max}
                        {item.reason && <span className="insp-muted"> · {t(`compliance.reasons.${item.reason}`, item.reason)}</span>}
                      </dd>,
                    ])}
                  </dl>
                )}
              </>
            )}
            {cert.ct_scts?.length > 0 && (
              <>
                <h3 className="insp-h3" style={grade ? { marginTop: 18 } : undefined}>{t('certificates.ctScts')}</h3>
                <dl className="insp-props">
                  {cert.ct_scts.map((sct, i) => [
                    <dt key={`${i}-t`}>#{i + 1}</dt>,
                    <dd key={`${i}-d`} className="insp-mono">{sct.log_url || '—'}{sct.timestamp ? ` · ${sct.timestamp}` : ''}</dd>,
                  ])}
                </dl>
              </>
            )}
          </section>
        )}
        <section className="is-wide">
          <CertDeploySection certificate={cert} />
        </section>
      </div>
    </>
  )
}
