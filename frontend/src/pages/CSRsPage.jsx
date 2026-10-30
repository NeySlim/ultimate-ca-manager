/**
 * CSRs (Certificate Signing Requests) Page - With Pending/History Tabs
 */
import { showNotices } from '../lib/notices'
import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { 
  FileText, Upload, SignIn, Trash, Download, 
  Clock, Key, UploadSimple, CheckCircle, Warning,
  ClockCounterClockwise, Certificate, Stamp, ClipboardText,
  Plus, X, GlobeSimple, At, ArrowsClockwise
} from '@phosphor-icons/react'
import {
  Badge, Button, Modal, Input, Select, HelpCard, FileUpload, Textarea,
  CompactSection, CompactGrid, CompactField, CompactHeader, CompactStats,
  KeyIndicator, EkuMultiSelect
} from '../components'
import { SmartImportModal } from '../components/SmartImport'
import { ResponsiveLayout, ResponsiveDataTable } from '../components/ui/responsive'
import { csrsService, casService, templatesService, mscaService, ekuService, certificatesService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, useModals } from '../hooks'
import { useMobile } from '../contexts/MobileContext'
import { extractData, formatDate, cn , downloadBlob} from '../lib/utils'
import { getSanValidationError, sanRowsToPayload } from '../lib/sanValidate'
import { daysSinceExpiry, expiryVariant, hasExpiry } from '../lib/expiry'
import { VALIDITY } from '../constants/config'
import { signingCas, unlistedSigningCas } from '../lib/caSelection'
import { soleImported } from '../lib/importResult'
import { PostQuantumBadge } from '../components/PostQuantumBadge'
import { CSR_LABELS, KEY_ALGORITHMS, groupedOptions, keyAlgorithmLabel, listAlgorithms } from '../lib/keyAlgorithms'
import { useFipsMode } from '../lib/policyAlgorithms'
import { BrainpoolNotice } from '../components/BrainpoolNotice'
import { useOpenEntity } from '../hooks/useOpenEntity'
export default function CSRsPage() {
  const { t } = useTranslation()
  const { isMobile } = useMobile()
  const navigate = useNavigate()
  const openEntity = useOpenEntity()
  const { showSuccess, showError, showConfirm, showWarning } = useNotification()
  const { canWrite, canDelete, hasPermission } = usePermission()
  // Direct private-key export is the admin-only read:private_keys scope,
  // as on the certificates page
  const canExportKey = hasPermission('read:private_keys')
  const canReadCertificates = hasPermission('read:certificates')
  const [searchParams, setSearchParams] = useSearchParams()
  const { modals, open: openModal, close: closeModal } = useModals(['upload', 'sign', 'generate'])
  
  // Tab definitions (inside component for translations)
  const TABS = [
    { id: 'pending', label: t('common.pending'), icon: Warning },
    { id: 'history', label: t('common.history'), icon: ClockCounterClockwise }
  ]
  
  // Tab state
  const [activeTab, setActiveTab] = useState(searchParams.get('tab') || 'pending')
  
  // Data state. The API pages both lists: only the active tab's current page
  // is held here, and the counts come from the server's totals
  const [rows, setRows] = useState([])
  const [listTotal, setListTotal] = useState(0) // rows matching the search, active tab
  const [pendingTotal, setPendingTotal] = useState(0)
  const [historyTotal, setHistoryTotal] = useState(0)
  // What the search box shows, and the term actually sent (debounced)
  const [searchInput, setSearchInput] = useState('')
  const [searchValue, setSearchValue] = useState('')
  // Server-side sort; null = the API's default, newest first
  const [sort, setSort] = useState(null)
  const [loading, setLoading] = useState(true)
  const [cas, setCAs] = useState([])
  
  // Selection & modals
  const [selectedCSR, setSelectedCSR] = useState(null)
  const [showImportModal, setShowImportModal] = useState(false)
  const [signCA, setSignCA] = useState('')
  const [signCertType, setSignCertType] = useState('server')
  const [signExtraEkus, setSignExtraEkus] = useState([])
  // Names added to the request's own at signing (#389)
  const [signSans, setSignSans] = useState([])
  const [knownEkus, setKnownEkus] = useState([])
  useEffect(() => {
    let cancelled = false
    ekuService.getKnown()
      .then((resp) => { if (!cancelled) setKnownEkus(resp?.data?.ekus || resp?.ekus || []) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])
  const EKU_DEFAULTS_BY_TYPE = {
    server: ['1.3.6.1.5.5.7.3.1'],
    client: ['1.3.6.1.5.5.7.3.2'],
    combined: ['1.3.6.1.5.5.7.3.1', '1.3.6.1.5.5.7.3.2'],
    intermediate_ca: [],
    code_signing: ['1.3.6.1.5.5.7.3.3'],
    email: ['1.3.6.1.5.5.7.3.4'],
  }
  const [validityDays, setValidityDays] = useState(VALIDITY.DEFAULT_DAYS)
  const [signMode, setSignMode] = useState('local') // 'local' or 'msca'
  const [mscaConnections, setMscaConnections] = useState([])
  const [selectedMsca, setSelectedMsca] = useState('')
  const [mscaTemplates, setMscaTemplates] = useState([])
  const [selectedTemplate, setSelectedTemplate] = useState('')
  const [loadingTemplates, setLoadingTemplates] = useState(false)
  const [eoboEnabled, setEoboEnabled] = useState(false)
  const [enrolleeName, setEnrolleeName] = useState('')
  const [enrolleeUpn, setEnrolleeUpn] = useState('')
  
  // Generate CSR form state
  const [genCN, setGenCN] = useState('')
  const [genOrg, setGenOrg] = useState('')
  const [genOU, setGenOU] = useState('')
  const [genCountry, setGenCountry] = useState('')
  const [genState, setGenState] = useState('')
  const [genLocality, setGenLocality] = useState('')
  const [genKeyType, setGenKeyType] = useState('RSA 2048')
  const fips = useFipsMode()
  const [genSans, setGenSans] = useState([{ type: 'DNS', value: '' }])
  const [generating, setGenerating] = useState(false)
  
  // Upload modal
  const [uploadMode, setUploadMode] = useState('file') // 'file' or 'paste'
  const [pastedPEM, setPastedPEM] = useState('')
  
  // Key upload modal
  const [showKeyModal, setShowKeyModal] = useState(false)
  const [keyPem, setKeyPem] = useState('')
  const [keyPassphrase, setKeyPassphrase] = useState('')

  // Re-key modal
  const [showRekeyChoice, setShowRekeyChoice] = useState(false)
  const [rekeyCSR, setRekeyCSR] = useState(null)

  // Handle tab change
  const handleTabChange = (tabId) => {
    if (tabId !== activeTab) {
      // The other tab's rows must not show under this tab's columns
      setRows([])
      setListTotal(0)
      setSearchInput('')
      setSearchValue('')
      setLoading(true)
    }
    setActiveTab(tabId)
    setSelectedCSR(null)
    setPage(1)
    setSearchParams({ tab: tabId })
  }

  // Pagination state
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)

  useEffect(() => {
    loadAux()
    if (searchParams.get('action') === 'upload') {
      openModal('upload')
      searchParams.delete('action')
      setSearchParams(searchParams)
    }
  }, [])

  // The active tab's page, plus both tabs' unfiltered totals for the counts.
  // A reload started earlier must not overwrite a later one (page or search
  // changed while an action's reload was in flight)
  const listSeq = useRef(0)
  // Read through refs: the loader must change only when the query does, not
  // whenever a caller hands in a new function identity
  const showErrorRef = useRef(showError)
  showErrorRef.current = showError
  const tRef = useRef(t)
  tRef.current = t
  const loadLists = useCallback(async () => {
    const seq = ++listSeq.current
    const fetchPending = (params) => csrsService.getAll(params)
    const fetchHistory = (params) => csrsService.getHistory(params)
    const isPending = activeTab === 'pending'
    const fetchActive = isPending ? fetchPending : fetchHistory
    const fetchOther = isPending ? fetchHistory : fetchPending
    const params = { page, per_page: perPage }
    if (searchValue) params.search = searchValue
    if (sort) {
      params.sort_by = sort.key
      params.sort_order = sort.direction
    }
    const totalOf = (res) => res?.meta?.total ?? (res?.data || []).length
    try {
      setLoading(true)
      const [activeRes, otherRes, activeAllRes] = await Promise.all([
        fetchActive(params),
        fetchOther({ page: 1, per_page: 1 }),
        // While searching, the active page's total is the filtered one
        searchValue ? fetchActive({ page: 1, per_page: 1 }) : null,
      ])
      if (seq !== listSeq.current) return
      const filteredTotal = totalOf(activeRes)
      const activeAll = activeAllRes ? totalOf(activeAllRes) : filteredTotal
      const otherAll = totalOf(otherRes)
      setRows(activeRes.data || [])
      setListTotal(filteredTotal)
      setPendingTotal(isPending ? activeAll : otherAll)
      setHistoryTotal(isPending ? otherAll : activeAll)
      // The last row of the last page went away: stay on a page that exists
      const lastPage = Math.max(1, Math.ceil(filteredTotal / perPage))
      if (page > lastPage) setPage(lastPage)
    } catch (error) {
      if (seq !== listSeq.current) return
      showErrorRef.current(error.message || tRef.current('messages.errors.loadFailed.csrs'))
    } finally {
      if (seq === listSeq.current) setLoading(false)
    }
  }, [activeTab, page, perPage, searchValue, sort])

  useEffect(() => {
    loadLists()
  }, [loadLists])

  // Send the search once typing pauses, not on every keystroke
  useEffect(() => {
    const term = searchInput.trim()
    if (term === searchValue) return
    const timer = setTimeout(() => {
      setSearchValue(term)
      setPage(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [searchInput, searchValue])

  const handleSortChange = useCallback((newSort) => {
    setSort(newSort ? { key: newSort.key, direction: newSort.direction } : null)
    setPage(1)
  }, [])

  // CAs and MS CA connections for the sign dialog
  const loadAux = async () => {
    try {
      const [casRes, mscaRes] = await Promise.all([
        casService.getAll(),
        mscaService.getEnabled().catch(() => ({ data: [] }))
      ])
      setCAs(casRes.data || casRes.cas || [])
      setMscaConnections(mscaRes.data || [])
    } catch (error) {
      showError(error.message || t('messages.errors.loadFailed.csrs'))
    }
  }

  const loadData = () => Promise.all([loadLists(), loadAux()])

  // Reload when the change was made elsewhere. The loader is read through a
  // ref so the listener never holds the filters of the moment it registered.
  const loadDataRef = useRef(loadData)
  loadDataRef.current = loadData
  useEffect(() => {
    const handler = (e) => {
      if (e.detail?.type === 'certificate') loadDataRef.current()
    }
    window.addEventListener('ucm:data-changed', handler)
    return () => window.removeEventListener('ucm:data-changed', handler)
  }, [])

  const loadCSRDetails = async (csr) => {
    try {
      const response = await csrsService.getById(csr.id)
      const data = extractData(response)
      setSelectedCSR({ ...data, ...csr }) // Merge to keep signed_by info
    } catch {
      setSelectedCSR(csr)
    }
  }

  // A new request lands in the pending tab: show it there
  const openCreatedCSR = (response) => {
    const csr = extractData(response)
    if (!csr?.id) return
    handleTabChange('pending')
    loadCSRDetails(csr)
  }

  const handleUpload = async (files) => {
    try {
      const file = files[0]
      const text = await file.text()
      const created = await csrsService.upload(text)
      showSuccess(t('messages.success.create.csr'))
      closeModal('upload')
      loadData()
      openCreatedCSR(created)
    } catch (error) {
      showError(error.message || t('csrs.uploadFailed'))
    }
  }

  const handlePasteUpload = async () => {
    if (!pastedPEM.trim()) {
      showError(t('csrs.csrPEMError'))
      return
    }
    if (!pastedPEM.includes('-----BEGIN') || !pastedPEM.includes('REQUEST')) {
      showError(t('csrs.invalidCSRFormat'))
      return
    }
    try {
      const created = await csrsService.upload(pastedPEM.trim())
      showSuccess(t('messages.success.create.csr'))
      closeModal('upload')
      setPastedPEM('')
      setUploadMode('file')
      loadData()
      openCreatedCSR(created)
    } catch (error) {
      showError(error.message || t('csrs.uploadFailed'))
    }
  }

  // Added names belong to one signing: another request starts without them
  useEffect(() => { setSignSans([]) }, [selectedCSR?.id])

  // A device that keeps its key often cannot produce its request twice (#389)
  const handleSignAgain = async (row) => {
    try {
      const created = await csrsService.resubmit(row.id)
      showSuccess(t('csrs.signAgainDone'))
      loadData()
      openCreatedCSR(created)
    } catch (error) {
      showError(error.message || t('csrs.signAgainFailed'))
    }
  }

  const handleSign = async () => {
    if (signMode === 'local') {
      if (!signCA) {
        showError(t('common.selectCA'))
        return
      }
      const addedSans = signCertType === 'intermediate_ca' ? [] : signSans
      const sanError = addedSans
        .map(s => getSanValidationError(s.type, s.value))
        .find(Boolean)
      if (sanError) {
        showError(t(sanError.key, sanError.params))
        return
      }
      try {
        const signed = await csrsService.sign(
          selectedCSR.id, signCA, validityDays, signCertType, signExtraEkus, sanRowsToPayload(addedSans))
        setSignSans([])
        if (signed?.data?.approval_required) {
          // An issuance policy queued the signing for approval
          showWarning(t('certificates.approvalRequired', { policy: signed.data.policy_name }))
          showNotices(signed, showWarning)
          closeModal('sign')
          loadData()
          setSelectedCSR(null)
          return
        }
        showSuccess(t('messages.success.other.signed'))
        showNotices(signed, showWarning)
        // A CA signed from an external request holds no key (#348)
        if ((signed?.data || signed)?.certificate_only) showWarning(t('cas.certificateOnlyBanner'))
        closeModal('sign')
        loadData()
        setSelectedCSR(null)
        // Signing as an intermediate CA creates a CA, not a certificate
        const result = signed?.data
        openEntity(signCertType === 'intermediate_ca' ? 'ca' : 'certificate', result?.id)
      } catch (error) {
        showError(error.message || t('csrs.signFailed'))
      }
    } else {
      // MS CA signing
      if (!selectedMsca) {
        showError(t('msca.selectConnection'))
        return
      }
      if (!selectedTemplate) {
        showError(t('msca.selectTemplate'))
        return
      }
      if (eoboEnabled && !enrolleeUpn?.trim()) {
        showError(t('msca.eobo.upnRequired'))
        return
      }
      try {
        const signData = { template: selectedTemplate }
        if (eoboEnabled) {
          if (enrolleeName) signData.enrollee_name = enrolleeName
          if (enrolleeUpn) signData.enrollee_upn = enrolleeUpn
        }
        const result = await mscaService.signCSR(selectedMsca, selectedCSR.id, signData)
        const csrId = selectedCSR.id
        if (result.data?.status === 'issued') {
          showSuccess(t('messages.success.other.signed'))
        } else if (result.data?.status === 'pending') {
          showSuccess(t('msca.pendingMessage'))
        }
        closeModal('sign')
        loadData()
        setSelectedCSR(null)
        // The issued certificate is stored on the request's own row
        if (result.data?.status === 'issued') openEntity('certificate', csrId)
      } catch (error) {
        showError(error.message || t('csrs.signFailed'))
      }
    }
  }

  const handleMscaConnectionChange = async (mscaId) => {
    setSelectedMsca(mscaId)
    setSelectedTemplate('')
    setMscaTemplates([])
    if (!mscaId) return
    setLoadingTemplates(true)
    try {
      const response = await mscaService.getTemplates(mscaId)
      setMscaTemplates(response.data || [])
      const conn = mscaConnections.find(c => String(c.id) === String(mscaId))
      if (conn?.default_template) {
        setSelectedTemplate(conn.default_template)
      }
    } catch (error) {
      showError(error.message || t('msca.testFailed'))
    } finally {
      setLoadingTemplates(false)
    }
  }

  const handleGenerate = async () => {
    if (!genCN.trim()) {
      showError(t('certificates.cnRequired'))
      return
    }
    const sanError = genSans
      .map((s) => getSanValidationError(s.type, s.value))
      .find(Boolean)
    if (sanError) {
      showError(t(sanError.key, sanError.params))
      return
    }
    setGenerating(true)
    try {
      const sans = genSans.filter(s => s.value.trim()).map(s => `${s.type}:${s.value.trim()}`)
      const created = await csrsService.create({
        cn: genCN.trim(),
        organization: genOrg.trim() || undefined,
        department: genOU.trim() || undefined,
        country: genCountry.trim() || undefined,
        state: genState.trim() || undefined,
        locality: genLocality.trim() || undefined,
        key_type: genKeyType,
        sans
      })
      showSuccess(t('messages.success.create.csr'))
      closeModal('generate')
      resetGenerateForm()
      loadData()
      openCreatedCSR(created)
    } catch (error) {
      showError(error.message || t('csrs.generateFailed'))
    } finally {
      setGenerating(false)
    }
  }

  const resetGenerateForm = () => {
    setGenCN(''); setGenOrg(''); setGenOU(''); setGenCountry('')
    setGenState(''); setGenLocality(''); setGenKeyType('RSA 2048')
    setGenSans([{ type: 'DNS', value: '' }])
  }

  const handleDelete = async (id) => {
    const confirmed = await showConfirm(t('messages.confirm.delete.csr'), {
      title: t('csrs.deleteCSR'),
      confirmText: t('common.delete'),
      variant: 'danger'
    })
    if (!confirmed) return
    try {
      await csrsService.delete(id)
      showSuccess(t('messages.success.delete.csr'))
      loadData()
      setSelectedCSR(null)
    } catch (error) {
      showError(error.message || t('csrs.deleteFailed'))
    }
  }

  const handleUploadKey = async () => {
    if (!keyPem.trim()) {
      showError(t('csrs.provideKey'))
      return
    }
    if (!keyPem.includes('PRIVATE KEY')) {
      showError(t('csrs.invalidKeyFormat'))
      return
    }
    try {
      await csrsService.uploadKey(selectedCSR.id, keyPem.trim(), keyPassphrase || null)
      showSuccess(t('messages.success.other.keyUploaded'))
      setShowKeyModal(false)
      setKeyPem('')
      setKeyPassphrase('')
      // Refresh selected CSR first, then background-refresh list
      const updated = await csrsService.getById(selectedCSR.id)
      setSelectedCSR(updated.data || updated)
      loadData()
    } catch (error) {
      showError(error.message || t('csrs.keyUploadFailed'))
    }
  }

  const handleDownload = async (id, filename) => {
    try {
      const blob = await csrsService.download(id)
      downloadBlob(blob, filename || 'csr.pem')
      showSuccess(t('common.downloadSuccess'))
    } catch (error) {
      showError(error.message || t('csrs.downloadFailed'))
    }
  }

  // The key of a CSR awaiting an external CA: needed next to the certificate
  // that CA returns (#341)
  // A signed request's row holds both: its certificate comes from the
  // certificate export, the CSR route only ever returns the request.
  const handleDownloadCertificate = async (row) => {
    try {
      const blob = await certificatesService.export(row.id, 'pem')
      downloadBlob(blob, `${row.cn || 'cert'}.crt`)
      showSuccess(t('common.downloadSuccess'))
    } catch (error) {
      showError(error.message || t('csrs.downloadFailed'))
    }
  }

  const handleDownloadKey = async (row) => {
    try {
      const blob = await csrsService.downloadKey(row.id)
      downloadBlob(blob, `${row.cn || 'csr'}.key`)
      showSuccess(t('common.downloadSuccess'))
    } catch (error) {
      showError(error.message || t('csrs.downloadFailed'))
    }
  }

  // Re-key: extract CSR fields to pre-fill form
  const parseSansFromCSR = (csr) => {
    const sans = []
    const parseSanField = (field, type) => {
      if (!field) return
      let arr
      try {
        arr = typeof field === 'string' ? JSON.parse(field) : field
      } catch {
        return // skip malformed SAN field
      }
      if (Array.isArray(arr)) arr.forEach(v => v && sans.push({ type, value: v }))
    }
    parseSanField(csr.san_dns, 'DNS')
    parseSanField(csr.san_ip, 'IP')
    parseSanField(csr.san_email, 'Email')
    parseSanField(csr.san_uri, 'URI')
    parseSanField(csr.san_upn, 'UPN')
    return sans.length > 0 ? sans : [{ type: 'DNS', value: '' }]
  }

  const mapKeyType = (csr) => {
    const algo = (csr.key_algorithm || '').toUpperCase()
    const size = csr.key_size
    if (algo === 'EC' || algo === 'ECDSA') return `EC P-${size || 256}`
    return `RSA ${size || 2048}`
  }

  const handleRekeyAsCSR = (csr) => {
    setGenCN(csr.common_name || csr.cn || '')
    setGenOrg(csr.organization || '')
    setGenOU(csr.organizational_unit || '')
    setGenCountry(csr.country || '')
    setGenState(csr.state || '')
    setGenLocality(csr.locality || '')
    setGenKeyType(mapKeyType(csr))
    setGenSans(parseSansFromCSR(csr))
    setShowRekeyChoice(false)
    openModal('generate')
  }

  const handleRekeyAsCert = (csr) => {
    const algo = (csr.key_algorithm || '').toUpperCase()
    const size = csr.key_size
    const prefill = {
      cn: csr.common_name || csr.cn || '',
      organization: csr.organization || '',
      organizational_unit: csr.organizational_unit || '',
      country: csr.country || '',
      state: csr.state || '',
      locality: csr.locality || '',
      email: csr.email || '',
      key_type: (algo === 'EC' || algo === 'ECDSA') ? 'ecdsa' : 'rsa',
      key_size: String(size || 2048),
      sans: parseSansFromCSR(csr).filter(s => s.value).map(s => ({ type: s.type.toLowerCase(), value: s.value })),
    }
    setShowRekeyChoice(false)
    navigate('/certificates', { state: { prefill, source: 'rekey' } })
  }

  const handleRekey = (csr) => {
    setRekeyCSR(csr)
    setShowRekeyChoice(true)
  }

  // Current data: the active tab's page, as the API returned it
  const currentData = rows

  // Stats
  const stats = useMemo(() => [
    { icon: Warning, label: t('common.pending'), value: pendingTotal, variant: 'warning' },
    { icon: CheckCircle, label: t('csrs.signed'), value: historyTotal, variant: 'success' },
    { icon: FileText, label: t('common.total'), value: pendingTotal + historyTotal, variant: 'primary' }
  ], [pendingTotal, historyTotal, t])

  // Pending table columns
  const pendingColumns = useMemo(() => [
    {
      key: 'cn',
      header: t('common.commonName'),
      priority: 1,
      render: (val, row) => (
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg flex items-center justify-center shrink-0 icon-bg-orange">
            <FileText size={14} weight="duotone" />
          </div>
          <span className="font-medium truncate">{row.common_name || row.cn || val || t('common.unnamed')}</span>
          <KeyIndicator hasKey={row.has_private_key} size={14} />
        </div>
      ),
      mobileRender: (val, row) => (
        <div className="flex items-center justify-between gap-2 w-full">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <div className="w-6 h-6 rounded-lg flex items-center justify-center shrink-0 icon-bg-orange">
              <FileText size={14} weight="duotone" />
            </div>
            <span className="font-medium truncate">{row.common_name || row.cn || val || t('common.unnamed')}</span>
            <KeyIndicator hasKey={row.has_private_key} size={12} />
          </div>
          <Badge variant="warning" size="sm" dot>{t('common.pending')}</Badge>
        </div>
      )
    },
    {
      key: 'organization',
      header: t('common.organization'),
      sortable: false, // not a stored column: the server cannot order by it
      priority: 3,
      hideOnMobile: true,
      render: (val) => <span className="text-sm text-text-secondary">{val || '—'}</span>
    },
    {
      key: 'created_at',
      header: t('common.created'),
      priority: 2,
      render: (val) => (
        <span className="text-xs text-text-secondary whitespace-nowrap">
          {formatDate(val, 'short')}
        </span>
      )
    },
    {
      key: 'key_type',
      header: t('common.key'),
      sortable: false, // key_algo is only stored once the request is signed
      priority: 4,
      hideOnMobile: true,
      render: (val, row) => (
        <span className="text-xs font-mono text-text-secondary">
          {keyAlgorithmLabel(row.key_algorithm, t, row.security_level) || '—'} {row.key_size ? `(${row.key_size})` : ''}
        </span>
      )
    }
  ], [t])

  // History table columns
  const historyColumns = useMemo(() => [
    {
      key: 'cn',
      header: t('common.commonName'),
      priority: 1,
      render: (val, row) => (
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg flex items-center justify-center shrink-0 icon-bg-emerald">
            <Certificate size={14} weight="duotone" />
          </div>
          <span className="font-medium truncate">{row.common_name || row.cn || val || t('common.unnamed')}</span>
          <KeyIndicator hasKey={row.has_private_key} size={14} />
          {row.source === 'acme' && (
            <Badge variant="info" size="sm">ACME</Badge>
          )}
          {row.source === 'scep' && (
            <Badge variant="purple" size="sm">SCEP</Badge>
          )}
        </div>
      ),
      mobileRender: (val, row) => (
        <div className="flex items-center justify-between gap-2 w-full">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <div className="w-6 h-6 rounded-lg flex items-center justify-center shrink-0 icon-bg-emerald">
              <Certificate size={14} weight="duotone" />
            </div>
            <span className="font-medium truncate">{row.common_name || row.cn || val || t('common.unnamed')}</span>
            <KeyIndicator hasKey={row.has_private_key} size={12} />
          </div>
          <Badge variant="success" size="sm" dot>{t('csrs.signed')}</Badge>
        </div>
      )
    },
    {
      key: 'signed_by',
      header: t('common.signedBy'),
      sortable: false, // resolved from the CA table per row
      priority: 2,
      hideOnMobile: true,
      render: (val, row) => (
        <div className="flex items-center gap-2">
          <Stamp size={14} className="text-accent-primary" />
          <span className="text-sm text-text-primary truncate">{val || row.issuer_name || '—'}</span>
        </div>
      ),
      mobileRender: (val, row) => (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-text-tertiary">CA:</span>
          <span className="text-text-secondary truncate">{val || row.issuer_name || '—'}</span>
        </div>
      )
    },
    {
      key: 'signed_at',
      header: t('csrs.signed'),
      priority: 3,
      render: (val, row) => (
        <span className="text-xs text-text-secondary whitespace-nowrap">
          {formatDate(val || row.valid_from, 'short')}
        </span>
      )
    },
    {
      key: 'valid_to',
      header: t('common.expires'),
      priority: 4,
      hideOnMobile: true,
      render: (val, row) => {
        const days = row.days_remaining
        if (!hasExpiry(days)) return <span className="text-text-tertiary">—</span>
        return (
          <Badge variant={expiryVariant(days)} size="sm">
            {days <= 0
              ? t('details.expiredDaysAgo', { count: daysSinceExpiry(days) })
              : t('csrs.daysRemaining', { days })}
          </Badge>
        )
      }
    }
  ], [t])

  // Row actions for pending
  const pendingRowActions = useCallback((row) => [
    { label: t('csrs.downloadCSR'), icon: Download, onClick: () => handleDownload(row.id, `${row.cn || 'csr'}.csr`) },
    ...(canExportKey && row.has_private_key ? [
      { label: t('csrs.downloadKey'), icon: Key, onClick: () => handleDownloadKey(row) }
    ] : []),
    ...(canWrite('csrs') ? [
      { label: t('csrs.sign'), icon: SignIn, onClick: () => { setSelectedCSR(row); openModal('sign') }},
      { label: t('csrs.rekey'), icon: ArrowsClockwise, onClick: () => handleRekey(row) }
    ] : []),
    ...(canDelete('csrs') ? [
      { label: t('common.delete'), icon: Trash, variant: 'danger', onClick: () => handleDelete(row.id) }
    ] : [])
  ], [canWrite, canDelete, canExportKey, t])

  // Row actions for history
  const historyRowActions = useCallback((row) => [
    ...(canReadCertificates ? [
      { label: t('common.downloadCertificate'), icon: Download, onClick: () => handleDownloadCertificate(row) }
    ] : []),
    { label: t('csrs.downloadCSR'), icon: FileText, onClick: () => handleDownload(row.id, `${row.cn || 'csr'}.csr`) },
    { label: t('common.viewInCertificates'), icon: Certificate, onClick: () => navigate(`/certificates?id=${row.id}`) },
    ...(canWrite('csrs') && canReadCertificates ? [
      { label: t('csrs.signAgain'), icon: SignIn, onClick: () => handleSignAgain(row) }
    ] : []),
    ...(canWrite('csrs') ? [
      { label: t('csrs.rekey'), icon: ArrowsClockwise, onClick: () => handleRekey(row) }
    ] : [])
  ], [canWrite, canReadCertificates, t])

  // Help content
  const helpContent = (
    <div className="space-y-4">
      {/* Quick Stats */}
      <div className="visual-section">
        <div className="visual-section-header">
          <FileText size={16} className="status-primary-text" />
          {t('csrs.csrStatistics')}
        </div>
        <div className="visual-section-body">
          <div className="quick-info-grid">
            <div className="help-stat-card">
              <div className="help-stat-value help-stat-value-warning">{pendingTotal}</div>
              <div className="help-stat-label">{t('common.pending')}</div>
            </div>
            <div className="help-stat-card">
              <div className="help-stat-value help-stat-value-success">{historyTotal}</div>
              <div className="help-stat-label">{t('csrs.signed')}</div>
            </div>
            <div className="help-stat-card">
              <div className="help-stat-value help-stat-value-primary">{pendingTotal + historyTotal}</div>
              <div className="help-stat-label">{t('common.total')}</div>
            </div>
          </div>
        </div>
      </div>

      <HelpCard title={t('common.aboutCSRs')} variant="info">
        {t('csrs.aboutCSRsDescription')}
      </HelpCard>
      <HelpCard title={t('common.status')} variant="info">
        <div className="space-y-1.5 mt-2">
          <div className="flex items-center gap-2">
            <Badge variant="warning" size="sm" dot>{t('common.pending')}</Badge>
            <span className="text-xs">{t('csrs.pendingDescription')}</span>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="success" size="sm" dot>{t('csrs.signed')}</Badge>
            <span className="text-xs">{t('csrs.signedDescription')}</span>
          </div>
        </div>
      </HelpCard>
      <HelpCard title={t('csrs.workflow')} variant="tip">
        {t('csrs.workflowSteps')}
      </HelpCard>
    </div>
  )

  // Tabs with counts
  const tabsWithCounts = TABS.map(tab => ({
    ...tab,
    count: tab.id === 'pending' ? pendingTotal : historyTotal
  }))

  return (
    <>
      <ResponsiveLayout
        title={t('common.csrs')}
        subtitle={t('csrs.pendingSubtitle', { pending: pendingTotal, signed: historyTotal })}
        icon={FileText}
        stats={stats}
        helpPageKey="csrs"
        tabs={tabsWithCounts}
        activeTab={activeTab}
        onTabChange={handleTabChange}
        tabLayout="sidebar"
        splitView={true}
        splitEmptyContent={
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="w-14 h-14 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
              <FileText size={24} className="text-text-tertiary" />
            </div>
            <p className="text-sm text-text-secondary">{t('csrs.selectCSR')}</p>
          </div>
        }
        slideOverOpen={!!selectedCSR}
        onSlideOverClose={() => setSelectedCSR(null)}
        slideOverTitle={activeTab === 'pending' ? t('common.csrDetails') : t('common.certificateDetails')}
        slideOverContent={selectedCSR && (
          activeTab === 'pending' ? (
            <CSRDetailsPanel 
              csr={selectedCSR}
              canWrite={canWrite}
              canDelete={canDelete}
              onSign={() => openModal('sign')}
              onDownload={() => handleDownload(selectedCSR.id, `${selectedCSR.cn || 'csr'}.csr`)}
              onDownloadKey={canExportKey && selectedCSR.has_private_key ? () => handleDownloadKey(selectedCSR) : undefined}
              onDelete={() => handleDelete(selectedCSR.id)}
              onUploadKey={() => setShowKeyModal(true)}
              onRekey={canWrite('csrs') ? () => handleRekey(selectedCSR) : undefined}
              t={t}
            />
          ) : (
            <SignedCSRDetailsPanel 
              cert={selectedCSR}
              onDownload={canReadCertificates ? () => handleDownloadCertificate(selectedCSR) : undefined}
              onDownloadCSR={() => handleDownload(selectedCSR.id, `${selectedCSR.cn || 'csr'}.csr`)}
              onSignAgain={canWrite('csrs') && canReadCertificates ? () => handleSignAgain(selectedCSR) : undefined}
              onRekey={canWrite('csrs') ? () => handleRekey(selectedCSR) : undefined}
              t={t}
            />
          )
        )}
      >
        <ResponsiveDataTable
          data={currentData.map(item => ({
            ...item,
            cn: item.common_name || item.cn || item.subject || t('common.unnamed')
          }))}
          columns={activeTab === 'pending' ? pendingColumns : historyColumns}
          loading={loading}
          selectedId={selectedCSR?.id}
          onRowClick={(item) => item ? loadCSRDetails(item) : setSelectedCSR(null)}
          searchable
          searchPlaceholder={activeTab === 'pending' ? t('csrs.searchPending') : t('csrs.searchSigned')}
          // Searched server-side across every page: no searchKeys, so the
          // table does not filter the returned page a second time
          externalSearch={searchInput}
          onSearchChange={setSearchInput}
          columnStorageKey={`ucm-csrs-${activeTab}-columns`}
          densityStorageKey="ucm-csrs-density"
          toolbarActions={activeTab === 'pending' && canWrite('csrs') && (
            isMobile ? (
              <div className="flex gap-2">
                <Button type="button" size="lg" onClick={() => openModal('generate')} className="w-11 h-11 p-0">
                  <Plus size={22} weight="bold" />
                </Button>
                <Button type="button" size="lg" variant="secondary" onClick={() => setShowImportModal(true)} className="w-11 h-11 p-0">
                  <UploadSimple size={22} weight="bold" />
                </Button>
              </div>
            ) : (
              <div className="flex gap-2">
                <Button type="button" size="sm" onClick={() => openModal('generate')}>
                  <Plus size={14} weight="bold" />
                  {t('csrs.generateCSR')}
                </Button>
                <Button type="button" size="sm" variant="secondary" onClick={() => setShowImportModal(true)}>
                  <UploadSimple size={14} weight="bold" />
                  {t('common.import')}
                </Button>
              </div>
            )
          )}
          sortable
          onSortChange={handleSortChange}
          pagination={{
            page,
            total: listTotal,
            perPage,
            onChange: setPage,
            onPerPageChange: (v) => { setPerPage(v); setPage(1) },
          }}
          emptyIcon={activeTab === 'pending' ? Warning : CheckCircle}
          emptyTitle={activeTab === 'pending' ? t('csrs.noPendingCSRs') : t('csrs.noSignedCertificates')}
          emptyDescription={activeTab === 'pending' 
            ? t('csrs.uploadToStart') 
            : t('csrs.signToSee')}
          emptyAction={activeTab === 'pending' && canWrite('csrs') && (
            <Button type="button" onClick={() => setShowImportModal(true)}>
              <UploadSimple size={16} /> {t('csrs.importCSR')}
            </Button>
          )}
        />
      </ResponsiveLayout>

      {/* Upload CSR Modal */}
      <Modal
        open={modals.upload}
        onOpenChange={() => { closeModal('upload'); setPastedPEM(''); setUploadMode('file') }}
        title={t('csrs.uploadCSR')}
      >
        <div className="p-4 space-y-4">
          {/* Mode tabs */}
          <div className="flex gap-1 p-1 bg-bg-tertiary rounded-lg">
            <button
              onClick={() => setUploadMode('file')}
              className={cn(
                "flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                uploadMode === 'file' 
                  ? "bg-bg-primary text-text-primary shadow-sm" 
                  : "text-text-secondary hover:text-text-primary"
              )}
            >
              <UploadSimple size={16} /> {t('common.uploadFile')}
            </button>
            <button
              onClick={() => setUploadMode('paste')}
              className={cn(
                "flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                uploadMode === 'paste' 
                  ? "bg-bg-primary text-text-primary shadow-sm" 
                  : "text-text-secondary hover:text-text-primary"
              )}
            >
              <ClipboardText size={16} /> {t('csrs.pastePEM')}
            </button>
          </div>

          {uploadMode === 'file' ? (
            <>
              <p className="text-sm text-text-secondary">
                {t('csrs.uploadCSRDescription')}
              </p>
              <FileUpload
                accept=".pem,.csr"
                onUpload={handleUpload}
                maxSize={1024 * 1024}
              />
            </>
          ) : (
            <>
              <p className="text-sm text-text-secondary">
                {t('csrs.pasteCSRDescription')}
              </p>
              <Textarea
                value={pastedPEM}
                onChange={(e) => setPastedPEM(e.target.value)}
                placeholder="-----BEGIN CERTIFICATE REQUEST-----
MIICijCCAXICAQAwRTELMAkGA1UEBhMCVVMx...
-----END CERTIFICATE REQUEST-----"
                rows={10}
                className="font-mono text-xs"
              />
              <div className="flex justify-end gap-2 pt-2 border-t border-border">
                <Button type="button" variant="secondary" onClick={() => { closeModal('upload'); setPastedPEM('') }}>
                  {t('common.cancel')}
                </Button>
                <Button type="button" onClick={handlePasteUpload} disabled={!pastedPEM.trim()}>
                  <UploadSimple size={16} /> {t('common.upload')}
                </Button>
              </div>
            </>
          )}
        </div>
      </Modal>

      {/* Sign CSR Modal */}
      <Modal
        open={modals.sign}
        onOpenChange={() => { closeModal('sign'); setSignMode('local'); setSelectedMsca(''); setSelectedTemplate(''); setEoboEnabled(false); setEnrolleeName(''); setEnrolleeUpn('') }}
        title={t('common.signCSR')}
      >
        <div className="p-4 space-y-4">
          <p className="text-sm text-text-secondary">
            {t('csrs.signCSRDescription')}
          </p>

          {/* Mode toggle — only show if MS CA connections exist */}
          {mscaConnections.length > 0 && (
            <div className="flex gap-1 p-1 bg-tertiary-50 rounded-lg">
              <button
                type="button"
                className={`flex-1 px-3 py-1.5 text-sm rounded-md transition-colors ${signMode === 'local' ? 'bg-bg-primary text-text-primary shadow-sm font-medium' : 'text-text-secondary hover:text-text-primary'}`}
                onClick={() => setSignMode('local')}
              >
                {t('msca.signLocal')}
              </button>
              <button
                type="button"
                className={`flex-1 px-3 py-1.5 text-sm rounded-md transition-colors ${signMode === 'msca' ? 'bg-bg-primary text-text-primary shadow-sm font-medium' : 'text-text-secondary hover:text-text-primary'}`}
                onClick={() => setSignMode('msca')}
              >
                {t('msca.signMicrosoft')}
              </button>
            </div>
          )}

          {signMode === 'local' ? (
            <>
              <Select
                label={t('common.certificateAuthority')}
                options={signingCas(cas).map(ca => ({ value: String(ca.id), label: ca.descr || ca.name || ca.common_name }))}
                value={signCA}
                onChange={setSignCA}
                placeholder={t('csrs.selectCA')}
                helperText={unlistedSigningCas(cas) > 0 ? t('cas.notListedForSigning', { count: unlistedSigningCas(cas) }) : undefined}
              />

              <Select
                label={t('csrs.certTypeForSign')}
                options={[
                  { value: 'server', label: t('certificates.certTypes.server') },
                  { value: 'client', label: t('certificates.certTypes.client') },
                  { value: 'combined', label: t('certificates.certTypes.combined') },
                  { value: 'intermediate_ca', label: t('certificates.certTypes.intermediateCA') },
                  { value: 'code_signing', label: t('certificates.certTypes.codeSigning') },
                  { value: 'email', label: t('certificates.certTypes.email') },
                ]}
                value={signCertType}
                onChange={setSignCertType}
              />

              <Input
                label={t('csrs.validityPeriod')}
                type="number"
                value={validityDays}
                onChange={(e) => setValidityDays(parseInt(e.target.value))}
                min="1"
                max="3650"
              />

              <EkuMultiSelect
                value={signExtraEkus}
                onChange={setSignExtraEkus}
                defaults={EKU_DEFAULTS_BY_TYPE[signCertType] || []}
                knownEkus={knownEkus}
              />

              {signCertType !== 'intermediate_ca' && (
                <div>
                  <label className="text-sm font-medium text-text-primary mb-1 block">
                    {t('csrs.signAddNames')}
                  </label>
                  <p className="text-xs text-text-secondary mb-2">{t('csrs.signAddNamesHelp')}</p>
                  <SanRows
                    rows={signSans}
                    onChange={setSignSans}
                    types={['Email', 'DNS', 'IP', 'URI']}
                    allowEmpty
                    t={t}
                  />
                </div>
              )}
            </>
          ) : (
            <>
              <Select
                label={t('msca.selectConnection')}
                options={mscaConnections.map(c => ({ value: String(c.id), label: `${c.name} (${c.server})` }))}
                value={selectedMsca}
                onChange={handleMscaConnectionChange}
                placeholder={t('msca.selectConnection')}
              />

              {selectedMsca && (
                <Select
                  label={t('msca.selectTemplate')}
                  options={mscaTemplates.map(t => ({ value: t, label: t }))}
                  value={selectedTemplate}
                  onChange={setSelectedTemplate}
                  placeholder={loadingTemplates ? t('msca.loadingTemplates') : t('msca.selectTemplate')}
                  disabled={loadingTemplates}
                />
              )}

              {selectedMsca && (
                <div className="space-y-3">
                  <label className="flex items-center gap-2 text-sm cursor-pointer">
                    <input
                      type="checkbox"
                      checked={eoboEnabled}
                      onChange={(e) => {
                        const enabled = e.target.checked
                        setEoboEnabled(enabled)
                        if (enabled && selectedCSR) {
                          if (!enrolleeName && selectedCSR.subject) {
                            setEnrolleeName(selectedCSR.subject)
                          }
                          if (!enrolleeUpn) {
                            // Priority 1: SAN UPN (Microsoft OID 1.3.6.1.4.1.311.20.2.3)
                            let foundUpn = ''
                            if (selectedCSR.san_upn) {
                              try {
                                const upns = typeof selectedCSR.san_upn === 'string'
                                  ? JSON.parse(selectedCSR.san_upn)
                                  : selectedCSR.san_upn
                                if (Array.isArray(upns) && upns.length > 0) {
                                  foundUpn = upns[0]
                                }
                              } catch { /* ignore parse errors */ }
                            }
                            // Priority 2: SAN email
                            if (!foundUpn && selectedCSR.san_email) {
                              try {
                                const emails = typeof selectedCSR.san_email === 'string'
                                  ? JSON.parse(selectedCSR.san_email)
                                  : selectedCSR.san_email
                                if (Array.isArray(emails) && emails.length > 0) {
                                  foundUpn = emails[0]
                                }
                              } catch { /* ignore parse errors */ }
                            }
                            // Priority 3: subject emailAddress
                            if (!foundUpn && selectedCSR.email) {
                              foundUpn = selectedCSR.email
                            }
                            if (foundUpn) {
                              setEnrolleeUpn(foundUpn)
                            }
                          }
                        }
                      }}
                      className="rounded border-border"
                    />
                    <span className="text-text-secondary">{t('msca.eobo.enable')}</span>
                  </label>

                  {eoboEnabled && (
                    <div className="space-y-3 pl-6 border-l-2 border-border">
                      <Input
                        label={t('msca.eobo.enrolleeName')}
                        value={enrolleeName}
                        onChange={(e) => setEnrolleeName(e.target.value)}
                        placeholder={t('msca.eobo.enrolleeNamePlaceholder')}
                      />
                      <Input
                        label={t('msca.eobo.enrolleeUpn')}
                        value={enrolleeUpn}
                        onChange={(e) => setEnrolleeUpn(e.target.value)}
                        placeholder={t('msca.eobo.enrolleeUpnPlaceholder')}
                        required
                      />
                      <p className="text-xs text-text-tertiary">
                        {t('msca.eobo.hint')}
                      </p>
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          <div className="flex justify-end gap-2 pt-4 border-t border-border">
            <Button type="button" variant="secondary" onClick={() => closeModal('sign')}>{t('common.cancel')}</Button>
            <Button
              type="button"
              onClick={handleSign}
              disabled={signMode === 'local' ? !signCA : (!selectedMsca || !selectedTemplate)}
            >
              <SignIn size={16} /> {t('common.signCSR')}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Generate CSR Modal */}
      <Modal
        open={modals.generate}
        onOpenChange={() => { closeModal('generate'); resetGenerateForm() }}
        title={t('csrs.generateCSR')}
        size="lg"
      >
        <div className="p-4 space-y-4">
          <p className="text-sm text-text-secondary">
            {t('csrs.generateDescription')}
          </p>

          {/* Common Name (required) */}
          <Input
            label={`${t('common.commonName')} *`}
            value={genCN}
            onChange={(e) => setGenCN(e.target.value)}
            placeholder="example.com"
          />

          {/* Key Type */}
          <Select
            label={t('common.keyType')}
            options={groupedOptions(listAlgorithms({ labels: CSR_LABELS, fips }), t,
              k => (k.csrKey ? t(k.csrKey) : k.display), k => k.csr)}
            value={genKeyType}
            onChange={setGenKeyType}
          />
          <BrainpoolNotice label={KEY_ALGORITHMS.find(k => k.csr === genKeyType)?.label} />

          {/* Subject Details */}
          <details className="group">
            <summary className="cursor-pointer text-sm font-medium text-text-primary flex items-center gap-1 py-1">
              <span className="transition-transform group-open:rotate-90">▶</span>
              {t('certificates.subjectDetails')}
            </summary>
            <div className="mt-3 grid grid-cols-2 gap-3">
              <Input
                label={t('common.country')}
                value={genCountry}
                onChange={(e) => setGenCountry(e.target.value)}
                placeholder="US"
                maxLength={2}
              />
              <Input
                label={t('common.state')}
                value={genState}
                onChange={(e) => setGenState(e.target.value)}
                placeholder={t('certificates.statePlaceholder')}
              />
              <Input
                label={t('common.locality')}
                value={genLocality}
                onChange={(e) => setGenLocality(e.target.value)}
                placeholder={t('certificates.localityPlaceholder')}
              />
              <Input
                label={t('common.organization')}
                value={genOrg}
                onChange={(e) => setGenOrg(e.target.value)}
                placeholder={t('certificates.orgPlaceholder')}
              />
              <Input
                label={t('csrs.department')}
                value={genOU}
                onChange={(e) => setGenOU(e.target.value)}
                placeholder={t('csrs.departmentPlaceholder')}
              />
            </div>
          </details>

          {/* SANs */}
          <div>
            <label className="text-sm font-medium text-text-primary mb-2 block">
              {t('csrs.sansList')}
            </label>
            <SanRows
              rows={genSans}
              onChange={setGenSans}
              types={['DNS', 'IP', 'Email', 'URI', 'UPN']}
              t={t}
            />
          </div>

          <div className="flex justify-end gap-2 pt-4 border-t border-border">
            <Button type="button" variant="secondary" onClick={() => { closeModal('generate'); resetGenerateForm() }}>
              {t('common.cancel')}
            </Button>
            <Button type="button" onClick={handleGenerate} disabled={!genCN.trim() || generating}>
              <Plus size={16} /> {generating ? t('common.generating') : t('csrs.generateCSR')}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Upload Private Key Modal */}
      <Modal
        open={showKeyModal}
        onOpenChange={() => { setShowKeyModal(false); setKeyPem(''); setKeyPassphrase('') }}
        title={t('csrs.uploadPrivateKey')}
      >
        <div className="p-4 space-y-4">
          <p className="text-sm text-text-secondary">
            {t('csrs.uploadPrivateKey')} <strong>{selectedCSR?.common_name || selectedCSR?.cn}</strong>
          </p>
          <Textarea
            label={t('common.privateKeyPEM')}
            value={keyPem}
            onChange={(e) => setKeyPem(e.target.value)}
            placeholder="-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQE...
-----END PRIVATE KEY-----"
            rows={8}
            className="font-mono text-xs"
          />
          <Input
            label={t('csrs.passphrase')}
            type="password"
            noAutofill
            value={keyPassphrase}
            onChange={(e) => setKeyPassphrase(e.target.value)}
            placeholder={t('csrs.passphraseHint')}
          />
          <div className="flex justify-end gap-2 pt-2 border-t border-border">
            <Button type="button" variant="secondary" onClick={() => { setShowKeyModal(false); setKeyPem(''); setKeyPassphrase('') }}>
              {t('common.cancel')}
            </Button>
            <Button type="button" onClick={handleUploadKey} disabled={!keyPem.trim()}>
              <UploadSimple size={16} /> {t('csrs.uploadKey')}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Smart Import Modal */}
      <SmartImportModal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        onImportComplete={(result) => {
          setShowImportModal(false)
          loadData()
          const sole = soleImported(result)
          if (sole?.type === 'csr') openCreatedCSR({ id: sole.id })
          else if (sole) openEntity(sole.type, sole.id)
        }}
      />

      {/* Re-key Choice Modal */}
      <Modal
        open={showRekeyChoice}
        onOpenChange={() => setShowRekeyChoice(false)}
        title={t('csrs.rekeyTitle')}
      >
        <div className="p-4 space-y-4">
          <p className="text-sm text-text-secondary">
            {t('csrs.rekeyDescription', { cn: rekeyCSR?.common_name || rekeyCSR?.cn || '' })}
          </p>
          <div className="grid grid-cols-1 gap-3">
            <button
              type="button"
              onClick={() => handleRekeyAsCSR(rekeyCSR)}
              className="flex items-start gap-3 p-4 rounded-lg border border-border hover:border-accent-primary hover:bg-accent-primary-op5 transition-colors text-left"
            >
              <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0 icon-bg-orange">
                <FileText size={20} weight="duotone" />
              </div>
              <div>
                <div className="font-medium text-sm text-text-primary">{t('csrs.rekeyAsCSR')}</div>
                <div className="text-xs text-text-secondary mt-0.5">{t('csrs.rekeyAsCSRDescription')}</div>
              </div>
            </button>
            {/* Issuing lands on the certificates page, which needs
                write:certificates: without it the navigation arrived and
                nothing opened. */}
            {canWrite('certificates') && (
              <button
                type="button"
                onClick={() => handleRekeyAsCert(rekeyCSR)}
                className="flex items-start gap-3 p-4 rounded-lg border border-border hover:border-accent-primary hover:bg-accent-primary-op5 transition-colors text-left"
              >
                <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0 icon-bg-emerald">
                  <Certificate size={20} weight="duotone" />
                </div>
                <div>
                  <div className="font-medium text-sm text-text-primary">{t('csrs.rekeyAsCert')}</div>
                  <div className="text-xs text-text-secondary mt-0.5">{t('csrs.rekeyAsCertDescription')}</div>
                </div>
              </button>
            )}
          </div>
          <div className="flex justify-end pt-2 border-t border-border">
            <Button type="button" variant="secondary" onClick={() => setShowRekeyChoice(false)}>
              {t('common.cancel')}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}

// =============================================================================
// CSR DETAILS PANEL (for pending CSRs)
// =============================================================================

const SAN_PLACEHOLDERS = {
  DNS: 'example.com', IP: '10.0.0.1', Email: 'admin@example.com',
  UPN: 'user@domain.local', URI: 'https://example.com',
}

// Typed SAN rows; without `allowEmpty` the last row cannot be removed.
function SanRows({ rows, onChange, types, allowEmpty = false, t }) {
  const update = (i, patch) => onChange(rows.map((row, j) => (j === i ? { ...row, ...patch } : row)))
  return (
    <div className="space-y-2">
      {rows.map((san, i) => (
        <div key={i} className="flex gap-2 items-center">
          <Select
            options={types.map(type => ({ value: type, label: type }))}
            value={san.type}
            onChange={(val) => update(i, { type: val })}
            className="w-24 shrink-0"
          />
          <Input
            value={san.value}
            onChange={(e) => update(i, { value: e.target.value })}
            placeholder={SAN_PLACEHOLDERS[san.type]}
            className="flex-1"
          />
          {(allowEmpty || rows.length > 1) && (
            <Button type="button" variant="ghost" size="sm" aria-label={t('common.remove')}
              onClick={() => onChange(rows.filter((_, j) => j !== i))}>
              <X size={14} />
            </Button>
          )}
        </div>
      ))}
      <Button type="button" variant="outline" size="sm"
        onClick={() => onChange([...rows, { type: types[0], value: '' }])}>
        <Plus size={14} /> {t('certificates.addSan')}
      </Button>
    </div>
  )
}

function CSRDetailsPanel({ csr, canWrite, canDelete, onSign, onDownload, onDownloadKey, onDelete, onUploadKey, onRekey, t }) {
  return (
    <div className="p-3 space-y-3">
      {/* Header */}
      <CompactHeader
        icon={FileText}
        iconClass="bg-accent-warning-op20"
        title={csr.common_name || csr.cn || t('csrs.unnamedCSR')}
        subtitle={csr.organization}
        badge={
          <div className="flex gap-1">
            <Badge variant="warning" size="sm" icon={Clock}>{t('common.pending')}</Badge>
            {csr.has_private_key && <Badge variant="success" size="sm" icon={Key}>{t('common.hasKey')}</Badge>}
            <PostQuantumBadge postQuantum={csr.post_quantum} algorithm={csr.key_algorithm} />
          </div>
        }
      />

      {/* Stats */}
      <CompactStats stats={[
        { icon: Clock, value: csr.created_at ? formatDate(csr.created_at, 'short') : '—' },
        { icon: Key, value: [keyAlgorithmLabel(csr.key_algorithm, t, csr.security_level) || '—', csr.key_size].filter(Boolean).join(' ') },
      ]} />

      {/* Actions */}
      <div className="flex gap-2 flex-wrap">
        <Button type="button" size="sm" variant="secondary" onClick={onDownload}>
          <Download size={14} /> {t('common.download')}
        </Button>
        {onDownloadKey && (
          <Button type="button" size="sm" variant="secondary" onClick={onDownloadKey}>
            <Key size={14} /> {t('csrs.downloadKey')}
          </Button>
        )}
        {canWrite('csrs') && !csr.has_private_key && (
          <Button type="button" size="sm" variant="secondary" onClick={onUploadKey}>
            <UploadSimple size={14} /> {t('csrs.uploadKey')}
          </Button>
        )}
        {canWrite('csrs') && (
          <Button type="button" size="sm" onClick={onSign}>
            <SignIn size={14} /> {t('csrs.sign')}
          </Button>
        )}
        {canWrite('csrs') && onRekey && (
          <Button type="button" size="sm" variant="secondary" onClick={onRekey}>
            <ArrowsClockwise size={14} /> {t('csrs.rekey')}
          </Button>
        )}
        {canDelete('csrs') && (
          <Button type="button" size="sm" variant="danger" onClick={onDelete}>
            <Trash size={14} />
          </Button>
        )}
      </div>

      {/* Subject Information */}
      <CompactSection title={t('common.subject')}>
        <CompactGrid>
          <CompactField autoIcon="commonName" label={t('common.commonName')} value={csr.common_name || csr.cn} className="col-span-2" />
          <CompactField autoIcon="organization" label={t('common.organization')} value={csr.organization} />
          <CompactField autoIcon="orgUnit" label={t('common.orgUnit')} value={csr.organizational_unit} />
          <CompactField autoIcon="country" label={t('common.country')} value={csr.country} />
          <CompactField autoIcon="state" label={t('common.state')} value={csr.state} />
          <CompactField autoIcon="locality" label={t('common.locality')} value={csr.locality} />
          <CompactField autoIcon="email" label={t('common.email')} value={csr.email} />
        </CompactGrid>
      </CompactSection>

      {/* Key Information */}
      <CompactSection title={t('common.keyInformation')}>
        <CompactGrid>
          <CompactField autoIcon="algorithm" label={t('common.algorithm')} value={keyAlgorithmLabel(csr.key_algorithm, t, csr.security_level) || '—'} />
          <CompactField autoIcon="keySize" label={t('common.keySize')} value={csr.key_size} />
          <CompactField autoIcon="signature" label={t('common.signature')} value={csr.signature_algorithm} />
        </CompactGrid>
      </CompactSection>

      {/* SANs */}
      {(csr.sans?.length > 0 || csr.san_dns?.length > 0) && (
        <CompactSection title={t('common.subjectAltNames')}>
          <div className="text-xs text-text-secondary space-y-1">
            {(csr.sans || csr.san_dns || []).map((san, i) => (
              <div key={i} className="font-mono bg-bg-tertiary px-2 py-1 rounded">
                {san}
              </div>
            ))}
          </div>
        </CompactSection>
      )}

      {/* Timeline */}
      <CompactSection title={t('common.timeline')}>
        <CompactGrid>
          <CompactField autoIcon="created" label={t('common.created')} value={csr.created_at ? formatDate(csr.created_at) : '—'} />
          <CompactField autoIcon="requester" label={t('csrs.requester')} value={csr.requester || csr.created_by} />
        </CompactGrid>
      </CompactSection>
    </div>
  )
}

// =============================================================================
// SIGNED CSR DETAILS PANEL (for history)
// =============================================================================

function SignedCSRDetailsPanel({ cert, onDownload, onDownloadCSR, onSignAgain, onRekey, t }) {
  const navigate = useNavigate()
  // `|| 0` turned a null expiry date into a confident "0 days left", and
  // turned the old -1 "no expiry" sentinel into "Expired".
  const daysRemaining = cert.days_remaining
  const expiryBadge = expiryVariant(daysRemaining)
  const isAcme = cert.source === 'acme'
  const isScep = cert.source === 'scep'
  
  return (
    <div className="p-3 space-y-3">
      {/* Header */}
      <CompactHeader
        icon={Certificate}
        iconClass="bg-accent-success-op20"
        title={cert.common_name || cert.cn || t('csrs.unnamedCertificate')}
        subtitle={cert.organization}
        badge={
          <div className="flex gap-1">
            <Badge variant="success" size="sm" icon={CheckCircle}>{t('csrs.signed')}</Badge>
            {isAcme && <Badge variant="info" size="sm">ACME</Badge>}
            {isScep && <Badge variant="purple" size="sm">SCEP</Badge>}
          </div>
        }
      />

      {/* Stats */}
      <CompactStats stats={[
        { icon: Stamp, value: cert.signed_by || cert.issuer_name || '—' },
        { icon: Clock, value: hasExpiry(daysRemaining)
            ? t('csrs.remaining', { days: daysRemaining })
            : t('common.never') },
      ]} />

      {/* Actions */}
      <div className="flex gap-2 flex-wrap">
        {onDownload && (
          <Button type="button" size="sm" variant="secondary" className="flex-1" onClick={onDownload}>
            <Download size={14} /> {t('common.downloadCertificate')}
          </Button>
        )}
        <Button type="button" size="sm" variant="secondary" onClick={onDownloadCSR}>
          <FileText size={14} /> {t('csrs.downloadCSR')}
        </Button>
        {onSignAgain && (
          <Button type="button" size="sm" variant="secondary" onClick={onSignAgain}>
            <SignIn size={14} /> {t('csrs.signAgain')}
          </Button>
        )}
        <Button 
          type="button"
          size="sm" 
          variant="secondary"
          onClick={() => navigate(`/certificates?id=${cert.id}`)}
        >
          <Certificate size={14} /> {t('common.viewCertificate')}
        </Button>
        {onRekey && (
          <Button type="button" size="sm" variant="secondary" onClick={onRekey}>
            <ArrowsClockwise size={14} /> {t('csrs.rekey')}
          </Button>
        )}
      </div>

      {/* Signing Information */}
      <CompactSection title={t('common.signingDetails')}>
        <CompactGrid>
          <CompactField autoIcon="signedBy" label={t('common.signedBy')} value={cert.signed_by || cert.issuer_name} className="col-span-2" />
          <CompactField autoIcon="signedAt" label={t('csrs.signed')} value={cert.signed_at ? formatDate(cert.signed_at) : formatDate(cert.valid_from)} />
          <CompactField autoIcon="expires" label={t('common.expires')} value={cert.valid_to ? formatDate(cert.valid_to) : '—'} />
          <CompactField 
            autoIcon="status" label={t('common.status')} 
            value={
              <Badge variant={expiryBadge} size="sm">
                {!hasExpiry(daysRemaining)
                  ? t('common.never')
                  : daysRemaining <= 0
                    ? t('details.expiredDaysAgo', { count: daysSinceExpiry(daysRemaining) })
                    : t('csrs.daysLeft', { days: daysRemaining })}
              </Badge>
            } 
          />
        </CompactGrid>
      </CompactSection>

      {/* Subject Information */}
      <CompactSection title={t('common.subject')}>
        <CompactGrid>
          <CompactField autoIcon="commonName" label={t('common.commonName')} value={cert.common_name || cert.cn} className="col-span-2" />
          <CompactField autoIcon="organization" label={t('common.organization')} value={cert.organization} />
          <CompactField autoIcon="orgUnit" label={t('common.orgUnit')} value={cert.organizational_unit} />
          <CompactField autoIcon="country" label={t('common.country')} value={cert.country} />
          <CompactField autoIcon="state" label={t('common.state')} value={cert.state} />
        </CompactGrid>
      </CompactSection>

      {/* Key Information */}
      <CompactSection title={t('common.keyInformation')}>
        <CompactGrid>
          <CompactField autoIcon="algorithm" label={t('common.algorithm')} value={keyAlgorithmLabel(cert.key_algorithm, t, cert.security_level) || '—'} />
          <CompactField autoIcon="keySize" label={t('common.keySize')} value={cert.key_size} />
          <CompactField autoIcon="serial" label={t('common.serial')} value={cert.serial_number} copyable mono className="col-span-2" />
        </CompactGrid>
      </CompactSection>

      {/* Timeline */}
      <CompactSection title={t('common.timeline')}>
        <CompactGrid>
          <CompactField autoIcon="created" label={t('csrs.csrCreated')} value={cert.created_at ? formatDate(cert.created_at) : '—'} />
          <CompactField autoIcon="issued" label={t('csrs.certificateIssued')} value={cert.valid_from ? formatDate(cert.valid_from) : '—'} />
        </CompactGrid>
      </CompactSection>
    </div>
  )
}
