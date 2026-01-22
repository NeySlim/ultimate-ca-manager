import { Modal } from '../ui/Modal';
import { Badge } from '../ui/Badge';

export function ViewCertificateModal({ isOpen, onClose, certificate }) {
  if (!certificate) return null;

  const formatDate = (dateStr) => {
    if (!dateStr) return 'N/A';
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  const isExpired = certificate.validUntil && new Date(certificate.validUntil) < new Date();
  const isExpiringSoon = certificate.validUntil && 
    new Date(certificate.validUntil) < new Date(Date.now() + 30 * 24 * 60 * 60 * 1000);

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="large">
      <Modal.Header>
        <i className="ph ph-certificate" style={{ marginRight: '8px' }} />
        Certificate Details
      </Modal.Header>

      <Modal.Body>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* General Information */}
          <div>
            <h3 style={{ 
              fontSize: '14px', 
              fontWeight: 600, 
              color: 'var(--text-primary)', 
              marginBottom: '12px' 
            }}>
              General Information
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: '140px 1fr', gap: '12px' }}>
              <div style={{ fontSize: '13px', color: 'var(--text-tertiary)' }}>Name:</div>
              <div style={{ fontSize: '13px', color: 'var(--text-primary)', fontWeight: 500 }}>
                {certificate.name}
              </div>

              <div style={{ fontSize: '13px', color: 'var(--text-tertiary)' }}>Subject:</div>
              <div style={{ fontSize: '13px', color: 'var(--text-primary)', fontFamily: 'JetBrains Mono, monospace' }}>
                {certificate.subject}
              </div>

              <div style={{ fontSize: '13px', color: 'var(--text-tertiary)' }}>Valid Until:</div>
              <div style={{ fontSize: '13px', color: 'var(--text-primary)' }}>
                {formatDate(certificate.validUntil)}
                {isExpired && (
                  <Badge variant="danger" style={{ marginLeft: '8px' }}>Expired</Badge>
                )}
                {!isExpired && isExpiringSoon && (
                  <Badge variant="warning" style={{ marginLeft: '8px' }}>Expiring Soon</Badge>
                )}
              </div>

              <div style={{ fontSize: '13px', color: 'var(--text-tertiary)' }}>Usage:</div>
              <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                {certificate.usage?.map((u, idx) => (
                  <Badge key={idx} variant="info">{u}</Badge>
                ))}
              </div>

              <div style={{ fontSize: '13px', color: 'var(--text-tertiary)' }}>Auto-Trusted:</div>
              <div style={{ fontSize: '13px', color: 'var(--text-primary)' }}>
                {certificate.autoTrusted ? 'Yes' : 'No'}
              </div>
            </div>
          </div>

          {/* Fingerprints */}
          <div>
            <h3 style={{ 
              fontSize: '14px', 
              fontWeight: 600, 
              color: 'var(--text-primary)', 
              marginBottom: '12px' 
            }}>
              Fingerprints
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: '140px 1fr', gap: '12px' }}>
              <div style={{ fontSize: '13px', color: 'var(--text-tertiary)' }}>SHA-256:</div>
              <div style={{ 
                fontSize: '11px', 
                color: 'var(--text-primary)', 
                fontFamily: 'JetBrains Mono, monospace',
                wordBreak: 'break-all'
              }}>
                {certificate.fingerprint}
              </div>
            </div>
          </div>
        </div>
      </Modal.Body>

      <Modal.Footer>
        <Modal.CloseButton onClick={onClose}>Close</Modal.CloseButton>
      </Modal.Footer>
    </Modal>
  );
}
