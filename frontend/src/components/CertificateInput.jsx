/**
 * The certificate and key a connection presents, in the mockup's form vocabulary: its source in a
 * `.segmented` field (paste the PEM, read a file, or take a managed certificate), the PEM in monospace
 * textareas, the file as « Choisir un fichier… » (or dropped on the field), what was read in a status line.
 * Its fields are `.field.full`, for the two-column grid of the form that holds it.
 * Files are read by the SmartImport analyze API.
 */
import { useState, useCallback, useId } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from './atelier/Icon'
import { Input, Select, Textarea, Notice, SegmentedField } from './atelier/Form'
import { certificateLabel } from '../lib/utils'
import { fetchAllPages } from '../lib/fetchAllPages'
import { apiClient as api, certificatesService } from '../services'

const ACCEPT_FORMATS = '.pem,.crt,.cer,.key,.csr,.der,.p12,.pfx,.p7b,.p7c'
const BINARY_EXTS = ['.der', '.p12', '.pfx']

// Server-side cap on /certificates, and the ceiling the dropdown pages up to
const MANAGED_PER_PAGE = 100
const MANAGED_MAX_CERTS = 500

const MODES = [
  { key: 'paste', labelKey: 'certInput.modePaste' },
  { key: 'upload', labelKey: 'certInput.modeUpload' },
  { key: 'managed', labelKey: 'certInput.modeManaged' },
]

export function CertificateInput({
  label,
  value = { cert_pem: '', key_pem: '' },
  onChange,
  requireKey = false,
  showKeyField = true,
  certLabel,
  keyLabel,
}) {
  const { t } = useTranslation()
  const [mode, setMode] = useState('paste')
  const [uploading, setUploading] = useState(false)
  const [uploadedFile, setUploadedFile] = useState(null)
  const [filePassword, setFilePassword] = useState('')
  const [needsPassword, setNeedsPassword] = useState(false)
  const [managedCerts, setManagedCerts] = useState(null)
  const [loadingCerts, setLoadingCerts] = useState(false)
  const fid = useId()

  // Load managed certificates on demand, walking the pages: the listing
  // pages on `per_page` (100 max) and filters on `has_private_key` itself.
  const loadManagedCerts = useCallback(async () => {
    if (managedCerts) return
    setLoadingCerts(true)
    try {
      const getPage = requireKey
        ? (query) => certificatesService.getAll({ ...query, has_private_key: true })
        : certificatesService.getAll
      const certs = await fetchAllPages(getPage, { perPage: MANAGED_PER_PAGE, max: MANAGED_MAX_CERTS })
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
      let content
      if (isBinary) {
        const bytes = new Uint8Array(await file.arrayBuffer())
        let binary = ''
        for (let i = 0; i < bytes.length; i += 0x8000) {
          binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000))
        }
        content = btoa(binary)
      } else {
        content = await file.text()
      }

      // The route reads `content` (text or base64) and returns each `pem` only on request
      const payload = { content, include_pem: true }
      if (password) payload.password = password

      const result = await api.post('/import/analyze', payload)
      const objects = result.data?.objects || []

      const cert = objects.find(o => o.type === 'certificate' && !o.is_ca)
        || objects.find(o => o.type === 'certificate')
      const key = objects.find(o => o.type === 'private_key')

      // A sealed key comes back without its PEM: ask for the password, or report a wrong one
      if (key && !key.pem) {
        if (key.error && password) throw new Error(key.error)
        setNeedsPassword(true)
        setUploadedFile(file)
        return
      }

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

  // A file dropped on the file field is read as one picked
  const handleDrop = useCallback((e) => {
    const file = e.dataTransfer?.files?.[0]
    if (file) { e.preventDefault(); handleFile(file) }
  }, [handleFile])

  const removeFile = () => { setUploadedFile(null); setNeedsPassword(false); setFilePassword(''); onChange({ cert_pem: '', key_pem: '' }) }

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
    <>
      <SegmentedField id={`${fid}-source`} label={t('certInput.source')} options={MODES.map(m => ({ value: m.key, label: t(m.labelKey) }))}
        pressed={(v) => mode === v} onPick={handleModeChange} />

      {mode === 'paste' && (
        <>
          <Textarea id={`${fid}-cert`} label={effectiveCertLabel} mono rows={4} spellCheck={false} placeholder="-----BEGIN CERTIFICATE-----"
            value={value.cert_pem} onChange={(e) => onChange({ ...value, cert_pem: e.target.value })} />
          {showKeyField && (
            <Textarea id={`${fid}-key`} label={effectiveKeyLabel} mono rows={4} spellCheck={false} placeholder="-----BEGIN PRIVATE KEY-----"
              value={value.key_pem} onChange={(e) => onChange({ ...value, key_pem: e.target.value })} />
          )}
        </>
      )}

      {mode === 'upload' && (
        <>
          <div className="field full" onDragOver={(e) => { if (e.dataTransfer?.types?.includes?.('Files')) e.preventDefault() }} onDrop={handleDrop}>
            <span>{effectiveCertLabel}</span>
            {uploadedFile?.parsed ? (
              <p className="group-hint" role="status">
                <Icon name="check" /> {uploadedFile.name}{' '}
                <button type="button" className="text-link" onClick={removeFile}>{t('tools.removeFile')}</button>
              </p>
            ) : (
              <span className="row-actions">
                <label className="text-link">
                  <input type="file" accept={ACCEPT_FORMATS} className="sr-only"
                    onChange={(e) => { if (e.target.files?.[0]) handleFile(e.target.files[0]); e.target.value = '' }} />
                  {t('common.chooseFile')}
                </label>
              </span>
            )}
            <small aria-live="polite">{uploading ? t('certInput.analyzing') : 'PEM, DER, PKCS#12/PFX, P7B'}</small>
          </div>

          {needsPassword && (
            <div className="field full">
              <div className="settings-actions">
                <Input id={`${fid}-password`} type="password" label={t('certInput.filePassword')} placeholder={t('certInput.enterPassword')}
                  value={filePassword} onChange={(e) => setFilePassword(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handlePasswordSubmit() } }} />
                <button type="button" className="btn" onClick={handlePasswordSubmit} disabled={!filePassword}>{t('common.ok')}</button>
              </div>
            </div>
          )}

          {uploadedFile?.error && <Notice tone="bad">{uploadedFile.error}</Notice>}

          {uploadedFile?.parsed && value.cert_pem && (
            <div className="field full">
              <span>{effectiveCertLabel}</span>
              <pre className="code-preview">{value.cert_pem.substring(0, 200)}...</pre>
              {value.key_pem && <small><Icon name="lock" /> {t('certInput.keyExtracted')}</small>}
            </div>
          )}
        </>
      )}

      {mode === 'managed' && (
        <Select id={`${fid}-managed`} full label={t('certInput.selectCertificate')} value="" disabled={loadingCerts}
          onChange={(certId) => handleSelectManaged(certId)}
          hint={loadingCerts ? t('common.loading')
            : requireKey && managedCerts && managedCerts.length === 0 ? t('certInput.noCertsWithKey')
            : value.cert_pem ? [t('certInput.certLoaded'), value.key_pem && t('certInput.keyLoaded')].filter(Boolean).join(' · ') : undefined}
          options={[
            { value: '', label: t('certInput.chooseCertificate') },
            ...(managedCerts || []).map(c => ({
              value: String(c.id),
              label: `${certificateLabel(c) || c.subject || `#${c.id}`}${c.key_type ? ` (${c.key_type})` : ''}${c.has_private_key ? ' 🔑' : ''}`,
            })),
          ]} />
      )}
    </>
  )
}

export default CertificateInput
