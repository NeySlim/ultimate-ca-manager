import { useState } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { SuccessAnimation } from '../ui/SuccessAnimation';
import toast from 'react-hot-toast';
import styles from './SharedModalForm.module.css';

export function CreateUserModal({ isOpen, onClose }) {
  const [showSuccess, setShowSuccess] = useState(false);
  const [formData, setFormData] = useState({
    username: '',
    password: '',
    confirmPassword: '',
    email: '',
    fullName: '',
    role: 'operator',
    permissions: {
      manageCAs: false,
      issueCertificates: true,
      revokeCertificates: false,
      manageUsers: false,
      viewLogs: true,
      manageSettings: false,
    },
  });

  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!formData.username || !formData.password) {
      toast.error('Username and password are required');
      return;
    }

    if (formData.password !== formData.confirmPassword) {
      toast.error('Passwords do not match');
      return;
    }

    if (formData.password.length < 8) {
      toast.error('Password must be at least 8 characters');
      return;
    }

    setIsSubmitting(true);

    try {
      const response = await fetch('/api/v2/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: formData.username,
          password: formData.password,
          email: formData.email,
          full_name: formData.fullName,
          role: formData.role,
          permissions: formData.permissions,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.message || 'Failed to create user');
      }

      setShowSuccess(true);
      toast.success('User created successfully');
      setTimeout(() => {
        onClose();
        setShowSuccess(false);
        setFormData({
          username: '',
          password: '',
          confirmPassword: '',
          email: '',
          fullName: '',
          role: 'operator',
          permissions: {
            manageCAs: false,
            issueCertificates: true,
            revokeCertificates: false,
            manageUsers: false,
            viewLogs: true,
            manageSettings: false,
          },
        });
        window.location.reload();
      }, 2000);
    } catch (error) {
      toast.error(error.message || 'Failed to create user');
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

  const handlePermissionChange = (permission) => {
    setFormData(prev => ({
      ...prev,
      permissions: {
        ...prev.permissions,
        [permission]: !prev.permissions[permission]
      }
    }));
  };

  const handleRoleChange = (e) => {
    const role = e.target.value;
    let permissions = { ...formData.permissions };

    // Preset permissions based on role
    if (role === 'admin') {
      permissions = {
        manageCAs: true,
        issueCertificates: true,
        revokeCertificates: true,
        manageUsers: true,
        viewLogs: true,
        manageSettings: true,
      };
    } else if (role === 'operator') {
      permissions = {
        manageCAs: false,
        issueCertificates: true,
        revokeCertificates: false,
        manageUsers: false,
        viewLogs: true,
        manageSettings: false,
      };
    } else if (role === 'viewer') {
      permissions = {
        manageCAs: false,
        issueCertificates: false,
        revokeCertificates: false,
        manageUsers: false,
        viewLogs: true,
        manageSettings: false,
      };
    }

    setFormData(prev => ({
      ...prev,
      role,
      permissions
    }));
  };

  const footer = (
    <>
      <Button variant="secondary" onClick={onClose} disabled={isSubmitting}>
        Cancel
      </Button>
      <Button variant="primary" onClick={handleSubmit} disabled={isSubmitting}>
        {isSubmitting ? 'Creating...' : 'Create User'}
      </Button>
    </>
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Create User"
      size="md"
      footer={footer}
    >
      <form onSubmit={handleSubmit} className={styles.form}>
        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>Account Information</h3>
          
          <Input
            label="Username"
            name="username"
            value={formData.username}
            onChange={handleChange}
            placeholder="john.doe"
            required
          />

          <Input
            label="Full Name"
            name="fullName"
            value={formData.fullName}
            onChange={handleChange}
            placeholder="John Doe"
          />

          <Input
            label="Email Address"
            name="email"
            type="email"
            value={formData.email}
            onChange={handleChange}
            placeholder="john.doe@example.com"
          />
        </div>

        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>Security</h3>
          
          <Input
            label="Password"
            name="password"
            type="password"
            value={formData.password}
            onChange={handleChange}
            placeholder="••••••••"
            required
            helpText="Minimum 8 characters"
          />

          <Input
            label="Confirm Password"
            name="confirmPassword"
            type="password"
            value={formData.confirmPassword}
            onChange={handleChange}
            placeholder="••••••••"
            required
          />
        </div>

        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>Role & Permissions</h3>
          
          <div className={styles.field}>
            <label className={styles.label}>Role</label>
            <select
              name="role"
              value={formData.role}
              onChange={handleRoleChange}
              className={styles.select}
            >
              <option value="admin">Administrator</option>
              <option value="operator">Operator</option>
              <option value="viewer">Viewer</option>
            </select>
            <p className={styles.helpText}>
              {formData.role === 'admin' && 'Full access to all features'}
              {formData.role === 'operator' && 'Can issue and manage certificates'}
              {formData.role === 'viewer' && 'Read-only access'}
            </p>
          </div>

          <div className={styles.permissionsGrid}>
            <label className={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={formData.permissions.manageCAs}
                onChange={() => handlePermissionChange('manageCAs')}
                className={styles.checkbox}
              />
              <span>Manage CAs</span>
            </label>

            <label className={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={formData.permissions.issueCertificates}
                onChange={() => handlePermissionChange('issueCertificates')}
                className={styles.checkbox}
              />
              <span>Issue Certificates</span>
            </label>

            <label className={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={formData.permissions.revokeCertificates}
                onChange={() => handlePermissionChange('revokeCertificates')}
                className={styles.checkbox}
              />
              <span>Revoke Certificates</span>
            </label>

            <label className={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={formData.permissions.manageUsers}
                onChange={() => handlePermissionChange('manageUsers')}
                className={styles.checkbox}
              />
              <span>Manage Users</span>
            </label>

            <label className={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={formData.permissions.viewLogs}
                onChange={() => handlePermissionChange('viewLogs')}
                className={styles.checkbox}
              />
              <span>View Logs</span>
            </label>

            <label className={styles.checkboxLabel}>
              <input
                type="checkbox"
                checked={formData.permissions.manageSettings}
                onChange={() => handlePermissionChange('manageSettings')}
                className={styles.checkbox}
              />
              <span>Manage Settings</span>
            </label>
          </div>
        </div>
      </form>

      {showSuccess && (
        <SuccessAnimation
          message="User Created!"
          onComplete={() => setShowSuccess(false)}
        />
      )}
    </Modal>
  );
}
