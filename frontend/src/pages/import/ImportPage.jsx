import { useState } from 'react';
import { Tabs } from '../../components/ui/Tabs';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Badge } from '../../components/ui/Badge';
import { DataTable } from '../../components/domain/DataTable';
import styles from './ImportPage.module.css';

export function ImportPage() {
  const [caMethod, setCaMethod] = useState(0);
  const [certMethod, setCertMethod] = useState(0);

  const opnsenseItems = [
    { id: 1, type: 'CA', name: 'Root CA', subject: 'CN=Root CA', validUntil: '2034-02-15' },
    { id: 2, type: 'Certificate', name: 'Web GUI', subject: 'CN=opnsense.local', validUntil: '2025-03-01' },
    { id: 3, type: 'Certificate', name: 'VPN Server', subject: 'CN=vpn.acme.com', validUntil: '2025-06-12' },
  ];

  const opnsenseColumns = [
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
      <Tabs>
        <Tabs.List>
          <Tabs.Tab>CA Import</Tabs.Tab>
          <Tabs.Tab>Certificate Import</Tabs.Tab>
          <Tabs.Tab>OPNsense Import</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panels>
          {/* Tab 1: CA Import */}
          <Tabs.Panel>
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
          </Tabs.Panel>

          {/* Tab 2: Certificate Import */}
          <Tabs.Panel>
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
          </Tabs.Panel>

          {/* Tab 3: OPNsense Import */}
          <Tabs.Panel>
            <div className={styles.tabContent}>
              <Card>
                <Card.Header><h3>OPNsense Connection</h3></Card.Header>
                <Card.Body>
                  <form className={styles.form}>
                    <Input label="Host" placeholder="opnsense.local" defaultValue="192.168.1.1" />
                    <Input label="Port" type="number" placeholder="443" defaultValue="443" />
                    <Input label="API Key" placeholder="Enter API key" />
                    <Input label="API Secret" type="password" placeholder="Enter API secret" />
                    <div className={styles.formCheckbox}>
                      <input type="checkbox" id="verify-ssl" defaultChecked />
                      <label htmlFor="verify-ssl">Verify SSL Certificate</label>
                    </div>
                    <Button variant="primary" icon="ph ph-plug">Connect</Button>
                  </form>
                </Card.Body>
              </Card>

              <Card>
                <Card.Header>
                  <h3>Available Items</h3>
                  <div style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>Connected to 192.168.1.1</div>
                </Card.Header>
                <Card.Body>
                  <DataTable
                    columns={opnsenseColumns}
                    data={opnsenseItems}
                    onRowClick={(row) => console.log('Item:', row)}
                    pageSize={10}
                  />
                </Card.Body>
              </Card>
            </div>
          </Tabs.Panel>
        </Tabs.Panels>
      </Tabs>
    </div>
  );
}

export default ImportPage;
