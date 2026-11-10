/**
 * TrustCertPanel: pure presentation of one trust store certificate. Reads the
 * trust store payload (not_before/not_after, certificate_pem, added_*) and
 * falls back to the certificate field names.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { 
  Certificate, 
  Key, 
  Clock, 
  Calendar, 
  Copy,
  CheckCircle,
  ShieldCheck,
  Globe,
  Buildings,
  MapPin,
  Hash,
  Fingerprint,
  Tag,
  User,
  Info
} from '@phosphor-icons/react'
import { Badge } from '../Badge'
import { Button } from '../Button'
import { CompactSection, CompactGrid, CompactField } from '../DetailCard'
import { cn, daysRemaining as computeDaysRemaining } from '../../lib/utils'
import { useClipboard } from '../../hooks/useClipboard'
import { keyAlgorithmLabel } from '../../lib/keyAlgorithms'
import { PostQuantumBadge } from '../PostQuantumBadge'
import { showSection } from './sections'
import { formatDate as formatDateUtil } from '../../lib/utils'

// Format date helper — delegates to shared util
function formatDate(dateStr) {
  if (!dateStr) return '—'
  return formatDateUtil(dateStr)
}

// Purpose badge configuration
const getPurposeConfig = (t) => ({
  ca: { variant: 'info', label: t('trustStore.caTrust'), description: t('trustStore.caTrustDesc') },
  tls: { variant: 'success', label: t('trustStore.tlsTrust'), description: t('trustStore.tlsTrustDesc') },
  code: { variant: 'warning', label: t('common.codeSigning'), description: t('trustStore.codeSigningDesc') },
  email: { variant: 'default', label: t('common.email'), description: t('trustStore.emailTrustDesc') },
  client: { variant: 'info', label: t('trustStore.clientAuth'), description: t('trustStore.clientAuthDesc') }
})

export function TrustCertPanel({
  cert,
  section = 'all',
  showPem = true,
  embedded = false,
  // Caller content (its action row), rendered under the summary
  children,
}) {

  const { t } = useTranslation()
  const [showFullPem, setShowFullPem] = useState(false)
  const { copy: copyPem, isCopied } = useClipboard()
  const pemCopied = isCopied('pem')
  
  if (!cert) return null

  const on = (...names) => showSection(section, ...names)
  const validTo = cert.valid_to ?? cert.not_after
  const validFrom = cert.valid_from ?? cert.not_before
  const pem = cert.pem ?? cert.certificate_pem
  
  // Determine status based on validity
  const getStatus = () => {
    if (validTo) {
      const remaining = computeDaysRemaining(validTo)
      // null means the date could not be read, not that it has passed.
      if (remaining !== null && remaining <= 0) return 'expired'
      if (remaining !== null && remaining <= 30) return 'expiring'
    }
    return 'valid'
  }
  
  const status = getStatus()
  const statusConfig = {
    valid: { variant: 'success', label: t('common.valid') },
    expiring: { variant: 'warning', label: t('common.detailsExpiring') },
    expired: { variant: 'danger', label: t('common.expired') }
  }
  
  const purposeConfig = getPurposeConfig(t)
  
  // Calculate days remaining
  const daysRemaining = validTo ? computeDaysRemaining(validTo) : null
  
  // Get purposes as array
  const purposes = cert.purpose ? 
    (Array.isArray(cert.purpose) ? cert.purpose : cert.purpose.split(',').map(p => p.trim())) 
    : []
  
  return (
    <div className={cn("space-y-3 sm:space-y-4 p-3 sm:p-4", embedded && "space-y-3 p-3")}>
      {on('overview') && (<>
      {!embedded && <>
      {/* Header with badges */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-base font-semibold text-text-primary truncate">
              {cert.name || cert.common_name || cert.descr}
            </h3>
            <Badge variant={statusConfig[status].variant}>
              {statusConfig[status].label}
            </Badge>
            <PostQuantumBadge postQuantum={cert.post_quantum} algorithm={cert.key_type} />
          </div>
          {cert.organization && (
            <p className="text-xs text-text-secondary mt-1">{cert.organization}</p>
          )}
        </div>
      </div>
      
      {/* Purpose badges */}
      {purposes.length > 0 && (
        <div className="flex gap-2 flex-wrap">
          {purposes.map((purpose, idx) => {
            const config = purposeConfig[purpose.toLowerCase()] || { variant: 'default', label: purpose }
            return (
              <Badge key={idx} variant={config.variant}>
                <Tag size={12} className="mr-1" />
                {config.label}
              </Badge>
            )
          })}
        </div>
      )}
      
      {/* Quick Stats */}
      <div className="grid grid-cols-3 gap-2">
        <div className="bg-tertiary-op50 rounded-lg p-2 text-center">
          <Key size={16} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-2xs text-text-tertiary">{t('common.keyType')}</div>
          <div className="text-xs font-medium text-text-primary">{keyAlgorithmLabel(cert.key_type, t, cert.security_level) || t('common.na')}</div>
        </div>
        <div className="bg-tertiary-op50 rounded-lg p-2 text-center">
          <ShieldCheck size={16} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-2xs text-text-tertiary">{t('common.signature')}</div>
          <div className="text-xs font-medium text-text-primary">{cert.signature_algorithm || t('common.na')}</div>
        </div>
        <div className="bg-tertiary-op50 rounded-lg p-2 text-center">
          <Certificate size={16} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-2xs text-text-tertiary">{t('common.type')}</div>
          <div className="text-xs font-medium text-text-primary">{cert.is_ca ? t('common.ca') : t('common.endEntity')}</div>
        </div>
      </div>
      
      {/* Days Remaining Indicator */}
      {daysRemaining !== null && (
        <div className={cn(
          "flex items-center gap-2 px-3 py-2 rounded-lg text-xs",
          daysRemaining <= 0 && "bg-status-danger-op10 text-status-danger",
          daysRemaining > 0 && daysRemaining <= 30 && "bg-status-warning-op10 text-status-warning",
          daysRemaining > 30 && daysRemaining <= 90 && "bg-status-info-op10 text-status-info",
          daysRemaining > 90 && "bg-status-success-op10 text-status-success"
        )}>
          <Clock size={14} />
          {daysRemaining <= 0 ? (
            <span>{t('details.expiredDaysAgo', { count: Math.abs(daysRemaining) })}</span>
          ) : (
            <span>{t('details.daysRemaining', { count: daysRemaining })}</span>
          )}
        </div>
      )}
      </>}
      {children}
      </>)}
      {on('overview') && (<>
      {/* Embedded: compact status bar */}
      {embedded && (
        <div className="flex items-center gap-2 flex-wrap px-3 py-2 rounded-lg border border-border bg-tertiary-op30">
          <Badge variant={statusConfig[status].variant} size="sm">
            {statusConfig[status].label}
          </Badge>
          <PostQuantumBadge postQuantum={cert.post_quantum} algorithm={cert.key_type} />
          {purposes.length > 0 && purposes.slice(0, 2).map((purpose, idx) => {
            const config = purposeConfig[purpose.toLowerCase()] || { variant: 'default', label: purpose }
            return <Badge key={idx} variant={config.variant} size="sm">{config.label}</Badge>
          })}
          <span className="text-2xs text-text-tertiary">•</span>
          <span className="text-2xs text-text-secondary">{keyAlgorithmLabel(cert.key_type, t, cert.security_level) || t('common.na')}</span>
        </div>
      )}
      
      </>)}
      {on('overview') && (<>
      {/* Subject Information */}
      <CompactSection title={t('common.subject')} icon={Globe}>
        <CompactGrid>
          <CompactField label={t('common.commonName')} value={cert.common_name} icon={Globe} />
          <CompactField label={t('common.country')} value={cert.country} autoIcon="country" />
          <CompactField label={t('common.stateProvince')} value={cert.state} autoIcon="state" />
          <CompactField label={t('common.locality')} value={cert.locality} icon={MapPin} />
          <CompactField label={t('common.organization')} value={cert.organization} icon={Buildings} />
          <CompactField label={t('common.orgUnit')} value={cert.organizational_unit} autoIcon="orgUnit" />
        </CompactGrid>
      </CompactSection>
      
      </>)}
      {on('overview', 'chain') && (<>
      {/* Issuer */}
      {cert.issuer && (
        <CompactSection title={t('common.issuer')} icon={ShieldCheck}>
          <CompactField autoIcon="issuerDN" label={t('details.issuerDN')} value={cert.issuer} mono />
        </CompactSection>
      )}
      
      </>)}
      {on('overview') && (<>
      {/* Validity Period */}
      <CompactSection title={t('common.validity')} icon={Calendar}>
        <CompactGrid>
          <CompactField label={t('common.validFrom')} value={formatDate(validFrom)} icon={Calendar} />
          <CompactField label={t('common.validUntil')} value={formatDate(validTo)} icon={Calendar} />
        </CompactGrid>
      </CompactSection>
      
      </>)}
      {on('overview') && (<>
      {/* Technical Details */}
      <CompactSection title={t('common.technicalDetails')} icon={Info}>
        <CompactGrid>
          <CompactField label={t('common.serialNumber')} value={cert.serial || cert.serial_number} icon={Hash} mono />
          <CompactField label={t('common.keyType')} value={keyAlgorithmLabel(cert.key_type, t, cert.security_level)} icon={Key} />
          <CompactField
            label={t('common.issuerSignatureAlgorithm')}
            hint={t('common.issuerSignatureAlgorithmHint')}
            value={cert.signature_algorithm}
            autoIcon="issuerSignatureAlgorithm"
          />
          {cert.subject && (
            <CompactField autoIcon="subjectDN" label={t('details.subjectDN')} value={cert.subject} className="col-span-2" mono />
          )}
        </CompactGrid>
      </CompactSection>
      
      </>)}
      {on('overview') && (<>
      {/* Fingerprints */}
      <CompactSection title={t('common.fingerprints')} icon={Fingerprint} collapsible defaultOpen={false}>
        <CompactField label="SHA-256" value={cert.thumbprint_sha256 || cert.fingerprint_sha256} icon={Fingerprint} mono />
        <CompactField label="SHA-1" value={cert.thumbprint_sha1 || cert.fingerprint_sha1} icon={Fingerprint} mono />
      </CompactSection>
      
      </>)}
      {on('pem') && (<>
      {/* PEM */}
      {showPem && pem && (
        <CompactSection title={t('details.pemCertificate')} icon={Certificate} collapsible defaultOpen={false}>
          <div className="relative">
            <pre className={cn(
              "text-2xs font-mono text-text-secondary bg-tertiary-op50 p-2 rounded overflow-x-auto",
              !showFullPem && "max-h-24 overflow-hidden"
            )}>
              {pem}
            </pre>
            {!showFullPem && pem.length > 500 && (
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
                copyPem(pem, 'pem')
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
      <CompactSection title={t('details.metadata')} icon={Info} collapsible defaultOpen={false}>
        <CompactGrid>
          <CompactField label={t('details.addedAt')} value={formatDate(cert.created_at ?? cert.added_at)} icon={Calendar} />
          <CompactField label={t('details.addedBy')} value={cert.created_by ?? cert.added_by} icon={User} />
          {cert.notes && (
            <CompactField autoIcon="notes" label={t('common.notes')} value={cert.notes} className="col-span-2" />
          )}
        </CompactGrid>
      </CompactSection>
      </>)}
    </div>
  )
}
