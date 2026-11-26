/**
 * SmartImport: reads every crypto format (PEM, DER, PKCS#12/PFX, PKCS#7/P7B, CSR, private keys),
 * shows what it found, then imports the objects chosen. Drawn with the mockup's form, list and
 * notice vocabulary, inside its wide modal() (SmartImportModal).
 */
import { useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { AtelierDialog } from './atelier/AtelierDialog'
import { Btn, TextLink } from './atelier/Btn'
import { Pill } from './atelier/Pill'
import { Icon } from './atelier/Icon'
import { Section, Facts, RecordList, RecordRow } from './atelier/Detail'
import { Input, Textarea, ToggleSwitch, ModalActions, Notice } from './atelier/Form'
import { SkeletonPanel } from './atelier/Skeleton'
import { apiClient as api } from '../services'
import { useNotification } from '../contexts/NotificationContext'
import { formatDate } from '../lib/utils'
import { keyAlgorithmLabel } from '../lib/keyAlgorithms'
import { crossSummary } from '../lib/importResult'

// Supported file formats
const SUPPORTED_FORMATS = {
  text: ['.pem', '.crt', '.cer', '.key', '.csr', '.p7b', '.p7c'],
  binary: ['.der', '.p12', '.pfx']
}

const ALL_FORMATS = [...SUPPORTED_FORMATS.text, ...SUPPORTED_FORMATS.binary].join(',')

const TYPE_LABELS = { certificate: 'import.typeCertificate', private_key: 'import.typePrivateKey', csr: 'import.typeCsr', ca_certificate: 'import.typeCaCertificate' }

// One object found: its box to import it, its name, its kind in pills, its details on demand
export function ObjectCard({ obj, expanded, onToggle, selected, onSelect }) {
  const { t } = useTranslation()
  const labelKey = obj.is_ca ? TYPE_LABELS.ca_certificate : TYPE_LABELS[obj.type] || TYPE_LABELS.certificate
  const displayName = obj.subject || obj.san_dns?.[0] || `${obj.type} #${obj.index + 1}`
  const box = `import-object-${obj.index}`
  return (
    <RecordRow
      title={<label className="checkbox-line" htmlFor={box}><input type="checkbox" id={box} checked={selected} onChange={() => onSelect(!selected)} />{displayName}</label>}
      meta={(
        <>
          <Pill label={t(labelKey)} icon={obj.type === 'private_key' ? 'key' : obj.type === 'csr' ? 'file' : obj.is_ca ? 'shield' : 'cert'} />
          {obj.is_self_signed && <> <Pill tone="muted" label={t('import.selfSigned')} /></>}
          {obj.chain_position === 'root' && <> <Pill label={t('common.root')} icon="anchor" /></>}
          {obj.chain_position === 'intermediate' && <> <Pill label={t('common.intermediate')} icon="branch" /></>}
          {obj.is_encrypted && <> <Pill tone="warn" icon="lock" label={t('import.encrypted')} /></>}
          {obj.matched_key_index !== null && obj.matched_key_index !== undefined && <> <Pill tone="good" icon="link" label={t('import.hasMatchingKey')} /></>}
        </>
      )}
      extra={(
        <>
          {obj.error && <Notice tone="bad">{obj.error}</Notice>}
          {expanded && (
            <Facts items={[
              obj.subject && { label: t('common.subject'), value: <span className="mono">{obj.subject}</span>, long: true },
              obj.issuer && obj.issuer !== obj.subject && { label: t('common.issuer'), value: <span className="mono">{obj.issuer}</span>, long: true },
              obj.san_dns?.length > 0 && { label: t('details.sanDns'), value: <span className="mono">{obj.san_dns.join(', ')}</span>, long: true },
              obj.not_before && [t('common.valid'), `${formatDate(obj.not_before)} → ${formatDate(obj.not_after)}`],
              obj.key_algorithm && [t('common.algorithm'), `${keyAlgorithmLabel(obj.key_algorithm, t, obj.security_level)}${obj.key_size > 0 ? ` (${obj.key_size} bits)` : ''}`],
            ]} />
          )}
        </>
      )}
      action={<TextLink aria-expanded={expanded} onClick={onToggle}>{t('common.details')}</TextLink>}
    />
  )
}

// A chain found: its completeness and trust, its path from the root to the leaf, its problems
function ChainCard({ chain, index }) {
  const { t } = useTranslation()
  const path = [
    chain.root && (chain.root.subject?.split(',')[0] || t('common.root')),
    ...(chain.intermediates || []).map((int, i) => int.subject?.split(',')[0] || `${t('common.intermediate')} ${i + 1}`),
    chain.leaf && (chain.leaf.subject?.split(',')[0] || chain.leaf.san_dns?.[0] || t('import.leaf')),
  ].filter(Boolean)
  return (
    <RecordRow
      title={`${t('import.chain')} ${index + 1}`}
      meta={(
        <>
          {path.join(' → ')} · {chain.chain_length} {t('common.certificates').toLowerCase()}
          {chain.trust_anchor && <> · {t('import.trustAnchor')} : {chain.trust_anchor}</>}
        </>
      )}
      badge={(
        <span>
          {chain.is_complete ? <Pill tone="good" label={t('import.complete')} /> : <Pill tone="warn" label={t('import.incomplete')} />}
          {chain.trust_source === 'trust_store' && <> <Pill tone="good" label={t('import.verifiedTrustStore')} /></>}
          {chain.trust_source === 'managed_ca' && <> <Pill tone="good" label={t('import.linkedToCA')} /></>}
        </span>
      )}
      extra={chain.errors?.length > 0 && chain.errors.map((err, i) => <Notice key={i} tone="warn">{err}</Notice>)}
    />
  )
}

// What the analysis found wrong (bad), doubtful (warn) or worth knowing
function ValidationIssues({ validation }) {
  if (!validation) return null
  const { errors, warnings, infos } = validation
  return (
    <>
      {errors?.map((err, i) => <Notice key={`e${i}`} tone="bad">{err}</Notice>)}
      {warnings?.map((warn, i) => <Notice key={`w${i}`} tone="warn">{warn}</Notice>)}
      {infos?.map((inf, i) => <Notice key={`i${i}`}>{inf}</Notice>)}
    </>
  )
}

// Result of an import: what was created, cross-certificates attached or left out, warnings, errors
export function ImportResultStep({ importResult, onReset, onDone }) {
  const { t } = useTranslation()
  const totalImported = (importResult?.csrs_imported || 0) +
                       (importResult?.certificates_imported || 0) +
                       (importResult?.cas_imported || 0)
  const errors = importResult?.errors || []
  const warnings = importResult?.warnings || []
  const unverifiableParents = importResult?.unverifiable_parents || []
  const cross = crossSummary(importResult)
  const done = totalImported > 0 || cross.attached > 0
  const plural = (n, one) => `${n} ${one}${n > 1 ? 's' : ''}`

  return (
    <>
      <Section title={done ? t('import.importComplete') : t('import.noObjectsImported')}>
        {done
          ? totalImported > 0 && <p className="small muted">{t('import.successImported', { count: totalImported })}</p>
          : <p className="small muted">{errors.length > 0 ? errors[0] : t('import.allSkipped')}</p>}
        {done && (
          <RecordList label={t('common.imported')}>
            {importResult?.csrs_imported > 0 && <RecordRow key="csrs" title={plural(importResult.csrs_imported, 'CSR')} />}
            {importResult?.certificates_imported > 0 && <RecordRow key="certs" title={`${importResult.certificates_imported} ${t('common.certificate')}${importResult.certificates_imported > 1 ? 's' : ''}`} />}
            {importResult?.cas_imported > 0 && <RecordRow key="cas" title={plural(importResult.cas_imported, 'CA')} />}
            {cross.attached > 0 && <RecordRow key="cross" title={<span data-testid="cross-attached">{t('import.crossAttached', { count: cross.attached })}</span>} />}
            {importResult?.keys_matched > 0 && <RecordRow key="keys" title={t('import.privateKeysMatched', { count: importResult.keys_matched })} />}
          </RecordList>
        )}
      </Section>

      {cross.skipped > 0 && <Notice tone="warn"><span data-testid="cross-skipped">{t('import.crossSkipped', { count: cross.skipped })}</span></Notice>}

      {unverifiableParents.length > 0 && (
        <div data-testid="unverifiable-parents">
          <Section title={t('import.unverifiableParentsTitle')}>
            {unverifiableParents.map((p) => (
              <Notice key={p.ca_id} tone="warn">{t('import.unverifiableParent', { ca: p.ca_name, parent: p.candidate?.name, algorithm: p.algorithm })}</Notice>
            ))}
          </Section>
        </div>
      )}

      {warnings.map((w, i) => <Notice key={`w${i}`} tone="warn">{w}</Notice>)}
      {errors.map((e, i) => <Notice key={`e${i}`} tone="bad">{e}</Notice>)}

      <ModalActions>
        <Btn onClick={onReset}>{t('import.importMore')}</Btn>
        <Btn tone="primary" write={false} onClick={onDone}>{t('common.done')}</Btn>
      </ModalActions>
    </>
  )
}

/**
 * SmartImport Widget - can be used standalone or in modal
 */
export function SmartImportWidget({ onImportComplete, onCancel }) {
  const { t } = useTranslation()
  const { showError, showSuccess } = useNotification()
  
  const [step, setStep] = useState('input')
  const [files, setFiles] = useState([]) // { name, type, data (base64 or text), size, password }
  const [pemContent, setPemContent] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const [password, setPassword] = useState('')
  const [useGlobalPassword, setUseGlobalPassword] = useState(false)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [isImporting, setIsImporting] = useState(false)
  const [analysisResult, setAnalysisResult] = useState(null)
  const [importResult, setImportResult] = useState(null)
  const [selectedObjects, setSelectedObjects] = useState(new Set())
  const [expandedObjects, setExpandedObjects] = useState(new Set())
  const [importOptions, setImportOptions] = useState({
    import_cas: true, import_certs: true, import_keys: true, import_csrs: true, skip_duplicates: true
  })
  
  // Check if we have encrypted content
  const hasEncryptedPem = pemContent.includes('ENCRYPTED')
  const encryptedFileIndices = files.reduce((acc, f, i) => {
    if (f.name.match(/\.(p12|pfx)$/i) || f.name.match(/\.key$/i)) acc.push(i)
    else if (f.type === 'text' && f.data && f.data.includes('ENCRYPTED')) acc.push(i)
    return acc
  }, [])
  const hasEncryptedFiles = encryptedFileIndices.length > 0
  const hasEncrypted = hasEncryptedPem || hasEncryptedFiles
  
  // Reset state
  const reset = useCallback(() => {
    setStep('input')
    setFiles([])
    setPemContent('')
    setPassword('')
    setUseGlobalPassword(false)
    setAnalysisResult(null)
    setImportResult(null)
    setSelectedObjects(new Set())
    setExpandedObjects(new Set())
  }, [])
  
  // Read a single file
  // Always reads as ArrayBuffer first, then detects PEM vs DER by content
  // because .crt/.cer files can be either PEM or DER format
  const readFile = async (file) => {
    const ext = '.' + file.name.split('.').pop().toLowerCase()
    const allFormats = [...SUPPORTED_FORMATS.text, ...SUPPORTED_FORMATS.binary]
    
    if (!allFormats.includes(ext)) {
      showError(t('import.unsupportedFormat', { name: file.name, formats: allFormats.join(', ') }))
      return null
    }
    
    try {
      const buffer = await file.arrayBuffer()
      const bytes = new Uint8Array(buffer)
      // Detect PEM by checking for "-----BEGIN" header in content
      const header = String.fromCharCode(...bytes.slice(0, 11))
      const isPem = header.startsWith('-----BEGIN')
      
      if (isPem) {
        const text = new TextDecoder().decode(bytes)
        return { name: file.name, type: 'text', data: text, size: file.size, ext }
      } else {
        // Spread by blocks: one call over the whole file passes the engine's argument limit
        let binary = ''
        for (let i = 0; i < bytes.length; i += 0x8000) {
          binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000))
        }
        const base64 = btoa(binary)
        return { name: file.name, type: 'binary', data: base64, size: file.size, ext }
      }
    } catch {
      showError(t('import.readFailed', { name: file.name }))
      return null
    }
  }
  
  // Read multiple files
  const readFiles = useCallback(async (fileList) => {
    const results = await Promise.all(Array.from(fileList).map(readFile))
    const validFiles = results.filter(Boolean)
    setFiles(prev => [...prev, ...validFiles])
  }, [])
  
  // Files dropped on the file field are read as files picked
  const handleDrop = useCallback((e) => {
    setDragOver(false)
    if (!e.dataTransfer?.files?.length) return
    e.preventDefault()
    readFiles(e.dataTransfer.files)
  }, [readFiles])
  const handleFileSelect = useCallback((e) => {
    if (e.target.files.length > 0) readFiles(e.target.files)
    e.target.value = ''
  }, [readFiles])
  
  // Remove a file
  const removeFile = (index) => {
    setFiles(prev => prev.filter((_, i) => i !== index))
  }
  
  // Build content for API
  const buildContent = () => {
    const parts = []
    
    // Add pasted PEM content
    if (pemContent.trim()) {
      parts.push(pemContent.trim())
    }
    
    // Add files
    for (const file of files) {
      if (file.type === 'text') {
        parts.push(file.data)
      } else {
        // Binary files: wrap in pseudo-PEM for transport
        const typeMarker = file.ext === '.p12' || file.ext === '.pfx' ? 'PKCS12' 
          : file.ext === '.der' ? 'DER CERTIFICATE' 
          : 'BINARY DATA'
        parts.push(`-----BEGIN ${typeMarker}-----\n${file.data}\n-----END ${typeMarker}-----`)
      }
    }
    
    return parts.join('\n\n')
  }
  
  // Get effective password for API call
  const getEffectivePassword = () => {
    if (useGlobalPassword) return password || undefined
    // If per-file, send the first non-empty file password (backend handles single password)
    const filePassword = files.find(f => f.password)?.password
    return filePassword || password || undefined
  }
  
  // Build per-file passwords map
  const getFilePasswords = () => {
    if (useGlobalPassword) return undefined
    const passwords = {}
    files.forEach((f, i) => {
      if (f.password) passwords[i] = f.password
    })
    return Object.keys(passwords).length > 0 ? passwords : undefined
  }
  
  // Update file password
  const setFilePassword = (index, pwd) => {
    setFiles(prev => prev.map((f, i) => i === index ? { ...f, password: pwd } : f))
  }
  
  // Analyze content
  const handleAnalyze = async () => {
    const content = buildContent()
    if (!content) {
      showError(t('import.pleaseAddFiles'))
      return
    }
    
    setIsAnalyzing(true)
    try {
      const response = await api.post('/import/analyze', { 
        content, 
        password: getEffectivePassword(),
        file_passwords: getFilePasswords()
      })
      // response = {success, data} - data contains {objects, chains, ...}
      const result = response.data || response
      setAnalysisResult(result)
      setSelectedObjects(new Set(result.objects.map((_, i) => i)))
      setStep('preview')
    } catch (err) {
      console.error('[SmartImport] Analysis error:', err)
      showError(err.message || t('import.analyzeFailed'))
    } finally {
      setIsAnalyzing(false)
    }
  }
  
  // Execute import
  const handleImport = async () => {
    if (!analysisResult || selectedObjects.size === 0) return
    
    setIsImporting(true)
    setStep('importing')
    try {
      const response = await api.post('/import/execute', {
        content: buildContent(),
        password: getEffectivePassword(),
        file_passwords: getFilePasswords(),
        options: { ...importOptions, selected_indices: Array.from(selectedObjects) }
      })
      const result = response.data || response
      setImportResult(result)
      setStep('result')
      // Count total imports
      const totalImported = (result.csrs_imported || 0) + 
                           (result.certificates_imported || 0) + 
                           (result.cas_imported || 0)
      if (totalImported > 0) {
        showSuccess(t('import.successImported', { count: totalImported }))
      }
    } catch (err) {
      showError(err.message || t('common.importFailed'))
      setStep('preview')
    } finally {
      setIsImporting(false)
    }
  }
  
  // Toggle object selection/expansion
  const toggleObject = (index) => {
    setSelectedObjects(prev => {
      const next = new Set(prev)
      next.has(index) ? next.delete(index) : next.add(index)
      return next
    })
  }
  
  const toggleExpand = (index) => {
    setExpandedObjects(prev => {
      const next = new Set(prev)
      next.has(index) ? next.delete(index) : next.add(index)
      return next
    })
  }
  
  const selectAll = () => {
    if (selectedObjects.size === analysisResult?.objects?.length) {
      setSelectedObjects(new Set())
    } else {
      setSelectedObjects(new Set(analysisResult?.objects?.map((_, i) => i) || []))
    }
  }
  
  const canAnalyze = (pemContent.trim() || files.length > 0) && !isAnalyzing

  // Input: files (picked or dropped), their passwords, the pasted PEM, the password of encrypted content
  const renderInputStep = () => (
    <>
      <div className="form-fields">
        <div className={`field full${dragOver ? ' dragover' : ''}`} onDrop={handleDrop}
          onDragOver={(e) => { if (e.dataTransfer?.types?.includes?.('Files')) { e.preventDefault(); setDragOver(true) } }}
          onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setDragOver(false) }}>
          <span>{t('import.files')}</span>
          <span className="drop-zone">
            {t('import.dropFileHere')}
            <label className="text-link">
              <input type="file" multiple accept={ALL_FORMATS} className="sr-only" onChange={handleFileSelect} />
              {t('common.chooseFile')}
            </label>
          </span>
          <small>{t('import.allFormats')}</small>
          {files.length > 0 && (
            <RecordList label={t('import.files')}>
              {files.map((file, i) => (
                <RecordRow key={i} title={file.name} meta={`${file.ext.toUpperCase().slice(1)} · ${(file.size / 1024).toFixed(1)} KB`}
                  action={<button type="button" className="text-link" aria-label={t('common.remove')} onClick={() => removeFile(i)}><Icon name="close" /></button>} />
              ))}
            </RecordList>
          )}
        </div>
        {hasEncryptedFiles && (
          <ToggleSwitch label={t('import.useGlobalPassword')} checked={useGlobalPassword} onChange={setUseGlobalPassword} />
        )}
        {!useGlobalPassword && files.map((file, i) => (encryptedFileIndices.includes(i) && (
          <Input key={i} type="password" autoComplete="new-password" label={t('import.filePasswordFor', { name: file.name })}
            value={file.password || ''} onChange={(e) => setFilePassword(i, e.target.value)} />
        )))}
        <Textarea label={t('common.orPastePem')} mono rows={6} spellCheck={false} placeholder={t('import.pastePemPlaceholder')}
          value={pemContent} onChange={(e) => setPemContent(e.target.value)} />
        {hasEncrypted && (useGlobalPassword || hasEncryptedPem) && (
          <>
            <Notice tone="warn">{t('import.encryptedDetected')}</Notice>
            <Input type="password" autoComplete="new-password" label={t('common.password')} placeholder={t('common.enterPassword')}
              value={password} onChange={(e) => setPassword(e.target.value)} />
          </>
        )}
      </div>
      {onCancel ? (
        <ModalActions>
          <Btn onClick={onCancel}>{t('common.cancel')}</Btn>
          <Btn tone="primary" write={false} icon="search" onClick={handleAnalyze} disabled={!canAnalyze}>
            {isAnalyzing ? t('import.analyzing') : t('import.analyze')}
          </Btn>
        </ModalActions>
      ) : (
        <div className="settings-actions">
          <Btn tone="primary" write={false} icon="search" onClick={handleAnalyze} disabled={!canAnalyze}>
            {isAnalyzing ? t('import.analyzing') : t('import.analyze')}
          </Btn>
          <span className="group-hint">{t('import.analyzeHint')}</span>
        </div>
      )}
    </>
  )

  // Preview: what was found (counts, chains, key pairs, problems), the objects to import, the options
  const renderPreviewStep = () => {
    const { objects, chains, matching, validation } = analysisResult || {}
    const count = (keep) => objects?.filter(keep).length || 0
    const option = (key, label) => (
      <ToggleSwitch key={key} label={t(label)} checked={importOptions[key]} onChange={(on) => setImportOptions(prev => ({ ...prev, [key]: on }))} />
    )
    return (
      <>
        <Facts items={[
          count(o => o.type === 'certificate' && !o.is_ca) > 0 && [t('common.certificates'), count(o => o.type === 'certificate' && !o.is_ca)],
          count(o => o.is_ca) > 0 && [t('common.cas'), count(o => o.is_ca)],
          count(o => o.type === 'private_key') > 0 && [t('import.typePrivateKey'), count(o => o.type === 'private_key')],
          count(o => o.type === 'csr') > 0 && [t('import.typeCsr'), count(o => o.type === 'csr')],
        ]} />

        {chains?.length > 0 && (
          <Section title={t('import.certificateChains')}>
            <RecordList>{chains.map((chain, i) => <ChainCard key={i} chain={chain} index={i} />)}</RecordList>
          </Section>
        )}

        {matching?.matched_pairs?.length > 0 && <Notice>{t('import.keyPairsDetected', { count: matching.matched_pairs.length })}</Notice>}
        <ValidationIssues validation={validation} />

        <Section title={<>{t('import.detectedObjects')} ({objects?.length || 0}) <TextLink onClick={selectAll}>{selectedObjects.size === objects?.length ? t('common.deselectAll') : t('common.selectAll')}</TextLink></>}>
          <RecordList>
            {objects?.map((obj, i) => (
              <ObjectCard key={i} obj={obj} expanded={expandedObjects.has(i)} onToggle={() => toggleExpand(i)} selected={selectedObjects.has(i)} onSelect={() => toggleObject(i)} />
            ))}
          </RecordList>
        </Section>

        <Section title={t('import.importOptions')}>
          <div className="form-fields">
            {option('skip_duplicates', 'import.skipDuplicates')}
            {option('import_cas', 'import.importCAs')}
            {option('import_certs', 'import.importCertificates')}
            {option('import_keys', 'import.importKeys')}
            {option('import_csrs', 'import.importCSRs')}
          </div>
        </Section>

        <ModalActions>
          <Btn onClick={() => {
            setStep('input')
            setAnalysisResult(null)
            setSelectedObjects(new Set())
          }}>{t('common.back')}</Btn>
          <Btn tone="primary" icon="upload" onClick={handleImport} disabled={selectedObjects.size === 0 || isImporting}>
            {t('import.importObjects', { count: selectedObjects.size })}
          </Btn>
        </ModalActions>
      </>
    )
  }

  const renderImportingStep = () => <SkeletonPanel label={t('import.importingObjects')} />

  const renderResultStep = () => (
    <ImportResultStep
      importResult={importResult}
      onReset={reset}
      onDone={() => onImportComplete?.(importResult)}
    />
  )
  
  return (
    <>
      {step === 'input' && renderInputStep()}
      {step === 'preview' && renderPreviewStep()}
      {step === 'importing' && renderImportingStep()}
      {step === 'result' && renderResultStep()}
    </>
  )
}

/** SmartImport in the mockup's wide modal(): the mockup has no import screen, the dialog takes its vocabulary. */
export function SmartImportModal({ isOpen, onClose, onImportComplete }) {
  const { t } = useTranslation()
  if (!isOpen) return null
  const handleComplete = (result) => {
    onImportComplete?.(result)
    onClose()
  }
  return (
    <AtelierDialog title={t('import.smartImport')} size="wide" onClose={onClose} testId="smart-import-dialog">
      <SmartImportWidget onImportComplete={handleComplete} onCancel={onClose} />
    </AtelierDialog>
  )
}

// Default export for backward compatibility
export default SmartImportModal
