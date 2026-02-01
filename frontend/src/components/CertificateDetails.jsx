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
  ArrowsClockwise
} from '@phosphor-icons/react'
import { Badge } from './Badge'
import { Button } from './Button'
import { CompactSection, CompactGrid, CompactField, CompactHeader, CompactStats } from './DetailCard'
import { cn } from '../lib/utils'

// Status badge config
const statusConfig = {
  valid: { variant: 'success', label: 'Valid' },
  expiring: { variant: 'warning', label: 'Expiring Soon' },
  expired: { variant: 'danger', label: 'Expired' },
  revoked: { variant: 'danger', label: 'Revoked' }
}

// Source badge config
const sourceConfig = {
  acme: { variant: 'info', label: 'ACME' },
  scep: { variant: 'warning', label: 'SCEP' },
  import: { variant: 'default', label: 'Imported' },
  csr: { variant: 'default', label: 'From CSR' },
  manual: { variant: 'default', label: 'Manual' }
}

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

// Expiry indicator
function ExpiryIndicator({ daysRemaining, validTo }) {
  let color = 'text-status-success'
  let bgColor = 'bg-status-success/10'
  let label = `${daysRemaining} days remaining`
  
  if (daysRemaining <= 0) {
    color = 'text-status-error'
    bgColor = 'bg-status-error/10'
    label = 'Expired'
  } else if (daysRemaining <= 7) {
    color = 'text-status-error'
    bgColor = 'bg-status-error/10'
    label = `${daysRemaining} days remaining`
  } else if (daysRemaining <= 30) {
    color = 'text-status-warning'
    bgColor = 'bg-status-warning/10'
  }
  
  return (
    <div className={cn("flex items-center gap-2 px-3 py-2 rounded-lg", bgColor)}>
      <Clock size={16} className={color} />
      <div>
        <div className={cn("text-sm font-medium", color)}>{label}</div>
        <div className="text-xs text-text-tertiary">Expires {formatDate(validTo, 'short')}</div>
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
  canWrite = false,
  canDelete = false,
  compact = false,
  showActions = true,
  showPem = true
}) {
  const [pemCopied, setPemCopied] = useState(false)
  const [showFullPem, setShowFullPem] = useState(false)
  
  if (!certificate) return null
  
  const cert = certificate
  const status = cert.revoked ? 'revoked' : (cert.status || 'valid')
  const statusBadge = statusConfig[status] || statusConfig.valid
  const sourceBadge = sourceConfig[cert.source] || null
  
  return (
    <div className={cn("space-y-4 p-4", compact && "space-y-3 p-3")}>
      {/* Header */}
      <div className="flex items-start gap-3">
        <div className={cn(
          "p-2.5 rounded-lg shrink-0",
          cert.revoked ? "bg-status-error/10" : "bg-accent-primary/10"
        )}>
          <Certificate size={24} className={cert.revoked ? "text-status-error" : "text-accent-primary"} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-lg font-semibold text-text-primary truncate">
              {cert.cn || cert.common_name || cert.descr || 'Certificate'}
            </h3>
            <Badge variant={statusBadge.variant} size="sm">{statusBadge.label}</Badge>
            {sourceBadge && <Badge variant={sourceBadge.variant} size="sm">{sourceBadge.label}</Badge>}
          </div>
          <p className="text-xs text-text-tertiary truncate mt-0.5">{cert.subject}</p>
        </div>
      </div>
      
      {/* Expiry indicator */}
      {!cert.revoked && cert.days_remaining !== undefined && (
        <ExpiryIndicator daysRemaining={cert.days_remaining} validTo={cert.valid_to} />
      )}
      
      {/* Quick stats */}
      <div className="grid grid-cols-3 gap-2">
        <div className="bg-bg-tertiary/50 rounded-lg p-2.5 text-center">
          <Key size={16} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-xs font-medium text-text-primary">{cert.key_algorithm || 'RSA'}</div>
          <div className="text-[10px] text-text-tertiary">{cert.key_size ? `${cert.key_size} bits` : '—'}</div>
        </div>
        <div className="bg-bg-tertiary/50 rounded-lg p-2.5 text-center">
          <Lock size={16} className={cn("mx-auto mb-1", cert.has_private_key ? "text-status-success" : "text-text-tertiary")} />
          <div className="text-xs font-medium text-text-primary">{cert.has_private_key ? 'Has Key' : 'No Key'}</div>
          <div className="text-[10px] text-text-tertiary">{cert.private_key_location || '—'}</div>
        </div>
        <div className="bg-bg-tertiary/50 rounded-lg p-2.5 text-center">
          <ShieldCheck size={16} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-xs font-medium text-text-primary truncate">{cert.signature_algorithm || '—'}</div>
          <div className="text-[10px] text-text-tertiary">Signature</div>
        </div>
      </div>
      
      {/* Actions */}
      {showActions && (
        <div className="flex flex-wrap gap-2">
          {onExport && (
            <>
              <Button size="sm" variant="secondary" onClick={() => onExport('pem')}>
                <Download size={14} /> PEM
              </Button>
              <Button size="sm" variant="secondary" onClick={() => onExport('der')}>
                <Download size={14} /> DER
              </Button>
              {cert.has_private_key && (
                <Button size="sm" variant="secondary" onClick={() => onExport('p12')}>
                  <Download size={14} /> PKCS#12
                </Button>
              )}
            </>
          )}
          {onRenew && canWrite && !cert.revoked && (
            <Button size="sm" variant="secondary" onClick={onRenew}>
              <ArrowsClockwise size={14} /> Renew
            </Button>
          )}
          {onRevoke && canWrite && !cert.revoked && (
            <Button size="sm" variant="danger" onClick={onRevoke}>
              <X size={14} /> Revoke
            </Button>
          )}
          {onDelete && canDelete && (
            <Button size="sm" variant="danger" onClick={onDelete}>
              <Trash size={14} />
            </Button>
          )}
        </div>
      )}
      
      {/* Subject Information */}
      <CompactSection title="Subject">
        <CompactGrid>
          <CompactField icon={Globe} label="Common Name" value={cert.cn || cert.common_name} />
          <CompactField icon={Buildings} label="Organization" value={cert.organization} />
          <CompactField label="Org Unit" value={cert.organizational_unit} />
          <CompactField icon={MapPin} label="Locality" value={cert.locality} />
          <CompactField label="State" value={cert.state} />
          <CompactField label="Country" value={cert.country} />
          <CompactField icon={Envelope} label="Email" value={cert.email} colSpan={2} />
        </CompactGrid>
      </CompactSection>
      
      {/* Validity Period */}
      <CompactSection title="Validity">
        <CompactGrid>
          <CompactField icon={Calendar} label="Valid From" value={formatDate(cert.valid_from)} />
          <CompactField icon={Calendar} label="Valid Until" value={formatDate(cert.valid_to)} />
        </CompactGrid>
      </CompactSection>
      
      {/* Technical Details */}
      <CompactSection title="Technical Details">
        <CompactGrid>
          <CompactField icon={Hash} label="Serial" value={cert.serial_number} mono copyable />
          <CompactField icon={Key} label="Key Type" value={cert.key_type} />
          <CompactField label="Sig Algo" value={cert.signature_algorithm} />
          <CompactField label="Cert Type" value={cert.cert_type} />
        </CompactGrid>
      </CompactSection>
      
      {/* SANs */}
      {cert.san_combined && (
        <CompactSection title="Subject Alternative Names">
          <div className="text-xs font-mono text-text-primary break-all bg-bg-tertiary/30 p-2 rounded">
            {cert.san_combined}
          </div>
        </CompactSection>
      )}
      
      {/* Issuer */}
      <CompactSection title="Issuer">
        <CompactGrid cols={1}>
          <CompactField label="Issuer DN" value={cert.issuer} mono />
          <CompactField label="Issuing CA" value={cert.issuer_name} />
          <CompactField label="CA Reference" value={cert.caref} mono copyable />
        </CompactGrid>
      </CompactSection>
      
      {/* Thumbprints */}
      <CompactSection title="Fingerprints" collapsible defaultOpen={false}>
        <CompactGrid cols={1}>
          <CompactField icon={Fingerprint} label="SHA-1" value={cert.thumbprint_sha1} mono copyable />
          <CompactField icon={Fingerprint} label="SHA-256" value={cert.thumbprint_sha256} mono copyable />
        </CompactGrid>
      </CompactSection>
      
      {/* PEM */}
      {showPem && cert.pem && (
        <CompactSection title="PEM Certificate" collapsible defaultOpen={false}>
          <div className="relative">
            <pre className={cn(
              "text-[10px] font-mono text-text-secondary bg-bg-tertiary/50 p-2 rounded overflow-x-auto",
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
              {showFullPem ? 'Show Less' : 'Show Full'}
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
              {pemCopied ? 'Copied!' : 'Copy PEM'}
            </Button>
          </div>
        </CompactSection>
      )}
      
      {/* Revocation info */}
      {cert.revoked && (
        <CompactSection title="Revocation Details">
          <div className="bg-status-error/10 border border-status-error/20 rounded-lg p-3">
            <div className="flex items-center gap-2 text-status-error mb-2">
              <X size={16} />
              <span className="font-medium">This certificate has been revoked</span>
            </div>
            <CompactGrid>
              <CompactField label="Revoked At" value={formatDate(cert.revoked_at)} />
              <CompactField label="Reason" value={cert.revoke_reason || 'Unspecified'} />
            </CompactGrid>
          </div>
        </CompactSection>
      )}
      
      {/* Metadata */}
      <CompactSection title="Metadata" collapsible defaultOpen={false}>
        <CompactGrid>
          <CompactField label="Created" value={formatDate(cert.created_at)} />
          <CompactField label="Created By" value={cert.created_by} />
          <CompactField label="Source" value={cert.source} />
          <CompactField label="Imported From" value={cert.imported_from} />
          <CompactField label="Reference ID" value={cert.refid} mono copyable colSpan={2} />
        </CompactGrid>
      </CompactSection>
    </div>
  )
}

export default CertificateDetails
