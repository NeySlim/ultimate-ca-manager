/**
 * Users Page
 */
import { useState, useEffect } from 'react'
import { User, Plus, Trash, LockKey, ToggleLeft, ToggleRight } from '@phosphor-icons/react'
import {
  ExplorerPanel, DetailsPanel, Table, Button, Badge,
  Input, Select, Modal,
  LoadingSpinner, EmptyState, StatusIndicator
} from '../components'
import { usersService } from '../services'
import { useNotification } from '../contexts'
import { extractData } from '../lib/utils'

export default function UsersPage() {
  const { showSuccess, showError } = useNotification()
  
  const [users, setUsers] = useState([])
  const [selectedUser, setSelectedUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [formData, setFormData] = useState({})
  const [roleFilter, setRoleFilter] = useState('all')

  useEffect(() => {
    loadUsers()
  }, [roleFilter])

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
      console.log('User loaded:', data)
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
      const created = await usersService.create(newUserData)
      showSuccess('User created successfully')
      setShowCreateModal(false)
      loadUsers()
      selectUser(created)
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
    if (!confirm('Are you sure you want to delete this user?')) return
    
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
    if (!confirm('Are you sure you want to reset this user\'s password?')) return
    
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

  const userColumns = [
    { 
      key: 'username', 
      label: 'Username',
      render: (val) => <span className="font-medium">{val}</span>
    },
    { key: 'email', label: 'Email' },
    {
      key: 'role',
      label: 'Role',
      render: (val) => (
        <Badge variant={val === 'admin' ? 'primary' : 'secondary'}>
          {val}
        </Badge>
      )
    },
    {
      key: 'active',
      label: 'Status',
      render: (val) => (
        <div className="flex items-center gap-2">
          <StatusIndicator status={val ? 'active' : 'inactive'} />
          <span className="text-sm">{val ? 'Active' : 'Inactive'}</span>
        </div>
      )
    },
    {
      key: 'last_login',
      label: 'Last Login',
      render: (val) => val ? new Date(val).toLocaleString() : 'Never'
    },
  ]

  return (
    <>
      <ExplorerPanel
        title={selectedUser?.username || 'Select a user'}
        actions={selectedUser && (
          <>
            {editing ? (
              <Button size="sm" onClick={handleUpdate}>
                Save
              </Button>
            ) : (
              <Button variant="secondary" size="sm" onClick={() => setEditing(true)}>
                Edit
              </Button>
            )}
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
      >
        {!selectedUser ? (
          <EmptyState
            title="No user selected"
            description="Select a user from the list to view details"
          />
        ) : (
          <div className="space-y-6">
            {/* Basic Info */}
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-4">Basic Information</h3>
              <div className="space-y-4">
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
                <div className="flex items-center gap-3">
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
              <h3 className="text-sm font-semibold text-text-primary mb-4">Role & Permissions</h3>
              <div className="space-y-4">
                <Select
                  label="Role"
                  options={[
                    { value: 'admin', label: 'Administrator' },
                    { value: 'operator', label: 'Operator' },
                    { value: 'viewer', label: 'Viewer' },
                  ]}
                  value={formData.role || 'user'}
                  onChange={(val) => updateFormData('role', val)}
                  disabled={!editing}
                />
                
                <div>
                  <p className="text-sm font-medium text-text-primary mb-2">Permissions</p>
                  <div className="space-y-2">
                    {['Manage CAs', 'Issue Certificates', 'Revoke Certificates', 'Manage Users', 'View Audit Logs'].map(perm => (
                      <label key={perm} className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={formData.permissions?.includes(perm) || false}
                          onChange={(e) => {
                            const newPerms = e.target.checked
                              ? [...(formData.permissions || []), perm]
                              : (formData.permissions || []).filter(p => p !== perm)
                            updateFormData('permissions', newPerms)
                          }}
                          disabled={!editing}
                          className="rounded border-border bg-bg-tertiary"
                        />
                        <span className="text-sm text-text-primary">{perm}</span>
                      </label>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Security */}
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-4">Security</h3>
              <div className="grid grid-cols-2 gap-4">
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
              </div>
            </div>

            {/* Activity */}
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-4">Activity</h3>
              <div className="grid grid-cols-2 gap-4">
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
                    {new Date(selectedUser.created_at).toLocaleDateString()}
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
          </div>
        )}
      </ExplorerPanel>

      <DetailsPanel
        breadcrumb={[
          { label: 'Users' },
          { label: `${users.length} users` }
        ]}
        title="Users"
      >
        <div className="p-4 space-y-3">
          <Select
            label="Filter by Role"
            options={[
              { value: 'all', label: 'All Roles' },
              { value: 'admin', label: 'Administrators' },
              { value: 'operator', label: 'Operators' },
              { value: 'viewer', label: 'Viewers' },
            ]}
            value={roleFilter}
            onChange={setRoleFilter}
          />

          <Button onClick={() => setShowCreateModal(true)} className="w-full">
            <Plus size={18} />
            Create User
          </Button>
        </div>

        <div className="flex-1 overflow-auto">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <LoadingSpinner />
            </div>
          ) : users.length === 0 ? (
            <EmptyState
              icon={User}
              title="No users"
              description="Create your first user account"
            />
          ) : (
            <Table
              columns={userColumns}
              data={users}
              onRowClick={selectUser}
              selectedId={selectedUser?.id}
            />
          )}
        </div>
      </DetailsPanel>

      {/* Create User Modal */}
      <Modal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="Create New User"
      >
        <CreateUserForm
          onSubmit={handleCreate}
          onCancel={() => setShowCreateModal(false)}
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
