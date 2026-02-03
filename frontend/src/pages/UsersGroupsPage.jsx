/**
 * UsersGroupsPage - User and Group management
 * Pattern: ResponsiveLayout + ResponsiveDataTable + Modal actions
 * 
 * DESKTOP: Dense table with hover rows, inline slide-over details
 * MOBILE: Card-style list with full-screen details
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { 
  User, Users, Plus, Trash, PencilSimple, Key, 
  CheckCircle, XCircle, Crown, Clock, ShieldCheck, UserCircle
} from '@phosphor-icons/react'
import {
  ResponsiveLayout, ResponsiveDataTable, Badge, Button, Modal, Input, Select,
  HelpCard, LoadingSpinner, MemberTransferModal,
  CompactSection, CompactGrid, CompactField, CompactHeader
} from '../components'
import { usersService, groupsService, rolesService } from '../services'
import { useNotification, useMobile } from '../contexts'
import { usePermission } from '../hooks'
import { formatDate, cn } from '../lib/utils'
import { ERRORS, SUCCESS, LABELS, CONFIRM } from '../lib/messages'

export default function UsersGroupsPage() {
  const { isMobile } = useMobile()
  const [searchParams, setSearchParams] = useSearchParams()
  const { showSuccess, showError, showConfirm } = useNotification()
  const { canWrite, canDelete } = usePermission()
  
  // Tab state
  const [activeTab, setActiveTab] = useState(searchParams.get('tab') || 'users')
  
  // Data
  const [users, setUsers] = useState([])
  const [groups, setGroups] = useState([])
  const [roles, setRoles] = useState([])
  const [loading, setLoading] = useState(true)
  
  // Selection
  const [selectedUser, setSelectedUser] = useState(null)
  const [selectedGroup, setSelectedGroup] = useState(null)
  
  // Modals
  const [showUserModal, setShowUserModal] = useState(false)
  const [showGroupModal, setShowGroupModal] = useState(false)
  const [showMemberModal, setShowMemberModal] = useState(false)
  const [editingUser, setEditingUser] = useState(null)
  const [editingGroup, setEditingGroup] = useState(null)
  const [savingMembers, setSavingMembers] = useState(false)
  
  // Pagination
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)
  
  // Filters
  const [filterRole, setFilterRole] = useState('')
  const [filterStatus, setFilterStatus] = useState('')

  // Tab change
  const handleTabChange = (tab) => {
    setActiveTab(tab)
    setSearchParams({ tab })
    setSelectedUser(null)
    setSelectedGroup(null)
    setPage(1)
  }

  // Load data
  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      setLoading(true)
      const [usersRes, groupsRes, rolesRes] = await Promise.all([
        usersService.getAll(),
        groupsService.getAll(),
        rolesService.getAll().catch(() => ({ data: [] }))
      ])
      setUsers(usersRes.data || [])
      setGroups(groupsRes.data || [])
      setRoles(rolesRes.data || [])
    } catch (error) {
      showError(ERRORS.LOAD_FAILED.GENERIC)
    } finally {
      setLoading(false)
    }
  }

  // ============= USER ACTIONS =============
  
  const handleCreateUser = async (data) => {
    try {
      await usersService.create(data)
      showSuccess(SUCCESS.CREATE.USER)
      setShowUserModal(false)
      setEditingUser(null)
      loadData()
    } catch (error) {
      showError(error.message || ERRORS.CREATE_FAILED.USER)
    }
  }

  const handleUpdateUser = async (data) => {
    try {
      await usersService.update(editingUser.id, data)
      showSuccess(SUCCESS.UPDATE.USER)
      setShowUserModal(false)
      setEditingUser(null)
      loadData()
      if (selectedUser?.id === editingUser.id) {
        setSelectedUser({ ...selectedUser, ...data })
      }
    } catch (error) {
      showError(error.message || ERRORS.UPDATE_FAILED.USER)
    }
  }

  const handleDeleteUser = async (user) => {
    const confirmed = await showConfirm(`Delete user "${user.username}"?`, {
      title: CONFIRM.DELETE.TITLE,
      confirmText: 'Delete',
      variant: 'danger'
    })
    if (!confirmed) return
    try {
      await usersService.delete(user.id)
      showSuccess(SUCCESS.DELETE.USER)
      if (selectedUser?.id === user.id) setSelectedUser(null)
      loadData()
    } catch (error) {
      showError(error.message || ERRORS.DELETE_FAILED.USER)
    }
  }

  const handleToggleUser = async (user) => {
    try {
      await usersService.update(user.id, { active: !user.active })
      showSuccess(`User ${user.active ? 'disabled' : 'enabled'}`)
      loadData()
      if (selectedUser?.id === user.id) {
        setSelectedUser({ ...selectedUser, active: !user.active })
      }
    } catch (error) {
      showError(error.message || ERRORS.UPDATE_FAILED.USER)
    }
  }

  const handleResetPassword = async (user) => {
    const confirmed = await showConfirm(`Reset password for "${user.username}"?`, {
      title: CONFIRM.RESET_PASSWORD.TITLE,
      confirmText: 'Reset'
    })
    if (!confirmed) return
    try {
      const res = await usersService.resetPassword(user.id)
      showSuccess(`New password: ${res.password || 'Check email'}`)
    } catch (error) {
      showError(error.message || 'Failed to reset password')
    }
  }

  // ============= GROUP ACTIONS =============
  
  const handleCreateGroup = async (data) => {
    try {
      await groupsService.create(data)
      showSuccess(SUCCESS.CREATE.GROUP)
      setShowGroupModal(false)
      setEditingGroup(null)
      loadData()
    } catch (error) {
      showError(error.message || ERRORS.CREATE_FAILED.GROUP)
    }
  }

  const handleUpdateGroup = async (data) => {
    try {
      await groupsService.update(editingGroup.id, data)
      showSuccess(SUCCESS.UPDATE.GROUP)
      setShowGroupModal(false)
      setEditingGroup(null)
      loadData()
    } catch (error) {
      showError(error.message || ERRORS.UPDATE_FAILED.GROUP)
    }
  }

  const handleDeleteGroup = async (group) => {
    const confirmed = await showConfirm(`Delete group "${group.name}"?`, {
      title: CONFIRM.DELETE.TITLE,
      confirmText: 'Delete',
      variant: 'danger'
    })
    if (!confirmed) return
    try {
      await groupsService.delete(group.id)
      showSuccess(SUCCESS.DELETE.GROUP)
      if (selectedGroup?.id === group.id) setSelectedGroup(null)
      loadData()
    } catch (error) {
      showError(error.message || ERRORS.DELETE_FAILED.GROUP)
    }
  }

  // Save members from the transfer modal
  const handleSaveMembers = async (newMemberIds) => {
    if (!selectedGroup) return
    
    setSavingMembers(true)
    try {
      const currentIds = new Set((selectedGroup.members || []).map(m => m.id || m.user_id))
      const newIds = new Set(newMemberIds)
      
      // Find members to add
      const toAdd = newMemberIds.filter(id => !currentIds.has(id))
      // Find members to remove
      const toRemove = [...currentIds].filter(id => !newIds.has(id))
      
      // Execute all changes
      await Promise.all([
        ...toAdd.map(userId => groupsService.addMember(selectedGroup.id, userId)),
        ...toRemove.map(userId => groupsService.removeMember(selectedGroup.id, userId))
      ])
      
      showSuccess(`Members updated: ${toAdd.length} added, ${toRemove.length} removed`)
      setShowMemberModal(false)
      loadData()
      
      // Refresh selected group
      const updated = await groupsService.getById(selectedGroup.id)
      setSelectedGroup(updated.data)
    } catch (error) {
      showError(error.message || ERRORS.UPDATE_FAILED.GROUP)
    } finally {
      setSavingMembers(false)
    }
  }

  // ============= FILTERED DATA =============
  
  const filteredUsers = useMemo(() => {
    let result = [...users]
    if (filterRole) result = result.filter(u => u.role === filterRole)
    if (filterStatus === 'active') result = result.filter(u => u.active)
    if (filterStatus === 'disabled') result = result.filter(u => !u.active)
    return result
  }, [users, filterRole, filterStatus])

  const filteredGroups = useMemo(() => groups, [groups])

  // ============= STATS =============
  
  const stats = useMemo(() => {
    if (activeTab === 'users') {
      const active = users.filter(u => u.active).length
      const disabled = users.filter(u => !u.active).length
      const admins = users.filter(u => u.role === 'admin').length
      return [
        { icon: CheckCircle, label: 'Active', value: active, variant: 'success' },
        { icon: XCircle, label: 'Disabled', value: disabled, variant: 'secondary' },
        { icon: Crown, label: 'Admins', value: admins, variant: 'primary' },
        { icon: User, label: 'Total', value: users.length, variant: 'default' }
      ]
    } else {
      return [
        { icon: Users, label: 'Groups', value: groups.length, variant: 'primary' },
        { icon: User, label: 'Users', value: users.length, variant: 'secondary' }
      ]
    }
  }, [activeTab, users, groups])

  // ============= COLUMNS =============
  
  const userColumns = useMemo(() => [
    {
      key: 'username',
      header: 'User',
      priority: 1,
      sortable: true,
      render: (val, row) => {
        // Color avatar based on role AND status - theme-aware
        const avatarColors = {
          admin: 'icon-bg-violet ring-1 ring-violet-500/30',
          operator: 'icon-bg-blue ring-1 ring-blue-500/30',
          viewer: 'icon-bg-teal ring-1 ring-teal-500/30'
        }
        // Override with orange for disabled users
        const colorClass = row.active 
          ? (avatarColors[row.role] || avatarColors.viewer)
          : 'icon-bg-orange ring-1 ring-orange-500/30'
        return (
          <div className="flex items-center gap-3">
            <div className={cn(
              "w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold shadow-sm",
              colorClass
            )}>
              {val?.charAt(0)?.toUpperCase() || '?'}
            </div>
            <div className="min-w-0">
              <div className="font-medium text-text-primary truncate">{val || '—'}</div>
              <div className="text-xs text-text-secondary truncate">{row.email || '—'}</div>
            </div>
          </div>
        )
      }
    },
    {
      key: 'role',
      header: 'Role',
      priority: 2,
      sortable: true,
      render: (val, row) => {
        // Colorful role badges for ALL roles
        const roleConfig = {
          admin: { variant: 'violet', dot: true },
          operator: { variant: 'primary', dot: false },
          viewer: { variant: 'teal', dot: false }
        }
        const config = roleConfig[val] || roleConfig.viewer
        return (
          <Badge variant={config.variant} size="sm" dot={config.dot}>
            {val === 'admin' && <Crown weight="fill" className="h-3 w-3 mr-1" />}
            {val || 'viewer'}
          </Badge>
        )
      }
    },
    {
      key: 'active',
      header: 'Status',
      priority: 3,
      sortable: true,
      render: (val) => (
        <Badge 
          variant={val ? 'success' : 'orange'} 
          size="sm" 
          icon={val ? CheckCircle : XCircle} 
          dot 
          pulse={val}
        >
          {val ? 'Active' : 'Disabled'}
        </Badge>
      )
    },
    {
      key: 'last_login',
      header: 'Last Login',
      hideOnMobile: true,
      sortable: true,
      render: (val) => (
        <span className="text-xs text-text-secondary whitespace-nowrap">
          {val ? formatDate(val) : 'Never'}
        </span>
      )
    }
  ], [])

  const groupColumns = useMemo(() => [
    {
      key: 'name',
      header: 'Group',
      priority: 1,
      sortable: true,
      render: (val) => (
        <div className="flex items-center gap-2">
          <Users size={16} className="text-accent-primary shrink-0" />
          <span className="font-medium">{val}</span>
        </div>
      )
    },
    {
      key: 'description',
      header: 'Description',
      priority: 2,
      hideOnMobile: true,
      render: (val) => (
        <span className="text-text-secondary truncate">{val || '—'}</span>
      )
    },
    {
      key: 'member_count',
      header: 'Members',
      priority: 3,
      sortable: true,
      render: (val, row) => {
        const count = row.members?.length || val || 0
        return (
          <Badge variant="outline" size="sm">
            {count} {count === 1 ? 'member' : 'members'}
          </Badge>
        )
      }
    }
  ], [])

  // ============= ROW ACTIONS =============
  
  const userRowActions = useCallback((row) => [
    { label: 'Edit', icon: PencilSimple, onClick: () => { setEditingUser(row); setShowUserModal(true) } },
    { label: row.active ? 'Disable' : 'Enable', icon: row.active ? XCircle : CheckCircle, onClick: () => handleToggleUser(row) },
    { label: 'Reset Password', icon: Key, onClick: () => handleResetPassword(row) },
    ...(canDelete('users') ? [
      { label: 'Delete', icon: Trash, variant: 'danger', onClick: () => handleDeleteUser(row) }
    ] : [])
  ], [canDelete])

  const groupRowActions = useCallback((row) => [
    { label: 'Edit', icon: PencilSimple, onClick: () => { setEditingGroup(row); setShowGroupModal(true) } },
    ...(canDelete('users') ? [
      { label: 'Delete', icon: Trash, variant: 'danger', onClick: () => handleDeleteGroup(row) }
    ] : [])
  ], [canDelete])

  // ============= HELP CONTENT =============
  
  const helpContent = (
    <div className="space-y-4">
      {/* Quick Stats */}
      <div className="visual-section">
        <div className="visual-section-header">
          <Users size={16} className="status-primary-text" />
          {activeTab === 'users' ? 'User Statistics' : 'Group Statistics'}
        </div>
        <div className="visual-section-body">
          {activeTab === 'users' ? (
            <div className="grid grid-cols-2 gap-3">
              <div className="help-stat-card">
                <div className="help-stat-value help-stat-value-success">{users.filter(u => u.active).length}</div>
                <div className="help-stat-label">Active</div>
              </div>
              <div className="help-stat-card">
                <div className="help-stat-value">{users.filter(u => !u.active).length}</div>
                <div className="help-stat-label">Disabled</div>
              </div>
              <div className="help-stat-card">
                <div className="help-stat-value help-stat-value-primary">{users.filter(u => u.role === 'admin').length}</div>
                <div className="help-stat-label">Admins</div>
              </div>
              <div className="help-stat-card">
                <div className="help-stat-value">{users.length}</div>
                <div className="help-stat-label">Total</div>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              <div className="help-stat-card">
                <div className="help-stat-value help-stat-value-primary">{groups.length}</div>
                <div className="help-stat-label">Groups</div>
              </div>
              <div className="help-stat-card">
                <div className="help-stat-value">{users.length}</div>
                <div className="help-stat-label">Users</div>
              </div>
            </div>
          )}
        </div>
      </div>

      <HelpCard title="User Management" variant="info">
        Create and manage user accounts. Assign roles to control access levels.
      </HelpCard>
      <HelpCard title="Roles" variant="tip">
        <div className="space-y-1.5 mt-2">
          <div className="flex items-center gap-2">
            <Badge variant="primary" size="sm" dot>{LABELS.ROLES.ADMIN}</Badge>
            <span className="text-xs">Full access</span>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="warning" size="sm" dot>{LABELS.ROLES.OPERATOR}</Badge>
            <span className="text-xs">Manage certificates</span>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="secondary" size="sm" dot>{LABELS.ROLES.VIEWER}</Badge>
            <span className="text-xs">Read-only access</span>
          </div>
        </div>
      </HelpCard>
    </div>
  )

  // ============= DETAIL PANEL =============
  
  const userDetailContent = selectedUser && (
    <div className="p-3 space-y-4">
      <CompactHeader
        icon={UserCircle}
        iconClass={selectedUser.active ? "bg-accent-primary/20" : "bg-text-muted/20"}
        title={selectedUser.username}
        subtitle={selectedUser.email}
        badge={
          <Badge variant={selectedUser.active ? 'success' : 'secondary'} size="sm" icon={selectedUser.active ? CheckCircle : XCircle}>
            {selectedUser.active ? 'Active' : 'Disabled'}
          </Badge>
        }
      />

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        {canWrite('users') && (
          <>
            <Button size="sm" variant="secondary" onClick={() => { setEditingUser(selectedUser); setShowUserModal(true) }}>
              <PencilSimple size={14} /> Edit
            </Button>
            <Button size="sm" variant="secondary" onClick={() => handleToggleUser(selectedUser)}>
              {selectedUser.active ? <XCircle size={14} /> : <CheckCircle size={14} />}
              {selectedUser.active ? 'Disable' : 'Enable'}
            </Button>
            <Button size="sm" variant="secondary" onClick={() => handleResetPassword(selectedUser)}>
              <Key size={14} /> Reset Password
            </Button>
          </>
        )}
        {canDelete('users') && (
          <Button size="sm" variant="danger" onClick={() => handleDeleteUser(selectedUser)}>
            <Trash size={14} /> Delete
          </Button>
        )}
      </div>

      <CompactSection title="User Information" icon={UserCircle}>
        <CompactGrid columns={1}>
          <CompactField label="Full Name" value={selectedUser.full_name || '—'} />
          <CompactField label="Email" value={selectedUser.email} />
          <CompactField label="Role" value={selectedUser.role} />
        </CompactGrid>
      </CompactSection>

      <CompactSection title="Activity" icon={Clock}>
        <CompactGrid columns={1}>
          <CompactField label="Created" value={formatDate(selectedUser.created_at)} />
          <CompactField label="Last Login" value={selectedUser.last_login ? formatDate(selectedUser.last_login) : 'Never'} />
          <CompactField label="Login Count" value={selectedUser.login_count || 0} />
        </CompactGrid>
      </CompactSection>

      <CompactSection title="Security" icon={ShieldCheck}>
        <CompactGrid columns={1}>
          <CompactField label="MFA Enabled" value={selectedUser.mfa_enabled ? 'Yes' : 'No'} />
          <CompactField label="TOTP Configured" value={selectedUser.totp_confirmed ? 'Yes' : 'No'} />
        </CompactGrid>
      </CompactSection>
    </div>
  )

  const groupDetailContent = selectedGroup && (
    <div className="p-3 space-y-4">
      <CompactHeader
        icon={Users}
        iconClass="bg-accent-primary/20"
        title={selectedGroup.name}
        subtitle={`${selectedGroup.members?.length || 0} ${(selectedGroup.members?.length || 0) === 1 ? 'member' : 'members'}`}
      />

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        {canWrite('users') && (
          <Button size="sm" variant="secondary" onClick={() => { setEditingGroup(selectedGroup); setShowGroupModal(true) }}>
            <PencilSimple size={14} /> Edit
          </Button>
        )}
        {canDelete('users') && (
          <Button size="sm" variant="danger" onClick={() => handleDeleteGroup(selectedGroup)}>
            <Trash size={14} /> Delete
          </Button>
        )}
      </div>

      <CompactSection title="Group Information">
        <CompactGrid columns={1}>
          <CompactField label="Name" value={selectedGroup.name} />
          <CompactField label="Description" value={selectedGroup.description || '—'} />
          <CompactField label="Created" value={formatDate(selectedGroup.created_at)} />
        </CompactGrid>
      </CompactSection>

      <CompactSection title="Members">
        <div className="space-y-3">
          {/* Manage Members Button */}
          {canWrite('users') && (
            <div className="flex justify-end">
              <Button size="sm" onClick={() => setShowMemberModal(true)}>
                <Users size={14} /> Manage Members
              </Button>
            </div>
          )}

          {/* Members Preview */}
          {(selectedGroup.members?.length || 0) === 0 ? (
            <p className="text-sm text-text-tertiary text-center py-4">
              No members in this group
            </p>
          ) : (
            <div className="space-y-2">
              {selectedGroup.members.slice(0, 5).map(member => (
                <div
                  key={member.id || member.user_id || member.username}
                  className="flex items-center gap-3 px-3 py-2 bg-bg-tertiary/50 border border-border rounded-lg"
                >
                  <div className="w-7 h-7 rounded-full bg-accent-primary/20 flex items-center justify-center">
                    <User size={14} className="text-accent-primary" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-text-primary truncate">
                      {member.username}
                    </p>
                    {member.email && (
                      <p className="text-xs text-text-tertiary truncate">
                        {member.email}
                      </p>
                    )}
                  </div>
                </div>
              ))}
              {selectedGroup.members.length > 5 && (
                <button
                  onClick={() => setShowMemberModal(true)}
                  className="w-full text-sm text-accent-primary hover:text-accent-primary/80 py-2"
                >
                  + {selectedGroup.members.length - 5} more members
                </button>
              )}
            </div>
          )}
        </div>
      </CompactSection>
    </div>
  )

  // ============= RENDER =============
  
  const currentData = activeTab === 'users' ? filteredUsers : filteredGroups
  const currentColumns = activeTab === 'users' ? userColumns : groupColumns
  const currentRowActions = activeTab === 'users' ? userRowActions : groupRowActions
  const currentSelected = activeTab === 'users' ? selectedUser : selectedGroup
  const currentDetailContent = activeTab === 'users' ? userDetailContent : groupDetailContent
  
  const handleSelect = async (item) => {
    if (activeTab === 'users') {
      setSelectedUser(item)
      setSelectedGroup(null)
    } else {
      // Load full group details with members
      setSelectedGroup(item) // Show immediately
      setSelectedUser(null)
      try {
        const res = await groupsService.getById(item.id)
        setSelectedGroup(res.data) // Update with members
      } catch (error) {
        console.error('Failed to load group details:', error)
      }
    }
  }

  const handleOpenCreateModal = () => {
    if (activeTab === 'users') {
      setEditingUser(null)
      setShowUserModal(true)
    } else {
      setEditingGroup(null)
      setShowGroupModal(true)
    }
  }

  // Tabs
  const tabs = [
    { id: 'users', label: 'Users', icon: User, count: users.length },
    { id: 'groups', label: 'Groups', icon: Users, count: groups.length }
  ]

  return (
    <>
      <ResponsiveLayout
        title={activeTab === 'users' ? 'Users' : 'Groups'}
        subtitle={`${currentData.length} ${activeTab}`}
        icon={activeTab === 'users' ? User : Users}
        stats={stats}
        tabs={tabs}
        activeTab={activeTab}
        onTabChange={handleTabChange}
        helpContent={helpContent}
        helpTitle="User Management"
        splitView={true}
        splitEmptyContent={
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="w-14 h-14 rounded-xl bg-bg-tertiary flex items-center justify-center mb-3">
              {activeTab === 'users' ? <User size={24} className="text-text-tertiary" /> : <Users size={24} className="text-text-tertiary" />}
            </div>
            <p className="text-sm text-text-secondary">
              Select {activeTab === 'users' ? 'a user' : 'a group'} to view details
            </p>
          </div>
        }
        slideOverOpen={!!currentSelected}
        slideOverTitle={currentSelected?.username || currentSelected?.name || 'Details'}
        slideOverContent={currentDetailContent}
        slideOverWidth="lg"
        onSlideOverClose={() => { setSelectedUser(null); setSelectedGroup(null) }}
      >
        <div className="flex flex-col h-full min-h-0">
          <ResponsiveDataTable
          data={currentData}
          columns={currentColumns}
          loading={loading}
          onRowClick={handleSelect}
          selectedId={currentSelected?.id}
          rowActions={currentRowActions}
          searchable
          searchPlaceholder={`Search ${activeTab}...`}
          searchKeys={activeTab === 'users' ? ['username', 'email', 'full_name', 'role'] : ['name', 'description']}
          toolbarFilters={activeTab === 'users' ? [
            {
              key: 'role',
              value: filterRole,
              onChange: setFilterRole,
              placeholder: LABELS.FILTERS.ALL_ROLES,
              options: [
                { value: 'admin', label: LABELS.ROLES.ADMIN },
                { value: 'operator', label: LABELS.ROLES.OPERATOR },
                { value: 'viewer', label: LABELS.ROLES.VIEWER }
              ]
            },
            {
              key: 'status',
              value: filterStatus,
              onChange: setFilterStatus,
              placeholder: LABELS.FILTERS.ALL_STATUS,
              options: [
                { value: 'active', label: LABELS.STATUS.ACTIVE },
                { value: 'disabled', label: 'Disabled' }
              ]
            }
          ] : []}
          toolbarActions={canWrite('users') && (
            isMobile ? (
              <Button size="lg" onClick={handleOpenCreateModal} className="w-11 h-11 p-0">
                <Plus size={22} weight="bold" />
              </Button>
            ) : (
              <Button size="sm" onClick={handleOpenCreateModal}>
                <Plus size={14} weight="bold" />
                New {activeTab === 'users' ? 'User' : 'Group'}
              </Button>
            )
          )}
          sortable
          defaultSort={{ key: activeTab === 'users' ? 'username' : 'name', direction: 'asc' }}
          pagination={{
            page,
            total: currentData.length,
            perPage,
            onChange: setPage,
            onPerPageChange: (v) => { setPerPage(v); setPage(1) }
          }}
          emptyIcon={activeTab === 'users' ? User : Users}
          emptyTitle={`No ${activeTab}`}
          emptyDescription={`Create your first ${activeTab === 'users' ? 'user' : 'group'} to get started`}
          emptyAction={canWrite('users') && (
            <Button onClick={handleOpenCreateModal}>
              <Plus size={16} /> New {activeTab === 'users' ? 'User' : 'Group'}
            </Button>
          )}
        />
        </div>
      </ResponsiveLayout>

      {/* User Modal */}
      <Modal
        open={showUserModal}
        onOpenChange={(open) => { setShowUserModal(open); if (!open) setEditingUser(null) }}
        title={editingUser ? 'Edit User' : 'Create User'}
        size="md"
      >
        <UserForm
          user={editingUser}
          onSubmit={editingUser ? handleUpdateUser : handleCreateUser}
          onCancel={() => { setShowUserModal(false); setEditingUser(null) }}
        />
      </Modal>

      {/* Group Modal */}
      <Modal
        open={showGroupModal}
        onOpenChange={(open) => { setShowGroupModal(open); if (!open) setEditingGroup(null) }}
        title={editingGroup ? 'Edit Group' : 'Create Group'}
        size="md"
      >
        <GroupForm
          group={editingGroup}
          onSubmit={editingGroup ? handleUpdateGroup : handleCreateGroup}
          onCancel={() => { setShowGroupModal(false); setEditingGroup(null) }}
        />
      </Modal>

      {/* Member Transfer Modal */}
      {selectedGroup && (
        <MemberTransferModal
          open={showMemberModal}
          onClose={() => setShowMemberModal(false)}
          title={`Manage Members - ${selectedGroup.name}`}
          allUsers={users}
          currentMembers={selectedGroup.members || []}
          onSave={handleSaveMembers}
          loading={savingMembers}
        />
      )}
    </>
  )
}

// ============= USER FORM =============

function UserForm({ user, onSubmit, onCancel }) {
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    full_name: '',
    role: 'viewer'
  })
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (user) {
      setFormData({
        username: user.username || '',
        email: user.email || '',
        password: '',
        full_name: user.full_name || '',
        role: user.role || 'viewer'
      })
    } else {
      setFormData({
        username: '',
        email: '',
        password: '',
        full_name: '',
        role: 'viewer'
      })
    }
  }, [user])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      const data = { ...formData }
      if (user && !data.password) delete data.password
      await onSubmit(data)
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4">
      <Input
        label="Username"
        value={formData.username}
        onChange={(e) => setFormData(p => ({ ...p, username: e.target.value }))}
        required
        disabled={!!user}
        placeholder="johndoe"
      />
      <Input
        label="Email"
        type="email"
        value={formData.email}
        onChange={(e) => setFormData(p => ({ ...p, email: e.target.value }))}
        required
        placeholder="john@example.com"
      />
      <Input
        label="Full Name"
        value={formData.full_name}
        onChange={(e) => setFormData(p => ({ ...p, full_name: e.target.value }))}
        placeholder="John Doe"
      />
      <Input
        label={user ? 'New Password (leave blank to keep)' : 'Password'}
        type="password"
        value={formData.password}
        onChange={(e) => setFormData(p => ({ ...p, password: e.target.value }))}
        required={!user}
        placeholder="••••••••"
      />
      <Select
        label="Role"
        value={formData.role}
        onChange={(val) => setFormData(p => ({ ...p, role: val }))}
        options={[
          { value: 'admin', label: LABELS.ROLES.ADMIN },
          { value: 'operator', label: LABELS.ROLES.OPERATOR },
          { value: 'viewer', label: LABELS.ROLES.VIEWER }
        ]}
      />
      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={loading}>
          {loading ? <LoadingSpinner size="sm" /> : (user ? 'Update' : 'Create')}
        </Button>
      </div>
    </form>
  )
}

// ============= GROUP FORM =============

function GroupForm({ group, onSubmit, onCancel }) {
  const [formData, setFormData] = useState({
    name: '',
    description: ''
  })
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (group) {
      setFormData({
        name: group.name || '',
        description: group.description || ''
      })
    } else {
      setFormData({
        name: '',
        description: ''
      })
    }
  }, [group])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      await onSubmit(formData)
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4">
      <Input
        label="Group Name"
        value={formData.name}
        onChange={(e) => setFormData(p => ({ ...p, name: e.target.value }))}
        required
        placeholder="developers"
      />
      <Input
        label="Description"
        value={formData.description}
        onChange={(e) => setFormData(p => ({ ...p, description: e.target.value }))}
        placeholder="Development team"
      />
      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={loading}>
          {loading ? <LoadingSpinner size="sm" /> : (group ? 'Update' : 'Create')}
        </Button>
      </div>
    </form>
  )
}
