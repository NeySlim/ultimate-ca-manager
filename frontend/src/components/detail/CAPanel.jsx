/**
 * CAPanel: pure presentation of one Certificate Authority. Actions and their
 * modals live in hooks/useEntityActions; `section` picks one named part.
 * The rule covers direct imports: self-loading field components (see
 * README.md) are known exceptions until the inspector lot.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { formatDate as formatDateUtil, daysRemaining } from '../../lib/utils'
import { daysSinceExpiry, expiryBucket, hasExpiry } from '../../lib/expiry'
import {
  Certificate,
  Key,
  Lock,
  Clock,
  Calendar,
  Copy,
  CheckCircle,
  ShieldCheck,
  Globe,
  Envelope,
  Buildings,
  MapPin,
  Hash,
  Fingerprint,
  TreeStructure,
  Link,
} from '@phosphor-icons/react'
import { Badge, CATypeIcon } from '../Badge'
import { Button } from '../Button'
import { CompactSection, CompactGrid, CompactField } from '../DetailCard'
import { CertificateExtensions } from './CertificateExtensions'
import { showSection } from './sections'
import { CACrlSection } from '../cas/CACrlSection'
import { CrossCertificatesSection } from '../cas/CrossCertificatesSection'
import { ChainUsageSection } from '../cas/ChainUsageSection'
import { SignatureSchemeField } from '../cas/SignatureSchemeField'
import { ComplianceProfileField } from '../cas/ComplianceProfileField'
import { IssuanceVisibilityField } from '../cas/IssuanceVisibilityField'
import { ParentConfirmationSection } from '../cas/ParentConfirmationSection'
import { cn } from '../../lib/utils'
import { useClipboard } from '../../hooks/useClipboard'
import { holdsNoKey, needsKeyImport } from '../../lib/caSelection'
import { caKeyParts, keyAlgorithmLabel } from '../../lib/keyAlgorithms'
import { PostQuantumBadge } from '../PostQuantumBadge'

// Format date helper - delegates to shared util
function formatDate(dateStr) {
  if (!dateStr) return '-'
  return formatDateUtil(dateStr)
}

export function CAPanel({
  ca,
  // Imports the missing key; rendered inside the "no key" banner when given
  onImportKey,
  onCaChanged,
  canWriteCas = false,
  canAttachProfile = false,
  section = 'all',
  showPem = true,
  embedded = false,
}) {

  const { t } = useTranslation()
  const [showFullPem, setShowFullPem] = useState(false)
  const { copy: copyPem, isCopied } = useClipboard()
  const pemCopied = isCopied('pem')

  if (!ca) return null

  // The CA serializer has no days_remaining (only Certificate.to_dict does), so
  // `ca.days_remaining` was undefined: every comparison below was false, the CA
  // could never read as expiring, and the badge further down interpolated an
  // undefined count. Derive it from valid_to, which the serializer does send,
  // flooring the way the server floors its own days_remaining.
  const caDaysRemaining = daysRemaining(ca.valid_to)

  // Determine status
  const getStatus = () => {
    if (ca.pending) return 'pending'
    if (ca.revoked || ca.status === 'Revoked') return 'revoked'
    if (ca.offline) return 'offline'
    if (ca.status === 'Expired') return 'expired'
    if (expiryBucket(caDaysRemaining) === 'expiring') return 'expiring'
    return 'valid'
  }

  const status = getStatus()
  const { family: keyFamily, spec: keySpec } = caKeyParts(ca.key_type)
  const on = (...names) => showSection(section, ...names)
  const statusConfig = {
    valid: { variant: 'success', label: t('common.active') },
    expiring: { variant: 'warning', label: t('common.detailsExpiring') },
    expired: { variant: 'danger', label: t('common.expired') },
    revoked: { variant: 'danger', label: t('common.revoked') },
    pending: { variant: 'warning', label: t('cas.awaitingCertificate') },
    offline: { variant: 'warning', label: t('cas.offline') },
  }
  // Cross-signed count (#400) and the HSM that holds the key
  const keyBadges = (size) => (<>
    {ca.cross_certificate_count > 0 && (
      <Badge variant="info" size={size} data-testid="cross-badge">
        {t('crossCerts.badge', { count: ca.cross_certificate_count })}
      </Badge>
    )}
    {ca.uses_hsm && (
      <Badge variant="info" size={size} title={[ca.hsm_provider_name, ca.hsm_key_label].filter(Boolean).join(' / ')}>
        {t('cas.detail.hsmBacked')}
      </Badge>
    )}
  </>)

  return (
    <div className={cn("space-y-3 sm:space-y-4 p-3 sm:p-4", embedded && "space-y-3 p-3")}>
      {on('overview') && (<>
      {!embedded && <>
      {/* Header with badges and actions */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <CATypeIcon isRoot={ca.is_root} size="lg" />
            <h3 className="text-base font-semibold text-text-primary truncate">
              {ca.common_name || ca.descr}
            </h3>
            <Badge variant={ca.is_root ? 'warning' : 'info'}>
              {ca.is_root ? t('common.rootCA') : t('common.intermediate')}
            </Badge>
            <Badge variant={statusConfig[status].variant}>
              {statusConfig[status].label}
            </Badge>
            {keyBadges(undefined)}
            <PostQuantumBadge postQuantum={ca.post_quantum} algorithm={ca.key_type} />
          </div>
          {ca.organization && (
            <p className="text-xs text-text-secondary mt-1 pl-9">{ca.organization}</p>
          )}
        </div>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-4 gap-2">
        <div className="bg-tertiary-op50 rounded-lg p-2 text-center">
          <Key size={16} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-2xs text-text-tertiary">{t('common.keyType')}</div>
          <div className="text-xs font-medium text-text-primary">{keyAlgorithmLabel(ca.key_type, t, ca.security_level) || t('common.na')}</div>
        </div>
        <div className="bg-tertiary-op50 rounded-lg p-2 text-center">
          <Lock size={16} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-2xs text-text-tertiary">{t('common.privateKey')}</div>
          <div className="text-xs font-medium text-text-primary">
            {ca.has_private_key ? t('details.available') : t('common.none')}
          </div>
        </div>
        <div className="bg-tertiary-op50 rounded-lg p-2 text-center">
          <ShieldCheck size={16} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-2xs text-text-tertiary">{t('common.signature')}</div>
          <div className="text-xs font-medium text-text-primary">{ca.signature_algorithm || ca.hash_algorithm || t('common.na')}</div>
        </div>
        <div className="bg-tertiary-op50 rounded-lg p-2 text-center">
          <Certificate size={16} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-2xs text-text-tertiary">{t('common.certificates')}</div>
          <div className="text-xs font-medium text-text-primary">{ca.certs || 0}</div>
        </div>
      </div>

      {/* Days Remaining Indicator */}
      {/* Computed from `valid_to`, which the CA payload does carry: reading
          `ca.days_remaining` rendered "undefined days remaining". */}
      {hasExpiry(caDaysRemaining) && (
        <div className={cn(
          "flex items-center gap-2 px-3 py-2 rounded-lg text-xs",
          caDaysRemaining <= 0 && "bg-status-danger-op10 text-status-danger",
          caDaysRemaining > 0 && caDaysRemaining <= 30 && "bg-status-warning-op10 text-status-warning",
          caDaysRemaining > 30 && caDaysRemaining <= 90 && "bg-status-info-op10 text-status-info",
          caDaysRemaining > 90 && "bg-status-success-op10 text-status-success"
        )}>
          <Clock size={14} />
          {caDaysRemaining <= 0 ? (
            <span>{t('details.expiredDaysAgo', { count: daysSinceExpiry(caDaysRemaining) })}</span>
          ) : (
            <span>{t('details.daysRemaining', { count: caDaysRemaining })}</span>
          )}
        </div>
      )}
      </>}
      </>)}
      {on('overview') && (<>
      {/* Embedded: compact status bar */}
      {embedded && (
        <div className="flex items-center gap-2 flex-wrap px-3 py-2 rounded-lg border border-border bg-tertiary-op30">
          <Badge variant={ca.is_root ? 'warning' : 'info'} size="sm">
            {ca.is_root ? t('common.rootCA') : t('common.intermediate')}
          </Badge>
          <Badge variant={statusConfig[status].variant} size="sm">
            {statusConfig[status].label}
          </Badge>
          {keyBadges('sm')}
          <PostQuantumBadge postQuantum={ca.post_quantum} algorithm={ca.key_type} />
          <span className="text-2xs text-text-tertiary">•</span>
          <span className="text-2xs text-text-secondary">{keyAlgorithmLabel(ca.key_type, t, ca.security_level) || t('common.na')}</span>
          <span className="text-2xs text-text-tertiary">•</span>
          <span className="text-2xs text-text-secondary">{ca.certs || 0} {t('common.certificatesShort')}</span>
        </div>
      )}
      </>)}
      {on('overview') && (<>
      {/* Awaiting the signed certificate (external-CSR mode, #298) */}
      {ca.pending && (
        <div className="rounded-lg px-3 py-2 bg-status-warning-op20 border border-status-warning-op40 text-xs">
          <div className="font-medium text-status-warning">{t('cas.awaitingCertificate')}</div>
          <p className="text-2xs text-text-secondary mt-1">{t('cas.awaitingBannerText')}</p>
        </div>
      )}

      {ca.offline && (
        <div className="rounded-lg px-3 py-2 bg-status-warning-op20 border border-status-warning-op40 text-xs font-medium text-status-warning">
          {t('cas.offline')}
        </div>
      )}

      {/* Revoked by the parent CA (#343) */}
      {ca.revoked && (
        <div className="rounded-lg px-3 py-2 bg-status-danger-op20 border border-status-danger-op40 text-xs text-text-secondary">
          {t('cas.revokedBanner', {
            date: ca.revoked_at ? formatDate(ca.revoked_at) : '-',
            reason: t(`revocation.reasons.${ca.revoke_reason || 'unspecified'}`),
          })}
        </div>
      )}
      </>)}
      {on('overview') && (<>
      {/* A CA above this one is revoked (#343) */}
      {ca.revoked_in_chain && !ca.revoked && (
        <div className="rounded-lg px-3 py-2 bg-status-danger-op15 border border-status-danger-op40 text-xs text-text-secondary">
          {t('cas.chainRevokedBanner')}
        </div>
      )}
      {/* Parent whose signature cannot be verified here: proposed, or confirmed by hand */}
      <ParentConfirmationSection ca={ca} canWrite={canWriteCas} onChanged={onCaChanged} />
      </>)}
      {on('overview') && (<>
      {/* No key: a warning when it was expected (#348), a plain note for a root imported without it (#426) */}
      {holdsNoKey(ca) && (
        <div className={`rounded-lg px-3 py-2 border text-xs text-text-secondary flex items-start gap-2 flex-wrap ${
          needsKeyImport(ca) ? 'bg-status-warning-op15 border-status-warning-op40' : 'bg-tertiary-40 border-border'}`}>
          <span className="flex-1 min-w-[12rem]">{t(needsKeyImport(ca) ? 'cas.certificateOnlyBanner' : 'cas.noPrivateKeyBanner')}</span>
          {onImportKey && (
            <Button type="button" size="xs" variant="secondary" onClick={onImportKey}>
              <Key size={12} /> {t('cas.importPrivateKey')}
            </Button>
          )}
        </div>
      )}
      </>)}
      {on('chain') && (<>
      {/* Cross-certificates and chain usage */}
      <CrossCertificatesSection ca={ca} canWrite={canWriteCas} />
      <ChainUsageSection ca={ca} />
      </>)}
      {on('overview') && (<>
      {/* Subject Information */}
      <CompactSection title={t('common.subject')} icon={Globe} iconClass="icon-bg-blue">
        <CompactGrid>
          <CompactField icon={Globe} label={t('common.commonName')} value={ca.common_name} />
          <CompactField autoIcon="country" label={t('common.country')} value={ca.country} />
          <CompactField autoIcon="state" label={t('common.state')} value={ca.state} />
          <CompactField icon={MapPin} label={t('common.locality')} value={ca.locality} />
          <CompactField icon={Buildings} label={t('common.organization')} value={ca.organization} />
          <CompactField autoIcon="orgUnit" label={t('common.orgUnit')} value={ca.organizational_unit} />
          <CompactField icon={Envelope} label={t('common.email')} value={ca.email} colSpan={2} />
        </CompactGrid>
      </CompactSection>
      </>)}
      {on('overview', 'chain') && (<>
      {/* Issuer (if intermediate) */}
      {!ca.is_root && ca.issuer && (
        <CompactSection title={t('common.issuer')} icon={TreeStructure} iconClass="icon-bg-orange">
          <CompactGrid cols={1}>
            <CompactField icon={TreeStructure} label={t('details.issuerDN')} value={ca.issuer} />
          </CompactGrid>
        </CompactSection>
      )}
      </>)}
      {on('overview') && (<>
      {/* Validity Period */}
      <CompactSection title={t('common.validity')} icon={Calendar} iconClass="icon-bg-green">
        <CompactGrid>
          <CompactField icon={Calendar} label={t('common.validFrom')} value={formatDate(ca.valid_from)} />
          <CompactField icon={Calendar} label={t('common.validUntil')} value={formatDate(ca.valid_to)} />
        </CompactGrid>
      </CompactSection>
      </>)}
      {on('overview') && (<>
      {/* Technical Details */}
      <CompactSection title={t('common.technicalDetails')} icon={Key} iconClass="icon-bg-purple">
        <CompactGrid>
          <CompactField icon={Hash} label={t('common.serial')} value={ca.serial_number} mono copyable />
          <CompactField autoIcon="algorithm" label={t('common.algorithm')} value={keyAlgorithmLabel(keyFamily, t, ca.security_level) || '-'} />
          {keySpec && <CompactField autoIcon="keySize" label={t('common.keySize')} value={keySpec} />}
          <CompactField autoIcon="signatureAlgorithm" label={t('common.signatureAlgorithm')} value={ca.signature_algorithm || ca.hash_algorithm} />
          <SignatureSchemeField ca={ca} canWrite={canWriteCas} onChanged={onCaChanged} />
          <ComplianceProfileField ca={ca} canWrite={canWriteCas} canAttach={canAttachProfile} onChanged={onCaChanged} />
          <IssuanceVisibilityField ca={ca} canWrite={canWriteCas} onChanged={onCaChanged} />
          {ca.uses_hsm && (
            <>
              <CompactField label={t('cas.create.hsmProvider')} value={ca.hsm_provider_name || '-'} />
              <CompactField label={t('cas.detail.hsmKey')} value={ca.hsm_key_label || '-'} mono />
            </>
          )}
          <CompactField autoIcon="subjectDN" label={t('details.subjectDN')} value={ca.subject} mono colSpan={2} />
        </CompactGrid>
      </CompactSection>
      </>)}
      {on('overview') && (<>
      {/* RFC 5280 Constraints */}
      {(ca.path_length !== null && ca.path_length !== undefined || ca.name_constraints_permitted?.length || ca.name_constraints_excluded?.length || ca.policy_constraints_require !== null || ca.inhibit_any_policy !== null || ca.sia_enabled) && (
        <CompactSection title={t('cas.rfc5280Constraints')} icon={ShieldCheck} iconClass="icon-bg-amber" collapsible defaultOpen={false}>
          <CompactGrid cols={1}>
            {(ca.path_length !== null && ca.path_length !== undefined) && (
              <CompactField icon={TreeStructure} label={t('cas.pathLength')} value={ca.path_length === 0 ? t('cas.pathLengthLeafOnly') : String(ca.path_length)} />
            )}
            {ca.name_constraints_permitted?.length > 0 && (
              <CompactField icon={ShieldCheck} label={t('cas.nameConstraintsPermitted')} value={ca.name_constraints_permitted.map(c => `${c.type}:${c.value}`).join(', ')} mono />
            )}
            {ca.name_constraints_excluded?.length > 0 && (
              <CompactField icon={ShieldCheck} label={t('cas.nameConstraintsExcluded')} value={ca.name_constraints_excluded.map(c => `${c.type}:${c.value}`).join(', ')} mono />
            )}
            {ca.policy_constraints_require !== null && ca.policy_constraints_require !== undefined && (
              <CompactField icon={ShieldCheck} label={t('cas.policyConstraintsRequire')} value={String(ca.policy_constraints_require)} />
            )}
            {ca.policy_constraints_inhibit !== null && ca.policy_constraints_inhibit !== undefined && (
              <CompactField icon={ShieldCheck} label={t('cas.policyConstraintsInhibit')} value={String(ca.policy_constraints_inhibit)} />
            )}
            {ca.inhibit_any_policy !== null && ca.inhibit_any_policy !== undefined && (
              <CompactField icon={ShieldCheck} label={t('cas.inhibitAnyPolicy')} value={String(ca.inhibit_any_policy)} />
            )}
            {ca.sia_enabled && ca.sia_urls?.length > 0 && (
              <CompactField icon={Link} label={t('cas.siaUrls')} value={ca.sia_urls.join(', ')} mono />
            )}
          </CompactGrid>
        </CompactSection>
      )}
      </>)}
      {on('overview') && (<>
      {/* CRL/OCSP Configuration */}
      {(ca.cdp_enabled || ca.ocsp_enabled) && (
        <CompactSection title={t('details.revocationConfig')} icon={Link} iconClass="icon-bg-cyan">
          <CompactGrid cols={1}>
            {ca.cdp_enabled && (
              <CompactField icon={Link} label={t('details.crlDistPoint')} value={ca.cdp_url} mono />
            )}
            {ca.ocsp_enabled && (
              <CompactField icon={Link} label={t('details.ocspUrl')} value={ca.ocsp_url} mono />
            )}
          </CompactGrid>
        </CompactSection>
      )}
      </>)}
      {on('overview') && (<>
      {/* Revocation list — key-less/offline CA served from an external CRL (#302) */}
      <CACrlSection ca={ca} />
      </>)}
      {on('extensions') && (<>
      {/* X.509 Extensions */}
      <CertificateExtensions extensions={ca.extensions} defaultOpen={false} />
      </>)}
      {on('overview') && (<>
      {/* Fingerprints */}
      <CompactSection title={t('common.fingerprints')} icon={Fingerprint} iconClass="icon-bg-gray" collapsible defaultOpen={false}>
        <CompactGrid cols={1}>
          <CompactField icon={Fingerprint} label="SHA-256" value={ca.thumbprint_sha256} mono copyable />
          <CompactField icon={Fingerprint} label="SHA-1" value={ca.thumbprint_sha1} mono copyable />
        </CompactGrid>
      </CompactSection>
      </>)}
      {on('pem') && (<>
      {/* PEM */}
      {showPem && ca.pem && (
        <CompactSection title={t('details.pemCertificate')} icon={Certificate} iconClass="icon-bg-green" collapsible defaultOpen={false}>
          <div className="relative">
            <pre className={cn(
              "text-2xs font-mono text-text-secondary bg-tertiary-op50 p-2 rounded overflow-x-auto",
              !showFullPem && "max-h-24 overflow-hidden"
            )}>
              {ca.pem}
            </pre>
            {!showFullPem && ca.pem.length > 500 && (
              <div className="absolute bottom-0 left-0 right-0 h-8 bg-gradient-to-t from-bg-primary to-transparent pointer-events-none" />
            )}
          </div>
          <div className="flex gap-2 mt-2">
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={(e) => {
                e.stopPropagation()
                setShowFullPem(!showFullPem)
              }}
            >
              {showFullPem ? t('details.showLess') : t('details.showFull')}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={(e) => {
                e.stopPropagation()
                copyPem(ca.pem, 'pem')
              }}
            >
              {pemCopied ? <CheckCircle size={14} /> : <Copy size={14} />}
              {pemCopied ? t('common.copied') : t('details.copyPem')}
            </Button>
          </div>
        </CompactSection>
      )}
      </>)}
      {on('overview') && (<>
      {/* Metadata */}
      <CompactSection title={t('details.metadata')} collapsible defaultOpen={false}>
        <CompactGrid>
          <CompactField autoIcon="createdAt" label={t('common.created')} value={formatDate(ca.created_at)} />
          <CompactField autoIcon="createdBy" label={t('details.createdBy')} value={ca.created_by} />
          <CompactField autoIcon="importedFrom" label={t('details.importedFrom')} value={ca.imported_from} colSpan={2} />
        </CompactGrid>
      </CompactSection>
      </>)}
    </div>
  )
}
