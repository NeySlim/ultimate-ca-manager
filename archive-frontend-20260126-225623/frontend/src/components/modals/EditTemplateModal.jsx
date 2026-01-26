import { useState, useEffect } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import toast from 'react-hot-toast';
import { useTemplateDetails, useUpdateTemplate } from '../../hooks/useTemplates';

export function EditTemplateModal({ isOpen, onClose, templateId }) {
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    validityDays: 397,
    keyType: 'RSA-2048',
    digest: 'sha256',
    isActive: true,
  });

  const { data: templateData } = useTemplateDetails(templateId);
  const updateTemplate = useUpdateTemplate();

  useEffect(() => {
    if (templateData?.data) {
      const template = templateData.data;
      setFormData({
        name: template.name || '',
        description: template.description || '',
        validityDays: template.validity_days || 397,
        keyType: template.key_type || 'RSA-2048',
        digest: template.digest || 'sha256',
        isActive: template.is_active !== false,
      });
    }
  }, [templateData]);

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!formData.name) {
      toast.error('Template name is required');
      return;
    }

    updateTemplate.mutate({
      id: templateId,
      name: formData.name,
      description: formData.description,
      validity_days: parseInt(formData.validityDays),
      key_type: formData.keyType,
      digest: formData.digest,
      is_active: formData.isActive,
    }, {
      onSuccess: () => {
        onClose();
      },
    });
  };

  if (!templateId) return null;

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="medium">
      <Modal.Header>
        <i className="ph ph-pencil-simple" style={{ marginRight: '8px' }} />
        Edit Template
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
                Template Name <span style={{ color: 'var(--status-danger)' }}>*</span>
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
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
              <textarea
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
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

            {/* Validity Days */}
            <div>
              <label style={{ 
                display: 'block', 
                fontSize: '13px', 
                fontWeight: 500, 
                color: 'var(--text-primary)', 
                marginBottom: '6px' 
              }}>
                Validity (Days)
              </label>
              <input
                type="number"
                value={formData.validityDays}
                onChange={(e) => setFormData({ ...formData, validityDays: e.target.value })}
                min="1"
                max="3650"
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

            {/* Key Type */}
            <div>
              <label style={{ 
                display: 'block', 
                fontSize: '13px', 
                fontWeight: 500, 
                color: 'var(--text-primary)', 
                marginBottom: '6px' 
              }}>
                Key Type
              </label>
              <select
                value={formData.keyType}
                onChange={(e) => setFormData({ ...formData, keyType: e.target.value })}
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
                <option value="RSA-2048">RSA 2048</option>
                <option value="RSA-4096">RSA 4096</option>
                <option value="ECDSA-P256">ECDSA P-256</option>
                <option value="ECDSA-P384">ECDSA P-384</option>
              </select>
            </div>

            {/* Digest */}
            <div>
              <label style={{ 
                display: 'block', 
                fontSize: '13px', 
                fontWeight: 500, 
                color: 'var(--text-primary)', 
                marginBottom: '6px' 
              }}>
                Signature Algorithm
              </label>
              <select
                value={formData.digest}
                onChange={(e) => setFormData({ ...formData, digest: e.target.value })}
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
                <option value="sha256">SHA-256</option>
                <option value="sha384">SHA-384</option>
                <option value="sha512">SHA-512</option>
              </select>
            </div>

            {/* Active Status */}
            <div>
              <label style={{ 
                display: 'flex',
                alignItems: 'center',
                fontSize: '13px', 
                fontWeight: 500, 
                color: 'var(--text-primary)',
                cursor: 'pointer',
              }}>
                <input
                  type="checkbox"
                  checked={formData.isActive}
                  onChange={(e) => setFormData({ ...formData, isActive: e.target.checked })}
                  style={{ marginRight: '8px' }}
                />
                Active Template
              </label>
            </div>
          </div>
        </Modal.Body>

        <Modal.Footer>
          <Modal.CloseButton onClick={onClose} disabled={updateTemplate.isPending}>
            Cancel
          </Modal.CloseButton>
          <Button 
            type="submit" 
            variant="primary" 
            icon="ph ph-check"
            disabled={updateTemplate.isPending}
          >
            {updateTemplate.isPending ? 'Saving...' : 'Save Changes'}
          </Button>
        </Modal.Footer>
      </form>
    </Modal>
  );
}
