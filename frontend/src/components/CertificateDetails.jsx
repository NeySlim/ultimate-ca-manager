/**
 * CertificateDetails Component
 * 
 * Reusable component for displaying certificate details.
 * Can be used in modals, slide-overs, or standalone pages.
 * Uses global Compact components for consistent styling.
 * 
 * Usage:
 *   <CertificateDetails 
 *     certificate={cert} 
 *     onExport={handleExport}
 *     onRevoke={handleRevoke}
 *     onDelete={handleDelete}
 *     canWrite={true}
 *     canDelete={true}
 *   />
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { 
  Certificate, 
  Key, 
  Lock, 
  Clock, 
  Calendar,
  Download, 
  X, 
  Trash,
  Copy,
  CheckCircle,
  Warning,
  ShieldCheck,
  Globe,
  Envelope,
  Buildings,
  MapPin,
  Hash,
  Fingerprint,
  ArrowsClockwise,
  UploadSimple,
  LinkSimple
} from '@phosphor-icons/react'
import { Badge } from './Badge'
import { Button } from './Button'
import { CompactSection, CompactGrid, CompactField } from './DetailCard'
import { cn } from '../lib/utils'

// Format date helper
function formatDate(dateStr, format = 'full') {
  if (!dateStr) return '—'
  try {
    const date = new Date(dateStr)
    if (format === 'short') {
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
    }
    return date.toLocaleDateString('en-US', { 
      year: 'numeric', 
      month: 'long', 
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch {
    return dateStr
  }
}

const CERT_TYPE_LABELS = {
  server_cert: 'Server',
  client_cert: 'Client',
  code_signing: 'Code Signing',
  email_cert: 'Email / S/MIME',
  ca_cert: 'CA',
  intermediate_ca: 'Intermediate CA',
  root_ca: 'Root CA',
  self_signed: 'Self-Signed',
}

function formatCertType(type) {
  if (!type) return null
  return CERT_TYPE_LABELS[type] || type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

// Expiry indicator - uses t from parent
function ExpiryIndicator({ daysRemaining, validTo, t }) {
  let color = 'text-status-success'
  let bgColor = 'bg-status-success/10'
  let label = `${daysRemaining}d`
  
  if (daysRemaining <= 0) {
    color = 'text-status-danger'
    bgColor = 'bg-status-danger/10'
    label = t('common.expired')
  } else if (daysRemaining <= 7) {
    color = 'text-status-danger'
    bgColor = 'bg-status-danger/10'
    label = t('details.daysLeft', { count: daysRemaining })
  } else if (daysRemaining <= 30) {
    color = 'text-status-warning'
    bgColor = 'bg-status-warning/10'
    label = t('details.daysLeft', { count: daysRemaining })
  } else {
    label = t('details.daysLeft', { count: daysRemaining })
  }
  
  return (
    <div className={cn("flex items-center gap-2 px-2 sm:px-3 py-1.5 sm:py-2 rounded-lg", bgColor)}>
      <Clock size={14} className={cn("sm:w-4 sm:h-4", color)} />
      <div>
        <div className={cn("text-xs sm:text-sm font-medium", color)}>{label}</div>
        <div className="text-2xs sm:text-xs text-text-tertiary">{t('common.expires')}: {formatDate(validTo, 'short')}</div>
      </div>
    </div>
  )
}

export function CertificateDetails({ 
  certificate,
  onExport,
  onRevoke,
  onDelete,
  onRenew,
  onUploadKey,
  onAddToTrustStore,
  canWrite = false,
  canDelete = false,
  compact = false,
  showActions = true,
  showPem = true,
  embedded = false,
}) {
  const { t } = useTranslation()
  const [pemCopied, setPemCopied] = useState(false)
  const [showFullPem, setShowFullPem] = useState(false)
  
  if (!certificate) return null
  
  const cert = certificate
  const status = cert.revoked ? 'revoked' : (cert.status || 'valid')
  
  // Status badge config
  const statusConfig = {
    valid: { variant: 'success', label: t('common.valid') },
    expiring: { variant: 'warning', label: t('common.detailsExpiring') },
    expired: { variant: 'danger', label: t('common.expired') },
    revoked: { variant: 'danger', label: t('common.revoked') }
  }
  
  // Source badge config
  const sourceConfig = {
    acme: { variant: 'info', label: 'ACME' },
    scep: { variant: 'warning', label: 'SCEP' },
    import: { variant: 'default', label: t('common.imported') },
    csr: { variant: 'default', label: t('details.fromCSR') },
    manual: { variant: 'default', label: t('common.manual') }
  }
  
  const statusBadge = statusConfig[status] || statusConfig.valid
  const sourceBadge = sourceConfig[cert.source] || null
  
  return (
    <div className={cn("space-y-3 sm:space-y-4 p-3 sm:p-4", compact && "space-y-2 p-2", embedded && "space-y-2 p-0")}>
      {!embedded && <>
      {/* Header */}
      <div className="flex items-start gap-2 sm:gap-3">
        <div className={cn(
          "p-2 sm:p-2.5 rounded-lg shrink-0",
          cert.revoked ? "bg-status-danger/10" : "bg-accent-primary/10"
        )}>
          <Certificate size={20} className={cn("sm:w-6 sm:h-6", cert.revoked ? "text-status-danger" : "text-accent-primary")} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
            <h3 className="text-base sm:text-lg font-semibold text-text-primary truncate">
              {cert.cn || cert.common_name || cert.descr || 'Certificate'}
            </h3>
            <Badge variant={statusBadge.variant} size="sm">{statusBadge.label}</Badge>
            {sourceBadge && <Badge variant={sourceBadge.variant} size="sm">{sourceBadge.label}</Badge>}
          </div>
          <p className="text-2xs sm:text-xs text-text-tertiary truncate mt-0.5">{cert.subject}</p>
        </div>
      </div>
      
      {/* Expiry indicator */}
      {!cert.revoked && cert.days_remaining !== undefined && (
        <ExpiryIndicator daysRemaining={cert.days_remaining} validTo={cert.valid_to} t={t} />
      )}
      
      {/* Quick stats */}
      <div className="grid grid-cols-3 sm:grid-cols-3 gap-2">
        <div className="bg-bg-tertiary/50 rounded-lg p-2 sm:p-2.5 text-center">
          <Key size={14} className="mx-auto text-text-tertiary mb-0.5 sm:mb-1 sm:w-4 sm:h-4" />
          <div className="text-2xs sm:text-xs font-medium text-text-primary">{cert.key_algorithm || 'RSA'}</div>
          <div className="text-3xs sm:text-2xs text-text-tertiary hidden sm:block">{cert.key_size ? `${cert.key_size} bits` : '—'}</div>
        </div>
        <div className="bg-bg-tertiary/50 rounded-lg p-2 sm:p-2.5 text-center">
          <Lock size={14} className={cn("mx-auto mb-0.5 sm:mb-1 sm:w-4 sm:h-4", cert.has_private_key ? "text-status-success" : "text-text-tertiary")} />
          <div className="text-2xs sm:text-xs font-medium text-text-primary">{cert.has_private_key ? t('common.hasKey') : t('details.noKey')}</div>
          <div className="text-3xs sm:text-2xs text-text-tertiary hidden sm:block">
            {cert.has_private_key ? (cert.private_key_location || '—') : '—'}
          </div>
        </div>
        <div className="bg-bg-tertiary/50 rounded-lg p-2 sm:p-2.5 text-center">
          <ShieldCheck size={14} className="mx-auto text-text-tertiary mb-0.5 sm:mb-1 sm:w-4 sm:h-4" />
          <div className="text-2xs sm:text-xs font-medium text-text-primary truncate">{cert.signature_algorithm?.split('-')[0] || '—'}</div>
          <div className="text-3xs sm:text-2xs text-text-tertiary hidden sm:block">{t('common.signature')}</div>
        </div>
      </div>
      
      {/* Actions - compact on mobile */}
      {showActions && (
        <div className="flex flex-wrap gap-1.5 sm:gap-2">
          {/* Export buttons grouped */}
          {onExport && (
            <div className="flex flex-wrap gap-1 p-1 rounded-lg bg-bg-tertiary/50">
              <Button size="xs" variant="ghost" onClick={() => onExport('pem')} className="!px-2 hover:bg-bg-secondary">
                <Download size={12} /> PEM
              </Button>
              <Button size="xs" variant="ghost" onClick={() => onExport('der')} className="!px-2 hover:bg-bg-secondary">
                <Download size={12} /> DER
              </Button>
              <Button size="xs" variant="ghost" onClick={() => onExport('pkcs7')} className="!px-2 hover:bg-bg-secondary">
                <Download size={12} /> P7B
              </Button>
              {cert.has_private_key && (
                <>
                  <Button size="xs" variant="ghost" onClick={() => onExport('pkcs12')} className="!px-2 hover:bg-bg-secondary">
                    <Download size={12} /> P12
                  </Button>
                  <Button size="xs" variant="ghost" onClick={() => onExport('pfx')} className="!px-2 hover:bg-bg-secondary">
                    <Download size={12} /> PFX
                  </Button>
                </>
              )}
            </div>
          )}
          {/* Action buttons */}
          {onRenew && canWrite && !cert.revoked && (
            <Button size="xs" variant="secondary" onClick={onRenew} title={t('certificates.renewCertificate')}>
              <ArrowsClockwise size={14} />
            </Button>
          )}
          {onRevoke && canWrite && !cert.revoked && (
            <Button size="xs" variant="warning-soft" onClick={onRevoke} title={t('certificates.revokeCertificate')}>
              <X size={14} />
            </Button>
          )}
          {onDelete && canDelete && (
            <Button size="xs" variant="danger-soft" onClick={onDelete} title={t('common.delete')}>
              <Trash size={14} />
            </Button>
          )}
        </div>
      )}
      </>}

      {/* Embedded: compact status bar */}
      {embedded && (
        <div className="flex items-center gap-2 flex-wrap px-1 pb-1">
          <Badge variant={statusBadge.variant} size="sm">{statusBadge.label}</Badge>
          {sourceBadge && <Badge variant={sourceBadge.variant} size="sm">{sourceBadge.label}</Badge>}
          {cert.days_remaining !== undefined && !cert.revoked && (
            <span className={cn(
              "text-2xs font-medium",
              cert.days_remaining <= 0 ? "text-status-danger" :
              cert.days_remaining <= 30 ? "text-status-warning" : "text-text-tertiary"
            )}>
              {cert.days_remaining <= 0 ? t('common.expired') : t('details.daysShort', { count: cert.days_remaining })}
            </span>
          )}
          <span className="text-2xs text-text-tertiary">•</span>
          <span className="text-2xs text-text-secondary">{cert.key_algorithm || 'RSA'}{cert.key_size ? ` ${cert.key_size}` : ''}</span>
          <span className="text-2xs text-text-tertiary">•</span>
          <span className={cn("text-2xs", cert.has_private_key ? "text-status-success" : "text-text-tertiary")}>
            {cert.has_private_key ? '🔑' : '—'} {t('common.privateKey')}
          </span>
        </div>
      )}
      
      {/* Subject Information */}
      <CompactSection title={t('common.subject')} icon={Globe} iconClass="icon-bg-blue">
        <CompactGrid>
          <CompactField icon={Globe} label={t('common.commonName')} value={cert.cn || cert.common_name} />
          <CompactField icon={Buildings} label={t('common.organization')} value={cert.organization} />
          <CompactField autoIcon="orgUnit" label={t('common.orgUnit')} value={cert.organizational_unit} />
          <CompactField icon={MapPin} label={t('common.locality')} value={cert.locality} />
          <CompactField autoIcon="state" label={t('common.state')} value={cert.state} />
          <CompactField autoIcon="country" label={t('common.country')} value={cert.country} />
          <CompactField icon={Envelope} label={t('common.email')} value={cert.email} colSpan={2} />
        </CompactGrid>
      </CompactSection>
      
      {/* Validity Period */}
      <CompactSection title={t('common.validity')} icon={Calendar} iconClass="icon-bg-green">
        <CompactGrid>
          <CompactField icon={Calendar} label={t('common.validFrom')} value={formatDate(cert.valid_from)} />
          <CompactField icon={Calendar} label={t('common.validUntil')} value={formatDate(cert.valid_to)} />
        </CompactGrid>
      </CompactSection>
      
      {/* Technical Details */}
      <CompactSection title={t('common.technicalDetails')} icon={Key} iconClass="icon-bg-purple">
        <CompactGrid>
          <CompactField icon={Hash} label={t('common.serial')} value={cert.serial_number} mono copyable />
          <CompactField autoIcon="keyType" label={t('common.keyType')} value={cert.key_type} />
          <CompactField autoIcon="signatureAlgorithm" label={t('common.signatureAlgorithm')} value={cert.signature_algorithm} />
          <CompactField autoIcon="certType" label={t('details.certType')} value={formatCertType(cert.cert_type)} />
        </CompactGrid>
      </CompactSection>
      
      {/* SANs */}
      {cert.san_combined && (
        <CompactSection title={t('common.subjectAltNames')} icon={Globe} iconClass="icon-bg-cyan">
          <div className="text-xs font-mono text-text-primary break-all bg-bg-tertiary/30 p-2 rounded border border-border/50">
            {cert.san_combined}
          </div>
        </CompactSection>
      )}
      
      {/* Issuer */}
      <CompactSection title={t('common.issuer')} icon={ShieldCheck} iconClass="icon-bg-orange">
        <CompactGrid cols={1}>
          <CompactField autoIcon="issuer" label={t('common.issuer')} value={cert.issuer} mono />
          <CompactField autoIcon="ca" label={t('common.ca')} value={cert.issuer_name} />
          <CompactField autoIcon="caReference" label={t('details.caReference')} value={cert.caref} mono copyable />
        </CompactGrid>
      </CompactSection>

      {/* Chain Validation */}
      {cert.chain_status && (
        <CompactSection 
          title={t('details.chainValidation')} 
          icon={LinkSimple} 
          iconClass={cert.chain_status.status === 'complete' ? 'icon-bg-emerald' : cert.chain_status.status === 'incomplete' ? 'icon-bg-orange' : 'icon-bg-teal'}
        >
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              {cert.chain_status.status === 'complete' ? (
                <Badge variant="success" size="sm" dot>{t('details.chainComplete')}</Badge>
              ) : cert.chain_status.status === 'incomplete' ? (
                <Badge variant="warning" size="sm" dot>{t('details.chainIncomplete')}</Badge>
              ) : (
                <Badge variant="secondary" size="sm" dot>{t('details.chainPartial')}</Badge>
              )}
              {cert.chain_status.trust_source === 'trust_store' && (
                <Badge variant="teal" size="sm">✓ Trust Store</Badge>
              )}
              {cert.chain_status.trust_source === 'managed_ca' && (
                <Badge variant="primary" size="sm">✓ {t('details.managedCA')}</Badge>
              )}
            </div>
            {cert.chain_status.trust_anchor && (
              <CompactField autoIcon="ca" label={t('details.trustAnchor')} value={cert.chain_status.trust_anchor} />
            )}
            {cert.chain_status.chain?.length > 0 && (
              <div className="flex items-center gap-1 text-xs flex-wrap mt-1">
                <span className="px-2 py-0.5 rounded icon-bg-blue text-[10px]">{cert.common_name || 'Leaf'}</span>
                {cert.chain_status.chain.map((link, i) => (
                  <span key={i} className="flex items-center gap-1">
                    <span className="text-text-tertiary">→</span>
                    <span className={cn(
                      "px-2 py-0.5 rounded text-[10px]",
                      link.type === 'trust_store' ? 'icon-bg-amber' : 'icon-bg-emerald'
                    )}>{link.name}</span>
                  </span>
                ))}
              </div>
            )}
            {cert.chain_status.status === 'incomplete' && (
              <div className="mt-2 p-2 rounded-lg bg-accent-warning/5 border border-accent-warning/20">
                <p className="text-[11px] text-text-secondary">
                  {t('details.chainIncompleteHint')}
                </p>
                {onAddToTrustStore && cert.caref && (
                  <Button
                    size="xs"
                    variant="secondary"
                    className="mt-1.5"
                    onClick={() => onAddToTrustStore(cert.caref)}
                  >
                    <ShieldCheck size={12} className="mr-1" />
                    {t('details.addIssuerToTrustStore')}
                  </Button>
                )}
              </div>
            )}
          </div>
        </CompactSection>
      )}
      
      {/* Thumbprints */}
      <CompactSection title={t('common.fingerprints')} icon={Fingerprint} iconClass="icon-bg-gray" collapsible defaultOpen={false}>
        <CompactGrid cols={1}>
          <CompactField autoIcon="sha1" label="SHA-1" value={cert.thumbprint_sha1} mono copyable />
          <CompactField autoIcon="sha256" label="SHA-256" value={cert.thumbprint_sha256} mono copyable />
        </CompactGrid>
      </CompactSection>
      
      {/* PEM */}
      {showPem && cert.pem && (
        <CompactSection title={t('details.pemCertificate')} icon={Certificate} iconClass="icon-bg-green" collapsible defaultOpen={false}>
          <div className="relative">
            <pre className={cn(
              "text-2xs font-mono text-text-secondary bg-bg-tertiary/50 p-2 rounded overflow-x-auto border border-border/30",
              !showFullPem && "max-h-24 overflow-hidden"
            )}>
              {cert.pem}
            </pre>
            {!showFullPem && cert.pem.length > 500 && (
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
                navigator.clipboard.writeText(cert.pem)
                setPemCopied(true)
                setTimeout(() => setPemCopied(false), 2000)
              }}
            >
              {pemCopied ? <CheckCircle size={14} /> : <Copy size={14} />}
              {pemCopied ? t('common.copied') : t('details.copyPem')}
            </Button>
          </div>
        </CompactSection>
      )}
      
      {/* Revocation info */}
      {cert.revoked && (
        <CompactSection title={t('details.revocationDetails')}>
          <div className="bg-status-danger/10 border border-status-danger/20 rounded-lg p-3">
            <div className="flex items-center gap-2 text-status-danger mb-2">
              <X size={16} />
              <span className="font-medium">{t('details.certificateRevoked')}</span>
            </div>
            <CompactGrid>
              <CompactField autoIcon="revokedAt" label={t('details.revokedAt')} value={formatDate(cert.revoked_at)} />
              <CompactField autoIcon="reason" label={t('details.reason')} value={cert.revoke_reason || t('details.unspecified')} />
            </CompactGrid>
          </div>
        </CompactSection>
      )}
      
      {/* Metadata */}
      <CompactSection title={t('details.metadata')} collapsible defaultOpen={false}>
        <CompactGrid>
          <CompactField autoIcon="created" label={t('common.created')} value={formatDate(cert.created_at)} />
          <CompactField autoIcon="createdBy" label={t('details.createdBy')} value={cert.created_by} />
          <CompactField autoIcon="source" label={t('common.source')} value={cert.source} />
          <CompactField autoIcon="importedFrom" label={t('details.importedFrom')} value={cert.imported_from} />
          <CompactField autoIcon="referenceId" label={t('details.referenceId')} value={cert.refid} mono copyable colSpan={2} />
        </CompactGrid>
      </CompactSection>
    </div>
  )
}

export default CertificateDetails
