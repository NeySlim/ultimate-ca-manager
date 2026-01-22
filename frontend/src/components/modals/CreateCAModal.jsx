import { useState } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { useCreateCA } from '../../hooks/useCAs';
import toast from 'react-hot-toast';
import styles from './CreateCAModal.module.css';

export function CreateCAModal({ isOpen, onClose }) {
  const [formData, setFormData] = useState({
    commonName: '',
    organization: '',
    organizationalUnit: '',
    country: '',
    state: '',
    locality: '',
    validityDays: '3650',
    keySize: '2048',
    isRoot: true,
  });

  const createCA = useCreateCA();

  const handleSubmit = (e) => {
    e.preventDefault();
    
    if (!formData.commonName) {
      toast.error('Common Name is required');
      return;
    }

    createCA.mutate({
      common_name: formData.commonName,
      organization: formData.organization,
      organizational_unit: formData.organizationalUnit,
      country: formData.country,
      state: formData.state,
      locality: formData.locality,
      validity_days: parseInt(formData.validityDays),
      key_size: parseInt(formData.keySize),
      is_root: formData.isRoot,
    }, {
      onSuccess: () => {
        toast.success('CA created successfully');
        onClose();
        setFormData({
          commonName: '',
          organization: '',
          organizationalUnit: '',
          country: '',
          state: '',
          locality: '',
          validityDays: '3650',
          keySize: '2048',
          isRoot: true,
        });
      },
      onError: (error) => {
        toast.error(`Failed to create CA: ${error.message}`);
      },
    });
  };

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Create Certificate Authority"
      size="lg"
      footer={
        <>
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button 
            variant="primary" 
            onClick={handleSubmit}
            disabled={createCA.isPending}
          >
            {createCA.isPending ? 'Creating...' : 'Create CA'}
          </Button>
        </>
      }
    >
      <form className={styles.form} onSubmit={handleSubmit}>
        {/* Type Selection */}
        <div className={styles.fieldGroup}>
          <label className={styles.label}>CA Type</label>
          <div className={styles.radioGroup}>
            <label className={styles.radio}>
              <input
                type="radio"
                checked={formData.isRoot}
                onChange={() => handleChange('isRoot', true)}
              />
              <span>Root CA</span>
            </label>
            <label className={styles.radio}>
              <input
                type="radio"
                checked={!formData.isRoot}
                onChange={() => handleChange('isRoot', false)}
              />
              <span>Intermediate CA</span>
            </label>
          </div>
        </div>

        {/* Subject Information */}
        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>Subject Information</h3>
          
          <div className={styles.fieldGroup}>
            <label className={styles.label}>Common Name (CN) *</label>
            <Input
              value={formData.commonName}
              onChange={(e) => handleChange('commonName', e.target.value)}
              placeholder="My Root CA"
              required
            />
          </div>

          <div className={styles.fieldRow}>
            <div className={styles.fieldGroup}>
              <label className={styles.label}>Organization (O)</label>
              <Input
                value={formData.organization}
                onChange={(e) => handleChange('organization', e.target.value)}
                placeholder="My Company"
              />
            </div>
            <div className={styles.fieldGroup}>
              <label className={styles.label}>Organizational Unit (OU)</label>
              <Input
                value={formData.organizationalUnit}
                onChange={(e) => handleChange('organizationalUnit', e.target.value)}
                placeholder="IT Department"
              />
            </div>
          </div>

          <div className={styles.fieldRow}>
            <div className={styles.fieldGroup}>
              <label className={styles.label}>Country (C)</label>
              <Input
                value={formData.country}
                onChange={(e) => handleChange('country', e.target.value)}
                placeholder="US"
                maxLength={2}
              />
            </div>
            <div className={styles.fieldGroup}>
              <label className={styles.label}>State/Province (ST)</label>
              <Input
                value={formData.state}
                onChange={(e) => handleChange('state', e.target.value)}
                placeholder="California"
              />
            </div>
            <div className={styles.fieldGroup}>
              <label className={styles.label}>City/Locality (L)</label>
              <Input
                value={formData.locality}
                onChange={(e) => handleChange('locality', e.target.value)}
                placeholder="San Francisco"
              />
            </div>
          </div>
        </div>

        {/* Settings */}
        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>Settings</h3>
          
          <div className={styles.fieldRow}>
            <div className={styles.fieldGroup}>
              <label className={styles.label}>Validity (days)</label>
              <Input
                type="number"
                value={formData.validityDays}
                onChange={(e) => handleChange('validityDays', e.target.value)}
                min="1"
                max="36500"
              />
            </div>
            <div className={styles.fieldGroup}>
              <label className={styles.label}>Key Size (bits)</label>
              <select
                className={styles.select}
                value={formData.keySize}
                onChange={(e) => handleChange('keySize', e.target.value)}
              >
                <option value="2048">2048</option>
                <option value="4096">4096</option>
              </select>
            </div>
          </div>
        </div>
      </form>
    </Modal>
  );
}
