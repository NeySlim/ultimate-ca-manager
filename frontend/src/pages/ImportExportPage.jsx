/**
 * Import / Export Page - Unified with Smart Import
 */
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { 
  UploadSimple, DownloadSimple, CloudArrowUp, ArrowsLeftRight, 
  CheckCircle, Certificate, ShieldCheck, Key
} from '@phosphor-icons/react'
import { 
  ResponsiveLayout, Button, Input, DetailSection 
} from '../components'
import { SmartImportWidget } from '../components/SmartImport'
import { opnsenseService, casService, certificatesService } from '../services'
import { useNotification } from '../contexts'
import { SUCCESS } from '../lib/messages'

const STORAGE_KEY = 'opnsense_config'

// Simplified tabs - Smart Import replaces old import tabs
const TABS = [
  { id: 'import', label: 'Import', icon: UploadSimple },
  { id: 'opnsense', label: 'OpnSense', icon: CloudArrowUp },
  { id: 'export-certs', label: 'Export Certs', icon: DownloadSimple },
  { id: 'export-cas', label: 'Export CAs', icon: DownloadSimple },
]

export default function ImportExportPage() {
  const { showSuccess, showError } = useNotification()
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState('import')
  const [processing, setProcessing] = useState(false)
  const [cas, setCas] = useState([])
  
  // OpnSense connection details
  const [opnsenseHost, setOpnsenseHost] = useState('')
  const [opnsensePort, setOpnsensePort] = useState('443')
  const [opnsenseApiKey, setOpnsenseApiKey] = useState('')
  const [opnsenseApiSecret, setOpnsenseApiSecret] = useState('')
  const [testResult, setTestResult] = useState(null)
  const [testItems, setTestItems] = useState([])

  // Load saved config on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved) {
        const config = JSON.parse(saved)
        setOpnsenseHost(config.host || '')
        setOpnsensePort(config.port || '443')
        setOpnsenseApiKey(config.api_key || '')
        setOpnsenseApiSecret(config.api_secret || '')
      }
    } catch (e) {}
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
  }

  // OpnSense handlers
  const saveOpnsenseConfig = () => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        host: opnsenseHost,
        port: opnsensePort,
        api_key: opnsenseApiKey,
        api_secret: opnsenseApiSecret
      }))
      showSuccess('Configuration saved')
    } catch (e) {}
  }

  const handleTestConf = async () => {
    setProcessing(true)
    setTestResult(null)
    try {
      const result = await opnsenseService.test({
        host: opnsenseHost,
        port: opnsensePort,
        api_key: opnsenseApiKey,
        api_secret: opnsenseApiSecret
      })
      setTestResult('success')
      setTestItems(result.data?.items || [])
      saveOpnsenseConfig()
    } catch (error) {
      setTestResult('error')
      showError(error.message || 'Connection failed')
    } finally {
      setProcessing(false)
    }
  }

  const handleImportFromOpnsense = async () => {
    setProcessing(true)
    try {
      const result = await opnsenseService.import({
        host: opnsenseHost,
        port: opnsensePort,
        api_key: opnsenseApiKey,
        api_secret: opnsenseApiSecret
      })
      showSuccess(result.message || SUCCESS.IMPORT.OPNSENSE)
      loadCAs()
    } catch (error) {
      showError(error.message || 'Import failed')
    } finally {
      setProcessing(false)
    }
  }

  // Export handlers
  const handleExportAllCerts = async (format) => {
    try {
      const blob = await certificatesService.exportAll(format)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      // Map format to extension
      const ext = { pem: 'pem', der: 'der', pkcs12: 'p12', pkcs7: 'p7b', pfx: 'pfx', p7b: 'p7b' }[format] || format
      a.download = `certificates.${ext}`
      a.click()
      URL.revokeObjectURL(url)
      showSuccess('Certificates exported')
    } catch (error) {
      showError(error.message || 'Export failed')
    }
  }

  const handleExportAllCAs = async (format) => {
    try {
      const blob = await casService.exportAll(format)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const ext = { pem: 'pem', der: 'der', pkcs12: 'p12', pkcs7: 'p7b', pfx: 'pfx', p7b: 'p7b' }[format] || format
      a.download = `ca-certificates.${ext}`
      a.click()
      URL.revokeObjectURL(url)
      showSuccess('CA certificates exported')
    } catch (error) {
      showError(error.message || 'Export failed')
    }
  }

  // Smart import complete handler
  const handleImportComplete = (result) => {
    if (result?.imported?.length > 0) {
      // Navigate to first imported item
      const first = result.imported[0]
      if (first.type === 'ca' || first.type === 'ca_certificate') {
        navigate(`/cas?selected=${first.id}`)
      } else if (first.type === 'certificate') {
        navigate(`/certificates?selected=${first.id}`)
      }
    }
  }

  // Content for each tab
  const renderContent = () => {
    switch (activeTab) {
      case 'import':
        return (
          <DetailSection 
            title="Smart Import" 
            icon={UploadSimple} 
            iconClass="icon-bg-violet" 
            description="Import certificates, keys, CSRs, and chains from any format"
          >
            <SmartImportWidget onImportComplete={handleImportComplete} />
          </DetailSection>
        )
      
      case 'opnsense':
        return (
          <div className="space-y-4">
            <DetailSection title="OpnSense Connection" icon={CloudArrowUp} iconClass="icon-bg-orange" description="Import certificates from OpnSense firewall">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Input 
                  label="Host / IP" 
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
                  placeholder="API Key"
                />
                <Input 
                  label="API Secret" 
                  type="password"
                  value={opnsenseApiSecret}
                  onChange={(e) => setOpnsenseApiSecret(e.target.value)}
                  placeholder="API Secret"
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
            
            <div className="flex gap-3 pt-2">
              <Button
                variant="secondary"
                onClick={handleTestConf}
                disabled={processing || !opnsenseHost || !opnsenseApiKey || !opnsenseApiSecret}
                size="lg"
              >
                {processing ? 'Testing...' : 'Test Connection'}
              </Button>
              {testResult === 'success' && testItems.length > 0 && (
                <Button onClick={handleImportFromOpnsense} disabled={processing} size="lg">
                  <UploadSimple size={18} />
                  Import {testItems.length} Certificates
                </Button>
              )}
            </div>
          </div>
        )
      
      case 'export-certs':
        return (
          <DetailSection title="Export All Certificates" icon={Certificate} iconClass="icon-bg-blue" description="Download all certificates in a single file">
            <div className="grid grid-cols-2 gap-3">
              <Button variant="secondary" onClick={() => handleExportAllCerts('pem')} className="justify-center">
                <DownloadSimple size={16} /> PEM Bundle
              </Button>
              <Button onClick={() => handleExportAllCerts('pkcs7')} className="justify-center">
                <DownloadSimple size={16} /> P7B Bundle
              </Button>
            </div>
            <p className="text-xs text-text-tertiary mt-2">Use individual certificate export for DER, PKCS#12, or PFX formats</p>
          </DetailSection>
        )
      
      case 'export-cas':
        return (
          <DetailSection title="Export All CAs" icon={ShieldCheck} iconClass="icon-bg-green" description={`Download all CA certificates (${cas.length} total)`}>
            <div className="grid grid-cols-2 gap-3">
              <Button variant="secondary" onClick={() => handleExportAllCAs('pem')} className="justify-center">
                <DownloadSimple size={16} /> PEM Bundle
              </Button>
              <Button onClick={() => handleExportAllCAs('pkcs7')} className="justify-center">
                <DownloadSimple size={16} /> P7B Bundle
              </Button>
            </div>
            <p className="text-xs text-text-tertiary mt-2">Use individual CA export for DER, PKCS#12, or PFX formats</p>
          </DetailSection>
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
