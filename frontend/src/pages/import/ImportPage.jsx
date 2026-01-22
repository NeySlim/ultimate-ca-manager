import { useState } from 'react';
import { PageTopBar, SectionTabs, Tab } from '../../components/common';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Badge } from '../../components/ui/Badge';
import { DataTable } from '../../components/domain/DataTable';
import { Modal } from '../../components/ui/Modal';
import { useTestOPNsenseConnection, useImportFromOPNsense } from '../../hooks/useOPNsenseImport';
import { Check, Warning } from '@phosphor-icons/react';
import styles from './ImportPage.module.css';

export function ImportPage() {
  const [activeTab, setActiveTab] = useState('ca');
  const [caMethod, setCaMethod] = useState(0);
  const [certMethod, setCertMethod] = useState(0);
  
  // OPNsense state
  const [opnsenseConfig, setOpnsenseConfig] = useState({
    host: '',
    port: '443',
    api_key: '',
    api_secret: '',
    verify_ssl: false
  });
  const [opnsenseItems, setOpnsenseItems] = useState([]);
  const [connectedHost, setConnectedHost] = useState(null);
  const [showImportModal, setShowImportModal] = useState(false);
  const [selectedItems, setSelectedItems] = useState([]);
  
  // Mutations
  const testConnection = useTestOPNsenseConnection();
  const importItems = useImportFromOPNsense();

  const handleTestConnection = async () => {
    try {
      const result = await testConnection.mutateAsync(opnsenseConfig);
      if (result.success) {
        setOpnsenseItems(result.items);
        setConnectedHost(`${opnsenseConfig.host}:${opnsenseConfig.port}`);
        // Select all items by default
        setSelectedItems(result.items.map(item => item.id));
      }
    } catch (error) {
      console.error('Connection test failed:', error);
    }
  };

  const handleImport = async () => {
    try {
      const result = await importItems.mutateAsync({
        ...opnsenseConfig,
        items: selectedItems
      });
      if (result.success) {
        setShowImportModal(false);
        // Clear selection and items
        setSelectedItems([]);
        setOpnsenseItems([]);
        setConnectedHost(null);
      }
    } catch (error) {
      console.error('Import failed:', error);
    }
  };

  const toggleItemSelection = (id) => {
    setSelectedItems(prev =>
      prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
    );
  };

  const opnsenseColumns = [
    {
      key: 'selected',
      label: '',
      render: (row) => (
        <input
          type="checkbox"
          checked={selectedItems.includes(row.id)}
          onChange={() => toggleItemSelection(row.id)}
        />
      ),
    },
    {
      key: 'type',
      label: 'Type',
      render: (row) => (
        <Badge variant={row.type === 'CA' ? 'info' : 'success'}>{row.type}</Badge>
      ),
    },
    { key: 'name', label: 'Name' },
    { key: 'subject', label: 'Subject', render: (row) => <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}>{row.subject}</span> },
    { key: 'validUntil', label: 'Valid Until' },
  ];

  const renderSubMethods = (items, active, onChange) => (
    <div className={styles.subMethods}>
      {items.map((item, idx) => (
        <div
          key={idx}
          className={`${styles.subMethod} ${active === idx ? styles.active : ''}`}
          onClick={() => onChange(idx)}
        >
          <i className={item.icon} />
          <div className={styles.subMethodTitle}>{item.title}</div>
        </div>
      ))}
    </div>
  );

  return (
    <div className={styles.importPage}>
      <PageTopBar
        icon="ph ph-upload"
        title="Import"
        badge={<Badge variant="info">Multiple Formats</Badge>}
        actions={
          <>
            <Button icon="ph ph-question">Help</Button>
            <Button variant="primary" icon="ph ph-upload-simple">Upload Files</Button>
          </>
        }
      />

      <SectionTabs>
        <Tab active={activeTab === 'ca'} onClick={() => setActiveTab('ca')}>
          CA Import
        </Tab>
        <Tab active={activeTab === 'cert'} onClick={() => setActiveTab('cert')}>
          Certificate Import
        </Tab>
        <Tab active={activeTab === 'opnsense'} onClick={() => setActiveTab('opnsense')}>
          OPNsense Import
        </Tab>
      </SectionTabs>

      {activeTab === 'ca' && (
        <div className={styles.tabContent}>
              {renderSubMethods(
                [
                  { icon: 'ph ph-clipboard-text', title: 'Paste PEM' },
                  { icon: 'ph ph-upload', title: 'Upload Files' },
                  { icon: 'ph ph-package', title: 'Container P12/PFX' },
                ],
                caMethod,
                setCaMethod
              )}

              {caMethod === 0 && (
                <Card>
                  <Card.Header><h3>Paste PEM Encoded CA</h3></Card.Header>
                  <Card.Body>
                    <form className={styles.form}>
                      <div className={styles.formGroup}>
                        <label className={styles.formLabel}>CA Certificate (PEM)</label>
                        <textarea
                          className={styles.formTextarea}
                          placeholder="-----BEGIN CERTIFICATE-----&#10;MIIFazCCA1OgAwIBAgIRAIIQz7DSQONZRGPgu2OCiwAwDQYJKoZIhvcNAQELBQAw&#10;...&#10;-----END CERTIFICATE-----"
                        />
                        <div className={styles.formHelp}>Paste the PEM-encoded CA certificate</div>
                      </div>
                      <div className={styles.formGroup}>
                        <label className={styles.formLabel}>Private Key (Optional, PEM)</label>
                        <textarea
                          className={styles.formTextarea}
                          placeholder="-----BEGIN PRIVATE KEY-----&#10;MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7VJ...&#10;-----END PRIVATE KEY-----"
                        />
                        <div className={styles.formHelp}>Only required if this CA will issue certificates</div>
                      </div>
                      <Input label="CA Name" placeholder="My Root CA" />
                      <div className={styles.formCheckbox}>
                        <input type="checkbox" id="ca-trust" />
                        <label htmlFor="ca-trust">Add to Trust Store</label>
                      </div>
                      <Button variant="primary" icon="ph ph-download">Import CA</Button>
                    </form>
                  </Card.Body>
                </Card>
              )}

              {caMethod === 1 && (
                <Card>
                  <Card.Header><h3>Upload CA Files</h3></Card.Header>
                  <Card.Body>
                    <form className={styles.form}>
                      <div className={styles.formGroup}>
                        <label className={styles.formLabel}>CA Certificate File</label>
                        <input type="file" className={styles.formInput} accept=".pem,.crt,.cer" />
                        <div className={styles.formHelp}>Upload PEM or DER encoded certificate</div>
                      </div>
                      <div className={styles.formGroup}>
                        <label className={styles.formLabel}>Private Key File (Optional)</label>
                        <input type="file" className={styles.formInput} accept=".pem,.key" />
                        <div className={styles.formHelp}>Only required if this CA will issue certificates</div>
                      </div>
                      <Input label="CA Name" placeholder="My Root CA" />
                      <div className={styles.formCheckbox}>
                        <input type="checkbox" id="ca-trust-upload" />
                        <label htmlFor="ca-trust-upload">Add to Trust Store</label>
                      </div>
                      <Button variant="primary" icon="ph ph-download">Import CA</Button>
                    </form>
                  </Card.Body>
                </Card>
              )}

              {caMethod === 2 && (
                <Card>
                  <Card.Header><h3>Import from P12/PFX Container</h3></Card.Header>
                  <Card.Body>
                    <form className={styles.form}>
                      <div className={styles.formGroup}>
                        <label className={styles.formLabel}>P12/PFX File</label>
                        <input type="file" className={styles.formInput} accept=".p12,.pfx" />
                        <div className={styles.formHelp}>PKCS#12 container with CA certificate and private key</div>
                      </div>
                      <Input label="Container Password" type="password" placeholder="Enter password" />
                      <Input label="CA Name" placeholder="My Root CA" />
                      <div className={styles.formCheckbox}>
                        <input type="checkbox" id="ca-trust-p12" />
                        <label htmlFor="ca-trust-p12">Add to Trust Store</label>
                      </div>
                      <Button variant="primary" icon="ph ph-download">Import CA</Button>
                    </form>
                  </Card.Body>
                </Card>
              )}
            </div>
      )}

      {activeTab === 'cert' && (
        <div className={styles.tabContent}>
              {renderSubMethods(
                [
                  { icon: 'ph ph-clipboard-text', title: 'Paste PEM' },
                  { icon: 'ph ph-upload', title: 'Upload Files' },
                  { icon: 'ph ph-package', title: 'Container' },
                ],
                certMethod,
                setCertMethod
              )}

              {certMethod === 0 && (
                <Card>
                  <Card.Header><h3>Paste PEM Encoded Certificate</h3></Card.Header>
                  <Card.Body>
                    <form className={styles.form}>
                      <div className={styles.formGroup}>
                        <label className={styles.formLabel}>Certificate (PEM)</label>
                        <textarea className={styles.formTextarea} placeholder="-----BEGIN CERTIFICATE-----&#10;..." />
                      </div>
                      <div className={styles.formGroup}>
                        <label className={styles.formLabel}>Private Key (Optional, PEM)</label>
                        <textarea className={styles.formTextarea} placeholder="-----BEGIN PRIVATE KEY-----&#10;..." />
                      </div>
                      <Input label="Certificate Name" placeholder="server.example.com" />
                      <Button variant="primary" icon="ph ph-download">Import Certificate</Button>
                    </form>
                  </Card.Body>
                </Card>
              )}

              {certMethod === 1 && (
                <Card>
                  <Card.Header><h3>Upload Certificate Files</h3></Card.Header>
                  <Card.Body>
                    <form className={styles.form}>
                      <div className={styles.formGroup}>
                        <label className={styles.formLabel}>Certificate File</label>
                        <input type="file" className={styles.formInput} accept=".pem,.crt,.cer" />
                        <div className={styles.formHelp}>Upload PEM or DER encoded certificate</div>
                      </div>
                      <div className={styles.formGroup}>
                        <label className={styles.formLabel}>Private Key File (Optional)</label>
                        <input type="file" className={styles.formInput} accept=".pem,.key" />
                      </div>
                      <div className={styles.formGroup}>
                        <label className={styles.formLabel}>Certificate Chain (Optional)</label>
                        <input type="file" className={styles.formInput} accept=".pem,.crt" />
                        <div className={styles.formHelp}>Intermediate certificates</div>
                      </div>
                      <Input label="Certificate Name" placeholder="server.example.com" />
                      <Button variant="primary" icon="ph ph-download">Import Certificate</Button>
                    </form>
                  </Card.Body>
                </Card>
              )}

              {certMethod === 2 && (
                <Card>
                  <Card.Header><h3>Import from Container</h3></Card.Header>
                  <Card.Body>
                    <form className={styles.form}>
                      <div className={styles.formGroup}>
                        <label className={styles.formLabel}>P12/PFX File</label>
                        <input type="file" className={styles.formInput} accept=".p12,.pfx" />
                        <div className={styles.formHelp}>PKCS#12 container with certificate and private key</div>
                      </div>
                      <Input label="Container Password" type="password" placeholder="Enter password" />
                      <Input label="Certificate Name" placeholder="server.example.com" />
                      <Button variant="primary" icon="ph ph-download">Import Certificate</Button>
                    </form>
                  </Card.Body>
                </Card>
              )}
            </div>
      )}

      {activeTab === 'opnsense' && (
        <div className={styles.tabContent}>
          <Card>
            <Card.Header><h3>OPNsense Connection</h3></Card.Header>
            <Card.Body>
              <form className={styles.form} onSubmit={(e) => { e.preventDefault(); handleTestConnection(); }}>
                <Input
                  label="Host"
                  placeholder="192.168.1.1"
                  value={opnsenseConfig.host}
                  onChange={(e) => setOpnsenseConfig({ ...opnsenseConfig, host: e.target.value })}
                />
                <Input
                  label="Port"
                  type="number"
                  placeholder="443"
                  value={opnsenseConfig.port}
                  onChange={(e) => setOpnsenseConfig({ ...opnsenseConfig, port: e.target.value })}
                />
                <Input
                  label="API Key"
                  placeholder="Enter API key"
                  value={opnsenseConfig.api_key}
                  onChange={(e) => setOpnsenseConfig({ ...opnsenseConfig, api_key: e.target.value })}
                />
                <Input
                  label="API Secret"
                  type="password"
                  placeholder="Enter API secret"
                  value={opnsenseConfig.api_secret}
                  onChange={(e) => setOpnsenseConfig({ ...opnsenseConfig, api_secret: e.target.value })}
                />
                <div className={styles.formCheckbox}>
                  <input
                    type="checkbox"
                    id="verify-ssl"
                    checked={opnsenseConfig.verify_ssl}
                    onChange={(e) => setOpnsenseConfig({ ...opnsenseConfig, verify_ssl: e.target.checked })}
                  />
                  <label htmlFor="verify-ssl">Verify SSL Certificate</label>
                </div>
                
                <Button
                  type="submit"
                  variant="primary"
                  icon="ph ph-plug"
                  disabled={testConnection.isPending}
                >
                  {testConnection.isPending ? 'Testing...' : 'Test Connection'}
                </Button>
                
                {testConnection.isError && (
                  <div style={{ color: 'var(--status-danger)', fontSize: '13px', marginTop: '8px' }}>
                    <Warning size={16} /> {testConnection.error?.response?.data?.error || 'Connection failed'}
                  </div>
                )}
                
                {testConnection.isSuccess && testConnection.data?.success && (
                  <div style={{ color: 'var(--status-success)', fontSize: '13px', marginTop: '8px' }}>
                    <Check size={16} /> Connected! Found {testConnection.data.stats.cas} CAs and {testConnection.data.stats.certificates} certificates
                  </div>
                )}
              </form>
            </Card.Body>
          </Card>

          {opnsenseItems.length > 0 && (
            <Card>
              <Card.Header>
                <h3>Available Items</h3>
                <div style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>
                  Connected to {connectedHost} • {selectedItems.length} of {opnsenseItems.length} selected
                </div>
              </Card.Header>
              <Card.Body>
                <DataTable
                  columns={opnsenseColumns}
                  data={opnsenseItems}
                  pageSize={10}
                />
                <div style={{ marginTop: '16px', display: 'flex', gap: '8px' }}>
                  <Button
                    variant="primary"
                    icon="ph ph-download-simple"
                    disabled={selectedItems.length === 0}
                    onClick={() => setShowImportModal(true)}
                  >
                    Import Selected ({selectedItems.length})
                  </Button>
                  <Button
                    onClick={() => setSelectedItems(opnsenseItems.map(i => i.id))}
                  >
                    Select All
                  </Button>
                  <Button
                    onClick={() => setSelectedItems([])}
                  >
                    Deselect All
                  </Button>
                </div>
              </Card.Body>
            </Card>
          )}
        </div>
      )}

      {/* Import Confirmation Modal */}
      <Modal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        title="Confirm Import"
        footer={
          <>
            <Button onClick={() => setShowImportModal(false)}>Cancel</Button>
            <Button
              variant="primary"
              onClick={handleImport}
              disabled={importItems.isPending}
            >
              {importItems.isPending ? 'Importing...' : `Import ${selectedItems.length} Items`}
            </Button>
          </>
        }
      >
        <p>You are about to import {selectedItems.length} items from OPNsense ({connectedHost}):</p>
        <ul style={{ marginTop: '12px', paddingLeft: '20px' }}>
          {opnsenseItems.filter(item => selectedItems.includes(item.id)).map(item => (
            <li key={item.id} style={{ marginBottom: '4px' }}>
              <Badge variant={item.type === 'CA' ? 'info' : 'success'}>{item.type}</Badge> {item.name}
            </li>
          ))}
        </ul>
        <p style={{ marginTop: '12px', color: 'var(--text-tertiary)', fontSize: '12px' }}>
          This action will add these items to your UCM trust store.
        </p>
      </Modal>
    </div>
  );
}

export default ImportPage;
