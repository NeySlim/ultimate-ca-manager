/**
 * Users Page - User management with PageLayout
 */
import { useState, useEffect } from 'react'
import { 
  User, Plus, Trash, LockKey, ToggleLeft, ToggleRight, 
  ShieldCheck, UserCircle, Eye, MagnifyingGlass, UsersThree
} from '@phosphor-icons/react'
import {
  PageLayout, FocusItem, Button, Badge, Card,
  Input, Select, Modal,
  LoadingSpinner, EmptyState, StatusIndicator, PermissionsDisplay, HelpCard
} from '../components'
import { usersService, rolesService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, useModals } from '../hooks'
import { extractData } from '../lib/utils'

export default function UsersPage() {
  const { showSuccess, showError, showConfirm } = useNotification()
  const { canWrite } = usePermission()
  const { modals, open: openModal, close: closeModal } = useModals(['create'])
  
  const [users, setUsers] = useState([])
  const [selectedUser, setSelectedUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [formData, setFormData] = useState({})
  const [roleFilter, setRoleFilter] = useState('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [rolesData, setRolesData] = useState(null)

  // Load roles data on mount
  useEffect(() => {
    loadRolesData()
  }, [])

  useEffect(() => {
    loadUsers()
  }, [roleFilter])

  const loadRolesData = async () => {
    try {
      const data = await rolesService.getAll()
      setRolesData(data)
    } catch (error) {
      console.error('Failed to load roles:', error)
      showError('Failed to load role permissions')
    }
  }

  const loadUsers = async () => {
    setLoading(true)
    try {
      const data = await usersService.getAll({
        role: roleFilter !== 'all' ? roleFilter : undefined
      })
      const usersList = data.data || []
      setUsers(usersList)
      if (usersList.length > 0 && !selectedUser) {
        selectUser(usersList[0])
      }
    } catch (error) {
      showError(error.message || 'Failed to load users')
    } finally {
      setLoading(false)
    }
  }

  const selectUser = async (user) => {
    try {
      const response = await usersService.getById(user.id)
      const data = extractData(response)
      setSelectedUser({ ...data })
      setFormData({ ...data })
      setEditing(false)
    } catch (error) {
      console.error('Failed to load user:', error)
      showError(error.message || 'Failed to load user details')
    }
  }

  const handleCreate = async (newUserData) => {
    try {
      const response = await usersService.create(newUserData)
      const created = extractData(response)
      showSuccess('User created successfully')
      closeModal('create')
      loadUsers()
      if (created?.id) {
        selectUser(created)
      }
    } catch (error) {
      showError(error.message || 'Failed to create user')
    }
  }

  const handleUpdate = async () => {
    try {
      await usersService.update(selectedUser.id, formData)
      showSuccess('User updated successfully')
      setEditing(false)
      loadUsers()
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
      setSelectedUser(null)
      loadUsers()
    } catch (error) {
      showError(error.message || 'Failed to delete user')
    }
  }

  const handleToggleActive = async (id) => {
    try {
      await usersService.toggleActive(id)
      showSuccess('User status updated')
      loadUsers()
      if (selectedUser?.id === id) {
        selectUser(selectedUser)
      }
    } catch (error) {
      showError(error.message || 'Failed to toggle user status')
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

  const updateFormData = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  // Calculate user stats by role
  const adminCount = users.filter(u => u.role === 'admin').length
  const operatorCount = users.filter(u => u.role === 'operator').length
  const viewerCount = users.filter(u => u.role === 'viewer').length
  const activeCount = users.filter(u => u.active).length

  // Filter users by search
  const filteredUsers = users.filter(user => {
    if (!searchQuery) return true
    const query = searchQuery.toLowerCase()
    return (
      user.username?.toLowerCase().includes(query) ||
      user.email?.toLowerCase().includes(query) ||
      user.full_name?.toLowerCase().includes(query)
    )
  })

  // Help content for modal
  const helpContent = (
    <div className="space-y-4">
      {/* User Statistics */}
      <Card className="p-4 space-y-3 bg-gradient-to-br from-accent-primary/5 to-transparent">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <UsersThree size={16} className="text-accent-primary" />
          User Statistics
        </h3>
        <div className="grid grid-cols-2 gap-3">
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-text-primary">{users.length}</p>
            <p className="text-xs text-text-secondary">Total Users</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-status-success">{activeCount}</p>
            <p className="text-xs text-text-secondary">Active</p>
          </div>
        </div>
      </Card>

      {/* Role Distribution */}
      <Card className="p-4 space-y-3 bg-gradient-to-br from-emerald-500/10 to-transparent">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <ShieldCheck size={16} className="text-accent-primary" />
          Role Distribution
        </h3>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary flex items-center gap-2">
              <ShieldCheck size={14} className="text-status-error" />
              Administrators
            </span>
            <span className="text-sm font-medium text-text-primary">{adminCount}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary flex items-center gap-2">
              <UserCircle size={14} className="text-status-warning" />
              Operators
            </span>
            <span className="text-sm font-medium text-text-primary">{operatorCount}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary flex items-center gap-2">
              <Eye size={14} className="text-status-info" />
              Viewers
            </span>
            <span className="text-sm font-medium text-text-primary">{viewerCount}</span>
          </div>
        </div>
      </Card>

      {/* Help Cards */}
      <div className="space-y-3">
        <HelpCard variant="info" title="User Management">
          Manage user accounts, assign roles, and control access permissions. 
          Each user has a role that determines what actions they can perform.
        </HelpCard>
        
        <HelpCard variant="tip" title="Role-Based Access">
          Administrators have full access. Operators can manage CAs and certificates. 
          Viewers have read-only access to all resources.
        </HelpCard>

        <HelpCard variant="warning" title="Security Best Practices">
          Enforce strong passwords, enable 2FA for admin accounts, and regularly 
          review user access. Disable inactive accounts promptly.
        </HelpCard>
      </div>
    </div>
  )

  // Focus panel content (user list with search and filter)
  const focusContent = (
    <div className="p-2 space-y-1.5">
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <LoadingSpinner />
        </div>
      ) : filteredUsers.length === 0 ? (
        <EmptyState 
          icon={User}
          title="No users"
          description={searchQuery ? "No matching users" : "Create your first user"}
        />
      ) : (
        filteredUsers.map((user) => {
          const isSelected = selectedUser?.id === user.id
          return (
            <FocusItem
              key={user.id}
              icon={user.role === 'admin' ? ShieldCheck : User}
              title={user.username}
              subtitle={user.email}
              badge={
                <div className="flex items-center gap-1">
                  <Badge 
                    variant={user.role === 'admin' ? 'primary' : user.role === 'operator' ? 'warning' : 'secondary'} 
                    size="sm"
                  >
                    {user.role}
                  </Badge>
                  {!user.active && (
                    <Badge variant="danger" size="sm">Inactive</Badge>
                  )}
                </div>
              }
              selected={isSelected}
              onClick={() => selectUser(user)}
            />
          )
        })
      )}
    </div>
  )

  // Focus panel actions
  const focusActions = canWrite('users') && (
    <Button onClick={() => openModal('create')} size="sm" className="w-full">
      <Plus size={16} />
      Create User
    </Button>
  )

  if (loading && users.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <LoadingSpinner />
      </div>
    )
  }

  return (
    <>
      <PageLayout
        title="Users"
        focusTitle="Users"
        focusContent={
          <div className="flex flex-col h-full">
            {/* Search and Filter */}
            <div className="p-3 space-y-2 border-b border-border">
              <div className="relative">
                <MagnifyingGlass size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-tertiary" />
                <input
                  type="text"
                  placeholder="Search users..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-8 pr-3 py-1.5 text-sm bg-bg-tertiary border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-accent-primary text-text-primary placeholder:text-text-tertiary"
                />
              </div>
              <Select
                options={[
                  { value: 'all', label: 'All Roles' },
                  { value: 'admin', label: 'Administrators' },
                  { value: 'operator', label: 'Operators' },
                  { value: 'viewer', label: 'Viewers' },
                ]}
                value={roleFilter}
                onChange={setRoleFilter}
              />
            </div>
            {/* User List */}
            <div className="flex-1 overflow-auto">
              {focusContent}
            </div>
          </div>
        }
        focusActions={focusActions}
        focusFooter={`${filteredUsers.length} user(s)`}
        helpContent={helpContent}
        helpTitle="Users - Help"
      >
        {/* Main Content - User Details */}
        {!selectedUser ? (
          <div className="flex items-center justify-center h-full">
            <EmptyState 
              icon={User}
              title="Select a User"
              description="Choose a user from the list to view details"
            />
          </div>
        ) : (
          <div className="p-6 space-y-6">
            {/* Header with actions */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-full bg-accent-primary/10 flex items-center justify-center">
                  {selectedUser.role === 'admin' ? (
                    <ShieldCheck size={24} className="text-accent-primary" />
                  ) : (
                    <User size={24} className="text-accent-primary" />
                  )}
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-text-primary">{selectedUser.username}</h2>
                  <p className="text-sm text-text-secondary">{selectedUser.email}</p>
                </div>
              </div>
              {canWrite('users') && (
                <div className="flex items-center gap-2">
                  {editing ? (
                    <>
                      <Button size="sm" onClick={handleUpdate}>Save</Button>
                      <Button variant="ghost" size="sm" onClick={() => {
                        setEditing(false)
                        setFormData({ ...selectedUser })
                      }}>Cancel</Button>
                    </>
                  ) : (
                    <>
                      <Button variant="secondary" size="sm" onClick={() => setEditing(true)}>Edit</Button>
                      <Button 
                        variant="secondary" 
                        size="sm" 
                        onClick={() => handleToggleActive(selectedUser.id)}
                      >
                        {selectedUser.active ? <ToggleRight size={16} /> : <ToggleLeft size={16} />}
                        {selectedUser.active ? 'Disable' : 'Enable'}
                      </Button>
                      <Button 
                        variant="secondary" 
                        size="sm" 
                        onClick={() => handleResetPassword(selectedUser.id)}
                      >
                        <LockKey size={16} />
                        Reset Password
                      </Button>
                      <Button variant="danger" size="sm" onClick={() => handleDelete(selectedUser.id)}>
                        <Trash size={16} />
                        Delete
                      </Button>
                    </>
                  )}
                </div>
              )}
            </div>

            {/* Basic Info */}
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-4 uppercase tracking-wide">Basic Information</h3>
              <div className="grid grid-cols-2 gap-4">
                <Input
                  label="Username"
                  value={formData.username || ''}
                  onChange={(e) => updateFormData('username', e.target.value)}
                  disabled={!editing}
                />
                <Input
                  label="Email"
                  type="email"
                  value={formData.email || ''}
                  onChange={(e) => updateFormData('email', e.target.value)}
                  disabled={!editing}
                />
                <Input
                  label="Full Name"
                  value={formData.full_name || ''}
                  onChange={(e) => updateFormData('full_name', e.target.value)}
                  disabled={!editing}
                />
                <div className="flex items-center gap-3 pt-6">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.active || false}
                      onChange={(e) => updateFormData('active', e.target.checked)}
                      disabled={!editing}
                      className="rounded border-border bg-bg-tertiary"
                    />
                    <span className="text-sm text-text-primary">Active</span>
                  </label>
                </div>
              </div>
            </div>

            {/* Role & Permissions */}
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-4 uppercase tracking-wide">Role & Permissions</h3>
              <div className="grid grid-cols-2 gap-4">
                <Select
                  label="Role"
                  options={[
                    { value: 'admin', label: 'Administrator' },
                    { value: 'operator', label: 'Operator' },
                    { value: 'viewer', label: 'Viewer' },
                  ]}
                  value={formData.role || 'viewer'}
                  onChange={(val) => updateFormData('role', val)}
                  disabled={!editing}
                />
                <div>
                  <p className="text-sm font-medium text-text-primary mb-2">Permissions</p>
                  {rolesData && formData.role && (
                    <PermissionsDisplay
                      role={formData.role}
                      permissions={rolesData[formData.role]?.permissions || []}
                      description={rolesData[formData.role]?.description}
                    />
                  )}
                  {!rolesData && (
                    <div className="text-xs text-text-secondary">Loading permissions...</div>
                  )}
                </div>
              </div>
            </div>

            {/* Security */}
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-4 uppercase tracking-wide">Security</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <p className="text-xs text-text-secondary uppercase mb-1">2FA Status</p>
                  <Badge variant={selectedUser.two_factor_enabled ? 'success' : 'secondary'}>
                    {selectedUser.two_factor_enabled ? 'Enabled' : 'Disabled'}
                  </Badge>
                </div>
                <div>
                  <p className="text-xs text-text-secondary uppercase mb-1">Last Password Change</p>
                  <p className="text-sm text-text-primary">
                    {selectedUser.password_changed_at 
                      ? new Date(selectedUser.password_changed_at).toLocaleDateString()
                      : 'Never'}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-secondary uppercase mb-1">Login Count</p>
                  <p className="text-sm text-text-primary">{selectedUser.login_count || 0}</p>
                </div>
                <div>
                  <p className="text-xs text-text-secondary uppercase mb-1">Failed Logins</p>
                  <p className="text-sm text-text-primary">{selectedUser.failed_login_count || 0}</p>
                </div>
              </div>
            </div>

            {/* Activity */}
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-4 uppercase tracking-wide">Activity</h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <div>
                  <p className="text-xs text-text-secondary uppercase mb-1">Last Login</p>
                  <p className="text-sm text-text-primary">
                    {selectedUser.last_login 
                      ? new Date(selectedUser.last_login).toLocaleString()
                      : 'Never'}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-secondary uppercase mb-1">Created</p>
                  <p className="text-sm text-text-primary">
                    {selectedUser.created_at ? new Date(selectedUser.created_at).toLocaleDateString() : '-'}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-secondary uppercase mb-1">Account Status</p>
                  <StatusIndicator status={selectedUser.active ? 'success' : 'warning'}>
                    {selectedUser.active ? 'Active' : 'Inactive'}
                  </StatusIndicator>
                </div>
              </div>
            </div>
          </div>
        )}
      </PageLayout>

      {/* Create User Modal */}
      <Modal
        open={modals.create}
        onClose={() => closeModal('create')}
        title="Create New User"
      >
        <CreateUserForm
          onSubmit={handleCreate}
          onCancel={() => closeModal('create')}
        />
      </Modal>
    </>
  )
}

function CreateUserForm({ onSubmit, onCancel }) {
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    full_name: '',
    password: '',
    role: 'user',
    active: true,
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    onSubmit(formData)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
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
        label="Password"
        type="password"
        value={formData.password}
        onChange={(e) => setFormData(prev => ({ ...prev, password: e.target.value }))}
        required
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
      
      <div className="flex gap-3 pt-4">
        <Button type="submit">Create User</Button>
        <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  )
}
