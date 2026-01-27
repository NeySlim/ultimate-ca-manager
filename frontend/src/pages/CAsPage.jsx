/**
 * CAs (Certificate Authorities) Page
 */
import { useState, useEffect } from 'react'
import { 
  ShieldCheck, Crown, Key, Download, Trash, PencilSimple,
  Tree, SquaresFour, Certificate
} from '@phosphor-icons/react'
import {
  ExplorerPanel, DetailsPanel, TreeView, Table, Button, 
  Badge, Modal, Input, Select, ExportDropdown,
  Tabs, LoadingSpinner, EmptyState, Tooltip
} from '../components'
import { casService } from '../services'
import { useNotification } from '../contexts'
import { extractCN, extractData, formatDate, formatDateTime } from '../lib/utils'

export default function CAsPage() {
  const { showSuccess, showError } = useNotification()
  
  const [cas, setCAs] = useState([])
  const [treeData, setTreeData] = useState([])
  const [selectedCA, setSelectedCA] = useState(null)
  const [issuedCerts, setIssuedCerts] = useState([])
  const [loading, setLoading] = useState(true)
  const [viewMode, setViewMode] = useState('tree') // 'tree' or 'grid'
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  useEffect(() => {
    loadCAs()
  }, [])

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
      const treeRoots = treeDataRes.data?.roots || []
      const treeOrphans = treeDataRes.data?.orphans || []
      setTreeData(buildTreeNodes([...treeRoots, ...treeOrphans]))
      
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
    if (!confirm('Are you sure you want to delete this CA? This action cannot be undone.')) {
      return
    }
    
    try {
      await casService.delete(id)
      showSuccess('CA deleted successfully')
      loadCAs()
      setSelectedCA(null)
    } catch (error) {
      showError(error.message || 'Failed to delete CA')
    }
  }

  const handleExport = async (id, format = 'pem') => {
    try {
      const blob = await casService.export(id, format)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `ca.${format}`
      a.click()
      showSuccess('CA exported successfully')
    } catch (error) {
      showError(error.message || 'Failed to export CA')
    }
  }

  const certColumns = [
    { key: 'common_name', label: 'Common Name' },
    { key: 'serial_number', label: 'Serial' },
    { key: 'valid_to', label: 'Expires', render: (val) => new Date(val).toLocaleDateString() },
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
              onRowClick={(cert) => console.log('View cert:', cert.id)}
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
            <Button onClick={() => handleExport(selectedCA.id, 'pem')}>
              <Download size={16} />
              PEM Format
            </Button>
            <Button variant="secondary" onClick={() => handleExport(selectedCA.id, 'der')}>
              <Download size={16} />
              DER Format
            </Button>
            <Button variant="secondary" onClick={() => handleExport(selectedCA.id, 'p12')}>
              <Download size={16} />
              PKCS#12 (with private key)
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
      id: 'ocsp',
      label: 'OCSP',
      icon: <ShieldCheck size={16} />,
      content: (
        <div className="space-y-6">
          <div>
            <h3 className="text-sm font-semibold text-text-primary mb-4">OCSP Configuration</h3>
            <p className="text-sm text-text-secondary mb-4">
              Configure Online Certificate Status Protocol (OCSP) settings for real-time certificate revocation checking.
            </p>

            <div className="space-y-4">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  defaultChecked={false}
                  className="rounded border-border bg-bg-tertiary"
                />
                <div>
                  <p className="text-sm text-text-primary font-medium">Enable OCSP Responder</p>
                  <p className="text-xs text-text-secondary">Allow OCSP requests for this CA</p>
                </div>
              </label>

              <Input
                label="OCSP Responder URL"
                value={`${window.location.origin}/ocsp/${selectedCA.refid}`}
                readOnly
                helperText="URL for OCSP clients to check certificate status"
                className="bg-bg-tertiary"
              />

              <Input
                label="Response Validity (hours)"
                type="number"
                defaultValue="24"
                min="1"
                max="168"
                helperText="How long OCSP responses remain valid (1-168 hours)"
              />

              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  defaultChecked={true}
                  className="rounded border-border bg-bg-tertiary"
                />
                <div>
                  <p className="text-sm text-text-primary font-medium">Include Next Update</p>
                  <p className="text-xs text-text-secondary">Add nextUpdate field to OCSP responses</p>
                </div>
              </label>

              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  defaultChecked={false}
                  className="rounded border-border bg-bg-tertiary"
                />
                <div>
                  <p className="text-sm text-text-primary font-medium">Require Nonce</p>
                  <p className="text-xs text-text-secondary">Prevent replay attacks (recommended)</p>
                </div>
              </label>

              <div className="p-4 bg-bg-tertiary border border-border rounded-sm">
                <h4 className="text-xs font-semibold text-text-primary uppercase mb-2">OCSP Statistics</h4>
                <div className="grid grid-cols-3 gap-4 text-sm">
                  <div>
                    <p className="text-text-secondary text-xs">Total Requests</p>
                    <p className="text-text-primary font-semibold">-</p>
                  </div>
                  <div>
                    <p className="text-text-secondary text-xs">Good Responses</p>
                    <p className="text-text-primary font-semibold">-</p>
                  </div>
                  <div>
                    <p className="text-text-secondary text-xs">Revoked Responses</p>
                    <p className="text-text-primary font-semibold">-</p>
                  </div>
                </div>
              </div>

              <div className="flex gap-3 pt-4 border-t border-border">
                <Button onClick={() => showSuccess('OCSP settings saved')}>
                  Save OCSP Settings
                </Button>
              </div>
            </div>
          </div>
        </div>
      )
    }
  ] : []

  const filteredCAs = cas.filter(ca =>
    ca.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    ca.subject?.toLowerCase().includes(searchQuery.toLowerCase())
  )

  return (
    <>
      <ExplorerPanel
        title="Certificate Authorities"
        searchable
        searchValue={searchQuery}
        onSearch={setSearchQuery}
        footer={
          <div className="text-xs text-text-secondary">
            {cas.length} total CAs
          </div>
        }
      >
        <div className="p-4 space-y-3">
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

          <Button onClick={() => setShowCreateModal(true)} className="w-full">
            <ShieldCheck size={18} />
            Create CA
          </Button>
        </div>

        <div className="flex-1 overflow-auto p-4">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <LoadingSpinner />
            </div>
          ) : viewMode === 'tree' ? (
            treeData.length === 0 ? (
              <EmptyState
                icon={ShieldCheck}
                title="No CAs yet"
                description="Create your first Certificate Authority"
              />
            ) : (
              <TreeView
                nodes={treeData}
                selectedId={selectedCA?.id}
                onSelect={(node) => loadCADetails(node.id)}
              />
            )
          ) : (
            <div className="space-y-2">
              {filteredCAs.map((ca) => (
                <div
                  key={ca.id}
                  onClick={() => loadCADetails(ca.id)}
                  className={`p-4 rounded-xl border cursor-pointer transition-all ${
                    selectedCA?.id === ca.id
                      ? 'bg-accent-primary/10 border-accent-primary'
                      : 'bg-bg-tertiary border-border hover:border-accent-primary/50'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    {getCAIcon(ca.type)}
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-text-primary truncate">{ca.name}</p>
                      <p className="text-xs text-text-secondary truncate">{ca.subject}</p>
                    </div>
                    <Badge variant={ca.type === 'root' ? 'primary' : 'secondary'}>
                      {ca.type}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </ExplorerPanel>

      <DetailsPanel
        breadcrumb={[
          { label: 'CAs' },
          { label: selectedCA?.name || '...' }
        ]}
        title={selectedCA?.name || 'Select a CA'}
        actions={selectedCA && (
          <>
            <Button variant="secondary" size="sm">
              <PencilSimple size={16} />
              Edit
            </Button>
            <ExportDropdown 
              onExport={(format) => handleExport(selectedCA.id, format)} 
              formats={['pem', 'der', 'pkcs12']}
            />
            <Button variant="danger" size="sm" onClick={() => handleDelete(selectedCA.id)}>
              <Trash size={16} />
              Delete
            </Button>
          </>
        )}
      >
        {!selectedCA ? (
          <EmptyState
            title="No CA selected"
            description="Select a Certificate Authority from the list"
          />
        ) : (
          <Tabs tabs={detailTabs} defaultTab="overview" />
        )}
      </DetailsPanel>

      {/* Create CA Modal */}
      <Modal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="Create Certificate Authority"
        size="lg"
      >
        <p className="text-text-secondary mb-4">CA creation form will be implemented here</p>
        <Button onClick={() => setShowCreateModal(false)}>Close</Button>
      </Modal>
    </>
  )
}
