/**
 * CSRDetails Component
 * 
 * Reusable component for displaying Certificate Signing Request details.
 * Uses global Compact components for consistent styling.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
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
const getStatusConfig = (t) => ({
  pending: { variant: 'warning', label: t('common.pending') },
  approved: { variant: 'success', label: t('common.approved') },
  rejected: { variant: 'danger', label: t('common.rejected') },
  signed: { variant: 'success', label: t('csrs.signed') }
})

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
  const { t } = useTranslation()
  const [showFullPem, setShowFullPem] = useState(false)
  const [pemCopied, setPemCopied] = useState(false)
  
  if (!csr) return null
  
  const status = csr.status?.toLowerCase() || 'pending'
  const isPending = status === 'pending'
  const statusConfig = getStatusConfig(t)
  
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
          <div className="text-2xs text-text-tertiary">{t('common.keyType')}</div>
          <div className="text-xs font-medium text-text-primary">{csr.key_type || csr.key_algorithm || 'N/A'}</div>
        </div>
        <div className="bg-bg-tertiary/50 rounded-lg p-2 text-center">
          <Hash size={16} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-2xs text-text-tertiary">{t('common.keySize')}</div>
          <div className="text-xs font-medium text-text-primary">{csr.key_size || 'N/A'}</div>
        </div>
        <div className="bg-bg-tertiary/50 rounded-lg p-2 text-center">
          <FileText size={16} className="mx-auto text-text-tertiary mb-1" />
          <div className="text-2xs text-text-tertiary">{t('common.signature')}</div>
          <div className="text-xs font-medium text-text-primary">{csr.signature_algorithm || 'N/A'}</div>
        </div>
      </div>
      
      {/* Actions */}
      {showActions && isPending && (
        <div className="flex gap-2 flex-wrap">
          {onSign && canWrite && (
            <Button size="sm" variant="primary" onClick={onSign}>
              <Check size={14} /> {t('common.signCSR')}
            </Button>
          )}
          {onReject && canWrite && (
            <Button size="sm" variant="danger" onClick={onReject}>
              <Trash size={14} /> {t('csrs.rejectCSR')}
            </Button>
          )}
          {onDownload && (
            <Button size="sm" variant="secondary" onClick={onDownload}>
              <Download size={14} /> {t('csrs.downloadCSR')}
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
      <CompactSection title={t('common.subject')}>
        <CompactGrid>
          <CompactField icon={Globe} label={t('common.commonName')} value={csr.common_name || csr.cn} />
          <CompactField icon={Buildings} label={t('common.organization')} value={csr.organization || csr.o} />
          <CompactField autoIcon="orgUnit" label={t('common.orgUnit')} value={csr.organizational_unit || csr.ou} />
          <CompactField icon={MapPin} label={t('common.locality')} value={csr.locality || csr.l} />
          <CompactField autoIcon="state" label={t('common.state')} value={csr.state || csr.st} />
          <CompactField autoIcon="country" label={t('common.country')} value={csr.country || csr.c} />
          <CompactField icon={Envelope} label={t('common.email')} value={csr.email} colSpan={2} />
        </CompactGrid>
      </CompactSection>
      
      {/* Subject Alternative Names */}
      {(csr.san || csr.sans || csr.san_dns || csr.san_ip) && (
        <CompactSection title={t('common.subjectAltNames')}>
          <CompactGrid cols={1}>
            {csr.san_dns && csr.san_dns.length > 0 && (
              <CompactField 
                icon={Globe} 
                label={t('details.dnsNames')} 
                value={Array.isArray(csr.san_dns) ? csr.san_dns.join(', ') : csr.san_dns} 
              />
            )}
            {csr.san_ip && csr.san_ip.length > 0 && (
              <CompactField 
                icon={ListBullets} 
                label={t('details.ipAddresses')} 
                value={Array.isArray(csr.san_ip) ? csr.san_ip.join(', ') : csr.san_ip} 
              />
            )}
            {csr.san && !csr.san_dns && !csr.san_ip && (
              <CompactField icon={ListBullets} label={t('details.sans')} value={csr.san} />
            )}
            {csr.sans && (
              <CompactField icon={ListBullets} label={t('details.sans')} value={csr.sans} />
            )}
          </CompactGrid>
        </CompactSection>
      )}
      
      {/* Technical Details */}
      <CompactSection title={t('common.technicalDetails')}>
        <CompactGrid>
          <CompactField icon={Key} label={t('common.keyAlgorithm')} value={csr.key_algorithm || csr.key_type} />
          <CompactField autoIcon="keySize" label={t('common.keySize')} value={csr.key_size} />
          <CompactField autoIcon="signatureAlgorithm" label={t('common.signatureAlgorithm')} value={csr.signature_algorithm} />
          <CompactField label={t('details.subjectDN')} value={csr.subject} mono colSpan={2} />
        </CompactGrid>
      </CompactSection>
      
      {/* PEM */}
      {showPem && csr.pem && (
        <CompactSection title={t('details.csrPem')} collapsible defaultOpen={false}>
          <div className="relative">
            <pre className={cn(
              "text-2xs font-mono text-text-secondary bg-bg-tertiary/50 p-2 rounded overflow-x-auto",
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
              {showFullPem ? t('details.showLess') : t('details.showFull')}
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
              {pemCopied ? t('common.copied') : t('details.copyPem')}
            </Button>
          </div>
        </CompactSection>
      )}
      
      {/* Metadata */}
      <CompactSection title={t('details.metadata')} collapsible defaultOpen={false}>
        <CompactGrid>
          <CompactField icon={Calendar} label={t('common.createdAt')} value={formatDate(csr.created_at)} />
          <CompactField autoIcon="createdBy" label={t('details.createdBy')} value={csr.created_by} />
          <CompactField autoIcon="signedAt" label={t('details.signedAt')} value={csr.signed_at ? formatDate(csr.signed_at) : null} />
          <CompactField autoIcon="signedBy" label={t('common.signedBy')} value={csr.signed_by} />
        </CompactGrid>
      </CompactSection>
    </div>
  )
}
