import { useState } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { FileUpload } from '../ui/FileUpload';
import toast from 'react-hot-toast';
import styles from './ImportCAModal.module.css';

export function ImportCSRModal({ isOpen, onClose }) {
  const [file, setFile] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!file) {
      toast.error('Please select a CSR file to import');
      return;
    }

    setIsSubmitting(true);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch('/api/v2/csrs/import', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.message || 'Failed to import CSR');
      }

      toast.success('CSR imported successfully');
      onClose();
      setFile(null);
      
      window.location.reload();
    } catch (error) {
      toast.error(error.message || 'Failed to import CSR');
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
        {isSubmitting ? 'Importing...' : 'Import CSR'}
      </Button>
    </>
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Import Certificate Signing Request"
      size="md"
      footer={footer}
    >
      <form onSubmit={handleSubmit} className={styles.form}>
        <FileUpload
          file={file}
          onFileChange={setFile}
          accept=".csr,.pem"
          maxSize={10 * 1024 * 1024}
        />

        <div className={styles.infoBox}>
          <i className="ph ph-info"></i>
          <p>
            CSR files must be in PEM format. After import, you can sign the CSR 
            to issue a certificate.
          </p>
        </div>
      </form>
    </Modal>
  );
}
