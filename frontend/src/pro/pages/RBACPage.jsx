/**
 * RBAC Management Page (Pro Feature)
 * Role-Based Access Control with custom roles and permissions
 * 
 * Uses UnifiedManagementLayout for consistent UX with UsersPage
 */
import { useState, useEffect, useMemo } from 'react'
import { 
  Shield, Plus, Trash, Lock, CheckCircle, XCircle, Warning, UsersThree,
  PencilSimple
} from '@phosphor-icons/react'
import {
  UnifiedManagementLayout, Button, Input, Badge, FormModal, HelpCard,
  CompactSection, CompactGrid, CompactField, CompactStats, CompactHeader
} from '../../components'
import { useNotification } from '../../contexts'
import { useModals } from '../../hooks'
import { apiClient } from '../../services/apiClient'

// Permission categories for RBAC
const PERMISSION_CATEGORIES = {
  certificates: {
    label: 'Certificates',
    permissions: ['read:certs', 'write:certs', 'delete:certs', 'revoke:certs', 'export:certs']
  },
  cas: {
    label: 'Certificate Authorities',
    permissions: ['read:cas', 'write:cas', 'delete:cas', 'export:cas']
  },
  users: {
    label: 'User Management',
    permissions: ['read:users', 'write:users', 'delete:users']
  },
  settings: {
    label: 'System Settings',
    permissions: ['read:settings', 'write:settings']
  },
  audit: {
    label: 'Audit Logs',
    permissions: ['read:audit', 'export:audit']
  },
  scep: {
    label: 'SCEP Protocol',
    permissions: ['read:scep', 'write:scep', 'approve:scep']
  },
  acme: {
    label: 'ACME Protocol',
    permissions: ['read:acme', 'write:acme']
  }
}

const totalPermissions = Object.values(PERMISSION_CATEGORIES).reduce(
  (acc, cat) => acc + cat.permissions.length, 0
)

export default function RBACPage() {
  const { showSuccess, showError } = useNotification()
  const { modals, open: openModal, close: closeModal } = useModals(['create'])
  
  const [loading, setLoading] = useState(true)
  const [roles, setRoles] = useState([])
  const [selectedRole, setSelectedRole] = useState(null)
  
  // Form state for create modal
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    permissions: [],
    is_system: false
  })

  useEffect(() => {
    loadRoles()
  }, [])

  const loadRoles = async () => {
    setLoading(true)
    try {
      const res = await apiClient.get('/rbac/roles')
      setRoles(res.data || [])
    } catch (error) {
      showError('Failed to load roles')
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async () => {
    try {
      await apiClient.post('/rbac/roles', formData)
      showSuccess('Role created')
      closeModal('create')
      loadRoles()
      setFormData({ name: '', description: '', permissions: [], is_system: false })
    } catch (error) {
      showError(error.message || 'Failed to create role')
    }
  }

  const handleUpdate = async () => {
    if (!selectedRole || selectedRole.is_system) return
    try {
      await apiClient.put(`/rbac/roles/${selectedRole.id}`, {
        ...selectedRole,
        permissions: selectedRole.permissions
      })
      showSuccess('Role updated')
      loadRoles()
    } catch (error) {
      showError(error.message || 'Failed to update role')
    }
  }

  const handleDelete = async (role) => {
    if (role.is_system) {
      showError('Cannot delete system role')
      return
    }
    if (!confirm(`Delete role "${role.name}"? Users with this role will be set to 'viewer'.`)) return
    try {
      await apiClient.delete(`/rbac/roles/${role.id}`)
      showSuccess('Role deleted')
      setSelectedRole(null)
      loadRoles()
    } catch (error) {
      showError(error.message || 'Failed to delete role')
    }
  }

  const togglePermission = (permission) => {
    if (!selectedRole || selectedRole.is_system) return
    
    const current = selectedRole.permissions || []
    const updated = current.includes(permission)
      ? current.filter(p => p !== permission)
      : [...current, permission]
    
    setSelectedRole({ ...selectedRole, permissions: updated })
  }

  const toggleCategoryPermissions = (category) => {
    if (!selectedRole || selectedRole.is_system) return
    
    const categoryPerms = PERMISSION_CATEGORIES[category].permissions
    const current = selectedRole.permissions || []
    const allSelected = categoryPerms.every(p => current.includes(p))
    
    const updated = allSelected
      ? current.filter(p => !categoryPerms.includes(p))
      : [...new Set([...current, ...categoryPerms])]
    
    setSelectedRole({ ...selectedRole, permissions: updated })
  }

  // Table columns
  const columns = [
    {
      key: 'name',
      header: 'Role Name',
      render: (val, row) => (
        <div className="flex items-center gap-2">
          {row.is_system ? (
            <Lock size={16} className="text-text-tertiary shrink-0" />
          ) : (
            <Shield size={16} className="text-accent-primary shrink-0" />
          )}
          <span className="font-medium truncate">{val}</span>
        </div>
      )
    },
    {
      key: 'is_system',
      header: 'Type',
      render: (val) => (
        <Badge variant={val ? 'secondary' : 'primary'} size="sm">
          {val ? 'System' : 'Custom'}
        </Badge>
      )
    },
    {
      key: 'permissions',
      header: 'Permissions',
      render: (val) => (
        <span className="text-xs text-text-secondary">
          {val?.length || 0} / {totalPermissions}
        </span>
      )
    },
    {
      key: 'user_count',
      header: 'Users',
      render: (val) => val || 0
    }
  ]

  // Row actions
  const rowActions = (row) => row.is_system ? [] : [
    { label: 'Delete', icon: Trash, variant: 'danger', onClick: () => handleDelete(row) }
  ]

  // Stats
  const stats = useMemo(() => {
    const systemRoles = roles.filter(r => r.is_system).length
    const customRoles = roles.filter(r => !r.is_system).length
    return [
      { label: 'Total', value: roles.length, icon: Shield },
      { label: 'System', value: systemRoles, icon: Lock, variant: 'secondary' },
      { label: 'Custom', value: customRoles, icon: Shield, variant: 'success' },
    ]
  }, [roles])

  // Render details panel
  const renderDetails = (role) => (
    <div className="p-3 space-y-3">
      {/* Header */}
      <CompactHeader
        icon={role.is_system ? Lock : Shield}
        iconClass={role.is_system ? 'bg-bg-tertiary' : 'bg-accent-primary/20'}
        title={role.name}
        subtitle={role.description || 'No description'}
        badge={
          <Badge variant={role.is_system ? 'secondary' : 'primary'} size="sm">
            {role.is_system ? 'System' : 'Custom'}
          </Badge>
        }
      />

      {/* Stats */}
      <CompactStats stats={[
        { icon: CheckCircle, value: `${role.permissions?.length || 0} perms` },
        { icon: UsersThree, value: `${role.user_count || 0} users` },
      ]} />

      {/* Actions */}
      {!role.is_system && (
        <div className="flex gap-2">
          <Button size="sm" className="flex-1" onClick={handleUpdate}>
            <CheckCircle size={14} />
            Save Changes
          </Button>
          <Button size="sm" variant="danger" onClick={() => handleDelete(role)}>
            <Trash size={14} />
          </Button>
        </div>
      )}

      {/* System Role Warning */}
      {role.is_system && (
        <div className="p-3 rounded-lg status-warning-bg status-warning-border border">
          <div className="flex items-center gap-2 status-warning-text text-xs">
            <Warning size={14} />
            <span>System roles cannot be modified</span>
          </div>
        </div>
      )}

      {/* Role Info */}
      <CompactSection title="Role Information">
        <CompactGrid>
          <CompactField label="Name" value={role.name} />
          <CompactField label="Type" value={role.is_system ? 'System' : 'Custom'} />
        </CompactGrid>
        {role.description && (
          <p className="text-xs text-text-secondary mt-2">{role.description}</p>
        )}
      </CompactSection>

      {/* Permissions */}
      <CompactSection title="Permissions">
        <div className="space-y-4">
          {Object.entries(PERMISSION_CATEGORIES).map(([key, category]) => {
            const categoryPerms = category.permissions
            const selectedPerms = role.permissions || []
            const allSelected = categoryPerms.every(p => selectedPerms.includes(p))
            const someSelected = categoryPerms.some(p => selectedPerms.includes(p))

            return (
              <div key={key} className="border-b border-border/30 pb-3 last:border-0 last:pb-0">
                <button
                  onClick={() => toggleCategoryPermissions(key)}
                  disabled={role.is_system}
                  className="flex items-center gap-2 mb-2 text-xs font-medium text-text-primary hover:text-accent-primary transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {allSelected ? (
                    <CheckCircle size={14} weight="fill" className="status-success-text" />
                  ) : someSelected ? (
                    <CheckCircle size={14} weight="duotone" className="status-warning-text" />
                  ) : (
                    <XCircle size={14} weight="duotone" className="text-text-tertiary" />
                  )}
                  {category.label}
                </button>

                <div className="flex flex-wrap gap-1.5 pl-5">
                  {categoryPerms.map(perm => {
                    const isSelected = selectedPerms.includes(perm)
                    const permLabel = perm.split(':')[0]

                    return (
                      <button
                        key={perm}
                        onClick={() => togglePermission(perm)}
                        disabled={role.is_system}
                        className={`flex items-center gap-1 px-2 py-1 rounded text-[10px] transition-all ${
                          isSelected
                            ? 'status-success-bg status-success-text status-success-border border'
                            : 'bg-bg-tertiary text-text-secondary hover:bg-bg-tertiary/80'
                        } disabled:opacity-50 disabled:cursor-not-allowed`}
                      >
                        {isSelected ? (
                          <CheckCircle size={10} weight="fill" />
                        ) : (
                          <XCircle size={10} />
                        )}
                        {permLabel}
                      </button>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
      </CompactSection>

      {/* Summary */}
      <CompactSection title="Coverage">
        <div className="flex items-center gap-4">
          <div className="flex-1 bg-bg-tertiary rounded-full h-2 overflow-hidden">
            <div 
              className="h-full bg-accent-primary transition-all"
              style={{ width: `${((role.permissions?.length || 0) / totalPermissions) * 100}%` }}
            />
          </div>
          <span className="text-xs text-text-secondary">
            {role.permissions?.length || 0}/{totalPermissions}
          </span>
        </div>
      </CompactSection>
    </div>
  )

  // Help content
  const helpContent = (
    <div className="space-y-4">
      <HelpCard title="RBAC" variant="info">
        Define granular permissions per role. System roles are read-only.
      </HelpCard>
      <HelpCard title="System Roles" variant="warning">
        Built-in roles (admin, operator, viewer) cannot be modified.
      </HelpCard>
    </div>
  )

  // Table filters
  const tableFilters = [
    {
      key: 'is_system',
      label: 'Type',
      options: [
        { value: true, label: 'System' },
        { value: false, label: 'Custom' }
      ]
    }
  ]

  return (
    <>
      <UnifiedManagementLayout
        title="Role-Based Access Control"
        subtitle={`${roles.length} role${roles.length !== 1 ? 's' : ''}`}
        icon={Shield}
        stats={stats}
        data={roles}
        columns={columns}
        loading={loading}
        selectedItem={selectedRole}
        onSelectItem={setSelectedRole}
        renderDetails={renderDetails}
        detailsTitle="Role Details"
        splitView={true}
        splitEmptyContent={
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="w-14 h-14 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
              <Shield size={24} className="text-text-tertiary" weight="duotone" />
            </div>
            <p className="text-sm text-text-secondary">Select a role to view permissions</p>
          </div>
        }
        searchable
        searchPlaceholder="Search roles..."
        searchKeys={['name', 'description']}
        sortable
        defaultSort={{ key: 'name', direction: 'asc' }}
        paginated={false}
        rowActions={rowActions}
        filters={tableFilters}
        emptyIcon={Shield}
        emptyTitle="No roles found"
        emptyDescription="Create custom roles for granular access control"
        emptyAction={
          <Button onClick={() => openModal('create')}>
            <Plus size={16} /> Create Role
          </Button>
        }
        helpContent={helpContent}
        actions={
          <Button size="sm" onClick={() => openModal('create')}>
            <Plus size={16} /> Create Role
          </Button>
        }
      />

      {/* Create Role Modal */}
      <FormModal
        open={modals.create}
        onClose={() => closeModal('create')}
        title="Create Custom Role"
        onSubmit={handleCreate}
        submitLabel="Create"
        disabled={!formData.name}
      >
        <Input
          label="Role Name"
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          placeholder="e.g., Certificate Manager"
        />
        <Input
          label="Description"
          value={formData.description}
          onChange={(e) => setFormData({ ...formData, description: e.target.value })}
          placeholder="Brief description of this role"
        />
      </FormModal>
    </>
  )
}
