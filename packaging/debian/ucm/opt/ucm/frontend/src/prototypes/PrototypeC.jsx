// PROTOTYPE C: Split View (VS Code Explorer style)
import { useState } from 'react'
import { Certificate, ShieldCheck, CaretRight, CaretDown } from '@phosphor-icons/react'
import { Card } from '../components/Card'
import { Badge } from '../components/Badge'

export default function PrototypeC() {
  const [selected, setSelected] = useState('cert-1')
  const [expanded, setExpanded] = useState({ certs: true, cas: true })
  
  const data = {
    cas: [
      { id: 'ca-1', name: 'Root CA', children: 2 },
      { id: 'ca-2', name: 'Intermediate CA', children: 3 },
    ],
    certs: [
      { id: 'cert-1', name: 'app.example.com', status: 'valid', expires: '2025-12-31' },
      { id: 'cert-2', name: 'api.example.com', status: 'expiring', expires: '2025-02-10' },
      { id: 'cert-3', name: 'web.example.com', status: 'valid', expires: '2026-06-15' },
    ]
  }
  
  return (
    <div className="flex h-screen bg-bg-primary">
      {/* Compact List */}
      <div className="w-80 border-r border-border bg-gradient-to-b from-bg-secondary to-bg-tertiary overflow-y-auto">
        <div className="p-3 border-b border-border">
          <input 
            placeholder="Search..." 
            className="w-full px-3 py-1.5 bg-bg-tertiary border border-border rounded-lg text-xs focus:outline-none focus:ring-1 focus:ring-accent-primary"
          />
        </div>
        
        <div className="p-2">
          {/* CAs Section */}
          <div>
            <button 
              onClick={() => setExpanded({...expanded, cas: !expanded.cas})}
              className="flex items-center gap-1 text-xs uppercase tracking-wider text-text-secondary px-2 py-1.5 hover:bg-bg-tertiary rounded w-full"
            >
              {expanded.cas ? <CaretDown size={12} /> : <CaretRight size={12} />}
              <ShieldCheck size={12} />
              Certificate Authorities ({data.cas.length})
            </button>
            {expanded.cas && data.cas.map(ca => (
              <button
                key={ca.id}
                onClick={() => setSelected(ca.id)}
                className={`w-full text-left px-6 py-1.5 text-xs rounded flex items-center gap-2 ${
                  selected === ca.id ? 'bg-accent-primary text-white' : 'hover:bg-bg-tertiary text-text-primary'
                }`}
              >
                <ShieldCheck size={12} weight="fill" />
                {ca.name}
                <span className="ml-auto text-[10px] opacity-70">{ca.children}</span>
              </button>
            ))}
          </div>
          
          {/* Certs Section */}
          <div className="mt-3">
            <button 
              onClick={() => setExpanded({...expanded, certs: !expanded.certs})}
              className="flex items-center gap-1 text-xs uppercase tracking-wider text-text-secondary px-2 py-1.5 hover:bg-bg-tertiary rounded w-full"
            >
              {expanded.certs ? <CaretDown size={12} /> : <CaretRight size={12} />}
              <Certificate size={12} />
              Certificates ({data.certs.length})
            </button>
            {expanded.certs && data.certs.map(cert => (
              <button
                key={cert.id}
                onClick={() => setSelected(cert.id)}
                className={`w-full text-left px-6 py-1.5 text-xs rounded flex items-center gap-2 ${
                  selected === cert.id ? 'bg-accent-primary text-white' : 'hover:bg-bg-tertiary text-text-primary'
                }`}
              >
                <Certificate size={12} />
                <span className="truncate">{cert.name}</span>
                {cert.status === 'expiring' && <div className="w-1.5 h-1.5 bg-accent-warning rounded-full ml-auto" />}
              </button>
            ))}
          </div>
        </div>
      </div>
      
      {/* Details Panel */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-3xl">
          <div className="mb-6">
            <div className="flex items-center gap-2 mb-3">
              <Certificate size={16} className="text-accent-primary" />
              <h2 className="text-2xl font-bold">app.example.com</h2>
            </div>
            <div className="flex gap-2">
              <Badge variant="success">Valid</Badge>
              <Badge variant="info">Active</Badge>
            </div>
          </div>
          
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-3">
              <Card className="p-3">
                <div className="text-[10px] uppercase tracking-wider text-text-secondary mb-1">Serial</div>
                <div className="text-xs font-mono">1A:2B:3C:4D</div>
              </Card>
              <Card className="p-3">
                <div className="text-[10px] uppercase tracking-wider text-text-secondary mb-1">Expires</div>
                <div className="text-xs font-semibold">2025-12-31</div>
              </Card>
              <Card className="p-3">
                <div className="text-[10px] uppercase tracking-wider text-text-secondary mb-1">Algorithm</div>
                <div className="text-xs font-mono">RSA 4096</div>
              </Card>
            </div>
            
            <Card className="p-4">
              <div className="text-xs font-bold uppercase tracking-wider text-text-secondary mb-3">Certificate Chain</div>
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-xs p-2 bg-bg-tertiary/30 rounded">
                  <Certificate size={12} className="text-accent-primary" />
                  app.example.com (End Entity)
                </div>
                <div className="flex items-center gap-2 text-xs p-2 bg-bg-tertiary/30 rounded">
                  <ShieldCheck size={12} className="text-accent-success" />
                  Intermediate CA
                </div>
                <div className="flex items-center gap-2 text-xs p-2 bg-bg-tertiary/30 rounded">
                  <ShieldCheck size={12} className="text-accent-success" />
                  Root CA
                </div>
              </div>
            </Card>
          </div>
        </div>
      </div>
    </div>
  )
}
