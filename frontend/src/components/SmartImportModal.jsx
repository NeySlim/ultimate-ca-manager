/**
 * SmartImportModal - Intelligent import interface for certificates, keys, CSRs
 */
import { useState, useRef, useCallback, useEffect } from 'react'
import { 
  UploadSimple, FileText, Key, ShieldCheck, Certificate,
  WarningCircle, CheckCircle, XCircle, LockSimple, Link,
  CaretDown, CaretRight, ArrowsClockwise
} from '@phosphor-icons/react'
import { Modal } from './Modal'
import { Button } from './Button'
import { Badge } from './Badge'
import { apiClient as api } from '../services'
import { useNotification } from '../contexts/NotificationContext'

// Type icons and colors
const TYPE_CONFIG = {
  certificate: { icon: Certificate, color: 'cyan', label: 'Certificate' },
  private_key: { icon: Key, color: 'amber', label: 'Private Key' },
  csr: { icon: FileText, color: 'purple', label: 'CSR' },
  ca_certificate: { icon: ShieldCheck, color: 'emerald', label: 'CA Certificate' }
}

// Object card component
function ObjectCard({ obj, expanded, onToggle, selected, onSelect }) {
  const config = obj.is_ca ? TYPE_CONFIG.ca_certificate : TYPE_CONFIG[obj.type] || TYPE_CONFIG.certificate
  const Icon = config.icon
  const displayName = obj.subject || obj.san_dns?.[0] || `${obj.type} #${obj.index + 1}`
  
  const iconBgColor = config.color === 'cyan' ? 'blue' : config.color === 'amber' ? 'orange' : config.color === 'emerald' ? 'green' : 'purple'
  
  return (
    <div className={`border rounded-lg transition-colors ${selected ? 'border-accent-primary bg-accent-primary/5' : 'border-border hover:border-border-hover'}`}>
      <div className="flex items-center gap-3 p-3 cursor-pointer" onClick={onToggle}>
        <input 
          type="checkbox"
          checked={selected}
          onChange={(e) => { e.stopPropagation(); onSelect(!selected) }}
          className="w-4 h-4 rounded border-border text-accent-primary focus:ring-accent-primary"
        />
        
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center icon-bg-${iconBgColor}`}>
          <Icon size={16} className={`text-accent-${iconBgColor}`} />
        </div>
        
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-sm truncate">{displayName}</span>
            {obj.is_encrypted && <LockSimple size={16} className="text-amber-500" title="Encrypted" />}
            {obj.matched_key_index !== null && <Link size={16} className="text-green-500" title="Has matching key" />}
          </div>
          <div className="flex items-center gap-2 text-xs text-text-secondary">
            <Badge variant={config.color} size="xs">{config.label}</Badge>
            {obj.is_self_signed && <Badge variant="gray" size="xs">Self-Signed</Badge>}
            {obj.chain_position === 'root' && <Badge variant="amber" size="xs">Root</Badge>}
            {obj.chain_position === 'intermediate' && <Badge variant="blue" size="xs">Intermediate</Badge>}
          </div>
        </div>
        
        {expanded ? <CaretDown size={16} className="text-text-secondary" /> : <CaretRight size={16} className="text-text-secondary" />}
      </div>
      
      {expanded && (
        <div className="px-3 pb-3 border-t border-border pt-3 space-y-2 text-sm">
          {obj.subject && (
            <div className="flex gap-2">
              <span className="text-text-secondary w-20 shrink-0">Subject:</span>
              <span className="font-mono text-xs break-all">{obj.subject}</span>
            </div>
          )}
          {obj.issuer && obj.issuer !== obj.subject && (
            <div className="flex gap-2">
              <span className="text-text-secondary w-20 shrink-0">Issuer:</span>
              <span className="font-mono text-xs break-all">{obj.issuer}</span>
            </div>
          )}
          {obj.san_dns?.length > 0 && (
            <div className="flex gap-2">
              <span className="text-text-secondary w-20 shrink-0">SAN DNS:</span>
              <span className="font-mono text-xs">{obj.san_dns.join(', ')}</span>
            </div>
          )}
          {obj.not_before && (
            <div className="flex gap-2">
              <span className="text-text-secondary w-20 shrink-0">Valid:</span>
              <span className="text-xs">{new Date(obj.not_before).toLocaleDateString()} → {new Date(obj.not_after).toLocaleDateString()}</span>
            </div>
          )}
          {obj.key_algorithm && (
            <div className="flex gap-2">
              <span className="text-text-secondary w-20 shrink-0">Algorithm:</span>
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
  const hasIssues = chain.errors?.length > 0
  
  return (
    <div className={`border rounded-lg p-3 ${hasIssues ? 'border-amber-500 bg-amber-500/5' : 'border-border'}`}>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-sm font-medium">Chain {index + 1}</span>
        {chain.is_complete ? <Badge variant="green" size="xs">Complete</Badge> : <Badge variant="amber" size="xs">Incomplete</Badge>}
        <span className="text-xs text-text-secondary ml-auto">{chain.chain_length} certificate(s)</span>
      </div>
      
      <div className="flex items-center gap-1 text-xs flex-wrap">
        {chain.root && (
          <>
            <span className="px-2 py-1 bg-amber-500/10 text-amber-600 rounded">{chain.root.subject?.split(',')[0] || 'Root'}</span>
            <span className="text-text-secondary">→</span>
          </>
        )}
        {chain.intermediates?.map((int, i) => (
          <span key={i}>
            <span className="px-2 py-1 bg-blue-500/10 text-blue-600 rounded">{int.subject?.split(',')[0] || `Intermediate ${i + 1}`}</span>
            <span className="text-text-secondary mx-1">→</span>
          </span>
        ))}
        {chain.leaf && (
          <span className="px-2 py-1 bg-cyan-500/10 text-cyan-600 rounded">{chain.leaf.subject?.split(',')[0] || chain.leaf.san_dns?.[0] || 'Leaf'}</span>
        )}
      </div>
      
      {hasIssues && (
        <div className="mt-2 text-xs text-amber-600">
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
  const { errors, warnings, info } = validation
  if (!errors?.length && !warnings?.length && !info?.length) return null
  
  return (
    <div className="space-y-2">
      {errors?.map((err, i) => (
        <div key={`e${i}`} className="flex items-start gap-2 text-sm text-red-500 bg-red-500/10 p-2 rounded">
          <XCircle size={16} className="shrink-0 mt-0.5" /><span>{err}</span>
        </div>
      ))}
      {warnings?.map((warn, i) => (
        <div key={`w${i}`} className="flex items-start gap-2 text-sm text-amber-500 bg-amber-500/10 p-2 rounded">
          <WarningCircle size={16} className="shrink-0 mt-0.5" /><span>{warn}</span>
        </div>
      ))}
      {info?.map((inf, i) => (
        <div key={`i${i}`} className="flex items-start gap-2 text-sm text-blue-500 bg-blue-500/10 p-2 rounded">
          <CheckCircle size={16} className="shrink-0 mt-0.5" /><span>{inf}</span>
        </div>
      ))}
    </div>
  )
}

export default function SmartImportModal({ isOpen, onClose, onImportComplete }) {
  const { showNotification } = useNotification()
  const fileInputRef = useRef(null)
  
  const [step, setStep] = useState('input')
  const [content, setContent] = useState('')
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
  
  useEffect(() => {
    if (isOpen) {
      setStep('input')
      setContent('')
      setPassword('')
      setAnalysisResult(null)
      setImportResult(null)
      setSelectedObjects(new Set())
      setExpandedObjects(new Set())
    }
  }, [isOpen])
  
  const readFiles = useCallback(async (files) => {
    const contents = []
    for (const file of files) {
      try {
        if (file.name.endsWith('.p12') || file.name.endsWith('.pfx')) {
          const buffer = await file.arrayBuffer()
          const base64 = btoa(String.fromCharCode(...new Uint8Array(buffer)))
          contents.push(`-----BEGIN PKCS12-----\n${base64}\n-----END PKCS12-----`)
        } else if (file.name.endsWith('.der') || file.name.endsWith('.cer')) {
          const buffer = await file.arrayBuffer()
          const base64 = btoa(String.fromCharCode(...new Uint8Array(buffer)))
          contents.push(`-----BEGIN CERTIFICATE-----\n${base64}\n-----END CERTIFICATE-----`)
        } else {
          contents.push(await file.text())
        }
      } catch (err) {
        console.error(`Failed to read ${file.name}:`, err)
      }
    }
    setContent(prev => prev ? prev + '\n\n' + contents.join('\n\n') : contents.join('\n\n'))
  }, [])
  
  const handleDragOver = useCallback((e) => { e.preventDefault(); setIsDragOver(true) }, [])
  const handleDragLeave = useCallback((e) => { e.preventDefault(); setIsDragOver(false) }, [])
  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setIsDragOver(false)
    const files = Array.from(e.dataTransfer.files)
    if (files.length > 0) readFiles(files)
  }, [readFiles])
  const handleFileSelect = useCallback((e) => {
    const files = Array.from(e.target.files)
    if (files.length > 0) readFiles(files)
    e.target.value = ''
  }, [readFiles])
  
  const handleAnalyze = async () => {
    if (!content.trim()) return
    setIsAnalyzing(true)
    try {
      const response = await api.post('/api/v2/import/analyze', { content: content.trim(), password: password || undefined })
      setAnalysisResult(response.data.data)
      setSelectedObjects(new Set(response.data.data.objects.map((_, i) => i)))
      setStep('preview')
    } catch (err) {
      showNotification('error', err.response?.data?.error || 'Failed to analyze content')
    } finally {
      setIsAnalyzing(false)
    }
  }
  
  const handleImport = async () => {
    if (!analysisResult || selectedObjects.size === 0) return
    setIsImporting(true)
    setStep('importing')
    try {
      const response = await api.post('/api/v2/import/execute', {
        content: content.trim(),
        password: password || undefined,
        options: { ...importOptions, selected_indices: Array.from(selectedObjects) }
      })
      setImportResult(response.data.data)
      setStep('result')
      if (response.data.data.imported?.length > 0) {
        showNotification('success', `Successfully imported ${response.data.data.imported.length} object(s)`)
      }
    } catch (err) {
      showNotification('error', err.response?.data?.error || 'Import failed')
      setStep('preview')
    } finally {
      setIsImporting(false)
    }
  }
  
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
  
  const renderInputStep = () => (
    <div className="space-y-4">
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
        <p className="text-xs text-text-secondary">PEM, DER, PKCS12, PKCS7 files supported</p>
        <input ref={fileInputRef} type="file" multiple accept=".pem,.crt,.cer,.der,.key,.p12,.pfx,.p7b,.p7c,.csr" onChange={handleFileSelect} className="hidden" />
      </div>
      
      <div className="relative">
        <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-border"></div></div>
        <div className="relative flex justify-center text-xs uppercase"><span className="bg-bg-primary px-2 text-text-secondary">or paste content</span></div>
      </div>
      
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder="Paste PEM-encoded certificates, keys, CSRs, or chains here..."
        className="w-full h-48 p-3 font-mono text-xs border border-border rounded-lg bg-bg-secondary resize-none focus:outline-none focus:ring-2 focus:ring-accent-primary"
      />
      
      {content.includes('ENCRYPTED') && (
        <div className="flex items-center gap-2">
          <LockSimple size={16} className="text-amber-500" />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password for encrypted content"
            className="flex-1 px-3 py-2 text-sm border border-border rounded-lg bg-bg-secondary focus:outline-none focus:ring-2 focus:ring-accent-primary"
          />
        </div>
      )}
    </div>
  )
  
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
        <div className="flex gap-4 text-sm">
          {stats.certs > 0 && <div>🔐 {stats.certs} Certificate{stats.certs > 1 ? 's' : ''}</div>}
          {stats.cas > 0 && <div>🛡️ {stats.cas} CA{stats.cas > 1 ? 's' : ''}</div>}
          {stats.keys > 0 && <div>🔑 {stats.keys} Key{stats.keys > 1 ? 's' : ''}</div>}
          {stats.csrs > 0 && <div>📄 {stats.csrs} CSR{stats.csrs > 1 ? 's' : ''}</div>}
        </div>
        
        {chains?.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-sm font-medium">Certificate Chains</h3>
            {chains.map((chain, i) => <ChainCard key={i} chain={chain} index={i} />)}
          </div>
        )}
        
        {matching?.matched_pairs?.length > 0 && (
          <div className="text-sm text-green-600 bg-green-500/10 p-2 rounded flex items-center gap-2">
            <Link size={16} />
            {matching.matched_pairs.length} key-certificate pair{matching.matched_pairs.length > 1 ? 's' : ''} detected
          </div>
        )}
        
        <ValidationIssues validation={validation} />
        
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium">Detected Objects</h3>
            <button type="button" onClick={selectAll} className="text-xs text-accent-primary hover:underline">
              {selectedObjects.size === objects?.length ? 'Deselect All' : 'Select All'}
            </button>
          </div>
          
          <div className="space-y-2 max-h-64 overflow-y-auto pr-2">
            {objects?.map((obj, i) => (
              <ObjectCard key={i} obj={obj} expanded={expandedObjects.has(i)} onToggle={() => toggleExpand(i)} selected={selectedObjects.has(i)} onSelect={() => toggleObject(i)} />
            ))}
          </div>
        </div>
        
        <div className="border-t border-border pt-4">
          <h3 className="text-sm font-medium mb-2">Import Options</h3>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={importOptions.skip_duplicates} onChange={(e) => setImportOptions(prev => ({ ...prev, skip_duplicates: e.target.checked }))} className="w-4 h-4 rounded" />
              Skip duplicates
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={importOptions.import_cas} onChange={(e) => setImportOptions(prev => ({ ...prev, import_cas: e.target.checked }))} className="w-4 h-4 rounded" />
              Import CAs
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={importOptions.import_certs} onChange={(e) => setImportOptions(prev => ({ ...prev, import_certs: e.target.checked }))} className="w-4 h-4 rounded" />
              Import certificates
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={importOptions.import_keys} onChange={(e) => setImportOptions(prev => ({ ...prev, import_keys: e.target.checked }))} className="w-4 h-4 rounded" />
              Import keys
            </label>
          </div>
        </div>
      </div>
    )
  }
  
  const renderImportingStep = () => (
    <div className="flex flex-col items-center justify-center py-12">
      <ArrowsClockwise size={48} className="text-accent-primary animate-spin mb-4" />
      <p className="text-sm">Importing objects...</p>
    </div>
  )
  
  const renderResultStep = () => {
    const { imported, skipped, failed } = importResult || {}
    return (
      <div className="space-y-4">
        <div className="text-center py-6">
          {imported?.length > 0 ? (
            <>
              <CheckCircle size={48} className="text-green-500 mx-auto mb-3" weight="fill" />
              <h3 className="text-lg font-medium">Import Complete</h3>
              <p className="text-sm text-text-secondary">Successfully imported {imported.length} object{imported.length > 1 ? 's' : ''}</p>
            </>
          ) : (
            <>
              <WarningCircle size={48} className="text-amber-500 mx-auto mb-3" />
              <h3 className="text-lg font-medium">No Objects Imported</h3>
              <p className="text-sm text-text-secondary">{skipped?.length > 0 ? 'All objects were skipped or already exist' : 'Import failed'}</p>
            </>
          )}
        </div>
        
        {imported?.length > 0 && (
          <div className="space-y-1">
            <h4 className="text-sm font-medium text-green-600">Imported:</h4>
            {imported.map((item, i) => <div key={i} className="text-sm pl-4">✓ {item.type}: {item.name || item.subject || `#${item.id}`}</div>)}
          </div>
        )}
        
        {skipped?.length > 0 && (
          <div className="space-y-1">
            <h4 className="text-sm font-medium text-amber-600">Skipped:</h4>
            {skipped.map((item, i) => <div key={i} className="text-sm pl-4">⊘ {item.type}: {item.reason}</div>)}
          </div>
        )}
        
        {failed?.length > 0 && (
          <div className="space-y-1">
            <h4 className="text-sm font-medium text-red-600">Failed:</h4>
            {failed.map((item, i) => <div key={i} className="text-sm pl-4">✗ {item.type}: {item.error}</div>)}
          </div>
        )}
      </div>
    )
  }
  
  const renderFooter = () => {
    switch (step) {
      case 'input':
        return (
          <>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button onClick={handleAnalyze} disabled={!content.trim() || isAnalyzing}>{isAnalyzing ? 'Analyzing...' : 'Analyze'}</Button>
          </>
        )
      case 'preview':
        return (
          <>
            <Button variant="secondary" onClick={() => setStep('input')}>Back</Button>
            <Button onClick={handleImport} disabled={selectedObjects.size === 0 || isImporting}>Import {selectedObjects.size} Object{selectedObjects.size > 1 ? 's' : ''}</Button>
          </>
        )
      case 'result':
        return (
          <>
            <Button variant="secondary" onClick={() => { setStep('input'); setContent(''); setAnalysisResult(null); setImportResult(null) }}>Import More</Button>
            <Button onClick={() => { onImportComplete?.(); onClose() }}>Done</Button>
          </>
        )
      default:
        return null
    }
  }
  
  return (
    <Modal
      isOpen={isOpen}
      onClose={step !== 'importing' ? onClose : undefined}
      title={step === 'input' ? 'Smart Import' : step === 'preview' ? 'Review & Import' : step === 'importing' ? 'Importing...' : 'Import Result'}
      size="lg"
    >
      <div className="p-4">
        {step === 'input' && renderInputStep()}
        {step === 'preview' && renderPreviewStep()}
        {step === 'importing' && renderImportingStep()}
        {step === 'result' && renderResultStep()}
      </div>
      
      <div className="flex justify-end gap-2 p-4 border-t border-border">
        {renderFooter()}
      </div>
    </Modal>
  )
}
