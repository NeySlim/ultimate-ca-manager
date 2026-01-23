import { Modal } from '../ui/Modal';
import { Badge } from '../ui/Badge';
import { getBadgeVariant } from '../../utils/getBadgeVariant';
import styles from './ViewCADetailsModal.module.css';

export function ViewCADetailsModal({ isOpen, onClose, ca }) {
  if (!ca) return null;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="CA Details"
      size="large"
    >
      <div className={styles.container}>
        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>Basic Information</h3>
          <div className={styles.grid}>
            <div className={styles.field}>
              <label>Common Name</label>
              <div className={styles.value}>{ca.name || ca.commonName}</div>
            </div>
            <div className={styles.field}>
              <label>Type</label>
              <Badge variant={getBadgeVariant('ca-type', ca.type)}>{ca.type}</Badge>
            </div>
            <div className={styles.field}>
              <label>Status</label>
              <Badge variant={getBadgeVariant('ca-status', ca.status || ca.crlStatus)}>
                {ca.status || ca.crlStatus}
              </Badge>
            </div>
            {ca.issuer && (
              <div className={styles.field}>
                <label>Issuer</label>
                <div className={styles.value}>{ca.issuer}</div>
              </div>
            )}
          </div>
        </div>

        {ca.validFrom && (
          <div className={styles.section}>
            <h3 className={styles.sectionTitle}>Validity</h3>
            <div className={styles.grid}>
              <div className={styles.field}>
                <label>Valid From</label>
                <div className={styles.value}>{ca.validFrom}</div>
              </div>
              <div className={styles.field}>
                <label>Valid Until</label>
                <div className={styles.value}>{ca.validUntil}</div>
              </div>
            </div>
          </div>
        )}

        {(ca.fingerprint || ca.serialNumber) && (
          <div className={styles.section}>
            <h3 className={styles.sectionTitle}>Identification</h3>
            <div className={styles.grid}>
              {ca.serialNumber && (
                <div className={styles.field}>
                  <label>Serial Number</label>
                  <div className={styles.mono}>{ca.serialNumber}</div>
                </div>
              )}
              {ca.fingerprint && (
                <div className={styles.field}>
                  <label>Fingerprint (SHA-256)</label>
                  <div className={styles.mono}>{ca.fingerprint}</div>
                </div>
              )}
            </div>
          </div>
        )}

        {(ca.ocspStatus || ca.lastGenerated || ca.nextUpdate) && (
          <div className={styles.section}>
            <h3 className={styles.sectionTitle}>CRL/OCSP Information</h3>
            <div className={styles.grid}>
              {ca.lastGenerated && (
                <div className={styles.field}>
                  <label>Last Generated</label>
                  <div className={styles.value}>{ca.lastGenerated}</div>
                </div>
              )}
              {ca.nextUpdate && (
                <div className={styles.field}>
                  <label>Next Update</label>
                  <div className={styles.value}>{ca.nextUpdate}</div>
                </div>
              )}
              {ca.ocspStatus && (
                <div className={styles.field}>
                  <label>OCSP Status</label>
                  <Badge variant={getBadgeVariant('ocsp-status', ca.ocspStatus)}>
                    {ca.ocspStatus}
                  </Badge>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
