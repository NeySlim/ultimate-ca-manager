/**
 * Certificate tools, on the mockup's sectioned form (settingsView()): the table of contents of the
 * tools, then the tool chosen in its frame (one at a time): its fields, its run as the line of a
 * settings test (the button, then the outcome in words), and the details of the outcome under it.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toolsService } from '../services'
import { useNotification } from '../contexts'
import { useClipboard } from '../hooks'
import { formatDate, downloadBlob } from '../lib/utils'
import { keyAlgorithmLabel } from '../lib/keyAlgorithms'
import { Zone, PageHead, Btn, Pill, Facts, RecordList, RecordRow } from '../components/atelier'
import { copyRow, fact } from '../components/atelier/facts'
import { digestHex } from '../lib/digestHex'
import { SettingsLayout, SettingsToc, SettingsJump, SettingsFrame, SettingsGroup, SettingsTest } from '../components/atelier/SettingsView'
import { Input, NumberInput, Notice, PemField, SecretInput, Select, Textarea } from '../components/atelier/Form'
import { useSectionParam } from '../components/atelier/useSectionParam'

// 'RSA 2048-bit', 'EC secp384r1', 'ML-DSA-65 (level 3)': no size for a key that has none
function publicKeyText(pk, t, bitSuffix = '') {
  const size = pk?.size ? `${pk.size}${bitSuffix}` : pk?.curve
  return [keyAlgorithmLabel(pk?.type, t, pk?.security_level), size].filter(Boolean).join(' ') || null
}

// The tools in the order of the table of contents, with the mockup's pictogram of each
const TOOLS = [
  { id: 'ssl-checker', labelKey: 'tools.sslChecker', descKey: 'tools.sslCheckerDesc', icon: 'globe' },
  { id: 'csr-decoder', labelKey: 'tools.csrDecoder', descKey: 'tools.csrDecoderDesc', icon: 'file' },
  { id: 'cert-decoder', labelKey: 'tools.decoder', descKey: 'tools.certDecoderDesc', icon: 'cert' },
  { id: 'key-matcher', labelKey: 'tools.keyMatcher', descKey: 'tools.keyMatcherDesc', icon: 'key' },
  { id: 'converter', labelKey: 'tools.converter', descKey: 'tools.converterDesc', icon: 'refresh' },
]
// Every PEM a tool reads takes one height
const PEM_ROWS = 6
const ANY_FILE = '.pem,.crt,.cer,.der,.p12,.pfx,.p7b,.p7c,.key,.csr'
const keyOutput = (format) => format === 'pkcs12' || format === 'jks'

export default function CertificateToolsPage() {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const { copy: clipboardCopy } = useClipboard()
  // The tool a link names (/tools?tab=converter) is the one shown
  const [activeTool, setActiveTool] = useSectionParam(TOOLS.map((tool) => tool.id), 'ssl-checker')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)

  const [sslHostname, setSslHostname] = useState('')
  const [sslPort, setSslPort] = useState('443')
  const [csrPem, setCsrPem] = useState('')
  const [certPem, setCertPem] = useState('')
  const [matchCert, setMatchCert] = useState('')
  const [matchKey, setMatchKey] = useState('')
  const [matchCsr, setMatchCsr] = useState('')
  const [matchPassword, setMatchPassword] = useState('')
  // The input to convert: pasted text or a file's content (PEM text, else BASE64:); its file, for the name
  const [convertPem, setConvertPem] = useState('')
  const [convertFile, setConvertFile] = useState(null)
  const [convertFormat, setConvertFormat] = useState('der')
  const [convertKey, setConvertKey] = useState('')
  const [convertChain, setConvertChain] = useState('')
  const [convertPassword, setConvertPassword] = useState('')
  const [pkcs12Password, setPkcs12Password] = useState('')

  // A PKCS#12 / PFX file needs its password
  const needsInputPassword = convertFile && /\.(p12|pfx)$/i.test(convertFile.name)
  // The server opens the input and a separate key with the same password
  const sealedPem = /ENCRYPTED/.test(convertPem) || /ENCRYPTED/.test(convertKey)
  const mustGivePassword = Boolean(needsInputPassword || sealedPem)
  const showPasswordField = mustGivePassword || Boolean(convertKey.trim())

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
      setResult({ type: 'ssl', tool: 'ssl-checker', data: response.data })
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
      setResult({ type: 'csr', tool: 'csr-decoder', data: response.data })
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
      setResult({ type: 'cert', tool: 'cert-decoder', data: response.data })
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
      setResult({ type: 'match', tool: 'key-matcher', data: response.data })
    } catch (error) {
      showError(error.message || t('tools.failedToMatchKeys'))
      setResult({ type: 'error', message: error.message })
    } finally {
      setLoading(false)
    }
  }

  const handleConvert = async () => {
    // Get content from file or textarea
    const content = convertPem.trim()
    const keyContent = convertKey.trim()
    
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
      setResult({ type: 'convert', tool: 'converter', data: response.data })
    } catch (error) {
      showError(error.message || t('tools.conversionFailed'))
      setResult({ type: 'error', message: error.message })
    } finally {
      setLoading(false)
    }
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

  const handleToolChange = (toolId) => {
    setActiveTool(toolId)
    resetResult()
  }

  const listed = (values) => (values?.length ? values.map((v) => String(v).replace('DNS:', '')).join(', ') : null)
  const dated = (value) => value && formatDate(value)
  // A digest in its chip on a long row; a serial in octets (the API writes it in hexadecimal, unpadded)
  const digest = (label, value) => ({ ...fact(label, value), kind: 'hex', long: true })
  const serial = (label, value) => {
    const hex = value ? digestHex(String(value).length % 2 ? `0${value}` : value) : value
    return { ...fact(label, hex), kind: 'hex', long: Boolean(hex && hex.length > 23) }
  }
  const signature = (label, value) => fact(label, value && <span title={t('common.issuerSignatureAlgorithmHint')}>{value}</span>)

  const sections = TOOLS.map((tool) => ({ id: tool.id, label: t(tool.labelKey), description: t(tool.descKey), icon: tool.icon }))
  const active = sections.find((section) => section.id === activeTool)

  // The outcome of the last run, in the words of the test line; the details follow under it
  const own = result && (result.type === 'error' || result.tool === activeTool) ? result : null
  const outcome = (() => {
    if (!own) return null
    if (own.type === 'error') return { ok: false, text: own.message || t('common.error') }
    const d = own.data || {}
    switch (own.type) {
      case 'ssl': return { ok: !d.has_issues, text: [d.has_issues ? t('tools.issuesFound') : t('tools.certificateOk'), d.hostname && `${d.hostname}:${d.port}`].filter(Boolean).join(' · ') }
      case 'csr': return { ok: d.is_signature_valid !== false, text: d.is_signature_valid === false ? t('tools.csrSignatureInvalid') : t('tools.decodedBelow') }
      case 'cert': return {
        ok: d.status === 'valid',
        text: `${d.status === 'valid' ? t('tools.validCertificate') : d.status === 'expired' ? t('common.expired') : t('tools.notYetValid')} · ${d.is_ca ? t('common.certificateAuthority') : t('tools.endEntityCertificate')}`,
      }
      case 'match': return {
        ok: !!d.all_match,
        text: `${d.all_match ? t('tools.allItemsMatch') : t('tools.mismatchDetected')} · ${t('tools.matchCount', { matches: d.matches?.length || 0, mismatches: d.mismatches?.length || 0 })}`,
      }
      case 'convert': return { ok: true, text: `${t('tools.conversionSuccessful')} · ${t('tools.outputFile', { filename: d.filename, format: d.format?.toUpperCase() })}` }
      default: return null
    }
  })()

  const run = (label, icon, onRun) => (
    <SettingsTest id={activeTool} label={label} icon={icon} write={false} primary busy={loading} onTest={onRun} result={outcome} hint={t('tools.runHint')} />
  )

  const renderSSLChecker = () => (
    <>
      <SettingsGroup legend={t('tools.sectionConnection')}>
        <Input id="tool-hostname" label={t('tools.hostname')} placeholder={t('common.commonNamePlaceholder')} value={sslHostname}
          onChange={(e) => setSslHostname(e.target.value)} />
        <NumberInput id="tool-port" label={t('common.portLabel')} placeholder={t('common.portPlaceholder')} value={sslPort}
          onChange={(e) => setSslPort(e.target.value)} />
      </SettingsGroup>
      {run(t('tools.checkSSL'), 'globe', handleCheckSSL)}
    </>
  )

  const renderCSRDecoder = () => (
    <>
      <SettingsGroup legend={t('tools.sectionPemInput')}>
        <PemField id="tool-csr" label={t('tools.csrPemLabel')} value={csrPem} onChange={setCsrPem} rows={PEM_ROWS} accept=".pem,.csr,.der"
          placeholder={'-----BEGIN CERTIFICATE REQUEST-----\n...\n-----END CERTIFICATE REQUEST-----'} />
      </SettingsGroup>
      {run(t('tools.decodeCsr'), 'file', handleDecodeCSR)}
    </>
  )

  const renderCertDecoder = () => (
    <>
      <SettingsGroup legend={t('tools.sectionCertificateInput')}>
        <PemField id="tool-cert" label={t('tools.certPemLabel')} value={certPem} onChange={setCertPem} rows={PEM_ROWS} accept=".pem,.crt,.cer,.der"
          placeholder={'-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----'} />
      </SettingsGroup>
      {run(t('tools.decodeCert'), 'cert', handleDecodeCert)}
    </>
  )

  const renderKeyMatcher = () => (
    <>
      <SettingsGroup legend={t('tools.sectionKeyInput')} legendHidden>
        <PemField id="tool-match-cert" label={t('tools.certificateOptional')} value={matchCert} onChange={setMatchCert} rows={PEM_ROWS}
          accept=".pem,.crt,.cer,.der" placeholder="-----BEGIN CERTIFICATE-----" />
        <PemField id="tool-match-key" label={t('tools.privateKeyOptional')} value={matchKey} onChange={setMatchKey} rows={PEM_ROWS}
          accept=".pem,.key,.der" placeholder="-----BEGIN PRIVATE KEY-----" />
        <PemField id="tool-match-csr" label={t('tools.csrOptional')} value={matchCsr} onChange={setMatchCsr} rows={PEM_ROWS}
          accept=".pem,.csr,.der" placeholder="-----BEGIN CERTIFICATE REQUEST-----" />
        <SecretInput id="tool-match-password" label={t('tools.keyPassword')} placeholder={t('tools.keyPasswordPlaceholder')} value={matchPassword}
          onChange={(e) => setMatchPassword(e.target.value)} />
      </SettingsGroup>
      {run(t('tools.matchKeys'), 'key', handleMatchKeys)}
    </>
  )

  const renderConverter = () => (
    <>
      <SettingsGroup legend={t('tools.sectionConversion')} legendHidden>
        <PemField id="tool-convert-input" label={t('tools.inputAnyFormat')} value={convertPem} rows={PEM_ROWS} accept={ANY_FILE} hint={t('tools.supportsFormats')}
          placeholder={'-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----'}
          onChange={(v) => { setConvertFile(null); setConvertPem(v) }}
          onFile={(file) => { setConvertFile(file); setConvertPassword('') }} />
        {/* Password field: a PKCS12/PFX file, an encrypted PEM, or a separate key */}
        {showPasswordField && (
          <SecretInput id="tool-convert-password" label={t('tools.inputPassword')} required={mustGivePassword} value={convertPassword}
            placeholder={needsInputPassword ? t('tools.pkcs12PasswordPlaceholder') : t('tools.keyOrFilePasswordPlaceholder')}
            onChange={(e) => setConvertPassword(e.target.value)} />
        )}
        <Select id="tool-convert-format" label={t('tools.outputFormat')} value={convertFormat} onChange={setConvertFormat}
          options={[
            { value: 'pem', label: t('tools.pemText') },
            { value: 'der', label: t('tools.derBinary') },
            { value: 'pkcs12', label: t('tools.pkcs12') },
            { value: 'jks', label: 'JKS (Java KeyStore)' },
            { value: 'pkcs7', label: t('tools.pkcs7') },
          ]} />
        {keyOutput(convertFormat) && (
          <Input id="tool-convert-output-password" label={t('tools.outputPkcs12Password')} type="password" autoComplete="new-password" required
            placeholder={t('tools.passwordForP12')} value={pkcs12Password} onChange={(e) => setPkcs12Password(e.target.value)} showStrength />
        )}
      </SettingsGroup>
      {keyOutput(convertFormat) && (
        <SettingsGroup legend={t('tools.pkcs12RequiresKey')}>
          <PemField id="tool-convert-key" label={t('tools.privateKeyFile')} value={convertKey} onChange={setConvertKey} rows={3}
            accept=".pem,.key,.der" placeholder="-----BEGIN PRIVATE KEY-----" />
          <Textarea id="tool-convert-chain" mono label={t('tools.caChainOptional')} placeholder={t('tools.caChainPlaceholder')} value={convertChain}
            onChange={(e) => setConvertChain(e.target.value)} rows={3} />
        </SettingsGroup>
      )}
      {convertFormat === 'pkcs7' && (
        <SettingsGroup legend={t('tools.caChainOptional')}>
          <Textarea id="tool-convert-chain" mono label={t('tools.caChainOptional')} placeholder={t('tools.additionalCerts')} value={convertChain}
            onChange={(e) => setConvertChain(e.target.value)} rows={PEM_ROWS} />
        </SettingsGroup>
      )}
      {run(t('tools.convert'), 'refresh', handleConvert)}
    </>
  )

  const statusPill = (ok, words) => <Pill tone={ok ? 'good' : 'bad'} label={words} />

  const renderSSLResult = (d) => (
    <SettingsGroup legend={t('tools.sslCheckResult')} grid={false} wide>
      {d.issues?.length > 0 && <Notice tone="bad">{d.issues.join(' · ')}</Notice>}
      <Facts items={[
        copyRow(t('common.commonName'), d.subject?.commonName),
        fact(t('common.issuer'), d.issuer?.commonName || d.issuer?.organizationName),
        fact(t('common.validFrom'), dated(d.not_valid_before)),
        fact(t('common.validUntil'), dated(d.not_valid_after)),
        fact(t('tools.daysLeft'), d.days_until_expiry),
        { label: t('common.status'), state: [d.status === 'valid' ? 'good' : 'bad', d.status] },
        fact(t('tools.tlsVersion'), d.tls_version),
        fact(t('tools.cipher'), d.cipher?.name),
        fact(t('common.keyType'), publicKeyText(d.public_key, t, '-bit')),
        signature(t('common.issuerSignatureShort'), d.signature_algorithm),
        listed(d.extensions?.subject_alt_names) && { label: t('common.subjectAltNames'), value: listed(d.extensions.subject_alt_names), long: true },
        digest(t('common.sha256'), d.fingerprints?.sha256),
      ]} />
    </SettingsGroup>
  )

  const renderCSRResult = (d) => (
    <SettingsGroup legend={t('common.csrDetails')} grid={false} wide>
      <Facts items={[
        copyRow(t('common.commonName'), d.subject?.commonName),
        fact(t('common.organization'), d.subject?.organizationName),
        fact(t('common.country'), d.subject?.countryName),
        fact(t('common.state'), d.subject?.stateOrProvinceName),
        fact(t('common.keyType'), publicKeyText(d.public_key, t)),
        { label: t('tools.signatureValid'), state: d.is_signature_valid ? ['good', t('common.yes')] : ['bad', t('common.no')] },
        listed(d.extensions?.subject_alt_names) && { label: t('tools.requestedSans'), value: listed(d.extensions.subject_alt_names), long: true },
      ]} />
    </SettingsGroup>
  )

  const renderCertResult = (d) => (
    <SettingsGroup legend={t('common.certificateDetails')} grid={false} wide>
      <Facts items={[
        copyRow(t('tools.subjectCn'), d.subject?.commonName),
        fact(t('tools.issuerCn'), d.issuer?.commonName),
        fact(t('common.organization'), d.subject?.organizationName),
        fact(t('tools.issuerOrg'), d.issuer?.organizationName),
        fact(t('common.validFrom'), dated(d.not_valid_before)),
        fact(t('common.validUntil'), dated(d.not_valid_after)),
        fact(t('tools.daysLeft'), d.days_until_expiry),
        serial(t('common.serialNumber'), d.serial_number),
        fact(t('tools.version'), d.version),
        fact(t('common.keyType'), publicKeyText(d.public_key, t)),
        signature(t('common.issuerSignatureAlgorithm'), d.signature_algorithm),
        listed(d.extensions?.key_usage) && { label: t('common.keyUsage'), value: listed(d.extensions.key_usage), long: true },
        listed(d.extensions?.extended_key_usage) && { label: t('common.extKeyUsage'), value: listed(d.extensions.extended_key_usage), long: true },
        listed(d.extensions?.subject_alt_names) && { label: t('common.subjectAltNames'), value: listed(d.extensions.subject_alt_names), long: true },
        digest(t('tools.sha1'), d.fingerprints?.sha1),
        digest(t('tools.sha256'), d.fingerprints?.sha256),
      ]} />
    </SettingsGroup>
  )

  const ITEM_WORDS = { certificate: 'common.certificate', private_key: 'common.privateKey', csr: 'common.csr' }
  const renderMatchResult = (d) => (
    <SettingsGroup legend={t('tools.keyMatchResults')} grid={false} wide>
      <RecordList empty={t('tools.noParsedItems')}>
        {(d.items || []).map((item, i) => (
          <RecordRow key={`item-${i}`} title={ITEM_WORDS[item.type] ? t(ITEM_WORDS[item.type]) : item.type}
            meta={[item.cn, item.key_type, item.error].filter(Boolean).join(' · ')}
            badge={statusPill(item.valid, item.valid ? t('tools.itemRead') : t('tools.itemUnreadable'))} />
        ))}
        {(d.matches || []).map((m, i) => (
          <RecordRow key={`match-${i}`} title={`${m.item1} ↔ ${m.item2}`} badge={statusPill(true, t('tools.matches'))} />
        ))}
        {(d.mismatches || []).map((m, i) => (
          <RecordRow key={`mismatch-${i}`} title={`${m.item1} ≠ ${m.item2}`} badge={statusPill(false, t('tools.mismatches'))} />
        ))}
      </RecordList>
    </SettingsGroup>
  )

  const renderConvertResult = (d) => (
    <SettingsGroup legend={t('tools.conversionResult')} grid={false} wide>
      {(d.format === 'pem' || d.format === 'pkcs7') && (
        <div className="field full">
          <Textarea id="tool-convert-output" mono readOnly rows={8} label={d.filename} value={d.data || ''} />
        </div>
      )}
      <div className="settings-actions">
        {(d.format === 'pem' || d.format === 'pkcs7') && <Btn icon="copy" onClick={() => copyToClipboard(d.data)}>{t('common.copy')}</Btn>}
        <Btn tone="primary" write={false} icon="download" onClick={downloadConverted}>{t('tools.download', { filename: d.filename })}</Btn>
      </div>
    </SettingsGroup>
  )

  const renderDetails = () => {
    if (!own?.data || own.type === 'error') return null
    switch (own.type) {
      case 'ssl': return renderSSLResult(own.data)
      case 'csr': return renderCSRResult(own.data)
      case 'cert': return renderCertResult(own.data)
      case 'match': return renderMatchResult(own.data)
      case 'convert': return renderConvertResult(own.data)
      default: return null
    }
  }

  const FORMS = {
    'ssl-checker': renderSSLChecker, 'csr-decoder': renderCSRDecoder, 'cert-decoder': renderCertDecoder,
    'key-matcher': renderKeyMatcher, converter: renderConverter,
  }

  return (
    <Zone testId="tools-page">
      <PageHead title={t('common.tools')} total={t('tools.toolCount', { count: sections.length })} intent={t('shell.moduleDesc.tools')} />
      <SettingsLayout
        toc={<SettingsToc label={t('tools.tocLabel')} sections={sections} current={activeTool}
          hrefFor={(id) => (id === 'ssl-checker' ? '/tools' : `/tools?tab=${id}`)} onJump={handleToolChange} />}
      >
        <SettingsJump sections={sections} current={activeTool} onJump={handleToolChange} />
        <SettingsFrame id={active.id} label={active.label} desc={active.description}>
          {FORMS[activeTool]()}
          {renderDetails()}
        </SettingsFrame>
      </SettingsLayout>
    </Zone>
  )
}
