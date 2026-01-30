/**
 * Command Palette Component - Global search with Cmd+K
 */
import { useState, useEffect, useRef, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import * as Dialog from '@radix-ui/react-dialog'
import {
  MagnifyingGlass, House, Certificate, ShieldCheck, FileText, List,
  User, Key, Gear, Robot, UploadSimple, ClockCounterClockwise,
  UsersThree, Shield, Lock, UserCircle, ArrowRight, Command
} from '@phosphor-icons/react'
import { cn } from '../lib/utils'

const COMMANDS = [
  // Navigation
  { id: 'dashboard', label: 'Go to Dashboard', icon: House, path: '/', category: 'Navigation' },
  { id: 'certificates', label: 'Go to Certificates', icon: Certificate, path: '/certificates', category: 'Navigation' },
  { id: 'cas', label: 'Go to CAs', icon: ShieldCheck, path: '/cas', category: 'Navigation' },
  { id: 'csrs', label: 'Go to CSRs', icon: FileText, path: '/csrs', category: 'Navigation' },
  { id: 'templates', label: 'Go to Templates', icon: List, path: '/templates', category: 'Navigation' },
  { id: 'users', label: 'Go to Users', icon: User, path: '/users', category: 'Navigation' },
  { id: 'acme', label: 'Go to ACME', icon: Key, path: '/acme', category: 'Navigation' },
  { id: 'scep', label: 'Go to SCEP', icon: Robot, path: '/scep-config', category: 'Navigation' },
  { id: 'import', label: 'Go to Import', icon: UploadSimple, path: '/import', category: 'Navigation' },
  { id: 'audit', label: 'Go to Audit Logs', icon: ClockCounterClockwise, path: '/audit', category: 'Navigation' },
  { id: 'settings', label: 'Go to Settings', icon: Gear, path: '/settings', category: 'Navigation' },
  { id: 'account', label: 'Go to Account', icon: UserCircle, path: '/account', category: 'Navigation' },
  
  // Pro Navigation
  { id: 'groups', label: 'Go to Groups', icon: UsersThree, path: '/groups', category: 'Pro', pro: true },
  { id: 'rbac', label: 'Go to RBAC', icon: Shield, path: '/rbac', category: 'Pro', pro: true },
  { id: 'sso', label: 'Go to SSO', icon: Key, path: '/sso', category: 'Pro', pro: true },
  { id: 'hsm', label: 'Go to HSM', icon: Lock, path: '/hsm', category: 'Pro', pro: true },
  
  // Actions
  { id: 'new-cert', label: 'Issue New Certificate', icon: Certificate, path: '/certificates', action: 'new', category: 'Actions' },
  { id: 'new-ca', label: 'Create New CA', icon: ShieldCheck, path: '/cas', action: 'new', category: 'Actions' },
  { id: 'upload-csr', label: 'Upload CSR', icon: FileText, path: '/csrs', action: 'upload', category: 'Actions' },
]

export function CommandPalette({ open, onOpenChange, isPro = false }) {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef(null)
  const listRef = useRef(null)

  // Filter commands based on search and pro status
  const filteredCommands = useMemo(() => {
    const available = COMMANDS.filter(cmd => !cmd.pro || isPro)
    if (!search) return available
    
    const lower = search.toLowerCase()
    return available.filter(cmd => 
      cmd.label.toLowerCase().includes(lower) ||
      cmd.category.toLowerCase().includes(lower)
    )
  }, [search, isPro])

  // Group by category
  const groupedCommands = useMemo(() => {
    const groups = {}
    filteredCommands.forEach(cmd => {
      if (!groups[cmd.category]) groups[cmd.category] = []
      groups[cmd.category].push(cmd)
    })
    return groups
  }, [filteredCommands])

  // Reset selection when search changes
  useEffect(() => {
    setSelectedIndex(0)
  }, [search])

  // Focus input when opened
  useEffect(() => {
    if (open) {
      setSearch('')
      setSelectedIndex(0)
      setTimeout(() => inputRef.current?.focus(), 0)
    }
  }, [open])

  // Scroll selected item into view
  useEffect(() => {
    if (listRef.current && filteredCommands.length > 0) {
      const items = listRef.current.querySelectorAll('[data-command-item]')
      items[selectedIndex]?.scrollIntoView({ block: 'nearest' })
    }
  }, [selectedIndex, filteredCommands.length])

  const executeCommand = (command) => {
    onOpenChange(false)
    navigate(command.path)
    // TODO: Handle action parameter for specific actions
  }

  const handleKeyDown = (e) => {
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setSelectedIndex(i => Math.min(i + 1, filteredCommands.length - 1))
        break
      case 'ArrowUp':
        e.preventDefault()
        setSelectedIndex(i => Math.max(i - 1, 0))
        break
      case 'Enter':
        e.preventDefault()
        if (filteredCommands[selectedIndex]) {
          executeCommand(filteredCommands[selectedIndex])
        }
        break
      case 'Escape':
        onOpenChange(false)
        break
    }
  }

  let itemIndex = -1

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50" />
        <Dialog.Content 
          className="fixed top-[20%] left-1/2 -translate-x-1/2 w-full max-w-lg bg-bg-secondary border border-border rounded-lg shadow-2xl z-50 overflow-hidden"
          onKeyDown={handleKeyDown}
        >
          {/* Search Input */}
          <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
            <MagnifyingGlass size={18} className="text-text-tertiary" />
            <input
              ref={inputRef}
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search commands..."
              className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-tertiary outline-none"
            />
            <kbd className="px-1.5 py-0.5 text-[10px] bg-bg-tertiary border border-border rounded text-text-tertiary">
              ESC
            </kbd>
          </div>

          {/* Commands List */}
          <div ref={listRef} className="max-h-80 overflow-auto p-2">
            {filteredCommands.length === 0 ? (
              <div className="px-3 py-8 text-center text-text-tertiary text-sm">
                No commands found
              </div>
            ) : (
              Object.entries(groupedCommands).map(([category, commands]) => (
                <div key={category} className="mb-2">
                  <div className="px-3 py-1.5 text-[10px] font-semibold text-text-tertiary uppercase tracking-wider">
                    {category}
                  </div>
                  {commands.map(cmd => {
                    itemIndex++
                    const currentIndex = itemIndex
                    const Icon = cmd.icon
                    return (
                      <button
                        key={cmd.id}
                        data-command-item
                        onClick={() => executeCommand(cmd)}
                        onMouseEnter={() => setSelectedIndex(currentIndex)}
                        className={cn(
                          "w-full flex items-center gap-3 px-3 py-2 rounded-md text-left transition-colors",
                          currentIndex === selectedIndex
                            ? "bg-accent-primary/15 text-accent-primary"
                            : "text-text-secondary hover:bg-bg-tertiary"
                        )}
                      >
                        <Icon size={16} weight="duotone" />
                        <span className="flex-1 text-sm">{cmd.label}</span>
                        {currentIndex === selectedIndex && (
                          <ArrowRight size={14} className="text-accent-primary" />
                        )}
                      </button>
                    )
                  })}
                </div>
              ))
            )}
          </div>

          {/* Footer */}
          <div className="px-4 py-2 border-t border-border bg-bg-tertiary/50 flex items-center gap-4 text-[10px] text-text-tertiary">
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 bg-bg-tertiary border border-border rounded">↑↓</kbd>
              Navigate
            </span>
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 bg-bg-tertiary border border-border rounded">↵</kbd>
              Select
            </span>
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 bg-bg-tertiary border border-border rounded">esc</kbd>
              Close
            </span>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

/**
 * Hook to handle global keyboard shortcuts
 */
export function useKeyboardShortcuts({ onCommandPalette }) {
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Cmd+K or Ctrl+K - Open command palette
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        onCommandPalette?.()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onCommandPalette])
}
