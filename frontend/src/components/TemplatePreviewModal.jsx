/**
 * TemplatePreviewModal - Preview what a certificate would look like with this template
 */
import { useTranslation } from 'react-i18next'
import { X, Certificate, Eye, ShieldCheck, Key, Clock, Globe, ListBullets } from '@phosphor-icons/react'
import { Modal } from './Modal'
import { Badge } from './Badge'
import { cn } from '../lib/utils'

// Preview field component
function PreviewField({ label, value, icon: Icon, mono = false, badge = false }) {
  return (
    <div className="flex items-start gap-3 py-2 border-b border-border/30 last:border-0">
      {Icon && (
        <div className="w-6 h-6 rounded flex items-center justify-center icon-bg-blue shrink-0 mt-0.5">
          <Icon size={14} className="text-accent-primary" />
        </div>
      )}
      <div className="flex-1 min-w-0">
        <div className="text-xs text-text-secondary mb-0.5">{label}</div>
        {badge ? (
          <Badge variant={value === 'RSA' ? 'info' : value === 'EC' ? 'success' : 'default'} size="sm">
            {value}
          </Badge>
        ) : (
          <div className={cn(
            "text-sm text-text-primary",
            mono && "font-mono text-xs"
          )}>
            {value || '—'}
          </div>
        )}
      </div>
    </div>
  )
}

// Sample SAN preview
function SANPreview({ template }) {
  const sans = []
  if (template?.allow_any_cn) {
    sans.push('DNS: example.lan.pew.pet')
    sans.push('DNS: *.example.lan.pew.pet')
  }
  if (template?.san_types?.includes('email') || template?.san_types?.includes('rfc822Name')) {
    sans.push('Email: admin@example.com')
  }
  if (template?.san_types?.includes('ip') || template?.san_types?.includes('iPAddress')) {
    sans.push('IP: 192.168.1.100')
  }
  return sans.length > 0 ? sans.join('\n') : 'None configured'
}

export function TemplatePreviewModal({ open, onClose, template }) {
  const { t } = useTranslation()
  if (!template) return null

  // Calculate sample validity dates
  const now = new Date()
  const validFrom = now.toISOString().split('T')[0]
  const validityDays = template.validity_days || 365
  const validTo = new Date(now.getTime() + validityDays * 24 * 60 * 60 * 1000).toISOString().split('T')[0]
  
  // Determine key info
  const keyType = template.key_type || 'RSA'
  const keySize = template.key_size || (keyType === 'RSA' ? 2048 : 256)

  return (
    <Modal open={open} onClose={onClose} size="lg">
      <div className="p-4">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg icon-bg-purple flex items-center justify-center">
              <Eye size={18} className="text-accent-secondary" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-text-primary">{t('templates.preview')}</h2>
              <p className="text-xs text-text-secondary">{t('templates.previewFor')}: <strong>{template.name}</strong></p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-bg-tertiary text-text-secondary">
            <X size={18} />
          </button>
        </div>
        
        {/* Preview info banner */}
        <div className="flex items-center gap-2 p-2 mb-4 rounded-lg bg-accent-primary/10 border border-accent-primary/20">
          <Eye size={16} className="text-accent-primary" />
          <span className="text-xs text-text-secondary">
            {t('templates.previewDescription')}
          </span>
        </div>
        
        {/* Certificate preview card */}
        <div className="border border-border rounded-lg overflow-hidden">
          {/* Certificate header */}
          <div className="bg-bg-tertiary px-4 py-3 border-b border-border">
            <div className="flex items-center gap-2">
              <Certificate size={20} className="text-accent-primary" />
              <span className="font-medium text-text-primary">{t('templates.sampleCertificate')}</span>
              <Badge variant="success" size="sm">{t('common.valid')}</Badge>
            </div>
          </div>
          
          {/* Certificate fields */}
          <div className="p-4 space-y-1">
            <PreviewField 
              icon={Certificate}
              label="Common Name (CN)" 
              value={template.default_cn || template.allow_any_cn ? 'your-common-name.domain.com' : 'Fixed by template'} 
            />
            
            <PreviewField 
              icon={ShieldCheck}
              label="Template" 
              value={template.name} 
            />
            
            <PreviewField 
              icon={Key}
              label="Key Algorithm" 
              value={`${keyType} ${keySize}${keyType === 'EC' ? ' curve' : '-bit'}`}
            />
            
            <PreviewField 
              icon={Clock}
              label="Validity Period" 
              value={`${validityDays} days (${validFrom} → ${validTo})`}
            />
            
            {template.key_usage && (
              <PreviewField 
                icon={ListBullets}
                label="Key Usage" 
                value={Array.isArray(template.key_usage) ? template.key_usage.join(', ') : template.key_usage} 
              />
            )}
            
            {template.extended_key_usage && (
              <PreviewField 
                icon={ListBullets}
                label="Extended Key Usage" 
                value={Array.isArray(template.extended_key_usage) ? template.extended_key_usage.join(', ') : template.extended_key_usage} 
              />
            )}
            
            <PreviewField 
              icon={Globe}
              label="Subject Alternative Names (SANs)" 
              value={SANPreview({ template })}
              mono
            />
          </div>
          
          {/* Template restrictions */}
          {(template.max_path_length !== undefined || template.require_cn || !template.allow_any_cn) && (
            <div className="px-4 py-3 bg-bg-tertiary border-t border-border">
              <div className="text-xs font-medium text-text-secondary mb-2">{t('templates.restrictions')}</div>
              <div className="flex flex-wrap gap-2">
                {!template.allow_any_cn && (
                  <Badge variant="warning" size="sm">{t('templates.fixedCN')}</Badge>
                )}
                {template.require_cn && (
                  <Badge variant="info" size="sm">{t('templates.cnRequired')}</Badge>
                )}
                {template.max_path_length !== undefined && template.max_path_length >= 0 && (
                  <Badge variant="default" size="sm">{t('templates.pathLength')}: {template.max_path_length}</Badge>
                )}
                {template.basic_constraints === 'ca' && (
                  <Badge variant="purple" size="sm">{t('templates.caCertificate')}</Badge>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </Modal>
  )
}
