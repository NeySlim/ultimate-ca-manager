/**
 * TrustCertDetails Component
 * 
 * Reusable component for displaying Trust Store certificate details.
 * Uses global CompactSection/CompactGrid/CompactField for consistent styling.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { 
  Certificate, 
  Key, 
  Clock, 
  Calendar,
  Download, 
  Trash,
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

// Copy to clipboard helper
async function copyToClipboard(text, onSuccess) {
  try {
    await navigator.clipboard.writeText(text)
    onSuccess?.()
  } catch (err) {
    console.error('Failed to copy:', err)
  }
}

// Purpose badge configuration
const getPurposeConfig = (t) => ({
  ca: { variant: 'info', label: t('trustStore.caTrust'), description: t('trustStore.caTrustDesc') },
  tls: { variant: 'success', label: t('trustStore.tlsTrust'), description: t('trustStore.tlsTrustDesc') },
  code: { variant: 'warning', label: t('common.codeSigning'), description: t('trustStore.codeSigningDesc') },
  email: { variant: 'default', label: t('common.email'), description: t('trustStore.emailTrustDesc') },
  client: { variant: 'info', label: t('trustStore.clientAuth'), description: t('trustStore.clientAuthDesc') }
})

export function TrustCertDetails({ 
  cert,
  onExport,
  onDelete,
  canWrite = false,
  canDelete = false,
  showActions = true,
  showPem = true
}) {
  const { t } = useTranslation()
  const [showFullPem, setShowFullPem] = useState(false)
  const [pemCopied, setPemCopied] = useState(false)
  
  if (!cert) return null
  
  // Determine status based on validity
  const getStatus = () => {
    if (cert.valid_to) {
      const expiryDate = new Date(cert.valid_to)
      const now = new Date()
      const daysRemaining = Math.ceil((expiryDate - now) / (1000 * 60 * 60 * 24))
      if (daysRemaining <= 0) return 'expired'
      if (daysRemaining <= 30) return 'expiring'
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
  const daysRemaining = cert.valid_to ? 
    Math.ceil((new Date(cert.valid_to) - new Date()) / (1000 * 60 * 60 * 24)) : null
  
  // Get purposes as array
  const purposes = cert.purpose ? 
    (Array.isArray(cert.purpose) ? cert.purpose : cert.purpose.split(',').map(p => p.trim())) 
    : []
  
  return (
    <div className="space-y-4 p-4">
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
        <div className="bg-bg-tertiary/50 rounded-lg p-2 text-center">
          <Key size={16} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-2xs text-text-tertiary">{t('common.keyType')}</div>
          <div className="text-xs font-medium text-text-primary">{cert.key_type || 'N/A'}</div>
        </div>
        <div className="bg-bg-tertiary/50 rounded-lg p-2 text-center">
          <ShieldCheck size={16} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-2xs text-text-tertiary">{t('common.signature')}</div>
          <div className="text-xs font-medium text-text-primary">{cert.signature_algorithm || 'N/A'}</div>
        </div>
        <div className="bg-bg-tertiary/50 rounded-lg p-2 text-center">
          <Certificate size={16} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-2xs text-text-tertiary">{t('common.type')}</div>
          <div className="text-xs font-medium text-text-primary">{cert.is_ca ? t('common.ca') : t('common.endEntity')}</div>
        </div>
      </div>
      
      {/* Days Remaining Indicator */}
      {daysRemaining !== null && (
        <div className={cn(
          "flex items-center gap-2 px-3 py-2 rounded-lg text-xs",
          daysRemaining <= 0 && "bg-status-danger/10 text-status-danger",
          daysRemaining > 0 && daysRemaining <= 30 && "bg-status-warning/10 text-status-warning",
          daysRemaining > 30 && daysRemaining <= 90 && "bg-status-info/10 text-status-info",
          daysRemaining > 90 && "bg-status-success/10 text-status-success"
        )}>
          <Clock size={14} />
          {daysRemaining <= 0 ? (
            <span>{t('details.expiredDaysAgo', { count: Math.abs(daysRemaining) })}</span>
          ) : (
            <span>{t('details.daysRemaining', { count: daysRemaining })}</span>
          )}
        </div>
      )}
      
      {/* Actions */}
      {showActions && (
        <div className="flex gap-2 flex-wrap">
          {onExport && (
            <Button size="sm" variant="secondary" onClick={onExport}>
              <Download size={14} /> {t('common.export')}
            </Button>
          )}
          {onDelete && canDelete && (
            <Button size="sm" variant="danger" onClick={onDelete}>
              <Trash size={14} /> {t('common.delete')}
            </Button>
          )}
        </div>
      )}
      
      {/* Subject Information */}
      <CompactSection title={t('common.subject')} icon={Globe}>
        <CompactGrid>
          <CompactField label={t('common.commonName')} value={cert.common_name} icon={Globe} />
          <CompactField label={t('common.organization')} value={cert.organization} icon={Buildings} />
          <CompactField label={t('common.orgUnit')} value={cert.organizational_unit} autoIcon="orgUnit" />
          <CompactField label={t('common.locality')} value={cert.locality} icon={MapPin} />
          <CompactField label={t('common.stateProvince')} value={cert.state} autoIcon="state" />
          <CompactField label={t('common.country')} value={cert.country} autoIcon="country" />
        </CompactGrid>
      </CompactSection>
      
      {/* Issuer */}
      {cert.issuer && (
        <CompactSection title={t('common.issuer')} icon={ShieldCheck}>
          <CompactField label={t('details.issuerDN')} value={cert.issuer} mono />
        </CompactSection>
      )}
      
      {/* Validity Period */}
      <CompactSection title={t('common.validity')} icon={Calendar}>
        <CompactGrid>
          <CompactField label={t('common.validFrom')} value={formatDate(cert.valid_from)} icon={Calendar} />
          <CompactField label={t('common.validUntil')} value={formatDate(cert.valid_to)} icon={Calendar} />
        </CompactGrid>
      </CompactSection>
      
      {/* Technical Details */}
      <CompactSection title={t('common.technicalDetails')} icon={Info}>
        <CompactGrid>
          <CompactField label={t('common.serialNumber')} value={cert.serial || cert.serial_number} icon={Hash} mono />
          <CompactField label={t('common.keyType')} value={cert.key_type} icon={Key} />
          <CompactField label={t('common.signatureAlgorithm')} value={cert.signature_algorithm} autoIcon="signatureAlgorithm" />
          {cert.subject && (
            <CompactField label={t('details.subjectDN')} value={cert.subject} className="col-span-2" mono />
          )}
        </CompactGrid>
      </CompactSection>
      
      {/* Fingerprints */}
      <CompactSection title={t('common.fingerprints')} icon={Fingerprint} collapsible defaultOpen={false}>
        <CompactField label="SHA-256" value={cert.thumbprint_sha256 || cert.fingerprint_sha256} icon={Fingerprint} mono />
        <CompactField label="SHA-1" value={cert.thumbprint_sha1 || cert.fingerprint_sha1} icon={Fingerprint} mono />
      </CompactSection>
      
      {/* PEM */}
      {showPem && cert.pem && (
        <CompactSection title={t('details.pemCertificate')} icon={Certificate} collapsible defaultOpen={false}>
          <div className="relative">
            <pre className={cn(
              "text-2xs font-mono text-text-secondary bg-bg-tertiary/50 p-2 rounded overflow-x-auto",
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
                copyToClipboard(cert.pem, () => {
                  setPemCopied(true)
                  setTimeout(() => setPemCopied(false), 2000)
                })
              }}
            >
              {pemCopied ? <CheckCircle size={14} /> : <Copy size={14} />}
              {pemCopied ? t('common.copied') : t('details.copyPem')}
            </Button>
          </div>
        </CompactSection>
      )}
      
      {/* Metadata */}
      <CompactSection title={t('details.metadata')} icon={Info} collapsible defaultOpen={false}>
        <CompactGrid>
          <CompactField label={t('details.addedAt')} value={formatDate(cert.created_at)} icon={Calendar} />
          <CompactField label={t('details.addedBy')} value={cert.created_by} icon={User} />
          {cert.notes && (
            <CompactField label={t('common.notes')} value={cert.notes} className="col-span-2" />
          )}
        </CompactGrid>
      </CompactSection>
    </div>
  )
}
