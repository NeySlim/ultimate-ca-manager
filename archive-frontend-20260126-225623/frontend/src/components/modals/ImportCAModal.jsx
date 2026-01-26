import { useState } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { FileUpload } from '../ui/FileUpload';
import api from '../../services/api/api';
import toast from 'react-hot-toast';
import styles from './ImportCAModal.module.css';

export function ImportCAModal({ isOpen, onClose, onSuccess }) {
  const [file, setFile] = useState(null);
  const [format, setFormat] = useState('PEM');
  const [password, setPassword] = useState('');
  const [fileError, setFileError] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [preview, setPreview] = useState(null);

  const handleFileChange = (newFile, error) => {
    setFile(newFile);
    setFileError(error);
    setPreview(null);

    // Try to preview the file if it's PEM
    if (newFile && format === 'PEM') {
      const reader = new FileReader();
      reader.onload = (e) => {
        const content = e.target.result;
        if (content.includes('BEGIN CERTIFICATE')) {
          // Extract basic info from PEM
          const lines = content.split('\n');
          const certStart = lines.findIndex(l => l.includes('BEGIN CERTIFICATE'));
          const certEnd = lines.findIndex(l => l.includes('END CERTIFICATE'));
          if (certStart >= 0 && certEnd > certStart) {
            setPreview({
              type: 'PEM Certificate',
              lines: certEnd - certStart + 1,
              size: newFile.size,
            });
          }
        }
      };
      reader.readAsText(newFile);
    }
  };

  const handleUpload = async () => {
    if (!file) {
      toast.error('Please select a file to upload');
      return;
    }

    if (format === 'PKCS12' && !password) {
      toast.error('Password is required for PKCS12 format');
      return;
    }

    setIsUploading(true);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('format', format);
    if (password) {
      formData.append('password', password);
    }

    try {
      const response = await api.post('/api/v2/certificates/import', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      
      toast.success('CA imported successfully');
      
      // Reset form
      setFile(null);
      setFormat('PEM');
      setPassword('');
      setPreview(null);
      setFileError(null);
      
      // Call success callback and close
      if (onSuccess) onSuccess(response);
      onClose();
    } catch (error) {
      toast.error(`Import failed: ${error.message || 'Unknown error'}`);
    } finally {
      setIsUploading(false);
    }
  };

  const handleClose = () => {
    if (!isUploading) {
      setFile(null);
      setFormat('PEM');
      setPassword('');
      setPreview(null);
      setFileError(null);
      onClose();
    }
  };

  const acceptedFormats = {
    'PEM': '.pem,.crt,.cer',
    'DER': '.der,.cer',
    'PKCS12': '.p12,.pfx'
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Import Certificate Authority"
      size="lg"
      footer={
        <>
          <Button 
            variant="default" 
            onClick={handleClose}
            disabled={isUploading}
          >
            Cancel
          </Button>
          <Button 
            variant="primary" 
            onClick={handleUpload}
            disabled={!file || isUploading || !!fileError}
          >
            {isUploading ? 'Importing...' : 'Import CA'}
          </Button>
        </>
      }
    >
      <div className={styles.form}>
        {/* Format Selector */}
        <div className={styles.fieldGroup}>
          <label className={styles.label}>Certificate Format</label>
          <div className={styles.formatSelector}>
            {['PEM', 'DER', 'PKCS12'].map((fmt) => (
              <label key={fmt} className={styles.formatOption}>
                <input
                  type="radio"
                  name="format"
                  value={fmt}
                  checked={format === fmt}
                  onChange={(e) => {
                    setFormat(e.target.value);
                    setFile(null);
                    setPreview(null);
                  }}
                  disabled={isUploading}
                />
                <span className={styles.formatLabel}>{fmt}</span>
                <span className={styles.formatHint}>
                  {fmt === 'PEM' && 'Base64 encoded, most common'}
                  {fmt === 'DER' && 'Binary format'}
                  {fmt === 'PKCS12' && 'Password protected bundle'}
                </span>
              </label>
            ))}
          </div>
        </div>

        {/* File Upload */}
        <div className={styles.fieldGroup}>
          <label className={styles.label}>Certificate File</label>
          <FileUpload
            value={file}
            onChange={handleFileChange}
            accept={acceptedFormats[format]}
            maxSize={5 * 1024 * 1024} // 5MB
            disabled={isUploading}
            error={fileError}
          />
        </div>

        {/* Password (for PKCS12) */}
        {format === 'PKCS12' && (
          <div className={styles.fieldGroup}>
            <label className={styles.label}>Password</label>
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter PKCS12 password"
              disabled={isUploading}
            />
          </div>
        )}

        {/* Preview */}
        {preview && (
          <div className={styles.preview}>
            <h4 className={styles.previewTitle}>Certificate Preview</h4>
            <div className={styles.previewContent}>
              <div className={styles.previewRow}>
                <span className={styles.previewLabel}>Type:</span>
                <span className={styles.previewValue}>{preview.type}</span>
              </div>
              <div className={styles.previewRow}>
                <span className={styles.previewLabel}>Size:</span>
                <span className={styles.previewValue}>{preview.size} bytes</span>
              </div>
              {preview.lines && (
                <div className={styles.previewRow}>
                  <span className={styles.previewLabel}>Lines:</span>
                  <span className={styles.previewValue}>{preview.lines}</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Help Text */}
        <div className={styles.helpText}>
          <p>
            <strong>Note:</strong> The CA certificate will be validated and imported into the system.
            Make sure the file format matches the selected type.
          </p>
        </div>
      </div>
    </Modal>
  );
}
