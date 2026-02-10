/**
 * Command Palette Component - Global search with Cmd+K
 */
import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import * as Dialog from '@radix-ui/react-dialog'
import {
  MagnifyingGlass, House, Certificate, ShieldCheck, FileText, List,
  User, Key, Gear, Robot, UploadSimple, ClockCounterClockwise,
  UsersThree, Shield, Lock, UserCircle, ArrowRight, Command, Clock, Star,
  Spinner, Database, Wrench
} from '@phosphor-icons/react'
import { cn } from '../lib/utils'
import { useTranslation } from 'react-i18next'
import { useAllRecentHistory, useAllFavorites } from '../hooks'
import { searchService } from '../services'

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
  { id: 'tools', label: 'Go to Certificate Tools', icon: Wrench, path: '/tools', category: 'Navigation' },
  { id: 'audit', label: 'Go to Audit Logs', icon: ClockCounterClockwise, path: '/audit', category: 'Navigation' },
  { id: 'settings', label: 'Go to Settings', icon: Gear, path: '/settings', category: 'Navigation' },
  { id: 'account', label: 'Go to Account', icon: UserCircle, path: '/account', category: 'Navigation' },
  { id: 'groups', label: 'Go to Groups', icon: UsersThree, path: '/users?tab=groups', category: 'Navigation' },
  
  // Pro Navigation
  { id: 'rbac', label: 'Go to RBAC', icon: Shield, path: '/rbac', category: 'Pro', pro: true },
  { id: 'sso', label: 'Go to SSO', icon: Key, path: '/sso', category: 'Pro', pro: true },
  { id: 'hsm', label: 'Go to HSM', icon: Lock, path: '/hsm', category: 'Pro', pro: true },
  
  // Actions
  { id: 'new-cert', label: 'Issue New Certificate', icon: Certificate, path: '/certificates', action: 'new', category: 'Actions' },
  { id: 'new-ca', label: 'Create New CA', icon: ShieldCheck, path: '/cas', action: 'new', category: 'Actions' },
  { id: 'upload-csr', label: 'Upload CSR', icon: FileText, path: '/csrs', action: 'upload', category: 'Actions' },
]

export function CommandPalette({ open, onOpenChange }) {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [search, setSearch] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [searchResults, setSearchResults] = useState(null)
  const [isSearching, setIsSearching] = useState(false)
  const inputRef = useRef(null)
  const listRef = useRef(null)
  const searchTimeoutRef = useRef(null)
  const { allRecent, refreshHistory } = useAllRecentHistory()
  const { allFavorites, refreshFavorites } = useAllFavorites()

  // Get icon for recent item type
  const getTypeIcon = (type) => {
    switch (type) {
      case 'certificates': case 'certificate': return Certificate
      case 'cas': case 'ca': return ShieldCheck
      case 'users': case 'user': return User
      case 'csrs': case 'csr': return FileText
      case 'templates': case 'template': return List
      default: return Clock
    }
  }
  
  // Get path for item type
  const getTypePath = (type, id) => {
    switch (type) {
      case 'certificates': case 'certificate': return `/certificates?selected=${id}`
      case 'cas': case 'ca': return `/cas?selected=${id}`
      case 'users': case 'user': return `/users?selected=${id}`
      case 'csrs': case 'csr': return `/csrs?selected=${id}`
      case 'templates': case 'template': return `/templates?selected=${id}`
      default: return '/'
    }
  }

  // Debounced global search
  const performSearch = useCallback(async (query) => {
    if (!query || query.length < 2) {
      setSearchResults(null)
      setIsSearching(false)
      return
    }
    
    setIsSearching(true)
    try {
      const results = await searchService.globalSearch(query, 5)
      setSearchResults(results)
    } catch (error) {
      console.error('Search failed:', error)
      setSearchResults(null)
    } finally {
      setIsSearching(false)
    }
  }, [])

  // Debounce search input
  useEffect(() => {
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current)
    }
    
    if (search.length >= 2) {
      setIsSearching(true)
      searchTimeoutRef.current = setTimeout(() => {
        performSearch(search)
      }, 300)
    } else {
      setSearchResults(null)
      setIsSearching(false)
    }
    
    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current)
      }
    }
  }, [search, performSearch])

  // Refresh history and favorites when opened
  useEffect(() => {
    if (open) {
      refreshHistory()
      refreshFavorites()
    }
  }, [open, refreshHistory, refreshFavorites])

  // Filter commands based on search - all commands now available
  const filteredCommands = useMemo(() => {
    if (!search) return COMMANDS
    
    const lower = search.toLowerCase()
    return COMMANDS.filter(cmd => 
      cmd.label.toLowerCase().includes(lower) ||
      cmd.category.toLowerCase().includes(lower)
    )
  }, [search])
  
  // Filter recent items based on search
  const filteredRecent = useMemo(() => {
    if (!allRecent.length) return []
    if (!search) return allRecent.slice(0, 5)
    
    const lower = search.toLowerCase()
    return allRecent.filter(item =>
      item.name?.toLowerCase().includes(lower) ||
      item.subtitle?.toLowerCase().includes(lower) ||
      item.type?.toLowerCase().includes(lower)
    ).slice(0, 5)
  }, [search, allRecent])
  
  // Filter favorites based on search
  const filteredFavorites = useMemo(() => {
    if (!allFavorites.length) return []
    if (!search) return allFavorites.slice(0, 5)
    
    const lower = search.toLowerCase()
    return allFavorites.filter(item =>
      item.name?.toLowerCase().includes(lower) ||
      item.subtitle?.toLowerCase().includes(lower) ||
      item.type?.toLowerCase().includes(lower)
    ).slice(0, 5)
  }, [search, allFavorites])

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
          aria-describedby={undefined}
        >
          {/* Search Input */}
          <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
            {isSearching ? (
              <Spinner size={18} className="text-accent-primary animate-spin" />
            ) : (
              <MagnifyingGlass size={18} className="text-text-tertiary" />
            )}
            <input
              ref={inputRef}
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder={t('commandPalette.searchPlaceholder')}
              className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-tertiary outline-none"
            />
            <kbd className="px-1.5 py-0.5 text-2xs bg-bg-tertiary border border-border rounded text-text-tertiary">
              ESC
            </kbd>
          </div>

          {/* Commands List */}
          <div ref={listRef} className="max-h-80 overflow-auto p-2">
            {/* Database Search Results */}
            {searchResults && (
              <>
                {/* Certificates */}
                {searchResults.certificates?.length > 0 && (
                  <div className="mb-2">
                    <div className="px-3 py-1.5 text-2xs font-semibold text-text-tertiary uppercase tracking-wider flex items-center gap-1.5">
                      <Certificate size={10} />
                      Certificates ({searchResults.certificates.length})
                    </div>
                    {searchResults.certificates.map(item => (
                      <button
                        key={`cert-${item.id}`}
                        onClick={() => {
                          navigate(`/certificates?selected=${item.id}`)
                          onOpenChange(false)
                        }}
                        className="w-full flex items-center gap-3 px-3 py-2 rounded-md text-left transition-colors text-text-secondary hover:bg-bg-tertiary"
                      >
                        <Certificate size={16} weight="duotone" className="text-accent-primary" />
                        <div className="flex-1 min-w-0">
                          <span className="text-sm block truncate">{item.name}</span>
                          <span className="text-2xs text-text-tertiary truncate block">{item.subject}</span>
                        </div>
                        <span className={cn(
                          'text-2xs px-1.5 py-0.5 rounded',
                          item.status === 'valid' ? 'badge-bg-green' :
                          item.status === 'expired' ? 'alert-bg-red' :
                          'badge-bg-amber'
                        )}>{item.status}</span>
                      </button>
                    ))}
                  </div>
                )}

                {/* CAs */}
                {searchResults.cas?.length > 0 && (
                  <div className="mb-2">
                    <div className="px-3 py-1.5 text-2xs font-semibold text-text-tertiary uppercase tracking-wider flex items-center gap-1.5">
                      <ShieldCheck size={10} />
                      Certificate Authorities ({searchResults.cas.length})
                    </div>
                    {searchResults.cas.map(item => (
                      <button
                        key={`ca-${item.id}`}
                        onClick={() => {
                          navigate(`/cas?selected=${item.id}`)
                          onOpenChange(false)
                        }}
                        className="w-full flex items-center gap-3 px-3 py-2 rounded-md text-left transition-colors text-text-secondary hover:bg-bg-tertiary"
                      >
                        <ShieldCheck size={16} weight="duotone" className="text-violet-500" />
                        <div className="flex-1 min-w-0">
                          <span className="text-sm block truncate">{item.name}</span>
                          <span className="text-2xs text-text-tertiary truncate block">{item.subject}</span>
                        </div>
                        {item.is_root && (
                          <span className="text-2xs px-1.5 py-0.5 rounded badge-bg-violet">Root</span>
                        )}
                      </button>
                    ))}
                  </div>
                )}

                {/* Users */}
                {searchResults.users?.length > 0 && (
                  <div className="mb-2">
                    <div className="px-3 py-1.5 text-2xs font-semibold text-text-tertiary uppercase tracking-wider flex items-center gap-1.5">
                      <User size={10} />
                      Users ({searchResults.users.length})
                    </div>
                    {searchResults.users.map(item => (
                      <button
                        key={`user-${item.id}`}
                        onClick={() => {
                          navigate(`/users?selected=${item.id}`)
                          onOpenChange(false)
                        }}
                        className="w-full flex items-center gap-3 px-3 py-2 rounded-md text-left transition-colors text-text-secondary hover:bg-bg-tertiary"
                      >
                        <User size={16} weight="duotone" className="text-status-success" />
                        <div className="flex-1 min-w-0">
                          <span className="text-sm block truncate">{item.name}</span>
                          <span className="text-2xs text-text-tertiary truncate block">{item.email}</span>
                        </div>
                        <span className="text-2xs px-1.5 py-0.5 rounded bg-bg-tertiary">{item.role}</span>
                      </button>
                    ))}
                  </div>
                )}

                {/* Templates */}
                {searchResults.templates?.length > 0 && (
                  <div className="mb-2">
                    <div className="px-3 py-1.5 text-2xs font-semibold text-text-tertiary uppercase tracking-wider flex items-center gap-1.5">
                      <List size={10} />
                      Templates ({searchResults.templates.length})
                    </div>
                    {searchResults.templates.map(item => (
                      <button
                        key={`tpl-${item.id}`}
                        onClick={() => {
                          navigate(`/templates?selected=${item.id}`)
                          onOpenChange(false)
                        }}
                        className="w-full flex items-center gap-3 px-3 py-2 rounded-md text-left transition-colors text-text-secondary hover:bg-bg-tertiary"
                      >
                        <List size={16} weight="duotone" className="text-status-warning" />
                        <div className="flex-1 min-w-0">
                          <span className="text-sm block truncate">{item.name}</span>
                          <span className="text-2xs text-text-tertiary truncate block">{item.description}</span>
                        </div>
                      </button>
                    ))}
                  </div>
                )}

                {/* CSRs */}
                {searchResults.csrs?.length > 0 && (
                  <div className="mb-2">
                    <div className="px-3 py-1.5 text-2xs font-semibold text-text-tertiary uppercase tracking-wider flex items-center gap-1.5">
                      <FileText size={10} />
                      CSRs ({searchResults.csrs.length})
                    </div>
                    {searchResults.csrs.map(item => (
                      <button
                        key={`csr-${item.id}`}
                        onClick={() => {
                          navigate(`/csrs?selected=${item.id}`)
                          onOpenChange(false)
                        }}
                        className="w-full flex items-center gap-3 px-3 py-2 rounded-md text-left transition-colors text-text-secondary hover:bg-bg-tertiary"
                      >
                        <FileText size={16} weight="duotone" className="text-teal-500" />
                        <div className="flex-1 min-w-0">
                          <span className="text-sm block truncate">{item.name}</span>
                          <span className="text-2xs text-text-tertiary truncate block">{item.subject}</span>
                        </div>
                        <span className="text-2xs px-1.5 py-0.5 rounded bg-bg-tertiary">{item.status}</span>
                      </button>
                    ))}
                  </div>
                )}

                {/* No results message */}
                {searchResults.certificates?.length === 0 && 
                 searchResults.cas?.length === 0 && 
                 searchResults.users?.length === 0 && 
                 searchResults.templates?.length === 0 && 
                 searchResults.csrs?.length === 0 && (
                  <div className="px-3 py-4 text-center text-text-tertiary text-sm">
                    <Database size={24} className="mx-auto mb-2 opacity-50" />
                    {t('commandPalette.noResultsInDatabase')}
                  </div>
                )}

                {/* Separator */}
                {(searchResults.certificates?.length > 0 || searchResults.cas?.length > 0 || 
                  searchResults.users?.length > 0 || searchResults.templates?.length > 0 || 
                  searchResults.csrs?.length > 0) && filteredCommands.length > 0 && (
                  <div className="border-t border-border my-2" />
                )}
              </>
            )}

            {/* Favorites Section */}
            {filteredFavorites.length > 0 && !searchResults && (
              <div className="mb-2">
                <div className="px-3 py-1.5 text-2xs font-semibold text-text-tertiary uppercase tracking-wider flex items-center gap-1.5">
                  <Star size={10} weight="fill" className="text-status-warning" />
                  {t('commandPalette.favorites')}
                </div>
                {filteredFavorites.map(item => {
                  const Icon = getTypeIcon(item.type)
                  return (
                    <button
                      key={`fav-${item.type}-${item.id}`}
                      onClick={() => {
                        navigate(getTypePath(item.type, item.id))
                        onOpenChange(false)
                      }}
                      className="w-full flex items-center gap-3 px-3 py-2 rounded-md text-left transition-colors text-text-secondary hover:bg-bg-tertiary"
                    >
                      <Icon size={16} weight="duotone" />
                      <div className="flex-1 min-w-0">
                        <span className="text-sm block truncate">{item.name}</span>
                        {item.subtitle && (
                          <span className="text-2xs text-text-tertiary truncate block">{item.subtitle}</span>
                        )}
                      </div>
                      <Star size={12} weight="fill" className="text-status-warning" />
                    </button>
                  )
                })}
              </div>
            )}
            
            {/* Recent Items Section */}
            {filteredRecent.length > 0 && (
              <div className="mb-2">
                <div className="px-3 py-1.5 text-2xs font-semibold text-text-tertiary uppercase tracking-wider flex items-center gap-1.5">
                  <Clock size={10} />
                  {t('commandPalette.recent')}
                </div>
                {filteredRecent.map(item => {
                  const Icon = getTypeIcon(item.type)
                  return (
                    <button
                      key={`recent-${item.type}-${item.id}`}
                      onClick={() => {
                        navigate(getTypePath(item.type, item.id))
                        onOpenChange(false)
                      }}
                      className="w-full flex items-center gap-3 px-3 py-2 rounded-md text-left transition-colors text-text-secondary hover:bg-bg-tertiary"
                    >
                      <Icon size={16} weight="duotone" />
                      <div className="flex-1 min-w-0">
                        <span className="text-sm block truncate">{item.name}</span>
                        {item.subtitle && (
                          <span className="text-2xs text-text-tertiary truncate block">{item.subtitle}</span>
                        )}
                      </div>
                      <span className="text-2xs text-text-tertiary capitalize">{item.type}</span>
                    </button>
                  )
                })}
              </div>
            )}
            
            {filteredCommands.length === 0 && filteredRecent.length === 0 && filteredFavorites.length === 0 ? (
              <div className="px-3 py-8 text-center text-text-tertiary text-sm">
                {t('commandPalette.noCommandsFound')}
              </div>
            ) : (
              Object.entries(groupedCommands).map(([category, commands]) => (
                <div key={category} className="mb-2">
                  <div className="px-3 py-1.5 text-2xs font-semibold text-text-tertiary uppercase tracking-wider">
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
          <div className="px-4 py-2 border-t border-border bg-bg-tertiary/50 flex items-center gap-4 text-2xs text-text-tertiary">
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 bg-bg-tertiary border border-border rounded">↑↓</kbd>
              {t('commandPalette.navigate')}
            </span>
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 bg-bg-tertiary border border-border rounded">↵</kbd>
              {t('commandPalette.select')}
            </span>
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 bg-bg-tertiary border border-border rounded">esc</kbd>
              {t('common.close')}
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
