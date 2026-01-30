/**
 * CAs (Certificate Authorities) Page
 * Uses PageLayout for consistent layout structure
 */
import { useState, useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { 
  ShieldCheck, Crown, Key, Download, Trash, PencilSimple,
  Tree, SquaresFour, Certificate, UploadSimple, MagnifyingGlass,
  Database, Pulse
} from '@phosphor-icons/react'
import {
  PageLayout, FocusItem, TreeView, Table, Button, 
  Badge, Modal, Input, Select, ExportDropdown, Card,
  Tabs, LoadingSpinner, EmptyState, Tooltip, HelpCard, StatusIndicator
} from '../components'
import { casService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, useModals } from '../hooks'
import { extractCN, extractData, formatDate, formatDateTime } from '../lib/utils'

// OCSP Settings Tab Component
function OCSPSettingsTab({ ca, onUpdate, showSuccess, showError }) {
  const [ocspEnabled, setOcspEnabled] = useState(ca?.ocsp_enabled || false)
  const [ocspUrl, setOcspUrl] = useState(ca?.ocsp_url || `${window.location.origin}/ocsp/${ca?.refid || ''}`)
  const [cdpEnabled, setCdpEnabled] = useState(ca?.cdp_enabled || false)
  const [cdpUrl, setCdpUrl] = useState(ca?.cdp_url || `${window.location.origin}/crl/${ca?.refid || ''}.crl`)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (ca) {
      setOcspEnabled(ca.ocsp_enabled || false)
      setOcspUrl(ca.ocsp_url || `${window.location.origin}/ocsp/${ca.refid || ''}`)
      setCdpEnabled(ca.cdp_enabled || false)
      setCdpUrl(ca.cdp_url || `${window.location.origin}/crl/${ca.refid || ''}.crl`)
    }
  }, [ca])

  const handleSave = async () => {
    setSaving(true)
    try {
      await casService.update(ca.id, {
        ocsp_enabled: ocspEnabled,
        ocsp_url: ocspEnabled ? ocspUrl : null,
        cdp_enabled: cdpEnabled,
        cdp_url: cdpEnabled ? cdpUrl : null
      })
      showSuccess('OCSP/CDP settings saved successfully')
      if (onUpdate) onUpdate()
    } catch (error) {
      showError('Failed to save settings: ' + error.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <HelpCard variant="info" title="Certificate Revocation" compact>
        OCSP provides real-time status checks. CRL is a periodic list of revoked certificates. 
        Enable both for maximum compatibility.
      </HelpCard>

      <div>
        <h3 className="text-sm font-semibold text-text-primary mb-4">OCSP Configuration</h3>

        <div className="space-y-4">
          <label className="flex items-center gap-3 cursor-pointer p-3 bg-bg-tertiary border border-border rounded-sm hover:border-accent-primary/50 transition-colors">
            <input
              type="checkbox"
              checked={ocspEnabled}
              onChange={(e) => setOcspEnabled(e.target.checked)}
              className="w-4 h-4 rounded border-border bg-bg-primary accent-accent-primary"
            />
            <div className="flex-1">
              <p className="text-sm text-text-primary font-medium">Enable OCSP Responder</p>
              <p className="text-xs text-text-secondary">Allow OCSP requests for certificates issued by this CA</p>
            </div>
          </label>

          {ocspEnabled && (
            <Input
              label="OCSP Responder URL"
              value={ocspUrl}
              onChange={(e) => setOcspUrl(e.target.value)}
              placeholder="http://ocsp.example.com/ocsp"
              helperText="URL that will be embedded in issued certificates for OCSP checking"
            />
          )}
        </div>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-text-primary mb-4">CRL Distribution Point (CDP)</h3>

        <div className="space-y-4">
          <label className="flex items-center gap-3 cursor-pointer p-3 bg-bg-tertiary border border-border rounded-sm hover:border-accent-primary/50 transition-colors">
            <input
              type="checkbox"
              checked={cdpEnabled}
              onChange={(e) => setCdpEnabled(e.target.checked)}
              className="w-4 h-4 rounded border-border bg-bg-primary accent-accent-primary"
            />
            <div className="flex-1">
              <p className="text-sm text-text-primary font-medium">Enable CRL Distribution Point</p>
              <p className="text-xs text-text-secondary">Include CDP URL in issued certificates</p>
            </div>
          </label>

          {cdpEnabled && (
            <Input
              label="CRL Distribution Point URL"
              value={cdpUrl}
              onChange={(e) => setCdpUrl(e.target.value)}
              placeholder="http://crl.example.com/ca.crl"
              helperText="URL where the CRL can be downloaded"
            />
          )}
        </div>
      </div>

      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button variant="primary" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving...' : 'Save Settings'}
        </Button>
      </div>
    </div>
  )
}

export default function CAsPage() {
  const { showSuccess, showError, showConfirm, showPrompt } = useNotification()
  const { canWrite, canDelete } = usePermission()
  const [searchParams, setSearchParams] = useSearchParams()
  
  const [cas, setCAs] = useState([])
  const [treeRoots, setTreeRoots] = useState([])
  const [treeOrphans, setTreeOrphans] = useState([])
  const [selectedCA, setSelectedCA] = useState(null)
  const [issuedCerts, setIssuedCerts] = useState([])
  const [loading, setLoading] = useState(true)
  const [viewMode, setViewMode] = useState('tree') // 'tree' or 'grid'
  const { modals, open: openModal, close: closeModal } = useModals(['create', 'import'])
  const [searchQuery, setSearchQuery] = useState('')
  const [createFormType, setCreateFormType] = useState('root')
  const [importFile, setImportFile] = useState(null)
  const [importName, setImportName] = useState('')
  const [importPassword, setImportPassword] = useState('')
  const [importing, setImporting] = useState(false)
  const importFileRef = useRef(null)

  useEffect(() => {
    loadCAs()
    if (searchParams.get('action') === 'create') {
      openModal('create')
      searchParams.delete('action')
      setSearchParams(searchParams)
    }
  }, [])

  // Handle selected param from navigation (e.g., after import redirect)
  useEffect(() => {
    const selectedId = searchParams.get('selected')
    if (selectedId && cas.length > 0) {
      const ca = cas.find(c => c.id === parseInt(selectedId))
      if (ca) {
        setSelectedCA(ca)
        searchParams.delete('selected')
        setSearchParams(searchParams)
      }
    }
  }, [cas, searchParams])

  const loadCAs = async () => {
    setLoading(true)
    try {
      const [casData, treeDataRes] = await Promise.all([
        casService.getAll(),
        casService.getTree(),
      ])
      
      // API returns {data: [...], meta: {...}}
      const casList = casData.data || []
      setCAs(casList)
      
      // Tree API returns {data: {roots: [], orphans: []}}
      const roots = treeDataRes.data?.roots || []
      const orphans = treeDataRes.data?.orphans || []
      setTreeRoots(buildTreeNodes(roots))
      setTreeOrphans(buildTreeNodes(orphans))
      
      if (casList.length > 0 && !selectedCA) {
        loadCADetails(casList[0].id)
      }
    } catch (error) {
      showError(error.message || 'Failed to load CAs')
    } finally {
      setLoading(false)
    }
  }

  const buildTreeNodes = (nodes) => {
    return nodes.map(node => ({
      id: node.id,
      name: node.name,
      icon: getCAIcon(node.type),
      badge: node.issued_count ? node.issued_count.toString() : undefined,
      type: node.type,
      children: node.children ? buildTreeNodes(node.children) : undefined,
    }))
  }

  const getCAIcon = (type) => {
    switch (type) {
      case 'root':
        return <Crown size={16} weight="duotone" className="text-yellow-500" />
      case 'intermediate':
        return <ShieldCheck size={16} weight="duotone" className="text-blue-500" />
      default:
        return <Key size={16} weight="duotone" className="text-green-500" />
    }
  }

  const loadCADetails = async (id) => {
    try {
      const [caData, certsData] = await Promise.all([
        casService.getById(id),
        casService.getCertificates(id, { page: 1, per_page: 10 }),
      ])
      
      setSelectedCA(extractData(caData))
      setIssuedCerts(extractData(certsData) || [])
    } catch (error) {
      showError(error.message || 'Failed to load CA details')
    }
  }

  const handleDelete = async (id) => {
    const confirmed = await showConfirm('Are you sure you want to delete this CA? This action cannot be undone.', {
      title: 'Delete Certificate Authority',
      confirmText: 'Delete CA',
      variant: 'danger'
    })
    if (!confirmed) return
    
    try {
      await casService.delete(id)
      showSuccess('CA deleted successfully')
      loadCAs()
      setSelectedCA(null)
    } catch (error) {
      showError(error.message || 'Failed to delete CA')
    }
  }

  const handleImportCA = async () => {
    if (!importFile) {
      showError('Please select a file')
      return
    }
    setImporting(true)
    try {
      const formData = new FormData()
      formData.append('file', importFile)
      if (importName) formData.append('name', importName)
      if (importPassword) formData.append('password', importPassword)
      formData.append('format', 'auto')
      
      const result = await casService.import(formData)
      showSuccess(result.message || 'CA imported successfully')
      closeModal('import')
      setImportFile(null)
      setImportName('')
      setImportPassword('')
      await loadCAs()
      
      // Auto-select the imported CA to show details
      if (result.data) {
        setSelectedCA(result.data)
      }
    } catch (error) {
      showError(error.message || 'Failed to import CA')
    } finally {
      setImporting(false)
    }
  }

  const handleExport = async (format = 'pem', options = {}) => {
    if (!selectedCA) return
    try {
      const blob = await casService.export(selectedCA.id, format, options)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const ext = format === 'pkcs12' ? 'p12' : format === 'der' ? 'der' : 'pem'
      a.download = `${selectedCA.name || selectedCA.common_name || 'ca'}.${ext}`
      a.click()
      URL.revokeObjectURL(url)
      showSuccess('CA exported successfully')
    } catch (error) {
      showError(error.message || 'Failed to export CA')
    }
  }

  const certColumns = [
    { key: 'common_name', label: 'Common Name' },
    { key: 'serial_number', label: 'Serial' },
    { key: 'valid_to', label: 'Expires', render: (val) => val ? new Date(val).toLocaleDateString() : '-' },
    { 
      key: 'status', 
      label: 'Status',
      render: (val) => <Badge variant={val === 'valid' ? 'success' : 'warning'}>{val}</Badge>
    },
  ]

  const detailTabs = selectedCA ? [
    {
      id: 'overview',
      label: 'Overview',
      icon: <ShieldCheck size={16} />,
      content: (
        <div className="space-y-6">
          {/* Type & Status */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-xs text-text-secondary uppercase mb-1">Type</p>
              <div className="flex items-center gap-2">
                {getCAIcon(selectedCA.type)}
                <Badge variant={selectedCA.type === 'root' ? 'primary' : 'secondary'}>
                  {selectedCA.type}
                </Badge>
              </div>
            </div>
            <div>
              <p className="text-xs text-text-secondary uppercase mb-1">Status</p>
              <Badge variant={selectedCA.status === 'Active' ? 'success' : 'danger'}>
                {selectedCA.status}
              </Badge>
            </div>
          </div>

          {/* Subject Information */}
          <div>
            <h3 className="text-sm font-semibold text-text-primary mb-3">Subject Information</h3>
            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <p className="text-xs text-text-secondary uppercase mb-1">Common Name (CN)</p>
                <p className="text-sm text-text-primary font-medium">{selectedCA.common_name || 'N/A'}</p>
              </div>
              {selectedCA.organization && (
                <div className="col-span-2">
                  <p className="text-xs text-text-secondary uppercase mb-1">Organization (O)</p>
                  <p className="text-sm text-text-primary">{selectedCA.organization}</p>
                </div>
              )}
              {selectedCA.organizational_unit && (
                <div className="col-span-2">
                  <p className="text-xs text-text-secondary uppercase mb-1">Organizational Unit (OU)</p>
                  <p className="text-sm text-text-primary">{selectedCA.organizational_unit}</p>
                </div>
              )}
              <div>
                <p className="text-xs text-text-secondary uppercase mb-1">Country (C)</p>
                <p className="text-sm text-text-primary">{selectedCA.country || 'N/A'}</p>
              </div>
              <div>
                <p className="text-xs text-text-secondary uppercase mb-1">State (ST)</p>
                <p className="text-sm text-text-primary">{selectedCA.state || 'N/A'}</p>
              </div>
              <div className="col-span-2">
                <p className="text-xs text-text-secondary uppercase mb-1">Locality (L)</p>
                <p className="text-sm text-text-primary">{selectedCA.locality || 'N/A'}</p>
              </div>
            </div>
          </div>

          {/* Certificate Details */}
          <div>
            <h3 className="text-sm font-semibold text-text-primary mb-3">Certificate Details</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-text-secondary uppercase mb-1">Serial Number</p>
                <p className="text-sm font-mono text-text-primary">{selectedCA.serial || 'N/A'}</p>
              </div>
              <div>
                <p className="text-xs text-text-secondary uppercase mb-1">Issued Certificates</p>
                <p className="text-sm text-text-primary">{selectedCA.certs || 0} certificates</p>
              </div>
              <div>
                <p className="text-xs text-text-secondary uppercase mb-1">Valid From</p>
                <p className="text-sm text-text-primary">{formatDate(selectedCA.valid_from)}</p>
              </div>
              <div>
                <p className="text-xs text-text-secondary uppercase mb-1">Valid Until</p>
                <p className="text-sm text-text-primary">{formatDate(selectedCA.valid_to)}</p>
              </div>
              <div>
                <p className="text-xs text-text-secondary uppercase mb-1">Key Algorithm</p>
                <p className="text-sm text-text-primary">{selectedCA.key_algorithm || selectedCA.key_type || 'N/A'}</p>
              </div>
              <div>
                <p className="text-xs text-text-secondary uppercase mb-1">Signature Algorithm</p>
                <p className="text-sm text-text-primary">{selectedCA.signature_algorithm || selectedCA.hash_algorithm || 'N/A'}</p>
              </div>
              <div>
                <p className="text-xs text-text-secondary uppercase mb-1">Private Key</p>
                <Badge variant={selectedCA.has_private_key ? 'success' : 'warning'}>
                  {selectedCA.has_private_key ? 'Available' : 'Not Available'}
                </Badge>
              </div>
              {selectedCA.caref && (
                <div>
                  <p className="text-xs text-text-secondary uppercase mb-1">Parent CA</p>
                  <p className="text-sm text-text-primary">{selectedCA.caref}</p>
                </div>
              )}
            </div>
          </div>

          {/* CRL & OCSP Configuration */}
          {(selectedCA.cdp_enabled || selectedCA.ocsp_enabled) && (
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-3">Revocation Services</h3>
              <div className="space-y-3">
                {selectedCA.cdp_enabled && (
                  <div className="p-3 bg-bg-tertiary border border-border rounded-lg">
                    <div className="flex items-center gap-2 mb-2">
                      <Badge variant="success">CRL Enabled</Badge>
                    </div>
                    <p className="text-xs text-text-secondary uppercase mb-1">CRL Distribution Point</p>
                    <p className="text-xs font-mono text-text-primary break-all">
                      {selectedCA.cdp_url || 'Not configured'}
                    </p>
                  </div>
                )}
                {selectedCA.ocsp_enabled && (
                  <div className="p-3 bg-bg-tertiary border border-border rounded-lg">
                    <div className="flex items-center gap-2 mb-2">
                      <Badge variant="success">OCSP Enabled</Badge>
                    </div>
                    <p className="text-xs text-text-secondary uppercase mb-1">OCSP Responder URL</p>
                    <p className="text-xs font-mono text-text-primary break-all">
                      {selectedCA.ocsp_url || 'Not configured'}
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Full Subject/Issuer DN */}
          <div className="p-4 bg-bg-tertiary border border-border rounded-lg">
            <p className="text-xs text-text-secondary uppercase mb-2">Full Subject DN</p>
            <p className="text-xs font-mono text-text-primary break-all mb-4">
              {selectedCA.subject}
            </p>
            <p className="text-xs text-text-secondary uppercase mb-2">Issuer DN</p>
            <p className="text-xs font-mono text-text-primary break-all">
              {selectedCA.issuer}
            </p>
          </div>
        </div>
      )
    },
    {
      id: 'issued',
      label: 'Issued Certificates',
      icon: <Certificate size={16} />,
      content: (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-text-secondary">
              {issuedCerts.length} certificates issued by this CA
            </p>
            <Button size="sm">
              <Certificate size={16} />
              Issue New
            </Button>
          </div>
          
          {issuedCerts.length === 0 ? (
            <EmptyState
              icon={Certificate}
              title="No certificates issued"
              description="Issue your first certificate with this CA"
            />
          ) : (
            <Table
              columns={certColumns}
              data={issuedCerts}
              onRowClick={(cert) => window.location.href = `/certificates?id=${cert.id}`}
            />
          )}
        </div>
      )
    },
    {
      id: 'settings',
      label: 'Settings',
      content: (
        <div className="space-y-4">
          <div>
            <p className="text-sm font-medium text-text-primary mb-2">Default Validity Period</p>
            <Input 
              type="number" 
              value={selectedCA.default_validity_days || 365}
              disabled
              helperText="Days"
            />
          </div>
          <div>
            <p className="text-sm font-medium text-text-primary mb-2">CRL Distribution Points</p>
            <Input 
              value={selectedCA.crl_distribution_points || ''}
              disabled
              placeholder="http://example.com/ca.crl"
            />
          </div>
          <div>
            <p className="text-sm font-medium text-text-primary mb-2">OCSP Responder URL</p>
            <Input 
              value={selectedCA.ocsp_url || ''}
              disabled
              placeholder="http://ocsp.example.com"
            />
          </div>
        </div>
      )
    },
    {
      id: 'export',
      label: 'Export',
      content: (
        <div className="space-y-4">
          <p className="text-sm text-text-secondary">
            Export this Certificate Authority in various formats
          </p>
          <div className="flex flex-wrap gap-3">
            <Button onClick={() => handleExport('pem', {})}>
              <Download size={16} />
              PEM (Certificate only)
            </Button>
            <Button variant="secondary" onClick={() => handleExport('pem', { includeKey: true })}>
              <Download size={16} />
              PEM + Private Key
            </Button>
            <Button variant="secondary" onClick={() => handleExport('pem', { includeChain: true })}>
              <Download size={16} />
              PEM + CA Chain
            </Button>
            <Button variant="secondary" onClick={() => handleExport('der', {})}>
              <Download size={16} />
              DER Format
            </Button>
            <Button variant="secondary" onClick={async () => {
              const password = await showPrompt('Enter password for PKCS#12 file:', {
                title: 'Export PKCS#12',
                type: 'password',
                placeholder: 'Password',
                confirmText: 'Export'
              })
              if (password) handleExport('pkcs12', { password })
            }}>
              <Download size={16} />
              PKCS#12 (.p12)
            </Button>
          </div>
          
          <div className="mt-6 p-4 bg-bg-tertiary border border-border rounded-lg">
            <p className="text-xs text-text-secondary uppercase mb-2">Certificate Fingerprints</p>
            <div className="space-y-2">
              <div>
                <p className="text-xs text-text-secondary">SHA-256</p>
                <p className="text-xs font-mono text-text-primary break-all">
                  {selectedCA.fingerprint_sha256}
                </p>
              </div>
              <div>
                <p className="text-xs text-text-secondary">SHA-1</p>
                <p className="text-xs font-mono text-text-primary break-all">
                  {selectedCA.fingerprint_sha1}
                </p>
              </div>
            </div>
          </div>
        </div>
      )
    },
    {
      id: 'raw',
      label: 'Raw Data',
      content: (
        <div className="space-y-6">
          <div>
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-medium text-text-primary">PEM Format</p>
              <Button 
                variant="secondary" 
                size="sm"
                onClick={() => {
                  navigator.clipboard.writeText(selectedCA.pem || '')
                  showSuccess('PEM copied to clipboard')
                }}
                disabled={!selectedCA.pem}
              >
                Copy PEM
              </Button>
            </div>
            <pre className="bg-bg-tertiary border border-border rounded-lg p-4 text-xs overflow-x-auto max-h-64">
              {selectedCA.pem || 'PEM data not available'}
            </pre>
          </div>
          <div className="p-4 bg-bg-tertiary border border-border rounded-lg">
            <p className="text-xs text-text-secondary uppercase mb-2">Full Subject DN</p>
            <p className="text-xs font-mono text-text-primary break-all">
              {selectedCA.subject}
            </p>
          </div>
          <div className="p-4 bg-bg-tertiary border border-border rounded-lg">
            <p className="text-xs text-text-secondary uppercase mb-2">Full Issuer DN</p>
            <p className="text-xs font-mono text-text-primary break-all">
              {selectedCA.issuer}
            </p>
          </div>
        </div>
      )
    },
    {
      id: 'ocsp',
      label: 'OCSP',
      icon: <ShieldCheck size={16} />,
      content: <OCSPSettingsTab ca={selectedCA} onUpdate={loadCAs} showSuccess={showSuccess} showError={showError} />
    }
  ] : []

  const filteredCAs = cas.filter(ca =>
    ca.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    ca.subject?.toLowerCase().includes(searchQuery.toLowerCase())
  )

  // Calculate stats for help content
  const rootCAs = cas.filter(ca => ca.type === 'root').length
  const intermediateCAs = cas.filter(ca => ca.type === 'intermediate').length
  const totalCerts = cas.reduce((sum, ca) => sum + (ca.certs || 0), 0)

  // Help content for modal
  const helpContent = (
    <div className="space-y-4">
      {/* CA Statistics */}
      <Card className="p-4 space-y-3 bg-gradient-to-br from-accent-primary/5 to-transparent">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Database size={16} className="text-accent-primary" />
          CA Statistics
        </h3>
        <div className="grid grid-cols-3 gap-3">
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-yellow-500">{rootCAs}</p>
            <p className="text-xs text-text-secondary">Root CAs</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-blue-500">{intermediateCAs}</p>
            <p className="text-xs text-text-secondary">Intermediate</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-text-primary">{totalCerts}</p>
            <p className="text-xs text-text-secondary">Certificates</p>
          </div>
        </div>
      </Card>

      {/* Help Cards */}
      <div className="space-y-3">
        <HelpCard variant="info" title="About CAs">
          Certificate Authorities (CAs) are trusted entities that issue digital certificates.
          Root CAs are self-signed. Intermediate CAs are signed by their parent CA.
        </HelpCard>
        
        <HelpCard variant="tip" title="Best Practices">
          Keep your Root CA offline and use Intermediate CAs for issuing end-entity certificates.
          This limits exposure if an Intermediate CA is compromised.
        </HelpCard>

        <HelpCard variant="warning" title="Private Keys">
          Private keys should be protected. Consider using HSM (Hardware Security Module) 
          for production Root CAs to ensure maximum security.
        </HelpCard>
      </div>
    </div>
  )

  // Focus panel content (search + tree/list view)
  const focusContent = (
    <div className="flex flex-col h-full">
      {/* Search */}
      <div className="p-3 border-b border-border">
        <div className="relative">
          <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary" />
          <input
            type="text"
            placeholder="Search CAs..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-2 text-sm bg-bg-tertiary border border-border rounded-md focus:outline-none focus:border-accent-primary text-text-primary placeholder:text-text-tertiary"
          />
        </div>
      </div>

      {/* View mode toggle */}
      <div className="p-3 border-b border-border">
        <div className="flex gap-2">
          <Tooltip content="Tree View">
            <button
              onClick={() => setViewMode('tree')}
              className={`flex-1 p-2 rounded-lg transition-colors ${
                viewMode === 'tree' 
                  ? 'bg-accent-primary text-white' 
                  : 'bg-bg-tertiary text-text-secondary hover:text-text-primary'
              }`}
            >
              <Tree size={18} className="mx-auto" />
            </button>
          </Tooltip>
          <Tooltip content="Grid View">
            <button
              onClick={() => setViewMode('grid')}
              className={`flex-1 p-2 rounded-lg transition-colors ${
                viewMode === 'grid' 
                  ? 'bg-accent-primary text-white' 
                  : 'bg-bg-tertiary text-text-secondary hover:text-text-primary'
              }`}
            >
              <SquaresFour size={18} className="mx-auto" />
            </button>
          </Tooltip>
        </div>
      </div>

      {/* CA list/tree */}
      <div className="flex-1 overflow-auto p-2">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <LoadingSpinner />
          </div>
        ) : viewMode === 'tree' ? (
          (treeRoots.length === 0 && treeOrphans.length === 0) ? (
            <EmptyState
              icon={ShieldCheck}
              title="No CAs yet"
              description="Create your first Certificate Authority"
            />
          ) : (
            <div className="space-y-4">
              {/* Root CAs Section */}
              {treeRoots.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-text-secondary uppercase px-2 mb-2 flex items-center gap-2">
                    <Crown size={14} className="text-yellow-500" />
                    Root CAs ({treeRoots.length})
                  </p>
                  <TreeView
                    nodes={treeRoots}
                    selectedId={selectedCA?.id}
                    onSelect={(node) => loadCADetails(node.id)}
                  />
                </div>
              )}
              
              {/* Orphaned/Intermediate CAs Section */}
              {treeOrphans.length > 0 && (
                <div className="pt-2 border-t border-border">
                  <p className="text-xs font-semibold text-text-secondary uppercase px-2 mb-2 flex items-center gap-2">
                    <ShieldCheck size={14} className="text-orange-500" />
                    Orphaned CAs ({treeOrphans.length})
                  </p>
                  <TreeView
                    nodes={treeOrphans}
                    selectedId={selectedCA?.id}
                    onSelect={(node) => loadCADetails(node.id)}
                  />
                </div>
              )}
            </div>
          )
        ) : (
          <div className="space-y-1.5">
            {filteredCAs.length === 0 ? (
              <EmptyState
                icon={ShieldCheck}
                title="No CAs found"
                description={searchQuery ? "Try a different search" : "Create your first CA"}
              />
            ) : (
              filteredCAs.map((ca) => (
                <FocusItem
                  key={ca.id}
                  icon={ca.type === 'root' ? Crown : ShieldCheck}
                  title={ca.name}
                  subtitle={ca.subject}
                  badge={<Badge variant={ca.type === 'root' ? 'primary' : 'secondary'} size="sm">{ca.type}</Badge>}
                  selected={selectedCA?.id === ca.id}
                  onClick={() => loadCADetails(ca.id)}
                />
              ))
            )}
          </div>
        )}
      </div>
    </div>
  )

  // Focus actions (create and import buttons)
  const focusActions = canWrite('cas') && (
    <>
      <Button onClick={() => openModal('create')} size="sm" className="flex-1">
        <ShieldCheck size={16} />
        Create
      </Button>
      <Button variant="secondary" size="sm" onClick={() => openModal('import')}>
        <UploadSimple size={16} />
        Import
      </Button>
    </>
  )

  if (loading && cas.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner />
      </div>
    )
  }

  return (
    <>
      <PageLayout
        title="Certificate Authorities"
        focusTitle="CAs"
        focusContent={focusContent}
        focusActions={focusActions}
        focusFooter={`${cas.length} CA(s)`}
        helpContent={helpContent}
        helpTitle="Certificate Authorities - Aide"
      >
        {/* Main Content (CA details) */}
        {!selectedCA ? (
          <div className="flex items-center justify-center h-full">
            <EmptyState
              icon={ShieldCheck}
              title="No CA selected"
              description="Select a Certificate Authority from the list"
            />
          </div>
        ) : (
          <div className="flex flex-col h-full">
            {/* Header with breadcrumb and actions */}
            <div className="px-6 py-4 border-b border-border bg-bg-secondary flex items-center justify-between shrink-0">
              <div>
                <p className="text-xs text-text-secondary mb-1">CAs / {selectedCA.name || '...'}</p>
                <h2 className="text-lg font-semibold text-text-primary">{selectedCA.name || 'Select a CA'}</h2>
              </div>
              <div className="flex items-center gap-2">
                {canWrite('cas') && (
                  <Button variant="secondary" size="sm">
                    <PencilSimple size={16} />
                    Edit
                  </Button>
                )}
                <ExportDropdown 
                  onExport={handleExport}
                  hasPrivateKey={!!selectedCA.prv || selectedCA.has_key}
                />
                {canDelete('cas') && (
                  <Button variant="danger" size="sm" onClick={() => handleDelete(selectedCA.id)}>
                    <Trash size={16} />
                    Delete
                  </Button>
                )}
              </div>
            </div>

            {/* Tabs content */}
            <div className="flex-1 overflow-auto p-6">
              <Tabs tabs={detailTabs} defaultTab="overview" />
            </div>
          </div>
        )}
      </PageLayout>

      {/* Create CA Modal */}
      <Modal
        open={modals.create}
        onClose={() => closeModal('create')}
        title="Create Certificate Authority"
        size="lg"
      >
        <form onSubmit={async (e) => {
          e.preventDefault()
          const formData = new FormData(e.target)
          const data = {
            commonName: formData.get('commonName'),
            organization: formData.get('organization'),
            country: formData.get('country'),
            state: formData.get('state'),
            locality: formData.get('locality'),
            keyAlgo: formData.get('keyAlgo'),
            keySize: parseInt(formData.get('keySize')),
            validityYears: parseInt(formData.get('validityYears')),
            type: formData.get('type'),
            parentCAId: formData.get('type') === 'intermediate' ? formData.get('parentCAId') : null
          }
          
          try {
            await casService.create(data)
            showSuccess('CA created successfully')
            closeModal('create')
            loadCAs()
          } catch (error) {
            showError(error.message || 'Failed to create CA')
          }
        }} className="space-y-6">
          
          {/* Subject Information */}
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-text-primary">Subject Information</h3>
            
            <Input
              name="commonName"
              label="Common Name (CN)"
              placeholder="My Certificate Authority"
              required
            />
            
            <div className="grid grid-cols-2 gap-4">
              <Input
                name="organization"
                label="Organization (O)"
                placeholder="My Company"
              />
              <Input
                name="country"
                label="Country (C)"
                placeholder="US"
                maxLength={2}
              />
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              <Input
                name="state"
                label="State/Province (ST)"
                placeholder="California"
              />
              <Input
                name="locality"
                label="City/Locality (L)"
                placeholder="San Francisco"
              />
            </div>
          </div>

          {/* Key Configuration */}
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-text-primary">Key Configuration</h3>
            
            <div className="grid grid-cols-2 gap-4">
              <Select
                name="keyAlgo"
                label="Key Algorithm"
                options={[
                  { value: 'RSA', label: 'RSA' },
                  { value: 'ECDSA', label: 'ECDSA' }
                ]}
                defaultValue="RSA"
              />
              
              <Select
                name="keySize"
                label="Key Size"
                options={[
                  { value: '2048', label: '2048 bits' },
                  { value: '3072', label: '3072 bits' },
                  { value: '4096', label: '4096 bits' }
                ]}
                defaultValue="2048"
              />
            </div>
          </div>

          {/* Validity */}
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-text-primary">Validity</h3>
            
            <Select
              name="validityYears"
              label="Validity Period"
              options={[
                { value: '5', label: '5 years' },
                { value: '10', label: '10 years' },
                { value: '15', label: '15 years' },
                { value: '20', label: '20 years' }
              ]}
              defaultValue="10"
            />
          </div>

          {/* Type */}
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-text-primary">CA Type</h3>
            
            <Select
              name="type"
              label="Type"
              options={[
                { value: 'root', label: 'Root CA (Self-signed)' },
                { value: 'intermediate', label: 'Intermediate CA (Signed by parent)' }
              ]}
              value={createFormType}
              onChange={(value) => setCreateFormType(value)}
            />
            
            {/* Parent CA selector - only show if intermediate */}
            {createFormType === 'intermediate' && (
              <Select
                name="parentCAId"
                label="Parent CA"
                options={cas.map(ca => ({
                  value: ca.id.toString(),
                  label: ca.name || ca.descr
                }))}
                required
              />
            )}
          </div>

          {/* Actions */}
          <div className="flex gap-3 justify-end pt-4 border-t border-border">
            <Button
              type="button"
              variant="secondary"
              onClick={() => closeModal('create')}
            >
              Cancel
            </Button>
            <Button type="submit">
              Create CA
            </Button>
          </div>
        </form>
      </Modal>

      {/* Import CA Modal */}
      <Modal
        open={modals.import}
        onClose={() => closeModal('import')}
        title="Import CA"
        size="md"
      >
        <div className="space-y-4">
          <p className="text-sm text-text-secondary">
            Import an existing CA certificate from a file. Supports PEM, DER, and PKCS#12 formats.
          </p>
          
          <div>
            <label className="block text-xs font-medium text-text-primary mb-1">CA Certificate File</label>
            <input
              ref={importFileRef}
              type="file"
              accept=".pem,.crt,.cer,.der,.p12,.pfx"
              onChange={(e) => setImportFile(e.target.files[0])}
              className="w-full text-sm text-text-secondary file:mr-4 file:py-1.5 file:px-3 file:rounded-sm file:border-0 file:text-sm file:bg-accent-primary file:text-white hover:file:bg-accent-primary/80"
            />
            <p className="text-xs text-text-secondary mt-1">Accepted: .pem, .crt, .cer, .der, .p12, .pfx</p>
          </div>
          
          <Input 
            label="Display Name (optional)" 
            value={importName}
            onChange={(e) => setImportName(e.target.value)}
            placeholder="My Root CA"
          />
          
          <Input 
            label="Password (for PKCS#12)" 
            type="password"
            value={importPassword}
            onChange={(e) => setImportPassword(e.target.value)}
            placeholder="Enter password if needed"
          />
          
          <div className="flex gap-3 justify-end pt-4 border-t border-border">
            <Button
              variant="secondary"
              onClick={() => closeModal('import')}
            >
              Cancel
            </Button>
            <Button onClick={handleImportCA} disabled={importing || !importFile}>
              {importing ? <LoadingSpinner size="sm" /> : <UploadSimple size={16} />}
              Import CA
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}
