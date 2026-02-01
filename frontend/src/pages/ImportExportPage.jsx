/**
 * Import/Export Page
 * Uses PageLayout for consistent UI structure
 * Uses DetailCard design system for content
 */
import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { 
  UploadSimple, Certificate, ShieldCheck, Flask, FloppyDisk, FileArrowUp, 
  DownloadSimple, Database, CloudArrowUp, ArrowsLeftRight, CheckCircle, File
} from '@phosphor-icons/react'
import {
  PageLayout, FocusItem, Button, ExportDropdown, Input, LoadingSpinner, 
  Select, Card, Badge, HelpCard, DetailHeader, DetailSection, DetailGrid, DetailField, DetailContent
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

  // Action definitions for focus panel
  const actions = [
    { id: 'import-cert', title: 'Import Certificate', subtitle: 'PEM, DER, PKCS#12', icon: Certificate, category: 'import' },
    { id: 'import-ca', title: 'Import CA', subtitle: 'Certificate Authority', icon: ShieldCheck, category: 'import' },
    { id: 'import-opnsense', title: 'Import from OpnSense', subtitle: 'API connection', icon: CloudArrowUp, category: 'import' },
    { id: 'export-certs', title: 'Export Certificates', subtitle: 'Bulk export', icon: DownloadSimple, category: 'export' },
    { id: 'export-cas', title: 'Export CAs', subtitle: 'With hierarchy', icon: DownloadSimple, category: 'export' },
  ]

  // Help content for modal
  const helpContent = (
    <div className="space-y-4">
      {/* Quick Stats */}
      <Card className="p-4 space-y-3 bg-gradient-to-br from-accent-primary/5 to-transparent">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Database size={16} className="text-accent-primary" />
          Quick Stats
        </h3>
        <div className="grid grid-cols-2 gap-3">
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-text-primary">{cas.length}</p>
            <p className="text-xs text-text-secondary">Available CAs</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-emerald-500">✓</p>
            <p className="text-xs text-text-secondary">Ready</p>
          </div>
        </div>
      </Card>

      {/* Supported Formats */}
      <Card className="p-4 space-y-3">
        <h3 className="text-sm font-semibold text-text-primary">Supported Formats</h3>
        <div className="flex flex-wrap gap-2">
          <Badge variant="blue" size="sm">PEM</Badge>
          <Badge variant="purple" size="sm">DER</Badge>
          <Badge variant="emerald" size="sm">PKCS#12</Badge>
          <Badge variant="orange" size="sm">CRT/CER</Badge>
        </div>
      </Card>

      {/* Help Cards */}
      <div className="space-y-3">
        <HelpCard variant="info" title="Import Certificates">
          Import certificates from files (.pem, .crt, .der, .p12) or paste PEM content directly.
          Certificates are automatically linked to their issuing CA when possible.
        </HelpCard>
        
        <HelpCard variant="tip" title="Import CAs">
          Import existing Certificate Authorities to manage certificates issued by external PKIs.
          The CA hierarchy is preserved during import.
        </HelpCard>

        <HelpCard variant="info" title="OpnSense Import">
          Connect to an OpnSense firewall to import all certificates and CAs. 
          Requires API credentials with appropriate permissions.
        </HelpCard>

        <HelpCard variant="warning" title="Export Security">
          Exported PKCS#12 files may contain private keys. Store them securely 
          and use strong passwords when exporting sensitive certificates.
        </HelpCard>
      </div>
    </div>
  )

  // Focus panel content (operation category list)
  const focusContent = (
    <div className="p-2 space-y-4">
      {/* Import Section */}
      <div className="space-y-1">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-text-secondary px-2 mb-2">
          Import
        </h3>
        {actions.filter(a => a.category === 'import').map(action => (
          <FocusItem
            key={action.id}
            icon={action.icon}
            title={action.title}
            subtitle={action.subtitle}
            selected={selectedAction === action.id}
            onClick={() => { 
              setSelectedAction(action.id)
              setSelectedFile(null)
              setImportName('')
              setImportPassword('')
              setPemContent('')
            }}
          />
        ))}
      </div>

      {/* Export Section */}
      <div className="space-y-1">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-text-secondary px-2 mb-2">
          Export
        </h3>
        {actions.filter(a => a.category === 'export').map(action => (
          <FocusItem
            key={action.id}
            icon={action.icon}
            title={action.title}
            subtitle={action.subtitle}
            selected={selectedAction === action.id}
            onClick={() => setSelectedAction(action.id)}
          />
        ))}
      </div>
    </div>
  )

  return (
    <PageLayout
      title="Import & Export"
      focusTitle="Operations"
      focusContent={focusContent}
      focusActions={null}
      focusFooter={null}
      helpContent={helpContent}
      
    >
      <DetailContent>
        {/* Import Certificate */}
        {selectedAction === 'import-cert' && (
          <div className="max-w-3xl space-y-0">
            <DetailHeader
              icon={Certificate}
              title="Import Certificate"
              subtitle="Import certificates from files or paste PEM content"
              badge={<Badge variant="blue">PEM / DER / PKCS#12</Badge>}
              stats={[
                { icon: File, label: 'Formats', value: '.pem, .crt, .der, .p12' },
                { icon: ShieldCheck, label: 'Available CAs', value: cas.length }
              ]}
              actions={[
                { 
                  label: 'Import', 
                  icon: FileArrowUp, 
                  onClick: handleImportCertificate, 
                  disabled: processing || (!selectedFile && !pemContent.trim())
                }
              ]}
            />
            
            <DetailSection title="Certificate File">
              <div className="space-y-4">
                <div>
                  <input
                    ref={certFileRef}
                    type="file"
                    accept=".pem,.crt,.cer,.der,.p12,.pfx"
                    onChange={(e) => { setSelectedFile(e.target.files[0]); setPemContent('') }}
                    className="w-full text-sm text-text-secondary file:mr-4 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-sm file:bg-accent-primary file:text-white hover:file:bg-accent-primary/80"
                  />
                  <p className="text-xs text-text-secondary mt-1">Accepted: .pem, .crt, .cer, .der, .p12, .pfx</p>
                </div>
                
                <div className="flex items-center gap-3">
                  <div className="flex-1 border-t border-border"></div>
                  <span className="text-xs text-text-secondary">OR paste PEM content</span>
                  <div className="flex-1 border-t border-border"></div>
                </div>
                
                <div>
                  <label className="block text-[10px] md:text-xs text-text-tertiary uppercase tracking-wide mb-1">Paste PEM Content</label>
                  <textarea
                    value={pemContent}
                    onChange={(e) => { setPemContent(e.target.value); setSelectedFile(null); if (certFileRef.current) certFileRef.current.value = '' }}
                    placeholder="-----BEGIN CERTIFICATE-----&#10;...&#10;-----END CERTIFICATE-----"
                    rows={5}
                    className="w-full px-2 py-1.5 bg-bg-secondary border border-border rounded-md text-sm text-text-primary font-mono placeholder-text-secondary focus:outline-none focus:ring-1 focus:ring-accent-primary resize-y"
                  />
                </div>
              </div>
            </DetailSection>
            
            <DetailSection title="Options">
              <DetailGrid>
                <div className="col-span-full md:col-span-1">
                  <Input 
                    label="Display Name (optional)" 
                    value={importName}
                    onChange={(e) => setImportName(e.target.value)}
                    placeholder="My Certificate"
                  />
                </div>
                <div className="col-span-full md:col-span-1">
                  <Input 
                    label="Password (for PKCS#12)" 
                    type="password"
                    value={importPassword}
                    onChange={(e) => setImportPassword(e.target.value)}
                    placeholder="Enter password if needed"
                  />
                </div>
                <div className="col-span-full">
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
              </DetailGrid>
            </DetailSection>
            
            {/* Primary action button at bottom */}
            <div className="pt-4 border-t border-border/50">
              <Button
                onClick={handleImportCertificate}
                disabled={processing || (!selectedFile && !pemContent.trim())}
                className="w-full md:w-auto"
              >
                <FileArrowUp size={18} />
                {processing ? 'Importing...' : 'Import Certificate'}
              </Button>
            </div>
          </div>
        )}

        {/* Import CA */}
        {selectedAction === 'import-ca' && (
          <div className="max-w-3xl space-y-0">
            <DetailHeader
              icon={ShieldCheck}
              title="Import Certificate Authority"
              subtitle="Import a CA certificate from a file or paste PEM content"
              badge={<Badge variant="emerald">CA Import</Badge>}
              stats={[
                { icon: File, label: 'Formats', value: 'PEM, DER, PKCS#12' }
              ]}
              actions={[
                { 
                  label: 'Import CA', 
                  icon: FileArrowUp, 
                  onClick: handleImportCA, 
                  disabled: processing || (!selectedFile && !pemContent.trim())
                }
              ]}
            />
            
            <DetailSection title="CA Certificate File">
              <div className="space-y-4">
                <div>
                  <input
                    ref={caFileRef}
                    type="file"
                    accept=".pem,.crt,.cer,.der,.p12,.pfx"
                    onChange={(e) => { setSelectedFile(e.target.files[0]); setPemContent('') }}
                    className="w-full text-sm text-text-secondary file:mr-4 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-sm file:bg-accent-primary file:text-white hover:file:bg-accent-primary/80"
                  />
                  <p className="text-xs text-text-secondary mt-1">Accepted: .pem, .crt, .cer, .der, .p12, .pfx</p>
                </div>
                
                <div className="flex items-center gap-3">
                  <div className="flex-1 border-t border-border"></div>
                  <span className="text-xs text-text-secondary">OR paste PEM content</span>
                  <div className="flex-1 border-t border-border"></div>
                </div>
                
                <div>
                  <label className="block text-[10px] md:text-xs text-text-tertiary uppercase tracking-wide mb-1">Paste PEM Content</label>
                  <textarea
                    value={pemContent}
                    onChange={(e) => { setPemContent(e.target.value); setSelectedFile(null); if (caFileRef.current) caFileRef.current.value = '' }}
                    placeholder="-----BEGIN CERTIFICATE-----&#10;...&#10;-----END CERTIFICATE-----"
                    rows={5}
                    className="w-full px-2 py-1.5 bg-bg-secondary border border-border rounded-md text-sm text-text-primary font-mono placeholder-text-secondary focus:outline-none focus:ring-1 focus:ring-accent-primary resize-y"
                  />
                </div>
              </div>
            </DetailSection>
            
            <DetailSection title="Options">
              <DetailGrid>
                <div className="col-span-full md:col-span-1">
                  <Input 
                    label="Display Name (optional)" 
                    value={importName}
                    onChange={(e) => setImportName(e.target.value)}
                    placeholder="My Root CA"
                  />
                </div>
                <div className="col-span-full md:col-span-1">
                  <Input 
                    label="Password (for PKCS#12)" 
                    type="password"
                    value={importPassword}
                    onChange={(e) => setImportPassword(e.target.value)}
                    placeholder="Enter password if needed"
                  />
                </div>
              </DetailGrid>
            </DetailSection>
            
            {/* Primary action button at bottom */}
            <div className="pt-4 border-t border-border/50">
              <Button
                onClick={handleImportCA}
                disabled={processing || (!selectedCAFile && !caPemContent.trim())}
                className="w-full md:w-auto"
              >
                <FileArrowUp size={18} />
                {processing ? 'Importing...' : 'Import CA'}
              </Button>
            </div>
          </div>
        )}

        {/* Export Certificates */}
        {selectedAction === 'export-certs' && (
          <div className="max-w-3xl space-y-0">
            <DetailHeader
              icon={DownloadSimple}
              title="Export All Certificates"
              subtitle="Download all certificates in a single archive"
              badge={<Badge variant="purple">Bulk Export</Badge>}
            />
            
            <DetailSection title="Available Formats">
              <DetailGrid>
                <DetailField label="PEM" value="Base64 encoded, widely compatible" />
                <DetailField label="DER" value="Binary format, compact" />
                <DetailField label="PKCS#12" value="Includes private keys (password protected)" />
              </DetailGrid>
            </DetailSection>
            
            <DetailSection title="Export" noBorder>
              <ExportDropdown onExport={handleExportAllCerts} formats={['pem', 'der', 'pkcs12']} />
            </DetailSection>
          </div>
        )}

        {/* Export CAs */}
        {selectedAction === 'export-cas' && (
          <div className="max-w-3xl space-y-0">
            <DetailHeader
              icon={DownloadSimple}
              title="Export All Certificate Authorities"
              subtitle="Download all CAs including their hierarchy"
              badge={<Badge variant="emerald">CA Export</Badge>}
              stats={[
                { icon: ShieldCheck, label: 'Total CAs', value: cas.length }
              ]}
            />
            
            <DetailSection title="Available Formats">
              <DetailGrid>
                <DetailField label="PEM" value="Base64 encoded, widely compatible" />
                <DetailField label="DER" value="Binary format, compact" />
              </DetailGrid>
            </DetailSection>
            
            <DetailSection title="Export" noBorder>
              <ExportDropdown onExport={handleExportAllCAs} formats={['pem', 'der']} />
            </DetailSection>
          </div>
        )}

        {/* Import from OpnSense */}
        {selectedAction === 'import-opnsense' && (
          <div className="max-w-3xl space-y-0">
            <DetailHeader
              icon={CloudArrowUp}
              title="Import from OpnSense"
              subtitle="Connect to OpnSense API to import certificates and CAs"
              badge={testResult ? <Badge variant="emerald">Connected</Badge> : <Badge variant="secondary">Not Connected</Badge>}
              stats={testResult ? [
                { icon: ShieldCheck, label: 'CAs Found', value: testResult.cas },
                { icon: Certificate, label: 'Certificates', value: testResult.certificates }
              ] : undefined}
              actions={[
                { label: 'Save Config', icon: FloppyDisk, onClick: handleSaveConfig, variant: 'secondary', disabled: processing },
                { label: 'Test', icon: Flask, onClick: handleTestConf, variant: 'secondary', disabled: processing },
                { label: 'Import', icon: UploadSimple, onClick: handleImport, disabled: processing || !testResult }
              ]}
            />
            
            <DetailSection title="Connection Settings">
              <DetailGrid>
                <div className="col-span-full md:col-span-1">
                  <Input label="OpnSense Host" value={opnsenseHost} 
                    onChange={(e) => setOpnsenseHost(e.target.value)} 
                    placeholder="192.168.1.1" />
                </div>
                <div className="col-span-full md:col-span-1">
                  <Input label="Port" value={opnsensePort} 
                    onChange={(e) => setOpnsensePort(e.target.value)} 
                    placeholder="443" />
                </div>
              </DetailGrid>
            </DetailSection>
            
            <DetailSection title="API Credentials">
              <DetailGrid>
                <div className="col-span-full md:col-span-1">
                  <Input label="API Key" value={opnsenseApiKey} 
                    onChange={(e) => setOpnsenseApiKey(e.target.value)} 
                    placeholder="Enter API Key" />
                </div>
                <div className="col-span-full md:col-span-1">
                  <Input label="API Secret" type="password" value={opnsenseApiSecret} 
                    onChange={(e) => setOpnsenseApiSecret(e.target.value)} 
                    placeholder="Enter API Secret" />
                </div>
              </DetailGrid>
            </DetailSection>

            {testResult && (
              <DetailSection title="Connection Status">
                <div className="flex items-center gap-3 p-3 bg-green-500/10 border border-green-500/30 rounded-lg">
                  <CheckCircle size={24} className="text-green-500" weight="fill" />
                  <div>
                    <h4 className="text-sm font-semibold text-green-400">Connection Successful</h4>
                    <p className="text-xs text-text-secondary">Found {testResult.cas} CAs and {testResult.certificates} certificates ready to import</p>
                  </div>
                </div>
              </DetailSection>
            )}
          </div>
        )}
      </DetailContent>
    </PageLayout>
  )
}
