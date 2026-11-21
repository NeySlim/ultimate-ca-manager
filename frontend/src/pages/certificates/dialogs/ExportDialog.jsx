/**
 * The mockup's exportDialog(): the name, the formats as cards with a radio button, « Inclure la
 * chaîne de certification », the password of a format that carries the key, the structure
 * preview, the notices, Annuler and Télécharger. The product's formats (PKCS#7, JKS, the key
 * alone, the hybrid bundle) and options (the root, the key, the compatibility profile, the chain
 * variant) take the same pieces. Same props as components/ExportModal.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AtelierDialog, Icon } from '../../../components/atelier'
import { variantLabel } from '../../../components/ChainVariantSelect'
import { extractData } from '../../../lib/utils'
import { certificatesService } from '../../../services'
import { fetchChainVariants } from '../../../lib/crossCertificates'
import { exportPasswordPolicy, isExportPasswordValid, loadExportPasswordPolicy } from '../../../lib/exportPassword'
import { isExportFormatAllowed } from '../../../lib/keyAlgorithms'

const FORMATS = [
  { key: 'pem', label: 'PEM', description: 'export.formatPemDesc' },
  { key: 'der', label: 'DER', description: 'export.formatDerDesc' },
  { key: 'pkcs12', label: 'PKCS#12', description: 'export.formatP12Desc', requiresKey: true },
  { key: 'pkcs7', label: 'PKCS#7', description: 'export.formatP7bDesc' },
  { key: 'jks', label: 'JKS', description: 'export.formatJksDesc', requiresKey: true },
  { key: 'key', labelKey: 'export.formats.privateKey', description: 'export.formatKeyDesc', requiresKey: true },
  { key: 'hybrid-bundle', labelKey: 'export.formats.hybridBundle', description: 'export.formatHybridBundleDesc', requiresRelated: true },
]
const UNKNOWN = 'unknown'

export function ExportDialog({
  open, onClose, entityType = 'certificate', entityName = '', hasPrivateKey = false, canExportKey = false, isHsmBacked = false,
  keyAlgorithm = null, defaultFormat = 'pem', relatedCertificateId = null, onExport, chainVariantsFor,
}) {
  if (!open) return null
  return (
    <ExportBody onClose={onClose} entityType={entityType} entityName={entityName} hasPrivateKey={hasPrivateKey} canExportKey={canExportKey}
      isHsmBacked={isHsmBacked} keyAlgorithm={keyAlgorithm} defaultFormat={defaultFormat} relatedCertificateId={relatedCertificateId}
      onExport={onExport} chainVariantsFor={chainVariantsFor} />
  )
}

function ExportBody({ onClose, entityType, entityName, hasPrivateKey, canExportKey, isHsmBacked, keyAlgorithm, defaultFormat, relatedCertificateId, onExport, chainVariantsFor }) {
  const { t } = useTranslation()
  const allowed = (key) => isExportFormatAllowed(keyAlgorithm, key)
  const [format, setFormat] = useState(allowed(defaultFormat) ? defaultFormat : 'pem')
  const [includeChain, setIncludeChain] = useState(true)
  const [includeRoot, setIncludeRoot] = useState(false)
  const [includeKey, setIncludeKey] = useState(false)
  const [password, setPassword] = useState('')
  const [legacy, setLegacy] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [variants, setVariants] = useState([])
  const [variant, setVariant] = useState('auto')
  const [relatedHasKey, setRelatedHasKey] = useState(null)
  const [policy, setPolicy] = useState(exportPasswordPolicy())

  useEffect(() => {
    let cancelled = false
    loadExportPasswordPolicy().then((p) => { if (!cancelled) setPolicy(p) })
    return () => { cancelled = true }
  }, [])
  // The bundle carries both keys: offered when the linked certificate has one too (a failed lookup leaves it to the server)
  useEffect(() => {
    if (relatedCertificateId == null || !hasPrivateKey || !canExportKey) return undefined
    let cancelled = false
    certificatesService.getById(relatedCertificateId)
      .then((res) => { if (!cancelled) setRelatedHasKey(extractData(res)?.has_private_key === true) })
      .catch(() => { if (!cancelled) setRelatedHasKey(UNKNOWN) })
    return () => { cancelled = true }
  }, [relatedCertificateId, hasPrivateKey, canExportKey])
  useEffect(() => {
    if (!chainVariantsFor?.id) return undefined
    let cancelled = false
    fetchChainVariants(chainVariantsFor).then((v) => { if (!cancelled) setVariants(Array.isArray(v) ? v : []) }).catch(() => {})
    return () => { cancelled = true }
  }, [chainVariantsFor?.type, chainVariantsFor?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const withKey = format === 'pkcs12' || format === 'jks'
  const keyOnly = format === 'key'
  const bundle = format === 'hybrid-bundle'
  const carriesChain = !bundle && format !== 'der' && !keyOnly
  const carriesKey = format !== 'der' && format !== 'pkcs7'
  const keyOffered = hasPrivateKey && canExportKey && (!bundle || relatedHasKey === true || relatedHasKey === UNKNOWN)
  const effectiveKey = withKey || keyOnly ? true : includeKey && keyOffered && carriesKey
  const formats = FORMATS.filter((f) => (f.requiresRelated ? relatedCertificateId != null : true))
  // A format that needs the key stays listed, greyed, as the mockup's « Clé privée absente »
  const unavailable = (f) => (f.requiresKey && !(hasPrivateKey && canExportKey)) || !allowed(f.key)
  const why = (f) => {
    if (!allowed(f.key)) return t('export.unavailableForKeyAlgorithm', { algorithm: keyAlgorithm })
    if (f.requiresKey && !hasPrivateKey) return t('export.noPrivateKey')
    if (f.requiresKey && !canExportKey) return t('export.noKeyPermissionShort')
    return t(f.description)
  }
  const label = (f) => (f.labelKey ? t(f.labelKey) : f.label)
  const current = formats.find((f) => f.key === format) || formats[0]
  const lines = [
    entityName || null,
    bundle ? `  ${t('export.previewRelated')}` : null,
    includeChain && carriesChain ? `  ${t('export.previewChain')}` : null,
    includeChain && carriesChain && includeRoot && entityType === 'certificate' ? `  ${t('export.previewRoot')}` : null,
    effectiveKey ? `  ${t(withKey ? 'export.previewKeyEncrypted' : 'export.previewKey')}` : null,
  ].filter(Boolean)
  const valid = !withKey || isExportPasswordValid(password, policy)

  const submit = async () => {
    if (!valid || exporting) return
    setExporting(true)
    try {
      await onExport(format, {
        includeChain: includeChain && carriesChain,
        includeRoot: includeRoot && carriesChain,
        includeKey: effectiveKey,
        password: withKey ? password : undefined,
        legacy: format === 'pkcs12' ? legacy : undefined,
        chainVariant: includeChain && carriesChain && variant !== 'auto' ? variant : undefined,
      })
      onClose()
    } catch {
      // the caller says why
    } finally {
      setExporting(false)
    }
  }
  const check = (id, checked, onChange, text, hint) => (
    <label className="checkbox-line" htmlFor={id}>
      <input id={id} type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {hint ? <span>{text}<small className="muted" style={{ display: 'block' }}>{hint}</small></span> : text}
    </label>
  )

  return (
    <AtelierDialog title={t(entityType === 'ca' ? 'export.titleCa' : 'export.titleCertificate')} onClose={onClose} testId="export-dialog">
      <>
        {entityName && <p className="small muted">{entityName}</p>}
        <div className="format-grid" role="radiogroup" aria-label={t('export.format')}>
          {formats.map((f) => (
            <label key={f.key} className="format-option">
              <input type="radio" name="format" value={f.key} checked={format === f.key} disabled={unavailable(f)} onChange={() => setFormat(f.key)} />
              <span>{label(f)}<small>{why(f)}</small></span>
            </label>
          ))}
        </div>
        {carriesChain && check('export-chain', includeChain, setIncludeChain, t('export.includeChain'))}
        {carriesChain && includeChain && variants.length > 1 && (
          <label className="field">{t('chainVariant.label')}
            <select id="export-chain-variant" value={variant} onChange={(e) => setVariant(e.target.value)}>
              {[{ id: 'auto' }, ...variants].map((v) => <option key={v.id} value={v.id}>{variantLabel(v, t)}</option>)}
            </select>
            <small>{t('chainVariant.exportHint')}</small>
          </label>
        )}
        {carriesChain && includeChain && entityType === 'certificate' && check('export-root', includeRoot, setIncludeRoot, t('export.includeRoot'), t('export.includeRootDesc'))}
        {keyOffered && carriesKey && !withKey && !keyOnly && check('export-key', includeKey, setIncludeKey, t('export.includeKey'))}
        {format === 'pkcs12' && check('export-legacy', legacy, setLegacy, t('export.legacyPkcs12'), t('export.legacyPkcs12Desc'))}
        <div id="p12-options" hidden={!withKey}>
          <label className="field">{t('export.password')}
            <input type="password" name="password" value={password} autoComplete="new-password" onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); submit() } }} />
            <small>{t('export.passwordLengthHint', { min: policy.min_length, max: policy.max_length })}</small>
          </label>
        </div>
        <pre className="code-preview" id="export-preview" data-testid="export-preview">{[t('export.previewTitle', { format: label(current) }), '', ...lines].join('\n')}</pre>
        {withKey && <div className="notice"><Icon name="lock" />{t(format === 'pkcs12' ? 'export.pkcs12Note' : 'export.jksNote')}</div>}
        {bundle && hasPrivateKey && canExportKey && relatedHasKey === false && <div className="notice"><Icon name="lock" />{t('export.bundleRelatedHasNoKey')}</div>}
        {hasPrivateKey && !canExportKey && <div className="notice"><Icon name="lock" />{t('export.noKeyPermission')}</div>}
        {isHsmBacked && <div className="notice"><Icon name="lock" />{t('cas.detail.exportBlockedHsm')}</div>}
        <div className="modal-actions">
          <button type="button" className="btn" data-action="close-modal" onClick={onClose}>{t('common.cancel')}</button>
          <button type="button" className="btn primary" data-write="false" data-action="export-download" disabled={!valid || exporting || undefined} onClick={submit}>
            <Icon name="download" />{exporting ? t('common.exporting') : t('export.download')}
          </button>
        </div>
      </>
    </AtelierDialog>
  )
}

export default ExportDialog
