/**
 * CertificateInput — Unified certificate/key input component
 * 
 * Three input modes:
 * 1. Paste PEM text directly
 * 2. Upload a file (PEM, DER, PFX, P7B — auto-detected)
 * 3. Select from managed certificates
 * 
 * Uses the SmartImport analyze API for file parsing.
 */
import { useState, useRef, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { 
  TextAlignLeft, UploadSimple, Certificate, LockSimple,
  CheckCircle, X, File
} from '@phosphor-icons/react'
import { Button } from './Button'
import { Textarea } from './Textarea'
import { SelectComponent as Select } from './Select'
import { cn } from '../lib/utils'
import { apiClient as api, certificatesService } from '../services'

const ACCEPT_FORMATS = '.pem,.crt,.cer,.key,.csr,.der,.p12,.pfx,.p7b,.p7c'
const BINARY_EXTS = ['.der', '.p12', '.pfx']

const MODES = [
  { key: 'paste', icon: TextAlignLeft, labelKey: 'certInput.modePaste' },
  { key: 'upload', icon: UploadSimple, labelKey: 'certInput.modeUpload' },
  { key: 'managed', icon: Certificate, labelKey: 'certInput.modeManaged' },
]

export function CertificateInput({
  label,
  value = { cert_pem: '', key_pem: '' },
  onChange,
  requireKey = false,
  showKeyField = true,
  certLabel,
  keyLabel,
  className,
}) {
  const { t } = useTranslation()
  const [mode, setMode] = useState('paste')
  const [uploading, setUploading] = useState(false)
  const [uploadedFile, setUploadedFile] = useState(null)
  const [filePassword, setFilePassword] = useState('')
  const [needsPassword, setNeedsPassword] = useState(false)
  const [managedCerts, setManagedCerts] = useState(null)
  const [loadingCerts, setLoadingCerts] = useState(false)
  const [isDragOver, setIsDragOver] = useState(false)
  const fileInputRef = useRef(null)

  // Load managed certificates on demand
  const loadManagedCerts = useCallback(async () => {
    if (managedCerts) return
    setLoadingCerts(true)
    try {
      const resp = await certificatesService.getAll({ has_key: requireKey ? true : undefined, limit: 500 })
      const certs = resp.data || resp || []
      setManagedCerts(certs)
    } catch {
      setManagedCerts([])
    } finally {
      setLoadingCerts(false)
    }
  }, [managedCerts, requireKey])

  const handleModeChange = (newMode) => {
    setMode(newMode)
    if (newMode === 'managed') loadManagedCerts()
  }

  // File upload + auto-parse via SmartImport analyze API
  const handleFile = useCallback(async (file, password = '') => {
    const ext = '.' + file.name.split('.').pop().toLowerCase()
    const isBinary = BINARY_EXTS.includes(ext)

    setUploading(true)
    try {
      let fileData
      if (isBinary) {
        const buffer = await file.arrayBuffer()
        fileData = btoa(String.fromCharCode(...new Uint8Array(buffer)))
      } else {
        fileData = await file.text()
      }

      const payload = {
        files: [{ name: file.name, type: isBinary ? 'binary' : 'text', data: fileData }],
      }
      if (password) payload.password = password

      const result = await api.post('/import/analyze', payload)
      const objects = result.data?.objects || []

      const cert = objects.find(o => o.type === 'certificate' && !o.is_ca)
        || objects.find(o => o.type === 'certificate')
      const key = objects.find(o => o.type === 'private_key')

      if (!cert && !key) {
        // Maybe needs password (PKCS12)
        if (ext === '.p12' || ext === '.pfx') {
          setNeedsPassword(true)
          setUploadedFile(file)
          return
        }
        throw new Error(t('certInput.parseError'))
      }

      const newValue = {
        cert_pem: cert?.pem || value.cert_pem || '',
        key_pem: key?.pem || value.key_pem || '',
      }
      onChange(newValue)
      setUploadedFile({ name: file.name, parsed: true })
      setNeedsPassword(false)
    } catch (err) {
      // If error mentions password/encrypted, prompt for password
      if (err.message?.includes('password') || err.message?.includes('encrypt') || err.message?.includes('MAC')) {
        setNeedsPassword(true)
        setUploadedFile(file)
      } else {
        onChange({ cert_pem: '', key_pem: '' })
        setUploadedFile({ name: file.name, error: err.message || t('certInput.parseError') })
      }
    } finally {
      setUploading(false)
    }
  }, [onChange, value, t])

  // Handle password submit for encrypted files
  const handlePasswordSubmit = async () => {
    if (uploadedFile instanceof File) {
      await handleFile(uploadedFile, filePassword)
    }
  }

  // Drag & drop
  const handleDragOver = useCallback((e) => { e.preventDefault(); setIsDragOver(true) }, [])
  const handleDragLeave = useCallback((e) => { e.preventDefault(); setIsDragOver(false) }, [])
  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setIsDragOver(false)
    if (e.dataTransfer.files?.[0]) handleFile(e.dataTransfer.files[0])
  }, [handleFile])

  // Select managed cert — get cert PEM from detail, key PEM from export
  const handleSelectManaged = async (certId) => {
    if (!certId) {
      onChange({ cert_pem: '', key_pem: '' })
      return
    }
    try {
      const resp = await certificatesService.getById(certId)
      const cert = resp.data || resp
      const certPem = cert.pem || ''

      // Try to get private key via export endpoint
      let keyPem = ''
      if (cert.has_private_key) {
        try {
          const blob = await certificatesService.export(certId, 'key')
          keyPem = await blob.text()
        } catch {
          // No permission or export failed — that's OK
        }
      }

      onChange({ cert_pem: certPem.trim(), key_pem: keyPem.trim() })
    } catch {
      onChange({ cert_pem: '', key_pem: '' })
    }
  }

  const effectiveCertLabel = certLabel || label || t('certInput.certificate')
  const effectiveKeyLabel = keyLabel || t('certInput.privateKey')

  return (
    <div className={cn('space-y-3', className)}>
      {/* Mode switcher */}
      <div className="flex gap-1 p-0.5 rounded-lg bg-bg-secondary">
        {MODES.map(m => {
          const Icon = m.icon
          return (
            <button
              key={m.key}
              type="button"
              onClick={() => handleModeChange(m.key)}
              className={cn(
                'flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 rounded-md text-xs font-medium transition-all',
                mode === m.key
                  ? 'bg-bg-primary text-text-primary shadow-sm'
                  : 'text-text-tertiary hover:text-text-secondary'
              )}
            >
              <Icon size={14} />
              {t(m.labelKey)}
            </button>
          )
        })}
      </div>

      {/* Mode: Paste PEM */}
      {mode === 'paste' && (
        <div className="space-y-3">
          <Textarea
            label={effectiveCertLabel}
            value={value.cert_pem}
            onChange={(e) => onChange({ ...value, cert_pem: e.target.value })}
            rows={4}
            placeholder="-----BEGIN CERTIFICATE-----"
            className="font-mono text-xs"
          />
          {showKeyField && (
            <Textarea
              label={effectiveKeyLabel}
              value={value.key_pem}
              onChange={(e) => onChange({ ...value, key_pem: e.target.value })}
              rows={4}
              placeholder="-----BEGIN PRIVATE KEY-----"
              className="font-mono text-xs"
            />
          )}
        </div>
      )}

      {/* Mode: Upload file */}
      {mode === 'upload' && (
        <div className="space-y-3">
          {/* Drop zone */}
          {!uploadedFile?.parsed && (
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={cn(
                'flex flex-col items-center gap-2 p-6 border-2 border-dashed rounded-lg cursor-pointer transition-colors',
                isDragOver
                  ? 'border-accent-primary bg-accent-primary-op5'
                  : 'border-border hover:border-border-hover hover:bg-bg-secondary'
              )}
            >
              <UploadSimple size={24} className="text-text-tertiary" />
              <div className="text-sm text-text-secondary text-center">
                {uploading ? t('certInput.analyzing') : t('certInput.dropOrClick')}
              </div>
              <div className="text-xs text-text-tertiary">
                PEM, DER, PKCS#12/PFX, P7B
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept={ACCEPT_FORMATS}
                onChange={(e) => { if (e.target.files?.[0]) handleFile(e.target.files[0]); e.target.value = '' }}
                className="hidden"
              />
            </div>
          )}

          {/* Password prompt for encrypted files */}
          {needsPassword && (
            <div className="flex gap-2 items-end">
              <div className="flex-1">
                <label className="text-xs font-medium text-text-secondary mb-1 block">
                  <LockSimple size={12} className="inline mr-1" />
                  {t('certInput.filePassword')}
                </label>
                <input
                  type="password"
                  value={filePassword}
                  onChange={(e) => setFilePassword(e.target.value)}
                  placeholder={t('certInput.enterPassword')}
                  className="w-full h-8 px-3 text-sm rounded-md border border-border bg-bg-primary text-text-primary"
                  onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handlePasswordSubmit() } }}
                />
              </div>
              <Button type="button" size="sm" onClick={handlePasswordSubmit} disabled={!filePassword}>
                {t('common.ok')}
              </Button>
            </div>
          )}

          {/* Upload result */}
          {uploadedFile?.parsed && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-bg-secondary">
              <CheckCircle size={16} className="text-green-500 shrink-0" />
              <File size={14} className="text-text-tertiary shrink-0" />
              <span className="text-sm text-text-primary flex-1 truncate">{uploadedFile.name}</span>
              <button
                type="button"
                onClick={() => { setUploadedFile(null); setNeedsPassword(false); setFilePassword(''); onChange({ cert_pem: '', key_pem: '' }) }}
                className="text-text-tertiary hover:text-text-primary"
              >
                <X size={14} />
              </button>
            </div>
          )}

          {uploadedFile?.error && (
            <div className="text-xs text-red-500 px-1">{uploadedFile.error}</div>
          )}

          {/* Show parsed PEM preview (read-only) */}
          {uploadedFile?.parsed && value.cert_pem && (
            <div className="space-y-2">
              <div className="text-xs text-text-tertiary">{effectiveCertLabel}</div>
              <pre className="text-xs font-mono text-text-secondary bg-bg-secondary rounded p-2 max-h-20 overflow-auto">
                {value.cert_pem.substring(0, 200)}...
              </pre>
              {value.key_pem && (
                <>
                  <div className="text-xs text-text-tertiary">{effectiveKeyLabel}</div>
                  <div className="text-xs text-green-600 flex items-center gap-1">
                    <LockSimple size={12} /> {t('certInput.keyExtracted')}
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {/* Mode: Select managed cert */}
      {mode === 'managed' && (
        <div className="space-y-3">
          <Select
            label={t('certInput.selectCertificate')}
            value=""
            onChange={(certId) => handleSelectManaged(certId)}
            options={[
              { value: '', label: t('certInput.chooseCertificate') },
              ...(managedCerts || []).map(c => ({
                value: String(c.id),
                label: `${c.common_name || c.subject || c.descr || `#${c.id}`}${c.has_private_key ? ' 🔑' : ''}`,
              }))
            ]}
            disabled={loadingCerts}
          />
          {loadingCerts && (
            <div className="text-xs text-text-tertiary">{t('common.loading')}...</div>
          )}
          {/* Show what was selected */}
          {value.cert_pem && (
            <div className="space-y-1">
              <div className="flex items-center gap-1 text-xs text-green-600">
                <CheckCircle size={12} /> {t('certInput.certLoaded')}
              </div>
              {value.key_pem && (
                <div className="flex items-center gap-1 text-xs text-green-600">
                  <LockSimple size={12} /> {t('certInput.keyLoaded')}
                </div>
              )}
            </div>
          )}
          {requireKey && managedCerts && !loadingCerts && managedCerts.length === 0 && (
            <div className="text-xs text-text-tertiary">{t('certInput.noCertsWithKey')}</div>
          )}
        </div>
      )}
    </div>
  )
}

export default CertificateInput
