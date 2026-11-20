/**
 * ExportModal: the mockup's export dialog for certificates and CAs: formats with a radio
 * button, one-line options, the password of PKCS#12 and JKS, a structure preview, notices.
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
 *     keyAlgorithm="ML-DSA-65"   // greys out the formats that key cannot use
 *     relatedCertificateId={12}  // member of a hybrid pair: adds the 'hybrid-bundle' ZIP
 *     onExport={(format, options) => handleExport(format, options)}
 *   />
 */
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Download, Lock } from '@phosphor-icons/react'
import { Modal } from './Modal'
import { Button } from './Button'
import { ChainVariantSelect } from './ChainVariantSelect'
import { cn, extractData } from '../lib/utils'
import { certificatesService } from '../services'
import { fetchChainVariants } from '../lib/crossCertificates'
import { exportPasswordPolicy, isExportPasswordValid, loadExportPasswordPolicy } from '../lib/exportPassword'
import { isExportFormatAllowed } from '../lib/keyAlgorithms'
import './certificateDialogs.css'

const FORMATS = [
  { key: 'pem', label: 'PEM', description: 'export.formatPemDesc', ext: '.pem' },
  { key: 'der', label: 'DER', description: 'export.formatDerDesc', ext: '.der' },
  { key: 'pkcs7', label: 'PKCS#7', description: 'export.formatP7bDesc', ext: '.p7b' },
  { key: 'pkcs12', label: 'PKCS#12', description: 'export.formatP12Desc', ext: '.p12', requiresKey: true },
  { key: 'jks', label: 'JKS', description: 'export.formatJksDesc', ext: '.jks', requiresKey: true },
  { key: 'key', labelKey: 'export.formats.privateKey', description: 'export.formatKeyDesc', ext: '.key', requiresKey: true, keyOnly: true },
  // Both certificates of a hybrid pair (RFC 9763), and both keys when included
  { key: 'hybrid-bundle', labelKey: 'export.formats.hybridBundle', description: 'export.formatHybridBundleDesc', ext: '.zip', requiresRelated: true },
]

const RELATED_KEY_UNKNOWN = 'unknown'

export function ExportModal({
  open,
  onClose,
  entityType = 'certificate',
  entityName = '',
  hasPrivateKey = false,
  canExportKey = false,
  isHsmBacked = false,
  keyAlgorithm = null,
  defaultFormat = 'pem',
  relatedCertificateId = null,
  onExport,
  chainVariantsFor,
}) {
  const { t } = useTranslation()
  const [format, setFormat] = useState('pem')
  const [includeChain, setIncludeChain] = useState(true)
  const [includeRoot, setIncludeRoot] = useState(false)
  const [includeKey, setIncludeKey] = useState(false)
  const [password, setPassword] = useState('')
  // PKCS#12 compatibility profile (3DES/SHA-1) for importers that reject the
  // AES-256/SHA-256 default as a wrong password (#331); per-export, off by default
  const [legacy, setLegacy] = useState(false)
  const [exporting, setExporting] = useState(false)
  // Chains a cross-certificate makes possible (#400); empty when there is no choice
  const [chainVariants, setChainVariants] = useState([])
  const [chainVariant, setChainVariant] = useState('auto')

  const isAllowed = (key) => isExportFormatAllowed(keyAlgorithm, key)

  // The bundle carries both keys: offered when the related certificate has one too (null: loading).
  // A failed lookup leaves the option on: the server refuses a bundle with a missing key.
  const [relatedHasKey, setRelatedHasKey] = useState(null)
  useEffect(() => {
    setRelatedHasKey(null)
    if (!open || relatedCertificateId == null || !hasPrivateKey || !canExportKey) return undefined
    let cancelled = false
    certificatesService.getById(relatedCertificateId)
      .then((res) => { if (!cancelled) setRelatedHasKey(extractData(res)?.has_private_key === true) })
      .catch(() => { if (!cancelled) setRelatedHasKey(RELATED_KEY_UNKNOWN) })
    return () => { cancelled = true }
  }, [open, relatedCertificateId, hasPrivateKey, canExportKey])

  // Reset state when modal opens
  useEffect(() => {
    if (open) {
      setFormat(isAllowed(defaultFormat) ? defaultFormat : 'pem')
      setIncludeChain(true)
      setIncludeRoot(false)
      setIncludeKey(false)
      setPassword('')
      setLegacy(false)
      setExporting(false)
      setChainVariant('auto')
    }
  }, [open, defaultFormat, keyAlgorithm])

  useEffect(() => {
    setChainVariants([])
    if (!open || !chainVariantsFor?.id) return undefined
    let cancelled = false
    fetchChainVariants(chainVariantsFor)
      .then((variants) => { if (!cancelled) setChainVariants(Array.isArray(variants) ? variants : []) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [open, chainVariantsFor?.type, chainVariantsFor?.id])

  // PKCS12 always includes key — sync state
  const isPkcs12 = format === 'pkcs12'
  const isJks = format === 'jks'
  const isKeyOnly = format === 'key'
  const isBundle = format === 'hybrid-bundle'
  // DER holds one certificate; P7B holds certificates only (the server refuses the rest)
  const carriesChain = !isBundle && format !== 'der'
  const carriesKey = format !== 'der' && format !== 'pkcs7'
  const keyOffered = hasPrivateKey && canExportKey
    && (!isBundle || relatedHasKey === true || relatedHasKey === RELATED_KEY_UNKNOWN)
  const effectiveIncludeKey = (isPkcs12 || isJks || isKeyOnly) ? true : includeKey && keyOffered && carriesKey
  const needsPassword = isPkcs12 || isJks
  const showPasswordField = isPkcs12 || isJks

  // The rule belongs to the server (utils/export_password): this dialog
  // serves certificates and CAs, whose routes used to apply two different
  // ones, and it agreed with neither.
  const [passwordPolicy, setPasswordPolicy] = useState(exportPasswordPolicy())
  useEffect(() => {
    let cancelled = false
    loadExportPasswordPolicy().then((policy) => {
      if (!cancelled) setPasswordPolicy(policy)
    })
    return () => { cancelled = true }
  }, [])

  // Available formats: hide PKCS12 if no key or no permission
  const availableFormats = FORMATS.filter(f => {
    if (f.requiresRelated) return relatedCertificateId != null
    if (f.requiresKey) return hasPrivateKey && canExportKey
    return true
  })
  const unavailableReason = t('export.unavailableForKeyAlgorithm', { algorithm: keyAlgorithm })
  const hasUnavailable = availableFormats.some(f => !isAllowed(f.key))

  const handleExport = async () => {
    if (needsPassword && !isExportPasswordValid(password, passwordPolicy)) return
    setExporting(true)
    try {
      await onExport(format, {
        includeChain: includeChain && carriesChain,
        includeRoot: includeRoot && carriesChain,
        includeKey: effectiveIncludeKey,
        password: (isPkcs12 || isJks) ? password : undefined,
        legacy: isPkcs12 ? legacy : undefined,
        chainVariant: includeChain && carriesChain && chainVariant !== 'auto' ? chainVariant : undefined,
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

  // What the file will hold, line by line, as the mockup's structure preview
  const formatLabel = (f) => (f.labelKey ? t(f.labelKey) : f.label)
  const current = availableFormats.find(f => f.key === format) || FORMATS[0]
  const previewLines = [
    entityName || null,
    isBundle ? `  ${t('export.previewRelated')}` : null,
    includeChain && carriesChain && !isKeyOnly ? `  ${t('export.previewChain')}` : null,
    includeChain && carriesChain && includeRoot && !isKeyOnly && entityType === 'certificate' ? `  ${t('export.previewRoot')}` : null,
    effectiveIncludeKey ? `  ${t(needsPassword ? 'export.previewKeyEncrypted' : 'export.previewKey')}` : null,
  ].filter(Boolean)
  const preview = [t('export.previewTitle', { format: formatLabel(current) }), '', ...previewLines].join('\n')
  const check = (checked, onChange, label, desc, extra = {}) => (
    <label className={cn('ui-check-line', desc && 'has-desc')}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} {...extra} />
      {desc ? <span className="ui-check-text">{label}<small>{desc}</small></span> : label}
    </label>
  )

  return (
    <Modal open={open} onClose={() => onClose()} title={t(entityType === 'ca' ? 'export.titleCa' : 'export.titleCertificate')} size="md"
      className="ui-export-dialog">
      <form onSubmit={(e) => { e.preventDefault(); handleExport() }}>
        {entityName && <p className="ui-export-name">{entityName}</p>}

        {/* Formats: labels with a radio button, three columns */}
        <div className="ui-format-grid" role="radiogroup" aria-label={t('export.format', 'Format')}>
          {availableFormats.map(f => (
            <label key={f.key} className="ui-format-option" title={isAllowed(f.key) ? undefined : unavailableReason}>
              <input type="radio" name="export-format" value={f.key} checked={format === f.key}
                disabled={!isAllowed(f.key)} onChange={() => { if (isAllowed(f.key)) setFormat(f.key) }} />
              <span>{formatLabel(f)}<small>{t(f.description)}</small></span>
            </label>
          ))}
        </div>

        {/* Options: one line each; key-only and DER carry none */}
        {!isKeyOnly && format !== 'der' && (
          <div className="ui-export-options">
            {carriesChain && check(includeChain, setIncludeChain, t('export.includeChain', 'Include CA chain'))}
            {/* Which chain to present when a cross-certificate offers another path (#400) */}
            {carriesChain && includeChain && chainVariants.length > 1 && (
              <div className="ui-export-variant">
                <label htmlFor="export-chain-variant" className="ui-label">{t('chainVariant.label')}</label>
                <ChainVariantSelect id="export-chain-variant" variants={chainVariants} value={chainVariant} onChange={setChainVariant} />
                <p className="ui-help">{t('chainVariant.exportHint')}</p>
              </div>
            )}
            {/* Root trust anchors are normally installed on clients, not served. */}
            {carriesChain && entityType === 'certificate' && includeChain && (
              <div className="ui-export-sub">
                {check(includeRoot, setIncludeRoot, t('export.includeRoot', 'Include Root CA'), t('export.includeRootDesc', 'Usually unnecessary for TLS servers'))}
              </div>
            )}
            {/* Include private key: only if key exists AND user has permission */}
            {keyOffered && carriesKey && !isPkcs12 && !isJks && check(includeKey, setIncludeKey, t('export.includeKey', 'Include private key'))}
            {/* PKCS12 compatibility profile (#331) */}
            {isPkcs12 && check(legacy, setLegacy, t('export.legacyPkcs12'), t('export.legacyPkcs12Desc'), { 'data-testid': 'export-legacy-pkcs12' })}
          </div>
        )}

        {/* Password field: required for PKCS12 and JKS */}
        {showPasswordField && (
          <div className="ui-field">
            <label htmlFor="export-password" className="ui-label">{t('export.password', 'Password')}</label>
            <input
              id="export-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={t('export.passwordLengthHint', {
                defaultValue: 'Between {{min}} and {{max}} characters',
                min: passwordPolicy.min_length,
                max: passwordPolicy.max_length,
              })}
              autoComplete="new-password"
              autoFocus
              className="ui-control"
            />
          </div>
        )}

        <pre className="ui-code-preview" data-testid="export-preview">{preview}</pre>

        {/* Notices of the mockup: why a format is greyed, what the file always holds, what is withheld */}
        {hasUnavailable && <div className="ui-notice"><Lock size={14} aria-hidden="true" />{unavailableReason}</div>}
        {!isKeyOnly && format !== 'der' && isBundle && hasPrivateKey && canExportKey && relatedHasKey === false && (
          <div className="ui-notice"><Lock size={14} aria-hidden="true" />{t('export.bundleRelatedHasNoKey')}</div>
        )}
        {(isPkcs12 || isJks) && (
          <div className="ui-notice">
            <Lock size={14} aria-hidden="true" />
            {isPkcs12 ? t('export.pkcs12Note', 'PKCS#12 always includes the private key') : t('export.jksNote', 'JKS always includes the private key')}
          </div>
        )}
        {!isKeyOnly && format !== 'der' && hasPrivateKey && !canExportKey && (
          <div className="ui-notice"><Lock size={14} aria-hidden="true" />{t('export.noKeyPermission', 'Private key export requires elevated permissions')}</div>
        )}
        {!isKeyOnly && format !== 'der' && isHsmBacked && (
          <div className="ui-notice"><Lock size={14} aria-hidden="true" />{t('cas.detail.exportBlockedHsm', 'HSM-backed key cannot be exported')}</div>
        )}

        <div className="ui-dialog-actions">
          <Button type="button" variant="secondary" onClick={onClose}>
            {t('common.cancel', 'Cancel')}
          </Button>
          <Button type="submit" disabled={exporting || (needsPassword && !isExportPasswordValid(password, passwordPolicy))}>
            <Download size={16} aria-hidden="true" />
            {exporting ? t('common.exporting', 'Exporting...') : t('export.download', 'Download')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
