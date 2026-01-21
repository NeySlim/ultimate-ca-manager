import { Tabs } from '../../components/ui/Tabs';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import styles from './ImportPage.module.css';

/**
 * Import Page
 * 
 * Three tabs for importing:
 * - Certificate Authority
 * - Certificate
 * - OPNsense (special integration)
 */
export function ImportPage() {
  return (
    <div className={styles.importPage}>
      <Tabs>
        <Tabs.List>
          <Tabs.Tab>Import CA</Tabs.Tab>
          <Tabs.Tab>Import Certificate</Tabs.Tab>
          <Tabs.Tab>Import from OPNsense</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panels>
          {/* Import CA Tab */}
          <Tabs.Panel>
            <div className={styles.tabContent}>
              <Card>
                <Card.Header>
                  <h3>Import Certificate Authority</h3>
                </Card.Header>
                <Card.Body>
                  <form className={styles.form}>
                    <Input label="CA Name" placeholder="Enter CA name" />
                    
                    <div className={styles.fileUpload}>
                      <label className={styles.label}>CA Certificate (PEM)</label>
                      <div className={styles.uploadBox}>
                        <i className="ph ph-file-arrow-up" />
                        <span>Drop file here or click to upload</span>
                        <input type="file" accept=".pem,.crt,.cer" />
                      </div>
                    </div>

                    <div className={styles.fileUpload}>
                      <label className={styles.label}>CA Private Key (optional)</label>
                      <div className={styles.uploadBox}>
                        <i className="ph ph-file-arrow-up" />
                        <span>Drop file here or click to upload</span>
                        <input type="file" accept=".pem,.key" />
                      </div>
                    </div>

                    <div className={styles.formActions}>
                      <Button variant="primary" icon="ph ph-upload">Import CA</Button>
                      <Button variant="default">Cancel</Button>
                    </div>
                  </form>
                </Card.Body>
              </Card>
            </div>
          </Tabs.Panel>

          {/* Import Certificate Tab */}
          <Tabs.Panel>
            <div className={styles.tabContent}>
              <Card>
                <Card.Header>
                  <h3>Import Certificate</h3>
                </Card.Header>
                <Card.Body>
                  <form className={styles.form}>
                    <div className={styles.fileUpload}>
                      <label className={styles.label}>Certificate (PEM)</label>
                      <div className={styles.uploadBox}>
                        <i className="ph ph-file-arrow-up" />
                        <span>Drop file here or click to upload</span>
                        <input type="file" accept=".pem,.crt,.cer" />
                      </div>
                    </div>

                    <div className={styles.fileUpload}>
                      <label className={styles.label}>Private Key</label>
                      <div className={styles.uploadBox}>
                        <i className="ph ph-file-arrow-up" />
                        <span>Drop file here or click to upload</span>
                        <input type="file" accept=".pem,.key" />
                      </div>
                    </div>

                    <div className={styles.formActions}>
                      <Button variant="primary" icon="ph ph-upload">Import Certificate</Button>
                      <Button variant="default">Cancel</Button>
                    </div>
                  </form>
                </Card.Body>
              </Card>
            </div>
          </Tabs.Panel>

          {/* Import from OPNsense Tab */}
          <Tabs.Panel>
            <div className={styles.tabContent}>
              <Card>
                <Card.Header>
                  <h3>Import from OPNsense</h3>
                </Card.Header>
                <Card.Body>
                  <form className={styles.form}>
                    <Input label="OPNsense Host" placeholder="https://opnsense.acme.com" />
                    <Input label="API Key" placeholder="Enter API key" />
                    <Input label="API Secret" type="password" placeholder="Enter API secret" />

                    <div className={styles.infoBox}>
                      <i className="ph ph-info" />
                      <div>
                        <div className={styles.infoTitle}>OPNsense Integration</div>
                        <div className={styles.infoText}>
                          This will import all CAs and certificates from your OPNsense firewall.
                          Private keys will be imported if available.
                        </div>
                      </div>
                    </div>

                    <div className={styles.formActions}>
                      <Button variant="primary" icon="ph ph-arrow-square-in">Connect & Import</Button>
                      <Button variant="default">Cancel</Button>
                    </div>
                  </form>
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
