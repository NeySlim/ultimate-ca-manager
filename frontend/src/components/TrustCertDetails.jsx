/**
 * TrustCertDetails Component
 * 
 * Reusable component for displaying Trust Store certificate details.
 * Can be used in modals, slide-overs, or standalone pages.
 */
import { useState } from 'react'
import { 
  Certificate, 
  Key, 
  Clock, 
  Calendar,
  Download, 
  Trash,
  Copy,
  CheckCircle,
  Warning,
  ShieldCheck,
  Globe,
  Buildings,
  MapPin,
  Hash,
  Fingerprint,
  Tag,
  CaretDown,
  CaretUp
} from '@phosphor-icons/react'
import { Badge } from './Badge'
import { Button } from './Button'
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

// Section component
function Section({ title, children, collapsible = false, defaultOpen = true }) {
  const [isOpen, setIsOpen] = useState(defaultOpen)
  
  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button
        type="button"
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
  
  const handleCopy = (e) => {
    e.stopPropagation()
    copyToClipboard(String(value), () => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }
  
  return (
    <div className={cn("flex items-start gap-2", className)}>
      {Icon && <Icon size={14} className="text-text-tertiary mt-0.5 shrink-0" />}
      <div className="min-w-0 flex-1">
        <div className="text-[10px] uppercase tracking-wider text-text-tertiary">{label}</div>
        <div className={cn(
          "text-xs text-text-primary break-all",
          mono && "font-mono"
        )}>
          {value}
          {copyable && (
            <button 
              type="button"
              onClick={handleCopy}
              className="ml-2 text-text-tertiary hover:text-text-primary inline-flex"
            >
              {copied ? <CheckCircle size={12} className="text-status-success" /> : <Copy size={12} />}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

// Purpose badge configuration
const purposeConfig = {
  ca: { variant: 'info', label: 'CA Trust', description: 'Trusted for issuing certificates' },
  tls: { variant: 'success', label: 'TLS Trust', description: 'Trusted for TLS/SSL connections' },
  code: { variant: 'warning', label: 'Code Signing', description: 'Trusted for code signing' },
  email: { variant: 'default', label: 'Email', description: 'Trusted for S/MIME' },
  client: { variant: 'info', label: 'Client Auth', description: 'Trusted for client authentication' }
}

export function TrustCertDetails({ 
  cert,
  onExport,
  onDelete,
  canWrite = false,
  canDelete = false,
  showActions = true,
  showPem = true
}) {
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
    valid: { variant: 'success', label: 'Valid' },
    expiring: { variant: 'warning', label: 'Expiring Soon' },
    expired: { variant: 'danger', label: 'Expired' }
  }
  
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
          <div className="text-[10px] text-text-tertiary">Key Type</div>
          <div className="text-xs font-medium text-text-primary">{cert.key_type || 'N/A'}</div>
        </div>
        <div className="bg-bg-tertiary/50 rounded-lg p-2 text-center">
          <ShieldCheck size={16} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-[10px] text-text-tertiary">Signature</div>
          <div className="text-xs font-medium text-text-primary">{cert.signature_algorithm || 'N/A'}</div>
        </div>
        <div className="bg-bg-tertiary/50 rounded-lg p-2 text-center">
          <Certificate size={16} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-[10px] text-text-tertiary">Type</div>
          <div className="text-xs font-medium text-text-primary">{cert.is_ca ? 'CA' : 'End Entity'}</div>
        </div>
      </div>
      
      {/* Days Remaining Indicator */}
      {daysRemaining !== null && (
        <div className={cn(
          "flex items-center gap-2 px-3 py-2 rounded-lg text-xs",
          daysRemaining <= 0 && "bg-status-error/10 text-status-error",
          daysRemaining > 0 && daysRemaining <= 30 && "bg-status-warning/10 text-status-warning",
          daysRemaining > 30 && daysRemaining <= 90 && "bg-status-info/10 text-status-info",
          daysRemaining > 90 && "bg-status-success/10 text-status-success"
        )}>
          <Clock size={14} />
          {daysRemaining <= 0 ? (
            <span>Certificate expired {Math.abs(daysRemaining)} days ago</span>
          ) : (
            <span>{daysRemaining} days remaining until expiry</span>
          )}
        </div>
      )}
      
      {/* Actions */}
      {showActions && (
        <div className="flex gap-2 flex-wrap">
          {onExport && (
            <Button size="sm" variant="secondary" onClick={onExport}>
              <Download size={14} /> Export
            </Button>
          )}
          {onDelete && canDelete && (
            <Button size="sm" variant="danger" onClick={onDelete}>
              <Trash size={14} /> Remove
            </Button>
          )}
        </div>
      )}
      
      {/* Subject Information */}
      <Section title="Subject">
        <div className="grid grid-cols-2 gap-x-4 gap-y-2">
          <Field icon={Globe} label="Common Name" value={cert.common_name} />
          <Field icon={Buildings} label="Organization" value={cert.organization} />
          <Field label="Organizational Unit" value={cert.organizational_unit} />
          <Field icon={MapPin} label="Locality" value={cert.locality} />
          <Field label="State/Province" value={cert.state} />
          <Field label="Country" value={cert.country} />
        </div>
      </Section>
      
      {/* Issuer */}
      {cert.issuer && (
        <Section title="Issuer">
          <Field label="Issuer DN" value={cert.issuer} mono />
        </Section>
      )}
      
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
          <Field icon={Hash} label="Serial Number" value={cert.serial || cert.serial_number} mono copyable />
          <Field icon={Key} label="Key Type" value={cert.key_type} />
          <Field label="Signature Algorithm" value={cert.signature_algorithm} />
          {cert.subject && (
            <Field label="Subject DN" value={cert.subject} className="col-span-2" mono />
          )}
        </div>
      </Section>
      
      {/* Fingerprints */}
      <Section title="Fingerprints" collapsible defaultOpen={false}>
        <div className="space-y-2">
          <Field icon={Fingerprint} label="SHA-256" value={cert.thumbprint_sha256 || cert.fingerprint_sha256} mono copyable />
          <Field icon={Fingerprint} label="SHA-1" value={cert.thumbprint_sha1 || cert.fingerprint_sha1} mono copyable />
        </div>
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
      
      {/* Metadata */}
      <Section title="Metadata" collapsible defaultOpen={false}>
        <div className="grid grid-cols-2 gap-x-4 gap-y-2">
          <Field icon={Calendar} label="Added At" value={formatDate(cert.created_at)} />
          <Field label="Added By" value={cert.created_by} />
          {cert.notes && (
            <Field label="Notes" value={cert.notes} className="col-span-2" />
          )}
        </div>
      </Section>
    </div>
  )
}
