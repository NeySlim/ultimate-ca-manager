/**
 * Import/Export Page
 */
import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { UploadSimple, Certificate, ShieldCheck, Flask, FloppyDisk, FileArrowUp, DownloadSimple, ArrowsLeftRight, CheckCircle, Database, CloudArrowUp } from '@phosphor-icons/react'
import {
  ExplorerPanel, DetailsPanel, Button, ExportDropdown, Input, LoadingSpinner, Select, Card, Badge
} from '../components'
import { opnsenseService, casService, certificatesService } from '../services'
import { useNotification } from '../contexts'

const STORAGE_KEY = 'opnsense_config'

export default function ImportExportPage() {
  const { showSuccess, showError } = useNotification()
  const navigate = useNavigate()
  const [selectedAction, setSelectedAction] = useState('import-cert')
  const [processing, setProcessing] = useState(false)
  const certFileRef = useRef(null)
  const caFileRef = useRef(null)
  
  // Import form state
  const [importName, setImportName] = useState('')
  const [importPassword, setImportPassword] = useState('')
  const [selectedFile, setSelectedFile] = useState(null)
  const [pemContent, setPemContent] = useState('')  // For pasting PEM
  const [cas, setCas] = useState([])
  const [selectedCaId, setSelectedCaId] = useState('auto')
  
  // OpnSense connection details
  const [opnsenseHost, setOpnsenseHost] = useState('')
  const [opnsensePort, setOpnsensePort] = useState('443')
  const [opnsenseApiKey, setOpnsenseApiKey] = useState('')
  const [opnsenseApiSecret, setOpnsenseApiSecret] = useState('')
  const [testResult, setTestResult] = useState(null)
  const [testItems, setTestItems] = useState([]) // Store all items from test

  // Load saved config on mount
  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      try {
        const config = JSON.parse(saved)
        setOpnsenseHost(config.host || '')
        setOpnsensePort(config.port || '443')
        setOpnsenseApiKey(config.api_key || '')
        setOpnsenseApiSecret(config.api_secret || '')
      } catch (e) {
        // Ignore
      }
    }
    // Load CAs for import dropdown
    loadCAs()
  }, [])

  const loadCAs = async () => {
    try {
      const response = await casService.getAll()
      setCas(response.data || [])
    } catch (e) {
      // Ignore
    }
  }

  const handleImportCertificate = async () => {
    if (!selectedFile && !pemContent.trim()) {
      showError('Please select a file or paste PEM content')
      return
    }
    setProcessing(true)
    try {
      const formData = new FormData()
      if (selectedFile) {
        formData.append('file', selectedFile)
      } else {
        formData.append('pem_content', pemContent)
      }
      if (importName) formData.append('name', importName)
      if (importPassword) formData.append('password', importPassword)
      if (selectedCaId && selectedCaId !== 'auto') formData.append('ca_id', selectedCaId)
      formData.append('format', 'auto')
      
      const result = await certificatesService.import(formData)
      showSuccess(result.message || 'Certificate imported successfully')
      setSelectedFile(null)
      setImportName('')
      setImportPassword('')
      setPemContent('')
      setSelectedCaId('auto')
      if (certFileRef.current) certFileRef.current.value = ''
      
      // Navigate to the right page with the new item selected
      if (result.data) {
        if (result.message?.includes('CA')) {
          navigate(`/cas?selected=${result.data.id}`)
        } else {
          navigate(`/certificates?selected=${result.data.id}`)
        }
      }
    } catch (error) {
      showError(error.message || 'Failed to import certificate')
    } finally {
      setProcessing(false)
    }
  }

  const handleImportCA = async () => {
    if (!selectedFile && !pemContent.trim()) {
      showError('Please select a file or paste PEM content')
      return
    }
    setProcessing(true)
    try {
      const formData = new FormData()
      if (selectedFile) {
        formData.append('file', selectedFile)
      } else {
        formData.append('pem_content', pemContent)
      }
      if (importName) formData.append('name', importName)
      if (importPassword) formData.append('password', importPassword)
      formData.append('format', 'auto')
      
      const result = await casService.import(formData)
      showSuccess(result.message || 'CA imported successfully')
      setSelectedFile(null)
      setImportName('')
      setImportPassword('')
      setPemContent('')
      if (caFileRef.current) caFileRef.current.value = ''
      
      // Navigate to CAs page with the new CA selected
      if (result.data) {
        navigate(`/cas?selected=${result.data.id}`)
      }
    } catch (error) {
      showError(error.message || 'Failed to import CA')
    } finally {
      setProcessing(false)
    }
  }

  const handleSaveConfig = () => {
    if (!opnsenseHost || !opnsenseApiKey || !opnsenseApiSecret) {
      showError('Please fill all fields')
      return
    }
    const config = {
      host: opnsenseHost,
      port: opnsensePort,
      api_key: opnsenseApiKey,
      api_secret: opnsenseApiSecret
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(config))
    showSuccess('Configuration saved')
  }

  const handleExportAllCerts = async (format) => {
    setProcessing(true)
    try {
      // Fetch all certificates
      const { certificatesService } = await import('../services')
      const response = await certificatesService.getAll({ per_page: 1000 })
      const certs = response.data || []
      
      if (certs.length === 0) {
        showError('No certificates to export')
        return
      }
      
      // Create export data
      const exportData = certs.map(c => ({
        id: c.id,
        common_name: c.common_name,
        serial_number: c.serial_number,
        status: c.status,
        valid_from: c.valid_from,
        valid_until: c.valid_until,
        issuer: c.issuer_name
      }))
      
      // Download as JSON
      const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `certificates_export_${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
      
      showSuccess(`Exported ${certs.length} certificates`)
    } catch (err) {
      showError('Failed to export certificates')
    } finally {
      setProcessing(false)
    }
  }

  const handleExportAllCAs = async (format) => {
    setProcessing(true)
    try {
      // Fetch all CAs
      const { casService } = await import('../services')
      const response = await casService.getAll()
      const cas = response.data || []
      
      if (cas.length === 0) {
        showError('No CAs to export')
        return
      }
      
      // Create export data
      const exportData = cas.map(ca => ({
        id: ca.id,
        name: ca.name,
        common_name: ca.common_name,
        ca_type: ca.ca_type,
        valid_from: ca.valid_from,
        valid_until: ca.valid_until,
        serial_number: ca.serial_number
      }))
      
      // Download as JSON
      const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `cas_export_${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
      
      showSuccess(`Exported ${cas.length} CAs`)
    } catch (err) {
      showError('Failed to export CAs')
    } finally {
      setProcessing(false)
    }
  }

  const handleTestConf = async () => {
    if (!opnsenseHost || !opnsenseApiKey || !opnsenseApiSecret) {
      showError('Please fill all fields')
      return
    }
    setProcessing(true)
    try {
      const result = await opnsenseService.test({
        host: opnsenseHost,
        port: parseInt(opnsensePort),
        api_key: opnsenseApiKey,
        api_secret: opnsenseApiSecret,
        verify_ssl: false
      })
      
      if (result.success) {
        setTestResult(result.stats)
        setTestItems(result.items || []) // Store items for import
        showSuccess(`Found ${result.stats.certificates} certificates and ${result.stats.cas} CAs`)
      } else {
        showError(result.error || 'Connection failed')
        setTestResult(null)
        setTestItems([])
      }
    } catch (error) {
      showError(error.message || 'Failed to test connection')
      setTestResult(null)
      setTestItems([])
    } finally {
      setProcessing(false)
    }
  }

  const handleImport = async () => {
    if (!testResult || testItems.length === 0) {
      showError('Please test connection first')
      return
    }
    setProcessing(true)
    try {
      // Extract all item IDs from test results
      const itemIds = testItems.map(item => item.id)
      
      
      const result = await opnsenseService.import({
        host: opnsenseHost,
        port: parseInt(opnsensePort),
        api_key: opnsenseApiKey,
        api_secret: opnsenseApiSecret,
        verify_ssl: false,
        items: itemIds // Send all item UUIDs
      })
      
      
      if (result.success) {
        const total = result.imported.cas + result.imported.certificates
        const skipped = result.skipped || 0
        if (total > 0) {
          showSuccess(`Imported ${total} items (${result.imported.cas} CAs, ${result.imported.certificates} certificates)${skipped > 0 ? `, ${skipped} skipped` : ''}`)
        } else if (skipped > 0) {
          showSuccess(`All ${skipped} items already exist (skipped)`)
        } else {
          showError('No items were imported')
        }
        setTestResult(null)
        setTestItems([])
      } else {
        showError(result.error || 'Import failed')
      }
    } catch (error) {
      showError(error.message || 'Failed to import')
    } finally {
      setProcessing(false)
    }
  }

  const actions = [
    { id: 'import-cert', title: 'Import Certificate', icon: <Certificate size={18} weight="duotone" />, category: 'import' },
    { id: 'import-ca', title: 'Import CA', icon: <ShieldCheck size={18} weight="duotone" />, category: 'import' },
    { id: 'import-opnsense', title: 'Import from OpnSense', icon: <CloudArrowUp size={18} weight="duotone" />, category: 'import' },
    { id: 'export-certs', title: 'Export Certificates', icon: <DownloadSimple size={18} weight="duotone" />, category: 'export' },
    { id: 'export-cas', title: 'Export CAs', icon: <DownloadSimple size={18} weight="duotone" />, category: 'export' },
  ]

  return (
    <>
      <ExplorerPanel title="Import/Export">
        <div className="space-y-4">
          {/* Stats Cards */}
          <div className="px-2 space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-text-secondary px-1">
              Quick Stats
            </h3>
            <div className="grid grid-cols-2 gap-2">
              <Card className="p-2 text-center">
                <div className="text-lg font-bold text-accent">{cas.length}</div>
                <div className="text-xs text-text-secondary">CAs</div>
              </Card>
              <Card className="p-2 text-center">
                <div className="text-lg font-bold text-emerald-500">
                  <Database size={18} className="inline" />
                </div>
                <div className="text-xs text-text-secondary">Ready</div>
              </Card>
            </div>
          </div>

          {/* Import Section */}
          <div className="space-y-1">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-text-secondary px-3">
              Import
            </h3>
            {actions.filter(a => a.category === 'import').map(action => (
              <button 
                key={action.id} 
                onClick={() => { setSelectedAction(action.id); setSelectedFile(null); setImportName(''); setImportPassword(''); setPemContent('') }}
                className={`w-full flex items-center gap-3 px-3 py-2 rounded-md transition-colors ${
                  selectedAction === action.id 
                    ? 'bg-accent/10 text-accent border-l-2 border-accent' 
                    : 'hover:bg-bg-tertiary/50 text-text-primary'
                }`}
              >
                <span className={`p-1.5 rounded ${selectedAction === action.id ? 'bg-accent/20' : 'bg-bg-tertiary'}`}>
                  {action.icon}
                </span>
                <span className="text-sm font-medium">{action.title}</span>
              </button>
            ))}
          </div>

          {/* Export Section */}
          <div className="space-y-1">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-text-secondary px-3">
              Export
            </h3>
            {actions.filter(a => a.category === 'export').map(action => (
              <button 
                key={action.id} 
                onClick={() => setSelectedAction(action.id)}
                className={`w-full flex items-center gap-3 px-3 py-2 rounded-md transition-colors ${
                  selectedAction === action.id 
                    ? 'bg-accent/10 text-accent border-l-2 border-accent' 
                    : 'hover:bg-bg-tertiary/50 text-text-primary'
                }`}
              >
                <span className={`p-1.5 rounded ${selectedAction === action.id ? 'bg-accent/20' : 'bg-bg-tertiary'}`}>
                  {action.icon}
                </span>
                <span className="text-sm font-medium">{action.title}</span>
              </button>
            ))}
          </div>

          {/* Supported Formats */}
          <div className="px-3 pt-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-text-secondary mb-2">
              Supported Formats
            </h3>
            <div className="flex flex-wrap gap-1">
              <Badge variant="blue" size="sm">PEM</Badge>
              <Badge variant="purple" size="sm">DER</Badge>
              <Badge variant="emerald" size="sm">PKCS#12</Badge>
              <Badge variant="orange" size="sm">CRT</Badge>
            </div>
          </div>
        </div>
      </ExplorerPanel>

      <DetailsPanel breadcrumb={[{ label: 'Import/Export' }]} title={actions.find(a => a.id === selectedAction)?.title || 'Import/Export'}
        actions={
          selectedAction === 'export-certs' ? (
            <ExportDropdown onExport={handleExportAllCerts} formats={['pem', 'der', 'pkcs12']} />
          ) : selectedAction === 'export-cas' ? (
            <ExportDropdown onExport={handleExportAllCAs} formats={['pem', 'der']} />
          ) : null
        }>
        {/* Import Certificate */}
        {selectedAction === 'import-cert' && (
          <div className="max-w-2xl space-y-4">
            <h3 className="text-sm font-semibold text-text-primary">Import Certificate</h3>
            <p className="text-sm text-text-secondary">Import a certificate from a file or paste PEM content. Supports PEM, DER, and PKCS#12 formats.</p>
            
            <div className="p-4 bg-bg-tertiary border border-border rounded-sm space-y-4">
              <div>
                <label className="block text-xs font-medium text-text-primary mb-1">Certificate File</label>
                <input
                  ref={certFileRef}
                  type="file"
                  accept=".pem,.crt,.cer,.der,.p12,.pfx"
                  onChange={(e) => { setSelectedFile(e.target.files[0]); setPemContent('') }}
                  className="w-full text-sm text-text-secondary file:mr-4 file:py-1.5 file:px-3 file:rounded-sm file:border-0 file:text-sm file:bg-accent-primary file:text-white hover:file:bg-accent-primary/80"
                />
                <p className="text-xs text-text-secondary mt-1">Accepted: .pem, .crt, .cer, .der, .p12, .pfx</p>
              </div>
              
              <div className="flex items-center gap-3">
                <div className="flex-1 border-t border-border"></div>
                <span className="text-xs text-text-secondary">OR paste PEM content</span>
                <div className="flex-1 border-t border-border"></div>
              </div>
              
              <div>
                <label className="block text-xs font-medium text-text-primary mb-1">Paste PEM Content</label>
                <textarea
                  value={pemContent}
                  onChange={(e) => { setPemContent(e.target.value); setSelectedFile(null); if (certFileRef.current) certFileRef.current.value = '' }}
                  placeholder="-----BEGIN CERTIFICATE-----&#10;...&#10;-----END CERTIFICATE-----"
                  rows={6}
                  className="w-full px-2 py-1.5 bg-bg-secondary border border-border rounded-sm text-sm text-text-primary font-mono placeholder-text-secondary focus:outline-none focus:ring-1 focus:ring-accent-primary resize-y"
                />
              </div>
              
              <Input 
                label="Display Name (optional)" 
                value={importName}
                onChange={(e) => setImportName(e.target.value)}
                placeholder="My Certificate"
              />
              
              <Input 
                label="Password (for PKCS#12)" 
                type="password"
                value={importPassword}
                onChange={(e) => setImportPassword(e.target.value)}
                placeholder="Enter password if needed"
              />
              
              <Select
                label="Link to CA (optional)"
                value={selectedCaId}
                onChange={(e) => setSelectedCaId(e.target.value)}
                options={[
                  { value: 'auto', label: 'Auto-detect from issuer' },
                  ...cas.map(ca => ({ value: ca.id.toString(), label: ca.name }))
                ]}
              />
              
              <div className="flex gap-3 pt-2">
                <Button onClick={handleImportCertificate} disabled={processing || (!selectedFile && !pemContent.trim())}>
                  {processing ? <LoadingSpinner size="sm" /> : <FileArrowUp size={16} />}
                  Import Certificate
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Import CA */}
        {selectedAction === 'import-ca' && (
          <div className="max-w-2xl space-y-4">
            <h3 className="text-sm font-semibold text-text-primary">Import Certificate Authority</h3>
            <p className="text-sm text-text-secondary">Import a CA certificate from a file or paste PEM content. Supports PEM, DER, and PKCS#12 formats.</p>
            
            <div className="p-4 bg-bg-tertiary border border-border rounded-sm space-y-4">
              <div>
                <label className="block text-xs font-medium text-text-primary mb-1">CA Certificate File</label>
                <input
                  ref={caFileRef}
                  type="file"
                  accept=".pem,.crt,.cer,.der,.p12,.pfx"
                  onChange={(e) => { setSelectedFile(e.target.files[0]); setPemContent('') }}
                  className="w-full text-sm text-text-secondary file:mr-4 file:py-1.5 file:px-3 file:rounded-sm file:border-0 file:text-sm file:bg-accent-primary file:text-white hover:file:bg-accent-primary/80"
                />
                <p className="text-xs text-text-secondary mt-1">Accepted: .pem, .crt, .cer, .der, .p12, .pfx</p>
              </div>
              
              <div className="flex items-center gap-3">
                <div className="flex-1 border-t border-border"></div>
                <span className="text-xs text-text-secondary">OR paste PEM content</span>
                <div className="flex-1 border-t border-border"></div>
              </div>
              
              <div>
                <label className="block text-xs font-medium text-text-primary mb-1">Paste PEM Content</label>
                <textarea
                  value={pemContent}
                  onChange={(e) => { setPemContent(e.target.value); setSelectedFile(null); if (caFileRef.current) caFileRef.current.value = '' }}
                  placeholder="-----BEGIN CERTIFICATE-----&#10;...&#10;-----END CERTIFICATE-----"
                  rows={6}
                  className="w-full px-2 py-1.5 bg-bg-secondary border border-border rounded-sm text-sm text-text-primary font-mono placeholder-text-secondary focus:outline-none focus:ring-1 focus:ring-accent-primary resize-y"
                />
              </div>
              
              <Input 
                label="Display Name (optional)" 
                value={importName}
                onChange={(e) => setImportName(e.target.value)}
                placeholder="My Root CA"
              />
              
              <Input 
                label="Password (for PKCS#12)" 
                type="password"
                value={importPassword}
                onChange={(e) => setImportPassword(e.target.value)}
                placeholder="Enter password if needed"
              />
              
              <div className="flex gap-3 pt-2">
                <Button onClick={handleImportCA} disabled={processing || (!selectedFile && !pemContent.trim())}>
                  {processing ? <LoadingSpinner size="sm" /> : <FileArrowUp size={16} />}
                  Import CA
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Export Certificates */}
        {selectedAction === 'export-certs' && (
          <div className="max-w-2xl space-y-4">
            <h3 className="text-sm font-semibold text-text-primary">Export All Certificates</h3>
            <p className="text-sm text-text-secondary">Download all certificates in a single archive. Choose your preferred format using the Export dropdown above.</p>
            <div className="p-4 bg-bg-tertiary border border-border rounded-sm">
              <h4 className="text-xs font-semibold text-text-primary uppercase mb-2">Available Formats</h4>
              <ul className="text-sm text-text-secondary space-y-1">
                <li><strong>PEM:</strong> Base64 encoded, widely compatible</li>
                <li><strong>DER:</strong> Binary format, compact</li>
                <li><strong>PKCS#12:</strong> Includes private keys (password protected)</li>
              </ul>
            </div>
          </div>
        )}

        {/* Export CAs */}
        {selectedAction === 'export-cas' && (
          <div className="max-w-2xl space-y-4">
            <h3 className="text-sm font-semibold text-text-primary">Export All Certificate Authorities</h3>
            <p className="text-sm text-text-secondary">Download all CAs including their hierarchy. Use the Export dropdown above to select format.</p>
          </div>
        )}

        {/* Import from OpnSense */}
        {selectedAction === 'import-opnsense' && (
          <div className="max-w-2xl space-y-4">
            <h3 className="text-sm font-semibold text-text-primary">Import from OpnSense</h3>
            <p className="text-sm text-text-secondary">Connect to OpnSense API to import certificates and CAs.</p>
            
            <div className="p-4 bg-bg-tertiary border border-border rounded-sm space-y-4">
              <Input label="OpnSense Host" value={opnsenseHost} 
                onChange={(e) => setOpnsenseHost(e.target.value)} 
                placeholder="192.168.1.1" />
              
              <Input label="Port" value={opnsensePort} 
                onChange={(e) => setOpnsensePort(e.target.value)} 
                placeholder="443" />
              
              <Input label="API Key" value={opnsenseApiKey} 
                onChange={(e) => setOpnsenseApiKey(e.target.value)} 
                placeholder="Enter API Key" />
              
              <Input label="API Secret" type="password" value={opnsenseApiSecret} 
                onChange={(e) => setOpnsenseApiSecret(e.target.value)} 
                placeholder="Enter API Secret" />
              
              <div className="flex gap-3 pt-2">
                <Button variant="secondary" onClick={handleSaveConfig} disabled={processing}>
                  <FloppyDisk size={16} />Save Conf
                </Button>
                <Button variant="secondary" onClick={handleTestConf} disabled={processing}>
                  {processing ? <LoadingSpinner size="sm" /> : <Flask size={16} />}Test Conf
                </Button>
                <Button onClick={handleImport} disabled={processing || !testResult}>
                  {processing ? <LoadingSpinner size="sm" /> : <UploadSimple size={16} />}Import
                </Button>
              </div>
            </div>

            {testResult && (
              <div className="p-4 bg-green-500/10 border border-green-500/30 rounded-sm">
                <h4 className="text-sm font-semibold text-green-400 mb-2">✓ Connection Successful</h4>
                <p className="text-sm text-text-secondary"><strong>CAs:</strong> {testResult.cas}</p>
                <p className="text-sm text-text-secondary"><strong>Certificates:</strong> {testResult.certificates}</p>
              </div>
            )}
          </div>
        )}
      </DetailsPanel>

    </>
  )
}
