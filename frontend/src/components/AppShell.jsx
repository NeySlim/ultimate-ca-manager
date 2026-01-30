/**
 * AppShell Component - Main application layout with mobile support
 */
import { useState, useEffect } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { List, X } from '@phosphor-icons/react'
import { Sidebar } from './Sidebar'
import { CommandPalette, useKeyboardShortcuts } from './CommandPalette'
import { cn } from '../lib/utils'

export function AppShell() {
  const location = useLocation()
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(false)
  
  // Extract current page from pathname (empty string for dashboard)
  const activePage = location.pathname.split('/')[1] || ''

  // Check for mobile viewport
  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 768)
    checkMobile()
    window.addEventListener('resize', checkMobile)
    return () => window.removeEventListener('resize', checkMobile)
  }, [])

  // Close mobile menu on navigation
  useEffect(() => {
    setMobileMenuOpen(false)
  }, [location.pathname])

  // Keyboard shortcuts
  useKeyboardShortcuts({
    onCommandPalette: () => setCommandPaletteOpen(true)
  })

  return (
    <div className="flex h-full w-full bg-bg-primary overflow-hidden">
      {/* Mobile Header */}
      {isMobile && (
        <div className="fixed top-0 left-0 right-0 h-12 bg-bg-secondary border-b border-border flex items-center px-3 z-40">
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="w-9 h-9 flex items-center justify-center rounded-md text-text-secondary hover:bg-bg-tertiary"
          >
            {mobileMenuOpen ? <X size={20} /> : <List size={20} />}
          </button>
          <span className="ml-3 text-sm font-semibold text-text-primary uppercase tracking-wide">
            {activePage || 'Dashboard'}
          </span>
          <div className="flex-1" />
          <button
            onClick={() => setCommandPaletteOpen(true)}
            className="px-2 py-1 text-xs text-text-tertiary bg-bg-tertiary border border-border rounded flex items-center gap-1.5"
          >
            <span>Search</span>
            <kbd className="text-[10px]">⌘K</kbd>
          </button>
        </div>
      )}

      {/* Sidebar - Hidden on mobile, shown in overlay */}
      <div className={cn(
        "flex-shrink-0 z-50",
        isMobile && "fixed inset-y-0 left-0 transform transition-transform duration-200",
        isMobile && !mobileMenuOpen && "-translate-x-full",
        isMobile && mobileMenuOpen && "translate-x-0"
      )}>
        <Sidebar activePage={activePage} />
      </div>

      {/* Mobile overlay */}
      {isMobile && mobileMenuOpen && (
        <div 
          className="fixed inset-0 bg-black/50 z-40"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      {/* Main Content */}
      <div className={cn(
        "flex-1 flex min-h-0 min-w-0 overflow-hidden",
        isMobile && "pt-12" // Account for mobile header
      )}>
        <Outlet />
      </div>

      {/* Command Palette */}
      <CommandPalette 
        open={commandPaletteOpen} 
        onOpenChange={setCommandPaletteOpen}
        isPro={true} // TODO: Get from license context
      />
    </div>
  )
}
