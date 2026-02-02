/**
 * Groups Management Page (Pro Feature)
 * Manage user groups with role inheritance
 * Uses ManagementLayout for consistent desktop/mobile experience
 */
import { useState, useEffect } from 'react'
import { 
  UsersThree, Plus, Trash, PencilSimple, User, Shield, 
  Crown, Calendar
} from '@phosphor-icons/react'
import {
  ManagementLayout, Button, Input, Card,
  Badge, Modal, FormModal, HelpCard,
  CompactHeader, CompactSection, CompactGrid, CompactField, CompactStats
} from '../../components'
import { pluralize } from '../../lib/ui'
import { useNotification } from '../../contexts'
import { useModals } from '../../hooks'
import { apiClient } from '../../services/apiClient'

export default function GroupsPage() {
  const { showSuccess, showError } = useNotification()
  const { modals, open: openModal, close: closeModal } = useModals()
  
  const [loading, setLoading] = useState(true)
  const [groups, setGroups] = useState([])
  const [selectedGroup, setSelectedGroup] = useState(null)
  const [users, setUsers] = useState([])
  
  // Form state
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    role: 'viewer',
    permissions: []
  })

  useEffect(() => {
    loadGroups()
  }, [])

  const loadGroups = async () => {
    setLoading(true)
    try {
      const [groupsRes, usersRes] = await Promise.all([
        apiClient.get('/groups'),
        apiClient.get('/users')
      ])
      setGroups(groupsRes.data || [])
      setUsers(usersRes.data || [])
    } catch (error) {
      showError('Failed to load groups')
    } finally {
      setLoading(false)
    }
  }

  const selectGroup = async (group) => {
    try {
      const res = await apiClient.get(`/groups/${group.id}`)
      setSelectedGroup(res.data || group)
    } catch (error) {
      setSelectedGroup(group)
    }
  }

  const handleCreate = async () => {
    try {
      await apiClient.post('/groups', formData)
      showSuccess('Group created')
      closeModal('create')
      loadGroups()
      setFormData({ name: '', description: '', role: 'viewer', permissions: [] })
    } catch (error) {
      showError(error.message || 'Failed to create group')
    }
  }

  const handleDelete = async (group) => {
    if (!confirm(`Delete group "${group.name}"?`)) return
    try {
      await apiClient.delete(`/groups/${group.id}`)
      showSuccess('Group deleted')
      setSelectedGroup(null)
      loadGroups()
    } catch (error) {
      showError(error.message || 'Failed to delete group')
    }
  }

  const handleAddMember = async (userId) => {
    if (!selectedGroup) return
    try {
      await apiClient.post(`/groups/${selectedGroup.id}/members`, { user_id: userId })
      showSuccess('Member added')
      loadGroups()
      selectGroup(selectedGroup)
    } catch (error) {
      showError(error.message || 'Failed to add member')
    }
  }

  const handleRemoveMember = async (userId) => {
    if (!selectedGroup) return
    try {
      await apiClient.delete(`/groups/${selectedGroup.id}/members/${userId}`)
      showSuccess('Member removed')
      loadGroups()
      selectGroup(selectedGroup)
    } catch (error) {
      showError(error.message || 'Failed to remove member')
    }
  }

  const groupMembers = selectedGroup?.members || []
  const availableUsers = users.filter(u => 
    !groupMembers.some(m => m.user_id === u.id)
  )

  // Help content
  const helpContent = (
    <div className="space-y-4">
      <Card className="p-4 space-y-3 bg-gradient-to-br from-accent-primary/5 to-transparent">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <UsersThree size={16} className="text-accent-primary" />
          Group Statistics
        </h3>
        <div className="grid grid-cols-2 gap-3">
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-text-primary">{groups.length}</p>
            <p className="text-xs text-text-secondary">Total Groups</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-accent-primary">
              {groups.reduce((sum, g) => sum + (g.member_count || 0), 0)}
            </p>
            <p className="text-xs text-text-secondary">Total Members</p>
          </div>
        </div>
      </Card>

      <HelpCard variant="info" title="User Groups">
        Groups allow bulk permission assignment. Members inherit the group's role and permissions.
      </HelpCard>

      <HelpCard variant="tip" title="Best Practice">
        Create groups by function (e.g., "PKI Operators", "Auditors") rather than by department.
      </HelpCard>
    </div>
  )

  // Render group details
  const renderGroupDetails = (group) => (
    <div className="p-3 space-y-3">
      <CompactHeader
        icon={UsersThree}
        iconClass="bg-accent-primary/20"
        title={group.name}
        subtitle={group.description || 'No description'}
        badge={
          <Badge variant="primary" size="sm">
            {pluralize(group.member_count || 0, 'member')}
          </Badge>
        }
      />

      <CompactStats stats={[
        { icon: Shield, value: `${group.permissions?.length || 0} perms` },
        { icon: Calendar, value: group.created_at ? new Date(group.created_at).toLocaleDateString() : 'N/A' }
      ]} />

      <div className="flex gap-2">
        <Button size="sm" variant="secondary" onClick={() => openModal('edit')}>
          <PencilSimple size={14} /> Edit
        </Button>
        <Button size="sm" variant="danger" onClick={() => handleDelete(group)}>
          <Trash size={14} />
        </Button>
      </div>

      <CompactSection title="Group Information">
        <CompactGrid>
          <CompactField label="Group Name" value={group.name} />
          <CompactField label="Description" value={group.description || 'No description'} />
          <CompactField label="Member Count" value={group.member_count || 0} />
          <CompactField label="Permissions" value={group.permissions?.length || 0} />
          <CompactField 
            label="Created" 
            value={group.created_at 
              ? new Date(group.created_at).toLocaleDateString()
              : 'N/A'
            }
          />
          <CompactField 
            label="Updated" 
            value={group.updated_at 
              ? new Date(group.updated_at).toLocaleDateString()
              : 'N/A'
            }
          />
        </CompactGrid>
      </CompactSection>

      <CompactSection title="Members">
        <div className="space-y-3">
          {availableUsers.length > 0 && (
            <div className="flex justify-end">
              <Button size="sm" onClick={() => openModal('addMember')}>
                <Plus size={14} />
                Add Member
              </Button>
            </div>
          )}

          {groupMembers.length === 0 ? (
            <p className="text-sm text-text-tertiary text-center py-4">
              No members in this group
            </p>
          ) : (
            <div className="space-y-2">
              {groupMembers.map(member => (
                <div
                  key={member.user_id}
                  className="flex items-center justify-between px-3 py-2.5 bg-bg-tertiary/50 border border-border rounded-lg"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-accent-primary/20 flex items-center justify-center">
                      <User size={16} className="text-accent-primary" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-text-primary">
                        {member.username}
                      </p>
                      <p className="text-xs text-text-tertiary">
                        {member.email}
                      </p>
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => handleRemoveMember(member.user_id)}
                  >
                    <Trash size={14} className="status-danger-text" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </CompactSection>
    </div>
  )

  return (
    <>
      <ManagementLayout
        title="Groups"
        items={groups}
        loading={loading}
        selectedItem={selectedGroup}
        onSelectItem={selectGroup}
        
        // Item display
        itemIcon={UsersThree}
        itemTitle={(g) => g.name}
        itemSubtitle={(g) => pluralize(g.member_count || 0, 'member')}
        itemBadge={(g) => (
          <Badge variant="secondary" size="sm">
            {g.permissions?.length || 0} perms
          </Badge>
        )}
        
        // Details
        renderDetails={renderGroupDetails}
        detailsTitle="Group Details"
        
        // Actions
        onCreate={() => openModal('create')}
        createLabel="Create Group"
        
        // Search
        searchable
        searchKeys={['name', 'description']}
        searchPlaceholder="Search groups..."
        
        // Help
        helpContent={helpContent}
        
        // Empty state
        emptyIcon={UsersThree}
        emptyTitle="No groups"
        emptyDescription="Create your first group to organize users"
        itemName="group"
      />

      {/* Create Group Modal */}
      <FormModal
        open={modals.create}
        onClose={() => closeModal('create')}
        title="Create Group"
        onSubmit={handleCreate}
        submitLabel="Create"
        disabled={!formData.name}
      >
        <Input
          label="Group Name"
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          placeholder="e.g., PKI Operators"
        />
        <Input
          label="Description"
          value={formData.description}
          onChange={(e) => setFormData({ ...formData, description: e.target.value })}
          placeholder="Optional description"
        />
        <div>
          <label className="text-xs font-medium text-text-secondary mb-1.5 block">
            Default Role
          </label>
          <select
            value={formData.role}
            onChange={(e) => setFormData({ ...formData, role: e.target.value })}
            className="w-full px-3 py-2 bg-bg-tertiary border border-border rounded-lg text-sm text-text-primary"
          >
            <option value="viewer">Viewer</option>
            <option value="operator">Operator</option>
            <option value="admin">Admin</option>
          </select>
        </div>
      </FormModal>

      {/* Add Member Modal */}
      <Modal
        open={modals.addMember}
        onOpenChange={(open) => !open && closeModal('addMember')}
        title="Add Member"
      >
        <div className="p-4 space-y-2 max-h-80 overflow-auto">
          {availableUsers.length === 0 ? (
            <p className="text-sm text-text-tertiary text-center py-4">
              All users are already members of this group
            </p>
          ) : (
            availableUsers.map(user => (
              <button
                key={user.id}
                onClick={() => { handleAddMember(user.id); closeModal('addMember') }}
                className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-bg-tertiary transition-colors"
              >
                <div className="w-8 h-8 rounded-full bg-accent-primary/20 flex items-center justify-center">
                  <User size={16} className="text-accent-primary" />
                </div>
                <div className="text-left">
                  <p className="text-sm font-medium text-text-primary">{user.username}</p>
                  <p className="text-xs text-text-tertiary">{user.email}</p>
                </div>
              </button>
            ))
          )}
        </div>
      </Modal>
    </>
  )
}
