/**
 * CSRDetails Component
 * 
 * Reusable component for displaying Certificate Signing Request details.
 * Uses global Compact components for consistent styling.
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
  ListBullets
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
      <CompactSection title="Subject">
        <CompactGrid>
          <CompactField icon={Globe} label="Common Name" value={csr.common_name || csr.cn} />
          <CompactField icon={Buildings} label="Organization" value={csr.organization || csr.o} />
          <CompactField label="Org Unit" value={csr.organizational_unit || csr.ou} />
          <CompactField icon={MapPin} label="Locality" value={csr.locality || csr.l} />
          <CompactField label="State" value={csr.state || csr.st} />
          <CompactField label="Country" value={csr.country || csr.c} />
          <CompactField icon={Envelope} label="Email" value={csr.email} colSpan={2} />
        </CompactGrid>
      </CompactSection>
      
      {/* Subject Alternative Names */}
      {(csr.san || csr.sans || csr.san_dns || csr.san_ip) && (
        <CompactSection title="Subject Alternative Names">
          <CompactGrid cols={1}>
            {csr.san_dns && csr.san_dns.length > 0 && (
              <CompactField 
                icon={Globe} 
                label="DNS Names" 
                value={Array.isArray(csr.san_dns) ? csr.san_dns.join(', ') : csr.san_dns} 
              />
            )}
            {csr.san_ip && csr.san_ip.length > 0 && (
              <CompactField 
                icon={ListBullets} 
                label="IP Addresses" 
                value={Array.isArray(csr.san_ip) ? csr.san_ip.join(', ') : csr.san_ip} 
              />
            )}
            {csr.san && !csr.san_dns && !csr.san_ip && (
              <CompactField icon={ListBullets} label="SANs" value={csr.san} />
            )}
            {csr.sans && (
              <CompactField icon={ListBullets} label="SANs" value={csr.sans} />
            )}
          </CompactGrid>
        </CompactSection>
      )}
      
      {/* Technical Details */}
      <CompactSection title="Technical Details">
        <CompactGrid>
          <CompactField icon={Key} label="Key Algorithm" value={csr.key_algorithm || csr.key_type} />
          <CompactField label="Key Size" value={csr.key_size} />
          <CompactField label="Sig Algo" value={csr.signature_algorithm} />
          <CompactField label="Subject DN" value={csr.subject} mono colSpan={2} />
        </CompactGrid>
      </CompactSection>
      
      {/* PEM */}
      {showPem && csr.pem && (
        <CompactSection title="CSR PEM" collapsible defaultOpen={false}>
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
                navigator.clipboard.writeText(csr.pem)
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
          <CompactField icon={Calendar} label="Created At" value={formatDate(csr.created_at)} />
          <CompactField label="Created By" value={csr.created_by} />
          <CompactField label="Signed At" value={csr.signed_at ? formatDate(csr.signed_at) : null} />
          <CompactField label="Signed By" value={csr.signed_by} />
        </CompactGrid>
      </CompactSection>
    </div>
  )
}
