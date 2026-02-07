/**
 * RBAC Management Page (Pro Feature)
 * Role-Based Access Control with custom roles and permissions
 * 
 * Migrated to ResponsiveLayout for consistent UX
 */
import { useState, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { 
  Shield, Plus, Trash, Lock, CheckCircle, XCircle, Warning, UsersThree
} from '@phosphor-icons/react'
import {
  Badge, Button, Input, FormModal, HelpCard,
  CompactSection, CompactGrid, CompactField, CompactStats, CompactHeader,
  FormSelect
} from '../../components'
import { ResponsiveLayout, ResponsiveDataTable } from '../../components/ui/responsive'
import { useNotification, useMobile } from '../../contexts'
import { useModals } from '../../hooks'
import { apiClient } from '../../services/apiClient'
import { ERRORS, SUCCESS, CONFIRM } from '../../lib/messages'

// Permission categories for RBAC - aligned with backend
const PERMISSION_CATEGORIES = {
  certificates: {
    label: 'Certificates',
    permissions: ['read:certs', 'write:certs', 'delete:certs', 'revoke:certs']
  },
  cas: {
    label: 'Certificate Authorities',
    permissions: ['read:cas', 'write:cas', 'delete:cas', 'admin:cas']
  },
  csrs: {
    label: 'Certificate Requests',
    permissions: ['read:csrs', 'write:csrs', 'delete:csrs', 'sign:csrs']
  },
  users: {
    label: 'User Management',
    permissions: ['read:users', 'write:users', 'delete:users', 'admin:users']
  },
  groups: {
    label: 'Group Management',
    permissions: ['read:groups', 'write:groups', 'delete:groups', 'admin:groups']
  },
  settings: {
    label: 'System Settings',
    permissions: ['read:settings', 'write:settings', 'admin:system']
  },
  audit: {
    label: 'Audit Logs',
    permissions: ['read:audit', 'export:audit']
  },
  acme: {
    label: 'ACME Protocol',
    permissions: ['read:acme', 'write:acme', 'delete:acme']
  },
  scep: {
    label: 'SCEP Protocol',
    permissions: ['read:scep', 'write:scep', 'delete:scep']
  },
  truststore: {
    label: 'Trust Store',
    permissions: ['read:truststore', 'write:truststore', 'delete:truststore']
  },
  hsm: {
    label: 'HSM Management',
    permissions: ['read:hsm', 'write:hsm', 'delete:hsm']
  },
  sso: {
    label: 'Single Sign-On',
    permissions: ['read:sso', 'write:sso', 'delete:sso']
  },
  templates: {
    label: 'Certificate Templates',
    permissions: ['read:templates', 'write:templates', 'delete:templates']
  }
}

const totalPermissions = Object.values(PERMISSION_CATEGORIES).reduce(
  (acc, cat) => acc + cat.permissions.length, 0
)

export default function RBACPage() {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const { modals, open: openModal, close: closeModal } = useModals(['create'])
  const { isMobile } = useMobile()
  
  const [loading, setLoading] = useState(true)
  const [roles, setRoles] = useState([])
  const [selectedRole, setSelectedRole] = useState(null)
  const [filterType, setFilterType] = useState('')
  
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    permissions: [],
    inherits_from: null,
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
      showError(ERRORS.LOAD_FAILED.ROLES)
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async () => {
    try {
      await apiClient.post('/rbac/roles', formData)
      showSuccess(SUCCESS.CREATE.ROLE)
      closeModal('create')
      loadRoles()
      setFormData({ name: '', description: '', permissions: [], inherits_from: null, is_system: false })
    } catch (error) {
      showError(error.message || ERRORS.CREATE_FAILED.ROLE)
    }
  }

  const handleUpdate = async () => {
    if (!selectedRole || selectedRole.is_system) return
    try {
      await apiClient.put(`/rbac/roles/${selectedRole.id}`, {
        ...selectedRole,
        permissions: selectedRole.permissions
      })
      showSuccess(SUCCESS.UPDATE.ROLE)
      loadRoles()
    } catch (error) {
      showError(error.message || ERRORS.UPDATE_FAILED.ROLE)
    }
  }

  const handleDelete = async (role) => {
    if (role.is_system) {
      showError(CONFIRM.RBAC.SYSTEM_ROLE)
      return
    }
    if (!confirm(CONFIRM.RBAC.DELETE_ROLE.replace('{name}', role.name))) return
    try {
      await apiClient.delete(`/rbac/roles/${role.id}`)
      showSuccess(SUCCESS.DELETE.ROLE)
      setSelectedRole(null)
      loadRoles()
    } catch (error) {
      showError(error.message || ERRORS.DELETE_FAILED.ROLE)
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

  // Table columns with icon-bg classes
  const columns = [
    {
      key: 'name',
      header: t('rbac.roleName'),
      priority: 1,
      sortable: true,
      render: (val, row) => (
        <div className="flex items-center gap-2">
          <div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${
            row.is_system ? 'icon-bg-amber' : 'icon-bg-violet'
          }`}>
            {row.is_system ? <Lock size={14} weight="duotone" /> : <Shield size={14} weight="duotone" />}
          </div>
          <span className="font-medium truncate">{val}</span>
        </div>
      ),
      mobileRender: (val, row) => (
        <div className="flex items-center justify-between gap-2 w-full">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${
              row.is_system ? 'icon-bg-amber' : 'icon-bg-violet'
            }`}>
              {row.is_system ? <Lock size={14} weight="duotone" /> : <Shield size={14} weight="duotone" />}
            </div>
            <span className="font-medium truncate">{val}</span>
          </div>
          <Badge variant={row.is_system ? 'warning' : 'success'} size="sm" dot>
            {row.is_system ? t('rbac.systemRole') : t('rbac.customRole')}
          </Badge>
        </div>
      )
    },
    {
      key: 'is_system',
      header: t('rbac.roleType'),
      priority: 2,
      sortable: true,
      hideOnMobile: true,
      render: (val) => (
        <Badge variant={val ? 'warning' : 'success'} size="sm" dot>
          {val ? t('rbac.systemRole') : t('rbac.customRole')}
        </Badge>
      )
    },
    {
      key: 'inherits_from',
      header: t('rbac.inherits'),
      priority: 3,
      hideOnMobile: true,
      render: (val, row) => val ? (
        <Badge variant="cyan" size="sm" icon={Shield}>
          {row.parent_name || `#${val}`}
        </Badge>
      ) : (
        <span className="text-text-tertiary text-xs">—</span>
      )
    },
    {
      key: 'permissions',
      header: t('rbac.permissions'),
      priority: 2,
      hideOnMobile: true,
      render: (val, row) => {
        const permCount = row.all_permissions?.length || val?.length || 0
        const percentage = Math.round((permCount / totalPermissions) * 100)
        return (
          <div className="flex items-center gap-2">
            <div className="w-16 h-1.5 bg-bg-tertiary rounded-full overflow-hidden">
              <div className="h-full bg-accent-primary transition-all" style={{ width: `${percentage}%` }} />
            </div>
            <span className="text-xs text-text-secondary">{permCount}</span>
          </div>
        )
      },
      mobileRender: (val, row) => {
        const permCount = row.all_permissions?.length || val?.length || 0
        return (
          <div className="flex items-center gap-2 text-xs">
            <span className="text-text-tertiary">{t('rbac.permissions')}:</span>
            <span className="text-text-secondary">{permCount}</span>
          </div>
        )
      }
    },
    {
      key: 'user_count',
      header: t('rbac.users'),
      priority: 3,
      hideOnMobile: true,
      render: (val) => (
        <Badge variant={val > 0 ? 'primary' : 'secondary'} size="sm">
          {val || 0}
        </Badge>
      )
    }
  ]

  const rowActions = (row) => row.is_system ? [] : [
    { label: t('common.delete'), icon: Trash, variant: 'danger', onClick: () => handleDelete(row) }
  ]

  const stats = useMemo(() => {
    const systemRoles = roles.filter(r => r.is_system).length
    const customRoles = roles.filter(r => !r.is_system).length
    const totalUsers = roles.reduce((acc, r) => acc + (r.user_count || 0), 0)
    return [
      { label: t('rbac.stats.total'), value: roles.length, icon: Shield, variant: 'primary' },
      { label: t('rbac.stats.system'), value: systemRoles, icon: Lock, variant: 'warning' },
      { label: t('rbac.stats.custom'), value: customRoles, icon: Shield, variant: 'success' },
      { label: t('rbac.stats.users'), value: totalUsers, icon: UsersThree, variant: 'cyan' },
    ]
  }, [roles, t])

  // Help content
  const helpContent = (
    <div className="space-y-4">
      <HelpCard title="RBAC" variant="info">
        {t('rbac.helpInfo')}
      </HelpCard>
      <HelpCard title={t('rbac.systemRole')} variant="warning">
        {t('rbac.helpSystemRoles')}
      </HelpCard>
    </div>
  )

  // Details panel content
  const renderDetails = (role) => (
    <div className="p-3 space-y-3">
      <CompactHeader
        icon={role.is_system ? Lock : Shield}
        iconClass={role.is_system ? 'icon-bg-amber' : 'icon-bg-violet'}
        title={role.name}
        subtitle={role.description || 'No description'}
        badge={
          <Badge variant={role.is_system ? 'secondary' : 'primary'} size="sm">
            {role.is_system ? t('rbac.systemRole') : t('rbac.customRole')}
          </Badge>
        }
      />

      <CompactStats stats={[
        { icon: CheckCircle, value: t('rbac.permissionCount', { count: role.permissions?.length || 0 }) },
        { icon: UsersThree, value: t('rbac.userCount', { count: role.user_count || 0 }) },
      ]} />

      {!role.is_system && (
        <div className="flex gap-2">
          <Button size="sm" className="flex-1" onClick={handleUpdate}>
            <CheckCircle size={14} /> {t('rbac.saveChanges')}
          </Button>
          <Button size="sm" variant="danger" onClick={() => handleDelete(role)}>
            <Trash size={14} />
          </Button>
        </div>
      )}

      {role.is_system && (
        <div className="p-3 rounded-lg status-warning-bg status-warning-border border">
          <div className="flex items-center gap-2 status-warning-text text-xs">
            <Warning size={14} />
            <span>{t('rbac.systemRoleWarning')}</span>
          </div>
        </div>
      )}

      <CompactSection title={t('rbac.roleInformation')}>
        <CompactGrid>
          <CompactField label={t('common.name')} value={role.name} />
          <CompactField label={t('rbac.roleType')} value={role.is_system ? t('rbac.systemRole') : t('rbac.customRole')} />
          {role.inherits_from && (
            <CompactField label={t('rbac.inheritsFrom')} value={role.parent_name || `Role #${role.inherits_from}`} />
          )}
        </CompactGrid>
        {role.description && <p className="text-xs text-text-secondary mt-2">{role.description}</p>}
      </CompactSection>

      <CompactSection title={t('rbac.permissions')}>
        <div className="space-y-4">
          {Object.entries(PERMISSION_CATEGORIES).map(([key, category]) => {
            const categoryPerms = category.permissions
            const directPerms = role.permissions || []
            const allPerms = role.all_permissions || directPerms
            const allSelected = categoryPerms.every(p => allPerms.includes(p))
            const someSelected = categoryPerms.some(p => allPerms.includes(p))

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
                    const isDirect = directPerms.includes(perm)
                    const isInherited = !isDirect && allPerms.includes(perm)
                    const permLabel = perm.split(':')[0]
                    return (
                      <button
                        key={perm}
                        onClick={() => togglePermission(perm)}
                        disabled={role.is_system || isInherited}
                  title={isInherited ? t('rbac.inherited', { name: role.parent_name }) : undefined}
                        className={`flex items-center gap-1 px-2 py-1 rounded text-2xs transition-all ${
                          isDirect
                            ? 'status-success-bg status-success-text status-success-border border'
                            : isInherited
                            ? 'status-primary-bg status-primary-text border border-dashed border-accent-primary/30'
                            : 'bg-bg-tertiary text-text-secondary hover:bg-bg-tertiary/80'
                        } disabled:opacity-50 disabled:cursor-not-allowed`}
                      >
                        {isDirect ? <CheckCircle size={10} weight="fill" /> : isInherited ? <CheckCircle size={10} weight="duotone" /> : <XCircle size={10} />}
                        {permLabel}
                        {isInherited && <span className="opacity-60">↑</span>}
                      </button>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
      </CompactSection>

      <CompactSection title={t('rbac.coverage')}>
        <div className="flex items-center gap-4">
          <div className="flex-1 bg-bg-tertiary rounded-full h-2 overflow-hidden">
            <div className="h-full bg-accent-primary transition-all" style={{ width: `${((role.permissions?.length || 0) / totalPermissions) * 100}%` }} />
          </div>
          <span className="text-xs text-text-secondary">{role.permissions?.length || 0}/{totalPermissions}</span>
        </div>
      </CompactSection>
    </div>
  )

  return (
    <>
      <ResponsiveLayout
        title={t('rbac.title')}
        subtitle={t('rbac.subtitle', { count: roles.length })}
        icon={Shield}
        stats={stats}
        helpContent={helpContent}
        helpTitle={t('rbac.helpTitle')}
        helpPageKey="rbac"
        splitView={true}
        splitEmptyContent={
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="w-14 h-14 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
              <Shield size={24} className="text-text-tertiary" weight="duotone" />
            </div>
            <p className="text-sm text-text-secondary">{t('rbac.selectRole')}</p>
          </div>
        }
        slideOverOpen={!!selectedRole}
        slideOverTitle={selectedRole?.name || 'Role Details'}
        slideOverContent={selectedRole && renderDetails(selectedRole)}
        slideOverWidth="lg"
        onSlideOverClose={() => setSelectedRole(null)}
      >
        <div className="flex flex-col h-full min-h-0">
          <ResponsiveDataTable
            data={roles}
            columns={columns}
            loading={loading}
            onRowClick={setSelectedRole}
            selectedId={selectedRole?.id}
            rowActions={rowActions}
            searchable
            searchPlaceholder={t('rbac.searchRoles')}
            searchKeys={['name', 'description']}
            toolbarFilters={[
              {
                key: 'is_system',
                value: filterType,
                onChange: setFilterType,
                placeholder: t('rbac.allTypes'),
                options: [
                  { value: 'true', label: t('rbac.systemRole') },
                  { value: 'false', label: t('rbac.customRole') }
                ]
              }
            ]}
            toolbarActions={
              isMobile ? (
                <Button size="lg" onClick={() => openModal('create')} className="w-11 h-11 p-0">
                  <Plus size={22} weight="bold" />
                </Button>
              ) : (
                <Button size="sm" onClick={() => openModal('create')}>
                  <Plus size={16} /> {t('rbac.createRole')}
                </Button>
              )
            }
            emptyIcon={Shield}
            emptyTitle={t('rbac.noRoles')}
            emptyDescription={t('rbac.noRolesDescription')}
            emptyAction={
              <Button onClick={() => openModal('create')}>
                <Plus size={16} /> {t('rbac.createRole')}
              </Button>
            }
          />
        </div>
      </ResponsiveLayout>

      <FormModal
        open={modals.create}
        onClose={() => closeModal('create')}
        title={t('rbac.createCustomRole')}
        onSubmit={handleCreate}
        submitLabel={t('common.create')}
        disabled={!formData.name}
      >
        <Input
          label={t('rbac.roleName')}
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          placeholder={t('rbac.roleNamePlaceholder')}
        />
        <Input
          label={t('common.description')}
          value={formData.description}
          onChange={(e) => setFormData({ ...formData, description: e.target.value })}
          placeholder={t('rbac.roleDescription')}
        />
        <FormSelect
          label={t('rbac.inheritsFrom')}
          value={formData.inherits_from?.toString() || '__none__'}
          onChange={(value) => setFormData({ ...formData, inherits_from: value && value !== '__none__' ? parseInt(value) : null })}
          options={[
            { value: '__none__', label: t('rbac.inheritNone') },
            ...roles.filter(r => !r.is_system).map(r => ({
              value: r.id.toString(),
              label: r.name
            }))
          ]}
          hint={t('rbac.inheritHint')}
        />
      </FormModal>
    </>
  )
}
