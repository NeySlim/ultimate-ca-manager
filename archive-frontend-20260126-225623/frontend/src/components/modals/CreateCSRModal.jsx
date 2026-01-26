import { useState } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import toast from 'react-hot-toast';
import styles from './SharedModalForm.module.css';

export function CreateCSRModal({ isOpen, onClose }) {
  const [formData, setFormData] = useState({
    commonName: '',
    organization: '',
    organizationalUnit: '',
    country: '',
    state: '',
    locality: '',
    email: '',
    keySize: '2048',
    keyType: 'RSA',
    sans: '', // Subject Alternative Names (comma-separated)
  });

  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!formData.commonName) {
      toast.error('Common Name is required');
      return;
    }

    setIsSubmitting(true);

    try {
      const payload = {
        subject: {
          common_name: formData.commonName,
          organization: formData.organization,
          organizational_unit: formData.organizationalUnit,
          country: formData.country,
          state: formData.state,
          locality: formData.locality,
          email: formData.email,
        },
        key_size: parseInt(formData.keySize),
        key_type: formData.keyType.toLowerCase(),
      };

      // Add SANs if provided
      if (formData.sans.trim()) {
        payload.sans = formData.sans.split(',').map(s => s.trim()).filter(Boolean);
      }

      const response = await fetch('/api/v2/csrs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.message || 'Failed to create CSR');
      }

      toast.success('CSR created successfully');
      onClose();
      
      // Reset form
      setFormData({
        commonName: '',
        organization: '',
        organizationalUnit: '',
        country: '',
        state: '',
        locality: '',
        email: '',
        keySize: '2048',
        keyType: 'RSA',
        sans: '',
      });

      // Refresh list
      window.location.reload();
    } catch (error) {
      toast.error(error.message || 'Failed to create CSR');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleChange = (e) => {
    setFormData(prev => ({
      ...prev,
      [e.target.name]: e.target.value
    }));
  };

  const footer = (
    <>
      <Button variant="secondary" onClick={onClose} disabled={isSubmitting}>
        Cancel
      </Button>
      <Button variant="primary" onClick={handleSubmit} disabled={isSubmitting}>
        {isSubmitting ? 'Creating...' : 'Create CSR'}
      </Button>
    </>
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Create Certificate Signing Request"
      size="md"
      footer={footer}
    >
      <form onSubmit={handleSubmit} className={styles.form}>
        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>Subject Information</h3>
          
          <Input
            label="Common Name (CN)"
            name="commonName"
            value={formData.commonName}
            onChange={handleChange}
            placeholder="example.com"
            required
          />

          <Input
            label="Organization (O)"
            name="organization"
            value={formData.organization}
            onChange={handleChange}
            placeholder="My Organization"
          />

          <Input
            label="Organizational Unit (OU)"
            name="organizationalUnit"
            value={formData.organizationalUnit}
            onChange={handleChange}
            placeholder="IT Department"
          />

          <div className={styles.row}>
            <Input
              label="Country (C)"
              name="country"
              value={formData.country}
              onChange={handleChange}
              placeholder="US"
              maxLength={2}
            />

            <Input
              label="State (ST)"
              name="state"
              value={formData.state}
              onChange={handleChange}
              placeholder="California"
            />

            <Input
              label="Locality (L)"
              name="locality"
              value={formData.locality}
              onChange={handleChange}
              placeholder="San Francisco"
            />
          </div>

          <Input
            label="Email Address"
            name="email"
            type="email"
            value={formData.email}
            onChange={handleChange}
            placeholder="admin@example.com"
          />
        </div>

        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>Key Settings</h3>
          
          <div className={styles.row}>
            <div className={styles.field}>
              <label className={styles.label}>Key Type</label>
              <select
                name="keyType"
                value={formData.keyType}
                onChange={handleChange}
                className={styles.select}
              >
                <option value="RSA">RSA</option>
                <option value="ECDSA">ECDSA</option>
              </select>
            </div>

            <div className={styles.field}>
              <label className={styles.label}>Key Size</label>
              <select
                name="keySize"
                value={formData.keySize}
                onChange={handleChange}
                className={styles.select}
              >
                {formData.keyType === 'RSA' ? (
                  <>
                    <option value="2048">2048 bits</option>
                    <option value="3072">3072 bits</option>
                    <option value="4096">4096 bits</option>
                  </>
                ) : (
                  <>
                    <option value="256">P-256</option>
                    <option value="384">P-384</option>
                    <option value="521">P-521</option>
                  </>
                )}
              </select>
            </div>
          </div>
        </div>

        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>Extensions</h3>
          
          <Input
            label="Subject Alternative Names (SANs)"
            name="sans"
            value={formData.sans}
            onChange={handleChange}
            placeholder="example.com, www.example.com, *.example.com"
            helpText="Comma-separated list of additional domains"
          />
        </div>
      </form>
    </Modal>
  );
}
