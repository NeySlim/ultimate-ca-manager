import { useState } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { FileUpload } from '../ui/FileUpload';
import toast from 'react-hot-toast';
import styles from './ImportCAModal.module.css';

export function ImportCertificateModal({ isOpen, onClose }) {
  const [file, setFile] = useState(null);
  const [format, setFormat] = useState('pem');
  const [password, setPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!file) {
      toast.error('Please select a file to import');
      return;
    }

    if (format === 'pkcs12' && !password) {
      toast.error('Password is required for PKCS#12 files');
      return;
    }

    setIsSubmitting(true);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('format', format);
      if (password) {
        formData.append('password', password);
      }

      const response = await fetch('/api/v2/certificates/import', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.message || 'Failed to import certificate');
      }

      toast.success('Certificate imported successfully');
      onClose();
      setFile(null);
      setPassword('');
      setFormat('pem');
      
      window.location.reload();
    } catch (error) {
      toast.error(error.message || 'Failed to import certificate');
    } finally {
      setIsSubmitting(false);
    }
  };

  const footer = (
    <>
      <Button variant="secondary" onClick={onClose} disabled={isSubmitting}>
        Cancel
      </Button>
      <Button variant="primary" onClick={handleSubmit} disabled={isSubmitting}>
        {isSubmitting ? 'Importing...' : 'Import Certificate'}
      </Button>
    </>
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Import Certificate"
      size="md"
      footer={footer}
    >
      <form onSubmit={handleSubmit} className={styles.form}>
        <div className={styles.section}>
          <label className={styles.label}>Certificate Format</label>
          <select
            value={format}
            onChange={(e) => setFormat(e.target.value)}
            className={styles.select}
          >
            <option value="pem">PEM (Base64 encoded)</option>
            <option value="der">DER (Binary)</option>
            <option value="pkcs12">PKCS#12 (.p12, .pfx)</option>
          </select>
        </div>

        <FileUpload
          file={file}
          onFileChange={setFile}
          accept=".pem,.crt,.cer,.der,.p12,.pfx"
          maxSize={10 * 1024 * 1024}
        />

        {format === 'pkcs12' && (
          <div className={styles.section}>
            <label className={styles.label}>PKCS#12 Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={styles.input}
              placeholder="Enter PKCS#12 password"
            />
            <p className={styles.helpText}>
              Required to decrypt PKCS#12 files
            </p>
          </div>
        )}
      </form>
    </Modal>
  );
}
