/**
 * CADetails Component
 * 
 * Reusable component for displaying Certificate Authority details.
 * Can be used in modals, slide-overs, or standalone pages.
 */
import { useState } from 'react'
import { 
  Certificate, 
  Key, 
  Lock, 
  Clock, 
  Calendar,
  Download, 
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
  TreeStructure,
  CaretDown,
  CaretUp,
  Link
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

export function CADetails({ 
  ca,
  onExport,
  onDelete,
  canWrite = false,
  canDelete = false,
  showActions = true,
  showPem = true
}) {
  const [showFullPem, setShowFullPem] = useState(false)
  const [pemCopied, setPemCopied] = useState(false)
  
  if (!ca) return null
  
  // Determine status
  const getStatus = () => {
    if (ca.status === 'Expired') return 'expired'
    if (ca.days_remaining !== null && ca.days_remaining <= 30) return 'expiring'
    return 'valid'
  }
  
  const status = getStatus()
  const statusConfig = {
    valid: { variant: 'success', label: 'Active' },
    expiring: { variant: 'warning', label: 'Expiring Soon' },
    expired: { variant: 'danger', label: 'Expired' }
  }
  
  return (
    <div className="space-y-4 p-4">
      {/* Header with badges and actions */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-base font-semibold text-text-primary truncate">
              {ca.common_name || ca.descr}
            </h3>
            <Badge variant={ca.is_root ? 'info' : 'default'}>
              {ca.is_root ? 'Root CA' : 'Intermediate'}
            </Badge>
            <Badge variant={statusConfig[status].variant}>
              {statusConfig[status].label}
            </Badge>
          </div>
          {ca.organization && (
            <p className="text-xs text-text-secondary mt-1">{ca.organization}</p>
          )}
        </div>
      </div>
      
      {/* Quick Stats */}
      <div className="grid grid-cols-4 gap-2">
        <div className="bg-bg-tertiary/50 rounded-lg p-2 text-center">
          <Key size={16} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-[10px] text-text-tertiary">Key Type</div>
          <div className="text-xs font-medium text-text-primary">{ca.key_type || 'N/A'}</div>
        </div>
        <div className="bg-bg-tertiary/50 rounded-lg p-2 text-center">
          <Lock size={16} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-[10px] text-text-tertiary">Private Key</div>
          <div className="text-xs font-medium text-text-primary">
            {ca.has_private_key ? 'Available' : 'None'}
          </div>
        </div>
        <div className="bg-bg-tertiary/50 rounded-lg p-2 text-center">
          <ShieldCheck size={16} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-[10px] text-text-tertiary">Signature</div>
          <div className="text-xs font-medium text-text-primary">{ca.signature_algorithm || ca.hash_algorithm || 'N/A'}</div>
        </div>
        <div className="bg-bg-tertiary/50 rounded-lg p-2 text-center">
          <Certificate size={16} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-[10px] text-text-tertiary">Certificates</div>
          <div className="text-xs font-medium text-text-primary">{ca.certs || 0}</div>
        </div>
      </div>
      
      {/* Days Remaining Indicator */}
      {ca.days_remaining !== null && (
        <div className={cn(
          "flex items-center gap-2 px-3 py-2 rounded-lg text-xs",
          ca.days_remaining <= 0 && "bg-status-error/10 text-status-error",
          ca.days_remaining > 0 && ca.days_remaining <= 30 && "bg-status-warning/10 text-status-warning",
          ca.days_remaining > 30 && ca.days_remaining <= 90 && "bg-status-info/10 text-status-info",
          ca.days_remaining > 90 && "bg-status-success/10 text-status-success"
        )}>
          <Clock size={14} />
          {ca.days_remaining <= 0 ? (
            <span>Certificate expired {Math.abs(ca.days_remaining)} days ago</span>
          ) : (
            <span>{ca.days_remaining} days remaining until expiry</span>
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
              <Trash size={14} /> Delete
            </Button>
          )}
        </div>
      )}
      
      {/* Subject Information */}
      <Section title="Subject">
        <div className="grid grid-cols-2 gap-x-4 gap-y-2">
          <Field icon={Globe} label="Common Name" value={ca.common_name} />
          <Field icon={Buildings} label="Organization" value={ca.organization} />
          <Field label="Organizational Unit" value={ca.organizational_unit} />
          <Field icon={MapPin} label="Locality" value={ca.locality} />
          <Field label="State/Province" value={ca.state} />
          <Field label="Country" value={ca.country} />
          <Field icon={Envelope} label="Email" value={ca.email} />
        </div>
      </Section>
      
      {/* Issuer (if intermediate) */}
      {!ca.is_root && ca.issuer && (
        <Section title="Issuer">
          <div className="grid grid-cols-2 gap-x-4 gap-y-2">
            <Field icon={TreeStructure} label="Issuer DN" value={ca.issuer} className="col-span-2" />
          </div>
        </Section>
      )}
      
      {/* Validity Period */}
      <Section title="Validity">
        <div className="grid grid-cols-2 gap-x-4 gap-y-2">
          <Field icon={Calendar} label="Valid From" value={formatDate(ca.valid_from)} />
          <Field icon={Calendar} label="Valid Until" value={formatDate(ca.valid_to)} />
        </div>
      </Section>
      
      {/* Technical Details */}
      <Section title="Technical Details">
        <div className="grid grid-cols-2 gap-x-4 gap-y-2">
          <Field icon={Hash} label="Serial Number" value={ca.serial} mono copyable />
          <Field icon={Key} label="Key Type" value={ca.key_type} />
          <Field label="Signature Algorithm" value={ca.signature_algorithm || ca.hash_algorithm} />
          <Field label="Subject DN" value={ca.subject} className="col-span-2" mono />
        </div>
      </Section>
      
      {/* CRL/OCSP Configuration */}
      {(ca.cdp_enabled || ca.ocsp_enabled) && (
        <Section title="Revocation Configuration">
          <div className="grid grid-cols-2 gap-x-4 gap-y-2">
            {ca.cdp_enabled && (
              <Field icon={Link} label="CRL Distribution Point" value={ca.cdp_url} className="col-span-2" mono />
            )}
            {ca.ocsp_enabled && (
              <Field icon={Link} label="OCSP URL" value={ca.ocsp_url} className="col-span-2" mono />
            )}
          </div>
        </Section>
      )}
      
      {/* Fingerprints */}
      <Section title="Fingerprints" collapsible defaultOpen={false}>
        <div className="space-y-2">
          <Field icon={Fingerprint} label="SHA-256" value={ca.thumbprint_sha256} mono copyable />
          <Field icon={Fingerprint} label="SHA-1" value={ca.thumbprint_sha1} mono copyable />
        </div>
      </Section>
      
      {/* PEM */}
      {showPem && ca.pem && (
        <Section title="PEM Certificate" collapsible defaultOpen={false}>
          <div className="relative">
            <pre className={cn(
              "text-[10px] font-mono text-text-secondary bg-bg-tertiary/50 p-2 rounded overflow-x-auto",
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
              {showFullPem ? 'Show Less' : 'Show Full'}
            </Button>
            <Button 
              type="button"
              size="sm" 
              variant="ghost"
              onClick={(e) => {
                e.stopPropagation()
                copyToClipboard(ca.pem, () => {
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
          <Field label="Created At" value={formatDate(ca.created_at)} />
          <Field label="Created By" value={ca.created_by} />
          {ca.imported_from && (
            <Field label="Imported From" value={ca.imported_from} className="col-span-2" />
          )}
        </div>
      </Section>
    </div>
  )
}
