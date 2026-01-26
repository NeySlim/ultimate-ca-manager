import { useState } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import toast from 'react-hot-toast';
import styles from './SharedModalForm.module.css';

export function CreateACMEAccountModal({ isOpen, onClose }) {
  const [formData, setFormData] = useState({
    email: '',
    provider: 'letsencrypt',
    termsAccepted: false,
  });

  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!formData.email) {
      toast.error('Email is required');
      return;
    }

    if (!formData.termsAccepted) {
      toast.error('You must accept the terms of service');
      return;
    }

    setIsSubmitting(true);

    try {
      const response = await fetch('/api/v2/acme/accounts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: formData.email,
          provider: formData.provider,
          terms_accepted: formData.termsAccepted,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.message || 'Failed to create ACME account');
      }

      toast.success('ACME account created successfully');
      onClose();
      
      setFormData({
        email: '',
        provider: 'letsencrypt',
        termsAccepted: false,
      });

      window.location.reload();
    } catch (error) {
      toast.error(error.message || 'Failed to create ACME account');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const footer = (
    <>
      <Button variant="secondary" onClick={onClose} disabled={isSubmitting}>
        Cancel
      </Button>
      <Button variant="primary" onClick={handleSubmit} disabled={isSubmitting}>
        {isSubmitting ? 'Creating...' : 'Create Account'}
      </Button>
    </>
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="New ACME Account"
      size="sm"
      footer={footer}
    >
      <form onSubmit={handleSubmit} className={styles.form}>
        <div className={styles.section}>
          <div className={styles.field}>
            <label className={styles.label}>Provider</label>
            <select
              name="provider"
              value={formData.provider}
              onChange={handleChange}
              className={styles.select}
            >
              <option value="letsencrypt">Let's Encrypt</option>
              <option value="letsencrypt-staging">Let's Encrypt (Staging)</option>
              <option value="buypass">Buypass</option>
              <option value="zerossl">ZeroSSL</option>
            </select>
            <p className={styles.helpText}>
              Let's Encrypt is recommended for production use
            </p>
          </div>

          <Input
            label="Email Address"
            name="email"
            type="email"
            value={formData.email}
            onChange={handleChange}
            placeholder="admin@example.com"
            required
            helpText="Used for certificate expiry notifications and account recovery"
          />

          <div className={styles.field}>
            <label className={styles.checkboxLabel}>
              <input
                type="checkbox"
                name="termsAccepted"
                checked={formData.termsAccepted}
                onChange={handleChange}
                className={styles.checkbox}
              />
              <span>
                I agree to the{' '}
                <a
                  href={
                    formData.provider === 'letsencrypt' 
                      ? 'https://letsencrypt.org/repository/' 
                      : '#'
                  }
                  target="_blank"
                  rel="noopener noreferrer"
                  className={styles.link}
                >
                  {formData.provider === 'letsencrypt' 
                    ? "Let's Encrypt Subscriber Agreement" 
                    : 'Terms of Service'}
                </a>
              </span>
            </label>
          </div>
        </div>
      </form>
    </Modal>
  );
}
