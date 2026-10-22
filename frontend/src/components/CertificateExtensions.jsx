/**
 * CertificateExtensions — Shared X.509 extension display component.
 * Used by CertificateDetails, CADetails, and DiscoveryPage.
 */
import { useTranslation } from 'react-i18next'
import { ShieldCheck } from '@phosphor-icons/react'
import { Badge } from './Badge'
import { CompactSection } from './DetailCard'

const SAN_COLORS = {
  DNS: 'primary', IP: 'warning', Email: 'teal', URI: 'cyan',
  UPN: 'violet', DirName: 'orange', RegisteredID: 'secondary'
}

export function CertificateExtensions({ extensions, defaultOpen = true }) {
  const { t } = useTranslation()

  if (!extensions || Object.keys(extensions).length === 0) return null

  // Filter out subject_alt_names since it's displayed separately
  const hasNonSanExtensions = Object.keys(extensions).some(k => k !== 'subject_alt_names')
  if (!hasNonSanExtensions) return null

  return (
    <CompactSection title={t('details.extensions')} icon={ShieldCheck} iconClass="icon-bg-indigo" collapsible defaultOpen={defaultOpen}>
      <div className="space-y-3">
        {/* Basic Constraints */}
        {extensions.basic_constraints && (
          <div className="space-y-1">
            <div className="text-xs font-semibold text-text-primary flex items-center gap-1.5">
              {t('details.ext.basicConstraints')}
              {extensions.basic_constraints.critical && <Badge variant="danger" size="sm">Critical</Badge>}
            </div>
            <div className="flex gap-2 text-xs">
              <Badge variant={extensions.basic_constraints.ca ? 'warning' : 'secondary'} size="sm">
                CA: {extensions.basic_constraints.ca ? 'TRUE' : 'FALSE'}
              </Badge>
              {extensions.basic_constraints.path_length !== null && extensions.basic_constraints.path_length !== undefined && (
                <Badge variant="secondary" size="sm">
                  Path Length: {extensions.basic_constraints.path_length}
                </Badge>
              )}
            </div>
          </div>
        )}

        {/* Key Usage */}
        {extensions.key_usage && (
          <div className="space-y-1">
            <div className="text-xs font-semibold text-text-primary flex items-center gap-1.5">
              {t('details.ext.keyUsage')}
              {extensions.key_usage.critical && <Badge variant="danger" size="sm">Critical</Badge>}
            </div>
            <div className="flex flex-wrap gap-1">
              {extensions.key_usage.usages.map(u => (
                <Badge key={u} variant="primary" size="sm">{u}</Badge>
              ))}
            </div>
          </div>
        )}

        {/* Extended Key Usage */}
        {extensions.extended_key_usage && (
          <div className="space-y-1">
            <div className="text-xs font-semibold text-text-primary flex items-center gap-1.5">
              {t('details.ext.extKeyUsage')}
              {extensions.extended_key_usage.critical && <Badge variant="danger" size="sm">Critical</Badge>}
            </div>
            <div className="flex flex-wrap gap-1">
              {extensions.extended_key_usage.usages.map(u => (
                <Badge key={u.oid} variant="teal" size="sm" title={u.oid}>{u.name}</Badge>
              ))}
            </div>
          </div>
        )}

        {/* Subject Key Identifier */}
        {extensions.subject_key_identifier && (
          <div className="space-y-1">
            <div className="text-xs font-semibold text-text-primary">{t('details.ext.ski')}</div>
            <div className="text-2xs font-mono text-text-secondary break-all">{extensions.subject_key_identifier.value}</div>
          </div>
        )}

        {/* Authority Key Identifier */}
        {extensions.authority_key_identifier && (
          <div className="space-y-1">
            <div className="text-xs font-semibold text-text-primary">{t('details.ext.aki')}</div>
            <div className="text-2xs font-mono text-text-secondary break-all">{extensions.authority_key_identifier.key_id}</div>
          </div>
        )}

        {/* CRL Distribution Points */}
        {extensions.crl_distribution_points?.urls?.length > 0 && (
          <div className="space-y-1">
            <div className="text-xs font-semibold text-text-primary">{t('details.ext.crlDP')}</div>
            {extensions.crl_distribution_points.urls.map((url, i) => (
              <div key={i} className="text-2xs font-mono text-accent-primary break-all">{url}</div>
            ))}
          </div>
        )}

        {/* Authority Information Access */}
        {extensions.authority_info_access && (
          <div className="space-y-1">
            <div className="text-xs font-semibold text-text-primary">{t('details.ext.aia')}</div>
            {extensions.authority_info_access.ocsp?.map((url, i) => (
              <div key={`ocsp-${i}`} className="flex items-start gap-2 text-2xs">
                <Badge variant="secondary" size="sm" className="shrink-0">OCSP</Badge>
                <span className="font-mono text-accent-primary break-all">{url}</span>
              </div>
            ))}
            {extensions.authority_info_access.ca_issuers?.map((url, i) => (
              <div key={`ca-${i}`} className="flex items-start gap-2 text-2xs">
                <Badge variant="secondary" size="sm" className="shrink-0">CA Issuers</Badge>
                <span className="font-mono text-accent-primary break-all">{url}</span>
              </div>
            ))}
          </div>
        )}

        {/* Certificate Policies */}
        {extensions.certificate_policies?.policies?.length > 0 && (
          <div className="space-y-1">
            <div className="text-xs font-semibold text-text-primary">{t('details.ext.policies')}</div>
            {extensions.certificate_policies.policies.map((p, i) => (
              <div key={i} className="text-2xs font-mono text-text-secondary">
                {p.name || p.oid}
                {p.qualifiers?.map((q, j) => (
                  <span key={j} className="ml-2 text-accent-primary">{q.value}</span>
                ))}
              </div>
            ))}
          </div>
        )}

        {/* Qualified Certificate Statements (RFC 3739, ETSI EN 319 412-5) */}
        {extensions.qc_statements && <QcStatements qc={extensions.qc_statements} />}

        {/* Name Constraints */}
        {extensions.name_constraints && (
          <div className="space-y-1">
            <div className="text-xs font-semibold text-text-primary flex items-center gap-1.5">
              {t('details.ext.nameConstraints')}
              {extensions.name_constraints.critical && <Badge variant="danger" size="sm">Critical</Badge>}
            </div>
            {extensions.name_constraints.permitted && (
              <div className="text-2xs"><span className="text-status-success font-medium">Permitted:</span> {extensions.name_constraints.permitted.join(', ')}</div>
            )}
            {extensions.name_constraints.excluded && (
              <div className="text-2xs"><span className="text-status-danger font-medium">Excluded:</span> {extensions.name_constraints.excluded.join(', ')}</div>
            )}
          </div>
        )}

        {/* Signed Certificate Timestamps (SCT) */}
        {extensions.signed_certificate_timestamps && (
          <div className="space-y-1">
            <div className="text-xs font-semibold text-text-primary flex items-center gap-1.5">
              {t('details.ext.sct')}
              {extensions.signed_certificate_timestamps.critical && <Badge variant="danger" size="sm">Critical</Badge>}
            </div>
            <Badge variant="teal" size="sm">Present</Badge>
          </div>
        )}
      </div>
    </CompactSection>
  )
}

function QcStatements({ qc }) {
  const { t } = useTranslation()
  const lim = qc.limit_value
  return (
    <div className="space-y-1" data-testid="qc-statements">
      <div className="text-xs font-semibold text-text-primary flex items-center gap-1.5">
        {t('details.ext.qcStatements')}
        {qc.critical && <Badge variant="danger" size="sm">Critical</Badge>}
      </div>
      <div className="flex flex-wrap gap-1">
        {qc.compliance && <Badge variant="success" size="sm">{t('details.ext.qc.compliance')}</Badge>}
        {qc.sscd && <Badge variant="success" size="sm">{t('details.ext.qc.sscd')}</Badge>}
        {qc.type && <Badge variant="teal" size="sm">{t('details.ext.qc.type')}: {qc.type}</Badge>}
        {qc.semantics && <Badge variant="secondary" size="sm">{t('details.ext.qc.semantics')}: {qc.semantics}</Badge>}
      </div>
      {qc.cc_legislation?.length > 0 && (
        <div className="text-2xs"><span className="font-medium">{t('details.ext.qc.ccLegislation')}:</span> {qc.cc_legislation.join(', ')}</div>
      )}
      {qc.retention_period != null && (
        <div className="text-2xs"><span className="font-medium">{t('details.ext.qc.retention')}:</span> {t('details.ext.qc.retentionYears', { count: qc.retention_period })}</div>
      )}
      {lim && (
        <div className="text-2xs font-mono"><span className="font-medium font-sans">{t('details.ext.qc.limit')}:</span> {lim.amount}e{lim.exponent} {lim.currency}</div>
      )}
      {qc.pds?.map((p, i) => (
        <div key={i} className="flex items-start gap-2 text-2xs">
          <Badge variant="secondary" size="sm" className="shrink-0">{t('details.ext.qc.pds')} {p.language}</Badge>
          <span className="font-mono text-accent-primary break-all">{p.url}</span>
        </div>
      ))}
    </div>
  )
}

export function SubjectAltNames({ extensions, sanCombined }) {
  const { t } = useTranslation()
  
  const hasEntries = extensions?.subject_alt_names?.entries?.length > 0
  if (!hasEntries && !sanCombined) return null

  return (
    <CompactSection title={t('details.subjectAltNames')} icon={ShieldCheck} iconClass="icon-bg-teal">
      {hasEntries ? (
        <div className="flex flex-wrap gap-1">
          {extensions.subject_alt_names.entries.map((entry, i) => (
            <Badge key={i} variant={SAN_COLORS[entry.type] || 'secondary'} size="sm">
              <span className="font-semibold mr-1">{entry.type}:</span>{entry.value}
            </Badge>
          ))}
        </div>
      ) : (
        <div className="flex flex-wrap gap-1">
          {sanCombined.split(',').map((s, i) => (
            <Badge key={i} variant="secondary" size="sm">{s.trim()}</Badge>
          ))}
        </div>
      )}
    </CompactSection>
  )
}
