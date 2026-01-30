/**
 * Users Page - User management with Pro Groups tab
 * 
 * Pro features (Groups) are dynamically added when Pro module is present
 */
import { useState, useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { 
  User, Plus, Trash, LockKey, PencilSimple, Clock,
  ShieldCheck, UserCircle, Eye, UsersThree
} from '@phosphor-icons/react'
import {
  ListPageLayout, Badge, Button, Modal, Input, Select,
  DetailHeader, DetailSection, DetailGrid, DetailField, HelpCard
} from '../components'
import { usersService, rolesService } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { formatDate, extractData } from '../lib/utils'

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
        {/* Tab Navigation */}
        <TabNavigation 
          tabs={allTabs} 
          activeTab={activeTab} 
          onTabChange={handleTabChange} 
        />
        {/* Pro Tab Content - full size, let component control layout */}
        <div className="flex-1 min-h-0 w-full">
          <ProComponent />
        </div>
      </div>
    )
  }
  
  // Default: render Users tab
  return (
    <div className="flex flex-col h-full w-full">
      {/* Only show tabs if there are Pro tabs */}
      {proTabs.length > 0 && (
        <TabNavigation 
          tabs={allTabs} 
          activeTab={activeTab} 
          onTabChange={handleTabChange} 
        />
      )}
      {/* Users Content */}
      <div className="flex-1 min-h-0 w-full">
        <UsersContent />
      </div>
    </div>
  )
}

// Tab navigation component
function TabNavigation({ tabs, activeTab, onTabChange }) {
  return (
    <div className="border-b border-border bg-bg-secondary px-4 shrink-0">
      <div className="flex gap-1">
        {tabs.map(tab => {
          const Icon = tab.icon
          const isActive = activeTab === tab.id
          return (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                isActive 
                  ? 'border-accent-primary text-accent-primary' 
                  : 'border-transparent text-text-secondary hover:text-text-primary'
              }`}
            >
              <Icon size={16} />
              {tab.label}
              {tab.pro && <Badge variant="info" size="sm">Pro</Badge>}
            </button>
          )
        })}
      </div>
    </div>
  )
}

// Users content (extracted from original UsersPage)
function UsersContent() {
  const [users, setUsers] = useState([])
  const [selectedUser, setSelectedUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showEditModal, setShowEditModal] = useState(false)
  const [rolesData, setRolesData] = useState(null)
  const { showSuccess, showError, showConfirm } = useNotification()
  const { canWrite, canDelete } = usePermission()

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

  // Table filters
  const tableFilters = useMemo(() => [
    {
      key: 'role',
      label: 'Role',
      options: [
        { value: 'admin', label: 'Admin' },
        { value: 'operator', label: 'Operator' },
        { value: 'viewer', label: 'Viewer' }
      ]
    },
    {
      key: 'active',
      label: 'Status',
      options: [
        { value: true, label: 'Active' },
        { value: false, label: 'Inactive' }
      ]
    }
  ], [])

  // Table columns
  const columns = [
    {
      key: 'username',
      header: 'Username',
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
      render: (val) => val || '—'
    },
    {
      key: 'role',
      header: 'Role',
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
      sortType: 'date',
      render: (val) => val ? formatDate(val) : 'Never'
    }
  ]

  // Row actions
  const rowActions = (row) => [
    ...(canWrite('users') ? [
      { label: 'Edit', icon: PencilSimple, onClick: () => { setSelectedUser(row); setShowEditModal(true) }},
      { label: 'Reset Password', icon: LockKey, onClick: () => handleResetPassword(row.id) }
    ] : []),
    ...(canDelete('users') ? [
      { label: 'Delete', icon: Trash, variant: 'danger', onClick: () => handleDelete(row.id) }
    ] : [])
  ]

  // Render details panel
  const renderDetails = (user) => (
    <div className="p-4 space-y-4">
      <DetailHeader
        icon={user.role === 'admin' ? ShieldCheck : User}
        title={user.username}
        subtitle={user.email}
        badge={
          <Badge 
            variant={
              user.role === 'admin' ? 'primary' :
              user.role === 'operator' ? 'warning' : 'secondary'
            }
          >
            {user.role || 'viewer'}
          </Badge>
        }
        stats={[
          { icon: Clock, label: 'Last Login', value: user.last_login ? formatDate(user.last_login) : 'Never' },
          { icon: LockKey, label: '2FA', value: user.two_factor_enabled ? 'Enabled' : 'Disabled' },
        ]}
        actions={[
          ...(canWrite('users') ? [
            { label: 'Edit', icon: PencilSimple, onClick: () => setShowEditModal(true) },
            { label: 'Reset Password', icon: LockKey, onClick: () => handleResetPassword(user.id) }
          ] : []),
          ...(canDelete('users') ? [
            { label: 'Delete', icon: Trash, variant: 'danger', onClick: () => handleDelete(user.id) }
          ] : [])
        ]}
      />

      <DetailSection title="Basic Information">
        <DetailGrid>
          <DetailField label="Username" value={user.username} />
          <DetailField label="Email" value={user.email} copyable />
          <DetailField label="Full Name" value={user.full_name} />
          <DetailField 
            label="Status" 
            value={
              <Badge variant={user.active ? 'success' : 'danger'}>
                {user.active ? 'Active' : 'Inactive'}
              </Badge>
            }
          />
        </DetailGrid>
      </DetailSection>

      <DetailSection title="Role & Permissions">
        <DetailGrid>
          <DetailField 
            label="Role" 
            value={
              <Badge variant={user.role === 'admin' ? 'primary' : user.role === 'operator' ? 'warning' : 'secondary'}>
                {user.role || 'viewer'}
              </Badge>
            }
          />
          <DetailField 
            label="Description" 
            value={rolesData?.[user.role]?.description || 'Standard user permissions'}
          />
        </DetailGrid>
      </DetailSection>

      <DetailSection title="Security">
        <DetailGrid>
          <DetailField 
            label="2FA Status" 
            value={
              <Badge variant={user.two_factor_enabled ? 'success' : 'secondary'}>
                {user.two_factor_enabled ? 'Enabled' : 'Disabled'}
              </Badge>
            }
          />
          <DetailField 
            label="Password Changed" 
            value={user.password_changed_at ? formatDate(user.password_changed_at) : 'Never'}
          />
          <DetailField label="Login Count" value={user.login_count || 0} />
          <DetailField label="Failed Logins" value={user.failed_login_count || 0} />
        </DetailGrid>
      </DetailSection>

      <DetailSection title="Activity">
        <DetailGrid>
          <DetailField label="Last Login" value={user.last_login ? formatDate(user.last_login) : 'Never'} />
          <DetailField label="Created" value={user.created_at ? formatDate(user.created_at) : '—'} />
        </DetailGrid>
      </DetailSection>
    </div>
  )

  // Help content
  const helpContent = (
    <div className="space-y-4">
      <HelpCard title="User Management" variant="info">
        Manage user accounts, assign roles, and control access permissions.
      </HelpCard>
      <HelpCard title="Roles" variant="default">
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
      <ListPageLayout
        title="Users"
        data={users}
        columns={columns}
        loading={loading}
        selectedItem={selectedUser}
        onSelectItem={(user) => user ? loadUserDetails(user) : setSelectedUser(null)}
        renderDetails={renderDetails}
        detailsTitle="User Details"
        searchable
        searchPlaceholder="Search users..."
        searchKeys={['username', 'email', 'full_name', 'role']}
        sortable
        defaultSort={{ key: 'username', direction: 'asc' }}
        paginated
        pageSize={25}
        rowActions={rowActions}
        filters={tableFilters}
        emptyIcon={User}
        emptyTitle="No users"
        emptyDescription="Create your first user to get started"
        emptyAction={canWrite('users') && (
          <Button onClick={() => setShowCreateModal(true)}>
            <Plus size={16} /> New User
          </Button>
        )}
        helpContent={helpContent}
        actions={canWrite('users') && (
          <Button size="sm" onClick={() => setShowCreateModal(true)}>
            <Plus size={16} /> New User
          </Button>
        )}
      />

      {/* Create User Modal */}
      <Modal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
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
        onClose={() => setShowEditModal(false)}
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
