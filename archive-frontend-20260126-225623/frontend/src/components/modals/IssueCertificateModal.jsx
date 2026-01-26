import { useState, useEffect } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { SuccessAnimation } from '../ui/SuccessAnimation';
import { useIssueCertificate } from '../../hooks/useCertificates';
import { useCAs } from '../../hooks/useCAs';
import toast from 'react-hot-toast';
import styles from './IssueCertificateModal.module.css';

export function IssueCertificateModal({ isOpen, onClose }) {
  const [showSuccess, setShowSuccess] = useState(false);
  const [formData, setFormData] = useState({
    ca_id: '',
    common_name: '',
    organization: '',
    organizational_unit: '',
    country: '',
    state: '',
    locality: '',
    san: '',
    validity_days: '365',
    key_size: '2048',
    key_usage: ['digitalSignature', 'keyEncipherment'],
  });

  const issueCertificate = useIssueCertificate();
  const { data: casResponse, isLoading: loadingCAs } = useCAs();
  const cas = casResponse?.data || [];

  // Set default CA when CAs are loaded
  useEffect(() => {
    if (cas.length > 0 && !formData.ca_id) {
      setFormData(prev => ({ ...prev, ca_id: cas[0].id.toString() }));
    }
  }, [cas, formData.ca_id]);

  const handleSubmit = (e) => {
    e.preventDefault();
    
    if (!formData.ca_id) {
      toast.error('Please select a Certificate Authority');
      return;
    }
    
    if (!formData.common_name) {
      toast.error('Common Name is required');
      return;
    }

    const payload = {
      ca_id: parseInt(formData.ca_id),
      common_name: formData.common_name,
      organization: formData.organization,
      organizational_unit: formData.organizational_unit,
      country: formData.country,
      state: formData.state,
      locality: formData.locality,
      san: formData.san,
      validity_days: parseInt(formData.validity_days),
      key_size: parseInt(formData.key_size),
      key_usage: formData.key_usage,
    };

    issueCertificate.mutate(payload, {
      onSuccess: () => {
        setShowSuccess(true);
        toast.success('Certificate issued successfully');
        setTimeout(() => {
          onClose();
          setShowSuccess(false);
          resetForm();
        }, 2000);
      },
      onError: (error) => {
        toast.error(`Failed to issue certificate: ${error.message}`);
      },
    });
  };

  const resetForm = () => {
    setFormData({
      ca_id: cas.length > 0 ? cas[0].id.toString() : '',
      common_name: '',
      organization: '',
      organizational_unit: '',
      country: '',
      state: '',
      locality: '',
      san: '',
      validity_days: '365',
      key_size: '2048',
      key_usage: ['digitalSignature', 'keyEncipherment'],
    });
  };

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleKeyUsageToggle = (usage) => {
    setFormData(prev => ({
      ...prev,
      key_usage: prev.key_usage.includes(usage)
        ? prev.key_usage.filter(u => u !== usage)
        : [...prev.key_usage, usage]
    }));
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Issue Certificate"
      size="lg"
      footer={
        <>
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button 
            variant="primary" 
            onClick={handleSubmit}
            disabled={issueCertificate.isPending}
          >
            {issueCertificate.isPending ? 'Issuing...' : 'Issue Certificate'}
          </Button>
        </>
      }
    >
      <form className={styles.form} onSubmit={handleSubmit}>
        {/* CA Selection */}
        <div className={styles.fieldGroup}>
          <label className={styles.label}>Certificate Authority *</label>
          <select
            className={styles.select}
            value={formData.ca_id}
            onChange={(e) => handleChange('ca_id', e.target.value)}
            disabled={loadingCAs}
          >
            {loadingCAs ? (
              <option>Loading CAs...</option>
            ) : cas.length === 0 ? (
              <option>No CAs available</option>
            ) : (
              cas.map(ca => (
                <option key={ca.id} value={ca.id}>
                  {ca.name}
                </option>
              ))
            )}
          </select>
        </div>

        {/* Subject Information */}
        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>Subject Information</h3>
          
          <div className={styles.fieldGroup}>
            <label className={styles.label}>Common Name (CN) *</label>
            <Input
              value={formData.common_name}
              onChange={(e) => handleChange('common_name', e.target.value)}
              placeholder="example.com"
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
                value={formData.organizational_unit}
                onChange={(e) => handleChange('organizational_unit', e.target.value)}
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

          <div className={styles.fieldGroup}>
            <label className={styles.label}>Subject Alternative Names (SAN)</label>
            <Input
              value={formData.san}
              onChange={(e) => handleChange('san', e.target.value)}
              placeholder="DNS:example.com, DNS:*.example.com, IP:192.168.1.1"
            />
            <span className={styles.fieldHint}>Comma-separated list (e.g., DNS:example.com, IP:192.168.1.1)</span>
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
                value={formData.validity_days}
                onChange={(e) => handleChange('validity_days', e.target.value)}
                min="1"
                max="36500"
              />
            </div>
            <div className={styles.fieldGroup}>
              <label className={styles.label}>Key Size (bits)</label>
              <select
                className={styles.select}
                value={formData.key_size}
                onChange={(e) => handleChange('key_size', e.target.value)}
              >
                <option value="2048">2048</option>
                <option value="4096">4096</option>
              </select>
            </div>
          </div>
        </div>

        {/* Key Usage */}
        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>Key Usage</h3>
          
          <div className={styles.checkboxGroup}>
            <label className={styles.checkbox}>
              <input
                type="checkbox"
                checked={formData.key_usage.includes('digitalSignature')}
                onChange={() => handleKeyUsageToggle('digitalSignature')}
              />
              <span>Digital Signature</span>
            </label>
            <label className={styles.checkbox}>
              <input
                type="checkbox"
                checked={formData.key_usage.includes('keyEncipherment')}
                onChange={() => handleKeyUsageToggle('keyEncipherment')}
              />
              <span>Key Encipherment</span>
            </label>
            <label className={styles.checkbox}>
              <input
                type="checkbox"
                checked={formData.key_usage.includes('dataEncipherment')}
                onChange={() => handleKeyUsageToggle('dataEncipherment')}
              />
              <span>Data Encipherment</span>
            </label>
            <label className={styles.checkbox}>
              <input
                type="checkbox"
                checked={formData.key_usage.includes('keyAgreement')}
                onChange={() => handleKeyUsageToggle('keyAgreement')}
              />
              <span>Key Agreement</span>
            </label>
            <label className={styles.checkbox}>
              <input
                type="checkbox"
                checked={formData.key_usage.includes('keyCertSign')}
                onChange={() => handleKeyUsageToggle('keyCertSign')}
              />
              <span>Certificate Signing</span>
            </label>
            <label className={styles.checkbox}>
              <input
                type="checkbox"
                checked={formData.key_usage.includes('crlSign')}
                onChange={() => handleKeyUsageToggle('crlSign')}
              />
              <span>CRL Signing</span>
            </label>
          </div>
        </div>
      </form>

      {showSuccess && (
        <SuccessAnimation
          message="Certificate Issued!"
          onComplete={() => setShowSuccess(false)}
        />
      )}
    </Modal>
  );
}
