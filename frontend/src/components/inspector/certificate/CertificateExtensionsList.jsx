/**
 * X.509 extensions of a certificate: one entry per extension, its name and identifier on
 * the left, its value on the right.
 */
import { useTranslation } from 'react-i18next'
import { Copy, Check } from '@phosphor-icons/react'
import { useClipboard } from '../../../hooks/useClipboard'
import { truncateHex } from '../../../lib/customExtensions'
import { alternativeNames } from './certificateFacts'

const OIDS = {
  subject_alt_names: '2.5.29.17',
  basic_constraints: '2.5.29.19',
  key_usage: '2.5.29.15',
  extended_key_usage: '2.5.29.37',
  subject_key_identifier: '2.5.29.14',
  authority_key_identifier: '2.5.29.35',
  crl_distribution_points: '2.5.29.31',
  authority_info_access: '1.3.6.1.5.5.7.1.1',
  certificate_policies: '2.5.29.32',
  name_constraints: '2.5.29.30',
  qc_statements: '1.3.6.1.5.5.7.1.3',
  signed_certificate_timestamps: '1.3.6.1.4.1.11129.2.4.2',
}
const SAN_PREFIX = { Email: 'RFC822' }

const lines = (values) => values.filter(Boolean).map((v, i) => <span key={i}>{v}</span>)

function qcLines(qc, t) {
  const limit = qc.limit_value
  return [
    qc.compliance && t('details.ext.qc.compliance'),
    qc.sscd && t('details.ext.qc.sscd'),
    qc.type && `${t('details.ext.qc.type')}: ${[].concat(qc.type).join(', ')}`,
    qc.semantics && `${t('details.ext.qc.semantics')}: ${qc.semantics}`,
    qc.cc_legislation?.length > 0 && `${t('details.ext.qc.ccLegislation')}: ${qc.cc_legislation.join(', ')}`,
    qc.retention_period != null && `${t('details.ext.qc.retention')}: ${t('details.ext.qc.retentionYears', { count: qc.retention_period })}`,
    limit && `${t('details.ext.qc.limit')}: ${limit.amount}e${limit.exponent} ${limit.currency}`,
    ...(qc.pds || []).map((p) => `${t('details.ext.qc.pds')} ${p.language}: ${p.url}`),
  ]
}

export function CertificateExtensionsList({ certificate }) {
  const { t } = useTranslation()
  const { copy, isCopied } = useClipboard()
  const ext = certificate.extensions || {}
  const names = alternativeNames(certificate)
  const rows = []
  const add = (key, label, value, critical) => rows.push({ key, label, oid: OIDS[key] || key, critical: !!critical, value })

  if (names.length) {
    add('subject_alt_names', t('details.subjectAltNames'),
      lines(names.map((n) => (n.type ? `${SAN_PREFIX[n.type] || n.type}: ${n.value}` : n.value))), ext.subject_alt_names?.critical)
  }
  if (ext.basic_constraints) {
    const bc = ext.basic_constraints
    add('basic_constraints', t('details.ext.basicConstraints'), lines([
      `CA: ${bc.ca ? 'TRUE' : 'FALSE'}`,
      bc.path_length !== null && bc.path_length !== undefined && `Path Length: ${bc.path_length}`,
    ]), bc.critical)
  }
  if (ext.key_usage) add('key_usage', t('details.ext.keyUsage'), (ext.key_usage.usages || []).join(', '), ext.key_usage.critical)
  if (ext.extended_key_usage) {
    add('extended_key_usage', t('details.ext.extKeyUsage'),
      lines((ext.extended_key_usage.usages || []).map((u) => u.name || u.oid)), ext.extended_key_usage.critical)
  }
  if (ext.subject_key_identifier) add('subject_key_identifier', t('details.ext.ski'), <span className="insp-mono">{ext.subject_key_identifier.value}</span>)
  if (ext.authority_key_identifier) add('authority_key_identifier', t('details.ext.aki'), <span className="insp-mono">{ext.authority_key_identifier.key_id}</span>)
  if (ext.authority_info_access) {
    const aia = ext.authority_info_access
    add('authority_info_access', t('details.ext.aia'), lines([
      ...(aia.ocsp || []).map((url) => `OCSP: ${url}`),
      ...(aia.ca_issuers || []).map((url) => `CA Issuers: ${url}`),
    ]))
  }
  if (ext.crl_distribution_points?.urls?.length > 0) add('crl_distribution_points', t('details.ext.crlDP'), lines(ext.crl_distribution_points.urls))
  if (ext.certificate_policies?.policies?.length > 0) {
    add('certificate_policies', t('details.ext.policies'), lines(ext.certificate_policies.policies.map((p) =>
      [p.name || p.oid, ...(p.qualifiers || []).map((q) => q.value)].join(' '))))
  }
  if (ext.qc_statements) add('qc_statements', t('details.ext.qcStatements'), <span data-testid="qc-statements">{lines(qcLines(ext.qc_statements, t))}</span>, ext.qc_statements.critical)
  if (ext.name_constraints) {
    const nc = ext.name_constraints
    add('name_constraints', t('details.ext.nameConstraints'), lines([
      nc.permitted && `${t('inspector.cert.ext.permitted')}: ${nc.permitted.join(', ')}`,
      nc.excluded && `${t('inspector.cert.ext.excluded')}: ${nc.excluded.join(', ')}`,
    ]), nc.critical)
  }
  if (ext.signed_certificate_timestamps) {
    add('signed_certificate_timestamps', t('details.ext.sct'), t('inspector.cert.ext.present'), ext.signed_certificate_timestamps.critical)
  }
  for (const other of ext.other_extensions || []) {
    rows.push({
      key: `other-${other.oid}`, label: other.name || t('details.ext.otherExtensions'), oid: other.oid, critical: !!other.critical,
      value: other.value_hex ? (
        <>
          <span className="insp-mono" title={other.value_hex}>{truncateHex(other.value_hex)}</span>
          <button type="button" className="insp-copy" onClick={() => copy(other.value_hex, other.oid)}
            aria-label={t('details.ext.copyValue')} title={isCopied(other.oid) ? t('common.copied') : t('details.ext.copyValue')}>
            {isCopied(other.oid) ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
          </button>
        </>
      ) : '—',
    })
  }

  if (!rows.length) return <p className="insp-foot">{t('inspector.cert.ext.none')}</p>
  return (
    <dl className="insp-ext" data-testid="cert-extensions">
      {rows.map((row) => (
        <div key={row.key}>
          <dt>
            {row.label}
            <small className="insp-mono">{row.oid}{row.critical ? ` · ${t('inspector.cert.ext.critical')}` : ''}</small>
          </dt>
          <dd>{row.value}</dd>
        </div>
      ))}
    </dl>
  )
}
