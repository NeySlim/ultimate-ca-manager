import { useState } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import toast from 'react-hot-toast';
import styles from './SharedModalForm.module.css';

export function CreateACMEOrderModal({ isOpen, onClose }) {
  const [formData, setFormData] = useState({
    domains: '',
    challengeType: 'http-01',
  });

  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!formData.domains.trim()) {
      toast.error('At least one domain is required');
      return;
    }

    const domainList = formData.domains
      .split(',')
      .map(d => d.trim())
      .filter(Boolean);

    if (domainList.length === 0) {
      toast.error('Please enter valid domains');
      return;
    }

    setIsSubmitting(true);

    try {
      const response = await fetch('/api/v2/acme/orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          domains: domainList,
          challenge_type: formData.challengeType,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.message || 'Failed to create ACME order');
      }

      toast.success('ACME order created successfully');
      onClose();
      
      setFormData({
        domains: '',
        challengeType: 'http-01',
      });

      window.location.reload();
    } catch (error) {
      toast.error(error.message || 'Failed to create ACME order');
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
        {isSubmitting ? 'Creating...' : 'Create Order'}
      </Button>
    </>
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="New ACME Order"
      size="md"
      footer={footer}
    >
      <form onSubmit={handleSubmit} className={styles.form}>
        <div className={styles.section}>
          <Input
            label="Domains"
            name="domains"
            value={formData.domains}
            onChange={handleChange}
            placeholder="example.com, www.example.com, *.example.com"
            required
            helpText="Comma-separated list of domains to include in the certificate"
          />

          <div className={styles.field}>
            <label className={styles.label}>Challenge Type</label>
            <select
              name="challengeType"
              value={formData.challengeType}
              onChange={handleChange}
              className={styles.select}
            >
              <option value="http-01">HTTP-01 (Port 80)</option>
              <option value="dns-01">DNS-01 (DNS TXT Record)</option>
              <option value="tls-alpn-01">TLS-ALPN-01 (Port 443)</option>
            </select>
            <p className={styles.helpText}>
              {formData.challengeType === 'http-01' && 
                'Requires HTTP server on port 80. Best for single domains.'}
              {formData.challengeType === 'dns-01' && 
                'Requires DNS access. Required for wildcard certificates.'}
              {formData.challengeType === 'tls-alpn-01' && 
                'Requires TLS server on port 443. Alternative to HTTP-01.'}
            </p>
          </div>
        </div>

        <div className={styles.infoBox}>
          <i className="ph ph-info"></i>
          <div>
            <strong>Next Steps:</strong>
            <ol style={{ marginTop: '8px', paddingLeft: '20px' }}>
              <li>Order will be created and authorizations started</li>
              <li>Complete the {formData.challengeType.toUpperCase()} challenge for each domain</li>
              <li>Certificate will be issued automatically upon validation</li>
            </ol>
          </div>
        </div>
      </form>
    </Modal>
  );
}
