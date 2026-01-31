/**
 * CertificateDetails Component
 * 
 * Reusable component for displaying certificate details.
 * Can be used in modals, slide-overs, or standalone pages.
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
  ArrowsClockwise,
  CaretDown,
  CaretUp
} from '@phosphor-icons/react'
import { Badge } from './Badge'
import { Button } from './Button'
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

// Copy to clipboard helper
async function copyToClipboard(text, onSuccess) {
  try {
    await navigator.clipboard.writeText(text)
    onSuccess?.()
  } catch (err) {
    console.error('Failed to copy:', err)
  }
}

// Section component
function Section({ title, children, collapsible = false, defaultOpen = true }) {
  const [isOpen, setIsOpen] = useState(defaultOpen)
  
  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button
        onClick={() => collapsible && setIsOpen(!isOpen)}
        className={cn(
          "w-full px-3 py-2 bg-bg-tertiary/50 flex items-center justify-between text-left",
          collapsible && "cursor-pointer hover:bg-bg-tertiary"
        )}
        disabled={!collapsible}
      >
        <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
          {title}
        </span>
        {collapsible && (
          isOpen ? <CaretUp size={14} className="text-text-tertiary" /> : <CaretDown size={14} className="text-text-tertiary" />
        )}
      </button>
      {isOpen && (
        <div className="p-3 space-y-2">
          {children}
        </div>
      )}
    </div>
  )
}

// Field component
function Field({ icon: Icon, label, value, mono = false, copyable = false, className }) {
  const [copied, setCopied] = useState(false)
  
  if (!value && value !== 0) return null
  
  const handleCopy = () => {
    copyToClipboard(String(value), () => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }
  
  return (
    <div className={cn("flex items-start gap-2 group", className)}>
      {Icon && <Icon size={14} className="text-text-tertiary mt-0.5 shrink-0" />}
      <div className="min-w-0 flex-1">
        <div className="text-[10px] text-text-tertiary uppercase tracking-wider">{label}</div>
        <div className={cn(
          "text-sm text-text-primary break-all",
          mono && "font-mono text-xs"
        )}>
          {value}
        </div>
      </div>
      {copyable && (
        <button
          onClick={handleCopy}
          className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-bg-tertiary rounded"
          title="Copy"
        >
          {copied ? (
            <CheckCircle size={14} className="text-status-success" />
          ) : (
            <Copy size={14} className="text-text-tertiary" />
          )}
        </button>
      )}
    </div>
  )
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
      <Section title="Subject">
        <div className="grid grid-cols-2 gap-x-4 gap-y-2">
          <Field icon={Globe} label="Common Name" value={cert.cn || cert.common_name} />
          <Field icon={Buildings} label="Organization" value={cert.organization} />
          <Field label="Organizational Unit" value={cert.organizational_unit} />
          <Field icon={MapPin} label="Locality" value={cert.locality} />
          <Field label="State/Province" value={cert.state} />
          <Field label="Country" value={cert.country} />
          <Field icon={Envelope} label="Email" value={cert.email} />
        </div>
      </Section>
      
      {/* Validity Period */}
      <Section title="Validity">
        <div className="grid grid-cols-2 gap-x-4 gap-y-2">
          <Field icon={Calendar} label="Valid From" value={formatDate(cert.valid_from)} />
          <Field icon={Calendar} label="Valid Until" value={formatDate(cert.valid_to)} />
        </div>
      </Section>
      
      {/* Technical Details */}
      <Section title="Technical Details">
        <div className="grid grid-cols-2 gap-x-4 gap-y-2">
          <Field icon={Hash} label="Serial Number" value={cert.serial_number} mono copyable />
          <Field icon={Key} label="Key Type" value={cert.key_type} />
          <Field label="Signature Algorithm" value={cert.signature_algorithm} />
          <Field label="Certificate Type" value={cert.cert_type} />
        </div>
      </Section>
      
      {/* SANs */}
      {cert.san_combined && (
        <Section title="Subject Alternative Names">
          <div className="text-xs font-mono text-text-primary break-all bg-bg-tertiary/30 p-2 rounded">
            {cert.san_combined}
          </div>
        </Section>
      )}
      
      {/* Issuer */}
      <Section title="Issuer">
        <Field label="Issuer DN" value={cert.issuer} mono />
        <Field label="Issuing CA" value={cert.issuer_name} />
        {cert.caref && <Field label="CA Reference" value={cert.caref} mono copyable />}
      </Section>
      
      {/* Thumbprints */}
      <Section title="Fingerprints" collapsible defaultOpen={false}>
        <Field icon={Fingerprint} label="SHA-1" value={cert.thumbprint_sha1} mono copyable />
        <Field icon={Fingerprint} label="SHA-256" value={cert.thumbprint_sha256} mono copyable />
      </Section>
      
      {/* PEM */}
      {showPem && cert.pem && (
        <Section title="PEM Certificate" collapsible defaultOpen={false}>
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
                copyToClipboard(cert.pem, () => {
                  setPemCopied(true)
                  setTimeout(() => setPemCopied(false), 2000)
                })
              }}
            >
              {pemCopied ? <CheckCircle size={14} /> : <Copy size={14} />}
              {pemCopied ? 'Copied!' : 'Copy PEM'}
            </Button>
          </div>
        </Section>
      )}
      
      {/* Revocation info */}
      {cert.revoked && (
        <Section title="Revocation Details">
          <div className="bg-status-error/10 border border-status-error/20 rounded-lg p-3">
            <div className="flex items-center gap-2 text-status-error mb-2">
              <X size={16} />
              <span className="font-medium">This certificate has been revoked</span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div>
                <span className="text-text-tertiary">Revoked At:</span>
                <span className="ml-2 text-text-primary">{formatDate(cert.revoked_at)}</span>
              </div>
              <div>
                <span className="text-text-tertiary">Reason:</span>
                <span className="ml-2 text-text-primary">{cert.revoke_reason || 'Unspecified'}</span>
              </div>
            </div>
          </div>
        </Section>
      )}
      
      {/* Metadata */}
      <Section title="Metadata" collapsible defaultOpen={false}>
        <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
          <Field label="Created" value={formatDate(cert.created_at)} />
          <Field label="Created By" value={cert.created_by} />
          <Field label="Source" value={cert.source} />
          {cert.imported_from && <Field label="Imported From" value={cert.imported_from} />}
          <Field label="Reference ID" value={cert.refid} mono copyable />
        </div>
      </Section>
    </div>
  )
}

export default CertificateDetails
