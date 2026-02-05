/**
 * CADetails Component
 * 
 * Reusable component for displaying Certificate Authority details.
 * Uses global Compact components for consistent styling.
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
  ShieldCheck,
  Globe,
  Envelope,
  Buildings,
  MapPin,
  Hash,
  Fingerprint,
  TreeStructure,
  Link
} from '@phosphor-icons/react'
import { Badge, CATypeIcon } from './Badge'
import { Button } from './Button'
import { CompactSection, CompactGrid, CompactField } from './DetailCard'

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
            <CATypeIcon isRoot={ca.is_root} size="lg" />
            <h3 className="text-base font-semibold text-text-primary truncate">
              {ca.common_name || ca.descr}
            </h3>
            <Badge variant={ca.is_root ? 'warning' : 'info'}>
              {ca.is_root ? 'Root CA' : 'Intermediate'}
            </Badge>
            <Badge variant={statusConfig[status].variant}>
              {statusConfig[status].label}
            </Badge>
          </div>
          {ca.organization && (
            <p className="text-xs text-text-secondary mt-1 pl-9">{ca.organization}</p>
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
          ca.days_remaining <= 0 && "bg-status-danger/10 text-status-danger",
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
            <Button size="sm" variant="danger-soft" onClick={onDelete}>
              <Trash size={14} /> Delete
            </Button>
          )}
        </div>
      )}
      
      {/* Subject Information */}
      <CompactSection title="Subject" icon={Globe} iconClass="icon-bg-blue">
        <CompactGrid>
          <CompactField icon={Globe} label="Common Name" value={ca.common_name} />
          <CompactField icon={Buildings} label="Organization" value={ca.organization} />
          <CompactField autoIcon label="Org Unit" value={ca.organizational_unit} />
          <CompactField icon={MapPin} label="Locality" value={ca.locality} />
          <CompactField autoIcon label="State" value={ca.state} />
          <CompactField autoIcon label="Country" value={ca.country} />
          <CompactField icon={Envelope} label="Email" value={ca.email} colSpan={2} />
        </CompactGrid>
      </CompactSection>
      
      {/* Issuer (if intermediate) */}
      {!ca.is_root && ca.issuer && (
        <CompactSection title="Issuer" icon={TreeStructure} iconClass="icon-bg-orange">
          <CompactGrid cols={1}>
            <CompactField icon={TreeStructure} label="Issuer DN" value={ca.issuer} />
          </CompactGrid>
        </CompactSection>
      )}
      
      {/* Validity Period */}
      <CompactSection title="Validity" icon={Calendar} iconClass="icon-bg-green">
        <CompactGrid>
          <CompactField icon={Calendar} label="Valid From" value={formatDate(ca.valid_from)} />
          <CompactField icon={Calendar} label="Valid Until" value={formatDate(ca.valid_to)} />
        </CompactGrid>
      </CompactSection>
      
      {/* Technical Details */}
      <CompactSection title="Technical Details" icon={Key} iconClass="icon-bg-purple">
        <CompactGrid>
          <CompactField icon={Hash} label="Serial" value={ca.serial} mono copyable />
          <CompactField autoIcon label="Key Type" value={ca.key_type} />
          <CompactField autoIcon label="Sig Algo" value={ca.signature_algorithm || ca.hash_algorithm} />
          <CompactField label="Subject DN" value={ca.subject} mono colSpan={2} />
        </CompactGrid>
      </CompactSection>
      
      {/* CRL/OCSP Configuration */}
      {(ca.cdp_enabled || ca.ocsp_enabled) && (
        <CompactSection title="Revocation Configuration" icon={Link} iconClass="icon-bg-cyan">
          <CompactGrid cols={1}>
            {ca.cdp_enabled && (
              <CompactField icon={Link} label="CRL Distribution Point" value={ca.cdp_url} mono />
            )}
            {ca.ocsp_enabled && (
              <CompactField icon={Link} label="OCSP URL" value={ca.ocsp_url} mono />
            )}
          </CompactGrid>
        </CompactSection>
      )}
      
      {/* Fingerprints */}
      <CompactSection title="Fingerprints" icon={Fingerprint} iconClass="icon-bg-gray" collapsible defaultOpen={false}>
        <CompactGrid cols={1}>
          <CompactField icon={Fingerprint} label="SHA-256" value={ca.thumbprint_sha256} mono copyable />
          <CompactField icon={Fingerprint} label="SHA-1" value={ca.thumbprint_sha1} mono copyable />
        </CompactGrid>
      </CompactSection>
      
      {/* PEM */}
      {showPem && ca.pem && (
        <CompactSection title="PEM Certificate" icon={Certificate} iconClass="icon-bg-green" collapsible defaultOpen={false}>
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
                navigator.clipboard.writeText(ca.pem)
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
      
      {/* Metadata */}
      <CompactSection title="Metadata" collapsible defaultOpen={false}>
        <CompactGrid>
          <CompactField autoIcon label="Created" value={formatDate(ca.created_at)} />
          <CompactField autoIcon label="Created By" value={ca.created_by} />
          <CompactField label="Imported From" value={ca.imported_from} colSpan={2} />
        </CompactGrid>
      </CompactSection>
    </div>
  )
}
