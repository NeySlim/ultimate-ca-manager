/**
 * Import/Export Page
 */
import { useState, useEffect } from 'react'
import { UploadSimple, Certificate, ShieldCheck, Flask, FloppyDisk } from '@phosphor-icons/react'
import {
  ExplorerPanel, DetailsPanel, Button, ExportDropdown, Input, LoadingSpinner
} from '../components'
import { opnsenseService } from '../services'
import { useNotification } from '../contexts'

const STORAGE_KEY = 'opnsense_config'

export default function ImportExportPage() {
  const { showSuccess, showError } = useNotification()
  const [selectedAction, setSelectedAction] = useState('export-certs')
  const [processing, setProcessing] = useState(false)
  
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
        console.error('Failed to load saved config:', e)
      }
    }
  }, [])

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
    { id: 'export-certs', title: 'Export All Certificates', icon: <Certificate size={20} />, category: 'export' },
    { id: 'export-cas', title: 'Export All CAs', icon: <ShieldCheck size={20} />, category: 'export' },
    { id: 'import-opnsense', title: 'Import from OpnSense', icon: <UploadSimple size={20} />, category: 'import' }
  ]

  return (
    <>
      <ExplorerPanel title="Import/Export">
        <div className="px-2 py-1.5 space-y-1">
          <p className="text-xs font-semibold text-text-secondary uppercase px-2 mb-2">Export</p>
          {actions.filter(a => a.category === 'export').map(action => (
            <button key={action.id} onClick={() => setSelectedAction(action.id)}
              className={`w-full flex items-start gap-3 px-2 py-1.5 rounded-sm transition-colors ${
                selectedAction === action.id ? 'bg-bg-tertiary text-accent' : 'hover:bg-bg-tertiary/50 text-text-primary'
              }`}>
              {action.icon}
              <span className="text-sm font-medium">{action.title}</span>
            </button>
          ))}
          <p className="text-xs font-semibold text-text-secondary uppercase px-2 mb-2 mt-3">Import</p>
          {actions.filter(a => a.category === 'import').map(action => (
            <button key={action.id} onClick={() => setSelectedAction(action.id)}
              className={`w-full flex items-start gap-3 px-2 py-1.5 rounded-sm transition-colors ${
                selectedAction === action.id ? 'bg-bg-tertiary text-accent' : 'hover:bg-bg-tertiary/50 text-text-primary'
              }`}>
              {action.icon}
              <span className="text-sm font-medium">{action.title}</span>
            </button>
          ))}
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
        {selectedAction === 'export-cas' && (
          <div className="max-w-2xl space-y-4">
            <h3 className="text-sm font-semibold text-text-primary">Export All Certificate Authorities</h3>
            <p className="text-sm text-text-secondary">Download all CAs including their hierarchy. Use the Export dropdown above to select format.</p>
          </div>
        )}
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
