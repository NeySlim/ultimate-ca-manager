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
    { id: 'import', label: t('importExport.tabs.import'), icon: UploadSimple },
    { id: 'opnsense', label: t('importExport.tabs.opnsense'), icon: CloudArrowUp },
    { id: 'export-certs', label: t('importExport.tabs.exportCerts'), icon: DownloadSimple },
    { id: 'export-cas', label: t('importExport.tabs.exportCAs'), icon: DownloadSimple },
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
      showError(error.message || t('importExport.opnsense.connectionFailed'))
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
      showError(error.message || t('importExport.importFailed'))
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
                  placeholder="192.168.1.1"
                />
                <Input 
                  label={t('importExport.opnsense.portLabel')}
                  value={opnsensePort}
                  onChange={(e) => setOpnsensePort(e.target.value)}
                  placeholder="443"
                />
                <Input 
                  label={t('importExport.opnsense.apiKeyLabel')}
                  value={opnsenseApiKey}
                  onChange={(e) => setOpnsenseApiKey(e.target.value)}
                  placeholder="API Key"
                />
                <Input 
                  label={t('importExport.opnsense.apiSecretLabel')}
                  type="password"
                  value={opnsenseApiSecret}
                  onChange={(e) => setOpnsenseApiSecret(e.target.value)}
                  placeholder="API Secret"
                />
              </div>
            </DetailSection>
            
            {testResult && (
              <DetailSection title={t('importExport.opnsense.connectionResult')} icon={testResult === 'success' ? CheckCircle : Key} iconClass={testResult === 'success' ? 'icon-bg-emerald' : 'icon-bg-orange'}>
                {testResult === 'success' ? (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2 text-status-success">
                      <CheckCircle size={18} weight="fill" />
                      <span className="text-sm font-medium">{t('importExport.opnsense.connectedSuccessfully')}</span>
                    </div>
                    {testItems.length > 0 && (
                      <div className="text-sm text-text-secondary">
                        {t('importExport.opnsense.foundCertificates', { count: testItems.length })}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-sm text-status-danger">{t('importExport.opnsense.connectionFailed')}</div>
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
                {processing ? t('importExport.opnsense.testing') : t('importExport.opnsense.testConnection')}
              </Button>
              {testResult === 'success' && testItems.length > 0 && (
                <Button onClick={handleImportFromOpnsense} disabled={processing} size="lg">
                  <UploadSimple size={18} />
                  {t('importExport.opnsense.importCertificates', { count: testItems.length })}
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
      title={t('importExport.title')}
      subtitle={t('importExport.subtitle')}
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
