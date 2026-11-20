/**
 * Certificate Tools Page
 * SSL checker, decoders, converters - like SSLShopper tools
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Globe, FileMagnifyingGlass, Key, ArrowsLeftRight,
  CheckCircle, XCircle, Warning, Certificate,
  Copy, Download, Spinner
} from '@phosphor-icons/react'
import {
  Button, Badge, Textarea, Input, Select, FileUpload,
  CompactSection, CompactGrid, CompactField,
} from '../components'
import { ResponsiveLayout } from '../components/ui/responsive'
import { toolsService } from '../services'
import { useNotification } from '../contexts'
import { useClipboard } from '../hooks'
import { cn, formatDate , downloadBlob} from '../lib/utils'
import { keyAlgorithmLabel } from '../lib/keyAlgorithms'
import { FormLayout, SectionToc, SectionJump, FormSection, FormGroup, useSectionParam } from '../components/sectioned'

// Tool definitions with tab-compatible format for sidebar layout
// 'RSA 2048-bit', 'EC secp384r1', 'ML-DSA-65 (level 3)': no size for a key that has none
function publicKeyText(pk, t, bitSuffix = '') {
  const size = pk?.size ? `${pk.size}${bitSuffix}` : pk?.curve
  return [keyAlgorithmLabel(pk?.type, t, pk?.security_level), size].filter(Boolean).join(' ') || null
}

const TOOLS = [
  {
    id: 'ssl-checker',
    nameKey: 'tools.sslChecker',
    descKey: 'tools.sslCheckerDesc',
    icon: Globe,
    color: 'icon-bg-emerald',
    labelKey: 'tools.sslChecker'
  },
  {
    id: 'csr-decoder',
    nameKey: 'tools.csrDecoder',
    descKey: 'tools.csrDecoderDesc',
    icon: FileMagnifyingGlass,
    color: 'icon-bg-blue',
    labelKey: 'tools.csrDecoder'
  },
  {
    id: 'cert-decoder',
    nameKey: 'tools.decoder',
    descKey: 'tools.certDecoderDesc',
    icon: Certificate,
    color: 'icon-bg-violet',
    labelKey: 'tools.decoder'
  },
  {
    id: 'key-matcher',
    nameKey: 'tools.keyMatcher',
    descKey: 'tools.keyMatcherDesc',
    icon: Key,
    color: 'icon-bg-orange',
    labelKey: 'tools.keyMatcher'
  },
  {
    id: 'converter',
    nameKey: 'tools.converter',
    descKey: 'tools.converterDesc',
    icon: ArrowsLeftRight,
    color: 'icon-bg-teal',
    labelKey: 'tools.converter'
  }
]

export default function CertificateToolsPage() {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const { copy: clipboardCopy } = useClipboard()
  // The tool a link names (/tools?tab=converter) is the one shown
  const [activeTool, setActiveTool] = useSectionParam(TOOLS.map((tool) => tool.id), 'ssl-checker')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)

  // Help content now provided via FloatingHelpPanel (helpPageKey="certTools")

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
  const [convertFormat, setConvertFormat] = useState('der')
  const [convertKey, setConvertKey] = useState('')
  const [convertKeyFile, setConvertKeyFile] = useState(null)
  const [convertChain, setConvertChain] = useState('')
  const [convertPassword, setConvertPassword] = useState('')
  const [pkcs12Password, setPkcs12Password] = useState('')

  // Detect if uploaded file needs a password (binary: p12, pfx, encrypted key)
  const needsInputPassword = convertFile && /\.(p12|pfx)$/i.test(convertFile.name)
  // The server opens the input and a separate key with the same password
  const sealedPem = /ENCRYPTED/.test(convertPem) || /ENCRYPTED/.test(convertKey)
  const mustGivePassword = Boolean(needsInputPassword || sealedPem)
  const showPasswordField = mustGivePassword || Boolean(convertKeyFile || convertKey.trim())

  const resetResult = () => setResult(null)

  const handleCheckSSL = async () => {
    if (!sslHostname.trim()) {
      showError(t('tools.pleaseEnterHostname'))
      return
    }
    setLoading(true)
    resetResult()
    try {
      const response = await toolsService.checkSsl({
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
      const response = await toolsService.decodeCsr({
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
      const response = await toolsService.decodeCert({
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
      const response = await toolsService.matchKeys({
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
    // Guard: PKCS12/PFX input requires password
    if (mustGivePassword && !convertPassword) {
      showError(t('tools.pkcs12PasswordRequired'))
      return
    }
    // Guard: PKCS12 output requires key + password
    if ((convertFormat === 'pkcs12' || convertFormat === 'jks') && !keyContent) {
      showError(t('tools.privateKeyRequired'))
      return
    }
    if ((convertFormat === 'pkcs12' || convertFormat === 'jks') && !pkcs12Password) {
      showError(t('tools.pkcs12OutputPasswordRequired'))
      return
    }
    setLoading(true)
    resetResult()
    try {
      const response = await toolsService.convert({
        pem: content,
        output_format: convertFormat,
        private_key: keyContent,
        chain: convertChain.trim(),
        password: convertPassword,
        output_password: (convertFormat === 'pkcs12' || convertFormat === 'jks') ? pkcs12Password : ''
      })
      setResult({ type: 'convert', data: response.data })
    } catch (error) {
      showError(error.message || t('tools.conversionFailed'))
      setResult({ type: 'error', message: error.message })
    } finally {
      setLoading(false)
    }
  }

  // Helper to read file — detects PEM vs DER by content
  const readFileAsText = (file) => {
    return new Promise((resolve) => {
      const reader = new FileReader()
      reader.onload = (e) => {
        const bytes = new Uint8Array(e.target.result)
        const header = String.fromCharCode(...bytes.slice(0, 11))
        if (header.startsWith('-----BEGIN')) {
          resolve(new TextDecoder().decode(bytes))
        } else {
          resolve('BASE64:' + btoa(String.fromCharCode(...bytes)))
        }
      }
      reader.readAsArrayBuffer(file)
    })
  }

  const downloadConverted = () => {
    if (!result?.data?.data) return
    const { data, filename, format } = result.data
    
    let blob
    if (format === 'der' || format === 'pkcs12' || format === 'jks') {
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
    
    downloadBlob(blob, filename)
    showSuccess(t('tools.downloaded', { filename }))
  }

  const copyToClipboard = (text) => {
    clipboardCopy(text)
    showSuccess(t('common.copied'))
  }

  // Read file content (PEM as text, binary as base64)
  // Always reads as ArrayBuffer first, then detects PEM vs DER
  // because .crt/.cer files can be either PEM or DER format
  const readFileContent = (file) => {
    return new Promise((resolve) => {
      const reader = new FileReader()
      reader.onload = (event) => {
        const bytes = new Uint8Array(event.target.result)
        // Check if content starts with "-----BEGIN" (PEM text)
        const header = String.fromCharCode(...bytes.slice(0, 11))
        if (header.startsWith('-----BEGIN')) {
          resolve(new TextDecoder().decode(bytes))
        } else {
          let binary = ''
          for (let i = 0; i < bytes.length; i++) {
            binary += String.fromCharCode(bytes[i])
          }
          resolve('BASE64:' + btoa(binary))
        }
      }
      reader.readAsArrayBuffer(file)
    })
  }

  // Reusable drop zone + textarea for PEM/file input
  const TextareaWithUpload = ({ label, placeholder, value, onChange, rows = 6, accept = '.pem,.crt,.cer,.der,.p12,.pfx,.p7b,.key,.csr' }) => {
    const isBinary = value?.startsWith('BASE64:')
    
    return (
      <div className="space-y-3">
        <FileUpload
          compact
          accept={accept}
          maxSize={50 * 1024 * 1024}
          onFileSelect={async (file) => {
            const content = await readFileContent(file)
            onChange({ target: { value: content } })
          }}
          helperText={accept}
        />
        {!isBinary && (
          <>
            <div className="flex items-center gap-2">
              <div className="flex-1 h-px bg-border" />
              <span className="text-xs text-text-secondary">{t('common.orPastePem')}</span>
              <div className="flex-1 h-px bg-border" />
            </div>
            <Textarea
              label={label}
              placeholder={placeholder}
              value={value}
              onChange={onChange}
              rows={rows}
              className="font-mono text-xs"
            />
          </>
        )}
        {isBinary && (
          <div className="flex items-center gap-2 text-sm">
            <CheckCircle size={16} className="text-status-success" />
            <span className="text-text-primary">[{t('tools.binaryFileLoaded')} - {Math.round(value.length / 1.37)} bytes]</span>
            <Button type="button" variant="ghost" size="xs" onClick={() => onChange({ target: { value: '' } })}>
              <XCircle size={16} />
            </Button>
          </div>
        )}
      </div>
    )
  }

  const handleToolChange = (toolId) => {
    setActiveTool(toolId)
    resetResult()
  }

  const sections = TOOLS.map(tool => ({
    id: tool.id,
    label: t(tool.labelKey),
    description: t(tool.descKey),
    icon: tool.icon,
  }))
  const toolGroups = [
    { id: 'analysis', label: t('tools.groups.analysis'), ids: ['ssl-checker', 'csr-decoder', 'cert-decoder'] },
    { id: 'verification', label: t('tools.groups.verification'), ids: ['key-matcher'] },
    { id: 'conversion', label: t('tools.groups.conversion'), ids: ['converter'] },
  ]
  const active = sections.find(section => section.id === activeTool)

  // Render SSL Checker
  const renderSSLChecker = () => (
    <>
      <FormGroup title={t('tools.sectionConnection')}>
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
      <Button type="button" onClick={handleCheckSSL} disabled={loading}>
        {loading ? <Spinner size={16} className="animate-spin" /> : <Globe size={16} />}
        {t('tools.checkSSL')}
      </Button>
    </div>
    </FormGroup>
    </>
  )

  // Render CSR Decoder
  const renderCSRDecoder = () => (
    <>
      <FormGroup title={t('tools.sectionPemInput')}>
    <div className="space-y-4">
      <TextareaWithUpload
        label={t('tools.csrPemLabel')}
        placeholder="-----BEGIN CERTIFICATE REQUEST-----&#10;...&#10;-----END CERTIFICATE REQUEST-----"
        value={csrPem}
        onChange={(e) => setCsrPem(e.target.value)}
        rows={8}
        accept=".pem,.csr,.der"
      />
      <Button type="button" onClick={handleDecodeCSR} disabled={loading}>
        {loading ? <Spinner size={16} className="animate-spin" /> : <FileMagnifyingGlass size={16} />}
        {t('tools.decodeCsr')}
      </Button>
    </div>
    </FormGroup>
    </>
  )

  // Render Certificate Decoder
  const renderCertDecoder = () => (
    <>
      <FormGroup title={t('tools.sectionCertificateInput')}>
    <div className="space-y-4">
      <TextareaWithUpload
        label={t('tools.certPemLabel')}
        placeholder="-----BEGIN CERTIFICATE-----&#10;...&#10;-----END CERTIFICATE-----"
        value={certPem}
        onChange={(e) => setCertPem(e.target.value)}
        rows={8}
        accept=".pem,.crt,.cer,.der"
      />
      <Button type="button" onClick={handleDecodeCert} disabled={loading}>
        {loading ? <Spinner size={16} className="animate-spin" /> : <Certificate size={16} />}
        {t('tools.decodeCert')}
      </Button>
    </div>
    </FormGroup>
    </>
  )

  // Render Key Matcher
  const renderKeyMatcher = () => (
    <>
      <FormGroup title={t('tools.sectionKeyInput')}>
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
        noAutofill
        placeholder={t('tools.keyPasswordPlaceholder')}
        value={matchPassword}
        onChange={(e) => setMatchPassword(e.target.value)}
        className="max-w-xs"
      />
      <Button type="button" onClick={handleMatchKeys} disabled={loading}>
        {loading ? <Spinner size={16} className="animate-spin" /> : <Key size={16} />}
        {t('tools.matchKeys')}
      </Button>
    </div>
    </FormGroup>
    </>
  )

  // Render Converter
  const renderConverter = () => (
    <>
      <FormGroup title={t('tools.sectionConversion')}>
    <div className="space-y-4">
      {/* Input section */}
      <div className="p-4 border border-border rounded-lg bg-secondary-op50 space-y-4">
        <div className="text-sm font-medium text-text-primary">{t('tools.inputAnyFormat')}</div>
        
        {/* File upload drop zone */}
        <FileUpload
          compact
          accept=".pem,.crt,.cer,.der,.p12,.pfx,.p7b,.p7c,.key,.csr"
          maxSize={50 * 1024 * 1024}
          onFileSelect={async (file) => {
            setConvertFile(file)
            const content = await readFileContent(file)
            setConvertFileData(content)
            setConvertPassword('')
          }}
          helperText={t('tools.supportsFormats')}
        />
        
        {convertFile && (
          <div className="flex items-center gap-2 text-sm">
            <CheckCircle size={16} className="text-status-success" />
            <span className="text-text-primary">{convertFile.name}</span>
            <Button 
              variant="ghost"
              size="xs"
              onClick={() => { setConvertFile(null); setConvertFileData(null); setConvertPassword('') }}
            >
              <XCircle size={16} />
            </Button>
          </div>
        )}

        {/* Password field: a PKCS12/PFX file, an encrypted PEM, or a separate key */}
        {showPasswordField && (
          <Input
            label={t('tools.inputPassword')}
            type="password"
            noAutofill
            required={mustGivePassword}
            placeholder={needsInputPassword ? t('tools.pkcs12PasswordPlaceholder') : t('tools.keyOrFilePasswordPlaceholder')}
            value={convertPassword}
            onChange={(e) => setConvertPassword(e.target.value)}
          />
        )}
        
        {/* Or paste PEM */}
        {!convertFile && (
          <>
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
            />
          </>
        )}
      </div>

      {/* Output format */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-end">
        <Select
          label={t('tools.outputFormat')}
          value={convertFormat}
          onChange={convertFormat => setConvertFormat(convertFormat)}
          options={[
            { value: 'pem', label: t('tools.pemText') },
            { value: 'der', label: t('tools.derBinary') },
            { value: 'pkcs12', label: t('tools.pkcs12') },
            { value: 'jks', label: 'JKS (Java KeyStore)' },
            { value: 'pkcs7', label: t('tools.pkcs7') },
          ]}
        />
        {(convertFormat === 'pkcs12' || convertFormat === 'jks') && (
          <Input
            label={t('tools.outputPkcs12Password')}
            type="password"
            noAutofill
            required
            placeholder={t('tools.passwordForP12')}
            value={pkcs12Password}
            onChange={(e) => setPkcs12Password(e.target.value)}
            showStrength
          />
        )}
      </div>

      {/* Additional inputs for PKCS12/JKS output */}
      {(convertFormat === 'pkcs12' || convertFormat === 'jks') && (
        <div className="p-4 border border-border rounded-lg bg-secondary-op50 space-y-4">
          <div className="text-sm font-medium text-text-primary">{t('tools.pkcs12RequiresKey')}</div>
          
          <FileUpload
            compact
            label={t('tools.privateKeyFile')}
            accept=".pem,.key,.der"
            maxSize={50 * 1024 * 1024}
            onFileSelect={async (file) => {
              setConvertKeyFile(file)
              const content = await readFileContent(file)
              setConvertKey(content)
            }}
          />
          
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

      <Button type="button" onClick={handleConvert} disabled={loading}>
        {loading ? <Spinner size={16} className="animate-spin" /> : <ArrowsLeftRight size={16} />}
        {t('tools.convert')}
      </Button>
    </div>
    </FormGroup>
    </>
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
          data.has_issues ? 'bg-status-danger-op10' : 'bg-status-success-op10'
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
          <CompactField autoIcon="validFrom" label={t('common.validFrom')} value={formatDate(data.not_valid_before)} />
          <CompactField autoIcon="validUntil" label={t('common.validUntil')} value={formatDate(data.not_valid_after)} />
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
          <CompactField autoIcon="keyType" label={t('common.keyType')} value={publicKeyText(data.public_key, t, '-bit')} />
          <CompactField autoIcon="signature" label={t('common.issuerSignatureShort')} hint={t('common.issuerSignatureAlgorithmHint')} value={data.signature_algorithm} />
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
          <CompactField autoIcon="keyType" label={t('common.keyType')} value={publicKeyText(data.public_key, t)} />
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
          data.status !== 'valid' ? 'bg-status-danger-op10' : 'bg-status-success-op10'
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
          <CompactField autoIcon="validFrom" label={t('common.validFrom')} value={formatDate(data.not_valid_before)} />
          <CompactField autoIcon="validUntil" label={t('common.validUntil')} value={formatDate(data.not_valid_after)} />
          <CompactField autoIcon="daysLeft" label={t('tools.daysLeft')} value={data.days_until_expiry} />
        </CompactGrid>

        {/* Technical */}
        <CompactGrid cols={2}>
          <CompactField autoIcon="serialNumber" label={t('common.serialNumber')} value={data.serial_number} copyable mono />
          <CompactField autoIcon="version" label={t('tools.version')} value={data.version} />
          <CompactField autoIcon="keyType" label={t('common.keyType')} value={publicKeyText(data.public_key, t)} />
          <CompactField autoIcon="issuerSignatureAlgorithm" label={t('common.issuerSignatureAlgorithm')} hint={t('common.issuerSignatureAlgorithmHint')} value={data.signature_algorithm} />
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
          data.all_match ? 'bg-status-success-op10' : 'bg-status-danger-op10'
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
            <Button
              variant="ghost"
              size="xs"
              onClick={() => copyToClipboard(data.data)}
              className="absolute top-2 right-2"
            >
              <Copy size={14} />
            </Button>
          </div>
        )}

        <Button type="button" onClick={downloadConverted}>
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
        <div className="p-4 bg-status-danger-op10 rounded-lg flex items-center gap-3">
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

  // One tool at a time in its frame; the table of contents picks it, its form keeps its own action
  return (
    <ResponsiveLayout
      title={t('common.tools')}
      total={t('tools.toolCount', { count: sections.length })}
      intent={t('tools.intent')}
      helpPageKey="certTools"
    >
      <FormLayout
        toc={(
          <SectionToc
            label={t('tools.tocLabel')}
            sections={sections}
            groups={toolGroups}
            current={activeTool}
            hrefFor={(id) => (id === 'ssl-checker' ? '/tools' : `/tools?tab=${id}`)}
            onJump={handleToolChange}
          />
        )}
      >
        <SectionJump label={t('sectioned.jumpLabel')} sections={sections} value={activeTool} onJump={handleToolChange} />
        <FormSection id={active.id} title={active.label} description={active.description}>
          {renderToolForm()}
          {result && renderResult()}
        </FormSection>
      </FormLayout>
    </ResponsiveLayout>
  )
}
