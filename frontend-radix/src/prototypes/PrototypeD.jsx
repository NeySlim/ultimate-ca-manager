// PROTOTYPE D: Split View COMPLETE avec navigation + search + settings + THEMES
import { useState } from 'react'
import { 
  Certificate, ShieldCheck, CaretRight, CaretDown, MagnifyingGlass,
  Key, FileText, Gear, User, SignOut, House, List, Clock, Lock, Palette, Check
} from '@phosphor-icons/react'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { Card } from '../components/Card'
import { Badge } from '../components/Badge'
import { useTheme } from '../contexts/ThemeContext'

export default function PrototypeD() {
  const { currentTheme, setCurrentTheme, themes } = useTheme()
  const [activePage, setActivePage] = useState('certificates')
  const [selected, setSelected] = useState('cert-1')
  const [expanded, setExpanded] = useState({ certs: true, cas: true })
  const [searchQuery, setSearchQuery] = useState('')
  
  const pages = [
    { id: 'dashboard', icon: House, label: 'Dashboard' },
    { id: 'certificates', icon: Certificate, label: 'Certificates' },
    { id: 'cas', icon: ShieldCheck, label: 'CAs' },
    { id: 'csrs', icon: FileText, label: 'CSRs' },
    { id: 'templates', icon: List, label: 'Templates' },
    { id: 'users', icon: User, label: 'Users' },
    { id: 'acme', icon: Key, label: 'ACME' },
    { id: 'settings', icon: Gear, label: 'Settings' },
  ]
  
  const data = {
    cas: [
      { id: 'ca-1', name: 'Root CA', children: 2 },
      { id: 'ca-2', name: 'Intermediate CA', children: 3 },
    ],
    certs: [
      { id: 'cert-1', name: 'app.example.com', status: 'valid', expires: '2025-12-31' },
      { id: 'cert-2', name: 'api.example.com', status: 'expiring', expires: '2025-02-10' },
      { id: 'cert-3', name: 'web.example.com', status: 'valid', expires: '2026-06-15' },
      { id: 'cert-4', name: 'mail.example.com', status: 'valid', expires: '2026-03-20' },
    ]
  }
  
  const filteredCerts = data.certs.filter(c => 
    c.name.toLowerCase().includes(searchQuery.toLowerCase())
  )
  
  return (
    <div className="flex h-screen bg-bg-primary">
      {/* Super Compact Sidebar - Navigation */}
      <div className="w-14 border-r border-border bg-gradient-to-b from-bg-secondary to-bg-tertiary flex flex-col items-center py-3 gap-1">
        {/* Logo */}
        <div className="w-10 h-10 bg-gradient-to-br from-accent-primary to-blue-600 rounded-xl flex items-center justify-center mb-3 shadow-lg shadow-accent-primary/30">
          <ShieldCheck size={20} weight="bold" className="text-white" />
        </div>
        
        {/* Page Icons */}
        {pages.map(page => {
          const Icon = page.icon
          return (
            <button
              key={page.id}
              onClick={() => setActivePage(page.id)}
              className={`w-10 h-10 rounded-lg flex items-center justify-center transition-all relative group ${
                activePage === page.id 
                  ? 'bg-accent-primary text-white shadow-lg shadow-accent-primary/30' 
                  : 'text-text-secondary hover:bg-bg-tertiary hover:text-text-primary'
              }`}
              title={page.label}
            >
              <Icon size={18} weight={activePage === page.id ? 'fill' : 'regular'} />
              {activePage === page.id && (
                <div className="absolute left-0 w-1 h-6 bg-accent-primary rounded-r-full -ml-0.5" />
              )}
              {/* Tooltip */}
              <div className="absolute left-full ml-2 px-2 py-1 bg-bg-tertiary border border-border rounded text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-50">
                {page.label}
              </div>
            </button>
          )
        })}
        
        {/* User Menu at bottom */}
        <div className="mt-auto space-y-2">
          {/* Theme Selector */}
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <button className="w-10 h-10 rounded-lg bg-bg-tertiary border border-border flex items-center justify-center hover:bg-border transition-colors group">
                <Palette size={18} className="text-text-secondary group-hover:text-accent-primary transition-colors" />
              </button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content 
                className="bg-bg-secondary border border-border rounded-xl p-1 shadow-2xl min-w-[200px] z-50"
                sideOffset={5}
                side="right"
              >
                <div className="px-3 py-2 text-xs font-bold text-text-secondary uppercase tracking-wider border-b border-border mb-1">
                  Theme
                </div>
                {Object.values(themes).map(theme => (
                  <DropdownMenu.Item 
                    key={theme.id}
                    onClick={() => setCurrentTheme(theme.id)}
                    className="px-3 py-2 text-sm rounded-lg hover:bg-bg-tertiary outline-none cursor-pointer flex items-center justify-between"
                  >
                    <div className="flex items-center gap-2">
                      <div 
                        className="w-4 h-4 rounded border border-border" 
                        style={{ backgroundColor: theme.colors['accent-primary'] }}
                      />
                      {theme.name}
                    </div>
                    {currentTheme === theme.id && (
                      <Check size={14} weight="bold" className="text-accent-primary" />
                    )}
                  </DropdownMenu.Item>
                ))}
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
          
          {/* User Menu */}
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <button className="w-10 h-10 rounded-lg bg-bg-tertiary border border-border flex items-center justify-center hover:bg-border transition-colors">
                <User size={18} className="text-text-secondary" />
              </button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content 
                className="bg-bg-secondary border border-border rounded-xl p-1 shadow-2xl min-w-[180px] z-50"
                sideOffset={5}
                side="right"
              >
                <DropdownMenu.Item className="px-3 py-2 text-sm rounded-lg hover:bg-bg-tertiary outline-none cursor-pointer flex items-center gap-2">
                  <User size={14} />
                  Account
                </DropdownMenu.Item>
                <DropdownMenu.Item className="px-3 py-2 text-sm rounded-lg hover:bg-bg-tertiary outline-none cursor-pointer flex items-center gap-2">
                  <Gear size={14} />
                  Settings
                </DropdownMenu.Item>
                <DropdownMenu.Separator className="h-px bg-border my-1" />
                <DropdownMenu.Item className="px-3 py-2 text-sm rounded-lg hover:bg-accent-danger/10 text-accent-danger outline-none cursor-pointer flex items-center gap-2">
                  <SignOut size={14} />
                  Sign out
                </DropdownMenu.Item>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
        </div>
      </div>
      
      {/* Explorer Panel with Search */}
      <div className="w-80 border-r border-border bg-gradient-to-b from-bg-secondary to-bg-tertiary flex flex-col">
        {/* Search Bar */}
        <div className="p-3 border-b border-border">
          <div className="relative">
            <MagnifyingGlass size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-secondary" />
            <input 
              placeholder="Search certificates..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-2 bg-bg-tertiary border border-border rounded-lg text-xs focus:outline-none focus:ring-1 focus:ring-accent-primary placeholder:text-text-secondary"
            />
          </div>
        </div>
        
        {/* Page Title */}
        <div className="px-3 py-2 border-b border-border/50">
          <div className="flex items-center gap-2">
            {(() => {
              const Page = pages.find(p => p.id === activePage)
              const Icon = Page?.icon
              return (
                <>
                  {Icon && <Icon size={16} className="text-accent-primary" />}
                  <span className="font-bold text-sm">{Page?.label}</span>
                  <span className="text-xs text-text-secondary ml-auto">{filteredCerts.length}</span>
                </>
              )
            })()}
          </div>
        </div>
        
        {/* Explorer Tree */}
        <div className="flex-1 overflow-y-auto p-2">
          {/* CAs Section */}
          <div className="mb-3">
            <button 
              onClick={() => setExpanded({...expanded, cas: !expanded.cas})}
              className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-text-secondary px-2 py-1.5 hover:bg-bg-tertiary rounded w-full font-bold"
            >
              {expanded.cas ? <CaretDown size={12} weight="bold" /> : <CaretRight size={12} weight="bold" />}
              <ShieldCheck size={12} weight="bold" />
              Authorities ({data.cas.length})
            </button>
            {expanded.cas && data.cas.map(ca => (
              <button
                key={ca.id}
                onClick={() => setSelected(ca.id)}
                className={`w-full text-left px-6 py-1.5 text-xs rounded flex items-center gap-2 transition-all ${
                  selected === ca.id 
                    ? 'bg-accent-primary text-white shadow-md' 
                    : 'hover:bg-bg-tertiary text-text-primary'
                }`}
              >
                <ShieldCheck size={12} weight="fill" />
                <span className="flex-1 truncate">{ca.name}</span>
                <span className="text-[10px] opacity-70">{ca.children}</span>
              </button>
            ))}
          </div>
          
          {/* Certs Section */}
          <div>
            <button 
              onClick={() => setExpanded({...expanded, certs: !expanded.certs})}
              className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-text-secondary px-2 py-1.5 hover:bg-bg-tertiary rounded w-full font-bold"
            >
              {expanded.certs ? <CaretDown size={12} weight="bold" /> : <CaretRight size={12} weight="bold" />}
              <Certificate size={12} weight="bold" />
              Certificates ({filteredCerts.length})
            </button>
            {expanded.certs && filteredCerts.map(cert => (
              <button
                key={cert.id}
                onClick={() => setSelected(cert.id)}
                className={`w-full text-left px-6 py-1.5 text-xs rounded flex items-center gap-2 transition-all ${
                  selected === cert.id 
                    ? 'bg-accent-primary text-white shadow-md' 
                    : 'hover:bg-bg-tertiary text-text-primary'
                }`}
              >
                <Certificate size={12} />
                <span className="flex-1 truncate">{cert.name}</span>
                {cert.status === 'expiring' && (
                  <Clock size={10} className="text-accent-warning" weight="fill" />
                )}
              </button>
            ))}
          </div>
          
          {searchQuery && filteredCerts.length === 0 && (
            <div className="text-xs text-text-secondary text-center py-8">
              No results for "{searchQuery}"
            </div>
          )}
        </div>
        
        {/* Footer Stats */}
        <div className="px-3 py-2 border-t border-border text-[10px] text-text-secondary flex items-center justify-between">
          <span>{filteredCerts.length} items</span>
          <span className="flex items-center gap-1">
            <div className="w-1.5 h-1.5 bg-accent-success rounded-full" />
            Connected
          </span>
        </div>
      </div>
      
      {/* Details Panel */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto p-6">
          {/* Breadcrumb */}
          <div className="flex items-center gap-2 text-xs text-text-secondary mb-4">
            <span className="hover:text-text-primary cursor-pointer">Certificates</span>
            <CaretRight size={10} />
            <span className="text-text-primary font-medium">app.example.com</span>
          </div>
          
          {/* Header */}
          <div className="mb-6">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 bg-gradient-to-br from-accent-primary to-blue-600 rounded-xl flex items-center justify-center shadow-lg shadow-accent-primary/30">
                <Certificate size={20} weight="duotone" className="text-white" />
              </div>
              <div className="flex-1">
                <h2 className="text-2xl font-bold">app.example.com</h2>
                <p className="text-xs text-text-secondary">End-entity certificate</p>
              </div>
              <button className="px-3 py-1.5 bg-bg-tertiary hover:bg-border rounded-lg text-xs transition-colors border border-border">
                Actions
              </button>
            </div>
            <div className="flex gap-2">
              <Badge variant="success">Valid</Badge>
              <Badge variant="info">Active</Badge>
            </div>
          </div>
          
          {/* Quick Info Grid */}
          <div className="grid grid-cols-4 gap-3 mb-6">
            <Card className="p-3">
              <div className="text-[10px] uppercase tracking-wider text-text-secondary mb-1 font-bold">Serial</div>
              <div className="text-xs font-mono">1A:2B:3C:4D</div>
            </Card>
            <Card className="p-3">
              <div className="text-[10px] uppercase tracking-wider text-text-secondary mb-1 font-bold">Expires</div>
              <div className="text-xs font-semibold">2025-12-31</div>
            </Card>
            <Card className="p-3">
              <div className="text-[10px] uppercase tracking-wider text-text-secondary mb-1 font-bold">Algorithm</div>
              <div className="text-xs font-mono">RSA 4096</div>
            </Card>
            <Card className="p-3">
              <div className="text-[10px] uppercase tracking-wider text-text-secondary mb-1 font-bold">Status</div>
              <div className="text-xs font-semibold text-accent-success">Active</div>
            </Card>
          </div>
          
          {/* Detailed Sections */}
          <div className="space-y-4">
            <Card className="p-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-text-secondary mb-3 flex items-center gap-2">
                <Lock size={12} />
                Certificate Chain
              </h3>
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-xs p-2 bg-bg-tertiary/50 rounded-lg border border-border/30">
                  <Certificate size={12} className="text-accent-primary" />
                  <span className="flex-1">app.example.com</span>
                  <span className="text-[10px] text-text-secondary">End Entity</span>
                </div>
                <div className="flex items-center gap-2 text-xs p-2 bg-bg-tertiary/50 rounded-lg border border-border/30">
                  <ShieldCheck size={12} className="text-accent-success" />
                  <span className="flex-1">Intermediate CA</span>
                  <span className="text-[10px] text-text-secondary">Issuer</span>
                </div>
                <div className="flex items-center gap-2 text-xs p-2 bg-bg-tertiary/50 rounded-lg border border-border/30">
                  <ShieldCheck size={12} className="text-accent-success" />
                  <span className="flex-1">Root CA</span>
                  <span className="text-[10px] text-text-secondary">Root</span>
                </div>
              </div>
            </Card>
            
            <Card className="p-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-text-secondary mb-3">Subject Alternative Names</h3>
              <div className="space-y-1.5">
                <div className="text-xs p-2 bg-bg-tertiary/30 rounded font-mono">DNS: *.example.com</div>
                <div className="text-xs p-2 bg-bg-tertiary/30 rounded font-mono">DNS: example.com</div>
                <div className="text-xs p-2 bg-bg-tertiary/30 rounded font-mono">IP: 192.168.1.100</div>
              </div>
            </Card>
          </div>
        </div>
      </div>
    </div>
  )
}
