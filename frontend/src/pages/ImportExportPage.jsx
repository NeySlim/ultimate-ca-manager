/**
 * Import / Export Page - Refactored with ResponsiveLayout
 */
import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { 
  UploadSimple, Certificate, ShieldCheck, FloppyDisk, FileArrowUp, 
  DownloadSimple, CloudArrowUp, ArrowsLeftRight, CheckCircle, File,
  Gear, Key
} from '@phosphor-icons/react'
import { 
  ResponsiveLayout, Button, Input, Select, Badge, DetailSection 
} from '../components'
import { opnsenseService, casService, certificatesService } from '../services'
import { useNotification } from '../contexts'
import { cn } from '../lib/utils'
import { ERRORS, SUCCESS, LABELS } from '../lib/messages'

const STORAGE_KEY = 'opnsense_config'

// Tab definitions - simplified for ResponsiveLayout
const TABS = [
  { id: 'import-cert', label: 'Certificate', icon: Certificate },
  { id: 'import-ca', label: 'CA', icon: ShieldCheck },
  { id: 'import-opnsense', label: 'OpnSense', icon: CloudArrowUp },
  { id: 'export-certs', label: 'Export Certs', icon: DownloadSimple },
  { id: 'export-cas', label: 'Export CAs', icon: DownloadSimple },
]

export default function ImportExportPage() {
  const { showSuccess, showError } = useNotification()
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState('import-cert')
  const [processing, setProcessing] = useState(false)
  const certFileRef = useRef(null)
  const caFileRef = useRef(null)
  
  // Import form state
  const [importName, setImportName] = useState('')
  const [importPassword, setImportPassword] = useState('')
  const [selectedFile, setSelectedFile] = useState(null)
  const [pemContent, setPemContent] = useState('')
  const [cas, setCas] = useState([])
  const [selectedCaId, setSelectedCaId] = useState('auto')
  
  // OpnSense connection details
  const [opnsenseHost, setOpnsenseHost] = useState('')
  const [opnsensePort, setOpnsensePort] = useState('443')
  const [opnsenseApiKey, setOpnsenseApiKey] = useState('')
  const [opnsenseApiSecret, setOpnsenseApiSecret] = useState('')
  const [testResult, setTestResult] = useState(null)
  const [testItems, setTestItems] = useState([])

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
      } catch (e) {}
    }
    loadCAs()
  }, [])

  const loadCAs = async () => {
    try {
      const response = await casService.getAll()
      setCas(response.data || [])
    } catch (e) {}
  }

  const handleTabChange = (tabId) => {
    setActiveTab(tabId)
    setSelectedFile(null)
    setImportName('')
    setImportPassword('')
    setPemContent('')
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
      showSuccess(result.message || SUCCESS.IMPORT.CERTIFICATE)
      setSelectedFile(null)
      setImportName('')
      setImportPassword('')
      setPemContent('')
      setSelectedCaId('auto')
      if (certFileRef.current) certFileRef.current.value = ''
      
      if (result.data) {
        if (result.message?.includes('CA')) {
          navigate(`/cas?selected=${result.data.id}`)
        } else {
          navigate(`/certificates?selected=${result.data.id}`)
        }
      }
    } catch (error) {
      showError(error.message || ERRORS.IMPORT_FAILED.GENERIC)
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
      showSuccess(result.message || SUCCESS.IMPORT.CA)
      setSelectedFile(null)
      setImportName('')
      setImportPassword('')
      setPemContent('')
      if (caFileRef.current) caFileRef.current.value = ''
      
      if (result.data) {
        navigate(`/cas?selected=${result.data.id}`)
      }
    } catch (error) {
      showError(error.message || ERRORS.IMPORT_FAILED.GENERIC)
    } finally {
      setProcessing(false)
    }
  }

  const handleExportAllCerts = async (format) => {
    setProcessing(true)
    try {
      const response = await certificatesService.getAll()
      const certs = response.data || []
      
      if (certs.length === 0) {
        showError('No certificates to export')
        return
      }
      
      const exportData = certs.map(c => ({
        id: c.id,
        common_name: c.common_name,
        serial_number: c.serial_number,
        status: c.status,
        valid_from: c.valid_from,
        valid_until: c.valid_until,
        issuer: c.issuer_name
      }))
      
      const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `certificates_export_${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
      
      showSuccess(`Exported ${certs.length} certificates`)
    } catch (err) {
      showError(ERRORS.EXPORT_FAILED.GENERIC)
    } finally {
      setProcessing(false)
    }
  }

  const handleExportAllCAs = async (format) => {
    setProcessing(true)
    try {
      const response = await casService.getAll()
      const allCas = response.data || []
      
      if (allCas.length === 0) {
        showError('No CAs to export')
        return
      }
      
      const exportData = allCas.map(ca => ({
        id: ca.id,
        name: ca.name,
        common_name: ca.common_name,
        ca_type: ca.ca_type,
        valid_from: ca.valid_from,
        valid_until: ca.valid_until,
        serial_number: ca.serial_number
      }))
      
      const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `cas_export_${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
      
      showSuccess(`Exported ${allCas.length} CAs`)
    } catch (err) {
      showError(ERRORS.EXPORT_FAILED.GENERIC)
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
        api_secret: opnsenseApiSecret
      })
      setTestResult(result.success ? 'success' : 'error')
      setTestItems(result.data?.items || [])
      if (result.success) {
        showSuccess('Connection successful!')
        localStorage.setItem(STORAGE_KEY, JSON.stringify({
          host: opnsenseHost,
          port: opnsensePort,
          api_key: opnsenseApiKey,
          api_secret: opnsenseApiSecret
        }))
      } else {
        showError(result.message || 'Connection failed')
      }
    } catch (error) {
      setTestResult('error')
      showError(error.message || 'Connection failed')
    } finally {
      setProcessing(false)
    }
  }

  const handleImportFromOpnsense = async () => {
    if (!testItems.length) {
      showError('Please test the connection first')
      return
    }
    setProcessing(true)
    try {
      const result = await opnsenseService.importCertificates({
        host: opnsenseHost,
        port: parseInt(opnsensePort),
        api_key: opnsenseApiKey,
        api_secret: opnsenseApiSecret
      })
      if (result.success) {
        showSuccess(result.message || `Imported ${result.data?.count || 0} items`)
        setTestResult(null)
        setTestItems([])
      } else {
        showError(result.message || 'Import failed')
      }
    } catch (error) {
      showError(error.message || ERRORS.IMPORT_FAILED.GENERIC)
    } finally {
      setProcessing(false)
    }
  }

  // Content for each tab
  const renderContent = () => {
    switch (activeTab) {
      case 'import-cert':
        return (
          <div className="space-y-4">
            <DetailSection title="Certificate File" icon={File} iconClass="icon-bg-blue">
              <div className="space-y-4">
                <div>
                  <input
                    ref={certFileRef}
                    type="file"
                    accept=".pem,.crt,.cer,.der,.p12,.pfx"
                    onChange={(e) => { setSelectedFile(e.target.files[0]); setPemContent('') }}
                    className="w-full text-sm text-text-secondary file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-accent-primary file:text-white hover:file:bg-accent-primary/90 file:cursor-pointer"
                  />
                  <p className="text-xs text-text-tertiary mt-2">Formats: .pem, .crt, .cer, .der, .p12, .pfx</p>
                </div>
                
                <div className="flex items-center gap-3">
                  <div className="flex-1 border-t border-border/50"></div>
                  <span className="text-xs text-text-tertiary uppercase tracking-wide">or paste PEM</span>
                  <div className="flex-1 border-t border-border/50"></div>
                </div>
                
                <textarea
                  value={pemContent}
                  onChange={(e) => { setPemContent(e.target.value); setSelectedFile(null); if (certFileRef.current) certFileRef.current.value = '' }}
                  placeholder="-----BEGIN CERTIFICATE-----&#10;...&#10;-----END CERTIFICATE-----"
                  rows={4}
                  className="w-full px-3 py-2 bg-bg-tertiary border border-border rounded-lg text-sm text-text-primary font-mono placeholder:text-text-tertiary focus:outline-none focus:ring-2 focus:ring-accent-primary/50 focus:border-accent-primary resize-y"
                />
              </div>
            </DetailSection>
            
            <DetailSection title="Options" icon={Gear} iconClass="icon-bg-violet">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
                <div className="md:col-span-2">
                  <Select
                    label="Link to CA (optional)"
                    value={selectedCaId}
                    onChange={(e) => setSelectedCaId(e.target.value)}
                    options={[
                      { value: 'auto', label: 'Auto-detect from issuer' },
                      ...cas.map(ca => ({ value: ca.id.toString(), label: ca.name }))
                    ]}
                  />
                </div>
              </div>
            </DetailSection>
            
            <div className="sticky bottom-0 bg-bg-primary py-4 -mx-4 px-4 md:relative md:mx-0 md:px-0 md:py-0 border-t border-border/50 md:border-0">
              <Button
                onClick={handleImportCertificate}
                disabled={processing || (!selectedFile && !pemContent.trim())}
                className="w-full md:w-auto"
                size="lg"
              >
                <FileArrowUp size={18} />
                {processing ? 'Importing...' : 'Import Certificate'}
              </Button>
            </div>
          </div>
        )
      
      case 'import-ca':
        return (
          <div className="space-y-4">
            <DetailSection title="CA Certificate File" icon={ShieldCheck} iconClass="icon-bg-violet">
              <div className="space-y-4">
                <div>
                  <input
                    ref={caFileRef}
                    type="file"
                    accept=".pem,.crt,.cer,.der,.p12,.pfx"
                    onChange={(e) => { setSelectedFile(e.target.files[0]); setPemContent('') }}
                    className="w-full text-sm text-text-secondary file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-accent-primary file:text-white hover:file:bg-accent-primary/90 file:cursor-pointer"
                  />
                  <p className="text-xs text-text-tertiary mt-2">Formats: .pem, .crt, .cer, .der, .p12, .pfx</p>
                </div>
                
                <div className="flex items-center gap-3">
                  <div className="flex-1 border-t border-border/50"></div>
                  <span className="text-xs text-text-tertiary uppercase tracking-wide">or paste PEM</span>
                  <div className="flex-1 border-t border-border/50"></div>
                </div>
                
                <textarea
                  value={pemContent}
                  onChange={(e) => { setPemContent(e.target.value); setSelectedFile(null); if (caFileRef.current) caFileRef.current.value = '' }}
                  placeholder="-----BEGIN CERTIFICATE-----&#10;...&#10;-----END CERTIFICATE-----"
                  rows={4}
                  className="w-full px-3 py-2 bg-bg-tertiary border border-border rounded-lg text-sm text-text-primary font-mono placeholder:text-text-tertiary focus:outline-none focus:ring-2 focus:ring-accent-primary/50 focus:border-accent-primary resize-y"
                />
              </div>
            </DetailSection>
            
            <DetailSection title="Options" icon={Gear} iconClass="icon-bg-teal">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
              </div>
            </DetailSection>
            
            <div className="sticky bottom-0 bg-bg-primary py-4 -mx-4 px-4 md:relative md:mx-0 md:px-0 md:py-0 border-t border-border/50 md:border-0">
              <Button
                onClick={handleImportCA}
                disabled={processing || (!selectedFile && !pemContent.trim())}
                className="w-full md:w-auto"
                size="lg"
              >
                <FileArrowUp size={18} />
                {processing ? 'Importing...' : 'Import CA'}
              </Button>
            </div>
          </div>
        )
      
      case 'import-opnsense':
        return (
          <div className="space-y-4">
            <DetailSection title="OpnSense Connection" icon={CloudArrowUp} iconClass="icon-bg-orange" description="Import certificates from OpnSense firewall">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Input 
                  label="Host" 
                  value={opnsenseHost}
                  onChange={(e) => setOpnsenseHost(e.target.value)}
                  placeholder="192.168.1.1"
                />
                <Input 
                  label="Port" 
                  value={opnsensePort}
                  onChange={(e) => setOpnsensePort(e.target.value)}
                  placeholder="443"
                />
                <Input 
                  label="API Key" 
                  value={opnsenseApiKey}
                  onChange={(e) => setOpnsenseApiKey(e.target.value)}
                  placeholder="Your API key"
                />
                <Input 
                  label="API Secret" 
                  type="password"
                  value={opnsenseApiSecret}
                  onChange={(e) => setOpnsenseApiSecret(e.target.value)}
                  placeholder="Your API secret"
                />
              </div>
            </DetailSection>
            
            {testResult && (
              <DetailSection title="Connection Result" icon={testResult === 'success' ? CheckCircle : Key} iconClass={testResult === 'success' ? 'icon-bg-emerald' : 'icon-bg-orange'}>
                {testResult === 'success' ? (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2 text-status-success">
                      <CheckCircle size={18} weight="fill" />
                      <span className="text-sm font-medium">Connected successfully</span>
                    </div>
                    {testItems.length > 0 && (
                      <div className="text-sm text-text-secondary">
                        Found {testItems.length} certificates available for import
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-sm text-status-error">Connection failed. Check your credentials.</div>
                )}
              </DetailSection>
            )}
            
            <div className="sticky bottom-0 bg-bg-primary py-4 -mx-4 px-4 md:relative md:mx-0 md:px-0 md:py-0 border-t border-border/50 md:border-0">
              <div className="flex gap-3">
                <Button
                  variant="secondary"
                  onClick={handleTestConf}
                  disabled={processing || !opnsenseHost || !opnsenseApiKey || !opnsenseApiSecret}
                  size="lg"
                >
                  {processing ? 'Testing...' : 'Test Connection'}
                </Button>
                {testResult === 'success' && testItems.length > 0 && (
                  <Button
                    onClick={handleImportFromOpnsense}
                    disabled={processing}
                    size="lg"
                  >
                    <FileArrowUp size={18} />
                    Import {testItems.length} Certificates
                  </Button>
                )}
              </div>
            </div>
          </div>
        )
      
      case 'export-certs':
        return (
          <div className="space-y-4">
            <DetailSection title="Export All Certificates" icon={Certificate} iconClass="icon-bg-emerald" description="Download all certificates in your preferred format">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <Button variant="secondary" onClick={() => handleExportAllCerts('pem')} className="justify-center">
                  <DownloadSimple size={16} /> PEM Format
                </Button>
                <Button variant="secondary" onClick={() => handleExportAllCerts('der')} className="justify-center">
                  <DownloadSimple size={16} /> DER Format
                </Button>
                <Button onClick={() => handleExportAllCerts('pkcs12')} className="justify-center">
                  <DownloadSimple size={16} /> PKCS#12
                </Button>
              </div>
            </DetailSection>
          </div>
        )
      
      case 'export-cas':
        return (
          <div className="space-y-4">
            <DetailSection title="Export All Certificate Authorities" icon={ShieldCheck} iconClass="icon-bg-teal" description={`Download all CA certificates (${cas.length} total)`}>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <Button variant="secondary" onClick={() => handleExportAllCAs('pem')} className="justify-center">
                  <DownloadSimple size={16} /> PEM Format
                </Button>
                <Button onClick={() => handleExportAllCAs('der')} className="justify-center">
                  <DownloadSimple size={16} /> DER Format
                </Button>
              </div>
            </DetailSection>
          </div>
        )
      
      default:
        return null
    }
  }

  return (
    <ResponsiveLayout
      title="Import / Export"
      subtitle="Transfer certificates and CAs"
      icon={ArrowsLeftRight}
      tabs={TABS}
      activeTab={activeTab}
      onTabChange={handleTabChange}
      helpPageKey="importExport"
    >
      <div className="max-w-3xl mx-auto p-4 md:p-6">
        {renderContent()}
      </div>
    </ResponsiveLayout>
  )
}
