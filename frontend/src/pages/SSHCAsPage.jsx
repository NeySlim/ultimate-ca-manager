/**
 * SSHCAsPage - SSH Certificate Authority management
 * Pattern: ResponsiveLayout + ResponsiveDataTable + Modal actions
 *
 * DESKTOP: Dense table with hover rows, inline slide-over details
 * MOBILE: Card-style list with full-screen details
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Key, Plus, Trash, PencilSimple, Download, Copy,
  ShieldCheck, User, Clock, Fingerprint, Terminal, Check
} from '@phosphor-icons/react'
import {
  ResponsiveLayout, ResponsiveDataTable, Badge, Button, Input, Select,
  FormModal,
  CompactSection, CompactGrid, CompactField, CompactHeader
} from '../components'
import { sshCasService } from '../services'
import { useNotification, useMobile } from '../contexts'
import { usePermission } from '../hooks'
import { formatDate } from '../lib/utils'

const KEY_ALGORITHM_OPTIONS = [
  { value: 'ed25519', label: 'Ed25519' },
  { value: 'rsa', label: 'RSA' },
  { value: 'ecdsa-p256', label: 'ECDSA P-256' },
  { value: 'ecdsa-p384', label: 'ECDSA P-384' },
  { value: 'ecdsa-p521', label: 'ECDSA P-521' },
]

const RSA_KEY_SIZE_OPTIONS = [
  { value: '2048', label: '2048' },
  { value: '4096', label: '4096' },
]

const DEFAULT_EXTENSIONS = [
  { value: 'permit-pty', labelKey: 'sshCas.extensions.permitPty' },
  { value: 'permit-agent-forwarding', labelKey: 'sshCas.extensions.permitAgentForwarding' },
  { value: 'permit-X11-forwarding', labelKey: 'sshCas.extensions.permitX11Forwarding' },
  { value: 'permit-port-forwarding', labelKey: 'sshCas.extensions.permitPortForwarding' },
  { value: 'permit-user-rc', labelKey: 'sshCas.extensions.permitUserRc' },
]

export default function SSHCAsPage() {
  const { t } = useTranslation()
  const { isMobile } = useMobile()
  const { showSuccess, showError, showConfirm } = useNotification()
  const { canWrite, canDelete } = usePermission()

  // Data
  const [sshCas, setSSHCAs] = useState([])
  const [loading, setLoading] = useState(true)

  // Selection
  const [selectedCA, setSelectedCA] = useState(null)

  // Modals
  const [showModal, setShowModal] = useState(false)
  const [editingCA, setEditingCA] = useState(null)

  // Pagination
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)

  // Filters
  const [filterType, setFilterType] = useState('')

  // Copy state
  const [copied, setCopied] = useState(false)

  // Load data
  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      setLoading(true)
      const res = await sshCasService.getAll()
      setSSHCAs(res.data || [])
    } catch (error) {
      showError(error.message || t('messages.errors.loadFailed.sshCas'))
    } finally {
      setLoading(false)
    }
  }

  // ============= ACTIONS =============

  const handleCreate = async (data) => {
    try {
      await sshCasService.create(data)
      showSuccess(t('messages.success.create.sshCa'))
      setShowModal(false)
      setEditingCA(null)
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.createFailed.sshCa'))
    }
  }

  const handleUpdate = async (data) => {
    try {
      await sshCasService.update(editingCA.id, data)
      showSuccess(t('messages.success.update.sshCa'))
      setShowModal(false)
      setEditingCA(null)
      loadData()
      if (selectedCA?.id === editingCA.id) {
        setSelectedCA({ ...selectedCA, ...data })
      }
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.sshCa'))
    }
  }

  const handleDelete = async (ca) => {
    const confirmed = await showConfirm(t('messages.confirm.delete.sshCa'), {
      title: t('sshCas.deleteCA'),
      confirmText: t('common.delete'),
      variant: 'danger'
    })
    if (!confirmed) return
    try {
      await sshCasService.delete(ca.id)
      showSuccess(t('messages.success.delete.sshCa'))
      if (selectedCA?.id === ca.id) setSelectedCA(null)
      loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.deleteFailed.sshCa'))
    }
  }

  const handleDownloadPublicKey = async (ca) => {
    try {
      const res = await sshCasService.getPublicKey(ca.id)
      const publicKey = res.data?.public_key || res.data
      const blob = new Blob([typeof publicKey === 'string' ? publicKey : JSON.stringify(publicKey)], { type: 'text/plain' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${ca.descr || 'ssh-ca'}_key.pub`
      a.click()
      URL.revokeObjectURL(url)
    } catch (error) {
      showError(error.message || t('messages.errors.downloadFailed.publicKey'))
    }
  }

  const handleDownloadKRL = async (ca) => {
    try {
      const blob = await sshCasService.getKRL(ca.id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${ca.descr || 'ssh-ca'}_krl.bin`
      a.click()
      URL.revokeObjectURL(url)
    } catch (error) {
      showError(error.message || t('messages.errors.downloadFailed.krl'))
    }
  }

  const handleCopyPublicKey = async (ca) => {
    try {
      const res = await sshCasService.getPublicKey(ca.id)
      const publicKey = res.data?.public_key || res.data
      await navigator.clipboard.writeText(typeof publicKey === 'string' ? publicKey : JSON.stringify(publicKey))
      setCopied(true)
      showSuccess(t('sshCas.publicKeyCopied'))
      setTimeout(() => setCopied(false), 2000)
    } catch (error) {
      showError(error.message || t('messages.errors.copyFailed.publicKey'))
    }
  }

  // ============= FILTERED DATA =============

  const filteredCAs = useMemo(() => {
    if (!filterType) return sshCas
    return sshCas.filter(ca => ca.ca_type === filterType)
  }, [sshCas, filterType])

  // ============= STATS =============

  const stats = useMemo(() => {
    const userCAs = sshCas.filter(ca => ca.ca_type === 'user').length
    const hostCAs = sshCas.filter(ca => ca.ca_type === 'host').length
    const totalCerts = sshCas.reduce((acc, ca) => acc + (ca.certificate_count || 0), 0)
    return [
      { icon: Key, label: t('sshCas.stats.total'), value: sshCas.length, variant: 'primary' },
      { icon: User, label: t('sshCas.stats.userCas'), value: userCAs, variant: 'teal' },
      { icon: ShieldCheck, label: t('sshCas.stats.hostCas'), value: hostCAs, variant: 'violet' },
      { icon: Terminal, label: t('sshCas.stats.certificates'), value: totalCerts, variant: 'default' },
    ]
  }, [sshCas, t])

  // ============= COLUMNS =============

  const columns = useMemo(() => [
    {
      key: 'descr',
      header: t('sshCas.description'),
      priority: 1,
      sortable: true,
      render: (val, row) => {
        const isUser = row.ca_type === 'user'
        return (
          <div className="flex items-center gap-2">
            <div className={`w-6 h-6 rounded-lg flex items-center justify-center shrink-0 ${
              isUser ? 'icon-bg-teal' : 'icon-bg-violet'
            }`}>
              {isUser ? <User size={14} weight="duotone" /> : <ShieldCheck size={14} weight="duotone" />}
            </div>
            <span className="font-medium truncate">{val || t('common.unnamed')}</span>
          </div>
        )
      },
      mobileRender: (val, row) => {
        const isUser = row.ca_type === 'user'
        return (
          <div className="flex items-center justify-between gap-2 w-full">
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <div className={`w-6 h-6 rounded-lg flex items-center justify-center shrink-0 ${
                isUser ? 'icon-bg-teal' : 'icon-bg-violet'
              }`}>
                {isUser ? <User size={14} weight="duotone" /> : <ShieldCheck size={14} weight="duotone" />}
              </div>
              <span className="font-medium truncate">{val || t('common.unnamed')}</span>
            </div>
            <Badge variant={isUser ? 'teal' : 'violet'} size="sm" dot>
              {isUser ? t('sshCas.typeUser') : t('sshCas.typeHost')}
            </Badge>
          </div>
        )
      }
    },
    {
      key: 'ca_type',
      header: t('sshCas.caType'),
      priority: 2,
      sortable: true,
      hideOnMobile: true,
      render: (val) => (
        <Badge variant={val === 'user' ? 'teal' : 'violet'} size="sm" icon={val === 'user' ? User : ShieldCheck}>
          {val === 'user' ? t('sshCas.typeUser') : t('sshCas.typeHost')}
        </Badge>
      )
    },
    {
      key: 'key_type',
      header: t('sshCas.keyType'),
      priority: 3,
      hideOnMobile: true,
      sortable: true,
      render: (val) => (
        <span className="text-sm text-text-secondary font-mono">
          {val || '—'}
        </span>
      ),
      mobileRender: (val) => (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-text-tertiary">{t('sshCas.keyType')}:</span>
          <span className="text-text-secondary font-mono">{val || '—'}</span>
        </div>
      )
    },
    {
      key: 'fingerprint',
      header: t('sshCas.fingerprint'),
      priority: 4,
      hideOnMobile: true,
      render: (val) => (
        <span className="text-xs text-text-secondary font-mono truncate max-w-[200px]">
          {val ? `${val.substring(0, 24)}…` : '—'}
        </span>
      )
    },
    {
      key: 'certificate_count',
      header: t('sshCas.stats.certificates'),
      priority: 3,
      hideOnMobile: true,
      sortable: true,
      render: (val) => (
        <Badge variant={val > 0 ? 'primary' : 'secondary'} size="sm" icon={Terminal}>
          {val || 0}
        </Badge>
      )
    },
    {
      key: 'created_at',
      header: t('common.created'),
      priority: 4,
      hideOnMobile: true,
      sortable: true,
      render: (val) => (
        <span className="text-xs text-text-secondary">{formatDate(val)}</span>
      )
    }
  ], [t])

  // ============= ROW ACTIONS =============

  const rowActions = useCallback((row) => [
    ...(canWrite('ssh') ? [
      { label: t('common.edit'), icon: PencilSimple, onClick: () => { setEditingCA(row); setShowModal(true) } }
    ] : []),
    { label: t('sshCas.downloadPublicKey'), icon: Download, onClick: () => handleDownloadPublicKey(row) },
    ...(canDelete('ssh') ? [
      { label: t('common.delete'), icon: Trash, variant: 'danger', onClick: () => handleDelete(row) }
    ] : [])
  ], [canWrite, canDelete, t])

  // ============= DETAIL PANEL =============

  const detailContent = selectedCA && (
    <div className="p-3 space-y-4">
      <CompactHeader
        icon={selectedCA.ca_type === 'user' ? User : ShieldCheck}
        iconClass={selectedCA.ca_type === 'user' ? 'icon-bg-teal' : 'icon-bg-violet'}
        title={selectedCA.descr || t('common.unnamed')}
        subtitle={t('sshCas.stats.certificates') + ': ' + (selectedCA.certificate_count || 0)}
        badge={
          <Badge variant={selectedCA.ca_type === 'user' ? 'teal' : 'violet'} size="sm">
            {selectedCA.ca_type === 'user' ? t('sshCas.typeUser') : t('sshCas.typeHost')}
          </Badge>
        }
      />

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        <Button type="button" size="sm" variant="secondary" onClick={() => handleDownloadPublicKey(selectedCA)}>
          <Download size={14} /> {t('sshCas.downloadPublicKey')}
        </Button>
        <Button type="button" size="sm" variant="secondary" onClick={() => handleDownloadKRL(selectedCA)}>
          <Download size={14} /> {t('sshCas.downloadKrl')}
        </Button>
        <Button type="button" size="sm" variant="secondary" onClick={() => handleCopyPublicKey(selectedCA)}>
          {copied ? <Check size={14} /> : <Copy size={14} />}
          {copied ? t('sshCas.publicKeyCopied') : t('sshCas.copyPublicKey')}
        </Button>
        {canWrite('ssh') && (
          <Button type="button" size="sm" variant="secondary" onClick={() => { setEditingCA(selectedCA); setShowModal(true) }}>
            <PencilSimple size={14} /> {t('common.edit')}
          </Button>
        )}
        {canDelete('ssh') && (
          <Button type="button" size="sm" variant="danger" onClick={() => handleDelete(selectedCA)}>
            <Trash size={14} /> {t('common.delete')}
          </Button>
        )}
      </div>

      {/* CA Information */}
      <CompactSection title={t('sshCas.caInformation')} icon={Key}>
        <CompactGrid columns={2}>
          <CompactField
            autoIcon="type"
            label={t('sshCas.caType')}
            value={selectedCA.ca_type === 'user' ? t('sshCas.typeUser') : t('sshCas.typeHost')}
          />
          <CompactField
            autoIcon="keyType"
            label={t('sshCas.keyType')}
            value={selectedCA.key_type || '—'}
          />
          <CompactField
            label={t('sshCas.fingerprint')}
            icon={Fingerprint}
            value={selectedCA.fingerprint || '—'}
            mono
            copyable
          />
          <CompactField
            label={t('sshCas.serialCounter')}
            value={selectedCA.serial_counter ?? '—'}
          />
          <CompactField
            autoIcon="createdAt"
            label={t('common.created')}
            value={formatDate(selectedCA.created_at)}
          />
          <CompactField
            autoIcon="createdBy"
            label={t('common.createdBy')}
            value={selectedCA.created_by || '—'}
          />
        </CompactGrid>
      </CompactSection>

      {/* Configuration */}
      <CompactSection title={t('sshCas.configuration')} icon={Clock} collapsible>
        <CompactGrid columns={2}>
          <CompactField
            autoIcon="default"
            label={t('sshCas.defaultTtl')}
            value={selectedCA.default_ttl || '—'}
          />
          <CompactField
            autoIcon="maximum"
            label={t('sshCas.maxTtl')}
            value={selectedCA.max_ttl || '—'}
          />
        </CompactGrid>

        {selectedCA.default_extensions?.length > 0 && (
          <div className="mt-3 space-y-1">
            <div className="text-xs font-semibold text-text-primary">
              {t('sshCas.defaultExtensions')}
            </div>
            <div className="flex flex-wrap gap-1">
              {selectedCA.default_extensions.map(ext => (
                <Badge key={ext} variant="teal" size="sm">{ext}</Badge>
              ))}
            </div>
          </div>
        )}

        {selectedCA.allowed_principals && (
          <div className="mt-3 space-y-1">
            <div className="text-xs font-semibold text-text-primary">
              {t('sshCas.allowedPrincipals')}
            </div>
            <div className="flex flex-wrap gap-1">
              {(Array.isArray(selectedCA.allowed_principals)
                ? selectedCA.allowed_principals
                : selectedCA.allowed_principals.split(',').map(p => p.trim()).filter(Boolean)
              ).map(principal => (
                <Badge key={principal} variant="primary" size="sm">{principal}</Badge>
              ))}
            </div>
          </div>
        )}
      </CompactSection>

      {/* Public Key */}
      {selectedCA.public_key && (
        <CompactSection title={t('sshCas.publicKey')} icon={Key} collapsible defaultOpen={false}>
          <div className="relative">
            <pre className="text-2xs font-mono text-text-secondary break-all bg-tertiary-op50 p-2 rounded whitespace-pre-wrap max-h-32 overflow-y-auto">
              {selectedCA.public_key}
            </pre>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="absolute top-1 right-1"
              onClick={() => handleCopyPublicKey(selectedCA)}
            >
              {copied ? <Check size={12} /> : <Copy size={12} />}
            </Button>
          </div>
        </CompactSection>
      )}
    </div>
  )

  // ============= RENDER =============

  return (
    <>
      <ResponsiveLayout
        title={t('sshCas.title')}
        subtitle={t('sshCas.subtitle', { count: sshCas.length })}
        icon={Key}
        stats={stats}
        helpPageKey="sshCas"
        splitView={true}
        splitEmptyContent={
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="w-14 h-14 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
              <Key size={24} className="text-text-tertiary" weight="duotone" />
            </div>
            <p className="text-sm text-text-secondary">{t('sshCas.selectCA')}</p>
          </div>
        }
        slideOverOpen={!!selectedCA}
        slideOverTitle={selectedCA?.descr || t('sshCas.title')}
        slideOverContent={detailContent}
        slideOverWidth="lg"
        onSlideOverClose={() => setSelectedCA(null)}
      >
        <ResponsiveDataTable
          data={filteredCAs}
          columns={columns}
          loading={loading}
          onRowClick={setSelectedCA}
          selectedId={selectedCA?.id}
          searchable
          searchPlaceholder={t('sshCas.searchPlaceholder')}
          searchKeys={['descr', 'ca_type', 'key_type', 'fingerprint']}
          toolbarFilters={[
            {
              key: 'ca_type',
              value: filterType,
              onChange: setFilterType,
              placeholder: t('common.allTypes'),
              options: [
                { value: 'user', label: t('sshCas.typeUser') },
                { value: 'host', label: t('sshCas.typeHost') }
              ]
            }
          ]}
          toolbarActions={canWrite('ssh') && (
            isMobile ? (
              <Button type="button" size="lg" onClick={() => { setEditingCA(null); setShowModal(true) }} className="w-11 h-11 p-0">
                <Plus size={22} weight="bold" />
              </Button>
            ) : (
              <Button type="button" size="sm" onClick={() => { setEditingCA(null); setShowModal(true) }}>
                <Plus size={14} weight="bold" />
                {t('sshCas.createCA')}
              </Button>
            )
          )}
          rowActions={rowActions}
          sortable
          defaultSort={{ key: 'descr', direction: 'asc' }}
          pagination={{
            page,
            total: filteredCAs.length,
            perPage,
            onChange: setPage,
            onPerPageChange: (v) => { setPerPage(v); setPage(1) }
          }}
          emptyIcon={Key}
          emptyTitle={t('sshCas.noData')}
          emptyDescription={t('sshCas.noDataDescription')}
          emptyAction={canWrite('ssh') && (
            <Button type="button" onClick={() => { setEditingCA(null); setShowModal(true) }}>
              <Plus size={16} /> {t('sshCas.createCA')}
            </Button>
          )}
        />
      </ResponsiveLayout>

      {/* Create / Edit Modal */}
      {showModal && (
        <SSHCAModal
          ca={editingCA}
          onSave={editingCA ? handleUpdate : handleCreate}
          onClose={() => { setShowModal(false); setEditingCA(null) }}
        />
      )}
    </>
  )
}

// ============= SSH CA FORM MODAL =============

function SSHCAModal({ ca, onSave, onClose }) {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(false)
  const [formData, setFormData] = useState({
    description: ca?.descr || '',
    ca_type: ca?.ca_type || 'user',
    key_algorithm: ca?.key_algorithm || 'ed25519',
    key_size: ca?.key_size || '4096',
    default_ttl: ca?.default_ttl || '',
    max_ttl: ca?.max_ttl || '',
    default_extensions: ca?.default_extensions || ['permit-pty', 'permit-agent-forwarding'],
    allowed_principals: Array.isArray(ca?.allowed_principals)
      ? ca.allowed_principals.join(', ')
      : (ca?.allowed_principals || ''),
  })

  const handleChange = (field, value) => setFormData(prev => ({ ...prev, [field]: value }))

  const toggleExtension = (ext) => {
    setFormData(prev => {
      const exts = prev.default_extensions
      return {
        ...prev,
        default_extensions: exts.includes(ext)
          ? exts.filter(e => e !== ext)
          : [...exts, ext]
      }
    })
  }

  const showKeySize = formData.key_algorithm === 'rsa'

  const handleSubmit = async () => {
    setLoading(true)
    try {
      const principals = formData.allowed_principals
        .split(',')
        .map(p => p.trim())
        .filter(Boolean)
      await onSave({
        descr: formData.description,
        ca_type: formData.ca_type,
        key_type: formData.key_algorithm,
        ...(showKeySize && { key_size: parseInt(formData.key_size) }),
        default_ttl: formData.default_ttl || undefined,
        max_ttl: formData.max_ttl || undefined,
        default_extensions: formData.ca_type === 'user' ? formData.default_extensions : [],
        allowed_principals: principals.length > 0 ? principals : undefined,
      })
    } finally {
      setLoading(false)
    }
  }

  const checkboxCls = 'flex items-center gap-1.5 text-sm text-text-primary cursor-pointer select-none'

  return (
    <FormModal
      open={true}
      onClose={onClose}
      title={ca ? t('sshCas.editCA') : t('sshCas.createCA')}
      size="lg"
      onSubmit={handleSubmit}
      submitLabel={ca ? t('common.save') : t('common.create')}
      loading={loading}
      disabled={loading || !formData.description.trim()}
    >
      <Input
        label={t('sshCas.description')}
        value={formData.description}
        onChange={e => handleChange('description', e.target.value)}
        placeholder={t('sshCas.modal.descriptionPlaceholder')}
        required
      />

      <div className="grid grid-cols-2 gap-4">
        <Select
          label={t('sshCas.caType')}
          value={formData.ca_type}
          onChange={value => handleChange('ca_type', value)}
          options={[
            { value: 'user', label: t('sshCas.typeUser') },
            { value: 'host', label: t('sshCas.typeHost') },
          ]}
          disabled={!!ca}
        />
        <Select
          label={t('sshCas.keyAlgorithm')}
          value={formData.key_algorithm}
          onChange={value => {
            handleChange('key_algorithm', value)
            if (value === 'rsa') handleChange('key_size', '4096')
          }}
          options={KEY_ALGORITHM_OPTIONS}
          disabled={!!ca}
        />
      </div>

      {showKeySize && (
        <Select
          label={t('sshCas.keySize')}
          value={formData.key_size}
          onChange={value => handleChange('key_size', value)}
          options={RSA_KEY_SIZE_OPTIONS}
          disabled={!!ca}
        />
      )}

      <div className="grid grid-cols-2 gap-4">
        <Input
          label={t('sshCas.defaultTtl')}
          value={formData.default_ttl}
          onChange={e => handleChange('default_ttl', e.target.value)}
          placeholder={t('sshCas.modal.ttlPlaceholder')}
        />
        <Input
          label={t('sshCas.maxTtl')}
          value={formData.max_ttl}
          onChange={e => handleChange('max_ttl', e.target.value)}
          placeholder={t('sshCas.modal.ttlPlaceholder')}
        />
      </div>

      {/* Default extensions — only for user CAs */}
      {formData.ca_type === 'user' && (
        <div className="border-t border-border pt-4">
          <label className="block text-xs font-medium text-text-secondary mb-2">
            {t('sshCas.defaultExtensions')}
          </label>
          <div className="flex flex-wrap gap-x-4 gap-y-2">
            {DEFAULT_EXTENSIONS.map(ext => (
              <label key={ext.value} className={checkboxCls}>
                <input
                  type="checkbox"
                  checked={formData.default_extensions.includes(ext.value)}
                  onChange={() => toggleExtension(ext.value)}
                  className="accent-accent-primary"
                />
                {t(ext.labelKey)}
              </label>
            ))}
          </div>
        </div>
      )}

      <Input
        label={t('sshCas.allowedPrincipals')}
        value={formData.allowed_principals}
        onChange={e => handleChange('allowed_principals', e.target.value)}
        placeholder={t('sshCas.modal.principalsPlaceholder')}
        helperText={t('sshCas.modal.principalsHelperText')}
      />
    </FormModal>
  )
}
