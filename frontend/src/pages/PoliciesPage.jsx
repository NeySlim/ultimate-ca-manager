/**
 * PoliciesPage — Certificate Policies & Approval Workflows
 * CRUD for certificate policies with rules, approval settings, and notifications.
 */
import { useState, useEffect, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Gavel, Plus, PencilSimple, Trash, Power, ShieldCheck,
  Warning, CheckCircle, XCircle, Certificate, ArrowsDownUp,
  UsersThree, Bell, Funnel, CaretDown, CaretUp
} from '@phosphor-icons/react'
import {
  ResponsiveLayout, ResponsiveDataTable, Card, Button, Badge,
  Input, Modal, LoadingSpinner, Select, Textarea
} from '../components'
import { policiesService, casService, groupsService } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { formatDate, cn } from '../lib/utils'

// Policy type options
const POLICY_TYPES = [
  { value: 'issuance', label: 'Issuance' },
  { value: 'renewal', label: 'Renewal' },
  { value: 'revocation', label: 'Revocation' },
]

// Key type options
const KEY_TYPE_OPTIONS = [
  { value: 'RSA-2048', label: 'RSA 2048-bit' },
  { value: 'RSA-4096', label: 'RSA 4096-bit' },
  { value: 'EC-P256', label: 'ECDSA P-256' },
  { value: 'EC-P384', label: 'ECDSA P-384' },
  { value: 'EC-P521', label: 'ECDSA P-521' },
]

const DEFAULT_FORM = {
  name: '',
  description: '',
  policy_type: 'issuance',
  ca_id: null,
  template_id: null,
  requires_approval: false,
  approval_group_id: null,
  min_approvers: 1,
  notify_on_violation: true,
  is_active: true,
  priority: 100,
  rules: {
    max_validity_days: 397,
    allowed_key_types: ['RSA-2048', 'RSA-4096', 'EC-P256', 'EC-P384'],
    required_extensions: [],
    san_restrictions: {
      max_dns_names: 50,
      dns_pattern: '',
      require_approval_for_external: false,
    },
  },
  notification_emails: [],
}

export default function PoliciesPage() {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const { canRead, canWrite, canDelete } = usePermission()

  // Data state
  const [policies, setPolicies] = useState([])
  const [loading, setLoading] = useState(true)
  const [cas, setCas] = useState([])
  const [groups, setGroups] = useState([])

  // Modal state
  const [showModal, setShowModal] = useState(false)
  const [editing, setEditing] = useState(null)
  const [formData, setFormData] = useState({ ...DEFAULT_FORM })
  const [saving, setSaving] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(null)
  const [actionInProgress, setActionInProgress] = useState(false)

  // Detail state
  const [selectedPolicy, setSelectedPolicy] = useState(null)

  // Filters
  const [filterType, setFilterType] = useState('')
  const [filterStatus, setFilterStatus] = useState('')

  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      const [policiesRes, casRes, groupsRes] = await Promise.all([
        policiesService.list(),
        casService.getAll().catch(() => ({ data: [] })),
        groupsService.getAll().catch(() => ({ data: [] })),
      ])
      setPolicies(policiesRes.data || [])
      setCas(casRes.data || [])
      setGroups(groupsRes.data || [])
    } catch (err) {
      showError(t('policies.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [showError, t])

  useEffect(() => { loadData() }, [loadData])

  // Filtered policies
  const filteredPolicies = useMemo(() => {
    let result = policies
    if (filterType) result = result.filter(p => p.policy_type === filterType)
    if (filterStatus === 'active') result = result.filter(p => p.is_active)
    if (filterStatus === 'inactive') result = result.filter(p => !p.is_active)
    return result
  }, [policies, filterType, filterStatus])

  // Stats
  const stats = useMemo(() => [
    {
      icon: Gavel,
      label: t('policies.total'),
      value: policies.length,
      variant: 'default',
    },
    {
      icon: CheckCircle,
      label: t('policies.active'),
      value: policies.filter(p => p.is_active).length,
      variant: 'success',
      filterValue: 'active',
    },
    {
      icon: XCircle,
      label: t('policies.inactive'),
      value: policies.filter(p => !p.is_active).length,
      variant: 'warning',
      filterValue: 'inactive',
    },
    {
      icon: ShieldCheck,
      label: t('policies.withApproval'),
      value: policies.filter(p => p.requires_approval).length,
      variant: 'info',
    },
  ], [policies, t])

  // Column definitions
  const columns = useMemo(() => [
    {
      key: 'name',
      header: t('common.name'),
      priority: 1,
      sortable: true,
      render: (val, row) => (
        <div className="flex items-center gap-2">
          <div className={cn(
            'w-2 h-2 rounded-full shrink-0',
            row.is_active ? 'bg-green-500' : 'bg-gray-400'
          )} />
          <div>
            <div className="font-medium text-text-primary">{val}</div>
            {row.description && (
              <div className="text-xs text-text-muted truncate max-w-[200px]">{row.description}</div>
            )}
          </div>
        </div>
      ),
    },
    {
      key: 'policy_type',
      header: t('common.type'),
      priority: 2,
      sortable: true,
      render: (val) => (
        <Badge variant={val === 'issuance' ? 'info' : val === 'renewal' ? 'success' : 'warning'}>
          {val}
        </Badge>
      ),
    },
    {
      key: 'ca_name',
      header: t('policies.scope'),
      priority: 3,
      render: (val) => val || <span className="text-text-muted">{t('policies.allCAs')}</span>,
    },
    {
      key: 'priority',
      header: t('policies.priority'),
      priority: 3,
      sortable: true,
      render: (val) => (
        <span className="text-text-secondary font-mono text-sm">{val}</span>
      ),
    },
    {
      key: 'requires_approval',
      header: t('policies.approval'),
      priority: 2,
      render: (val, row) => val ? (
        <div className="flex items-center gap-1.5">
          <UsersThree size={14} className="text-accent-primary" weight="fill" />
          <span className="text-xs text-text-secondary">
            {row.min_approvers}+ {row.approval_group_name || ''}
          </span>
        </div>
      ) : (
        <span className="text-text-muted text-xs">{t('common.no')}</span>
      ),
    },
    {
      key: 'is_active',
      header: t('common.status'),
      priority: 1,
      render: (val) => (
        <Badge variant={val ? 'success' : 'warning'}>
          {val ? t('policies.active') : t('policies.inactive')}
        </Badge>
      ),
    },
  ], [t])

  // Row actions
  const rowActions = useCallback((row) => {
    const actions = []
    if (canWrite('policies')) {
      actions.push({
        label: t('common.edit'),
        icon: PencilSimple,
        onClick: () => openEditModal(row),
      })
      actions.push({
        label: row.is_active ? t('policies.disable') : t('policies.enable'),
        icon: Power,
        onClick: () => handleToggle(row),
      })
    }
    if (canDelete('policies')) {
      actions.push({
        label: t('common.delete'),
        icon: Trash,
        variant: 'danger',
        onClick: () => setShowDeleteConfirm(row),
      })
    }
    return actions
  }, [canWrite, canDelete, t])

  // Modal handlers
  const openCreateModal = () => {
    setEditing(null)
    setFormData({ ...DEFAULT_FORM, rules: { ...DEFAULT_FORM.rules, san_restrictions: { ...DEFAULT_FORM.rules.san_restrictions } } })
    setShowModal(true)
  }

  const openEditModal = (policy) => {
    setEditing(policy)
    setFormData({
      name: policy.name || '',
      description: policy.description || '',
      policy_type: policy.policy_type || 'issuance',
      ca_id: policy.ca_id || null,
      template_id: policy.template_id || null,
      requires_approval: policy.requires_approval || false,
      approval_group_id: policy.approval_group_id || null,
      min_approvers: policy.min_approvers || 1,
      notify_on_violation: policy.notify_on_violation ?? true,
      is_active: policy.is_active ?? true,
      priority: policy.priority || 100,
      rules: {
        max_validity_days: policy.rules?.max_validity_days || 397,
        allowed_key_types: policy.rules?.allowed_key_types || ['RSA-2048', 'RSA-4096', 'EC-P256', 'EC-P384'],
        required_extensions: policy.rules?.required_extensions || [],
        san_restrictions: {
          max_dns_names: policy.rules?.san_restrictions?.max_dns_names || 50,
          dns_pattern: policy.rules?.san_restrictions?.dns_pattern || '',
          require_approval_for_external: policy.rules?.san_restrictions?.require_approval_for_external || false,
        },
      },
      notification_emails: policy.notification_emails || [],
    })
    setShowModal(true)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!formData.name.trim()) return

    try {
      setSaving(true)
      if (editing) {
        await policiesService.update(editing.id, formData)
        showSuccess(t('policies.updated'))
      } else {
        await policiesService.create(formData)
        showSuccess(t('policies.created'))
      }
      setShowModal(false)
      loadData()
    } catch (err) {
      showError(t('policies.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const handleToggle = async (policy) => {
    if (actionInProgress) return
    try {
      setActionInProgress(true)
      await policiesService.toggle(policy.id)
      showSuccess(policy.is_active ? t('policies.disabled') : t('policies.enabled'))
      loadData()
    } catch (err) {
      showError(t('policies.toggleFailed'))
    } finally {
      setActionInProgress(false)
    }
  }

  const handleDelete = async (policy) => {
    if (actionInProgress) return
    try {
      setActionInProgress(true)
      await policiesService.delete(policy.id)
      showSuccess(t('policies.deleted'))
      setShowDeleteConfirm(null)
      loadData()
    } catch (err) {
      showError(t('policies.deleteFailed'))
    } finally {
      setActionInProgress(false)
    }
  }

  const updateRule = (key, value) => {
    setFormData(prev => ({
      ...prev,
      rules: { ...prev.rules, [key]: value },
    }))
  }

  const toggleKeyType = (keyType) => {
    setFormData(prev => {
      const current = prev.rules.allowed_key_types || []
      const next = current.includes(keyType)
        ? current.filter(k => k !== keyType)
        : [...current, keyType]
      return { ...prev, rules: { ...prev.rules, allowed_key_types: next } }
    })
  }

  // Policy detail (slide-over)
  const slideOverContent = selectedPolicy ? (
    <div className="p-4 space-y-4">
      {/* Status */}
      <div className="flex items-center gap-2">
        <Badge variant={selectedPolicy.is_active ? 'success' : 'warning'} size="lg">
          {selectedPolicy.is_active ? t('policies.active') : t('policies.inactive')}
        </Badge>
        <Badge variant={selectedPolicy.policy_type === 'issuance' ? 'info' : selectedPolicy.policy_type === 'renewal' ? 'success' : 'warning'}>
          {selectedPolicy.policy_type}
        </Badge>
      </div>

      {selectedPolicy.description && (
        <p className="text-sm text-text-secondary">{selectedPolicy.description}</p>
      )}

      {/* Scope */}
      <div className="border-t border-border pt-3">
        <h4 className="text-sm font-semibold text-text-primary mb-2">{t('policies.scope')}</h4>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div className="text-text-muted">{t('policies.targetCA')}</div>
          <div className="text-text-primary">{selectedPolicy.ca_name || t('policies.allCAs')}</div>
          <div className="text-text-muted">{t('policies.priority')}</div>
          <div className="text-text-primary font-mono">{selectedPolicy.priority}</div>
        </div>
      </div>

      {/* Rules */}
      {selectedPolicy.rules && Object.keys(selectedPolicy.rules).length > 0 && (
        <div className="border-t border-border pt-3">
          <h4 className="text-sm font-semibold text-text-primary mb-2">{t('policies.rules')}</h4>
          <div className="space-y-2 text-sm">
            {selectedPolicy.rules.max_validity_days > 0 && (
              <div className="flex justify-between">
                <span className="text-text-muted">{t('policies.maxValidity')}</span>
                <span className="text-text-primary">{selectedPolicy.rules.max_validity_days} {t('common.days')}</span>
              </div>
            )}
            {selectedPolicy.rules.allowed_key_types?.length > 0 && (
              <div>
                <span className="text-text-muted">{t('policies.allowedKeyTypes')}</span>
                <div className="flex flex-wrap gap-1 mt-1">
                  {selectedPolicy.rules.allowed_key_types.map(k => (
                    <Badge key={k} variant="default" size="sm">{k}</Badge>
                  ))}
                </div>
              </div>
            )}
            {selectedPolicy.rules.san_restrictions?.max_dns_names != null && selectedPolicy.rules.san_restrictions.max_dns_names > 0 && (
              <div className="flex justify-between">
                <span className="text-text-muted">{t('policies.maxSANs')}</span>
                <span className="text-text-primary">{selectedPolicy.rules.san_restrictions.max_dns_names}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Approval */}
      {selectedPolicy.requires_approval && (
        <div className="border-t border-border pt-3">
          <h4 className="text-sm font-semibold text-text-primary mb-2">{t('policies.approvalWorkflow')}</h4>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="text-text-muted">{t('policies.approvalGroup')}</div>
            <div className="text-text-primary">{selectedPolicy.approval_group_name || '—'}</div>
            <div className="text-text-muted">{t('policies.minApprovers')}</div>
            <div className="text-text-primary">{selectedPolicy.min_approvers}</div>
          </div>
        </div>
      )}

      {/* Metadata */}
      <div className="border-t border-border pt-3">
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div className="text-text-muted">{t('common.createdAt')}</div>
          <div className="text-text-primary">{formatDate(selectedPolicy.created_at)}</div>
          {selectedPolicy.created_by && (
            <>
              <div className="text-text-muted">{t('common.createdBy')}</div>
              <div className="text-text-primary">{selectedPolicy.created_by}</div>
            </>
          )}
        </div>
      </div>

      {/* Actions */}
      {canWrite('policies') && (
        <div className="border-t border-border pt-3 flex gap-2">
          <Button type="button" size="sm" onClick={() => openEditModal(selectedPolicy)}>
            <PencilSimple size={14} className="mr-1" /> {t('common.edit')}
          </Button>
          <Button type="button" size="sm" variant="secondary" onClick={() => handleToggle(selectedPolicy)}>
            <Power size={14} className="mr-1" />
            {selectedPolicy.is_active ? t('policies.disable') : t('policies.enable')}
          </Button>
        </div>
      )}
    </div>
  ) : null

  // Toolbar filters
  const toolbarFilters = [
    {
      key: 'type',
      value: filterType,
      onChange: setFilterType,
      placeholder: t('policies.allTypes'),
      options: [
        { value: '', label: t('policies.allTypes') },
        ...POLICY_TYPES,
      ],
    },
    {
      key: 'status',
      value: filterStatus,
      onChange: setFilterStatus,
      placeholder: t('policies.allStatuses'),
      options: [
        { value: '', label: t('policies.allStatuses') },
        { value: 'active', label: t('policies.active') },
        { value: 'inactive', label: t('policies.inactive') },
      ],
    },
  ]

  return (
    <>
      <ResponsiveLayout
        title={t('policies.title')}
        subtitle={t('policies.subtitle')}
        icon={Gavel}
        stats={stats}
        activeStatFilter={filterStatus}
        onStatClick={(stat) => setFilterStatus(prev => prev === stat.filterValue ? '' : stat.filterValue)}
        helpPageKey="policies"
        actions={canWrite('policies') ? (
          <Button type="button" onClick={openCreateModal}>
            <Plus size={16} className="mr-1.5" /> {t('policies.createPolicy')}
          </Button>
        ) : null}
        slideOverOpen={!!selectedPolicy}
        slideOverTitle={selectedPolicy?.name}
        slideOverContent={slideOverContent}
        onSlideOverClose={() => setSelectedPolicy(null)}
        loading={loading}
      >
        <ResponsiveDataTable
          data={filteredPolicies}
          columns={columns}
          loading={loading}
          selectedId={selectedPolicy?.id}
          onRowClick={setSelectedPolicy}
          rowActions={rowActions}
          searchable
          searchPlaceholder={t('policies.searchPlaceholder')}
          searchKeys={['name', 'description', 'policy_type', 'ca_name']}
          sortable
          defaultSort={{ key: 'priority', direction: 'asc' }}
          toolbarFilters={toolbarFilters}
          emptyIcon={Gavel}
          emptyTitle={t('policies.noPolicies')}
          emptyDescription={t('policies.noPoliciesDesc')}
          emptyAction={canWrite('policies') ? (
            <Button type="button" onClick={openCreateModal} size="sm">
              <Plus size={14} className="mr-1" /> {t('policies.createPolicy')}
            </Button>
          ) : null}
        />
      </ResponsiveLayout>

      {/* Create/Edit Modal */}
      <Modal
        open={showModal}
        onOpenChange={(open) => { if (!open) { setShowModal(false); setEditing(null) } }}
        title={editing ? t('policies.editPolicy') : t('policies.createPolicy')}
        size="lg"
      >
        <form onSubmit={handleSubmit} className="p-4 space-y-4 max-h-[70vh] overflow-y-auto">
          {/* Basic Info */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Input
              label={t('policies.policyName')}
              value={formData.name}
              onChange={(e) => setFormData(p => ({ ...p, name: e.target.value }))}
              placeholder={t('policies.policyNamePlaceholder')}
              required
            />
            <Select
              label={t('common.type')}
              value={formData.policy_type}
              onChange={(val) => setFormData(p => ({ ...p, policy_type: val }))}
              options={POLICY_TYPES}
            />
          </div>

          <Textarea
            label={t('common.description')}
            value={formData.description}
            onChange={(e) => setFormData(p => ({ ...p, description: e.target.value }))}
            placeholder={t('policies.descriptionPlaceholder')}
            rows={2}
          />

          {/* Scope */}
          <div className="border-t border-border pt-4">
            <h4 className="text-sm font-medium text-text-primary mb-3 flex items-center gap-1.5">
              <Certificate size={16} /> {t('policies.scope')}
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Select
                label={t('policies.targetCA')}
                value={formData.ca_id || ''}
                onChange={(val) => setFormData(p => ({ ...p, ca_id: val ? parseInt(val) : null }))}
                options={[
                  { value: '', label: t('policies.allCAs') },
                  ...cas.map(ca => ({ value: ca.id, label: ca.common_name })),
                ]}
              />
              <Input
                label={t('policies.priority')}
                type="number"
                value={formData.priority}
                onChange={(e) => setFormData(p => ({ ...p, priority: parseInt(e.target.value) || 100 }))}
                min={1}
                max={1000}
              />
            </div>
          </div>

          {/* Rules */}
          <div className="border-t border-border pt-4">
            <h4 className="text-sm font-medium text-text-primary mb-3 flex items-center gap-1.5">
              <Gavel size={16} /> {t('policies.rules')}
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Input
                label={t('policies.maxValidity')}
                type="number"
                value={formData.rules.max_validity_days}
                onChange={(e) => updateRule('max_validity_days', parseInt(e.target.value) || 397)}
                min={1}
                max={3650}
              />
              <Input
                label={t('policies.maxSANs')}
                type="number"
                value={formData.rules.san_restrictions?.max_dns_names || 50}
                onChange={(e) => setFormData(p => ({
                  ...p,
                  rules: {
                    ...p.rules,
                    san_restrictions: {
                      ...p.rules.san_restrictions,
                      max_dns_names: parseInt(e.target.value) || 50,
                    },
                  },
                }))}
                min={1}
                max={500}
              />
            </div>

            {/* Allowed Key Types */}
            <div className="mt-3">
              <label className="text-sm font-medium text-text-primary mb-2 block">
                {t('policies.allowedKeyTypes')}
              </label>
              <div className="flex flex-wrap gap-2">
                {KEY_TYPE_OPTIONS.map(opt => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => toggleKeyType(opt.value)}
                    className={cn(
                      'px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors',
                      formData.rules.allowed_key_types?.includes(opt.value)
                        ? 'bg-accent-primary-op10 border-accent-primary text-accent-primary'
                        : 'bg-bg-secondary border-border text-text-muted hover:border-border-hover'
                    )}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            {/* DNS Pattern */}
            <div className="mt-3">
              <Input
                label={t('policies.dnsPattern')}
                value={formData.rules.san_restrictions?.dns_pattern || ''}
                onChange={(e) => setFormData(p => ({
                  ...p,
                  rules: {
                    ...p.rules,
                    san_restrictions: {
                      ...p.rules.san_restrictions,
                      dns_pattern: e.target.value,
                    },
                  },
                }))}
                placeholder="*.company.com"
              />
            </div>
          </div>

          {/* Approval Workflow */}
          <div className="border-t border-border pt-4">
            <h4 className="text-sm font-medium text-text-primary mb-3 flex items-center gap-1.5">
              <UsersThree size={16} /> {t('policies.approvalWorkflow')}
            </h4>
            <div className="flex items-center gap-3 mb-3">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={formData.requires_approval}
                  onChange={(e) => setFormData(p => ({ ...p, requires_approval: e.target.checked }))}
                  className="rounded border-border"
                />
                <span className="text-sm text-text-primary">{t('policies.requireApproval')}</span>
              </label>
            </div>

            {formData.requires_approval && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pl-6">
                <Select
                  label={t('policies.approvalGroup')}
                  value={formData.approval_group_id || ''}
                  onChange={(val) => setFormData(p => ({ ...p, approval_group_id: val ? parseInt(val) : null }))}
                  options={[
                    { value: '', label: t('policies.selectGroup') },
                    ...groups.map(g => ({ value: g.id, label: g.name })),
                  ]}
                />
                <Input
                  label={t('policies.minApprovers')}
                  type="number"
                  value={formData.min_approvers}
                  onChange={(e) => setFormData(p => ({ ...p, min_approvers: parseInt(e.target.value) || 1 }))}
                  min={1}
                  max={10}
                />
              </div>
            )}
          </div>

          {/* Notifications */}
          <div className="border-t border-border pt-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={formData.notify_on_violation}
                onChange={(e) => setFormData(p => ({ ...p, notify_on_violation: e.target.checked }))}
                className="rounded border-border"
              />
              <Bell size={16} className="text-text-secondary" />
              <span className="text-sm text-text-primary">{t('policies.notifyOnViolation')}</span>
            </label>
          </div>

          {/* Footer */}
          <div className="flex justify-end gap-2 pt-4 border-t border-border">
            <Button type="button" variant="secondary" onClick={() => { setShowModal(false); setEditing(null) }}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={saving || !formData.name.trim()}>
              {saving ? <LoadingSpinner size="sm" /> : (editing ? t('common.update') : t('common.create'))}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Delete Confirmation */}
      <Modal
        open={!!showDeleteConfirm}
        onOpenChange={(open) => { if (!open) setShowDeleteConfirm(null) }}
        title={t('policies.deletePolicy')}
        size="sm"
      >
        <div className="p-4">
          <p className="text-text-secondary text-sm mb-4">
            {t('policies.deleteConfirm', { name: showDeleteConfirm?.name })}
          </p>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setShowDeleteConfirm(null)}>
              {t('common.cancel')}
            </Button>
            <Button type="button" variant="danger" onClick={() => handleDelete(showDeleteConfirm)} disabled={actionInProgress}>
              {actionInProgress ? <LoadingSpinner size="sm" /> : t('common.delete')}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}
