/**
 * CSRDetails Component
 * 
 * Reusable component for displaying Certificate Signing Request details.
 * Can be used in modals, slide-overs, or standalone pages.
 */
import { useState } from 'react'
import { 
  FileText, 
  Key, 
  Clock, 
  Calendar,
  Download,
  Check,
  Trash,
  Copy,
  CheckCircle,
  Globe,
  Envelope,
  Buildings,
  MapPin,
  Hash,
  CaretDown,
  CaretUp,
  ListBullets
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

// Status configuration
const statusConfig = {
  pending: { variant: 'warning', label: 'Pending' },
  approved: { variant: 'success', label: 'Approved' },
  rejected: { variant: 'danger', label: 'Rejected' },
  signed: { variant: 'success', label: 'Signed' }
}

export function CSRDetails({ 
  csr,
  onSign,
  onReject,
  onDelete,
  onDownload,
  canWrite = false,
  canDelete = false,
  showActions = true,
  showPem = true
}) {
  const [showFullPem, setShowFullPem] = useState(false)
  const [pemCopied, setPemCopied] = useState(false)
  
  if (!csr) return null
  
  const status = csr.status?.toLowerCase() || 'pending'
  const isPending = status === 'pending'
  
  return (
    <div className="space-y-4 p-4">
      {/* Header with badges and actions */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-base font-semibold text-text-primary truncate">
              {csr.common_name || csr.cn || csr.descr}
            </h3>
            <Badge variant={statusConfig[status]?.variant || 'default'}>
              {statusConfig[status]?.label || status}
            </Badge>
          </div>
          {csr.organization && (
            <p className="text-xs text-text-secondary mt-1">{csr.organization}</p>
          )}
        </div>
      </div>
      
      {/* Quick Stats */}
      <div className="grid grid-cols-3 gap-2">
        <div className="bg-bg-tertiary/50 rounded-lg p-2 text-center">
          <Key size={16} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-[10px] text-text-tertiary">Key Type</div>
          <div className="text-xs font-medium text-text-primary">{csr.key_type || csr.key_algorithm || 'N/A'}</div>
        </div>
        <div className="bg-bg-tertiary/50 rounded-lg p-2 text-center">
          <Hash size={16} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-[10px] text-text-tertiary">Key Size</div>
          <div className="text-xs font-medium text-text-primary">{csr.key_size || 'N/A'}</div>
        </div>
        <div className="bg-bg-tertiary/50 rounded-lg p-2 text-center">
          <FileText size={16} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-[10px] text-text-tertiary">Signature</div>
          <div className="text-xs font-medium text-text-primary">{csr.signature_algorithm || 'N/A'}</div>
        </div>
      </div>
      
      {/* Actions */}
      {showActions && isPending && (
        <div className="flex gap-2 flex-wrap">
          {onSign && canWrite && (
            <Button size="sm" variant="primary" onClick={onSign}>
              <Check size={14} /> Sign CSR
            </Button>
          )}
          {onReject && canWrite && (
            <Button size="sm" variant="danger" onClick={onReject}>
              <Trash size={14} /> Reject
            </Button>
          )}
          {onDownload && (
            <Button size="sm" variant="secondary" onClick={onDownload}>
              <Download size={14} /> Download CSR
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
          <Field icon={Globe} label="Common Name" value={csr.common_name || csr.cn} />
          <Field icon={Buildings} label="Organization" value={csr.organization || csr.o} />
          <Field label="Organizational Unit" value={csr.organizational_unit || csr.ou} />
          <Field icon={MapPin} label="Locality" value={csr.locality || csr.l} />
          <Field label="State/Province" value={csr.state || csr.st} />
          <Field label="Country" value={csr.country || csr.c} />
          <Field icon={Envelope} label="Email" value={csr.email} />
        </div>
      </Section>
      
      {/* Subject Alternative Names */}
      {(csr.san || csr.sans || csr.san_dns || csr.san_ip) && (
        <Section title="Subject Alternative Names">
          <div className="space-y-2">
            {csr.san_dns && csr.san_dns.length > 0 && (
              <Field 
                icon={Globe} 
                label="DNS Names" 
                value={Array.isArray(csr.san_dns) ? csr.san_dns.join(', ') : csr.san_dns} 
              />
            )}
            {csr.san_ip && csr.san_ip.length > 0 && (
              <Field 
                icon={ListBullets} 
                label="IP Addresses" 
                value={Array.isArray(csr.san_ip) ? csr.san_ip.join(', ') : csr.san_ip} 
              />
            )}
            {csr.san && !csr.san_dns && !csr.san_ip && (
              <Field icon={ListBullets} label="SANs" value={csr.san} />
            )}
            {csr.sans && (
              <Field icon={ListBullets} label="SANs" value={csr.sans} />
            )}
          </div>
        </Section>
      )}
      
      {/* Technical Details */}
      <Section title="Technical Details">
        <div className="grid grid-cols-2 gap-x-4 gap-y-2">
          <Field icon={Key} label="Key Algorithm" value={csr.key_algorithm || csr.key_type} />
          <Field label="Key Size" value={csr.key_size} />
          <Field label="Signature Algorithm" value={csr.signature_algorithm} />
          {csr.subject && (
            <Field label="Subject DN" value={csr.subject} className="col-span-2" mono />
          )}
        </div>
      </Section>
      
      {/* PEM */}
      {showPem && csr.pem && (
        <Section title="CSR PEM" collapsible defaultOpen={false}>
          <div className="relative">
            <pre className={cn(
              "text-[10px] font-mono text-text-secondary bg-bg-tertiary/50 p-2 rounded overflow-x-auto",
              !showFullPem && "max-h-24 overflow-hidden"
            )}>
              {csr.pem}
            </pre>
            {!showFullPem && csr.pem.length > 500 && (
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
                copyToClipboard(csr.pem, () => {
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
          <Field icon={Calendar} label="Created At" value={formatDate(csr.created_at)} />
          <Field label="Created By" value={csr.created_by} />
          {csr.signed_at && (
            <Field label="Signed At" value={formatDate(csr.signed_at)} />
          )}
          {csr.signed_by && (
            <Field label="Signed By" value={csr.signed_by} />
          )}
        </div>
      </Section>
    </div>
  )
}
