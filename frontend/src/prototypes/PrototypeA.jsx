// PROTOTYPE A: Sidebar + Main Focus (Linear/Notion style)
import { useState } from 'react'
import { Certificate, ShieldCheck, Clock, FileText, CaretRight } from '@phosphor-icons/react'
import { Card } from '../components/Card'
import { Badge } from '../components/Badge'

export default function PrototypeA() {
  const [selected, setSelected] = useState('cert-1')
  
  const items = [
    { id: 'cert-1', name: 'app.example.com', type: 'cert', status: 'valid', expires: '2025-12-31' },
    { id: 'cert-2', name: 'api.example.com', type: 'cert', status: 'expiring', expires: '2025-02-10' },
    { id: 'ca-1', name: 'Root CA', type: 'ca', status: 'valid', expires: '2030-01-01' },
    { id: 'cert-3', name: 'web.example.com', type: 'cert', status: 'valid', expires: '2026-06-15' },
  ]
  
  const selectedItem = items.find(i => i.id === selected)
  
  return (
    <div className="flex h-screen bg-bg-primary">
      {/* Compact Sidebar */}
      <div className="w-64 border-r border-border bg-gradient-to-b from-bg-secondary to-bg-tertiary flex flex-col">
        <div className="p-4 border-b border-border">
          <div className="flex items-center gap-2">
            <ShieldCheck size={20} weight="duotone" className="text-accent-primary" />
            <span className="font-bold text-sm">UCM</span>
          </div>
        </div>
        
        <div className="flex-1 overflow-y-auto p-2">
          <div className="text-xs uppercase tracking-wider text-text-secondary px-2 py-2 font-bold">Objects</div>
          {items.map(item => (
            <button
              key={item.id}
              onClick={() => setSelected(item.id)}
              className={`w-full text-left px-3 py-2 rounded-lg mb-1 text-sm transition-all flex items-center gap-2 ${
                selected === item.id 
                  ? 'bg-accent-primary text-white shadow-lg' 
                  : 'hover:bg-bg-tertiary text-text-secondary'
              }`}
            >
              {item.type === 'ca' ? <ShieldCheck size={14} /> : <Certificate size={14} />}
              <span className="truncate flex-1">{item.name}</span>
              {item.status === 'expiring' && <div className="w-2 h-2 bg-accent-warning rounded-full" />}
            </button>
          ))}
        </div>
        
        <div className="p-3 border-t border-border text-xs text-text-secondary">
          {items.length} objects
        </div>
      </div>
      
      {/* Main Detail Panel */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto p-8">
          <div className="mb-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-12 h-12 bg-gradient-to-br from-accent-primary to-blue-600 rounded-xl flex items-center justify-center">
                {selectedItem?.type === 'ca' ? <ShieldCheck size={24} className="text-white" /> : <Certificate size={24} className="text-white" />}
              </div>
              <div>
                <h1 className="text-3xl font-bold">{selectedItem?.name}</h1>
                <p className="text-text-secondary text-sm">Certificate details</p>
              </div>
            </div>
            <Badge variant={selectedItem?.status}>{selectedItem?.status}</Badge>
          </div>
          
          <div className="grid grid-cols-2 gap-4 mb-6">
            <Card className="p-4">
              <div className="text-xs uppercase tracking-wider text-text-secondary mb-2">Serial Number</div>
              <div className="font-mono text-sm">1A:2B:3C:4D:5E:6F</div>
            </Card>
            <Card className="p-4">
              <div className="text-xs uppercase tracking-wider text-text-secondary mb-2">Expires</div>
              <div className="text-sm font-semibold">{selectedItem?.expires}</div>
            </Card>
            <Card className="p-4">
              <div className="text-xs uppercase tracking-wider text-text-secondary mb-2">Issuer</div>
              <div className="text-sm">Root CA</div>
            </Card>
            <Card className="p-4">
              <div className="text-xs uppercase tracking-wider text-text-secondary mb-2">Key Algorithm</div>
              <div className="text-sm font-mono">RSA 4096</div>
            </Card>
          </div>
          
          <Card className="p-5">
            <h3 className="font-bold mb-4">Subject Alternative Names</h3>
            <div className="space-y-2">
              <div className="text-sm">DNS: *.example.com</div>
              <div className="text-sm">DNS: example.com</div>
              <div className="text-sm">IP: 192.168.1.100</div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
