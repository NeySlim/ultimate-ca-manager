import { useState } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import toast from 'react-hot-toast';
import { useAddTrustedCert } from '../../hooks/useTrustStore';

export function AddCAToTrustStoreModal({ isOpen, onClose }) {
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    certificatePem: '',
    purpose: 'root_ca',
    notes: '',
  });

  const addCert = useAddTrustedCert();

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!formData.name || !formData.certificatePem) {
      toast.error('Name and certificate PEM are required');
      return;
    }

    if (!formData.certificatePem.includes('BEGIN CERTIFICATE')) {
      toast.error('Invalid certificate format. Expected PEM format.');
      return;
    }

    addCert.mutate({
      name: formData.name,
      description: formData.description,
      certificate_pem: formData.certificatePem,
      purpose: formData.purpose,
      notes: formData.notes,
    }, {
      onSuccess: () => {
        setFormData({
          name: '',
          description: '',
          certificatePem: '',
          purpose: 'root_ca',
          notes: '',
        });
        onClose();
      },
    });
  };

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (evt) => {
        setFormData({ ...formData, certificatePem: evt.target.result });
      };
      reader.readAsText(file);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="medium">
      <Modal.Header>
        <i className="ph ph-plus" style={{ marginRight: '8px' }} />
        Add CA to Trust Store
      </Modal.Header>

      <form onSubmit={handleSubmit}>
        <Modal.Body>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {/* Name */}
            <div>
              <label style={{ 
                display: 'block', 
                fontSize: '13px', 
                fontWeight: 500, 
                color: 'var(--text-primary)', 
                marginBottom: '6px' 
              }}>
                Name <span style={{ color: 'var(--status-danger)' }}>*</span>
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="e.g., DigiCert Global Root CA"
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  fontSize: '13px',
                  border: '1px solid var(--border-primary)',
                  borderRadius: 'var(--radius)',
                  background: 'var(--bg-primary)',
                  color: 'var(--text-primary)',
                }}
              />
            </div>

            {/* Description */}
            <div>
              <label style={{ 
                display: 'block', 
                fontSize: '13px', 
                fontWeight: 500, 
                color: 'var(--text-primary)', 
                marginBottom: '6px' 
              }}>
                Description
              </label>
              <input
                type="text"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="Brief description"
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  fontSize: '13px',
                  border: '1px solid var(--border-primary)',
                  borderRadius: 'var(--radius)',
                  background: 'var(--bg-primary)',
                  color: 'var(--text-primary)',
                }}
              />
            </div>

            {/* Purpose */}
            <div>
              <label style={{ 
                display: 'block', 
                fontSize: '13px', 
                fontWeight: 500, 
                color: 'var(--text-primary)', 
                marginBottom: '6px' 
              }}>
                Purpose
              </label>
              <select
                value={formData.purpose}
                onChange={(e) => setFormData({ ...formData, purpose: e.target.value })}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  fontSize: '13px',
                  border: '1px solid var(--border-primary)',
                  borderRadius: 'var(--radius)',
                  background: 'var(--bg-primary)',
                  color: 'var(--text-primary)',
                }}
              >
                <option value="root_ca">Root CA</option>
                <option value="intermediate_ca">Intermediate CA</option>
                <option value="code_signing">Code Signing</option>
                <option value="email">Email Protection</option>
                <option value="custom">Custom</option>
              </select>
            </div>

            {/* Certificate PEM */}
            <div>
              <label style={{ 
                display: 'block', 
                fontSize: '13px', 
                fontWeight: 500, 
                color: 'var(--text-primary)', 
                marginBottom: '6px' 
              }}>
                Certificate (PEM) <span style={{ color: 'var(--status-danger)' }}>*</span>
              </label>
              <div style={{ marginBottom: '8px' }}>
                <input
                  type="file"
                  accept=".pem,.crt,.cer"
                  onChange={handleFileUpload}
                  style={{ fontSize: '13px' }}
                />
              </div>
              <textarea
                value={formData.certificatePem}
                onChange={(e) => setFormData({ ...formData, certificatePem: e.target.value })}
                placeholder="-----BEGIN CERTIFICATE-----&#10;...&#10;-----END CERTIFICATE-----"
                rows={8}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  fontSize: '12px',
                  fontFamily: 'JetBrains Mono, monospace',
                  border: '1px solid var(--border-primary)',
                  borderRadius: 'var(--radius)',
                  background: 'var(--bg-tertiary)',
                  color: 'var(--text-primary)',
                  resize: 'vertical',
                }}
              />
            </div>

            {/* Notes */}
            <div>
              <label style={{ 
                display: 'block', 
                fontSize: '13px', 
                fontWeight: 500, 
                color: 'var(--text-primary)', 
                marginBottom: '6px' 
              }}>
                Notes
              </label>
              <textarea
                value={formData.notes}
                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                placeholder="Additional notes..."
                rows={3}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  fontSize: '13px',
                  border: '1px solid var(--border-primary)',
                  borderRadius: 'var(--radius)',
                  background: 'var(--bg-primary)',
                  color: 'var(--text-primary)',
                  resize: 'vertical',
                }}
              />
            </div>
          </div>
        </Modal.Body>

        <Modal.Footer>
          <Modal.CloseButton onClick={onClose} disabled={addCert.isPending}>
            Cancel
          </Modal.CloseButton>
          <Button 
            type="submit" 
            variant="primary" 
            icon="ph ph-plus"
            disabled={addCert.isPending}
          >
            {addCert.isPending ? 'Adding...' : 'Add to Trust Store'}
          </Button>
        </Modal.Footer>
      </form>
    </Modal>
  );
}
