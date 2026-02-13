/**
 * Certificate Tools Page
 * SSL checker, decoders, converters - like SSLShopper tools
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Wrench, Globe, FileMagnifyingGlass, Key, ArrowsLeftRight,
  CheckCircle, XCircle, Warning, Certificate,
  Copy, Download, ArrowRight, Spinner, UploadSimple
} from '@phosphor-icons/react'
import {
  Button, Badge, Textarea, Input,
  CompactSection, CompactGrid, CompactField
} from '../components'
import { ResponsiveLayout } from '../components/ui/responsive'
import { apiClient } from '../services'
import { useNotification } from '../contexts'
import { cn } from '../lib/utils'

// Tool definitions - only static data, names/descriptions are translated in component
const TOOLS = [
  {
    id: 'ssl-checker',
    nameKey: 'tools.sslChecker',
    descKey: 'tools.sslCheckerDesc',
    icon: Globe,
    color: 'green'
  },
  {
    id: 'csr-decoder',
    nameKey: 'tools.csrDecoder',
    descKey: 'tools.csrDecoderDesc',
    icon: FileMagnifyingGlass,
    color: 'blue'
  },
  {
    id: 'cert-decoder',
    nameKey: 'tools.decoder',
    descKey: 'tools.certDecoderDesc',
    icon: Certificate,
    color: 'purple'
  },
  {
    id: 'key-matcher',
    nameKey: 'tools.keyMatcher',
    descKey: 'tools.keyMatcherDesc',
    icon: Key,
    color: 'orange'
  },
  {
    id: 'converter',
    nameKey: 'tools.converter',
    descKey: 'tools.converterDesc',
    icon: ArrowsLeftRight,
    color: 'teal'
  }
]

const iconColors = {
  green: 'icon-bg-emerald',
  blue: 'icon-bg-blue',
  purple: 'icon-bg-violet',
  orange: 'icon-bg-orange',
  teal: 'icon-bg-teal'
}

export default function CertificateToolsPage() {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const [activeTool, setActiveTool] = useState('ssl-checker')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)

  // Help content with translations
  const helpContent = {
    title: t('common.tools'),
    description: t('tools.helpDescription'),
    sections: [
      {
        title: t('tools.sslChecker'),
        content: t('tools.helpSslChecker')
      },
      {
        title: t('tools.csrDecoder'),
        content: t('tools.helpCsrDecoder')
      },
      {
        title: t('tools.decoder'),
        content: t('tools.helpCertDecoder')
      },
      {
        title: t('tools.keyMatcher'),
        content: t('tools.helpKeyMatcher')
      },
      {
        title: t('tools.converter'),
        content: t('tools.helpConverter')
      }
    ]
  }

  // SSL Checker state
  const [sslHostname, setSslHostname] = useState('')
  const [sslPort, setSslPort] = useState('443')

  // CSR Decoder state
  const [csrPem, setCsrPem] = useState('')

  // Certificate Decoder state
  const [certPem, setCertPem] = useState('')

  // Key Matcher state
  const [matchCert, setMatchCert] = useState('')
  const [matchKey, setMatchKey] = useState('')
  const [matchCsr, setMatchCsr] = useState('')
  const [matchPassword, setMatchPassword] = useState('')

  // Converter state
  const [convertPem, setConvertPem] = useState('')
  const [convertFile, setConvertFile] = useState(null)
  const [convertFileData, setConvertFileData] = useState(null)
  const [convertType, setConvertType] = useState('certificate')
  const [convertFormat, setConvertFormat] = useState('der')
  const [convertKey, setConvertKey] = useState('')
  const [convertKeyFile, setConvertKeyFile] = useState(null)
  const [convertChain, setConvertChain] = useState('')
  const [convertPassword, setConvertPassword] = useState('')
  const [pkcs12Password, setPkcs12Password] = useState('')

  // Handle file upload for converter
  const handleConvertFileChange = async (e, setter, dataSetter) => {
    const file = e.target.files?.[0]
    if (!file) return
    setter(file)
    
    // Read file content
    const reader = new FileReader()
    reader.onload = (event) => {
      const content = event.target.result
      // Check if it's text (PEM) or binary
      if (typeof content === 'string') {
        dataSetter(content)
      } else {
        // Binary - convert to base64
        const bytes = new Uint8Array(content)
        let binary = ''
        for (let i = 0; i < bytes.length; i++) {
          binary += String.fromCharCode(bytes[i])
        }
        dataSetter('BASE64:' + btoa(binary))
      }
    }
    
    // Try reading as text first for PEM files
    if (file.name.match(/\.(pem|crt|cer|key|csr)$/i)) {
      reader.readAsText(file)
    } else {
      reader.readAsArrayBuffer(file)
    }
  }

  const resetResult = () => setResult(null)

  const handleCheckSSL = async () => {
    if (!sslHostname.trim()) {
      showError(t('tools.pleaseEnterHostname'))
      return
    }
    setLoading(true)
    resetResult()
    try {
      const response = await apiClient.post('/tools/check-ssl', {
        hostname: sslHostname.trim(),
        port: parseInt(sslPort) || 443
      })
      setResult({ type: 'ssl', data: response.data })
    } catch (error) {
      showError(error.message || t('tools.failedToCheckSsl'))
      setResult({ type: 'error', message: error.message })
    } finally {
      setLoading(false)
    }
  }

  const handleDecodeCSR = async () => {
    if (!csrPem.trim()) {
      showError(t('tools.pleasePasteCsr'))
      return
    }
    setLoading(true)
    resetResult()
    try {
      const response = await apiClient.post('/tools/decode-csr', {
        pem: csrPem.trim()
      })
      setResult({ type: 'csr', data: response.data })
    } catch (error) {
      showError(error.message || t('tools.failedToDecodeCsr'))
      setResult({ type: 'error', message: error.message })
    } finally {
      setLoading(false)
    }
  }

  const handleDecodeCert = async () => {
    if (!certPem.trim()) {
      showError(t('tools.pleasePasteCert'))
      return
    }
    setLoading(true)
    resetResult()
    try {
      const response = await apiClient.post('/tools/decode-cert', {
        pem: certPem.trim()
      })
      setResult({ type: 'cert', data: response.data })
    } catch (error) {
      showError(error.message || t('tools.failedToDecodeCert'))
      setResult({ type: 'error', message: error.message })
    } finally {
      setLoading(false)
    }
  }

  const handleMatchKeys = async () => {
    if (!matchCert.trim() && !matchKey.trim() && !matchCsr.trim()) {
      showError(t('tools.pleaseProvideItem'))
      return
    }
    setLoading(true)
    resetResult()
    try {
      const response = await apiClient.post('/tools/match-keys', {
        certificate: matchCert.trim(),
        private_key: matchKey.trim(),
        csr: matchCsr.trim(),
        password: matchPassword
      })
      setResult({ type: 'match', data: response.data })
    } catch (error) {
      showError(error.message || t('tools.failedToMatchKeys'))
      setResult({ type: 'error', message: error.message })
    } finally {
      setLoading(false)
    }
  }

  const handleConvert = async () => {
    // Get content from file or textarea
    const content = convertFileData || convertPem.trim()
    const keyContent = convertKeyFile ? await readFileAsText(convertKeyFile) : convertKey.trim()
    
    if (!content) {
      showError(t('tools.pleaseUploadOrPaste'))
      return
    }
    if (convertFormat === 'pkcs12' && !keyContent) {
      showError(t('tools.privateKeyRequired'))
      return
    }
    setLoading(true)
    resetResult()
    try {
      const response = await apiClient.post('/tools/convert', {
        pem: content,
        input_type: convertType,
        output_format: convertFormat,
        private_key: keyContent,
        chain: convertChain.trim(),
        password: convertPassword,
        pkcs12_password: pkcs12Password
      })
      setResult({ type: 'convert', data: response.data })
    } catch (error) {
      showError(error.message || t('tools.conversionFailed'))
      setResult({ type: 'error', message: error.message })
    } finally {
      setLoading(false)
    }
  }

  // Helper to read file as text
  const readFileAsText = (file) => {
    return new Promise((resolve) => {
      const reader = new FileReader()
      reader.onload = (e) => resolve(e.target.result)
      reader.readAsText(file)
    })
  }

  const downloadConverted = () => {
    if (!result?.data?.data) return
    const { data, filename, format } = result.data
    
    let blob
    if (format === 'der' || format === 'pkcs12') {
      // Binary format - decode base64
      const binary = atob(data)
      const bytes = new Uint8Array(binary.length)
      for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i)
      }
      blob = new Blob([bytes], { type: 'application/octet-stream' })
    } else {
      // Text format
      blob = new Blob([data], { type: 'text/plain' })
    }
    
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
    showSuccess(t('tools.downloaded', { filename }))
  }

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text)
    showSuccess(t('common.copiedToClipboard'))
  }

  // Reusable Textarea with file upload
  const TextareaWithUpload = ({ label, placeholder, value, onChange, rows = 6, accept = '.pem,.crt,.cer,.der,.p12,.pfx,.p7b,.key,.csr' }) => {
    const fileInputId = `file-${label.replace(/\s/g, '-').toLowerCase()}`
    
    const handleFile = async (e) => {
      const file = e.target.files?.[0]
      if (!file) return
      
      const reader = new FileReader()
      reader.onload = (event) => {
        const content = event.target.result
        if (typeof content === 'string') {
          onChange({ target: { value: content } })
        } else {
          // Binary - convert to base64 with prefix
          const bytes = new Uint8Array(content)
          let binary = ''
          for (let i = 0; i < bytes.length; i++) {
            binary += String.fromCharCode(bytes[i])
          }
          onChange({ target: { value: 'BASE64:' + btoa(binary) } })
        }
      }
      
      // PEM files as text, others as binary
      if (file.name.match(/\.(pem|crt|cer|key|csr)$/i)) {
        reader.readAsText(file)
      } else {
        reader.readAsArrayBuffer(file)
      }
    }
    
    return (
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-text-primary">{label}</label>
          <label htmlFor={fileInputId} className="flex items-center gap-1 text-xs text-accent-primary hover:underline cursor-pointer">
            <UploadSimple size={12} />
            {t('tools.uploadFile')}
          </label>
          <input
            id={fileInputId}
            type="file"
            accept={accept}
            onChange={handleFile}
            className="hidden"
          />
        </div>
        <textarea
          placeholder={placeholder}
          value={value?.startsWith('BASE64:') ? `[Binary file loaded - ${Math.round(value.length / 1.37)} bytes]` : value}
          onChange={onChange}
          rows={rows}
          className="w-full px-3 py-2 rounded-md border border-border bg-bg-secondary text-text-primary placeholder:text-text-tertiary focus:outline-none focus:ring-2 focus:ring-accent-primary/30 font-mono text-xs resize-none"
          readOnly={value?.startsWith('BASE64:')}
        />
      </div>
    )
  }

  // Render tool selector
  const renderToolSelector = () => (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-6">
      {TOOLS.map(tool => {
        const Icon = tool.icon
        const isActive = activeTool === tool.id
        return (
          <button
            key={tool.id}
            onClick={() => { setActiveTool(tool.id); resetResult() }}
            className={cn(
              'p-3 rounded-lg border text-left transition-all',
              isActive
                ? 'border-accent-primary bg-accent-primary/10'
                : 'border-border bg-bg-secondary hover:border-accent-primary/50'
            )}
          >
            <div className={cn('w-8 h-8 rounded-lg flex items-center justify-center mb-2', iconColors[tool.color])}>
              <Icon size={18} weight="duotone" className="text-text-primary" />
            </div>
            <div className="text-sm font-medium text-text-primary">{t(tool.nameKey)}</div>
            <div className="text-xs text-text-secondary mt-0.5 line-clamp-2">{t(tool.descKey)}</div>
          </button>
        )
      })}
    </div>
  )

  // Render SSL Checker
  const renderSSLChecker = () => (
    <div className="space-y-4">
      <div className="flex gap-3">
        <div className="flex-1">
          <Input
            label={t('tools.hostname')}
            placeholder={t('common.commonNamePlaceholder')}
            value={sslHostname}
            onChange={(e) => setSslHostname(e.target.value)}
          />
        </div>
        <div className="w-24">
          <Input
            label={t('common.portLabel')}
            placeholder={t('common.portPlaceholder')}
            value={sslPort}
            onChange={(e) => setSslPort(e.target.value)}
          />
        </div>
      </div>
      <Button onClick={handleCheckSSL} disabled={loading}>
        {loading ? <Spinner size={16} className="animate-spin" /> : <Globe size={16} />}
        {t('tools.checkSSL')}
      </Button>
    </div>
  )

  // Render CSR Decoder
  const renderCSRDecoder = () => (
    <div className="space-y-4">
      <TextareaWithUpload
        label={t('tools.csrPemLabel')}
        placeholder="-----BEGIN CERTIFICATE REQUEST-----&#10;...&#10;-----END CERTIFICATE REQUEST-----"
        value={csrPem}
        onChange={(e) => setCsrPem(e.target.value)}
        rows={8}
        accept=".pem,.csr,.der"
      />
      <Button onClick={handleDecodeCSR} disabled={loading}>
        {loading ? <Spinner size={16} className="animate-spin" /> : <FileMagnifyingGlass size={16} />}
        {t('tools.decodeCsr')}
      </Button>
    </div>
  )

  // Render Certificate Decoder
  const renderCertDecoder = () => (
    <div className="space-y-4">
      <TextareaWithUpload
        label={t('tools.certPemLabel')}
        placeholder="-----BEGIN CERTIFICATE-----&#10;...&#10;-----END CERTIFICATE-----"
        value={certPem}
        onChange={(e) => setCertPem(e.target.value)}
        rows={8}
        accept=".pem,.crt,.cer,.der"
      />
      <Button onClick={handleDecodeCert} disabled={loading}>
        {loading ? <Spinner size={16} className="animate-spin" /> : <Certificate size={16} />}
        {t('tools.decodeCert')}
      </Button>
    </div>
  )

  // Render Key Matcher
  const renderKeyMatcher = () => (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <TextareaWithUpload
          label={t('tools.certificateOptional')}
          placeholder="-----BEGIN CERTIFICATE-----"
          value={matchCert}
          onChange={(e) => setMatchCert(e.target.value)}
          rows={6}
          accept=".pem,.crt,.cer,.der"
        />
        <TextareaWithUpload
          label={t('tools.privateKeyOptional')}
          placeholder="-----BEGIN PRIVATE KEY-----"
          value={matchKey}
          onChange={(e) => setMatchKey(e.target.value)}
          rows={6}
          accept=".pem,.key,.der"
        />
        <TextareaWithUpload
          label={t('tools.csrOptional')}
          placeholder="-----BEGIN CERTIFICATE REQUEST-----"
          value={matchCsr}
          onChange={(e) => setMatchCsr(e.target.value)}
          rows={6}
          accept=".pem,.csr,.der"
        />
      </div>
      <Input
        label={t('tools.keyPassword')}
        type="password"
        placeholder={t('tools.keyPasswordPlaceholder')}
        value={matchPassword}
        onChange={(e) => setMatchPassword(e.target.value)}
        className="max-w-xs"
      />
      <Button onClick={handleMatchKeys} disabled={loading}>
        {loading ? <Spinner size={16} className="animate-spin" /> : <Key size={16} />}
        {t('tools.matchKeys')}
      </Button>
    </div>
  )

  // Render Converter
  const renderConverter = () => (
    <div className="space-y-4">
      {/* Input section */}
      <div className="p-4 border border-border rounded-lg bg-bg-secondary/50 space-y-4">
        <div className="text-sm font-medium text-text-primary">{t('tools.inputAnyFormat')}</div>
        
        {/* File upload */}
        <div>
          <label className="block text-xs font-medium text-text-secondary mb-1">{t('common.uploadFile')}</label>
          <input
            type="file"
            accept=".pem,.crt,.cer,.der,.p12,.pfx,.p7b,.p7c,.key,.csr"
            onChange={(e) => handleConvertFileChange(e, setConvertFile, setConvertFileData)}
            className="w-full text-sm text-text-secondary file:mr-3 file:py-1.5 file:px-3 file:border-0 file:rounded file:bg-accent-primary file:text-white file:cursor-pointer hover:file:bg-accent-primary/90"
          />
          <p className="text-xs text-text-secondary mt-1">
            {t('tools.supportsFormats')}
          </p>
        </div>
        
        {convertFile && (
          <div className="flex items-center gap-2 text-sm">
            <CheckCircle size={16} className="text-status-success" />
            <span className="text-text-primary">{convertFile.name}</span>
            <button 
              onClick={() => { setConvertFile(null); setConvertFileData(null) }}
              className="text-text-secondary hover:text-status-danger"
            >
              <XCircle size={16} />
            </button>
          </div>
        )}
        
        {/* Or paste */}
        <div className="flex items-center gap-2">
          <div className="flex-1 h-px bg-border" />
          <span className="text-xs text-text-secondary">{t('common.orPastePem')}</span>
          <div className="flex-1 h-px bg-border" />
        </div>
        
        <Textarea
          placeholder="-----BEGIN CERTIFICATE-----&#10;...&#10;-----END CERTIFICATE-----"
          value={convertPem}
          onChange={(e) => setConvertPem(e.target.value)}
          rows={4}
          className="font-mono text-xs"
          disabled={!!convertFileData}
        />
      </div>

      {/* Output format */}
      <div className="flex gap-4 flex-wrap items-end">
        <div className="flex items-center gap-2">
          <ArrowRight size={20} className="text-text-secondary" />
        </div>
        <div>
          <label className="block text-xs font-medium text-text-secondary mb-1">{t('tools.outputFormat')}</label>
          <select
            value={convertFormat}
            onChange={(e) => setConvertFormat(e.target.value)}
            className="px-3 py-2 text-sm bg-bg-secondary border border-border rounded-md text-text-primary"
          >
            <option value="pem">{t('tools.pemText')}</option>
            <option value="der">{t('tools.derBinary')}</option>
            <option value="pkcs12">{t('tools.pkcs12')}</option>
            <option value="pkcs7">{t('tools.pkcs7')}</option>
          </select>
        </div>
      </div>

      {/* Additional inputs for PKCS12 output */}
      {convertFormat === 'pkcs12' && (
        <div className="p-4 border border-border rounded-lg bg-bg-secondary/50 space-y-4">
          <div className="text-sm font-medium text-text-primary">{t('tools.pkcs12RequiresKey')}</div>
          
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1">{t('tools.privateKeyFile')}</label>
            <input
              type="file"
              accept=".pem,.key,.der"
              onChange={(e) => handleConvertFileChange(e, setConvertKeyFile, (data) => setConvertKey(data))}
              className="w-full text-sm text-text-secondary file:mr-3 file:py-1.5 file:px-3 file:border-0 file:rounded file:bg-bg-tertiary file:text-text-primary file:cursor-pointer"
            />
          </div>
          
          {!convertKeyFile && (
            <Textarea
              label={t('tools.orPasteKey')}
              placeholder="-----BEGIN PRIVATE KEY-----"
              value={convertKey}
              onChange={(e) => setConvertKey(e.target.value)}
              rows={3}
              className="font-mono text-xs"
            />
          )}
          
          <Textarea
            label={t('tools.caChainOptional')}
            placeholder={t('tools.caChainPlaceholder')}
            value={convertChain}
            onChange={(e) => setConvertChain(e.target.value)}
            rows={3}
            className="font-mono text-xs"
          />
        </div>
      )}

      {convertFormat === 'pkcs7' && (
        <Textarea
          label={t('tools.caChainOptional')}
          placeholder={t('tools.additionalCerts')}
          value={convertChain}
          onChange={(e) => setConvertChain(e.target.value)}
          rows={4}
          className="font-mono text-xs"
        />
      )}

      <div className="flex gap-3 flex-wrap items-end">
        <Input
          label={t('tools.inputPassword')}
          type="password"
          placeholder={t('tools.forEncryptedFiles')}
          value={convertPassword}
          onChange={(e) => setConvertPassword(e.target.value)}
          className="w-48"
        />
        {convertFormat === 'pkcs12' && (
          <Input
            label={t('tools.outputPkcs12Password')}
            type="password"
            placeholder={t('tools.passwordForP12')}
            value={pkcs12Password}
            onChange={(e) => setPkcs12Password(e.target.value)}
            className="w-48"
            showStrength
          />
        )}
      </div>

      <Button onClick={handleConvert} disabled={loading}>
        {loading ? <Spinner size={16} className="animate-spin" /> : <ArrowsLeftRight size={16} />}
        {t('tools.convert')}
      </Button>
    </div>
  )

  // Render SSL result
  const renderSSLResult = (data) => {
    if (!data) return null
    return (
    <CompactSection title={t('tools.sslCheckResult')} defaultOpen>
      <div className="space-y-4">
        {/* Status banner */}
        <div className={cn(
          'p-3 rounded-lg flex items-center gap-3',
          data.has_issues ? 'bg-status-danger/10' : 'bg-status-success/10'
        )}>
          {data.has_issues ? (
            <XCircle size={24} weight="fill" className="text-status-danger" />
          ) : (
            <CheckCircle size={24} weight="fill" className="text-status-success" />
          )}
          <div>
            <div className="font-medium text-text-primary">
              {data.has_issues ? t('tools.issuesFound') : t('tools.certificateOk')}
            </div>
            <div className="text-sm text-text-secondary">
              {data.hostname}:{data.port}
            </div>
          </div>
        </div>

        {/* Issues */}
        {data.issues?.length > 0 && (
          <div className="space-y-1">
            {data.issues.map((issue, i) => (
              <div key={i} className="flex items-center gap-2 text-sm text-status-danger">
                <Warning size={14} />
                {issue}
              </div>
            ))}
          </div>
        )}

        {/* Certificate info */}
        <CompactGrid cols={2}>
          <CompactField autoIcon="commonName" label={t('common.commonName')} value={data.subject?.commonName} copyable />
          <CompactField autoIcon="issuer" label={t('common.issuer')} value={data.issuer?.commonName || data.issuer?.organizationName} />
          <CompactField autoIcon="validFrom" label={t('common.validFrom')} value={new Date(data.not_valid_before).toLocaleDateString()} />
          <CompactField autoIcon="validUntil" label={t('common.validUntil')} value={new Date(data.not_valid_after).toLocaleDateString()} />
          <CompactField autoIcon="daysLeft" label={t('tools.daysLeft')} value={data.days_until_expiry} />
          <CompactField autoIcon="status" label={t('common.status')} value={
            <Badge variant={data.status === 'valid' ? 'success' : 'danger'}>
              {data.status}
            </Badge>
          } />
        </CompactGrid>

        {/* Connection info */}
        <CompactGrid cols={2}>
          <CompactField autoIcon="tlsVersion" label={t('tools.tlsVersion')} value={data.tls_version} />
          <CompactField autoIcon="cipher" label={t('tools.cipher')} value={data.cipher?.name} />
          <CompactField autoIcon="keyType" label={t('common.keyType')} value={`${data.public_key?.type} ${data.public_key?.size}-bit`} />
          <CompactField autoIcon="signature" label={t('common.signature')} value={data.signature_algorithm} />
        </CompactGrid>

        {/* SANs */}
        {data.extensions?.subject_alt_names?.length > 0 && (
          <div>
            <div className="text-xs font-medium text-text-secondary mb-1">{t('common.subjectAltNames')}</div>
            <div className="flex flex-wrap gap-1">
              {data.extensions.subject_alt_names.map((san, i) => (
                <Badge key={i} variant="secondary">{san.replace('DNS:', '')}</Badge>
              ))}
            </div>
          </div>
        )}

        {/* Fingerprints */}
        <CompactGrid cols={1}>
          <CompactField autoIcon="sha256" label={t('common.sha256')} value={data.fingerprints?.sha256} copyable mono className="text-xs" />
        </CompactGrid>
      </div>
    </CompactSection>
  )}

  // Render CSR result
  const renderCSRResult = (data) => {
    if (!data) return null
    return (
    <CompactSection title={t('common.csrDetails')} defaultOpen>
      <div className="space-y-4">
        <CompactGrid cols={2}>
          <CompactField autoIcon="commonName" label={t('common.commonName')} value={data.subject?.commonName} copyable />
          <CompactField autoIcon="organization" label={t('common.organization')} value={data.subject?.organizationName} />
          <CompactField autoIcon="country" label={t('common.country')} value={data.subject?.countryName} />
          <CompactField autoIcon="state" label={t('common.state')} value={data.subject?.stateOrProvinceName} />
          <CompactField autoIcon="keyType" label={t('common.keyType')} value={`${data.public_key?.type} ${data.public_key?.size || data.public_key?.curve}`} />
          <CompactField autoIcon="signatureValid" label={t('tools.signatureValid')} value={
            <Badge variant={data.is_signature_valid ? 'success' : 'danger'}>
              {data.is_signature_valid ? t('common.yes') : t('common.no')}
            </Badge>
          } />
        </CompactGrid>

        {data.extensions?.subject_alt_names?.length > 0 && (
          <div>
            <div className="text-xs font-medium text-text-secondary mb-1">{t('tools.requestedSans')}</div>
            <div className="flex flex-wrap gap-1">
              {data.extensions.subject_alt_names.map((san, i) => (
                <Badge key={i} variant="secondary">{san.replace('DNS:', '')}</Badge>
              ))}
            </div>
          </div>
        )}
      </div>
    </CompactSection>
  )}

  // Render Certificate result
  const renderCertResult = (data) => {
    if (!data) return null
    return (
    <CompactSection title={t('common.certificateDetails')} defaultOpen>
      <div className="space-y-4">
        {/* Status */}
        <div className={cn(
          'p-3 rounded-lg flex items-center gap-3',
          data.status !== 'valid' ? 'bg-status-danger/10' : 'bg-status-success/10'
        )}>
          {data.status !== 'valid' ? (
            <XCircle size={24} weight="fill" className="text-status-danger" />
          ) : (
            <CheckCircle size={24} weight="fill" className="text-status-success" />
          )}
          <div>
            <div className="font-medium text-text-primary">
              {data.status === 'valid' ? t('tools.validCertificate') : data.status === 'expired' ? t('common.expired') : t('tools.notYetValid')}
            </div>
            <div className="text-sm text-text-secondary">
              {data.is_ca ? t('common.certificateAuthority') : t('tools.endEntityCertificate')}
            </div>
          </div>
        </div>

        {/* Subject & Issuer */}
        <CompactGrid cols={2}>
          <CompactField autoIcon="subjectCn" label={t('tools.subjectCn')} value={data.subject?.commonName} copyable />
          <CompactField autoIcon="issuerCn" label={t('tools.issuerCn')} value={data.issuer?.commonName} />
          <CompactField autoIcon="organization" label={t('common.organization')} value={data.subject?.organizationName} />
          <CompactField autoIcon="issuerOrg" label={t('tools.issuerOrg')} value={data.issuer?.organizationName} />
        </CompactGrid>

        {/* Validity */}
        <CompactGrid cols={3}>
          <CompactField autoIcon="validFrom" label={t('common.validFrom')} value={new Date(data.not_valid_before).toLocaleDateString()} />
          <CompactField autoIcon="validUntil" label={t('common.validUntil')} value={new Date(data.not_valid_after).toLocaleDateString()} />
          <CompactField autoIcon="daysLeft" label={t('tools.daysLeft')} value={data.days_until_expiry} />
        </CompactGrid>

        {/* Technical */}
        <CompactGrid cols={2}>
          <CompactField autoIcon="serialNumber" label={t('common.serialNumber')} value={data.serial_number} copyable mono />
          <CompactField autoIcon="version" label={t('tools.version')} value={data.version} />
          <CompactField autoIcon="keyType" label={t('common.keyType')} value={`${data.public_key?.type} ${data.public_key?.size || data.public_key?.curve}`} />
          <CompactField autoIcon="signatureAlgorithm" label={t('common.signatureAlgorithm')} value={data.signature_algorithm} />
        </CompactGrid>

        {/* Extensions */}
        {data.extensions?.key_usage?.length > 0 && (
          <div>
            <div className="text-xs font-medium text-text-secondary mb-1">{t('common.keyUsage')}</div>
            <div className="flex flex-wrap gap-1">
              {data.extensions.key_usage.map((ku, i) => (
                <Badge key={i} variant="secondary">{ku}</Badge>
              ))}
            </div>
          </div>
        )}

        {data.extensions?.extended_key_usage?.length > 0 && (
          <div>
            <div className="text-xs font-medium text-text-secondary mb-1">{t('common.extKeyUsage')}</div>
            <div className="flex flex-wrap gap-1">
              {data.extensions.extended_key_usage.map((eku, i) => (
                <Badge key={i} variant="secondary">{eku}</Badge>
              ))}
            </div>
          </div>
        )}

        {data.extensions?.subject_alt_names?.length > 0 && (
          <div>
            <div className="text-xs font-medium text-text-secondary mb-1">{t('common.subjectAltNames')}</div>
            <div className="flex flex-wrap gap-1">
              {data.extensions.subject_alt_names.map((san, i) => (
                <Badge key={i} variant="secondary">{san.replace('DNS:', '')}</Badge>
              ))}
            </div>
          </div>
        )}

        {/* Fingerprints */}
        <CompactGrid cols={1}>
          <CompactField autoIcon="sha1" label={t('tools.sha1')} value={data.fingerprints?.sha1} copyable mono className="text-xs" />
          <CompactField autoIcon="sha256" label={t('tools.sha256')} value={data.fingerprints?.sha256} copyable mono className="text-xs" />
        </CompactGrid>
      </div>
    </CompactSection>
  )}

  // Render Match result
  const renderMatchResult = (data) => {
    if (!data) return null
    return (
    <CompactSection title={t('tools.keyMatchResults')} defaultOpen>
      <div className="space-y-4">
        {/* Overall status */}
        <div className={cn(
          'p-4 rounded-lg flex items-center gap-3',
          data.all_match ? 'bg-status-success/10' : 'bg-status-danger/10'
        )}>
          {data.all_match ? (
            <CheckCircle size={32} weight="fill" className="text-status-success" />
          ) : (
            <XCircle size={32} weight="fill" className="text-status-danger" />
          )}
          <div>
            <div className="text-lg font-medium text-text-primary">
              {data.all_match ? t('tools.allItemsMatch') : t('tools.mismatchDetected')}
            </div>
            <div className="text-sm text-text-secondary">
              {t('tools.matchCount', { matches: data.matches?.length || 0, mismatches: data.mismatches?.length || 0 })}
            </div>
          </div>
        </div>

        {/* Items parsed */}
        <div>
          <div className="text-xs font-medium text-text-secondary mb-2">{t('tools.parsedItems')}</div>
          <div className="space-y-2">
            {data.items?.map((item, i) => (
              <div key={i} className="flex items-center gap-2 p-2 rounded bg-bg-secondary">
                {item.valid ? (
                  <CheckCircle size={16} className="text-status-success" />
                ) : (
                  <XCircle size={16} className="text-status-danger" />
                )}
                <Badge variant={item.type === 'certificate' ? 'primary' : item.type === 'private_key' ? 'warning' : 'secondary'}>
                  {item.type}
                </Badge>
                {item.cn && <span className="text-sm text-text-primary">{item.cn}</span>}
                {item.key_type && <span className="text-sm text-text-secondary">{item.key_type}</span>}
                {item.error && <span className="text-sm text-status-danger">{item.error}</span>}
              </div>
            ))}
          </div>
        </div>

        {/* Match details */}
        {data.matches?.length > 0 && (
          <div>
            <div className="text-xs font-medium text-text-secondary mb-2">{t('tools.matches')}</div>
            <div className="space-y-1">
              {data.matches.map((m, i) => (
                <div key={i} className="flex items-center gap-2 text-sm text-status-success">
                  <CheckCircle size={14} />
                  {m.item1} ↔ {m.item2}
                </div>
              ))}
            </div>
          </div>
        )}

        {data.mismatches?.length > 0 && (
          <div>
            <div className="text-xs font-medium text-text-secondary mb-2">{t('tools.mismatches')}</div>
            <div className="space-y-1">
              {data.mismatches.map((m, i) => (
                <div key={i} className="flex items-center gap-2 text-sm text-status-danger">
                  <XCircle size={14} />
                  {m.item1} ≠ {m.item2}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </CompactSection>
  )}

  // Render Convert result
  const renderConvertResult = (data) => {
    if (!data) return null
    return (
    <CompactSection title={t('tools.conversionResult')} defaultOpen>
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <CheckCircle size={24} weight="fill" className="text-status-success" />
          <div>
            <div className="font-medium text-text-primary">{t('tools.conversionSuccessful')}</div>
            <div className="text-sm text-text-secondary">
              {t('tools.outputFile', { filename: data.filename, format: data.format?.toUpperCase() })}
            </div>
          </div>
        </div>

        {/* Show text content for PEM/PKCS7 */}
        {(data.format === 'pem' || data.format === 'pkcs7') && (
          <div className="relative">
            <pre className="p-3 bg-bg-secondary rounded-lg text-xs font-mono overflow-x-auto max-h-64 text-text-primary">
              {data.data}
            </pre>
            <button
              onClick={() => copyToClipboard(data.data)}
              className="absolute top-2 right-2 p-1.5 rounded bg-bg-tertiary hover:bg-bg-secondary"
            >
              <Copy size={14} className="text-text-secondary" />
            </button>
          </div>
        )}

        <Button onClick={downloadConverted}>
          <Download size={16} />
          {t('tools.download', { filename: data.filename })}
        </Button>
      </div>
    </CompactSection>
  )}

  // Render result based on type
  const renderResult = () => {
    if (!result) return null

    if (result.type === 'error') {
      return (
        <div className="p-4 bg-status-danger/10 rounded-lg flex items-center gap-3">
          <XCircle size={24} className="text-status-danger" />
          <div className="text-status-danger">{result.message}</div>
        </div>
      )
    }

    switch (result.type) {
      case 'ssl': return renderSSLResult(result.data)
      case 'csr': return renderCSRResult(result.data)
      case 'cert': return renderCertResult(result.data)
      case 'match': return renderMatchResult(result.data)
      case 'convert': return renderConvertResult(result.data)
      default: return null
    }
  }

  // Render active tool form
  const renderToolForm = () => {
    switch (activeTool) {
      case 'ssl-checker': return renderSSLChecker()
      case 'csr-decoder': return renderCSRDecoder()
      case 'cert-decoder': return renderCertDecoder()
      case 'key-matcher': return renderKeyMatcher()
      case 'converter': return renderConverter()
      default: return null
    }
  }

  return (
    <ResponsiveLayout
      title={t('common.tools')}
      subtitle={t('tools.subtitle')}
      icon={Wrench}
      helpContent={helpContent}
    >
      <div className="space-y-6 p-4">
        {/* Tool selector */}
        {renderToolSelector()}

        {/* Tool form */}
        <div className="bg-bg-primary border border-border rounded-lg p-4">
          {renderToolForm()}
        </div>

        {/* Result */}
        {result && (
          <div className="mt-4">
            {renderResult()}
          </div>
        )}
      </div>
    </ResponsiveLayout>
  )
}
