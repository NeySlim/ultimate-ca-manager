/**
 * Test Page - Phase 1 Components Test
 */
import { useState } from 'react'
import { ThemeProvider } from './contexts/ThemeContext'
import { AuthProvider } from './contexts/AuthContext'
import { NotificationProvider, useNotification } from './contexts/NotificationContext'
import { AppShell } from './components/AppShell'
import { ExplorerPanel } from './components/ExplorerPanel'
import { DetailsPanel } from './components/DetailsPanel'
import { Table } from './components/Table'
import { TreeView } from './components/TreeView'
import { Card } from './components/Card'
import { Button } from './components/Button'
import { Badge } from './components/Badge'
import { Input } from './components/Input'
import { Modal } from './components/Modal'
import { StatusIndicator } from './components/StatusIndicator'
import { TabsComponent } from './components/Tabs'
import { ShieldCheck, Certificate, Key } from '@phosphor-icons/react'

function TestPageContent() {
  const { showSuccess, showError, showWarning, showInfo } = useNotification()
  const [showModal, setShowModal] = useState(false)
  const [searchValue, setSearchValue] = useState('')

  // Test data
  const tableData = [
    { id: 1, name: 'app.example.com', status: 'valid', expires: '2025-12-31', issuer: 'Root CA' },
    { id: 2, name: 'api.example.com', status: 'expiring', expires: '2025-02-10', issuer: 'Int CA' },
    { id: 3, name: 'web.example.com', status: 'valid', expires: '2026-06-15', issuer: 'Root CA' },
  ]

  const tableColumns = [
    { key: 'name', label: 'Common Name' },
    { key: 'status', label: 'Status', render: (val) => (
      <div className="flex items-center gap-2">
        <StatusIndicator status={val} />
        <Badge variant={val === 'valid' ? 'success' : 'warning'}>{val}</Badge>
      </div>
    )},
    { key: 'expires', label: 'Expires' },
    { key: 'issuer', label: 'Issuer' },
  ]

  const treeData = [
    {
      id: 'ca-1',
      name: 'Root CA',
      icon: <ShieldCheck size={16} weight="duotone" className="text-blue-500" />,
      badge: '2',
      children: [
        {
          id: 'ca-2',
          name: 'Intermediate CA',
          icon: <Certificate size={16} weight="duotone" className="text-green-500" />,
          badge: '3',
          children: [
            {
              id: 'ca-3',
              name: 'Sub CA',
              icon: <Key size={16} weight="duotone" className="text-orange-500" />,
            }
          ]
        }
      ]
    }
  ]

  const tabs = [
    { 
      id: 'overview', 
      label: 'Overview', 
      icon: <ShieldCheck size={16} />,
      content: (
        <div className="space-y-4">
          <Card>
            <h3 className="font-semibold text-text-primary mb-2">System Stats</h3>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <p className="text-xs text-text-secondary">Total CAs</p>
                <p className="text-2xl font-bold text-text-primary">12</p>
              </div>
              <div>
                <p className="text-xs text-text-secondary">Certificates</p>
                <p className="text-2xl font-bold text-text-primary">247</p>
              </div>
              <div>
                <p className="text-xs text-text-secondary">Expiring Soon</p>
                <p className="text-2xl font-bold text-orange-500">8</p>
              </div>
            </div>
          </Card>
        </div>
      )
    },
    { 
      id: 'table', 
      label: 'Certificates Table', 
      icon: <Certificate size={16} />,
      content: (
        <Table
          columns={tableColumns}
          data={tableData.filter(d => d.name.toLowerCase().includes(searchValue.toLowerCase()))}
          onRowClick={(row) => showInfo(`Clicked: ${row.name}`)}
          selectable
        />
      )
    },
    { 
      id: 'tree', 
      label: 'CAs Tree', 
      icon: <Key size={16} />,
      content: <TreeView nodes={treeData} onSelect={(node) => showInfo(`Selected: ${node.name}`)} />
    },
  ]

  return (
    <AppShell>
      {({ activePage }) => (
        <>
          <ExplorerPanel
            title="Certificates"
            searchable
            searchValue={searchValue}
            onSearch={setSearchValue}
            footer={
              <div className="text-xs text-text-secondary">
                {tableData.length} total certificates
              </div>
            }
          >
            <div className="p-4">
              <TreeView nodes={treeData} onSelect={(node) => showSuccess(`Selected: ${node.name}`)} />
            </div>
          </ExplorerPanel>

          <DetailsPanel
            breadcrumb={[
              { label: 'Home', onClick: () => showInfo('Home clicked') },
              { label: 'Certificates', onClick: () => showInfo('Certs clicked') },
              { label: 'app.example.com' },
            ]}
            title="Phase 1 Component Test"
            actions={
              <>
                <Button variant="secondary" onClick={() => setShowModal(true)}>
                  Open Modal
                </Button>
                <Button onClick={() => showSuccess('Success test!')}>
                  Test Success
                </Button>
              </>
            }
          >
            <div className="space-y-6">
              {/* Notifications Test */}
              <Card>
                <h3 className="font-semibold text-text-primary mb-4">Notification Tests</h3>
                <div className="flex gap-2">
                  <Button onClick={() => showSuccess('Success!')} variant="primary" size="sm">
                    Success
                  </Button>
                  <Button onClick={() => showError('Error!')} variant="danger" size="sm">
                    Error
                  </Button>
                  <Button onClick={() => showWarning('Warning!')} variant="secondary" size="sm">
                    Warning
                  </Button>
                  <Button onClick={() => showInfo('Info!')} variant="ghost" size="sm">
                    Info
                  </Button>
                </div>
              </Card>

              {/* Form Inputs Test */}
              <Card>
                <h3 className="font-semibold text-text-primary mb-4">Form Inputs</h3>
                <div className="space-y-3">
                  <Input label="Email" type="email" placeholder="email@example.com" />
                  <Input label="Password" type="password" error="Password is required" />
                  <Input label="Disabled" disabled value="Disabled input" />
                </div>
              </Card>

              {/* Tabs Test */}
              <TabsComponent tabs={tabs} defaultTab="overview" />
            </div>
          </DetailsPanel>

          {/* Test Modal */}
          <Modal
            open={showModal}
            onClose={() => setShowModal(false)}
            title="Test Modal"
            size="md"
          >
            <div className="space-y-4">
              <p className="text-text-primary">This is a test modal with all components!</p>
              <Input label="Test Input" placeholder="Type something..." />
              <div className="flex gap-2">
                <Button onClick={() => {
                  showSuccess('Modal action successful!')
                  setShowModal(false)
                }}>
                  Submit
                </Button>
                <Button variant="ghost" onClick={() => setShowModal(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          </Modal>
        </>
      )}
    </AppShell>
  )
}

export default function TestPage() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <NotificationProvider>
          <TestPageContent />
        </NotificationProvider>
      </AuthProvider>
    </ThemeProvider>
  )
}
