/**
 * MemberTransferModal - Dual-list member management
 * 
 * Left: Available users (not in group)
 * Right: Group members
 * 
 * Features:
 * - Drag & drop between lists
 * - Click +/- icons to transfer
 * - Multi-select with checkboxes
 * - Search/filter in each list
 * - Bulk add/remove with arrow buttons
 */
import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { 
  User, MagnifyingGlass, Plus, Minus, CaretRight, CaretLeft,
  CaretDoubleRight, CaretDoubleLeft, CheckSquare, Square
} from '@phosphor-icons/react'
import { Modal } from './Modal'
import { Button } from './Button'
import { cn } from '../lib/utils'

export function MemberTransferModal({
  open,
  onClose,
  title,
  allUsers = [],
  currentMembers = [],
  onSave,
  loading = false,
}) {
  const { t } = useTranslation()
  const modalTitle = title || t('members.manageMembers')
  // Local state for pending changes - store user IDs
  const [members, setMembers] = useState(() => 
    currentMembers.map(m => m.user_id)
  )
  
  // Search states
  const [searchAvailable, setSearchAvailable] = useState('')
  const [searchMembers, setSearchMembers] = useState('')
  
  // Selection states
  const [selectedAvailable, setSelectedAvailable] = useState(new Set())
  const [selectedMembers, setSelectedMembers] = useState(new Set())
  
  // Drag state - use ref for persistence across renders
  const draggedUserRef = useRef(null)
  const [dragOver, setDragOver] = useState(null) // 'available' | 'members'

  // Reset state when modal opens or currentMembers changes
  useEffect(() => {
    if (open) {
      setMembers(currentMembers.map(m => m.user_id))
      setSelectedAvailable(new Set())
      setSelectedMembers(new Set())
      setSearchAvailable('')
      setSearchMembers('')
    }
  }, [open, currentMembers])

  // Computed lists
  const availableUsers = useMemo(() => {
    const memberSet = new Set(members)
    return allUsers
      .filter(u => !memberSet.has(u.id))
      .filter(u => {
        if (!searchAvailable) return true
        const search = searchAvailable.toLowerCase()
        return (
          u.username?.toLowerCase().includes(search) ||
          u.email?.toLowerCase().includes(search) ||
          u.full_name?.toLowerCase().includes(search)
        )
      })
  }, [allUsers, members, searchAvailable])

  const memberUsers = useMemo(() => {
    const memberSet = new Set(members)
    return allUsers
      .filter(u => memberSet.has(u.id))
      .filter(u => {
        if (!searchMembers) return true
        const search = searchMembers.toLowerCase()
        return (
          u.username?.toLowerCase().includes(search) ||
          u.email?.toLowerCase().includes(search) ||
          u.full_name?.toLowerCase().includes(search)
        )
      })
  }, [allUsers, members, searchMembers])

  // Actions
  const addUser = useCallback((userId) => {
    setMembers(prev => [...prev, userId])
    setSelectedAvailable(prev => {
      const next = new Set(prev)
      next.delete(userId)
      return next
    })
  }, [])

  const removeUser = useCallback((userId) => {
    setMembers(prev => prev.filter(id => id !== userId))
    setSelectedMembers(prev => {
      const next = new Set(prev)
      next.delete(userId)
      return next
    })
  }, [])

  const addSelected = useCallback(() => {
    setMembers(prev => [...prev, ...Array.from(selectedAvailable)])
    setSelectedAvailable(new Set())
  }, [selectedAvailable])

  const removeSelected = useCallback(() => {
    setMembers(prev => prev.filter(id => !selectedMembers.has(id)))
    setSelectedMembers(new Set())
  }, [selectedMembers])

  const addAll = useCallback(() => {
    const availableIds = availableUsers.map(u => u.id)
    setMembers(prev => [...new Set([...prev, ...availableIds])])
    setSelectedAvailable(new Set())
  }, [availableUsers])

  const removeAll = useCallback(() => {
    const memberIds = memberUsers.map(u => u.id)
    setMembers(prev => prev.filter(id => !memberIds.includes(id)))
    setSelectedMembers(new Set())
  }, [memberUsers])

  // Selection toggle
  const toggleAvailableSelection = (userId) => {
    setSelectedAvailable(prev => {
      const next = new Set(prev)
      if (next.has(userId)) next.delete(userId)
      else next.add(userId)
      return next
    })
  }

  const toggleMemberSelection = (userId) => {
    setSelectedMembers(prev => {
      const next = new Set(prev)
      if (next.has(userId)) next.delete(userId)
      else next.add(userId)
      return next
    })
  }

  // Drag handlers
  const handleDragStart = (e, user, from) => {
    draggedUserRef.current = { user, from }
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', user.id.toString())
  }

  const handleDragOver = (e, target) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setDragOver(target)
  }

  const handleDragLeave = () => {
    setDragOver(null)
  }

  const handleDrop = (e, target) => {
    e.preventDefault()
    setDragOver(null)
    
    if (!draggedUserRef.current) return
    
    const { user, from } = draggedUserRef.current
    
    if (from === 'available' && target === 'members') {
      addUser(user.id)
    } else if (from === 'members' && target === 'available') {
      removeUser(user.id)
    }
    
    draggedUserRef.current = null
  }

  // Save handler
  const handleSave = () => {
    onSave?.(members)
  }

  // Check if there are changes
  const hasChanges = useMemo(() => {
    const originalSet = new Set(currentMembers.map(m => m.user_id))
    const newSet = new Set(members)
    if (originalSet.size !== newSet.size) return true
    for (const id of originalSet) {
      if (!newSet.has(id)) return true
    }
    return false
  }, [currentMembers, members])

  // User item component
  const UserItem = ({ user, selected, onToggle, onAction, actionIcon: ActionIcon, actionVariant, draggable, from }) => (
    <div
      draggable={draggable}
      onDragStart={draggable ? (e) => handleDragStart(e, user, from) : undefined}
      className={cn(
        "flex items-center gap-2 px-2 py-1.5 rounded-md transition-all cursor-pointer",
        "hover:bg-bg-tertiary",
        selected && "bg-accent-primary/10 border border-accent-primary/30",
        !selected && "border border-transparent",
        draggable && "cursor-grab active:cursor-grabbing"
      )}
      onClick={() => onToggle(user.id)}
    >
      {/* Checkbox */}
      <button
        onClick={(e) => { e.stopPropagation(); onToggle(user.id) }}
        className="text-text-secondary hover:text-accent-primary"
      >
        {selected ? (
          <CheckSquare size={16} weight="fill" className="text-accent-primary" />
        ) : (
          <Square size={16} />
        )}
      </button>

      {/* Avatar */}
      <div className="w-7 h-7 rounded-full bg-accent-primary/20 flex items-center justify-center shrink-0">
        <User size={14} className="text-accent-primary" />
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-text-primary truncate">
          {user.username}
        </p>
        <p className="text-xs text-text-tertiary truncate">
          {user.email || user.full_name || ''}
        </p>
      </div>

      {/* Action button */}
      <button
        onClick={(e) => { e.stopPropagation(); onAction(user.id) }}
        className={cn(
          "p-1 rounded transition-colors",
          actionVariant === 'add' && "text-status-success hover:bg-status-success/10",
          actionVariant === 'remove' && "text-status-danger hover:bg-status-danger/10"
        )}
      >
        <ActionIcon size={16} weight="bold" />
      </button>
    </div>
  )

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={modalTitle}
      size="xl"
    >
      <div className="p-4">
        <div className="flex gap-4 h-[400px]">
          {/* Left: Available Users */}
          <div
            className={cn(
              "flex-1 flex flex-col border rounded-lg overflow-hidden transition-colors",
              dragOver === 'available' ? "border-accent-primary bg-accent-primary/5" : "border-border"
            )}
            onDragOver={(e) => handleDragOver(e, 'available')}
            onDragLeave={handleDragLeave}
            onDrop={(e) => handleDrop(e, 'available')}
          >
            {/* Header */}
            <div className="px-3 py-2 bg-bg-secondary border-b border-border">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-text-primary">
                  {t('members.availableUsers')}
                </span>
                <span className="text-xs text-text-tertiary">
                  {availableUsers.length}
                </span>
              </div>
              {/* Search */}
              <div className="relative">
                <MagnifyingGlass size={14} className="absolute left-2 top-1/2 -translate-y-1/2 text-text-tertiary" />
                <input
                  type="text"
                  placeholder={t('common.search') + '...'}
                  value={searchAvailable}
                  onChange={(e) => setSearchAvailable(e.target.value)}
                  className="w-full pl-7 pr-2 py-1.5 text-xs bg-bg-tertiary border border-border rounded text-text-primary placeholder:text-text-tertiary focus:outline-none focus:ring-1 focus:ring-accent-primary"
                />
              </div>
            </div>

            {/* List */}
            <div className="flex-1 overflow-auto p-2 space-y-1">
              {availableUsers.length === 0 ? (
                <p className="text-xs text-text-tertiary text-center py-4">
                  {searchAvailable ? t('members.noMatchingUsers') : t('members.allUsersAreMembers')}
                </p>
              ) : (
                availableUsers.map(user => (
                  <UserItem
                    key={user.id}
                    user={user}
                    selected={selectedAvailable.has(user.id)}
                    onToggle={toggleAvailableSelection}
                    onAction={addUser}
                    actionIcon={Plus}
                    actionVariant="add"
                    draggable
                    from="available"
                  />
                ))
              )}
            </div>
          </div>

          {/* Center: Transfer buttons */}
          <div className="flex flex-col items-center justify-center gap-2 py-4">
            <Button
              size="sm"
              variant="secondary"
              onClick={addAll}
              disabled={availableUsers.length === 0}
              title={t('members.addAll')}
              className="w-9 h-9 p-0"
            >
              <CaretDoubleRight size={16} />
            </Button>
            <Button
              size="sm"
              variant="primary"
              onClick={addSelected}
              disabled={selectedAvailable.size === 0}
              title={t('members.addSelected')}
              className="w-9 h-9 p-0"
            >
              <CaretRight size={18} weight="bold" />
            </Button>
            <Button
              size="sm"
              variant="danger"
              onClick={removeSelected}
              disabled={selectedMembers.size === 0}
              title={t('members.removeSelected')}
              className="w-9 h-9 p-0"
            >
              <CaretLeft size={18} weight="bold" />
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={removeAll}
              disabled={memberUsers.length === 0}
              title={t('members.removeAll')}
              className="w-9 h-9 p-0"
            >
              <CaretDoubleLeft size={16} />
            </Button>
          </div>

          {/* Right: Group Members */}
          <div
            className={cn(
              "flex-1 flex flex-col border rounded-lg overflow-hidden transition-colors",
              dragOver === 'members' ? "border-accent-primary bg-accent-primary/5" : "border-border"
            )}
            onDragOver={(e) => handleDragOver(e, 'members')}
            onDragLeave={handleDragLeave}
            onDrop={(e) => handleDrop(e, 'members')}
          >
            {/* Header */}
            <div className="px-3 py-2 bg-bg-secondary border-b border-border">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-text-primary">
                  {t('members.groupMembers')}
                </span>
                <span className="text-xs text-text-tertiary">
                  {memberUsers.length}
                </span>
              </div>
              {/* Search */}
              <div className="relative">
                <MagnifyingGlass size={14} className="absolute left-2 top-1/2 -translate-y-1/2 text-text-tertiary" />
                <input
                  type="text"
                  placeholder={t('common.search') + '...'}
                  value={searchMembers}
                  onChange={(e) => setSearchMembers(e.target.value)}
                  className="w-full pl-7 pr-2 py-1.5 text-xs bg-bg-tertiary border border-border rounded text-text-primary placeholder:text-text-tertiary focus:outline-none focus:ring-1 focus:ring-accent-primary"
                />
              </div>
            </div>

            {/* List */}
            <div className="flex-1 overflow-auto p-2 space-y-1">
              {memberUsers.length === 0 ? (
                <p className="text-xs text-text-tertiary text-center py-4">
                  {searchMembers ? t('members.noMatchingMembers') : t('members.noMembersYet')}
                </p>
              ) : (
                memberUsers.map(user => (
                  <UserItem
                    key={user.id}
                    user={user}
                    selected={selectedMembers.has(user.id)}
                    onToggle={toggleMemberSelection}
                    onAction={removeUser}
                    actionIcon={Minus}
                    actionVariant="remove"
                    draggable
                    from="members"
                  />
                ))
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between mt-4 pt-4 border-t border-border">
          <p className="text-xs text-text-tertiary">
            {hasChanges ? (
              <span className="text-status-warning">{t('common.unsavedChanges')}</span>
            ) : (
              t('members.dragOrUseButtons')
            )}
          </p>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleSave} disabled={!hasChanges || loading}>
              {loading ? t('common.loading') : t('common.save')}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  )
}

export default MemberTransferModal
