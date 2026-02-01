/**
 * Users Page - User management with Pro Groups tab
 * 
 * Pro features (Groups) are dynamically added when Pro module is present
 * Uses ResponsiveLayout for unified mobile/desktop UX
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { 
  User, Plus, Trash, LockKey, PencilSimple, Clock,
  ShieldCheck, UserCircle, Eye, CheckCircle, XCircle, X
} from '@phosphor-icons/react'
import {
  Badge, Button, Modal, Input, Select, HelpCard,
  CompactSection, CompactGrid, CompactField, CompactStats, CompactHeader
} from '../components'
import { ResponsiveLayout, ResponsiveDataTable } from '../components/ui/responsive'
import { usersService, rolesService } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { useMobile } from '../contexts/MobileContext'
import { formatDate, extractData, cn } from '../lib/utils'

// Base tabs
const BASE_TABS = [
  { id: 'users', label: 'Users', icon: User }
]

export default function UsersPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  
  // Pro tabs (dynamically loaded)
  const [proTabs, setProTabs] = useState([])
  
  // Active tab - from URL or default to 'users'
  const [activeTab, setActiveTab] = useState(searchParams.get('tab') || 'users')
  
  // Dynamically load Pro tabs
  useEffect(() => {
    import('../pro/users')
      .then(module => setProTabs(module.proUsersTabs || []))
      .catch(() => {}) // Pro module not available
  }, [])
  
  // All tabs = base + pro
  const allTabs = useMemo(() => [...BASE_TABS, ...proTabs], [proTabs])
  
  // Handle tab change with URL update
  const handleTabChange = (tabId) => {
    setActiveTab(tabId)
    if (tabId === 'users') {
      searchParams.delete('tab')
    } else {
      searchParams.set('tab', tabId)
    }
    setSearchParams(searchParams, { replace: true })
  }
  
  // Find active Pro tab component
  const activeProTab = proTabs.find(t => t.id === activeTab)
  
  // If active tab is a Pro tab with component, render it
  if (activeProTab?.component) {
    const ProComponent = activeProTab.component
    return (
      <div className="flex flex-col h-full w-full">
        <ProComponent 
          tabs={allTabs}
          activeTab={activeTab}
          onTabChange={handleTabChange}
        />
      </div>
    )
  }
  
  // Default: render Users tab
  return (
    <UsersContent 
      tabs={proTabs.length > 0 ? allTabs : null}
      activeTab={activeTab}
      onTabChange={handleTabChange}
    />
  )
}

// =============================================================================
// USERS CONTENT
// =============================================================================

function UsersContent({ tabs, activeTab, onTabChange }) {
  const { isMobile } = useMobile()
  const [users, setUsers] = useState([])
  const [selectedUser, setSelectedUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showEditModal, setShowEditModal] = useState(false)
  const [rolesData, setRolesData] = useState(null)
  const { showSuccess, showError, showConfirm } = useNotification()
  const { canWrite, canDelete } = usePermission()
  
  // Filters state
  const [filterRole, setFilterRole] = useState('')
  const [filterActive, setFilterActive] = useState('')
  
  // Pagination state
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      setLoading(true)
      const [usersRes, rolesRes] = await Promise.all([
        usersService.getAll(),
        rolesService.getAll()
      ])
      setUsers(usersRes.data || [])
      setRolesData(rolesRes)
    } catch (error) {
      showError('Failed to load users')
    } finally {
      setLoading(false)
    }
  }

  const loadUserDetails = async (user) => {
    try {
      const response = await usersService.getById(user.id)
      setSelectedUser(extractData(response) || user)
    } catch {
      setSelectedUser(user)
    }
  }

  const handleCreate = async (userData) => {
    try {
      await usersService.create(userData)
      showSuccess('User created successfully')
      setShowCreateModal(false)
      loadData()
    } catch (error) {
      showError(error.message || 'Failed to create user')
    }
  }

  const handleEdit = async (userData) => {
    if (!selectedUser) return
    try {
      await usersService.update(selectedUser.id, userData)
      showSuccess('User updated successfully')
      setShowEditModal(false)
      loadData()
    } catch (error) {
      showError(error.message || 'Failed to update user')
    }
  }

  const handleDelete = async (id) => {
    const confirmed = await showConfirm('Are you sure you want to delete this user?', {
      title: 'Delete User',
      confirmText: 'Delete',
      variant: 'danger'
    })
    if (!confirmed) return
    try {
      await usersService.delete(id)
      showSuccess('User deleted successfully')
      loadData()
      setSelectedUser(null)
    } catch (error) {
      showError(error.message || 'Failed to delete user')
    }
  }

  const handleResetPassword = async (id) => {
    const confirmed = await showConfirm('Are you sure you want to reset this user\'s password?', {
      title: 'Reset Password',
      confirmText: 'Reset Password'
    })
    if (!confirmed) return
    try {
      const result = await usersService.resetPassword(id)
      showSuccess(`Password reset. New password: ${result.temporary_password}`)
    } catch (error) {
      showError(error.message || 'Failed to reset password')
    }
  }

  // Filter configuration (same format as CertificatesPage)
  const filters = useMemo(() => [
    {
      key: 'role',
      label: 'Role',
      type: 'select',
      value: filterRole,
      onChange: setFilterRole,
      placeholder: 'All Roles',
      options: [
        { value: 'admin', label: 'Admin' },
        { value: 'operator', label: 'Operator' },
        { value: 'viewer', label: 'Viewer' }
      ]
    },
    {
      key: 'active',
      label: 'Status',
      type: 'select',
      value: filterActive,
      onChange: setFilterActive,
      placeholder: 'All Status',
      options: [
        { value: 'true', label: 'Active' },
        { value: 'false', label: 'Inactive' }
      ]
    }
  ], [filterRole, filterActive])
  
  const activeFiltersCount = (filterRole ? 1 : 0) + (filterActive ? 1 : 0)

  // Filter data
  const filteredUsers = useMemo(() => {
    return users.filter(user => {
      if (filterRole && user.role !== filterRole) return false
      if (filterActive !== '' && String(user.active) !== filterActive) return false
      return true
    })
  }, [users, filterRole, filterActive])

  // Table columns
  const columns = useMemo(() => [
    {
      key: 'username',
      header: 'Username',
      priority: 1,
      render: (val, row) => (
        <div className="flex items-center gap-2">
          <User size={16} className="text-accent-primary shrink-0" />
          <span className="font-medium truncate">{val}</span>
        </div>
      )
    },
    {
      key: 'email',
      header: 'Email',
      priority: 3,
      hideOnMobile: true,
      render: (val) => val || '—'
    },
    {
      key: 'role',
      header: 'Role',
      priority: 2,
      render: (val) => (
        <Badge 
          variant={
            val === 'admin' ? 'primary' :
            val === 'operator' ? 'warning' : 
            'secondary'
          }
          size="sm"
        >
          {val || 'viewer'}
        </Badge>
      )
    },
    {
      key: 'active',
      header: 'Status',
      priority: 4,
      hideOnMobile: true,
      render: (val) => (
        <Badge 
          variant={val ? 'success' : 'danger'}
          size="sm"
        >
          {val ? 'Active' : 'Inactive'}
        </Badge>
      )
    },
    {
      key: 'last_login',
      header: 'Last Login',
      priority: 5,
      hideOnMobile: true,
      render: (val) => val ? formatDate(val) : 'Never'
    }
  ], [])

  // Row actions
  const rowActions = useCallback((row) => [
    ...(canWrite('users') ? [
      { label: 'Edit', icon: PencilSimple, onClick: () => { setSelectedUser(row); setShowEditModal(true) }},
      { label: 'Reset Password', icon: LockKey, onClick: () => handleResetPassword(row.id) }
    ] : []),
    ...(canDelete('users') ? [
      { label: 'Delete', icon: Trash, variant: 'danger', onClick: () => handleDelete(row.id) }
    ] : [])
  ], [canWrite, canDelete])

  // Compute stats from users data
  const stats = useMemo(() => {
    const activeCount = users.filter(u => u.active).length
    const inactiveCount = users.filter(u => !u.active).length
    const adminCount = users.filter(u => u.role === 'admin').length
    const operatorCount = users.filter(u => u.role === 'operator').length
    
    return [
      { label: 'Active', value: activeCount, icon: CheckCircle, variant: 'success' },
      { label: 'Inactive', value: inactiveCount, icon: XCircle, variant: 'danger' },
      { label: 'Admins', value: adminCount, icon: ShieldCheck, variant: 'primary' },
      { label: 'Operators', value: operatorCount, icon: UserCircle, variant: 'warning' },
    ]
  }, [users])

  // Help content
  const helpContent = (
    <div className="space-y-4">
      <HelpCard title="User Management" variant="info">
        Manage user accounts, assign roles, and control access permissions.
      </HelpCard>
      <HelpCard title="Roles" variant="tip">
        <ul className="text-sm space-y-1">
          <li className="flex items-center gap-2">
            <ShieldCheck size={14} className="text-status-error" />
            <Badge variant="primary" size="sm">admin</Badge> - Full system access
          </li>
          <li className="flex items-center gap-2">
            <UserCircle size={14} className="text-status-warning" />
            <Badge variant="warning" size="sm">operator</Badge> - Manage CAs & certs
          </li>
          <li className="flex items-center gap-2">
            <Eye size={14} className="text-status-info" />
            <Badge variant="secondary" size="sm">viewer</Badge> - Read-only access
          </li>
        </ul>
      </HelpCard>
      <HelpCard title="Security Tips" variant="warning">
        Enforce strong passwords, enable 2FA for admin accounts, and regularly review user access.
      </HelpCard>
    </div>
  )

  return (
    <>
      <ResponsiveLayout
        title="Users"
        icon={User}
        tabs={tabs}
        activeTab={activeTab}
        onTabChange={onTabChange}
        stats={stats}
        helpContent={helpContent}
        splitView={true}
        splitEmptyContent={
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="w-14 h-14 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
              <User size={24} className="text-text-tertiary" />
            </div>
            <p className="text-sm text-text-secondary">Select a user to view details</p>
          </div>
        }
        slideOverOpen={!!selectedUser}
        onSlideOverClose={() => setSelectedUser(null)}
        slideOverTitle="User Details"
        slideOverContent={selectedUser && (
          <UserDetails 
            user={selectedUser}
            rolesData={rolesData}
            canWrite={canWrite}
            canDelete={canDelete}
            onEdit={() => setShowEditModal(true)}
            onResetPassword={() => handleResetPassword(selectedUser.id)}
            onDelete={() => handleDelete(selectedUser.id)}
          />
        )}
      >
        <ResponsiveDataTable
          data={filteredUsers}
          columns={columns}
          loading={loading}
          selectedId={selectedUser?.id}
          onRowClick={(user) => user ? loadUserDetails(user) : setSelectedUser(null)}
          rowActions={rowActions}
          searchable
          searchPlaceholder="Search users..."
          searchKeys={['username', 'email', 'full_name', 'role']}
          toolbarFilters={[
            {
              key: 'role',
              value: filterRole,
              onChange: setFilterRole,
              placeholder: 'All Roles',
              options: [
                { value: 'admin', label: 'Admin' },
                { value: 'operator', label: 'Operator' },
                { value: 'viewer', label: 'Viewer' }
              ]
            },
            {
              key: 'active',
              value: filterActive,
              onChange: setFilterActive,
              placeholder: 'All Status',
              options: [
                { value: 'true', label: 'Active' },
                { value: 'false', label: 'Inactive' }
              ]
            }
          ]}
          toolbarActions={canWrite('users') && (
            isMobile ? (
              <Button size="lg" onClick={() => setShowCreateModal(true)} className="w-11 h-11 p-0">
                <Plus size={22} weight="bold" />
              </Button>
            ) : (
              <Button size="sm" onClick={() => setShowCreateModal(true)}>
                <Plus size={14} weight="bold" />
                New User
              </Button>
            )
          )}
          sortable
          emptyIcon={User}
          emptyTitle="No users"
          emptyDescription="Create your first user to get started"
          emptyAction={canWrite('users') && (
            <Button onClick={() => setShowCreateModal(true)}>
              <Plus size={16} /> New User
            </Button>
          )}
        />
      </ResponsiveLayout>

      {/* Create User Modal */}
      <Modal
        open={showCreateModal}
        onOpenChange={setShowCreateModal}
        title="Create New User"
        size="md"
      >
        <UserForm
          onSubmit={handleCreate}
          onCancel={() => setShowCreateModal(false)}
        />
      </Modal>

      {/* Edit User Modal */}
      <Modal
        open={showEditModal}
        onOpenChange={setShowEditModal}
        title="Edit User"
        size="md"
      >
        <UserForm
          user={selectedUser}
          onSubmit={handleEdit}
          onCancel={() => setShowEditModal(false)}
        />
      </Modal>
    </>
  )
}

// =============================================================================
// USER DETAILS PANEL
// =============================================================================

function UserDetails({ user, rolesData, canWrite, canDelete, onEdit, onResetPassword, onDelete }) {
  return (
    <div className="p-3 space-y-3">
      {/* Header */}
      <CompactHeader
        icon={user.role === 'admin' ? ShieldCheck : User}
        iconClass={user.role === 'admin' ? "bg-status-error/20" : "bg-accent-primary/20"}
        title={user.username}
        subtitle={user.email}
        badge={
          <Badge variant={user.role === 'admin' ? 'primary' : user.role === 'operator' ? 'warning' : 'secondary'} size="sm">
            {user.role || 'viewer'}
          </Badge>
        }
      />

      {/* Stats */}
      <CompactStats stats={[
        { icon: Clock, value: user.last_login ? formatDate(user.last_login, 'short') : 'Never logged in' },
        { icon: LockKey, iconClass: user.two_factor_enabled ? "text-status-success" : "text-text-tertiary", value: user.two_factor_enabled ? '2FA On' : '2FA Off' },
        { badge: user.active ? 'Active' : 'Inactive', badgeVariant: user.active ? 'success' : 'danger' }
      ]} />

      {/* Actions */}
      <div className="flex gap-2">
        {canWrite('users') && (
          <>
            <Button size="sm" variant="secondary" className="flex-1" onClick={onEdit}>
              <PencilSimple size={14} /> Edit
            </Button>
            <Button size="sm" variant="secondary" onClick={onResetPassword}>
              <LockKey size={14} />
            </Button>
          </>
        )}
        {canDelete('users') && (
          <Button size="sm" variant="danger" onClick={onDelete}>
            <Trash size={14} />
          </Button>
        )}
      </div>

      {/* Basic Info */}
      <CompactSection title="Basic Information">
        <CompactGrid>
          <CompactField label="Username" value={user.username} />
          <CompactField label="Full Name" value={user.full_name} />
          <CompactField label="Email" value={user.email} className="col-span-2" />
        </CompactGrid>
      </CompactSection>

      {/* Role */}
      <CompactSection title="Role & Permissions">
        <CompactGrid>
          <div className="text-xs">
            <span className="text-text-tertiary">Role:</span>
            <Badge variant={user.role === 'admin' ? 'primary' : user.role === 'operator' ? 'warning' : 'secondary'} size="sm" className="ml-1">
              {user.role || 'viewer'}
            </Badge>
          </div>
          <CompactField label="Desc" value={rolesData?.[user.role]?.description || 'Standard permissions'} />
        </CompactGrid>
      </CompactSection>

      {/* Security */}
      <CompactSection title="Security">
        <CompactGrid>
          <div className="text-xs">
            <span className="text-text-tertiary">2FA:</span>
            <span className={cn("ml-1", user.two_factor_enabled ? "text-status-success" : "text-text-secondary")}>
              {user.two_factor_enabled ? 'Enabled' : 'Disabled'}
            </span>
          </div>
          <CompactField label="Pwd Changed" value={user.password_changed_at ? formatDate(user.password_changed_at, 'short') : 'Never'} />
          <CompactField label="Logins" value={user.login_count || 0} />
          <CompactField label="Failed" value={user.failed_login_count || 0} />
        </CompactGrid>
      </CompactSection>

      {/* Activity */}
      <CompactSection title="Activity">
        <CompactGrid>
          <CompactField label="Last Login" value={user.last_login ? formatDate(user.last_login) : 'Never'} />
          <CompactField label="Created" value={user.created_at ? formatDate(user.created_at, 'short') : '—'} />
        </CompactGrid>
      </CompactSection>
    </div>
  )
}

// =============================================================================
// USER FORM
// =============================================================================

function UserForm({ user, onSubmit, onCancel }) {
  const [formData, setFormData] = useState({
    username: user?.username || '',
    email: user?.email || '',
    full_name: user?.full_name || '',
    password: '',
    role: user?.role || 'viewer',
    active: user?.active ?? true,
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    // Don't send empty password on edit
    const data = { ...formData }
    if (user && !data.password) delete data.password
    onSubmit(data)
  }

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4">
      <Input
        label="Username"
        value={formData.username}
        onChange={(e) => setFormData(prev => ({ ...prev, username: e.target.value }))}
        required
      />
      <Input
        label="Email"
        type="email"
        value={formData.email}
        onChange={(e) => setFormData(prev => ({ ...prev, email: e.target.value }))}
        required
      />
      <Input
        label="Full Name"
        value={formData.full_name}
        onChange={(e) => setFormData(prev => ({ ...prev, full_name: e.target.value }))}
      />
      <Input
        label={user ? "Password (leave blank to keep current)" : "Password"}
        type="password"
        value={formData.password}
        onChange={(e) => setFormData(prev => ({ ...prev, password: e.target.value }))}
        required={!user}
      />
      <Select
        label="Role"
        options={[
          { value: 'admin', label: 'Administrator' },
          { value: 'operator', label: 'Operator' },
          { value: 'viewer', label: 'Viewer' },
        ]}
        value={formData.role}
        onChange={(val) => setFormData(prev => ({ ...prev, role: val }))}
      />
      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="active"
          checked={formData.active}
          onChange={(e) => setFormData(prev => ({ ...prev, active: e.target.checked }))}
          className="rounded border-border bg-bg-tertiary"
        />
        <label htmlFor="active" className="text-sm text-text-primary">Active</label>
      </div>
      
      <div className="flex justify-end gap-3 pt-4">
        <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>
        <Button type="submit">{user ? 'Save Changes' : 'Create User'}</Button>
      </div>
    </form>
  )
}
