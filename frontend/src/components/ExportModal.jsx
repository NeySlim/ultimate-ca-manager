/**
 * ExportModal — Unified export dialog for certificates and CAs
 * 
 * Provides format selection, optional chain/key inclusion, and password for PKCS12.
 * Private key options are hidden when user lacks write permission.
 * 
 * Usage:
 *   <ExportModal
 *     open={showExport}
 *     onClose={() => setShowExport(false)}
 *     entityType="certificate"
 *     entityName="my-cert.example.com"
 *     hasPrivateKey={true}
 *     canExportKey={canWrite('certificates')}
 *     onExport={(format, options) => handleExport(format, options)}
 *   />
 */
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Download, Lock, Certificate, ShieldCheck } from '@phosphor-icons/react'
import { Modal } from './Modal'
import { Button } from './Button'
import { cn } from '../lib/utils'

const FORMATS = [
  { key: 'pem', label: 'PEM', description: 'export.formatPemDesc', ext: '.pem' },
  { key: 'der', label: 'DER', description: 'export.formatDerDesc', ext: '.der' },
  { key: 'pkcs7', label: 'P7B / PKCS#7', description: 'export.formatP7bDesc', ext: '.p7b' },
  { key: 'pkcs12', label: 'P12 / PKCS#12', description: 'export.formatP12Desc', ext: '.p12', requiresKey: true },
  { key: 'key', label: 'Private Key', description: 'export.formatKeyDesc', ext: '.key', requiresKey: true, keyOnly: true },
]

export function ExportModal({
  open,
  onClose,
  entityType = 'certificate',
  entityName = '',
  hasPrivateKey = false,
  canExportKey = false,
  onExport,
}) {
  const { t } = useTranslation()
  const [format, setFormat] = useState('pem')
  const [includeChain, setIncludeChain] = useState(true)
  const [includeKey, setIncludeKey] = useState(false)
  const [password, setPassword] = useState('')
  const [exporting, setExporting] = useState(false)

  // Reset state when modal opens
  useEffect(() => {
    if (open) {
      setFormat('pem')
      setIncludeChain(true)
      setIncludeKey(false)
      setPassword('')
      setExporting(false)
    }
  }, [open])

  // PKCS12 always includes key — sync state
  const isPkcs12 = format === 'pkcs12'
  const isKeyOnly = format === 'key'
  const effectiveIncludeKey = (isPkcs12 || isKeyOnly) ? true : includeKey
  const needsPassword = isPkcs12  // Only PKCS12 requires password
  const showPasswordField = isPkcs12 || isKeyOnly || includeKey  // Show optional password for key exports

  // Available formats: hide PKCS12 if no key or no permission
  const availableFormats = FORMATS.filter(f => {
    if (f.requiresKey) return hasPrivateKey && canExportKey
    return true
  })

  const handleExport = async () => {
    if (needsPassword && password.length < 4) return
    setExporting(true)
    try {
      await onExport(format, {
        includeChain,
        includeKey: effectiveIncludeKey,
        password: (needsPassword || (effectiveIncludeKey && password)) ? password : undefined,
      })
      onClose()
    } catch {
      // Error handled by parent
    } finally {
      setExporting(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !exporting) handleExport()
  }

  return (
    <Modal open={open} onClose={() => onClose()} title={t('export.title', 'Export')} size="sm">
      <form onSubmit={(e) => { e.preventDefault(); handleExport() }} className="p-4 space-y-4">
        {/* Entity name */}
        {entityName && (
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-bg-secondary text-sm">
            {entityType === 'ca' ? (
              <ShieldCheck size={16} className="text-accent-primary shrink-0" />
            ) : (
              <Certificate size={16} className="text-accent-primary shrink-0" />
            )}
            <span className="text-text-primary font-medium truncate">{entityName}</span>
          </div>
        )}

        {/* Format selection */}
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-text-secondary uppercase tracking-wide">
            {t('export.format', 'Format')}
          </label>
          <div className="grid grid-cols-2 gap-2">
            {availableFormats.map(f => (
              <button
                type="button"
                key={f.key}
                onClick={() => setFormat(f.key)}
                className={cn(
                  'flex flex-col items-start px-3 py-2 rounded-lg border text-left transition-all',
                  format === f.key
                    ? 'border-accent-primary bg-accent-primary/10 ring-1 ring-accent-primary/30'
                    : 'border-border hover:border-border-hover hover:bg-bg-secondary'
                )}
              >
                <span className={cn(
                  'text-sm font-semibold',
                  format === f.key ? 'text-accent-primary' : 'text-text-primary'
                )}>
                  {f.label}
                </span>
                <span className="text-xs text-text-tertiary mt-0.5">
                  {t(f.description)}
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* Options — hidden for key-only export */}
        {!isKeyOnly && (
        <div className="space-y-2">
          <label className="text-xs font-medium text-text-secondary uppercase tracking-wide">
            {t('export.options', 'Options')}
          </label>

          {/* Include chain */}
          <label className="flex items-center gap-2.5 px-3 py-2 rounded-lg hover:bg-bg-secondary transition-colors cursor-pointer">
            <input
              type="checkbox"
              checked={includeChain}
              onChange={(e) => setIncludeChain(e.target.checked)}
              className="w-4 h-4 rounded accent-accent-primary"
            />
            <div>
              <div className="text-sm text-text-primary">{t('export.includeChain', 'Include CA chain')}</div>
              <div className="text-xs text-text-tertiary">{t('export.includeChainDesc', 'Include issuing CA certificates')}</div>
            </div>
          </label>

          {/* Include private key — only if key exists AND user has permission */}
          {hasPrivateKey && canExportKey && !isPkcs12 && (
            <label className="flex items-center gap-2.5 px-3 py-2 rounded-lg hover:bg-bg-secondary transition-colors cursor-pointer">
              <input
                type="checkbox"
                checked={includeKey}
                onChange={(e) => setIncludeKey(e.target.checked)}
                className="w-4 h-4 rounded accent-accent-primary"
              />
              <div>
                <div className="text-sm text-text-primary">{t('export.includeKey', 'Include private key')}</div>
                <div className="text-xs text-text-tertiary">{t('export.includeKeyDesc', 'Attach the private key to the export')}</div>
              </div>
            </label>
          )}

          {/* PKCS12 note */}
          {isPkcs12 && (
            <div className="flex items-center gap-2 px-3 py-1.5 text-xs text-text-secondary">
              <Lock size={14} className="shrink-0" />
              {t('export.pkcs12Note', 'PKCS#12 always includes the private key')}
            </div>
          )}

          {/* No key notice for viewers */}
          {hasPrivateKey && !canExportKey && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-bg-secondary text-xs text-text-tertiary">
              <Lock size={14} className="shrink-0" />
              {t('export.noKeyPermission', 'Private key export requires elevated permissions')}
            </div>
          )}
        </div>
        )}

        {/* Password field — required for PKCS12, optional for key export */}
        {showPasswordField && (
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-text-secondary uppercase tracking-wide">
              {t('export.password', 'Password')}
              {!needsPassword && <span className="ml-1 text-text-tertiary font-normal normal-case">({t('common.optional', 'optional')})</span>}
            </label>
            <div className="relative">
              <Lock size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={t('export.passwordPlaceholder', 'Min. 4 characters')}
                autoFocus
                className={cn(
                  'w-full h-9 pl-9 pr-3 text-sm rounded-lg border border-border bg-bg-primary text-text-primary',
                  'placeholder:text-text-tertiary focus:outline-none focus:ring-1 focus:ring-accent-primary/50 focus:border-accent-primary'
                )}
              />
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-end gap-2 pt-4 border-t border-border">
          <Button type="button" variant="secondary" onClick={onClose}>
            {t('common.cancel', 'Cancel')}
          </Button>
          <Button
            type="submit"
            disabled={exporting || (needsPassword && password.length < 4)}
          >
            <Download size={16} />
            {exporting ? t('common.exporting', 'Exporting...') : t('export.download', 'Download')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
