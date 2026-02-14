/**
 * Import / Export Page - Unified with Smart Import
 */
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
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

export default function ImportExportPage() {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const navigate = useNavigate()
  
  // Tabs with translations
  const TABS = [
    { id: 'import', label: t('common.import'), icon: UploadSimple },
    { id: 'opnsense', label: t('importExport.tabs.opnsense'), icon: CloudArrowUp },
    { id: 'export-certs', label: t('importExport.tabs.exportCerts'), icon: DownloadSimple },
    { id: 'export-cas', label: t('importExport.exportCAs'), icon: DownloadSimple },
  ]
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
      showSuccess(t('importExport.opnsense.configSaved'))
    } catch (e) {}
  }

  const handleTestConf = async () => {
    setProcessing(true)
    setTestResult(null)
    setTestItems([])
    try {
      const result = await opnsenseService.test({
        host: opnsenseHost,
        port: opnsensePort,
        api_key: opnsenseApiKey,
        api_secret: opnsenseApiSecret
      })
      setTestResult({ success: true, stats: result.stats })
      setTestItems((result.items || []).map(item => ({ ...item, selected: true })))
      saveOpnsenseConfig()
    } catch (error) {
      setTestResult({ success: false, error: error.message })
      showError(error.message || t('importExport.opnsense.connectionFailed'))
    } finally {
      setProcessing(false)
    }
  }

  const toggleItemSelection = (id) => {
    setTestItems(prev => prev.map(item => 
      item.id === id ? { ...item, selected: !item.selected } : item
    ))
  }

  const toggleAllItems = (selected) => {
    setTestItems(prev => prev.map(item => ({ ...item, selected })))
  }

  const handleImportFromOpnsense = async () => {
    const selectedItems = testItems.filter(i => i.selected).map(i => i.id)
    if (selectedItems.length === 0) {
      showError(t('importExport.opnsense.noItemsSelected'))
      return
    }
    setProcessing(true)
    try {
      const result = await opnsenseService.import({
        host: opnsenseHost,
        port: opnsensePort,
        api_key: opnsenseApiKey,
        api_secret: opnsenseApiSecret,
        items: selectedItems
      })
      const imported = (result.imported?.cas || 0) + (result.imported?.certificates || 0)
      showSuccess(t('importExport.opnsense.importSuccess', { count: imported, skipped: result.skipped || 0 }))
      setTestResult(null)
      setTestItems([])
      loadCAs()
    } catch (error) {
      showError(error.message || t('common.importFailed'))
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
      showSuccess(t('importExport.export.certificatesExported'))
    } catch (error) {
      showError(error.message || t('importExport.export.exportFailed'))
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
      showSuccess(t('importExport.export.caExported'))
    } catch (error) {
      showError(error.message || t('importExport.export.exportFailed'))
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
            title={t('importExport.smartImport.title')}
            icon={UploadSimple} 
            iconClass="icon-bg-violet" 
            description={t('importExport.smartImport.description')}
          >
            <SmartImportWidget onImportComplete={handleImportComplete} />
          </DetailSection>
        )
      
      case 'opnsense':
        return (
          <div className="space-y-4">
            <DetailSection title={t('importExport.opnsense.title')} icon={CloudArrowUp} iconClass="icon-bg-orange" description={t('importExport.opnsense.description')}>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Input 
                  label={t('importExport.opnsense.hostLabel')}
                  value={opnsenseHost}
                  onChange={(e) => setOpnsenseHost(e.target.value)}
                  placeholder={t('importExport.opnsense.hostPlaceholder')}
                />
                <Input 
                  label={t('common.portLabel')}
                  value={opnsensePort}
                  onChange={(e) => setOpnsensePort(e.target.value)}
                  placeholder={t('common.portPlaceholder')}
                />
                <Input 
                  label={t('importExport.opnsense.apiKeyLabel')}
                  value={opnsenseApiKey}
                  onChange={(e) => setOpnsenseApiKey(e.target.value)}
                  placeholder={t('importExport.opnsense.apiKeyLabel')}
                />
                <Input 
                  label={t('importExport.opnsense.apiSecretLabel')}
                  type="password"
                  value={opnsenseApiSecret}
                  onChange={(e) => setOpnsenseApiSecret(e.target.value)}
                  placeholder={t('importExport.opnsense.apiSecretLabel')}
                />
              </div>
            </DetailSection>
            
            {testResult && (
              <DetailSection 
                title={t('importExport.opnsense.connectionResult')} 
                icon={testResult.success ? CheckCircle : Key} 
                iconClass={testResult.success ? 'icon-bg-emerald' : 'icon-bg-orange'}
              >
                {testResult.success ? (
                  <div className="space-y-4">
                    <div className="flex items-center gap-2 text-status-success">
                      <CheckCircle size={18} weight="fill" />
                      <span className="text-sm font-medium">{t('importExport.opnsense.connectedSuccessfully')}</span>
                    </div>
                    
                    {/* Stats summary */}
                    {testResult.stats && (
                      <div className="flex gap-4">
                        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-bg-secondary">
                          <ShieldCheck size={16} className="text-accent-primary" />
                          <span className="text-sm font-medium">{testResult.stats.cas} CA{testResult.stats.cas > 1 ? 's' : ''}</span>
                        </div>
                        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-bg-secondary">
                          <Certificate size={16} className="text-accent-primary" />
                          <span className="text-sm font-medium">{testResult.stats.certificates} {t('common.certificates')}</span>
                        </div>
                      </div>
                    )}
                    
                    {/* Items list with checkboxes */}
                    {testItems.length > 0 && (
                      <div className="border border-border rounded-lg overflow-hidden">
                        <div className="flex items-center justify-between px-3 py-2 bg-bg-secondary border-b border-border">
                          <label className="flex items-center gap-2 text-sm font-medium cursor-pointer">
                            <input
                              type="checkbox"
                              checked={testItems.every(i => i.selected)}
                              onChange={(e) => toggleAllItems(e.target.checked)}
                              className="w-4 h-4 rounded border-border text-accent-primary"
                            />
                            {t('importExport.opnsense.selectAll')} ({testItems.filter(i => i.selected).length}/{testItems.length})
                          </label>
                        </div>
                        <div className="max-h-64 overflow-y-auto divide-y divide-border">
                          {testItems.map(item => (
                            <label key={item.id} className="flex items-center gap-3 px-3 py-2 hover:bg-bg-secondary cursor-pointer transition-colors">
                              <input
                                type="checkbox"
                                checked={item.selected}
                                onChange={() => toggleItemSelection(item.id)}
                                className="w-4 h-4 rounded border-border text-accent-primary shrink-0"
                              />
                              <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase shrink-0 ${
                                item.type === 'CA' 
                                  ? 'bg-accent-primary/15 text-accent-primary' 
                                  : 'bg-status-info/15 text-status-info'
                              }`}>
                                {item.type}
                              </span>
                              <span className="text-sm truncate">{item.name || t('common.unnamed')}</span>
                            </label>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-sm text-status-danger">{testResult.error || t('importExport.opnsense.connectionFailed')}</div>
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
                {processing ? t('common.testing') : t('common.testConnection')}
              </Button>
              {testResult?.success && testItems.some(i => i.selected) && (
                <Button onClick={handleImportFromOpnsense} disabled={processing} size="lg">
                  <UploadSimple size={18} />
                  {t('importExport.opnsense.importSelected', { count: testItems.filter(i => i.selected).length })}
                </Button>
              )}
            </div>
          </div>
        )
      
      case 'export-certs':
        return (
          <DetailSection title={t('importExport.export.allCertsTitle')} icon={Certificate} iconClass="icon-bg-blue" description={t('importExport.export.allCertsDesc')}>
            <div className="grid grid-cols-2 gap-3">
              <Button variant="secondary" onClick={() => handleExportAllCerts('pem')} className="justify-center">
                <DownloadSimple size={16} /> {t('importExport.export.pemBundle')}
              </Button>
              <Button onClick={() => handleExportAllCerts('pkcs7')} className="justify-center">
                <DownloadSimple size={16} /> {t('importExport.export.p7bBundle')}
              </Button>
            </div>
            <p className="text-xs text-text-tertiary mt-2">{t('importExport.export.individualExportHint')}</p>
          </DetailSection>
        )
      
      case 'export-cas':
        return (
          <DetailSection title={t('importExport.export.allCAsTitle')} icon={ShieldCheck} iconClass="icon-bg-green" description={t('importExport.export.allCAsDesc', { count: cas.length })}>
            <div className="grid grid-cols-2 gap-3">
              <Button variant="secondary" onClick={() => handleExportAllCAs('pem')} className="justify-center">
                <DownloadSimple size={16} /> {t('importExport.export.pemBundle')}
              </Button>
              <Button onClick={() => handleExportAllCAs('pkcs7')} className="justify-center">
                <DownloadSimple size={16} /> {t('importExport.export.p7bBundle')}
              </Button>
            </div>
            <p className="text-xs text-text-tertiary mt-2">{t('importExport.export.individualCAExportHint')}</p>
          </DetailSection>
        )
      
      default:
        return null
    }
  }

  return (
    <ResponsiveLayout
      title={t('common.importExport')}
      subtitle={t('importExport.subtitle')}
      icon={ArrowsLeftRight}
      tabs={TABS}
      activeTab={activeTab}
      onTabChange={handleTabChange}
      tabLayout="sidebar"
      sidebarContentClass=""
      tabGroups={[
        { labelKey: 'importExport.groups.import', tabs: ['import', 'opnsense'], color: 'icon-bg-blue' },
        { labelKey: 'importExport.groups.export', tabs: ['export-certs', 'export-cas'], color: 'icon-bg-emerald' },
      ]}
      helpPageKey="importExport"
    >
      <div className="max-w-3xl mx-auto p-4 md:p-6">
        {renderContent()}
      </div>
    </ResponsiveLayout>
  )
}
