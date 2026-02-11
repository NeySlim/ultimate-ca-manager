/**
 * CertificateCompareModal - Compare two certificates side by side
 */
import { useState, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { X, Certificate, ArrowsLeftRight } from '@phosphor-icons/react'
import { Modal } from './Modal'
import { Badge } from './Badge'
import { Select } from './ui/Select'
import { cn, formatDate } from '../lib/utils'

// Field comparison helper
function CompareField({ label, value1, value2, mono = false }) {
  const same = value1 === value2
  return (
    <div className="grid grid-cols-[140px,1fr,1fr] gap-2 py-1.5 border-b border-border/50 last:border-0">
      <span className="text-xs text-text-secondary font-medium">{label}</span>
      <span className={cn(
        "text-xs truncate",
        mono && "font-mono",
        same ? "text-text-primary" : "text-status-warning"
      )}>
        {value1 || '—'}
      </span>
      <span className={cn(
        "text-xs truncate",
        mono && "font-mono", 
        same ? "text-text-primary" : "text-status-warning"
      )}>
        {value2 || '—'}
      </span>
    </div>
  )
}

export function CertificateCompareModal({ open, onClose, certificates = [], initialCert = null }) {
  const { t } = useTranslation()
  const [cert1Id, setCert1Id] = useState(initialCert?.id || '')
  const [cert2Id, setCert2Id] = useState('')
  
  useEffect(() => {
    if (initialCert?.id) {
      setCert1Id(initialCert.id)
    }
  }, [initialCert])
  
  const cert1 = useMemo(() => certificates.find(c => String(c.id) === String(cert1Id)), [certificates, cert1Id])
  const cert2 = useMemo(() => certificates.find(c => String(c.id) === String(cert2Id)), [certificates, cert2Id])
  
  const options = useMemo(() => [
    { value: '', label: t('compare.selectCertificate') },
    ...certificates.map(c => ({
      value: String(c.id),
      label: c.common_name || c.subject || `${t('common.certificate')} #${c.id}`
    }))
  ], [certificates, t])
  
  // Swap certificates
  const handleSwap = () => {
    const temp = cert1Id
    setCert1Id(cert2Id)
    setCert2Id(temp)
  }
  
  // Calculate differences
  const differences = useMemo(() => {
    if (!cert1 || !cert2) return 0
    let diff = 0
    const fields = [
      'common_name', 'issuer', 'status', 'key_type', 'key_size',
      'valid_from', 'valid_to', 'serial_number'
    ]
    fields.forEach(f => {
      if (String(cert1[f] || '') !== String(cert2[f] || '')) diff++
    })
    return diff
  }, [cert1, cert2])

  return (
    <Modal open={open} onClose={onClose} size="xl">
      <div className="p-4">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg icon-bg-blue flex items-center justify-center">
              <ArrowsLeftRight size={18} className="text-accent-primary" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-text-primary">{t('compare.title')}</h2>
              <p className="text-xs text-text-secondary">{t('compare.subtitle')}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-bg-tertiary text-text-secondary">
            <X size={18} />
          </button>
        </div>
        
        {/* Certificate selectors */}
        <div className="grid grid-cols-[1fr,auto,1fr] gap-2 items-end mb-4">
          <div>
            <label className="text-xs text-text-secondary mb-1 block">{t('compare.certificateA')}</label>
            <Select
              value={cert1Id}
              onChange={val => setCert1Id(val)}
              options={options}
              className="w-full"
            />
          </div>
          <button
            onClick={handleSwap}
            disabled={!cert1Id || !cert2Id}
            className="p-2 rounded hover:bg-bg-tertiary text-text-secondary disabled:opacity-50"
            title={t('compare.swap')}
          >
            <ArrowsLeftRight size={18} />
          </button>
          <div>
            <label className="text-xs text-text-secondary mb-1 block">{t('compare.certificateB')}</label>
            <Select
              value={cert2Id}
              onChange={val => setCert2Id(val)}
              options={options.filter(o => o.value !== cert1Id)}
              className="w-full"
            />
          </div>
        </div>
        
        {/* Comparison summary */}
        {cert1 && cert2 && (
          <div className="flex items-center gap-4 mb-4 p-2 rounded-lg bg-bg-tertiary">
            <Badge variant={differences === 0 ? 'success' : 'warning'}>
              {differences === 0 ? t('compare.identical') : t('compare.differences', { count: differences })}
            </Badge>
            <span className="text-xs text-text-secondary">
              {differences === 0 
                ? t('compare.identicalDescription')
                : t('compare.differencesDescription')
              }
            </span>
          </div>
        )}
        
        {/* Comparison table */}
        {cert1 && cert2 ? (
          <div className="border border-border rounded-lg overflow-hidden">
            {/* Header row */}
            <div className="grid grid-cols-[140px,1fr,1fr] gap-2 py-2 px-3 bg-bg-tertiary border-b border-border">
              <span className="text-xs font-semibold text-text-secondary">{t('compare.field')}</span>
              <div className="flex items-center gap-2">
                <Certificate size={14} className="text-accent-primary" />
                <span className="text-xs font-semibold text-text-primary truncate">
                  {cert1.common_name || t('compare.certificateA')}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <Certificate size={14} className="text-accent-secondary" />
                <span className="text-xs font-semibold text-text-primary truncate">
                  {cert2.common_name || t('compare.certificateB')}
                </span>
              </div>
            </div>
            
            {/* Comparison fields */}
            <div className="px-3 py-1 max-h-[400px] overflow-y-auto">
              <CompareField label={t('common.commonName')} value1={cert1.common_name} value2={cert2.common_name} />
              <CompareField label={t('common.status')} value1={cert1.status} value2={cert2.status} />
              <CompareField label={t('common.issuer')} value1={cert1.issuer} value2={cert2.issuer} />
              <CompareField label={t('common.keyType')} value1={cert1.key_type} value2={cert2.key_type} />
              <CompareField label={t('common.keySize')} value1={cert1.key_size} value2={cert2.key_size} />
              <CompareField label={t('common.validFrom')} value1={formatDate(cert1.valid_from)} value2={formatDate(cert2.valid_from)} />
              <CompareField label={t('common.validUntil')} value1={formatDate(cert1.valid_to)} value2={formatDate(cert2.valid_to)} />
              <CompareField label={t('common.serialNumber')} value1={cert1.serial_number} value2={cert2.serial_number} mono />
              <CompareField label={t('common.signatureAlgorithm')} value1={cert1.signature_algorithm} value2={cert2.signature_algorithm} />
              {(cert1.san || cert2.san) && (
                <CompareField label={t('details.sans')} value1={cert1.san} value2={cert2.san} />
              )}
              {(cert1.thumbprint_sha256 || cert2.thumbprint_sha256) && (
                <CompareField label="SHA-256" value1={cert1.thumbprint_sha256?.substring(0, 32) + '...'} value2={cert2.thumbprint_sha256?.substring(0, 32) + '...'} mono />
              )}
            </div>
          </div>
        ) : (
          <div className="text-center py-8 text-text-secondary">
            <ArrowsLeftRight size={32} className="mx-auto mb-2 opacity-50" />
            <p className="text-sm">{t('compare.selectTwoToCompare')}</p>
          </div>
        )}
      </div>
    </Modal>
  )
}
