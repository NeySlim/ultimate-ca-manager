import { useState } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import toast from 'react-hot-toast';
import styles from './CreateCAModal.module.css';

export function CreateTemplateModal({ isOpen, onClose }) {
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    type: 'server',
    validityDays: '365',
    keySize: '2048',
    keyUsage: {
      digitalSignature: true,
      keyEncipherment: true,
      dataEncipherment: false,
      keyAgreement: false,
      keyCertSign: false,
      crlSign: false,
    },
    extendedKeyUsage: {
      serverAuth: false,
      clientAuth: false,
      codeSigning: false,
      emailProtection: false,
      timeStamping: false,
    },
  });

  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!formData.name) {
      toast.error('Template name is required');
      return;
    }

    setIsSubmitting(true);

    try {
      const keyUsageList = Object.entries(formData.keyUsage)
        .filter(([_, enabled]) => enabled)
        .map(([key, _]) => key);

      const extendedKeyUsageList = Object.entries(formData.extendedKeyUsage)
        .filter(([_, enabled]) => enabled)
        .map(([key, _]) => key);

      const response = await fetch('/api/v2/templates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: formData.name,
          description: formData.description,
          type: formData.type,
          validity_days: parseInt(formData.validityDays),
          key_size: parseInt(formData.keySize),
          key_usage: keyUsageList,
          extended_key_usage: extendedKeyUsageList,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.message || 'Failed to create template');
      }

      toast.success('Template created successfully');
      onClose();
      
      setFormData({
        name: '',
        description: '',
        type: 'server',
        validityDays: '365',
        keySize: '2048',
        keyUsage: {
          digitalSignature: true,
          keyEncipherment: true,
          dataEncipherment: false,
          keyAgreement: false,
          keyCertSign: false,
          crlSign: false,
        },
        extendedKeyUsage: {
          serverAuth: false,
          clientAuth: false,
          codeSigning: false,
          emailProtection: false,
          timeStamping: false,
        },
      });

      window.location.reload();
    } catch (error) {
      toast.error(error.message || 'Failed to create template');
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

  const handleKeyUsageChange = (usage) => {
    setFormData(prev => ({
      ...prev,
      keyUsage: {
        ...prev.keyUsage,
        [usage]: !prev.keyUsage[usage]
      }
    }));
  };

  const handleExtendedKeyUsageChange = (usage) => {
    setFormData(prev => ({
      ...prev,
      extendedKeyUsage: {
        ...prev.extendedKeyUsage,
        [usage]: !prev.extendedKeyUsage[usage]
      }
    }));
  };

  const handleTypeChange = (e) => {
    const type = e.target.value;
    let keyUsage = { ...formData.keyUsage };
    let extendedKeyUsage = { ...formData.extendedKeyUsage };

    // Preset based on type
    if (type === 'server') {
      keyUsage = {
        digitalSignature: true,
        keyEncipherment: true,
        dataEncipherment: false,
        keyAgreement: false,
        keyCertSign: false,
        crlSign: false,
      };
      extendedKeyUsage = {
        serverAuth: true,
        clientAuth: false,
        codeSigning: false,
        emailProtection: false,
        timeStamping: false,
      };
    } else if (type === 'client') {
      keyUsage = {
        digitalSignature: true,
        keyEncipherment: true,
        dataEncipherment: false,
        keyAgreement: false,
        keyCertSign: false,
        crlSign: false,
      };
      extendedKeyUsage = {
        serverAuth: false,
        clientAuth: true,
        codeSigning: false,
        emailProtection: false,
        timeStamping: false,
      };
    } else if (type === 'ca') {
      keyUsage = {
        digitalSignature: true,
        keyEncipherment: false,
        dataEncipherment: false,
        keyAgreement: false,
        keyCertSign: true,
        crlSign: true,
      };
      extendedKeyUsage = {
        serverAuth: false,
        clientAuth: false,
        codeSigning: false,
        emailProtection: false,
        timeStamping: false,
      };
    }

    setFormData(prev => ({
      ...prev,
      type,
      keyUsage,
      extendedKeyUsage
    }));
  };

  const footer = (
    <>
      <Button variant="secondary" onClick={onClose} disabled={isSubmitting}>
        Cancel
      </Button>
      <Button variant="primary" onClick={handleSubmit} disabled={isSubmitting}>
        {isSubmitting ? 'Creating...' : 'Create Template'}
      </Button>
    </>
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="New Certificate Template"
      size="md"
      footer={footer}
    >
      <form onSubmit={handleSubmit} className={styles.form}>
        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>Template Information</h3>
          
          <Input
            label="Template Name"
            name="name"
            value={formData.name}
            onChange={handleChange}
            placeholder="Web Server Template"
            required
          />

          <Input
            label="Description"
            name="description"
            value={formData.description}
            onChange={handleChange}
            placeholder="Template for web server certificates"
          />

          <div className={styles.field}>
            <label className={styles.label}>Template Type</label>
            <select
              name="type"
              value={formData.type}
              onChange={handleTypeChange}
              className={styles.select}
            >
              <option value="server">Server Authentication</option>
              <option value="client">Client Authentication</option>
              <option value="ca">Certificate Authority</option>
              <option value="code-signing">Code Signing</option>
              <option value="email">Email Protection</option>
            </select>
          </div>
        </div>

        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>Certificate Settings</h3>
          
          <div className={styles.row}>
            <Input
              label="Validity Period (Days)"
              name="validityDays"
              type="number"
              value={formData.validityDays}
              onChange={handleChange}
              min="1"
              max="3650"
            />

            <div className={styles.field}>
              <label className={styles.label}>Key Size</label>
              <select
                name="keySize"
                value={formData.keySize}
                onChange={handleChange}
                className={styles.select}
              >
                <option value="2048">2048 bits</option>
                <option value="3072">3072 bits</option>
                <option value="4096">4096 bits</option>
              </select>
            </div>
          </div>
        </div>

        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>Key Usage</h3>
          
          <div className={styles.permissionsGrid}>
            <label className={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={formData.keyUsage.digitalSignature}
                onChange={() => handleKeyUsageChange('digitalSignature')}
                className={styles.checkbox}
              />
              <span>Digital Signature</span>
            </label>

            <label className={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={formData.keyUsage.keyEncipherment}
                onChange={() => handleKeyUsageChange('keyEncipherment')}
                className={styles.checkbox}
              />
              <span>Key Encipherment</span>
            </label>

            <label className={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={formData.keyUsage.dataEncipherment}
                onChange={() => handleKeyUsageChange('dataEncipherment')}
                className={styles.checkbox}
              />
              <span>Data Encipherment</span>
            </label>

            <label className={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={formData.keyUsage.keyAgreement}
                onChange={() => handleKeyUsageChange('keyAgreement')}
                className={styles.checkbox}
              />
              <span>Key Agreement</span>
            </label>

            <label className={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={formData.keyUsage.keyCertSign}
                onChange={() => handleKeyUsageChange('keyCertSign')}
                className={styles.checkbox}
              />
              <span>Certificate Sign</span>
            </label>

            <label className={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={formData.keyUsage.crlSign}
                onChange={() => handleKeyUsageChange('crlSign')}
                className={styles.checkbox}
              />
              <span>CRL Sign</span>
            </label>
          </div>
        </div>

        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>Extended Key Usage</h3>
          
          <div className={styles.permissionsGrid}>
            <label className={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={formData.extendedKeyUsage.serverAuth}
                onChange={() => handleExtendedKeyUsageChange('serverAuth')}
                className={styles.checkbox}
              />
              <span>TLS Web Server Authentication</span>
            </label>

            <label className={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={formData.extendedKeyUsage.clientAuth}
                onChange={() => handleExtendedKeyUsageChange('clientAuth')}
                className={styles.checkbox}
              />
              <span>TLS Web Client Authentication</span>
            </label>

            <label className={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={formData.extendedKeyUsage.codeSigning}
                onChange={() => handleExtendedKeyUsageChange('codeSigning')}
                className={styles.checkbox}
              />
              <span>Code Signing</span>
            </label>

            <label className={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={formData.extendedKeyUsage.emailProtection}
                onChange={() => handleExtendedKeyUsageChange('emailProtection')}
                className={styles.checkbox}
              />
              <span>Email Protection</span>
            </label>

            <label className={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={formData.extendedKeyUsage.timeStamping}
                onChange={() => handleExtendedKeyUsageChange('timeStamping')}
                className={styles.checkbox}
              />
              <span>Time Stamping</span>
            </label>
          </div>
        </div>
      </form>
    </Modal>
  );
}
