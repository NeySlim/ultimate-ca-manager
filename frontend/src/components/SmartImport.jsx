/**
 * SmartImport - Intelligent import component for all crypto formats
 * 
 * Supports: PEM, DER, PKCS12/PFX, PKCS7/P7B, CSR, private keys
 * Can be used standalone or wrapped in a modal
 */
import { useState, useRef, useCallback, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { 
  UploadSimple, FileText, Key, ShieldCheck, Certificate,
  WarningCircle, CheckCircle, XCircle, LockSimple, Link,
  CaretDown, CaretRight, ArrowsClockwise, File, Trash
} from '@phosphor-icons/react'
import { Button } from './Button'
import { Badge } from './Badge'
import { Modal } from './Modal'
import { apiClient as api } from '../services'
import { useNotification } from '../contexts/NotificationContext'

// Supported file formats
const SUPPORTED_FORMATS = {
  text: ['.pem', '.crt', '.cer', '.key', '.csr', '.p7b', '.p7c'],
  binary: ['.der', '.p12', '.pfx']
}

const ALL_FORMATS = [...SUPPORTED_FORMATS.text, ...SUPPORTED_FORMATS.binary].join(',')

// Type icons and colors - keys for translations
const TYPE_CONFIG = {
  certificate: { icon: Certificate, color: 'blue', labelKey: 'import.typeCertificate' },
  private_key: { icon: Key, color: 'orange', labelKey: 'import.typePrivateKey' },
  csr: { icon: FileText, color: 'purple', labelKey: 'import.typeCsr' },
  ca_certificate: { icon: ShieldCheck, color: 'green', labelKey: 'import.typeCaCertificate' }
}

// Object card component
function ObjectCard({ obj, expanded, onToggle, selected, onSelect }) {
  const { t } = useTranslation()
  const config = obj.is_ca ? TYPE_CONFIG.ca_certificate : TYPE_CONFIG[obj.type] || TYPE_CONFIG.certificate
  const Icon = config.icon
  const displayName = obj.subject || obj.san_dns?.[0] || `${obj.type} #${obj.index + 1}`
  
  return (
    <div className={`border rounded-lg transition-colors ${selected ? 'border-accent-primary bg-accent-primary/5' : 'border-border hover:border-border-hover'}`}>
      <div className="flex items-center gap-3 p-3 cursor-pointer" onClick={onToggle}>
        <input 
          type="checkbox"
          checked={selected}
          onChange={(e) => { e.stopPropagation(); onSelect(!selected) }}
          className="w-4 h-4 rounded border-border text-accent-primary focus:ring-accent-primary"
        />
        
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center icon-bg-${config.color}`}>
          <Icon size={16} className={`text-accent-${config.color}`} />
        </div>
        
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-sm truncate">{displayName}</span>
            {obj.is_encrypted && <LockSimple size={16} className="text-status-warning" title={t('import.encrypted')} />}
            {obj.matched_key_index !== null && <Link size={16} className="text-status-success" title={t('import.hasMatchingKey')} />}
          </div>
          <div className="flex items-center gap-2 text-xs text-text-secondary">
            <Badge variant={config.color} size="xs">{t(config.labelKey)}</Badge>
            {obj.is_self_signed && <Badge variant="gray" size="xs">{t('import.selfSigned')}</Badge>}
            {obj.chain_position === 'root' && <Badge variant="amber" size="xs">{t('import.root')}</Badge>}
            {obj.chain_position === 'intermediate' && <Badge variant="blue" size="xs">{t('import.intermediate')}</Badge>}
          </div>
        </div>
        
        {expanded ? <CaretDown size={16} className="text-text-secondary" /> : <CaretRight size={16} className="text-text-secondary" />}
      </div>
      
      {expanded && (
        <div className="px-3 pb-3 border-t border-border pt-3 space-y-2 text-sm">
          {obj.subject && (
            <div className="flex gap-2">
              <span className="text-text-secondary w-20 shrink-0">{t('details.subject')}:</span>
              <span className="font-mono text-xs break-all">{obj.subject}</span>
            </div>
          )}
          {obj.issuer && obj.issuer !== obj.subject && (
            <div className="flex gap-2">
              <span className="text-text-secondary w-20 shrink-0">{t('details.issuer')}:</span>
              <span className="font-mono text-xs break-all">{obj.issuer}</span>
            </div>
          )}
          {obj.san_dns?.length > 0 && (
            <div className="flex gap-2">
              <span className="text-text-secondary w-20 shrink-0">{t('details.sanDns')}:</span>
              <span className="font-mono text-xs">{obj.san_dns.join(', ')}</span>
            </div>
          )}
          {obj.not_before && (
            <div className="flex gap-2">
              <span className="text-text-secondary w-20 shrink-0">{t('details.valid')}:</span>
              <span className="text-xs">{new Date(obj.not_before).toLocaleDateString()} → {new Date(obj.not_after).toLocaleDateString()}</span>
            </div>
          )}
          {obj.key_algorithm && (
            <div className="flex gap-2">
              <span className="text-text-secondary w-20 shrink-0">{t('details.algorithm')}:</span>
              <span className="text-xs">{obj.key_algorithm} ({obj.key_size} bits)</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// Chain visualization
function ChainCard({ chain, index }) {
  const { t } = useTranslation()
  const hasIssues = chain.errors?.length > 0
  
  return (
    <div className={`border rounded-lg p-3 ${hasIssues ? 'alert-bg-amber' : 'border-border'}`}>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-sm font-medium">{t('import.chain')} {index + 1}</span>
        {chain.is_complete ? <Badge variant="green" size="xs">{t('import.complete')}</Badge> : <Badge variant="amber" size="xs">{t('import.incomplete')}</Badge>}
        <span className="text-xs text-text-secondary ml-auto">{chain.chain_length} {t('common.certificates').toLowerCase()}</span>
      </div>
      
      <div className="flex items-center gap-1 text-xs flex-wrap">
        {chain.root && (
          <>
            <span className="px-2 py-1 rounded badge-bg-amber">{chain.root.subject?.split(',')[0] || t('import.root')}</span>
            <span className="text-text-secondary">→</span>
          </>
        )}
        {chain.intermediates?.map((int, i) => (
          <span key={i}>
            <span className="px-2 py-1 rounded badge-bg-blue">{int.subject?.split(',')[0] || `${t('import.intermediate')} ${i + 1}`}</span>
            <span className="text-text-secondary mx-1">→</span>
          </span>
        ))}
        {chain.leaf && (
          <span className="px-2 py-1 rounded icon-bg-teal">{chain.leaf.subject?.split(',')[0] || chain.leaf.san_dns?.[0] || t('import.leaf')}</span>
        )}
      </div>
      
      {hasIssues && (
        <div className="mt-2 text-xs text-status-warning">
          {chain.errors.map((err, i) => (
            <div key={i} className="flex items-center gap-1"><WarningCircle size={12} />{err}</div>
          ))}
        </div>
      )}
    </div>
  )
}

// Validation issues
function ValidationIssues({ validation }) {
  if (!validation) return null
  const { errors, warnings, infos } = validation
  if (!errors?.length && !warnings?.length && !infos?.length) return null
  
  return (
    <div className="space-y-2">
      {errors?.map((err, i) => (
        <div key={`e${i}`} className="flex items-start gap-2 text-sm p-2 rounded alert-bg-red">
          <XCircle size={16} className="shrink-0 mt-0.5" /><span>{err}</span>
        </div>
      ))}
      {warnings?.map((warn, i) => (
        <div key={`w${i}`} className="flex items-start gap-2 text-sm p-2 rounded alert-bg-amber">
          <WarningCircle size={16} className="shrink-0 mt-0.5" /><span>{warn}</span>
        </div>
      ))}
      {infos?.map((inf, i) => (
        <div key={`i${i}`} className="flex items-start gap-2 text-sm p-2 rounded alert-bg-green">
          <CheckCircle size={16} className="shrink-0 mt-0.5" /><span>{inf}</span>
        </div>
      ))}
    </div>
  )
}

/**
 * SmartImport Widget - can be used standalone or in modal
 */
export function SmartImportWidget({ onImportComplete, onCancel, compact = false }) {
  const { showError, showSuccess } = useNotification()
  const fileInputRef = useRef(null)
  
  const [step, setStep] = useState('input')
  const [files, setFiles] = useState([]) // { name, type, data (base64 or text), size }
  const [pemContent, setPemContent] = useState('')
  const [password, setPassword] = useState('')
  const [isDragOver, setIsDragOver] = useState(false)
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
  const hasEncrypted = pemContent.includes('ENCRYPTED') || files.some(f => f.name.match(/\.(p12|pfx)$/i))
  
  // Reset state
  const reset = useCallback(() => {
    setStep('input')
    setFiles([])
    setPemContent('')
    setPassword('')
    setAnalysisResult(null)
    setImportResult(null)
    setSelectedObjects(new Set())
    setExpandedObjects(new Set())
  }, [])
  
  // Read a single file
  const readFile = async (file) => {
    const ext = '.' + file.name.split('.').pop().toLowerCase()
    const isBinary = SUPPORTED_FORMATS.binary.includes(ext)
    
    try {
      if (isBinary) {
        const buffer = await file.arrayBuffer()
        const base64 = btoa(String.fromCharCode(...new Uint8Array(buffer)))
        return { name: file.name, type: 'binary', data: base64, size: file.size, ext }
      } else {
        const text = await file.text()
        return { name: file.name, type: 'text', data: text, size: file.size, ext }
      }
    } catch (err) {
      console.error(`Failed to read ${file.name}:`, err)
      return null
    }
  }
  
  // Read multiple files
  const readFiles = useCallback(async (fileList) => {
    const results = await Promise.all(Array.from(fileList).map(readFile))
    const validFiles = results.filter(Boolean)
    setFiles(prev => [...prev, ...validFiles])
  }, [])
  
  // Drag & drop handlers
  const handleDragOver = useCallback((e) => { e.preventDefault(); setIsDragOver(true) }, [])
  const handleDragLeave = useCallback((e) => { e.preventDefault(); setIsDragOver(false) }, [])
  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setIsDragOver(false)
    if (e.dataTransfer.files.length > 0) readFiles(e.dataTransfer.files)
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
        password: password || undefined 
      })
      // response = {success, data} - data contains {objects, chains, ...}
      const result = response.data || response
      setAnalysisResult(result)
      setSelectedObjects(new Set(result.objects.map((_, i) => i)))
      setStep('preview')
    } catch (err) {
      console.error('[SmartImport] Analysis error:', err)
      showError(err.response?.data?.error || err.message || t('import.analyzeFailed'))
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
        password: password || undefined,
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
      showError(err.response?.data?.error || t('import.importFailed'))
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
  
  // Render input step
  const renderInputStep = () => (
    <div className="space-y-4">
      {/* Drop zone */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors ${isDragOver ? 'border-accent-primary bg-accent-primary/5' : 'border-border hover:border-border-hover'}`}
      >
        <UploadSimple size={40} className="mx-auto mb-3 text-text-secondary" />
        <p className="text-sm mb-1">
          Drop files here or{' '}
          <button type="button" onClick={() => fileInputRef.current?.click()} className="text-accent-primary hover:underline">browse</button>
        </p>
        <p className="text-xs text-text-secondary">
          All formats: PEM, DER, CRT, CER, KEY, CSR, P12/PFX, P7B
        </p>
        <input 
          ref={fileInputRef} 
          type="file" 
          multiple 
          accept={ALL_FORMATS}
          onChange={handleFileSelect} 
          className="hidden" 
        />
      </div>
      
      {/* File list */}
      {files.length > 0 && (
        <div className="space-y-2">
          <div className="text-sm font-medium">{t('import.files')} ({files.length})</div>
          {files.map((file, i) => (
            <div key={i} className="flex items-center gap-2 p-2 bg-bg-secondary rounded-lg">
              <File size={16} className="text-text-secondary" />
              <span className="text-sm flex-1 truncate">{file.name}</span>
              <Badge variant={file.type === 'binary' ? 'amber' : 'blue'} size="xs">
                {file.ext.toUpperCase().slice(1)}
              </Badge>
              <span className="text-xs text-text-secondary">{(file.size / 1024).toFixed(1)} KB</span>
              <button onClick={() => removeFile(i)} className="text-status-danger hover:text-status-danger">
                <Trash size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
      
      {/* Or paste PEM */}
      <div className="relative">
        <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-border"></div></div>
        <div className="relative flex justify-center text-xs uppercase"><span className="bg-bg-primary px-2 text-text-secondary">{t('import.orPastePem')}</span></div>
      </div>
      
      <textarea
        value={pemContent}
        onChange={(e) => setPemContent(e.target.value)}
        placeholder={t('import.pastePemPlaceholder')}
        className="w-full h-32 p-3 font-mono text-xs border border-border rounded-lg bg-bg-secondary resize-none focus:outline-none focus:ring-2 focus:ring-accent-primary"
      />
      
      {/* Password for encrypted content */}
      {hasEncrypted && (
        <div className="flex items-center gap-2 p-3 rounded-lg alert-bg-amber">
          <LockSimple size={18} />
          <div className="flex-1">
            <p className="text-sm font-medium">{t('import.encryptedDetected')}</p>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t('common.enterPassword')}
              className="mt-2 w-full px-3 py-2 text-sm border border-border rounded-lg bg-bg-primary focus:outline-none focus:ring-2 focus:ring-accent-primary"
            />
          </div>
        </div>
      )}
      
      {/* Actions */}
      <div className="flex justify-end gap-2 pt-2">
        {onCancel && <Button variant="secondary" onClick={onCancel}>{t('common.cancel')}</Button>}
        <Button onClick={handleAnalyze} disabled={(!pemContent.trim() && files.length === 0) || isAnalyzing}>
          {isAnalyzing ? <><ArrowsClockwise size={16} className="animate-spin" /> {t('import.analyzing')}</> : t('import.analyze')}
        </Button>
      </div>
    </div>
  )
  
  // Render preview step  
  const renderPreviewStep = () => {
    const { objects, chains, matching, validation } = analysisResult || {}
    const stats = {
      certs: objects?.filter(o => o.type === 'certificate' && !o.is_ca).length || 0,
      cas: objects?.filter(o => o.is_ca).length || 0,
      keys: objects?.filter(o => o.type === 'private_key').length || 0,
      csrs: objects?.filter(o => o.type === 'csr').length || 0
    }
    
    return (
      <div className="space-y-4">
        {/* Stats */}
        <div className="flex flex-wrap gap-3 text-sm">
          {stats.certs > 0 && <Badge variant="blue" icon={Certificate}>{stats.certs} Certificate{stats.certs > 1 ? 's' : ''}</Badge>}
          {stats.cas > 0 && <Badge variant="green" icon={ShieldCheck}>{stats.cas} CA{stats.cas > 1 ? 's' : ''}</Badge>}
          {stats.keys > 0 && <Badge variant="orange" icon={Key}>{stats.keys} Key{stats.keys > 1 ? 's' : ''}</Badge>}
          {stats.csrs > 0 && <Badge variant="purple" icon={FileText}>{stats.csrs} CSR{stats.csrs > 1 ? 's' : ''}</Badge>}
        </div>
        
        {/* Chains */}
        {chains?.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-sm font-medium">{t('import.certificateChains')}</h3>
            {chains.map((chain, i) => <ChainCard key={i} chain={chain} index={i} />)}
          </div>
        )}
        
        {/* Key matching */}
        {matching?.matched_pairs?.length > 0 && (
          <div className="text-sm p-2 rounded flex items-center gap-2 alert-bg-green">
            <Link size={16} />
            {t('import.keyPairsDetected', { count: matching.matched_pairs.length })}
          </div>
        )}
        
        <ValidationIssues validation={validation} />
        
        {/* Objects list */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium">{t('import.detectedObjects')} ({objects?.length || 0})</h3>
            <button type="button" onClick={selectAll} className="text-xs text-accent-primary hover:underline">
              {selectedObjects.size === objects?.length ? t('common.deselectAll') : t('common.selectAll')}
            </button>
          </div>
          
          <div className={`space-y-2 overflow-y-auto pr-1 ${compact ? 'max-h-48' : 'max-h-64'}`}>
            {objects?.map((obj, i) => (
              <ObjectCard key={i} obj={obj} expanded={expandedObjects.has(i)} onToggle={() => toggleExpand(i)} selected={selectedObjects.has(i)} onSelect={() => toggleObject(i)} />
            ))}
          </div>
        </div>
        
        {/* Import options */}
        <div className="border-t border-border pt-4">
          <h3 className="text-sm font-medium mb-2">{t('import.importOptions')}</h3>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={importOptions.skip_duplicates} onChange={(e) => setImportOptions(prev => ({ ...prev, skip_duplicates: e.target.checked }))} className="w-4 h-4 rounded" />
              {t('import.skipDuplicates')}
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={importOptions.import_cas} onChange={(e) => setImportOptions(prev => ({ ...prev, import_cas: e.target.checked }))} className="w-4 h-4 rounded" />
              {t('import.importCAs')}
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={importOptions.import_certs} onChange={(e) => setImportOptions(prev => ({ ...prev, import_certs: e.target.checked }))} className="w-4 h-4 rounded" />
              {t('import.importCertificates')}
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={importOptions.import_keys} onChange={(e) => setImportOptions(prev => ({ ...prev, import_keys: e.target.checked }))} className="w-4 h-4 rounded" />
              {t('import.importKeys')}
            </label>
          </div>
        </div>
        
        {/* Actions */}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="secondary" onClick={() => {
            setStep('input')
            setAnalysisResult(null)
            setSelectedObjects(new Set())
          }}>{t('common.back')}</Button>
          <Button onClick={handleImport} disabled={selectedObjects.size === 0 || isImporting}>
            {t('import.importObjects', { count: selectedObjects.size })}
          </Button>
        </div>
      </div>
    )
  }
  
  // Render importing step
  const renderImportingStep = () => (
    <div className="flex flex-col items-center justify-center py-12">
      <ArrowsClockwise size={48} className="text-accent-primary animate-spin mb-4" />
      <p className="text-sm">{t('import.importingObjects')}</p>
    </div>
  )
  
  // Render result step
  const renderResultStep = () => {
    // Backend returns: csrs_imported, certificates_imported, cas_imported, imported_ids, errors, warnings
    const totalImported = (importResult?.csrs_imported || 0) + 
                         (importResult?.certificates_imported || 0) + 
                         (importResult?.cas_imported || 0)
    const errors = importResult?.errors || []
    const warnings = importResult?.warnings || []
    const importedIds = importResult?.imported_ids || {}
    
    return (
      <div className="space-y-4">
        <div className="text-center py-6">
          {totalImported > 0 ? (
            <>
              <CheckCircle size={48} className="text-status-success mx-auto mb-3" weight="fill" />
              <h3 className="text-lg font-medium">{t('import.importComplete')}</h3>
              <p className="text-sm text-text-secondary">{t('import.successImported', { count: totalImported })}</p>
            </>
          ) : (
            <>
              <WarningCircle size={48} className="text-status-warning mx-auto mb-3" />
              <h3 className="text-lg font-medium">{t('import.noObjectsImported')}</h3>
              <p className="text-sm text-text-secondary">{errors.length > 0 ? errors[0] : t('import.allSkipped')}</p>
            </>
          )}
        </div>
        
        {/* Show what was imported */}
        {totalImported > 0 && (
          <div className="space-y-1">
            <h4 className="text-sm font-medium text-status-success">{t('import.imported')}:</h4>
            {importResult?.csrs_imported > 0 && (
              <div className="text-sm pl-4">✓ {importResult.csrs_imported} CSR{importResult.csrs_imported > 1 ? 's' : ''}</div>
            )}
            {importResult?.certificates_imported > 0 && (
              <div className="text-sm pl-4">✓ {importResult.certificates_imported} {t('common.certificate')}{importResult.certificates_imported > 1 ? 's' : ''}</div>
            )}
            {importResult?.cas_imported > 0 && (
              <div className="text-sm pl-4">✓ {importResult.cas_imported} CA{importResult.cas_imported > 1 ? 's' : ''}</div>
            )}
            {importResult?.keys_matched > 0 && (
              <div className="text-sm pl-4 text-text-secondary">🔑 {importResult.keys_matched} {t('import.privateKeysMatched')}</div>
            )}
          </div>
        )}
        
        {warnings.length > 0 && (
          <div className="space-y-1">
            <h4 className="text-sm font-medium text-status-warning">{t('common.warnings')}:</h4>
            {warnings.map((w, i) => <div key={i} className="text-sm pl-4">⚠ {w}</div>)}
          </div>
        )}
        
        {errors.length > 0 && (
          <div className="space-y-1">
            <h4 className="text-sm font-medium text-status-danger">{t('common.errors')}:</h4>
            {errors.map((e, i) => <div key={i} className="text-sm pl-4">✗ {e}</div>)}
          </div>
        )}
        
        {/* Actions */}
        <div className="flex justify-end gap-2 pt-4">
          <Button variant="secondary" onClick={reset}>{t('import.importMore')}</Button>
          <Button onClick={() => { onImportComplete?.(importResult); }}>{t('common.done')}</Button>
        </div>
      </div>
    )
  }
  
  return (
    <div className={compact ? '' : 'space-y-4'}>
      {step === 'input' && renderInputStep()}
      {step === 'preview' && renderPreviewStep()}
      {step === 'importing' && renderImportingStep()}
      {step === 'result' && renderResultStep()}
    </div>
  )
}

/**
 * SmartImport Modal - wraps widget in a modal
 */
export function SmartImportModal({ isOpen, onClose, onImportComplete }) {
  const { t } = useTranslation()
  const handleComplete = (result) => {
    onImportComplete?.(result)
    onClose()
  }
  
  return (
    <Modal
      open={isOpen}
      onClose={onClose}
      title={t('import.smartImport')}
      size="lg"
    >
      <div className="p-4">
        {/* Key forces remount when modal opens, resetting all state */}
        <SmartImportWidget 
          key={isOpen ? 'open' : 'closed'}
          onImportComplete={handleComplete}
          onCancel={onClose}
          compact
        />
      </div>
    </Modal>
  )
}

// Default export for backward compatibility
export default SmartImportModal
