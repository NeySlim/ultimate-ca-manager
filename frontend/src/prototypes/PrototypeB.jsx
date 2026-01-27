// PROTOTYPE B: Ultra-Dense Grid (Airtable style)
import { Certificate, ShieldCheck, Clock, Eye } from '@phosphor-icons/react'
import { Badge } from '../components/Badge'

export default function PrototypeB() {
  const rows = [
    { name: 'app.example.com', serial: '1A:2B:3C', issuer: 'Root CA', status: 'valid', expires: '2025-12-31', algo: 'RSA 4096' },
    { name: 'api.example.com', serial: '2B:3C:4D', issuer: 'Int CA', status: 'expiring', expires: '2025-02-10', algo: 'ECDSA P-256' },
    { name: 'web.example.com', serial: '3C:4D:5E', issuer: 'Root CA', status: 'valid', expires: '2026-06-15', algo: 'RSA 2048' },
    { name: 'mail.example.com', serial: '4D:5E:6F', issuer: 'Int CA', status: 'valid', expires: '2025-08-20', algo: 'RSA 4096' },
    { name: 'vpn.example.com', serial: '5E:6F:7A', issuer: 'Root CA', status: 'valid', expires: '2027-01-15', algo: 'ECDSA P-384' },
  ]
  
  return (
    <div className="min-h-screen bg-bg-primary p-4">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-bold flex items-center gap-2">
          <Certificate size={20} className="text-accent-primary" />
          Certificates
          <span className="text-sm text-text-secondary font-normal">({rows.length})</span>
        </h1>
      </div>
      
      <div className="bg-gradient-to-br from-bg-secondary to-bg-tertiary border border-border/50 rounded-xl overflow-hidden">
        <table className="w-full">
          <thead className="bg-bg-tertiary/50 sticky top-0">
            <tr className="border-b border-border">
              <th className="px-2 py-1.5 text-left text-[10px] font-bold uppercase tracking-wider text-text-secondary w-[200px]">Name</th>
              <th className="px-2 py-1.5 text-left text-[10px] font-bold uppercase tracking-wider text-text-secondary w-[100px]">Serial</th>
              <th className="px-2 py-1.5 text-left text-[10px] font-bold uppercase tracking-wider text-text-secondary w-[120px]">Issuer</th>
              <th className="px-2 py-1.5 text-left text-[10px] font-bold uppercase tracking-wider text-text-secondary w-[90px]">Status</th>
              <th className="px-2 py-1.5 text-left text-[10px] font-bold uppercase tracking-wider text-text-secondary w-[100px]">Expires</th>
              <th className="px-2 py-1.5 text-left text-[10px] font-bold uppercase tracking-wider text-text-secondary w-[110px]">Algorithm</th>
              <th className="px-2 py-1.5 w-[40px]"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-b border-border/30 hover:bg-accent-primary/5 group transition-colors">
                <td className="px-2 py-2 text-xs font-semibold">{row.name}</td>
                <td className="px-2 py-2 text-[11px] font-mono text-text-secondary">{row.serial}</td>
                <td className="px-2 py-2 text-xs text-text-secondary">{row.issuer}</td>
                <td className="px-2 py-2"><Badge variant={row.status} className="text-[10px] px-2 py-0.5">{row.status}</Badge></td>
                <td className="px-2 py-2 text-xs text-text-secondary">{row.expires}</td>
                <td className="px-2 py-2 text-[11px] font-mono text-text-secondary">{row.algo}</td>
                <td className="px-2 py-2">
                  <button className="opacity-0 group-hover:opacity-100 transition-opacity text-accent-primary hover:text-accent-primary/80">
                    <Eye size={14} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      
      <div className="mt-3 text-xs text-text-secondary">
        Showing {rows.length} certificates
      </div>
    </div>
  )
}
