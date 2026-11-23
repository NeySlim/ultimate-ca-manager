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
import { EkuMultiSelect } from '../components'
import { Input, Select, Textarea, ToggleSwitch, SegmentedField, SecretInput } from '../components/atelier/Form'
import {
  Zone, AtelierDialog, Icon, FieldError, Btn, IconBtn, PageHead, Toolbar, SearchField, ListView, Dock, DockBody, EmptyBlock, NoMatch, LoadError, LoadCause,
  useSortParam,
} from '../components/atelier'
import { SmartImportModal } from '../components/SmartImport'
import { csrsService, casService, mscaService, ekuService, certificatesService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, useModals } from '../hooks'
import { extractData, downloadBlob } from '../lib/utils'
import { getSanValidationError, sanRowsToPayload } from '../lib/sanValidate'
import { VALIDITY } from '../constants/config'
import { hiddenFromIssuance, listedForIssuance, signingCas, unlistedSigningCas } from '../lib/caSelection'
import { withHiddenCas, pickOrToggle } from '../components/cas/hiddenCasOption'
import { soleImported } from '../lib/importResult'
import {
  CSR_LABELS, KEY_ALGORITHMS, algorithmForKeyType, algorithmName, findAlgorithm,
  groupedOptions, isUsable, listAlgorithms,
} from '../lib/keyAlgorithms'
import { useKeyPlatform } from '../lib/policyAlgorithms'
import { BrainpoolNotice } from '../components/BrainpoolNotice'
import { useOpenEntity } from '../hooks/useOpenEntity'
import { useDockSelection, asId } from '../components/atelier/useDockParam'
import { issueWithSubjectOverride } from '../lib/uniqueSubject'
import { dateOf } from './admin/adminDates'
import { CsrSections, csrSections, csrName as csrNameOf, csrSubject as csrSubjectOf, csrPill as csrPillOf, csrRequester, csrKey } from './csrs/CsrSections'
import { useDetached } from '../components/detached/useDetached'
import { CertMenu } from './certificates/inspector/CertMenu'
import { PhoneMoreActions } from './pki/PhoneMoreActions'

const DEFAULT_CSR_KEY_TYPE = findAlgorithm(CSR_LABELS[0]).csr

// Registry row of a listed CSR's key: its stored spelling, else '<algorithm> <size>'
const csrKeyRow = (csr) => algorithmForKeyType(csr.key_type)
  || algorithmForKeyType([csr.key_algorithm, csr.key_size].filter(Boolean).join(' '))

const CSR_SECTIONS = ['overview', 'details', 'pem']

// The newest request first (T4); the keys the server sorts both lists on
const CSR_SORT = { key: 'created_at', asc: false }
const CSR_SORT_KEYS = ['id', 'cn', 'requester', 'key_type', 'created_at']

export default function CSRsPage() {
  const { t, i18n } = useTranslation()
  const locale = i18n?.language || 'en'
  const navigate = useNavigate()
  const openEntity = useOpenEntity()
  const detached = useDetached()
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
  // The server sorts, the newest submitted first by default; the sort lives in the address, the tab's own (T4, T9)
  const { sort, onSort: sortBy } = useSortParam(CSR_SORT, CSR_SORT_KEYS)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [cas, setCAs] = useState([])
  
  // Selection & modals
  // The open request and its section live in the URL (`item`, `section`); the palette's former ?selected= still opens it.
  // Its detail is read below, so the hook never drops an id the list page lacks
  const csrDock = useDockSelection(rows, { ready: false, sections: CSR_SECTIONS, aliases: ['selected'] })
  const selectedCSR = csrDock.selected
  const setSelectedCSR = csrDock.select
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
  const [uploadFile, setUploadFile] = useState(null)
  const [genSubjectOpen, setGenSubjectOpen] = useState(false)
  
  // Key upload modal
  const [showKeyModal, setShowKeyModal] = useState(false)
  const [keyPem, setKeyPem] = useState('')
  const [keyPassphrase, setKeyPassphrase] = useState('')

  // Re-key modal
  const [showRekeyChoice, setShowRekeyChoice] = useState(false)
  const [rekeyCSR, setRekeyCSR] = useState(null)

  // Handle tab change
  // `open`: the request to show in the new tab, written with it in one step
  const handleTabChange = (tabId, open = null) => {
    if (tabId !== activeTab) {
      // The other tab's rows must not show under this tab's columns
      setRows([])
      setListTotal(0)
      setSearchInput('')
      setSearchValue('')
      setLoading(true)
    }
    setActiveTab(tabId)
    setPage(1)
    // The new tab's URL carries no open request but the one asked: the dock follows it
    setSearchParams(open ? { tab: tabId, item: String(open.id) } : { tab: tabId })
    if (open) csrDock.hold(open)
  }

  // Pagination state
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)
  // A new sort, clicked or read from the address (Back, a link), starts on page one
  const sortMark = `${sort.key}:${sort.asc}`
  const [sortSeen, setSortSeen] = useState(sortMark)
  if (sortSeen !== sortMark) { setSortSeen(sortMark); setPage(1) }

  useEffect(() => {
    loadAux()
  }, [])

  // `?action=upload` (the palette) opens the upload form, the page already open or not, then leaves the URL
  const askedAction = searchParams.get('action')
  useEffect(() => {
    if (askedAction !== 'upload') return
    if (canWrite('csrs')) openModal('upload')
    const next = new URLSearchParams(searchParams)
    next.delete('action')
    setSearchParams(next, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [askedAction])

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
    params.sort_by = sort.key
    params.sort_order = sort.asc ? 'asc' : 'desc'
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

  // The open request's detail, read whether it was opened here or by a link (then perhaps off the list's page)
  const csrItem = csrDock.item
  useEffect(() => {
    if (!csrItem || loading) return undefined
    let live = true
    const csr = rows.find((r) => String(r.id) === csrItem)
    csrsService.getById(csr?.id ?? asId(csrItem)).then((response) => {
      if (live) setSelectedCSR({ ...extractData(response), ...csr }) // Merge to keep signed_by info
    }, () => {
      if (live && !csr) setSelectedCSR(null)
    })
    return () => { live = false }
  }, [csrItem, loading]) // eslint-disable-line react-hooks/exhaustive-deps

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
    handleTabChange('pending', csr)
  }

  const handleUpload = async (files) => {
    try {
      const file = files[0]
      const text = await file.text()
      const created = await csrsService.upload(text)
      showSuccess(t('messages.success.create.csr'))
      closeModal('upload')
      setUploadFile(null)
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

  // EOBO: switched on, the enrollee is prefilled from the request (subject, then SAN UPN, SAN email, subject email)
  const toggleEobo = (enabled) => {
    setEoboEnabled(enabled)
    if (!enabled || !selectedCSR) return
    if (!enrolleeName && selectedCSR.subject) setEnrolleeName(selectedCSR.subject)
    if (enrolleeUpn) return
    const first = (value) => {
      try {
        const list = typeof value === 'string' ? JSON.parse(value) : value
        return Array.isArray(list) && list.length > 0 ? list[0] : ''
      } catch { return '' }
    }
    // Priority 1: SAN UPN (Microsoft OID 1.3.6.1.4.1.311.20.2.3); 2: SAN email; 3: subject emailAddress
    const foundUpn = (selectedCSR.san_upn && first(selectedCSR.san_upn)) || (selectedCSR.san_email && first(selectedCSR.san_email)) || selectedCSR.email || ''
    if (foundUpn) setEnrolleeUpn(foundUpn)
  }
  const closeUpload = () => { closeModal('upload'); setPastedPEM(''); setUploadMode('file'); setUploadFile(null) }
  const closeSign = () => { closeModal('sign'); setSignMode('local'); setSelectedMsca(''); setSelectedTemplate(''); setEoboEnabled(false); setEnrolleeName(''); setEnrolleeUpn('') }
  const closeGenerate = () => { if (generating) return; closeModal('generate'); resetGenerateForm() }
  const closeKey = () => { setShowKeyModal(false); setKeyPem(''); setKeyPassphrase('') }
  const uploadTooLarge = uploadFile && uploadFile.size > 1024 * 1024
  const signOptions = withHiddenCas(
    listedForIssuance(signingCas(cas), showHiddenCas, signCA).map(ca => ({ value: String(ca.id), label: ca.descr || ca.name || ca.common_name })),
    { count: hiddenFromIssuance(signingCas(cas), signCA), shown: showHiddenCas, t })

  const dialogs = (
    <>
      {/* Upload CSR: a file or the pasted PEM */}
      {modals.upload && (
        <AtelierDialog title={t('csrs.uploadCSR')} size="narrow" onClose={closeUpload} testId="csr-upload-dialog">
          <form noValidate onSubmit={(e) => { e.preventDefault(); if (uploadMode === 'paste') handlePasteUpload(); else if (uploadFile && !uploadTooLarge) handleUpload([uploadFile]) }}>
            <div className="form-fields">
              <SegmentedField label={t('common.source')} pressed={(v) => uploadMode === v} onPick={setUploadMode}
                options={[{ value: 'file', label: t('common.uploadFile') }, { value: 'paste', label: t('csrs.pastePEM') }]} />
              {uploadMode === 'file' ? (
                <div className="field full">
                  <label htmlFor="csr-upload-file">{t('csrs.uploadCSRDescription')}</label>
                  <input id="csr-upload-file" type="file" accept=".pem,.csr" aria-describedby="hint-csr-upload-file"
                    onChange={(e) => setUploadFile(e.target.files?.[0] || null)} />
                  <small id="hint-csr-upload-file">.pem, .csr · 1 MB</small>
                  {uploadTooLarge && <FieldError id="err-csr-upload-file" message={t('csrs.uploadTooLarge')} />}
                </div>
              ) : (
                <Textarea id="csr-upload-pem" label={t('csrs.pasteCSRDescription')} mono rows={10} value={pastedPEM} spellCheck={false}
                  onChange={(e) => setPastedPEM(e.target.value)}
                  placeholder={'-----BEGIN CERTIFICATE REQUEST-----\nMIICijCCAXICAQAwRTELMAkGA1UEBhMCVVMx...\n-----END CERTIFICATE REQUEST-----'} />
              )}
            </div>
            <div className="modal-actions">
              <button type="button" className="btn" data-action="close-modal" onClick={closeUpload}>{t('common.cancel')}</button>
              <button type="submit" className="btn primary" disabled={(uploadMode === 'paste' ? !pastedPEM.trim() : !uploadFile || uploadTooLarge) || undefined}>
                <Icon name="upload" />{t('common.upload')}
              </button>
            </div>
          </form>
        </AtelierDialog>
      )}

      {/* Sign CSR: locally, or through a Microsoft CA when connections exist */}
      {modals.sign && (
        <AtelierDialog title={t('common.signCSR')} subtitle={t('csrs.signCSRDescription')} onClose={closeSign} testId="csr-sign-dialog">
          <form noValidate onSubmit={(e) => { e.preventDefault(); handleSign() }}>
            <div className="form-fields">
              {mscaConnections.length > 0 && (
                <SegmentedField label={t('csrs.signWith')} pressed={(v) => signMode === v} onPick={setSignMode}
                  options={[{ value: 'local', label: t('msca.signLocal') }, { value: 'msca', label: t('msca.signMicrosoft') }]} />
              )}
              {signMode === 'local' ? (
                <>
                  <Select id="csr-sign-ca" label={t('common.certificateAuthority')} options={signOptions} value={signCA} full
                    onChange={pickOrToggle(setSignCA, () => setShowHiddenCas(v => !v))} placeholder={t('csrs.selectCA')}
                    helperText={unlistedSigningCas(cas) > 0 ? t('cas.notListedForSigning', { count: unlistedSigningCas(cas) }) : undefined} />
                  <Select id="csr-sign-type" label={t('csrs.certTypeForSign')} value={signCertType} onChange={setSignCertType}
                    options={[
                      { value: 'server', label: t('certificates.certTypes.server') },
                      { value: 'client', label: t('certificates.certTypes.client') },
                      { value: 'combined', label: t('certificates.certTypes.combined') },
                      { value: 'intermediate_ca', label: t('certificates.certTypes.intermediateCA') },
                      { value: 'code_signing', label: t('certificates.certTypes.codeSigning') },
                      { value: 'email', label: t('certificates.certTypes.email') },
                    ]} />
                  <Input id="csr-sign-days" label={t('csrs.validityPeriod')} type="number" min="1" max="3650" short
                    value={Number.isNaN(validityDays) ? '' : validityDays} onChange={(e) => setValidityDays(parseInt(e.target.value))} />
                  <EkuMultiSelect value={signExtraEkus} onChange={setSignExtraEkus} defaults={EKU_DEFAULTS_BY_TYPE[signCertType] || []} knownEkus={knownEkus} />
                  {signCertType !== 'intermediate_ca' && (
                    <SanRows id="csr-sign-san" legend={t('csrs.signAddNames')} hint={t('csrs.signAddNamesHelp')} rows={signSans} onChange={setSignSans}
                      types={['Email', 'DNS', 'IP', 'URI']} allowEmpty t={t} />
                  )}
                </>
              ) : (
                <>
                  <Select id="csr-sign-msca" label={t('msca.selectConnection')} full value={selectedMsca} onChange={handleMscaConnectionChange}
                    options={mscaConnections.map(c => ({ value: String(c.id), label: `${c.name} (${c.server})` }))} placeholder={t('msca.selectConnection')} />
                  {selectedMsca && (
                    <Select id="csr-sign-msca-template" label={t('msca.selectTemplate')} full value={selectedTemplate} onChange={setSelectedTemplate}
                      options={mscaTemplates.map(name => ({ value: name, label: name }))} disabled={loadingTemplates}
                      placeholder={loadingTemplates ? t('msca.loadingTemplates') : t('msca.selectTemplate')} />
                  )}
                  {selectedMsca && (
                    <ToggleSwitch id="csr-sign-eobo" label={t('msca.eobo.enable')} checked={eoboEnabled} onChange={toggleEobo} />
                  )}
                  {selectedMsca && eoboEnabled && (
                    <>
                      <Input id="csr-sign-enrollee" label={t('msca.eobo.enrolleeName')} value={enrolleeName} onChange={(e) => setEnrolleeName(e.target.value)}
                        placeholder={t('msca.eobo.enrolleeNamePlaceholder')} />
                      <Input id="csr-sign-upn" label={t('msca.eobo.enrolleeUpn')} value={enrolleeUpn} onChange={(e) => setEnrolleeUpn(e.target.value)}
                        placeholder={t('msca.eobo.enrolleeUpnPlaceholder')} required helperText={t('msca.eobo.hint')} />
                    </>
                  )}
                </>
              )}
            </div>
            <div className="modal-actions">
              <button type="button" className="btn" data-action="close-modal" onClick={closeSign}>{t('common.cancel')}</button>
              <button type="submit" className="btn primary" disabled={(signMode === 'local' ? !signCA : (!selectedMsca || !selectedTemplate)) || undefined}>
                <Icon name="stamp" />{t('common.signCSR')}
              </button>
            </div>
          </form>
        </AtelierDialog>
      )}

      {/* Generate CSR: the name, the key, the subject folded, the alternative names */}
      {modals.generate && (
        <AtelierDialog title={t('csrs.generateCSR')} subtitle={t('csrs.generateDescription')} size="wide" onClose={closeGenerate} testId="csr-generate-dialog">
          <form noValidate onSubmit={(e) => { e.preventDefault(); handleGenerate() }}>
            <div className="form-fields">
              <Input id="csr-gen-cn" label={`${t('common.commonName')} *`} value={genCN} onChange={(e) => setGenCN(e.target.value)} placeholder="example.com" required data-autofocus="" />
              <Select id="csr-gen-key" label={t('common.keyType')} value={genKeyType} onChange={setGenKeyChoice}
                options={groupedOptions(csrKeys, t, k => algorithmName(k, t, 'csrKey'), k => k.csr)}
                after={<BrainpoolNotice atelier label={KEY_ALGORITHMS.find(k => k.csr === genKeyType)?.label} />} />
              <div className="field full advanced">
                <button type="button" className="advanced-toggle" aria-expanded={genSubjectOpen} aria-controls="csr-gen-subject" onClick={() => setGenSubjectOpen(v => !v)}>
                  <Icon name={genSubjectOpen ? 'down' : 'right'} /><span>{t('certificates.subjectDetails')}</span>
                </button>
                <div className="subject-grid" id="csr-gen-subject" hidden={!genSubjectOpen}>
                  <Input id="csr-gen-country" label={t('common.country')} value={genCountry} onChange={(e) => setGenCountry(e.target.value)} placeholder="US" maxLength={2} />
                  <Input id="csr-gen-state" label={t('common.state')} value={genState} onChange={(e) => setGenState(e.target.value)} placeholder={t('certificates.statePlaceholder')} />
                  <Input id="csr-gen-locality" label={t('common.locality')} value={genLocality} onChange={(e) => setGenLocality(e.target.value)} placeholder={t('certificates.localityPlaceholder')} />
                  <Input id="csr-gen-email" label={t('common.email')} type="email" value={genEmail} onChange={(e) => setGenEmail(e.target.value)} placeholder={t('certificates.emailPlaceholder')} />
                  <Input id="csr-gen-org" label={t('common.organization')} value={genOrg} onChange={(e) => setGenOrg(e.target.value)} placeholder={t('certificates.orgPlaceholder')} />
                  <Input id="csr-gen-ou" label={t('csrs.department')} value={genOU} onChange={(e) => setGenOU(e.target.value)} placeholder={t('csrs.departmentPlaceholder')} />
                </div>
              </div>
              <SanRows id="csr-gen-san" legend={t('csrs.sansList')} rows={genSans} onChange={setGenSans} types={['DNS', 'IP', 'Email', 'URI', 'UPN']} t={t} />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn" data-action="close-modal" onClick={closeGenerate} disabled={generating || undefined}>{t('common.cancel')}</button>
              <button type="submit" className="btn primary" disabled={!genCN.trim() || generating || undefined}>
                <Icon name="plus" />{generating ? t('common.generating') : t('csrs.generateCSR')}
              </button>
            </div>
          </form>
        </AtelierDialog>
      )}

      {/* Upload the private key of the open request */}
      {showKeyModal && (
        <AtelierDialog title={t('csrs.uploadPrivateKey')} subtitle={selectedCSR?.common_name || selectedCSR?.cn} size="narrow" onClose={closeKey} testId="csr-key-dialog">
          <form noValidate onSubmit={(e) => { e.preventDefault(); handleUploadKey() }}>
            <div className="form-fields">
              <Textarea id="csr-key-pem" label={t('common.privateKeyPEM')} mono rows={8} value={keyPem} spellCheck={false} data-autofocus=""
                onChange={(e) => setKeyPem(e.target.value)}
                placeholder={'-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQE...\n-----END PRIVATE KEY-----'} />
              <SecretInput id="csr-key-passphrase" label={t('csrs.passphrase')} full value={keyPassphrase} onChange={(e) => setKeyPassphrase(e.target.value)}
                placeholder={t('csrs.passphraseHint')} />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn" data-action="close-modal" onClick={closeKey}>{t('common.cancel')}</button>
              <button type="submit" className="btn primary" disabled={!keyPem.trim() || undefined}><Icon name="upload" />{t('csrs.uploadKey')}</button>
            </div>
          </form>
        </AtelierDialog>
      )}

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

      {/* Re-key: a new request, or a certificate issued at once (write:certificates) */}
      {showRekeyChoice && (
        <AtelierDialog title={t('csrs.rekeyTitle')} size="narrow" onClose={() => setShowRekeyChoice(false)} testId="csr-rekey-dialog">
          <p className="muted" style={{ marginBottom: 20 }}>{t('csrs.rekeyDescription', { cn: rekeyCSR?.common_name || rekeyCSR?.cn || '' })}</p>
          <div className="choice-grid">
            <button type="button" className="format-option" style={{ textAlign: 'left' }} onClick={() => handleRekeyAsCSR(rekeyCSR)}>
              <Icon name="file" /><span>{t('csrs.rekeyAsCSR')}<small>{t('csrs.rekeyAsCSRDescription')}</small></span>
            </button>
            {/* Issuing lands on the certificates page, which needs write:certificates */}
            {canWrite('certificates') && (
              <button type="button" className="format-option" style={{ textAlign: 'left' }} onClick={() => handleRekeyAsCert(rekeyCSR)}>
                <Icon name="cert" /><span>{t('csrs.rekeyAsCert')}<small>{t('csrs.rekeyAsCertDescription')}</small></span>
              </button>
            )}
          </div>
          <div className="modal-actions">
            <button type="button" className="btn" data-action="close-modal" onClick={() => setShowRekeyChoice(false)}>{t('common.cancel')}</button>
          </div>
        </AtelierDialog>
      )}
    </>
  )

  // The open request in the dock: what the list row holds, then its detail once read
  const { section, setSection } = csrDock
  const [menuOpen, setMenuOpen] = useState(false)
  const openCSR = (row) => setSelectedCSR(row)
  const signed = activeTab === 'history'
  const csrName = (row) => csrNameOf(t, row)
  const csrSubject = (row) => csrSubjectOf(t, row)
  const csrDate = (row) => dateOf(row.created_at, locale) || '—'
  const csrPill = (row) => csrPillOf(t, row, signed)
  const pages = Math.max(1, Math.ceil(listTotal / perPage))
  const first = listTotal ? (page - 1) * perPage + 1 : 0
  const last = Math.min(listTotal, page * perPage)
  const narrowed = Boolean(searchValue)
  const write = canWrite('csrs')

  const open = selectedCSR
  const openSigned = open && (open.status === 'Signed' || signed)
  const menuItems = open ? [
    !openSigned && canExportKey && open.has_private_key && { id: 'key', icon: 'key', label: t('csrs.downloadKey'), onClick: () => handleDownloadKey(open) },
    !openSigned && write && !open.has_private_key && { id: 'upload-key', icon: 'upload', label: t('csrs.uploadKey'), write: true, onClick: () => setShowKeyModal(true) },
    !openSigned && canWrite('certificates') && mscaRequest && { id: 'msca', icon: 'refresh', label: t('msca.checkStatus'), write: true, onClick: handleCheckMscaStatus },
    openSigned && { id: 'csr', icon: 'file', label: t('csrs.downloadCSR'), onClick: () => handleDownload(open.id, `${open.cn || 'csr'}.csr`) },
    openSigned && canReadCertificates && { id: 'view', icon: 'cert', label: t('common.viewCertificate'), onClick: () => navigate(`/certificates?item=${open.id}`) },
    openSigned && write && canReadCertificates && { id: 'sign-again', icon: 'stamp', label: t('csrs.signAgain'), write: true, onClick: () => handleSignAgain(open) },
    write && { id: 'rekey', icon: 'refresh', label: t('csrs.rekey'), write: true, onClick: () => handleRekey(open) },
    !openSigned && canDelete('csrs') && { id: 'delete', icon: 'close', label: t('common.delete'), danger: true, write: true, onClick: () => handleDelete(open.id) },
  ].filter(Boolean) : []

  const dock = open && (
    <Dock label={t('atelier.detailOf', { name: t('common.csrs') })} tabsLabel={t('atelier.openItem')} activeKey={open.id}
      tabs={[{ key: open.id, title: csrName(open), icon: 'file' }]} onClose={() => setSelectedCSR(null)}
      onDetach={detached?.available ? () => { detached.open('csr', [open.id]); setSelectedCSR(null) } : undefined}>
      <DockBody icon="file" title={csrName(open)} badge={csrPill(open)} section={section} onSection={setSection}
        sectionsLabel={t('atelier.sectionsOf', { name: csrName(open) })}
        sections={csrSections(t, openSigned)}
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
        <CsrSections csr={open} signed={openSigned} section={section} />
      </DockBody>
    </Dock>
  )

  const pendingEmpty = !signed
  const emptyBlock = narrowed ? (
    <NoMatch title={t('table.noResults')} text={t('table.adjustFilters')} resetLabel={t('table.clearFilters')} onReset={() => setSearchInput('')} />
  ) : (
    <EmptyBlock id="csrs" icon="file" title={pendingEmpty ? t('csrs.module.emptyTitle') : t('csrs.noSignedCertificates')}
      text={pendingEmpty ? t('csrs.module.emptyText') : t('csrs.signToSee')}
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
          <PhoneMoreActions title={t('common.csrs')} items={[{ id: 'import', icon: 'upload', label: t('common.import'), write: true, onClick: () => setShowImportModal(true) }]} />
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
        sort={sort} onSort={sortBy} nameSort="id"
        // The subject names the request (its name is a number): it takes the room left and folds last (L7, R2)
        columns={[
          { id: 'subject', label: t('csrs.module.subject'), cell: csrSubject, kind: 'text', grow: true, priority: 2, sort: 'cn' },
          { id: 'requester', label: t('csrs.module.requester'), cell: csrRequester, kind: 'text', priority: 3, sort: 'requester' },
          { id: 'key', label: t('csrs.module.key'), cell: csrKey, kind: 'fit', priority: 3, sort: 'key_type' },
          { id: 'submitted', label: t('csrs.module.submitted'), labelFull: t('table.fullSubmitted'), cell: csrDate, kind: 'fit', priority: 2, labelled: true, sort: 'created_at' },
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

// Typed SAN rows, the issue form's row-list of san-row; without `allowEmpty` the last row cannot be removed.
function SanRows({ id, legend, hint, rows, onChange, types, allowEmpty = false, t }) {
  const update = (i, patch) => onChange(rows.map((row, j) => (j === i ? { ...row, ...patch } : row)))
  return (
    <fieldset className="field full" aria-describedby={hint ? `hint-${id}` : undefined}>
      <legend>{legend}</legend>
      {hint && <small id={`hint-${id}`}>{hint}</small>}
      <div className="row-list">
        {rows.map((san, i) => (
          <div className="san-row" key={i}>
            <label className="sr-only" htmlFor={`${id}-type-${i}`}>{t('certificates.issueForm.sanType', { n: i + 1 })}</label>
            <select id={`${id}-type-${i}`} value={san.type} onChange={(e) => update(i, { type: e.target.value })}>
              {types.map(type => <option key={type} value={type}>{type}</option>)}
            </select>
            <label className="sr-only" htmlFor={`${id}-value-${i}`}>{t('certificates.issueForm.sanValue', { n: i + 1 })}</label>
            <input id={`${id}-value-${i}`} value={san.value} placeholder={SAN_PLACEHOLDERS[san.type]} autoComplete="off" spellCheck="false"
              onChange={(e) => update(i, { value: e.target.value })} />
            {(allowEmpty || rows.length > 1) ? (
              <button type="button" className="icon-btn" aria-label={t('certificates.issueForm.removeSan', { n: i + 1 })}
                onClick={() => onChange(rows.filter((_, j) => j !== i))}>
                <Icon name="close" />
              </button>
            ) : <span />}
          </div>
        ))}
      </div>
      <button type="button" className="btn quiet add-row" onClick={() => onChange([...rows, { type: types[0], value: '' }])}>
        <Icon name="plus" />{t('certificates.addSan')}
      </button>
    </fieldset>
  )
}
