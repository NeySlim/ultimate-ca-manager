/**
 * CSRs: the mockup's csr module, a simplePage() list (Sujet, Demandeur, Clé, Déposée, État) with its
 * one-object dock, on the server's two paged lists (pending, signed) as the state chips. What the
 * product has more (generate, import, search and sort on the server, sign locally or through a
 * Microsoft CA, the key, re-key, the PEM) takes the page head, the toolbar, the dock actions and
 * its « ⋯ » menu, and a further dock tab.
 */
import { showNotices } from '../lib/notices'
import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { FileText, SignIn, UploadSimple, ClipboardText, Plus, X, Certificate } from '@phosphor-icons/react'
import {
  Button, Modal, Input, Select, FileUpload, Textarea, EkuMultiSelect
} from '../components'
import {
  Zone, Btn, IconBtn, Pill, PageHead, Toolbar, SearchField, ListView, Dock, DockBody, Section, Props, EmptyBlock, NoMatch, LoadError, LoadCause,
} from '../components/atelier'
import { SmartImportModal } from '../components/SmartImport'
import { csrsService, casService, mscaService, ekuService, certificatesService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, useModals } from '../hooks'
import { extractData, cn, downloadBlob } from '../lib/utils'
import { getSanValidationError, sanRowsToPayload } from '../lib/sanValidate'
import { VALIDITY } from '../constants/config'
import { hiddenFromIssuance, listedForIssuance, signingCas, unlistedSigningCas } from '../lib/caSelection'
import { HiddenCasToggle } from '../components/cas/HiddenCasToggle'
import { soleImported } from '../lib/importResult'
import {
  CSR_LABELS, KEY_ALGORITHMS, algorithmForKeyType, algorithmName, findAlgorithm,
  groupedOptions, isUsable, listAlgorithms,
} from '../lib/keyAlgorithms'
import { certificateKeyLabel, serialHex } from '../lib/certificateDetail'
import { useKeyPlatform } from '../lib/policyAlgorithms'
import { BrainpoolNotice } from '../components/BrainpoolNotice'
import { useOpenEntity } from '../hooks/useOpenEntity'
import { issueWithSubjectOverride } from '../lib/uniqueSubject'
import { dateOf } from './admin/adminDates'
import { PemPanel } from './certificates/inspector/PemPanel'
import { CertMenu } from './certificates/inspector/CertMenu'

const DEFAULT_CSR_KEY_TYPE = findAlgorithm(CSR_LABELS[0]).csr

// Registry row of a listed CSR's key: its stored spelling, else '<algorithm> <size>'
const csrKeyRow = (csr) => algorithmForKeyType(csr.key_type)
  || algorithmForKeyType([csr.key_algorithm, csr.key_size].filter(Boolean).join(' '))

export default function CSRsPage() {
  const { t, i18n } = useTranslation()
  const locale = i18n?.language || 'en'
  const navigate = useNavigate()
  const openEntity = useOpenEntity()
  const { showSuccess, showError, showInfo, showConfirm, showWarning } = useNotification()
  const { canWrite, canDelete, hasPermission } = usePermission()
  // Direct private-key export is the admin-only read:private_keys scope,
  // as on the certificates page
  const canExportKey = hasPermission('read:private_keys')
  const canReadCertificates = hasPermission('read:certificates')
  const [searchParams, setSearchParams] = useSearchParams()
  const { modals, open: openModal, close: closeModal } = useModals(['upload', 'sign', 'generate'])
  
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
  const [loadError, setLoadError] = useState(null)
  const [cas, setCAs] = useState([])
  
  // Selection & modals
  const [selectedCSR, setSelectedCSR] = useState(null)
  const [showImportModal, setShowImportModal] = useState(false)
  const [signCA, setSignCA] = useState('')
  const [showHiddenCas, setShowHiddenCas] = useState(false)
  // Each opening of the sign dialog starts with the hidden CAs hidden again
  useEffect(() => { if (modals.sign) setShowHiddenCas(false) }, [modals.sign])
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
  const [genEmail, setGenEmail] = useState('')
  const [genLocality, setGenLocality] = useState('')
  // The user's pick, else the key the server issues when none is named, else the form default
  const [genKeyChoice, setGenKeyChoice] = useState(null)
  const platform = useKeyPlatform()
  const serverKey = CSR_LABELS.includes(platform.defaultKeyType) ? findAlgorithm(platform.defaultKeyType).csr : null
  const genKeyType = genKeyChoice ?? serverKey ?? DEFAULT_CSR_KEY_TYPE
  const csrKeys = useMemo(() => listAlgorithms({ labels: CSR_LABELS, ...platform }), [platform])
  // Only a key this server refuses (ML-DSA or Brainpool in FIPS mode) gives way to the first offered
  useEffect(() => {
    if (!isUsable(KEY_ALGORITHMS.find(k => k.csr === genKeyType), platform)) setGenKeyChoice(csrKeys[0].csr)
  }, [csrKeys, genKeyType, platform])
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
      setLoadError(null)
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
      setLoadError(error)
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

  // The Microsoft CA request still awaiting approval for the selected CSR, if any
  const [mscaRequest, setMscaRequest] = useState(null)
  const [checkingMsca, setCheckingMsca] = useState(false)
  const selectedCsrId = selectedCSR?.id
  useEffect(() => {
    setMscaRequest(null)
    // The status route imports the certificate: it requires write:certificates
    if (!selectedCsrId || activeTab !== 'pending' || !canWrite('certificates')) return undefined
    let cancelled = false
    mscaService.getPendingRequests()
      .then((res) => {
        if (!cancelled) setMscaRequest((res.data || []).find((r) => r.csr_id === selectedCsrId) || null)
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [selectedCsrId, activeTab]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleCheckMscaStatus = async () => {
    if (!mscaRequest || checkingMsca) return
    const csrId = selectedCsrId
    setCheckingMsca(true)
    try {
      const res = await mscaService.checkRequest(mscaRequest.msca_id, mscaRequest.id)
      const status = res.data?.status
      if (status === 'issued') {
        showSuccess(t('msca.checkIssued'))
        loadData()
        setSelectedCSR(null)
        openEntity('certificate', csrId)
      } else if (status === 'denied') {
        showError(t('msca.checkDenied'))
        loadData()
        setMscaRequest(null)
      } else if (status === 'superseded') {
        showInfo(t('msca.checkSuperseded'))
        loadData()
        setMscaRequest(null)
      } else {
        showInfo(t('msca.checkStillPending'))
      }
    } catch (error) {
      showError(error.message || t('msca.checkFailed'))
    } finally {
      setCheckingMsca(false)
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
        const signed = await issueWithSubjectOverride(options => csrsService.sign(
          selectedCSR.id, signCA, validityDays, signCertType, signExtraEkus, sanRowsToPayload(addedSans),
          options), showConfirm, t)
        if (signed === null) return  // the operator kept the refusal of a taken subject
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
        email: genEmail.trim() || undefined,
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
    setGenState(''); setGenLocality(''); setGenEmail(''); setGenKeyChoice(null)
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

  const handleRekeyAsCSR = (csr) => {
    setGenCN(csr.common_name || csr.cn || '')
    setGenOrg(csr.organization || '')
    setGenOU(csr.organizational_unit || '')
    setGenCountry(csr.country || '')
    setGenState(csr.state || '')
    setGenLocality(csr.locality || '')
    setGenEmail(csr.email || '')
    // An unknown CSR key is no user choice: the server default applies
    setGenKeyChoice(csrKeyRow(csr)?.csr ?? null)
    setGenSans(parseSansFromCSR(csr))
    setShowRekeyChoice(false)
    openModal('generate')
  }

  const handleRekeyAsCert = (csr) => {
    // A CSR key the form cannot issue leaves the choice to the server default
    const [keyType, keySize] = csrKeyRow(csr)?.issue || []
    const prefill = {
      cn: csr.common_name || csr.cn || '',
      organization: csr.organization || '',
      organizational_unit: csr.organizational_unit || '',
      country: csr.country || '',
      state: csr.state || '',
      locality: csr.locality || '',
      email: csr.email || '',
      key_type: keyType,
      key_size: keySize,
      sans: parseSansFromCSR(csr).filter(s => s.value).map(s => ({ type: s.type.toLowerCase(), value: s.value })),
    }
    setShowRekeyChoice(false)
    navigate('/certificates', { state: { prefill, source: 'rekey' } })
  }

  const handleRekey = (csr) => {
    setRekeyCSR(csr)
    setShowRekeyChoice(true)
  }

  const dialogs = (
    <>
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
                options={listedForIssuance(signingCas(cas), showHiddenCas, signCA).map(ca => ({ value: String(ca.id), label: ca.descr || ca.name || ca.common_name }))}
                value={signCA}
                onChange={setSignCA}
                placeholder={t('csrs.selectCA')}
                helperText={unlistedSigningCas(cas) > 0 ? t('cas.notListedForSigning', { count: unlistedSigningCas(cas) }) : undefined}
              />
              <HiddenCasToggle count={hiddenFromIssuance(signingCas(cas), signCA)} shown={showHiddenCas} onToggle={() => setShowHiddenCas(v => !v)} />

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
            options={groupedOptions(csrKeys, t,
              k => algorithmName(k, t, 'csrKey'), k => k.csr)}
            value={genKeyType}
            onChange={setGenKeyChoice}
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
                label={t('common.email')}
                type="email"
                value={genEmail}
                onChange={(e) => setGenEmail(e.target.value)}
                placeholder={t('certificates.emailPlaceholder')}
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

  // The open request in the dock: what the list row holds, then its detail once read
  const [section, setSection] = useState('overview')
  const [menuOpen, setMenuOpen] = useState(false)
  const openCSR = (row) => {
    if (row.id !== selectedCSR?.id) setSection('overview')
    loadCSRDetails(row)
  }
  const signed = activeTab === 'history'
  const csrName = (row) => t('csrs.module.name', { id: row.id })
  const csrSubject = (row) => row.common_name || row.cn || row.subject || t('common.unnamed')
  const csrRequester = (row) => row.requester || row.created_by || '—'
  const csrKey = (row) => certificateKeyLabel(row) || '—'
  const csrDate = (row) => dateOf(row.created_at, locale) || '—'
  const csrPill = (row) => (row.status === 'Signed' || (signed && row.status !== 'Pending')
    ? <Pill label={t('csrs.states.signed')} tone="good" />
    : <Pill label={t('csrs.states.pending')} tone="warn" />)
  const sortState = sort ? { key: sort.key, asc: sort.direction === 'asc' } : null
  const onSort = (key) => handleSortChange(sort?.key === key
    ? (sort.direction === 'asc' ? { key, direction: 'desc' } : null)
    : { key, direction: 'asc' })
  const pages = Math.max(1, Math.ceil(listTotal / perPage))
  const first = listTotal ? (page - 1) * perPage + 1 : 0
  const last = Math.min(listTotal, page * perPage)
  const narrowed = Boolean(searchValue)
  const write = canWrite('csrs')

  const open = selectedCSR
  const openSigned = open && (open.status === 'Signed' || signed)
  const summary = open && (openSigned
    ? t('csrs.module.signedSummary', { ca: open.signed_by || open.issuer_name || '—', date: dateOf(open.signed_at || open.valid_from, locale) || '—' })
    : (open.descr || t('csrs.module.pendingSummary')))
  const sans = open ? (open.sans?.length ? open.sans : (open.san_combined ? open.san_combined.split(',').map((s) => s.trim()).filter(Boolean) : [])) : []
  const menuItems = open ? [
    !openSigned && canExportKey && open.has_private_key && { id: 'key', icon: 'key', label: t('csrs.downloadKey'), onClick: () => handleDownloadKey(open) },
    !openSigned && write && !open.has_private_key && { id: 'upload-key', icon: 'upload', label: t('csrs.uploadKey'), write: true, onClick: () => setShowKeyModal(true) },
    !openSigned && canWrite('certificates') && mscaRequest && { id: 'msca', icon: 'refresh', label: t('msca.checkStatus'), write: true, onClick: handleCheckMscaStatus },
    openSigned && { id: 'csr', icon: 'file', label: t('csrs.downloadCSR'), onClick: () => handleDownload(open.id, `${open.cn || 'csr'}.csr`) },
    openSigned && canReadCertificates && { id: 'view', icon: 'cert', label: t('common.viewCertificate'), onClick: () => navigate(`/certificates?id=${open.id}`) },
    openSigned && write && canReadCertificates && { id: 'sign-again', icon: 'stamp', label: t('csrs.signAgain'), write: true, onClick: () => handleSignAgain(open) },
    write && { id: 'rekey', icon: 'refresh', label: t('csrs.rekey'), write: true, onClick: () => handleRekey(open) },
    !openSigned && canDelete('csrs') && { id: 'delete', icon: 'close', label: t('common.delete'), danger: true, write: true, onClick: () => handleDelete(open.id) },
  ].filter(Boolean) : []

  const dock = open && (
    <Dock label={t('atelier.detailOf', { name: t('common.csrs') })} tabsLabel={t('atelier.openItem')} activeKey={open.id}
      tabs={[{ key: open.id, title: csrName(open), icon: 'file' }]} onClose={() => setSelectedCSR(null)}>
      <DockBody icon="file" title={csrName(open)} badge={csrPill(open)} section={section} onSection={setSection}
        sectionsLabel={t('atelier.sectionsOf', { name: csrName(open) })}
        sections={[['overview', t('atelier.overview')], ['details', t('csrs.module.details')], ...(openSigned ? [] : [['pem', 'PEM']])]}
        actions={<>
          {openSigned ? (
            canReadCertificates && <Btn icon="download" id="csr-download-cert" onClick={() => handleDownloadCertificate(open)}>{t('common.downloadCertificate')}</Btn>
          ) : (
            <>
              <Btn icon="download" id="csr-download" onClick={() => handleDownload(open.id, `${open.cn || 'csr'}.csr`)}>{t('common.download')}</Btn>
              {write && <Btn tone="primary" icon="stamp" id="csr-sign" onClick={() => openModal('sign')}>{t('csrs.sign')}</Btn>}
            </>
          )}
          {menuItems.length > 0 && (
            <IconBtn quiet icon="more" title={false} label={t('csrs.module.moreActions', { name: csrName(open) })} data-csr-menu={open.id} onClick={() => setMenuOpen(true)} />
          )}
        </>}>
        {section === 'overview' && (
          <div className="module-detail">
            <Section title={t('atelier.properties')}>
              <Props items={[
                [t('csrs.module.subject'), csrSubject(open)],
                [t('csrs.module.requester'), csrRequester(open)],
                [t('csrs.module.key'), csrKey(open)],
                [t('csrs.module.submitted'), csrDate(open)],
                [t('atelier.state'), csrPill(open)],
                openSigned && [t('common.signedBy'), open.signed_by || open.issuer_name || '—'],
                openSigned && [t('common.expires'), dateOf(open.valid_to, locale) || '—'],
                openSigned && open.serial_number && [t('common.serial'), <span key="serial" className="mono">{serialHex(open.serial_number)}</span>],
              ]} />
            </Section>
            <Section title={t('atelier.summary')}><p className="summary">{summary}</p></Section>
          </div>
        )}
        {section === 'details' && (
          <div className="module-detail">
            <Section title={t('common.subject')}>
              <Props items={[
                [t('common.organization'), open.organization || '—'],
                [t('common.orgUnit'), open.organizational_unit || '—'],
                [t('common.country'), open.country || '—'],
                [t('common.state'), open.state || '—'],
                [t('common.locality'), open.locality || '—'],
                [t('common.email'), open.email || '—'],
                [t('common.signature'), open.signature_algorithm || '—'],
              ]} />
            </Section>
            <Section title={t('common.subjectAltNames')}>
              {sans.length ? <ul className="record-list">{sans.map((s) => <li key={s}><div className="rl-main"><span className="mono">{s}</span></div></li>)}</ul>
                : <p className="muted small">{t('csrs.module.noSans')}</p>}
            </Section>
          </div>
        )}
        {section === 'pem' && <PemPanel cert={open} />}
      </DockBody>
    </Dock>
  )

  const pendingEmpty = !signed
  const emptyBlock = narrowed ? (
    <NoMatch title={t('table.noResults')} text={t('table.adjustFilters')} resetLabel={t('table.clearFilters')} onReset={() => setSearchInput('')} />
  ) : (
    <EmptyBlock id="csrs" icon="file" title={pendingEmpty ? t('csrs.noPendingCSRs') : t('csrs.noSignedCertificates')}
      text={pendingEmpty ? t('csrs.uploadToStart') : t('csrs.signToSee')}
      action={pendingEmpty && write ? { label: t('csrs.importCSR'), icon: 'upload', onClick: () => setShowImportModal(true), write: true } : undefined} />
  )

  return (
    <Zone dock={dock} testId="csrs-zone" after={<>
      {menuOpen && open && <CertMenu title={t('csrs.module.actionsTitle')} name={csrName(open)} items={menuItems} onClose={() => setMenuOpen(false)} />}
      {dialogs}
    </>}>
      <PageHead title={t('common.csrs')} total={t('csrs.module.unit', { count: pendingTotal + historyTotal })} intent={t('shell.moduleDesc.csrs')}
        actions={write && <>
          <Btn icon="upload" id="csr-import" write onClick={() => setShowImportModal(true)}>{t('common.import')}</Btn>
          <Btn tone="primary" icon="plus" id="csr-generate" onClick={() => openModal('generate')}>{t('csrs.generateCSR')}</Btn>
        </>} />
      <ListView label={t('common.csrs')} caption={t('csrs.module.caption')} icon="file" rows={rows} loading={loading}
        filters={{
          views: [
            { id: 'pending', label: t('csrs.states.pending'), count: pendingTotal },
            { id: 'history', label: t('csrs.states.signed'), count: historyTotal },
          ],
          active: activeTab, onChange: handleTabChange, label: t('csrs.module.filterByState'),
        }}
        toolbar={(
          <Toolbar>
            <SearchField id="csr-search" name="q" label={signed ? t('csrs.searchSigned') : t('csrs.searchPending')}
              placeholder={signed ? t('csrs.searchSigned') : t('csrs.searchPending')} value={searchInput} onChange={setSearchInput} />
          </Toolbar>
        )}
        title={csrName} status={csrPill} openedId={open?.id} onOpen={openCSR}
        sort={sortState} onSort={onSort}
        columns={[
          { id: 'subject', label: t('csrs.module.subject'), cell: csrSubject, grow: true, sort: 'cn' },
          { id: 'requester', label: t('csrs.module.requester'), cell: csrRequester },
          { id: 'key', label: t('csrs.module.key'), cell: csrKey },
          { id: 'submitted', label: t('csrs.module.submitted'), cell: csrDate, sort: 'created_at' },
          { status: true },
        ]}
        error={loadError && (
          <LoadError id="csrs" title={t('messages.errors.loadFailed.csrs')} onRetry={loadLists} journal={hasPermission?.('read:audit') ? '/audit' : undefined}
            cause={<LoadCause error={{ status: loadError.status, request: loadError.status && `GET /api/v2/${signed ? 'csrs/history' : 'csrs'}`, message: loadError.message }} />} />
        )}
        empty={emptyBlock}
        footer={{
          range: t('csrs.module.range', { start: first, end: last, count: listTotal }),
          pagination: { page, pages, perPage, onPage: setPage, onPerPage: (v) => { setPerPage(v); setPage(1) } },
        }} />
    </Zone>
  )
}

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
