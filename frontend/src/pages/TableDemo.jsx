/**
 * Table Demo - Showcase DataTable capabilities
 */
import { useState } from 'react'
import { Certificate, User, Trash, PencilSimple, Download, Eye } from '@phosphor-icons/react'
import { DataTable, SimpleTable, Badge, Button } from '../components'

// Mock data
const mockCertificates = Array.from({ length: 47 }, (_, i) => ({
  id: i + 1,
  common_name: `cert-${i + 1}.example.com`,
  issuer: i % 3 === 0 ? 'Root CA' : 'Intermediate CA',
  status: ['valid', 'valid', 'valid', 'expiring', 'expired'][i % 5],
  valid_from: new Date(2024, 0, 1 + i).toISOString(),
  valid_to: new Date(2025, 0, 1 + i * 30).toISOString(),
  key_type: i % 2 === 0 ? 'RSA 2048' : 'EC P-256',
  serial: `${Math.random().toString(16).slice(2, 10)}...`
}))

export default function TableDemo() {
  const [selected, setSelected] = useState([])
  
  const columns = [
    { 
      key: 'common_name', 
      header: 'Common Name',
      render: (val) => (
        <div className="flex items-center gap-2">
          <Certificate size={16} className="text-accent-primary" />
          <span className="font-medium">{val}</span>
        </div>
      )
    },
    { key: 'issuer', header: 'Issuer' },
    { 
      key: 'status', 
      header: 'Status',
      render: (val) => (
        <Badge variant={val === 'valid' ? 'success' : val === 'expiring' ? 'warning' : 'danger'}>
          {val}
        </Badge>
      )
    },
    { 
      key: 'valid_to', 
      header: 'Expires',
      sortType: 'date',
      render: (val) => new Date(val).toLocaleDateString()
    },
    { key: 'key_type', header: 'Key Type' },
    { key: 'serial', header: 'Serial', visible: false }
  ]
  
  const rowActions = (row) => [
    { label: 'View', icon: Eye, onClick: () => alert(`View ${row.common_name}`) },
    { label: 'Download', icon: Download, onClick: () => alert(`Download ${row.common_name}`) },
    { label: 'Edit', icon: PencilSimple, onClick: () => alert(`Edit ${row.common_name}`) },
    { label: 'Delete', icon: Trash, variant: 'danger', onClick: () => alert(`Delete ${row.common_name}`) },
  ]
  
  return (
    <div className="h-full flex flex-col">
      <div className="p-6 border-b border-border bg-bg-secondary">
        <h1 className="text-xl font-bold text-text-primary">DataTable Demo</h1>
        <p className="text-sm text-text-secondary mt-1">
          Powerful table with pagination, search, sorting, column management, row selection
        </p>
      </div>
      
      <div className="flex-1 overflow-hidden">
        <DataTable
          data={mockCertificates}
          columns={columns}
          selectable
          multiSelect
          selectedRows={selected}
          onSelectionChange={setSelected}
          searchable
          searchPlaceholder="Search certificates..."
          searchKeys={['common_name', 'issuer']}
          sortable
          defaultSort={{ key: 'common_name', direction: 'asc' }}
          columnToggle
          paginated
          pageSize={10}
          pageSizeOptions={[10, 25, 50]}
          variant="default"
          rowActions={rowActions}
          onRowClick={(row) => console.log('Clicked:', row)}
          emptyIcon={Certificate}
          emptyTitle="No certificates"
          emptyDescription="No certificates match your search"
        />
      </div>
    </div>
  )
}
