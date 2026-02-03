/**
 * Groups Section - Pro Feature
 * Uses UnifiedManagementLayout for consistent UX with Users
 */
import { useState, useEffect, useMemo } from 'react'
import { 
  UsersThree, Plus, Trash, PencilSimple, User, Shield, Clock,
  CheckCircle, XCircle
} from '@phosphor-icons/react'
import { 
  UnifiedManagementLayout, Badge, Button, Modal, Input, Select, HelpCard,
  CompactSection, CompactGrid, CompactField, CompactStats, CompactHeader
} from '../../components'
import { useNotification } from '../../contexts/NotificationContext'
import { apiClient } from '../../services/apiClient'
import { pluralize, formatDate } from '../../lib/ui'

export default function GroupsSection({ tabs, activeTab, onTabChange }) {
  const [groups, setGroups] = useState([])
  const [selectedGroup, setSelectedGroup] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [modalMode, setModalMode] = useState('create')
  const { showSuccess, showError, showConfirm } = useNotification()

  useEffect(() => {
    loadGroups()
  }, [])

  const loadGroups = async () => {
    try {
      const response = await apiClient.get('/groups')
      setGroups(response.data || [])
    } catch (error) {
      showError('Failed to load groups')
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = () => {
    setSelectedGroup(null)
    setModalMode('create')
    setShowModal(true)
  }

  const handleEdit = () => {
    setModalMode('edit')
    setShowModal(true)
  }

  const handleDelete = async () => {
    if (!selectedGroup) return
    const confirmed = await showConfirm(
      `Delete group "${selectedGroup.name}"? Members will be removed from this group.`,
      { title: 'Delete Group', confirmText: 'Delete', variant: 'danger' }
    )
    if (!confirmed) return
    try {
      await apiClient.delete(`/groups/${selectedGroup.id}`)
      showSuccess('Group deleted')
      loadGroups()
      setSelectedGroup(null)
    } catch (error) {
      showError('Failed to delete group')
    }
  }

  const handleSave = async (formData) => {
    try {
      if (modalMode === 'create') {
        await apiClient.post('/groups', formData)
        showSuccess('Group created')
      } else {
        await apiClient.put(`/groups/${selectedGroup.id}`, formData)
        showSuccess('Group updated')
      }
      setShowModal(false)
      loadGroups()
    } catch (error) {
      showError(error.message || 'Failed to save group')
    }
  }

  // Table columns
  const columns = useMemo(() => [
    {
      key: 'name',
      header: 'Group Name',
      sortable: true,
      render: (val, row) => (
        <div className="flex items-center gap-2">
          <UsersThree size={16} className="text-accent-primary shrink-0" />
          <span className="font-medium truncate">{val}</span>
        </div>
      )
    },
    {
      key: 'description',
      header: 'Description',
      render: (val) => (
        <span className="text-text-secondary truncate">
          {val || 'No description'}
        </span>
      )
    },
    {
      key: 'member_count',
      header: 'Members',
      width: 100,
      sortable: true,
      render: (val) => (
        <Badge variant="secondary" size="sm">
          {val || 0}
        </Badge>
      )
    },
    {
      key: 'default_role',
      header: 'Default Role',
      width: 120,
      render: (val) => (
        <Badge variant="info" size="sm">
          {val || 'viewer'}
        </Badge>
      )
    }
  ], [])

  // Row actions
  const rowActions = (row) => [
    {
      label: 'Edit',
      icon: PencilSimple,
      onClick: () => {
        setSelectedGroup(row)
        setModalMode('edit')
        setShowModal(true)
      }
    },
    {
      label: 'Delete',
      icon: Trash,
      variant: 'danger',
      onClick: async () => {
        const confirmed = await showConfirm(
          `Delete group "${row.name}"?`,
          { title: 'Delete Group', confirmText: 'Delete', variant: 'danger' }
        )
        if (confirmed) {
          try {
            await apiClient.delete(`/groups/${row.id}`)
            showSuccess('Group deleted')
            loadGroups()
            if (selectedGroup?.id === row.id) setSelectedGroup(null)
          } catch (error) {
            showError('Failed to delete group')
          }
        }
      }
    }
  ]

  // Render group details in focus panel
  const renderDetails = (group) => (
    <div className="p-3 space-y-3">
      {/* Header */}
      <CompactHeader
        icon={UsersThree}
        iconClass="bg-accent-primary/20"
        title={group.name}
        subtitle={group.description || 'No description'}
        badge={<Badge variant="info" size="sm">Pro</Badge>}
      />

      {/* Stats */}
      <CompactStats stats={[
        { icon: User, value: pluralize(group.member_count || 0, 'member') },
        { icon: Shield, value: group.default_role || 'viewer' },
      ]} />

      {/* Actions */}
      <div className="flex gap-2">
        <Button size="sm" variant="secondary" className="flex-1" onClick={handleEdit}>
          <PencilSimple size={14} /> Edit
        </Button>
        <Button size="sm" variant="danger" onClick={handleDelete}>
          <Trash size={14} />
        </Button>
      </div>

      {/* Group Info */}
      <CompactSection title="Group Information">
        <CompactGrid>
          <CompactField label="Members" value={group.member_count || 0} />
          <CompactField label="Default Role" value={group.default_role || 'viewer'} />
          <CompactField label="Created" value={group.created_at ? formatDate(group.created_at, 'short') : '—'} />
          <CompactField label="Updated" value={group.updated_at ? formatDate(group.updated_at, 'short') : '—'} />
        </CompactGrid>
      </CompactSection>

      {/* Members Section */}
      <CompactSection title={`Members (${group.members?.length || 0})`}>
        {group.members && group.members.length > 0 ? (
          <div className="space-y-1.5">
            {group.members.map(member => (
              <div 
                key={member.id} 
                className="flex items-center gap-2 p-1.5 rounded bg-bg-tertiary/50"
              >
                <div className="w-6 h-6 rounded-full bg-accent-primary/10 flex items-center justify-center">
                  <User size={12} className="text-accent-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-text-primary truncate">
                    {member.username}
                  </p>
                </div>
                <Badge variant="secondary" size="sm">
                  {member.role || 'viewer'}
                </Badge>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-text-tertiary py-2 text-center">
            No members in this group yet
          </p>
        )}
      </CompactSection>
    </div>
  )

  // Help content
  const helpContent = (
    <div className="space-y-4">
      <HelpCard variant="info" title="What are Groups?">
        Groups allow you to organize users and assign permissions to multiple users at once.
        A user can belong to multiple groups.
      </HelpCard>
      <HelpCard variant="tip" title="Best Practices">
        Create groups based on team roles (e.g., "Certificate Operators", "Security Admins").
        Assign a default role to automatically set permissions for new members.
      </HelpCard>
    </div>
  )

  // Compute stats
  const stats = useMemo(() => {
    const totalMembers = groups.reduce((sum, g) => sum + (g.member_count || 0), 0)
    const adminGroups = groups.filter(g => g.default_role === 'admin').length
    const operatorGroups = groups.filter(g => g.default_role === 'operator').length
    
    return [
      { label: 'Groups', value: groups.length, icon: UsersThree, variant: 'info' },
      { label: 'Members', value: totalMembers, icon: User, variant: 'secondary' },
      { label: 'Admin Groups', value: adminGroups, icon: Shield, variant: 'primary' },
    ]
  }, [groups])

  return (
    <>
      <UnifiedManagementLayout
        title="Groups"
        tabs={tabs}
        activeTab={activeTab}
        onTabChange={onTabChange}
        stats={stats}
        data={groups}
        columns={columns}
        loading={loading}
        selectedItem={selectedGroup}
        onSelectItem={setSelectedGroup}
        renderDetails={renderDetails}
        detailsTitle="Group Details"
        searchable
        searchPlaceholder="Search groups..."
        searchKeys={['name', 'description']}
        sortable
        defaultSort={{ key: 'name', direction: 'asc' }}
        paginated
        pageSize={25}
        rowActions={rowActions}
        emptyIcon={UsersThree}
        emptyTitle="No groups yet"
        emptyDescription="Create groups to organize users and manage permissions"
        emptyAction={
          <Button onClick={handleCreate}>
            <Plus size={16} /> New Group
          </Button>
        }
        helpContent={helpContent}
        actions={
          <Button size="sm" onClick={handleCreate}>
            <Plus size={16} /> New Group
          </Button>
        }
      />
      
      {/* Group Modal */}
      <Modal
        open={showModal}
        onClose={() => setShowModal(false)}
        title={modalMode === 'edit' ? 'Edit Group' : 'Create Group'}
        size="md"
      >
        <GroupForm
          group={modalMode === 'edit' ? selectedGroup : null}
          onSubmit={handleSave}
          onCancel={() => setShowModal(false)}
        />
      </Modal>
    </>
  )
}

function GroupForm({ group, onSubmit, onCancel }) {
  const [formData, setFormData] = useState({
    name: group?.name || '',
    description: group?.description || '',
    default_role: group?.default_role || 'viewer',
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    onSubmit(formData)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <Input
        label="Group Name"
        value={formData.name}
        onChange={e => setFormData({ ...formData, name: e.target.value })}
        required
        placeholder="e.g., Certificate Operators"
      />
      <Input
        label="Description"
        value={formData.description}
        onChange={e => setFormData({ ...formData, description: e.target.value })}
        placeholder="What is this group for?"
      />
      <Select
        label="Default Role"
        value={formData.default_role}
        onChange={value => setFormData({ ...formData, default_role: value })}
        options={[
          { value: 'admin', label: 'Admin' },
          { value: 'operator', label: 'Operator' },
          { value: 'viewer', label: 'Viewer' },
        ]}
      />
      <div className="flex justify-end gap-2 pt-4 border-t border-border">
        <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>
        <Button type="submit">{group ? 'Save Changes' : 'Create Group'}</Button>
      </div>
    </form>
  )
}
